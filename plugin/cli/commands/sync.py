"""`compass sync` - regenerate derived vault state from disk.

Reproduces the mechanical half of the former index-sync skill: heal the root
index in both directions (append missing entries, prune lines that relocation
made stale - never a line whose text exists nowhere else), append missing
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
import os
import re
import sys
import time
from pathlib import Path

import capturelib
import vaultlib
from commands import hot_path
from commands import sweep

# A type directory's index section is its name title-cased, with overrides for
# names that do not title-case cleanly. Unknown dirs (e.g. retro -> ## Retro)
# work without code changes.
SECTION_OVERRIDES = {"prs": "PRs"}


def section_for(type_dir):
    return "## " + SECTION_OVERRIDES.get(type_dir, type_dir.capitalize())

# Vault-root-relative paths `sync` itself writes; a hook fire for any of
# these is its own echo. Exact matches only: a nested folder's index.md is
# an artifact whose write must sync, not an echo.
GENERATED_OUTPUTS = {
    "index.md",
    "meta/tag-index.yaml",
    "meta/lessons-catalog.yaml",
    "meta/working-set.yaml",
}

INDEX_TOKEN_CAP = 5000
INDEX_LINE_CAP = 250
# 50 lessons (LESSON_COUNT_CAP) at the fixed 7-line row shape, plus header;
# the two caps agree by construction so a legal lesson count cannot trip the
# line cap on its own.
CATALOG_LINE_CAP = 360
CATALOG_BYTE_CAP = 25_000
LESSON_COUNT_CAP = 50
LOG_MAX_AGE_DAYS = 30
CAPTURE_LOG_MAX_AGE_DAYS = 365

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INDEX_WARNING = "<!-- WARNING: index.md exceeded hot-path cap. Run /compass:consolidate before next session. -->"
CATALOG_WARNING = "# WARNING: catalog exceeded cap. Run /compass:consolidate before next session."
HOT_PATH_WARNING_PREFIX = "<!-- WARNING: hot path "

# The minimal index.md /compass:setup writes for a new vault, reused here so
# a vault synced before index.md exists gets the same shape rather than an
# empty file.
INDEX_SKELETON = (
    '---\n'
    'title: "Project Index"\n'
    'type: index\n'
    'created: {date}\n'
    'updated: {date}\n'
    '---\n'
    '\n'
    '# Project Index\n'
)

# `lessons: []` is the empty-catalog marker `/compass:setup` writes. It is
# valid only while the catalog holds zero rows; a block-sequence row nested
# under it (`  - file: ...`) is not valid YAML once real content is added.
# `[ \t]*$` (not `\s*$`) keeps the match on this one line so a blank line
# following the marker is never swallowed by the substitution.
LESSONS_EMPTY_MARKER = re.compile(r"^lessons:[ \t]*\[\][ \t]*$", re.MULTILINE)


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
    mirroring the folder-name convention root folder specs use. A root loose
    nested doc (`vaultlib.is_loose_nested`) also gets the vault-relative
    form, since nothing scopes its subfolder to keep the bare stem unique.
    """
    if record["kind"] == "folder-index":
        # A folder is not a file, so a bare folder link cannot be clicked
        # open in Obsidian; the piped full path to its index.md can, and
        # displays as the plain folder name.
        return f"{record['name']}/index|{record['path'].parent.name}"
    if record["unit"] is None:
        if vaultlib.is_loose_nested(record["path"], record["kind"]):
            return record["name"]
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


def _covered_by_folder_line(record):
    """True when an ancestor folder between this record and its type-dir
    root carries an `index.md` - the folder artifact whose own entry line,
    with its child count, is the root index's pointer to this record's
    whole subtree (ADR-021 D-01). Checks every ancestor, so a doc inside a
    plain grouping subfolder of a listed domain counts as covered too."""
    parts = record["rel"].split("/")
    base = record["path"].parents[len(parts) - 1]
    folder = record["path"].parent
    if record["kind"] == "folder-index":
        folder = folder.parent
    while folder != base:
        if (folder / "index.md").is_file():
            return True
        folder = folder.parent
    return False


