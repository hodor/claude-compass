"""Tests for the branches `ablatelib.ablate` contains beyond its stated contract:
new-test detection from added `def` lines, the path with no code diff, the
single rerun of a flipped test, leftover scratch worktrees, and checkpoint
records that are only partly readable.

Adversarial themes: a pre-existing green test blamed on a task that only
added other tests, a parametrized test id that never matches the `def` name
it came from, a flaky red counted as a flip, a stale `ablate-TASK-NNN`
directory or registration blocking the next run, and one bad checkpoint entry
discarding the good ones.
"""

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ablatelib  # noqa: E402
from test_ablatelib import (  # noqa: E402
    BASE_CALC, DEPENDENT_TESTS, FIXED_CALC, PYTEST_CMD,
    ablate_dirs, build_repo, git, worktree_list, write_files,
)

OLD_TAUTOLOGY = "def test_old_tautology():\n    assert 1 + 1 == 2\n"
FLAKY_TEST = (
    "import os\nfrom pathlib import Path\n\n\n"
    "def test_flaky():\n"
    "    marker = Path(os.environ['ABLATE_FLAKE_FILE'])\n"
    "    runs = int(marker.read_text()) if marker.exists() else 0\n"
    "    marker.write_text(str(runs + 1))\n"
    "    assert runs != 1\n"
)


def test_unflipped_verdict_blames_only_tests_the_merge_defined(tmp_path):
    """Adversarial where: a test file the merge merely edited has a green test
    that was already independent of the code before the task; the verdict
    counts it as the task's own unflipped test instead of looking only at the
    `def` lines the merge added, or misses a tautology the merge did add."""
    rows = {
        "added test flips, old tautology untouched": (
            DEPENDENT_TESTS, "PASS", ["test_old_tautology"]),
        "added test is itself a tautology": (
            DEPENDENT_TESTS + "\n\ndef test_new_tautology():\n    assert 2 + 2 == 4\n",
            "FINDING", ["test_new_tautology", "test_old_tautology"]),
    }
    for name, (added_tests, verdict, unflipped) in rows.items():
        sub = tmp_path / name.split(",")[0].replace(" ", "-")
        sub.mkdir()
        repo, _ = build_repo(
            sub,
            {"calc.py": BASE_CALC,
             "tests/test_calc.py": OLD_TAUTOLOGY},
            {"calc.py": FIXED_CALC,
             "tests/test_calc.py": OLD_TAUTOLOGY + "\n\n" + added_tests})

        result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

        assert (result["verdict"], result["unflipped"]) == (verdict, unflipped), name


def test_parametrized_new_test_that_stays_green_is_a_finding(tmp_path):
    """Adversarial where: a new parametrized test is recorded as
    `test_param[1]`/`test_param[2]`, which never equals the `def` name
    `test_param` taken from the added lines, so a tautology hidden behind
    parametrize is never reported."""
    param_test = (
        "import pytest\n\n\n"
        "@pytest.mark.parametrize('value', [1, 2])\n"
        "def test_param(value):\n    assert value > 0\n")
    repo, _ = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS,
         "tests/test_param.py": param_test})

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert [i for i in result["unflipped"] if i.startswith("test_param")] != []
    assert result["verdict"] == "FINDING"


def test_merge_without_a_code_diff_runs_once_and_judges_new_tests_unflipped(tmp_path):
    """Adversarial where: a merge that touches only test files has no patch to
    reverse; the path must not crash on an empty patch, must report every
    green new test as unflipped (FINDING on a behavior task), and under
    --refactor must pass because nothing can flip."""
    for refactor, verdict in ((False, "FINDING"), (True, "PASS")):
        sub = tmp_path / f"refactor-{refactor}"
        sub.mkdir()
        repo, _ = build_repo(
            sub, {"calc.py": FIXED_CALC},
            {"tests/test_calc.py": DEPENDENT_TESTS})

        result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD, refactor=refactor)

        assert result["verdict"] == verdict, f"refactor={refactor}"
        assert result["unflipped"] == ["TestCalc.test_class_add", "test_add"]
        assert result["flipped"] == [] and result["collection_errors"] == []
        assert ablate_dirs(repo) == []


