"""A fake `claude` that compacts a resumed session, for the probe's re-compaction arms.

Run as a script (`python fake_compact_claude.py <claude arguments>`). Every call
is logged as `fake_reply_claude` logs it (FAKE_REPLY_LOG: argv, cwd, stdin,
listing, env). A call whose stdin is a stream-json user message `/compact` and
whose argv holds `--resume <id>` runs the PreCompact hooks of its `--settings`
file through the shell, then appends to the resumed session's transcript
(`$CLAUDE_CONFIG_DIR/projects/<encoded cwd>/<id>.jsonl`) a compact boundary and
a compact summary reading `ZQNEWSUMMARY` followed by what the hooks printed, and
prints a stream-json session with no reply. Any other call answers with the
reply in FAKE_REPLY_FILE, as `fake_reply_claude` does.

FAKE_COMPACT_MODE `nosummary` makes a compaction append nothing.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import fake_claude
import fake_reply_claude

NEW_SUMMARY = "ZQNEWSUMMARY"


def _hook_output(argv):
    if "--settings" not in argv:
        return ""
    settings = json.loads(Path(argv[argv.index("--settings") + 1]).read_text(encoding="utf-8"))
    printed = []
    for entry in settings.get("hooks", {}).get("PreCompact", []):
        for hook in entry.get("hooks", []):
            done = subprocess.run(hook["command"], shell=True, capture_output=True)
            printed.append(done.stdout.decode("utf-8", errors="replace"))
    return "".join(printed)


def _compact(argv):
    session = argv[argv.index("--resume") + 1]
    folder = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())
    path = folder / f"{session}.jsonl"
    printed = _hook_output(argv)
    if os.environ.get("FAKE_COMPACT_MODE") != "nosummary":
        records = [
            {"type": "system", "subtype": "compact_boundary", "sessionId": session, "isSidechain": False,
             "content": "Conversation compacted", "compactMetadata": {"trigger": "manual", "preTokens": 900}},
            {"type": "user", "sessionId": session, "isSidechain": False, "isCompactSummary": True,
             "message": {"role": "user", "content": f"{NEW_SUMMARY} {printed}"}},
        ]
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(record) + "\n" for record in records))
    sid = fake_claude.SECRET_SESSION_IDS[0]
    totals = (3, 2, 50, 7)
    events = [
        fake_claude.init_event(sid, Path(os.getcwd())),
        {"type": "system", "subtype": "compact_boundary", "session_id": sid},
        fake_claude.result_event(sid, {fake_claude.MAIN_MODEL: totals}, text=""),
    ]
    for event in events:
        sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()
    return 0


def main(argv):
    stdin_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    fake_reply_claude._log_call(argv, stdin_text)
    try:
        message = json.loads(stdin_text.strip().splitlines()[0]) if stdin_text.strip() else None
    except ValueError:
        message = None
    content = (message or {}).get("message", {}).get("content") if isinstance(message, dict) else None
    if "--resume" in argv and isinstance(content, str) and content.strip().startswith("/compact"):
        return _compact(argv)
    reply_file = os.environ.get("FAKE_REPLY_FILE")
    reply = Path(reply_file).read_text(encoding="utf-8") if reply_file else ""
    events, code = fake_reply_claude._events(reply, None, Path(os.getcwd()))
    for event in events:
        sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
