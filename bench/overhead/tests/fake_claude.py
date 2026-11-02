"""A fake `claude` executable that replays canned `stream-json`.

Run as `python fake_claude.py <claude arguments>`. The scenario is named by the
environment variable FAKE_CLAUDE_SCENARIO; every invocation (argv, working
directory, the whole environment it received) is appended as one JSON line to
the file named by FAKE_CLAUDE_LOG. `fake_claude.py purge <path> --yes` logs and
exits 0, whatever the scenario.

The module also exposes the event builders so a test can build the same
streams in-process without a subprocess: `events_for(name, cwd)`.

Scenarios
---------
clean                       one turn, exit 0, result is_error false
clean_with_stray_line       clean, plus a non-JSON line in the middle of stdout
clean_mentions_limit        clean, but the model's text and a tool input quote
                            `usage_limit_reached` and `rejected`
subagent                    main model plus a subagent on a second model; one
                            message id repeated across two assistant events
multiturn_clear             two turns, `/clear`, two more turns (running totals
                            restart after the clear)
limit_event                 `rate_limit_event` with status rejected, then an
                            error result with no api_error; exit 1
limit_api_error             result is_error, subtype success, api_error
                            usage_limit_reached, no rate_limit_event; exit 1
limit_api_error_other_subtype
                            as limit_api_error with subtype error_during_execution
limit_silent                nothing on stdout; exit 1; the transcript ends in an
                            entry with isApiErrorMessage true
transient_429               rate_limit_event status allowed_warning, then an
                            error result whose api_error is not
                            usage_limit_reached; exit 1
error_result_other          is_error result, subtype success, api_error
                            server_error; exit 1
subtype_lookalike           is_error result whose subtype reads like a limit,
                            with no api_error; exit 1
crash                       two events, then a truncated JSON line; exit 3
silent_crash                nothing on stdout; exit 1; the transcript ends in an
                            ordinary assistant entry
silent_crash_no_transcript  nothing on stdout; exit 1; no transcript written
no_result_exit0             events but no result event; exit 0

A usage-limit `rate_limit_event` carries its fields both at the top level and
under `rate_limit_info`, so a reader written to either layout finds them.

A `/clear` shows in the stream as a fresh `system/init` event with a new
session id; the running totals in the `result` events that follow restart from
zero.

Each scenario (except silent_crash_no_transcript) also writes a transcript to
`$CLAUDE_CONFIG_DIR/projects/<cwd with every non-alphanumeric character
replaced by "-">/<session id>.jsonl`.
"""

import json
import os
import re
import sys
from pathlib import Path

MAIN_MODEL = "claude-opus-5-5"
SUB_MODEL = "claude-haiku-4-5"
VERSION = "2.1.316"
RESETS_AT = 1790000000

# Strings that must never reach a record.
SECRET_TOPIC = "harpsichord tuner"
SECRET_PROMPT = "Build me a harpsichord tuner called QuuxTune"
SECRET_ASSISTANT_TEXT = "I will create the zzquux engine for the harpsichord tuner"
SECRET_RESULT_TEXT = "Finished the harpsichord tuner in zzquux/engine.py"
SECRET_TOOL_PATH = "src/zzquux/engine.py"
SECRET_SESSION_IDS = (
    "5f0c1e0a-aaaa-4bbb-8ccc-0123456789ab",
    "6a1d2f1b-bbbb-4ccc-9ddd-123456789abc",
    "7b2e3a2c-cccc-4ddd-aeee-23456789abcd",
)

LIMIT_TEXT = "You've hit your limit"


def encode_cwd(cwd):
    """The folder name Claude Code gives a working directory under projects/."""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))


def _model_usage_entry(totals):
    i, o, cr, cw = totals
    return {
        "inputTokens": i,
        "outputTokens": o,
        "cacheReadInputTokens": cr,
        "cacheCreationInputTokens": cw,
        "webSearchRequests": 0,
        "costUSD": 0.0123,
        "contextWindow": 200000,
        "maxOutputTokens": 32000,
    }


