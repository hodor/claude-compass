"""Tests for `looprunner`, the control-loop runner: one iteration through the
state machine, the dry run, and the dampener (`write_baseline`, `check`).

Public API under test (module `looprunner`, importable from `plugin/cli`).
`loop_dir` is `<project>/.compass/loops/LOOP-NNN-name/`; the project root is
`loop_dir.parents[2]` and the loop id is the folder name's `LOOP-NNN` prefix.
Every function prints for the human and returns an int exit code; none raises
for an expected refusal, and none returns 2.

    run_iteration(loop_dir, dry_run=False, *, now=None) -> int
        One iteration: lock, recover, sense, gate (budget, WIP), control,
        assemble the prompt, actuate, re-sense, judge, record, unlock. `now`
        is a timezone-aware datetime that fixes the UTC day the daily budget
        counts; None reads the clock. Exit code 0 for a run that completed
        its iteration (verified or failed actuator run, dry run). A refusal
        (an index `status` other than `active` without dry_run, a loop at
        rest in paused, halted or done, a live run lock) prints a reason on
        stderr, returns 1 and changes nothing on disk. Throttled, done and
        halted endings carry no pinned exit code.
    write_baseline(loop_dir) -> int
        Runs the domain sensor and writes its sorted items to `baseline.json`.
        0 on success. An invalid reading prints on stderr, returns 1 and
        leaves any existing `baseline.json` byte-identical. It touches neither
        `state.json` nor `ledger.jsonl`.
    check(loop_dir, blocking=False) -> int
        Runs the sensor and prints the items absent from the baseline (new)
        and the baseline items the sensor no longer reports (fixed), one per
        line. Returns 1 only when `blocking` is true and there is at least one
        new item; a fixed item alone never blocks. An invalid reading returns
        1. It never rewrites `baseline.json`.

Files a run reads and writes:

    loop.json, index.md (`status:` frontmatter), actuator.md, golden/*.md,
    feedback.md, state.json, ledger.jsonl, baseline.json   in the loop folder
    <project>/.compass/tmp/loops/LOOP-NNN.lock             the run lock
    <project>/.compass/tmp/loops/LOOP-NNN/<run-id>/        per-run scratch: a
        file holding the assembled prompt and a file holding the actuator's
        stdout

Every real (non-dry) iteration appends exactly one ledger row of type `run`,
whatever the ending, plus the `transition` rows `looplib.advance` writes. A
run row carries: `run_id`, `outcome` (helpful, neutral, harmful, failed,
throttled for a gate stop), `item` (the controller's selection, when one was
made), `cost_usd` (the result event's real cost; the run's full
`max_budget_usd` when no result event arrived; 0 for a run that never reached
the actuator), `num_turns`, `duration_ms`, `subtype`, `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_creation_tokens` (from the result
event), and `reading_before` / `reading_after`, each
`{"value": number, "items_count": n}` or null when not read.

The actuator is the binary `COMPASS_CLAUDE_BIN` names. Its stdin is the
prompt as UTF-8 bytes; its environment is the inherited one plus
`COMPASS_WORKER_SESSION=1`.

Adversarial themes: budget arithmetic exactly on the boundary and on the UTC
day line, a lock that outlives its run, a timeout that kills only the
launcher, an actuator that rewrites the controls that bound it, limits
hardcoded instead of read from `loop.json`, counters that reset or fail to
reset, a prompt that leaks the caps, a dry run that writes, and a runner that
spends money on a halted loop.
"""

import base64
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import looplib  # noqa: E402

try:
    import looprunner
except ModuleNotFoundError as exc:
    if exc.name != "looprunner":
        raise
    looprunner = None

FIXTURES = Path(CLI_DIR) / "tests" / "fixtures" / "result_events"
R2_SUCCESS = FIXTURES / "r2.json"
R3_BUDGET_STOP = FIXTURES / "r3.json"

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
ITEMS = ["alpha.py::bare-except", "bravo.py::bare-except", "charlie.py::bare-except"]

ACTUATOR_MD = (
    "ACTUATOR-MARKER-ONE: fix the selected item.\n"
    "\n"
    "Rules:\n"
    "- keep the edit small\n"
    "- explique a ação, não só o código\n"
)
GOLDEN_A = "GOLDEN-MARKER-A\n\nBefore:\n    except:\nAfter:\n    except ValueError:\n"
GOLDEN_B = "GOLDEN-MARKER-B\n\nAnti-pattern: swallowing every error.\n"
GOLDEN_IGNORED = "IGNORED-NOTES-MARKER\n"
FEEDBACK_MD = "FEEDBACK-MARKER-ONE\n\n## Guidance\n- never touch the tests folder\n"

# Values that appear in loop.json and must never reach the actuator prompt.
CAP_NUMBERS = ["37", "2.75", "91", "41.5", "83.25"]

SUCCESS_EVENTS = ["start", "off-set-point", "clear", "selected", "finished", "helpful"]

STUB_BODY = textwrap.dedent(
    r"""
    import base64
    import json
    import os
    import subprocess
    import sys
    import threading
    import time

    def _watchdog():
        time.sleep(25)
        os._exit(9)

    threading.Thread(target=_watchdog, daemon=True).start()

    stdin_bytes = sys.stdin.buffer.read()
    with open(os.environ["STUB_PLAN"], encoding="utf-8") as fh:
        plan = json.load(fh)

    calls = os.environ["STUB_CALLS"]
    os.makedirs(calls, exist_ok=True)
    n = len(os.listdir(calls))
    while True:
        n += 1
        try:
            fd = os.open(
                os.path.join(calls, "call-%03d.json" % n),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            break
        except FileExistsError:
            continue
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "argv": sys.argv[1:],
                "cwd": os.getcwd(),
                "env": dict(os.environ),
                "stdin_b64": base64.b64encode(stdin_bytes).decode("ascii"),
                "lock_exists": os.path.exists(plan["lock_path"]),
            },
            fh,
        )

    spec = dict(plan.get("default", {}))
    scripted = plan.get("calls", [])
    if n <= len(scripted):
        spec.update(scripted[n - 1])

    if spec.get("set_reading") is not None:
        with open(plan["reading_file"], "w", encoding="utf-8", newline="") as fh:
            fh.write(spec["set_reading"])
    for tamper in spec.get("tamper", []):
        mode = "a" if tamper.get("append") else "w"
        with open(tamper["path"], mode, encoding="utf-8", newline="") as fh:
            fh.write(tamper["text"])

    if spec.get("hang"):
        heartbeat = spec["heartbeat"]
        code = (
            "import time\n"
            "for _ in range(150):\n"
            "    open(%r, 'ab').write(b'x')\n"
            "    time.sleep(0.2)\n"
        ) % heartbeat
        subprocess.Popen([sys.executable, "-c", code])
        for _ in range(30):
            if os.path.exists(heartbeat) and os.path.getsize(heartbeat) > 0:
                break
            time.sleep(0.1)
        time.sleep(40)

    out = sys.stdout.buffer
    if spec.get("stdout_text") is not None:
        out.write(spec["stdout_text"].encode("utf-8"))
    elif spec.get("stdout_file"):
        with open(spec["stdout_file"], "rb") as fh:
            out.write(fh.read())
    out.flush()
    sys.exit(spec.get("exit", 0))
    """
)

