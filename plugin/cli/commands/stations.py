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

Counts are the non-negative integers a row carries; any other value counts as
zero. A task line without a `complexity:` field groups under the letter
`none`. Rows whose task id is null or names no task of any plan are counted on
one `unknown task rows` line. A task id that the plans in scope carry with
different letters has no single letter; its rows group under the letter
`ambiguous`.

`--plan PLAN-NNN` limits the groups to the root plan of that number, and
`--plan <unit>/PLAN-NNN` to a unit's plan (a unit numbers its plans locally).
A folder plan's child files belong to the plan of their folder. Rows of tasks
that belong only to other plans are left out of the report.

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

USAGE = """usage: compass stations [--plan PLAN-NNN | --plan <unit>/PLAN-NNN]

Per complexity letter, model and station: spawns, bugs found, FAIL items,
fix cycles and unparsed rows, joined from the station log to the plans.
"""

_PLAN_ID = re.compile(r"^PLAN-(\d+)(?:-|$)", re.IGNORECASE)
_PLAN_ARG = re.compile(r"^(?:([^/\s]+)/)?PLAN-(\d+)$", re.IGNORECASE)
_UNSAFE_TEXT = re.compile(r"[\s\x00-\x1f\x7f-\x9f]+")
_LETTER_ORDER = {"XS": 0, "S": 1, "M": 2, "L": 3}
NO_LETTER = "none"
AMBIGUOUS = "ambiguous"
NO_VALUE = "-"
HEADER = ("letter", "model", "station", "spawns", "bugs", "fails", "cycles", "unparsed")


def _plan_key(record):
    """`(unit or None, plan number)` of a plan artifact, the number read from
    the first path part under `plans/` named PLAN-NNN: the file stem of a flat
    plan, the folder of a folder plan and of its child files. None when no
    part is."""
    parts = list(Path(record["rel"]).parts)
    parts[-1] = Path(parts[-1]).stem
    for part in parts:
        match = _PLAN_ID.match(part)
        if match:
            return record["unit"], int(match.group(1))
    return None


def _read_plans(vault_root):
    """`[(plan key or None, {task id: letter or None})]` for every plan file."""
    plans = []
    for record in vaultlib.scan_artifacts(vault_root):
        if record["type_dir"] != "plans":
            continue
        try:
            text = vaultlib.read_vault_text(record["path"])
        except (OSError, UnicodeDecodeError):
            continue
        plans.append((_plan_key(record), planlib.task_letters(text)))
    return plans


def _read_rows(vault_root):
    """The dict rows of the station log. Lines split on "\\n" only, a byte
    order mark is dropped, and a blank line, a line that is not JSON or one
    that is not a JSON object yields nothing."""
    path = Path(vault_root).joinpath(*stationlib.LOG_PARTS)
    try:
        raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError:
        return []
    rows = []
    for line in raw.split("\n"):
        if not line.strip():
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
    ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if ok else 0


def _text(value):
    """A one-line printable form of a log text field: each run of whitespace
    or control characters becomes one underscore."""
    if not isinstance(value, str):
        return NO_VALUE
    return _UNSAFE_TEXT.sub("_", value.strip()) or NO_VALUE


def _group_order(key):
    letter, model, station = key
    if letter in _LETTER_ORDER:
        rank = _LETTER_ORDER[letter]
    else:
        rank = {NO_LETTER: 5, AMBIGUOUS: 6}.get(letter, 4)
    return (rank, letter, model, station)


def _parse_args(args):
    """`(plan key or None, error message or None)` from the arguments; a plan
    key is `(unit or None, number)`."""
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
            return None, f"--plan takes PLAN-NNN or <unit>/PLAN-NNN, got {value}"
        plan = (match.group(1), int(match.group(2)))
    return plan, None


def build_groups(rows, plans, plan_key=None):
    """`(groups, unknown)`: the per-group counts and the number of rows whose
    task id matches no plan. A task id the plans in scope carry with different
    letters groups under the letter `ambiguous`. With `plan_key`, rows of
    tasks that belong to other plans only are left out of both."""
    owners = {}
    for key, letters in plans:
        for task, letter in letters.items():
            owners.setdefault(task, []).append((key, letter or NO_LETTER))
    groups = {}
    unknown = 0
    for row in rows:
        task = row.get("task")
        found = owners.get(task) if isinstance(task, str) else None
        if not found:
            unknown += 1
            continue
        if plan_key is not None:
            found = [pair for pair in found if pair[0] == plan_key]
            if not found:
                continue
        letters = {pair[1] for pair in found}
        letter = letters.pop() if len(letters) == 1 else AMBIGUOUS
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
    plan_key, error = _parse_args(args)
    if error:
        sys.stderr.write(f"compass stations: {error}\n{USAGE}")
        return 1
    try:
        vault_root = vaultlib.find_vault_root()
    except FileNotFoundError as exc:
        sys.stderr.write(f"compass stations: {exc}\n")
        return 1
    plans = _read_plans(vault_root)
    if plan_key is not None and not any(key == plan_key for key, _ in plans):
        unit, number = plan_key
        name = f"{unit}/PLAN-{number:03d}" if unit else f"PLAN-{number:03d}"
        sys.stderr.write(f"compass stations: no plan {name} in the vault\n")
        return 1
    groups, unknown = build_groups(_read_rows(vault_root), plans, plan_key)
    sys.stdout.write("\n".join(render(groups, unknown)) + "\n")
    return 0
