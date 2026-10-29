"""Tests for `compass clone` (`commands/clone.py`), which runs a headless,
non-persisted fork of old Claude Code sessions so each writes down the lessons
it learned. The binary under test is a stub set through `COMPASS_CLAUDE_BIN`
that records its argv, environment and stdin and replays a canned stream-json.

Interface pinned by these tests
-------------------------------

Invocation: `clone.run(args) -> int`, reached as

    compass clone <id>... [--jobs N] [--timeout S] [--discard]
                  [--prompt-file P] [--run-id R]

- `<id>` is a session id of UUID shape (8-4-4-4-12 hex digits, nothing
  before or after). Repeated ids collapse to one clone, first occurrence
  wins. One malformed id refuses the whole invocation.
- `--jobs N`: clones running at once, an integer >= 1, default 3.
- `--timeout S`: seconds each clone may run (a number > 0, fractions allowed),
  default 1800. The deadline restarts for every clone.
- `--discard`: save no transcript; the lesson file and `run.json` remain.
- `--prompt-file P`: UTF-8 text replacing the default prompt. Every
  `{output}` in it is replaced by the clone's lesson file path; any other
  brace text passes through untouched.
- `--run-id R`: the run folder name, `[A-Za-z0-9][A-Za-z0-9._-]*`.
- A refusal (no ids, malformed id, unknown option, bad option value, missing
  prompt file, bad run id, a run folder that already exists, a dsh binary,
  no vault) returns 1, prints a message on stderr, and creates no run folder
  and writes no log row. The command never returns 2 and never raises
  SystemExit.
- Once the run folder exists the command returns 0, whatever the clones'
  statuses; `run.json` is the record.

The project is the parent of the vault `vaultlib.find_vault_root()` finds
(`CLAUDE_PROJECT_DIR` first). The child's cwd is the project root.

Run id: `--run-id R` when given, else the UTC time `%Y%m%dT%H%M%S%fZ`
(microseconds, so two default runs never share a folder). The first stdout
line is `run-id: <id>`, the second `run-dir: <path>`; then one line per
session as it ends: `<session-id> <status>`, optionally followed by
whitespace and more text (the text names `original_changed` when the original
transcript changed).

Run folder: `sessions.run_dir(project, run_id)`, i.e.
`<COMPASS_HOME>/sessions/<project-key>/<run-id>/`, holding `run.json`, each
clone's lesson file `<session-id>.md`, and, unless `--discard`, its
transcript `<session-id>.jsonl`. Nothing else is created there.

`run.json` (rewritten atomically as each clone ends, so it always holds every
finished clone):

    {"run_id": str, "project_path": str, "project_key": str,
     "started_at": ISO-8601 UTC, "finished_at": ISO-8601 UTC | null,
     "discard": bool, "jobs": int, "timeout": number,
     "clones": [ROW, ...]}

    ROW = {"session_id": str,
           "status": "done" | "context-full" | "timeout" | "failed"
                     | "missing" | "active",
           "reason": str | null,          non-empty str for failed, timeout,
                                          missing and active
           "exit_code": int | null,
           "cost_usd": number | null,     the result line's total_cost_usd
           "lesson_file": str,            absolute path
           "kept": bool,                  a transcript was saved
           "transcript": str | null,      absolute path when kept
           "original_before": {"sha256": hex, "size": int, "mtime": number}
                              | null,
           "original_after": same shape | null,
           "original_changed": bool}      hash, size or mtime differ

A `missing` or `active` row never ran: `kept` false, `transcript` null,
`original_*` null, `original_changed` false.

Status: the last stream line whose `type` is `result` decides. `done`:
`is_error` false. `context-full`: `is_error` true and the `result` text
contains `Prompt is too long`. `failed`: any other error result, a nonzero
exit with no result line, an exit 0 with no result line, or a binary that
could not be started. `timeout`: the clone outlived `--timeout` and was
killed with its whole process tree. `missing`: the session has no transcript.
`active`: `sessionslib.is_active` (modified within 10 minutes).

Clone log: one row per clone that ran (statuses done, context-full, timeout,
failed; never missing or active) appended as one JSON line to
`<project>/.compass/meta/clone-log.jsonl`, creating the folder and tolerating
an existing log that lacks a trailing newline:

    {"event": "clone", "at": ISO-8601 UTC, "run_id": str, "session_id": str,
     "status": str, "cost_usd": number | null, "kept": bool,
     "transcript": str | null}

No row carries stream or lesson text. Every other file the run writes is
under `COMPASS_HOME`.

Child invocation: the binary is `capture_worker._resolve_binary`'s; argv
holds `-p`, `--resume <id>`, `--fork-session`, `--no-session-persistence`,
`--verbose`, `--output-format stream-json`, `--model <session model>`,
`--tools Read,Glob,Grep,Write,Edit`, `--allowedTools Read,Glob,Grep,Write,Edit`,
`--strict-mcp-config`, `--add-dir <run folder>`. The prompt goes on stdin as
UTF-8 bytes, newlines untouched, and stdin then closes; no prompt text is in
argv. The environment is the inherited one plus `DISABLE_AUTO_COMPACT=1` and
`COMPASS_WORKER_SESSION=1`. Each stdout line of the child is saved to the
transcript as it arrives, byte for byte.

Adversarial where the plan is easy to get subtly wrong: a stdin or argv
that a Windows launcher mangles, text-mode newline translation of the prompt
or the transcript, a stderr pipe nobody drains, a timeout that kills only the
launcher and not its child, a run-wide instead of per-clone deadline, a
classifier that reads a phrase out of assistant text instead of the result
line, a zero cost treated as missing, a log writer that glues rows together,
and a command that reads its own stdin and hangs in a background shell.

`commands/clone.py` does not exist yet. The import is guarded so collection
succeeds; every test fails on invocation rather than at collection.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sessionslib  # noqa: E402

try:
    from commands import clone
except ImportError:
    clone = None


LAUNCHER = Path(__file__).resolve().parents[1] / "compass"

SID_A = "3f2a9c1e-7b4d-4e8a-9c5f-0a1b2c3d4e5f"
SID_B = "9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b6a"
SID_C = "c0ffee00-1234-4abc-9def-0123456789ab"
SID_D = "0badf00d-4321-4cba-8fed-ba9876543210"

TOOLS = "Read,Glob,Grep,Write,Edit"
SENTINEL = "SECRET-STREAM-TEXT-7731"

STUB_BODY = textwrap.dedent(
    r"""
    import json
    import os
    import subprocess
    import sys
    import threading
    import time
    import uuid

    def _watchdog():
        time.sleep(22)
        os._exit(9)

    threading.Thread(target=_watchdog, daemon=True).start()

    stdin_bytes = sys.stdin.buffer.read()
    argv = sys.argv[1:]
    sid = argv[argv.index("--resume") + 1] if "--resume" in argv else "none"
    add_dir = argv[argv.index("--add-dir") + 1] if "--add-dir" in argv else None

    with open(os.environ["STUB_PLAN"], encoding="utf-8") as fh:
        plan = json.load(fh)
    spec = dict(plan.get("default", {}))
    spec.update(plan.get(sid, {}))

    calls = os.environ["STUB_CALLS"]
    os.makedirs(calls, exist_ok=True)
    with open(os.path.join(calls, sid + ".json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "argv": argv,
                "cwd": os.getcwd(),
                "env": dict(os.environ),
                "stdin": stdin_bytes.decode("utf-8", "replace"),
            },
            fh,
        )
    token = "%d-%s" % (os.getpid(), uuid.uuid4().hex)
    with open(os.path.join(calls, token + ".invoked"), "w", encoding="utf-8") as fh:
        fh.write(sid)

    counting_dir = spec.get("concurrency_dir")
    mine = None
    if counting_dir:
        os.makedirs(counting_dir, exist_ok=True)
        mine = os.path.join(counting_dir, sid + ".active")
        open(mine, "w").close()
        running = len([n for n in os.listdir(counting_dir) if n.endswith(".active")])
        os.makedirs(spec["counts_dir"], exist_ok=True)
        with open(os.path.join(spec["counts_dir"], token + ".count"), "w", encoding="utf-8") as fh:
            fh.write(str(running))

    hold = spec.get("hold_for")
    if hold:
        for _ in range(150):
            if os.path.exists(hold):
                break
            time.sleep(0.1)

    stderr_bytes = spec.get("stderr_bytes", 0)
    if stderr_bytes:
        sys.stderr.buffer.write(b"e" * stderr_bytes)
        sys.stderr.buffer.flush()

    if spec.get("lesson") is not None and add_dir:
        with open(os.path.join(add_dir, sid + ".md"), "w", encoding="utf-8") as fh:
            fh.write(spec["lesson"])

    target = spec.get("tamper_target")
    if target:
        if spec.get("tamper") == "append":
            with open(target, "ab") as fh:
                fh.write(b'{"type":"user","message":{"role":"user","content":"x"}}\n')
        elif spec.get("tamper") == "touch":
            stat = os.stat(target)
            os.utime(target, (stat.st_atime, stat.st_mtime + 500))

    data = b""
    if spec.get("stream_file"):
        with open(spec["stream_file"], "rb") as fh:
            data = fh.read()
    lines = data.splitlines(keepends=True)

    out = sys.stdout.buffer
    if lines:
        out.write(lines[0])
        out.flush()
    if spec.get("watch") and add_dir and lines:
        seen = False
        transcript = os.path.join(add_dir, sid + ".jsonl")
        for _ in range(80):
            try:
                with open(transcript, "rb") as fh:
                    if lines[0] in fh.read():
                        seen = True
                        break
            except OSError:
                pass
            time.sleep(0.1)
        with open(os.path.join(calls, sid + ".watch"), "w") as fh:
            fh.write("seen" if seen else "unseen")
    for line in lines[1:]:
        out.write(line)
        out.flush()

    if spec.get("hang"):
        heartbeat = spec["heartbeat"]
        code = (
            "import time\n"
            "for _ in range(150):\n"
            "    open(%r, 'ab').write(b'x')\n"
            "    time.sleep(0.2)\n"
        ) % heartbeat
        subprocess.Popen([sys.executable, "-c", code])
        for _ in range(50):
            if os.path.exists(heartbeat) and os.path.getsize(heartbeat) > 0:
                break
            time.sleep(0.1)
        time.sleep(25)

    if spec.get("sleep"):
        time.sleep(spec["sleep"])
    if mine:
        os.remove(mine)
    sys.exit(spec.get("exit", 0))
    """
)


def make_stub(tmp):
    body = tmp / "stub_body.py"
    body.write_text(STUB_BODY, encoding="utf-8")
    if sys.platform == "win32":
        launcher = tmp / "stub.bat"
        launcher.write_text(
            '@echo off\r\n"' + sys.executable + '" "' + str(body) + '" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher = tmp / "stub.sh"
        launcher.write_text(
            '#!/bin/sh\nexec "' + sys.executable + '" "' + str(body) + '" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    return launcher


def stream_bytes(*records):
    return b"".join(json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n" for r in records)


def init_record(sid):
    return {"type": "system", "subtype": "init", "session_id": sid}


def assistant_text(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def result_record(is_error=False, text="finished", cost=0.29):
    record = {"type": "result", "subtype": "success", "is_error": is_error, "result": text}
    if cost is not None:
        record["total_cost_usd"] = cost
    return record


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(*roots):
    seen = {}
    for root in roots:
        for path in Path(root).rglob("*"):
            if path.is_file():
                stat = path.stat()
                seen[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return seen


def norm(path):
    return os.path.normcase(os.path.normpath(str(path)))


def flag_value(argv, flag):
    return argv[argv.index(flag) + 1]


class CloneHarness(unittest.TestCase):
    """A temp project with a vault, temp `CLAUDE_CONFIG_DIR`, `COMPASS_HOME`
    and HOME, and a stub binary driven by a JSON plan file."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.project = self.base / "proj"
        (self.project / ".compass").mkdir(parents=True)
        self.cfg = self.base / "cfg"
        self.cfg.mkdir()
        self.home = self.base / "home"
        self.home.mkdir()
        self.chome = self.base / "chome"
        self.chome.mkdir()
        self.stubdir = self.base / "stub"
        self.stubdir.mkdir()
        self.calls = self.stubdir / "calls"

        backup = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(backup)))
        for name in ("DISABLE_AUTO_COMPACT", "COMPASS_WORKER_SESSION", "CLAUDE_CONFIG_DIR"):
            os.environ.pop(name, None)
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.home)
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.cfg)
        os.environ["COMPASS_HOME"] = str(self.chome)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        os.environ["COMPASS_CLAUDE_BIN"] = str(make_stub(self.stubdir))
        os.environ["STUB_PLAN"] = str(self.stubdir / "plan.json")
        os.environ["STUB_CALLS"] = str(self.calls)

        self.clean = self.stubdir / "clean.stream"
        self.clean.write_bytes(
            stream_bytes(init_record("x"), assistant_text("working"), result_record())
        )
        self.set_plan({"stream_file": str(self.clean)})

    def set_plan(self, default=None, **per_session):
        plan = {"default": default or {"stream_file": str(self.clean)}}
        plan.update(per_session)
        (self.stubdir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    def write_stream(self, name, data):
        path = self.stubdir / name
        path.write_bytes(data)
        return str(path)

    def add_session(self, sid, model="claude-opus-4-1-20250805", used=1000, age=172800):
        path = sessionslib.transcripts_dir(self.project) / f"{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {"type": "attachment", "attachment": {"type": "model", "identity": {"modelId": model}}},
            {"type": "user", "message": {"role": "user", "content": "build the feature"}},
            {
                "type": "assistant",
                "isSidechain": False,
                "message": {
                    "role": "assistant",
                    "content": [],
                    "usage": {
                        "input_tokens": used,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 10,
                    },
                },
            },
        ]
        path.write_bytes(b"".join(json.dumps(r).encode("utf-8") + b"\n" for r in records))
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
        return path

    def invoke(self, *args):
        self.assertIsNotNone(clone, "plugin/cli/commands/clone.py is not built")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = clone.run(list(args))
            except SystemExit as exc:
                self.fail(f"clone.run raised SystemExit({exc.code!r})")
        return code, out.getvalue(), err.getvalue()

    def run_dir(self, run_id):
        return sessionslib.run_dir(self.project, run_id)

    def read_run(self, run_id):
        return json.loads((self.run_dir(run_id) / "run.json").read_text(encoding="utf-8"))

    def row(self, run_id, sid):
        rows = [r for r in self.read_run(run_id)["clones"] if r["session_id"] == sid]
        self.assertEqual(len(rows), 1, f"expected one row for {sid} in {run_id}")
        return rows[0]

    def call(self, sid):
        return json.loads((self.calls / f"{sid}.json").read_text(encoding="utf-8"))

    def call_log(self):
        if not self.calls.is_dir():
            return []
        return [p.read_text(encoding="utf-8") for p in self.calls.glob("*.invoked")]

    def log_path(self):
        return self.project / ".compass" / "meta" / "clone-log.jsonl"

    def log_rows(self):
        path = self.log_path()
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def assert_nothing_created(self):
        self.assertEqual(list(self.chome.rglob("*")), [], "a refusal must create no run folder")
        self.assertFalse(self.log_path().exists(), "a refusal must write no log row")


