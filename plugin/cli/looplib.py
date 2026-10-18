"""The control-loop library: the loop definition, the state machine, the state
file, the ledger and the run lock.

A loop is a folder (`.compass/loops/LOOP-NNN-name/`) holding `loop.json` (the
machine definition), `state.json` (the current state) and `ledger.jsonl` (the
append-only record of transitions, runs and reviews). The run lock is a file
under `.compass/tmp/loops/`.

The state machine is one declared table, `TRANSITIONS`; `transition()` is a
pure lookup and refuses every (state, event) pair the table does not list.
The ledger is the loop's memory: `fold()` turns its rows into the counters the
gate and the stop limits read, so no counter lives anywhere but the ledger.

Every ledger row carries `ts`, ISO-8601 with a UTC offset, and spend is always
the `cost_usd` key. A ledger line that does not parse is reported by
`read_ledger()`, never fatal.
"""

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import vaultlib

RESTING = frozenset({"idle", "throttled", "paused", "halted", "done"})
WORKING = frozenset({"sensing", "gating", "controlling", "actuating", "verifying"})
STATES = RESTING | WORKING

TRANSITIONS = {
    ("idle", "start"): "sensing",
    ("throttled", "start"): "sensing",
    ("sensing", "at-set-point"): "done",
    ("sensing", "invalid-reading"): "halted",
    ("sensing", "off-set-point"): "gating",
    ("gating", "wip-full"): "throttled",
    ("gating", "daily-budget-spent"): "throttled",
    ("gating", "total-budget-spent"): "halted",
    ("gating", "clear"): "controlling",
    ("controlling", "selected"): "actuating",
    ("controlling", "nothing-selected"): "halted",
    ("actuating", "finished"): "verifying",
    ("actuating", "failed"): "idle",
    ("actuating", "failed-limit"): "halted",
    ("actuating", "controls-changed"): "halted",
    ("verifying", "helpful"): "idle",
    ("verifying", "neutral"): "idle",
    ("verifying", "harmful"): "idle",
    ("verifying", "harmful-limit"): "halted",
    ("verifying", "no-progress-limit"): "halted",
    ("idle", "pause"): "paused",
    ("throttled", "pause"): "paused",
    ("paused", "resume"): "idle",
    ("halted", "resume"): "idle",
    ("done", "reopen"): "idle",
    **{(state, "crash-recovered"): "idle" for state in sorted(WORKING)},
}
EVENTS = frozenset(event for (_state, event) in TRANSITIONS)

# A run's lock outlives its wall-clock timeout by this margin before it counts
# as left behind by a crash.
LOCK_GRACE_SECONDS = 600

DEFINITION_FILE = "loop.json"
STATE_FILE = "state.json"
LEDGER_FILE = "ledger.jsonl"

_VERIFIED = frozenset({"helpful", "neutral", "harmful"})

_STR, _NUMBER, _INT, _STR_LIST = "str", "number", "int", "list of str"
_DEFINITION_FIELDS = {
    "sensor_command": _STR,
    "sensor_timeout_s": _NUMBER,
    "target": _NUMBER,
    "direction": _STR,
    "controller": _STR,
    "controller_command": _STR,
    "wip_command": _STR,
    "model": _STR,
    "max_turns": _INT,
    "max_budget_usd": _NUMBER,
    "timeout_s": _NUMBER,
    "allowed_tools": _STR_LIST,
    "daily_budget_usd": _NUMBER,
    "total_budget_usd": _NUMBER,
    "wip_limit": _INT,
    "max_actuator_failures": _INT,
    "max_harmful_runs": _INT,
    "max_runs_without_help": _INT,
}
_OPTIONAL_FIELDS = frozenset({"controller_command", "wip_command"})
_COMMAND_FIELDS = frozenset({"sensor_command", "controller_command", "wip_command"})
_CHOICES = {"direction": ("down", "up"), "controller": ("first", "command")}


class TransitionError(ValueError):
    """A (state, event) pair the transition table does not list."""


class DefinitionError(ValueError):
    """A `loop.json` that is missing, unparseable or invalid; the message
    names the offending field."""


class StateError(ValueError):
    """A `state.json` that does not parse or names a state outside STATES."""


