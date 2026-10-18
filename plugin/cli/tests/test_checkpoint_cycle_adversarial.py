"""Adversarial tests for `compass test-checkpoint cycle`.

The themes are the places the cycle verdict can silently go wrong once real
evidence and real vault state reach it: evidence saved in other encodings,
pytest statuses beyond pass and fail, parametrized ids that hold `]` and
`::`, a damaged cycle log, task ids that reach the filesystem, evidence that
holds no tests, two cycles recorded at once, huge evidence, and the open
checkpoint set changing between two cycles.
"""

import codecs
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLI_DIR))

from commands import test_checkpoint  # noqa: E402

TEST_FILE = "tests/test_widget.py"


def run_cycle(argv):
    """Invoke `test_checkpoint.run` in-process. Returns `(code, stdout, stderr)`."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = test_checkpoint.run(argv)
    return code, out.getvalue(), err.getvalue()


def pytest_lines(*rows):
    """pytest `-v` text for `(node_suffix, status)` rows, e.g. `("A::t1", "FAILED")`."""
    return "".join(f"{TEST_FILE}::{node} {status} [ 50%]\n" for node, status in rows)


class VaultCase(unittest.TestCase):
    """A scratch project holding only an empty `.compass/` vault."""

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
    def checkpoints(self):
        return self.root / ".compass" / "tmp" / "test-checkpoints"

    def log_path(self, task):
        return self.checkpoints / f"{task}.cycles.jsonl"

    def log_lines(self, task):
        path = self.log_path(task)
        if not path.is_file():
            return []
        return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def evidence(self, data):
        self.counter += 1
        path = self.root / f"run{self.counter}.txt"
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def cycle(self, task, data):
        """One `cycle` call on `data`. Returns `(code, stdout, stderr)`."""
        return run_cycle(["cycle", task, "--evidence", str(self.evidence(data))])

    def verdict(self, task, data):
        code, out, err = self.cycle(task, data)
        self.assertEqual(code, 0, out + err)
        head = out.splitlines()[0]
        return head.split(": ", 1)[1].split(" - ")[0], out

    def tree_snapshot(self):
        return sorted(
            str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()
        )


class EvidenceEncodingTests(VaultCase):
    def test_encoded_evidence_is_read_the_same_as_utf8(self):
        """Adversarial where: evidence saved by a PowerShell redirect
        (UTF-16 with a byte-order mark), a Windows console (cp1252 holding a
        non-ASCII byte beside the test lines), or an editor (UTF-8 with a
        BOM, CRLF line ends) decodes to garbage or to a first line the
        parser cannot match, so a fixed test reads as vanished (harmful) or
        the file reads as testless."""
        before = (
            f"{TEST_FILE}::A::t1 FAILED [ 10%]\n"
            "# café “note”\n"
            f"{TEST_FILE}::A::t2 PASSED [ 20%]\n"
        )
        after = before.replace("A::t1 FAILED", "A::t1 PASSED")
        crlf = lambda text: text.replace("\n", "\r\n")  # noqa: E731
        encoders = {
            "utf-16 LE with BOM": lambda t: codecs.BOM_UTF16_LE + t.encode("utf-16-le"),
            "utf-16 BE with BOM": lambda t: codecs.BOM_UTF16_BE + t.encode("utf-16-be"),
            "utf-16 LE with BOM, CRLF": lambda t: codecs.BOM_UTF16_LE + crlf(t).encode("utf-16-le"),
            "utf-8 with BOM": lambda t: codecs.BOM_UTF8 + t.encode("utf-8"),
            "cp1252": lambda t: t.encode("cp1252"),
            "cp1252, CRLF": lambda t: crlf(t).encode("cp1252"),
            "utf-8 with one invalid byte": lambda t: t.encode("utf-8").replace(b"caf", b"\xff\xfe"),
        }
        for index, (label, encode) in enumerate(encoders.items()):
            task = f"TASK-{500 + index}"
            with self.subTest(encoding=label):
                first, _ = self.verdict(task, encode(before))
                second, out = self.verdict(task, encode(after))
                self.assertEqual(first, "neutral")
                self.assertEqual(second, "helpful", out)
                self.assertIn("fixed 1,", out)


class StatusTests(VaultCase):
    def test_statuses_beyond_pass_and_fail_move_the_verdict(self):
        """Adversarial where: a previously failing test that turns SKIPPED,
        XFAIL or XPASS is read as fixed (a builder hiding a failure behind a
        marker), an ERROR is read as not failing, or a new test that
        arrives SKIPPED/XFAIL is read as a new failure."""
        rows = [
            ("failing -> PASSED", "FAILED", "PASSED", "helpful"),
            ("failing -> ERROR still counts as failing", "FAILED", "ERROR", "neutral"),
            ("ERROR -> PASSED", "ERROR", "PASSED", "helpful"),
            ("failing -> SKIPPED hides the failure", "FAILED", "SKIPPED", "harmful"),
            ("failing -> XFAIL hides the failure", "FAILED", "XFAIL", "harmful"),
            ("failing -> XPASS is not a proven pass", "FAILED", "XPASS", "harmful"),
            ("passing -> ERROR is a new failure", "PASSED", "ERROR", "harmful"),
            ("passing -> SKIPPED is not a failure", "PASSED", "SKIPPED", "neutral"),
            ("passing -> XFAIL is not a failure", "PASSED", "XFAIL", "neutral"),
        ]
        for index, (label, was, now, expected) in enumerate(rows):
            task = f"TASK-{520 + index}"
            with self.subTest(row=label):
                # t_other fails in both runs so cycle 0 always holds a failure.
                self.verdict(task, pytest_lines(("A::t", was), ("A::t_other", "FAILED")))
                got, out = self.verdict(task, pytest_lines(("A::t", now), ("A::t_other", "FAILED")))
                self.assertEqual(got, expected, out)

    def test_new_test_arriving_with_a_non_failing_status_is_not_a_new_failure(self):
        """Adversarial where: a test that did not exist in the previous run
        and arrives SKIPPED, XFAIL or PASSED is counted as a new failure
        because the comparison treats any key outside the previous run as
        new."""
        for index, status in enumerate(["PASSED", "SKIPPED", "XFAIL", "XPASS"]):
            task = f"TASK-{540 + index}"
            with self.subTest(status=status):
                self.verdict(task, pytest_lines(("A::t", "FAILED")))
                got, out = self.verdict(
                    task, pytest_lines(("A::t", "FAILED"), ("A::fresh", status))
                )
                self.assertEqual(got, "neutral", out)


class ParametrizedIdTests(VaultCase):
    def test_parametrized_ids_with_brackets_colons_and_spaces(self):
        """Adversarial where: a param id holding `::`, `]`, spaces or a
        status word splits the node id at the wrong place, so the failing
        case is dropped (never failing) or filed under another name, and a
        later fix reads as neutral or as a vanished test."""
        rows = [
            ("double colon inside the param", "t[a::b]"),
            ("space inside the param", "t[a b]"),
            ("status word inside the param", "t[PASSED]"),
            ("close bracket inside the param", "t[x]y]"),
            ("empty param", "t[]"),
        ]
        for index, (label, node) in enumerate(rows):
            task = f"TASK-{560 + index}"
            with self.subTest(row=label):
                first = pytest_lines((f"A::{node}", "FAILED"), ("A::keep", "FAILED"))
                fixed = pytest_lines((f"A::{node}", "PASSED"), ("A::keep", "FAILED"))
                self.verdict(task, first)
                got, out = self.verdict(task, fixed)
                self.assertEqual((got, "fixed 1," in out), ("helpful", True), out)

    def test_one_failing_case_of_a_parametrized_test_keeps_the_test_failing(self):
        """Adversarial where: the passing sibling case is the last line read
        for the test name, so a test with one failing case among passing
        ones reads as passing and the next cycle's fix is never seen."""
        task = "TASK-570"
        mixed = pytest_lines(("A::t[a]", "FAILED"), ("A::t[b]", "PASSED"))
        self.verdict(task, mixed)
        got, out = self.verdict(task, mixed)
        self.assertEqual(got, "neutral")
        self.assertIn("still failing 1", out)
        got, out = self.verdict(
            task, pytest_lines(("A::t[a]", "PASSED"), ("A::t[b]", "PASSED"))
        )
        self.assertEqual((got, "fixed 1," in out), ("helpful", True), out)


