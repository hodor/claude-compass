"""`compass reach --report <file> --diff <range> [--repo <dir>]` or
`compass reach --run "<command>" --lang python|node --diff <range>
[--repo <dir>] [--python <interpreter>]` - the changed lines of a diff that a
coverage report shows as never run.

Reads an LCOV or Cobertura report, takes the added and changed lines of
non-test files from `git diff -U0 <range>` in the repository, and prints per
file `path: N of M changed lines run`, the unrun line numbers, and the
functions that start on a changed line and never ran. A changed file the
report does not name prints `path: not in the measurement` and makes the
verdict a finding.

`--run` produces the report itself. For Python it writes a coverage rc file
under `.compass/tmp/reach/<UTC>/` and a `compass_reach_cov.pth` startup file
into the interpreter's site-packages, runs the command through the shell with
`COVERAGE_PROCESS_START` set, removes the startup file in a `finally`, then
combines the per-process data files and exports XML; the command itself, its
Python children, pool workers and shell-wrapped hooks all measure themselves.
The interpreter is `--python`, else `venv/` or `.venv/` in the repository,
else `python` on PATH, and must be a virtual environment with coverage 7.10
or newer. For Node the command runs under `npx --no-install c8` with an LCOV
reporter. The command's exit code prints as `run exit: N` and never changes
the verdict.

The last line is `REACH: PASS`, `REACH: FINDING`, `REACH: N/A` or
`REACH: SKIP: <reason>`. A missing, empty or unreadable report, no data file
after a run, an interpreter outside a virtual environment, a missing coverage
or c8, an existing startup file, and a report naming none of the changed
files are SKIP verdicts, never a percentage; a diff with no executable change
is N/A. Exit 0 for every verdict; exit 1 for bad arguments or a range git
cannot resolve.
"""

import datetime
import glob
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import reachlib

USAGE = (
    "usage: compass reach --report <file> --diff <range> [--repo <dir>]\n"
    '       compass reach --run "<command>" --lang python|node --diff <range>'
    " [--repo <dir>] [--python <interpreter>]"
)

_FLAGS = ("report", "run", "lang", "python", "diff", "repo")


def _parse_args(args):
    """Return `(options, error)`, with exactly one side set."""
    options = {name: None for name in _FLAGS}
    index = 0
    while index < len(args):
        flag = args[index]
        if not flag.startswith("--") or flag[2:] not in options:
            return None, f"unknown argument {flag}"
        if index + 1 >= len(args):
            return None, f"{flag} requires a value"
        options[flag[2:]] = args[index + 1]
        index += 2
    if options["report"] is not None and options["run"] is not None:
        return None, "--run and --report are exclusive"
    if options["report"] is None and options["run"] is None:
        return None, "--report or --run is required"
    if options["diff"] is None:
        return None, "--diff is required"
    if options["run"] is None:
        for name in ("lang", "python"):
            if options[name] is not None:
                return None, f"--{name} needs --run"
    else:
        if options["lang"] not in ("python", "node"):
            return None, "--lang must be python or node with --run"
        if options["python"] is not None and options["lang"] != "python":
            return None, "--python needs --lang python"
    return options, None


def _git_diff(repo, diff_range):
    """Return `(diff text, error)` for `git diff -U0` over the range."""
    try:
        proc = subprocess.run(
            [
                "git", "-C", repo, "-c", "core.quotepath=false",
                "diff", "-U0", "--no-color", "--no-ext-diff",
                "--src-prefix=a/", "--dst-prefix=b/", diff_range,
            ],
            capture_output=True,
        )
    except OSError as exc:
        return None, f"cannot run git: {exc}"
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        return None, f"git diff {diff_range} failed: {detail}"
    return proc.stdout.decode("utf-8", "replace"), None


def _load_coverage(report_path, repo_root, changed):
    """Return `(coverage, reason)`: the parsed report, or None with the reason
    no measurement exists."""
    try:
        with open(report_path, "rb") as handle:
            text = handle.read().decode("utf-8-sig", "replace")
    except OSError:
        return None, "no measurement"
    try:
        coverage = reachlib.parse_report(text, repo_root, set(changed))
    except (ET.ParseError, ValueError, TypeError, OverflowError):
        return None, "no measurement: report unreadable"
    if not coverage:
        return None, "no measurement"
    return coverage, None


def _format_numbers(numbers):
    return ", ".join(str(n) for n in numbers)


def _utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _interpreter(repo, given):
    """The interpreter to measure with: `given`, else `venv/` or `.venv/` in
    the repository, else `python` on PATH; None when none exists."""
    if given:
        return given
    folder, name = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    for venv in ("venv", ".venv"):
        candidate = os.path.join(repo, venv, folder, name)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("python")


_PROBE = (
    "import sys, sysconfig\n"
    "print(sys.prefix != sys.base_prefix)\n"
    "print(sysconfig.get_paths()['purelib'])\n"
    "try:\n"
    "    import coverage\n"
    "    print(coverage.__version__)\n"
    "except ImportError:\n"
    "    print('none')\n"
)