class LockHeld(RuntimeError):
    """The run lock exists, or belongs to a run that is still live."""


def transition(state, event):
    """The state `event` leads to from `state`; TransitionError otherwise."""
    try:
        return TRANSITIONS[(state, event)]
    except (KeyError, TypeError):
        raise TransitionError(
            f"no transition from state {state!r} on event {event!r}"
        ) from None


def advance(loop_dir, event, reason):
    """Apply `event` to the state on disk and record it in the ledger.

    The event is checked before anything is written, so an illegal event
    leaves state.json and the ledger untouched.
    """
    state = read_state(loop_dir)
    new = transition(state["state"], event)
    write_state(loop_dir, {**state, "state": new})
    append_ledger(
        loop_dir,
        {
            "type": "transition",
            "from": state["state"],
            "event": event,
            "to": new,
            "reason": reason,
        },
    )
    return new


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _field_problem(key, value):
    """Why `value` is wrong for `key`, or None when it is acceptable."""
    kind = _DEFINITION_FIELDS[key]
    if kind == _STR:
        if not isinstance(value, str):
            return "must be a string"
        if (key in _COMMAND_FIELDS or key in _CHOICES) and not value.strip():
            return "must not be blank"
        if key in _CHOICES and value not in _CHOICES[key]:
            return "must be one of " + ", ".join(repr(c) for c in _CHOICES[key])
    elif kind == _STR_LIST:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return "must be a list of strings"
    elif kind == _INT:
        if not isinstance(value, int) or isinstance(value, bool):
            return "must be an integer"
        if value < 0:
            return "must not be negative"
    elif not _is_number(value):
        return "must be a number"
    elif key != "target" and value < 0:
        return "must not be negative"
    return None


def load_definition(loop_dir):
    """Read and validate `<loop_dir>/loop.json`; DefinitionError names the
    first offending field."""
    path = Path(loop_dir) / DEFINITION_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DefinitionError(f"{DEFINITION_FILE}: {path} does not exist") from None
    except (OSError, ValueError) as exc:
        raise DefinitionError(f"{DEFINITION_FILE}: cannot read {path}: {exc}") from None
    if not isinstance(data, dict):
        raise DefinitionError(f"{DEFINITION_FILE}: {path} must hold a JSON object")
    for key in data:
        if key not in _DEFINITION_FIELDS:
            raise DefinitionError(f"unknown key {key!r} in {path}")
    for key in _DEFINITION_FIELDS:
        if key not in data:
            if key in _OPTIONAL_FIELDS:
                continue
            raise DefinitionError(f"missing key {key!r} in {path}")
        problem = _field_problem(key, data[key])
        if problem:
            raise DefinitionError(f"{key!r} {problem} in {path}")
    if data["controller"] == "command" and "controller_command" not in data:
        raise DefinitionError(
            f"missing key 'controller_command' (required when controller is "
            f"'command') in {path}"
        )
    return data


def read_state(loop_dir):
    """The parsed `state.json`; a missing file reads as an idle loop."""
    path = Path(loop_dir) / STATE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"state": "idle"}
    except (OSError, ValueError) as exc:
        raise StateError(f"cannot read {path}: {exc}") from None
    if not isinstance(data, dict):
        raise StateError(f"{path} must hold a JSON object")
    if data.get("state") not in STATES:
        raise StateError(f"{path}: unknown state {data.get('state')!r}")
    return data


def write_state(loop_dir, state_dict):
    """Write `state.json` pretty-printed, LF-terminated on every platform."""
    text = json.dumps(state_dict, indent=2) + "\n"
    vaultlib.write_text_lf(Path(loop_dir) / STATE_FILE, text)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_ledger(loop_dir, row):
    """Append `row` as one LF-terminated JSON line, stamping `ts` when the row
    carries none."""
    line = json.dumps({"ts": _now_iso(), **row}) + "\n"
    path = Path(loop_dir) / LEDGER_FILE
    with open(path, "ab") as handle:
        handle.write(line.encode("utf-8"))


