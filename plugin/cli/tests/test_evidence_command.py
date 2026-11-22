"""Tests for `commands.evidence`, the `compass evidence run|rerun|show` command.

Adversarial themes: the command's output streamed or truncated wrongly (more
or fewer than the last 40 lines), the checked command's exit code lost, flags
after `--` swallowed by the parser, a refused request that already ran the
command, a rerun that reports the wrong word.

The module is run in a subprocess (`commands.evidence.run(argv)`, its return
value becomes the exit code) with the throwaway repo as the working directory.

Interface pinned here:

- `evidence run --task TASK-NNN --check <slug> -- <command...>`: stdout is the
  last 40 lines of the combined output followed by one final line
  `record: <repo-relative POSIX path of the .json record>`; nothing else goes
  to stdout; exit code is the command's. A refused request exits nonzero,
  writes a message to stderr and runs nothing.
- `evidence rerun <record>` (path absolute or relative to the working
  directory): the first stdout line is exactly `match` or `mismatch`. After
  `mismatch` the recorded and the rerun exit codes and verdict lines appear in
  the output. A dirty-tree record adds a line containing `uncommitted` (on
  stdout or stderr). An unreadable record exits nonzero.
- `evidence show TASK-NNN`: one line per record, sorted by check, each holding
  the check as a whole token, `exit=<n>`, the first 12 characters of the sha
  and `clean` or `dirty`; an unreadable record's line holds `unreadable`; no
  records exit 0 with one line containing `no records`.
- No subcommand, an unknown subcommand, or missing required flags exit nonzero
  with a message on stderr."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

CLI_DIR = Path(__file__).resolve().parents[1]
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
    (root / ".compass").mkdir(parents=True)
    (root / "sub").mkdir()
    (root / ".compass" / "index.md").write_text("# index\n", encoding="utf-8")
    (root / "value.txt").write_text("3", encoding="utf-8")
    (root / "sub" / "f.txt").write_text("f", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "base")
    return root


def evidence(cwd, *args):
    return subprocess.run(
        [PY, "-c", DRIVER, str(CLI_DIR), *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8",
    )


def py(code, *rest):
    return [PY, "-c", code, *rest]


def run_cmd(cwd, slug, argv, task="TASK-403"):
    return evidence(cwd, "run", "--task", task, "--check", slug, "--", *argv)


def lines_of(text):
    return text.splitlines()


@pytest.mark.parametrize("count", [100, 41, 40, 39, 1])
def test_run_prints_exactly_the_last_forty_lines_then_the_record_path(repo, count):
    """Adversarial where: an off-by-one tail (39 or 41 lines), the whole
    output streamed to stdout, or the record path missing or not last. Cases
    straddle the 40-line boundary."""
    code = f"for i in range({count}): print('row-%03d' % i)"
    done = run_cmd(repo, "tail", py(code))
    assert done.returncode == 0, done.stderr
    out = lines_of(done.stdout)
    expected = ["row-%03d" % i for i in range(max(0, count - 40), count)]
    assert out[:-1] == expected
    assert out[-1] == "record: .compass/evidence/TASK-403/tail.json"
    full = (repo / ".compass/evidence/TASK-403/tail.out").read_text(encoding="utf-8")
    assert lines_of(full) == ["row-%03d" % i for i in range(count)]


@pytest.mark.parametrize("code", [0, 1, 7, 113])
def test_run_exits_with_the_commands_exit_code_and_writes_the_record(repo, code):
    """Adversarial where: the checked command's exit code replaced by 0 or 1,
    or the record not written when the command fails."""
    done = run_cmd(repo, "codes", py(f"import sys; sys.exit({code})"))
    assert done.returncode == code
    record = json.loads(
        (repo / ".compass/evidence/TASK-403/codes.json").read_text(encoding="utf-8")
    )
    assert record["exit_code"] == code


def test_run_keeps_flags_after_the_double_dash_for_the_command(repo):
    """Adversarial where: `--check` or `--task` inside the command swallowed by
    the evidence parser, or arguments with spaces and quotes split or
    re-quoted on the way into the record."""
    argv = py(
        "import sys; print(sys.argv[1:])",
        "--check", "inner", "--task", "TASK-1", 'a b "c"', "--",
    )
    done = run_cmd(repo, "passthru", argv)
    assert done.returncode == 0, done.stderr
    record = json.loads(
        (repo / ".compass/evidence/TASK-403/passthru.json").read_text(encoding="utf-8")
    )
    assert record["argv"] == argv
    assert record["check"] == "passthru" and record["task"] == "TASK-403"
    assert "inner" in done.stdout


def test_run_from_a_subdirectory_writes_to_the_repo_root(repo):
    """Adversarial where: the evidence folder created under the invoking
    directory, or the printed record path relative to the wrong base."""
    done = run_cmd(repo / "sub", "insub", py("pass"))
    assert done.returncode == 0, done.stderr
    assert (repo / ".compass/evidence/TASK-403/insub.json").is_file()
    assert not (repo / "sub/.compass").exists()
    assert lines_of(done.stdout)[-1] == "record: .compass/evidence/TASK-403/insub.json"


@pytest.mark.parametrize(
    "args",
    [
        ["run", "--task", "TASK-403", "--check", "a/b", "--", "PYMARK"],
        ["run", "--task", "TASK-403", "--check", "..", "--", "PYMARK"],
        ["run", "--task", "../TASK-1", "--check", "ok", "--", "PYMARK"],
        ["run", "--task", "TASK-403", "--", "PYMARK"],
        ["run", "--check", "ok", "--", "PYMARK"],
        ["run", "--task", "TASK-403", "--check", "ok"],
        ["run", "--task", "TASK-403", "--check", "ok", "--"],
    ],
    ids=[
        "slash-slug", "dotdot-slug", "dotdot-task", "no-check",
        "no-task", "no-double-dash", "empty-command",
    ],
)
def test_run_refuses_bad_requests_without_running_the_command(repo, tmp_path, args):
    """Adversarial where: a slug or task with path separators, a missing flag
    or an empty command accepted, running the command anyway, or leaving an
    evidence folder behind."""
    marker = tmp_path / "ran.txt"
    command = py("import sys; open(sys.argv[1], 'w').write('x')", str(marker))
    expanded = []
    for arg in args:
        expanded.extend(command if arg == "PYMARK" else [arg])
    done = evidence(repo, *expanded)
    assert done.returncode != 0
    assert done.stderr.strip() != ""
    assert "Traceback" not in done.stderr
    assert not marker.exists()
    assert not (repo / ".compass/evidence").exists()


def test_run_outside_a_git_repo_exits_nonzero_without_running(tmp_path):
    """Adversarial where: a traceback instead of a message, or the command run
    with no repo to record against."""
    outside = tmp_path / "plain"
    outside.mkdir()
    marker = tmp_path / "ran.txt"
    done = run_cmd(
        outside, "x", py("import sys; open(sys.argv[1], 'w').write('x')", str(marker))
    )
    assert done.returncode != 0
    assert "Traceback" not in done.stderr
    assert not marker.exists()


@pytest.mark.parametrize("args", [[], ["bogus"], ["rerun"], ["show"]])
def test_bad_invocation_exits_nonzero_with_a_message(repo, args):
    """Adversarial where: no subcommand, an unknown one, or a missing positional
    argument exiting 0 or raising a traceback."""
    done = evidence(repo, *args)
    assert done.returncode != 0
    assert done.stderr.strip() != ""
    assert "Traceback" not in done.stderr


def test_rerun_prints_match_first_and_leaves_no_worktree(repo):
    """Adversarial where: `match` printed after other text, the exit code
    ignored, a relative record path not resolved against the working directory,
    or the scratch worktree left behind. The repo changes after the record, so
    only a rerun at the recorded sha matches."""
    code = "import sys; sys.exit(int(open('value.txt').read()))"
    recorded = run_cmd(repo, "again", py(code))
    assert recorded.returncode == 3
    (repo / "value.txt").write_text("0", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "change")
    for path in (
        str(repo / ".compass/evidence/TASK-403/again.json"),
        ".compass/evidence/TASK-403/again.json",
    ):
        done = evidence(repo, "rerun", path)
        assert lines_of(done.stdout)[0] == "match", (path, done.stdout, done.stderr)
        assert not (repo / ".claude/worktrees/evidence-again").exists()
    assert git(repo, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_rerun_reports_mismatch_with_both_sides(repo, tmp_path):
    """Adversarial where: a mismatch reported as a bare word, so the reader
    cannot see the recorded and the rerun verdict lines and exit codes."""
    flag = tmp_path / "flag.txt"
    flag.write_text("PASS", encoding="utf-8")
    code = (
        "import sys; v = open(sys.argv[1]).read(); print('REACH: ' + v);"
        " sys.exit(2 if v == 'PASS' else 6)"
    )
    run_cmd(repo, "differ", py(code, str(flag)))
    flag.write_text("FINDING", encoding="utf-8")
    done = evidence(repo, "rerun", str(repo / ".compass/evidence/TASK-403/differ.json"))
    out = lines_of(done.stdout)
    assert out[0] == "mismatch"
    text = done.stdout
    assert "REACH: PASS" in text and "REACH: FINDING" in text
    assert re.search(r"(?<!\d)2(?!\d)", text) and re.search(r"(?<!\d)6(?!\d)", text)


def test_rerun_of_dirty_record_warns_about_uncommitted_changes(repo):
    """Adversarial where: the warning missing for a dirty-tree record, or
    printed for a clean one."""
    run_cmd(repo, "clean", py("pass"))
    (repo / "value.txt").write_text("8", encoding="utf-8")
    run_cmd(repo, "dirty", py("pass"))
    clean = evidence(repo, "rerun", ".compass/evidence/TASK-403/clean.json")
    dirty = evidence(repo, "rerun", ".compass/evidence/TASK-403/dirty.json")
    assert "uncommitted" not in (clean.stdout + clean.stderr).lower()
    assert "uncommitted" in (dirty.stdout + dirty.stderr).lower()
    assert lines_of(dirty.stdout)[0] == "match"


@pytest.mark.parametrize("damage", ["missing", "not-json"])
def test_rerun_of_unreadable_record_exits_nonzero_with_a_message(repo, damage):
    """Adversarial where: a traceback or exit 0 for a record that cannot be
    read, or a worktree created anyway."""
    path = repo / ".compass/evidence/TASK-403/bad.json"
    if damage == "not-json":
        path.parent.mkdir(parents=True)
        path.write_text("{oops", encoding="utf-8")
    done = evidence(repo, "rerun", str(path))
    assert done.returncode != 0
    assert done.stderr.strip() != ""
    assert "Traceback" not in done.stderr
    assert not (repo / ".claude/worktrees").exists()


def test_show_lists_records_of_exactly_that_task_sorted(repo):
    """Adversarial where: TASK-40 listing TASK-403's records by prefix, `.out`
    files counted as records, one unreadable record hiding the rest, the
    sha, exit code or tree state missing from a line, or an empty task failing."""
    run_cmd(repo, "zeta", py("pass"))
    run_cmd(repo, "alpha", py("import sys; sys.exit(2)"))
    run_cmd(repo, "other", py("pass"), task="TASK-40")
    (repo / ".compass/evidence/TASK-403/broken.json").write_text("{", encoding="utf-8")
    sha = git(repo, "rev-parse", "HEAD")

    done = evidence(repo, "show", "TASK-403")
    assert done.returncode == 0, done.stderr
    rows = lines_of(done.stdout)
    assert len(rows) == 3, done.stdout
    first, second, third = rows
    assert re.search(r"(?<![\w-])alpha(?![\w-])", first)
    assert "exit=2" in first and sha[:12] in first and "clean" in first
    assert re.search(r"(?<![\w-])broken(?![\w-])", second) and "unreadable" in second
    assert re.search(r"(?<![\w-])zeta(?![\w-])", third)
    assert "exit=0" in third
    assert "other" not in done.stdout

    short = evidence(repo, "show", "TASK-40")
    assert len(lines_of(short.stdout)) == 1 and "other" in short.stdout

    none = evidence(repo, "show", "TASK-999")
    assert none.returncode == 0
    assert len(lines_of(none.stdout)) == 1 and "no records" in none.stdout


def test_show_marks_a_dirty_record_dirty(repo):
    """Adversarial where: the tree state dropped from the listing, so a dirty
    record reads as clean evidence."""
    (repo / "value.txt").write_text("8", encoding="utf-8")
    run_cmd(repo, "dirty", py("pass"))
    done = evidence(repo, "show", "TASK-403")
    row = lines_of(done.stdout)[0]
    assert "dirty" in row and "clean" not in row
