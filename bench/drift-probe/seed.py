"""Seed a scratch clone of this repository with known staleness.

`seed.py TARGET --seed N [--list PATH]` clones the repository (`git clone
--local`) into the empty folder TARGET outside the repository, scans the clone
for a baseline, draws 100 items from the baseline-clean ones with a fixed random
seed, makes 20 of them stale, commits the changes in the clone and freezes the
list of items in a JSON file that `score.py` reads back.

The draw: 40 code references (8 stale: 3 shifted, 3 edited, 1 moved, 1 deleted),
30 index lines (6 stale: 3 target `summary` edited, 3 index text edited) and 30
lesson-catalog rows (6 stale: 3 lesson `score` changed, 3 lesson `summary`
edited). The other 80 items are controls that stay as they were.

The scan reads `driftlib` from the clone's own `plugin/cli`; no sync or other
vault tool runs between the seeding commit and the scan.
"""

import argparse
import json
import os
import posixpath
import random
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED = 1
EDIT_MARKER = " drift-probe"

NEED = {"ref": 40, "index": 30, "catalog": 30}
STALE_CHANGES = {
    "ref": (("shifted", "shifted"), ("shifted", "shifted"), ("shifted", "shifted"),
            ("edited", "changed"), ("edited", "changed"), ("edited", "changed"),
            ("moved", "moved"), ("deleted", "missing")),
    "index": (("summary-edited", "index-drift"),) * 3 + (("text-edited", "index-drift"),) * 3,
    "catalog": (("score", "catalog-drift"),) * 3 + (("summary", "catalog-drift"),) * 3,
}
GROUP_KIND = (("refs", "ref"), ("index", "index"), ("catalog", "catalog"))

CLEAN_REF_CLASSES = ("unchanged", "changed-elsewhere")
EXCLUDED_REF_PREFIXES = (".compass/", ".claude/", "plugin/cli/", "bench/drift-probe/")
EXCLUDED_CITING_PREFIXES = (".compass/lessons/", ".compass/meta/")


class AlreadyFrozen(Exception):
    """The seed list already exists and is never rewritten."""


class Refused(Exception):
    """The target folder is inside the repository or not empty."""


# Drawing --------------------------------------------------------------------


def _candidate_key(kind, candidate):
    return (kind, candidate["file"], candidate["line"], candidate.get("ref_path"))


def draw_seeds(candidates, seed):
    """Draw the seed list from baseline-clean `candidates` with random seed `seed`.

    `candidates` maps "refs", "index" and "catalog" to lists of dicts holding at
    least "file" and "line" (refs also "ref_path"). Returns
    {"seed": seed, "items": [...]}; the same inputs give an equal result.
    Raises ValueError when a group holds fewer candidates than it needs.
    """
    rng = random.Random(seed)
    items = []
    for group, kind in GROUP_KIND:
        pool = []
        seen = set()
        for candidate in candidates.get(group, []):
            key = _candidate_key(kind, candidate)
            if key not in seen:
                seen.add(key)
                pool.append(candidate)
        need = NEED[kind]
        if len(pool) < need:
            raise ValueError(
                f"{group}: {len(pool)} baseline-clean candidates, {need} needed")
        picked = rng.sample(pool, need)
        stale = STALE_CHANGES[kind]
        for number, candidate in enumerate(picked):
            change, expected = stale[number] if number < len(stale) else (None, None)
            item = dict(candidate)
            item.update(id=f"{kind}-{number:02d}", kind=kind, stale=change is not None,
                        change=change, expected_class=expected)
            items.append(item)
    return {"seed": seed, "items": items}


def finalize_catalog_lines(seed_list):
    """Point each catalog item at the catalog line its drift record lands on.

    A catalog drift record carries the line of the differing field: the
    `summary` line for a summary change, the `score` line for a score change.
    Controls alternate between the two so both fields are watched.
    """
    controls = 0
    for item in seed_list["items"]:
        if item["kind"] != "catalog":
            continue
        if item["stale"]:
            use_summary = item["change"] == "summary"
        else:
            use_summary = controls % 2 == 1
            controls += 1
        item["line"] = item["summary_line"] if use_summary else item["score_line"]
    return seed_list


# Target and frozen list -------------------------------------------------------


