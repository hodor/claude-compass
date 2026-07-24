"""`compass tree` - render the spec/folder hierarchy.

Indents two spaces per folder depth and marks folder specs with a trailing
slash, so the shape of a nested spec tree is visible at a glance. Unit
folders render as top-level branches after the root specs: the unit name,
then each of the unit's own type directories with their artifacts.
"""

import sys

import vaultlib


def _sort_key(record):
    # A folder's `index.md` must render before that folder's children, so its
    # final path segment sorts as empty rather than as the literal "index.md".
    parts = record["rel"].split("/")
    if parts[-1] == "index.md":
        parts[-1] = ""
    return parts


def _artifact_lines(records, base_indent):
    """Lines for one type directory's artifacts, indented `base_indent` levels
    plus each record's own folder depth."""
    lines = []
    for record in sorted(records, key=_sort_key):
        label = record["name"].split("/")[-1]
        if record["kind"] == "folder-index":
            label += "/"
        lines.append("  " * (record["depth"] + base_indent) + label)
    return lines


def render(vault_root):
    records = vaultlib.scan_artifacts(vault_root)
    root_specs = [r for r in records if r["unit"] is None and r["type_dir"] == "specs"]
    lines = ["specs"] + _artifact_lines(root_specs, 1)
    for unit in vaultlib.classify_root_dirs(vault_root)["units"]:
        lines.append(unit)
        unit_records = [r for r in records if r["unit"] == unit]
        for type_dir in vaultlib.classify_root_dirs(vault_root / unit)["type_dirs"]:
            lines.append("  " + type_dir)
            in_dir = [r for r in unit_records if r["type_dir"] == type_dir]
            lines.extend(_artifact_lines(in_dir, 2))
    return "\n".join(lines)


def run(args):
    sys.stdout.write(render(vaultlib.find_vault_root()) + "\n")
    return 0
