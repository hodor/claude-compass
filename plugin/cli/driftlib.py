"""Detect drift between vault documents and the sources they restate.

Three scans share the module: `scan_refs` classifies code references against
git history, `scan_index_lines` compares index lines with the `summary` of the
document each links, and `scan_catalog` compares lesson-catalog rows with
their lesson files.

Code references: a code reference is `path:N`, `path:N-M` or a comma list of those, written
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

The text scans read documents from the working tree. Only an index line that
differs from its target costs git calls: one `git blame` per index document
and per target holding such a line, for the commit times that say which side
changed last.

`apply_fixes` rewrites the corrections the scans prove: inside the backtick
code span of the citing line, a `shifted` reference whose cited text is
byte-identical at its new line and a `moved` reference whose rename carries
the cited text over at similarity 100; in an index line, the description of an
`index-drift` record whose target changed last. A citing document with changes
against HEAD is left alone. Documents are read and written as bytes, so line
endings and every byte outside a rewritten span survive.
"""

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import vaultlib

CLASSES = (
    "unchanged", "changed-elsewhere", "shifted", "changed",
    "moved", "missing", "unclassifiable", "malformed",
)
INDEX_CLASSES = ("index-drift", "no-summary", "unresolved-link", "ambiguous-link")
CATALOG_CLASSES = ("catalog-drift", "missing")
CATALOG_FIELDS = ("status", "category", "area", "tags", "score", "summary",
                  "escalated")

SKIPPED_VAULT_DIRS = ("archive", "tmp")
ZERO_SHA = "0" * 40

_REF = re.compile(
    r"(?P<path>[\w.\-/@+]+):(?P<spec>\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)"
)
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*$")
_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_TOKEN = re.compile(r"\S+")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_INDEX_ENTRY = re.compile(
    r"^\s*-\s+\[\[[^\]]+\]\]\s*(?:\((?:folder, )?\d+ children\))?"
    r"\s*(?:[-\u2014\u2013]\s+(?P<desc>.*\S))?\s*$"
)
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
_SUMMARY_KEY = re.compile(r"^summary:")
_CATALOG_ROW = re.compile(r"^  - file:")
_CATALOG_FIELD = re.compile(r"^    ([A-Za-z0-9_]+):")

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


def _element_bounds(element):
    """`(start, end)` of one comma-list element, or None when a number has
    more digits than `_MAX_DIGITS`."""
    pieces = element.split("-")
    if any(len(piece) > _MAX_DIGITS for piece in pieces):
        return None
    return int(pieces[0]), int(pieces[-1])


def _ranges(spec):
    """Yield (start, end, malformed) for each element of a comma list."""
    for element in spec.split(","):
        bounds = _element_bounds(element)
        if bounds is None:
            continue
        start, end = bounds
        yield start, end, start < 1 or end < start


def _fence_walk(lines):
    """Yield `(number, line, in_fence)` for every line that is not a fence
    delimiter; `number` is 1-based and `in_fence` marks a line inside a
    fenced code block."""
    opener = None
    for number, line in enumerate(lines, 1):
        if opener is None:
            match = _FENCE.match(line)
            if match:
                opener = match.group(1)
                continue
        else:
            close = _FENCE_CLOSE.match(line)
            if (close and close.group(1)[0] == opener[0]
                    and len(close.group(1)) >= len(opener)):
                opener = None
                continue
        yield number, line, opener is not None


def _document_refs(rel, text, tops):
    refs = []
    for number, line, fenced in _fence_walk(text.split("\n")):
        for token in _reference_tokens(line, fenced):
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


def _run_diff(repo, base, head, paths):
    return _git(repo, "diff", "-U0", "--no-renames", "--no-color",
                "--no-ext-diff", "--no-textconv",
                "--src-prefix=a/", "--dst-prefix=b/",
                base, head, "--", *paths)


