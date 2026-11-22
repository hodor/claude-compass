"""Station rows: one counts-only record per finished checking subagent.

A SubagentStop event plus the subagent's final report becomes one JSON row in
`.compass/meta/station-log.jsonl`: time, agent type, station, task id, the
verdict counts the report carries, and the model that ran. `compass test-checkpoint
cycle` appends a `fix-cycle` row to the same log. A row never holds report text,
only the values read from it.

Stations: a tester report's Mode section names `tester-pre` or `tester-post`;
`validator`, `builder` and `debug` are their agent types. A report that matches
no known form gets its agent type as the station and `verdict: unparsed`.
"""

import datetime
import contextlib
import json
import os
import re
import time
from pathlib import Path

import modelslib
import sessionslib

try:
    import msvcrt
except ImportError:
    msvcrt = None
    import fcntl

LOG_PARTS = ("meta", "station-log.jsonl")
LOCK_PARTS = ("tmp", "station-log.lock")
LOCK_ATTEMPTS = 400
LOCK_RETRY_SECONDS = 0.025
UNPARSED = "unparsed"
DEFAULT_AGENT_TYPE = "unknown"
TRANSCRIPT_SOURCE = "transcript"

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_TASK_ID = re.compile(r"\bTASK-\d+\b")
_MODE_VALUE = re.compile(r"^(pre|post)-build\b", re.IGNORECASE)
_VERDICT_LINE = re.compile(r"^\s*\**VERDICT:\**\s*(PASS|FAIL|PARTIAL)\b")
_BULLET = re.compile(r"^[-*][ \t]+(.*\S)")
_NONE_ITEM = re.compile(r"^\W*(none|no\s+bugs?|n/a)\b", re.IGNORECASE)
_FAIL_CELL = re.compile(r"^\W*FAIL\b")
_CHECKS_CELL = re.compile(r"^\W*(\d+)\s*/\s*(\d+)\b")


def _bare_agent(raw):
    """The agent name with a single leading `<plugin>:` scope removed."""
    if not isinstance(raw, str) or not raw.strip():
        return DEFAULT_AGENT_TYPE
    name = raw.strip().partition(":")[2].strip() if ":" in raw else raw.strip()
    return name or DEFAULT_AGENT_TYPE


def _section(lines, title, max_level):
    """The lines under the first heading whose text starts with `title`
    (case-insensitive), up to the next heading of level `max_level` or
    shallower. None when no such heading exists."""
    start = None
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if start is None:
            if match and match.group(2).strip().lower().startswith(title.lower()):
                start = index + 1
        elif match and len(match.group(1)) <= max_level:
            return lines[start:index]
    return None if start is None else lines[start:]


def _task_id(agent, lines, text):
    if agent == "builder":
        task_lines = _section(lines, "Task", 6)
        found = _TASK_ID.search("\n".join(task_lines)) if task_lines else None
        if found:
            return found.group(0)
    found = _TASK_ID.search(text)
    return found.group(0) if found else None


def _parse_tester(lines):
    mode = _section(lines, "Mode", 6)
    value = next((ln.strip().strip("*_` ") for ln in mode or [] if ln.strip()), "")
    match = _MODE_VALUE.match(value)
    if not match:
        return None
    if match.group(1).lower() == "pre":
        return {"station": "tester-pre"}
    bugs = _section(lines, "Bugs Found", 6) or []
    count = 0
    for line in bugs:
        item = _BULLET.match(line)
        if item and not _NONE_ITEM.match(item.group(1)):
            count += 1
    return {"station": "tester-post", "bugs": count}


def _is_fail_row(line):
    """Whether a Phase Results table row reports a failure: a cell after the
    task cell that starts with FAIL, or a checks cell `N/M` with N below M."""
    if not line.lstrip().startswith("|"):
        return False
    for cell in line.strip().strip("|").split("|")[1:]:
        if _FAIL_CELL.match(cell):
            return True
        checks = _CHECKS_CELL.match(cell)
        if checks and int(checks.group(1)) < int(checks.group(2)):
            return True
    return False


