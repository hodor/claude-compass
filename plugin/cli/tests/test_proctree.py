"""Tests for proctree: launching a child as the root of its own process tree
and killing the whole tree.

The kill tests build a three-level tree (root, children, grandchildren)
whose members keep spawning new descendants while the kill runs, then assert
no member of the tree is alive afterwards. Six trees run in parallel.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import proctree  # noqa: E402

PARALLEL_TREES = 6
SETTLE_SECONDS = 15

# Argv: level, pid directory. Every process records its pid as a file in the
# directory. Levels 0 and 1 start two children at once and then one more every
# 100 ms, so new descendants keep appearing while a kill runs; level 2 sleeps.
TREE_SCRIPT = """
import os, subprocess, sys, time
level, pid_dir = int(sys.argv[1]), sys.argv[2]
open(os.path.join(pid_dir, str(os.getpid())), "w").close()
if level >= 2:
    time.sleep(300)
    sys.exit(0)

def spawn():
    subprocess.Popen(
        [sys.executable, os.path.join(pid_dir, "tree.py"), str(level + 1), pid_dir],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

spawn()
spawn()
for _ in range(60):
    time.sleep(0.1)
    spawn()
"""


def _is_alive(pid):
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            # ERROR_INVALID_PARAMETER: no such process. Any other failure
            # (access denied) leaves the process alive.
            return ctypes.get_last_error() != 87
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[-1].split()[0]
    except OSError:
        ps = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
        )
        stat = ps.stdout.strip()[:1]
    return bool(stat) and stat != "Z"


def _recorded_pids(pid_dir):
    return [int(name) for name in os.listdir(pid_dir) if name.isdigit()]


def _start_tree(pid_dir):
    script = Path(pid_dir) / "tree.py"
    script.write_text(TREE_SCRIPT, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script), "0", str(pid_dir)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **proctree.popen_kwargs(),
    )
    return proc, proctree.assign(proc)


def _wait_for_depth(pid_dir, minimum, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(_recorded_pids(pid_dir)) >= minimum:
            return True
        time.sleep(0.05)
    return False


def _survivors(pid_dir):
    """The recorded pids still alive after SETTLE_SECONDS, re-listed each
    poll so a descendant recorded late is counted too."""
    deadline = time.monotonic() + SETTLE_SECONDS
    alive = []
    while time.monotonic() < deadline:
        alive = [pid for pid in _recorded_pids(pid_dir) if _is_alive(pid)]
        if not alive:
            return []
        time.sleep(0.1)
    return alive


def _reap_survivors(pids):
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, 9)
        except OSError:
            pass


class KillTreeTests(unittest.TestCase):
    def _run_one(self, results, index, release_only):
        pid_dir = Path(tempfile.mkdtemp(prefix="proctree-"))
        proc, job = _start_tree(pid_dir)
        try:
            if not _wait_for_depth(pid_dir, 6):
                results[index] = ["tree never reached six members"]
                return
            time.sleep(0.2)
            if release_only:
                proctree.release(job)
            else:
                proctree.kill(proc, job)
                proctree.release(job)
            try:
                proc.wait(timeout=SETTLE_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            survivors = _survivors(pid_dir)
            results[index] = survivors
            _reap_survivors(survivors)
        finally:
            proctree.kill(proc, job)
            proctree.release(job)
            for name in os.listdir(pid_dir):
                try:
                    os.remove(pid_dir / name)
                except OSError:
                    pass
            try:
                os.rmdir(pid_dir)
            except OSError:
                pass

    def _run_parallel(self, release_only):
        results = [None] * PARALLEL_TREES
        threads = [
            threading.Thread(target=self._run_one, args=(results, i, release_only))
            for i in range(PARALLEL_TREES)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return results

    def test_three_level_tree_killed_with_no_survivor_in_parallel(self):
        results = self._run_parallel(release_only=False)
        for index, survivors in enumerate(results):
            self.assertEqual(survivors, [], f"tree {index} left survivors")

    @unittest.skipUnless(sys.platform == "win32", "kill-on-close is a Windows Job Object property")
    def test_releasing_the_job_kills_the_tree(self):
        results = self._run_parallel(release_only=True)
        for index, survivors in enumerate(results):
            self.assertEqual(survivors, [], f"tree {index} survived the job handle closing")


class AssignTests(unittest.TestCase):
    def test_assign_returns_a_job_only_on_windows(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **proctree.popen_kwargs(),
        )
        job = None
        try:
            job = proctree.assign(proc)
            if sys.platform == "win32":
                self.assertIsNotNone(job)
            else:
                self.assertIsNone(job)
        finally:
            proctree.kill(proc, job)
            proctree.release(job)
            proc.wait(timeout=SETTLE_SECONDS)

    def test_kill_and_release_accept_no_job(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **proctree.popen_kwargs(),
        )
        proctree.kill(proc, None)
        proctree.release(None)
        proc.wait(timeout=SETTLE_SECONDS)
        self.assertIsNotNone(proc.returncode)

    def test_kill_after_the_child_exited_does_not_raise(self):
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **proctree.popen_kwargs(),
        )
        proc.wait(timeout=SETTLE_SECONDS)
        proctree.kill(proc, None)


if __name__ == "__main__":
    unittest.main()
