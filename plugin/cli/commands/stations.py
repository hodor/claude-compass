"""`compass stations [--plan PLAN-NNN]` - the station log joined to task size.

Reads `.compass/meta/station-log.jsonl` (rows written by `stationlib`) and
each plan's task lines, and prints one line per (complexity letter, model,
station) group:

    letter  model  station  spawns  bugs  fails  cycles  unparsed

- `spawns`: rows of that group, fix-cycle rows excluded
- `bugs`: bugs found, summed over post-build tester rows
- `fails`: FAIL items, summed over validator rows
- `cycles`: fix-cycle rows
- `unparsed`: rows whose report matched no known form

A task line without a `complexity:` field groups under the letter `none`. Rows
whose task id is null or names no task of any plan are counted on one
`unknown task rows` line. `--plan` limits the groups to that plan's tasks; rows
belonging to other plans are left out of the report.

Read-only: nothing is written. A missing, empty or partly malformed log
reports what it holds and exits 0.
"""

import json
import re
import sys
from pathlib import Path

import planlib
import stationlib
import vaultlib

USAGE = """usage: compass stations [--plan PLAN-NNN]

Per complexity letter, model and station: spawns, bugs found, FAIL items,
fix cycles and unparsed rows, joined from the station log to the plans.
"""

_PLAN_ID = re.compile(r"^PLAN-(\d+)(?:-|$)", re.IGNORECASE)
_PLAN_ARG = re.compile(r"^PLAN-(\d+)$", re.IGNORECASE)
_LETTER_ORDER = {"XS": 0, "S": 1, "M": 2, "L": 3}
NO_LETTER = "none"
NO_VALUE = "-"
HEADER = ("letter", "model", "station", "spawns", "bugs", "fails", "cycles", "unparsed")


def _plan_number(record):
    """The PLAN number of a plan artifact (its file stem, or its folder name
    for a folder plan), or None."""
    path = record["path"]
    name = path.parent.name if record["kind"] == "folder-index" else path.stem
    match = _PLAN_ID.match(name)
    return int(match.group(1)) if match else None


def _read_plans(vault_root):
    """`[(plan number or None, {task id: letter or None})]` for every plan."""
    plans = []
    for record in vaultlib.scan_artifacts(vault_root):
        if record["type_dir"] != "plans":
            continue
        try:
            text = vaultlib.read_vault_text(record["path"])
        except (OSError, UnicodeDecodeError):
            continue
        plans.append((_plan_number(record), planlib.task_letters(text)))
    return plans


def _read_rows(vault_root):
    """The dict rows of the station log; a missing log, a blank line or a line
    that is not a JSON object yields nothing for it."""
    path = Path(vault_root).joinpath(*stationlib.LOG_PARTS)
    try:
        raw = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _count(row, key):
    value = row.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _text(value):
    return value if isinstance(value, str) and value.strip() else NO_VALUE


def _group_order(key):
    letter, model, station = key
    if letter in _LETTER_ORDER:
        rank = _LETTER_ORDER[letter]
    else:
        rank = 5 if letter == NO_LETTER else 4
    return (rank, letter, model, station)


def _parse_args(args):
    """`(plan number or None, error message or None)` from the arguments."""
    plan = None
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--plan" and rest:
            value = rest.pop(0)
        elif arg.startswith("--plan="):
            value = arg.partition("=")[2]
        else:
            return None, f"unknown argument {arg}"
        match = _PLAN_ARG.match(value)
        if not match:
            return None, f"--plan takes PLAN-NNN, got {value}"
        plan = int(match.group(1))
    return plan, None


def build_groups(rows, plans, plan_number=None):
    """`(groups, unknown)`: the per-group counts and the number of rows whose
    task id matches no plan. With `plan_number`, rows of tasks that belong to
    other plans only are left out of both."""
    owners = {}
    for number, letters in plans:
        for task, letter in letters.items():
            owners.setdefault(task, []).append((number, letter))
    groups = {}
    unknown = 0
    for row in rows:
        task = row.get("task")
        found = owners.get(task) if isinstance(task, str) else None
        if not found:
            unknown += 1
            continue
        if plan_number is not None:
            found = [pair for pair in found if pair[0] == plan_number]
            if not found:
                continue
        letter = found[0][1] or NO_LETTER
        station = _text(row.get("station"))
        key = (letter, _text(row.get("model")), station)
        counts = groups.setdefault(key, [0, 0, 0, 0, 0])
        if station == "fix-cycle":
            counts[3] += 1
        else:
            counts[0] += 1
        counts[1] += _count(row, "bugs")
        counts[2] += _count(row, "fails")
        if row.get("verdict") == stationlib.UNPARSED:
            counts[4] += 1
    return groups, unknown


def render(groups, unknown):
    """The report lines: an aligned table, or a note when no row joined, then
    the unknown-task line when any row matched no plan."""
    if groups:
        table = [HEADER]
        for key in sorted(groups, key=_group_order):
            table.append(key + tuple(str(n) for n in groups[key]))
        widths = [max(len(row[col]) for row in table) for col in range(len(HEADER))]
        lines = [
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
            for row in table
        ]
    else:
        lines = ["no station rows joined to a task"]
    if unknown:
        lines.append(f"unknown task rows: {unknown}")
    return lines


def run(args):
    plan_number, error = _parse_args(args)
    if error:
        sys.stderr.write(f"compass stations: {error}\n{USAGE}")
        return 1
    try:
        vault_root = vaultlib.find_vault_root()
    except FileNotFoundError as exc:
        sys.stderr.write(f"compass stations: {exc}\n")
        return 1
    plans = _read_plans(vault_root)
    if plan_number is not None and not any(n == plan_number for n, _ in plans):
        sys.stderr.write(f"compass stations: no plan PLAN-{plan_number:03d} in the vault\n")
        return 1
    groups, unknown = build_groups(_read_rows(vault_root), plans, plan_number)
    sys.stdout.write("\n".join(render(groups, unknown)) + "\n")
    return 0
