"""`compass context-check --hook` - the PostToolUse context threshold.

Runs after every main-agent tool call. It reads the session transcript,
measures how full the context window is, and once usage reaches the
threshold (80% of the whole window by default) prints
`{"continue": false, "stopReason": ...}`: Claude Code lets the tool that
just ran finish, starts no next step, and shows the human the reason, which
suggests `/compass:handoff` (SPEC-025 D-01, D-02).

Used tokens are the statusline's own formula over the latest assistant
message's usage: `input_tokens + cache_creation_input_tokens +
cache_read_input_tokens`. The window follows Claude Code's own model table
(code.claude.com/docs/en/model-config): a `[1m]` model id is 1,000,000;
Claude 3.x, Opus 4.0-4.6, Sonnet 4.x and Haiku 4.x are 200,000; every other
model - Fable, Opus 4.7+, Sonnet 5+, Haiku 5+ - runs 1M natively.
`CLAUDE_CODE_DISABLE_1M_CONTEXT` holds native-1M models at 200,000, a model
Claude Code does not recognize takes `CLAUDE_CODE_MAX_CONTEXT_TOKENS` when
set, and `COMPASS_CONTEXT_WINDOW` overrides everything. An unrecognized model
with neither variable is taken as 1M, so an unknown window never halts a
session early. The transcript is read from its end in growing chunks, so a
long session costs one bounded read; the model id is cached per session in
`.compass/tmp/context-state.json` and the window recomputed from it on every
call.

The suggestion is made at two levels, once each: the threshold (80%) and a
final one (95%, SPEC-025 D-04). The state file records the highest level
already suggested, so later calls in the same session pass - the handoff can
run, or the human can decline and keep working - until usage reaches the
next level. A session that jumps past both at once is told once. The record
clears when usage falls back under the threshold (as after `/compact`), which
arms both levels again.

Subagent events (carrying `agent_id`) and capture-worker sessions
(`COMPASS_WORKER_SESSION`) pass. Every failure - no transcript, an
unreadable line, no usage yet - passes with exit 0 and no output.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import vaultlib

DEFAULT_THRESHOLD = 80
DEFAULT_FINAL_THRESHOLD = 95
STANDARD_WINDOW = 200_000
EXTENDED_WINDOW = 1_000_000
TAIL_CHUNK = 256 * 1024
STATE_FILE = ("tmp", "context-state.json")
STATE_SESSIONS_KEPT = 50
# Parallel tool calls run one hook process each against the same state file;
# Windows refuses a read or a replace while another process holds it.
STATE_ATTEMPTS = 20
STATE_RETRY_SECONDS = 0.01
# `claude-opus-4-6`, `us.anthropic.claude-sonnet-4-5-v1`, `claude-sonnet-4-20250514`
# (a date, not a minor version), `claude-haiku-5-5`.
_CLAUDE_MODEL = re.compile(r"claude-(?P<family>opus|sonnet|haiku)-(?P<major>\d+)(?:-(?P<minor>\d{1,2})(?!\d))?")
_FABLE_MODEL = re.compile(r"claude-fable\b")
# Claude 3.x and earlier name the version first: `claude-3-5-sonnet-20241022`.
_LEGACY_MODEL = re.compile(r"claude-[1-3](?:-\d)?-(?:opus|sonnet|haiku|instant)|claude-[12](?:\.\d)?(?:$|-)")
STOP_REASON = (
    "Context is at {pct}% of the window. Compass stopped before the next step - "
    "run /compass:handoff to carry this session into a fresh one, or say so to keep working."
)
FINAL_STOP_REASON = (
    "Context is at {pct}% of the window, close to full. Compass stopped before the next step - "
    "run /compass:handoff now to carry this session into a fresh one."
)


def _percent_env(name, default):
    try:
        value = int(os.environ.get(name, default))
    except ValueError:
        return default
    return value if 0 < value <= 100 else default


def threshold():
    return _percent_env("COMPASS_CONTEXT_THRESHOLD", DEFAULT_THRESHOLD)


def levels():
    """The percentages at which the handoff is suggested, ascending: the
    threshold, then the final level when it lies above the threshold."""
    first = threshold()
    final = _percent_env("COMPASS_CONTEXT_FINAL_THRESHOLD", DEFAULT_FINAL_THRESHOLD)
    return [first, final] if final > first else [first]


def _env_tokens(name):
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return None
    return value if value > 0 else None


def _standard_window_model(model_id):
    """True for the Claude models whose window is 200,000 without `[1m]`."""
    if _LEGACY_MODEL.search(model_id):
        return True
    match = _CLAUDE_MODEL.search(model_id)
    if not match:
        return False
    family, major = match.group("family"), int(match.group("major"))
    minor = int(match.group("minor") or 0)
    if major < 4:
        return True
    if major == 4:
        return family != "opus" or minor < 7
    return False


def window_for(model_id):
    override = _env_tokens("COMPASS_CONTEXT_WINDOW")
    if override:
        return override
    model_id = (model_id or "").strip().lower()
    if model_id.endswith("[1m]"):
        return EXTENDED_WINDOW
    if _standard_window_model(model_id):
        return STANDARD_WINDOW
    if _CLAUDE_MODEL.search(model_id) or _FABLE_MODEL.search(model_id):
        if os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "").strip() not in ("", "0", "false"):
            return STANDARD_WINDOW
        return EXTENDED_WINDOW
    return _env_tokens("CLAUDE_CODE_MAX_CONTEXT_TOKENS") or EXTENDED_WINDOW


def _model_of(record):
    attachment = record.get("attachment")
    if not isinstance(attachment, dict) or attachment.get("type") != "model":
        return None
    model_id = (attachment.get("identity") or {}).get("modelId")
    return model_id if isinstance(model_id, str) and model_id else None


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
        used = sum(
            int(value or 0)
            for value in (usage.get(key) for key in
                          ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            if not isinstance(value, bool)
        )
    except (TypeError, ValueError, OverflowError):
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
        record = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    return record if isinstance(record, dict) else None


def measure(transcript_path, cached_model=None):
    """Return (used, model_id) for a transcript, either None when unknown.
    The scan stops once both are known. With a cached model id it stops at
    the usage line before the latest one: a model switch shows as a model
    line between two API calls, and the hook runs after every call."""
    used = model = None
    for record in _records_backward(transcript_path):
        if model is None:
            model = _model_of(record)
        record_used = _used_of(record)
        if used is None:
            used = record_used
            continue
        if model is not None or (cached_model is not None and record_used is not None):
            break
    return used, model or cached_model


def _retrying(action):
    """Run `action`, retrying while another process holds the file."""
    for attempt in range(STATE_ATTEMPTS):
        try:
            return action()
        except PermissionError:
            if attempt == STATE_ATTEMPTS - 1:
                raise
            time.sleep(STATE_RETRY_SECONDS)


def _load_state(path):
    try:
        state = json.loads(_retrying(lambda: path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _save_state(path, state):
    """Write the state through a temp file named for this process and an
    atomic replace. A replace still refused after the retries leaves the
    previous state in place."""
    if len(state) > STATE_SESSIONS_KEPT:
        state = dict(list(state.items())[-STATE_SESSIONS_KEPT:])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    try:
        _retrying(lambda: os.replace(tmp, path))
    except PermissionError:
        tmp.unlink(missing_ok=True)


def _offered_level(entry, first_level):
    """The highest level already suggested in this session; a state entry
    holding only the older `halted` flag counts as the first level."""
    offered = entry.get("offered")
    if isinstance(offered, (int, float)) and not isinstance(offered, bool):
        return offered
    return first_level if entry.get("halted") else 0


def decide(event, state):
    """Return the stopReason to emit, or None to pass. Mutates `state`
    (keyed by session id) to record the model and the crossing."""
    if event.get("agent_id") or event.get("agent_type"):
        return None
    transcript = event.get("transcript_path")
    session = event.get("session_id") or ""
    if not transcript or not Path(transcript).is_file():
        return None
    entry = state.get(session) if isinstance(state.get(session), dict) else {}
    used, model = measure(transcript, entry.get("model"))
    if not used:
        return None
    window = window_for(model)
    marks = levels()
    offered = _offered_level(entry, marks[0])
    pct = used * 100 / window
    reached = max((level for level in marks if pct >= level), default=0)
    reason = None
    if reached > offered:
        reason = (FINAL_STOP_REASON if reached == marks[-1] and len(marks) > 1 else STOP_REASON).format(pct=int(pct))
    entry = {"model": model, "offered": reached if reason or reached == 0 else offered}
    state.pop(session, None)
    state[session] = entry
    return reason


def run(args):
    if "--hook" not in args:
        sys.stdout.write(
            "compass context-check --hook: PostToolUse hook. Reads the event on stdin and halts the "
            f"main agent once at each of {', '.join(f'{p}%' for p in levels())} context usage.\n"
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
