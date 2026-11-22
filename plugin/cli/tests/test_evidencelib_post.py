"""Tests for the branches `evidencelib` and `commands.evidence` contain beyond
their stated contract.

Adversarial themes: a command that cannot be started recorded as a real exit
code, a leftover scratch worktree of every shape that can occur, a record whose
sha the repository does not hold, the exit codes `rerun` returns, and the exact
edge of the check-name pattern."""

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import evidencelib  # noqa: E402

PY = sys.executable
DRIVER = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from commands import evidence; sys.exit(evidence.run(sys.argv[2:]))"
)


def git(repo, *args):
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "value.txt").write_text("3", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


def py(code, *rest):
    return [PY, "-c", code, *rest]


def cli(cwd, *args):
    return subprocess.run(
        [PY, "-c", DRIVER, CLI_DIR, *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8",
    )


def evidence_worktrees(repo):
    return [
        line for line in git(repo, "worktree", "list", "--porcelain").splitlines()
        if "evidence-" in line
    ]


def force_remove(function, path, _excinfo):
    os.chmod(path, 0o700)
    function(path)


def test_unstartable_command_is_recorded_with_exit_127_and_reruns_as_a_match(repo):
    """Adversarial where: an executable that does not exist raising out of
    `run_check` (no record kept), or recorded with an exit code a rerun cannot
    reproduce, or a rerun of it reported as a mismatch."""
    record, path = evidencelib.run_check(
        repo, "TASK-403", "ghost", ["no-such-executable-0f3a", "arg"]
    )
    kept = path.with_suffix(".out").read_bytes()
    assert record["exit_code"] == 127
    assert kept.strip() != b""
    assert record["output_sha256"] == hashlib.sha256(kept).hexdigest()
    result = evidencelib.rerun(path)
    assert result["verdict"] == "match"
    assert result["exit_code"] == 127

    done = cli(
        repo, "run", "--task", "TASK-403", "--check", "ghost2", "--",
        "no-such-executable-0f3a",
    )
    assert done.returncode == 127
    assert "record: .compass/evidence/TASK-403/ghost2.json" in done.stdout
    assert "Traceback" not in done.stderr


@pytest.mark.parametrize(
    "leftover", ["registered-with-junk", "plain-directory", "registered-then-deleted"]
)
def test_rerun_clears_a_leftover_scratch_worktree_of_any_shape(repo, leftover):
    """Adversarial where: a scratch worktree left by an interrupted rerun
    (still registered with git, a bare directory, or registered with its
    directory gone) making `git worktree add` fail or letting stale files leak
    into the rerun."""
    _, path = evidencelib.run_check(
        repo, "TASK-403", "again",
        py("import os; print('REQ: ' + str(os.path.exists('stale.txt')))"),
    )
    stale = repo / ".claude" / "worktrees" / "evidence-again"
    if leftover == "plain-directory":
        stale.mkdir(parents=True)
        (stale / "stale.txt").write_text("junk", encoding="utf-8")
    else:
        git(repo, "worktree", "add", "--detach", str(stale), "HEAD")
        (stale / "stale.txt").write_text("junk", encoding="utf-8")
        if leftover == "registered-then-deleted":
            shutil.rmtree(stale, onerror=force_remove)
    result = evidencelib.rerun(path)
    assert result["verdict"] == "match"
    assert result["last_line"] == "REQ: False"
    assert not stale.exists()
    assert evidence_worktrees(repo) == []


def test_rerun_of_a_sha_the_repository_does_not_hold_is_refused_cleanly(repo):
    """Adversarial where: a record naming a commit that is not in the
    repository (garbage-collected, or from another clone) surfacing as a
    traceback, leaving a scratch worktree, or rewriting the record."""
    _, path = evidencelib.run_check(repo, "TASK-403", "gone", py("pass"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sha"] = "0" * 40
    path.write_text(json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(evidencelib.EvidenceError):
        evidencelib.rerun(path)
    assert path.read_bytes() == before
    assert evidence_worktrees(repo) == []
    assert not (repo / ".claude" / "worktrees" / "evidence-gone").exists()

    done = cli(repo, "rerun", str(path))
    assert done.returncode not in (0, 1)
    assert done.stderr.strip() != ""
    assert "Traceback" not in done.stderr
    assert done.stdout.strip() == ""


@pytest.mark.parametrize("sha", ["-f", "--force", "-b"])
def test_rerun_refuses_a_sha_that_git_would_read_as_an_option(repo, sha):
    """Adversarial where: a record whose sha starts with `-` being passed to
    `git worktree add` as a flag, so the rerun silently runs at HEAD (or some
    other commit) while claiming to rerun at the recorded sha."""
    _, path = evidencelib.run_check(repo, "TASK-403", "flagged", py("pass"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["sha"] = sha
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(evidencelib.EvidenceError):
        evidencelib.rerun(path)
    assert evidence_worktrees(repo) == []


def test_rerun_exit_code_is_zero_for_match_and_one_for_mismatch(repo, tmp_path):
    """Adversarial where: `rerun` exiting 0 on a mismatch (a validator script
    reading only the exit code would pass a changed result), or nonzero on a
    match, or a mismatch exiting with the same code as a refused request."""
    flag = tmp_path / "flag.txt"
    flag.write_text("0", encoding="utf-8")
    code = "import sys; sys.exit(int(open(sys.argv[1]).read()))"
    run = cli(
        repo, "run", "--task", "TASK-403", "--check", "flip", "--",
        *py(code, str(flag)),
    )
    assert run.returncode == 0
    record = repo / ".compass" / "evidence" / "TASK-403" / "flip.json"
    match = cli(repo, "rerun", str(record))
    assert match.returncode == 0
    assert match.stdout.splitlines()[0] == "match"

    data = json.loads(record.read_text(encoding="utf-8"))
    data["exit_code"] = 9
    record.write_text(json.dumps(data), encoding="utf-8")
    mismatch = cli(repo, "rerun", str(record))
    assert mismatch.returncode == 1
    assert mismatch.stdout.splitlines()[0] == "mismatch"

    refused = cli(repo, "rerun", str(repo / "absent.json"))
    assert refused.returncode == 2


@pytest.mark.parametrize(
    "slug,accepted",
    [
        ("a", True),
        ("Z", True),
        ("0", True),
        ("a_", True),
        ("a-", True),
        ("a_-", True),
        ("a.b", True),
        ("a..b", True),
        ("v1.2.3", True),
        ("_", False),
        ("-", False),
        ("_a", False),
        ("-a", False),
        (".a", False),
        ("a.", False),
        ("a..", False),
        ("a b", False),
        (" a", False),
        ("a ", False),
        ("a:b", False),
        ("a*", False),
        ("café", False),
        ("a\x00", False),
        ("a\n", False),
        ("a\r\n", False),
        ("a\nb", False),
    ],
)
def test_check_name_pattern_accepts_exactly_the_documented_shape(slug, accepted):
    """Adversarial where: the end-of-string anchor matching before a trailing
    newline (so a name ending in a newline passes validation and fails later as
    a bad file name after the command already ran), a boundary character class
    off by one at the first or last position, or a non-ASCII letter accepted as
    a letter."""
    if accepted:
        assert evidencelib.validate_slug(slug) is None
    else:
        with pytest.raises(evidencelib.EvidenceError):
            evidencelib.validate_slug(slug)


@pytest.mark.parametrize("field", ["slug", "task"])
def test_name_with_trailing_newline_is_refused_before_the_command_runs(
    repo, tmp_path, field
):
    """Adversarial where: a check name or task id ending in a newline slipping
    through validation, running the command, and only then failing on the
    file system with an uncaught OSError instead of a refusal."""
    marker = tmp_path / "ran.txt"
    argv = py("import sys; open(sys.argv[1], 'w').write('x')", str(marker))
    task, slug = "TASK-403", "ok"
    if field == "slug":
        slug = "ok\n"
    else:
        task = "TASK-403\n"
    with pytest.raises(evidencelib.EvidenceError):
        evidencelib.run_check(repo, task, slug, argv)
    assert not marker.exists()
    assert not (repo / ".compass" / "evidence").exists()


def test_cli_run_with_a_trailing_newline_slug_exits_2_without_running(repo, tmp_path):
    """Adversarial where: the same newline slug at the command line ending in
    a traceback (exit 1) after the command ran, instead of the refusal exit 2."""
    marker = tmp_path / "ran.txt"
    done = cli(
        repo, "run", "--task", "TASK-403", "--check", "ok\n", "--",
        *py("import sys; open(sys.argv[1], 'w').write('x')", str(marker)),
    )
    assert done.returncode == 2
    assert "Traceback" not in done.stderr
    assert not marker.exists()