def check_target(target, repo_root):
    """Raise Refused unless `target` is a missing or empty folder outside `repo_root`."""
    resolved = Path(target).resolve()
    repo = Path(repo_root).resolve()
    here = os.path.normcase(str(resolved))
    there = os.path.normcase(str(repo))
    if here == there or here.startswith(there.rstrip(os.sep) + os.sep):
        raise Refused(f"target {target} is inside the repository")
    if resolved.exists():
        if not resolved.is_dir():
            raise Refused(f"target {target} is not a folder")
        if any(resolved.iterdir()):
            raise Refused(f"target {target} is not empty")


def write_frozen(path, seed_list):
    """Write `seed_list` as UTF-8 JSON to a path that does not exist yet."""
    path = Path(path)
    try:
        handle = open(path, "x", encoding="utf-8", newline="\n")
    except FileExistsError:
        raise AlreadyFrozen(f"{path} is frozen") from None
    with handle:
        json.dump(seed_list, handle, indent=2, sort_keys=True)
        handle.write("\n")


# Scan -------------------------------------------------------------------------

_WORKER = r'''
import json, os, re, sys
mode, clone = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(clone, "plugin", "cli"))
from pathlib import Path
import driftlib
import vaultlib
from commands.sync import ENTRY_PATTERN

vault = Path(clone) / ".compass"


def rel(path):
    return os.path.relpath(path, clone).replace(os.sep, "/")


def scan():
    return (driftlib.scan_refs(clone, vault) + driftlib.scan_index_lines(clone, vault)
            + driftlib.scan_catalog(clone, vault))


def lines_of(path):
    return vaultlib.read_vault_text(path).split("\n")


def inline_field(lines, key):
    """1-based line of a single-line frontmatter `key:` value, or None."""
    if not lines or lines[0].strip() != "---":
        return None
    found = None
    for number in range(2, len(lines) + 1):
        line = lines[number - 1]
        if line.rstrip() == "---":
            return found
        if found is None:
            if line.startswith(key + ":"):
                value = line[len(key) + 1:].strip()
                if not value or value[0] in "|>":
                    return None
                found = number
        elif line.strip() and line[0] in " \t":
            return None
        else:
            return found
    return None


def index_inventory():
    wiki = re.compile(r"\[\[([^\]]+)\]\]")
    mapping = vaultlib.resolvable_names_map(vault)
    entries, target_uses = [], {}
    for dirpath, dirnames, filenames in os.walk(vault):
        at_root = os.path.relpath(dirpath, vault) == "."
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".")
                             and not (at_root and d in ("archive", "tmp")))
        if "index.md" not in filenames:
            continue
        path = os.path.join(dirpath, "index.md")
        lines = lines_of(path)
        fenced, _open = vaultlib.fence_mask(lines)
        for number, line in enumerate(lines, 1):
            if fenced[number - 1]:
                continue
            entry = ENTRY_PATTERN.match(line)
            if not entry:
                continue
            link = wiki.search(line)
            name = vaultlib.split_link(link.group(1))[0] if link else ""
            resolved = vaultlib.resolve_link(mapping, name) if name else []
            if len(resolved) != 1:
                continue
            target_uses[resolved[0]] = target_uses.get(resolved[0], 0) + 1
            if entry.group("desc") is None:
                continue
            entries.append((rel(path), number, entry.group("desc"), resolved[0]))
    out = []
    for file, number, desc, target in entries:
        if target_uses[target] != 1:
            continue
        target_path = vault / target
        text = vaultlib.read_vault_text(target_path)
        data, _error = vaultlib.parse_frontmatter_text(text)
        summary = data.get("summary")
        span = inline_field(text.split("\n"), "summary")
        if not isinstance(summary, str) or summary != desc or span is None:
            continue
        out.append({"file": file, "line": number, "target": rel(target_path),
                    "target_summary_line": span})
    return out, set(target_uses)


def catalog_inventory(indexed, records):
    catalog = vault / "meta" / "lessons-catalog.yaml"
    if not catalog.is_file():
        return []
    lessons = {}
    for path in sorted((vault / "lessons").rglob("*.md")):
        lessons.setdefault(path.name, []).append(path)
    lines = vaultlib.read_vault_text(catalog).split("\n")
    rows, current = [], None
    for number, text in enumerate(lines, 1):
        if text.startswith("  - file:"):
            current = {"line": number, "fields": {}}
            rows.append(current)
        elif current is not None:
            match = re.match(r"^    ([A-Za-z0-9_]+):", text)
            if match:
                current["fields"][match.group(1)] = number
    reported = {r["line"] for r in records
                if r["file"] == rel(catalog) and r["class"] not in ("unchanged", "changed-elsewhere")}
    ends = [r["line"] - 1 for r in rows[1:]] + [len(lines)]
    out = []
    for row, end in zip(rows, ends):
        if any(row["line"] <= number <= end for number in reported):
            continue
        data, _error = vaultlib.parse_frontmatter_text(
            "---\n" + lines[row["line"] - 1][4:] + "\n---\n")
        name = data.get("file")
        paths = lessons.get(name) if isinstance(name, str) else None
        if not paths or len(paths) != 1:
            continue
        fields = row["fields"]
        if "score" not in fields or "summary" not in fields:
            continue
        lesson_lines = lines_of(paths[0])
        score_line = inline_field(lesson_lines, "score")
        summary_line = inline_field(lesson_lines, "summary")
        if score_line is None or summary_line is None:
            continue
        if not re.match(r"^score:\s*\d+\s*$", lesson_lines[score_line - 1]):
            continue
        if os.path.relpath(paths[0], vault).replace(os.sep, "/") in indexed:
            continue
        out.append({"file": rel(catalog), "line": fields["score"],
                    "score_line": fields["score"], "summary_line": fields["summary"],
                    "lesson": rel(paths[0]), "lesson_score_line": score_line,
                    "lesson_summary_line": summary_line})
    return out


if mode == "scan":
    json.dump(scan(), sys.stdout)
else:
    records = scan()
    index, indexed = index_inventory()
    json.dump({"records": records, "index": index,
               "catalog": catalog_inventory(indexed, records)}, sys.stdout)
'''


