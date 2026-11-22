"""Adversarial tests for `compass drift` aimed at branches of its implementation.

Covers table-cell escaping in the report, the run-log reader and appender
(damaged rows, a missing final newline), report-name collisions, argument
parsing, a repository without commits, a vault nested below the repository
root, and non-ASCII text on a narrow stdout encoding.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from commands import drift  # noqa: E402
from test_drift_command import (  # noqa: E402
    DOC, DRIFT_DIR, LOG, commit, doc_citing, git, log_rows, new_repo,
    refs_repo, reports, run_drift, source, write,
)

COMPASS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "compass")


def finding(**cells):
    row = {c: "" for c in drift.COLUMNS}
    row.update(Class="changed", File="a.md", Line="3", **cells)
    return row


def table_rows(text):
    """The report's lines after the table's separator line, as a reader's line
    splitter sees them."""
    lines = text.splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith("|---"))
    return [line for line in lines[start + 1:] if line]


class CellEscapingTests(unittest.TestCase):
    def test_a_lone_carriage_return_in_a_cell_never_splits_the_row(self):
        """Adversarial where: `_cell` folds only CRLF and LF, so a lone CR in cited
        text starts a new line in the report and orphans the rest of the row
        from the table."""
        for sep in ("\r",):
            with self.subTest(sep=repr(sep)):
                row = finding(**{"Old text": f"before{sep}after"})
                text = drift.render_report([row], {"changed": 1}, "a" * 40,
                                           "2026-01-01 00:00:00")
                self.assertEqual(len(table_rows(text)), 1, repr(text))

    def test_a_pipe_in_cited_text_keeps_eight_cells(self):
        """Adversarial where: an unescaped `|` in old or current text shifts every
        later cell one column right."""
        row = finding(**{"Old text": "a | b || c", "Current text": "x|y"})
        line = table_rows(drift.render_report(
            [row], {"changed": 1}, None, "2026-01-01 00:00:00"))[0]
        unescaped = [i for i, ch in enumerate(line)
                     if ch == "|" and (i == 0 or line[i - 1] != "\\")]
        self.assertEqual(len(unescaped), len(drift.COLUMNS) + 1, line)

    def test_report_with_no_head_commit_says_so(self):
        """Adversarial where: `head` is None when the repository has no commit
        and the short-hash slice would raise."""
        text = drift.render_report([finding()], {"changed": 1}, None,
                                   "2026-01-01 00:00:00")
        self.assertIn("no commit", text)

    def test_crlf_source_lines_leave_no_carriage_return_in_the_report(self):
        """Adversarial where: a cited file with CRLF endings carries a trailing
        CR into old or current text that survives as a raw line break."""
        repo = new_repo(self)
        lines = [f"C{n} token" for n in range(1, 11)]
        (repo / "src").mkdir()
        (repo / "src" / "c.py").write_bytes(("\r\n".join(lines) + "\r\n").encode())
        write(repo, DOC, doc_citing("src/c.py:3-4"))
        commit(repo, "base", ".")
        lines[2], lines[3] = "C3 rewritten", "C4 rewritten"
        (repo / "src" / "c.py").write_bytes(("\r\n".join(lines) + "\r\n").encode())
        commit(repo, "edit", ".")
        code, _out, _err = run_drift(self, repo)
        self.assertEqual(code, 0)
        text = reports(repo)[0].read_bytes().decode("utf-8")
        self.assertNotIn("\r", text)
        self.assertEqual(len(table_rows(text)), 1, text)


class LatestOpenReportTests(unittest.TestCase):
    def read(self, *raw_lines):
        vault = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, vault, True)
        folder = vault / "archive" / "drift"
        folder.mkdir(parents=True)
        (folder / "log.jsonl").write_bytes("\n".join(raw_lines).encode("utf-8"))
        return drift.latest_open_report(str(vault))

    def test_damaged_and_foreign_lines_are_skipped_for_the_newest_valid_row(self):
        """Adversarial where: a truncated last line, a blank line, a JSON array
        or a bare string raised or masked the real latest row."""
        good = json.dumps({"report": "DRIFT-1.md", "counts": {"changed": 2}})
        found = self.read(good, "", '{"report": "DRIFT-2.md", "coun', "[1, 2]",
                          '"text"', "42", "null")
        self.assertEqual(found, ("DRIFT-1.md", 2))

    def test_clean_row_after_a_dirty_one_clears_the_report(self):
        """Adversarial where: scanning forward instead of from the end keeps the
        stale dirty row."""
        self.assertIsNone(self.read(
            json.dumps({"report": "DRIFT-1.md", "counts": {"changed": 1}}),
            json.dumps({"report": "clean", "counts": {}})))

    def test_non_string_or_empty_report_value_is_not_open(self):
        """Adversarial where: `report` of null, number, list or empty string was
        treated as a report name."""
        for value in (None, 7, ["DRIFT-1.md"], ""):
            with self.subTest(value=value):
                self.assertIsNone(self.read(json.dumps({"report": value})))

    def test_row_without_usable_counts_still_names_its_report(self):
        """Adversarial where: counts absent, null or a list made the total sum
        raise instead of reporting zero."""
        for counts in (None, [1, 2], "3", {"changed": "x"}):
            with self.subTest(counts=counts):
                self.assertEqual(
                    self.read(json.dumps({"report": "DRIFT-1.md", "counts": counts})),
                    ("DRIFT-1.md", 0))

    def test_latest_row_with_invalid_utf8_is_read_not_raised(self):
        """Adversarial where: stray bytes in the log raise UnicodeDecodeError."""
        vault = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, vault, True)
        folder = vault / "archive" / "drift"
        folder.mkdir(parents=True)
        (folder / "log.jsonl").write_bytes(
            b'{"report": "DRIFT-1.md", "counts": {"changed": 1}}\n\xff\xfe\n')
        self.assertEqual(drift.latest_open_report(str(vault)), ("DRIFT-1.md", 1))


class AppendTests(unittest.TestCase):
    def test_log_without_a_final_newline_keeps_both_rows_parseable(self):
        """Adversarial where: appending to a log whose last line lacks a newline
        glues the new JSON object onto the old one."""
        repo = refs_repo(self)[0]
        folder = repo / DRIFT_DIR
        folder.mkdir(parents=True)
        (repo / LOG).write_bytes(b'{"report": "clean", "counts": {}}')
        self.assertEqual(run_drift(self, repo)[0], 0)
        rows = log_rows(repo)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["report"], "clean")

    def test_log_ending_in_crlf_gets_no_blank_row_between(self):
        """Adversarial where: the missing-newline check misreads a CRLF ending
        and inserts an extra separator."""
        repo = refs_repo(self)[0]
        (repo / DRIFT_DIR).mkdir(parents=True)
        (repo / LOG).write_bytes(b'{"report": "clean", "counts": {}}\r\n')
        run_drift(self, repo)
        self.assertEqual(len(log_rows(repo)), 2)

    def test_report_name_collision_moves_the_stamp_on_and_keeps_the_old_file(self):
        """Adversarial where: a report name already taken is opened for writing,
        or the retry loop never leaves the taken stamp."""
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, folder, True)
        taken = folder / "DRIFT-20260101T000000000000Z.md"
        taken.write_text("original", encoding="utf-8")
        stamps = iter([datetime(2026, 1, 1, tzinfo=timezone.utc),
                       datetime(2026, 1, 1, 0, 0, 0, 1, tzinfo=timezone.utc)])

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return next(stamps)

        with mock.patch.object(drift, "datetime", Clock):
            name = drift._write_report(str(folder), "new")
        self.assertNotEqual(name, taken.name)
        self.assertEqual(taken.read_text(encoding="utf-8"), "original")
        self.assertEqual((folder / name).read_text(encoding="utf-8"), "new")


class ArgumentTests(unittest.TestCase):
    def test_base_from_forms(self):
        """Adversarial where: the `=` form, a missing value and an unknown value
        each take a different branch of `parse_args`."""
        self.assertEqual(drift.parse_args(["--base-from=add"]), (False, "add"))
        self.assertEqual(drift.parse_args(["--print", "--base-from", "add"]),
                         (True, "add"))
        for bad in (["--base-from"], ["--base-from=nope"], ["--base-from", ""],
                    ["--base-from", "--print"], ["extra"], ["--prnt"]):
            with self.subTest(args=bad), self.assertRaises(ValueError):
                drift.parse_args(bad)

    def test_bad_arguments_exit_1_and_write_nothing(self):
        """Adversarial where: arguments validated after the scan write a log row
        or report for a run that was refused."""
        repo = refs_repo(self)[0]
        for args in (["--base-from=nope"], ["--nope"]):
            with self.subTest(args=args):
                code, out, err = run_drift(self, repo, *args)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertTrue(err.strip())
        self.assertEqual(log_rows(repo), [])
        self.assertEqual(reports(repo), [])

    def test_base_from_add_runs_and_logs(self):
        """Adversarial where: the `add` base path is exercised only through the
        flag and raised when a ref has no add commit."""
        repo = refs_repo(self)[0]
        code, _out, err = run_drift(self, repo, "--base-from", "add")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(log_rows(repo)), 1)


class RepositoryShapeTests(unittest.TestCase):
    def test_repository_without_commits_exits_cleanly(self):
        """Adversarial where: `_head` returns None and blame, log or diff calls
        against a missing HEAD raise a traceback instead of a clean exit."""
        repo = new_repo(self)
        write(repo, DOC, doc_citing("src/c.py:2"))
        write(repo, "src/c.py", source("C"))
        try:
            code, out, err = run_drift(self, repo)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"traceback instead of an exit code: {exc!r}")
        self.assertIn(code, (0, 1))
        if code == 1:
            self.assertEqual(len(err.strip().splitlines()), 1, err)
        else:
            self.assertEqual(log_rows(repo)[0]["head"], None)

    def test_vault_below_the_repository_root_is_scanned_without_error(self):
        """Adversarial where: `_repo_root` joins the `--show-cdup` prefix to the
        project path and a project directory that is not the repo root breaks
        the join."""
        repo = new_repo(self)
        project = repo / "sub"
        write(project, "src/c.py", source("C"))
        write(project, DOC, doc_citing("src/c.py:2"))
        commit(repo, "base", ".")
        os.environ["CLAUDE_PROJECT_DIR"] = str(project)
        self.addCleanup(os.environ.pop, "CLAUDE_PROJECT_DIR", None)
        code, _out, err = run_drift(self, project)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(log_rows(project)), 1)

    def test_second_run_does_not_scan_its_own_report(self):
        """Adversarial where: the report quotes cited lines; if the next scan
        reads it, its findings and counts grow run over run."""
        repo, _base = refs_repo(self)
        run_drift(self, repo)
        run_drift(self, repo)
        run_drift(self, repo)
        rows = log_rows(repo)
        self.assertEqual(rows[0]["counts"], rows[2]["counts"])


class EncodingTests(unittest.TestCase):
    def test_print_with_non_ascii_text_on_a_narrow_stdout_does_not_crash(self):
        """Adversarial where: `sys.stdout.write` of text outside the console code
        page raises UnicodeEncodeError and the command dies mid-report."""
        repo = new_repo(self)
        lines = source("C")
        lines[1] = "C2 arrow → kana あ snowman ☃"
        write(repo, "src/c.py", lines)
        write(repo, DOC, doc_citing("src/c.py:2"))
        commit(repo, "base", ".")
        lines[1] = "C2 changed → あ"
        write(repo, "src/c.py", lines)
        commit(repo, "edit", ".")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo),
                   PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        done = subprocess.run([sys.executable, COMPASS, "drift", "--print"],
                              capture_output=True, env=env, cwd=str(repo))
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        self.assertNotIn(b"Traceback", done.stderr)

    def test_report_file_is_utf8_whatever_the_console_encoding(self):
        """Adversarial where: the report is written with the locale encoding and
        non-ASCII cited text is lost or raises on write."""
        repo = new_repo(self)
        lines = source("C")
        lines[1] = "C2 あ→"
        write(repo, "src/c.py", lines)
        write(repo, DOC, doc_citing("src/c.py:2"))
        commit(repo, "base", ".")
        lines[1] = "C2 ☃ changed"
        write(repo, "src/c.py", lines)
        commit(repo, "edit", ".")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo),
                   PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        done = subprocess.run([sys.executable, COMPASS, "drift"],
                              capture_output=True, env=env, cwd=str(repo))
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        text = reports(repo)[0].read_bytes().decode("utf-8")
        self.assertIn("☃", text)
        self.assertIn("あ", text)


class ZeroClassTests(unittest.TestCase):
    def test_print_lists_every_class_including_those_with_no_findings(self):
        """Adversarial where: counts are built from the findings only, so a class
        with zero findings is absent and a reader cannot tell it was checked
        from it being unsupported."""
        repo, _base = refs_repo(self)
        _code, out, _err = run_drift(self, repo, "--print")
        for name in drift.CLASS_ORDER:
            with self.subTest(cls=name):
                self.assertRegex(out, rf"(?m)^- {name}: \d+$")


if __name__ == "__main__":
    unittest.main()
