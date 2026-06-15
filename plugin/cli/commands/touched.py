"""`compass touched <spec>` - record a working-set marker.

The working set is the rolling window of specs the agent has recently touched,
the signal `admit-check` uses for hot-path admission control (ADR-004). Stored
as a simple YAML list in `meta/working-set.yaml`, most-recent last, capped.
"""

import sys

import vaultlib

WORKING_SET_MAX = 10


def working_set_path(vault_root):
    return vault_root / "meta" / "working-set.yaml"


def load(vault_root):
    path = working_set_path(vault_root)
    if not path.is_file():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def save(vault_root, items):
    path = working_set_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "working_set:\n" + "".join(f"- {item}\n" for item in items)
    vaultlib.write_text_lf(path, body)


def run(args):
    if not args:
        sys.stderr.write("usage: compass touched <spec>\n")
        return 1
    spec = args[0]
    vault_root = vaultlib.find_vault_root()
    items = load(vault_root)
    if spec in items:
        items.remove(spec)
    items.append(spec)
    save(vault_root, items[-WORKING_SET_MAX:])
    return 0
