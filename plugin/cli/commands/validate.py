"""`compass validate` - vault integrity check.

Reports two severities. Errors are things that break machine-readability (a
file with no frontmatter, or missing a core field title/type/status) and make
the command exit 1. Warnings are advisory (dangling wikilinks, ambiguous
wikilinks, unclassified root folders, missing recommended fields, hot-path cap
breaches, unreconciled sizing decisions) and do not fail the command -
dangling links are valid stubs in an Obsidian vault. Wikilinks resolve through
`vaultlib.resolvable_names_map`, the same resolution `sync` emits against,
covering every markdown file in the vault including archive/ and custom type
dirs. A link name that maps to more than one file is flagged
`ambiguous_wikilink`; a root folder that is neither reserved, a marked unit,
nor a typed artifact dir is flagged `unclassified_root_folder` - reported for
the human, never guessed at. Every unit folder and folder spec on disk is
checked against `.compass/meta/sizing-log.yaml` (ADR-011 D-08): a `sizing_id`
absent from frontmatter is flagged `sizing_unrecorded`, and a `sizing_id`
present but naming no row in the log is flagged `sizing_orphaned_id` -
neither ever changes the exit code, since the vault predates the log and
every pre-existing shape starts out unrecorded.
"""

import re
import sys

import vaultlib
from commands import sizing
from commands import sweep
from commands.hot_path import HOT_PATH_CAP, measure

# Missing one of these is an error - the artifact cannot be classified/indexed.
CORE_REQUIRED = ["title", "type", "status"]

# Full expected frontmatter per known type. Anything here beyond CORE_REQUIRED
# is recommended: missing it is a warning, not an error.
# `summary` is expected on every type: the root index renders it as the
# artifact's one-line description, so an artifact without one leaves that line
# as the only copy of its description and the index can never be shortened
# without losing it.
EXPECTED_FIELDS = {
    "spec": ["title", "type", "status", "area", "tags", "created", "updated", "summary"],
    "plan": ["title", "type", "status", "area", "tags", "created", "updated", "depends_on", "summary"],
    "research": ["title", "type", "status", "area", "tags", "created", "updated", "summary"],
    "decision": ["title", "type", "status", "confidence", "area", "tags", "created", "updated", "summary"],
    "lesson": ["title", "type", "status", "category", "area", "tags", "created", "updated", "score", "summary"],
    "handoff": ["title", "type", "status", "area", "tags", "created", "updated", "summary"],
    "domain": ["title", "type", "status", "tags", "created", "updated", "summary"],
}

# Direct-children ceiling for taxonomy-governed folders (the type dirs
# specs/, research/, decisions/, and lessons/, and every domain folder
# inside them - lessons and ADRs taxonomize like everything else, SPEC-022
# D-12). Past it, validate suggests a split; the number is a tunable
# default, and exempt dirs (plans/ mirror their specs; handoffs/ and prs/
# are chronological) never warn so the suggestion stays meaningful.
FOLDER_CEILING = 12
CEILING_GOVERNED_DIRS = ("specs", "research", "decisions", "lessons")

SPECIAL_TARGETS = {"active", "backlog", "index", "vision"}
# Top-level vault files whose own wikilinks are validated. A stale index entry
# (a link to a deleted artifact) surfaces here, since sync is append-only for
# index.md and cannot remove it.
TOP_LEVEL_FILES = ["index.md", "active.md", "backlog.md", "vision.md"]
INDEX_LINE_CAP = 250

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INLINE_CODE = re.compile(r"`[^`]*`")


def _check_links(rel, text, resolve, warnings):
    """Append a warning for each wikilink in `text` that does not resolve to
    exactly one file: `broken_wikilink` when the name maps to nothing,
    `ambiguous_wikilink` (with every matching path listed) when it maps to
    more than one. `resolve` is `vaultlib.resolvable_names_map` output, the
    same resolution `sync` emits links against."""
    for lineno, target in _wikilinks_in(text):
        if target in SPECIAL_TARGETS:
            continue
        paths = resolve.get(target)
        if paths is None:
            warnings.append(f"broken_wikilink: {rel}:{lineno}: [[{target}]]")
        elif len(paths) > 1:
            listed = ", ".join(sorted(paths))
            warnings.append(f"ambiguous_wikilink: {rel}:{lineno}: [[{target}]] -> {listed}")


