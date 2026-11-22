"""Post-build tests for `compass stations` and `planlib.task_letters`: defect
classes that exist only once the join, the log reader and the plan scan are
written. Adversarial themes: plan scopes (unit folders, `--plan` numbers,
an id present in two plans), regions of a plan file that hold no live task,
row fields of the wrong type, and log bytes the line reader can split or
reject."""

import json
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import planlib  # noqa: E402

from test_stations import (  # noqa: E402
    group_counts, log_row, make_vault, run_stations, tree_snapshot,
    unknown_task_ints, write_log, write_plan,
)

HEAD = '---\ntitle: "P"\ntype: plan\nstatus: active\nsummary: "p"\ntags: [x]\n---\n\n# P\n\n'
UNIT_INDEX = "---\ntitle: u\ntype: unit\nstatus: active\n---\n"


def plan(body):
    return HEAD + body


def make_unit_plan(vault, name, body):
    unit = vault / "myunit"
    (unit / "plans").mkdir(parents=True, exist_ok=True)
    (unit / "index.md").write_text(UNIT_INDEX, encoding="utf-8")
    (unit / "plans" / name).write_text(plan(body), encoding="utf-8")


class TaskLettersTests(unittest.TestCase):
    def test_task_letters_regions(self):
        """Adversarial where: a task line in a region that is not a live task
        (fenced example, blockquote, a wave record) is read as live, or a
        `## Later` task is dropped. One behavior (`task_letters`), one row
        per region."""
        text = plan(
            "## Wave 1\n\n- [ ] TASK-1: a - complexity: S\n\n"
            "```\n- [ ] TASK-2: fenced - complexity: L\n```\n\n"
            "> - [ ] TASK-3: quoted - complexity: L\n\n"
            "## Later\n\n- [ ] TASK-4: later - complexity: M\n\n"
            "## Wave 1 elaborated\n\n- [ ] TASK-5: record - complexity: L\n"
        )
        got = planlib.task_letters(text)
        rows = {
            "live task kept": ("TASK-1", "S", True),
            "fenced task ignored": ("TASK-2", None, False),
            "blockquoted task ignored": ("TASK-3", None, False),
            "Later task kept with its letter": ("TASK-4", "M", True),
            "record region task ignored": ("TASK-5", None, False),
        }
        for name, (task, letter, present) in rows.items():
            with self.subTest(name=name):
                self.assertEqual(task in got, present)
                if present:
                    self.assertEqual(got[task], letter)


