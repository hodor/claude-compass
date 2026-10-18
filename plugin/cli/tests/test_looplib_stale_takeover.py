"""Tests for `looplib.take_stale_lock` and the lock handling inside
`looplib.recover`: a lock judged stale is cleared without ever removing a lock
another runner created in the meantime.

`take_stale_lock(lock_path, timeout_s, now=None)` returns True when the lock is
gone afterwards because it was stale or absent, and False when it is live or
was replaced while it was judged. `recover` removes the stale lock it found and
leaves any other lock alone.

Adversarial themes: a fresh lock slipping in between the staleness judgment
and the removal, two recoverers working the same crashed loop, and tombstones
left behind.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import looplib  # noqa: E402

TIMEOUT_S = 91
STALE_LOCK = '{"pid": 1, "started": 1000.0}'
FRESH_LOCK = '{"pid": 4242, "started": 9999999999.0}'


class StaleTakeoverTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.loop_dir = self.base / "loop"
        self.loop_dir.mkdir()
        self.lock = self.base / "tmp" / "LOOP-001.lock"
        self.lock.parent.mkdir()
        self.definition = {"timeout_s": TIMEOUT_S, "max_budget_usd": 2.5}

    def write_lock(self, text):
        self.lock.write_text(text, encoding="utf-8")

    def tombstones(self):
        return [p.name for p in self.lock.parent.iterdir() if p.name != self.lock.name]

    def crash_left_state(self):
        looplib.write_state(self.loop_dir, {"state": "actuating", "run_id": "RUN-OLD"})

    def test_stale_lock_is_cleared_without_a_tombstone(self):
        """Adversarial where: the takeover leaves its tombstone behind, or
        reports a cleared lock while the file is still there."""
        self.write_lock(STALE_LOCK)
        self.assertTrue(looplib.take_stale_lock(self.lock, TIMEOUT_S))
        self.assertFalse(self.lock.exists())
        self.assertEqual(self.tombstones(), [])

    def test_absent_lock_counts_as_cleared(self):
        """Adversarial where: a lock another runner already cleared makes the
        takeover fail, so the second runner refuses a free loop."""
        self.assertTrue(looplib.take_stale_lock(self.lock, TIMEOUT_S))

    def test_live_lock_is_left_untouched(self):
        """Adversarial where: a lock inside its timeout is renamed away or
        deleted, so two runs hold the loop at once."""
        self.write_lock(FRESH_LOCK)
        self.assertFalse(looplib.take_stale_lock(self.lock, TIMEOUT_S))
        self.assertEqual(self.lock.read_text(encoding="utf-8"), FRESH_LOCK)
        self.assertEqual(self.tombstones(), [])

    def test_fresh_lock_that_slips_in_after_the_judgment_survives(self):
        """Adversarial where: the lock judged stale is replaced by a runner's
        fresh lock before the takeover moves it, and the takeover deletes the
        fresh one."""
        self.write_lock(STALE_LOCK)
        real_is_stale = looplib.is_stale

        def judge_then_replace(lock_path, timeout_s, now=None):
            verdict = real_is_stale(lock_path, timeout_s, now)
            self.write_lock(FRESH_LOCK)
            return verdict

        with mock.patch.object(looplib, "is_stale", judge_then_replace):
            self.assertFalse(looplib.take_stale_lock(self.lock, TIMEOUT_S))
        self.assertEqual(self.lock.read_text(encoding="utf-8"), FRESH_LOCK)
        self.assertEqual(self.tombstones(), [])

    def test_a_runner_that_took_the_lock_first_is_not_followed_by_a_delete(self):
        """Adversarial where: both callers judge the lock stale, the first
        clears it and takes a fresh one, and the second then deletes that
        fresh lock."""
        self.write_lock(STALE_LOCK)
        second_judged = []
        real_is_stale = looplib.is_stale

        def first_runner_wins(lock_path, timeout_s, now=None):
            verdict = real_is_stale(lock_path, timeout_s, now)
            if not second_judged:
                second_judged.append(verdict)
                self.assertTrue(looplib.take_stale_lock(self.lock, TIMEOUT_S))
                looplib.acquire_lock(self.lock, TIMEOUT_S)
            return verdict

        with mock.patch.object(looplib, "is_stale", first_runner_wins):
            self.assertFalse(looplib.take_stale_lock(self.lock, TIMEOUT_S))
        self.assertEqual(second_judged, [True])
        self.assertTrue(self.lock.exists())
        self.assertEqual(json.loads(self.lock.read_text(encoding="utf-8"))["pid"], os.getpid())
        self.assertEqual(self.tombstones(), [])

    def test_recover_removes_the_stale_lock_it_found(self):
        """Adversarial where: recovering a crash-left loop leaves the stale
        lock in place, so every later run is refused by a lock nobody holds."""
        self.crash_left_state()
        self.write_lock(STALE_LOCK)
        self.assertTrue(looplib.recover(self.loop_dir, self.lock, self.definition))
        self.assertFalse(self.lock.exists())
        self.assertEqual(self.tombstones(), [])
        self.assertEqual(looplib.read_state(self.loop_dir)["state"], "idle")

    def test_recover_keeps_a_lock_another_runner_took_during_recovery(self):
        """Adversarial where: a second recoverer finishes first and starts a
        run under a fresh lock, and the slower recoverer deletes that lock when
        it ends its own recovery."""
        self.crash_left_state()
        self.write_lock(STALE_LOCK)
        real_append = looplib.append_ledger
        replaced = []

        def append_then_other_runner_locks(loop_dir, row):
            real_append(loop_dir, row)
            if not replaced:
                replaced.append(True)
                self.write_lock(FRESH_LOCK)

        with mock.patch.object(looplib, "append_ledger", append_then_other_runner_locks):
            self.assertTrue(looplib.recover(self.loop_dir, self.lock, self.definition))
        self.assertEqual(self.lock.read_text(encoding="utf-8"), FRESH_LOCK)
        self.assertEqual(self.tombstones(), [])

    def test_recover_by_the_lock_holder_neither_judges_nor_removes_the_lock(self):
        """Adversarial where: the process that holds the run lock is refused
        by its own live lock, or its recovery deletes the lock it is running
        under, letting a second runner in."""
        self.crash_left_state()
        looplib.acquire_lock(self.lock, TIMEOUT_S)
        held = self.lock.read_bytes()
        self.assertTrue(
            looplib.recover(self.loop_dir, self.lock, self.definition, lock_held=True)
        )
        self.assertEqual(self.lock.read_bytes(), held)
        self.assertEqual(looplib.read_state(self.loop_dir)["state"], "idle")
        rows, _skipped = looplib.read_ledger(self.loop_dir)
        self.assertEqual([r["outcome"] for r in rows if r.get("type") == "run"], ["crashed"])

    def test_recover_does_not_remove_a_lock_that_appeared_after_it_started(self):
        """Adversarial where: recovery began with no lock file, and a lock
        created by another runner meanwhile is deleted at the end."""
        self.crash_left_state()
        real_append = looplib.append_ledger

        def append_then_other_runner_locks(loop_dir, row):
            real_append(loop_dir, row)
            self.write_lock(FRESH_LOCK)

        with mock.patch.object(looplib, "append_ledger", append_then_other_runner_locks):
            self.assertTrue(looplib.recover(self.loop_dir, self.lock, self.definition))
        self.assertEqual(self.lock.read_text(encoding="utf-8"), FRESH_LOCK)


CONTENDER = r"""
import json
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
import looplib