# Prints the file named by argv[1]. With argv[2] it also appends the working
# directory to that log. A file starting with "SLEEP <seconds>" sleeps first.
CAT_BODY = textwrap.dedent(
    r"""
    import os
    import sys
    import time

    if len(sys.argv) > 2:
        with open(sys.argv[2], "a", encoding="utf-8") as fh:
            fh.write(os.getcwd() + "\n")
    with open(sys.argv[1], "rb") as fh:
        data = fh.read()
    if data.startswith(b"SLEEP "):
        time.sleep(float(data.split()[1]))
    sys.stdout.buffer.write(data)
    """
)


def quote(path):
    return '"%s"' % Path(path).as_posix()


def command(*parts):
    return " ".join(quote(p) for p in parts)


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


def reading(value, items=ITEMS):
    return json.dumps({"valid": True, "value": value, "items": list(items)})


def run_row(outcome, run_id, cost=0.0, item=None, ts="2026-10-18T08:00:00+00:00"):
    row = {"type": "run", "run_id": run_id, "outcome": outcome, "cost_usd": cost, "ts": ts}
    if item is not None:
        row["item"] = item
    return row


def review_row(run_id):
    return {"type": "review", "run_id": run_id, "decision": "accept"}


def resume_row():
    return {"type": "transition", "from": "halted", "event": "resume", "to": "idle",
            "reason": "test"}


def files_under(directory):
    """Map of relative path -> bytes for every file under `directory`."""
    directory = Path(directory)
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def word_present(number, text):
    return re.search(r"(?<![\w.])" + re.escape(number) + r"(?!\w)", text) is not None


class RunnerHarness(unittest.TestCase):
    """A temp project with one loop, a stub actuator binary driven by a JSON
    plan, and a sensor script that prints whatever `reading.json` holds."""

    def setUp(self):
        self.assertIsNotNone(looprunner, "plugin/cli/looprunner.py is not importable")
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.project = self.base / "proj"
        self.root = self.project / ".compass"
        self.loop_dir = self.root / "loops" / "LOOP-001-test"
        self.lock = self.root / "tmp" / "loops" / "LOOP-001.lock"
        self.scratch_root = self.root / "tmp" / "loops" / "LOOP-001"
        self.root.joinpath("meta").mkdir(parents=True)

        tools = self.base / "tools"
        tools.mkdir()
        self.cat = tools / "cat.py"
        self.cat.write_text(CAT_BODY, encoding="utf-8")
        self.reading_file = tools / "reading.json"
        self.cwd_log = tools / "cwd.log"
        self.plan_file = tools / "plan.json"
        self.calls_dir = tools / "calls"
        self.heartbeat = tools / "heartbeat.bin"
        self.stub_bin = make_stub(tools)

        saved = {
            name: os.environ.get(name)
            for name in ("CLAUDE_PROJECT_DIR", "COMPASS_CLAUDE_BIN", "COMPASS_WORKER_SESSION",
                         "STUB_PLAN", "STUB_CALLS", "XTEST_INHERITED")
        }

        def restore():
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        self.addCleanup(restore)
        os.environ.pop("COMPASS_WORKER_SESSION", None)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        os.environ["COMPASS_CLAUDE_BIN"] = str(self.stub_bin)
        os.environ["STUB_PLAN"] = str(self.plan_file)
        os.environ["STUB_CALLS"] = str(self.calls_dir)
        os.environ["XTEST_INHERITED"] = "kept-through-the-runner"

    # ---- fixtures -------------------------------------------------------

    def default_definition(self):
        return {
            "sensor_command": command(sys.executable, self.cat, self.reading_file, self.cwd_log),
            "sensor_timeout_s": 20,
            "target": 0,
            "direction": "down",
            "controller": "first",
            "model": "claude-test-model-x",
            "max_turns": 37,
            "max_budget_usd": 2.75,
            "timeout_s": 91,
            "allowed_tools": ["Read", "Edit", "Glob"],
            "daily_budget_usd": 41.5,
            "total_budget_usd": 83.25,
            "wip_limit": 4,
            "max_actuator_failures": 3,
            "max_harmful_runs": 2,
            "max_runs_without_help": 5,
        }

    def new_loop(self, definition=None, status="active", state=None, sensor=None,
                 seeds=(), stub=None, stub_calls=(), actuator=ACTUATOR_MD):
        """Build a fresh loop folder, wiping every earlier one, so a table of
        rows can share one test method."""
        for path in (self.root / "loops", self.root / "tmp", self.calls_dir):
            shutil.rmtree(path, ignore_errors=True)
        self.cwd_log.unlink(missing_ok=True)
        self.heartbeat.unlink(missing_ok=True)
        (self.loop_dir / "golden").mkdir(parents=True)
        self.definition = {**self.default_definition(), **(definition or {})}
        (self.loop_dir / "loop.json").write_text(json.dumps(self.definition), encoding="utf-8")
        (self.loop_dir / "index.md").write_text(
            "---\ntitle: Test loop\ntype: loop\nstatus: %s\nsummary: a test loop\n---\n\n"
            "# Test loop\n" % status,
            encoding="utf-8",
        )
        (self.loop_dir / "actuator.md").write_bytes(actuator.encode("utf-8"))
        (self.loop_dir / "golden" / "a-first.md").write_bytes(GOLDEN_A.encode("utf-8"))
        (self.loop_dir / "golden" / "b-second.md").write_bytes(GOLDEN_B.encode("utf-8"))
        (self.loop_dir / "golden" / "ignored.txt").write_bytes(GOLDEN_IGNORED.encode("utf-8"))
        (self.loop_dir / "feedback.md").write_bytes(FEEDBACK_MD.encode("utf-8"))
        looplib.write_state(self.loop_dir, state or {"state": "idle"})
        self.set_sensor(sensor if sensor is not None else reading(10))
        self.set_stub(stub, stub_calls)
        for row in seeds:
            looplib.append_ledger(self.loop_dir, row)
        self.seeded_run_rows = len([r for r in seeds if r.get("type") == "run"])

    def set_sensor(self, text):
        self.reading_file.write_text(text, encoding="utf-8", newline="")

    def set_stub(self, default=None, scripted=()):
        plan = {
            "reading_file": str(self.reading_file),
            "lock_path": str(self.lock),
            "default": {"stdout_file": str(R2_SUCCESS), **(default or {})},
            "calls": list(scripted),
        }
        self.plan_file.write_text(json.dumps(plan), encoding="utf-8")

    # ---- driving and reading --------------------------------------------

    def iterate(self, dry_run=False, now=NOW):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = looprunner.run_iteration(self.loop_dir, dry_run, now=now)
        return (0 if code is None else code), out.getvalue(), err.getvalue()

    def call_runner(self, function, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = function(self.loop_dir, *args)
        return (0 if code is None else code), out.getvalue(), err.getvalue()

    def calls(self):
        if not self.calls_dir.exists():
            return []
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(self.calls_dir.glob("call-*.json"))]

    @staticmethod
    def stdin_of(call):
        return base64.b64decode(call["stdin_b64"])

    def ledger(self):
        rows, skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual(skipped, [])
        return rows

    def run_rows(self):
        return [r for r in self.ledger() if r.get("type") == "run"]

    def new_run_rows(self):
        """The run rows the iteration under test appended after the seeds."""
        return self.run_rows()[self.seeded_run_rows:]

    def events(self):
        return [r["event"] for r in self.ledger() if r.get("type") == "transition"]

    def state(self):
        return looplib.read_state(self.loop_dir)["state"]

    def assert_no_lock(self):
        self.assertFalse(self.lock.exists(), "the run lock was left behind")

    def assert_nothing_launched(self):
        self.assertEqual(self.calls(), [])


