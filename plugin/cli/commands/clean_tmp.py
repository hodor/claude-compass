"""`compass clean-tmp` - delete extraction logs older than 30 days and prune
capture-log rows older than 365 days."""

import sys

import vaultlib
from commands.sync import _clean_logs


def run(args):
    deleted, capture_log_pruned = _clean_logs(vaultlib.find_vault_root())
    sys.stdout.write(f"extraction logs deleted: {deleted}\n")
    if capture_log_pruned:
        sys.stdout.write(f"capture-log rows pruned: {capture_log_pruned}\n")
    return 0
