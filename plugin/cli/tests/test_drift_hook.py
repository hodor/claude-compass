"""Tests for `compass drift --hook` and the run-dedupe of a plain `compass drift`.

Contract under test
-------------------
* `--hook` reads the newest row of `.compass/archive/drift/log.jsonl`. When
  that row's HEAD is the current HEAD it exits 0 having written and spawned
  nothing. Otherwise (HEAD moved, empty log, absent log) it takes
  `.compass/tmp/drift.lock`, spawns one detached `compass drift` process and
  returns at once, without scanning.
* The lock is created exclusively and is stale after 10 minutes: a fresh lock
  blocks the spawn, an older one does not.
* A hook never fails a session start (exit 0 without git) and prints nothing,
  since SessionStart output reaches the model's context.
* A run without `--print` writes a new report only when its finding set
  (class, file, line, cites) differs from the latest report's; otherwise its
  log row names the latest report and carries `same: true`.

The spawn is stubbed by wrapping `subprocess.Popen`: only a call whose argv
holds `drift` is recorded and faked, so the git calls the command makes still
run for real. Every test builds its own temporary git repository.

Adversarial themes: a hook that scans inline instead of detaching, a hook
that spawns `--hook` again (a loop), a lock that is never refreshed so every
session respawns, HEAD compared against any row instead of the newest, a hook
that writes before it knows HEAD moved, and a dedupe that compares counts or
HEAD instead of the finding set.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402

DOC = ".compass/specs/s.md"
DRIFT_DIR = ".compass/archive/drift"
LOG = f"{DRIFT_DIR}/log.jsonl"
LOCK = ".compass/tmp/drift.lock"
MINUTE = 60


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


def commit(repo, message):
    git(repo, "add", "-A", "--", ".")
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


def refs_repo(case):
    """A repo whose vault document cites two changed references (src/b.py
    lines 3 and 4) and one unchanged one (src/c.py line 2)."""
    repo = new_repo(case)
    write(repo, "src/b.py", source("B"))
    write(repo, "src/c.py", source("C"))
    write(repo, DOC, ["# Spec", "", "See `src/b.py:3`.", "See `src/b.py:4`.",
                      "See `src/c.py:2`."])
    commit(repo, "base")
    b = source("B")
    b[2], b[3] = "B3 rewritten", "B4 rewritten"
    write(repo, "src/b.py", b)
    commit(repo, "edit b")
    return repo


def plain_repo(case):
    """A repo with one commit and a vault holding no findings."""
    repo = new_repo(case)
    write(repo, "src/a.py", source("A"))
    write(repo, ".compass/index.md", ["# Index"])
    commit(repo, "base")
    return repo


def run_drift(case, repo, *args):
    """Dispatch `compass drift` against `repo`; return (code, stdout, stderr)."""
    saved = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(repo)
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = maincli.main(["drift", *args])
    finally:
        if saved is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved
    return code, out.getvalue(), err.getvalue()


def run_hook(case, repo):
    """Run `compass drift --hook` with the drift spawn stubbed; return
    (code, stdout, spawned) where `spawned` is a list of (argv, kwargs)."""
    real_popen = subprocess.Popen
    spawned = []

    def fake_popen(argv, *args, **kwargs):
        if isinstance(argv, (list, tuple)) and "drift" in argv:
            spawned.append((list(argv), kwargs))
            return mock.Mock(pid=4242)
        return real_popen(argv, *args, **kwargs)

    with mock.patch.object(subprocess, "Popen", fake_popen):
        code, out, _err = run_drift(case, repo, "--hook")
    return code, out, spawned


def log_row(head, at=None, report="clean"):
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at or time.time()))
    return {"at": stamp, "head": head, "counts": {"shifted": 0}, "report": report}


def write_log(repo, rows):
    path = Path(repo) / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def log_rows(repo):
    path = Path(repo) / LOG
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def reports(repo):
    folder = Path(repo) / DRIFT_DIR
    return sorted(folder.glob("DRIFT-*.md")) if folder.is_dir() else []


def vault_files(repo):
    """Every file under the repo's `.compass/` with its bytes."""
    root = Path(repo) / ".compass"
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def make_lock(repo, age_seconds):
    path = Path(repo) / LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("held", encoding="utf-8")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))
    return path


class HookGateTests(unittest.TestCase):
    def test_hook_compares_head_with_the_newest_log_row_only(self):
        """Adversarial where: the hook compares HEAD against any row of the
        log instead of the newest one, or writes (a lock, a row) before it
        knows HEAD moved. Rows: newest row at HEAD does nothing even though an
        older row names another commit; newest row at an old commit spawns
        even though an older row names HEAD."""
        repo = plain_repo(self)
        old = git(repo, "rev-parse", "HEAD")
        write(repo, "src/a.py", source("A") + ["A11 token"])
        head = commit(repo, "move")
        self.assertNotEqual(old, head)

        write_log(repo, [log_row(old), log_row(head)])
        before = vault_files(repo)
        code, out, spawned = run_hook(self, repo)
        self.assertEqual((code, out, spawned), (0, "", []))
        self.assertEqual(vault_files(repo), before)

        write_log(repo, [log_row(head), log_row(old)])
        code, out, spawned = run_hook(self, repo)
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(len(spawned), 1)

    def test_empty_or_absent_log_spawns(self):
        """Adversarial where: a log with no row is read as 'HEAD unchanged'
        (None == None) or crashes the hook on the empty read, so a fresh
        install never gets its first scan."""
        for name, content in (("absent", None), ("empty file", ""),
                              ("blank lines only", "\n\n")):
            with self.subTest(name):
                repo = plain_repo(self)
                if content is not None:
                    path = Path(repo) / LOG
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                code, out, spawned = run_hook(self, repo)
                self.assertEqual((code, out), (0, ""))
                self.assertEqual(len(spawned), 1)

    def test_a_vault_without_git_exits_zero_and_spawns_nothing(self):
        """Adversarial where: the hook lets the missing-git error of a plain
        run (exit 1, stderr) reach a session start, which would fail it."""
        repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, repo, True)
        write(repo, ".compass/index.md", ["# Index"])
        code, out, spawned = run_hook(self, repo)
        self.assertEqual((code, out, spawned), (0, "", []))
        self.assertFalse((Path(repo) / LOCK).exists())