class ActuatorInvocationTests(RunnerHarness):
    def test_argv_carries_the_loop_json_caps_and_never_resumes(self):
        """Adversarial where: a flag is hardcoded instead of read from
        loop.json, the prompt leaks into argv, or a second iteration resumes
        the first session (a resumed session gets a fresh budget cap)."""
        self.new_loop(
            definition={"model": "claude-test-model-y", "max_turns": 41,
                        "max_budget_usd": 1.25, "allowed_tools": ["Read", "Grep"]},
        )
        for _ in range(2):
            code, _out, _err = self.iterate()
            self.assertEqual(code, 0)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        for call in calls:
            argv = call["argv"]
            self.assertIn("-p", argv)
            self.assertEqual(argv[argv.index("--output-format") + 1], "json")
            self.assertEqual(argv[argv.index("--max-turns") + 1], "41")
            self.assertEqual(float(argv[argv.index("--max-budget-usd") + 1]), 1.25)
            self.assertEqual(argv[argv.index("--model") + 1], "claude-test-model-y")
            tail = argv[argv.index("--allowedTools") + 1:]
            names = []
            for token in tail:
                if token.startswith("-"):
                    break
                names += [t for t in re.split(r"[,\s]+", token) if t]
            self.assertEqual(sorted(names), ["Grep", "Read"])
            for banned in ("--resume", "--continue", "-c", "-r"):
                self.assertNotIn(banned, argv)
            self.assertFalse(any("ACTUATOR-MARKER" in token for token in argv))

    def test_prompt_arrives_whole_on_stdin_in_order(self):
        """Adversarial where: sections come out in the wrong order, a golden
        pattern file is dropped or a non-markdown file is included, multi-line
        text is cut at the first newline, non-ASCII text is mangled, or a
        text-mode pipe turns every LF into CRLF."""
        self.new_loop()
        self.assertEqual(self.iterate()[0], 0)
        (call,) = self.calls()
        raw = self.stdin_of(call)
        self.assertNotIn(b"\r", raw)
        prompt = raw.decode("utf-8")
        for text in (ACTUATOR_MD, GOLDEN_A, GOLDEN_B, FEEDBACK_MD):
            self.assertIn(text.strip(), prompt)
        self.assertNotIn("IGNORED-NOTES-MARKER", prompt)
        heading_selected = prompt.index("## Selected work (controller output)")
        positions = [
            prompt.index("ACTUATOR-MARKER-ONE"),
            prompt.index("## Golden patterns"),
            prompt.index("GOLDEN-MARKER-A"),
            prompt.index("GOLDEN-MARKER-B"),
            heading_selected,
            prompt.index(ITEMS[0], heading_selected),
            prompt.index("## Feedback"),
            prompt.index("FEEDBACK-MARKER-ONE"),
        ]
        self.assertEqual(positions, sorted(set(positions)))

    def test_environment_marks_the_worker_and_keeps_the_project_dir(self):
        """Adversarial where: the child is launched with a scrubbed
        environment (no CLAUDE_PROJECT_DIR) or without the worker marker, so
        the project's own hooks fire inside the headless session."""
        self.new_loop()
        self.assertEqual(self.iterate()[0], 0)
        (call,) = self.calls()
        env = call["env"]
        self.assertEqual(env.get("COMPASS_WORKER_SESSION"), "1")
        self.assertEqual(Path(env["CLAUDE_PROJECT_DIR"]).resolve(), self.project)
        self.assertEqual(env.get("XTEST_INHERITED"), "kept-through-the-runner")

    def test_prompt_never_states_a_cap_or_budget_number(self):
        """Adversarial where: the prompt tells the actuator its own turn
        count, run budget, timeout or the loop's daily and lifetime budgets,
        inviting it to ration effort around numbers instead of the task."""
        self.new_loop()
        self.assertEqual(self.iterate()[0], 0)
        sent = self.stdin_of(self.calls()[0]).decode("utf-8")
        for number in CAP_NUMBERS:
            with self.subTest(number=number):
                self.assertFalse(word_present(number, sent), f"{number} leaked")

    def test_actuator_runs_while_the_lock_is_held_and_cwd_is_the_project(self):
        """Adversarial where: the lock is taken only after the actuator has
        started (two runs spend at once), or the domain sensor runs from the
        wrong directory so a relative path in its command reads nothing."""
        self.new_loop()
        self.assertEqual(self.iterate()[0], 0)
        (call,) = self.calls()
        self.assertTrue(call["lock_exists"])
        logged = self.cwd_log.read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(logged), 2)
        for line in logged:
            self.assertEqual(Path(line).resolve(), self.project)


