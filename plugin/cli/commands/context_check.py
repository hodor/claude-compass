"""`compass context-check --hook` - the PostToolUse context threshold.

Runs after every main-agent tool call. It reads the session transcript,
measures how full the context window is, and once usage reaches the
threshold (80% of the whole window by default) prints
`{"continue": false, "stopReason": ...}`: Claude Code lets the tool that
just ran finish, starts no next step, and shows the human the reason, which
suggests `/compass:handoff` (SPEC-025 D-01, D-02).

Used tokens are the statusline's own formula over the latest assistant
message's usage: `input_tokens + cache_creation_input_tokens +
cache_read_input_tokens`. The window is 1,000,000 when the latest model
attachment's `modelId` ends in `[1m]`, otherwise 200,000. The transcript is
read from its end in growing chunks, so a long session costs one bounded
read; the window is cached per session in `.compass/tmp/context-state.json`.

The halt fires once per crossing: the state file records it, later calls in
the same session pass so the handoff itself can run, and the record clears
when usage falls back under the threshold (as after `/compact`), which arms
the next crossing.

Subagent events (carrying `agent_id`) and capture-worker sessions
(`COMPASS_WORKER_SESSION`) pass. Every failure - no transcript, an
unreadable line, no usage yet - passes with exit 0 and no output.
"""

import json
import os
import sys
from pathlib import Path

import vaultlib

DEFAULT_THRESHOLD = 80
STANDARD_WINDOW = 200_000
EXTENDED_WINDOW = 1_000_000
TAIL_CHUNK = 256 * 1024
STATE_FILE = ("tmp", "context-state.json")
STATE_SESSIONS_KEPT = 50
STOP_REASON = (
    "Context is at {pct}% of the window. Compass stopped before the next step - "
    "run /compass:handoff to carry this session into a fresh one."
)


def threshold():
    try:
        value = int(os.environ.get("COMPASS_CONTEXT_THRESHOLD", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD
    return value if 0 < value <= 100 else DEFAULT_THRESHOLD


def _window_of(record):
    attachment = record.get("attachment")
    if not isinstance(attachment, dict) or attachment.get("type") != "model":
        return None
    model_id = (attachment.get("identity") or {}).get("modelId") or ""
    return EXTENDED_WINDOW if model_id.endswith("[1m]") else STANDARD_WINDOW


def _used_of(record):
    if record.get("type") != "assistant" or record.get("isSidechain"):
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        used = (int(usage.get("input_tokens") or 0)
                + int(usage.get("cache_creation_input_tokens") or 0)
                + int(usage.get("cache_read_input_tokens") or 0))
    except (TypeError, ValueError):
        return None
    return used or None  # synthetic messages carry all-zero usage


def _records_backward(path):
    """Yield parsed transcript records from the last line to the first,
    reading the file in chunks from its end."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        position = fh.tell()
        remainder = b""
        while position > 0:
            step = min(TAIL_CHUNK, position)
            position -= step
            fh.seek(position)
            block = fh.read(step) + remainder
            lines = block.split(b"\n")
            remainder = lines.pop(0)  # possibly partial; completed by the next chunk
            for raw in reversed(lines):
                record = _parse(raw)
                if record is not None:
                    yield record
        record = _parse(remainder)
        if record is not None:
            yield record


def _parse(raw):
    raw = raw.strip()
    if not raw:
        return None
    try:
        record = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return record if isinstance(record, dict) else None


def measure(transcript_path, cached_window=None):
    """Return (used, window) for a transcript, either None when unknown.
    The scan stops once both are known; a cached window stops it at the
    latest usage."""
    used = window = None
    for record in _records_backward(transcript_path):
        if window is None:
            window = _window_of(record)
        if used is None:
            used = _used_of(record)
        if used is not None and (window is not None or cached_window is not None):
            break
    return used, window or cached_window


def _load_state(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _save_state(path, state):
    if len(state) > STATE_SESSIONS_KEPT:
        state = dict(list(state.items())[-STATE_SESSIONS_KEPT:])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, path)


def decide(event, state):
    """Return the stopReason to emit, or None to pass. Mutates `state`
    (keyed by session id) to record the window and the crossing."""
    if event.get("agent_id") or event.get("agent_type"):
        return None
    transcript = event.get("transcript_path")
    session = event.get("session_id") or ""
    if not transcript or not Path(transcript).is_file():
        return None
    entry = state.get(session) if isinstance(state.get(session), dict) else {}
    used, window = measure(transcript, entry.get("window"))
    if not used or not window:
        return None
    entry = dict(entry, window=window)
    pct = used * 100 / window
    reason = None
    if pct < threshold():
        entry["halted"] = False
    elif not entry.get("halted"):
        entry["halted"] = True
        reason = STOP_REASON.format(pct=int(pct))
    state.pop(session, None)
    state[session] = entry
    return reason


def run(args):
    if "--hook" not in args:
        sys.stdout.write(
            "compass context-check --hook: PostToolUse hook. Reads the event on stdin and halts the "
            f"main agent once per crossing of {threshold()}% context usage.\n"
        )
        return 0
    if os.environ.get("COMPASS_WORKER_SESSION"):
        return 0
    try:
        data = sys.stdin.read().strip()
        event = json.loads(data) if data else {}
        if not isinstance(event, dict):
            return 0
        state_path = vaultlib.find_vault_root().joinpath(*STATE_FILE)
        state = _load_state(state_path)
        reason = decide(event, state)
        _save_state(state_path, state)
        if reason:
            sys.stdout.write(json.dumps({"continue": False, "stopReason": reason}))
        return 0
    except Exception as exc:  # a measuring fault must not stall the session
        try:
            import bugs
            bugs.capture_exception(vaultlib.find_vault_root(), "context-check", exc)
        except Exception:
            pass
        return 0
