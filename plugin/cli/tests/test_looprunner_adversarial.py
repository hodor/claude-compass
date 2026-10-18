"""Adversarial tests for `looprunner` aimed at defects only the finished
implementation can reveal: how the actuator's raw output is decoded and
bounded, what a run does when the loop folder changes underneath it, two
processes racing for one loop, the UTC day line, zero-valued caps, console
encodings, odd paths, and an interrupt in the middle of actuation.

The contract under test is the one in `test_looprunner.py`; this file reuses
its harness and adds a stub actuator whose behavior is a snippet of Python
carried in the plan file.
"""

import base64
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import looplib  # noqa: E402
import test_looprunner as base  # noqa: E402

looprunner = base.looprunner

CODE_STUB_BODY = textwrap.dedent(
    r"""
    import base64
    import json
    import os
    import sys
    import time

    stdin_bytes = sys.stdin.buffer.read()
    with open(os.environ["STUB_PLAN"], encoding="utf-8") as fh:
        plan = json.load(fh)
    calls = os.environ["STUB_CALLS"]
    os.makedirs(calls, exist_ok=True)
    n = 0
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
    if plan.get("set_reading") is not None:
        with open(plan["reading_file"], "w", encoding="utf-8", newline="") as fh:
            fh.write(plan["set_reading"])
    with open(plan["result_file"], "rb") as fh:
        envelope = fh.read()
    exec(compile(plan["code"], "stub-code", "exec"))
    """
)

# Runs one real iteration in a fresh interpreter and exits with its code.
RUNNER_CHILD = textwrap.dedent(
    r"""
    import sys
    from datetime import datetime
    from pathlib import Path

    sys.path.insert(0, sys.argv[1])
    import looprunner

    sys.exit(looprunner.run_iteration(Path(sys.argv[2]), False))
    """
)

# As RUNNER_CHILD, but delivers a KeyboardInterrupt to the main thread once
# the file named by argv[3] has bytes in it (the actuator's child is alive).
INTERRUPT_CHILD = textwrap.dedent(
    r"""
    import _thread
    import os
    import sys
    import threading
    import time
    from pathlib import Path

    sys.path.insert(0, sys.argv[1])
    import looprunner

    heartbeat = sys.argv[3]

    def interrupter():
        for _ in range(300):
            if os.path.exists(heartbeat) and os.path.getsize(heartbeat) > 0:
                break
            time.sleep(0.1)
        time.sleep(0.5)
        _thread.interrupt_main()

    threading.Thread(target=interrupter, daemon=True).start()
    try:
        code = looprunner.run_iteration(Path(sys.argv[2]), False)
    except KeyboardInterrupt:
        print("INTERRUPTED")
        sys.exit(130)
    sys.exit(code)
    """
)


