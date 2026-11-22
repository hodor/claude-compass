"""Tests for `compass drift`: the report, the run log and the `drift_open`
validate warning.

The command is dispatched through `maincli.main`, as a user runs it. Every
test builds its own temporary git repository holding a `.compass/` vault and
points `CLAUDE_PROJECT_DIR` at it; nothing reads a live vault.

Contract under test
-------------------
* A run scans code references, index lines and catalog rows. Findings are
  every record the scanners return except those of class `unchanged` and
  `changed-elsewhere`.
* A run with findings writes `.compass/archive/drift/DRIFT-<UTC>.md`: it opens
  with a count per class, then one row per finding carrying the citing file,
  the line, the base commit, the old text, the current text, the class and
  the proposal. A row is one line of the report.
* Every run, clean or not, appends exactly one JSON object line to
  `.compass/archive/drift/log.jsonl`: the HEAD commit, the counts per class
  and the report's file name, or the word `clean` when there was no report.
  The log's field names are not fixed here; the helpers below find a value by
  what it is, never by its key.
* `--print` writes the report text to stdout and writes no file, log row
  included.
* Exit 0 whatever was found. Exit 1, with one line on stderr, when git is
  unavailable or there is no vault.
* After a run, `compass validate` carries a `drift_open` warning naming the
  report when the latest log row names one, and nothing once a later row is
  `clean`.

Adversarial themes: a report overwritten by a second run in the same second,
a log rewritten instead of appended, a log row written by `--print`, a clean
run mistaken for no run, a stale `drift_open` after the drift was fixed,
counts that drift from the rows, and a report that feeds its own next scan.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from commands import validate  # noqa: E402

DOC = ".compass/specs/s.md"
INDEX = ".compass/index.md"
CATALOG = ".compass/meta/lessons-catalog.yaml"
SPEC = ".compass/specs/SPEC-001-alpha.md"
LESSON = ".compass/lessons/LESSON-a.md"
DRIFT_DIR = ".compass/archive/drift"
LOG = f"{DRIFT_DIR}/log.jsonl"


def git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return done.stdout.strip()


def write(repo, rel, lines):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def commit(repo, message, *paths):
    git(repo, "add", "-A", "--", *paths)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def new_repo(case):
    repo = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, repo, True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Tester")
    git(repo, "config", "user.email", "tester@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def source(prefix, count=10):
    return [f"{prefix}{n} token" for n in range(1, count + 1)]


def doc_citing(*cited):
    """A vault document with each reference in `cited` as a code span on its
    own line, starting at line 3."""
    return ["# Spec", ""] + [f"See `{c}`." for c in cited]


def run_drift(case, repo, *args, env=None):
    """Dispatch `compass drift` against `repo`; return (code, stdout, stderr)."""
    saved = {k: os.environ.get(k) for k in ("CLAUDE_PROJECT_DIR", *(env or {}))}
    os.environ["CLAUDE_PROJECT_DIR"] = str(repo)
    os.environ.update(env or {})
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = maincli.main(["drift", *args])
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return code, out.getvalue(), err.getvalue()


def reports(repo):
    folder = Path(repo) / DRIFT_DIR
    return sorted(folder.glob("DRIFT-*.md")) if folder.is_dir() else []


def log_rows(repo):
    path = Path(repo) / LOG
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def names_head(row, head):
    """Whether a value of `row`, whatever its key, is `head` (full or an
    abbreviation of at least 7 characters)."""
    return any(isinstance(v, str) and len(v) >= 7 and head.startswith(v)
               for v in row.values())


def counts_of(row):
    """The per-class counts of `row`: its one dict of integers."""
    found = [v for v in row.values()
             if isinstance(v, dict) and all(isinstance(n, int) for n in v.values())]
    return found[0] if found else {}


def report_name_of(row):
    """The report file name `row` names, or `clean`."""
    for value in row.values():
        if isinstance(value, str) and (value == "clean" or "DRIFT-" in value):
            return value.replace("\\", "/").rsplit("/", 1)[-1]
    return None


def class_token(name):
    return re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")


def count_token(number):
    return re.compile(rf"(?<![\w.]){number}(?![\w.])")


def row_lines(text, marker):
    return [line for line in text.splitlines() if marker in line]


def header_of(text, first_row_marker):
    """The report's lines before the first line carrying `first_row_marker`."""
    out = []
    for line in text.splitlines():
        if first_row_marker in line:
            break
        out.append(line)
    return out


