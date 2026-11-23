"""`compass requirements <spec>` - list a spec's requirements.

Prints one row per requirement with its stable id (`O-n`, `S-n`, `C-n`, `K-1`,
`D-NN`) and a 12-hex hash of its whitespace-normalized text, so an id whose
text changed shows as a changed hash. A `[deferred]` or `[informational]`
decision carries that tag in the listing.

    compass requirements <spec-path> [--json] [--for-task TASK-NNN --plan <plan>]

`--json` prints the rows as one JSON array. `--for-task` keeps every
non-decision row plus the decisions the task's plan line cites as
`decisions: [<spec-stem>/D-NN, ...]`.

Exit 0 for any readable spec, a spec with zero rows included; exit 1 for a
missing or unreadable spec or plan, a usage error, or a spec whose rows hold
the same authored id twice (the message names both lines).
"""

import json
import sys
from pathlib import Path

import requirementslib
import vaultlib

USAGE = (
    "usage: compass requirements <spec-path> [--json] "
    "[--for-task TASK-NNN --plan <plan-path>]"
)

_TAGS_SHOWN = ("deferred", "informational")


def _fail(message):
    sys.stderr.write(f"compass requirements: {message}\n")
    return 1


def _parse(args):
    """`(options, error)`: spec path, json flag, task id and plan path."""
    options = {"spec": None, "json": False, "task": None, "plan": None}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--json":
            options["json"] = True
        elif arg in ("--for-task", "--plan"):
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                return None, f"{arg} needs a value"
            options["task" if arg == "--for-task" else "plan"] = args[i + 1]
            i += 1
        elif arg.startswith("--"):
            return None, f"unknown flag {arg}"
        elif options["spec"] is None:
            options["spec"] = arg
        else:
            return None, f"unexpected argument {arg}"
        i += 1
    if options["spec"] is None:
        return None, "a spec path is required"
    if (options["task"] is None) != (options["plan"] is None):
        return None, "--for-task and --plan are used together"
    return options, None


def _spec_stem(path):
    """The name a plan cites the spec by: the file stem, or the folder name
    for a folder spec's `index.md`."""
    path = Path(path)
    return path.parent.name if path.stem == "index" else path.stem


def _listing_line(row):
    line = f"{row['id']}  {row['hash']}  {row['text']}"
    tags = [tag for tag in _TAGS_SHOWN if tag in row.get("tags", [])]
    return line + "".join(f" [{tag}]" for tag in tags)


def run(args):
    options, error = _parse(args)
    if error:
        sys.stderr.write(f"compass requirements: {error}\n{USAGE}\n")
        return 1

    spec = Path(options["spec"])
    try:
        spec_text = vaultlib.read_vault_text(spec)
    except (OSError, UnicodeDecodeError) as exc:
        return _fail(f"cannot read spec {options['spec']}: {exc}")
    duplicate = requirementslib.duplicate_report(spec_text)
    if duplicate:
        return _fail(duplicate)
    rows = requirementslib.extract_requirements(spec_text)

    if options["task"] is not None:
        try:
            plan_text = vaultlib.read_vault_text(options["plan"])
        except (OSError, UnicodeDecodeError) as exc:
            return _fail(f"cannot read plan {options['plan']}: {exc}")
        rows = requirementslib.rows_for_task(
            rows, plan_text, options["task"], _spec_stem(spec)
        )

    if options["json"]:
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
    else:
        for row in rows:
            sys.stdout.write(_listing_line(row) + "\n")
    return 0
