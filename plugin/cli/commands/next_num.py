"""`compass next-num <type> [scope]` - next local artifact number.

Computes max+1 from the filesystem, scoped to a single folder so numbering is
local per folder (a subtree stays portable). The optional scope is either a
unit folder name (numbering runs inside the unit's own type dir, e.g.
`next-num spec compass-cli` scans `compass-cli/specs/`) or a folder-artifact
name inside the root type dir. Scopes that traverse outside the vault are
rejected. Reads nothing but directory names and the unit marker.
"""

import re
import sys
from pathlib import Path

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
        sys.stderr.write("usage: compass next-num <type> [scope]\n")
        return 1
    type_name = args[0]
    scope = args[1] if len(args) > 1 else None

    type_dir = vaultlib.TYPE_TO_DIR.get(type_name)
    prefix = PREFIX.get(type_name)
    if not type_dir or not prefix:
        sys.stderr.write(f"compass next-num: type '{type_name}' is not numbered\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    if scope:
        parts = scope.replace("\\", "/").split("/")
        if ".." in parts or Path(scope).is_absolute():
            sys.stderr.write(f"compass next-num: scope '{scope}' leaves the vault\n")
            return 1
        if scope in vaultlib.classify_root_dirs(vault_root)["units"]:
            base = vault_root / scope / type_dir
        else:
            base = vault_root / type_dir / scope
    else:
        base = vault_root / type_dir

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
