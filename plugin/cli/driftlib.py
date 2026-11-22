"""Classify code references in vault documents against git history.

A code reference is `path:N`, `path:N-M` or a comma list of those, written
inside an inline code span or a fenced code block. For each cited line range
the scan finds a base commit (the commit that last changed the citing line, or
the commit that added the citing document), diffs the cited path from that
base to HEAD, and reports how the range fared: unchanged, changed-elsewhere,
shifted, changed, moved, missing, unclassifiable or malformed.

Git calls are batched: one `git blame` per citing document, one `git diff`
per base commit covering every cited path, one `git log` per base commit that
has deleted paths, and one long-lived `git cat-file --batch` for blob reads.
Independent calls run on a thread pool. The working tree is never consulted
for cited paths; documents are read from the working tree so line numbers
match what a human sees, and uncommitted citing lines are unclassifiable.
"""

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CLASSES = (
    "unchanged", "changed-elsewhere", "shifted", "changed",
    "moved", "missing", "unclassifiable", "malformed",
)

SKIPPED_VAULT_DIRS = ("archive", "tmp")
ZERO_SHA = "0" * 40

_REF = re.compile(
    r"(?P<path>[\w.\-/@+]+):(?P<spec>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)"
)
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")
_SHA = re.compile(r"^[0-9a-f]{40}$")

_ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
_MAX_ARG_CHARS = 16000
_MAX_BLAME_RANGES = 150
_MAX_DIGITS = 9