class EvidenceWithoutTestsTests(VaultCase):
    def test_evidence_without_tests_exits_1_and_leaves_the_log_untouched(self):
        """Adversarial where: an empty file, a banner-only file, a
        directory, or a collection error page is logged as a cycle with an
        empty failing set, so the next real run reads every failure as new
        (harmful) and the cycle counter advances on nothing."""
        task = "TASK-580"
        self.verdict(task, pytest_lines(("A::t", "FAILED")))
        before = self.log_path(task).read_bytes()
        directory = self.root / "evidence_dir"
        directory.mkdir()
        rows = [
            ("empty file", self.evidence(b"")),
            ("whitespace only", self.evidence("\n  \n")),
            ("banner only", self.evidence("no tests ran in 0.01s\n")),
            ("collection error page", self.evidence("ERROR collecting tests/test_x.py\nImportError\n")),
            ("utf-16 BOM with no body", self.evidence(codecs.BOM_UTF16_LE)),
            ("a directory", directory),
        ]
        for label, path in rows:
            with self.subTest(row=label):
                code, out, err = run_cycle(["cycle", task, "--evidence", str(path)])
                self.assertEqual(code, 1, out + err)
                self.assertNotIn("cycle ", out)
                self.assertEqual(self.log_path(task).read_bytes(), before)