def _diff_paths(repo, base, head, paths):
    """Diff entries by path for the cited paths between `base` and `head`.
    A chunk git rejects (a pathspec escaping the repository) is retried one
    path at a time; a path git still rejects maps to None."""
    merged = {}
    for chunk in _chunks(paths):
        code, out = _run_diff(repo, base, head, chunk)
        if code == 0:
            merged.update(_parse_diff(out))
            continue
        for path in chunk:
            code, out = _run_diff(repo, base, head, [path])
            if code == 0:
                merged.update(_parse_diff(out))
            else:
                merged[path] = None
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
        if diffs[base] and any(e["deleted"] for e in diffs[base].values() if e)
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
    if above and shift:
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
    if path in table and table[path] is None:
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


# Index lines and catalog rows ---------------------------------------------


def _repo_rel(repo, path):
    return os.path.relpath(os.path.abspath(path), os.path.abspath(repo)).replace(
        os.sep, "/")


def _index_documents(vault):
    """Every `index.md` under the vault, skipping the vault-root `archive/`
    and `tmp/` and any hidden directory."""
    root = os.fspath(vault)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        at_root = os.path.relpath(dirpath, root) == "."
        dirnames[:] = sorted(
            d for d in dirnames
            if not d.startswith(".") and not (at_root and d in SKIPPED_VAULT_DIRS)
        )
        if "index.md" in filenames:
            found.append(os.path.join(dirpath, "index.md"))
    return sorted(found)


def _summary_span(lines):
    """First and last 1-based line of the frontmatter `summary:` value, or
    None. A block scalar's indented continuation lines belong to the span."""
    if not lines or lines[0].strip() != "---":
        return None
    start = last = None
    for number in range(2, len(lines) + 1):
        line = lines[number - 1]
        if line.rstrip() == "---":
            break
        if start is None:
            if _SUMMARY_KEY.match(line):
                start = last = number
        elif not line.strip() or line[0] in " \t":
            if line.strip():
                last = number
        else:
            break
    return None if start is None else (start, last)


def _read_target(vault, rel, cache):
    """`(summary or None, span or None)` for a vault-relative document."""
    if rel not in cache:
        summary, span = None, None
        try:
            text = vaultlib.read_vault_text(vault / rel)
        except OSError:
            text = None
        if text is not None:
            data, _error = vaultlib.parse_frontmatter_text(text)
            value = data.get("summary")
            if isinstance(value, str) and value.strip():
                summary = value
                span = _summary_span(text.split("\n"))
        cache[rel] = (summary, span)
    return cache[rel]


def _blame_times(repo, rel, numbers):
    """Map line number -> committer time for the committed lines among
    `numbers` of one document; uncommitted lines and untracked documents
    are absent."""
    spans = _merge_ranges(numbers)
    args = ["blame", "--porcelain"]
    if len(spans) <= _MAX_BLAME_RANGES:
        for first, last in spans:
            args += ["-L", f"{first},{last}"]
    code, out = _git(repo, *args, "--", rel)
    if code != 0:
        return {}
    shas, times, current = {}, {}, None
    for line in out.split("\n"):
        if line.startswith("\t"):
            continue
        match = _BLAME_HEADER.match(line)
        if match:
            current = match.group(1)
            shas[int(match.group(2))] = current
        elif line.startswith("committer-time ") and current:
            try:
                times[current] = int(line.split()[1])
            except (IndexError, ValueError):
                pass
    return {
        number: times[sha] for number, sha in shas.items()
        if sha != ZERO_SHA and sha in times
    }