class RunRecordTests(RunnerHarness):
    def test_successful_run_walks_the_machine_and_records_everything(self):
        """Adversarial where: a transition is skipped or reordered, the run
        row loses a field (tokens, turns, readings, item), the real cost is
        replaced by the cap, or the per-run scratch is never written."""
        self.new_loop(stub={"set_reading": reading(8, ITEMS[1:])})
        code, _out, _err = self.iterate()
        self.assertEqual(code, 0)
        self.assertEqual(self.events(), SUCCESS_EVENTS)
        self.assertEqual(self.state(), "idle")
        (row,) = self.run_rows()
        self.assertEqual(row["outcome"], "helpful")
        self.assertEqual(row["item"], ITEMS[0])
        self.assertEqual(row["cost_usd"], 0.0463805)
        self.assertEqual(row["num_turns"], 1)
        self.assertEqual(row["duration_ms"], 1675)
        self.assertEqual(row["subtype"], "success")
        self.assertEqual(
            (row["input_tokens"], row["output_tokens"],
             row["cache_read_tokens"], row["cache_creation_tokens"]),
            (20, 219, 20375, 21614),
        )
        self.assertEqual(row["reading_before"], {"value": 10, "items_count": 3})
        self.assertEqual(row["reading_after"], {"value": 8, "items_count": 2})
        scratch = self.scratch_root / row["run_id"]
        texts = [p.read_text(encoding="utf-8") for p in scratch.iterdir()]
        sent = self.stdin_of(self.calls()[0]).decode("utf-8")
        self.assertTrue(any(sent.strip() == t.strip() for t in texts), "no prompt file")
        self.assertTrue(any('"total_cost_usd"' in t for t in texts), "no actuator output")
        self.assert_no_lock()

    def test_change_judgment_rows(self):
        """Adversarial where: the runner judges on the value alone and calls
        an improvement that adds a new finding helpful, treats a rise as
        progress under direction up, or calls an unchanged reading helpful."""
        rows = [
            ("value falls, items shrink", {}, reading(8, ITEMS[1:]), "helpful"),
            ("value falls by a hair", {}, reading(9.99), "helpful"),
            ("nothing moves", {}, reading(10), "neutral"),
            ("value rises", {}, reading(12), "harmful"),
            ("value falls but an item is new", {}, reading(8, ITEMS + ["zulu.py::bare-except"]),
             "harmful"),
            ("up: value rises", {"direction": "up", "target": 100}, reading(12), "helpful"),
            ("up: value falls", {"direction": "up", "target": 100}, reading(8), "harmful"),
        ]
        for name, definition, after, expected in rows:
            with self.subTest(name=name):
                self.new_loop(definition=definition, stub={"set_reading": after})
                self.assertEqual(self.iterate()[0], 0)
                (row,) = self.run_rows()
                self.assertEqual(row["outcome"], expected)
                self.assertEqual(self.state(), "idle")
                self.assertEqual(self.events()[-1], expected)


