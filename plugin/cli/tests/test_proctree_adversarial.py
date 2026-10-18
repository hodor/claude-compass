"""Adversarial tests for proctree: handle lifetime, an orphaned descendant,
the no-job fallback, nested jobs, and kill/release racing each other.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import proctree  # noqa: E402
from tests.test_proctree import (  # noqa: E402
    SETTLE_SECONDS,
    _is_alive,
    _recorded_pids,
    _survivors,
    _reap_survivors,
    _wait_for_depth,
)

QUIET = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
WINDOWS = sys.platform == "win32"


def _handle_count():
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    count = wintypes.DWORD()
    kernel32.GetProcessHandleCount(kernel32.GetCurrentProcess(), ctypes.byref(count))
    return count.value


# Spawns one grandchild that records its pid and sleeps, records its own pid,
# and exits at once, orphaning the grandchild.
ORPHANER = """
import os, subprocess, sys
pid_dir = sys.argv[1]
subprocess.Popen(
    [sys.executable, "-c",
     "import os, sys, time; open(os.path.join(sys.argv[1], str(os.getpid())), 'w').close(); time.sleep(300)",
     pid_dir],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
open(os.path.join(pid_dir, str(os.getpid())), "w").close()
"""


class HandleLifetimeTests(unittest.TestCase):
    @unittest.skipUnless(WINDOWS, "job handles exist only on Windows")
    def test_two_hundred_sequential_kill_release_cycles_leak_no_handles(self):
        """Adversarial where: a job handle (or the OpenProcess handle in
        assign) is not closed on some path, so a long-lived caller that
        launches many children accumulates handles until the process dies."""
        def cycle(kill_first):
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                **QUIET, **proctree.popen_kwargs())
            job = proctree.assign(proc)
            if kill_first:
                proctree.kill(proc, job)
            proc.wait(timeout=SETTLE_SECONDS) if kill_first else None
            proctree.release(job)
            if not kill_first:
                proc.wait(timeout=SETTLE_SECONDS)
            proc.stdin and proc.stdin.close()

        cycle(True)  # warm up lazily created handles
        before = _handle_count()
        for index in range(200):
            cycle(kill_first=index % 20 == 0)
        grown = _handle_count() - before
        self.assertLess(grown, 20, f"{grown} handles leaked over 200 runs")

    @unittest.skipUnless(WINDOWS, "job handles exist only on Windows")
    def test_assigning_an_exited_process_returns_none_and_leaks_nothing(self):
        """Adversarial where: assign() on a child that already exited fails
        at AssignProcessToJobObject; the failure path must close both the
        job and the process handle and report None."""
        proc = subprocess.Popen([sys.executable, "-c", "pass"], **QUIET, **proctree.popen_kwargs())
        proc.wait(timeout=SETTLE_SECONDS)
        proctree.assign(proc)  # warm up
        before = _handle_count()
        results = [proctree.assign(proc) for _ in range(100)]
        grown = _handle_count() - before
        for job in results:
            proctree.release(job)
        self.assertLess(grown, 10, f"{grown} handles leaked across 100 failed assigns")
        self.assertEqual(
            [r for r in results if r is not None],
            [],
            "a job was returned for a process that had already exited",
        )


class FallbackAndOrphanTests(unittest.TestCase):
    def test_orphaned_grandchild_dies_when_the_job_is_killed(self):
        """Adversarial where: the child exits leaving a grandchild whose
        parent chain is broken, so `taskkill /T` cannot find it; only the job
        (Windows) or the process group (POSIX) still reaches it."""
        with tempfile.TemporaryDirectory(prefix="proctree-orphan-") as pid_dir:
            script = Path(pid_dir) / "orphaner.py"
            script.write_text(ORPHANER, encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, str(script), pid_dir], **QUIET, **proctree.popen_kwargs())
            job = proctree.assign(proc)
            try:
                self.assertTrue(_wait_for_depth(pid_dir, 2), "grandchild never started")
                proc.wait(timeout=SETTLE_SECONDS)
                proctree.kill(proc, job)
                survivors = _survivors(pid_dir)
                _reap_survivors(survivors)
                self.assertEqual(survivors, [], "an orphaned descendant survived the kill")
            finally:
                proctree.release(job)
                _reap_survivors([p for p in _recorded_pids(pid_dir) if _is_alive(p)])

    def test_orphaned_grandchild_dies_when_the_job_handle_closes(self):
        """Adversarial where: release() alone (the caller crashed or skipped
        kill) must still take the orphan down through kill-on-close."""
        if not WINDOWS:
            self.skipTest("kill-on-close is a Windows Job Object property")
        with tempfile.TemporaryDirectory(prefix="proctree-orphan-") as pid_dir:
            script = Path(pid_dir) / "orphaner.py"
            script.write_text(ORPHANER, encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, str(script), pid_dir], **QUIET, **proctree.popen_kwargs())
            job = proctree.assign(proc)
            try:
                self.assertTrue(_wait_for_depth(pid_dir, 2), "grandchild never started")
                proc.wait(timeout=SETTLE_SECONDS)
                proctree.release(job)
                survivors = _survivors(pid_dir)
                _reap_survivors(survivors)
                self.assertEqual(survivors, [], "the orphan outlived the job handle")
            finally:
                _reap_survivors([p for p in _recorded_pids(pid_dir) if _is_alive(p)])

    def test_kill_without_a_job_still_ends_a_settled_tree(self):
        """Adversarial where: when assign() returns None (job setup failed),
        kill(proc, None) must still reach children and grandchildren through
        taskkill /T or the group kill; a regression that only handles the job
        path leaves the whole tree running."""
        tree = textwrap.dedent("""
            import os, subprocess, sys, time
            level, pid_dir = int(sys.argv[1]), sys.argv[2]
            open(os.path.join(pid_dir, str(os.getpid())), "w").close()
            if level < 2:
                for _ in range(2):
                    subprocess.Popen([sys.executable, os.path.join(pid_dir, "t.py"),
                                      str(level + 1), pid_dir],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
            time.sleep(300)
        """)
        with tempfile.TemporaryDirectory(prefix="proctree-nojob-") as pid_dir:
            (Path(pid_dir) / "t.py").write_text(tree, encoding="utf-8")
            proc = subprocess.Popen(
                [sys.executable, str(Path(pid_dir) / "t.py"), "0", pid_dir],
                **QUIET, **proctree.popen_kwargs())
            try:
                self.assertTrue(_wait_for_depth(pid_dir, 7, timeout=30), "tree never settled")
                proctree.kill(proc, None)
                survivors = _survivors(pid_dir)
                _reap_survivors(survivors)
                self.assertEqual(survivors, [], "the no-job fallback left descendants alive")
            finally:
                _reap_survivors([p for p in _recorded_pids(pid_dir) if _is_alive(p)])


class ConcurrencyTests(unittest.TestCase):
    def test_kill_and_release_racing_from_two_threads_do_not_raise(self):
        """Adversarial where: clone's stop path kills a (proc, job) pair
        while the worker thread releases the same job; the handle is closed
        under the kill's feet or closed twice."""
        errors = []

        def guarded(fn, *args):
            try:
                fn(*args)
            except BaseException as exc:  # noqa: BLE001
                errors.append(repr(exc))

        for _ in range(5):
            proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                **QUIET, **proctree.popen_kwargs())
            job = proctree.assign(proc)
            killer = threading.Thread(target=guarded, args=(proctree.kill, proc, job))
            releaser = threading.Thread(target=guarded, args=(proctree.release, job))
            killer.start()
            releaser.start()
            killer.join()
            releaser.join()
            guarded(proctree.release, job)
            guarded(proctree.kill, proc, job)
            proc.wait(timeout=SETTLE_SECONDS)
        self.assertEqual(errors, [])


@unittest.skipUnless(WINDOWS, "nested Job Objects are a Windows concern")
class NestedJobTests(unittest.TestCase):
    def test_tree_kill_works_when_this_process_is_already_inside_a_job(self):
        """Adversarial where: the caller already runs inside a job that
        forbids breakaway (CI runners, IDE terminals); the new job is nested,
        and a platform or code path that cannot nest silently returns no job
        or fails to kill the grandchild."""
        runner = textwrap.dedent("""
            import ctypes, os, subprocess, sys, tempfile, time
            from ctypes import wintypes
            sys.path.insert(0, sys.argv[1])
            import proctree
            from tests.test_proctree import _survivors, _reap_survivors, _wait_for_depth

            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateJobObjectW.restype = wintypes.HANDLE
            k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
            k.GetCurrentProcess.restype = wintypes.HANDLE
            k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            k.SetInformationJobObject.argtypes = [
                wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
            outer = k.CreateJobObjectW(None, None)
            # Extended limits with no breakaway flag and no kill-on-close.
            buf = ctypes.create_string_buffer(144)
            assert k.SetInformationJobObject(outer, 9, buf, 144)
            assert k.AssignProcessToJobObject(outer, k.GetCurrentProcess())

            pid_dir = tempfile.mkdtemp(prefix="proctree-nested-")
            script = os.path.join(pid_dir, "t.py")
            open(script, "w").write(
                "import os, subprocess, sys, time\\n"
                "pd = sys.argv[1]\\n"
                "open(os.path.join(pd, str(os.getpid())), 'w').close()\\n"
                "if len(sys.argv) < 3:\\n"
                "    subprocess.Popen([sys.executable, __file__, pd, 'x'],"
                " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\\n"
                "time.sleep(300)\\n")
            proc = subprocess.Popen([sys.executable, script, pid_dir],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, **proctree.popen_kwargs())
            job = proctree.assign(proc)
            if job is None:
                print("NOJOB")
            ok = _wait_for_depth(pid_dir, 2, timeout=20)
            proctree.kill(proc, job)
            proctree.release(job)
            alive = _survivors(pid_dir)
            _reap_survivors(alive)
            print("DEPTH", ok, "ALIVE", len(alive))
        """)
        root = str(Path(__file__).resolve().parent.parent)
        result = subprocess.run(
            [sys.executable, "-c", runner, root],
            capture_output=True, text=True, timeout=120, cwd=root)
        self.assertIn("DEPTH True ALIVE 0", result.stdout, result.stdout + result.stderr)
        self.assertNotIn("NOJOB", result.stdout, "nesting inside an outer job returned no job")


if __name__ == "__main__":
    unittest.main()
