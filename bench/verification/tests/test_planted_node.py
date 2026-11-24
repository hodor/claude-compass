"""Tests for the Node mode of planted.py, the planted-defect probe on a Node package.

Adversarial themes: a Node seed whose planted failures do not hold (task A's
one-line arrow reported as run because the report counts the line but not the
function, a changed line of task C that the driver never reaches, a test of
task B that passes without B's change) makes the second language's measurement
meaningless; a driver that leaves its HTTP server open hangs every check and
rerun; a fixed port makes two probes collide; a c8 installed only where the
build ran is missing in the scratch worktree of `compass evidence rerun`; a
build that stays inside `--lang python` defaults changes the first probe.

Module contract the tests pin
-----------------------------
planted.py   (importable from bench/verification/)
    build(root, *, repo_root, uv="uv", lang="python") -> Path
        lang "node" writes the Node seed (no venv) and installs c8 into
        <root>/.tools; Refused rules are the Python ones.
    run_suite(project, lang="python") -> (bool, str)   `node --test` for "node"
    run_checks(project, *, cli, lang="python") -> [row, ...]   as for Python;
        every check and rerun runs with npm_config_prefix=<project>/.tools
    main(["--lang", "node", ...]) -> int   EXPECTED is shared by both languages
Node seed files: src/core.js (one `exports.<name> = ...` statement per
function), bin/tally.js (command line), src/server.js (HTTP server, route
/top?text=), scripts/drive.js (starts the server on port 0, sends one request,
prints the answer, closes the server). Tests use `node:test`.
"""

import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

TESTS_DIR = Path(__file__).resolve().parent
VERIFICATION_DIR = TESTS_DIR.parent
REPO_ROOT = VERIFICATION_DIR.parents[1]
OVERHEAD_DIR = REPO_ROOT / "bench" / "overhead"