# An index entry line: bullet, one wikilink, optional folder child count,
# optionally a dash-separated description (hand-authored lines use plain,
# em, or en dashes). Only lines of this shape are ever prune candidates.
ENTRY_PATTERN = re.compile(
    r"^\s*-\s+\[\[[^\]]+\]\]\s*(?:\(folder, \d+ children\))?"
    r"\s*(?:[-—–]\s+(?P<desc>.*\S))?\s*$"
)


def _text_preserved(desc, record):
    """A dropped line must take no text with it (the Data rule): the line
    carries no description, or text the artifact's own file already holds -
    its `summary:`, its `title:`, or anywhere in its body (where `compass
    move` preserves a divergent index description before pruning)."""
    if desc is None:
        return True
    data = record["_data"] or {}
    if desc in (data.get("summary"), data.get("title")):
        return True
    try:
        return desc in vaultlib.read_vault_text(record["path"])
    except OSError:
        return False


def _drop_reason(line, infos, covered, listed, section_paths, indexed_paths):
    """Why this section line should be pruned, or None to keep it.

    The bullet's leading wikilink is the entry's subject, and it alone
    decides the drop - it must resolve to exactly one file. Links cited
    inside the description travel with the description text, which
    `_text_preserved` proves loses nothing: `covered` - a listed folder's
    line now points at the artifact's subtree; `duplicate` - this section
    already indexed the artifact on an earlier line; `mislocated` - the
    artifact is listed, but its home is another section, which holds or
    will receive its entry."""
    match = ENTRY_PATTERN.match(line)
    if not match or not infos:
        return None
    resolved = infos[0][3]
    if len(resolved) != 1:
        return None
    path = resolved[0]
    desc = match.group("desc")
    record = covered.get(path)
    if record is not None and _text_preserved(desc, record):
        return "covered"
    record = listed.get(path)
    if record is not None and _text_preserved(desc, record):
        if path in indexed_paths:
            return "duplicate"
        if path not in section_paths:
            return "mislocated"
    return None


def _merge_duplicate_sections(lines):
    """Fold repeated identical `## ` headings into the first occurrence:
    each later body appends to the first section and the later heading
    goes. Returns (lines, merged_count)."""
    spans = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            if spans:
                spans[-1][1] = i
            spans.append([i, len(lines), line.strip()])
    first_end, relocate, remove = {}, {}, set()
    merged = 0
    for start, end, text in spans:
        if text in first_end:
            relocate.setdefault(first_end[text], []).extend(
                l for l in lines[start + 1:end] if l.strip()
            )
            remove.update(range(start, end))
            merged += 1
        else:
            first_end[text] = end
    if not merged:
        return lines, 0
    out = []
    for i, line in enumerate(lines):
        if i in relocate:
            out.extend(relocate[i])
        if i in remove:
            continue
        out.append(line)
    return out, merged


