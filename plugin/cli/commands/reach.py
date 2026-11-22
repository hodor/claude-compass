"""`compass reach --report <file> --diff <range> [--repo <dir>]` - the changed
lines of a diff that a coverage report shows as never run.

Reads an LCOV or Cobertura report, takes the added and changed lines of
non-test files from `git diff -U0 <range>` in the repository, and prints per
file `path: N of M changed lines run`, the unrun line numbers, and the
functions that start on a changed line and never ran. A changed file the
report does not name prints `path: not in the measurement` and makes the
verdict a finding.

The last line is `REACH: PASS`, `REACH: FINDING`, `REACH: N/A` or
`REACH: SKIP: <reason>`. A missing, empty or unreadable report, and a report
naming none of the changed files, are SKIP verdicts, never a percentage; a
diff with no executable change is N/A. Exit 0 for every verdict; exit 1 for
bad arguments or a range git cannot resolve.
"""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import reachlib

USAGE = "usage: compass reach --report <file> --diff <range> [--repo <dir>]"


def _parse_args(args):
    """Return `(options, error)`, with exactly one side set."""
    options = {"report": None, "diff": None, "repo": None}
    index = 0
    while index < len(args):
        flag = args[index]
        if flag not in ("--report", "--diff", "--repo"):
            return None, f"unknown argument {flag}"
        if index + 1 >= len(args):
            return None, f"{flag} requires a value"
        options[flag[2:]] = args[index + 1]
        index += 2
    if options["report"] is None:
        return None, "--report is required"
    if options["diff"] is None:
        return None, "--diff is required"
    return options, None


def _git_diff(repo, diff_range):
    """Return `(diff text, error)` for `git diff -U0` over the range."""
    try:
        proc = subprocess.run(
            [
                "git", "-C", repo, "-c", "core.quotepath=false",
                "diff", "-U0", "--no-color", "--no-ext-diff", diff_range,
            ],
            capture_output=True,
        )
    except OSError as exc:
        return None, f"cannot run git: {exc}"
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        return None, f"git diff {diff_range} failed: {detail}"
    return proc.stdout.decode("utf-8", "replace"), None


def _load_coverage(report_path, repo_root):
    """Return `(coverage, reason)`: the parsed report, or None with the reason
    no measurement exists."""
    try:
        with open(report_path, "rb") as handle:
            text = handle.read().decode("utf-8-sig", "replace")
    except OSError:
        return None, "no measurement"
    try:
        coverage = reachlib.parse_report(text, repo_root)
    except (ET.ParseError, ValueError, TypeError):
        return None, "no measurement: report unreadable"
    if not coverage:
        return None, "no measurement"
    return coverage, None


def _format_numbers(numbers):
    return ", ".join(str(n) for n in numbers)


def run(args):
    options, error = _parse_args(args)
    if error:
        sys.stderr.write(f"compass reach: {error}\n{USAGE}\n")
        return 1
    repo = options["repo"] or os.getcwd()
    if not os.path.isdir(repo):
        sys.stderr.write(f"compass reach: not a directory: {repo}\n")
        return 1
    diff_text, error = _git_diff(repo, options["diff"])
    if error:
        sys.stderr.write(f"compass reach: {error}\n")
        return 1
    changed = reachlib.changed_lines_from_diff(diff_text)
    coverage, reason = _load_coverage(options["report"], os.path.abspath(repo))
    result = reachlib.evaluate(coverage, changed)
    if result["verdict"] == "SKIP" and reason:
        result["reason"] = reason
    for entry in result["files"]:
        if not entry["measured"]:
            print(f"{entry['path']}: not in the measurement")
            continue
        if entry["total"] == 0 and not entry["unreached_functions"]:
            continue
        print(
            f"{entry['path']}: {entry['run']} of {entry['total']} changed lines run"
        )
        if entry["unrun"]:
            print(f"  unrun lines: {_format_numbers(entry['unrun'])}")
        if entry["unreached_functions"]:
            print(f"  unreached functions: {', '.join(entry['unreached_functions'])}")
    if result["verdict"] == "SKIP":
        print(f"REACH: SKIP: {result['reason']}")
    else:
        print(f"REACH: {result['verdict']}")
    return 0