lock, marker, rounds = sys.argv[2], sys.argv[3], int(sys.argv[4])
acquired = violations = 0
errors = []
for _ in range(rounds):
    try:
        looplib.acquire_lock(lock, 91)
    except looplib.LockHeld:
        try:
            looplib.is_stale(lock, 91)
            looplib.take_stale_lock(lock, 91)
        except Exception as exc:
            errors.append(repr(exc))
        time.sleep(0.002)
        continue
    except Exception as exc:
        errors.append(repr(exc))
        continue
    acquired += 1
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        violations += 1
    else:
        time.sleep(0.003)
        os.remove(marker)
    try:
        looplib.release_lock(lock)
    except Exception as exc:
        errors.append(repr(exc))
print(json.dumps({"acquired": acquired, "violations": violations, "errors": errors}))
"""


class ContentionTests(unittest.TestCase):
    def test_processes_contending_for_a_stale_lock_never_share_it_or_fail(self):
        """Adversarial where: processes reading, deleting and creating the
        same lock file collide (PermissionError on Windows), two of them take
        the lock at once after a stale takeover, a release leaves the lock
        behind, or a takeover leaves a tombstone."""
        import subprocess

        base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, base, True)
        lock = base / "LOOP-001.lock"
        marker = base / "inside.marker"
        lock.write_text(STALE_LOCK, encoding="utf-8")
        script = base / "contender.py"
        script.write_text(CONTENDER, encoding="utf-8")
        procs = [
            subprocess.Popen(
                [sys.executable, str(script), CLI_DIR, str(lock), str(marker), "60"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(4)
        ]
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, err)
            results.append(json.loads(out))
        self.assertEqual([r["errors"] for r in results], [[]] * 4)
        self.assertEqual(sum(r["violations"] for r in results), 0)
        self.assertGreater(sum(r["acquired"] for r in results), 0)
        self.assertEqual(sorted(p.name for p in base.iterdir() if p.name.startswith("LOOP-001")), [])
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
