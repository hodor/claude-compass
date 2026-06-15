"""`compass next-num <type> [parent]` - next local artifact number.

Computes max+1 from the filesystem, scoped to a single folder so numbering is
local per folder (a subtree stays portable). Reads nothing but directory names.
"""

import re
import sys

import vaultlib

PREFIX = {
    "spec": "SPEC",
    "plan": "PLAN",
    "research": "RESEARCH",
    "decision": "ADR",
    "lesson": "LESSON",
    "pr": "PR",
}


def run(args):
    if not args:
        sys.stderr.write("usage: compass next-num <type> [parent]\n")
        return 1
    type_name = args[0]
    parent = args[1] if len(args) > 1 else None

    type_dir = vaultlib.TYPE_TO_DIR.get(type_name)
    prefix = PREFIX.get(type_name)
    if not type_dir or not prefix:
        sys.stderr.write(f"compass next-num: type '{type_name}' is not numbered\n")
        return 1

    base = vaultlib.find_vault_root() / type_dir
    if parent:
        base = base / parent

    pattern = re.compile(rf"^{prefix}-(\d+)-")
    highest = 0
    if base.is_dir():
        for entry in base.iterdir():
            stem = entry.stem if entry.is_file() else entry.name
            match = pattern.match(stem)
            if match:
                highest = max(highest, int(match.group(1)))

    sys.stdout.write(f"{highest + 1:03d}\n")
    return 0