def _run_worker(mode, clone):
    done = subprocess.run(
        [sys.executable, "-I", "-c", _WORKER, mode, os.fspath(clone)],
        capture_output=True, text=True, encoding="utf-8", cwd=os.fspath(clone))
    if done.returncode != 0:
        raise RuntimeError(f"scan failed in {clone}:\n{done.stderr.strip()}")
    return json.loads(done.stdout)


def run_scan(target):
    """Return the scan records (references, index lines, catalog rows) of the clone `target`."""
    return _run_worker("scan", target)


# Candidates -------------------------------------------------------------------


def build_candidates(clone, baseline):
    """Group the baseline-clean items of the clone into draw candidates.

    Every cited path appears once among the reference candidates, so a change
    to one path never lands on a second item. A reference whose citing line is
    a line another candidate changes is left out.
    """
    records = baseline["records"]
    reported = {(r["file"], r["line"]) for r in records
                if r.get("class") not in CLEAN_REF_CLASSES}
    index = [c for c in baseline["index"] if (c["file"], c["line"]) not in reported]
    catalog = baseline["catalog"]
    touched = {(c["file"], c["line"]) for c in index}
    touched |= {(c["target"], c["target_summary_line"]) for c in index}
    touched |= {(c["lesson"], c["lesson_score_line"]) for c in catalog}
    touched |= {(c["lesson"], c["lesson_summary_line"]) for c in catalog}

    uses = {}
    for record in records:
        if record.get("ref_path") is not None:
            key = (record["file"], record["line"], record["ref_path"])
            uses[key] = uses.get(key, 0) + 1
    refs, paths = [], set()
    for record in records:
        path = record.get("ref_path")
        if path is None or record["class"] not in CLEAN_REF_CLASSES:
            continue
        key = (record["file"], record["line"], path)
        if (uses[key] != 1 or path in paths
                or path != posixpath.normpath(path) or path.startswith("/")
                or path.startswith(EXCLUDED_REF_PREFIXES)
                or record["file"].startswith(EXCLUDED_CITING_PREFIXES)
                or posixpath.basename(record["file"]) == "index.md"
                or (record["file"], record["line"]) in touched
                or not os.path.isfile(os.path.join(clone, *path.split("/")))):
            continue
        paths.add(path)
        refs.append({"file": record["file"], "line": record["line"], "ref_path": path,
                     "ref_start": record["ref_start"], "ref_end": record["ref_end"]})
    return {"refs": refs, "index": index, "catalog": catalog}


# Mutations --------------------------------------------------------------------


def _read_lines(path):
    return path.read_bytes().decode("utf-8").split("\n")


