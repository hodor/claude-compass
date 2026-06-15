"""`compass admit-check <spec>` - hot-path admission control (ADR-004).

Exits 0 if the spec may enter the hot path: it is in the working set AND adding
its tokens keeps the hot path under the cap. Exits 1 otherwise, signalling the
agent to reach the spec through the tag index or folder navigation instead.
"""

import sys

import vaultlib
from commands.hot_path import HOT_PATH_CAP, measure
from commands.touched import load


def run(args):
    if not args:
        sys.stderr.write("usage: compass admit-check <spec>\n")
        return 1
    spec = args[0]
    vault_root = vaultlib.find_vault_root()

    if spec not in load(vault_root):
        return 1

    spec_path = vault_root / spec
    spec_tokens = 0
    if spec_path.is_file():
        spec_tokens = vaultlib.count_tokens(spec_path.read_text(encoding="utf-8"))

    return 0 if measure(vault_root) + spec_tokens <= HOT_PATH_CAP else 1