def _wikilinks_in(text):
    """Yield (line_number, target) for wikilinks outside code blocks/spans."""
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        cleaned = INLINE_CODE.sub("", line)
        for match in WIKILINK.finditer(cleaned):
            target = match.group(1).split("#")[0].split("|")[0].strip()
            if target:
                yield lineno, target


def _check_sizing_id(name, path, known_ids, warnings):
    """Append a `sizing_unrecorded` or `sizing_orphaned_id` warning for one
    unit folder or folder spec, or nothing when its `sizing_id` resolves in
    `known_ids`. `name` is the artifact's wikilink identity; `path` is its
    own `index.md`. A frontmatter parse error is skipped rather than
    warned on here - a broken artifact is already reported once, as
    `frontmatter_error`, by `check_vault`'s main loop."""
    data, error = vaultlib.parse_frontmatter(path)
    if error:
        return
    sizing_id = data.get("sizing_id")
    if not sizing_id:
        warnings.append(
            f"sizing_unrecorded: {name}: predates the sizing log, no "
            f"sizing_id recorded"
        )
    elif sizing_id not in known_ids:
        warnings.append(
            f"sizing_orphaned_id: {name}: sizing_id {sizing_id} names "
            f"no row in the sizing log"
        )


def _reconcile_sizing(vault_root, layout, records, warnings):
    """Warn about every unit folder and folder spec on disk whose shape
    change was never reconciled against `.compass/meta/sizing-log.yaml`
    (ADR-011 D-08): a `sizing_id` absent from frontmatter names a shape that
    predates the log, and a `sizing_id` present but naming no row in the log
    names an orphaned id - reported as two distinct warning classes so
    neither reading is mistaken for the other. A missing log file is not a
    crash: it parses as zero rows, so every id present is correctly reported
    orphaned and every id absent is correctly reported unrecorded. A folder
    spec that a *decision to stay flat* would have avoided is out of reach
    here - reconciliation only sees artifacts that already exist on disk.
    """
    log_path = sizing.log_path(vault_root)
    log_text = vaultlib.read_vault_text(log_path) if log_path.is_file() else ""
    rows, _skipped = sizing.parse_log(log_text)
    known_ids = {row["id"] for row in rows}

    for name in layout["units"]:
        _check_sizing_id(name, vault_root / name / "index.md", known_ids, warnings)
    for record in records:
        if record["kind"] == "folder-index":
            _check_sizing_id(record["name"], record["path"], known_ids, warnings)


def _taxonomy_checks(vault_root, records, warnings):
    """The taxonomy's standing suggestions: `folder_over_ceiling` when a
    governed folder's direct children pass the ceiling, `empty_scope` when
    a domain's Scope has no Class-here line, and `taxonomy_hints: N
    pending` naming every artifact whose author recorded placement doubt.
    Suggestions surface on every run so nothing waits on anyone's memory;
    all are warnings and never touch the exit code."""
    for root_name in CEILING_GOVERNED_DIRS:
        base = vault_root / root_name
        if not base.is_dir():
            continue
        # The type-dir root appears both as `base` and as its own
        # index.md's parent once it carries one; dedupe so each folder
        # warns at most once.
        candidates = list(dict.fromkeys(
            [base] + [p.parent for p in base.rglob("index.md")]
        ))
        for folder in candidates:
            children = [
                e for e in folder.iterdir()
                if e.name != "index.md" and not e.name.startswith(".")
                and (e.suffix == ".md" or e.is_dir())
            ]
            if len(children) > FOLDER_CEILING:
                rel = folder.relative_to(vault_root).as_posix()
                warnings.append(
                    f"folder_over_ceiling: {rel}: {len(children)} direct children "
                    f"(ceiling {FOLDER_CEILING}) - a split is worth proposing"
                )

    hints = []
    for record in records:
        data = record.get("_v_data")
        if data is None:
            data, error = vaultlib.parse_frontmatter(record["path"])
            if error:
                continue
        if data.get("type") == "domain":
            body = record["path"].read_text(encoding="utf-8")
            if not any(l.startswith("Class here:") for l in body.splitlines()):
                rel = record["path"].relative_to(vault_root).as_posix()
                warnings.append(
                    f"empty_scope: {rel}: Scope has no Class-here line - a blank "
                    f"at the point of doubt reads as 'nothing belongs here'"
                )
        if data.get("taxonomy_hint"):
            hints.append(record["path"].stem if record["path"].name != "index.md"
                         else record["path"].parent.name)
    if hints:
        warnings.append(
            f"taxonomy_hints: {len(hints)} pending - {', '.join(sorted(hints))}"
        )


