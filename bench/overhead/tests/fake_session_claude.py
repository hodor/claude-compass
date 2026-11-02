"""A scripted stand-in for `claude` that holds a conversation, for the driver
and simulated-human tests. It reuses the event builders of `fake_claude.py`.

Run as `python fake_session_claude.py --spec FILE <claude arguments>`; the spec
is a JSON file (build one with `command(spec, folder)`, which returns the argv
prefix to pass as `claude_cmd`). Every invocation appends to the spec's `log`
file: a `start` entry (argv, cwd, whole environment), then one `stdin` entry
(one-shot mode) or one `message` entry per user message (stream mode).

Spec keys
---------
mode            "stream" or "oneshot"
log             path of the JSON-lines log
init            stream mode: {"skills": n, "agents": m}, the first `system/init`
turns           stream mode: one entry per user message, in order; a message
                beyond the list gets a zero-usage "ok" turn. Entry keys:
                  text     assistant text (default "turn")
                  usage    [input, output, cache_read, cache_write] added to the
                           running totals (default [10, 5, 100, 20])
                  init     {"skills": n, "agents": m}: another `system/init`
                           event before the turn's events
                  write    {relative path: content} written under the cwd
                  limit    "rejected" (rate_limit_event, error result, exit 1)
                           or "api_error" (result with api_error
                           usage_limit_reached, exit 1)
                  error    true: an `error_max_budget_usd` error result, exit 1
                  crash    true: a truncated JSON line, exit 3
replies         one-shot mode: one entry per invocation, in order (the last
                repeats). A string is the result text; {"limit": true} is a
                usage-limit end, {"crash": true} a crash.
usage           one-shot mode: usage of each reply (default [10, 5, 100, 20])

A stream-mode message must be `{"type": "user", "message": {"role": "user",
"content": <string or list of text blocks>}}`; anything else exits 5 and logs
a `bad-message` entry. The session ends at end of stdin.
"""

import json
import os
import sys
from pathlib import Path

import fake_claude

DEFAULT_USAGE = [10, 5, 100, 20]
SESSION_ID = fake_claude.SECRET_SESSION_IDS[0]


def command(spec, folder):
    """argv prefix for `claude_cmd`: this script with `spec` written under `folder`."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    index = len(list(folder.glob("session-spec-*.json")))
    spec = dict(spec)
    spec.setdefault("log", str(folder / f"session-log-{index}.jsonl"))
    path = folder / f"session-spec-{index}.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return [sys.executable, str(Path(__file__).resolve()), "--spec", str(path)]


def read_log(spec_or_command):
    """Entries logged by the session built with `command`."""
    argv = spec_or_command
    path = Path(argv[argv.index("--spec") + 1])
    log = Path(json.loads(path.read_text(encoding="utf-8"))["log"])
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _emit(event):
    sys.stdout.write((event if isinstance(event, str) else json.dumps(event)) + "\n")
    sys.stdout.flush()


def _log(spec, entry):
    with open(spec["log"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def _init(counts, cwd):
    event = fake_claude.init_event(SESSION_ID, cwd)
    event["skills"] = [f"skill-{i}" for i in range(counts.get("skills", 0))]
    event["agents"] = [f"agent-{i}" for i in range(counts.get("agents", 0))]
    return event


def _text_of(message):
    content = message["message"]["content"]
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if block.get("type") == "text")


def _turn_events(text, totals, index):
    main = tuple(totals)
    return [
        fake_claude.assistant_event(SESSION_ID, f"msg_{index}", text, main),
        fake_claude.result_event(SESSION_ID, {fake_claude.MAIN_MODEL: main}, text=text),
    ]


def _end_with(turn, text, totals, index):
    """Emit the failure shape `turn` asks for; return the exit code, or None."""
    main = tuple(totals)
    if turn.get("limit") == "rejected":
        _emit(fake_claude.rate_limit_event("rejected", session_id=SESSION_ID))
        _emit(fake_claude.result_event(
            SESSION_ID, {fake_claude.MAIN_MODEL: main}, is_error=True, text=fake_claude.LIMIT_TEXT))
        return 1
    if turn.get("limit") == "api_error":
        _emit(fake_claude.result_event(
            SESSION_ID, {fake_claude.MAIN_MODEL: main}, is_error=True, text=fake_claude.LIMIT_TEXT,
            api_error="usage_limit_reached", terminal_reason="api_error", api_error_status=429))
        return 1
    if turn.get("error"):
        _emit(fake_claude.result_event(
            SESSION_ID, {fake_claude.MAIN_MODEL: main}, is_error=True, subtype="error_max_budget_usd",
            text="budget reached"))
        return 1
    if turn.get("crash"):
        _emit('{"type": "assistant", "message": {"id": "msg_x", "con')
        return 3
    return None


def run_stream(spec):
    cwd = Path(os.getcwd())
    _emit(_init(spec.get("init", {"skills": 2, "agents": 1}), cwd))
    totals = [0, 0, 0, 0]
    turns = spec.get("turns", [])
    index = 0
    while True:
        line = sys.stdin.readline()
        if not line:
            return 0
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            assert message["type"] == "user" and message["message"]["role"] == "user"
            text_in = _text_of(message)
        except Exception:
            _log(spec, {"kind": "bad-message", "line": line})
            return 5
        _log(spec, {"kind": "message", "text": text_in})
        turn = turns[index] if index < len(turns) else {"text": "ok", "usage": [0, 0, 0, 0]}
        index += 1
        for slot, delta in enumerate(turn.get("usage", DEFAULT_USAGE)):
            totals[slot] += delta
        if turn.get("init"):
            _emit(_init(turn["init"], cwd))
        for relative, content in turn.get("write", {}).items():
            target = cwd / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        code = _end_with(turn, turn.get("text", "turn"), totals, index)
        if code is not None:
            return code
        for event in _turn_events(turn.get("text", "turn"), totals, index):
            _emit(event)


def run_oneshot(spec, argv_log):
    prompt = sys.stdin.read()
    _log(spec, {"kind": "stdin", "text": prompt})
    counter = Path(spec["log"] + ".count")
    index = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
    counter.write_text(str(index + 1), encoding="utf-8")
    replies = spec.get("replies", ["ok"])
    reply = replies[min(index, len(replies) - 1)]
    totals = tuple(spec.get("usage", DEFAULT_USAGE))
    cwd = Path(os.getcwd())
    _emit(_init({}, cwd))
    if isinstance(reply, dict) and reply.get("crash"):
        _emit('{"type": "assistant", "message": {"id": "msg_x", "con')
        return 3
    if isinstance(reply, dict) and reply.get("limit"):
        _emit(fake_claude.rate_limit_event("rejected", session_id=SESSION_ID))
        _emit(fake_claude.result_event(
            SESSION_ID, {fake_claude.MAIN_MODEL: totals}, is_error=True, text=fake_claude.LIMIT_TEXT))
        return 1
    for event in _turn_events(reply, totals, index):
        _emit(event)
    return 0


def main(argv):
    spec = json.loads(Path(argv[argv.index("--spec") + 1]).read_text(encoding="utf-8"))
    rest = argv[argv.index("--spec") + 2:]
    _log(spec, {"kind": "start", "argv": rest, "cwd": os.getcwd(), "env": dict(os.environ)})
    if spec["mode"] == "stream":
        return run_stream(spec)
    return run_oneshot(spec, rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
