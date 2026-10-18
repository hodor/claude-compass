"""Adversarial tests for `looplib` aimed at the failure modes its own code
introduces: file encodings a Windows editor writes, JSON that parses but is
nonsense for a cap, ledger and lock files left in odd shapes by a crash,
hand-edited ledger rows, and writes that fail halfway.

These sit beside `test_looplib.py`, which pins the public contract; nothing
here restates it.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import looplib  # noqa: E402

BOM = b"\xef\xbb\xbf"

DEFINITION = {
    "sensor_command": "python sense.py",
    "sensor_timeout_s": 41,
    "target": 3,
    "direction": "down",
    "controller": "first",
    "model": "haiku",
    "max_turns": 7,
    "max_budget_usd": 0.37,
    "timeout_s": 523,
    "allowed_tools": ["Read", "Edit"],
    "daily_budget_usd": 1.9,
    "total_budget_usd": 8.3,
    "wip_limit": 4,
    "max_actuator_failures": 4,
    "max_harmful_runs": 3,
    "max_runs_without_help": 8,
}

NOW = 1_800_000_000.0


class LoopDirTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.loop_dir = self.root / "LOOP-001-demo"
        self.loop_dir.mkdir()
        self.lock_path = self.root / "tmp" / "loops" / "LOOP-001.lock"

    def put(self, name, data):
        (self.loop_dir / name).write_bytes(data)


class TestDefinitionParsing(LoopDirTestCase):
    def test_loop_json_with_a_byte_order_mark_loads(self):
        """Adversarial where: a loop.json saved by a Windows editor starts
        with a UTF-8 BOM and the strict utf-8 read hands json.loads a leading
        U+FEFF, so a valid definition is rejected as unparseable."""
        self.put("loop.json", BOM + json.dumps(DEFINITION).encode("utf-8"))
        self.assertEqual(looplib.load_definition(self.loop_dir), DEFINITION)

    def test_duplicate_keys_do_not_silently_pick_the_last(self):
        """Adversarial where: a loop.json that repeats `max_budget_usd`
        parses with the last value winning, so a cap the human tightened at
        the top of the file is silently overridden further down."""
        text = json.dumps(DEFINITION)[:-1] + ', "max_budget_usd": 99999}'
        self.put("loop.json", text.encode("utf-8"))
        with self.assertRaises(looplib.DefinitionError) as ctx:
            looplib.load_definition(self.loop_dir)
        self.assertIn("max_budget_usd", str(ctx.exception))

    def test_numbers_that_json_accepts_but_a_cap_cannot_hold(self):
        """Adversarial where: a value Python's json module parses (NaN,
        Infinity, an overflowing exponent, a 400-digit integer, a boolean, a
        numeric string) reaches the numeric check and either passes as a cap
        or escapes as a non-DefinitionError exception such as OverflowError."""
        huge_int = "1" + "0" * 400
        rows = [
            ("NaN cap", "max_budget_usd", "NaN"),
            ("Infinity cap", "daily_budget_usd", "Infinity"),
            ("negative Infinity cap", "total_budget_usd", "-Infinity"),
            ("overflowing exponent", "timeout_s", "1e999"),
            ("400-digit integer cap", "max_budget_usd", huge_int),
            ("400-digit integer target", "target", huge_int),
            ("true as a number cap", "daily_budget_usd", "true"),
            ("false as a number cap", "sensor_timeout_s", "false"),
            ("true as an integer cap", "max_turns", "true"),
            ("string for a number", "total_budget_usd", '"5"'),
            ("string for an integer", "wip_limit", '"3"'),
            ("null for a number", "timeout_s", "null"),
            ("float for an integer", "max_harmful_runs", "2.5"),
        ]
        for name, key, literal in rows:
            with self.subTest(name=name):
                fields = {k: json.dumps(v) for k, v in DEFINITION.items()}
                fields[key] = literal
                body = "{" + ", ".join(f'"{k}": {v}' for k, v in fields.items()) + "}"
                self.put("loop.json", body.encode("utf-8"))
                with self.assertRaises(looplib.DefinitionError) as ctx:
                    looplib.load_definition(self.loop_dir)
                self.assertIn(key, str(ctx.exception))


class TestStateFile(LoopDirTestCase):
    def test_state_json_with_a_byte_order_mark_reads(self):
        """Adversarial where: a state.json rewritten by a Windows editor with
        a UTF-8 BOM makes read_state raise StateError and strands the loop."""
        self.put("state.json", BOM + b'{"state": "paused"}')
        self.assertEqual(looplib.read_state(self.loop_dir)["state"], "paused")

    def test_unhashable_state_value_is_a_state_error(self):
        """Adversarial where: a state.json whose `state` is a list or object
        is looked up in a frozenset, raising TypeError (unhashable) instead
        of the StateError every other bad state gets."""
        for name, raw in [
            ("list", '{"state": ["idle"]}'),
            ("object", '{"state": {"a": 1}}'),
            ("null", '{"state": null}'),
            ("number", '{"state": 3}'),
        ]:
            with self.subTest(name=name):
                self.put("state.json", raw.encode("utf-8"))
                with self.assertRaises(looplib.StateError):
                    looplib.read_state(self.loop_dir)

    def test_empty_or_truncated_state_file_is_a_state_error(self):
        """Adversarial where: a zero-byte or half-written state.json parses
        as something other than an error and is treated as a valid state."""
        for name, raw in [("empty", b""), ("truncated", b'{"state": "idl')]:
            with self.subTest(name=name):
                self.put("state.json", raw)
                with self.assertRaises(looplib.StateError):
                    looplib.read_state(self.loop_dir)

    def test_advance_leaves_state_unchanged_when_the_ledger_cannot_be_written(
        self,
    ):
        """Adversarial where: advance writes state.json first and then the
        ledger append fails, leaving the loop in a new state with no ledger
        row to explain how it got there."""
        looplib.write_state(self.loop_dir, {"state": "idle"})
        (self.loop_dir / "ledger.jsonl").mkdir()
        with self.assertRaises(OSError):
            looplib.advance(self.loop_dir, "start", "go")
        self.assertEqual(looplib.read_state(self.loop_dir)["state"], "idle")

    def test_reader_never_sees_a_torn_state_file_during_writes(self):
        """Adversarial where: read_state runs while another thread rewrites
        state.json; on Windows os.replace can be refused while a reader holds
        the file open and the direct-write fallback exposes an empty or
        half-written file, surfacing as a spurious StateError."""
        looplib.write_state(self.loop_dir, {"state": "idle", "pad": "x" * 50000})
        stop = threading.Event()
        failures = []

        def reader():
            while not stop.is_set():
                try:
                    looplib.read_state(self.loop_dir)
                except looplib.StateError as exc:
                    failures.append(str(exc))
                    return

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for i in range(300):
                state = "idle" if i % 2 else "paused"
                looplib.write_state(self.loop_dir, {"state": state, "pad": "x" * 50000})
        finally:
            stop.set()
            thread.join()
        self.assertEqual(failures, [])


class TestLedgerReading(LoopDirTestCase):
    def test_first_row_of_a_ledger_with_a_byte_order_mark_is_not_lost(self):
        """Adversarial where: a ledger saved with a BOM has its first row
        skipped as unparseable, silently dropping a run from every counter."""
        self.put("ledger.jsonl", BOM + b'{"type": "run", "run_id": "a"}\n')
        rows, skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual((len(rows), skipped), (1, []))

    def test_ledger_line_shapes_that_arrive_from_other_tools(self):
        """Adversarial where: CRLF endings, a raw U+2028 inside a reason, a
        blank line between rows or a missing final newline make the line
        splitter drop, merge or mangle a row."""
        rows = [
            ("CRLF endings", b'{"n": 1}\r\n{"n": 2}\r\n', [1, 2]),
            (
                "raw U+2028 in a reason",
                '{"n": 1, "reason": "a b"}\n{"n": 2}\n'.encode(),
                [1, 2],
            ),
            (
                "raw U+0085 in a reason",
                '{"n": 1, "reason": "a\u0085b"}\n{"n": 2}\n'.encode(),
                [1, 2],
            ),
            ("blank lines between rows", b'{"n": 1}\n\n   \n{"n": 2}\n', [1, 2]),
            ("no final newline", b'{"n": 1}\n{"n": 2}', [1, 2]),
        ]
        for name, raw, expected in rows:
            with self.subTest(name=name):
                self.put("ledger.jsonl", raw)
                parsed, skipped = looplib.read_ledger(self.loop_dir)
                self.assertEqual([r["n"] for r in parsed], expected)
                self.assertEqual(skipped, [])

    def test_trailing_partial_line_is_skipped_and_reported_with_its_number(self):
        """Adversarial where: a crash mid-append leaves a truncated last line
        that is either fatal or reported with the wrong line number."""
        self.put("ledger.jsonl", b'{"n": 1}\n{"n": 2}\n{"n": 3, "reaso')
        parsed, skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual([r["n"] for r in parsed], [1, 2])
        self.assertEqual(skipped, [{"line": 3, "text": '{"n": 3, "reaso'}])

    def test_append_after_a_partial_line_keeps_the_new_row(self):
        """Adversarial where: a crash leaves a last line with no newline and
        the next append glues its row onto that fragment, so the new row is
        lost together with the fragment."""
        self.put("ledger.jsonl", b'{"n": 1}\n{"n": 2, "reaso')
        looplib.append_ledger(self.loop_dir, {"n": 3})
        parsed, _skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual([r["n"] for r in parsed], [1, 3])

    def test_concurrent_appends_each_land_as_their_own_line(self):
        """Adversarial where: appenders racing on one ledger interleave
        bytes inside a line, producing unparseable rows."""

        def worker(tag):
            for i in range(40):
                looplib.append_ledger(self.loop_dir, {"tag": tag, "i": i})

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        parsed, skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual((len(parsed), skipped), (240, []))

    def test_appends_from_separate_processes_each_land_as_their_own_line(self):
        """Adversarial where: an in-process lock serialises threads but not
        processes, so appenders in different processes (a run and a human's
        review) overwrite or interleave each other's rows on a platform whose
        append is not atomic."""
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); import looplib; "
            "[looplib.append_ledger(sys.argv[2], {'tag': int(sys.argv[3]), 'i': i}) "
            "for i in range(50)]"
        )
        cli_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", script, cli_dir, str(self.loop_dir), str(t)]
            )
            for t in range(4)
        ]
        self.assertEqual([p.wait(timeout=120) for p in procs], [0, 0, 0, 0])
        parsed, skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual((len(parsed), skipped), (200, []))
        self.assertEqual(
            sorted((r["tag"], r["i"]) for r in parsed),
            [(t, i) for t in range(4) for i in range(50)],
        )


def run(run_id, outcome, item=None):
    return {"type": "run", "run_id": run_id, "outcome": outcome, "item": item}


def resume():
    return {"type": "transition", "event": "resume"}


class TestFoldOnOddLedgers(unittest.TestCase):
    def test_resume_between_two_harmful_runs_restarts_the_streak(self):
        """Adversarial where: a resume row between two harmful runs does not
        reset the streak, so the loop halts again at once on its first run
        after the human resumed it."""
        counters = looplib.fold([run("a", "harmful"), resume(), run("b", "harmful")])
        self.assertEqual(counters["consecutive_harmful"], 1)

    def test_resume_zeroes_streaks_but_keeps_unreviewed_increments(self):
        """Adversarial where: a resume clears WIP along with the counters,
        releasing the gate while increments still await review."""
        counters = looplib.fold(
            [run("a", "harmful", "x"), run("b", "failed"), resume()]
        )
        self.assertEqual(
            (
                counters["wip"],
                counters["held_items"],
                counters["consecutive_failures"],
                counters["consecutive_harmful"],
                counters["runs_without_help"],
            ),
            (1, ["x"], 0, 0, 0),
        )

    def test_reviews_naming_unknown_or_repeated_runs_change_nothing_else(self):
        """Adversarial where: a review for a run id that never ran, or a
        second review of the same run, releases a different increment or
        drives a count negative."""
        review = lambda rid: {"type": "review", "run_id": rid}  # noqa: E731
        counters = looplib.fold(
            [
                run("a", "helpful", "x"),
                run("b", "neutral", "y"),
                review("ghost"),
                review("a"),
                review("a"),
            ]
        )
        self.assertEqual((counters["wip"], counters["held_items"]), (1, ["y"]))

    def test_rows_with_wrong_field_types_do_not_crash_the_fold(self):
        """Adversarial where: a hand-edited ledger row whose run_id, outcome
        or item is a list or number parses as JSON but makes fold raise
        TypeError (unhashable value or str/int comparison), taking the gate
        down on a file the reader promised never to be fatal on."""
        rows = [
            (
                "list run_id on a review",
                [run("a", "helpful", "x"), {"type": "review", "run_id": ["a"]}],
            ),
            ("list outcome", [run("a", ["helpful"], "x")]),
            ("list run_id on a run", [run(["a"], "helpful", "x")]),
            (
                "mixed item types",
                [run("a", "helpful", 7), run("b", "helpful", "x")],
            ),
            ("list item", [run("a", "helpful", ["x"]), run("b", "neutral", "y")]),
        ]
        for name, ledger in rows:
            with self.subTest(name=name):
                counters = looplib.fold(ledger)
                self.assertIn("wip", counters)


class TestLockFiles(LoopDirTestCase):
    def test_lock_files_that_hold_nonsense_are_aged_not_held_forever(self):
        """Adversarial where: a lock holding NaN, Infinity, a string, null or
        a far-future start compares False (or raises TypeError) against the
        age limit, so it is never stale and the loop is locked out for good
        after a crash."""
        timeout_s = 523
        long_ago = NOW - 10 * (timeout_s + looplib.LOCK_GRACE_SECONDS)
        rows = [
            ("NaN start", b'{"pid": 1, "started": NaN}'),
            ("Infinity start", b'{"pid": 1, "started": Infinity}'),
            ("string start", b'{"pid": 1, "started": "yesterday"}'),
            ("null start", b'{"pid": 1, "started": null}'),
            ("start ten years ahead", b'{"pid": 1, "started": 2115000000}'),
        ]
        for name, raw in rows:
            with self.subTest(name=name):
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                self.lock_path.write_bytes(raw)
                os.utime(self.lock_path, (long_ago, long_ago))
                self.assertTrue(looplib.is_stale(self.lock_path, timeout_s, NOW))

    def test_empty_or_corrupt_lock_ages_by_modification_time(self):
        """Adversarial where: a lock left empty (crash between create and
        write) or corrupt is judged stale at once, freeing a live run's
        lock, or is never judged stale at all."""
        timeout_s = 523
        limit = timeout_s + looplib.LOCK_GRACE_SECONDS
        rows = [("empty", b""), ("garbage", b"\x00\xffnot json"), ("array", b"[1, 2]")]
        for name, raw in rows:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self.lock_path.write_bytes(raw)
            with self.subTest(name=name, age="just inside the limit"):
                os.utime(self.lock_path, (NOW - limit + 5, NOW - limit + 5))
                self.assertFalse(looplib.is_stale(self.lock_path, timeout_s, NOW))
            with self.subTest(name=name, age="just past the limit"):
                os.utime(self.lock_path, (NOW - limit - 5, NOW - limit - 5))
                self.assertTrue(looplib.is_stale(self.lock_path, timeout_s, NOW))

    def test_lock_started_a_minute_in_the_future_is_live(self):
        """Adversarial where: mild clock skew puts a lock's start slightly
        ahead of now and the age arithmetic reads it as abandoned."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(
            json.dumps({"pid": os.getpid(), "started": NOW + 60}), encoding="utf-8"
        )
        self.assertFalse(looplib.is_stale(self.lock_path, 523, NOW))

    def test_recover_with_a_corrupt_live_lock_refuses_and_changes_nothing(self):
        """Adversarial where: recover meets a fresh, unreadable lock and
        either crashes with a non-LockHeld error or writes a crashed row."""
        looplib.write_state(
            self.loop_dir, {"state": "actuating", "run_id": "r1", "item": "x"}
        )
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_bytes(b"")
        before = looplib.read_state(self.loop_dir)
        with self.assertRaises(looplib.LockHeld):
            looplib.recover(self.loop_dir, self.lock_path, DEFINITION, time.time())
        self.assertEqual(looplib.read_state(self.loop_dir), before)
        self.assertEqual(looplib.read_ledger(self.loop_dir), ([], []))

    def test_failed_recovery_retried_charges_the_crashed_run_once(self):
        """Adversarial where: recover appends the crashed run row, then fails
        before the state returns to idle; the retry appends a second crashed
        row for the same run and the budget sums charge it twice."""
        looplib.write_state(
            self.loop_dir, {"state": "actuating", "run_id": "r1", "item": "x"}
        )
        real = looplib.write_state
        calls = []

        def flaky(loop_dir, state_dict):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("disk full")
            real(loop_dir, state_dict)

        with mock.patch.object(looplib, "write_state", flaky):
            with self.assertRaises(OSError):
                looplib.recover(self.loop_dir, self.lock_path, DEFINITION, NOW)
            self.assertTrue(
                looplib.recover(self.loop_dir, self.lock_path, DEFINITION, NOW)
            )
        crashed = [
            r
            for r in looplib.read_ledger(self.loop_dir)[0]
            if r.get("type") == "run" and r.get("run_id") == "r1"
        ]
        self.assertEqual(len(crashed), 1)

    def test_recover_does_not_touch_a_lock_when_the_state_is_resting(self):
        """Adversarial where: recover on a resting loop removes a lock that
        belongs to a run the other process is still starting."""
        looplib.write_state(self.loop_dir, {"state": "idle"})
        looplib.acquire_lock(self.lock_path, 523, NOW)
        self.assertFalse(
            looplib.recover(self.loop_dir, self.lock_path, DEFINITION, NOW)
        )
        self.assertTrue(self.lock_path.exists())


if __name__ == "__main__":
    unittest.main()