def _usage_block(totals):
    i, o, cr, cw = totals
    return {
        "input_tokens": i,
        "output_tokens": o,
        "cache_read_input_tokens": cr,
        "cache_creation_input_tokens": cw,
    }


def _sum_totals(by_model):
    return tuple(sum(t[k] for t in by_model.values()) for k in range(4))


def init_event(session_id, cwd):
    return {
        "type": "system",
        "subtype": "init",
        "cwd": str(cwd),
        "session_id": session_id,
        "tools": ["Bash", "Read", "Write", "Edit", "Task"],
        "mcp_servers": [],
        "model": MAIN_MODEL,
        "permissionMode": "acceptEdits",
        "apiKeySource": "none",
        "claude_code_version": VERSION,
        "skills": [],
        "agents": [],
        "plugins": [],
        "uuid": session_id[::-1],
    }


def hook_event(session_id):
    return {
        "type": "system",
        "subtype": "hook_response",
        "hook_name": "SessionStart",
        "output": SECRET_TOPIC,
        "session_id": session_id,
    }


def rate_limit_event(status, resets_at=RESETS_AT, session_id=SECRET_SESSION_IDS[0]):
    info = {"status": status, "resetsAt": resets_at, "rateLimitType": "seven_day"}
    return {"type": "rate_limit_event", "session_id": session_id, **info, "rate_limit_info": info}


def assistant_event(session_id, message_id, text, totals, *, model=MAIN_MODEL, parent=None, tool_use=None):
    content = [{"type": "text", "text": text}]
    if tool_use is not None:
        content.append(tool_use)
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "usage": _usage_block(totals),
        },
        "parent_tool_use_id": parent,
        "session_id": session_id,
        "uuid": f"{message_id}-uuid",
    }


def user_event(session_id, text):
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": text}]},
        "session_id": session_id,
    }


def result_event(session_id, by_model, *, subtype="success", is_error=False, text=SECRET_RESULT_TEXT, **extra):
    event = {
        "type": "result",
        "subtype": subtype,
        "is_error": is_error,
        "duration_ms": 4321,
        "duration_api_ms": 3210,
        "num_turns": 2,
        "result": text,
        "session_id": session_id,
        "total_cost_usd": 0.0456,
        "usage": _usage_block(_sum_totals(by_model)) if by_model else _usage_block((0, 0, 0, 0)),
        "modelUsage": {m: _model_usage_entry(t) for m, t in by_model.items()},
        "permission_denials": [],
        "terminal_reason": "completed",
    }
    event.update(extra)
    return event


def stream_from_segments(segments, cwd):
    """Events for a session cleared between segments.

    `segments` is a list of segments; a segment is a list of snapshots; a
    snapshot maps a model id to running totals (input, output, cache_read,
    cache_write) since the segment started. Each snapshot becomes one assistant
    event and one result event; each segment opens with its own init event.
    """
    events = []
    for index, snapshots in enumerate(segments):
        sid = SECRET_SESSION_IDS[index % len(SECRET_SESSION_IDS)]
        events.append(init_event(sid, cwd))
        events.append(hook_event(sid))
        for turn, snapshot in enumerate(snapshots):
            main = snapshot.get(MAIN_MODEL, (0, 0, 0, 0))
            events.append(assistant_event(sid, f"msg_{index}_{turn}", SECRET_ASSISTANT_TEXT, main))
            events.append(result_event(sid, snapshot))
    return events


DEFAULT_CLEAR_SEGMENTS = [
    [
        {MAIN_MODEL: (100, 50, 1000, 300)},
        {MAIN_MODEL: (180, 120, 2600, 300), SUB_MODEL: (40, 10, 0, 200)},
    ],
    [
        {MAIN_MODEL: (70, 30, 5000, 100)},
        {MAIN_MODEL: (90, 90, 9000, 100)},
    ],
]


