"""Measurement helpers for control loops: the actuator's result event, the
domain sensor, the spend sums over a loop's ledger, and the judgment of a
change between two sensor readings.

The result event is the JSON envelope `claude -p --output-format json` prints.
Cost, turns, duration, subtype and `is_error` come from its top-level fields;
token totals are summed over every model in `modelUsage`, because the
top-level `usage` block is zeroed on a budget stop and differs from
`modelUsage` on a resumed session.

A domain sensor is an argv list run from the project root. It prints
`{"valid": true, "value": <number>, "items": [<identity>, ...]}`. Anything
else, including a hung or missing command, is an invalid `Reading` carrying a
reason; `run_sensor` never raises.

Ledger rows are dicts. A row may carry `ts` (ISO-8601) and `cost_usd`; rows
without `cost_usd` contribute nothing to a spend sum. Days are UTC calendar
days.
"""

import json
import math
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

TOKEN_FIELDS = (
    ("input_tokens", "inputTokens"),
    ("output_tokens", "outputTokens"),
    ("cache_read_tokens", "cacheReadInputTokens"),
    ("cache_creation_tokens", "cacheCreationInputTokens"),
)
_KILL_WAIT_SECONDS = 30
UNKNOWN_DAY = "unknown"


class NoResultEvent(ValueError):
    """The text holds no usable result event."""


class ResultEvent:
    def __init__(
        self,
        cost_usd,
        num_turns,
        duration_ms,
        subtype,
        is_error,
        result,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_creation_tokens,
    ):
        self.cost_usd = cost_usd
        self.num_turns = num_turns
        self.duration_ms = duration_ms
        self.subtype = subtype
        self.is_error = is_error
        self.result = result
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_creation_tokens = cache_creation_tokens


class Reading:
    def __init__(self, valid, value=None, items=(), reason=None):
        self.valid = valid
        self.value = value
        self.items = list(items)
        self.reason = reason

    def __repr__(self):
        return (
            f"Reading(valid={self.valid!r}, value={self.value!r}, "
            f"items={self.items!r}, reason={self.reason!r})"
        )


def _is_number(value):
    """True for a real int or float that float() can hold: not a bool, not
    NaN or infinite, and not an integer beyond the float range."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _int_field(obj, key):
    value = obj.get(key)
    return int(value) if _is_number(value) else 0


def parse_result(text):
    """Parse the stdout of `claude -p --output-format json` into a ResultEvent.
    Raises NoResultEvent when the text is not one complete result envelope
    with a numeric `total_cost_usd`."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError, RecursionError) as exc:
        raise NoResultEvent(f"no result event in the output ({exc})") from None
    if not isinstance(data, dict) or data.get("type") != "result":
        raise NoResultEvent("no result event in the output")
    cost = data.get("total_cost_usd")
    if not _is_number(cost) or cost < 0:
        raise NoResultEvent("no result event with a non-negative numeric total_cost_usd")

    totals = dict.fromkeys((name for name, _ in TOKEN_FIELDS), 0)
    model_usage = data.get("modelUsage")
    if isinstance(model_usage, dict):
        for usage in model_usage.values():
            if not isinstance(usage, dict):
                continue
            for name, key in TOKEN_FIELDS:
                totals[name] += _int_field(usage, key)

    result = data.get("result")
    subtype = data.get("subtype")
    return ResultEvent(
        cost_usd=float(cost),
        num_turns=_int_field(data, "num_turns"),
        duration_ms=_int_field(data, "duration_ms"),
        subtype=subtype if isinstance(subtype, str) else "",
        is_error=bool(data.get("is_error")),
        result=result if isinstance(result, str) else None,
        **totals,
    )


