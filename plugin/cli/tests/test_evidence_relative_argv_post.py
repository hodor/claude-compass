"""Post-build tests for `evidencelib._start_argv` and the runs that use it.

Adversarial themes: path shapes the separator rewrite has to classify
(`..\\x`, mixed separators, drive-relative, UNC, rooted), a rewrite that
mutates the caller's argv list, a record or rerun that sees the rewritten
text, and a missing relative file that stops being exit 127."""

import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import evidencelib  # noqa: E402

WINDOWS = sys.platform == "win32"
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows path rules")
REL_PY = ".venv/Scripts/python.exe"
RAN = "post-relative-ran"


def git(repo, *args):
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture(scope="module")
def venv_template(tmp_path_factory):
    folder = tmp_path_factory.mktemp("post_venv") / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(folder)],
        check=True, capture_output=True,
    )
    return folder


@pytest.fixture
def repo(tmp_path, venv_template):
    """A committed repo with the venv at the root and `sub/deep` below it."""
    root = tmp_path / "repo"
    (root / ".compass").mkdir(parents=True)
    (root / "sub" / "deep").mkdir(parents=True)
    (root / ".compass" / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "sub" / "deep" / "f.txt").write_text("f", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    shutil.copytree(venv_template, root / ".venv")
    git(root, "add", "-f", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


def say():
    return ["-c", f"print({RAN!r})"]


def kept_output(root, slug):
    return (root / ".compass" / "evidence" / "TASK-441" / f"{slug}.out").read_bytes()


@windows_only
@pytest.mark.parametrize(
    "first",
    [
        "C:foo\\bar.exe",
        "C:foo/bar.exe",
        "\\\\host\\share\\x.exe",
        "//host/share/x.exe",
        "/rooted/x.exe",
        "\\rooted\\x.exe",
        "C:\\abs\\x.exe",
        "C:/abs/x.exe",
    ],
)
def test_drive_qualified_unc_and_rooted_first_words_pass_through(first, tmp_path):
    """Adversarial where: the drive-relative `C:foo\\bar`, a UNC share, or a
    rooted path being joined onto the cwd (yielding `<cwd>\\C:foo\\bar`)
    because the drive/root test misses one spelling."""
    argv = [first, "arg"]
    assert evidencelib._start_argv(argv, tmp_path) == argv


@windows_only
@pytest.mark.parametrize(
    "first",
    [
        "..\\x\\y.exe",
        "../x/y.exe",
        ".\\x\\y.exe",
        "./x/y.exe",
        "x\\y.exe",
        "x/y.exe",
        "x\\y/z.exe",
        "./x\\y/z.exe",
        "..\\x/y.exe",
    ],
)
def test_relative_first_words_join_onto_cwd_as_one_backslash_path(first, tmp_path):
    """Adversarial where: `..\\x`, `./x`, and mixed-separator spellings left
    unconverted or joined with a `/` left inside, so `CreateProcess` resolves
    them against the process's working directory."""
    cwd = tmp_path / "a" / "b"
    cwd.mkdir(parents=True)
    out = evidencelib._start_argv([first, "p/q"], cwd)
    expected = os.path.normpath(
        os.path.join(os.path.abspath(cwd), first.replace("/", "\\"))
    )
    assert out == [expected, "p/q"]
    assert "/" not in out[0]
    assert os.path.isabs(out[0])


@windows_only
def test_parent_form_climbs_out_of_the_cwd(tmp_path):
    """Adversarial where: normalisation skipped, leaving `<cwd>\\..\\x` or
    climbing the wrong number of levels."""
    cwd = tmp_path / "a" / "b"
    cwd.mkdir(parents=True)
    out = evidencelib._start_argv(["..\\..\\x.exe"], cwd)
    assert out == [str(tmp_path / "x.exe")]


@windows_only
def test_start_argv_does_not_mutate_the_callers_list(tmp_path):
    """Adversarial where: the rewrite assigning into `argv[0]` in place, so
    the record written afterwards holds the backslash-absolute text."""
    argv = ["x/y.exe", "a/b"]
    snapshot = list(argv)
    out = evidencelib._start_argv(argv, tmp_path)
    assert argv == snapshot
    assert out is not argv


def test_empty_argv_and_bare_names_come_back_unchanged(tmp_path):
    """Adversarial where: an empty argv raising IndexError on `argv[0]`, or a
    separator-free first word being joined onto the cwd."""
    assert evidencelib._start_argv([], tmp_path) == []
    assert evidencelib._start_argv(["git", "x/y"], tmp_path) == ["git", "x/y"]


@windows_only
def test_backslash_parent_form_runs_from_a_subfolder(repo):
    """Adversarial where: the `..\\` spelling (not `../`) resolved against the
    process's working directory, so a run from `sub/deep` cannot reach the
    root interpreter."""
    argv = ["..\\..\\" + REL_PY.replace("/", "\\"), *say()]
    record, _ = evidencelib.run_check(repo / "sub" / "deep", "TASK-441", "bsup", argv)
    assert record["exit_code"] == 0
    assert record["cwd"] == "sub/deep"
    assert record["argv"] == argv
    assert kept_output(repo, "bsup").strip() == RAN.encode()


@windows_only
def test_mixed_separator_first_word_runs_and_is_recorded_as_written(repo):
    """Adversarial where: a first word mixing `\\` and `/` taking a different
    path from the pure forms, or the record storing the normalised text."""
    argv = ["./.venv\\Scripts/python.exe", *say()]
    record, path = evidencelib.run_check(repo, "TASK-441", "mixed", argv)
    assert record["exit_code"] == 0
    assert record["argv"] == argv
    assert json.loads(path.read_text(encoding="utf-8"))["argv"] == argv


@windows_only
def test_rerun_from_a_nested_cwd_with_a_parent_relative_interpreter(repo):
    """Adversarial where: the rerun joining `../../.venv` onto the recorded
    `sub/deep` under the live repo rather than the scratch worktree, or under
    the worktree root, so the rerun exits 127 and mismatches."""
    argv = ["../../" + REL_PY, *say()]
    record, path = evidencelib.run_check(
        repo / "sub" / "deep", "TASK-441", "deeprr", argv
    )
    assert record["cwd"] == "sub/deep" and record["exit_code"] == 0
    result = evidencelib.rerun(path)
    assert result["verdict"] == "match"
    assert result["exit_code"] == 0
    assert json.loads(path.read_text(encoding="utf-8"))["argv"] == argv


@windows_only
@pytest.mark.parametrize(
    "first",
    [
        "missing/dir/x.exe",
        "..\\missing\\x.exe",
        "./missing/x.exe",
        "C:missing\\x.exe",
    ],
)
def test_relative_path_to_a_missing_file_records_127_and_the_argv_as_given(
    repo, first
):
    """Adversarial where: a start failure for the rewritten path escaping as
    an exception or the record carrying the joined absolute path instead of
    the argv as given."""
    argv = [first, "x/y"]
    record, path = evidencelib.run_check(repo / "sub", "TASK-441", "gone", argv)
    assert record["exit_code"] == evidencelib.NOT_STARTED_EXIT == 127
    assert record["argv"] == argv
    assert json.loads(path.read_text(encoding="utf-8"))["argv"] == argv
    assert kept_output(repo, "gone").strip() != b""


@windows_only
def test_rerun_of_a_missing_relative_file_matches_its_127(repo):
    """Adversarial where: the rerun path raising on the unstartable relative
    command instead of reporting exit 127 equal to the record."""
    _, path = evidencelib.run_check(
        repo / "sub", "TASK-441", "gonerr", ["nope/x.exe"]
    )
    result = evidencelib.rerun(path)
    assert result["exit_code"] == 127 == result["recorded_exit_code"]
    assert result["verdict"] == "match"
