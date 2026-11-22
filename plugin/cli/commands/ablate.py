"""`compass ablate TASK-NNN --cmd "<test command with {tests}>" [--refactor]
[--merge <sha>] [--repo <dir>]` - check that a task's tests depend on its code.

Finds the task's merge commit, reverts its non-test changes in a scratch git
worktree, and runs the test command before and after. Prints one line per
test (`flipped:`, `unflipped:`, `baseline-red:`, `collection-error:`) and,
as the last line, `ABLATE: PASS`, `ABLATE: FINDING` or
`ABLATE: SKIP: <reason>`. A new test that stays green without the code is a
FINDING; with `--refactor`, any test that goes red is. The verdict line holds
no sha, path or timestamp, so a rerun of the same check prints it unchanged.

`--repo` defaults to the current directory. Exit 0 for all three verdicts,
1 for bad arguments.
"""

import os
import re
import subprocess
import sys

import ablatelib

USAGE = (
    'usage: compass ablate TASK-NNN --cmd "<test command containing {tests}>" '
    "[--refactor] [--merge <sha>] [--repo <dir>]"
)

_VALUE_FLAGS = {"--cmd": "cmd", "--merge": "merge", "--repo": "repo"}


def _parse_args(args):
    """`(options, error)`, exactly one side set."""
    if not args or args[0].startswith("--"):
        return None, "a task id is required"
    task = args[0]
    if not re.fullmatch(r"TASK-[0-9]+", task):
        return None, f"{task!r} is not a task id (TASK-NNN)"
    options = {"task": task, "cmd": None, "merge": None, "repo": None, "refactor": False}
    i = 1
    while i < len(args):
        arg = args[i]
        if arg == "--refactor":
            options["refactor"] = True
            i += 1
        elif arg in _VALUE_FLAGS:
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                return None, f"{arg} expects a value"
            options[_VALUE_FLAGS[arg]] = args[i + 1]
            i += 2
        else:
            return None, f"unknown argument {arg}"
    if options["cmd"] is None:
        return None, "--cmd is required"
    if ablatelib.TESTS_PLACEHOLDER not in options["cmd"]:
        return None, f"--cmd must contain {ablatelib.TESTS_PLACEHOLDER}"
    return options, None


def _is_git_repo(path):
    done = subprocess.run(
        ["git", "rev-parse", "--git-dir"], cwd=path, capture_output=True,
    )
    return done.returncode == 0


def run(args):
    options, error = _parse_args(args)
    if error:
        print(f"compass ablate: {error}\n{USAGE}", file=sys.stderr)
        return 1
    repo = options["repo"] or os.getcwd()
    if not os.path.isdir(repo) or not _is_git_repo(repo):
        print(f"compass ablate: {repo} is not a git repository\n{USAGE}", file=sys.stderr)
        return 1
    result = ablatelib.ablate(
        repo, options["task"], options["cmd"],
        refactor=options["refactor"], merge=options["merge"],
    )
    print(ablatelib.format_report(result))
    return 0
