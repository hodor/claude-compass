"""Tests for planted.py, the planted-defect probe of the verification steps.

Adversarial themes: a seeded project whose planted failures do not hold (a task
whose change is reached, a test that depends on the change, a tie that sorts
alphabetically) makes every later measurement meaningless; a build that writes
into a non-empty folder or a git work tree damages foreign files; a verdict
parser that takes a quoted `REACH:` mid-line reads prose as a result; a report
that carries a path, sha or temp folder leaks the machine into a committed
page; a judge parser that keeps the first of a repeated row, or counts an
absent row as met, scores the validator on text it did not write.

Module contract the tests pin
-----------------------------
planted.py   (importable from bench/verification/)
    TASKS                [("A", "TASK-001"), ("B", "TASK-002"), ("C", "TASK-003")]
    EXPECTED             {"reach": {"A": "FINDING", "B": "PASS", "C": "PASS"},
                          "ablate": {"A": "PASS", "B": "FINDING", "C": "PASS"}}
    JUDGE_OWNED          {"O-3": "met", "K-1": "met", "C-1": "met", "C-2": "met",
                          "C-3": "unmet"}
    UNMET                {"partial", "missing", "contradicts"}
    Refused, JudgeError  exceptions
    build(root, *, repo_root, uv="uv") -> Path
        root missing or an empty folder outside any git work tree, else Refused
        (before anything is written). Seeds the `tally` project, lands three
        `--no-ff` merges `Merge TASK-00N: <title>` on `main`, copies
        plugin/cli (no tests/, no __pycache__/) to <root>/.claude/cli and
        plugin/templates/agents/validator.md to <root>/.claude/agents/.
    venv_python(project) -> Path
    merges(project) -> {"TASK-001": sha, ...}   first-parent merge commits
    run_suite(project) -> (green: bool, last_line: str)
    verdict(output, prefix) -> str | None
        the word after the last line that starts `<prefix>: `
    run_checks(project, *, cli) -> [{"letter", "task", "check", "verdict",
                                     "expected", "record", "rerun"}]
        A reach, A ablate, B reach, ... ; rerun is match | mismatch | error
    format_lines(green, suite_line, checks) -> [str]
    judge_prompt(project) -> str
    parse_judge(text) -> {id: status}
    score_judge(statuses) -> {"planted_flagged", "false_positives",
                              "missing_rows", "other_rows"}
    judge(project, *, repo_root, private_root=None, claude_cmd=None) -> dict
        {"statuses", "score", "tokens", "turns", "seconds"}; JudgeError when
        the session is not `done` or no REQ line comes back
    main(argv) -> int     [--root DIR] [--judge] [--json FILE]; 0 only when every
                          check equals EXPECTED, the suite is green and every
                          rerun matches
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
VERIFICATION_DIR = TESTS_DIR.parent
REPO_ROOT = VERIFICATION_DIR.parents[1]
OVERHEAD_DIR = REPO_ROOT / "bench" / "overhead"

for _path in (REPO_ROOT / "plugin" / "cli", OVERHEAD_DIR / "tests", OVERHEAD_DIR, VERIFICATION_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import fake_claude  # noqa: E402
import planted  # noqa: E402
from fake_reply_claude import fake_reply  # noqa: E402,F401  (pytest fixture)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HAS_UV = shutil.which("uv") is not None
needs_uv = pytest.mark.skipif(not HAS_UV, reason="uv is not on PATH")
SPEC_IDS = ["O-1", "O-2", "O-3", "K-1", "C-1", "C-2", "C-3"]
TASK_IDS = ["TASK-001", "TASK-002", "TASK-003"]


def git(cwd, *args, check=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(
        ["git", "-c", "user.name=tester", "-c", "user.email=tester@example.invalid",
         "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        capture_output=True, text=True, env=env, check=check, creationflags=NO_WINDOW,
    )
    return done.stdout.strip()


def run_tally(project, *args):
    return subprocess.run(
        [str(planted.venv_python(project)), "-m", "tally", *args],
        cwd=project, capture_output=True, text=True, creationflags=NO_WINDOW,
    )


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not HAS_UV:
        pytest.skip("uv is not on PATH")
    root = tmp_path_factory.mktemp("tally-project")
    return planted.build(root, repo_root=REPO_ROOT)


# ----------------------------------------------------------------- constants


def test_venv_python_path_follows_the_platform_without_needing_the_folder():
    """Adversarial where: the posix layout is used on Windows (or the reverse), so every
    suite and check command points at a python that does not exist."""
    project = Path("somewhere") / "proj"
    tail = Path(".venv") / ("Scripts" if sys.platform == "win32" else "bin")
    exe = "python.exe" if sys.platform == "win32" else "python"
    assert planted.venv_python(project) == project / tail / exe


# -------------------------------------------------------------- build refusals


def test_build_refuses_a_non_empty_folder_and_leaves_it_untouched(tmp_path):
    """Adversarial where: the seed is written over foreign files, or the folder is
    changed before the refusal."""
    root = tmp_path / "busy"
    root.mkdir()
    (root / "mine.txt").write_text("keep\n", encoding="utf-8")
    (root / ".hidden").write_text("keep\n", encoding="utf-8")
    with pytest.raises(planted.Refused):
        planted.build(root, repo_root=REPO_ROOT, uv="uv-that-is-not-installed")
    assert sorted(p.name for p in root.iterdir()) == [".hidden", "mine.txt"]
    assert (root / "mine.txt").read_text(encoding="utf-8") == "keep\n"


def test_build_refuses_a_folder_inside_a_git_work_tree_and_writes_nothing(tmp_path):
    """Adversarial where: the seeded project's merges land in an enclosing repository,
    rewriting its history, or the folder is created before the refusal."""
    outer = tmp_path / "outer"
    outer.mkdir()
    git(outer, "init", "-q")
    inside_missing = outer / "sub" / "proj"
    with pytest.raises(planted.Refused):
        planted.build(inside_missing, repo_root=REPO_ROOT, uv="uv-that-is-not-installed")
    assert not inside_missing.exists()
    inside_empty = outer / "empty"
    inside_empty.mkdir()
    with pytest.raises(planted.Refused):
        planted.build(inside_empty, repo_root=REPO_ROOT, uv="uv-that-is-not-installed")
    assert list(inside_empty.iterdir()) == []
    assert git(outer, "status", "--porcelain") == ""


# --------------------------------------------------------------- built project


@needs_uv
def test_built_project_has_a_green_suite_and_one_python_venv(built):
    """Adversarial where: a task leaves the suite red or the venv lacks pytest or
    coverage, so the probe measures an environment fault instead of a check."""
    green, last = planted.run_suite(built)
    assert green is True and "passed" in last and "failed" not in last
    assert planted.venv_python(built).is_file()
    done = subprocess.run(
        [str(planted.venv_python(built)), "-c", "import coverage, pytest"],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    assert done.returncode == 0, done.stderr


@needs_uv
def test_built_history_is_three_first_parent_no_ff_merges_on_main(built):
    """Adversarial where: a fast-forward lands a task with no merge commit, a merge
    carries the wrong title, or the seed is not the first commit."""
    assert git(built, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    subjects = git(built, "log", "--first-parent", "--format=%s").splitlines()
    merge_subjects = [s for s in subjects if s.startswith("Merge TASK-")]
    assert [re.match(r"Merge (TASK-\d{3}):", s).group(1) for s in reversed(merge_subjects)] == TASK_IDS
    assert subjects[-1] == "Seed the word tally"
    found = planted.merges(built)
    assert sorted(found) == TASK_IDS
    for task, sha in found.items():
        assert len(git(built, "rev-list", "--parents", "-n", "1", sha).split()) == 3
        assert git(built, "log", "-1", "--format=%s", sha).startswith(f"Merge {task}:")
    first_parent = git(built, "log", "--first-parent", "--format=%H").splitlines()
    positions = [first_parent.index(found[t]) for t in TASK_IDS]
    assert positions == sorted(positions, reverse=True)


@needs_uv
def test_each_task_branch_commit_is_titled_and_authored_by_the_probe(built):
    """Adversarial where: the task commits carry the machine's git identity, leaking a
    name into the committed project."""
    for task in TASK_IDS:
        subjects = git(built, "log", "--all", "--format=%s", f"--grep=^{task}: ").splitlines()
        assert any(s.startswith(f"{task}: ") for s in subjects), task
    assert set(git(built, "log", "--all", "--format=%ae").splitlines()) == {"probe@example.invalid"}


@needs_uv
def test_each_merge_diff_has_the_shape_the_planted_failure_needs(built):
    """Adversarial where: task B rewrites more than the one line, or A/C delete lines, so
    the earlier tasks' diff lines are not valid at HEAD and reach/ablate are off."""
    found = planted.merges(built)

    def core_numstat(task):
        sha = found[task]
        for row in git(built, "diff", "--numstat", f"{sha}^1", sha).splitlines():
            added, deleted, name = row.split("\t")
            if name == "tally/core.py":
                return int(added), int(deleted)
        raise AssertionError(f"{task} did not change tally/core.py")

    a_added, a_deleted = core_numstat("TASK-001")
    assert a_added > 0 and a_deleted == 0
    assert core_numstat("TASK-002") == (1, 1)
    c_added, c_deleted = core_numstat("TASK-003")
    assert c_added > 0 and c_deleted == 0