class GateTests(RunnerHarness):
    def assert_throttled(self, expected_event):
        self.assert_nothing_launched()
        self.assertEqual(self.state(), "throttled")
        self.assertEqual(self.events(), ["start", "off-set-point", expected_event])
        (row,) = self.new_run_rows()
        self.assertEqual(row["outcome"], "throttled")
        self.assertEqual(row.get("cost_usd", 0), 0)
        self.assertEqual(row["reading_before"], {"value": 10, "items_count": 3})
        self.assertIsNone(row["reading_after"])
        self.assert_no_lock()

    def test_daily_budget_gate_rows(self):
        """Adversarial where: the daily check is off by one at the exact fit
        (spend plus run budget equal to the budget must run), counts
        yesterday's spend, splits the UTC day at the local offset, or spends
        the run budget on a throttled run."""
        today = "2026-10-18T09:30:00+00:00"
        rows = [
            ("exact fit runs", [("2026-10-18T09:30:00+00:00", 7.25)], NOW, True),
            ("one cent over throttles", [(today, 7.26)], NOW, False),
            ("ledger at the budget throttles", [(today, 10.0)], NOW, False),
            ("two rows add up", [(today, 3.0), ("2026-10-18T10:00:00+00:00", 4.5)], NOW, False),
            ("first instant of the UTC day counts",
             [("2026-10-18T00:00:00+00:00", 7.5)], NOW, False),
            ("last second of yesterday is ignored",
             [("2026-10-17T23:59:59+00:00", 9.9)], NOW, True),
            ("an offset timestamp is read in UTC (yesterday)",
             [("2026-10-18T01:30:00+05:00", 9.9)], NOW, True),
            ("an offset timestamp is read in UTC (today)",
             [("2026-10-17T22:30:00-05:00", 7.5)], NOW, False),
            ("a non-UTC now still counts the UTC day",
             [("2026-10-18T20:00:00+00:00", 7.5)],
             datetime(2026, 10, 18, 22, 30, tzinfo=timezone(timedelta(hours=-5))), True),
        ]
        for name, spend, now, proceeds in rows:
            with self.subTest(name=name):
                seeds = [run_row("failed", f"RUN-{i}", cost, ts=ts)
                         for i, (ts, cost) in enumerate(spend)]
                self.new_loop(definition={"daily_budget_usd": 10.0, "total_budget_usd": 100.0},
                              seeds=seeds)
                self.iterate(now=now)
                if proceeds:
                    self.assertEqual(len(self.calls()), 1)
                    self.assertEqual(self.state(), "idle")
                else:
                    self.assert_throttled("daily-budget-spent")

    def test_lifetime_budget_gate_rows(self):
        """Adversarial where: the lifetime budget is compared without the
        run budget added, a spent loop merely throttles (and so resumes the
        next day) instead of halting for the human, or crashed-run charges
        are left out of the sum."""
        old = "2026-09-01T08:00:00+00:00"
        rows = [
            ("exact fit runs", [("failed", 17.25)], True),
            ("one cent over halts", [("failed", 17.26)], False),
            ("ledger at the budget halts", [("failed", 20.0)], False),
            ("a crashed run's charge counts", [("crashed", 17.5)], False),
        ]
        for name, spend, proceeds in rows:
            with self.subTest(name=name):
                seeds = [run_row(outcome, f"RUN-{i}", cost, ts=old)
                         for i, (outcome, cost) in enumerate(spend)]
                self.new_loop(definition={"daily_budget_usd": 100.0, "total_budget_usd": 20.0},
                              seeds=seeds)
                self.iterate()
                if proceeds:
                    self.assertEqual(len(self.calls()), 1)
                else:
                    self.assert_nothing_launched()
                    self.assertEqual(self.state(), "halted")
                    self.assertEqual(self.events(),
                                     ["start", "off-set-point", "total-budget-spent"])
                    (row,) = self.new_run_rows()
                    self.assertEqual(row.get("cost_usd", 0), 0)
                    self.assert_no_lock()

    def test_a_throttled_loop_runs_again_on_the_next_utc_day(self):
        """Adversarial where: throttled behaves like halted and never starts
        again, or the daily window does not roll over at midnight UTC."""
        self.new_loop(
            definition={"daily_budget_usd": 10.0, "total_budget_usd": 100.0},
            seeds=[run_row("failed", "RUN-SPENT", 7.5, ts="2026-10-18T09:00:00+00:00")],
        )
        self.iterate()
        self.assertEqual(self.state(), "throttled")
        self.assert_nothing_launched()
        code, _out, _err = self.iterate(now=NOW + timedelta(days=1))
        self.assertEqual(code, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.state(), "idle")

    def test_wip_gate_rows(self):
        """Adversarial where: the WIP limit is off by one, reviewed
        increments still count, a failed run is counted as an increment, or a
        wip_command is ignored in favour of the ledger count."""
        unreviewed = [run_row("neutral", f"RUN-{i}", item=f"old-{i}") for i in range(3)]
        reviewed = unreviewed + [review_row("RUN-0")]
        rows = [
            ("at the limit throttles", {}, unreviewed, None, False),
            ("one under the limit runs", {}, unreviewed[:2], None, True),
            ("a reviewed increment is released", {}, reviewed, None, True),
            ("failed runs hold no increment", {},
             [run_row("failed", f"RUN-{i}") for i in range(3)], None, True),
            ("wip_command above the limit throttles an empty ledger", {}, [], "5", False),
            ("wip_command at the limit throttles", {}, [], "3", False),
            ("wip_command under the limit overrides a full ledger", {}, unreviewed, "2", True),
        ]
        for name, definition, seeds, wip_output, proceeds in rows:
            with self.subTest(name=name):
                definition = {**definition, "wip_limit": 3}
                if wip_output is not None:
                    wip_file = self.base / "tools" / "wip.txt"
                    wip_file.write_text(wip_output, encoding="utf-8")
                    definition["wip_command"] = command(sys.executable, self.cat, wip_file)
                self.new_loop(definition=definition, seeds=seeds)
                self.iterate()
                if proceeds:
                    self.assertEqual(len(self.calls()), 1)
                else:
                    self.assert_throttled("wip-full")

    def test_set_point_rows(self):
        """Adversarial where: a reading exactly at the target still launches
        the actuator (off by one on the comparison), a reading past the target
        is not done, or the direction is ignored."""
        rows = [
            ("down: at the target", "down", 3.5, 3.5, True),
            ("down: past the target", "down", 3.5, 2, True),
            ("down: just above the target", "down", 3.5, 3.75, False),
            ("up: at the target", "up", 3.5, 3.5, True),
            ("up: past the target", "up", 3.5, 9, True),
            ("up: just below the target", "up", 3.5, 3.25, False),
        ]
        for name, direction, target, value, done in rows:
            with self.subTest(name=name):
                self.new_loop(definition={"direction": direction, "target": target},
                              sensor=reading(value))
                self.assertEqual(self.iterate()[0], 0)
                if done:
                    self.assert_nothing_launched()
                    self.assertEqual(self.state(), "done")
                    self.assertEqual(self.events(), ["start", "at-set-point"])
                    self.assertEqual(len(self.run_rows()), 1)
                else:
                    self.assertEqual(len(self.calls()), 1)
                    self.assertEqual(self.state(), "idle")
                self.assert_no_lock()

    def test_invalid_reading_halts_without_launching(self):
        """Adversarial where: unparseable, valid:false, non-numeric, empty or
        hung sensor output is read as "no findings" and the loop reports done
        or runs the actuator on nothing."""
        rows = [
            ("not json", "garbage", {}),
            ("valid false", json.dumps({"valid": False}), {}),
            ("non-numeric value", json.dumps({"valid": True, "value": "ten", "items": []}), {}),
            ("items is not a list", json.dumps({"valid": True, "value": 10, "items": "alpha"}), {}),
            ("empty output", "", {}),
            ("sensor hangs past its timeout", "SLEEP 30", {"sensor_timeout_s": 2}),
        ]
        for name, text, definition in rows:
            with self.subTest(name=name):
                self.new_loop(definition=definition, sensor=text)
                started = time.monotonic()
                self.iterate()
                self.assertLess(time.monotonic() - started, 15)
                self.assert_nothing_launched()
                self.assertEqual(self.state(), "halted")
                self.assertEqual(self.events(), ["start", "invalid-reading"])
                self.assertEqual(len(self.run_rows()), 1)
                reason = [r for r in self.ledger() if r.get("event") == "invalid-reading"][0]
                self.assertTrue(str(reason.get("reason", "")).strip())
                self.assert_no_lock()