def _sync_index(vault_root, records):
    """Heal the root index in both directions. Additions: one section per
    root type dir, one section per unit titled from the unit's `index.md`;
    an artifact counts as already indexed when any existing wikilink in its
    section resolves to the artifact's file. Removals: an entry line whose
    artifact a listed folder now covers, a duplicate of an earlier entry,
    and a repeated section heading all go - but only when the line's
    description text survives in the artifact itself (`_text_preserved`),
    so a prune can never destroy information. A line linking a loose
    nested doc by its type-dir-omitted name is recognized as the same
    artifact and rewritten in place to the current vault-relative form
    (see the per-section loop below), so it resolves on this and every
    later run. A vault with no `index.md` yet gets the same minimal
    skeleton `/compass:setup` writes. Returns
    (added_per_section, pruned_count, merged_heading_count)."""
    index_path = vault_root / "index.md"
    if index_path.is_file():
        lines = index_path.read_text(encoding="utf-8").split("\n")
        existed = True
    else:
        today = datetime.date.today().isoformat()
        lines = INDEX_SKELETON.format(date=today).split("\n")
        existed = False
    lines, sections_merged = _merge_duplicate_sections(lines)
    resolve = vaultlib.resolvable_names_map(vault_root)
    added = {}
    rewrites = 0
    pruned = 0

    root_by_dir = {}
    unit_recs = {}
    covered = {}
    for record in records:
        if record["_data"].get("status") == "archived":
            continue
        # Lessons are indexed by the catalog, which loads with the hot path;
        # a second per-lesson listing here would put every summary in the
        # hot path twice. The index's Lessons section is a pointer.
        if record["type_dir"] == "lessons":
            continue
        # The root index speaks in top-level entries (ADR-021): a folder
        # artifact's line, with its child count, is the pointer to its whole
        # subtree. Children of a folder artifact live inside it and resolve
        # by wikilink; listing them here would price every domain member
        # back onto the hot path. A loose nested doc with no listed folder
        # above it has no line pointing at it, so it stays listed.
        if record["depth"] > 0 and _covered_by_folder_line(record):
            covered[_rel_path(vault_root, record)] = record
            continue
        if record["unit"] is None:
            root_by_dir.setdefault(record["type_dir"], []).append(record)
        else:
            unit_recs.setdefault(record["unit"], []).append(record)
    listed = {
        _rel_path(vault_root, r): r
        for recs in list(root_by_dir.values()) + list(unit_recs.values())
        for r in recs
    }

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
        # A loose nested doc's link target may name this record by its
        # type-dir-omitted form; recognize that form as the same artifact
        # and rewrite the line to the current name so it resolves.
        legacy = {
            r["name"][len(r["type_dir"]) + 1:]: r
            for r in recs
            if r["unit"] is None and vaultlib.is_loose_nested(r["path"], r["kind"])
        }

        folder_by_path = {
            _rel_path(vault_root, r): r for r in recs if r["kind"] == "folder-index"
        }
        section_paths = {_rel_path(vault_root, r) for r in recs}
        indexed_paths = set()
        section_lines = []
        for line in lines[start + 1:end]:
            infos = []
            for raw in WIKILINK.findall(line):
                split_at = next((i for i, c in enumerate(raw) if c in "#|"), len(raw))
                target = raw[:split_at].strip()
                infos.append(
                    (raw, split_at, target, vaultlib.resolve_link(resolve, target))
                )
            if _drop_reason(line, infos, covered, listed, section_paths,
                            indexed_paths):
                pruned += 1
                continue
            updated = line
            # A plain-artifact line for a listed folder (promote keeps the
            # stem resolving but never re-renders the line) upgrades to the
            # folder pointer form, keeping the line's own description.
            entry = ENTRY_PATTERN.match(line)
            if entry and infos and "(folder," not in line and len(infos[0][3]) == 1:
                folder_rec = folder_by_path.get(infos[0][3][0])
                if folder_rec is not None:
                    data = folder_rec["_data"] or {}
                    desc = (entry.group("desc") or data.get("summary")
                            or data.get("title") or folder_rec["name"])
                    updated = (
                        f"{'  ' * folder_rec['depth']}- [[{_link_name(folder_rec)}]] "
                        f"(folder, {_child_count(folder_rec, records)} children)"
                        f" - {desc}"
                    )
                    if updated != line:
                        rewrites += 1
            for raw, split_at, target, resolved in infos:
                if resolved:
                    indexed_paths.update(resolved)
                    if len(resolved) == 1 and "(folder," in updated:
                        folder_rec = folder_by_path.get(resolved[0])
                        if folder_rec is not None:
                            count = _child_count(folder_rec, records)
                            fresh = re.sub(
                                r"\(folder, \d+ children\)",
                                f"(folder, {count} children)",
                                updated,
                            )
                            if fresh != updated:
                                updated = fresh
                                rewrites += 1
                    continue
                legacy_record = legacy.get(target)
                if legacy_record is not None:
                    # Keep any `#heading`/`|alias` suffix intact - only the
                    # identity portion of the link changes.
                    suffix = raw[split_at:]
                    updated = updated.replace(
                        f"[[{raw}]]", f"[[{legacy_record['name']}{suffix}]]"
                    )
                    indexed_paths.add(_rel_path(vault_root, legacy_record))
                    rewrites += 1
            section_lines.append(updated)
        lines[start + 1:end] = section_lines
        # Pruned lines shrank the section; the insertion point below must
        # track the new end or it lands past the next heading.
        end = start + 1 + len(section_lines)

        missing = [r for r in recs if _rel_path(vault_root, r) not in indexed_paths]
        if not missing:
            continue
        new_lines = [_entry_line(r, _child_count(r, records)) for r in missing]

        insert_at = end
        while insert_at - 1 > start and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines[insert_at:insert_at] = new_lines
        added[key] = len(new_lines)

    if added or rewrites or pruned or sections_merged or not existed:
        vaultlib.write_text_lf(index_path, "\n".join(lines))
    return added, pruned, sections_merged


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
        f'    summary: {vaultlib.yaml_double_quote(data["summary"])}'
    )
    if data.get("escalated") not in (None, ""):
        row += f'\n    escalated: {data["escalated"]}'
    return row