@needs_uv
def test_seeded_sources_hold_the_planted_shapes_at_each_merge(built):
    """Adversarial where: A's helper is called from the CLI (so it is reached), C's
    return is split across lines (so a changed line is not run), B keeps the old line,
    or a test file is missing."""
    found = planted.merges(built)

    def at(task, name):
        return git(built, "show", f"{found[task]}:{name}")

    assert 'return f"{n:,}"' in at("TASK-001", "tally/core.py")
    assert "format_total" not in at("TASK-003", "tally/__main__.py")
    assert "return len(text.split())" not in at("TASK-002", "tally/core.py")
    final = at("TASK-003", "tally/core.py")
    assert 'return max(counts, key=counts.get) if counts else ""' in final
    assert "Counter" in final and "def format_total(n):" in final
    assert 'count("one two") == 2' in at("TASK-002", "tests/test_punct.py")
    assert 'count("a b c") == 3' in at("TASK-002", "tests/test_punct.py")
    assert 'format_total(1234) == "1,234"' in at("TASK-001", "tests/test_fmt.py")
    top = at("TASK-003", "tests/test_top.py")
    assert 'top("The cat the dog") == "the"' in top and 'top("") == ""' in top
    ignored = set((built / ".gitignore").read_text(encoding="utf-8").split())
    assert {".venv/", ".claude/", ".compass/tmp/", "__pycache__/"} <= ignored


