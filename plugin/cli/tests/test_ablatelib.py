"""Tests for `ablatelib`, the engine behind `compass ablate`: it finds a
task's merge commit, reverts the merge's non-test changes in a scratch git
worktree, and reports which of the task's tests depend on that code.

Adversarial themes: a merge lookup that aliases TASK-40 onto TASK-402, a test
file the checkpoint names but the path patterns do not, a revert that leaks
into the real working tree or leaves its scratch worktree behind, a CRLF
checkout defeating the reverse patch, a baseline-red test miscounted as
unflipped, and a refactor judged by the behavior-task rule.

Interface pinned here (every function takes a git repo directory):

    find_merge_commit(repo, task, merge=None) -> str | None
        Full 40-hex sha of the newest first-parent commit on the current
        branch whose subject starts `Merge <task>:`. With `merge` given,
        that revision resolved to its full sha. None when nothing matches.

    split_diff_paths(paths, checkpoint_files=()) -> (test_paths, code_paths)
        Order-preserving partition of repo-relative POSIX paths. A path is a
        test path when it is in `checkpoint_files`, sits under a directory
        named `tests`, or has a basename `test_*`, `*_test.*`, `*.test.*` or
        `*.spec.*`.

    ablate(repo, task, cmd, refactor=False, merge=None) -> dict
        `cmd` holds the placeholder `{tests}`, replaced by the selected test
        files (repo-relative POSIX paths, space-separated). The command runs
        through the shell in the scratch worktree and must print per-test
        outcomes the parser in commands/test_checkpoint.py reads (pytest -v).
        The returned dict has keys:
          verdict          "PASS" | "FINDING" | "SKIP"
          merge            full sha of the merge commit
          flipped          sorted test ids green at baseline, not green after
                           the revert
          unflipped        sorted test ids green at baseline and after
          baseline_red     sorted test ids not green at baseline
          collection_errors sorted test ids green at baseline and absent after
                           the revert because their file failed to import
          reason           None, or git's message when verdict is SKIP
        A test id is `test_name`, or `Class.test_name` for a class method.

    format_report(result) -> str
        Lines `flipped: <id>`, `unflipped: <id>`, `baseline-red: <id>`,
        `collection-error: <id>` (one per id), then as the last line
        `ABLATE: PASS`, `ABLATE: FINDING` or `ABLATE: SKIP: <reason>`.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ablatelib  # noqa: E402

PYTEST_CMD = (
    f'"{Path(sys.executable).as_posix()}" -m pytest -v -p no:cacheprovider {{tests}}'
)

BASE_CALC = "def add(a, b):\n    return a - b\n"
FIXED_CALC = "def add(a, b):\n    return a + b\n"

DEPENDENT_TESTS = (
    "from calc import add\n\n\n"
    "class TestCalc:\n"
    "    def test_class_add(self):\n"
    "        assert add(2, 3) == 5\n\n\n"
    "def test_add():\n"
    "    assert add(4, 5) == 9\n"
)


def git(repo, *args, check=True):
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(repo), capture_output=True, text=True,
    )
    if check and done.returncode != 0:
        raise AssertionError(f"git {args} failed: {done.stderr}")
    return done.stdout.strip()


def write_files(repo, files, eol="\n"):
    for rel, content in files.items():
        path = Path(repo) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_bytes(content.replace("\n", eol).encode("utf-8"))


def add_merge(repo, branch, files, message, eol="\n"):
    """Branch off the current commit, commit `files` there, and merge the
    branch back with `--no-ff` under `message`. Returns the merge sha."""
    start = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    git(repo, "checkout", "-q", "-b", branch)
    write_files(repo, files, eol)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"work on {branch}")
    git(repo, "checkout", "-q", start)
    git(repo, "merge", "-q", "--no-ff", branch, "-m", message)
    return git(repo, "rev-parse", "HEAD")


def build_repo(tmp_path, base_files, branch_files, task="TASK-402", autocrlf=None, eol="\n"):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    if autocrlf is not None:
        git(repo, "config", "core.autocrlf", autocrlf)
    write_files(repo, base_files, eol)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    merge = add_merge(repo, "task-branch", branch_files, f"Merge {task}: add it", eol)
    return repo, merge


def ablate_dirs(repo):
    root = Path(repo) / ".claude" / "worktrees"
    return sorted(p.name for p in root.glob("ablate-*")) if root.exists() else []


def worktree_list(repo):
    return git(repo, "worktree", "list", "--porcelain")


def test_find_merge_commit_matches_the_task_exactly_and_only_on_this_branch(tmp_path):
    """Adversarial where: a prefix match returns TASK-402's merge for TASK-40
    (the newer TASK-402 merge sits on top), a merge on an unrelated branch is
    reachable by name only, and an abbreviated --merge sha is not widened."""
    repo, merge_402 = build_repo(tmp_path, {"a.py": "x = 1\n"}, {"b.py": "y = 1\n"})
    merge_40 = add_merge(repo, "b40", {"c.py": "z = 1\n"}, "Merge TASK-40: older sibling")
    merge_402_late = add_merge(repo, "b402", {"d.py": "w = 1\n"}, "Merge TASK-402: second pass")
    git(repo, "checkout", "-q", "-b", "elsewhere", merge_402)
    add_merge(repo, "b9", {"e.py": "v = 1\n"}, "Merge TASK-9: only on elsewhere")
    git(repo, "checkout", "-q", "main")

    rows = {
        "exact id, newest first-parent merge wins": (
            ablatelib.find_merge_commit(repo, "TASK-402"), merge_402_late),
        "shorter id does not alias onto the longer one": (
            ablatelib.find_merge_commit(repo, "TASK-40"), merge_40),
        "merge on a branch outside the current history": (
            ablatelib.find_merge_commit(repo, "TASK-9"), None),
        "task with no merge": (
            ablatelib.find_merge_commit(repo, "TASK-7"), None),
        "abbreviated --merge is resolved to the full sha": (
            ablatelib.find_merge_commit(repo, "TASK-402", merge=merge_40[:8]), merge_40),
    }
    for name, (got, want) in rows.items():
        assert got == want, name


def test_split_diff_paths_partitions_by_pattern_and_checkpoint():
    """Adversarial where: substring look-alikes (`contest.py`, `testing/`,
    `mytests/`) are taken for tests, a checkpointed file whose name matches
    no pattern is reverted as code, or the partition reorders its input."""
    paths = [
        "src/core.py", "tests/test_core.py", "plugin/cli/tests/helpers.py",
        "pkg/test_x.py", "pkg/x_test.py", "web/x.test.js", "web/x.spec.ts",
        "src/contest.py", "src/testing/runner.py", "mytests/a.py",
        "checks/verify_core.py", "README.md",
    ]
    tests, code = ablatelib.split_diff_paths(paths, checkpoint_files=["checks/verify_core.py"])
    assert tests == [
        "tests/test_core.py", "plugin/cli/tests/helpers.py", "pkg/test_x.py",
        "pkg/x_test.py", "web/x.test.js", "web/x.spec.ts", "checks/verify_core.py",
    ]
    assert code == [
        "src/core.py", "src/contest.py", "src/testing/runner.py", "mytests/a.py",
        "README.md",
    ]
    bare_tests, bare_code = ablatelib.split_diff_paths(["checks/verify_core.py"])
    assert (bare_tests, bare_code) == ([], ["checks/verify_core.py"])


def scenario_files():
    """name -> (base_files, branch_files, refactor, expected result subset)."""
    tautology = DEPENDENT_TESTS + "\n\ndef test_tautology():\n    assert 1 + 1 == 2\n"
    broken = DEPENDENT_TESTS + "\n\ndef test_broken():\n    assert add(1, 1) == 3\n"
    cosmetic_calc = "def add(left, right):\n    return left + right\n"
    return {
        "dependent tests flip": (
            {"calc.py": BASE_CALC},
            {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS},
            False,
            {"verdict": "PASS", "flipped": ["TestCalc.test_class_add", "test_add"],
             "unflipped": [], "baseline_red": [], "collection_errors": []},
        ),
        "assertion that holds without the code stays green": (
            {"calc.py": BASE_CALC},
            {"calc.py": FIXED_CALC, "tests/test_calc.py": tautology},
            False,
            {"verdict": "FINDING", "flipped": ["TestCalc.test_class_add", "test_add"],
             "unflipped": ["test_tautology"], "baseline_red": [], "collection_errors": []},
        ),
        "baseline-red test is named and left out of the verdict": (
            {"calc.py": BASE_CALC},
            {"calc.py": FIXED_CALC, "tests/test_calc.py": broken},
            False,
            {"verdict": "PASS", "flipped": ["TestCalc.test_class_add", "test_add"],
             "unflipped": [], "baseline_red": ["test_broken"], "collection_errors": []},
        ),
        "new module the tests import is a collection error": (
            {"README.md": "docs\n"},
            {"newmod.py": "def double(x):\n    return x * 2\n",
             "tests/test_newmod.py":
                 "from newmod import double\n\n\ndef test_double():\n    assert double(4) == 8\n"},
            False,
            {"verdict": "PASS", "unflipped": [], "baseline_red": [],
             "collection_errors": ["test_double"]},
        ),
        "refactor with no flip passes": (
            {"calc.py": "def add(a, b):\n    return a + b\n"},
            {"calc.py": cosmetic_calc,
             "tests/test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(4, 5) == 9\n"},
            True,
            {"verdict": "PASS", "flipped": [], "unflipped": ["test_add"]},
        ),
        "the same cosmetic change as a behavior task is a finding": (
            {"calc.py": "def add(a, b):\n    return a + b\n"},
            {"calc.py": cosmetic_calc,
             "tests/test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(4, 5) == 9\n"},
            False,
            {"verdict": "FINDING", "flipped": [], "unflipped": ["test_add"]},
        ),
        "refactor with one flip is a finding": (
            {"calc.py": "def add(a, b):\n    return a + b\n"},
            {"calc.py": cosmetic_calc,
             "tests/test_calc.py":
                 "from calc import add\n\n\ndef test_add():\n    assert add(4, 5) == 9\n\n\n"
                 "def test_add_by_keyword():\n    assert add(left=4, right=5) == 9\n"},
            True,
            {"verdict": "FINDING", "flipped": ["test_add_by_keyword"], "unflipped": ["test_add"]},
        ),
    }


@pytest.mark.parametrize("name", list(scenario_files()))
def test_ablate_classifies_each_test_and_picks_the_verdict(tmp_path, name):
    """Adversarial where: the verdict rule is misapplied - an unflipped test
    ignored on a behavior task, counted under --refactor, a baseline-red test
    counted as unflipped, or a test whose module vanishes after the revert
    dropped silently instead of named as a collection error."""
    base, branch, refactor, expected = scenario_files()[name]
    repo, merge = build_repo(tmp_path, base, branch)

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD, refactor=refactor)

    assert result["merge"] == merge
    for key, want in expected.items():
        assert result[key] == want, f"{name}: {key}"
    assert ablate_dirs(repo) == []


@pytest.mark.parametrize("variant", ["autocrlf-true checkout", "CRLF committed"])
def test_ablate_reverts_cleanly_when_the_tree_has_crlf_line_endings(tmp_path, variant):
    """Adversarial where: the worktree holds CRLF while the patch holds LF
    (autocrlf) or CRLF throughout, the reverse patch is rejected, and a task
    whose tests do depend on its code is reported SKIP instead of PASS."""
    if variant == "autocrlf-true checkout":
        repo, _ = build_repo(
            tmp_path, {"calc.py": BASE_CALC},
            {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS}, autocrlf="true")
    else:
        repo, _ = build_repo(
            tmp_path, {"calc.py": BASE_CALC},
            {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS},
            autocrlf="false", eol="\r\n")

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert (result["verdict"], result["reason"]) == ("PASS", None)
    assert result["flipped"] == ["TestCalc.test_class_add", "test_add"]


def test_ablate_selects_checkpointed_test_files_whose_names_match_no_pattern(tmp_path):
    """Adversarial where: the checkpoint file list is ignored (or looked up
    inside the scratch worktree, where the untracked checkpoint does not
    exist), so `checks/verify_calc.py` is reverted as code and its test
    never runs."""
    repo, _ = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC,
         "checks/verify_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(4, 5) == 9\n"})
    checkpoint = repo / ".compass" / "tmp" / "test-checkpoints" / "TASK-402.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(
        '{"task": "TASK-402", "files": [{"path": "checks/verify_calc.py", '
        '"sha256": "0", "ids": [[null, "test_add"]]}]}', encoding="utf-8")

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert (result["verdict"], result["flipped"]) == ("PASS", ["test_add"])


def test_ablate_leaves_the_real_working_tree_and_worktree_list_untouched(tmp_path):
    """Adversarial where: the revert is applied to the caller's checkout
    instead of the scratch worktree, or the scratch worktree stays
    registered after a clean run."""
    repo, _ = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS})

    ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert git(repo, "status", "--porcelain") == ""
    assert (repo / "calc.py").read_text(encoding="utf-8").replace("\r\n", "\n") == FIXED_CALC
    assert "ablate-" not in worktree_list(repo)
    assert worktree_list(repo).count("worktree ") == 1


def test_ablate_binary_change_that_cannot_be_reverted_is_a_skip_with_gits_message(tmp_path):
    """Adversarial where: a diff holding a binary file fails `git apply -R`
    and the failure is swallowed into PASS or crashes, instead of SKIP
    carrying git's message, with the scratch worktree still removed."""
    repo, _ = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "data.bin": b"\x00\x01\x02\xff\x00",
         "tests/test_calc.py": DEPENDENT_TESTS})

    result = ablatelib.ablate(repo, "TASK-402", PYTEST_CMD)

    assert result["verdict"] == "SKIP"
    assert "data.bin" in result["reason"]
    assert ablate_dirs(repo) == []
    assert "ablate-" not in worktree_list(repo)