def _sync_catalog(vault_root, records):
    """Append missing lesson rows to the root catalog, aggregating lessons
    from unit `lessons/` dirs so nested lessons stay on the hot path. The
    filename is the row key; two lesson files sharing a filename are a
    collision - reported, and only the first (by vault path) gets a row.
    The empty-list marker `lessons: []` is replaced with the block-sequence
    header `lessons:` the moment any row sits under it, whether newly
    appended in this run or already present, so the file is always valid
    YAML. Duplicate rows for one filename - a second writer inserting a row
    the hook already appended - collapse to the first block, and the count
    removed is returned so the repair is reported rather than silent."""
    catalog_path = vault_root / "meta" / "lessons-catalog.yaml"
    if not catalog_path.is_file():
        return 0, [], 0, 0
    text = vaultlib.read_vault_text(catalog_path)
    text, duplicates_removed = _collapse_duplicate_rows(text)
    existing = set(re.findall(r'file:\s*"?([^"\n]+)"?', text))
    by_filename = {}
    for record in records:
        if record["type_dir"] != "lessons" or record["kind"] == "folder-index":
            # Only lesson files belong in the catalog; a domain folder's own
            # index.md is a scope note, not a lesson.
            continue
        by_filename.setdefault(record["path"].name, []).append(record)
    text, healed = _heal_misparsed_rows(text, by_filename)
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

    corrupted = bool(existing) and bool(LESSONS_EMPTY_MARKER.search(text))
    if rows or corrupted or duplicates_removed or healed:
        text = LESSONS_EMPTY_MARKER.sub("lessons:", text, count=1)
        if rows:
            text = text.rstrip("\n") + "\n" + "\n".join(rows) + "\n"
        vaultlib.write_text_lf(catalog_path, text)
    return len(rows), collisions, duplicates_removed, healed


CATALOG_ROW_START = re.compile(r"(?m)^(?=  - file: )")

# The residue a pre-block-scalar parser left in catalog rows: a summary
# holding just the `>` / `|` indicator it read as the whole value.
MISPARSED_SUMMARY = re.compile(r'(?m)^    summary: "?[>|][+-]?"?\s*$')


def _heal_misparsed_rows(text, by_filename):
    """Regenerate rows whose summary is a bare block-scalar indicator. The
    row is derived state and the lesson file's frontmatter (now parsed with
    block-scalar support) is the source; a row for a file that no longer
    exists or still lacks fields stays as it is. Returns (text, healed)."""
    blocks = CATALOG_ROW_START.split(text)
    if len(blocks) < 2:
        return text, 0
    head, rows = blocks[0], blocks[1:]
    healed = 0
    kept = []
    for block in rows:
        if MISPARSED_SUMMARY.search(block):
            match = re.match(r'  - file:\s*"?([^"\n]+)"?', block)
            recs = by_filename.get(match.group(1)) if match else None
            row = _catalog_row(match.group(1), recs[0]["_data"]) if recs else None
            if row:
                kept.append(row + ("\n" if block.endswith("\n") else ""))
                healed += 1
                continue
        kept.append(block)
    if not healed:
        return text, 0
    return head + "".join(kept), healed


