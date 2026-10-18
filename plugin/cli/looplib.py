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
`read_ledger()`, never fatal, and a row whose fields have the wrong type is
reported by `fold()` the same way. The loop's JSON files are read with a
leading UTF-8 byte order mark tolerated.
"""

import json
import math
import os
import threading
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
# as left behind by a crash. A lock whose recorded start lies further ahead of
# the clock than this margin is not trusted and is aged by file modification
# time instead.
LOCK_GRACE_SECONDS = 600

# A state file is rewritten in place on filesystems that refuse an atomic
# replace, so a reader meeting an empty or partial file reads again briefly.
STATE_READ_ATTEMPTS = 20
STATE_READ_RETRY_SECONDS = 0.01

DEFINITION_FILE = "loop.json"
STATE_FILE = "state.json"
LEDGER_FILE = "ledger.jsonl"

# Appends within one process are serialised so that the check of the ledger's
# last byte and the write of the new line cannot interleave.
_APPEND_LOCK = threading.Lock()

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
    leaves state.json and the ledger untouched. A ledger write that fails
    puts the prior state back, so the state never moves without its row.
    """
    state = read_state(loop_dir)
    new = transition(state["state"], event)
    write_state(loop_dir, {**state, "state": new})
    try:
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
    except BaseException:
        write_state(loop_dir, state)
        raise
    return new


def _is_number(value):
    """A real, finite int or float; an int too large for a float is not."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


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
        if not _is_number(value):
            return "must be a finite integer"
        if value < 0:
            return "must not be negative"
    elif not _is_number(value):
        return "must be a finite number"
    elif key != "target" and value < 0:
        return "must not be negative"
    return None


def _read_json_text(path):
    """The file's text, a leading UTF-8 byte order mark dropped."""
    return path.read_bytes().decode("utf-8-sig")


def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise DefinitionError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def load_definition(loop_dir):
    """Read and validate `<loop_dir>/loop.json`; DefinitionError names the
    first offending field."""
    path = Path(loop_dir) / DEFINITION_FILE
    try:
        data = json.loads(_read_json_text(path), object_pairs_hook=_no_duplicate_keys)
    except FileNotFoundError:
        raise DefinitionError(f"{DEFINITION_FILE}: {path} does not exist") from None
    except DefinitionError as exc:
        raise DefinitionError(f"{exc} in {path}") from None
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
    """The parsed `state.json`; a missing file reads as an idle loop.

    A file that is empty or does not parse is read again a few times before
    it is reported, since a writer may be replacing it.
    """
    path = Path(loop_dir) / STATE_FILE
    data = None
    for attempt in range(STATE_READ_ATTEMPTS):
        try:
            data = json.loads(_read_json_text(path))
            break
        except FileNotFoundError:
            return {"state": "idle"}
        except (OSError, ValueError) as exc:
            if attempt == STATE_READ_ATTEMPTS - 1:
                raise StateError(f"cannot read {path}: {exc}") from None
            time.sleep(STATE_READ_RETRY_SECONDS)
    if not isinstance(data, dict):
        raise StateError(f"{path} must hold a JSON object")
    name = data.get("state")
    if not isinstance(name, str) or name not in STATES:
        raise StateError(f"{path}: unknown state {name!r}")
    return data


def write_state(loop_dir, state_dict):
    """Write `state.json` pretty-printed, LF-terminated on every platform."""
    text = json.dumps(state_dict, indent=2) + "\n"
    vaultlib.write_text_lf(Path(loop_dir) / STATE_FILE, text)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_ledger(loop_dir, row):
    """Append `row` as one LF-terminated JSON line, stamping `ts` when the row
    carries none.

    The line goes out in a single write to a file opened for appending. When
    the ledger ends in a partial line (a write cut short), the new row starts
    on its own line so only the fragment is lost.
    """
    line = (json.dumps({"ts": _now_iso(), **row}) + "\n").encode("utf-8")
    path = Path(loop_dir) / LEDGER_FILE
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    with _APPEND_LOCK:
        fd = os.open(path, flags, 0o666)
        try:
            size = os.fstat(fd).st_size
            if size:
                os.lseek(fd, size - 1, os.SEEK_SET)
                if os.read(fd, 1) != b"\n":
                    line = b"\n" + line
            os.write(fd, line)
        finally:
            os.close(fd)


