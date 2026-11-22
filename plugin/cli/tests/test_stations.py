"""Tests for `compass stations [--plan PLAN-NNN]`, the read-only report that
joins `.compass/meta/station-log.jsonl` rows to their task's complexity letter.
Adversarial themes: a row joined to the wrong task (prefix aliasing between
TASK-1 and TASK-10), a row with no letter or an unknown task miscounted, an
empty or missing log failing, a malformed log line aborting the report, and
the report writing anything.

Report interface pinned here: one line per (letter, model, station) group; the
line holds the letter, the model and the station as whole tokens, and after the
station token the integers spawns, bugs found, FAIL items, fix cycles and
unparsed rows, in that order. Rows whose task id matches no plan are reported
on one line containing "unknown task" with their count."""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from commands import stations  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_DIR = Path(__file__).resolve().parents[1]

PLAN_ONE = """---
title: "First plan"
type: plan
status: active
summary: "first"
tags: [x]
---

# First plan

## Wave 1

- [ ] TASK-1: small thing - complexity: S, depends_on: none, files: [a.py]
- [ ] TASK-2: medium thing - complexity: M, depends_on: none, files: [b.py]
- [ ] TASK-3: tiny thing - depends_on: none, complexity: XS
- [ ] TASK-4: thing with no letter - depends_on: none, files: [d.py]
"""

PLAN_TWO = """---
title: "Second plan"
type: plan
status: active
summary: "second"
tags: [x]
---

# Second plan

## Wave 1

- [ ] TASK-20: large thing - complexity: L, depends_on: none, files: [e.py]
"""

INT = r"(?<![\w.-])\d+(?![\w.-])"


def make_vault(case):
    tmp = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, tmp, True)
    vault = tmp / ".compass"
    (vault / "meta").mkdir(parents=True)
    (vault / "plans").mkdir()
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    case.addCleanup(restore)
    return vault


def write_plan(vault, name, text):
    (vault / "plans" / name).write_text(text, encoding="utf-8")


def log_row(station, task, model="modelalpha", **extra):
    row = {
        "ts": "2026-11-21T10:00:00+00:00",
        "agent_type": "tester",
        "station": station,
        "task": task,
        "model": model,
        "model_source": "transcript",
    }
    row.update(extra)
    return json.dumps(row)


def write_log(vault, lines):
    path = vault / "meta" / "station-log.jsonl"
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def run_stations(argv=()):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = stations.run(list(argv))
    return code, out.getvalue()


def token(text, word):
    return re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])", text)


def group_counts(output, letter, model, station):
    """The five integers on the line for one (letter, model, station) group:
    spawns, bugs, fails, cycles, unparsed. Fails when no line, or more than
    one line, holds all three tokens."""
    found = []
    for line in output.splitlines():
        if token(line, letter) and token(line, model) and token(line, station):
            tail = line[token(line, station).end():]
            found.append([int(n) for n in re.findall(INT, tail)])
    if len(found) != 1:
        raise AssertionError(
            f"expected one line for {letter}/{model}/{station}, found {len(found)} in:\n{output}")
    return found[0][:5]


def unknown_task_ints(output):
    ints = []
    for line in output.splitlines():
        if "unknown task" in line.lower():
            ints.extend(int(n) for n in re.findall(INT, line))
    return ints


def tree_snapshot(root):
    snap = {}
    for path in sorted(Path(root).rglob("*")):
        rel = path.relative_to(root).as_posix()
        snap[rel] = path.read_bytes() if path.is_file() else None
    return snap