def _collapse_duplicate_rows(text):
    """Keep the first row block per filename; return (text, removed).

    A block starts at a line beginning with `  - file: ` and runs to the
    next such line, so a `file:` token inside a summary string is never a
    boundary. The first occurrence wins: it is the one the hook wrote from
    the lesson's frontmatter."""
    blocks = CATALOG_ROW_START.split(text)
    if len(blocks) <= 2:
        return text, 0
    head, rows = blocks[0], blocks[1:]
    seen, kept, removed = set(), [], 0
    for block in rows:
        match = re.match(r'  - file:\s*"?([^"\n]+)"?', block)
        key = match.group(1) if match else block
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(block)
    if not removed:
        return text, 0
    return head + "".join(kept), removed


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


def _hot_path_marker(breakdown, total):
    parts = ", ".join(f"{rel} {count}" for rel, count in breakdown)
    return (
        f"{HOT_PATH_WARNING_PREFIX}{total} / {hot_path.HOT_PATH_CAP} tokens "
        f"({parts}). Run /compass:consolidate before next session. -->"
    )


def _hot_path_breakdown(vault_root, index_text):
    """Per-file token counts for the hot path. index.md's text comes from the
    caller so the count excludes any marker already prepended to it; counting
    a marker would let it hold itself above the cap."""
    breakdown = []
    for rel in hot_path.HOT_PATH_FILES:
        if rel == "index.md":
            breakdown.append((rel, vaultlib.count_tokens(index_text)))
            continue
        path = vault_root / rel
        if path.is_file():
            breakdown.append((rel, vaultlib.count_tokens(path.read_text(encoding="utf-8"))))
    return breakdown


def _check_hot_path_cap(vault_root, index_path):
    """Write, refresh, or clear index.md's aggregate hot-path marker.

    Every component cap can pass while the three hot-path files together
    breach the budget each turn pays for. This measures the total and records
    the per-file breakdown that names which file to cut. The marker is
    regenerated from current numbers and removed once the total is back under
    the cap; index.md is rewritten only when its text actually changes."""
    if not index_path.is_file():
        return False
    text = index_path.read_text(encoding="utf-8")
    stripped = "\n".join(
        line for line in text.split("\n")
        if not line.startswith(HOT_PATH_WARNING_PREFIX)
    )
    breakdown = _hot_path_breakdown(vault_root, stripped)
    total = sum(count for _, count in breakdown)
    over = total > hot_path.HOT_PATH_CAP
    desired = _hot_path_marker(breakdown, total) + "\n" + stripped if over else stripped
    if desired != text:
        vaultlib.write_text_lf(index_path, desired)
    return over


def _replace_section(text, heading, body_lines):
    """Replace `heading`'s section (through the next `## ` heading or EOF)
    with `body_lines`, appending the section when the heading is absent.
    Everything outside the section - frontmatter, Scope prose - is untouched.
    """
    lines = text.splitlines()
    block = [heading, ""] + body_lines
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        merged = lines + [""] + block
    else:
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
            len(lines),
        )
        merged = lines[:start] + block + [""] + lines[end:]
    return "\n".join(merged).rstrip("\n") + "\n"


def _lesson_listing_line(record):
    summary = (record["_data"] or {}).get("summary") or ""
    name = record["name"]
    link = f"[[{name}|{record['path'].stem}]]" if "/" in name else f"[[{name}]]"
    return f"- {link} - {summary}" if summary else f"- {link}"


