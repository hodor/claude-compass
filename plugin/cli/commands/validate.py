"""`compass validate` - vault integrity check.

Reports two severities. Errors are things that break machine-readability (a
file with no frontmatter, or missing a core field title/type/status) and make
the command exit 1. Warnings are advisory (dangling wikilinks, ambiguous
wikilinks, unclassified root folders, missing recommended fields, hot-path cap
breaches) and do not fail the command - dangling links are valid stubs in an
Obsidian vault. Wikilinks resolve through `vaultlib.resolvable_names_map`, the
same resolution `sync` emits against, covering every markdown file in the
vault including archive/ and custom type dirs. A link name that maps to more
than one file is flagged `ambiguous_wikilink`; a root folder that is neither
reserved, a marked unit, nor a typed artifact dir is flagged
`unclassified_root_folder` - reported for the human, never guessed at.
"""

import re
import sys

import vaultlib
from commands.hot_path import HOT_PATH_CAP, measure

# Missing one of these is an error - the artifact cannot be classified/indexed.
CORE_REQUIRED = ["title", "type", "status"]

# Full expected frontmatter per known type. Anything here beyond CORE_REQUIRED
# is recommended: missing it is a warning, not an error.
EXPECTED_FIELDS = {
    "spec": ["title", "type", "status", "area", "tags", "created", "updated"],
    "plan": ["title", "type", "status", "area", "tags", "created", "updated", "depends_on"],
    "research": ["title", "type", "status", "area", "tags", "created", "updated"],
    "decision": ["title", "type", "status", "confidence", "area", "tags", "created", "updated"],
    "lesson": ["title", "type", "status", "category", "area", "tags", "created", "updated", "score", "summary"],
    "handoff": ["title", "type", "status", "area", "tags", "created", "updated"],
}

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


def check_vault(vault_root):
    """Return (errors, warnings), each a list of human-readable strings."""
    errors, warnings = [], []
    records = vaultlib.scan_artifacts(vault_root)
    resolve = vaultlib.resolvable_names_map(vault_root)

    for name in vaultlib.classify_root_dirs(vault_root)["unclassified"]:
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
