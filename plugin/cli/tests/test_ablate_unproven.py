"""Tests for `compass ablate` reading the red kind a checkpoint stores: a test
whose only red was a collection error and that does not flip is printed
`unproven: <id>` instead of under `unflipped` or `collection-error`, and the
verdict stays what the other tests make it.

Every repository here is a real git repository; the checkpoint is written by
`compass test-checkpoint record --red-evidence` from run output shaped like a
real `pytest -v` run, so the red kinds are produced by the shipped writer and
read by the shipped reader.

Adversarial themes: a task that adds a new module reading FINDING on every
revert, the new line swallowing a real FINDING from a sibling test, a `fail`
kind or a flipped test relabelled `unproven`, and a checkpoint written before
the key existed printing a line it has no data for.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import ablate, test_checkpoint  # noqa: E402
from tests.test_ablatelib import (  # noqa: E402
    BASE_CALC, DEPENDENT_TESTS, FIXED_CALC, PYTEST_CMD, ablate_dirs, build_repo, git,
)

NEW_MODULE = "def thing():\n    return 1\n"
NEW_MODULE_TESTS = (
    "from newmod import thing\n\n\n"
    "def test_thing():\n    assert thing() == 1\n\n\n"
    "class TestNew:\n    def test_in_class(self):\n        assert thing() == 1\n"
)
TAUTOLOGY_TESTS = "def test_taut():\n    assert 1 + 1 == 2\n"


def collection_evidence(path):
    """`pytest -v` output for a file that fails to import."""
    return (
        "============================= test session starts =============================\n"
        "collecting ... collected 0 items / 1 error\n\n"
        "=================================== ERRORS ====================================\n"
        f"_____________________ ERROR collecting {path} _____________________\n"
        f"ImportError while importing test module '/repo/{path}'.\n"
        "Hint: make sure your test modules/packages have valid Python names.\n"
        "Traceback:\n"
        "E   ModuleNotFoundError: No module named 'newmod'\n"
        "=========================== short test summary info ===========================\n"
        f"ERROR {path}\n"
        "!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\n"
        "============================== 1 error in 0.16s ===============================\n"
    )


def failed_evidence(nodeid):
    return (
        "collecting ... collected 1 item\n\n"
        f"{nodeid} FAILED                                      [100%]\n\n"
        "=========================== short test summary info ===========================\n"
        f"FAILED {nodeid} - assert 1 == 2\n"
        "============================== 1 failed in 0.05s ==============================\n"
    )


def checkpoint(repo, tmp_path, monkeypatch, capsys, files, evidence=None, task="TASK-402"):
    """Record `files` (as of the task branch tip) as the task's checkpoint,
    with `evidence` text as the red evidence when given."""
    (repo / ".compass").mkdir(exist_ok=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    argv = ["record", task, *files, "--commit", git(repo, "rev-parse", "HEAD^2")]
    if evidence is not None:
        path = tmp_path / "red-evidence.txt"
        path.write_text(evidence, encoding="utf-8")
        argv += ["--red-evidence", str(path)]
    code = test_checkpoint.run(argv)
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err


def run_ablate(repo, capsys, task="TASK-402"):
    code = ablate.run([task, "--cmd", PYTEST_CMD, "--repo", str(repo)])
    out = capsys.readouterr()
    assert code == 0, out.err
    return [ln.strip() for ln in out.out.splitlines() if ln.strip()]


def new_module_repo(tmp_path, extra_branch_files=None):
    return build_repo(
        tmp_path, {"README.md": "base\n"},
        {"newmod.py": NEW_MODULE, "tests/test_newmod.py": NEW_MODULE_TESTS,
         **(extra_branch_files or {})})[0]


def test_collection_only_red_that_vanishes_on_revert_is_unproven_not_a_finding(
        tmp_path, monkeypatch, capsys):
    """Adversarial where: a task that adds a new module, whose tests were red
    only because the module did not exist, prints the tests under
    `collection-error` (or lets them reach FINDING), so every such task reads
    as a defect on revert instead of as tests whose red was never their own."""
    repo = new_module_repo(tmp_path)
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_newmod.py"],
               collection_evidence("tests/test_newmod.py"))
    lines = run_ablate(repo, capsys)
    assert lines == [
        "unproven: TestNew.test_in_class", "unproven: test_thing", "ABLATE: PASS",
    ]
    assert ablate_dirs(repo) == []


def test_checkpoint_without_red_kinds_prints_no_unproven_line(tmp_path, monkeypatch, capsys):
    """Adversarial where: a checkpoint recorded without evidence (or before
    the key existed) prints `unproven` for tests it holds no kind for, or
    stops printing the `collection-error` lines it printed before."""
    repo = new_module_repo(tmp_path)
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_newmod.py"])
    lines = run_ablate(repo, capsys)
    assert lines == [
        "collection-error: TestNew.test_in_class", "collection-error: test_thing",
        "ABLATE: PASS",
    ]


def test_fail_kind_that_stays_green_on_revert_is_an_unflipped_finding(
        tmp_path, monkeypatch, capsys):
    """Adversarial where: the `unproven` rule widens to every red kind, so a
    test that failed for its own reason before the build and still passes
    with the code reverted (a tautology) stops being reported as FINDING."""
    repo = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_taut.py": TAUTOLOGY_TESTS})[0]
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_taut.py"],
               failed_evidence("tests/test_taut.py::test_taut"))
    lines = run_ablate(repo, capsys)
    assert lines == ["unflipped: test_taut", "ABLATE: FINDING"]


def test_unproven_line_does_not_hide_a_finding_from_a_sibling_test(
        tmp_path, monkeypatch, capsys):
    """Adversarial where: one unproven test in the task turns the whole
    verdict to PASS, so a tautology checkpointed beside it goes unreported."""
    repo = new_module_repo(tmp_path, {"tests/test_taut.py": TAUTOLOGY_TESTS})
    evidence = (collection_evidence("tests/test_newmod.py")
                + failed_evidence("tests/test_taut.py::test_taut"))
    checkpoint(repo, tmp_path, monkeypatch, capsys,
               ["tests/test_newmod.py", "tests/test_taut.py"], evidence)
    lines = run_ablate(repo, capsys)
    assert lines == [
        "unproven: TestNew.test_in_class", "unproven: test_thing",
        "unflipped: test_taut", "ABLATE: FINDING",
    ]


def test_collection_kind_that_stays_green_is_unproven_and_leaves_the_verdict_alone(
        tmp_path, monkeypatch, capsys):
    """Adversarial where: a collection-kind test that is green both with and
    without the code is printed `unflipped` and read as a FINDING, though
    its recorded red was an import error and says nothing about the code."""
    repo = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_taut.py": TAUTOLOGY_TESTS})[0]
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_taut.py"],
               collection_evidence("tests/test_taut.py"))
    lines = run_ablate(repo, capsys)
    assert lines == ["unproven: test_taut", "ABLATE: PASS"]


def test_collection_kind_test_that_flips_is_still_reported_flipped(
        tmp_path, monkeypatch, capsys):
    """Adversarial where: any collection-kind test is printed `unproven`,
    including one that demonstrably fails once the code is reverted, so real
    evidence is discarded."""
    repo = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS})[0]
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_calc.py"],
               collection_evidence("tests/test_calc.py"))
    lines = run_ablate(repo, capsys)
    assert lines == ["flipped: TestCalc.test_class_add", "flipped: test_add", "ABLATE: PASS"]


@pytest.mark.parametrize("kind_evidence", ["absent", "passed"])
def test_absent_and_passed_kinds_keep_todays_handling(
        kind_evidence, tmp_path, monkeypatch, capsys):
    """Adversarial where: the `unproven` rule fires for any non-`fail` kind,
    so a test the evidence never mentioned, or one that was green before the
    build, vanishes into `unproven` instead of `collection-error`."""
    repo = new_module_repo(tmp_path)
    evidence = (
        "collecting ... collected 0 items\n\n"
        "============================ no tests ran in 0.01s ============================\n"
        if kind_evidence == "absent" else
        "collecting ... collected 1 item\n\n"
        "tests/test_newmod.py::test_thing PASSED                                  [100%]\n"
        "tests/test_newmod.py::TestNew::test_in_class PASSED                      [100%]\n"
    )
    checkpoint(repo, tmp_path, monkeypatch, capsys, ["tests/test_newmod.py"], evidence)
    lines = run_ablate(repo, capsys)
    assert lines == [
        "collection-error: TestNew.test_in_class", "collection-error: test_thing",
        "ABLATE: PASS",
    ]