def _clean(cwd):
    sid = SECRET_SESSION_IDS[0]
    totals = {MAIN_MODEL: (321, 123, 45678, 910)}
    return [
        init_event(sid, cwd),
        rate_limit_event("allowed", session_id=sid),
        hook_event(sid),
        assistant_event(
            sid, "msg_a", SECRET_ASSISTANT_TEXT, totals[MAIN_MODEL],
            tool_use={"type": "tool_use", "id": "toolu_1", "name": "Write",
                      "input": {"file_path": SECRET_TOOL_PATH, "content": SECRET_TOPIC}},
        ),
        user_event(sid, SECRET_PROMPT),
        result_event(sid, totals),
    ]


def _subagent(cwd):
    sid = SECRET_SESSION_IDS[0]
    main_a = (200, 40, 3000, 500)
    sub_a = (60, 20, 0, 400)
    final = {MAIN_MODEL: (260, 90, 7000, 500), SUB_MODEL: (60, 20, 0, 400)}
    return [
        init_event(sid, cwd),
        assistant_event(
            sid, "msg_main_1", SECRET_ASSISTANT_TEXT, main_a,
            tool_use={"type": "tool_use", "id": "toolu_task", "name": "Task",
                      "input": {"description": SECRET_TOPIC, "prompt": SECRET_PROMPT}},
        ),
        assistant_event(sid, "msg_main_1", SECRET_ASSISTANT_TEXT, main_a),
        assistant_event(sid, "msg_sub_1", SECRET_ASSISTANT_TEXT, sub_a, model=SUB_MODEL, parent="toolu_task"),
        user_event(sid, SECRET_RESULT_TEXT),
        assistant_event(sid, "msg_main_2", SECRET_ASSISTANT_TEXT, (60, 50, 4000, 0)),
        result_event(sid, final),
    ]


def _limit_error_result(sid, **extra):
    return result_event(
        sid, {MAIN_MODEL: (50, 5, 500, 100)}, is_error=True, text=LIMIT_TEXT,
        terminal_reason="api_error", api_error_status=429, **extra,
    )


def _transcript(session_id, cwd, *, api_error_tail):
    lines = [
        {"type": "user", "message": {"role": "user", "content": SECRET_PROMPT}, "cwd": str(cwd)},
        {"type": "assistant", "message": {"id": "msg_t1", "role": "assistant",
                                          "content": [{"type": "text", "text": SECRET_ASSISTANT_TEXT}]}},
    ]
    if api_error_tail:
        lines.append({
            "type": "assistant",
            "isApiErrorMessage": True,
            "error": "rate_limit",
            "message": {"id": "msg_t2", "role": "assistant",
                        "content": [{"type": "text", "text": LIMIT_TEXT}]},
        })
    else:
        lines.append({"type": "assistant", "message": {"id": "msg_t3", "role": "assistant",
                                                      "content": [{"type": "text", "text": "done"}]}})
    return lines