class StationsPlanScopeTests(unittest.TestCase):
    def test_unit_folder_plan_joins(self):
        """Adversarial where: tasks of a plan inside a unit folder
        (`.compass/<unit>/plans/`) are not scanned, so every row of them is
        reported as an unknown task."""
        vault = make_vault(self)
        make_unit_plan(vault, "PLAN-001-u.md", "- [ ] TASK-77: u - complexity: L, depends_on: none\n")
        write_log(vault, [log_row("tester-post", "TASK-77", bugs=2)])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "L", "modelalpha", "tester-post")[:2], [1, 2])
        self.assertEqual(unknown_task_ints(out), [])

    def test_unit_and_root_plans_sharing_a_number(self):
        """Adversarial where: unit plans are numbered locally, so root PLAN-001
        and a unit's PLAN-001 both answer `--plan PLAN-001` and a task of the
        unit plan shows up in the root plan's report."""
        vault = make_vault(self)
        write_plan(vault, "PLAN-001-root.md", plan("- [ ] TASK-1: r - complexity: S\n"))
        make_unit_plan(vault, "PLAN-001-u.md", "- [ ] TASK-2: u - complexity: L\n")
        write_log(vault, [log_row("builder", "TASK-1"), log_row("builder", "TASK-2")])
        code, out = run_stations(["--plan", "PLAN-001"])
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "S", "modelalpha", "builder")[0], 1)
        self.assertNotIn("L ", out)

    def test_folder_plan_child_file_tasks_join_under_plan_flag(self):
        """Adversarial where: tasks written in a child file of a folder plan
        carry no PLAN number of their own, so `--plan PLAN-NNN` drops their
        rows while the unfiltered report keeps them."""
        vault = make_vault(self)
        folder = vault / "plans" / "PLAN-040-big"
        folder.mkdir()
        (folder / "index.md").write_text(plan("- [ ] TASK-1: a - complexity: S\n"), encoding="utf-8")
        (folder / "detail.md").write_text(plan("- [ ] TASK-2: b - complexity: M\n"), encoding="utf-8")
        write_log(vault, [log_row("builder", "TASK-1"), log_row("builder", "TASK-2")])
        _, everything = run_stations()
        _, scoped = run_stations(["--plan", "PLAN-040"])
        self.assertEqual(group_counts(everything, "M", "modelalpha", "builder")[0], 1)
        self.assertEqual(group_counts(scoped, "M", "modelalpha", "builder")[0], 1)

    def test_task_id_in_two_plans(self):
        """Adversarial where: an id present in two plans is counted twice, or
        takes the letter of whichever plan the scan met first when `--plan`
        names the other one. One row per call shape."""
        vault = make_vault(self)
        write_plan(vault, "PLAN-001-a.md", plan("- [ ] TASK-9: a - complexity: S\n"))
        write_plan(vault, "PLAN-002-b.md", plan("- [ ] TASK-9: b - complexity: L\n"))
        write_log(vault, [log_row("builder", "TASK-9")])
        _, scoped_two = run_stations(["--plan", "PLAN-002"])
        _, scoped_one = run_stations(["--plan", "PLAN-001"])
        _, both = run_stations()
        self.assertEqual(group_counts(scoped_two, "L", "modelalpha", "builder")[0], 1)
        self.assertEqual(group_counts(scoped_one, "S", "modelalpha", "builder")[0], 1)
        spawns = sum(line.split().count("builder") for line in both.splitlines())
        self.assertEqual(spawns, 1)

    def test_plan_flag_naming_no_plan(self):
        """Adversarial where: `--plan` naming a plan that does not exist prints
        an empty report with exit 0 instead of failing, or `--plan` given
        without a value or in a wrong form passes, or the failing call writes
        into the vault. One row per argument."""
        vault = make_vault(self)
        write_plan(vault, "PLAN-001-a.md", plan("- [ ] TASK-1: a - complexity: S\n"))
        write_log(vault, [log_row("builder", "TASK-1")])
        before = tree_snapshot(vault)
        for argv in (["--plan", "PLAN-099"], ["--plan"], ["--plan", "99"], ["--plan=PLAN-"], ["--bogus"]):
            with self.subTest(argv=argv):
                code, out = run_stations(argv)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
        self.assertEqual(tree_snapshot(vault), before)


class StationsRowFieldTests(unittest.TestCase):
    def test_count_fields_of_the_wrong_kind(self):
        """Adversarial where: a count field that is a string, bool, float,
        negative or a list is summed, raises, or drives a column below zero.
        One behavior (counts are the non-negative ints), one row per kind;
        each row is its own station name so the groups stay apart."""
        vault = make_vault(self)
        write_plan(vault, "PLAN-001-a.md", plan("- [ ] TASK-1: a - complexity: S\n"))
        bad = {"str": "5", "bool": True, "float": 2.5, "negative": -5, "list": [3], "null": None}
        lines = [log_row("st-" + name, "TASK-1", bugs=value, fails=value) for name, value in bad.items()]
        lines.append(log_row("st-good", "TASK-1", bugs=4, fails=1))
        write_log(vault, lines)
        code, out = run_stations()
        self.assertEqual(code, 0)
        for name in bad:
            with self.subTest(name=name):
                self.assertEqual(group_counts(out, "S", "modelalpha", "st-" + name)[:3], [1, 0, 0])
        self.assertEqual(group_counts(out, "S", "modelalpha", "st-good")[:3], [1, 4, 1])
        with self.subTest(name="no column is negative"):
            self.assertNotRegex(out, r"\s-\d")

    def test_odd_task_values(self):
        """Adversarial where: a row whose `task` is a list, number, dict, or a
        padded or lowercase id raises (unhashable) or joins; all must be
        counted as unknown task rows."""
        vault = make_vault(self)
        write_plan(vault, "PLAN-001-a.md", plan("- [ ] TASK-1: a - complexity: S\n"))
        write_log(vault, [
            log_row("builder", ["TASK-1"]), log_row("builder", 1), log_row("builder", " TASK-1"),
            log_row("builder", "task-1"), log_row("builder", {"id": "TASK-1"}), log_row("builder", "TASK-1"),
        ])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(unknown_task_ints(out), [5])
        self.assertEqual(group_counts(out, "S", "modelalpha", "builder")[0], 1)