class ChildInvocationTests(CloneHarness):
    def test_argv_carries_every_flag_intact_with_the_session_model(self):
        """Adversarial where: a Windows launcher cuts a multi-line argument
        and every argument after it, so the prompt must stay out of argv and
        each flag (tool lists with commas, a model ending in `[1m]`, a run
        folder path) must arrive whole; an unscoped tool list or a bypass flag
        would hand a clone Bash."""
        self.add_session(SID_A, model="claude-opus-4-1-20250805", used=1000)
        self.add_session(SID_B, model="claude-sonnet-4-6", used=250000)
        code, _, _ = self.invoke(SID_A, SID_B, "--run-id", "argv1", "--jobs", "1")
        self.assertEqual(code, 0)

        run_folder = self.run_dir("argv1")
        for sid, model in ((SID_A, "claude-opus-4-1-20250805"), (SID_B, "claude-sonnet-4-6[1m]")):
            with self.subTest(sid=sid):
                argv = self.call(sid)["argv"]
                self.assertIn("-p", argv)
                for flag in ("--fork-session", "--no-session-persistence", "--verbose", "--strict-mcp-config"):
                    self.assertIn(flag, argv)
                self.assertEqual(flag_value(argv, "--resume"), sid)
                self.assertEqual(flag_value(argv, "--output-format"), "stream-json")
                self.assertEqual(flag_value(argv, "--model"), model)
                self.assertEqual(flag_value(argv, "--tools"), TOOLS)
                self.assertEqual(flag_value(argv, "--allowedTools"), TOOLS)
                self.assertEqual(norm(flag_value(argv, "--add-dir")), norm(run_folder))
                self.assertFalse([a for a in argv if "\n" in a], "a newline reached argv")
                self.assertFalse([a for a in argv if "Bash" in a], "Bash reached the tool lists")
                self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_environment_is_inherited_plus_compaction_off_and_worker_marker(self):
        """Adversarial where: the child env replaces instead of extends the
        inherited one (losing `CLAUDE_PROJECT_DIR`, auth), a pre-set
        `DISABLE_AUTO_COMPACT=0` wins over the required 1 (a setdefault), or
        the child runs from the caller's cwd instead of the project root."""
        self.add_session(SID_A)
        os.environ["DISABLE_AUTO_COMPACT"] = "0"
        os.environ["COMPASS_TEST_CANARY"] = "canary-value"
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        previous = os.getcwd()
        os.chdir(elsewhere)
        self.addCleanup(os.chdir, previous)

        self.invoke(SID_A, "--run-id", "env1")
        marker = self.call(SID_A)
        env = marker["env"]
        self.assertEqual(env.get("DISABLE_AUTO_COMPACT"), "1")
        self.assertEqual(env.get("COMPASS_WORKER_SESSION"), "1")
        self.assertEqual(env.get("COMPASS_TEST_CANARY"), "canary-value")
        self.assertEqual(norm(env.get("CLAUDE_PROJECT_DIR")), norm(self.project))
        self.assertEqual(norm(env.get("CLAUDE_CONFIG_DIR")), norm(self.cfg))
        self.assertEqual(norm(marker["cwd"]), norm(self.project))

    def test_run_from_a_linked_worktree_resumes_the_main_checkout_session(self):
        """Adversarial where: run inside `.claude/worktrees/<name>`, the
        project root is the worktree, so the original transcript is looked up
        under the worktree's key and the fork runs where `--resume` cannot
        find the session (GitHub #46)."""
        def git(cwd, *args):
            subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)

        (self.project / ".compass" / ".keep").write_text("", encoding="utf-8")
        git(self.project, "init", "-q")
        git(self.project, "add", ".compass")
        git(self.project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "vault")
        worktree = self.project / ".claude" / "worktrees" / "builder-1"
        git(self.project, "worktree", "add", "-q", str(worktree))
        self.add_session(SID_A)
        os.environ["CLAUDE_PROJECT_DIR"] = str(worktree)

        code, out, err = self.invoke(SID_A, "--run-id", "wt1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.row("wt1", SID_A)["status"], "done")
        self.assertEqual(norm(self.call(SID_A)["cwd"]), norm(self.project))

    def test_prompt_arrives_whole_on_stdin_with_the_output_path_filled_in(self):
        """Adversarial where: the prompt is built with `str.format` (crashing
        on or eating other brace text), written in text mode (newlines become
        CRLF, non-ASCII becomes `?`), shared between sessions (one clone
        writes to another's lesson file), or left in argv."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        template = "Header é 日本\nWrite to {output} now.\n\n{notaplaceholder} {} {0}\nend {output}"
        prompt_file = self.base / "prompt.txt"
        prompt_file.write_bytes(template.encode("utf-8"))
        self.invoke(SID_A, SID_B, "--run-id", "p1", "--prompt-file", str(prompt_file))

        for sid in (SID_A, SID_B):
            with self.subTest(sid=sid):
                lesson = str(self.run_dir("p1") / f"{sid}.md")
                self.assertEqual(self.call(sid)["stdin"], template.replace("{output}", lesson))
                self.assertFalse([a for a in self.call(sid)["argv"] if "notaplaceholder" in a])

    def test_default_prompt_names_each_clones_own_lesson_file_and_stays_off_argv(self):
        """Adversarial where: the default prompt omits the lesson path (the
        clone cannot write as it goes), names another session's path, or is
        passed in argv where a Windows launcher cuts it."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        self.invoke(SID_A, SID_B, "--run-id", "dp1")

        for sid, other in ((SID_A, SID_B), (SID_B, SID_A)):
            with self.subTest(sid=sid):
                stdin = self.call(sid)["stdin"].replace("/", os.sep).lower()
                own = norm(self.run_dir("dp1") / f"{sid}.md")
                foreign = norm(self.run_dir("dp1") / f"{other}.md")
                self.assertIn(own, stdin)
                self.assertNotIn(foreign, stdin)
                self.assertFalse([a for a in self.call(sid)["argv"] if len(a) > 200])

    def test_command_does_not_read_its_own_stdin(self):
        """Adversarial where: a command run from a background shell with an
        open, empty stdin hangs forever if it probes or reads it; the child
        must still get the prompt on its own stdin and see it close."""
        self.add_session(SID_A)
        proc = subprocess.Popen(
            [sys.executable, str(LAUNCHER), "clone", SID_A, "--run-id", "stdin1"],
            cwd=self.project,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.addCleanup(proc.kill)
        try:
            proc.wait(timeout=45)
        except subprocess.TimeoutExpired:
            self.fail("compass clone hung with an open stdin")
        finally:
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self.row("stdin1", SID_A)["status"], "done")
        self.assertTrue(self.call(SID_A)["stdin"].strip(), "the child received an empty prompt")


class EndClassificationTests(CloneHarness):
    def test_the_result_line_alone_classifies_the_clone(self):
        """Adversarial where: the status comes from the exit code or from a
        phrase in assistant text instead of the final result line (a clone
        that merely discusses `Prompt is too long` is done), a context-full
        run (exit 1 by design) is called failed, or an error result keeps no
        reason."""
        rows = {
            "clean": (
                stream_bytes(assistant_text("ok"), result_record()),
                0, "done", 0,
            ),
            "context full exits 1": (
                stream_bytes(assistant_text("ok"), result_record(True, "Prompt is too long", 0)),
                1, "context-full", 1,
            ),
            "context full inside longer text": (
                stream_bytes(result_record(True, "API Error: Prompt is too long: 523000 > 200000", 0)),
                1, "context-full", 1,
            ),
            "phrase only in assistant text": (
                stream_bytes(assistant_text("the Prompt is too long error"), result_record()),
                0, "done", 0,
            ),
            "phrase in a non-error result": (
                stream_bytes(result_record(False, "Prompt is too long was handled")),
                0, "done", 0,
            ),
            "other error result": (
                stream_bytes(result_record(True, "Credit balance is too low", 0)),
                1, "failed", 1,
            ),
            "nonzero exit no result": (
                stream_bytes(assistant_text("ok")), 3, "failed", 3,
            ),
            "exit zero no result": (
                stream_bytes(assistant_text("ok")), 0, "failed", 0,
            ),
        }
        for index, (name, (data, exit_code, status, recorded_exit)) in enumerate(rows.items()):
            with self.subTest(name):
                sid = f"0000000{index}-0000-4000-8000-000000000000"
                self.add_session(sid)
                self.set_plan({"stream_file": self.write_stream(f"s{index}.stream", data), "exit": exit_code})
                code, _, _ = self.invoke(sid, "--run-id", f"cls{index}")
                self.assertEqual(code, 0)
                row = self.row(f"cls{index}", sid)
                self.assertEqual(row["status"], status)
                self.assertEqual(row["exit_code"], recorded_exit)
                if status == "failed":
                    self.assertTrue(isinstance(row["reason"], str) and row["reason"].strip())
        failing = self.row("cls5", "00000005-0000-4000-8000-000000000000")
        self.assertIn("Credit balance is too low", failing["reason"])

    def test_cost_is_taken_from_the_result_line_and_zero_is_not_missing(self):
        """Adversarial where: a falsy `total_cost_usd` of 0 (the free
        context-full end) is stored as null, or a result without a cost
        invents one."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        self.add_session(SID_C)
        self.set_plan(
            None,
            **{
                SID_A: {"stream_file": self.write_stream("a", stream_bytes(result_record(cost=0.29)))},
                SID_B: {"stream_file": self.write_stream("b", stream_bytes(result_record(True, "Prompt is too long", 0))), "exit": 1},
                SID_C: {"stream_file": self.write_stream("c", stream_bytes(result_record(cost=None)))},
            },
        )
        self.invoke(SID_A, SID_B, SID_C, "--run-id", "cost1")
        self.assertEqual(self.row("cost1", SID_A)["cost_usd"], 0.29)
        self.assertEqual(self.row("cost1", SID_B)["cost_usd"], 0)
        self.assertIsNotNone(self.row("cost1", SID_B)["cost_usd"])
        self.assertIsNone(self.row("cost1", SID_C)["cost_usd"])

    def test_unstartable_binary_is_a_failed_clone_not_a_crash(self):
        """Adversarial where: a missing binary raises out of the runner, so
        the run folder, `run.json` and the other clones' rows are lost."""
        self.add_session(SID_A)
        os.environ["COMPASS_CLAUDE_BIN"] = str(self.base / "no-such-binary")
        code, _, _ = self.invoke(SID_A, "--run-id", "nobin")
        self.assertEqual(code, 0)
        row = self.row("nobin", SID_A)
        self.assertEqual(row["status"], "failed")
        self.assertTrue(isinstance(row["reason"], str) and row["reason"].strip())

    def test_stderr_nobody_reads_does_not_stall_the_clone(self):
        """Adversarial where: the child's stderr is a pipe the parent never
        drains while it reads stdout, so a chatty child fills the pipe buffer
        and the clone hangs until the timeout."""
        self.add_session(SID_A)
        self.set_plan({"stream_file": str(self.clean), "stderr_bytes": 400000})
        started = time.monotonic()
        self.invoke(SID_A, "--run-id", "err1", "--timeout", "15")
        self.assertEqual(self.row("err1", SID_A)["status"], "done")
        self.assertLess(time.monotonic() - started, 12)


class TranscriptTests(CloneHarness):
    def test_kept_transcript_is_the_stream_byte_for_byte(self):
        """Adversarial where: the transcript is decoded with the console code
        page (non-ASCII mangled), written in text mode (LF becomes CRLF on
        Windows), line-length limited (a 300 KB line truncated), or filtered
        to JSON lines (a plain-text warning dropped)."""
        self.add_session(SID_A)
        data = (
            stream_bytes(init_record(SID_A), assistant_text(f"café 日本語 🙂 ñ {SENTINEL}"))
            + b"WARNING plain text line\n"
            + b"[1, 2]\n"
            + stream_bytes(assistant_text("x" * 300000), result_record())
        )
        self.set_plan({"stream_file": self.write_stream("big", data)})
        self.invoke(SID_A, "--run-id", "tr1")
        saved = (self.run_dir("tr1") / f"{SID_A}.jsonl").read_bytes()
        self.assertEqual(saved, data)
        self.assertEqual(norm(self.row("tr1", SID_A)["transcript"]), norm(self.run_dir("tr1") / f"{SID_A}.jsonl"))

    def test_invalid_utf8_in_one_line_does_not_end_the_clone(self):
        """Adversarial where: a single undecodable byte in one stream line
        (asymmetric malformation among good lines) raises out of the reader,
        losing the result line behind it and calling a finished clone
        failed."""
        self.add_session(SID_A)
        data = (
            stream_bytes(init_record(SID_A))
            + b'{"type":"assistant","note":"\xff\xfe broken"}\n'
            + stream_bytes(assistant_text("after the bad line"), result_record())
        )
        self.set_plan({"stream_file": self.write_stream("bad", data)})
        code, _, _ = self.invoke(SID_A, "--run-id", "bad1")
        self.assertEqual(code, 0)
        self.assertEqual(self.row("bad1", SID_A)["status"], "done")
        self.assertIn(b"after the bad line", (self.run_dir("bad1") / f"{SID_A}.jsonl").read_bytes())

    def test_transcript_grows_while_the_clone_is_still_running(self):
        """Adversarial where: the transcript is buffered and written when the
        clone ends, so a clone killed at its timeout leaves nothing; the stub
        checks the file for its first line before it emits the rest."""
        self.add_session(SID_A)
        data = stream_bytes(init_record(SID_A), assistant_text("second"), result_record())
        self.set_plan({"stream_file": self.write_stream("w", data), "watch": True})
        self.invoke(SID_A, "--run-id", "watch1")
        self.assertEqual((self.calls / f"{SID_A}.watch").read_text(), "seen")

    def test_discard_saves_no_transcript_but_keeps_the_lesson_file(self):
        """Adversarial where: `--discard` skips the lesson file too, or leaves
        a `.jsonl` (or a temp copy of the stream) behind; and the default
        keeps nothing but the three expected files."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        self.set_plan({"stream_file": str(self.clean), "lesson": "- keep this lesson\n"})
        self.invoke(SID_A, "--run-id", "disc1", "--discard")
        self.invoke(SID_B, "--run-id", "keep1")

        self.assertEqual(set(os.listdir(self.run_dir("disc1"))), {f"{SID_A}.md", "run.json"})
        self.assertEqual((self.run_dir("disc1") / f"{SID_A}.md").read_text(encoding="utf-8"), "- keep this lesson\n")
        row = self.row("disc1", SID_A)
        self.assertFalse(row["kept"])
        self.assertIsNone(row["transcript"])
        self.assertTrue(self.read_run("disc1")["discard"])
        log = [r for r in self.log_rows() if r["run_id"] == "disc1"]
        self.assertEqual([(r["kept"], r["transcript"]) for r in log], [(False, None)])

        self.assertEqual(set(os.listdir(self.run_dir("keep1"))), {f"{SID_B}.md", f"{SID_B}.jsonl", "run.json"})
        self.assertTrue(self.row("keep1", SID_B)["kept"])


class TimeoutTests(CloneHarness):
    def test_timeout_kills_the_whole_tree_keeps_partial_work_and_restarts_per_clone(self):
        """Adversarial where: only the launcher is killed so its child keeps
        running, the run waits out the child's sleep instead of the timeout,
        the partial lesson file or transcript lines are discarded, or the
        deadline is run-wide so the clone queued behind the hung one is cut
        short."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        heartbeat = self.stubdir / "heartbeat"
        partial = stream_bytes(init_record(SID_A), assistant_text("partial work"))
        self.set_plan(
            None,
            **{
                SID_A: {
                    "stream_file": self.write_stream("hang", partial),
                    "hang": True,
                    "heartbeat": str(heartbeat),
                    "lesson": "- half a lesson\n",
                },
            },
        )
        started = time.monotonic()
        code, _, _ = self.invoke(SID_A, SID_B, "--run-id", "to1", "--timeout", "2", "--jobs", "1")
        elapsed = time.monotonic() - started
        self.assertEqual(code, 0)
        self.assertLess(elapsed, 14, "the run waited out the hung clone")

        hung = self.row("to1", SID_A)
        self.assertEqual(hung["status"], "timeout")
        self.assertTrue(isinstance(hung["reason"], str) and hung["reason"].strip())
        self.assertEqual((self.run_dir("to1") / f"{SID_A}.jsonl").read_bytes(), partial)
        self.assertEqual((self.run_dir("to1") / f"{SID_A}.md").read_text(encoding="utf-8"), "- half a lesson\n")
        self.assertEqual(self.row("to1", SID_B)["status"], "done")

        first = heartbeat.stat().st_size
        time.sleep(1.2)
        self.assertGreater(first, 0)
        self.assertEqual(heartbeat.stat().st_size, first, "the hung clone's child outlived the kill")


class OriginalIntegrityTests(CloneHarness):
    def test_a_changed_original_is_reported_and_an_untouched_one_is_not(self):
        """Adversarial where: the before/after check compares content only
        (a bare mtime bump slips through) or size only, `original_changed`
        stays false when the clone altered the transcript, or the recorded
        hashes are not the real sha256 of the file before and after."""
        for index, (name, tamper, expect_changed) in enumerate(
            (("untouched", None, False), ("appended", "append", True), ("mtime only", "touch", True))
        ):
            with self.subTest(name):
                sid = f"1111111{index}-0000-4000-8000-000000000000"
                path = self.add_session(sid)
                before_hash, before_size = sha256_of(path), path.stat().st_size
                self.set_plan({"stream_file": str(self.clean), "tamper": tamper, "tamper_target": str(path)})
                code, out, _ = self.invoke(sid, "--run-id", f"orig{index}")
                self.assertEqual(code, 0)
                row = self.row(f"orig{index}", sid)
                self.assertEqual(row["original_changed"], expect_changed)
                self.assertEqual(row["original_before"]["sha256"], before_hash)
                self.assertEqual(row["original_before"]["size"], before_size)
                self.assertEqual(row["original_after"]["sha256"], sha256_of(path))
                self.assertEqual(row["original_after"]["size"], path.stat().st_size)
                if expect_changed:
                    line = [ln for ln in out.splitlines() if ln.startswith(sid)]
                    self.assertTrue(line and "original_changed" in line[0], out)


class RefusalAndSkipTests(CloneHarness):
    def test_malformed_session_id_refuses_the_whole_invocation(self):
        """Adversarial where: the id shape check is a prefix match or lets a
        trailing newline through (`$` before `\\n`), so a path-shaped or
        near-miss id builds a run folder or a file name from untrusted text;
        one bad id next to a good one must still refuse everything."""
        self.add_session(SID_A)
        bad_ids = {
            "short id": "aaaa1111",
            "path traversal": "../../etc/passwd",
            "trailing newline": SID_B + "\n",
            "non hex last char": SID_B[:-1] + "g",
            "no dashes": SID_B.replace("-", ""),
            "one char too long": SID_B + "0",
            "path prefix": "x/" + SID_B,
            "empty": "",
        }
        for name, bad in bad_ids.items():
            with self.subTest(name):
                code, _, err = self.invoke(SID_A, bad)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip(), "a refusal prints a message")
                self.assert_nothing_created()
                self.assertEqual(self.call_log(), [])

    def test_bad_options_are_refused_with_exit_1_never_2(self):
        """Adversarial where: argparse's own error path exits 2 (or raises
        SystemExit), a boundary value like `--jobs 0` or `--timeout 0` is
        accepted, or a run id carrying a path separator escapes the sessions
        folder."""
        self.add_session(SID_A)
        rows = {
            "no ids": [],
            "unknown option": ["--bogus", SID_A],
            "jobs missing value": [SID_A, "--jobs"],
            "jobs zero": [SID_A, "--jobs", "0"],
            "jobs negative": [SID_A, "--jobs", "-1"],
            "jobs word": [SID_A, "--jobs", "x"],
            "jobs fraction": [SID_A, "--jobs", "1.5"],
            "timeout zero": [SID_A, "--timeout", "0"],
            "timeout negative": [SID_A, "--timeout", "-5"],
            "timeout word": [SID_A, "--timeout", "abc"],
            "prompt file absent": [SID_A, "--prompt-file", str(self.base / "absent.txt")],
            "run id dot dot slash": [SID_A, "--run-id", "../x"],
            "run id slash": [SID_A, "--run-id", "a/b"],
            "run id backslash": [SID_A, "--run-id", "a\\b"],
            "run id dot dot": [SID_A, "--run-id", ".."],
            "run id colon": [SID_A, "--run-id", "run:1"],
            "run id empty": [SID_A, "--run-id", ""],
            "run id missing value": [SID_A, "--run-id"],
        }
        for name, args in rows.items():
            with self.subTest(name):
                code, _, _ = self.invoke(*args)
                self.assertEqual(code, 1)
                self.assert_nothing_created()
                self.assertEqual(self.call_log(), [])

    def test_boundary_option_values_are_accepted(self):
        """Adversarial where: the smallest legal values are refused by an
        off-by-one (`--jobs 1`, a fractional `--timeout`, a run id with dots,
        dashes and underscores)."""
        self.add_session(SID_A)
        code, _, _ = self.invoke(SID_A, "--jobs", "1", "--timeout", "0.75", "--run-id", "my.run-1_x")
        self.assertEqual(code, 0)
        run = self.read_run("my.run-1_x")
        self.assertEqual(run["jobs"], 1)
        self.assertEqual(run["timeout"], 0.75)

    def test_existing_run_folder_is_never_overwritten(self):
        """Adversarial where: reusing a `--run-id` rewrites the earlier run's
        `run.json` and lesson files, destroying the record of that run."""
        self.invoke(SID_A, "--run-id", "dup1")
        first = (self.run_dir("dup1") / "run.json").read_bytes()
        code, _, err = self.invoke(SID_B, "--run-id", "dup1")
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        self.assertEqual((self.run_dir("dup1") / "run.json").read_bytes(), first)

    def test_missing_and_active_sessions_are_reported_and_never_run(self):
        """Adversarial where: a session without a transcript or one still
        being written is cloned anyway, gets a log row, or aborts the run so
        the good session beside it never runs; an 11 minute old transcript
        sits just past the active window and must run."""
        self.add_session(SID_A)
        self.add_session(SID_C, age=300)
        self.add_session(SID_D, age=660)
        code, out, _ = self.invoke(SID_A, SID_B, SID_C, SID_D, "--run-id", "skip1", "--jobs", "1")
        self.assertEqual(code, 0)

        self.assertEqual(sorted(self.call_log()), sorted([SID_A, SID_D]))
        for sid, status in ((SID_A, "done"), (SID_B, "missing"), (SID_C, "active"), (SID_D, "done")):
            with self.subTest(sid=sid):
                row = self.row("skip1", sid)
                self.assertEqual(row["status"], status)
                self.assertRegex(out, rf"(?m)^{sid}\s+{status}\b")
                if status in ("missing", "active"):
                    self.assertTrue(isinstance(row["reason"], str) and row["reason"].strip())
                    self.assertFalse(row["kept"])
                    self.assertIsNone(row["transcript"])
                    self.assertIsNone(row["original_before"])
                    self.assertFalse(row["original_changed"])
        self.assertEqual(sorted(r["session_id"] for r in self.log_rows()), sorted([SID_A, SID_D]))
        self.assertFalse((self.run_dir("skip1") / f"{SID_B}.jsonl").exists())

    def test_repeated_session_ids_run_once(self):
        """Adversarial where: the same id given twice starts two clones that
        write one lesson file and one transcript at the same time."""
        self.add_session(SID_A)
        self.invoke(SID_A, SID_A, "--run-id", "rep1")
        self.assertEqual(self.call_log(), [SID_A])
        self.assertEqual([r["session_id"] for r in self.read_run("rep1")["clones"]], [SID_A])

    def test_a_dsh_binary_is_refused(self):
        """Adversarial where: on a machine with dsh but no claude the resolver
        falls back to dsh, which cannot resume a Claude session; the clone
        must refuse before it creates a run folder."""
        self.add_session(SID_A)
        os.environ["COMPASS_CLAUDE_BIN"] = ""
        real_which = shutil.which
        shutil.which = lambda name, *a, **k: "X:/dsh.cmd" if name == "dsh" else None
        self.addCleanup(setattr, shutil, "which", real_which)
        meta = self.project / ".compass" / "meta"
        meta.mkdir(parents=True)
        (meta / "plugin.yaml").write_text("plugin:\n  name: compass\n  version: 1.0.0\n  hosts: [claude-code, dsh]\n", encoding="utf-8")
        code, out, err = self.invoke(SID_A, "--run-id", "dsh1")
        self.assertEqual(code, 1)
        self.assertIn("dsh", (out + err).lower())
        self.assertEqual(list(self.chome.rglob("*")), [])
        self.assertEqual(self.call_log(), [])


