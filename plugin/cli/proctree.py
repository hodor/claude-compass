"""Launch a child as the root of its own process tree and kill the whole tree.

On POSIX the child starts in a new session, so `os.killpg` reaches every
descendant. On Windows the child starts in a new process group and is placed
in a kill-on-close Job Object right after `Popen`; terminating the job, or
closing its handle, ends the child and every descendant, including one
spawned while the kill runs, which `taskkill /T` alone can miss. `taskkill /T`
remains the fallback when no job could be set up.

Typical use:

    proc = subprocess.Popen(argv, **proctree.popen_kwargs())
    job = proctree.assign(proc)
    try:
        ...                        # on timeout or interrupt: proctree.kill(proc, job)
    finally:
        proctree.release(job)

A descendant the child starts before `assign` returns is outside the job;
`taskkill /T` still reaches it through the parent chain. `taskkill` can fail
on a loaded machine ("Call cancelled", "Quota violation") without ending any
process; when it does, the tree is walked through a process snapshot taken in
this process and each descendant is terminated directly.
"""

import os
import subprocess
import sys
import threading

KILL_WAIT_SECONDS = 30

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_TH32CS_SNAPPROCESS = 0x00000002
_TASKKILL_PROCESS_NOT_FOUND = 128
_SNAPSHOT_PASSES = 5


def popen_kwargs():
    """The `Popen` keyword arguments that make the child lead its own tree."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


class WindowsJob:
    """A Windows Job Object that owns a process and every descendant it
    starts. `create()` returns None when the job cannot be set up."""

    def __init__(self, handle, kernel32):
        self._handle = handle
        self._kernel32 = kernel32
        self._lock = threading.Lock()

    @classmethod
    def create(cls):
        if sys.platform != "win32":
            return None
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            kernel32.CloseHandle(handle)
            return None
        return cls(handle, kernel32)

    def assign(self, pid):
        """Put the process `pid` in the job. Returns False when it cannot."""
        process = self._kernel32.OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        if not process:
            return False
        try:
            return bool(self._kernel32.AssignProcessToJobObject(self._handle, process))
        finally:
            self._kernel32.CloseHandle(process)

    def terminate(self):
        """End every process in the job. Returns False when it could not."""
        with self._lock:
            if not self._handle:
                return False
            return bool(self._kernel32.TerminateJobObject(self._handle, 1))

    def close(self):
        """Close the handle; the job's remaining processes are killed."""
        with self._lock:
            if self._handle:
                self._kernel32.CloseHandle(self._handle)
                self._handle = None


def assign(proc):
    """Place `proc` in a new kill-on-close job. Returns the job, or None on
    POSIX or when the job could not be set up or the assignment failed."""
    try:
        job = WindowsJob.create()
    except Exception:
        return None
    if job is None:
        return None
    try:
        assigned = job.assign(proc.pid)
    except Exception:
        assigned = False
    if not assigned:
        job.close()
        return None
    return job


def release(job):
    """Close `job` if there is one. Any process still in it is killed."""
    if job is not None:
        job.close()


def _process_parents():
    """Map every running pid to its parent pid from a process snapshot, or
    None when the snapshot cannot be taken (Windows only)."""
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return None
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        parents = {}
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            parents[entry.th32ProcessID] = entry.th32ParentProcessID
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return parents
    finally:
        kernel32.CloseHandle(snapshot)


def _terminate_pid(pid):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(_PROCESS_TERMINATE, False, pid)
    if not handle:
        return
    try:
        kernel32.TerminateProcess(handle, 1)
    finally:
        kernel32.CloseHandle(handle)


def _terminate_descendants(root_pid):
    """Terminate every descendant of `root_pid` found through the parent
    chain of a process snapshot. The snapshot is taken again after each pass,
    so a descendant started while the pass ran is found by the next one."""
    for _ in range(_SNAPSHOT_PASSES):
        parents = _process_parents()
        if parents is None:
            return
        found = {root_pid}
        grew = True
        while grew:
            grew = False
            for pid, parent in parents.items():
                if parent in found and pid not in found:
                    found.add(pid)
                    grew = True
        found.discard(root_pid)
        if not found:
            return
        for pid in found:
            _terminate_pid(pid)


def _kill_windows_tree(pid):
    """End the tree rooted at `pid` with `taskkill /T /F`; when taskkill
    fails or times out, walk the tree and terminate it directly."""
    try:
        result = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=KILL_WAIT_SECONDS,
        )
        if result.returncode in (0, _TASKKILL_PROCESS_NOT_FOUND):
            return
    except (OSError, subprocess.SubprocessError):
        pass
    _terminate_descendants(pid)


def kill(proc, job=None):
    """Kill `proc` and everything it started. A Windows `job` holding the
    child is terminated; when that succeeds the whole tree is gone. Without a
    job, or when the termination fails, `taskkill /T` with a snapshot walk as
    its backstop (Windows) or a group kill (POSIX) reaches the tree. The child
    itself is killed last."""
    if job is not None and job.terminate():
        try:
            proc.kill()
        except OSError:
            pass
        return
    try:
        if sys.platform == "win32":
            _kill_windows_tree(proc.pid)
        else:
            import signal

            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass
