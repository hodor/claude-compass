"""Engine behind `compass ablate`: revert a task's code in a scratch git
worktree and report which of the task's tests depend on it.

A task's tests are only evidence when they fail without the code they test.
`ablate` finds the task's merge commit, checks it out in a throwaway
worktree, runs the test command once (baseline), reverts the merge's
non-test changes with `git apply -R`, and runs the command again. A test
green at baseline and not green afterwards is `flipped`; one green in both
runs is `unflipped`; one green at baseline that vanishes from the second run
(its file no longer imports) is a `collection_error`; one not green at
baseline is `baseline_red` and takes no part in the verdict.

Per-test outcomes come from the run-output parser in
`commands/test_checkpoint.py`, so the test command must print one line per
test in a format that parser reads (`pytest -v`, `unittest -v`, TAP).
"""

import fnmatch
import json
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from commands import test_checkpoint

TESTS_PLACEHOLDER = "{tests}"
_TEST_NAME_PATTERNS = ("test_*", "*_test.*", "*.test.*", "*.spec.*")
_DEF_RE = re.compile(r"(?:async\s+)?def\s+(\w+)")
_ADDED_DEF_RE = re.compile(r"^\+\s*(?:async\s+)?def\s+(\w+)", re.MULTILINE)
_GIT_DIFF_FLAGS = (
    "--no-renames", "--no-ext-diff", "--no-color",
    "--src-prefix=a/", "--dst-prefix=b/",
)


def _git(repo, *args, stdin=None):
    """Run git in `repo`; returns a CompletedProcess with bytes output."""
    return subprocess.run(
        ["git", "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
         *args],
        cwd=str(repo), input=stdin, capture_output=True,
    )


def _text(data):
    return data.decode("utf-8", errors="replace")


def find_merge_commit(repo, task, merge=None):
    """Full sha of the task's merge commit, or None.

    With `merge`, that revision resolved to a full sha. Otherwise the newest
    first-parent commit on the current branch whose subject starts
    `Merge <task>:`; the colon keeps `TASK-40` from matching `TASK-402`."""
    if merge:
        done = _git(repo, "rev-parse", "--verify", "--quiet", f"{merge}^{{commit}}")
        sha = _text(done.stdout).strip()
        return sha if done.returncode == 0 and sha else None
    done = _git(repo, "log", "--first-parent", "--format=%H%x00%s")
    if done.returncode != 0:
        return None
    prefix = f"Merge {task}:"
    for line in _text(done.stdout).splitlines():
        sha, _, subject = line.partition("\x00")
        if subject.startswith(prefix):
            return sha
    return None


def _is_test_file_name(path):
    base = PurePosixPath(path).name
    return any(fnmatch.fnmatchcase(base, pattern) for pattern in _TEST_NAME_PATTERNS)


def split_diff_paths(paths, checkpoint_files=()):
    """`(test_paths, code_paths)`, each in input order. A path is a test path
    when it is a checkpoint file, sits under a directory named `tests`, or
    has a test-style file name (`test_*`, `*_test.*`, `*.test.*`, `*.spec.*`)."""
    checkpointed = set(checkpoint_files)
    tests, code = [], []
    for path in paths:
        parts = PurePosixPath(path).parts
        is_test = (
            path in checkpointed
            or "tests" in parts[:-1]
            or _is_test_file_name(path)
        )
        (tests if is_test else code).append(path)
    return tests, code


def _checkpoint_files(repo, task):
    """Repo-relative paths of the task's checkpointed test files, read from
    the real repo (the checkpoint is untracked, so a scratch checkout lacks
    it). Empty when there is no readable checkpoint."""
    path = Path(repo) / ".compass" / "tmp" / "test-checkpoints" / f"{task}.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("files", [])
        return [
            e["path"] for e in entries
            if isinstance(e, dict) and isinstance(e.get("path"), str)
        ]
    except (OSError, ValueError, AttributeError, TypeError):
        return []


def _name_status(repo, merge):
    """`[(status_letter, path)]` for `<merge>^1..<merge>`, or None with git's
    message as the second value when the diff cannot be taken."""
    done = _git(repo, "diff", "--name-status", "-z", *_GIT_DIFF_FLAGS, f"{merge}^1", merge)
    if done.returncode != 0:
        return None, _text(done.stderr).strip()
    tokens = _text(done.stdout).split("\x00")
    rows = []
    for i in range(0, len(tokens) - 1, 2):
        rows.append((tokens[i][:1], tokens[i + 1]))
    return rows, None


def _worktree_path(repo, task):
    return Path(repo) / ".claude" / "worktrees" / f"ablate-{task}"


def _remove_worktree(repo, path):
    _git(repo, "worktree", "remove", "--force", str(path))
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    _git(repo, "worktree", "prune")


