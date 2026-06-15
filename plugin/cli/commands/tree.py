"""`compass tree` - render the spec/folder hierarchy.

Indents two spaces per folder depth and marks folder specs with a trailing
slash, so the shape of a nested spec tree is visible at a glance.
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


def render(vault_root):
    records = [r for r in vaultlib.scan_artifacts(vault_root) if r["type_dir"] == "specs"]
    records.sort(key=_sort_key)
    lines = ["specs"]
    for record in records:
        label = record["name"].split("/")[-1]
        if record["kind"] == "folder-index":
            label += "/"
        lines.append("  " * (record["depth"] + 1) + label)
    return "\n".join(lines)


def run(args):
    sys.stdout.write(render(vaultlib.find_vault_root()) + "\n")
    return 0