def _probe(python):
    """Return `(in_venv, site_packages, coverage_version, error)` for an
    interpreter."""
    try:
        proc = subprocess.run(
            [python, "-I", "-c", _PROBE], capture_output=True, text=True
        )
    except OSError as exc:
        return None, None, None, f"cannot run interpreter {python}: {exc}"
    fields = proc.stdout.splitlines()
    if proc.returncode != 0 or len(fields) < 3:
        return None, None, None, f"cannot inspect interpreter {python}"
    return fields[0].strip() == "True", fields[1].strip(), fields[2].strip(), None


def _run_command(command, repo, env):
    """Run the command through the shell; return `(exit code, error)`. The
    command's own output goes to stderr so stdout carries only the verdict."""
    try:
        proc = subprocess.run(
            command, shell=True, cwd=repo, env=env, capture_output=True
        )
    except OSError as exc:
        return None, f"cannot run the command: {exc}"
    for stream in (proc.stdout, proc.stderr):
        if stream:
            sys.stderr.write(stream.decode("utf-8", "replace"))
    return proc.returncode, None


def _measure_python(options, repo, folder):
    """Return `(report path, exit code, skip reason)` for a Python run."""
    python = _interpreter(repo, options["python"])
    if python is None:
        return None, None, "no measurement: no Python interpreter found"
    in_venv, site, version, error = _probe(python)
    if error:
        return None, None, f"no measurement: {error}"
    if not in_venv:
        return None, None, (
            f"no measurement: {python} is not a virtual environment, and the "
            "startup file would measure every Python process on the machine"
        )
    parsed = reachlib.coverage_version(version)
    if parsed is None:
        return None, None, f"no measurement: coverage is not installed for {python}"
    if parsed < reachlib.MIN_COVERAGE:
        return None, None, f"no measurement: coverage {version} is older than 7.10"
    rc = os.path.join(folder, "coveragerc")
    with open(rc, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(reachlib.coverage_rc(repo, os.path.join(folder, ".coverage")))
    pth = os.path.join(site, reachlib.PTH_NAME)
    try:
        handle = open(pth, "x", encoding="utf-8", newline="\n")
    except FileExistsError:
        return None, None, f"no measurement: {pth} already exists; remove it and run again"
    except OSError as exc:
        return None, None, f"no measurement: cannot write {pth}: {exc}"
    try:
        with handle:
            handle.write(reachlib.PTH_BODY)
        env = dict(os.environ, COVERAGE_PROCESS_START=os.path.abspath(rc))
        code, error = _run_command(options["run"], repo, env)
    finally:
        if os.path.exists(pth):
            os.remove(pth)
    if error:
        return None, None, f"no measurement: {error}"
    if not glob.glob(os.path.join(folder, ".coverage.*")):
        return None, code, "no measurement: the run wrote no coverage data"
    xml_path = os.path.join(folder, "coverage.xml")
    for step in (["combine", "--rcfile", rc], ["xml", "--rcfile", rc, "-o", xml_path]):
        done = subprocess.run(
            [python, "-I", "-m", "coverage", *step], capture_output=True, text=True
        )
        if done.returncode != 0:
            return None, code, "no measurement: coverage could not build a report"
    return xml_path, code, None


def _measure_node(options, repo, folder):
    """Return `(report path, exit code, skip reason)` for a Node run."""
    if shutil.which("npx") is None:
        return None, None, "no measurement: npx is not installed"
    check = subprocess.run(
        "npx --no-install c8 --version", shell=True, cwd=repo, capture_output=True
    )
    if check.returncode != 0:
        return None, None, "no measurement: c8 is not installed"
    command = (
        f'npx --no-install c8 --reporter=lcov --report-dir "{folder}" '
        f'--temp-directory "{os.path.join(folder, "v8")}" {options["run"]}'
    )
    code, error = _run_command(command, repo, os.environ.copy())
    if error:
        return None, None, f"no measurement: {error}"
    report = os.path.join(folder, "lcov.info")
    if not os.path.isfile(report):
        return None, code, "no measurement: the run wrote no coverage data"
    return report, code, None


def _measure(options, repo):
    """Run the command under coverage; return `(report path, skip reason)` and
    print `run exit: N` when the command ran."""
    folder = os.path.join(repo, ".compass", "tmp", "reach", _utc_stamp())
    os.makedirs(folder)
    measure = _measure_python if options["lang"] == "python" else _measure_node
    report, code, reason = measure(options, repo, folder)
    if code is not None:
        print(f"run exit: {code}")
    return report, reason


def run(args):
    options, error = _parse_args(args)
    if error:
        sys.stderr.write(f"compass reach: {error}\n{USAGE}\n")
        return 1
    repo = options["repo"] or os.getcwd()
    if not os.path.isdir(repo):
        sys.stderr.write(f"compass reach: not a directory: {repo}\n")
        return 1
    repo = os.path.abspath(repo)
    diff_text, error = _git_diff(repo, options["diff"])
    if error:
        sys.stderr.write(f"compass reach: {error}\n")
        return 1
    changed = reachlib.changed_lines_from_diff(diff_text)
    if options["run"] is not None:
        report, reason = _measure(options, repo)
    else:
        report, reason = options["report"], None
    if report is None:
        coverage = None
    else:
        coverage, reason = _load_coverage(report, repo, changed)
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