def make_code_stub(tmp):
    body = tmp / "code_stub_body.py"
    body.write_text(CODE_STUB_BODY, encoding="utf-8")
    if sys.platform == "win32":
        launcher = tmp / "code_stub.bat"
        launcher.write_text(
            '@echo off\r\n"' + sys.executable + '" "' + str(body) + '" %*\r\n',
            encoding="utf-8",
        )
    else:
        launcher = tmp / "code_stub.sh"
        launcher.write_text(
            '#!/bin/sh\nexec "' + sys.executable + '" "' + str(body) + '" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    return launcher


def emit(text):
    """Stub code that writes the real success envelope after `text` ran."""
    return textwrap.dedent(text) + "\nsys.stdout.buffer.write(envelope)\n"


class AdvHarness(base.RunnerHarness):
    def setUp(self):
        super().setUp()
        self.code_stub = make_code_stub(self.base / "tools")

    def set_code_stub(self, code, **extra):
        """Replace the actuator with a stub running `code` (Python source with
        `envelope`, `plan`, `stdin_bytes`, `sys`, `os`, `time` in scope)."""
        plan = {
            "reading_file": str(self.reading_file),
            "lock_path": str(self.lock),
            "result_file": str(base.R2_SUCCESS),
            "set_reading": base.reading(5, base.ITEMS[:2]),
            "code": textwrap.dedent(code),
            **extra,
        }
        self.plan_file.write_text(json.dumps(plan), encoding="utf-8")
        os.environ["COMPASS_CLAUDE_BIN"] = str(self.code_stub)

    def spawn(self, script, *args):
        script_path = self.base / "tools" / ("child_%d.py" % len(list((self.base / "tools").glob("child_*.py"))))
        script_path.write_text(script, encoding="utf-8")
        return subprocess.Popen(
            [sys.executable, str(script_path), CLI_DIR, str(self.loop_dir), *map(str, args)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def wait_for_call(self, count=1, timeout=40):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.calls()) >= count:
                return
            time.sleep(0.05)
        self.fail("the actuator stub was never started")


class ActuatorOutputTests(AdvHarness):
    def test_oversized_and_undecodable_actuator_output_rows(self):
        """Adversarial where: a multi-megabyte stdout or stderr deadlocks the
        pipe reader or is truncated before the envelope is parsed, bytes that
        are not UTF-8 crash the decoder (or the console print of the failure
        reason) instead of costing the run, or a garbage flood is mistaken for
        a result."""
        big = 16 * 1024 * 1024
        rows = [
            ("16 MB result string in a valid envelope", """
                import json
                data = json.loads(envelope)
                data["result"] = "x" * %d
                sys.stdout.write(json.dumps(data))
             """ % big, "helpful", 0.0463805),
            ("16 MB on stderr beside a valid envelope", """
                sys.stderr.write("e" * %d)
                sys.stderr.flush()
                sys.stdout.buffer.write(envelope)
             """ % big, "helpful", 0.0463805),
            ("raw 0xFF bytes inside the result string", """
                sys.stdout.buffer.write(envelope.replace(b'"result":"', b'"result":"\\xff\\xfe', 1))
             """, "helpful", 0.0463805),
            ("non-UTF-8 flood and no envelope", """
                sys.stdout.buffer.write(b"\\xff\\xfe\\x80" * 1000)
             """, "failed", 2.75),
            ("16 MB of text and no envelope", """
                sys.stdout.write("garbage line\\n" * %d)
             """ % (big // 13), "failed", 2.75),
        ]
        for name, code, outcome, cost in rows:
            with self.subTest(name=name):
                self.new_loop()
                self.set_code_stub(code)
                started = time.monotonic()
                code_, _out, err = self.iterate()
                self.assertLess(time.monotonic() - started, 60)
                self.assertNotIn("Traceback", err)
                self.assertEqual(code_, 0)
                (row,) = self.run_rows()
                self.assertEqual(row["outcome"], outcome)
                self.assertEqual(row["cost_usd"], cost)
                self.assertEqual(self.state(), "idle")
                self.assert_no_lock()

    def test_error_envelope_with_success_subtype_is_a_failed_run(self):
        """Adversarial where: the runner reads `subtype` alone, so an
        envelope that says `is_error: true` beside `subtype: success` is
        judged on a re-sense as a verified run (and may be counted helpful)
        while the actuator reported an error. Its real cost must still be
        kept, and three of them must trip the failure limit."""
        self.new_loop(sensor=base.reading(10))
        envelope = json.loads(base.R2_SUCCESS.read_text(encoding="utf-8"))
        envelope.update(is_error=True, subtype="success")
        self.set_code_stub("sys.stdout.write(%r)" % json.dumps(envelope))
        for _ in range(3):
            self.set_sensor(base.reading(10))
            self.iterate()
        rows = self.run_rows()
        self.assertEqual([r["outcome"] for r in rows], ["failed"] * 3)
        self.assertEqual([r["cost_usd"] for r in rows], [0.0463805] * 3)
        self.assertIsNone(rows[0]["reading_after"])
        self.assertEqual(self.state(), "halted")
        self.assertEqual(self.events()[-1], "failed-limit")


class LoopFolderMutationTests(AdvHarness):
    def test_actuator_deleting_uncontrolled_loop_files_leaves_a_runnable_loop(self):
        """Adversarial where: an actuator removes files outside the four
        hashed control files (the golden patterns, feedback.md), so the next
        prompt assembly raises on the missing path, the run is halted as a
        tamper although none of the hashed files changed, or the cost of the
        run is lost. A removed actuator.md or index.md must make the next run
        a clean refusal, never a traceback or a stranded lock."""
        loop = "str(plan['loop_dir'])"
        rows = [
            ("golden folder removed", "shutil.rmtree(%s + '/golden')" % loop, 0, True),
            ("feedback.md removed", "os.remove(%s + '/feedback.md')" % loop, 0, True),
            ("actuator.md removed", "os.remove(%s + '/actuator.md')" % loop, 1, False),
            ("index.md removed", "os.remove(%s + '/index.md')" % loop, 1, False),
        ]
        for name, action, second_code, second_launches in rows:
            with self.subTest(name=name):
                self.new_loop()
                self.set_code_stub("import shutil\n" + action + "\nsys.stdout.buffer.write(envelope)",
                                   loop_dir=str(self.loop_dir))
                code, _out, err = self.iterate()
                self.assertEqual((code, self.state()), (0, "idle"), err)
                (row,) = self.run_rows()
                self.assertEqual(row["outcome"], "helpful")
                self.assertEqual(row["cost_usd"], 0.0463805)
                self.assert_no_lock()
                self.set_sensor(base.reading(10))
                self.set_code_stub("sys.stdout.buffer.write(envelope)", loop_dir=str(self.loop_dir))
                code, _out, err = self.iterate()
                self.assertNotIn("Traceback", err)
                self.assertEqual(code, second_code, err)
                self.assertEqual(len(self.calls()), 2 if second_launches else 1)
                self.assert_no_lock()
                if second_launches:
                    prompt = self.stdin_of(self.calls()[-1]).decode("utf-8")
                    self.assertIn("ACTUATOR-MARKER-ONE", prompt)
                    self.assertNotIn("FEEDBACK-MARKER-ONE" if "feedback" in name else "GOLDEN-MARKER-A", prompt)

    def test_loop_folder_removed_mid_run_ends_in_a_message_not_a_traceback(self):
        """Adversarial where: the whole loop folder disappears while the
        actuator runs, so the record step raises out of the runner as a
        traceback or leaves the run lock behind."""
        self.new_loop()
        self.set_code_stub("import shutil\nshutil.rmtree(plan['loop_dir'])\nsys.stdout.buffer.write(envelope)",
                           loop_dir=str(self.loop_dir))
        code, _out, err = self.iterate()
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertTrue(err.strip())
        self.assert_no_lock()


class FlakySensorTests(AdvHarness):
    def test_sensor_that_fails_on_the_second_read_ends_the_run_cleanly(self):
        """Adversarial where: a sensor that reads fine before the actuator and
        fails after it (a timeout, garbage) crashes the runner mid-verify,
        loses the actuator's real cost, or lets the next run spend on an
        unreadable sensor."""
        rows = [
            ("garbage second read", {"set_reading": "garbage"}, {}),
            ("second read times out", {"set_reading": "SLEEP 30\n"}, {"sensor_timeout_s": 3}),
        ]
        for name, spec, definition in rows:
            with self.subTest(name=name):
                self.new_loop(definition=definition, stub=spec)
                code, _out, err = self.iterate()
                self.assertEqual(code, 0, err)
                (row,) = self.run_rows()
                self.assertEqual(row["cost_usd"], 0.0463805)
                self.assertIsNone(row["reading_after"])
                self.assertEqual(self.state(), "idle")
                self.assert_no_lock()
                spent_calls = len(self.calls())
                self.iterate()
                self.assertEqual(self.state(), "halted")
                self.assertEqual(len(self.calls()), spent_calls)
                self.assertEqual(self.events()[-1], "invalid-reading")

    def test_sensor_that_flaps_after_every_run_still_trips_the_no_progress_limit(self):
        """Adversarial where: a run whose re-sense is unreadable is recorded
        as verified-neutral but the ending skips the no-progress check, so a
        sensor that reads fine before and fails after each run keeps the loop
        idle and spending until the lifetime budget instead of halting after
        `max_runs_without_help` verified runs with no help."""
        self.new_loop(definition={"max_runs_without_help": 2}, stub={"set_reading": "garbage"})
        for _ in range(3):
            self.set_sensor(base.reading(10))
            self.iterate()
        self.assertEqual(self.state(), "halted", "state after 3 unhelpful runs with limit 2")
        self.assertEqual(self.events()[-1], "no-progress-limit")


class ConcurrencyTests(AdvHarness):
    def test_two_processes_on_one_loop_run_exactly_once(self):
        """Adversarial where: both processes pass the recovery or lock step
        and launch the actuator twice, both record the crash of the same
        dead run, or the loser deletes the winner's lock and strands the
        state. Rows: an idle loop, and a crash-left loop with a stale lock."""
        stale = '{"pid": 1, "started": 1000.0}'
        rows = [
            ("idle loop", dict(), None, 0),
            ("crash-left loop with a stale lock", dict(state={"state": "actuating", "run_id": "RUN-dead"}),
             stale, 1),
        ]
        for name, kwargs, lock_text, crashes in rows:
            with self.subTest(name=name):
                self.new_loop(**kwargs)
                if lock_text is not None:
                    self.lock.parent.mkdir(parents=True, exist_ok=True)
                    self.lock.write_text(lock_text, encoding="utf-8")
                self.set_code_stub("time.sleep(4)\nsys.stdout.buffer.write(envelope)")
                first = self.spawn(RUNNER_CHILD)
                second = self.spawn(RUNNER_CHILD)
                results = []
                for proc in (first, second):
                    out, err = proc.communicate(timeout=90)
                    results.append((proc.returncode, err.decode("utf-8", "replace")))
                self.assertEqual(sorted(code for code, _ in results), [0, 1], results)
                for code, err in results:
                    self.assertNotIn("Traceback", err)
                self.assertEqual(len(self.calls()), 1)
                outcomes = sorted(r["outcome"] for r in self.run_rows())
                self.assertEqual(outcomes, sorted(["helpful"] + ["crashed"] * crashes))
                self.assertEqual(self.state(), "idle")
                self.assert_no_lock()

    def test_dry_run_beside_a_live_run_leaves_it_undisturbed(self):
        """Adversarial where: a dry run, which takes no lock, recovers the
        live run's working state as a crash, deletes or rewrites its lock,
        moves its state file, or appends to its ledger, so the real run
        later fails or double-records."""
        self.new_loop()
        self.set_code_stub("time.sleep(6)\nsys.stdout.buffer.write(envelope)")
        real = self.spawn(RUNNER_CHILD)
        try:
            self.wait_for_call()
            lock_before = self.lock.read_bytes()
            state_before = (self.loop_dir / "state.json").read_bytes()
            ledger_before = (self.loop_dir / "ledger.jsonl").read_bytes()
            scratch_before = base.files_under(self.root / "tmp" / "loops")
            for _ in range(2):
                code, out, err = self.iterate(dry_run=True)
                self.assertEqual(code, 0, err)
                self.assertIn("ACTUATOR-MARKER-ONE", out)
            self.assertEqual(self.lock.read_bytes(), lock_before)
            self.assertEqual((self.loop_dir / "state.json").read_bytes(), state_before)
            self.assertEqual((self.loop_dir / "ledger.jsonl").read_bytes(), ledger_before)
            self.assertEqual(base.files_under(self.root / "tmp" / "loops"), scratch_before)
        finally:
            _out, err = real.communicate(timeout=90)
        self.assertEqual(real.returncode, 0, err.decode("utf-8", "replace"))
        (row,) = self.run_rows()
        self.assertEqual(row["outcome"], "helpful")
        self.assertEqual(self.state(), "idle")
        self.assertNotIn("error", [r.get("type") for r in self.ledger()])
        self.assert_no_lock()


class UtcDayLineTests(AdvHarness):
    def test_runs_either_side_of_midnight_utc_count_against_their_own_day(self):
        """Adversarial where: the day of a run is taken from the local clock
        or the wrong offset, a run started at 23:59:59 UTC is charged to the
        next day, the daily budget is off by one on the boundary (daily equal
        to the run budget must still admit one run), or a non-UTC `now` such
        as 01:59:59+02:00 is treated as a new day when it is still the old
        one in UTC."""
        plus2 = timezone(timedelta(hours=2))
        last_second = datetime(2026, 10, 18, 23, 59, 59, tzinfo=timezone.utc)
        steps = [
            ("run at 23:59:59 UTC fills the day", last_second, "helpful"),
            ("same instant again is throttled", last_second, "throttled"),
            ("01:59:59+02:00 is still the old UTC day", datetime(2026, 10, 19, 1, 59, 59, tzinfo=plus2),
             "throttled"),
            ("naive 23:59:59 counts as UTC", datetime(2026, 10, 18, 23, 59, 59), "throttled"),
            ("02:00:00+02:00 is the next UTC day", datetime(2026, 10, 19, 2, 0, 0, tzinfo=plus2), "helpful"),
            ("00:00:00 UTC the next day, after one more run, is throttled",
             datetime(2026, 10, 19, 0, 0, 0, tzinfo=timezone.utc), "throttled"),
        ]
        self.new_loop(definition={"daily_budget_usd": 2.75})
        self.set_code_stub("sys.stdout.buffer.write(envelope)")
        for name, now, expected in steps:
            with self.subTest(name=name):
                self.set_sensor(base.reading(10))
                before = len(self.calls())
                self.iterate(now=now)
                row = self.run_rows()[-1]
                self.assertEqual(row["outcome"], expected)
                self.assertEqual(len(self.calls()) - before, 1 if expected == "helpful" else 0)
                if expected == "helpful":
                    self.assertEqual(row["ts"][:10], now.astimezone(timezone.utc).strftime("%Y-%m-%d")
                                     if now.tzinfo else now.strftime("%Y-%m-%d"))


class ZeroBudgetTests(AdvHarness):
    def test_zero_valued_budgets_never_reach_the_actuator(self):
        """Adversarial where: a budget of exactly zero is read as falsy or
        unlimited, so the gate lets a run through (a daily or lifetime cap of
        0 admits a run costing up to the run budget), or a run budget of 0 is
        passed to the CLI, where 0 is not known to mean 'spend nothing'."""
        rows = [
            ("daily budget 0 throttles", {"daily_budget_usd": 0}, "throttled", "daily-budget-spent"),
            ("lifetime budget 0 halts", {"total_budget_usd": 0}, "halted", "total-budget-spent"),
            ("run budget 0 never launches", {"max_budget_usd": 0}, None, None),
        ]
        for name, definition, outcome, event in rows:
            with self.subTest(name=name):
                self.new_loop(definition=definition)
                code, _out, err = self.iterate()
                self.assertNotIn("Traceback", err)
                self.assert_nothing_launched()
                self.assert_no_lock()
                if event is not None:
                    self.assertEqual(self.events()[-1], event)
                    self.assertEqual(self.run_rows()[-1]["outcome"], outcome)
                    self.assertEqual(self.run_rows()[-1]["cost_usd"], 0.0)


class OddPathTests(AdvHarness):
    def setUp(self):
        super().setUp()
        self.project = self.base / "prö jeto ação"
        self.root = self.project / ".compass"
        self.loop_dir = self.root / "loops" / "LOOP-001-açaí e espaço"
        self.lock = self.root / "tmp" / "loops" / "LOOP-001.lock"
        self.scratch_root = self.root / "tmp" / "loops" / "LOOP-001"
        (self.root / "meta").mkdir(parents=True)
        spaced_tools = self.base / "fer ramentas ç"
        spaced_tools.mkdir()
        self.cat = spaced_tools / "cat.py"
        self.cat.write_text(base.CAT_BODY, encoding="utf-8")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)

    def test_full_iteration_under_a_spaced_non_ascii_project_path(self):
        """Adversarial where: the sensor command, the actuator cwd, the scratch
        directory or the child's environment mangles or splits a path holding
        spaces and non-ASCII letters, or a non-ASCII item identity does not
        survive the trip sensor -> prompt (UTF-8 on stdin) -> ledger."""
        item = "ação/módulo ç.py::except-ão"
        self.new_loop(sensor=base.reading(10, [item, "zz.py::b"]))
        self.set_code_stub("sys.stdout.buffer.write(envelope)",
                           set_reading=base.reading(5, ["zz.py::b"]))
        code, _out, err = self.iterate()
        self.assertEqual(code, 0, err)
        (call,) = self.calls()
        self.assertEqual(Path(call["cwd"]).resolve(), self.project.resolve())
        self.assertEqual(Path(call["env"]["CLAUDE_PROJECT_DIR"]).resolve(), self.project.resolve())
        prompt = self.stdin_of(call).decode("utf-8")
        self.assertIn(item, prompt)
        (row,) = self.run_rows()
        self.assertEqual(row["item"], item)
        self.assertEqual(row["outcome"], "helpful")
        saved = list((self.scratch_root).glob("RUN-*/prompt.md"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), self.stdin_of(call))
        self.assertEqual(Path(self.cwd_log.read_text(encoding="utf-8").splitlines()[0]).resolve(),
                         self.project.resolve())
        self.assertEqual(self.call_runner(looprunner.write_baseline)[0], 0)
        _code, out, _err = self.call_runner(looprunner.check)
        self.assertIn("0 new, 0 fixed", out)


class ConsoleEncodingTests(AdvHarness):
    def run_on_console(self, encoding, function, *args, **kwargs):
        """Call `function` with strict-encoding byte streams standing in for
        the console; returns (code, stdout text, stderr text)."""
        out_raw, err_raw = io.BytesIO(), io.BytesIO()
        out = io.TextIOWrapper(out_raw, encoding=encoding, errors="strict", write_through=True)
        err = io.TextIOWrapper(err_raw, encoding=encoding, errors="strict", write_through=True)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = function(*args, **kwargs)
        return (0 if code is None else code), out_raw.getvalue().decode(encoding), \
            err_raw.getvalue().decode(encoding)

    def test_text_the_console_cannot_encode_is_replaced_not_raised(self):
        """Adversarial where: the dry-run prompt, a `check` listing or a halt
        message holding characters outside the console code page (cp1252 and
        ascii here) raises UnicodeEncodeError, so the command dies with a
        traceback after (or before) the work it printed. Rows: the dry-run
        prompt, a new item in `check`, an invalid-reading halt, a real run
        whose item is outside the code page."""
        wide = "日本語 → ✓"
        for encoding in ("cp1252", "ascii"):
            with self.subTest(name="dry-run prompt on " + encoding):
                self.new_loop(sensor=base.reading(10, [wide + ".py::x"]))
                (self.loop_dir / "golden" / "a-first.md").write_text(
                    "GOLDEN-MARKER-A " + wide + "\n", encoding="utf-8")
                code, out, err = self.run_on_console(
                    encoding, looprunner.run_iteration, self.loop_dir, True, now=base.NOW)
                self.assertEqual(code, 0, err)
                self.assertIn("GOLDEN-MARKER-A", out)
                self.assertIn("ACTUATOR-MARKER-ONE", out)
                self.assertNotIn("日本語", out)
            with self.subTest(name="check listing on " + encoding):
                self.new_loop(sensor=base.reading(10, [wide + ".py::x"]))
                (self.loop_dir / "baseline.json").write_text('{"items": []}', encoding="utf-8")
                code, out, err = self.run_on_console(encoding, looprunner.check, self.loop_dir, True)
                self.assertEqual(code, 1, err)
                self.assertIn("1 new, 0 fixed", out)
            with self.subTest(name="invalid reading message on " + encoding):
                self.new_loop(sensor=wide + " not json")
                code, out, err = self.run_on_console(
                    encoding, looprunner.run_iteration, self.loop_dir, False, now=base.NOW)
                self.assertEqual(code, 1, err)
                self.assertEqual(self.state(), "halted")
                self.assert_no_lock()
            with self.subTest(name="real run on " + encoding):
                self.new_loop(sensor=base.reading(10, [wide + ".py::x"]))
                code, out, err = self.run_on_console(
                    encoding, looprunner.run_iteration, self.loop_dir, False, now=base.NOW)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.run_rows()[0]["item"], wide + ".py::x")
                self.assertIn(wide, self.stdin_of(self.calls()[0]).decode("utf-8"))


@unittest.skipUnless(sys.platform == "win32", "a sharing violation on the lock file is a Windows condition")
class SharingLockedLockTests(AdvHarness):
    def hold_exclusively(self, path):
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        ]
        handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value, "could not open the lock exclusively")
        closed = []

        def release():
            if not closed:
                kernel.CloseHandle(handle)
                closed.append(True)

        self.addCleanup(release)
        return release

    def test_lock_another_process_holds_open_is_live_even_when_its_content_is_ancient(self):
        """Adversarial where: a lock file that cannot be read because another
        process has it open without sharing is judged by its (ancient, stale)
        recorded start and taken over from under the live run, or the run
        crashes with the sharing violation. Once the holder lets go, the same
        stale content must be taken over and the run proceeds. Rows: an idle
        loop and a working-state loop, both with the stale-looking content."""
        stale = '{"pid": 1, "started": 1000.0}'
        rows = [
            ("idle loop", dict()),
            ("crash-left working state", dict(state={"state": "actuating", "run_id": "RUN-held"})),
        ]
        for name, kwargs in rows:
            with self.subTest(name=name):
                self.new_loop(**kwargs)
                self.set_code_stub("sys.stdout.buffer.write(envelope)")
                self.lock.parent.mkdir(parents=True, exist_ok=True)
                self.lock.write_text(stale, encoding="utf-8")
                release = self.hold_exclusively(self.lock)
                before = base.files_under(self.loop_dir)
                code, _out, err = self.iterate()
                self.assertEqual(code, 1)
                self.assertNotIn("Traceback", err)
                self.assert_nothing_launched()
                self.assertTrue(self.lock.exists(), "the live run's lock was taken over")
                self.assertEqual(base.files_under(self.loop_dir), before)
                release()
                code, _out, err = self.iterate()
                self.assertEqual(code, 0, err)
                self.assertEqual(len(self.calls()), 1)
                self.assert_no_lock()


