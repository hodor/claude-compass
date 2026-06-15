"""`compass sync` - regenerate derived vault state from disk.

Reproduces the mechanical half of the former index-sync skill: append missing
entries to the root index (append-only, human lines preserved), append missing
lesson rows to the catalog, fully regenerate the tag index, check hot-path caps,
and prune old extraction logs.

Runs in two modes. Human mode (no hook stdin) syncs the whole vault and prints a
report. Hook mode (PostToolUse JSON on stdin) self-filters its own generated
outputs to avoid a write loop, succeeds silently, and never exits 2 - an exit 2
would block the user's write.
"""

import json
import re
import sys
import time
from pathlib import Path

import vaultlib

SECTION_BY_TYPE = {
    "spec": "## Specs",
    "plan": "## Plans",
    "research": "## Research",
    "decision": "## Decisions",
    "lesson": "## Lessons",
    "handoff": "## Handoffs",
    "pr": "## PRs",
}

# Files `sync` itself writes; a hook fire for any of these is its own echo.
GENERATED_OUTPUTS = [
    "index.md",
    "meta/tag-index.yaml",
    "meta/lessons-catalog.yaml",
    "meta/working-set.yaml",
]

INDEX_TOKEN_CAP = 5000
INDEX_LINE_CAP = 250
CATALOG_LINE_CAP = 200
CATALOG_BYTE_CAP = 25_000
LESSON_COUNT_CAP = 50
LOG_MAX_AGE_DAYS = 30

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INDEX_WARNING = "<!-- WARNING: index.md exceeded hot-path cap. Run /compass:consolidate before next session. -->"
CATALOG_WARNING = "# WARNING: catalog exceeded cap. Run /compass:consolidate before next session."


def _load_data(records):
    """Attach parsed frontmatter to each record once, reused by all steps."""
    for record in records:
        data, _ = vaultlib.parse_frontmatter(record["path"])
        record["_data"] = data


def _entry_line(record, child_count):
    data = record["_data"]
    summary = data.get("summary") or data.get("title") or record["name"]
    indent = "  " * record["depth"]
    label = f"[[{record['name']}]]"
    if record["kind"] == "folder-index":
        return f"{indent}- {label} (folder, {child_count} children) - {summary}"
    return f"{indent}- {label} - {summary}"


def _child_count(folder_record, records):
    prefix = folder_record["name"] + "/"
    return sum(
        1 for r in records
        if r["name"].startswith(prefix) and "/" not in r["name"][len(prefix):]
    )


def _sync_index(vault_root, records):
    """Append missing entries per type section. Append-only: existing lines,
    including human-authored descriptions, are never rewritten or removed."""
    index_path = vault_root / "index.md"
    lines = index_path.read_text(encoding="utf-8").split("\n")
    added = {}

    by_type = {}
    for record in records:
        if record["_data"].get("status") == "archived":
            continue
        by_type.setdefault(record["_data"].get("type"), []).append(record)

    for artifact_type, recs in by_type.items():
        section = SECTION_BY_TYPE.get(artifact_type)
        if not section:
            continue
        start = next((i for i, l in enumerate(lines) if l.strip() == section), None)
        if start is None:
            continue
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
            len(lines),
        )
        existing = set()
        for line in lines[start + 1:end]:
            existing.update(WIKILINK.findall(line))

        missing = [r for r in recs if r["name"] not in existing]
        if not missing:
            continue
        new_lines = [_entry_line(r, _child_count(r, records))
                     for r in sorted(missing, key=lambda r: r["rel"])]

        insert_at = end
        while insert_at - 1 > start and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines[insert_at:insert_at] = new_lines
        added[artifact_type] = len(new_lines)

    if added:
        vaultlib.write_text_lf(index_path, "\n".join(lines))
    return added


def _catalog_row(filename, data):
    required = ["status", "category", "area", "tags", "score", "summary"]
    if any(data.get(field) in (None, "", []) for field in required):
        return None
    tags = ", ".join(data.get("tags", []))
    return (
        f'  - file: "{filename}"\n'
        f'    status: {data["status"]}\n'
        f'    category: {data["category"]}\n'
        f'    area: {data["area"]}\n'
        f'    tags: [{tags}]\n'
        f'    score: {data["score"]}\n'
        f'    summary: "{data["summary"]}"'
    )


def _sync_catalog(vault_root, records):
    catalog_path = vault_root / "meta" / "lessons-catalog.yaml"
    if not catalog_path.is_file():
        return 0
    text = catalog_path.read_text(encoding="utf-8")
    existing = set(re.findall(r'file:\s*"?([^"\n]+)"?', text))
    rows = []
    for record in records:
        if record["type_dir"] != "lessons":
            continue
        filename = record["path"].name
        if filename in existing:
            continue
        row = _catalog_row(filename, record["_data"])
        if row:
            rows.append(row)
    if rows:
        vaultlib.write_text_lf(catalog_path, text.rstrip("\n") + "\n" + "\n".join(rows) + "\n")
    return len(rows)