def scan_refs(repo_root, vault_dir, base_from="blame"):
    """Return one classified record per code reference found under `vault_dir`.

    `base_from` is "blame" (base = commit that last changed the citing line)
    or "add" (base = commit that added the citing document). Records are
    sorted by (file, line, ref_start).
    """
    if base_from not in ("blame", "add"):
        raise ValueError(f"base_from must be 'blame' or 'add', got {base_from!r}")
    repo = str(repo_root)
    tops = _top_level_entries(repo)
    refs = _collect_refs(repo, Path(vault_dir), tops)
    head = _rev_parse(repo, "HEAD")
    workers = max(2, min(8, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        bases = _resolve_bases(repo, refs, base_from, head, pool)
        diffs, renames = _gather_history(repo, refs, bases, head, pool)
    blobs = _Blobs(repo)
    try:
        records = [
            _classify(ref, bases.get((ref["file"], ref["line"])), head,
                      diffs, renames, blobs)
            for ref in refs
        ]
    finally:
        blobs.close()
    records.sort(key=lambda rec: (rec["file"], rec["line"], rec["ref_start"]))
    return records


def _git(repo, *args):
    done = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", repo, *args],
        capture_output=True, env=_ENV,
    )
    return done.returncode, done.stdout.decode("utf-8", "replace")


def _rev_parse(repo, rev):
    code, out = _git(repo, "rev-parse", "--verify", "--quiet", rev + "^{commit}")
    out = out.strip()
    return out if code == 0 and _SHA.match(out) else None


def _top_level_entries(repo):
    code, out = _git(repo, "ls-files", "-z")
    if code != 0:
        return set()
    return {name.split("/", 1)[0] for name in out.split("\0") if name}


def _split_lines(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def _chunks(items, limit=_MAX_ARG_CHARS):
    chunk, size = [], 0
    for item in items:
        if chunk and size + len(item) + 1 > limit:
            yield chunk
            chunk, size = [], 0
        chunk.append(item)
        size += len(item) + 1
    if chunk:
        yield chunk


# Extraction ---------------------------------------------------------------


def _vault_documents(vault_dir):
    root = os.fspath(vault_dir)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        if os.path.relpath(dirpath, root) == ".":
            dirnames[:] = [d for d in dirnames if d not in SKIPPED_VAULT_DIRS]
        dirnames.sort()
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                found.append(os.path.join(dirpath, name))
    return found


def _reference_tokens(line, in_fence):
    if in_fence:
        yield from line.split()
        return
    for match in _SPAN.finditer(line):
        yield from match.group(2).split()


def _parse_token(token, tops):
    token = token.strip("(['\"").rstrip(".,;:)]'\"")
    match = _REF.fullmatch(token)
    if not match:
        return None
    path = match.group("path")
    norm = path[2:] if path.startswith("./") else path
    if not norm or norm.endswith("/") or norm.split("/", 1)[0] not in tops:
        return None
    return path, norm, match.group("spec")


def _ranges(spec):
    """Yield (start, end, malformed) for each element of a comma list."""
    for element in spec.split(","):
        pieces = element.split("-")
        if any(len(piece) > _MAX_DIGITS for piece in pieces):
            continue
        start = int(pieces[0])
        end = int(pieces[-1])
        yield start, end, start < 1 or end < start


def _document_refs(rel, text, tops):
    refs = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        for token in _reference_tokens(line, in_fence):
            parsed = _parse_token(token, tops)
            if parsed is None:
                continue
            path, norm, spec = parsed
            for start, end, malformed in _ranges(spec):
                refs.append({
                    "file": rel, "line": number, "ref_path": path,
                    "norm": norm, "ref_start": start, "ref_end": end,
                    "malformed": malformed,
                })
    return refs


def _collect_refs(repo, vault_dir, tops):
    refs = []
    for path in _vault_documents(vault_dir):
        try:
            with open(path, "rb") as handle:
                text = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        rel = os.path.relpath(path, repo).replace(os.sep, "/")
        refs.extend(_document_refs(rel, text, tops))
    return refs


# Base commits -------------------------------------------------------------


def _merge_ranges(numbers):
    merged = []
    for number in sorted(set(numbers)):
        if merged and number == merged[-1][1] + 1:
            merged[-1][1] = number
        else:
            merged.append([number, number])
    return merged


def _blame_document(repo, rel, numbers):
    spans = _merge_ranges(numbers)
    args = ["blame", "--porcelain"]
    if len(spans) <= _MAX_BLAME_RANGES:
        for first, last in spans:
            args += ["-L", f"{first},{last}"]
    code, out = _git(repo, *args, "--", rel)
    if code != 0:
        return {}
    found = {}
    for line in out.split("\n"):
        match = _BLAME_HEADER.match(line)
        if match and match.group(1) != ZERO_SHA:
            found[int(match.group(2))] = match.group(1)
    return found


def _document_add_commit(repo, rel):
    code, out = _git(repo, "log", "--follow", "--diff-filter=A",
                     "--format=%H", "--", rel)
    if code != 0:
        return None
    for line in out.split("\n"):
        if _SHA.match(line.strip()):
            return line.strip()
    return None


def _uncommitted_lines(repo, rels):
    """Map document -> set of line numbers that differ from HEAD."""
    changed = {}
    for chunk in _chunks(rels):
        code, out = _git(repo, "diff", "-U0", "--no-renames", "--no-color",
                         "--no-ext-diff", "--no-textconv",
                         "--src-prefix=a/", "--dst-prefix=b/", "HEAD", "--", *chunk)
        if code != 0:
            continue
        for rel, entry in _parse_diff(out).items():
            lines = changed.setdefault(rel, set())
            for _a, _b, start, count in entry["hunks"]:
                lines.update(range(start, start + count))
    return changed


def _resolve_bases(repo, refs, base_from, head, pool):
    """Map (document, line) -> base sha for every classifiable citing line."""
    wanted = {}
    for ref in refs:
        if not ref["malformed"]:
            wanted.setdefault(ref["file"], set()).add(ref["line"])
    if head is None:
        return {}
    docs = sorted(wanted)
    bases = {}
    if base_from == "blame":
        for rel, found in zip(
            docs, pool.map(lambda r: _blame_document(repo, r, wanted[r]), docs)
        ):
            for number, sha in found.items():
                bases[(rel, number)] = sha
        return bases
    uncommitted = _uncommitted_lines(repo, docs)
    for rel, sha in zip(docs, pool.map(lambda r: _document_add_commit(repo, r), docs)):
        if sha is None:
            continue
        for number in wanted[rel]:
            if number not in uncommitted.get(rel, ()):
                bases[(rel, number)] = sha
    return bases


# Diffs --------------------------------------------------------------------


def _parse_diff(text):
    files = {}
    current = None
    for line in text.split("\n"):
        if line.startswith("diff --git "):
            rest = line[len("diff --git "):]
            current = None
            if not rest.startswith('"'):
                path = rest[2:2 + (len(rest) - 5) // 2]
                current = {"deleted": False, "new": False,
                           "binary": False, "hunks": []}
                files[path] = current
        elif current is None:
            continue
        elif line.startswith("@@ "):
            match = _HUNK.match(line)
            if match:
                old_start, old_count, new_start, new_count = match.groups()
                current["hunks"].append((
                    int(old_start),
                    1 if old_count is None else int(old_count),
                    int(new_start),
                    1 if new_count is None else int(new_count),
                ))
        elif line.startswith("deleted file mode"):
            current["deleted"] = True
        elif line.startswith("new file mode"):
            current["new"] = True
        elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
            current["binary"] = True
    return files


def _diff_paths(repo, base, head, paths):
    merged = {}
    for chunk in _chunks(paths):
        code, out = _git(repo, "diff", "-U0", "--no-renames", "--no-color",
                         "--no-ext-diff", "--no-textconv",
                         "--src-prefix=a/", "--dst-prefix=b/",
                         base, head, "--", *chunk)
        if code != 0:
            return None
        merged.update(_parse_diff(out))
    return merged


def _rename_log(repo, base, head):
    """Chronological (commit, old, new, similarity) for renames in base..head."""
    code, out = _git(repo, "log", "--reverse", "-M", "--diff-filter=R",
                     "--name-status", "--format=%x01%H", f"{base}..{head}")
    if code != 0:
        return []
    renames = []
    commit = None
    for line in out.split("\n"):
        if line.startswith("\x01"):
            commit = line[1:].strip()
        elif line.startswith("R") and commit:
            parts = line.split("\t")
            if len(parts) == 3 and parts[0][1:].isdigit():
                renames.append((commit, parts[1], parts[2], int(parts[0][1:])))
    return renames


def _gather_history(repo, refs, bases, head, pool):
    """Return ({base: {path: diff entry} or None}, {base: rename list})."""
    paths_by_base = {}
    for ref in refs:
        base = bases.get((ref["file"], ref["line"]))
        if base and not ref["malformed"] and base != head:
            paths_by_base.setdefault(base, set()).add(ref["norm"])
    order = sorted(paths_by_base)
    diffs = dict(zip(order, pool.map(
        lambda b: _diff_paths(repo, b, head, sorted(paths_by_base[b])), order)))
    needs_log = [
        base for base in order
        if diffs[base] and any(e["deleted"] for e in diffs[base].values())
    ]
    renames = dict(zip(needs_log, pool.map(
        lambda b: _rename_log(repo, b, head), needs_log)))
    return diffs, renames


def _classify_hunks(hunks, start, end):
    """Return (class, new_start) for a cited range against old-side hunks."""
    shift = 0
    above = below = False
    for old_start, old_count, _new_start, new_count in hunks:
        if old_count > 0:
            last = old_start + old_count - 1
            if last < start:
                above = True
                shift += new_count - old_count
            elif old_start > end:
                below = True
            else:
                return "changed", None
        elif old_start < start:
            above = True
            shift += new_count
        elif old_start >= end:
            below = True
        else:
            return "changed", None
    if above:
        return "shifted", start + shift
    if below:
        return "changed-elsewhere", None
    return "unchanged", None


# Blobs --------------------------------------------------------------------


class _Blobs:
    """Cached line lists read through one `git cat-file --batch` process."""

    def __init__(self, repo):
        self._cache = {}
        self._proc = subprocess.Popen(
            ["git", "-C", repo, "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=_ENV,
        )

    def lines(self, rev, path):
        key = (rev, path)
        if key not in self._cache:
            self._cache[key] = self._read(f"{rev}:{path}")
        return self._cache[key]

    def _read(self, spec):
        try:
            self._proc.stdin.write(spec.encode("utf-8") + b"\n")
            self._proc.stdin.flush()
            header = self._proc.stdout.readline().decode("utf-8", "replace").split()
            if len(header) != 3 or header[1] != "blob":
                if len(header) == 3 and header[2].isdigit():
                    self._proc.stdout.read(int(header[2]) + 1)
                return None
            size = int(header[2])
            data = self._proc.stdout.read(size + 1)[:size]
        except (OSError, ValueError):
            return None
        return _split_lines(data.decode("utf-8", "replace"))

    def close(self):
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        self._proc.wait()


# Classification -----------------------------------------------------------


def _slice(lines, start, end):
    if lines is None:
        return None
    return "\n".join(lines[start - 1:end])


def _record(ref, base, cls, old=None, current=None, proposal=None):
    return {
        "file": ref["file"], "line": ref["line"], "ref_path": ref["ref_path"],
        "ref_start": ref["ref_start"], "ref_end": ref["ref_end"],
        "base": base, "class": cls, "old_text": old,
        "current_text": current, "proposal": proposal,
    }


def _follow_rename(path, renames, blobs, head):
    """Follow `path` through chronological renames; return the last hop."""
    current, last = path, None
    for commit, old, new, similarity in renames:
        if old == current:
            current, last = new, (commit, new, similarity)
    if last is None or blobs.lines(head, last[1]) is None:
        return None
    return last


def _classify(ref, base, head, diffs, renames, blobs):
    if ref["malformed"]:
        return _record(ref, None, "malformed")
    if base is None or head is None:
        return _record(ref, None, "unclassifiable")
    path, start, end = ref["norm"], ref["ref_start"], ref["ref_end"]
    old_lines = blobs.lines(base, path)
    if old_lines is None:
        return _record(ref, base, "unclassifiable")
    if end > len(old_lines):
        return _record(ref, None, "malformed")
    old = _slice(old_lines, start, end)
    if base == head:
        return _record(ref, base, "unchanged", old, old)
    table = diffs.get(base)
    if table is None:
        return _record(ref, base, "unclassifiable", old)
    entry = table.get(path)
    if entry is None:
        return _record(ref, base, "unchanged", old, _slice(old_lines, start, end))
    if entry["binary"]:
        return _record(ref, base, "unclassifiable", old)
    if entry["deleted"]:
        hop = _follow_rename(path, renames.get(base, []), blobs, head)
        if hop is None:
            return _record(ref, base, "missing", old)
        commit, new_path, similarity = hop
        return _record(
            ref, base, "moved", old,
            _slice(blobs.lines(head, new_path), start, end),
            {"new_path": new_path, "rename_commit": commit,
             "similarity": similarity},
        )
    new_lines = blobs.lines(head, path)
    cls, new_start = _classify_hunks(entry["hunks"], start, end)
    if cls == "shifted":
        shifted_end = new_start + (end - start)
        return _record(ref, base, cls, old,
                       _slice(new_lines, new_start, shifted_end),
                       {"new_line": new_start})
    return _record(ref, base, cls, old, _slice(new_lines, start, end))