def scenario(name, cwd):
    """(stdout lines, exit code, transcript lines or None) for `name`."""
    sid = SECRET_SESSION_IDS[0]
    benign = _transcript(sid, cwd, api_error_tail=False)
    if name == "clean":
        return _clean(cwd), 0, benign
    if name == "clean_with_stray_line":
        events = _clean(cwd)
        return events[:3] + ["[warn] telemetry unavailable, continuing"] + events[3:], 0, benign
    if name == "clean_mentions_limit":
        events = _clean(cwd)
        quote = 'the CLI printed "api_error": "usage_limit_reached" with status "rejected"'
        events[3] = assistant_event(
            sid, "msg_q", quote, (321, 123, 45678, 910),
            tool_use={"type": "tool_use", "id": "toolu_q", "name": "Bash",
                      "input": {"command": "echo usage_limit_reached rate_limit_event rejected"}},
        )
        events[5] = result_event(sid, {MAIN_MODEL: (321, 123, 45678, 910)}, text=quote)
        return events, 0, benign
    if name == "subagent":
        return _subagent(cwd), 0, benign
    if name == "multiturn_clear":
        return stream_from_segments(DEFAULT_CLEAR_SEGMENTS, cwd), 0, benign
    if name == "limit_event":
        events = [
            init_event(sid, cwd),
            assistant_event(sid, "msg_l1", SECRET_ASSISTANT_TEXT, (50, 5, 500, 100)),
            rate_limit_event("rejected", session_id=sid),
            result_event(sid, {MAIN_MODEL: (50, 5, 500, 100)}, is_error=True, text=LIMIT_TEXT),
        ]
        return events, 1, benign
    if name in ("limit_api_error", "limit_api_error_other_subtype"):
        subtype = "success" if name == "limit_api_error" else "error_during_execution"
        events = [
            init_event(sid, cwd),
            _limit_error_result(sid, api_error="usage_limit_reached", subtype=subtype),
        ]
        return events, 1, benign
    if name == "limit_silent":
        return [], 1, _transcript(sid, cwd, api_error_tail=True)
    if name == "transient_429":
        events = [
            init_event(sid, cwd),
            rate_limit_event("allowed_warning", session_id=sid),
            _limit_error_result(sid, api_error="rate_limit_exceeded"),
        ]
        return events, 1, benign
    if name == "error_result_other":
        events = [
            init_event(sid, cwd),
            result_event(sid, {MAIN_MODEL: (50, 5, 500, 100)}, is_error=True, text="server fell over",
                         api_error="server_error", terminal_reason="api_error", api_error_status=500),
        ]
        return events, 1, benign
    if name == "subtype_lookalike":
        events = [
            init_event(sid, cwd),
            result_event(sid, {MAIN_MODEL: (50, 5, 500, 100)}, is_error=True, text="stopped",
                         subtype="error_usage_limit_reached"),
        ]
        return events, 1, benign
    if name == "crash":
        events = [
            init_event(sid, cwd),
            assistant_event(sid, "msg_c1", SECRET_ASSISTANT_TEXT, (50, 5, 500, 100)),
            '{"type": "assistant", "message": {"id": "msg_c2", "con',
        ]
        return events, 3, benign
    if name == "silent_crash":
        return [], 1, benign
    if name == "silent_crash_no_transcript":
        return [], 1, None
    if name == "no_result_exit0":
        return [init_event(sid, cwd), assistant_event(sid, "msg_n1", SECRET_ASSISTANT_TEXT, (50, 5, 500, 100))], 0, benign
    raise KeyError(f"unknown fake claude scenario: {name}")


def events_for(name, cwd):
    """The JSON events of scenario `name` (stray non-JSON lines left out)."""
    lines, _, _ = scenario(name, cwd)
    return [line for line in lines if isinstance(line, dict)]


def _log_call(argv):
    path = os.environ.get("FAKE_CLAUDE_LOG")
    if not path:
        return
    entry = {"argv": argv, "cwd": os.getcwd(), "env": dict(os.environ)}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def main(argv):
    _log_call(argv)
    if argv and argv[0] == "purge":
        return 0
    name = os.environ.get("FAKE_CLAUDE_SCENARIO")
    if not name:
        sys.stderr.write("fake claude: FAKE_CLAUDE_SCENARIO is not set\n")
        return 2
    cwd = Path(os.getcwd())
    lines, code, transcript = scenario(name, cwd)
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    if transcript is not None and config:
        folder = Path(config) / "projects" / encode_cwd(cwd)
        folder.mkdir(parents=True, exist_ok=True)
        body = "".join(json.dumps(entry) + "\n" for entry in transcript)
        (folder / f"{SECRET_SESSION_IDS[0]}.jsonl").write_text(body, encoding="utf-8")
    for line in lines:
        sys.stdout.write((line if isinstance(line, str) else json.dumps(line)) + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