class FailureAndLimitTests(RunnerHarness):
    def test_failed_actuator_run_rows(self):
        """Adversarial where: a budget stop is recorded at the cap or at zero
        instead of its real cost (the usage block is zeroed there), a run
        with no result event costs nothing, or a launch failure escapes as an
        exception and strands the loop in a working state."""
        full = 2.75
        truncated = R2_SUCCESS.read_text(encoding="utf-8")[:60]
        rows = [
            ("budget stop keeps its real cost",
             {"stdout_file": str(R3_BUDGET_STOP), "exit": 1}, 0.0174133,
             {"subtype": "error_max_budget_usd", "input_tokens": 10, "output_tokens": 280,
              "cache_read_tokens": 13053, "cache_creation_tokens": 7349}),
            ("garbage output costs the full run budget",
             {"stdout_text": "not a result event", "exit": 0}, full, {}),
            ("empty output costs the full run budget", {"stdout_text": "", "exit": 1}, full, {}),
            ("truncated envelope costs the full run budget",
             {"stdout_text": truncated, "exit": 0}, full, {}),
        ]
        for name, spec, cost, extra in rows:
            with self.subTest(name=name):
                self.new_loop(stub=spec)
                self.iterate()
                (row,) = self.run_rows()
                self.assertEqual(row["outcome"], "failed")
                self.assertEqual(row["cost_usd"], cost)
                for key, value in extra.items():
                    self.assertEqual(row[key], value)
                self.assertEqual(self.state(), "idle")
                self.assertEqual(self.events()[-1], "failed")
                self.assert_no_lock()
        with self.subTest(name="binary that cannot launch"):
            self.new_loop()
            os.environ["COMPASS_CLAUDE_BIN"] = str(self.base / "no-such-binary")
            self.iterate()
            (row,) = self.run_rows()
            self.assertEqual(row["outcome"], "failed")
            self.assertEqual(row["cost_usd"], full)
            self.assertEqual(self.state(), "idle")
            self.assert_no_lock()

    def test_consecutive_failure_limit_rows(self):
        """Adversarial where: the limit is hardcoded to 3 instead of read
        from loop.json, the current failure is not counted, or the streak
        survives a verified run or a resume."""
        def failed(i):
            return run_row("failed", f"RUN-F{i}")

        rows = [
            ("limit 3 reached by the third failure", 3, [failed(1), failed(2)], True),
            ("limit 3 not reached by the second", 3, [failed(1)], False),
            ("limit 4 survives the third failure", 4, [failed(1), failed(2)], False),
            ("limit 4 reached by the fourth", 4, [failed(1), failed(2), failed(3)], True),
            ("a resume zeroes the streak", 4,
             [failed(1), failed(2), failed(3), resume_row()], False),
            ("a verified run ends the streak", 3,
             [failed(1), failed(2), run_row("helpful", "RUN-OK", item="old")], False),
        ]
        for name, limit, seeds, halts in rows:
            with self.subTest(name=name):
                self.new_loop(
                    definition={"max_actuator_failures": limit},
                    seeds=seeds,
                    stub={"stdout_file": str(R3_BUDGET_STOP), "exit": 1},
                )
                self.iterate()
                self.assertEqual(len(self.calls()), 1)
                self.assertEqual(self.state(), "halted" if halts else "idle")
                self.assertEqual(self.events()[-1], "failed-limit" if halts else "failed")
                self.assert_no_lock()

    def test_two_worsening_runs_in_a_row_halt(self):
        """Adversarial where: the second harmful run does not halt the loop
        because the readings of the first run are not carried into the next
        iteration, or the harmful streak is read from memory instead of the
        ledger."""
        self.new_loop(stub_calls=[{"set_reading": reading(12)}, {"set_reading": reading(14)}])
        self.iterate()
        self.assertEqual(self.state(), "idle")
        self.assertEqual(self.run_rows()[0]["outcome"], "harmful")
        self.iterate()
        self.assertEqual(self.state(), "halted")
        self.assertEqual(self.run_rows()[1]["outcome"], "harmful")
        self.assertEqual(self.events()[-1], "harmful-limit")
        self.assert_no_lock()

    def test_harmful_run_limit_rows(self):
        """Adversarial where: the limit is hardcoded to 2, the current harmful
        run is not counted, or a helpful or neutral run in between does not
        end the streak."""
        def harmful(i):
            return run_row("harmful", f"RUN-H{i}", item=f"old-h{i}")

        rows = [
            ("limit 3 not reached by the second", 3, [harmful(1)], False),
            ("limit 3 reached by the third", 3, [harmful(1), harmful(2)], True),
            ("limit 2 reached by the second", 2, [harmful(1)], True),
            ("a helpful run ends the streak", 2,
             [harmful(1), run_row("helpful", "RUN-OK", item="old-ok")], False),
            ("a neutral run ends the streak", 2,
             [harmful(1), run_row("neutral", "RUN-NEU", item="old-neu")], False),
        ]
        for name, limit, seeds, halts in rows:
            with self.subTest(name=name):
                self.new_loop(definition={"max_harmful_runs": limit}, seeds=seeds,
                              stub={"set_reading": reading(12)})
                self.iterate()
                self.assertEqual(self.state(), "halted" if halts else "idle")
                self.assertEqual(self.events()[-1], "harmful-limit" if halts else "harmful")

    def test_runs_without_help_limit_rows(self):
        """Adversarial where: the no-progress limit is hardcoded to 5, a
        helpful run does not reset the count, or a helpful current run is
        itself halted."""
        def neutral(i):
            return run_row("neutral", f"RUN-N{i}", item=f"old-n{i}")

        rows = [
            ("third verified run without help halts", [neutral(1), neutral(2)], reading(10), True),
            ("second does not", [neutral(1)], reading(10), False),
            ("a helpful run in between resets the count",
             [neutral(1), neutral(2), run_row("helpful", "RUN-OK", item="old-ok")],
             reading(10), False),
            ("the current run is helpful", [neutral(1), neutral(2)], reading(8), False),
        ]
        for name, seeds, after, halts in rows:
            with self.subTest(name=name):
                self.new_loop(definition={"max_runs_without_help": 3}, seeds=seeds,
                              stub={"set_reading": after})
                self.iterate()
                self.assertEqual(self.state(), "halted" if halts else "idle")
                if halts:
                    self.assertEqual(self.events()[-1], "no-progress-limit")