class StationsReportTests(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        write_plan(self.vault, "PLAN-001-first.md", PLAN_ONE)

    def test_counts_per_letter_model_and_station(self):
        """Adversarial where: rows are joined to the wrong letter, groups merge
        across models or stations, or a count is taken from the wrong field.
        One behavior (the per-group counts), one row per group: two post-build
        testers on one letter summed, the same letter under a second model kept
        apart, a pre-build row with no bugs field, validator FAIL items summed,
        XS kept apart from S, fix cycles counted, and an unparsed row counted
        in the unparsed column."""
        write_log(self.vault, [
            log_row("tester-post", "TASK-1", bugs=2),
            log_row("tester-post", "TASK-1", bugs=4),
            log_row("tester-post", "TASK-1", model="modelbeta", bugs=1),
            log_row("tester-pre", "TASK-1"),
            log_row("validator", "TASK-1", fails=3, result="FAIL"),
            log_row("validator", "TASK-1", fails=0, result="PASS"),
            log_row("builder", "TASK-2", model="modelgamma"),
            log_row("tester-post", "TASK-3", bugs=7),
            log_row("fix-cycle", "TASK-2", model="modelgamma", cycle=1, verdict="helpful"),
            log_row("fix-cycle", "TASK-2", model="modelgamma", cycle=2, verdict="neutral"),
            log_row("fix-cycle", "TASK-1", cycle=1, verdict="harmful"),
            log_row("general-purpose", "TASK-1", model="modelepsilon", verdict="unparsed"),
        ])
        code, out = run_stations()
        self.assertEqual(code, 0)
        rows = {
            "S post-build alpha: two spawns, six bugs": (("S", "modelalpha", "tester-post"), [2, 6, 0, 0, 0]),
            "S post-build beta kept apart": (("S", "modelbeta", "tester-post"), [1, 1, 0, 0, 0]),
            "S pre-build has no bugs": (("S", "modelalpha", "tester-pre"), [1, 0, 0, 0, 0]),
            "S validator sums FAIL items": (("S", "modelalpha", "validator"), [2, 0, 3, 0, 0]),
            "M builder": (("M", "modelgamma", "builder"), [1, 0, 0, 0, 0]),
            "XS is not folded into S": (("XS", "modelalpha", "tester-post"), [1, 7, 0, 0, 0]),
        }
        for name, (key, expected) in rows.items():
            with self.subTest(name=name):
                self.assertEqual(group_counts(out, *key), expected)
        with self.subTest(name="M fix cycles"):
            self.assertEqual(group_counts(out, "M", "modelgamma", "fix-cycle")[3], 2)
        with self.subTest(name="S fix cycle"):
            self.assertEqual(group_counts(out, "S", "modelalpha", "fix-cycle")[3], 1)
        with self.subTest(name="unparsed row"):
            self.assertEqual(group_counts(out, "S", "modelepsilon", "general-purpose")[4], 1)

    def test_unknown_task_rows_are_counted_apart(self):
        """Adversarial where: a row whose task id is absent from every plan is
        folded into a letter, dropped, or matched by prefix (TASK-10 and
        TASK-12 aliasing the plan's TASK-1). A known task with no letter must
        not count as unknown, so the count is exactly the three strangers."""
        write_log(self.vault, [
            log_row("tester-post", "TASK-999", model="modelzeta", bugs=5),
            log_row("tester-post", "TASK-10", model="modelzeta", bugs=5),
            log_row("builder", "TASK-12", model="modelzeta"),
            log_row("builder", "TASK-4", model="modeleta"),
            log_row("tester-post", "TASK-1", bugs=2),
        ])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual([n for n in unknown_task_ints(out) if n != 0], [3])
        self.assertEqual(group_counts(out, "S", "modelalpha", "tester-post"), [1, 2, 0, 0, 0])
        for line in out.splitlines():
            if "unknown task" not in line.lower():
                self.assertIsNone(token(line, "modelzeta"), line)

    def test_no_unknown_rows_reports_no_unknown_count(self):
        """Adversarial where: the unknown-task line reports a phantom count
        when every row matches a plan."""
        write_log(self.vault, [log_row("tester-post", "TASK-1", bugs=2)])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual([n for n in unknown_task_ints(out) if n != 0], [])

    def test_plan_flag_limits_to_that_plans_tasks(self):
        """Adversarial where: `--plan` is ignored (every plan's tasks listed)
        or matches the wrong plan. Plan one's task carries S under modelalpha,
        plan two's carries L under modeltheta."""
        write_plan(self.vault, "PLAN-002-second.md", PLAN_TWO)
        write_log(self.vault, [
            log_row("tester-post", "TASK-1", bugs=2),
            log_row("tester-post", "TASK-20", model="modeltheta", bugs=9),
        ])
        code, out = run_stations(["--plan", "PLAN-002"])
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "L", "modeltheta", "tester-post"), [1, 9, 0, 0, 0])
        self.assertIsNone(token(out, "modelalpha"))
        code, out = run_stations(["--plan", "PLAN-001"])
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "S", "modelalpha", "tester-post"), [1, 2, 0, 0, 0])
        self.assertIsNone(token(out, "modeltheta"))

    def test_without_plan_flag_every_plan_is_joined(self):
        """Adversarial where: only the first plan file is read, so a task in a
        later plan lands in the unknown-task count."""
        write_plan(self.vault, "PLAN-002-second.md", PLAN_TWO)
        write_log(self.vault, [
            log_row("tester-post", "TASK-1", bugs=2),
            log_row("tester-post", "TASK-20", model="modeltheta", bugs=9),
        ])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "L", "modeltheta", "tester-post"), [1, 9, 0, 0, 0])
        self.assertEqual([n for n in unknown_task_ints(out) if n != 0], [])

    def test_rows_with_missing_or_null_fields_do_not_abort_the_report(self):
        """Adversarial where: a row with a null task or a null model (an
        unparsed report carries no task id) crashes the join, or leaks into a
        known task's counts."""
        write_log(self.vault, [
            log_row("general-purpose", None, verdict="unparsed"),
            log_row("tester-post", "TASK-1", model=None, bugs=1),
            log_row("tester-post", "TASK-1", bugs=2),
        ])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "S", "modelalpha", "tester-post"), [1, 2, 0, 0, 0])

    def test_malformed_log_line_among_good_rows_does_not_abort(self):
        """Adversarial where: one torn or blank line in an append-only log
        stops the whole report, or exits non-zero, though the other rows are
        sound."""
        write_log(self.vault, [
            log_row("tester-post", "TASK-1", bugs=2),
            '{"ts": "2026-11-21T10:00:00+00:00", "station": "tester-po',
            "",
            log_row("tester-post", "TASK-1", bugs=4),
        ])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out, "S", "modelalpha", "tester-post"), [2, 6, 0, 0, 0])


class StationsReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.vault = make_vault(self)
        write_plan(self.vault, "PLAN-001-first.md", PLAN_ONE)

    def test_missing_log_exits_zero_and_creates_nothing(self):
        """Adversarial where: a missing log raises, exits 1, or is created
        empty by the report."""
        before = tree_snapshot(self.vault.parent)
        code, _ = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual(tree_snapshot(self.vault.parent), before)
        self.assertFalse((self.vault / "meta" / "station-log.jsonl").exists())

    def test_empty_log_exits_zero(self):
        """Adversarial where: a zero-byte log fails on the first read, or
        prints a count row for a group no row belongs to."""
        write_log(self.vault, [])
        code, out = run_stations()
        self.assertEqual(code, 0)
        self.assertEqual([n for n in unknown_task_ints(out) if n != 0], [])
        self.assertIsNone(token(out, "tester-post"))

    def test_populated_report_writes_no_file(self):
        """Adversarial where: the report rewrites the log (sorting or
        compacting it), writes a cache beside it, or touches a plan. Every
        byte of the project tree, including the log, is the same after."""
        write_plan(self.vault, "PLAN-002-second.md", PLAN_TWO)
        write_log(self.vault, [
            log_row("tester-post", "TASK-2", bugs=3),
            log_row("tester-post", "TASK-1", bugs=1),
            log_row("builder", "TASK-777"),
            "not json at all",
        ])
        before = tree_snapshot(self.vault.parent)
        for argv in ([], ["--plan", "PLAN-001"]):
            with self.subTest(argv=argv):
                code, _ = run_stations(argv)
                self.assertEqual(code, 0)
                self.assertEqual(tree_snapshot(self.vault.parent), before)


class StationsRegistrationTests(unittest.TestCase):
    def test_command_is_registered_once_and_runs_through_main(self):
        """Adversarial where: `stations` is missing from `COMMAND_SPECS` (so
        the CLI answers unknown command), is registered twice, or its run
        function is not the one dispatch reaches."""
        names = [name for name, _ in maincli.COMMAND_SPECS]
        self.assertEqual(names.count("stations"), 1)
        self.assertIn("stations", maincli.VALID_COMMANDS)
        vault = make_vault(self)
        write_plan(vault, "PLAN-001-first.md", PLAN_ONE)
        write_log(vault, [log_row("tester-post", "TASK-1", bugs=2)])
        out = io.StringIO()
        with redirect_stdout(out):
            code = maincli.main(["stations"])
        self.assertEqual(code, 0)
        self.assertEqual(group_counts(out.getvalue(), "S", "modelalpha", "tester-post"), [1, 2, 0, 0, 0])

    def test_runs_against_this_vault_and_exits_zero(self):
        """Adversarial where: the command fails on the real vault (its plans
        carry shapes the fixtures do not, such as Later regions and unit
        folders) or writes into it. Runs as a subprocess, the way the human
        invokes it, and leaves `git status` of the meta folder unchanged."""
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        status = ["git", "status", "--porcelain", "--", ".compass/meta"]
        before = subprocess.run(status, cwd=REPO_ROOT, capture_output=True, text=True).stdout
        proc = subprocess.run(
            [sys.executable, str(CLI_DIR / "compass"), "stations"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        after = subprocess.run(status, cwd=REPO_ROOT, capture_output=True, text=True).stdout
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
