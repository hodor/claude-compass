"""A fake `claude` that answers with a canned reply, for sessions whose output is parsed.

Run as a script (`python fake_reply_claude.py <claude arguments>`) it reads the
prompt from stdin and prints a `stream-json` session whose assistant message and
`result` text are the reply held in the file named by FAKE_REPLY_FILE. Each call
is appended as one JSON line to the file named by FAKE_REPLY_LOG:
`argv`, `cwd`, `stdin` (the prompt), `listing` (every file under the working
directory at the moment the session ran, relative, posix separators, sorted) and
`env`.

FAKE_REPLY_MODE selects what the call does:
    (unset)   the reply, exit 0
    limit     a usage-limit end (api_error usage_limit_reached), exit 1
    crash     nothing on stdout, exit 1
    error     an error result with a server api_error, exit 1

`claude purge <path> --yes` is logged and exits 0.

Imported as a module it offers the `fake_reply` pytest fixture, an object with
`.command` (the `claude_cmd` list), `.reply(text)`, `.mode(name)` and `.calls()`.
"""

import json
import os
import sys
from pathlib import Path

import pytest

import fake_claude


def _listing(root):
    found = []
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            found.append(Path(folder, name).relative_to(root).as_posix())
    return sorted(found)


def _log_call(argv, stdin_text):
    path = os.environ.get("FAKE_REPLY_LOG")
    if not path:
        return
    entry = {
        "argv": argv,
        "cwd": os.getcwd(),
        "stdin": stdin_text,
        "listing": _listing(os.getcwd()),
        "env": dict(os.environ),
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def _events(reply, mode, cwd):
    sid = fake_claude.SECRET_SESSION_IDS[0]
    model = fake_claude.MAIN_MODEL
    totals = (10, 5, 100, 20)
    if mode == "limit":
        return fake_claude.events_for("limit_api_error", cwd), 1
    if mode == "error":
        return fake_claude.events_for("error_result_other", cwd), 1
    if mode == "crash":
        return [], 1
    return [
        fake_claude.init_event(sid, cwd),
        fake_claude.assistant_event(sid, "msg_reply", reply, totals),
        fake_claude.result_event(sid, {model: totals}, text=reply),
    ], 0


def main(argv):
    stdin_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    _log_call(argv, stdin_text)
    if argv and argv[0] == "purge":
        return 0
    reply_file = os.environ.get("FAKE_REPLY_FILE")
    reply = Path(reply_file).read_text(encoding="utf-8") if reply_file else ""
    events, code = _events(reply, os.environ.get("FAKE_REPLY_MODE"), Path(os.getcwd()))
    for event in events:
        sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()
    return code


class ReplyFake:
    def __init__(self, folder, monkeypatch):
        self.command = [sys.executable, str(Path(__file__).resolve())]
        self._reply_file = folder / "reply.txt"
        self._log = folder / "reply-log.jsonl"
        self._monkeypatch = monkeypatch
        self._reply_file.write_text("", encoding="utf-8")
        monkeypatch.setenv("FAKE_REPLY_FILE", str(self._reply_file))
        monkeypatch.setenv("FAKE_REPLY_LOG", str(self._log))
        monkeypatch.delenv("FAKE_REPLY_MODE", raising=False)

    def reply(self, text):
        self._reply_file.write_text(text, encoding="utf-8")

    def mode(self, name):
        self._monkeypatch.setenv("FAKE_REPLY_MODE", name)

    def calls(self):
        if not self._log.exists():
            return []
        return [json.loads(line) for line in self._log.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def fake_reply(tmp_path, monkeypatch):
    folder = tmp_path / "fake-reply"
    folder.mkdir()
    return ReplyFake(folder, monkeypatch)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
