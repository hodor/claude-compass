"""`compass tree` - the whole vault at a glance, computed at invocation.

The root index lists only the first level and every folder below is read
live, so no single file shows everything anymore; this command renders it
on demand - every artifact under every type dir and unit, indented by
depth, each line carrying the artifact's own `summary:` (falling back to
its title). Nothing is stored: like the graph queries, the answer is
derived from the markdown at the moment it is asked for and can never be
stale.
"""

import sys

import vaultlib


def _label(record):
    if record["kind"] == "folder-index":
        return record["path"].parent.name + "/"
    return record["path"].stem


def _line(record):
    data = record.get("_data") or {}
    summary = data.get("summary") or data.get("title") or ""
    indent = "  " * (record["depth"] + 1)
    text = f"{indent}{_label(record)}"
    return f"{text} - {summary}" if summary else text


def render(vault_root):
    records = vaultlib.scan_artifacts(vault_root)
    for record in records:
        data, _ = vaultlib.parse_frontmatter(record["path"])
        record["_data"] = data
    lines = []
    groups = {}
    for record in records:
        top = record["unit"] or record["type_dir"]
        groups.setdefault(top, []).append(record)
    for top in sorted(groups):
        lines.append(top)
        # A folder whose doc is its own `index.md` renders through that
        # record; a plain grouping folder has no record, so its first
        # member emits a bare header line. Records sort with a folder's
        # index before the folder's members, keeping headers deduped.
        emitted = set()
        for record in sorted(groups[top], key=lambda r: r["name"]):
            parts = record["rel"].split("/")
            end = -2 if record["kind"] == "folder-index" else -1
            for i, part in enumerate(parts[:end]):
                folder = (record["type_dir"], "/".join(parts[: i + 1]))
                if folder not in emitted:
                    emitted.add(folder)
                    lines.append("  " * (i + 1) + part + "/")
            if record["kind"] == "folder-index":
                emitted.add((record["type_dir"], "/".join(parts[:-1])))
            lines.append(_line(record))
    return "\n".join(lines)


def run(args):
    sys.stdout.write(render(vaultlib.find_vault_root()) + "\n")
    return 0