def refs_repo(case):
    """Repo with three shifted refs, two changed refs, one unchanged ref.

    src/a.py gets two lines inserted above the cited lines (A5, A6, A7 shift
    to 7, 8, 9), src/b.py has lines 3 and 4 rewritten, src/c.py is untouched.
    Returns (repo, base_commit)."""
    repo = new_repo(case)
    write(repo, "src/a.py", source("A"))
    write(repo, "src/b.py", source("B"))
    write(repo, "src/c.py", source("C"))
    write(repo, DOC, doc_citing(
        "src/a.py:5", "src/a.py:6", "src/a.py:7",
        "src/b.py:3", "src/b.py:4", "src/c.py:2"))
    base = commit(repo, "base", ".")
    a = source("A")
    write(repo, "src/a.py", ["new one", "new two"] + a)
    b = source("B")
    b[2], b[3] = "B3 rewritten", "B4 rewritten"
    write(repo, "src/b.py", b)
    commit(repo, "edit", ".")
    return repo, base


def clean_repo(case):
    """Repo whose one reference still points at the line it cited."""
    repo = new_repo(case)
    write(repo, "src/c.py", source("C"))
    write(repo, DOC, doc_citing("src/c.py:2"))
    commit(repo, "base", ".")
    return repo


class ReportTests(unittest.TestCase):
    def test_findings_write_one_report_opening_with_a_count_per_class(self):
        """Adversarial where: counts computed from a different pass than the
        rows (a class counted twice, a non-finding class counted), counts
        placed after the rows, or a report that exits non-zero because it
        found something. Distinct counts (3 and 2) make a swapped pair fail,
        and the unchanged reference must add no row and no count."""
        repo, _ = refs_repo(self)
        code, _, _ = run_drift(self, repo)
        self.assertEqual(code, 0)
        written = reports(repo)
        self.assertEqual(len(written), 1, written)
        text = written[0].read_text(encoding="utf-8")
        header = header_of(text, DOC)
        self.assertTrue(any(class_token("shifted").search(l) and count_token(3).search(l)
                            for l in header), header)
        self.assertTrue(any(class_token("changed").search(l) and count_token(2).search(l)
                            for l in header), header)
        self.assertNotIn("C2 token", text)

    def test_each_finding_row_carries_both_texts_the_base_and_the_proposal(self):
        """Adversarial where: a row that names the class but not the old and
        current text forces the reader to open another file; a base commit
        dropped from the row; a shifted row that omits where the text now
        sits. The row is found by the unique old text it quotes."""
        repo, base = refs_repo(self)
        run_drift(self, repo)
        text = reports(repo)[0].read_text(encoding="utf-8")

        shifted = row_lines(text, "A5 token")
        self.assertEqual(len(shifted), 1, shifted)
        for needle in (DOC, base[:7]):
            self.assertIn(needle, shifted[0])
        self.assertTrue(class_token("shifted").search(shifted[0]), shifted[0])
        self.assertTrue(count_token(7).search(shifted[0]), "new line of the cited text")
        self.assertTrue(count_token(3).search(shifted[0]), "line of the citation")

        changed = row_lines(text, "B3 token")
        self.assertEqual(len(changed), 1, changed)
        for needle in (DOC, base[:7], "B3 rewritten"):
            self.assertIn(needle, changed[0])
        self.assertTrue(class_token("changed").search(changed[0]), changed[0])

    def test_index_and_catalog_findings_join_the_counts_and_rows(self):
        """Adversarial where: the command wired to the reference scanner only,
        so index lines and catalog rows never reach the report; the three
        scanners' records merged under one class; a catalog row reported
        without both of its values."""
        repo, _ = refs_repo(self)
        write(repo, INDEX, ["# Index", "", "## Specs", "",
                            "- [[SPEC-001-alpha]] - Alpha does Y"])
        write(repo, SPEC, ["---", "title: Alpha", "summary: Alpha does X", "---", "", "Body."])
        write(repo, CATALOG, [
            "lessons:", '  - file: "LESSON-a.md"', "    status: active",
            "    category: process", "    area: testing", "    tags: [a]",
            "    score: 3", '    summary: "Plain"'])
        write(repo, LESSON, [
            "---", "status: active", "category: process", "area: testing",
            "tags: [a]", "score: 9", "summary: Plain", "---", "", "Body."])
        commit(repo, "vault", ".compass")
        code, _, _ = run_drift(self, repo)
        self.assertEqual(code, 0)
        row = log_rows(repo)[0]
        counts = counts_of(row)
        self.assertEqual(
            {k: counts.get(k, 0) for k in ("shifted", "changed", "index-drift", "catalog-drift")},
            {"shifted": 3, "changed": 2, "index-drift": 1, "catalog-drift": 1}, counts)
        text = reports(repo)[0].read_text(encoding="utf-8")
        index_row = row_lines(text, "Alpha does Y")
        self.assertEqual(len(index_row), 1, index_row)
        self.assertIn("Alpha does X", index_row[0])
        self.assertTrue(class_token("index-drift").search(index_row[0]), index_row[0])
        catalog_row = row_lines(text, "lessons-catalog.yaml")
        self.assertEqual(len(catalog_row), 1, catalog_row)
        self.assertTrue(class_token("catalog-drift").search(catalog_row[0]), catalog_row[0])
        for number in (3, 9):
            self.assertTrue(count_token(number).search(catalog_row[0]), catalog_row[0])


