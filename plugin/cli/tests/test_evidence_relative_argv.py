"""Tests for how `evidencelib` starts a command whose first word is a path.

Adversarial themes: a relative first word written with forward slashes that
Windows cannot start (recorded as exit 127), a conversion that also rewrites
later arguments or an absolute path, a record that stores the converted text
instead of the argv as given, a relative path resolved against the process's
working directory instead of the command's, and a missing file that stops being
reported as exit 127.

The relative interpreter is a tiny virtual environment (`--without-pip`)
created once and copied into each throwaway repo as `.venv`, so the command is
`.venv/Scripts/python.exe` relative to the repo, as a validator session writes
it. Tests that need a Windows interpreter layout are skipped elsewhere."""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evidencelib  # noqa: E402

WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(
    not WINDOWS, reason="the relative interpreter layout is Scripts/python.exe"
)
REL_PY = ".venv/Scripts/python.exe"
RAN = "relative-interpreter-ran"


def git(repo, *args):
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture(scope="module")
def venv_template(tmp_path_factory):
    folder = tmp_path_factory.mktemp("venv_template") / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(folder)],
        check=True, capture_output=True,
    )
    return folder


def make_repo(tmp_path, venv_template, venv_in="."):
    """A committed repo whose `venv_in` folder holds a copy of the venv."""
    root = tmp_path / "repo"
    (root / ".compass").mkdir(parents=True)
    (root / "sub").mkdir()
    (root / ".compass" / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "sub" / "f.txt").write_text("f", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    shutil.copytree(venv_template, root / venv_in / ".venv")
    git(root, "add", "-f", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


@pytest.fixture
def repo(tmp_path, venv_template):
    return make_repo(tmp_path, venv_template)


def say():
    return ["-c", f"print({RAN!r})"]


def kept_output(root, slug, task="TASK-441"):
    return (root / ".compass" / "evidence" / task / f"{slug}.out").read_bytes()


@windows_only
def test_relative_forward_slash_interpreter_starts_and_prints(repo):
    """Adversarial where: a first word `.venv/Scripts/python.exe` handed to
    `CreateProcess` as written, so the run records exit 127 with the system's
    'cannot find the file' text instead of starting the interpreter."""
    record, _ = evidencelib.run_check(repo, "TASK-441", "rel", [REL_PY, *say()])
    assert record["exit_code"] == 0
    assert kept_output(repo, "rel").strip() == RAN.encode()


@windows_only
def test_record_keeps_the_forward_slash_argv_as_given(repo):
    """Adversarial where: the separator conversion leaking into the record
    (returned dict or JSON file), so a rerun on POSIX starts a backslash path
    that does not exist there."""
    argv = [REL_PY, *say()]
    record, path = evidencelib.run_check(repo, "TASK-441", "keep", argv)
    assert record["argv"] == argv
    assert json.loads(path.read_text(encoding="utf-8"))["argv"] == argv
    assert record["exit_code"] == 0


@windows_only
def test_rerun_of_a_relative_forward_slash_record_matches(repo):
    """Adversarial where: `rerun` calling `_execute` with the recorded argv
    unconverted, or converting against the live repo instead of the scratch
    worktree, so a run that exited 0 reruns to a mismatch."""
    _, path = evidencelib.run_check(repo, "TASK-441", "again", [REL_PY, *say()])
    result = evidencelib.rerun(path)
    assert result["verdict"] == "match"
    assert result["exit_code"] == 0 == result["recorded_exit_code"]


@windows_only
def test_relative_path_resolves_against_the_command_cwd_not_the_process_cwd(
    tmp_path, venv_template, monkeypatch
):
    """Adversarial where: the relative first word resolved against the
    process's working directory (or the repo root) instead of the command's
    `cwd`, which fails for a command run from a subdirectory holding its own
    interpreter."""
    root = make_repo(tmp_path, venv_template, venv_in="sub")
    monkeypatch.chdir(tmp_path)
    record, _ = evidencelib.run_check(
        root / "sub", "TASK-441", "insub", [REL_PY, *say()]
    )
    assert record["cwd"] == "sub"
    assert record["exit_code"] == 0
    assert kept_output(root, "insub").strip() == RAN.encode()


@windows_only
def test_rerun_resolves_the_relative_path_in_the_worktree_subdirectory(
    tmp_path, venv_template, monkeypatch
):
    """Adversarial where: a rerun resolving the relative first word against
    the live subdirectory rather than `<worktree>/<cwd>`, which passes while
    the live repo exists and breaks in the scratch worktree."""
    root = make_repo(tmp_path, venv_template, venv_in="sub")
    monkeypatch.chdir(tmp_path)
    _, path = evidencelib.run_check(
        root / "sub", "TASK-441", "subagain", [REL_PY, *say()]
    )
    result = evidencelib.rerun(path)
    assert result["verdict"] == "match" and result["exit_code"] == 0


@windows_only
def test_parent_and_dot_relative_first_words_start(repo):
    """Adversarial where: the conversion handling only a bare `dir/file` shape,
    so `../.venv/...` (run from `sub`) and `./.venv/...` stay unstartable."""
    up, _ = evidencelib.run_check(
        repo / "sub", "TASK-441", "up", ["../" + REL_PY, *say()]
    )
    here, _ = evidencelib.run_check(
        repo, "TASK-441", "dot", ["./" + REL_PY, *say()]
    )
    assert (up["exit_code"], here["exit_code"]) == (0, 0)
    assert kept_output(repo, "up").strip() == RAN.encode()
    assert kept_output(repo, "dot").strip() == RAN.encode()


@windows_only
def test_backslash_relative_first_word_still_starts(repo):
    """Adversarial where: a first word already written with backslashes being
    doubled or mangled by the conversion, or left for `CreateProcess` to
    resolve against the process's working directory instead of the command's."""
    argv = [REL_PY.replace("/", "\\"), *say()]
    record, _ = evidencelib.run_check(repo, "TASK-441", "bs", argv)
    assert record["exit_code"] == 0
    assert record["argv"] == argv


@windows_only
def test_missing_relative_file_still_records_exit_127_with_the_system_message(repo):
    """Adversarial where: the conversion swallowing the start failure (exit 0
    or a crash) or raising instead of recording exit 127 and the operating
    system's message for a relative file that does not exist."""
    argv = [".venv/Scripts/nonexistent.exe", "x"]
    record, _ = evidencelib.run_check(repo, "TASK-441", "missing", argv)
    assert record["exit_code"] == evidencelib.NOT_STARTED_EXIT == 127
    assert record["argv"] == argv
    assert kept_output(repo, "missing").strip() != b""


def test_bare_command_name_runs_unchanged(repo):
    """Adversarial where: a first word with no separator being resolved
    against the cwd (or rejected), so `git --version` stops being found on
    PATH."""
    record, _ = evidencelib.run_check(repo, "TASK-441", "bare", ["git", "--version"])
    assert record["exit_code"] == 0
    assert kept_output(repo, "bare").startswith(b"git version")


def test_absolute_interpreter_path_runs_unchanged(repo):
    """Adversarial where: an absolute first word being re-joined onto the cwd
    or having its drive and separators mangled by the conversion."""
    record, _ = evidencelib.run_check(
        repo, "TASK-441", "abs", [sys.executable, *say()]
    )
    assert record["exit_code"] == 0
    assert kept_output(repo, "abs").strip() == RAN.encode()
    assert record["argv"][0] == sys.executable


def test_later_arguments_holding_slashes_pass_unchanged(repo):
    """Adversarial where: the separator conversion applied to every argument,
    rewriting `a/b/c.txt`, `./x`, and a `-c` program holding `/` into
    backslash text before the child sees it."""
    code = "import sys; print(sys.argv[1]); print(sys.argv[2]); print(10 / 4)"
    argv = [sys.executable, "-c", code, "a/b/c.txt", "./x/y"]
    record, _ = evidencelib.run_check(repo, "TASK-441", "args", argv)
    assert record["exit_code"] == 0
    lines = kept_output(repo, "args").decode().splitlines()
    assert lines == ["a/b/c.txt", "./x/y", "2.5"]
    assert record["argv"] == argv
