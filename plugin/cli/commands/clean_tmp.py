"""`compass clean-tmp` - delete extraction logs older than 30 days."""

import sys

import vaultlib
from commands.sync import _clean_logs


def run(args):
    deleted = _clean_logs(vaultlib.find_vault_root())
    sys.stdout.write(f"extraction logs deleted: {deleted}\n")
    return 0
