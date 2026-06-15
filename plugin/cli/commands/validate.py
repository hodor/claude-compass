"""`compass validate` - vault integrity check.

Reports two severities. Errors are things that break machine-readability (a
file with no frontmatter, or missing a core field title/type/status) and make
the command exit 1. Warnings are advisory (dangling wikilinks, missing
recommended fields, hot-path cap breaches) and do not fail the command -
dangling links are valid stubs in an Obsidian vault. Wikilinks resolve against
every markdown file in the vault, including archive/ and custom type dirs.
"""

import re
import sys
from pathlib import Path

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
INDEX_LINE_CAP = 250

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
INLINE_CODE = re.compile(r"`[^`]*`")


def _resolvable_names(vault_root):
    """Every name a wikilink may resolve to, drawn from all vault markdown.

    Includes each file's bare stem, a folder spec's folder name, and the
    path-qualified name (relative to the vault, no extension). Covers archive/
    and any custom type dir so links there are not flagged.
    """
    vault_root = Path(vault_root)
    names = set(SPECIAL_TARGETS)
    for path in vaultlib.all_markdown_files(vault_root):
        names.add(path.stem)
        if path.name == "index.md":
            names.add(path.parent.name)
        rel = path.relative_to(vault_root).with_suffix("")
        names.add(str(rel).replace("\\", "/"))
    return names


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
    names = _resolvable_names(vault_root)

    for record in records:
        path = record["path"]
        rel = f"{record['type_dir']}/{record['rel']}"
        data, error = vaultlib.parse_frontmatter(path)
        if error:
            errors.append(f"frontmatter_error: {rel}: {error}")
            continue
        for field in EXPECTED_FIELDS.get(data.get("type"), CORE_REQUIRED):
            if data.get(field) in (None, "", []):
                msg = f"frontmatter_missing_field: {rel}: {field}"
                (errors if field in CORE_REQUIRED else warnings).append(msg)

        for lineno, target in _wikilinks_in(path.read_text(encoding="utf-8")):
            if target not in names:
                warnings.append(f"broken_wikilink: {rel}:{lineno}: [[{target}]]")

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