class LogTests(unittest.TestCase):
    def test_dirty_run_appends_one_row_naming_head_counts_and_the_report(self):
        """Adversarial where: a log row that names a report that was not
        written, counts that disagree with the report, a HEAD taken before
        the scan, or a row written as pretty-printed multi-line JSON so one
        run spans several lines."""
        repo, _ = refs_repo(self)
        run_drift(self, repo)
        rows = log_rows(repo)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertTrue(names_head(row, git(repo, "rev-parse", "HEAD")), row)
        counts = counts_of(row)
        self.assertEqual((counts.get("shifted"), counts.get("changed")), (3, 2), counts)
        self.assertEqual(report_name_of(row), reports(repo)[0].name)

    def test_clean_run_logs_clean_and_writes_no_report(self):
        """Adversarial where: a clean run that writes nothing, so "ran and
        found nothing" cannot be told from "never ran"; or one that writes an
        empty report; or counts that are nonzero because an unchanged
        reference was counted as drift."""
        repo = clean_repo(self)
        code, _, _ = run_drift(self, repo)
        self.assertEqual(code, 0)
        self.assertEqual(reports(repo), [])
        rows = log_rows(repo)
        self.assertEqual(len(rows), 1)
        self.assertEqual(report_name_of(rows[0]), "clean")
        self.assertTrue(names_head(rows[0], git(repo, "rev-parse", "HEAD")), rows[0])
        self.assertEqual(sum(counts_of(rows[0]).values()), 0)

    def test_second_run_appends_and_leaves_the_first_row_byte_identical(self):
        """Adversarial where: a log opened for write instead of append, or
        rewritten as a whole with the new row added, which loses the first
        row's bytes; and a report whose own cited text feeds the next scan so
        the second run counts more than the first."""
        repo, _ = refs_repo(self)
        run_drift(self, repo)
        before = (Path(repo) / LOG).read_bytes()
        run_drift(self, repo)
        after = (Path(repo) / LOG).read_bytes()
        self.assertTrue(after.startswith(before))
        rows = log_rows(repo)
        self.assertEqual(len(rows), 2)
        self.assertEqual(counts_of(rows[0]), counts_of(rows[1]))

    def test_second_dirty_run_never_overwrites_the_first_report(self):
        """Adversarial where: report names that carry whole seconds only, so
        two runs a moment apart name the same file and the second overwrites
        the first; the Data rule says a report is never replaced. The repo
        gains a finding between the runs, so an overwrite changes the bytes."""
        repo, _ = refs_repo(self)
        run_drift(self, repo)
        first = reports(repo)[0]
        first_bytes = first.read_bytes()
        c = source("C")
        c[1] = "C2 rewritten"
        write(repo, "src/c.py", c)
        commit(repo, "touch c", ".")
        run_drift(self, repo)
        self.assertEqual(len(reports(repo)), 2)
        self.assertEqual(first.read_bytes(), first_bytes)
        names = [report_name_of(r) for r in log_rows(repo)]
        self.assertEqual(len(set(names)), 2, names)
        for name in names:
            self.assertTrue((Path(repo) / DRIFT_DIR / name).is_file(), name)


class PrintFlagTests(unittest.TestCase):
    def test_print_shows_counts_on_stdout_and_writes_nothing(self):
        """Adversarial where: `--print` still writing a report or a log row,
        so a look at the findings changes what `compass validate` says; or
        printing nothing because the report was never built."""
        repo, _ = refs_repo(self)
        code, out, _ = run_drift(self, repo, "--print")
        self.assertEqual(code, 0)
        self.assertFalse((Path(repo) / DRIFT_DIR).exists())
        self.assertTrue(any(class_token("shifted").search(l) and count_token(3).search(l)
                            for l in out.splitlines()), out)
        self.assertTrue(any(class_token("changed").search(l) and count_token(2).search(l)
                            for l in out.splitlines()), out)

    def test_print_after_a_real_run_leaves_log_and_reports_untouched(self):
        """Adversarial where: `--print` appending a log row when a log
        already exists (the missing-directory case above cannot see it), or
        adding a second report next to the first."""
        repo, _ = refs_repo(self)
        run_drift(self, repo)
        log_before = (Path(repo) / LOG).read_bytes()
        names_before = [p.name for p in reports(repo)]
        run_drift(self, repo, "--print")
        self.assertEqual((Path(repo) / LOG).read_bytes(), log_before)
        self.assertEqual([p.name for p in reports(repo)], names_before)