for _path in (OVERHEAD_DIR, VERIFICATION_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import planted  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HAS_NODE = shutil.which("node") is not None and shutil.which("npm") is not None
pytestmark = pytest.mark.skipif(not HAS_NODE, reason="node or npm is not on PATH")
SPEC_IDS = ["O-1", "O-2", "O-3", "K-1", "C-1", "C-2", "C-3"]
TASK_IDS = ["TASK-001", "TASK-002", "TASK-003"]
FORMAT_TOTAL_LINE = 'exports.formatTotal = (n) => n.toLocaleString("en-US");'


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(cwd, *args, check=True):
    done = subprocess.run(
        ["git", "-c", "user.name=tester", "-c", "user.email=tester@example.invalid",
         "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        capture_output=True, text=True, env=clean_env(), check=check, creationflags=NO_WINDOW,
    )
    return done.stdout.strip()


def node_env(project):
    env = clean_env()
    env["npm_config_prefix"] = str(Path(project) / ".tools")
    return env


def run(argv, cwd, *, env=None, timeout=120):
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, env=env or clean_env(),
        timeout=timeout, creationflags=NO_WINDOW,
    )


def tally(project, *args):
    return run(["node", "bin/tally.js", *args], project)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("tally-node-project")
    try:
        return planted.build(root, repo_root=REPO_ROOT, lang="node")
    except planted.ProbeError as error:
        text = str(error).lower()
        if "c8" in text or "npm" in text:
            pytest.skip(f"c8 could not be installed: {error}")
        raise


# ------------------------------------------------------------- Python defaults


@pytest.mark.parametrize("function", ["build", "run_suite", "run_checks"])
def test_lang_defaults_to_python_in_every_entry_point(function):
    """Adversarial where: a default of "node" (or no default) changes what every existing
    caller of the Python probe builds and runs."""
    parameter = inspect.signature(getattr(planted, function)).parameters.get("lang")
    assert parameter is not None and parameter.default == "python"


# ----------------------------------------------------------------------- build


def test_build_refuses_a_non_empty_folder_for_node_and_leaves_it_untouched(tmp_path):
    """Adversarial where: the Node seed is written over foreign files, or npm runs before
    the refusal, because the Node path skips the Python path's target check."""
    root = tmp_path / "busy"
    root.mkdir()
    (root / "mine.txt").write_text("keep\n", encoding="utf-8")
    with pytest.raises(planted.Refused):
        planted.build(root, repo_root=REPO_ROOT, uv="uv-that-is-not-installed", lang="node")
    assert sorted(p.name for p in root.iterdir()) == ["mine.txt"]


def test_node_build_refuses_a_folder_inside_a_git_work_tree_and_writes_nothing(tmp_path):
    """Adversarial where: the Node project's merges land in an enclosing repository."""
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q")
    inside = outer / "sub" / "proj"
    with pytest.raises(planted.Refused):
        planted.build(inside, repo_root=REPO_ROOT, lang="node")
    assert not inside.exists()
    assert git(outer, "status", "--porcelain") == ""


def test_node_build_has_no_python_venv_and_holds_c8_under_dot_tools(built):
    """Adversarial where: the Node build makes a Python venv it never uses, or c8 lands in
    the global prefix, so the scratch worktree of a rerun cannot find it."""
    assert not (built / ".venv").exists()
    assert not planted.venv_python(built).exists()
    tools = built / ".tools"
    assert tools.is_dir()
    c8_packages = [p for p in tools.rglob("c8") if (p / "package.json").is_file()]
    assert c8_packages, "no c8 package under .tools"


def test_node_build_leaves_a_clean_work_tree_tracking_no_installed_tools(built):
    """Adversarial where: .tools, node_modules or a coverage folder is committed or left
    untracked, so records commit dirty or a rerun worktree carries megabytes."""
    assert git(built, "status", "--porcelain") == ""
    tracked = git(built, "ls-files").splitlines()
    assert not [t for t in tracked if t.startswith((".tools/", "node_modules/", "coverage/", ".claude/"))]


def test_node_built_suite_is_green_under_node_test(built):
    """Adversarial where: a task leaves the node:test suite red, or the suite runner reports
    green on a nonzero exit."""
    green, last = planted.run_suite(built, lang="node")
    assert green is True and last != ""
    done = run(["node", "--test"], built)
    assert done.returncode == 0, done.stdout + done.stderr


def test_node_run_suite_reports_red_for_a_failing_node_test(built):
    """Adversarial where: a failing node:test file is reported green (exit code ignored), or
    the failure leaves the project dirty for the next test."""
    broken = built / "tests" / "zz_broken.test.js"
    broken.write_text(
        'const test = require("node:test");\nconst assert = require("node:assert");\n'
        'test("broken", () => { assert.equal(1, 2); });\n',
        encoding="utf-8",
    )
    try:
        green, last = planted.run_suite(built, lang="node")
    finally:
        broken.unlink()
    assert green is False and last != ""
    assert planted.run_suite(built, lang="node")[0] is True


def test_node_history_is_three_first_parent_no_ff_merges_on_main(built):
    """Adversarial where: a fast-forward lands a task with no merge commit, a merge carries
    the wrong title, or the seed is not the first commit."""
    assert git(built, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    subjects = git(built, "log", "--first-parent", "--format=%s").splitlines()
    merge_subjects = [s for s in subjects if s.startswith("Merge TASK-")]
    assert [re.match(r"Merge (TASK-\d{3}):", s).group(1) for s in reversed(merge_subjects)] == TASK_IDS
    assert subjects[-1] == "Seed the word tally"
    found = planted.merges(built)
    assert sorted(found) == TASK_IDS
    for task, sha in found.items():
        assert len(git(built, "rev-list", "--parents", "-n", "1", sha).split()) == 3
    assert set(git(built, "log", "--all", "--format=%ae").splitlines()) == {"probe@example.invalid"}


def test_node_seed_files_exist_and_keep_one_exports_statement_per_function(built):
    """Adversarial where: a function is defined in a block so a later task's append moves
    an earlier task's lines (their diff ranges are then wrong at HEAD)."""
    for name in ("src/core.js", "bin/tally.js", "src/server.js", "scripts/drive.js"):
        assert (built / name).is_file(), name
    core = (built / "src" / "core.js").read_text(encoding="utf-8")
    for name in ("count", "formatTotal", "top"):
        assert re.search(rf"^exports\.{name} = ", core, re.M), name


def test_each_node_merge_diff_has_the_shape_the_planted_failure_needs(built):
    """Adversarial where: B rewrites more than its one counting line, A or C delete lines, or
    A's helper is more than the single arrow line, so the one-line-function case is gone."""
    found = planted.merges(built)

    def numstat(task):
        sha = found[task]
        for row in git(built, "diff", "--numstat", f"{sha}^1", sha).splitlines():
            added, deleted, name = row.split("\t")
            if name == "src/core.js":
                return int(added), int(deleted)
        raise AssertionError(f"{task} did not change src/core.js")

    a_added, a_deleted = numstat("TASK-001")
    assert a_deleted == 0
    assert numstat("TASK-002") == (1, 1)
    c_added, c_deleted = numstat("TASK-003")
    assert c_added > 0 and c_deleted == 0
    sha = found["TASK-001"]
    patch = git(built, "diff", "-U0", f"{sha}^1", sha, "--", "src/core.js")
    added = [ln[1:] for ln in patch.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    assert [ln for ln in added if ln.strip()] == [FORMAT_TOTAL_LINE]


def test_no_node_source_outside_core_calls_format_total(built):
    """Adversarial where: the command line, server or driver calls formatTotal, so task A's
    helper is reached and the reach check has no planted failure."""
    found = planted.merges(built)
    assert sorted(found) == TASK_IDS
    for name in ("bin/tally.js", "src/server.js", "scripts/drive.js"):
        assert "formatTotal" not in (built / name).read_text(encoding="utf-8"), name
        for sha in found.values():
            shown = git(built, "show", f"{sha}:{name}", check=False)
            assert "formatTotal" not in shown, (sha, name)


# ------------------------------------------------------------- command line


def test_node_command_line_matches_the_planted_defects(built):
    """Adversarial where: a tie sorts alphabetically (C-3 met, no planted failure), case is
    not folded (C-1), an empty text fails (C-2), punctuation is not stripped (O-1), or an
    unknown command exits 0."""
    top = tally(built, "top", "The cat saw the dog")
    assert (top.returncode, top.stdout.strip()) == (0, "the")
    tie = tally(built, "top", "b a")
    assert (tie.returncode, tie.stdout.strip()) == (0, "b")
    empty = tally(built, "top", "")
    assert (empty.returncode, empty.stdout) == (0, "")
    assert tally(built, "count", "one two three").stdout.strip() == "3"
    assert tally(built, "count", "a , b").stdout.strip() == "2"
    punctuated = tally(built, "top", "dog, dog cat")
    assert punctuated.stdout.strip() == "dog"
    unknown = tally(built, "frobnicate", "x")
    assert unknown.returncode != 0 and unknown.stderr.strip() != "" and unknown.stdout == ""


# -------------------------------------------------------------------- driver


def test_driver_answers_the_request_and_exits_zero_with_the_server_closed(built):
    """Adversarial where: the driver leaves the server listening, so the process never exits
    and every check and rerun hangs; or it prints nothing or an HTTP error body."""
    done = run(["node", "scripts/drive.js"], built, timeout=60)
    assert done.returncode == 0, done.stderr
    answer = done.stdout.strip()
    assert answer != "" and len(answer.split()) == 1 and "<" not in answer


def test_concurrent_drivers_all_succeed_because_the_port_is_chosen_by_the_system(built):
    """Adversarial where: a fixed port makes a second probe (or a rerun while the first still
    runs) fail with EADDRINUSE."""
    procs = [
        subprocess.Popen(
            ["node", "scripts/drive.js"], cwd=built, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=clean_env(), creationflags=NO_WINDOW,
        )
        for _ in range(4)
    ]
    results = [(p.communicate(timeout=60), p.returncode) for p in procs]
    assert [code for _, code in results] == [0, 0, 0, 0], [out[1] for out, _ in results]
    assert len({out[0].strip() for out, _ in results}) == 1


# --------------------------------------------------------------------- spec


def test_node_copied_cli_lists_the_seven_requirement_rows_and_plan_names_the_entry_points(built):
    """Adversarial where: the Node spec drifts from the Python one (a row lost or renamed),
    the copied CLI carries tests or caches, or the plan's entry points name no Node command."""
    cli = built / ".claude" / "cli"
    spec = built / ".compass" / "specs" / "SPEC-001-word-tally.md"
    done = run([sys.executable, "-B", str(cli / "compass"), "requirements", str(spec)], built)
    assert done.returncode == 0, done.stderr
    assert [line.split()[0] for line in done.stdout.splitlines() if line.strip()] == SPEC_IDS
    assert (built / ".claude" / "agents" / "validator.md").is_file()
    assert not (cli / "tests").exists()
    assert not any(p.name == "__pycache__" for p in cli.rglob("*"))
    plan = (built / ".compass" / "plans" / "PLAN-001-word-tally.md").read_text(encoding="utf-8")
    for task in TASK_IDS:
        assert f"- [x] {task}:" in plan
    assert "scripts/drive.js" in plan and "bin/tally.js" in plan
    assert "pytest" not in plan


# --------------------------------------------------------------------- reach


def reach(project, command, diff):
    cli = project / ".claude" / "cli" / "compass"
    return run(
        [sys.executable, "-B", str(cli), "reach", "--run", command, "--lang", "node", "--diff", diff],
        project, env=node_env(project), timeout=300,
    )


def test_reach_report_of_task_a_names_format_total_as_an_unreached_function(built):
    """Adversarial where: the one-line arrow is counted as run because its `DA` line hit at
    module load, so reach answers PASS and the planted failure is a miss; or c8 is not found
    through npm_config_prefix."""
    sha = planted.merges(built)["TASK-001"]
    done = reach(built, 'node bin/tally.js count "one two three"', f"{sha}^1..{sha}")
    lines = [ln.strip() for ln in done.stdout.splitlines() if ln.strip()]
    assert any("unreached functions:" in ln and "formatTotal" in ln for ln in lines), done.stdout + done.stderr
    assert lines[-1] == "REACH: FINDING"


def test_reach_of_task_a_passes_when_the_command_calls_format_total(built):
    """Adversarial where: reach flags task A whatever the command does (a false alarm that
    would make the FINDING on A meaningless)."""
    sha = planted.merges(built)["TASK-001"]
    command = "node -e \"console.log(require('./src/core.js').formatTotal(1234))\""
    done = reach(built, command, f"{sha}^1..{sha}")
    lines = [ln.strip() for ln in done.stdout.splitlines() if ln.strip()]
    assert lines and lines[-1] == "REACH: PASS", done.stdout + done.stderr


def test_reach_of_task_c_through_the_driver_runs_every_changed_line(built):
    """Adversarial where: a changed line of task C (the route, the top function, the server)
    is not run by scripts/drive.js, so the reach check has a finding the plan did not plant."""
    sha = planted.merges(built)["TASK-003"]
    done = reach(built, "node scripts/drive.js", f"{sha}^1..{sha}")
    lines = [ln.strip() for ln in done.stdout.splitlines() if ln.strip()]
    assert lines and lines[-1] == "REACH: PASS", done.stdout + done.stderr
    assert not any("unreached functions" in ln for ln in lines)


# --------------------------------------------------------------- run_checks


@pytest.mark.slow
def test_slow_node_run_checks_gives_the_expected_verdicts_and_every_rerun_matches(built):
    """Adversarial where: a check lands on the wrong task, a rerun in the scratch worktree
    cannot find c8 (error) or disagrees with the first run, c8 leaves a coverage folder in
    the work tree, or the checks pass only because the caller's own npm prefix held c8."""
    matrix = {"reach": {"A": "FINDING", "B": "PASS", "C": "PASS"},
              "ablate": {"A": "PASS", "B": "FINDING", "C": "PASS"}}
    cli = built / ".claude" / "cli" / "compass"
    with mock.patch.dict(os.environ):
        os.environ.pop("npm_config_prefix", None)
        os.environ.pop("NPM_CONFIG_PREFIX", None)
        results = planted.run_checks(built, cli=cli, lang="node")
    assert [(r["letter"], r["task"], r["check"]) for r in results] == [
        (letter, task, check) for letter, task in planted.TASKS for check in ("reach", "ablate")
    ]
    for row in results:
        assert row["verdict"] == row["expected"] == matrix[row["check"]][row["letter"]], row
        assert row["rerun"] == "match", row
        record = row["record"]
        assert record.endswith(".json") and "\\" not in record and not Path(record).is_absolute()
        assert git(built, "ls-files", "--", record) == record
    subjects = git(built, "log", "--format=%s").splitlines()
    for _, task in planted.TASKS:
        for check in ("reach", "ablate"):
            assert f"Record {task} {check} evidence" in subjects
    assert git(built, "status", "--porcelain") == ""
    assert planted.run_suite(built, lang="node")[0] is True


# ---------------------------------------------------------------------- main


def stub_main(monkeypatch, calls, *, reach_a="FINDING"):
    def build(root, **kwargs):
        calls["build"] = kwargs
        Path(root).mkdir(parents=True, exist_ok=True)
        return Path(root)

    def suite(project, **kwargs):
        calls["suite"] = kwargs
        return True, "1 passed"

    def checks(project, **kwargs):
        calls["checks"] = kwargs
        out = []
        for letter, task in planted.TASKS:
            for check in ("reach", "ablate"):
                verdict = planted.EXPECTED[check][letter]
                if (check, letter) == ("reach", "A"):
                    verdict = reach_a
                out.append({"letter": letter, "task": task, "check": check, "verdict": verdict,
                            "expected": planted.EXPECTED[check][letter],
                            "record": f"r/{task}-{check}.json", "rerun": "match"})
        return out

    monkeypatch.setattr(planted, "build", build)
    monkeypatch.setattr(planted, "run_suite", suite)
    monkeypatch.setattr(planted, "run_checks", checks)


def test_main_lang_node_passes_node_to_build_suite_and_checks(monkeypatch, tmp_path, capsys):
    """Adversarial where: --lang is parsed but one stage still builds or runs the Python
    probe, so the report mixes languages."""
    calls = {}
    stub_main(monkeypatch, calls)
    assert planted.main(["--lang", "node", "--root", str(tmp_path / "p")]) == 0
    assert calls["build"].get("lang") == "node"
    assert calls["suite"].get("lang") == "node"
    assert calls["checks"].get("lang") == "node"
    out = capsys.readouterr().out
    assert "reach A: FINDING" in out and "ablate B: FINDING" in out


def test_main_without_lang_keeps_the_python_probe(monkeypatch, tmp_path):
    """Adversarial where: the default language changes, so `planted.py` with no flag builds
    the Node project."""
    calls = {}
    stub_main(monkeypatch, calls)
    assert planted.main(["--root", str(tmp_path / "p")]) == 0
    for stage in ("build", "suite", "checks"):
        assert calls[stage].get("lang", "python") == "python", stage


def test_main_rejects_an_unknown_language(monkeypatch, tmp_path):
    """Adversarial where: an unknown language falls through to the Python probe and builds
    a project nobody asked for."""
    calls = {}
    stub_main(monkeypatch, calls)
    assert planted.main(["--lang", "node", "--root", str(tmp_path / "ok")]) == 0
    calls.clear()
    with pytest.raises(SystemExit) as stopped:
        planted.main(["--lang", "ruby", "--root", str(tmp_path / "p")])
    assert stopped.value.code == 2
    assert calls == {}


def test_main_reports_a_pass_on_task_a_as_a_miss_and_exits_one(monkeypatch, tmp_path, capsys):
    """Adversarial where: when the Node reach check answers PASS on task A, the run adjusts
    EXPECTED or exits 0 instead of reporting the miss."""
    calls = {}
    stub_main(monkeypatch, calls, reach_a="PASS")
    assert planted.main(["--lang", "node", "--root", str(tmp_path / "p")]) == 1
    assert "reach A: PASS" in capsys.readouterr().out
    assert planted.EXPECTED["reach"]["A"] == "FINDING"


def test_main_node_json_holds_the_same_keys_as_the_python_run(monkeypatch, tmp_path):
    """Adversarial where: the Node run writes a different JSON shape, so a comparison page
    cannot read both languages from one schema."""
    calls = {}
    stub_main(monkeypatch, calls)
    target = tmp_path / "out.json"
    assert planted.main(["--lang", "node", "--root", str(tmp_path / "p"), "--json", str(target)]) == 0
    assert sorted(json.loads(target.read_text(encoding="utf-8"))) == ["checks", "judge", "suite", "wall_seconds"]