def test_a_test_red_once_after_the_revert_is_not_a_flip(tmp_path, monkeypatch):
    """Adversarial where: a flaky test fails on the one run after the revert
    and passes on the rerun; counting the first red as a flip would credit the
    task with a dependency it does not have, while a test that stays red on
    the rerun must still be reported flipped."""
    monkeypatch.setenv("ABLATE_FLAKE_FILE", str(tmp_path / "flake-count.txt"))
    repo, _ = build_repo(
        tmp_path / "scratch", {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC,
         "tests/test_calc.py": DEPENDENT_TESTS,
         "tests/test_flaky.py": FLAKY_TEST})

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert result["flipped"] == ["TestCalc.test_class_add", "test_add"]
    assert result["unflipped"] == ["test_flaky"]


@pytest.mark.parametrize("leftover", ["unregistered directory", "registered worktree", "registration only"])
def test_a_leftover_scratch_worktree_does_not_block_the_next_run(tmp_path, leftover):
    """Adversarial where: an earlier aborted run left `ablate-TASK-402` behind
    as a plain directory, as a live registered worktree, or as a registration
    whose directory was deleted by hand; `git worktree add` refuses each, and
    the run must clear it and still give the real verdict instead of SKIP."""
    repo, merge = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS})
    stale = repo / ".claude" / "worktrees" / "ablate-TASK-402"
    if leftover == "unregistered directory":
        write_files(stale, {"junk.txt": "left over\n"})
    else:
        git(repo, "worktree", "add", "--detach", str(stale), merge)
        if leftover == "registration only":
            shutil.rmtree(stale)

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert (result["verdict"], result["reason"]) == ("PASS", None)
    assert result["flipped"] == ["TestCalc.test_class_add", "test_add"]
    assert ablate_dirs(repo) == []
    assert "ablate-" not in worktree_list(repo)


def test_a_merge_with_no_parent_is_a_skip_naming_git_not_a_crash(tmp_path):
    """Adversarial where: `--merge` given a root commit has no first parent,
    so `<sha>^1` cannot be diffed; the run must return SKIP with git's
    message and leave no scratch worktree."""
    repo, _ = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS})
    root = git(repo, "rev-list", "--max-parents=0", "HEAD")

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD, merge=root)

    assert result["verdict"] == "SKIP"
    assert result["merge"] == root
    assert result["reason"]
    assert ablate_dirs(repo) == []


def test_checkpoint_with_one_unreadable_entry_still_names_its_readable_files(tmp_path):
    """Adversarial where: a checkpoint record holds a pattern-less test file
    next to one malformed entry; a loader that discards the whole list on the
    first bad entry loses the good file, so its tests are never run. A
    truncated record must degrade to the path patterns without raising."""
    files = {
        "calc.py": FIXED_CALC,
        "checks/verify_calc.py":
            "from calc import add\n\n\ndef test_add():\n    assert add(1, 1) == 2\n",
    }
    repo, _ = build_repo(tmp_path, {"calc.py": BASE_CALC}, files)
    record_dir = repo / ".compass" / "tmp" / "test-checkpoints"
    record_dir.mkdir(parents=True)
    record_file = record_dir / "TASK-402.json"

    record_file.write_text(json.dumps(
        {"files": [{"path": "checks/verify_calc.py"}, "not-a-record"]}), encoding="utf-8")
    partial = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    record_file.write_text('{"files": [{"path": "checks/ver', encoding="utf-8")
    truncated = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert partial["flipped"] == ["test_add"]
    assert truncated["verdict"] in {"PASS", "FINDING", "SKIP"}