class InterruptTests(AdvHarness):
    def test_keyboard_interrupt_during_actuation_kills_the_tree_and_the_next_run_recovers(self):
        """Adversarial where: Ctrl-C while the actuator runs leaves its process
        tree alive and editing the checkout (the child leads its own process
        group, so the terminal's signal never reaches it), strands the run
        lock, or leaves a state the next run cannot recover from. The run was
        interrupted before it could be recorded, so the next run must charge
        it as crashed at the full run budget and then proceed."""
        self.new_loop(stub={"hang": True, "heartbeat": str(self.heartbeat)})
        child = self.spawn(INTERRUPT_CHILD, self.heartbeat)
        out, err = child.communicate(timeout=60)
        text = out.decode("utf-8", "replace")
        self.assertIn("INTERRUPTED", text, err.decode("utf-8", "replace"))
        size = self.heartbeat.stat().st_size
        self.assertGreater(size, 0, "the stub's child never started")
        time.sleep(1.5)
        self.assertEqual(self.heartbeat.stat().st_size, size, "the actuator tree outlived the interrupt")
        self.assert_no_lock()
        self.assertIn(self.state(), looplib.WORKING)
        self.set_code_stub("sys.stdout.buffer.write(envelope)")
        code, _out, err = self.iterate()
        self.assertEqual(code, 0, err)
        crashed = [r for r in self.run_rows() if r.get("outcome") == "crashed"]
        self.assertEqual(len(crashed), 1)
        self.assertEqual(crashed[0]["cost_usd"], 2.75)
        self.assertEqual(self.state(), "idle")
        self.assertEqual(self.run_rows()[-1]["outcome"], "helpful")


if __name__ == "__main__":
    unittest.main()