def _sync_lessons_indexes(vault_root, records):
    """Regenerate the `## Lessons` listing of `lessons/index.md` and of every
    lessons domain's `index.md` from lesson frontmatter, so lessons load like
    every other type dir: the type-root index carries the high-level surface
    (domains with counts, loose root lessons), each domain index lists its own
    members with summaries, and agents grep these instead of a monolithic
    catalog. Hand-written Scope prose is never touched. Returns the number of
    index files rewritten."""
    lessons_dir = vault_root / "lessons"
    if not lessons_dir.is_dir():
        return 0
    active = [
        r for r in records
        if r["type_dir"] == "lessons" and r["kind"] != "folder-index"
        and (r["_data"] or {}).get("status") != "archived"
    ]
    folders = sorted(
        (r for r in records
         if r["type_dir"] == "lessons" and r["kind"] == "folder-index"),
        key=lambda r: r["name"],
    )

    def direct_members(folder_name):
        prefix = folder_name + "/"
        return sorted(
            (r for r in active
             if r["name"].startswith(prefix) and "/" not in r["name"][len(prefix):]),
            key=lambda r: r["name"],
        )

    rewritten = 0
    for folder in folders:
        body = [_lesson_listing_line(r) for r in direct_members(folder["name"])]
        path = folder["path"]
        text = path.read_text(encoding="utf-8")
        desired = _replace_section(text, "## Lessons", body)
        if desired != text:
            vaultlib.write_text_lf(path, desired)
            rewritten += 1

    root_index = lessons_dir / "index.md"
    if not root_index.is_file() and (active or folders):
        # A vault with lessons but no lessons surface (an install that
        # predates the index hierarchy) gets a minimal one, so the hot
        # path's lessons file exists everywhere lessons do.
        today = datetime.date.today().isoformat()
        vaultlib.write_text_lf(root_index, (
            "---\n"
            'title: "lessons"\n'
            "type: domain\n"
            "status: active\n"
            "tags: [lessons]\n"
            'summary: "lessons learned - the surface agents grep first; '
            'compass lessons ranks via meta/lessons-catalog.yaml"\n'
            f"created: {today}\n"
            f"updated: {today}\n"
            "---\n\n"
            "# lessons\n\n"
            "## Scope\n\n"
            "Class here: lessons learned - 5-line bodies, listed below "
            "with their summaries.\n"
        ))
        rewritten += 1
    if root_index.is_file():
        body = []
        for folder in folders:
            count = len(direct_members(folder["name"]))
            summary = (folder["_data"] or {}).get("summary") or ""
            label = folder["path"].parent.name
            line = f"- [[{folder['name']}/index|{label}]] ({count} lessons)"
            body.append(f"{line} - {summary}" if summary else line)
        body.extend(
            _lesson_listing_line(r)
            for r in sorted(
                (r for r in active if "/" not in r["name"]),
                key=lambda r: r["name"],
            )
        )
        text = root_index.read_text(encoding="utf-8")
        desired = _replace_section(text, "## Lessons", body)
        if desired != text:
            vaultlib.write_text_lf(root_index, desired)
            rewritten += 1
    return rewritten


def _check_caps(vault_root, records):
    warnings = []
    index_path = vault_root / "index.md"
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8")
        # Measure without the warning line itself, so its own tokens can
        # neither trip the cap nor keep the warning alive at the boundary.
        stripped = "\n".join(
            line for line in text.split("\n") if line != INDEX_WARNING
        )
        over = (
            vaultlib.count_tokens(stripped) > INDEX_TOKEN_CAP
            or len(stripped.splitlines()) > INDEX_LINE_CAP
        )
        if over and INDEX_WARNING not in text:
            vaultlib.write_text_lf(index_path, INDEX_WARNING + "\n" + text)
            warnings.append("index.md")
        elif not over and INDEX_WARNING in text:
            vaultlib.write_text_lf(index_path, stripped)

    catalog_path = vault_root / "meta" / "lessons-catalog.yaml"
    if catalog_path.is_file():
        ctext = vaultlib.read_vault_text(catalog_path)
        # Measure without the warning line itself, so a stale warning can
        # neither trip the line cap nor keep itself alive at the boundary.
        stripped_cat = "\n".join(
            line for line in ctext.split("\n") if line != CATALOG_WARNING
        )
        lesson_count = sum(
            1 for r in records
            if r["type_dir"] == "lessons"
            and r["kind"] != "folder-index"  # domain scope notes are not lessons
            and r["_data"].get("status") != "archived"
        )
        over_cat = (
            len(stripped_cat.splitlines()) > CATALOG_LINE_CAP
            or len(stripped_cat.encode("utf-8")) > CATALOG_BYTE_CAP
            or lesson_count > LESSON_COUNT_CAP
        )
        if over_cat and CATALOG_WARNING not in ctext:
            vaultlib.write_text_lf(catalog_path, CATALOG_WARNING + "\n" + ctext)
            warnings.append("lessons-catalog.yaml")
        elif not over_cat and CATALOG_WARNING in ctext:
            vaultlib.write_text_lf(catalog_path, stripped_cat)

    if _check_hot_path_cap(vault_root, index_path):
        warnings.append("hot path")
    return warnings