def _write_lines(path, lines):
    path.write_bytes("\n".join(lines).encode("utf-8"))


def _append_to_value(line, marker=EDIT_MARKER):
    """Append `marker` to a line's value, inside its closing quote when quoted."""
    carriage = "\r" if line.endswith("\r") else ""
    body = line[:-1] if carriage else line
    stripped = body.rstrip()
    trailing = body[len(stripped):]
    value = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        stripped = stripped[:-1] + marker + stripped[-1]
    else:
        stripped += marker
    return stripped + trailing + carriage


def _edit_line(path, number, edit):
    lines = _read_lines(path)
    lines[number - 1] = edit(lines[number - 1])
    _write_lines(path, lines)


def _bump_score(line):
    match = re.match(r"^(score:\s*)(\d+)(\s*\r?)$", line)
    return f"{match.group(1)}{int(match.group(2)) + 1}{match.group(3)}"


def _git(clone, *args):
    done = subprocess.run(
        ["git", "-c", "user.name=drift-probe", "-c", "user.email=drift-probe@localhost",
         "-C", os.fspath(clone), *args],
        capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def apply_seeds(clone, seed_list):
    """Make the stale items stale in the clone and commit the changes."""
    clone = Path(clone)
    for item in seed_list["items"]:
        if not item["stale"]:
            continue
        change = item["change"]
        if item["kind"] == "ref":
            path = clone.joinpath(*item["ref_path"].split("/"))
            if change == "shifted":
                path.write_bytes(b"\n" + path.read_bytes())
            elif change == "edited":
                lines = _read_lines(path)
                number = item["ref_start"]
                lines[number - 1] = lines[number - 1].rstrip("\r") + EDIT_MARKER + (
                    "\r" if lines[number - 1].endswith("\r") else "")
                _write_lines(path, lines)
            elif change == "moved":
                stem, ext = os.path.splitext(item["ref_path"])
                _git(clone, "mv", item["ref_path"], f"{stem}-drift-moved{ext}")
            elif change == "deleted":
                _git(clone, "rm", "-q", item["ref_path"])
        elif item["kind"] == "index":
            if change == "summary-edited":
                _edit_line(clone.joinpath(*item["target"].split("/")),
                           item["target_summary_line"], _append_to_value)
            else:
                _edit_line(clone.joinpath(*item["file"].split("/")), item["line"],
                           lambda line: line.rstrip("\r") + EDIT_MARKER
                           + ("\r" if line.endswith("\r") else ""))
        else:
            lesson = clone.joinpath(*item["lesson"].split("/"))
            if change == "score":
                _edit_line(lesson, item["lesson_score_line"], _bump_score)
            else:
                _edit_line(lesson, item["lesson_summary_line"], _append_to_value)
    _git(clone, "add", "-A")
    _git(clone, "commit", "-q", "-m", "drift probe seeds")


# Entry point ------------------------------------------------------------------


def default_list_path(target):
    target = Path(target)
    return target.with_name(target.name + ".seeds.json")


def main(argv=None, *, repo_root=None):
    parser = argparse.ArgumentParser(
        prog="seed.py", description="Seed a scratch clone with known staleness.")
    parser.add_argument("target", help="empty folder outside the repository for the clone")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed of the draw")
    parser.add_argument("--list", dest="list_path",
                        help="frozen seed list (default: TARGET.seeds.json beside the target)")
    args = parser.parse_args(argv)
    repo = Path(repo_root) if repo_root is not None else REPO_ROOT
    list_path = Path(args.list_path) if args.list_path else default_list_path(args.target)

    if list_path.exists():
        print(f"seed list {list_path} is frozen; pick another path", file=sys.stderr)
        return 1
    try:
        check_target(args.target, repo)
    except Refused as error:
        print(str(error), file=sys.stderr)
        return 2

    target = Path(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(target.parent, "clone", "-q", "--local", os.fspath(repo), os.fspath(target))
    baseline = _run_worker("inventory", target)
    seed_list = finalize_catalog_lines(
        draw_seeds(build_candidates(target, baseline), args.seed))
    apply_seeds(target, seed_list)
    try:
        write_frozen(list_path, seed_list)
    except AlreadyFrozen as error:
        print(str(error), file=sys.stderr)
        return 1
    stale = sum(1 for item in seed_list["items"] if item["stale"])
    print(f"seeded {stale} of {len(seed_list['items'])} items in {target}; list {list_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