def _blame_all(repo, wanted):
    """Run `_blame_times` for {document: line numbers} on a thread pool and
    return {document: {line: time}}."""
    docs = sorted(wanted)
    if not docs:
        return {}
    workers = max(2, min(8, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda d: _blame_times(repo, d, wanted[d]), docs)
        return dict(zip(docs, results))


def _text_record(file, line, cls, target=None, old=None, current=None):
    return {
        "file": file, "line": line, "class": cls, "target": target,
        "field": None, "old_text": old, "current_text": current, "newer": None,
    }


def scan_index_lines(repo_root, vault_dir):
    """Compare each index entry line's description with its target's summary.

    Every `index.md` under `vault_dir` is read; a line shaped as a bullet,
    one wikilink, an optional child count and a description is checked
    against the `summary` of the document its leading wikilink resolves to. Returns records sorted by
    (file, line): `index-drift` (description differs, with `newer` naming the
    side whose last change is later), `no-summary`, `unresolved-link` and
    `ambiguous-link`. A line that agrees with its target yields no record.
    """
    repo = os.fspath(repo_root)
    vault = Path(os.path.abspath(vault_dir))
    mapping = vaultlib.resolvable_names_map(vault)
    targets = {}
    records = []
    drifted = []
    for path in _index_documents(vault):
        try:
            text = vaultlib.read_vault_text(path)
        except OSError:
            continue
        rel = _repo_rel(repo, path)
        lines = text.split("\n")
        fenced, _open = vaultlib.fence_mask(lines)
        for number, line in enumerate(lines, 1):
            if fenced[number - 1]:
                continue
            entry = _INDEX_ENTRY.match(line)
            if not entry or entry.group("desc") is None:
                continue
            desc = entry.group("desc")
            link = _WIKILINK.search(line)
            name = vaultlib.split_link(link.group(1))[0] if link else ""
            resolved = vaultlib.resolve_link(mapping, name) if name else []
            if not resolved:
                records.append(_text_record(rel, number, "unresolved-link", old=desc))
                continue
            if len(resolved) > 1:
                records.append(_text_record(rel, number, "ambiguous-link", old=desc))
                continue
            target = _repo_rel(repo, vault / resolved[0])
            summary, span = _read_target(vault, resolved[0], targets)
            if summary is None:
                records.append(_text_record(
                    rel, number, "no-summary", target, desc))
            elif summary != desc:
                record = _text_record(
                    rel, number, "index-drift", target, desc, summary)
                records.append(record)
                drifted.append((record, span))
    _assign_newer(repo, drifted)
    records.sort(key=lambda rec: (rec["file"], rec["line"]))
    return records


def _assign_newer(repo, drifted):
    """Set `newer` on each drift record from the committer times of the
    index line and of the target's summary lines."""
    wanted = {}
    for record, span in drifted:
        wanted.setdefault(record["file"], set()).add(record["line"])
        if span:
            wanted.setdefault(record["target"], set()).update(
                range(span[0], span[1] + 1))
    times = _blame_all(repo, wanted)
    for record, span in drifted:
        index_time = times.get(record["file"], {}).get(record["line"])
        target_times = [
            times.get(record["target"], {}).get(number)
            for number in range(span[0], span[1] + 1)
        ] if span else []
        if index_time is None or not target_times or None in target_times:
            continue
        target_time = max(target_times)
        if target_time > index_time:
            record["newer"] = "target"
        elif target_time < index_time:
            record["newer"] = "index"


def _catalog_rows(lines):
    """Split catalog lines into rows: each a dict with `line` (the
    `- file:` line), `fields` (field name -> its line) and `data` (the row
    parsed as frontmatter)."""
    rows = []
    block = []

    def flush():
        if not block:
            return
        body = [block[0][1][4:]]
        fields = {}
        for number, text in block[1:]:
            body.append(text[4:] if text.startswith("    ") else text.lstrip())
            match = _CATALOG_FIELD.match(text)
            if match:
                fields[match.group(1)] = number
        data, _error = vaultlib.parse_frontmatter_text(
            "---\n" + "\n".join(body) + "\n---\n")
        rows.append({"line": block[0][0], "fields": fields, "data": data})
        block.clear()

    for number, text in enumerate(lines, 1):
        if _CATALOG_ROW.match(text):
            flush()
            block.append((number, text))
        elif block:
            if text.strip() and text[0] not in " \t":
                flush()
            else:
                block.append((number, text))
    flush()
    return rows


def _lesson_files(vault):
    found = {}
    root = vault / "lessons"
    if root.is_dir():
        for path in sorted(root.rglob("*.md")):
            found.setdefault(path.name, path)
    return found


def _blank(value):
    return None if value in (None, "", []) else value


def _field_text(value):
    if value is None:
        return None
    if isinstance(value, list):
        return "[" + ", ".join(value) + "]"
    return str(value)


def _same_field(field, row_value, file_value):
    if field == "score" and row_value is not None and file_value is not None:
        try:
            return int(row_value) == int(file_value)
        except (TypeError, ValueError):
            pass
    return row_value == file_value


def scan_catalog(repo_root, vault_dir):
    """Compare lesson-catalog rows with the lesson file of the same filename.

    Rows of `<vault_dir>/meta/lessons-catalog.yaml` are matched to lesson
    files anywhere under `<vault_dir>/lessons`. Returns records sorted by
    (file, line): one `catalog-drift` record per differing field, one
    `missing` record per row with no lesson file. A row's `escalated` that
    the file lacks is not drift.
    """
    repo = os.fspath(repo_root)
    vault = Path(os.path.abspath(vault_dir))
    catalog = vault / "meta" / "lessons-catalog.yaml"
    try:
        text = vaultlib.read_vault_text(catalog)
    except OSError:
        return []
    rel = _repo_rel(repo, catalog)
    lessons = _lesson_files(vault)
    records = []
    for row in _catalog_rows(text.split("\n")):
        filename = _blank(row["data"].get("file"))
        if not isinstance(filename, str):
            continue
        path = lessons.get(filename)
        if path is None:
            records.append(_text_record(rel, row["line"], "missing"))
            continue
        try:
            data, _error = vaultlib.parse_frontmatter_text(
                vaultlib.read_vault_text(path))
        except OSError:
            continue
        target = _repo_rel(repo, path)
        for field in CATALOG_FIELDS:
            row_value = _blank(row["data"].get(field))
            file_value = _blank(data.get(field))
            if field == "escalated" and file_value is None:
                continue
            if _same_field(field, row_value, file_value):
                continue
            record = _text_record(
                rel, row["fields"].get(field, row["line"]), "catalog-drift",
                target, _field_text(row_value), _field_text(file_value))
            record["field"] = field
            records.append(record)
    records.sort(key=lambda rec: (rec["file"], rec["line"]))
    return records


# Applying proven corrections ------------------------------------------------


def _span_text(start, end):
    return str(start) if start == end else f"{start}-{end}"


def _fix_kind(record):
    """`"ref"` or `"index"` when `record` is a correction the scans prove
    mechanically, else None."""
    cls = record["class"]
    if "ref_path" in record:
        if record["old_text"] is None or record["old_text"] != record["current_text"]:
            return None
        proposal = record["proposal"] or {}
        if cls == "shifted" and "new_line" in proposal:
            return "ref"
        if cls == "moved" and proposal.get("similarity") == 100:
            return "ref"
        return None
    if cls == "index-drift" and record.get("newer") == "target":
        summary = record["current_text"]
        if summary and "\n" not in summary and "\r" not in summary:
            return "index"
    return None


def _ref_fix(record):
    """`(new path or None, new element text)` for a fixable reference record."""
    start, end = record["ref_start"], record["ref_end"]
    if record["class"] == "moved":
        return record["proposal"]["new_path"], _span_text(start, end)
    new = record["proposal"]["new_line"]
    return None, _span_text(new, new + end - start)


def _token_core(token):
    """`(lead, core)` of a token as `_parse_token` strips it: `lead`
    characters precede the core inside the token."""
    core = token.strip("(['\"").rstrip(".,;:)]'\"")
    lead = len(token) - len(token.lstrip("(['\""))
    if token[lead:lead + len(core)] != core:
        return None
    return lead, core


def _rewrite_ref_line(line, fixes):
    """Rewrite the fixable references of one citing line inside its backtick
    code spans. `fixes` maps `(path, start, end)` to `(new path or None, new
    element text)`. A token's path changes only when every element of its
    comma list moves to one new path. Returns the new line and the
    `(key, old, new)` hits, one per rewritten element."""
    edits, hits = [], []
    for span in _SPAN.finditer(line):
        for found in _TOKEN.finditer(span.group(2)):
            split = _token_core(found.group())
            match = _REF.fullmatch(split[1]) if split else None
            if not match:
                continue
            path = match.group("path")
            elements = match.group("spec").split(",")
            keys = []
            for element in elements:
                bounds = _element_bounds(element)
                key = (path, *bounds) if bounds else None
                keys.append(key if key in fixes else None)
            new_paths = {fixes[k][0] for k in keys if k}
            move = (len(new_paths) == 1 and None not in new_paths
                    and all(keys))
            target = path
            if move:
                target = new_paths.pop()
                if path.startswith("./"):
                    target = "./" + target
            rewritten = []
            for element, key in zip(elements, keys):
                if key is None or (fixes[key][0] and not move):
                    rewritten.append(element)
                    continue
                new_element = element if fixes[key][0] else fixes[key][1]
                rewritten.append(new_element)
                hits.append((key, f"{path}:{element}", f"{target}:{new_element}"))
            replacement = f"{target}:{','.join(rewritten)}"
            if replacement != split[1]:
                start = span.start(2) + found.start() + split[0]
                edits.append((start, start + len(split[1]), replacement))
    for start, end, replacement in sorted(edits, reverse=True):
        line = line[:start] + replacement + line[end:]
    return line, hits


def _dirty_documents(repo, rels):
    """The documents among `rels` that differ from HEAD, staged or not, or
    None when git cannot say."""
    dirty = set()
    for chunk in _chunks(rels):
        code, out = _git(repo, "diff", "--name-only", "-z", "--no-renames",
                         "--no-ext-diff", "--no-textconv", "HEAD", "--", *chunk)
        if code != 0:
            return None
        dirty.update(name for name in out.split("\0") if name)
    return dirty


def _fix_document(lines, records):
    """Apply the fixable `records` of one document to `lines` in place and
    return the applied `(record, old, new)` triples."""
    plain = {number for number, _line, fenced in _fence_walk(lines) if not fenced}
    by_line = {}
    for record in records:
        by_line.setdefault(record["line"], []).append(record)
    applied = []
    for number, group in sorted(by_line.items()):
        if number > len(lines):
            continue
        refs = [r for r in group if _fix_kind(r) == "ref"]
        if refs and number in plain:
            fixes, pending = {}, {}
            for record in refs:
                key = (record["ref_path"], record["ref_start"], record["ref_end"])
                fixes[key] = _ref_fix(record)
                pending.setdefault(key, []).append(record)
            lines[number - 1], hits = _rewrite_ref_line(lines[number - 1], fixes)
            for key, old, new in hits:
                if pending[key]:
                    applied.append((pending[key].pop(0), old, new))
        for record in group:
            if _fix_kind(record) != "index":
                continue
            line = lines[number - 1]
            body = line[:-1] if line.endswith("\r") else line
            match = _INDEX_ENTRY.match(body)
            if not match or match.group("desc") != record["old_text"]:
                continue
            new_body = (body[:match.start("desc")] + record["current_text"]
                        + body[match.end("desc"):])
            lines[number - 1] = new_body + line[len(body):]
            applied.append((record, record["old_text"], record["current_text"]))
    return applied


def apply_fixes(repo_root, records):
    """Rewrite every correction among `records` that the scans prove.

    Returns `(applied, skipped)`. `applied` has one dict per rewritten record:
    `file`, `line`, `class`, `old`, `new` and the `record` itself. `skipped`
    has one dict per citing document left alone (`file`, `count` of
    corrections not applied, `reason`): a document with changes against HEAD,
    or one that could not be read or written. Nothing is rewritten when HEAD
    does not resolve.
    """
    repo = os.fspath(repo_root)
    wanted = {}
    for record in records:
        if _fix_kind(record):
            wanted.setdefault(record["file"], []).append(record)
    if not wanted or _rev_parse(repo, "HEAD") is None:
        return [], []
    dirty = _dirty_documents(repo, sorted(wanted))
    applied, skipped = [], []
    for rel in sorted(wanted):
        group = wanted[rel]
        if dirty is None or rel in dirty:
            skipped.append({"file": rel, "count": len(group),
                            "reason": "uncommitted changes"})
            continue
        path = os.path.join(repo, rel)
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            skipped.append({"file": rel, "count": len(group),
                            "reason": "unreadable"})
            continue
        lines = data.decode("utf-8", "surrogateescape").split("\n")
        triples = _fix_document(lines, group)
        if not triples:
            continue
        try:
            with open(path, "wb") as handle:
                handle.write("\n".join(lines).encode("utf-8", "surrogateescape"))
        except OSError:
            skipped.append({"file": rel, "count": len(group),
                            "reason": "unwritable"})
            continue
        for record, old, new in triples:
            applied.append({"file": rel, "line": record["line"],
                            "class": record["class"], "old": old, "new": new,
                            "record": record})
    return applied, skipped
