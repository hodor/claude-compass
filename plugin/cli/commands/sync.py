"""`compass sync` - regenerate derived vault state from disk.

Reproduces the mechanical half of the former index-sync skill: append missing
entries to the root index (append-only, human lines preserved), append missing
lesson rows to the catalog (aggregating unit `lessons/` dirs), fully regenerate
the tag index, check hot-path caps, and prune old extraction logs.

Root artifacts are indexed under per-type sections with bare-stem wikilinks;
unit artifacts under one section per unit with path-qualified wikilinks. Every
link sync writes resolves through `vaultlib.resolvable_names_map`, the same
resolution `validate` checks against.

Runs in two modes. Human mode (no hook stdin) syncs the whole vault and prints a
report. Hook mode (PostToolUse JSON on stdin) self-filters its own generated
outputs to avoid a write loop, succeeds silently, and never exits 2 - an exit 2
would block the user's write.
"""

import datetime
import json
import re
import sys
import time
from pathlib import Path

import capturelib
import vaultlib

# A type directory's index section is its name title-cased, with overrides for
# names that do not title-case cleanly. Unknown dirs (e.g. retro -> ## Retro)
# work without code changes.
SECTION_OVERRIDES = {"prs": "PRs"}


def section_for(type_dir):
    return "## " + SECTION_OVERRIDES.get(type_dir, type_dir.capitalize())

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
CAPTURE_LOG_MAX_AGE_DAYS = 365

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INDEX_WARNING = "<!-- WARNING: index.md exceeded hot-path cap. Run /compass:consolidate before next session. -->"
CATALOG_WARNING = "# WARNING: catalog exceeded cap. Run /compass:consolidate before next session."


def _load_data(records):
    """Attach parsed frontmatter to each record once, reused by all steps."""
    for record in records:
        data, _ = vaultlib.parse_frontmatter(record["path"])
        record["_data"] = data


def _rel_path(vault_root, record):
    """Vault-relative POSIX path of a record's file, the resolution identity
    `vaultlib.resolvable_names_map` maps names onto."""
    return record["path"].relative_to(vault_root).as_posix()


def _link_name(record):
    """Wikilink target sync emits for a record.

    Root artifacts get bare-stem links (folder specs: the folder name), the
    shortest resolvable form. Unit artifacts get path-qualified links
    (vault-relative, no extension) so they stay unambiguous across units; a
    folder spec inside a unit links by its folder's vault-relative path,
    mirroring the folder-name convention root folder specs use.
    """
    if record["unit"] is None:
        if record["kind"] == "folder-index":
            return record["path"].parent.name
        return record["path"].stem
    return record["name"]


def _unit_title(vault_root, unit):
    """Index section title for a unit: the `title` frontmatter of the unit's
    own `index.md`, falling back to the folder name."""
    data, error = vaultlib.parse_frontmatter(Path(vault_root) / unit / "index.md")
    if not error and data.get("title"):
        return data["title"]
    return unit


