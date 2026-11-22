"""Adversarial tests for the `fix-cycle` row `compass test-checkpoint cycle`
appends to `.compass/meta/station-log.jsonl`.

Themes: one row per judged cycle carrying the task, the cycle number and the
verdict; a cycle that fails to judge records nothing; a failing log write
never changes the cycle command's output, exit code or its own cycle log.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import test_checkpoint  # noqa: E402

TEST_FILE = "tests/test_widget.py"


def pytest_lines(*rows):
    return "".join(f"{TEST_FILE}::{node} {status} [ 50%]\n" for node, status in rows)


class CycleStationCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / ".compass").mkdir()
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root)
        self.addCleanup(
            lambda: os.environ.pop("CLAUDE_PROJECT_DIR", None) if old is None
            else os.environ.__setitem__("CLAUDE_PROJECT_DIR", old)
        )
        self.counter = 0

    @property
    def log(self):
        return self.root / ".compass" / "meta" / "station-log.jsonl"

    def rows(self):
        if not self.log.is_file():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def cycle(self, task, data):
        self.counter += 1
        evidence = self.root / f"run{self.counter}.txt"
        evidence.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = test_checkpoint.run(["cycle", task, "--evidence", str(evidence)])
        return code, out.getvalue(), err.getvalue()


class FixCycleRowTests(CycleStationCase):
    def test_each_judged_cycle_appends_a_fix_cycle_row_in_order(self):
        """Adversarial where: the row carries the wrong cycle number (off by
        one against the cycle log, which starts at 0), the wrong verdict, or
        the other task's id when two tasks interleave their cycles."""
        start = pytest_lines(("A::t1", "FAILED"), ("A::t2", "FAILED"))
        better = pytest_lines(("A::t1", "PASSED"), ("A::t2", "FAILED"))
        worse = pytest_lines(("A::t1", "PASSED"), ("A::t2", "FAILED"), ("A::t3", "FAILED"))
        steps = [
            ("TASK-346", start, 0, "neutral"),
            ("TASK-900", start, 0, "neutral"),
            ("TASK-346", better, 1, "helpful"),
            ("TASK-346", worse, 2, "harmful"),
        ]
        for task, data, number, verdict in steps:
            code, out, err = self.cycle(task, data)
            self.assertEqual(code, 0, out + err)
            self.assertIn(f"cycle {number}: {verdict}", out)
        got = [(r["task"], r["cycle"], r["verdict"]) for r in self.rows()]
        self.assertEqual(got, [(t, n, v) for t, _, n, v in steps])
        for row in self.rows():
            self.assertEqual(row["station"], "fix-cycle")

    def test_cycle_that_cannot_be_judged_appends_no_row(self):
        """Adversarial where: an evidence file with no tests (exit 1) or a
        damaged cycle log still appends a fix-cycle row, counting a cycle
        that never ran."""
        code, _, _ = self.cycle("TASK-346", "no test results in here\n")
        self.assertEqual(code, 1, "testless evidence must exit 1")
        self.assertEqual(self.rows(), [])

        self.cycle("TASK-346", pytest_lines(("A::t1", "FAILED")))
        self.assertEqual(len(self.rows()), 1)
        damaged = self.root / ".compass" / "tmp" / "test-checkpoints" / "TASK-346.cycles.jsonl"
        damaged.write_text("{not a cycle record\n", encoding="utf-8")
        code, _, _ = self.cycle("TASK-346", pytest_lines(("A::t1", "PASSED")))
        self.assertEqual(code, 1, "a damaged cycle log must exit 1")
        self.assertEqual([r["cycle"] for r in self.rows()], [0])

    def test_unwritable_station_log_leaves_the_cycle_command_unchanged(self):
        """Adversarial where: the station write fails (the log path is a
        directory) and its exception turns a judged cycle into exit 1, or
        keeps the cycle from being recorded in its own log. The same evidence
        is judged in a clean project and must print the same output."""
        data = pytest_lines(("A::t1", "FAILED"))
        clean_code, clean_out, _ = self.cycle("TASK-346", data)
        clean_cycle_log = (
            self.root / ".compass" / "tmp" / "test-checkpoints" / "TASK-346.cycles.jsonl"
        ).read_text(encoding="utf-8")
        self.assertEqual(clean_code, 0)

        shutil.rmtree(self.root / ".compass")
        (self.root / ".compass").mkdir()
        self.log.mkdir(parents=True)
        code, out, err = self.cycle("TASK-346", data)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out, clean_out)
        cycle_log = (
            self.root / ".compass" / "tmp" / "test-checkpoints" / "TASK-346.cycles.jsonl"
        ).read_text(encoding="utf-8")
        self.assertEqual(len(cycle_log.splitlines()), len(clean_cycle_log.splitlines()))


if __name__ == "__main__":
    unittest.main()