class DamagedLogTests(VaultCase):
    def test_a_damaged_cycle_log_exits_1_and_is_left_byte_for_byte(self):
        """Adversarial where: a log with a truncated last line, a row whose
        `failing` entries are not `[class, name]` pairs, or a non-object row
        raises a traceback or is silently rewritten (dropping the evidence
        of earlier cycles), or a string entry is split into characters and
        every real failure reads as new."""
        good = json.dumps({"cycle": 0, "verdict": "neutral", "failing": [["A", "t"]]})
        rows = [
            ("truncated last line", good + '\n{"cycle": 1, "verd'),
            ("failing entry is an int", '{"cycle": 0, "failing": [1]}'),
            ("failing entry is a one-element list", '{"cycle": 0, "failing": [["A"]]}'),
            ("failing entry is a string", '{"cycle": 0, "failing": ["ab"]}'),
            ("row is null", "null"),
            ("row is a list", "[]"),
        ]
        evidence = pytest_lines(("A::t", "FAILED"))
        for index, (label, content) in enumerate(rows):
            task = f"TASK-{600 + index}"
            with self.subTest(row=label):
                self.checkpoints.mkdir(parents=True, exist_ok=True)
                raw = (content + "\n").encode("utf-8")
                self.log_path(task).write_bytes(raw)
                code, out, err = self.cycle(task, evidence)
                self.assertEqual(code, 1, out + err)
                self.assertIn(f"{task}.cycles.jsonl", err)
                self.assertEqual(self.log_path(task).read_bytes(), raw)


class TaskIdTests(VaultCase):
    def test_only_ascii_task_ids_reach_the_filesystem(self):
        """Adversarial where: an id with path separators, dots, a trailing
        newline, lowercase letters, non-ASCII digits or a suffix reaches the
        log path, writing outside `test-checkpoints/` or creating a log that
        `open-ids` and `verify` can never address."""
        evidence = self.evidence(pytest_lines(("A::t", "FAILED")))
        rejected = [
            "TASK-1/../../x", "TASK-1\\..\\..\\x", "../TASK-1", "/abs/TASK-1",
            "task-1", "TASK-", "TASK-1.cycles", "TASK-1 ", " TASK-1", "TASK-1\n",
            "TASK-１２", "TASK-١٢", "TASK--1", "TASK-1-2",
        ]
        for task in rejected:
            with self.subTest(task=task):
                before = self.tree_snapshot()
                code, out, err = run_cycle(["cycle", task, "--evidence", str(evidence)])
                self.assertEqual(code, 1, out + err)
                self.assertEqual(self.tree_snapshot(), before)