def _entry_line(record, child_count):
    data = record["_data"]
    summary = data.get("summary") or data.get("title") or record["name"]
    indent = "  " * record["depth"]
    label = f"[[{_link_name(record)}]]"
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
    """Append missing entries: one section per root type dir, one section per
    unit titled from the unit's `index.md`. Append-only: existing lines,
    including human-authored descriptions, are never rewritten or removed.
    An artifact counts as already indexed when any existing wikilink in its
    section resolves to the artifact's file, so sync never re-appends an
    entry `validate` already resolves regardless of the link form used."""
    index_path = vault_root / "index.md"
    lines = index_path.read_text(encoding="utf-8").split("\n")
    resolve = vaultlib.resolvable_names_map(vault_root)
    added = {}

    root_by_dir = {}
    unit_recs = {}
    for record in records:
        if record["_data"].get("status") == "archived":
            continue
        if record["unit"] is None:
            root_by_dir.setdefault(record["type_dir"], []).append(record)
        else:
            unit_recs.setdefault(record["unit"], []).append(record)

    sections = [
        (type_dir, section_for(type_dir), sorted(recs, key=lambda r: r["rel"]))
        for type_dir, recs in sorted(root_by_dir.items())
    ]
    sections += [
        (unit, "## " + _unit_title(vault_root, unit),
         sorted(recs, key=lambda r: (r["type_dir"], r["rel"])))
        for unit, recs in sorted(unit_recs.items())
    ]

    for key, header, recs in sections:
        start = next((i for i, l in enumerate(lines) if l.strip() == header), None)
        if start is None:
            # Section absent (e.g. a newly introduced type dir or unit):
            # create it at the end of the file so the new artifacts are not
            # lost.
            if lines and lines[-1].strip() != "":
                lines.append("")
            lines.append(header)
            lines.append("")
            start = len(lines) - 2
            end = len(lines)
        else:
            end = next(
                (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
                len(lines),
            )
        indexed_paths = set()
        for line in lines[start + 1:end]:
            for raw in WIKILINK.findall(line):
                target = raw.split("#")[0].split("|")[0].strip()
                indexed_paths.update(resolve.get(target, []))

        missing = [r for r in recs if _rel_path(vault_root, r) not in indexed_paths]
        if not missing:
            continue
        new_lines = [_entry_line(r, _child_count(r, records)) for r in missing]

        insert_at = end
        while insert_at - 1 > start and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines[insert_at:insert_at] = new_lines
        added[key] = len(new_lines)

    if added:
        vaultlib.write_text_lf(index_path, "\n".join(lines))
    return added


def _catalog_row(filename, data):
    required = ["status", "category", "area", "tags", "score", "summary"]
    if any(data.get(field) in (None, "", []) for field in required):
        return None
    tags = ", ".join(data.get("tags", []))
    row = (
        f'  - file: "{filename}"\n'
        f'    status: {data["status"]}\n'
        f'    category: {data["category"]}\n'
        f'    area: {data["area"]}\n'
        f'    tags: [{tags}]\n'
        f'    score: {data["score"]}\n'
        f'    summary: "{data["summary"]}"'
    )
    if data.get("escalated") not in (None, ""):
        row += f'\n    escalated: {data["escalated"]}'
    return row


def _sync_catalog(vault_root, records):
    """Append missing lesson rows to the root catalog, aggregating lessons
    from unit `lessons/` dirs so nested lessons stay on the hot path. The
    filename is the row key; two lesson files sharing a filename are a
    collision - reported, and only the first (by vault path) gets a row."""
    catalog_path = vault_root / "meta" / "lessons-catalog.yaml"
    if not catalog_path.is_file():
        return 0, []
    text = catalog_path.read_text(encoding="utf-8")
    existing = set(re.findall(r'file:\s*"?([^"\n]+)"?', text))
    by_filename = {}
    for record in records:
        if record["type_dir"] != "lessons":
            continue
        by_filename.setdefault(record["path"].name, []).append(record)
    rows, collisions = [], []
    for filename in sorted(by_filename):
        recs = sorted(by_filename[filename], key=lambda r: _rel_path(vault_root, r))
        if len(recs) > 1:
            paths = ", ".join(_rel_path(vault_root, r) for r in recs)
            collisions.append(f"{filename}: {paths}")
        if filename in existing:
            continue
        row = _catalog_row(filename, recs[0]["_data"])
        if row:
            rows.append(row)
    if rows:
        vaultlib.write_text_lf(catalog_path, text.rstrip("\n") + "\n" + "\n".join(rows) + "\n")
    return len(rows), collisions


def _sync_tag_index(vault_root, records):
    tag_map = {}
    for record in records:
        rel = _rel_path(vault_root, record)
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


def _prune_capture_log(vault_root):
    """Drop rows in `tmp/capture-log.jsonl` older than
    `CAPTURE_LOG_MAX_AGE_DAYS`, keyed by each row's own `at` timestamp
    rather than the file's mtime, since the whole log lives in one
    continuously-appended file. A line that cannot be parsed or dated is
    dropped along with the aged-out rows: a row that cannot be judged to be
    recent cannot be judged to have earned another year on disk either."""
    path = vault_root / "tmp" / "capture-log.jsonl"
    if not path.is_file():
        return 0
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=CAPTURE_LOG_MAX_AGE_DAYS
    )
    kept, pruned = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
            at = datetime.datetime.fromisoformat(row["at"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError, AttributeError):
            pruned += 1
            continue
        if at < cutoff:
            pruned += 1
            continue
        kept.append(stripped)
    if pruned:
        text = "\n".join(kept) + ("\n" if kept else "")
        vaultlib.write_text_lf(path, text)
    return pruned


def _clean_logs(vault_root):
    """Prune stale logs under `tmp/`: whole-file deletion of
    `extraction-log-*.md` past `LOG_MAX_AGE_DAYS`, row-level pruning of
    `capture-log.jsonl` past `CAPTURE_LOG_MAX_AGE_DAYS` - a much longer
    horizon, since a fleet-wide fire-rate measurement needs to look back
    further than one month. Returns `(extraction_deleted, capture_rows_pruned)`.
    """
    tmp = vault_root / "tmp"
    if not tmp.is_dir():
        return 0, 0
    cutoff = time.time() - LOG_MAX_AGE_DAYS * 86400
    deleted = 0
    for log in tmp.glob("extraction-log-*.md"):
        if log.is_file() and log.stat().st_mtime < cutoff:
            log.unlink()
            deleted += 1
    return deleted, _prune_capture_log(vault_root)


def sync(vault_root):
    """Run every sync step over the whole vault. Returns a report dict."""
    records = vaultlib.scan_artifacts(vault_root)
    _load_data(records)
    index_added = _sync_index(vault_root, records)
    catalog_added, catalog_collisions = _sync_catalog(vault_root, records)
    logs_deleted, capture_log_pruned = _clean_logs(vault_root)
    return {
        "index_added": index_added,
        "catalog_added": catalog_added,
        "catalog_collisions": catalog_collisions,
        "tags": _sync_tag_index(vault_root, records),
        "caps": _check_caps(vault_root, records),
        "logs_deleted": logs_deleted,
        "capture_log_pruned": capture_log_pruned,
    }


def format_report(report):
    parts = ["## Sync"]
    for atype, count in report["index_added"].items():
        parts.append(f"index: +{count} {atype}")
    if report["catalog_added"]:
        parts.append(f"catalog rows added: {report['catalog_added']}")
    for collision in report["catalog_collisions"]:
        parts.append(f"catalog filename collision: {collision}")
    parts.append(f"tags indexed: {report['tags']}")
    if report["caps"]:
        parts.append(f"caps exceeded (warning written): {', '.join(report['caps'])}")
    if report["logs_deleted"]:
        parts.append(f"extraction logs deleted: {report['logs_deleted']}")
    if report["capture_log_pruned"]:
        parts.append(f"capture-log rows pruned: {report['capture_log_pruned']}")
    return "\n".join(parts)


def _is_generated_output(file_path):
    norm = str(file_path).replace("\\", "/")
    return any(norm.endswith(suffix) for suffix in GENERATED_OUTPUTS)


def _record_write_signal(vault_root, norm):
    """Record a capture signal for a hook-mode vault write that already
    passed the self-filter above: `handoff-written` for a path under
    `handoffs/`, `vault-write` otherwise, keyed on the vault-relative POSIX
    path of the written file. Any failure here (a capturelib error, a
    corrupt state file) is swallowed - the sync report and exit code must
    never depend on this bookkeeping."""
    try:
        ref = norm.split(".compass/", 1)[-1]
        kind = "handoff-written" if ref.startswith("handoffs/") else "vault-write"
        capturelib.record_signal(vault_root, kind, ref)
    except Exception:
        pass


def _parse_hook_stdin():
    """Parse the PostToolUse event JSON the hook runtime pipes on stdin."""
    data = sys.stdin.read().strip()
    if not data:
        return {}
    try:
        obj = json.loads(data)
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def run(args):
    vault_root = vaultlib.find_vault_root()

    if "--hook" in args:
        # PostToolUse invocation: the event JSON arrives on stdin. Read it only
        # here, so the human/skill path below never touches stdin and cannot
        # block in a non-interactive shell with no input.
        try:
            hook_input = _parse_hook_stdin()
            file_path = (hook_input.get("tool_input") or {}).get("file_path", "")
            norm = str(file_path).replace("\\", "/")
            if "/.compass/" not in norm and not norm.startswith(".compass/"):
                return 0  # not a vault write
            if _is_generated_output(file_path):
                return 0  # loop guard: a fire triggered by our own write
            _record_write_signal(vault_root, norm)
            sync(vault_root)
            sys.stdout.write(json.dumps({"suppressOutput": True}))
            return 0
        except Exception as exc:  # never block the user's write
            try:
                import bugs
                bugs.capture_exception(vault_root, "sync", exc)
            except Exception:
                pass
            sys.stderr.write(f"compass sync: {exc}\n")
            return 1

    # Human / skill invocation: sync the whole vault and print a report.
    sys.stdout.write(format_report(sync(vault_root)) + "\n")
    return 0