def _prune_capture_log(vault_root):
    """Move rows of `tmp/capture-log.jsonl` older than
    `CAPTURE_LOG_MAX_AGE_DAYS` into `archive/logs/capture-log-archive.jsonl`,
    keyed by each row's own `at` timestamp rather than the file's mtime,
    since the whole log lives in one continuously-appended file. A line that
    cannot be parsed or dated ages out with them - archived, not judged, so
    even a corrupt row survives somewhere."""
    path = vault_root / "tmp" / "capture-log.jsonl"
    if not path.is_file():
        return 0
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=CAPTURE_LOG_MAX_AGE_DAYS
    )
    kept, aged = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
            at = datetime.datetime.fromisoformat(row["at"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError, AttributeError):
            aged.append(stripped)
            continue
        if at < cutoff:
            aged.append(stripped)
            continue
        kept.append(stripped)
    if aged:
        archive = vault_root / "archive" / "logs" / "capture-log-archive.jsonl"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with open(archive, "a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(aged) + "\n")
        text = "\n".join(kept) + ("\n" if kept else "")
        vaultlib.write_text_lf(path, text)
    return len(aged)


def _clean_logs(vault_root):
    """Age stale logs out of `tmp/` into `archive/logs/` - moved, never
    deleted: nothing in Compass destroys information; a log too old for the
    working set gets colder, not gone. Whole files (`extraction-log-*.md`,
    `worker-logs/*.log`) move past `LOG_MAX_AGE_DAYS` (ADR-013 D-07's aging
    clause); rows of `capture-log.jsonl` past `CAPTURE_LOG_MAX_AGE_DAYS` - a
    much longer horizon, since a fleet-wide fire-rate measurement needs to
    look back further than one month - append to
    `archive/logs/capture-log-archive.jsonl` before leaving the live file.
    Returns `(logs_archived, capture_rows_archived)`.
    """
    tmp = vault_root / "tmp"
    if not tmp.is_dir():
        return 0, 0
    archive_dir = vault_root / "archive" / "logs"
    cutoff = time.time() - LOG_MAX_AGE_DAYS * 86400
    moved = 0
    aged = [log for log in tmp.glob("extraction-log-*.md")
            if log.is_file() and log.stat().st_mtime < cutoff]
    worker_logs_dir = tmp / "worker-logs"
    if worker_logs_dir.is_dir():
        aged.extend(log for log in worker_logs_dir.glob("*.log")
                    if log.is_file() and log.stat().st_mtime < cutoff)
    for log in aged:
        archive_dir.mkdir(parents=True, exist_ok=True)
        dest = archive_dir / log.name
        # A name collision keeps both: the archived copy is the record.
        counter = 1
        while dest.exists():
            dest = archive_dir / f"{log.stem}-{counter}{log.suffix}"
            counter += 1
        try:
            log.replace(dest)
            moved += 1
        except OSError:
            pass  # a locked file just waits for the next sync
    return moved, _prune_capture_log(vault_root)


def sync(vault_root):
    """Run every sync step over the whole vault. Returns a report dict."""
    active_swept = sweep.sweep_active(vault_root, apply=True)
    records = vaultlib.scan_artifacts(vault_root)
    _load_data(records)
    index_added, index_pruned, index_sections_merged = _sync_index(vault_root, records)
    catalog_added, catalog_collisions, catalog_duplicates, catalog_healed = (
        _sync_catalog(vault_root, records))
    lessons_indexes = _sync_lessons_indexes(vault_root, records)
    logs_deleted, capture_log_pruned = _clean_logs(vault_root)
    return {
        "active_swept": active_swept,
        "index_added": index_added,
        "index_pruned": index_pruned,
        "index_sections_merged": index_sections_merged,
        "catalog_added": catalog_added,
        "catalog_collisions": catalog_collisions,
        "catalog_duplicates_removed": catalog_duplicates,
        "catalog_rows_healed": catalog_healed,
        "lessons_indexes": lessons_indexes,
        "tags": _sync_tag_index(vault_root, records),
        "caps": _check_caps(vault_root, records),
        "logs_deleted": logs_deleted,
        "capture_log_pruned": capture_log_pruned,
    }


def format_report(report):
    parts = ["## Sync"]
    swept = report.get("active_swept") or {}
    if swept.get("items") or swept.get("sections"):
        parts.append(
            f"active.md swept: {swept['items']} item(s), "
            f"{swept['sections']} whole section(s) -> archive/done.md"
        )
    for atype, count in report["index_added"].items():
        parts.append(f"index: +{count} {atype}")
    if report.get("index_pruned"):
        parts.append(f"index: -{report['index_pruned']} stale/duplicate line(s)")
    if report.get("index_sections_merged"):
        parts.append(
            f"index: merged {report['index_sections_merged']} duplicate heading(s)"
        )
    if report["catalog_added"]:
        parts.append(f"catalog rows added: {report['catalog_added']}")
    for collision in report["catalog_collisions"]:
        parts.append(f"catalog filename collision: {collision}")
    if report.get("catalog_duplicates_removed"):
        parts.append(f"catalog duplicate rows removed: {report['catalog_duplicates_removed']}")
    if report.get("catalog_rows_healed"):
        parts.append(
            f"catalog rows healed (block-scalar summary): {report['catalog_rows_healed']}"
        )
    if report.get("lessons_indexes"):
        parts.append(f"lessons indexes refreshed: {report['lessons_indexes']}")
    parts.append(f"tags indexed: {report['tags']}")
    if report["caps"]:
        parts.append(f"caps exceeded (warning written): {', '.join(report['caps'])}")
    if report["logs_deleted"]:
        parts.append(f"logs aged to archive/logs: {report['logs_deleted']}")
    if report["capture_log_pruned"]:
        parts.append(f"capture-log rows aged to archive/logs: {report['capture_log_pruned']}")
    return "\n".join(parts)


def _is_generated_output(file_path):
    norm = str(file_path).replace("\\", "/")
    if "/.compass/" in norm:
        rel = norm.split("/.compass/", 1)[1]
    else:
        rel = norm.split(".compass/", 1)[-1]
    return rel in GENERATED_OUTPUTS


def _record_write_signal(vault_root, norm):
    """Record a capture signal for a hook-mode vault write that already
    passed the self-filter above: `handoff-written` for a path under
    `handoffs/`, `vault-write` otherwise, keyed on the vault-relative POSIX
    path of the written file. Any failure here (a capturelib error, a
    corrupt state file) is swallowed - the sync report and exit code must
    never depend on this bookkeeping.

    Never called under `COMPASS_WORKER_SESSION` (ADR-013 D-11) - see `run`'s
    hook branch. The worker's own vault writes (new lessons) still need the
    index synced, which is why this function is skipped rather than the
    whole hook branch: recording a signal here would manufacture the exact
    due() evidence that reopens the capture loop on itself."""
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
            if not os.environ.get("COMPASS_WORKER_SESSION"):
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
