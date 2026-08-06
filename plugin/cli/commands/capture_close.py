"""`compass capture-close <opp-id> --outcome <outcome> [--candidates N]
[--written N] [--recurrence N] [--rejected N] [--revised N] [--archived N]
[--errors N]`

Closes a capture opportunity an extraction pass has finished processing,
the CLI surface `capturelib.close_opportunity` needed but never exposed:
Phase 1 gave it to `sync.py` and the hook commands as a library call, and
the extraction pass has no way to import Python. This command is that call,
reachable from the skill's own protocol via a shell-out instead.

Not a hook command: no `--hook` gate, no stdin, ordinary CLI error handling.
An opportunity id absent from `.compass/tmp/capture-opportunities/` or
already closed (its `opportunity.json` already carries a non-null
`outcome`) is a caller error, not a best-effort no-op - capture-close is
called exactly once per opportunity by design, so either case means the
caller has lost track of what it is closing, and silently succeeding would
hide that from the trace log. Exit 1 on either, never 2.

Count flags are optional and independent; an omitted flag is left out of
the `fired` trace row entirely rather than recorded as zero, matching
`capturelib.close_opportunity`'s own `None`-means-absent contract.
"""

import json
import sys
from pathlib import Path

import capturelib
import vaultlib

OPPORTUNITIES_DIR = ("tmp", "capture-opportunities")

# CLI flag -> close_opportunity keyword. Flag names read naturally as
# counts (plural); the keywords match the ones close_opportunity has always
# taken (mostly singular), so the mapping is not 1:1 in spelling.
COUNT_FLAGS = {
    "--candidates": "candidate",
    "--written": "written",
    "--recurrence": "recurrence",
    "--rejected": "rejected",
    "--revised": "revised",
    "--archived": "archived",
    "--errors": "error",
}

USAGE = (
    "usage: compass capture-close <opp-id> --outcome <outcome> "
    "[--candidates N] [--written N] [--recurrence N] [--rejected N] "
    "[--revised N] [--archived N] [--errors N]"
)


def _parse(args):
    """Returns `(opp_id, outcome, counts, error)` with `error` set on any
    malformed invocation - unknown flag, a flag missing its value, a
    non-integer count, more than one bare positional, or none at all."""
    opp_id = None
    outcome = None
    counts = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--outcome":
            if i + 1 >= len(args):
                return None, None, None, "--outcome expects a value"
            outcome = args[i + 1]
            i += 2
            continue
        if arg in COUNT_FLAGS:
            if i + 1 >= len(args):
                return None, None, None, f"{arg} expects an integer value"
            try:
                counts[COUNT_FLAGS[arg]] = int(args[i + 1])
            except ValueError:
                return None, None, None, f"{arg} expects an integer value"
            i += 2
            continue
        if arg.startswith("--"):
            return None, None, None, f"unknown flag {arg}"
        if opp_id is not None:
            return None, None, None, "exactly one opportunity id is expected"
        opp_id = arg
        i += 1
    if not opp_id or not outcome:
        return None, None, None, "an opportunity id and --outcome are required"
    return opp_id, outcome, counts, None


def run(args):
    opp_id, outcome, counts, error = _parse(args)
    if error:
        sys.stderr.write(f"compass capture-close: {error}\n{USAGE}\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    opp_path = Path(vault_root).joinpath(*OPPORTUNITIES_DIR) / opp_id / "opportunity.json"
    if not opp_path.is_file():
        sys.stderr.write(f"compass capture-close: unknown opportunity {opp_id}\n")
        return 1
    try:
        record = json.loads(opp_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    if isinstance(record, dict) and record.get("outcome") is not None:
        sys.stderr.write(f"compass capture-close: {opp_id} is already closed\n")
        return 1

    capturelib.close_opportunity(vault_root, opp_id, outcome, **counts)
    sys.stdout.write(f"compass capture-close: {opp_id} closed as {outcome}\n")
    return 0
