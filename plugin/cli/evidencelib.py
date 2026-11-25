"""Rerunnable evidence for a check: the command, the commit it ran at, and its
full output.

`run_check` executes a command from a directory inside a git repository and
writes two files under `<repo root>/.compass/evidence/<task>/`:

- `<check>.json`: the record (task, check, argv, cwd relative to the repo
  root, HEAD sha, tree state with the dirty paths, exit code, start and end
  time, Python version, `git --version`, sha256 of the output bytes).
- `<check>.out`: the command's stdout and stderr merged into one stream and
  stored byte for byte, never truncated.

`rerun` checks out the recorded sha into a scratch worktree under
`.claude/worktrees/evidence-<check>`, runs the recorded argv there, and
compares the result with the record. It writes nothing into the record.

A verdict line is the last line of an output when it starts with `REACH:`,
`ABLATE:` or `REQ:`. A rerun matches when the exit code and the verdict line
(absent on both sides counts as equal) are the same as recorded.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
from datetime import datetime
from pathlib import Path

EVIDENCE_DIR = Path(".compass") / "evidence"
VERDICT_PREFIXES = ("REACH:", "ABLATE:", "REQ:")
NOT_STARTED_EXIT = 127

_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9_-])?")
_SHA = re.compile(r"[0-9a-f]{4,64}")


class EvidenceError(Exception):
    """A request that is refused: bad name, no repository, unreadable record."""


def _check_name(kind, value):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise EvidenceError(
            f"invalid {kind} {value!r}: use letters, digits, '.', '_' and '-', "
            "starting and ending with a letter, digit, '_' or '-'"
        )


def validate_slug(slug):
    """Raise EvidenceError unless `slug` is a safe single path component."""
    _check_name("check name", slug)


def _validate_task(task):
    _check_name("task id", task)


def verdict_line(output_text):
    """The last line of `output_text` when it starts with a verdict prefix."""
    lines = output_text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return None
    last = lines[-1].rstrip("\r")
    return last if last.startswith(VERDICT_PREFIXES) else None


def tail_text(data, count):
    """The last `count` lines of `data` (bytes), decoded, newline separated."""
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    kept = [line.rstrip(b"\r") for line in lines[-count:]] if count > 0 else []
    return "\n".join(line.decode("utf-8", errors="replace") for line in kept)


def _git(cwd, *args):
    try:
        done = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, stdin=subprocess.DEVNULL
        )
    except OSError as error:
        raise EvidenceError(f"cannot run git in {cwd}: {error}")
    if done.returncode != 0:
        message = done.stderr.decode("utf-8", errors="replace").strip()
        raise EvidenceError(f"git {' '.join(args)} failed in {cwd}: {message}")
    return done.stdout


def repo_root(cwd):
    """`(root, relative cwd)` for a directory inside a git repository.

    The root keeps the form of the path given (it is the given directory with
    the repository prefix removed), and the relative cwd is a POSIX path, `.`
    at the root.
    """
    try:
        prefix = _git(cwd, "rev-parse", "--show-prefix").decode("utf-8").strip()
    except EvidenceError as error:
        raise EvidenceError(f"{cwd} is not inside a git repository ({error})")
    parts = [part for part in prefix.split("/") if part]
    root = Path(os.path.abspath(cwd))
    for _ in parts:
        root = root.parent
    return root, "/".join(parts) or "."


def _head_sha(root):
    return _git(root, "rev-parse", "HEAD").decode("utf-8").strip()


def _dirty_paths(root):
    raw = _git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    entries = raw.split(b"\0")
    paths = set()
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status = entry[:2].decode("ascii", errors="replace")
        path = entry[3:].decode("utf-8", errors="replace")
        if "R" in status or "C" in status:
            index += 1
        if path.startswith(EVIDENCE_DIR.as_posix() + "/"):
            continue
        paths.add(path)
    return sorted(paths)


def _start_argv(argv, cwd):
    """The argv handed to the operating system for `argv` run in `cwd`.

    On Windows a first word that is a relative path (it holds a separator and
    is not drive-qualified or rooted) is rewritten with backslashes and joined
    onto `cwd`, so `CreateProcess` finds it against the command's working
    directory. Any other argv, and every platform other than Windows, is
    returned unchanged.
    """
    if os.name != "nt" or not argv:
        return argv
    first = argv[0]
    if "/" not in first and "\\" not in first:
        return argv
    native = first.replace("/", "\\")
    if os.path.splitdrive(native)[0] or native.startswith("\\"):
        return argv
    return [os.path.normpath(os.path.join(os.path.abspath(cwd), native)), *argv[1:]]


def _execute(argv, cwd):
    """Run `argv` in `cwd`; `(exit code, merged output bytes, start, end)`."""
    started = datetime.now().astimezone()
    try:
        done = subprocess.run(
            _start_argv(argv, cwd),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )
        code, output = done.returncode, done.stdout
    except OSError as error:
        code, output = NOT_STARTED_EXIT, f"{error}\n".encode("utf-8")
    return code, output, started, datetime.now().astimezone()


def run_check(cwd, task, slug, argv):
    """Run `argv` from `cwd`, keep the record and output; `(record, json path)`.

    Every refusal happens before the command runs and before anything is
    written. A command that cannot be started is recorded with exit code 127
    and the operating system's message as its output.
    """
    validate_slug(slug)
    _validate_task(task)
    if not argv:
        raise EvidenceError("no command to run")
    root, relative_cwd = repo_root(cwd)
    sha = _head_sha(root)
    dirty = _dirty_paths(root)
    code, output, started, ended = _execute([str(a) for a in argv], Path(cwd))
    folder = root / EVIDENCE_DIR / task
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{slug}.out").write_bytes(output)
    record = {
        "task": task,
        "check": slug,
        "argv": list(argv),
        "cwd": relative_cwd,
        "sha": sha,
        "tree": "dirty" if dirty else "clean",
        "dirty_paths": dirty,
        "exit_code": code,
        "started": started.isoformat(),
        "ended": ended.isoformat(),
        "python": platform.python_version(),
        "git": _git(root, "--version").decode("utf-8").strip(),
        "output_sha256": hashlib.sha256(output).hexdigest(),
    }
    json_path = folder / f"{slug}.json"
    json_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record, json_path


def _read_record(path):
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise EvidenceError(f"cannot read record {path}: {error}")
    if not isinstance(record, dict):
        raise EvidenceError(f"record {path} is not a JSON object")
    return record


def _forget_readonly(function, path, _excinfo):
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _remove_worktree(root, worktree):
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        cwd=str(root), capture_output=True, stdin=subprocess.DEVNULL,
    )
    if worktree.exists():
        shutil.rmtree(worktree, onerror=_forget_readonly)
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=str(root), capture_output=True, stdin=subprocess.DEVNULL,
    )


def _recorded_fields(path, record):
    try:
        argv = [str(a) for a in record["argv"]]
        sha = str(record["sha"])
        cwd = str(record["cwd"])
        exit_code = int(record["exit_code"])
        check = str(record["check"])
        tree = record.get("tree")
    except (KeyError, TypeError, ValueError) as error:
        raise EvidenceError(f"record {path} is missing a field: {error}")
    parts = Path(cwd).parts
    if not argv or Path(cwd).is_absolute() or ".." in parts:
        raise EvidenceError(f"record {path} holds an unusable command or cwd")
    validate_slug(check)
    if not _SHA.fullmatch(sha):
        raise EvidenceError(f"record {path} holds a sha that is not hexadecimal: {sha!r}")
    return argv, sha, cwd, exit_code, check, tree


def rerun(record_path):
    """Rerun a record at its sha in a scratch worktree and compare.

    Returns a dict with `verdict` ("match" or "mismatch"), `exit_code`,
    `recorded_exit_code`, `last_line`, `recorded_last_line` (verdict lines or
    None) and `dirty_warning`.
    """
    path = Path(os.path.abspath(record_path))
    record = _read_record(path)
    argv, sha, cwd, recorded_code, check, tree = _recorded_fields(path, record)
    try:
        recorded_text = path.with_suffix(".out").read_bytes().decode(
            "utf-8", errors="replace"
        )
    except OSError as error:
        raise EvidenceError(f"cannot read the output kept for {path}: {error}")
    root, _ = repo_root(path.parent)
    worktree = root / ".claude" / "worktrees" / f"evidence-{check}"
    try:
        _remove_worktree(root, worktree)
        _git(root, "worktree", "add", "--detach", str(worktree), sha)
        code, output, _, _ = _execute(argv, worktree / cwd)
    finally:
        _remove_worktree(root, worktree)
    last_line = verdict_line(output.decode("utf-8", errors="replace"))
    recorded_last = verdict_line(recorded_text)
    same = code == recorded_code and last_line == recorded_last
    return {
        "verdict": "match" if same else "mismatch",
        "exit_code": code,
        "recorded_exit_code": recorded_code,
        "last_line": last_line,
        "recorded_last_line": recorded_last,
        "dirty_warning": tree == "dirty",
    }


def list_records(cwd, task):
    """The records of `task`, sorted by check; unreadable ones are flagged."""
    _validate_task(task)
    root, _ = repo_root(cwd)
    folder = root / EVIDENCE_DIR / task
    if not folder.is_dir():
        return []
    records = []
    for json_path in sorted(folder.glob("*.json"), key=lambda p: p.stem):
        try:
            record = _read_record(json_path)
        except EvidenceError:
            records.append({"check": json_path.stem, "unreadable": True})
        else:
            records.append(record)
    return records