class StationsLogBytesTests(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        write_plan(self.vault, "PLAN-001-a.md", plan("- [ ] TASK-1: a - complexity: S\n"))
        self.log = self.vault / "meta" / "station-log.jsonl"

    def test_row_text_with_unicode_line_separators(self):
        """Adversarial where: `stationlib.append_row` writes with
        `ensure_ascii=False`, so a model holding U+2028, U+2029 or U+0085
        reaches the log raw; a reader splitting with `str.splitlines` cuts
        that one JSON line in two and silently drops the row."""
        for sep in (" ", " ", "\u0085"):
            with self.subTest(sep=repr(sep)):
                row = json.dumps({"station": "builder", "task": "TASK-1", "model": "m" + sep + "x"},
                                 ensure_ascii=False)
                self.log.write_bytes((row + "\n").encode("utf-8"))
                code, out = run_stations()
                self.assertEqual(code, 0)
                self.assertEqual(unknown_task_ints(out), [])
                self.assertIn("builder", out)

    def test_log_with_bom_and_crlf(self):
        """Adversarial where: a log saved by a Windows editor starts with a
        UTF-8 BOM and ends lines with CRLF; the BOM makes the first row fail
        JSON parsing and it is dropped without a trace."""
        rows = [log_row("builder", "TASK-1"), log_row("builder", "TASK-1")]
        self.log.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(rows).encode("utf-8") + b"\r\n")
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "S", "modelalpha", "builder")[0], 2)

    def test_invalid_utf8_bytes_keep_other_rows(self):
        """Adversarial where: one row holding invalid UTF-8 bytes aborts the
        decode of the whole log instead of costing only itself."""
        good = log_row("builder", "TASK-1").encode("utf-8")
        self.log.write_bytes(good + b"\n" + b'{"task": "TASK-1", "model": "\xff\xfe"}\n' + good + b"\n")
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "S", "modelalpha", "builder")[0], 2)

    def test_model_text_cannot_forge_a_report_line(self):
        """Adversarial where: a model name holding a newline is printed raw and
        splits one group into two report lines, the second forged from log
        text."""
        write_log(self.vault, [log_row("builder", "TASK-1", model="evil\nL forged builder 99 99 99 99 99")])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 2)

    def test_large_log_reports_in_bounded_time(self):
        """Adversarial where: the join is quadratic in rows so a long-lived log
        makes the report crawl; 100k rows must finish in a few seconds and
        count exactly."""
        line = log_row("builder", "TASK-1")
        other = log_row("builder", "TASK-404")
        self.log.write_text("\n".join([line, other] * 50000) + "\n", encoding="utf-8")
        start = time.monotonic()
        code, out = run_stations()
        elapsed = time.monotonic() - start
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "S", "modelalpha", "builder")[0], 50000)
        self.assertEqual(unknown_task_ints(out), [50000])
        self.assertLess(elapsed, 10)


if __name__ == "__main__":
    unittest.main()