@needs_uv
def test_command_line_behavior_matches_the_planted_defects(built):
    """Adversarial where: a tie sorts alphabetically (C-3 met, no planted failure), case
    is not folded (C-1), an empty text fails (C-2), or B's punctuation strip is absent."""
    top = run_tally(built, "top", "The cat saw the dog")
    assert (top.returncode, top.stdout.strip()) == (0, "the")
    tie = run_tally(built, "top", "b a")
    assert (tie.returncode, tie.stdout.strip()) == (0, "b")
    empty = run_tally(built, "top", "")
    assert (empty.returncode, empty.stdout) == (0, "")
    counted = run_tally(built, "count", "one two three")
    assert counted.stdout.strip() == "3"
    stripped = run_tally(built, "count", "a , b")
    assert stripped.stdout.strip() == "2"
    unknown = run_tally(built, "frobnicate", "x")
    assert unknown.returncode == 2 and unknown.stderr.strip() != "" and unknown.stdout == ""


@needs_uv
def test_the_copied_cli_runs_and_lists_the_seven_requirement_rows_without_tests_or_caches(built):
    """Adversarial where: the copied CLI carries its test suite or source __pycache__ (the
    source folder has both), the validator agent is missing, or a malformed bullet, the
    KPI line or a missing constraint drops a requirement row."""
    cli = built / ".claude" / "cli"
    spec = built / ".compass" / "specs" / "SPEC-001-word-tally.md"
    done = subprocess.run(
        [str(planted.venv_python(built)), "-B", str(cli / "compass"), "requirements", str(spec)],
        cwd=built, capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    assert done.returncode == 0, done.stderr
    assert [line.split()[0] for line in done.stdout.splitlines() if line.strip()] == SPEC_IDS
    assert (built / ".claude" / "agents" / "validator.md").is_file()
    assert (REPO_ROOT / "plugin" / "cli" / "tests").is_dir()
    assert not (cli / "tests").exists()
    assert not any(p.name == "__pycache__" for p in cli.rglob("*"))
    plan = (built / ".compass" / "plans" / "PLAN-001-word-tally.md").read_text(encoding="utf-8")
    for task in TASK_IDS:
        assert f"- [x] {task}:" in plan
    assert plan.count("Automated verification: python -m pytest -q") == 3


@needs_uv
def test_run_suite_reports_red_with_the_failing_line(built):
    """Adversarial where: a failing suite is reported green (the exit code is ignored), or
    the last line is empty."""
    broken = built / "tests" / "test_zz_broken.py"
    broken.write_text("def test_broken():\n    assert False\n", encoding="utf-8")
    try:
        green, last = planted.run_suite(built)
    finally:
        broken.unlink()
    assert green is False and "failed" in last
    assert planted.run_suite(built)[0] is True


@needs_uv
@pytest.mark.slow
def test_slow_run_checks_gives_the_expected_verdicts_and_every_rerun_matches(built):
    """Adversarial where: a check lands on the wrong task (reach and ablate swapped), a
    rerun of a record disagrees with its first run, an ablation leaves the work tree
    edited, or the record files are not committed. Takes some seconds."""
    matrix = {"reach": {"A": "FINDING", "B": "PASS", "C": "PASS"},
              "ablate": {"A": "PASS", "B": "FINDING", "C": "PASS"}}
    cli = built / ".claude" / "cli" / "compass"
    results = planted.run_checks(built, cli=cli)
    assert [(r["letter"], r["task"], r["check"]) for r in results] == [
        (letter, task, check) for letter, task in planted.TASKS for check in ("reach", "ablate")
    ]
    for row in results:
        assert row["verdict"] == row["expected"] == matrix[row["check"]][row["letter"]], row
        assert row["rerun"] == "match", row
        record = row["record"]
        assert record.endswith(".json") and "\\" not in record and not Path(record).is_absolute()
        assert (built / record).is_file()
        assert git(built, "ls-files", "--", record) == record
    subjects = git(built, "log", "--format=%s").splitlines()
    for _, task in planted.TASKS:
        for check in ("reach", "ablate"):
            assert f"Record {task} {check} evidence" in subjects
    assert git(built, "status", "--porcelain") == ""
    assert planted.run_suite(built)[0] is True


# --------------------------------------------------------------------- verdict


@pytest.mark.parametrize("output, prefix, expected", [
    ("noise\nREACH: PASS\nmore\nREACH: FINDING\ntail\n", "REACH", "FINDING"),
    ("REACH: FINDING\nREACH: PASS\n", "REACH", "PASS"),
    ("REACH: SKIP: tool missing\n", "REACH", "SKIP"),
    ("ABLATE: N/A\n", "ABLATE", "N/A"),
    ("ABLATE: N/A: no test files\n", "ABLATE", "N/A"),
    ("ABLATE: PASS\nREACH: FINDING\n", "ABLATE", "PASS"),
    ("REACH: PASS\r\nREACH: FINDING\r\n", "REACH", "FINDING"),
    ("REACH: PASS", "REACH", "PASS"),
])
def test_verdict_takes_the_word_after_the_last_matching_line(output, prefix, expected):
    """Adversarial where: the first matching line wins, a SKIP reason or N/A is returned
    whole, a CRLF line keeps its carriage return, or the other check's line is read."""
    assert planted.verdict(output, prefix) == expected


@pytest.mark.parametrize("output, prefix", [
    ("", "REACH"),
    ("no verdict here\n", "REACH"),
    ("ABLATE: PASS\n", "REACH"),
    ("see the note: REACH: PASS expected\n", "REACH"),
    ("REACHABLE: PASS\n", "REACH"),
    ("REACH:PASS\n", "REACH"),
])
def test_verdict_is_none_without_a_line_that_starts_with_the_prefix(output, prefix):
    """Adversarial where: a quoted verdict mid-line, a longer word starting with the
    prefix, or a missing space after the colon is read as a result."""
    assert planted.verdict(output, prefix) is None


def test_a_quoted_prefix_after_a_real_verdict_does_not_replace_it():
    """Adversarial where: the last occurrence anywhere, not the last verdict line, wins."""
    assert planted.verdict("REACH: FINDING\nthe docs say REACH: PASS is possible\n", "REACH") == "FINDING"


# ---------------------------------------------------------------- format_lines


def make_checks(rerun=None, verdict_for=None):
    rerun = rerun or {}
    verdict_for = verdict_for or {}
    rows = []
    for letter, task in planted.TASKS:
        for check in ("reach", "ablate"):
            rows.append({
                "letter": letter, "task": task, "check": check,
                "verdict": verdict_for.get((check, letter), planted.EXPECTED[check][letter]),
                "expected": planted.EXPECTED[check][letter],
                "record": f".compass/tmp/evidence/{task}-{check}-0123456789abcdef.json",
                "rerun": rerun.get((check, letter), "match"),
            })
    return rows


def test_format_lines_for_a_green_suite_are_exact_and_carry_no_path_or_sha():
    """Adversarial where: the report prints a record path, a commit sha, a temp folder or
    the suite's timing line, leaking the machine into the committed page."""
    sha = "0123456789abcdef0123456789abcdef01234567"
    suite_line = f"3 passed in 0.42s ({sha}) C:\\Users\\someone\\AppData\\Local\\Temp\\tally-project"
    lines = planted.format_lines(True, suite_line, make_checks())
    assert lines == [
        "suite: green",
        "suite A: flagged nothing",
        "suite B: flagged nothing",
        "suite C: flagged nothing",
        "reach A: FINDING", "ablate A: PASS",
        "reach B: PASS", "ablate B: FINDING",
        "reach C: PASS", "ablate C: PASS",
        "rerun reach A: match", "rerun ablate A: match",
        "rerun reach B: match", "rerun ablate B: match",
        "rerun reach C: match", "rerun ablate C: match",
    ]
    text = "\n".join(lines)
    assert not re.search(r"[0-9a-f]{12,}", text)
    assert not any(token in text for token in (".json", "/", "\\", "Temp", "tally-project", "passed in"))


def test_format_lines_for_a_red_suite_flag_every_task():
    """Adversarial where: a red suite is reported as green or flags only some tasks, so
    the suite baseline reads as catching a defect it only failed on."""
    lines = planted.format_lines(False, "1 failed, 2 passed in 0.5s", make_checks())
    assert lines[:4] == ["suite: red", "suite A: flagged", "suite B: flagged", "suite C: flagged"]
    assert "flagged nothing" not in "\n".join(lines)


def test_format_lines_carry_each_rerun_status_and_each_actual_verdict():
    """Adversarial where: the rerun line is hardcoded `match`, or the expected verdict is
    printed in place of the actual one."""
    checks = make_checks(rerun={("ablate", "B"): "mismatch", ("reach", "C"): "error"},
                         verdict_for={("reach", "A"): "PASS"})
    lines = planted.format_lines(True, "ok", checks)
    assert "reach A: PASS" in lines and "reach A: FINDING" not in lines
    assert "rerun ablate B: mismatch" in lines
    assert "rerun reach C: error" in lines
    assert "rerun reach A: match" in lines


# ----------------------------------------------------------------- parse_judge


def test_parse_judge_reads_req_lines_and_lets_the_last_of_a_repeated_id_win():
    """Adversarial where: the first of a repeated row wins, prose around the rows is read
    as a row, or a CRLF reply keeps a carriage return in the status."""
    text = (
        "Analysis of the task.\r\n"
        "REQ O-3: met\r\n"
        "REQ C-3: met\r\n"
        "Reconsidering the tie.\r\n"
        "REQ C-3: missing\r\n"
        "REQ K-1: met"
    )
    assert planted.parse_judge(text) == {"O-3": "met", "C-3": "missing", "K-1": "met"}


def test_parse_judge_lowercases_statuses_and_keeps_an_unknown_one_as_given():
    """Adversarial where: a capitalised status is not recognised as UNMET, or an unknown
    status is dropped, hiding a row the judge did answer."""
    parsed = planted.parse_judge("REQ C-3: Missing\nREQ O-1: UNREQUESTED\nREQ O-2: banana\nREQ C-1: Partial")
    assert parsed == {"C-3": "missing", "O-1": "unrequested", "O-2": "banana", "C-1": "partial"}


@pytest.mark.parametrize("text", ["", "no rows at all\n", "the answer is C-3: missing\n"])
def test_parse_judge_gives_nothing_for_text_without_a_req_line(text):
    """Adversarial where: an id with a status outside a REQ line is read as a row."""
    assert planted.parse_judge(text) == {}


# ----------------------------------------------------------------- score_judge

CORRECT = {"O-3": "met", "K-1": "met", "C-1": "met", "C-2": "met", "C-3": "missing"}


def test_score_judge_of_a_correct_reply_flags_the_plant_with_no_false_positive():
    """Adversarial where: a correct judge is scored with a false positive or a missing
    row."""
    score = planted.score_judge(dict(CORRECT))
    assert score["planted_flagged"] is True
    assert score["false_positives"] == []
    assert score["missing_rows"] == []
    assert score["other_rows"] == {}


@pytest.mark.parametrize("status", ["partial", "missing", "contradicts"])
def test_every_unmet_status_for_c3_counts_as_flagging_the_plant(status):
    """Adversarial where: only `missing` is recognised as unmet."""
    assert planted.score_judge({**CORRECT, "C-3": status})["planted_flagged"] is True


@pytest.mark.parametrize("status", ["met", "unrequested", "banana"])
def test_c3_judged_met_or_not_unmet_means_the_plant_is_missed(status):
    """Adversarial where: any non-`met` status, including an unknown one, counts as
    flagging the plant."""
    score = planted.score_judge({**CORRECT, "C-3": status})
    assert score["planted_flagged"] is False
    assert score["false_positives"] == []


def test_a_met_row_judged_unmet_is_a_false_positive_and_c3_never_is():
    """Adversarial where: C-3 is listed as a false positive, or a met row judged partial
    or contradicting is not."""
    score = planted.score_judge({"O-3": "partial", "K-1": "met", "C-1": "missing", "C-2": "contradicts",
                                 "C-3": "missing"})
    assert sorted(score["false_positives"]) == ["C-1", "C-2", "O-3"]
    assert score["planted_flagged"] is True
    assert "C-3" not in score["false_positives"]


def test_a_met_row_judged_unrequested_or_unknown_is_not_a_false_positive():
    """Adversarial where: every status other than `met` is treated as an unmet finding."""
    score = planted.score_judge({**CORRECT, "O-3": "unrequested", "C-1": "banana"})
    assert score["false_positives"] == []


def test_absent_owned_rows_are_listed_and_are_not_false_positives_or_flags():
    """Adversarial where: an absent row is scored as met or unmet, so a judge that
    answered nothing looks perfect or wrong."""
    score = planted.score_judge({"O-3": "met", "K-1": "met"})
    assert sorted(score["missing_rows"]) == ["C-1", "C-2", "C-3"]
    assert score["planted_flagged"] is False
    assert score["false_positives"] == []
    empty = planted.score_judge({})
    assert sorted(empty["missing_rows"]) == ["C-1", "C-2", "C-3", "K-1", "O-3"]
    assert empty["planted_flagged"] is False and empty["other_rows"] == {}


def test_rows_other_tasks_own_go_to_other_rows_and_never_count_against_the_judge():
    """Adversarial where: O-1 and O-2 (owned by other tasks) are scored as false
    positives or reported as missing owned rows."""
    score = planted.score_judge({**CORRECT, "O-1": "missing", "O-2": "met"})
    assert score["other_rows"] == {"O-1": "missing", "O-2": "met"}
    assert score["false_positives"] == [] and score["missing_rows"] == []


# ------------------------------------------------------------------ judge_prompt


def test_judge_prompt_names_the_task_files_command_and_reply_format(tmp_path):
    """Adversarial where: the prompt asks for the whole validation instead of step 4j, a
    different task, or leaves `compass` unresolved so the session finds no CLI."""
    prompt = planted.judge_prompt(tmp_path)
    assert "TASK-003" in prompt
    assert ".compass/plans/PLAN-001-word-tally.md" in prompt
    assert ".compass/specs/SPEC-001-word-tally.md" in prompt
    assert "python .claude/cli/compass" in prompt
    assert "4j" in prompt
    assert "REQ <id>:" in prompt
    for word in ("met", "partial", "missing", "contradicts", "unrequested"):
        assert word in prompt
    assert str(tmp_path) not in prompt


# ------------------------------------------------------------------------ judge


@pytest.fixture
def plugin_repo(tmp_path):
    root = tmp_path / "plugin-repo"
    (root / "plugin").mkdir(parents=True)
    (root / "plugin" / "keep.txt").write_text("keep\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "initial")
    return root


@pytest.fixture
def seeded(tmp_path):
    folder = tmp_path / "judged-project"
    (folder / ".compass" / "plans").mkdir(parents=True)
    (folder / ".compass" / "specs").mkdir(parents=True)
    (folder / ".compass" / "plans" / "PLAN-001-word-tally.md").write_text("plan\n", encoding="utf-8")
    (folder / ".compass" / "specs" / "SPEC-001-word-tally.md").write_text("spec\n", encoding="utf-8")
    return folder


REPLY = (
    "SECRETPROSE the analysis of the diff.\n"
    "REQ O-3: met\nREQ K-1: met\nREQ C-1: met\nREQ C-2: met\nREQ C-3: missing\n"
)


def test_judge_runs_one_validator_session_and_scores_the_reply(seeded, plugin_repo, tmp_path, fake_reply):
    """Adversarial where: the session is not the validator agent, runs without the four
    tools (or with more), omits the task or the CLI command from its prompt, or the
    returned dict carries the answer text."""
    fake_reply.reply(REPLY)
    result = planted.judge(seeded, repo_root=plugin_repo, private_root=tmp_path / "private",
                           claude_cmd=fake_reply.command)
    (call,) = fake_reply.calls()
    argv = call["argv"]
    assert argv[argv.index("--agent") + 1] == "validator"
    assert argv[argv.index("--allowedTools") + 1] == "Read,Grep,Glob,Bash"
    assert "TASK-003" in call["stdin"] and "python .claude/cli/compass" in call["stdin"]
    assert Path(call["cwd"]).resolve() == seeded.resolve()
    assert result["statuses"] == {"O-3": "met", "K-1": "met", "C-1": "met", "C-2": "met", "C-3": "missing"}
    assert result["score"]["planted_flagged"] is True and result["score"]["false_positives"] == []
    assert result["turns"] == 2
    assert isinstance(result["seconds"], (int, float)) and result["seconds"] >= 0
    totals = result["tokens"][fake_claude.MAIN_MODEL]
    assert totals["input"] == 10 and totals["output"] == 5
    assert "SECRETPROSE" not in json.dumps(result)


def test_judge_scores_a_judge_that_misses_the_plant_and_invents_a_gap(seeded, plugin_repo, tmp_path, fake_reply):
    """Adversarial where: the score is computed from a fixed reply shape, hiding a miss or
    a false positive."""
    fake_reply.reply("REQ O-3: met\nREQ K-1: met\nREQ C-1: partial\nREQ C-2: met\nREQ C-3: met\n")
    result = planted.judge(seeded, repo_root=plugin_repo, private_root=tmp_path / "private",
                           claude_cmd=fake_reply.command)
    assert result["score"]["planted_flagged"] is False
    assert result["score"]["false_positives"] == ["C-1"]


def test_judge_raises_when_the_reply_holds_no_req_line(seeded, plugin_repo, tmp_path, fake_reply):
    """Adversarial where: a prose-only reply returns an empty status table that scores as a
    clean miss instead of a failed measurement."""
    fake_reply.reply("The task looks fine to me. No gaps.\n")
    with pytest.raises(planted.JudgeError):
        planted.judge(seeded, repo_root=plugin_repo, private_root=tmp_path / "private",
                      claude_cmd=fake_reply.command)


@pytest.mark.parametrize("mode", ["crash", "error", "limit"])
def test_judge_raises_when_the_session_does_not_finish(seeded, plugin_repo, tmp_path, fake_reply, mode):
    """Adversarial where: a failed or usage-limited session returns an empty or partial
    result as if it were a judged run."""
    fake_reply.reply(REPLY)
    fake_reply.mode(mode)
    with pytest.raises(planted.JudgeError):
        planted.judge(seeded, repo_root=plugin_repo, private_root=tmp_path / "private",
                      claude_cmd=fake_reply.command)


# ------------------------------------------------------------------------- main


def stub_pipeline(monkeypatch, tmp_path, *, green=True, verdict_for=None, rerun=None):
    built_to = tmp_path / "built"
    calls = {"build": [], "judge": 0}

    def fake_build(root, **kwargs):
        calls["build"].append((Path(root), kwargs))
        return Path(root)

    monkeypatch.setattr(planted, "build", fake_build)
    monkeypatch.setattr(planted, "run_suite", lambda project: (green, "1 passed in 0.1s" if green else "1 failed"))
    monkeypatch.setattr(planted, "run_checks", lambda project, *, cli: make_checks(rerun=rerun, verdict_for=verdict_for))

    def fake_judge(project, **kwargs):
        calls["judge"] += 1
        return {"statuses": dict(CORRECT), "score": planted.score_judge(dict(CORRECT)),
                "tokens": {}, "turns": 2, "seconds": 1.0}

    monkeypatch.setattr(planted, "judge", fake_judge)
    return built_to, calls


def test_main_exits_zero_only_when_every_check_matches_the_expected_verdicts(monkeypatch, tmp_path, capsys):
    """Adversarial where: the exit code ignores a wrong verdict, a red suite or a rerun that
    does not match."""
    root, _ = stub_pipeline(monkeypatch, tmp_path)
    assert planted.main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "suite: green" in out and "reach A: FINDING" in out and "wall: " in out
    assert "4j " not in out

    root, _ = stub_pipeline(monkeypatch, tmp_path, verdict_for={("ablate", "B"): "PASS"})
    assert planted.main(["--root", str(root)]) == 1
    root, _ = stub_pipeline(monkeypatch, tmp_path, green=False)
    assert planted.main(["--root", str(root)]) == 1
    root, _ = stub_pipeline(monkeypatch, tmp_path, rerun={("reach", "A"): "mismatch"})
    assert planted.main(["--root", str(root)]) == 1
    root, _ = stub_pipeline(monkeypatch, tmp_path, rerun={("reach", "A"): "error"})
    assert planted.main(["--root", str(root)]) == 1


def test_main_with_judge_prints_each_row_and_the_plant_line_and_writes_json(monkeypatch, tmp_path, capsys):
    """Adversarial where: --judge starts no session, the rows or the flagged/missed line
    are missing, or the json file carries a path or answer text."""
    root, calls = stub_pipeline(monkeypatch, tmp_path)
    target = tmp_path / "out.json"
    assert planted.main(["--root", str(root), "--judge", "--json", str(target)]) == 0
    out = capsys.readouterr().out
    assert calls["judge"] == 1
    for row, status in CORRECT.items():
        assert f"4j {row}: {status}" in out
    assert "4j planted C-3: flagged" in out
    assert "4j false positives: 0" in out
    assert json.loads(target.read_text(encoding="utf-8"))


def test_main_without_root_builds_in_a_new_folder_outside_the_repo(monkeypatch, tmp_path, capsys):
    """Adversarial where: the default build folder is inside the repository, so the
    seeded project's merges land in Compass's own history."""
    _, calls = stub_pipeline(monkeypatch, tmp_path)
    assert planted.main([]) == 0
    ((root, kwargs),) = calls["build"]
    resolved = Path(root).resolve()
    assert REPO_ROOT.resolve() not in (resolved, *resolved.parents)
    assert Path(kwargs.get("repo_root", REPO_ROOT)).resolve() == REPO_ROOT.resolve()