class IsolationTests(RunnerHarness):
    def test_timeout_kills_the_actuator_and_its_child(self):
        """Adversarial where: the timeout kills only the launcher, so a
        descendant keeps editing the checkout, or the wait is unbounded; the
        run must cost the full run budget."""
        self.new_loop(
            definition={"timeout_s": 4},
            stub={"hang": True, "heartbeat": str(self.heartbeat)},
        )
        started = time.monotonic()
        self.iterate()
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 20)
        size = self.heartbeat.stat().st_size
        self.assertGreater(size, 0, "the stub's child never started")
        time.sleep(1.2)
        self.assertEqual(self.heartbeat.stat().st_size, size, "the child outlived the run")
        (row,) = self.run_rows()
        self.assertEqual(row["outcome"], "failed")
        self.assertEqual(row["cost_usd"], 2.75)
        self.assertEqual(self.state(), "idle")
        self.assert_no_lock()

    def test_actuator_that_edits_the_controls_halts_the_loop(self):
        """Adversarial where: an actuator that rewrites loop.json (valid or
        broken), resets state.json, forges a ledger row or edits baseline.json
        goes unnoticed, the broken file crashes the runner while the loop
        sits in a working state, or the run's real cost is lost."""
        forged = '{"type": "review", "run_id": "forged"}\n'
        edited = json.dumps({**self.default_definition(), "max_budget_usd": 99})
        rows = [
            ("loop.json edited", "loop.json", edited, False),
            ("loop.json broken", "loop.json", "{not json", False),
            ("state.json reset", "state.json", json.dumps({"state": "idle"}), False),
            ("ledger.jsonl appended", "ledger.jsonl", forged, True),
            ("baseline.json edited", "baseline.json", json.dumps({"items": ["x"]}), False),
        ]
        for name, filename, text, append in rows:
            with self.subTest(name=name):
                self.new_loop()
                (self.loop_dir / "baseline.json").write_text(
                    json.dumps({"items": []}), encoding="utf-8")
                self.set_stub({"tamper": [{"path": str(self.loop_dir / filename),
                                           "text": text, "append": append}]})
                self.iterate()
                self.assertEqual(self.state(), "halted")
                events = self.events()
                self.assertEqual(events[-1], "controls-changed")
                self.assertNotIn("finished", events)
                row = [r for r in self.run_rows() if r.get("run_id") != "forged"][-1]
                self.assertEqual(row["cost_usd"], 0.0463805)
                self.assert_no_lock()

    def test_lock_is_released_in_every_resting_ending(self):
        """Adversarial where: an early return (done, halted, throttled, a
        failed or tampered run) skips the unlock, so every later run is
        refused by a lock nobody holds."""
        rows = [
            ("done", dict(sensor=reading(0))),
            ("invalid reading", dict(sensor="garbage")),
            ("throttled by wip", dict(
                definition={"wip_limit": 1},
                seeds=[run_row("neutral", "RUN-1", item="old-1")])),
            ("verified run", dict()),
            ("failed run", dict(stub={"stdout_file": str(R3_BUDGET_STOP), "exit": 1})),
            ("controls changed", dict(stub={"tamper": [{
                "path": str(self.loop_dir / "loop.json"), "text": "{}", "append": False}]})),
        ]
        for name, kwargs in rows:
            with self.subTest(name=name):
                self.new_loop(**kwargs)
                self.iterate()
                self.assertIn(self.state(), looplib.RESTING)
                self.assert_no_lock()
        with self.subTest(name="lock exists while the actuator runs"):
            self.new_loop()
            self.iterate()
            self.assertTrue(self.calls()[0]["lock_exists"])

    def test_a_live_lock_refuses_the_run_and_survives_it(self):
        """Adversarial where: a second run starts while one is live, or the
        refused run deletes the lock the live run still holds."""
        self.new_loop()
        looplib.acquire_lock(self.lock, 91)
        before = (self.lock.read_bytes(), files_under(self.loop_dir))
        code, _out, err = self.iterate(now=None)
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        self.assert_nothing_launched()
        self.assertEqual((self.lock.read_bytes(), files_under(self.loop_dir)), before)

    def test_crash_left_state_is_recovered_before_the_run_proceeds(self):
        """Adversarial where: a loop found in a working state is refused
        forever, the crashed run is not charged its full budget, or the
        recovery happens after the new run has already started."""
        stale = '{"pid": 1, "started": 1000.0}'
        rows = [("no lock file", None), ("stale lock file", stale)]
        for name, lock_text in rows:
            with self.subTest(name=name):
                self.new_loop(
                    state={"state": "actuating", "run_id": "RUN-OLD", "item": ITEMS[0]})
                if lock_text is not None:
                    self.lock.parent.mkdir(parents=True, exist_ok=True)
                    self.lock.write_text(lock_text, encoding="utf-8")
                code, _out, _err = self.iterate()
                self.assertEqual(code, 0)
                self.assertEqual(len(self.calls()), 1)
                self.assertEqual(self.state(), "idle")
                outcomes = [(r["run_id"], r["outcome"]) for r in self.run_rows()]
                self.assertEqual(outcomes[0], ("RUN-OLD", "crashed"))
                self.assertEqual(len(outcomes), 2)
                crashed = self.run_rows()[0]
                self.assertEqual(crashed["cost_usd"], 2.75)
                events = self.events()
                self.assertIn("crash-recovered", events)
                self.assertLess(events.index("crash-recovered"), events.index("start"))
                self.assert_no_lock()


class ControllerTests(RunnerHarness):
    def test_first_controller_skips_items_held_by_unreviewed_runs(self):
        """Adversarial where: the controller re-selects an item an unreviewed
        increment already holds, treats a reviewed or failed run as holding
        it, or sends the actuator an item that is not the one recorded."""
        rows = [
            ("first item held", [run_row("neutral", "RUN-1", item=ITEMS[0])], ITEMS[1]),
            ("two items held", [run_row("neutral", "RUN-1", item=ITEMS[0]),
                                run_row("harmful", "RUN-2", item=ITEMS[1])], ITEMS[2]),
            ("reviewed run releases its item",
             [run_row("neutral", "RUN-1", item=ITEMS[0]), review_row("RUN-1")], ITEMS[0]),
            ("failed run holds nothing", [run_row("failed", "RUN-1", item=ITEMS[0])], ITEMS[0]),
        ]
        for name, seeds, expected in rows:
            with self.subTest(name=name):
                self.new_loop(seeds=seeds)
                self.iterate()
                (call,) = self.calls()
                prompt = self.stdin_of(call).decode("utf-8")
                start = prompt.index("## Selected work (controller output)")
                section = prompt[start:prompt.index("## Feedback")]
                self.assertIn(expected, section)
                for other in ITEMS:
                    if other != expected:
                        self.assertNotIn(other, section)
                self.assertEqual(self.run_rows()[-1]["item"], expected)

    def test_nothing_to_select_halts_without_launching(self):
        """Adversarial where: every item is held, or the sensor reports none,
        and the runner launches the actuator on an empty or repeated task."""
        held = [run_row("neutral", f"RUN-{i}", item=item) for i, item in enumerate(ITEMS)]
        rows = [
            ("all items held", reading(10), held, {"wip_limit": 4}),
            ("no items at all", reading(10, []), [], {}),
        ]
        for name, sensor, seeds, definition in rows:
            with self.subTest(name=name):
                self.new_loop(definition=definition, sensor=sensor, seeds=seeds)
                self.iterate()
                self.assert_nothing_launched()
                self.assertEqual(self.state(), "halted")
                self.assertEqual(self.events()[-1], "nothing-selected")
                self.assert_no_lock()

    def test_command_controller_output_is_the_control_signal(self):
        """Adversarial where: the command controller's output is ignored in
        favour of the first sensor item, or an empty output launches the
        actuator with nothing to work on."""
        rows = [("script names the work", "pinned::item\n", "pinned::item"),
                ("script prints nothing", "", None)]
        for name, output, item in rows:
            with self.subTest(name=name):
                signal = self.base / "tools" / "signal.txt"
                signal.write_text(output, encoding="utf-8", newline="")
                self.new_loop(definition={
                    "controller": "command",
                    "controller_command": command(sys.executable, self.cat, signal)})
                self.iterate()
                if item is None:
                    self.assert_nothing_launched()
                    self.assertEqual(self.state(), "halted")
                    self.assertEqual(self.events()[-1], "nothing-selected")
                else:
                    (call,) = self.calls()
                    prompt = self.stdin_of(call).decode("utf-8")
                    start = prompt.index("## Selected work (controller output)")
                    self.assertIn(item, prompt[start:prompt.index("## Feedback")])
                    self.assertEqual(self.run_rows()[-1]["item"], item)