def _run_tests(worktree, cmd, test_files):
    """Output text of the test command run in `worktree` over `test_files`.
    Bytecode caching is off so a source file rewritten within the same second
    and size cannot be served from a stale compiled copy."""
    quoted = [f'"{p}"' if " " in p else p for p in test_files]
    command = cmd.replace(TESTS_PLACEHOLDER, " ".join(quoted))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run(
        command, shell=True, cwd=str(worktree), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return _text(done.stdout)


def _test_ids(output):
    """`{id: status}` from run output; an id is `name` or `Class.name`."""
    parsed = test_checkpoint._tests_by_class_and_name(
        test_checkpoint._parse_run_evidence(output))
    return {
        (name if class_name is None else f"{class_name}.{name}"): status
        for (class_name, name), status in parsed.items()
    }


def _new_test_names(repo, merge, name_status, test_files, checkpoint_files, test_patch):
    """Names of the tests the task introduced: every test in a checkpointed
    file or a test file the merge adds, plus the tests defined on added lines
    of a changed test file."""
    names = set()
    added = {path for status, path in name_status if status == "A"}
    for path in test_files:
        if path in added or path in checkpoint_files:
            done = _git(repo, "show", f"{merge}:{path}")
            if done.returncode == 0:
                names.update(_DEF_RE.findall(_text(done.stdout)))
    names.update(_ADDED_DEF_RE.findall(test_patch))
    return names


def ablate(repo, task, cmd, refactor=False, merge=None):
    """Run the ablation and return the result dict (see `format_report`).

    Keys: verdict (`PASS`, `FINDING`, `SKIP`), merge, flipped, unflipped,
    baseline_red, collection_errors, reason."""
    result = {
        "verdict": "SKIP", "merge": None, "flipped": [], "unflipped": [],
        "baseline_red": [], "collection_errors": [], "reason": None,
    }
    sha = find_merge_commit(repo, task, merge)
    if sha is None:
        result["reason"] = (
            f"no {merge} commit" if merge
            else f"no Merge {task}: commit on this branch"
        )
        return result
    result["merge"] = sha

    name_status, problem = _name_status(repo, sha)
    if name_status is None:
        result["reason"] = problem or "git diff failed"
        return result
    checkpoint_files = _checkpoint_files(repo, task)
    existing = [p for status, p in name_status if status != "D"]
    changed = [p for _, p in name_status]
    test_paths, code_paths = split_diff_paths(changed, checkpoint_files)
    selected = [p for p in test_paths if p in existing and _is_test_file_name(p)]
    selected += [p for p in checkpoint_files if p not in selected]

    code_patch = b""
    if code_paths:
        done = _git(
            repo, "--literal-pathspecs", "diff", *_GIT_DIFF_FLAGS,
            f"{sha}^1", sha, "--", *code_paths,
        )
        code_patch = done.stdout
    test_patch = ""
    if test_paths:
        done = _git(
            repo, "--literal-pathspecs", "diff", *_GIT_DIFF_FLAGS,
            f"{sha}^1", sha, "--", *test_paths,
        )
        test_patch = _text(done.stdout)

    worktree = _worktree_path(repo, task)
    _git(repo, "worktree", "prune")
    if worktree.exists():
        _remove_worktree(repo, worktree)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    added = _git(repo, "worktree", "add", "--detach", str(worktree), sha)
    if added.returncode != 0:
        result["reason"] = _text(added.stderr).strip() or "git worktree add failed"
        _remove_worktree(repo, worktree)
        return result
    try:
        selected = [p for p in selected if (worktree / p).is_file()]
        baseline = _test_ids(_run_tests(worktree, cmd, selected))
        green = {i for i, status in baseline.items() if status == "ok"}
        result["baseline_red"] = sorted(set(baseline) - green)

        after = dict(baseline)
        if code_patch.strip():
            applied = _git(
                worktree, "apply", "-R", "--ignore-whitespace",
                "--whitespace=nowarn", "-", stdin=code_patch,
            )
            if applied.returncode != 0:
                result["reason"] = _text(applied.stderr).strip() or "git apply -R failed"
                return result
            after = _test_ids(_run_tests(worktree, cmd, selected))
            candidates = {i for i in green if after.get(i) != "ok" and i in after}
            if candidates:
                rerun = _test_ids(_run_tests(worktree, cmd, selected))
                candidates = {i for i in candidates if rerun.get(i) != "ok"}
            collection = {i for i in green if i not in after}
        else:
            candidates, collection = set(), set()
        result["flipped"] = sorted(candidates)
        result["collection_errors"] = sorted(collection)
        result["unflipped"] = sorted(green - candidates - collection)
    finally:
        _remove_worktree(repo, worktree)

    new_names = _new_test_names(
        repo, sha, name_status, selected, set(checkpoint_files), test_patch)
    unflipped_new = [
        i for i in result["unflipped"]
        if not new_names or i.rsplit(".", 1)[-1] in new_names
    ]
    if refactor:
        finding = bool(result["flipped"])
    else:
        finding = bool(unflipped_new)
    result["verdict"] = "FINDING" if finding else "PASS"
    return result


def format_report(result):
    """One `label: id` line per test, then the verdict as the last line."""
    lines = []
    for label, key in (
        ("flipped", "flipped"), ("unflipped", "unflipped"),
        ("baseline-red", "baseline_red"), ("collection-error", "collection_errors"),
    ):
        lines.extend(f"{label}: {test_id}" for test_id in result.get(key, []))
    verdict = result["verdict"]
    if verdict == "SKIP":
        reason = " ".join(
            part.strip() for part in (result.get("reason") or "").splitlines() if part.strip()
        )
        lines.append(f"ABLATE: SKIP: {reason}" if reason else "ABLATE: SKIP")
    else:
        lines.append(f"ABLATE: {verdict}")
    return "\n".join(lines)