class HookSpawnTests(unittest.TestCase):
    def test_moved_head_spawns_one_detached_scan_and_returns_before_it_ends(self):
        """Adversarial where: the hook scans inline (a log row or a report
        exists when it returns), spawns the hook command itself (a respawn
        loop), spawns a `--print` scan that writes nothing, attaches the child
        to the session, or leaves no lock behind so the next session spawns
        again."""
        repo = refs_repo(self)
        write_log(repo, [log_row("0" * 40)])
        rows_before = log_rows(repo)
        code, out, spawned = run_hook(self, repo)
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(len(spawned), 1)
        argv, kwargs = spawned[0]
        self.assertIn("drift", argv)
        self.assertNotIn("--hook", argv)
        self.assertNotIn("--print", argv)
        if sys.platform == "win32":
            self.assertTrue(kwargs.get("creationflags", 0) & subprocess.DETACHED_PROCESS)
        else:
            self.assertTrue(kwargs.get("start_new_session"))
        self.assertEqual(log_rows(repo), rows_before)
        self.assertEqual(reports(repo), [])
        self.assertTrue((Path(repo) / LOCK).is_file())

    def test_lock_blocks_until_it_is_ten_minutes_old(self):
        """Adversarial where: the staleness bound is off by a minute either
        way (a 9-minute lock ignored, an 11-minute one honoured), a lock
        stolen without being refreshed so the next hook respawns at once, or
        no lock taken so two sessions starting together both scan."""
        for name, age, spawns in (("fresh", 0, 0), ("9 minutes", 9 * MINUTE, 0),
                                  ("11 minutes", 11 * MINUTE, 1)):
            with self.subTest(name):
                repo = plain_repo(self)
                write_log(repo, [log_row("0" * 40)])
                lock = make_lock(repo, age)
                code, out, spawned = run_hook(self, repo)
                self.assertEqual((code, out), (0, ""))
                self.assertEqual(len(spawned), spawns)
                if spawns:
                    self.assertGreater(lock.stat().st_mtime, time.time() - 5 * MINUTE)
                    _, _, again = run_hook(self, repo)
                    self.assertEqual(again, [])


class FindingSetDedupeTests(unittest.TestCase):
    def test_identical_findings_write_one_report_and_two_log_rows(self):
        """Adversarial where: the dedupe compares HEAD or the log counts
        instead of the finding set, so a run after an unrelated commit writes
        a second 400-row report; or the second row loses the name of the
        report it repeats; or the first row claims `same`."""
        repo = refs_repo(self)
        run_drift(self, repo)
        write(repo, "src/other.py", source("O"))
        new_head = commit(repo, "unrelated")
        run_drift(self, repo)
        files = reports(repo)
        rows = log_rows(repo)
        self.assertEqual(len(files), 1)
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0].get("same"), True)
        self.assertIs(rows[1].get("same"), True)
        self.assertEqual(rows[1]["report"], files[0].name)
        self.assertEqual(rows[1]["head"], new_head)

    def test_any_change_to_the_finding_set_writes_a_new_report(self):
        """Adversarial where: the comparison looks only at the count, so a
        finding that appears while another disappears, or one that moves to
        another line of its document, goes unreported. Rows: a finding added,
        a finding removed, and every finding moved down one line."""
        def add_finding(repo):
            c = source("C")
            c[1] = "C2 rewritten"
            write(repo, "src/c.py", c)
            commit(repo, "touch c")

        def remove_finding(repo):
            write(repo, DOC, ["# Spec", "", "See `src/b.py:3`.", "See `src/c.py:2`."])
            commit(repo, "drop a cite")

        def move_findings(repo):
            text = (Path(repo) / DOC).read_text(encoding="utf-8")
            write(repo, DOC, ["an added intro line"] + text.splitlines())
            commit(repo, "add a line above")

        for name, change in (("added", add_finding), ("removed", remove_finding),
                             ("moved", move_findings)):
            with self.subTest(name):
                repo = refs_repo(self)
                run_drift(self, repo)
                first = reports(repo)[0]
                first_bytes = first.read_bytes()
                change(repo)
                run_drift(self, repo)
                files = reports(repo)
                rows = log_rows(repo)
                self.assertEqual(len(files), 2)
                self.assertEqual(first.read_bytes(), first_bytes)
                self.assertNotEqual(rows[1].get("same"), True)
                self.assertEqual(rows[1]["report"], files[-1].name)