class RefusalAndDryRunTests(RunnerHarness):
    def test_loop_that_is_not_active_refuses_without_dry_run(self):
        """Adversarial where: a draft, review, done or archived loop spends
        money because only the state file is consulted, or a refusal writes a
        lock, a ledger row or scratch before it refuses."""
        for status in ("draft", "review", "done", "archived"):
            with self.subTest(status=status):
                self.new_loop(status=status)
                before = files_under(self.root)
                code, _out, err = self.iterate()
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assert_nothing_launched()
                self.assertEqual(files_under(self.root), before)

    def test_dry_run_of_a_draft_loop_prints_the_prompt_and_writes_nothing(self):
        """Adversarial where: dry run is refused for a draft loop (so a loop
        cannot be previewed before activation), or it writes a run row, moves
        the state, or launches the actuator."""
        self.new_loop(status="draft", seeds=[run_row("failed", "RUN-1", 0.01)])
        before = files_under(self.loop_dir)
        code, out, _err = self.iterate(dry_run=True)
        self.assertEqual(code, 0)
        self.assertIn("ACTUATOR-MARKER-ONE", out)
        self.assertIn(ITEMS[0], out)
        self.assert_nothing_launched()
        self.assertEqual(files_under(self.loop_dir), before)
        self.assert_no_lock()

    def test_dry_run_prints_exactly_the_prompt_a_real_run_sends(self):
        """Adversarial where: the dry run assembles a different prompt than
        the run it previews, or leaves state.json and ledger.jsonl changed."""
        self.new_loop(seeds=[run_row("failed", "RUN-1", 0.01)])
        state_before = (self.loop_dir / "state.json").read_bytes()
        ledger_before = (self.loop_dir / "ledger.jsonl").read_bytes()
        code, out, _err = self.iterate(dry_run=True)
        self.assertEqual(code, 0)
        self.assert_nothing_launched()
        self.assertEqual((self.loop_dir / "state.json").read_bytes(), state_before)
        self.assertEqual((self.loop_dir / "ledger.jsonl").read_bytes(), ledger_before)
        self.assertEqual([r for r in self.run_rows() if r["run_id"] != "RUN-1"], [])
        self.assert_no_lock()
        self.assertEqual(self.iterate()[0], 0)
        sent = self.stdin_of(self.calls()[0]).decode("utf-8")
        self.assertIn(sent, out)

    def test_dry_run_leaves_a_crash_left_loop_untouched(self):
        """Adversarial where: a dry run performs crash recovery on disk
        (a crashed row and a transition), writing to a ledger it promised to
        leave alone."""
        self.new_loop(state={"state": "actuating", "run_id": "RUN-OLD", "item": ITEMS[0]},
                      seeds=[run_row("failed", "RUN-1", 0.01)])
        before = files_under(self.loop_dir)
        self.iterate(dry_run=True)
        self.assert_nothing_launched()
        self.assertEqual(files_under(self.loop_dir), before)

    def test_a_loop_at_rest_in_paused_halted_or_done_does_not_run(self):
        """Adversarial where: a halted, paused or finished loop is started
        anyway (start is only legal from idle and throttled), spending the
        budget the halt was meant to protect."""
        for state in ("paused", "halted", "done"):
            with self.subTest(state=state):
                self.new_loop(state={"state": state})
                before = files_under(self.root)
                code, _out, err = self.iterate()
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
                self.assert_nothing_launched()
                self.assertEqual(files_under(self.root), before)

    def test_throttled_loop_starts_again(self):
        """Adversarial where: a loop stored as throttled is refused because
        start is checked against idle only."""
        self.new_loop(state={"state": "throttled"})
        self.assertEqual(self.iterate()[0], 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.state(), "idle")


class DampenerTests(RunnerHarness):
    def baseline_text(self):
        return (self.loop_dir / "baseline.json").read_text(encoding="utf-8")

    def write_baseline_ok(self):
        code, _out, _err = self.call_runner(looprunner.write_baseline)
        self.assertEqual(code, 0)

    def test_write_baseline_commits_the_sorted_items(self):
        """Adversarial where: the baseline keeps sensor order, stores nothing
        for a valid empty reading, rewrites state or ledger, or an invalid
        reading overwrites a good baseline with an empty one."""
        self.new_loop(seeds=[run_row("failed", "RUN-1", 0.01)],
                      sensor=reading(3, ["zulu.py::x", "alpha.py::x", "mike.py::x"]))
        state_before = (self.loop_dir / "state.json").read_bytes()
        ledger_before = (self.loop_dir / "ledger.jsonl").read_bytes()
        self.write_baseline_ok()
        text = self.baseline_text()
        json.loads(text)
        positions = [text.index(name) for name in ("alpha.py::x", "mike.py::x", "zulu.py::x")]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual((self.loop_dir / "state.json").read_bytes(), state_before)
        self.assertEqual((self.loop_dir / "ledger.jsonl").read_bytes(), ledger_before)

        self.set_sensor(reading(1, ["alpha.py::x"]))
        self.write_baseline_ok()
        self.assertNotIn("zulu.py::x", self.baseline_text())

        good = self.baseline_text()
        self.set_sensor("garbage")
        code, _out, err = self.call_runner(looprunner.write_baseline)
        self.assertEqual(code, 1)
        self.assertTrue(err.strip())
        self.assertEqual(self.baseline_text(), good)

        self.set_sensor(reading(0, []))
        self.write_baseline_ok()
        json.loads(self.baseline_text())
        self.assertNotIn("alpha.py::x", self.baseline_text())

    def test_check_lists_new_and_fixed_items_and_blocks_only_on_new(self):
        """Adversarial where: check exits 1 without --blocking, blocks on a
        fixed item or on a clean run, reports a baseline item as new, or
        rewrites the baseline when an item is fixed."""
        self.new_loop(sensor=reading(2, ["alpha.py::x", "bravo.py::x"]))
        self.write_baseline_ok()
        baseline = self.baseline_text()

        rows = [
            ("one new item", ["alpha.py::x", "bravo.py::x", "charlie.py::x"],
             ["charlie.py::x"], ["alpha.py::x", "bravo.py::x"], 0, 1),
            ("one fixed item", ["alpha.py::x"], ["bravo.py::x"], ["alpha.py::x"], 0, 0),
            ("new and fixed", ["alpha.py::x", "delta.py::x"],
             ["delta.py::x", "bravo.py::x"], ["alpha.py::x"], 0, 1),
            ("unchanged", ["alpha.py::x", "bravo.py::x"], [], [], 0, 0),
        ]
        for name, current, listed, unlisted, advisory_code, blocking_code in rows:
            with self.subTest(name=name):
                self.set_sensor(reading(len(current), current))
                code, out, _err = self.call_runner(looprunner.check, False)
                self.assertEqual(code, advisory_code)
                for item in listed:
                    self.assertIn(item, out)
                for item in unlisted:
                    self.assertNotIn(item, out)
                code, _out, _err = self.call_runner(looprunner.check, True)
                self.assertEqual(code, blocking_code)
                self.assertEqual(self.baseline_text(), baseline)

        with self.subTest(name="invalid reading"):
            self.set_sensor("garbage")
            for blocking in (False, True):
                code, _out, err = self.call_runner(looprunner.check, blocking)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip())
            self.assertEqual(self.baseline_text(), baseline)


if __name__ == "__main__":
    unittest.main()
