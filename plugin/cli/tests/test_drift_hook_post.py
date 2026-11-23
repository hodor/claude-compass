"""Adversarial tests for `compass drift --hook` aimed at branches of its
implementation: the usage-record opt-out in `maincli.dispatch`, the lock's
release on every way a detached scan can end, lock-file obstructions, a
concurrent start, a damaged run log or report, the `drift scan` doctor row on
a damaged log, and the hook's silence on stdout and stderr (SessionStart
output reaches the model's context).
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
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maincli  # noqa: E402
from commands import drift  # noqa: E402
from test_doctor import (  # noqa: E402
    drift_row, drift_scan_row, git_project,
)
from test_drift_hook import (  # noqa: E402
    DRIFT_DIR, LOCK, LOG, git, log_row, log_rows, make_lock,
    plain_repo, refs_repo, reports, run_drift, run_hook, write_log,
)

COMPASS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "compass")
USAGE_FILE = ".compass/meta/usage.yaml"


def usage_count(repo, command):
    path = Path(repo) / USAGE_FILE
    if not path.is_file():
        return 0
    found = re.search(rf"^  {re.escape(command)}:\n    count: (\d+)$",
                      path.read_text(encoding="utf-8"), re.MULTILINE)
    return int(found.group(1)) if found else 0


def parsed_log_rows(repo):
    rows = []
    for line in (Path(repo) / LOG).read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


class UsageRecordTests(unittest.TestCase):
    def test_only_the_hook_run_skips_the_usage_record(self):
        """Adversarial where: the opt-out leaks past `drift --hook` (a plain
        `drift` or `drift --print` stops counting as use), the hook still
        records itself (every session start inflates the count), or the
        opt-out silences other commands too. `usage` publishes no
        `records_usage`."""
        repo = plain_repo(self)
        run_hook(self, repo)
        self.assertEqual(usage_count(repo, "drift"), 0)
        run_drift(self, repo, "--print")
        self.assertEqual(usage_count(repo, "drift"), 1)
        run_drift(self, repo)
        self.assertEqual(usage_count(repo, "drift"), 2)
        run_hook(self, repo)
        self.assertEqual(usage_count(repo, "drift"), 2, "a second hook run recorded")
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(repo)}), \
                contextlib.redirect_stdout(io.StringIO()):
            maincli.main(["usage"])
        self.assertEqual(usage_count(repo, "usage"), 1)


class LockReleaseTests(unittest.TestCase):
    def _run_with_lock(self, repo, args, patches=()):
        lock = Path(repo) / LOCK
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("held", encoding="utf-8")
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {drift.LOCK_ENV: str(lock)}))
            for patch in patches:
                stack.enter_context(patch)
            code, _out, _err = run_drift(self, repo, *args)
        return code, lock

    def test_the_detached_scan_removes_the_lock_however_it_ends(self):
        """Adversarial where: the lock is removed only on the success path, so
        a scan that crashes or rejects its arguments leaves a lock that blocks
        every later session start for ten minutes."""
        rows = (
            ("clean run", plain_repo, (), False, 0),
            ("run with findings", refs_repo, (), False, 0),
            ("scan crashes", plain_repo, (), True, 1),
            ("bad argument", plain_repo, ("--bogus",), False, 1),
        )
        for name, build, args, crash, expected in rows:
            with self.subTest(name):
                repo = build(self)
                patches = (mock.patch.object(drift, "collect_records",
                                             side_effect=RuntimeError("scan crashed")),) \
                    if crash else ()
                code, lock = self._run_with_lock(repo, args, patches)
                self.assertEqual(code, expected)
                self.assertFalse(lock.exists())

    def test_a_scan_without_the_lock_variable_leaves_a_held_lock_alone(self):
        """Adversarial where: a person's own `compass drift` removes the lock
        a session-start scan holds, so a second scan starts beside it."""
        repo = plain_repo(self)
        lock = make_lock(repo, 0)
        with mock.patch.dict(os.environ):
            os.environ.pop(drift.LOCK_ENV, None)
            code, _out, _err = run_drift(self, repo)
        self.assertEqual(code, 0)
        self.assertTrue(lock.exists())

    def test_a_failed_spawn_releases_the_lock_and_still_exits_zero(self):
        """Adversarial where: Popen raising (interpreter path gone) leaves the
        lock taken with no scan running, or lets the OSError out of the hook."""
        repo = plain_repo(self)
        write_log(repo, [log_row("0" * 40)])
        real_popen = subprocess.Popen

        def refusing(argv, *args, **kwargs):
            if isinstance(argv, (list, tuple)) and "drift" in argv:
                raise FileNotFoundError("no interpreter")
            return real_popen(argv, *args, **kwargs)

        with mock.patch.object(subprocess, "Popen", refusing):
            code, out, _err = run_drift(self, repo, "--hook")
        self.assertEqual((code, out), (0, ""))
        self.assertFalse((Path(repo) / LOCK).exists())


class LockOwnershipTests(unittest.TestCase):
    def test_a_scan_whose_stale_lock_was_reclaimed_leaves_the_new_lock(self):
        """Adversarial where: a scan running past the stale bound has its lock
        reclaimed by a later hook, then its own exit removes the later scan's
        lock, so a third session start spawns a scan beside the second."""
        repo = plain_repo(self)
        lock = Path(repo) / LOCK
        lock.parent.mkdir(parents=True, exist_ok=True)
        first = drift._take_lock(str(lock))
        self.assertIsNotNone(first)
        stamp = time.time() - (drift.LOCK_STALE_SECONDS + 1)
        os.utime(lock, (stamp, stamp))
        second = drift._take_lock(str(lock))
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        env = {drift.LOCK_ENV: str(lock), drift.LOCK_TOKEN_ENV: first}
        with mock.patch.dict(os.environ, env):
            code, _out, _err = run_drift(self, repo)
        self.assertEqual(code, 0)
        self.assertTrue(lock.exists(), "the first scan removed the second scan's lock")
        self.assertEqual(lock.read_text(encoding="utf-8").strip(), second)
        with mock.patch.dict(os.environ, {drift.LOCK_ENV: str(lock),
                                          drift.LOCK_TOKEN_ENV: second}):
            code, _out, _err = run_drift(self, repo)
        self.assertEqual(code, 0)
        self.assertFalse(lock.exists(), "the owning scan left its lock behind")

    def test_the_spawned_scan_receives_the_token_the_hook_wrote(self):
        """Adversarial where: the hook writes one token and hands the scan
        another (or none), so the scan can never release its own lock."""
        repo = plain_repo(self)
        write_log(repo, [log_row("0" * 40)])
        _code, _out, spawned = run_hook(self, repo)
        self.assertEqual(len(spawned), 1)
        token = spawned[0][1]["env"][drift.LOCK_TOKEN_ENV]
        written = (Path(repo) / LOCK).read_text(encoding="utf-8").strip()
        self.assertEqual(token, written)


class LockBoundaryTests(unittest.TestCase):
    def test_staleness_bound_sits_between_599_and_601_seconds(self):
        """Adversarial where: the stale bound is off by a minute (a 599 s lock
        reclaimed, or a 601 s lock honoured)."""
        for name, age, spawns in (("599 s", 599, 0), ("601 s", 601, 1)):
            with self.subTest(name):
                repo = plain_repo(self)
                write_log(repo, [log_row("0" * 40)])
                make_lock(repo, age)
                code, out, spawned = run_hook(self, repo)
                self.assertEqual((code, out, len(spawned)), (0, "", spawns))

    def test_an_obstructed_lock_path_exits_zero_without_spawning(self):
        """Adversarial where: a lock path that is a directory, or a `tmp`
        that is a regular file, raises out of the hook instead of being
        swallowed, failing the session start."""
        for name in ("lock is a directory", "tmp is a file"):
            with self.subTest(name):
                repo = plain_repo(self)
                write_log(repo, [log_row("0" * 40)])
                lock = Path(repo) / LOCK
                if name == "lock is a directory":
                    lock.mkdir(parents=True)
                else:
                    lock.parent.write_text("not a folder", encoding="utf-8")
                code, out, spawned = run_hook(self, repo)
                self.assertEqual((code, out, spawned), (0, "", []))

    def test_simultaneous_session_starts_spawn_one_scan(self):
        """Adversarial where: the lock is checked then created (not created
        exclusively), so sessions starting together each pass the check and
        each start a scan."""
        for attempt in range(4):
            with self.subTest(attempt=attempt):
                repo = plain_repo(self)
                write_log(repo, [log_row("0" * 40)])
                real_popen = subprocess.Popen
                spawned = []
                barrier = threading.Barrier(6)

                def fake_popen(argv, *args, **kwargs):
                    if isinstance(argv, (list, tuple)) and "drift" in argv:
                        spawned.append(list(argv))
                        return mock.Mock(pid=1)
                    return real_popen(argv, *args, **kwargs)

                def start():
                    barrier.wait()
                    drift.run_hook()

                with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(repo)}), \
                        mock.patch.object(subprocess, "Popen", fake_popen):
                    threads = [threading.Thread(target=start) for _ in range(6)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(60)
                self.assertEqual(len(spawned), 1)


class DamagedRecordTests(unittest.TestCase):
    def test_a_torn_last_log_line_still_dedupes_and_is_skipped_by_the_hook(self):
        """Adversarial where: one torn log row (a crash mid-append) makes the
        scan stop deduping, or makes the hook read 'no row' and respawn on
        every session start although an earlier row names HEAD."""
        repo = refs_repo(self)
        run_drift(self, repo)
        self.assertEqual(len(reports(repo)), 1)
        with open(Path(repo) / LOG, "a", encoding="utf-8") as handle:
            handle.write('{"at": "2026-01-01T00:00:00Z", "he')
        code, out, spawned = run_hook(self, repo)
        self.assertEqual((code, out, spawned), (0, "", []))
        run_drift(self, repo)
        self.assertEqual(len(reports(repo)), 1, "a torn row broke the dedupe")
        self.assertTrue(parsed_log_rows(repo)[-1].get("same"))

    def test_a_log_holding_only_damaged_rows_counts_as_no_row(self):
        """Adversarial where: a log of garbage is read as 'HEAD unchanged' or
        crashes the hook, so a damaged log never heals."""
        for name, content in (("garbage", "{{{\nnot json\n"), ("array row", "[1, 2]\n")):
            with self.subTest(name):
                repo = plain_repo(self)
                path = Path(repo) / LOG
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                code, out, spawned = run_hook(self, repo)
                self.assertEqual((code, out, len(spawned)), (0, "", 1))

    def test_a_deleted_or_cut_report_makes_the_next_run_write_a_fresh_one(self):
        """Adversarial where: the log row says `same: true` and names a
        report file that no longer exists (or no longer parses), so the open
        findings have no report on disk."""
        for name in ("deleted", "cut before the table"):
            with self.subTest(name):
                repo = refs_repo(self)
                run_drift(self, repo)
                (first,) = reports(repo)
                if name == "deleted":
                    first.unlink()
                else:
                    first.write_text("# Drift report\n", encoding="utf-8")
                run_drift(self, repo)
                fresh = [p for p in reports(repo) if "## Findings" in p.read_text(encoding="utf-8")]
                self.assertEqual(len(fresh), 1)
                self.assertFalse(parsed_log_rows(repo)[-1].get("same"))


class DoctorRowOnDamagedLogTests(unittest.TestCase):
    def test_a_damaged_log_gives_one_row_and_never_a_failing_doctor(self):
        """Adversarial where: a torn or hand-edited log crashes doctor, turns
        the row FAIL, or drops it, so the one place a stale scan is visible
        goes dark. Rows: all-garbage bytes, a row whose date is unreadable, a
        row whose counts is not an object, a torn newest line over a valid
        older one."""
        project, _first, head = git_project(self)
        good = json.dumps(drift_row(head, 2, {"shifted": 4}))
        rows = (
            ("garbage bytes", b"\xff\xfe{{{\n\x00\x00", "WARN"),
            ("unreadable date", json.dumps({"at": "yesterday", "head": head,
                                            "counts": {"shifted": 1}}).encode(), "WARN"),
            ("counts is a list", json.dumps(drift_row(head, 2, [1, 2])).encode(), "OK"),
            ("torn newest over valid older", (good + '\n{"at": "20').encode(), "OK"),
        )
        for name, content, expected in rows:
            with self.subTest(name):
                path = project / ".compass" / "archive" / "drift" / "log.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                code, row = drift_scan_row()
                self.assertEqual((code, row["status"]), (0, expected))
                self.assertNotIn("\n", row["detail"])


class HookSilenceTests(unittest.TestCase):
    def _hook(self, repo, env_extra=None, cwd=None):
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo), **(env_extra or {})}
        return subprocess.run([sys.executable, COMPASS, "drift", "--hook"],
                              capture_output=True, text=True, env=env,
                              cwd=cwd or str(repo), timeout=120)

    def test_the_hook_prints_nothing_on_either_stream_in_every_environment(self):
        """Adversarial where: SessionStart injects a hook's stdout into the
        model's context, so any line the hook prints (a banner, a missing-git
        message, a traceback on stdout) pollutes every session. Run as a real
        process, because the stubbed tests share the test's own streams."""
        no_vault = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, no_vault, True)
        empty_path = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, empty_path, True)

        moved = plain_repo(self)
        write_log(moved, [log_row("0" * 40)])
        for name, repo, extra, cwd in (
            ("HEAD moved", moved, {}, None),
            ("no vault", no_vault, {}, str(no_vault)),
            ("no git on PATH", plain_repo(self), {"PATH": str(empty_path)}, None),
        ):
            with self.subTest(name):
                done = self._hook(repo, extra, cwd)
                self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))

    def test_the_hook_returns_before_the_scan_and_the_scan_then_clears_its_lock(self):
        """Adversarial where: the detached scan keeps the hook's pipes open
        (the hook's caller waits for the scan), the scan dies unseen in a vault
        with no `archive/drift` folder, or the scan ends without writing its
        log row or removing the lock."""
        repo = plain_repo(self)
        self.assertFalse((Path(repo) / DRIFT_DIR).exists())
        done = self._hook(repo)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        deadline = time.time() + 90
        while time.time() < deadline and (
                (Path(repo) / LOCK).exists() or not (Path(repo) / LOG).exists()):
            time.sleep(0.25)
        self.assertFalse((Path(repo) / LOCK).exists())
        self.assertEqual([r["head"] for r in log_rows(repo)], [git(repo, "rev-parse", "HEAD")])


if __name__ == "__main__":
    unittest.main()