def _kill_tree(proc):
    """Kill the child and everything it started. The child leads its own
    process group (created at launch), so a group kill on POSIX and
    `taskkill /T` on Windows reach its descendants too."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_KILL_WAIT_SECONDS,
            )
        else:
            import signal

            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _invalid(reason):
    return Reading(valid=False, reason=reason)


def _reading_from_stdout(text, returncode):
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        shown = text.strip()[:200] or "empty output"
        return _invalid(f"sensor output is not JSON (exit {returncode}): {shown}")
    if not isinstance(data, dict):
        return _invalid("sensor output is not a JSON object")
    if data.get("valid") is not True:
        return _invalid("sensor reported valid: false")
    value = data.get("value")
    if not _is_number(value):
        return _invalid(f"sensor value is not a finite number: {value!r}")
    items = data.get("items")
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        return _invalid("sensor items is not a list of strings")
    return Reading(valid=True, value=float(value), items=items)


def run_sensor(command, cwd, timeout):
    """Run the sensor `command` (an argv list) from `cwd` and return its
    Reading. A sensor still running after `timeout` seconds has its process
    tree killed and reads as invalid."""
    popen_kwargs = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_kwargs,
        )
    except (OSError, ValueError, TypeError, IndexError) as exc:
        return _invalid(f"could not start the sensor: {exc}")
    try:
        stdout, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=_KILL_WAIT_SECONDS)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        return _invalid(f"sensor timed out after {timeout:g} seconds")
    except (OSError, ValueError) as exc:
        _kill_tree(proc)
        return _invalid(f"could not read the sensor output: {exc}")
    return _reading_from_stdout(stdout.decode("utf-8", errors="replace"), proc.returncode)


def judge(before, after, direction):
    """Classify the change from `before` to `after` as "helpful", "neutral"
    or "harmful". Helpful: the value moved toward the target and no item is
    new. Harmful: the value moved away or any item is new, where items
    compare as a multiset. Neutral: anything else."""
    if direction not in ("down", "up"):
        raise ValueError(f"direction must be 'down' or 'up', got {direction!r}")
    if not (before.valid and after.valid):
        raise ValueError("judge needs two valid readings")
    delta = after.value - before.value
    if direction == "down":
        delta = -delta
    new_items = Counter(after.items) - Counter(before.items)
    if delta < 0 or new_items:
        return "harmful"
    if delta > 0:
        return "helpful"
    return "neutral"


def _utc(moment):
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _row_day(row):
    """The row's UTC day as "YYYY-MM-DD", or None when `ts` is absent or
    unreadable."""
    ts = row.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        return _utc(datetime.fromisoformat(ts.replace("Z", "+00:00"))).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None


def _row_cost(row):
    """The row's spend, or None when it carries no readable non-negative
    `cost_usd`. A negative cost is skipped so it can never cancel real spend."""
    cost = row.get("cost_usd")
    return float(cost) if _is_number(cost) and cost >= 0 else None


def spend_by_day(rows):
    """Sum `cost_usd` per UTC day ("YYYY-MM-DD"). The ledger is append-only
    and chronological, so a costed row whose `ts` is absent or unreadable
    takes the day of the nearest preceding row with a readable `ts`; with no
    such row it is summed under UNKNOWN_DAY. Rows without a readable cost are
    skipped."""
    days = {}
    last_day = None
    for row in rows:
        day = _row_day(row)
        if day is not None:
            last_day = day
        cost = _row_cost(row)
        if cost is None:
            continue
        key = day or last_day or UNKNOWN_DAY
        days[key] = days.get(key, 0.0) + cost
    return days


def spend_today(rows, now):
    """Spend on the UTC day that contains `now` (a naive `now` counts as UTC),
    plus any spend under UNKNOWN_DAY, which cannot be placed on a day and so
    counts against every day."""
    days = spend_by_day(rows)
    return days.get(_utc(now).strftime("%Y-%m-%d"), 0.0) + days.get(UNKNOWN_DAY, 0.0)


def spend_lifetime(rows):
    """Sum `cost_usd` over every row that carries a readable one."""
    return sum(cost for cost in map(_row_cost, rows) if cost is not None)