def check_vault(vault_root):
    """Return (errors, warnings), each a list of human-readable strings."""
    errors, warnings = [], []
    records = vaultlib.scan_artifacts(vault_root)
    resolve = vaultlib.resolvable_names_map(vault_root)
    layout = vaultlib.classify_root_dirs(vault_root)

    for name in layout["unclassified"]:
        warnings.append(
            f"unclassified_root_folder: {name}: holds markdown but is not a "
            f"reserved dir, has no 'type: unit' index.md marker, and has no "
            f"typed artifacts - not scanned"
        )

    for record in records:
        path = record["path"]
        rel = str(path.relative_to(vault_root)).replace("\\", "/")
        data, error = vaultlib.parse_frontmatter(path)
        if error:
            errors.append(f"frontmatter_error: {rel}: {error}")
            continue
        for field in EXPECTED_FIELDS.get(data.get("type"), CORE_REQUIRED):
            if data.get(field) in (None, "", []):
                msg = f"frontmatter_missing_field: {rel}: {field}"
                (errors if field in CORE_REQUIRED else warnings).append(msg)

        _check_links(rel, path.read_text(encoding="utf-8"), resolve, warnings)

    for rel in TOP_LEVEL_FILES:
        path = vault_root / rel
        if not path.is_file():
            continue
        _check_links(rel, path.read_text(encoding="utf-8"), resolve, warnings)

    index_path = vault_root / "index.md"
    if index_path.is_file():
        index_text = index_path.read_text(encoding="utf-8")
        if vaultlib.count_tokens(index_text) > HOT_PATH_CAP:
            warnings.append(f"cap_exceeded: index.md over {HOT_PATH_CAP} tokens")
        if len(index_text.splitlines()) > INDEX_LINE_CAP:
            warnings.append(f"cap_exceeded: index.md over {INDEX_LINE_CAP} lines")
    if measure(vault_root) > HOT_PATH_CAP:
        warnings.append(f"cap_exceeded: hot path over {HOT_PATH_CAP} tokens")

    _reconcile_sizing(vault_root, layout, records, warnings)
    _taxonomy_checks(vault_root, records, warnings)

    _, active_sections = sweep.collect(vault_root)
    lingering = sum(
        1
        for sec in active_sections
        for kind, _ in sec["blocks"]
        if kind == "done"
    )
    if lingering:
        warnings.append(
            f"active_done: {lingering} completed task(s) still in active.md "
            f"- compass sync sweeps them to archive/done.md"
        )

    return errors, warnings


def run(args):
    errors, warnings = check_vault(vaultlib.find_vault_root())
    if not errors and not warnings:
        sys.stdout.write("compass validate: clean\n")
        return 0
    sys.stderr.write(f"compass validate: {len(errors)} error(s), {len(warnings)} warning(s)\n")
    for finding in errors:
        sys.stderr.write(f"  ERROR   {finding}\n")
    for finding in warnings:
        sys.stderr.write(f"  warning {finding}\n")
    return 1 if errors else 0