def test_ablate_removes_its_worktree_when_the_test_command_forces_an_error(tmp_path):
    """Adversarial where: the scratch worktree is removed only on the happy
    path, so a command printing undecodable bytes (or any error mid-run)
    strands `.claude/worktrees/ablate-TASK-402` and blocks the next run."""
    repo, _ = build_repo(
        tmp_path, {"calc.py": BASE_CALC},
        {"calc.py": FIXED_CALC, "tests/test_calc.py": DEPENDENT_TESTS})
    garbage = (
        f'"{Path(sys.executable).as_posix()}" -c '
        '"import sys; sys.stdout.buffer.write(bytes([255, 254, 200, 10]))" {tests}'
    )

    try:
        ablatelib.ablate(repo, "TASK-402", garbage)
    except Exception:
        pass

    assert ablate_dirs(repo) == []
    assert "ablate-" not in worktree_list(repo)


def test_format_report_names_every_id_and_ends_with_the_verdict_line():
    """Adversarial where: the verdict line is not last (the evidence rerun
    compares last lines), an id label is conflated with its prefix twin
    (`flipped:` inside `unflipped:`), or a SKIP drops git's message."""
    result = {
        "verdict": "FINDING", "merge": "a" * 40, "reason": None,
        "flipped": ["test_a"], "unflipped": ["test_b"], "baseline_red": ["test_c"],
        "collection_errors": ["test_d"],
    }

    lines = [ln.strip() for ln in ablatelib.format_report(result).splitlines() if ln.strip()]

    assert lines[-1] == "ABLATE: FINDING"
    labelled = [ln for ln in lines if re.match(r"^(flipped|unflipped|baseline-red|collection-error): ", ln)]
    assert sorted(labelled) == [
        "baseline-red: test_c", "collection-error: test_d", "flipped: test_a", "unflipped: test_b",
    ]
    skip = dict(result, verdict="SKIP", reason="error: patch failed: x.py:1",
                flipped=[], unflipped=[], baseline_red=[], collection_errors=[])
    assert ablatelib.format_report(skip).splitlines()[-1] == "ABLATE: SKIP: error: patch failed: x.py:1"