class ConcurrencyTests(VaultCase):
    def test_simultaneous_cycles_each_get_their_own_number(self):
        """Adversarial where: two `cycle` calls for one task read the same
        log, both number themselves N, and the second atomic replace drops
        the first's row, so the cycle count under-reports and a harmful
        cycle can be lost."""
        workers = 8
        evidence = self.evidence(pytest_lines(("A::t", "FAILED")))
        child = self.root / "child.py"
        child.write_text(textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(CLI_DIR)!r})
            from commands import test_checkpoint
            start = float(sys.argv[1])
            while time.time() < start:
                pass
            sys.exit(test_checkpoint.run(["cycle", "TASK-650", "--evidence", {str(evidence)!r}]))
        """), encoding="utf-8")
        failures = []
        for attempt in range(3):
            task_log = self.log_path("TASK-650")
            if task_log.exists():
                task_log.write_text("", encoding="utf-8")
            start = time.time() + 3
            procs = [
                subprocess.Popen(
                    [sys.executable, str(child), repr(start)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env=dict(os.environ),
                )
                for _ in range(workers)
            ]
            numbers = []
            for proc in procs:
                out, err = proc.communicate(timeout=120)
                self.assertEqual(proc.returncode, 0, err)
                numbers.append(int(out.split(":", 1)[0].split()[1]))
            rows = len(self.log_lines("TASK-650"))
            if sorted(numbers) != list(range(workers)) or rows != workers:
                failures.append((attempt, sorted(numbers), rows))
        self.assertEqual(failures, [], "lost or duplicated cycle numbers")


class LargeEvidenceTests(VaultCase):
    def test_large_evidence_is_judged_in_bounded_time(self):
        """Adversarial where: a full-suite transcript of 200k tests, or one
        multi-megabyte line, makes the line regexes quadratic or the
        comparison quadratic in the failing set, so the loop stalls on a
        large repository."""
        lines = [f"{TEST_FILE}::C{i % 500}::test_{i} PASSED [ 50%]\n" for i in range(200_000)]
        lines[123_456] = f"{TEST_FILE}::C{123_456 % 500}::test_123456 FAILED [ 50%]\n"
        big = "".join(lines)
        begin = time.monotonic()
        self.verdict("TASK-660", big)
        fixed, out = self.verdict("TASK-660", big.replace("test_123456 FAILED", "test_123456 PASSED"))
        self.assertEqual((fixed, "fixed 1," in out), ("helpful", True), out)
        self.assertLess(time.monotonic() - begin, 60)

        long_line = "x.py" * 1_000_000 + "\n" + "a" * 3_000_000 + "\n" + pytest_lines(("A::t", "FAILED"))
        begin = time.monotonic()
        got, out = self.verdict("TASK-661", long_line)
        self.assertIn("still failing 1", out)
        self.assertLess(time.monotonic() - begin, 60)

    def test_many_failures_are_all_tracked(self):
        """Adversarial where: the comparison truncates or dedupes a large
        failing set, so fixing 5000 of 6000 failures reads as neutral."""
        task = "TASK-662"
        names = [f"t{i}" for i in range(6000)]
        self.verdict(task, pytest_lines(*[(f"A::{n}", "FAILED") for n in names]))
        rows = [(f"A::{n}", "PASSED" if i < 5000 else "FAILED") for i, n in enumerate(names)]
        got, out = self.verdict(task, pytest_lines(*rows))
        self.assertEqual(got, "helpful")
        self.assertIn("fixed 5000, new 0, still failing 1000", out)


class OpenSetChangesBetweenCyclesTests(VaultCase):
    def checkpoint(self, task, class_name, test, landed=False):
        self.checkpoints.mkdir(parents=True, exist_ok=True)
        record = {
            "files": [{"path": TEST_FILE, "ids": [[class_name, test]]}],
            "landed": landed, "not_required": False,
        }
        (self.checkpoints / f"{task}.json").write_text(json.dumps(record), encoding="utf-8")

    def test_a_checkpoint_recorded_for_another_task_between_cycles(self):
        """Adversarial where: a test failing in cycle 0 becomes an open
        checkpoint test (another task is checkpointed) before cycle 1; the
        previous failing set is not filtered by the new open set, so the
        same test, still failing or now absent from the run, is counted as
        a vanished test and the cycle reads harmful and escalates."""
        rows = [
            ("still failing", pytest_lines(("A::t", "FAILED"), ("A::keep", "FAILED"))),
            ("absent from the run", pytest_lines(("A::keep", "FAILED"))),
        ]
        for index, (label, after) in enumerate(rows):
            task = f"TASK-{670 + index}"
            with self.subTest(row=label):
                self.verdict(task, pytest_lines(("A::t", "FAILED"), ("A::keep", "FAILED")))
                self.checkpoint(f"TASK-{700 + index}", "A", "t")
                got, out = self.verdict(task, after)
                self.assertEqual(got, "neutral", out)
                self.assertIn("escalate: no", out)
                self.assertIn("still failing 1", out)

    def test_a_checkpoint_landing_between_cycles_exposes_its_failures(self):
        """Adversarial where: the open set is read once, or cached from the
        previous cycle, so a checkpoint that landed (verified green) still
        hides its test when that test later breaks."""
        task = "TASK-680"
        self.checkpoint("TASK-710", "A", "t")
        self.verdict(task, pytest_lines(("A::t", "FAILED"), ("A::keep", "FAILED")))
        self.checkpoint("TASK-710", "A", "t", landed=True)
        got, out = self.verdict(task, pytest_lines(("A::t", "FAILED"), ("A::keep", "FAILED")))
        self.assertEqual(got, "harmful", out)
        self.assertIn("new 1", out)

    def test_the_task_under_repair_keeps_its_own_checkpointed_failures_in_the_verdict(self):
        """Adversarial where: the open set includes the very task whose fix
        loop is running (its checkpoint is not landed until `verify
        --against-run` is green, i.e. exactly while its own tests fail), so
        fixing or breaking the task's own checkpointed tests never moves the
        verdict: a cycle that fixes the failing pre-build test reads neutral
        and one that breaks a second reads neutral instead of harmful."""
        task = "TASK-690"
        self.checkpoint(task, "A", "own_test")
        before = pytest_lines(("A::own_test", "FAILED"), ("A::keep", "PASSED"))
        self.verdict(task, before)
        got, out = self.verdict(task, pytest_lines(("A::own_test", "PASSED"), ("A::keep", "PASSED")))
        self.assertEqual((got, "fixed 1," in out), ("helpful", True), out)


if __name__ == "__main__":
    unittest.main()