class FailureTests(unittest.TestCase):
    def one_line_error(self, code, out, err, names):
        """One stderr line that says why: it names `names` (a lowercase
        fragment), so a command that is not registered at all fails too."""
        self.assertEqual(code, 1)
        self.assertIn(names, err.lower())
        self.assertNotIn("not implemented", err)
        self.assertEqual(out, "")
        self.assertEqual(len([l for l in err.splitlines() if l.strip()]), 1, err)
        self.assertNotIn("Traceback", err)

    def test_directory_without_git_exits_1_with_one_line_and_writes_nothing(self):
        """Adversarial where: a vault outside any repository crashing with a
        traceback, exiting 0 as if clean (and logging `clean`), or exiting 2,
        which would block the user's write if the command ever ran from a
        hook. The temp directory's parent is a git ceiling so no outer
        repository is found."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        write(tmp, DOC, doc_citing("src/c.py:2"))
        code, out, err = run_drift(
            self, tmp, env={"GIT_CEILING_DIRECTORIES": str(tmp.parent)})
        self.one_line_error(code, out, err, "git")
        self.assertFalse((tmp / DRIFT_DIR).exists())

    def test_git_missing_from_the_path_exits_1_with_one_line(self):
        """Adversarial where: the subprocess launch failing (git not found)
        escaping as an unhandled exception message of several lines instead
        of the one-line exit 1 the contract promises."""
        repo = clean_repo(self)
        code, out, err = run_drift(self, repo, env={"PATH": ""})
        self.one_line_error(code, out, err, "git")
        self.assertEqual(log_rows(repo), [])

    def test_no_vault_exits_1_with_one_line(self):
        """Adversarial where: a project with no `.compass/` crashing or
        creating `.compass/archive/drift/` out of nothing."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        git(tmp, "init", "-q")
        saved = os.getcwd()
        self.addCleanup(os.chdir, saved)
        os.chdir(tmp)
        code, out, err = run_drift(self, tmp)
        self.one_line_error(code, out, err, "vault")
        self.assertFalse((tmp / ".compass").exists())


class ValidateDriftOpenTests(unittest.TestCase):
    def shifted_repo(self):
        """Repo whose one reference points at a line that has since moved."""
        repo = new_repo(self)
        write(repo, "src/a.py", source("A"))
        write(repo, DOC, doc_citing("src/a.py:5"))
        write(repo, ".compass/index.md", ["# Index"])
        write(repo, ".compass/active.md", ["# Active"])
        commit(repo, "base", ".")
        return repo

    def open_findings(self, repo):
        _, warnings = validate.check_vault(Path(repo) / ".compass")
        return [w for w in warnings if w.startswith("drift_open:")]

    def test_warning_names_the_report_and_clears_after_a_later_clean_run(self):
        """Adversarial where: no warning although the latest run left a
        report; a warning that names no report; a warning that outlives the
        fix because validate reads the first log row or any report on disk
        rather than the latest row. The fix re-cites the shifted line in a
        new commit, so the next run classifies it unchanged."""
        repo = self.shifted_repo()
        self.assertEqual(self.open_findings(repo), [], "no log yet, nothing to warn about")

        write(repo, "src/a.py", ["new one"] + source("A"))
        commit(repo, "shift", ".")
        run_drift(self, repo)
        found = self.open_findings(repo)
        self.assertEqual(len(found), 1, found)
        self.assertIn(reports(repo)[0].name, found[0])

        write(repo, DOC, doc_citing("src/a.py:6"))
        commit(repo, "recite", ".compass/specs")
        run_drift(self, repo)
        self.assertEqual(report_name_of(log_rows(repo)[-1]), "clean")
        self.assertEqual(self.open_findings(repo), [])
        self.assertEqual(len(reports(repo)), 1, "the old report stays on disk")

    def test_validate_prints_the_warning_as_a_sentence_ending_in_its_code(self):
        """Adversarial where: the warning present in `check_vault` but missing
        from the printed lines, or printed in the raw `code: details` form."""
        repo = self.shifted_repo()
        write(repo, "src/a.py", ["new one"] + source("A"))
        commit(repo, "shift", ".")
        run_drift(self, repo)
        saved = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(repo)
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                validate.run([])
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = saved
        lines = [l.strip() for l in err.getvalue().splitlines() if "(drift_open)" in l]
        self.assertEqual(len(lines), 1, err.getvalue())
        self.assertFalse(lines[0].removeprefix("warning").strip().startswith("drift_open:"))
        self.assertIn(reports(repo)[0].name, lines[0])


if __name__ == "__main__":
    unittest.main()