def _sync_tag_index(vault_root, records):
    tag_map = {}
    for record in records:
        rel = f"{record['type_dir']}/{record['rel']}"
        for tag in record["_data"].get("tags") or []:
            tag_map.setdefault(tag, set()).add(rel)
    lines = [
        "# Generated by index-sync. Do not hand-edit; changes will be overwritten.",
        "# To merge / rename / retire tags, run /compass:consolidate.",
        "tags:",
    ]
    for tag in sorted(tag_map):
        lines.append(f"  {tag}:")
        for rel in sorted(tag_map[tag]):
            lines.append(f"  - {rel}")
    vaultlib.write_text_lf(vault_root / "meta" / "tag-index.yaml", "\n".join(lines) + "\n")
    return len(tag_map)


def _check_caps(vault_root, records):
    warnings = []
    index_path = vault_root / "index.md"
    text = index_path.read_text(encoding="utf-8")
    over = vaultlib.count_tokens(text) > INDEX_TOKEN_CAP or len(text.splitlines()) > INDEX_LINE_CAP
    if over and INDEX_WARNING not in text:
        vaultlib.write_text_lf(index_path, INDEX_WARNING + "\n" + text)
        warnings.append("index.md")

    catalog_path = vault_root / "meta" / "lessons-catalog.yaml"
    if catalog_path.is_file():
        ctext = catalog_path.read_text(encoding="utf-8")
        lesson_count = sum(
            1 for r in records
            if r["type_dir"] == "lessons" and r["_data"].get("status") != "archived"
        )
        over_cat = (
            len(ctext.splitlines()) > CATALOG_LINE_CAP
            or len(ctext.encode("utf-8")) > CATALOG_BYTE_CAP
            or lesson_count > LESSON_COUNT_CAP
        )
        if over_cat and CATALOG_WARNING not in ctext:
            vaultlib.write_text_lf(catalog_path, CATALOG_WARNING + "\n" + ctext)
            warnings.append("lessons-catalog.yaml")
    return warnings


def _clean_logs(vault_root):
    tmp = vault_root / "tmp"
    if not tmp.is_dir():
        return 0
    cutoff = time.time() - LOG_MAX_AGE_DAYS * 86400
    deleted = 0
    for log in tmp.glob("extraction-log-*.md"):
        if log.is_file() and log.stat().st_mtime < cutoff:
            log.unlink()
            deleted += 1
    return deleted


def sync(vault_root):
    """Run every sync step over the whole vault. Returns a report dict."""
    records = vaultlib.scan_artifacts(vault_root)
    _load_data(records)
    return {
        "index_added": _sync_index(vault_root, records),
        "catalog_added": _sync_catalog(vault_root, records),
        "tags": _sync_tag_index(vault_root, records),
        "caps": _check_caps(vault_root, records),
        "logs_deleted": _clean_logs(vault_root),
    }


def format_report(report):
    parts = ["## Sync"]
    for atype, count in report["index_added"].items():
        parts.append(f"index: +{count} {atype}")
    if report["catalog_added"]:
        parts.append(f"catalog rows added: {report['catalog_added']}")
    parts.append(f"tags indexed: {report['tags']}")
    if report["caps"]:
        parts.append(f"caps exceeded (warning written): {', '.join(report['caps'])}")
    if report["logs_deleted"]:
        parts.append(f"extraction logs deleted: {report['logs_deleted']}")
    return "\n".join(parts)


def _is_generated_output(file_path):
    norm = str(file_path).replace("\\", "/")
    return any(norm.endswith(suffix) for suffix in GENERATED_OUTPUTS)


def _read_hook_stdin():
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        data = sys.stdin.read()
    except (OSError, ValueError):
        return None
    data = data.strip()
    if not data:
        return None
    try:
        obj = json.loads(data)
    except ValueError:
        return None
    if isinstance(obj, dict) and "hook_event_name" in obj:
        return obj
    return None


def run(args):
    vault_root = vaultlib.find_vault_root()
    hook_input = _read_hook_stdin()

    if hook_input is not None:
        try:
            file_path = (hook_input.get("tool_input") or {}).get("file_path", "")
            norm = str(file_path).replace("\\", "/")
            if "/.compass/" not in norm and not norm.startswith(".compass/"):
                return 0  # not a vault write
            if _is_generated_output(file_path):
                return 0  # loop guard: a fire triggered by our own write
            sync(vault_root)
            sys.stdout.write(json.dumps({"suppressOutput": True}))
            return 0
        except Exception as exc:  # never block the user's write
            sys.stderr.write(f"compass sync: {exc}\n")
            return 1

    sys.stdout.write(format_report(sync(vault_root)) + "\n")
    return 0
