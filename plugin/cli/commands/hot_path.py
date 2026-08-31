"""`compass hot-path` - report the hot-path token count against the cap.

The hot path is what every agent turn loads: the root index, the active-tasks
file, and the lessons surface `lessons/index.md` - the high-level index whose
domain indexes agents grep and descend into. The full catalog stays the
machine index behind `compass lessons`, off the hot path. Read-only;
`validate` is what fails on a breach.
"""

import sys

import vaultlib

HOT_PATH_FILES = ["index.md", "active.md", "lessons/index.md"]
HOT_PATH_CAP = 5000


def measure(vault_root):
    total = 0
    for rel in HOT_PATH_FILES:
        path = vault_root / rel
        if path.is_file():
            total += vaultlib.count_tokens(path.read_text(encoding="utf-8"))
    return total


def run(args):
    total = measure(vaultlib.find_vault_root())
    sys.stdout.write(f"{total} / {HOT_PATH_CAP}\n")
    return 0
