"""`compass fix-frontmatter [--apply]` - repair frontmatter errors.

Clears the two error-level findings `compass validate` reports: a file with no
frontmatter, and a file missing a core field (title / type / status). It fills
only what can be derived deterministically - type from the directory, title
from the first heading or the filename, dates as today, status as `draft`. It
does NOT invent judgment fields (area, tags, the real status), which stay as
validate warnings for a human or agent to fill. Dry-run by default; `--apply`
writes.
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


def _type_for(type_dir):
    return SINGULAR.get(type_dir, type_dir)


def _title_from(text, stem):
    match = HEADING.search(text)
    if match:
        return match.group(1).strip()
    return stem.replace("-", " ").replace("_", " ").strip()


def _plan_fix(record, today):
    """Return (new_text, [change descriptions]) or (None, []) if nothing to do."""
    path = record["path"]
    text = path.read_text(encoding="utf-8")
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
    if not inserts:
        return None, []
    lines[closing:closing] = inserts
    return "\n".join(lines), changes


def run(args):
    apply = "--apply" in args
    vault_root = vaultlib.find_vault_root()
    today = datetime.date.today().isoformat()

    planned = []
    for record in vaultlib.scan_artifacts(vault_root):
        new_text, changes = _plan_fix(record, today)
        if new_text is not None:
            planned.append((f"{record['type_dir']}/{record['rel']}", changes))
            if apply:
                vaultlib.write_text_lf(record["path"], new_text)

    if not planned:
        sys.stdout.write("compass fix-frontmatter: nothing to fix\n")
        return 0
    verb = "fixed" if apply else "would fix (dry-run; pass --apply to write)"
    sys.stdout.write(f"compass fix-frontmatter: {verb} {len(planned)} file(s)\n")
    for rel, changes in planned:
        sys.stdout.write(f"  {rel}: {', '.join(changes)}\n")
    return 0