def read_ledger(loop_dir):
    """Every parsed row in file order, and one `{"line", "text"}` entry for
    each non-blank line that is not a JSON object."""
    path = Path(loop_dir) / LEDGER_FILE
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return [], []
    rows, skipped = [], []
    for number, raw in enumerate(text.split("\n"), start=1):
        raw = raw.rstrip("\r")
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            row = None
        if isinstance(row, dict):
            rows.append(row)
        else:
            skipped.append({"line": number, "text": raw})
    return rows, skipped


def fold(rows):
    """Counters over ledger rows.

    A verified run is one that reached `verifying` (outcome helpful, neutral
    or harmful) and so left an increment. `wip` counts the verified runs no
    review row names; `held_items` lists their items, sorted. A `resume`
    transition row zeroes the three consecutive counters. A failed run
    extends the failure streak and a verified run ends it; throttled and
    crashed runs touch no streak. Only helpful and neutral runs end the
    harmful streak. `runs_without_help` counts verified runs since the last
    helpful run.
    """
    reviewed = {r.get("run_id") for r in rows if r.get("type") == "review"}
    held = []
    failures = harmful = without_help = 0
    for row in rows:
        kind = row.get("type")
        if kind == "transition" and row.get("event") == "resume":
            failures = harmful = without_help = 0
        elif kind == "run":
            outcome = row.get("outcome")
            if outcome == "failed":
                failures += 1
                continue
            if outcome not in _VERIFIED:
                continue
            failures = 0
            harmful = harmful + 1 if outcome == "harmful" else 0
            without_help = 0 if outcome == "helpful" else without_help + 1
            if row.get("run_id") not in reviewed:
                held.append(row)
    return {
        "wip": len(held),
        "held_items": sorted(r["item"] for r in held if r.get("item") is not None),
        "consecutive_failures": failures,
        "consecutive_harmful": harmful,
        "runs_without_help": without_help,
    }


def acquire_lock(lock_path, timeout_s, now=None):
    """Create the lock file atomically, holding the pid and start time.

    `timeout_s` is the run's wall-clock limit; the same value passed to
    `is_stale` decides when the lock counts as abandoned.
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise LockHeld(f"run lock {lock_path} is held") from None
    started = time.time() if now is None else now
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps({"pid": os.getpid(), "started": started}))


def release_lock(lock_path):
    Path(lock_path).unlink(missing_ok=True)


def is_stale(lock_path, timeout_s, now=None):
    """True when the lock is older than `timeout_s` plus the grace margin, or
    gone. A lock whose content is unreadable (a holder between creating and
    writing it) is aged by its file modification time."""
    lock_path = Path(lock_path)
    now = time.time() if now is None else now
    try:
        started = json.loads(lock_path.read_text(encoding="utf-8"))["started"]
    except FileNotFoundError:
        return True
    except (OSError, ValueError, KeyError, TypeError):
        try:
            started = lock_path.stat().st_mtime
        except FileNotFoundError:
            return True
    return now - started > timeout_s + LOCK_GRACE_SECONDS


def recover(loop_dir, lock_path, definition, now=None):
    """Return a loop left in a working state by a crashed run to `idle`.

    A resting state is left alone (False). A working state whose lock is
    absent or stale is recovered (True): the earlier run is recorded as
    crashed, charged its full run budget, the state returns to idle and the
    lock is removed. A live lock raises LockHeld and changes nothing.
    """
    lock_path = Path(lock_path)
    state = read_state(loop_dir)
    if state["state"] in RESTING:
        return False
    timeout_s = definition["timeout_s"]
    if lock_path.exists() and not is_stale(lock_path, timeout_s, now):
        raise LockHeld(f"run lock {lock_path} belongs to a live run")
    reason = "stale run lock" if lock_path.exists() else "no run lock"
    new = transition(state["state"], "crash-recovered")
    append_ledger(
        loop_dir,
        {
            "type": "run",
            "run_id": state.get("run_id"),
            "outcome": "crashed",
            "item": state.get("item"),
            "cost_usd": definition["max_budget_usd"],
        },
    )
    idle = {k: v for k, v in state.items() if k not in ("run_id", "item")}
    write_state(loop_dir, {**idle, "state": new})
    append_ledger(
        loop_dir,
        {
            "type": "transition",
            "from": state["state"],
            "event": "crash-recovered",
            "to": new,
            "reason": reason,
        },
    )
    release_lock(lock_path)
    return True