def _parse_validator(lines):
    verdict = None
    for line in lines:
        found = _VERDICT_LINE.match(line)
        if found:
            verdict = found.group(1)
    if verdict is None:
        return None
    phase = _section(lines, "Phase Results", 3) or []
    fails = sum(1 for ln in phase if _is_fail_row(ln))
    return {"station": "validator", "result": verdict, "fails": fails}


def _has_heading(lines, title):
    return _section(lines, title, 6) is not None


def parse_report(agent_type, text):
    """Map a subagent's final report to its station and counts.

    Returns a dict with `station`, `task` and the counts its form carries
    (`bugs` for a post-build tester, `result` and `fails` for a validator), or
    `station` from the bare agent type with `verdict: unparsed` when the report
    matches no known form. Never raises.
    """
    agent = _bare_agent(agent_type)
    text = text if isinstance(text, str) else ""
    lines = text.splitlines()
    parsed = None
    if agent == "tester":
        parsed = _parse_tester(lines)
    elif agent == "validator":
        parsed = _parse_validator(lines)
    elif agent == "builder" and _has_heading(lines, "Build Report"):
        parsed = {"station": "builder"}
    elif agent == "debug" and _has_heading(lines, "Debug Report"):
        parsed = {"station": "debug"}
    if parsed is None:
        parsed = {"station": agent, "verdict": UNPARSED}
    parsed["task"] = _task_id(agent, lines, text)
    return parsed


def _now_iso():
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.isoformat().replace("+00:00", "Z")


def _transcript_model(event):
    path = event.get("agent_transcript_path")
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        return sessionslib.model_id(path)
    except Exception:
        return None


def _model_of(event, agent):
    """`(model, source)`: the subagent transcript's model when the event names
    a readable transcript, else the agent's resolved model and its source."""
    model = _transcript_model(event)
    if model:
        return model, TRANSCRIPT_SOURCE
    resolved, _effort, source = modelslib.resolve(agent)
    return resolved, source


def build_row(event, text):
    """One station row for a SubagentStop `event` and its final report `text`."""
    agent = _bare_agent(event.get("agent_type"))
    parsed = parse_report(agent, text)
    model, source = _model_of(event, agent)
    row = {"ts": _now_iso(), "agent_type": agent}
    row.update(parsed)
    row["model"] = model
    row["model_source"] = source
    return row


def fix_cycle_row(task, cycle, verdict):
    """The station row for one judged fix-loop cycle."""
    return {
        "ts": _now_iso(), "station": "fix-cycle", "task": task,
        "cycle": cycle, "verdict": verdict,
    }


@contextlib.contextmanager
def _log_lock(path):
    """Hold an exclusive OS lock on the sidecar file `path`, retrying while
    another process holds it. The OS drops the lock when its holder dies. When
    the lock stays held past the retry budget the body runs unlocked: a row
    is worth more than strict ordering."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o666)
    held = False
    try:
        for _ in range(LOCK_ATTEMPTS):
            try:
                if msvcrt:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
                break
            except OSError:
                time.sleep(LOCK_RETRY_SECONDS)
        try:
            yield
        finally:
            if held:
                if msvcrt:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def append_row(vault_dir, row):
    """Append `row` as one JSON line to the vault's station log, creating the
    meta folder when absent. The tail check and the write run under a sidecar
    lock, so rows from concurrent processes never interleave; a log whose last
    line has no trailing newline gets one ahead of the row in the same write."""
    vault = Path(vault_dir)
    path = vault.joinpath(*LOG_PARTS)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(row) + "\n").encode("utf-8")
    lock_path = vault.joinpath(*LOCK_PARTS)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _log_lock(lock_path):
        if not _ends_with_newline(path):
            line = b"\n" + line
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)


def _ends_with_newline(path):
    """True for a missing or empty log or one whose last byte is a newline."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                return True
            fh.seek(-1, os.SEEK_END)
            return fh.read(1) == b"\n"
    except FileNotFoundError:
        return True