def read_ledger(loop_dir):
    """Every parsed row in file order, and one `{"line", "text"}` entry for
    each non-blank line that is not a JSON object."""
    path = Path(loop_dir) / LEDGER_FILE
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
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


def _item_sort_key(item):
    return (type(item).__name__, str(item))


def _row_problem(row):
    """Why a run or review row cannot be counted, or None when it can."""
    kind = row.get("type")
    run_id = row.get("run_id")
    if kind == "review":
        if not isinstance(run_id, str):
            return "review run_id must be a string"
    elif kind == "run":
        if run_id is not None and not isinstance(run_id, str):
            return "run run_id must be a string"
        if not isinstance(row.get("outcome"), str):
            return "run outcome must be a string"
        item = row.get("item")
        if item is not None and (
            isinstance(item, bool) or not isinstance(item, (str, int, float))
        ):
            return "run item must be a string or a number"
    return None


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

    A run or review row whose fields have the wrong type is left out of every
    counter and listed under `skipped_rows` as `{"index", "reason"}`.
    """
    usable, skipped_rows = [], []
    for index, row in enumerate(rows):
        problem = _row_problem(row)
        if problem:
            skipped_rows.append({"index": index, "reason": problem})
        else:
            usable.append(row)
    reviewed = {r["run_id"] for r in usable if r.get("type") == "review"}
    held = []
    failures = harmful = without_help = 0
    for row in usable:
        kind = row.get("type")
        if kind == "transition" and row.get("event") == "resume":
            failures = harmful = without_help = 0
        elif kind == "run":
            outcome = row["outcome"]
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
        "held_items": sorted(
            (r["item"] for r in held if r.get("item") is not None),
            key=_item_sort_key,
        ),
        "consecutive_failures": failures,
        "consecutive_harmful": harmful,
        "runs_without_help": without_help,
        "skipped_rows": skipped_rows,
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


def _lock_started(lock_path, now):
    """When the lock's run began: the recorded start when it is a finite
    number no further ahead of `now` than the grace margin, otherwise the
    file's modification time. None when the file is gone."""
    try:
        started = json.loads(lock_path.read_text(encoding="utf-8"))["started"]
        if _is_number(started) and started <= now + LOCK_GRACE_SECONDS:
            return started
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        return lock_path.stat().st_mtime
    except FileNotFoundError:
        return None


def is_stale(lock_path, timeout_s, now=None):
    """True when the lock is older than `timeout_s` plus the grace margin, or
    gone. A lock whose recorded start is unusable (a holder between creating
    and writing it, a corrupt file) is aged by its modification time."""
    now = time.time() if now is None else now
    started = _lock_started(Path(lock_path), now)
    if started is None:
        return True
    return now - started > timeout_s + LOCK_GRACE_SECONDS


def _already_recorded_crash(loop_dir, run_id):
    rows, _skipped = read_ledger(loop_dir)
    return any(
        r.get("type") == "run"
        and r.get("outcome") == "crashed"
        and r.get("run_id") == run_id
        for r in rows
    )


def recover(loop_dir, lock_path, definition, now=None):
    """Return a loop left in a working state by a crashed run to `idle`.

    A resting state is left alone (False). A working state whose lock is
    absent or stale is recovered (True): the earlier run is recorded as
    crashed, charged its full run budget, the state returns to idle and the
    lock is removed. A run already recorded as crashed is not charged again,
    which makes a recovery that failed partway safe to retry. A live lock
    raises LockHeld and changes nothing.
    """
    lock_path = Path(lock_path)
    state = read_state(loop_dir)
    if state["state"] in RESTING:
        return False
    timeout_s = definition["timeout_s"]
    lock_present = lock_path.exists()
    if lock_present and not is_stale(lock_path, timeout_s, now):
        raise LockHeld(f"run lock {lock_path} belongs to a live run")
    new = transition(state["state"], "crash-recovered")
    run_id = state.get("run_id")
    if run_id is None or not _already_recorded_crash(loop_dir, run_id):
        append_ledger(
            loop_dir,
            {
                "type": "run",
                "run_id": run_id,
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
            "reason": "stale run lock" if lock_present else "no run lock",
        },
    )
    release_lock(lock_path)
    return True
