"""Tests for `compass ablate TASK-NNN --cmd "<command with {tests}>"
[--refactor] [--merge <sha>] [--repo <dir>]`, the command module
`commands.ablate`.

Adversarial themes: a verdict line that is not the last line or not
deterministic (`compass evidence rerun` compares it), an exit code that
turns a FINDING or SKIP into a failure, flags parsed but never applied,
and bad arguments that start work instead of exiting 1.

Interface pinned here: `run(args) -> int`. Output: one line per id
`flipped: <id>`, `unflipped: <id>`, `baseline-red: <id>`,
`collection-error: <id>`, then the last line `ABLATE: PASS`,
`ABLATE: FINDING` or `ABLATE: SKIP: <git message>`. Exit 0 for all three
verdicts, 1 for bad arguments (missing or malformed task id, missing
`--cmd`, unknown flag). `--repo` defaults to the current directory."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import ablate  # noqa: E402
from tests.test_ablatelib import (  # noqa: E402
    BASE_CALC, DEPENDENT_TESTS, FIXED_CALC, PYTEST_CMD, ablate_dirs, add_merge,
    build_repo, git,
)

COSMETIC_BASE = {"calc.py": "def add(a, b):\n    return a + b\n"}
COSMETIC_BRANCH = {
    "calc.py": "def add(left, right):\n    return left + right\n",
    "tests/test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(4, 5) == 9\n",
}


def run_ablate(capsys, args):
    code = ablate.run(args)
    out = capsys.readouterr()
    return code, [ln.strip() for ln in out.out.splitlines() if ln.strip()], out.err


def dependent_repo(tmp_path, extra_tests=""):
    return build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS + extra_tests})


def test_each_verdict_exits_zero_with_its_report_and_verdict_as_last_line(tmp_path, capsys):
    """Adversarial where: a FINDING or SKIP exits nonzero (so an evidence
    record of the run reads as a failed check), the verdict line is not
    last, or an id is printed under the wrong label."""
    pass_repo, _ = dependent_repo(tmp_path / "p")
    finding_repo, _ = dependent_repo(
        tmp_path / "f", "\n\ndef test_tautology():\n    assert 1 + 1 == 2\n")
    skip_repo, _ = build_repo(
        tmp_path / "s", {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "data.bin": b"\x00\x01\xff", "tests/test_calc.py": DEPENDENT_TESTS})
    rows = {
        "PASS": (pass_repo, "ABLATE: PASS", {"flipped: test_add", "flipped: TestCalc.test_class_add"}),
        "FINDING": (finding_repo, "ABLATE: FINDING",
                    {"flipped: test_add", "unflipped: test_tautology"}),
        "SKIP": (skip_repo, None, set()),
    }
    for name, (repo, last, expected_lines) in rows.items():
        code, lines, _ = run_ablate(
            capsys, ["TASK-402", "--cmd", PYTEST_CMD, "--repo", str(repo)])
        assert code == 0, name
        if last is not None:
            assert lines[-1] == last, name
        else:
            assert lines[-1].startswith("ABLATE: SKIP: ") and "data.bin" in lines[-1], name
        assert expected_lines <= set(lines), name
        assert not [ln for ln in lines[:-1] if ln.startswith("ABLATE:")], name
        assert ablate_dirs(repo) == [], name


def test_verdict_line_is_identical_across_runs_and_independent_of_the_repo_path(tmp_path, capsys):
    """Adversarial where: the verdict line embeds a sha, temp path or
    timestamp, so `compass evidence rerun` reports a mismatch for an
    unchanged check."""
    first, _ = dependent_repo(tmp_path / "one")
    second, _ = dependent_repo(tmp_path / "two")

    _, lines_a, _ = run_ablate(capsys, ["TASK-402", "--cmd", PYTEST_CMD, "--repo", str(first)])
    _, lines_b, _ = run_ablate(capsys, ["TASK-402", "--cmd", PYTEST_CMD, "--repo", str(first)])
    _, lines_c, _ = run_ablate(capsys, ["TASK-402", "--cmd", PYTEST_CMD, "--repo", str(second)])

    assert lines_a[-1] == lines_b[-1] == lines_c[-1] == "ABLATE: PASS"


def test_repo_defaults_to_the_current_directory(tmp_path, capsys, monkeypatch):
    """Adversarial where: omitting --repo resolves the repo from the
    plugin's own location instead of the caller's directory."""
    repo, _ = dependent_repo(tmp_path)
    monkeypatch.chdir(repo)

    code, lines, _ = run_ablate(capsys, ["TASK-402", "--cmd", PYTEST_CMD])

    assert (code, lines[-1]) == (0, "ABLATE: PASS")


def test_refactor_flag_changes_the_verdict_rule(tmp_path, capsys):
    """Adversarial where: --refactor is parsed but never reaches the
    verdict rule: a cosmetic change with no flip is a FINDING without the
    flag (unflipped new test) and a PASS with it."""
    repo, _ = build_repo(tmp_path, COSMETIC_BASE, COSMETIC_BRANCH)

    _, behavior_lines, _ = run_ablate(
        capsys, ["TASK-402", "--cmd", PYTEST_CMD, "--repo", str(repo)])
    _, refactor_lines, _ = run_ablate(
        capsys, ["TASK-402", "--cmd", PYTEST_CMD, "--repo", str(repo), "--refactor"])

    assert behavior_lines[-1] == "ABLATE: FINDING"
    assert refactor_lines[-1] == "ABLATE: PASS"


def test_merge_flag_selects_a_commit_whose_subject_names_no_task(tmp_path, capsys):
    """Adversarial where: --merge is ignored in favor of the subject search,
    so a merge made without the `Merge TASK-NNN:` subject is never found;
    a later TASK-402 merge on the branch must not be taken instead."""
    repo, _ = build_repo(tmp_path, {"calc.py": BASE_CALC}, {"README.md": "docs\n"})
    odd_merge = add_merge(
        repo, "odd", {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS},
        "Merge branch 'odd' into main")
    add_merge(repo, "later", {"notes.md": "later\n"}, "Merge TASK-402: docs only")

    code, lines, _ = run_ablate(
        capsys, ["TASK-402", "--cmd", PYTEST_CMD, "--repo", str(repo), "--merge", odd_merge])

    assert code == 0
    assert "flipped: test_add" in lines
    assert lines[-1] == "ABLATE: PASS"


@pytest.mark.parametrize("args", [
    pytest.param([], id="no arguments"),
    pytest.param(["TASK-402"], id="missing --cmd"),
    pytest.param(["--cmd", PYTEST_CMD], id="missing task id"),
    pytest.param(["402", "--cmd", PYTEST_CMD], id="task id without TASK- prefix"),
    pytest.param(["TASK-402", "--cmd", PYTEST_CMD, "--no-such-flag"], id="unknown flag"),
    pytest.param(["TASK-402", "--cmd"], id="--cmd with no value"),
])
def test_bad_arguments_exit_one_without_creating_a_worktree(tmp_path, capsys, args):
    """Adversarial where: a malformed invocation starts a baseline run (or
    crashes with a traceback) instead of exiting 1 with a message on
    stderr and no ABLATE verdict line."""
    repo, _ = dependent_repo(tmp_path)

    code, lines, err = run_ablate(capsys, args + ["--repo", str(repo)])

    assert code == 1
    assert err.strip() != ""
    assert not [ln for ln in lines if ln.startswith("ABLATE:")]
    assert ablate_dirs(repo) == []
    assert git(repo, "status", "--porcelain") == ""
