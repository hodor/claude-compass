"""`compass fix-frontmatter [--lift-summaries] [--apply]` - repair frontmatter.

Clears the two error-level findings `compass validate` reports: a file with no
frontmatter, and a file missing a core field (title / type / status). It fills
only what can be derived deterministically - type from the artifact's type
directory (`<unit>/specs/` yields `spec` for unit artifacts; a unit's own
`index.md` marker is not an artifact and is never touched), title from the
first heading or the filename, dates as today, status as `draft`. It
does NOT invent judgment fields (area, tags, the real status), which stay as
validate warnings for a human or agent to fill. Dry-run by default; `--apply`
writes.

`--lift-summaries` additionally fills a missing `summary:` from the root
index's one-line description of the artifact - text that already exists, in
the wrong place. Only a description that resolves to exactly one artifact
and never contradicts another line lifts; the index line itself is left
alone. An artifact still missing a summary afterwards is reported, since the
index cannot be shortened while its line is the only copy of that text.
"""

import datetime
import re
import sys

import vaultlib

# Plural type-dir name -> singular `type` value. Unknown dirs (e.g. retro) use
# the directory name unchanged.
SINGULAR = {
    "specs": "spec",
    "plans": "plan",
    "research": "research",
    "decisions": "decision",
    "lessons": "lesson",
    "handoffs": "handoff",
    "prs": "pr",
}

HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# A root-index entry line: bullet, wikilink, optional folder child count,
# then a dash-separated description (hand-authored lines use plain, em, or
# en dashes).
ENTRY_LINE = re.compile(
    r"^\s*-\s+\[\[([^\]]+)\]\]\s*(?:\(folder, \d+ children\))?"
    r"\s*[-—–]\s+(.*\S)\s*$"
)


def _type_for(type_dir):
    return SINGULAR.get(type_dir, type_dir)


def _quote(value):
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    return '"' + value.replace('"', "'") + '"'


def _index_descriptions(vault_root):
    """Map vault-relative artifact path -> its one-line description in the
    root index. A link that resolves to nothing or to several files is
    skipped; a path described twice with different text maps to None so the
    conflict is reported instead of one version silently winning."""
    index_path = vault_root / "index.md"
    if not index_path.is_file():
        return {}
    resolve = vaultlib.resolvable_names_map(vault_root)
    described = {}
    for line in vaultlib.read_vault_text(index_path).splitlines():
        match = ENTRY_LINE.match(line)
        if not match:
            continue
        target = re.split(r"[#|]", match.group(1), maxsplit=1)[0].strip()
        desc = match.group(2)
        paths = vaultlib.resolve_link(resolve, target)
        if len(paths) != 1:
            continue
        existing = described.get(paths[0], desc)
        described[paths[0]] = desc if existing == desc else None
    return described


def _title_from(text, stem):
    match = HEADING.search(text)
    if match:
        return match.group(1).strip()
    return stem.replace("-", " ").replace("_", " ").strip()


def _plan_fix(record, today, description=None):
    """Return (new_text, [change descriptions]) or (None, []) if nothing to do."""
    path = record["path"]
    text = vaultlib.read_vault_text(path)
    data, error = vaultlib.parse_frontmatter_text(text)

    if error:
        block = (
            "---\n"
            f"title: {_title_from(text, path.stem)}\n"
            f"type: {_type_for(record['type_dir'])}\n"
            "status: draft\n"
            f"created: {today}\n"
            f"updated: {today}\n"
            "---\n\n"
        )
        if description:
            head, _, _ = block.rpartition("---\n")
            block = head + f"summary: {_quote(description)}\n---\n"
            return block + text, ["added frontmatter", "lifted summary from index.md"]
        return block + text, ["added frontmatter"]

    lines = text.split("\n")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        return None, []
    inserts, changes = [], []
    if not data.get("title"):
        inserts.append(f"title: {_title_from(text, path.stem)}")
        changes.append("added title")
    if not data.get("type"):
        inserts.append(f"type: {_type_for(record['type_dir'])}")
        changes.append("added type")
    if not data.get("status"):
        inserts.append("status: draft")
        changes.append("added status")
    if description and not data.get("summary"):
        inserts.append(f"summary: {_quote(description)}")
        changes.append("lifted summary from index.md")
    if not inserts:
        return None, []
    lines[closing:closing] = inserts
    return "\n".join(lines), changes


def run(args):
    apply = "--apply" in args
    lift = "--lift-summaries" in args
    vault_root = vaultlib.find_vault_root()
    today = datetime.date.today().isoformat()
    descriptions = _index_descriptions(vault_root) if lift else {}

    planned, unlifted = [], []
    for record in vaultlib.scan_artifacts(vault_root):
        rel = record["path"].relative_to(vault_root).as_posix()
        description = descriptions.get(rel) if lift else None
        new_text, changes = _plan_fix(record, today, description)
        if new_text is not None:
            planned.append((rel, changes))
            if apply:
                vaultlib.write_text_lf(record["path"], new_text)
        if lift and description is None:
            data, error = vaultlib.parse_frontmatter(record["path"])
            if not error and not data.get("summary"):
                unlifted.append(rel)

    if not planned and not unlifted:
        sys.stdout.write("compass fix-frontmatter: nothing to fix\n")
        return 0
    verb = "fixed" if apply else "would fix (dry-run; pass --apply to write)"
    if planned:
        sys.stdout.write(f"compass fix-frontmatter: {verb} {len(planned)} file(s)\n")
        for rel, changes in planned:
            sys.stdout.write(f"  {rel}: {', '.join(changes)}\n")
    if unlifted:
        sys.stdout.write(
            f"compass fix-frontmatter: {len(unlifted)} artifact(s) missing summary "
            "with no unique index description to lift\n"
        )
        for rel in unlifted:
            sys.stdout.write(f"  {rel}\n")
    return 0