class RunRecordTests(CloneHarness):
    def test_run_record_schema_and_run_id_selection(self):
        """Adversarial where: `run.json` lacks the run-level facts the skill
        reads, the options are stored as their defaults instead of the values
        given (`--jobs 2 --timeout 7` are neither the default 3 / 1800), the
        default run id collides within one second, or stdout does not lead
        with the run id the skill must read."""
        self.add_session(SID_A)
        code, out, _ = self.invoke(SID_A, "--jobs", "2", "--timeout", "7")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        match = re.fullmatch(r"run-id: (\d{8}T\d{12}Z)", lines[0])
        self.assertTrue(match, f"first stdout line was {lines[0]!r}")
        run_id = match.group(1)
        self.assertEqual(lines[1], f"run-dir: {self.run_dir(run_id)}")
        self.assertRegex(out, rf"(?m)^{SID_A}\s+done\b")

        run = self.read_run(run_id)
        self.assertEqual(run["run_id"], run_id)
        self.assertEqual(run["project_key"], sessionslib.project_key(self.project))
        self.assertEqual(norm(run["project_path"]), norm(self.project))
        self.assertEqual((run["jobs"], run["timeout"], run["discard"]), (2, 7, False))
        self.assertRegex(run["started_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertRegex(run["finished_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        row = run["clones"][0]
        self.assertEqual(norm(row["lesson_file"]), norm(self.run_dir(run_id) / f"{SID_A}.md"))

        ids = set()
        for _ in range(3):
            _, text, _ = self.invoke(SID_B)
            ids.add(text.splitlines()[0])
        self.assertEqual(len(ids), 3, "default run ids collided")

        _, named, _ = self.invoke(SID_B, "--run-id", "chosen")
        self.assertEqual(named.splitlines()[0], "run-id: chosen")

    def test_run_json_holds_finished_clones_while_the_next_one_still_runs(self):
        """Adversarial where: `run.json` is written once at the end, so a run
        cut short (or read by the skill mid-run) loses every clone that had
        already finished; `finished_at` must stay null until the last one
        ends."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        release = self.stubdir / "release"
        self.set_plan(None, **{SID_B: {"stream_file": str(self.clean), "hold_for": str(release)}})
        out_file = (self.stubdir / "out.txt").open("wb")
        self.addCleanup(out_file.close)
        proc = subprocess.Popen(
            [sys.executable, str(LAUNCHER), "clone", SID_A, SID_B, "--jobs", "1", "--run-id", "hold1"],
            cwd=self.project,
            stdin=subprocess.PIPE,
            stdout=out_file,
            stderr=out_file,
        )
        self.addCleanup(proc.kill)
        self.addCleanup(proc.stdin.close)
        record_path = self.run_dir("hold1") / "run.json"
        mid = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                candidate = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                candidate = None
            if candidate and any(r["session_id"] == SID_A for r in candidate["clones"]):
                mid = candidate
                break
            time.sleep(0.1)
        release.write_text("go")
        proc.wait(timeout=45)

        self.assertIsNotNone(mid, "run.json never held the first clone's row")
        self.assertEqual([r["session_id"] for r in mid["clones"]], [SID_A])
        self.assertEqual(mid["clones"][0]["status"], "done")
        self.assertIsNone(mid["finished_at"])
        final = self.read_run("hold1")
        self.assertEqual(sorted(r["session_id"] for r in final["clones"]), sorted([SID_A, SID_B]))
        self.assertIsNotNone(final["finished_at"])


class WritesAndLogTests(CloneHarness):
    def test_every_file_is_under_compass_home_except_one_textless_log_row_per_clone(self):
        """Adversarial where: a clone leaves a file in the project, in
        `~/.claude/projects` or in HOME, or the log row carries stream or
        lesson text (session data in a repository); the vault's `meta` folder
        does not exist beforehand and an existing log without a trailing
        newline must not be glued to the first new row."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        data = stream_bytes(assistant_text(SENTINEL), result_record(cost=0.29))
        self.set_plan({"stream_file": self.write_stream("secret", data), "lesson": f"- {SENTINEL}\n"})
        self.log_path().parent.mkdir(parents=True)
        old_row = json.dumps({"event": "run", "run_id": "old", "at": "2026-01-01T00:00:00Z"})
        self.log_path().write_text(old_row, encoding="utf-8")
        before = snapshot(self.project, self.cfg, self.home)

        code, _, _ = self.invoke(SID_A, SID_B, "--run-id", "w1")
        self.assertEqual(code, 0)
        after = snapshot(self.project, self.cfg, self.home)
        changed = {p for p in after if before.get(p) != after[p]}
        self.assertEqual(changed, {str(self.log_path())})
        self.assertTrue((self.run_dir("w1") / f"{SID_A}.jsonl").is_file())

        raw = self.log_path().read_text(encoding="utf-8")
        self.assertTrue(raw.startswith(old_row + "\n"), "the old row was glued to the new one")
        self.assertNotIn(SENTINEL, raw)
        rows = self.log_rows()
        self.assertEqual(rows[0]["run_id"], "old")
        clones = rows[1:]
        self.assertEqual(sorted(r["session_id"] for r in clones), sorted([SID_A, SID_B]))
        for entry in clones:
            with self.subTest(entry["session_id"]):
                self.assertEqual(entry["event"], "clone")
                self.assertRegex(entry["at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
                self.assertEqual(entry["run_id"], "w1")
                self.assertEqual(entry["status"], "done")
                self.assertEqual(entry["cost_usd"], 0.29)
                self.assertTrue(entry["kept"])
                self.assertEqual(norm(entry["transcript"]), norm(self.run_dir("w1") / f"{entry['session_id']}.jsonl"))

    def test_log_rows_accumulate_across_runs(self):
        """Adversarial where: the second run truncates the log instead of
        appending, losing the record of which clones ran earlier."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        self.invoke(SID_A, "--run-id", "acc1")
        first = self.log_path().read_text(encoding="utf-8")
        self.invoke(SID_B, "--run-id", "acc2", "--discard")
        text = self.log_path().read_text(encoding="utf-8")
        self.assertTrue(text.startswith(first))
        self.assertEqual([(r["run_id"], r["session_id"]) for r in self.log_rows()], [("acc1", SID_A), ("acc2", SID_B)])


class ConcurrencyTests(CloneHarness):
    def test_jobs_bounds_how_many_clones_run_at_once(self):
        """Adversarial where: the pool ignores `--jobs` (all sessions start
        together), is off by one at the bound, runs serially whatever the
        value, or the default is not 3; each stub reports how many stubs are
        running when it starts."""
        rows = (
            ("jobs 1", ["--jobs", "1"], 3, 1),
            ("jobs 2 with three sessions", ["--jobs", "2"], 3, 2),
            ("default jobs with four sessions", [], 4, 3),
        )
        for index, (name, extra, count, expected_max) in enumerate(rows):
            with self.subTest(name):
                sids = [f"2222222{index}-000{n}-4000-8000-000000000000" for n in range(count)]
                for sid in sids:
                    self.add_session(sid)
                counts = self.stubdir / f"counts{index}"
                self.set_plan({
                    "stream_file": str(self.clean),
                    "concurrency_dir": str(self.stubdir / f"active{index}"),
                    "counts_dir": str(counts),
                    "sleep": 1.2,
                })
                code, _, _ = self.invoke(*sids, *extra, "--run-id", f"con{index}")
                self.assertEqual(code, 0)
                seen = [int(p.read_text()) for p in counts.glob("*.count")]
                self.assertEqual(len(seen), count)
                self.assertEqual(max(seen), expected_max)
                self.assertEqual(
                    sorted(r["session_id"] for r in self.read_run(f"con{index}")["clones"]), sorted(sids)
                )


STUB2_BODY = textwrap.dedent(
    r"""
    import json
    import os
    import sys
    import uuid

    argv = sys.argv[1:]
    with open(os.environ["STUB2_PLAN"], encoding="utf-8") as fh:
        spec = json.load(fh)
    if spec.get("read_stdin", True):
        sys.stdin.buffer.read()
    sid = argv[argv.index("--resume") + 1]
    calls = os.environ["STUB_CALLS"]
    os.makedirs(calls, exist_ok=True)
    name = "%d-%s.invoked" % (os.getpid(), uuid.uuid4().hex)
    with open(os.path.join(calls, name), "w", encoding="utf-8") as fh:
        fh.write(sid)
    if spec.get("stderr_hex"):
        sys.stderr.buffer.write(bytes.fromhex(spec["stderr_hex"]))
        sys.stderr.buffer.flush()
    if spec.get("stream_file"):
        with open(spec["stream_file"], "rb") as fh:
            sys.stdout.buffer.write(fh.read())
        sys.stdout.buffer.flush()
    sys.exit(spec.get("exit", 0))
    """
)


class ImplementationBranchTests(CloneHarness):
    """Defect classes that exist only once the runner's threads, encodings
    and error handling are written."""

    def use_second_stub(self, **spec):
        body = self.stubdir / "stub2_body.py"
        body.write_text(STUB2_BODY, encoding="utf-8")
        if sys.platform == "win32":
            launcher = self.stubdir / "stub2.bat"
            launcher.write_text(
                '@echo off\r\n"' + sys.executable + '" "' + str(body) + '" %*\r\n', encoding="utf-8"
            )
        else:
            launcher = self.stubdir / "stub2.sh"
            launcher.write_text('#!/bin/sh\nexec "' + sys.executable + '" "' + str(body) + '" "$@"\n', encoding="utf-8")
            launcher.chmod(0o755)
        plan = self.stubdir / "plan2.json"
        plan.write_text(json.dumps(spec), encoding="utf-8")
        os.environ["COMPASS_CLAUDE_BIN"] = str(launcher)
        os.environ["STUB2_PLAN"] = str(plan)

    def test_child_that_exits_without_reading_a_large_prompt_is_not_a_crash(self):
        """Adversarial where: the child ends while the stdin feeder is still
        writing a prompt far larger than the pipe buffer, so the write raises
        a broken-pipe error that escapes the feeder thread (a traceback on
        stderr, a hung join, or a clone lost) instead of the result line
        deciding the status."""
        self.add_session(SID_A)
        self.use_second_stub(read_stdin=False, stream_file=str(self.clean))
        prompt_file = self.base / "huge.txt"
        prompt_file.write_bytes(("{output} " + "x" * 79 + "\n").encode("utf-8") * 100000)
        started = time.monotonic()
        code, _, err = self.invoke(SID_A, "--run-id", "pipe1", "--prompt-file", str(prompt_file), "--timeout", "30")
        self.assertEqual(code, 0)
        self.assertLess(time.monotonic() - started, 25)
        self.assertEqual(self.row("pipe1", SID_A)["status"], "done")
        self.assertNotIn("Traceback", err)
        self.assertNotIn("Exception in thread", err)

    def test_stream_edges_do_not_hide_the_result_line_and_are_saved_verbatim(self):
        """Adversarial where: the last stream line has no newline (the
        iterator hands it over unterminated), lines end in CRLF (a strip-less
        parse sees trailing `\\r`), or the result line follows a line that is
        not valid UTF-8; the result is lost, the clone is called failed, or
        the saved transcript differs from the stream by a byte."""
        rows = {
            "no final newline": (
                stream_bytes(init_record(SID_A), assistant_text("working"))
                + json.dumps(result_record(cost=0.5)).encode("utf-8"),
                0.5,
            ),
            "crlf endings": (
                stream_bytes(init_record(SID_A), result_record(cost=0.75)).replace(b"\n", b"\r\n"),
                0.75,
            ),
            "undecodable bytes then unterminated result": (
                b'{"type":"assistant","note":"\xc3\x28 half"}\n'
                + json.dumps(result_record(cost=0.125)).encode("utf-8"),
                0.125,
            ),
        }
        for index, (name, (data, cost)) in enumerate(rows.items()):
            with self.subTest(name):
                sid = f"1111111{index}-0000-4000-8000-000000000000"
                self.add_session(sid)
                self.set_plan({"stream_file": self.write_stream(f"edge{index}", data)})
                code, _, _ = self.invoke(sid, "--run-id", f"edge{index}")
                self.assertEqual(code, 0)
                row = self.row(f"edge{index}", sid)
                self.assertEqual(row["status"], "done")
                self.assertEqual(row["cost_usd"], cost)
                self.assertEqual((self.run_dir(f"edge{index}") / f"{sid}.jsonl").read_bytes(), data)

    def test_error_results_without_usable_text_or_cost_still_classify(self):
        """Adversarial where: an error result whose `result` is null, blank
        or not a string crashes the context-full substring check or leaves
        the failed row without a reason; a `total_cost_usd` that is a string
        or a boolean is stored as a cost (True would be read as 1)."""
        rows = {
            "null text": ({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": None}, "failed", None),
            "blank text": ({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "  \n"}, "failed", None),
            "numeric text": ({"type": "result", "subtype": "error_x", "is_error": True, "result": 7}, "failed", None),
            "no text key": ({"type": "result", "subtype": "error_y", "is_error": True}, "failed", None),
            "string cost": ({"type": "result", "is_error": False, "result": "ok", "total_cost_usd": "0.29"}, "done", None),
            "boolean cost": ({"type": "result", "is_error": False, "result": "ok", "total_cost_usd": True}, "done", None),
        }
        for index, (name, (record, status, cost)) in enumerate(rows.items()):
            with self.subTest(name):
                sid = f"3333333{index}-0000-4000-8000-000000000000"
                self.add_session(sid)
                self.set_plan({"stream_file": self.write_stream(f"err{index}", stream_bytes(record)), "exit": 0 if status == "done" else 1})
                code, _, _ = self.invoke(sid, "--run-id", f"err{index}")
                self.assertEqual(code, 0)
                row = self.row(f"err{index}", sid)
                self.assertEqual(row["status"], status)
                self.assertIsNone(row["cost_usd"])
                if status == "failed":
                    self.assertTrue(isinstance(row["reason"], str) and row["reason"].strip())

    def test_interleaved_and_case_variant_duplicate_ids_collapse_to_one_row_each(self):
        """Adversarial where: the same id seen both as a missing session and
        as a present one in one invocation (or spelled with different hex
        case) produces a second row, a second child, or two clones writing
        one lesson file."""
        self.add_session(SID_A)
        code, _, _ = self.invoke(SID_B, SID_A, SID_B, SID_A, SID_A.upper(), "--run-id", "dup1")
        self.assertEqual(code, 0)
        rows = self.read_run("dup1")["clones"]
        self.assertEqual(sorted((r["session_id"], r["status"]) for r in rows), sorted([(SID_B, "missing"), (SID_A, "done")]))
        self.assertEqual(self.call_log(), [SID_A])

        shutil.rmtree(self.calls)
        code, _, _ = self.invoke(SID_A.upper(), SID_A, "--run-id", "dup2")
        self.assertEqual(code, 0)
        rows = self.read_run("dup2")["clones"]
        self.assertEqual([r["session_id"].lower() for r in rows], [SID_A])
        self.assertLessEqual(len(self.call_log()), 1)

    def test_run_json_is_valid_json_at_every_moment_of_a_run(self):
        """Adversarial where: `run.json` is rewritten in place (truncate then
        write) or its temp file is shared unguarded by finishing clones, so a
        reader polling during the run sees an empty or torn file, a vanished
        file, or a clone count that goes backwards."""
        import threading

        sids = [f"4444444{n}-0000-4000-8000-000000000000" for n in range(6)]
        for sid in sids:
            self.add_session(sid)
        self.set_plan({"stream_file": str(self.clean), "sleep": 0.3})
        record_path = self.run_dir("poll1") / "run.json"
        stop = threading.Event()
        bad = []
        counts = []

        def poll():
            seen_once = False
            while not stop.is_set():
                try:
                    text = record_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    if seen_once:
                        bad.append("run.json vanished")
                except OSError:
                    pass
                else:
                    seen_once = True
                    try:
                        data = json.loads(text)
                        ids = [r["session_id"] for r in data["clones"]]
                        if len(ids) != len(set(ids)):
                            bad.append("duplicate rows")
                        counts.append(len(ids))
                    except (ValueError, KeyError) as exc:
                        bad.append(f"torn read: {exc!r}")
                time.sleep(0.001)

        poller = threading.Thread(target=poll, daemon=True)
        poller.start()
        try:
            code, _, _ = self.invoke(*sids, "--run-id", "poll1", "--jobs", "3")
        finally:
            stop.set()
            poller.join(10)
        self.assertEqual(code, 0)
        self.assertEqual(bad, [])
        self.assertGreaterEqual(len(counts), 10)
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(len(self.read_run("poll1")["clones"]), 6)
        self.assertEqual(sorted(p.name for p in self.run_dir("poll1").glob("*.tmp")), [])

    def test_project_and_home_paths_with_spaces_and_non_ascii_reach_the_child_whole(self):
        """Adversarial where: a project folder or `COMPASS_HOME` containing
        spaces and non-ASCII characters is cut at the space or mangled by
        the launcher or a locale encoding, so the lesson path in the prompt,
        `--add-dir`, the child's cwd or the log row no longer names the real
        folder."""
        self.project = self.base / "pröj ect 日本"
        (self.project / ".compass").mkdir(parents=True)
        self.chome = self.base / "chöme dir ñ"
        self.chome.mkdir()
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        os.environ["COMPASS_HOME"] = str(self.chome)
        self.add_session(SID_A)
        self.set_plan({"stream_file": str(self.clean), "lesson": "- rule é 日本\n"})
        code, _, _ = self.invoke(SID_A, "--run-id", "uni1")
        self.assertEqual(code, 0)

        row = self.row("uni1", SID_A)
        self.assertEqual(row["status"], "done")
        self.assertEqual(norm(row["lesson_file"]), norm(self.run_dir("uni1") / f"{SID_A}.md"))
        marker = self.call(SID_A)
        self.assertIn(row["lesson_file"], marker["stdin"])
        self.assertEqual(norm(flag_value(marker["argv"], "--add-dir")), norm(self.run_dir("uni1")))
        self.assertEqual(norm(marker["cwd"]), norm(self.project))
        self.assertEqual(Path(row["lesson_file"]).read_text(encoding="utf-8"), "- rule é 日本\n")
        record_text = (self.run_dir("uni1") / "run.json").read_bytes().decode("utf-8")
        self.assertIn("日本", record_text)
        self.assertEqual([entry["session_id"] for entry in self.log_rows()], [SID_A])
        self.assertEqual(norm(self.log_rows()[0]["transcript"]), norm(row["transcript"]))

    def test_error_text_with_a_lone_surrogate_does_not_break_run_json(self):
        """Adversarial where: an error result whose text carries a JSON
        `\\ud83d` escape (a truncated emoji) puts a lone surrogate in the
        row's reason; encoding `run.json` to UTF-8 then raises, and because
        the row is already in the list every later rewrite raises too, so the
        record never shows this clone or any after it."""
        self.add_session(SID_A)
        self.add_session(SID_B)
        broken = b'{"type":"result","subtype":"error_during_execution","is_error":true,"result":"boom \\ud83d cut"}\n'
        self.set_plan(
            None,
            **{
                SID_A: {"stream_file": self.write_stream("sur", broken), "exit": 1},
                SID_B: {"stream_file": str(self.clean)},
            },
        )
        code, _, _ = self.invoke(SID_A, SID_B, "--run-id", "sur1", "--jobs", "1")
        self.assertEqual(code, 0)
        text = (self.run_dir("sur1") / "run.json").read_bytes().decode("utf-8")
        data = json.loads(text)
        self.assertEqual(sorted(r["session_id"] for r in data["clones"]), sorted([SID_A, SID_B]))
        self.assertIsNotNone(data["finished_at"])
        self.assertEqual(self.row("sur1", SID_A)["status"], "failed")
        self.assertEqual(self.row("sur1", SID_B)["status"], "done")

    def test_stderr_tail_cut_inside_a_multibyte_character_still_gives_a_reason(self):
        """Adversarial where: the kept 2000-byte stderr tail starts in the
        middle of a two-byte character, and decoding it strictly raises, so
        the failed clone has no row or an unreadable `run.json`."""
        self.add_session(SID_A)
        self.use_second_stub(stderr_hex=("é" * 5000 + "x").encode("utf-8").hex(), exit=1)
        code, _, _ = self.invoke(SID_A, "--run-id", "tail1")
        self.assertEqual(code, 0)
        row = self.row("tail1", SID_A)
        self.assertEqual(row["status"], "failed")
        self.assertIn("é", row["reason"])
        self.assertLess(len(row["reason"]), 2300)

    def test_prompt_file_with_a_byte_order_mark_does_not_send_the_mark(self):
        """Adversarial where: a prompt file saved by a Windows editor starts
        with a UTF-8 byte order mark, decoded as plain UTF-8 so the child's
        prompt begins with U+FEFF."""
        self.add_session(SID_A)
        prompt_file = self.base / "bom.txt"
        prompt_file.write_bytes(b"\xef\xbb\xbfWrite to {output} now.\n")
        self.invoke(SID_A, "--run-id", "bom1", "--prompt-file", str(prompt_file))
        self.assertTrue(self.call(SID_A)["stdin"].startswith("Write to "))

    def test_timeouts_too_large_for_arithmetic_are_refused_or_run_cleanly(self):
        """Adversarial where: a timeout of several hundred digits passes
        option parsing, then overflows the deadline arithmetic after the
        child has been launched (the clone fails with an OverflowError while
        its child runs on unwatched), or becomes `inf`, which `run.json`
        writes as the non-JSON token `Infinity`."""
        rows = {
            "integer beyond float range": "9" * 400,
            "decimal that parses to infinity": "9" * 400 + ".5",
        }
        for index, (name, value) in enumerate(rows.items()):
            with self.subTest(name):
                sid = f"5555555{index}-0000-4000-8000-000000000000"
                self.add_session(sid)
                before = len(self.call_log())
                code, _, _ = self.invoke(sid, "--run-id", f"big{index}", "--timeout", value)
                self.assertIn(code, (0, 1))
                if code == 1:
                    self.assertEqual(len(self.call_log()), before, "a refusal must launch no child")
                    self.assertFalse(self.run_dir(f"big{index}").exists())
                    continue

                def reject(token):
                    raise ValueError(f"non-JSON token {token}")

                text = (self.run_dir(f"big{index}") / "run.json").read_text(encoding="utf-8")
                json.loads(text, parse_constant=reject)
                self.assertEqual(self.row(f"big{index}", sid)["status"], "done")


class InterruptTests(CloneHarness):
    def test_interrupt_stops_the_run_and_leaves_no_child_running(self):
        """Adversarial where: Ctrl-C reaches the main thread while clones run
        in a pool; the pool is not cancelled, so queued sessions still launch
        after the interrupt and the running child (in its own process group,
        deaf to the console signal) keeps going unwatched once the command
        has returned."""
        import _thread
        import threading

        sids = [f"6666666{n}-0000-4000-8000-000000000000" for n in range(3)]
        for sid in sids:
            self.add_session(sid)
        beat = self.stubdir / "beat"
        self.set_plan({"stream_file": str(self.clean), "hang": True, "heartbeat": str(beat)})
        timer = threading.Timer(2.0, _thread.interrupt_main)
        self.addCleanup(timer.cancel)
        interrupted = False
        started = time.monotonic()
        timer.start()
        try:
            self.invoke(*sids, "--run-id", "int1", "--jobs", "1", "--timeout", "4")
        except KeyboardInterrupt:
            interrupted = True
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - started, 8, "the interrupt did not stop the run")
        size = beat.stat().st_size if beat.exists() else 0
        time.sleep(1.2)
        grown = (beat.stat().st_size if beat.exists() else 0) - size
        self.assertEqual(grown, 0, "a child kept running after the command returned")
        self.assertLessEqual(len(self.call_log()), 1, "a queued session launched after the interrupt")
        self.assertTrue(interrupted or self.read_run("int1")["finished_at"] is not None)


class LogRowLineTests(unittest.TestCase):
    def test_a_unicode_line_separator_in_a_field_stays_inside_one_row(self):
        """Adversarial where: a transcript path holding U+2028, U+2029 or
        U+0085 is written raw, so a reader splitting the log with
        `splitlines()` meets fragments that are not JSON."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        log = tmp / "meta" / "clone-log.jsonl"
        for sep in (" ", " ", "\u0085"):
            clone._append_log_row(log, {"event": "clone", "transcript": f"a{sep}b"})
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["transcript"] for row in rows], ["a b", "a b", "a\u0085b"])


if __name__ == "__main__":
    unittest.main()
