"""Post-build adversarial tests for stationlib: branches the implementation
introduced (transcript fallback, None-item filter, heading regex, newline
repair) that the task's public contract never named.

Themes: a hook that must never hang or raise on hostile input, rows that stay
exactly one line for any reader, and counts that do not drift with wording.
"""

import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stationlib  # noqa: E402


def _append_many(args):
    vault, tag, count = args
    for i in range(count):
        stationlib.append_row(vault, {"station": "fix-cycle", "task": f"{tag}-{i}", "pad": "x" * 300})


def _tester_post(bug_lines):
    return (
        "## Test Report\n\n### Mode\nPost-build\n\n### Bugs Found\n"
        + "\n".join(bug_lines)
        + "\n\n### Coverage\n- x\n"
    )


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)


class BugCountWording(unittest.TestCase):
    def test_none_wordings_in_bugs_found_count_zero(self):
        """Adversarial where: a Bugs Found section whose only item says it
        found nothing ("None found", "No bugs", "N/A") must not be tallied as
        a bug, or every clean post-build run logs bugs=1."""
        rows = {
            "none": "- None",
            "none-found": "- None found",
            "none-period": "- None.",
            "bold-none": "- **None**",
            "no-bugs": "- No bugs found",
        }
        for name, line in rows.items():
            with self.subTest(name=name):
                parsed = stationlib.parse_report("tester", _tester_post([line]))
                self.assertEqual(parsed["bugs"], 0)

    def test_none_item_beside_one_real_bug_counts_only_the_bug(self):
        """Adversarial where: asymmetric section (one None line, one real
        bug) must count 1, not 0 and not 2."""
        parsed = stationlib.parse_report(
            "tester", _tester_post(["- None", "- **B:** `a.py:1` - repro: x - expected: 1 / actual: 2"])
        )
        self.assertEqual(parsed["bugs"], 1)


class ValidatorFailRows(unittest.TestCase):
    def test_fail_word_inside_a_task_description_is_not_a_fail_row(self):
        """Adversarial where: a Phase Results row whose task description
        contains the word FAIL (a task about FAIL handling) but whose
        classification is a pass must not count as a failing row."""
        report = (
            "## Validation Report: [[PLAN-1-x]]\n\n### Phase Results\n#### Phase 1: A\n"
            "| Task | Status | Checks | Classification |\n|---|---|---|---|\n"
            "| TASK-9: report FAIL rows | [x] done | 3/3 passed | Matches plan |\n\n"
            "### Summary\nx\n\nVERDICT: PASS\n"
        )
        parsed = stationlib.parse_report("validator", report)
        self.assertEqual((parsed["result"], parsed["fails"]), ("PASS", 0))


class HostileInput(TmpCase):
    def test_heading_scan_is_linear_on_a_long_whitespace_run(self):
        """Adversarial where: a heading-shaped line carrying tens of
        thousands of spaces before a non-space char backtracks quadratically
        in the heading regex and stalls the SubagentStop hook."""
        text = "# a" + " " * 40000 + "b\n"
        start = time.monotonic()
        stationlib.parse_report("tester", text)
        self.assertLess(time.monotonic() - start, 1.5)

    def test_build_row_survives_every_unreadable_transcript_shape(self):
        """Adversarial where: an agent_transcript_path that is a directory,
        missing, non-UTF-8 bytes, NUL-bearing, or not a string must fall back
        to the resolved model rather than raise out of build_row."""
        bad = self.tmp / "bad.jsonl"
        bad.write_bytes(b"\xff\xfe\x00not json\n" * 20)
        shapes = {
            "directory": str(self.tmp),
            "missing": str(self.tmp / "nope.jsonl"),
            "non-utf8": str(bad),
            "nul": "a\0b",
            "empty": "",
            "int": 7,
            "list": ["x"],
        }
        for name, path in shapes.items():
            with self.subTest(name=name):
                row = stationlib.build_row({"agent_type": "tester", "agent_transcript_path": path}, "x")
                self.assertNotEqual(row["model_source"], stationlib.TRANSCRIPT_SOURCE)
                self.assertTrue(row["model"])

    def test_build_row_with_non_string_report_and_agent_values_does_not_raise(self):
        """Adversarial where: last_assistant_message None / a list and an
        agent_type that is a dict reach build_row from an untrusted event."""
        for name, event, text in (
            ("none-text", {"agent_type": "tester"}, None),
            ("list-text", {"agent_type": "validator"}, ["VERDICT: PASS"]),
            ("dict-agent", {"agent_type": {"a": 1}}, "x"),
        ):
            with self.subTest(name=name):
                row = stationlib.build_row(event, text)
                json.dumps(row)
                self.assertIn("station", row)

    def test_fifty_megabyte_report_without_newlines_parses_quickly(self):
        """Adversarial where: a pathological single-line final message must
        not make parsing superlinear."""
        start = time.monotonic()
        parsed = stationlib.parse_report("tester", "x" * 50_000_000)
        self.assertEqual(parsed["verdict"], stationlib.UNPARSED)
        self.assertLess(time.monotonic() - start, 5)


class AppendIntegrity(TmpCase):
    def test_line_separator_characters_in_a_value_keep_the_row_one_line(self):
        """Adversarial where: ensure_ascii=False writes U+2028, U+0085 and
        U+001C raw, so a reader using str.splitlines() sees one row as
        several broken lines. agent_type is copied from the event."""
        row = {"station": "a b\u0085c\u001cd\x0be", "task": None}
        stationlib.append_row(self.tmp, row)
        text = (self.tmp / "meta" / "station-log.jsonl").read_text(encoding="utf-8")
        self.assertEqual(len(text.splitlines()), 1)
        self.assertEqual(json.loads(text.splitlines()[0]), row)

    def test_unterminated_last_line_is_repaired_before_the_new_row(self):
        """Adversarial where: a log whose last line lacks its newline (a
        torn earlier write) must not fuse with the next row."""
        log = self.tmp / "meta" / "station-log.jsonl"
        log.parent.mkdir()
        log.write_bytes(b'{"station": "old"}')
        stationlib.append_row(self.tmp, {"station": "new"})
        parsed = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual([p["station"] for p in parsed], ["old", "new"])

    def test_parallel_processes_appending_lose_and_tear_no_row(self):
        """Adversarial where: SubagentStop hooks from parallel subagents
        append at once; interleaved writes must leave every line valid JSON
        with exactly the rows written."""
        workers, per = 6, 40
        with multiprocessing.Pool(workers) as pool:
            pool.map(_append_many, [(str(self.tmp), f"w{w}", per) for w in range(workers)])
        raw = (self.tmp / "meta" / "station-log.jsonl").read_bytes().decode("utf-8")
        lines = [line for line in raw.split("\n") if line]
        tasks = sorted(json.loads(line)["task"] for line in lines)
        expected = sorted(f"w{w}-{i}" for w in range(workers) for i in range(per))
        self.assertEqual(tasks, expected)


if __name__ == "__main__":
    unittest.main()
