"""Tests for ablation.py: the station ablation by planted defects.

The pure parts (mutation sites, diff reading, test-output parsing, the
location judge, the eligibility rule) run on literal inputs. Task discovery and
planting run on small git repositories built under pytest's temporary folder.
Sessions run against the fake `claude` of `fake_reply_claude`, never the real
one.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import ablation
import launch
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)


# ------------------------------------------------------------- mutation sites


def _sites(text, lang="python"):
    return ablation.mutation_sites(text, lang)


def _by_class(text, lang="python"):
    found = {}
    for cls, col, old, new in _sites(text, lang):
        found.setdefault(cls, []).append((col, old, new))
    return found


def test_comparison_swaps_each_operator_with_its_neighbour():
    found = _by_class("if a < b and c >= d:")
    pairs = {(old, new) for _col, old, new in found["comparison"]}
    assert pairs == {("<", "<="), (">=", ">")}


def test_comparison_never_splits_a_two_character_operator():
    for text in ("x = a << 2", "y = b >> 1", "def f() -> int:", "v := <-ch", "a <<= 1", "m = {k => v}"):
        lang = "go" if ":=" in text or "<-" in text else "python"
        assert "comparison" not in _by_class(text, lang), text


def test_equality_swaps_both_ways():
    found = _by_class("ok = a == b or c != d")
    assert {(old, new) for _c, old, new in found["equality"]} == {("==", "!="), ("!=", "==")}


def test_logic_swaps_whole_words_in_python():
    found = _by_class("if ready and not done or late:")
    assert {(old, new) for _c, old, new in found["logic"]} == {("and", "or"), ("or", "and")}
    assert "logic" not in _by_class("brand = origin + order")


def test_logic_swaps_go_operators():
    found = _by_class("if a && b || c {", "go")
    assert {(old, new) for _c, old, new in found["logic"]} == {("&&", "||"), ("||", "&&")}


def test_constant_raises_a_whole_integer_by_one():
    found = _by_class("limit = 10 + count")
    assert found["constant"] == [(8, "10", "11")]


def test_constant_skips_identifiers_floats_hex_and_versions():
    for text in ("x2 = v1 + 0.5", "mask = 0xff", "ver = 1.2.3", "a = 1e3", "name_3 = 2.0"):
        assert "constant" not in _by_class(text), text


def test_nothing_inside_strings_or_comments():
    assert _sites('msg = "a < b == c and 3"') == []
    assert _sites("msg = 'x >= 2'  # if a < b") == []
    assert _sites("# limit = 10 if a < b") == []
    assert _sites('s := "a < b" // x == 2', "go") == []
    assert _sites("s := `raw < 3`", "go") == []


def test_a_site_after_a_string_still_counts():
    found = _by_class('label = "n<3" if n < 3 else ""')
    assert ("comparison" in found) and ("constant" in found)
    cols = [col for col, _o, _n in found["comparison"]]
    assert all(col > len('label = "n<3"') for col in cols)


def test_escaped_quote_does_not_end_the_string():
    assert _sites(r'msg = "say \"a < b\" now"') == []


def test_import_and_decorator_lines_give_no_constant():
    assert "constant" not in _by_class("from x import y2")
    assert "constant" not in _by_class("import base64")
    assert "constant" not in _by_class("@retry(3)")
    assert "constant" not in _by_class('import "crypto/sha256"', "go")


def test_apply_site_changes_exactly_one_token():
    text = "if a < b and c < d:"
    sites = [s for s in _sites(text) if s[0] == "comparison"]
    cls, col, old, new = sites[1]
    out = ablation.apply_site(text, col, old, new)
    assert out == "if a < b and c <= d:"
    assert len(out) - len(text) == len(new) - len(old)


def test_apply_site_refuses_a_stale_column():
    with pytest.raises(ValueError):
        ablation.apply_site("if a < b:", 2, "<", "<=")


# ------------------------------------------------------------ paths and diffs


@pytest.mark.parametrize("path,lang,test", [
    ("tests/test_x.py", "python", True),
    ("src/pkg/test_util.py", "python", True),
    ("src/pkg/util_test.py", "python", True),
    ("conftest.py", "python", True),
    ("src/pkg/contest.py", "python", False),
    ("src/pkg/testing_helpers.py", "python", False),
    ("internal/a/a_test.go", "go", True),
    ("internal/a/testdata/x.go", "go", True),
    ("internal/a/a.go", "go", False),
])
def test_is_test_path(path, lang, test):
    assert ablation.is_test_path(path, lang) is test


def test_is_source_path():
    assert ablation.is_source_path("src/a.py", "python")
    assert not ablation.is_source_path("src/a.go", "python")
    assert not ablation.is_source_path("tests/test_a.py", "python")
    assert ablation.is_source_path("cmd/x/main.go", "go")
    assert not ablation.is_source_path("README.md", "go")


DIFF = """diff --git a/src/a.py b/src/a.py
index 1..2 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,4 @@
 def f(x):
-    return x
+    if x < 3:
+        return 0
     return x
@@ -10,2 +11,3 @@ def g():
     pass
+    y = 4
diff --git a/old.py b/old.py
deleted file mode 100644
--- a/old.py
+++ /dev/null
@@ -1 +0,0 @@
-gone = 1
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+a = 1
+++b = 2
"""


def test_added_lines_reads_new_side_numbers_across_hunks_and_files():
    added = ablation.added_lines(DIFF)
    assert added["src/a.py"] == [(2, "    if x < 3:"), (3, "        return 0"), (12, "    y = 4")]
    assert "old.py" not in added
    assert added["new.py"] == [(1, "a = 1"), (2, "++b = 2")]


def test_enclosing_function_python_and_go():
    py = ["import x", "", "def outer(a):", "    b = 1", "    async def inner():", "        return a < b"]
    assert ablation.enclosing_function(py, 6, "python") == "inner"
    assert ablation.enclosing_function(py, 4, "python") == "outer"
    assert ablation.enclosing_function(py, 1, "python") is None
    go = ["package a", "func (s *Stack) Push(v int) {", "  if v > 0 {", "}", "func Pop() int {", "  return 1", "}"]
    assert ablation.enclosing_function(go, 3, "go") == "Push"
    assert ablation.enclosing_function(go, 6, "go") == "Pop"


# ------------------------------------------------------------- test outputs


PYTEST_OUT = """....F.E
=========================== short test summary info ===========================
FAILED tests/test_a.py::test_one - AssertionError: assert 1 == 2
FAILED tests/test_a.py::test_two[case 1]
ERROR tests/test_b.py::test_three - fixture 'x' not found
3 failed, 4 passed
"""

GO_OUT = """=== RUN   TestA
--- FAIL: TestA (0.00s)
=== RUN   TestB
    --- FAIL: TestB/case_1 (0.00s)
--- PASS: TestC (0.00s)
FAIL
"""


def test_failing_tests_pytest():
    assert ablation.failing_tests(PYTEST_OUT, "python") == {
        "tests/test_a.py::test_one", "tests/test_a.py::test_two[case 1]", "tests/test_b.py::test_three",
    }


def test_failing_tests_go():
    assert ablation.failing_tests(GO_OUT, "go") == {"TestA", "TestB/case_1"}


def test_failing_tests_empty_output():
    assert ablation.failing_tests("", "python") == set()


def test_a_test_failing_on_both_states_is_not_caught():
    assert ablation.caught_by_tests({"t1"}, {"t1"}) is False
    assert ablation.caught_by_tests(set(), set()) is False
    assert ablation.caught_by_tests({"t1"}, set()) is False
    assert ablation.caught_by_tests({"t1"}, {"t1", "t2"}) is True


# ---------------------------------------------------------- the location judge


SITE = ablation.Site(path="src/game/combat.py", line=40, cls="comparison", col=8, old="<", new="<=",
                     function="resolve_hit")


@pytest.mark.parametrize("text,credited", [
    ("combat.py:40 compares with <=", True),
    ("see src/game/combat.py:43, the bound", True),
    ("see combat.py:37", True),
    ("see combat.py:44", False),
    ("see combat.py:36", False),
    ("combat.py has a bug", False),
    ("other.py:40 is wrong", False),
    ("resolve_hit lets a tie through", True),
    ("resolve_hits_all is fine", False),
    ("nothing here", False),
])
def test_names_site(text, credited):
    assert ablation.names_site(text, SITE) is credited


def test_names_site_without_a_function_credits_location_only():
    site = ablation.Site(path="a.go", line=5, cls="constant", col=0, old="3", new="4", function=None)
    assert ablation.names_site("a.go:5", site)
    assert not ablation.names_site("None of this", site)


def test_parse_findings():
    text = (
        "Review done.\n"
        "FINDING src/game/combat.py:41: the bound admits a tie\n"
        "- FINDING `src/x.py:3`: unused import\n"
        "**FINDING** **src/y.py:9**: debug print left in\n"
        "FINDING none\n"
    )
    found = ablation.parse_findings(text)
    assert ("src/game/combat.py", 41, "the bound admits a tie") in found
    assert ("src/x.py", 3, "unused import") in found
    assert ("src/y.py", 9, "debug print left in") in found
    assert len(found) == 3
    assert ablation.parse_findings("FINDING none\n") == []


def test_review_caught_by_line_window_or_function():
    assert ablation.review_caught("FINDING src/game/combat.py:42: off by one", SITE)
    assert not ablation.review_caught("FINDING src/game/combat.py:50: off by one", SITE)
    assert not ablation.review_caught("FINDING src/other/combat2.py:40: off by one", SITE)
    assert ablation.review_caught("FINDING src/game/rules.py:3: resolve_hit admits a tie", SITE)
    assert not ablation.review_caught("resolve_hit is wrong, but no FINDING line", SITE)


VALIDATOR_FAIL = """## Validation Report

VERDICT: FAIL

### Phase Results

| Task | Status | Checks |
|---|---|---|
| TASK-012 | FAIL | 2/3 |

The bound in combat.py:40 admits a tie.
"""

VALIDATOR_PASS = VALIDATOR_FAIL.replace("VERDICT: FAIL", "VERDICT: PASS").replace("| FAIL | 2/3 |", "| PASS | 3/3 |")


def test_validator_caught_needs_a_failure_and_the_site():
    assert ablation.validator_caught(VALIDATOR_FAIL, SITE)
    assert not ablation.validator_caught(VALIDATOR_PASS, SITE)
    assert not ablation.validator_caught(VALIDATOR_FAIL.replace("combat.py:40", "elsewhere"), SITE)
    assert not ablation.validator_caught("no report form at all, combat.py:40", SITE)


# ----------------------------------------------------------- eligibility rule


def _r(letter, **caught):
    return {"letter": letter, "caught": {s: caught.get(s.replace("-", "_"), False) for s in ablation.STATIONS}}


def test_a_station_that_alone_caught_one_defect_is_not_eligible():
    results = [_r("M", tester_post=True), _r("M", tester_post=True, validator=True)]
    table = ablation.eligibility(results)
    assert table["M"]["tester-post"] == {"caught": 2, "only": 1, "eligible": False}
    assert table["M"]["validator"] == {"caught": 1, "only": 0, "eligible": True}
    assert table["M"]["tester-pre"]["eligible"] is True
    assert table["M"]["defects"] == 2
    assert table["M"]["none"] == 0


def test_defects_caught_by_no_station_are_counted_apart():
    table = ablation.eligibility([_r("S"), _r("S", tester_pre=True, validator=True)])
    assert table["S"]["none"] == 1
    assert table["S"]["defects"] == 2
    assert table["S"]["tester-pre"]["only"] == 0


def test_a_letter_with_nothing_caught_is_not_eligible():
    table = ablation.eligibility([_r("L"), _r("L")])
    assert all(table["L"][s]["eligible"] is False for s in ablation.STATIONS)


def test_letters_are_kept_apart():
    table = ablation.eligibility([_r("S", validator=True), _r("L", tester_pre=True)])
    assert table["S"]["validator"]["only"] == 1
    assert table["L"]["validator"]["caught"] == 0
    assert set(table) == {"S", "L"}


# ------------------------------------------------------ projects and planting


def _git(repo, *args):
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, **launch.NO_WINDOW)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _commit(repo, files, message):
    for name, text in files.items():
        path = Path(repo, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=probe", "-c", "user.email=probe@example.invalid", "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


PLAN = """# Plan

- [x] TASK-001: Clamp a value - complexity: S, depends_on: none, files: [src/clamp.py, tests/test_clamp.py]
- [x] TASK-002: Two at once - complexity: M, depends_on: none, files: [src/b.py]
- [x] TASK-003: Unlettered task - depends_on: none, files: [src/c.py]
- [ ] TASK-004: Large thing - complexity: L, depends_on: none, files: [src/d.py]
- [x] TASK-005: Extra small - complexity: XS, depends_on: none, files: [src/e.py]
"""

CLAMP = '''def clamp(value, low, high):
    """Clamp value into [low, high]."""
    if value < low:
        return low
    if value > high:
        return high
    return value
'''

CLAMP_TEST = '''from src.clamp import clamp


def test_below():
    assert clamp(-5, 0, 10) == 0


def test_inside():
    assert clamp(5, 0, 10) == 5
'''


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "projects" / "proj-aaaaaa"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "--initial-branch=main")
    _commit(repo, {"pyproject.toml": "[project]\nname='p'\n", ".compass/plans/PLAN-001-x.md": PLAN,
                   "src/__init__.py": ""}, "Seed")
    pre = _commit(repo, {"tests/test_clamp.py": CLAMP_TEST}, "test(TASK-001): failing tests before implementation")
    build = _commit(repo, {"src/clamp.py": CLAMP}, "TASK-001: clamp a value")
    _commit(repo, {"tests/test_b.py": "def test_b():\n    assert True\n"},
            "test(TASK-002, TASK-004): failing tests before implementation")
    _commit(repo, {"src/b.py": "B = 1\n"}, "TASK-002: first half")
    _commit(repo, {"src/b.py": "B = 2\n"}, "TASK-002: second half")
    _commit(repo, {"src/d.py": "D = 1\n"}, "TASK-004, TASK-005: two tasks at once")
    _commit(repo, {"src/clamp.py": CLAMP + "\n\nLATER = 1\n"}, "Later work")
    return repo, pre, build


def test_project_lang(tmp_path):
    (tmp_path / "py").mkdir()
    (tmp_path / "py" / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "go").mkdir()
    (tmp_path / "go" / "go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "none").mkdir()
    assert ablation.project_lang(tmp_path / "py") == "python"
    assert ablation.project_lang(tmp_path / "go") == "go"
    assert ablation.project_lang(tmp_path / "none") is None


def test_plan_letters(project):
    repo, _pre, _build = project
    assert ablation.plan_letters(repo) == {"TASK-001": "S", "TASK-002": "M", "TASK-004": "L"}


def test_find_tasks_keeps_only_single_commit_tasks_with_a_pre_build_commit(project):
    repo, pre, build = project
    tasks = ablation.find_tasks(repo)
    assert [(t.task, t.letter, t.lang) for t in tasks] == [("TASK-001", "S", "python")]
    assert tasks[0].pre_commit == pre and tasks[0].build_commit == build


def _task(project_name, task, letter):
    return ablation.Task(project=Path(project_name), task=task, letter=letter, lang="python",
                         pre_commit="a", build_commit="b")


def test_pick_is_deterministic_capped_and_spread_across_projects():
    pool = [_task(p, "TASK-%03d" % i, letter) for p in ("p1", "p2", "p3") for i, letter in
            enumerate(["S", "S", "M", "M", "L"])]
    first = ablation.pick(pool, 2, seed=7)
    assert first == ablation.pick(list(reversed(pool)), 2, seed=7)
    by_letter = {}
    for task in first:
        by_letter.setdefault(task.letter, []).append(task)
    assert all(len(v) <= 2 for v in by_letter.values())
    for letter in ("S", "M"):
        assert len({t.project for t in by_letter[letter]}) == 2
    assert len(by_letter["L"]) == 2


def test_pick_takes_a_second_from_one_project_only_when_no_other_project_remains():
    pool = [_task("p1", "TASK-001", "S"), _task("p1", "TASK-002", "S"), _task("p2", "TASK-003", "S")]
    picked = ablation.pick(pool, 3, seed=0)
    assert len(picked) == 3
    assert ablation.pick(pool, 2, seed=0)[0].project != ablation.pick(pool, 2, seed=0)[1].project


def test_plant_rewrites_only_the_builder_commit(project, tmp_path):
    repo, pre, build = project
    task = ablation.find_tasks(repo)[0]
    dest = tmp_path / "planted"
    site = ablation.plant(task, dest, seed=1, compile_check=lambda d, s: True)
    assert site.path == "src/clamp.py"
    assert site.function == "clamp"
    planted = _git(dest, "rev-parse", "HEAD")
    assert _git(dest, "rev-parse", "--abbrev-ref", "HEAD") == "planted"
    assert _git(dest, "rev-parse", "planted^") == pre
    assert _git(dest, "rev-parse", "clean") == build
    assert _git(dest, "log", "-1", "--format=%s%n%an", planted) == _git(repo, "log", "-1", "--format=%s%n%an", build)
    diff = _git(dest, "diff", "clean", "planted")
    changed = [ln for ln in diff.splitlines() if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    assert len(changed) == 2
    before, after = changed[0][1:], changed[1][1:]
    assert ablation.apply_site(before, site.col, site.old, site.new) == after
    clamp_lines = CLAMP.splitlines()
    assert clamp_lines[site.line - 1] == before
    assert "LATER" not in (dest / "src" / "clamp.py").read_text(encoding="utf-8")


def test_plant_never_mutates_a_test_file_or_the_docstring(project, tmp_path):
    repo, _pre, _build = project
    task = ablation.find_tasks(repo)[0]
    for seed in range(8):
        site = ablation.plant(task, tmp_path / ("p%d" % seed), seed=seed, compile_check=lambda d, s: True)
        assert site.path == "src/clamp.py"
        assert site.line != 2


def test_plant_restricts_to_the_class_asked(project, tmp_path):
    repo, _pre, _build = project
    task = ablation.find_tasks(repo)[0]
    site = ablation.plant(task, tmp_path / "c", seed=0, cls="comparison", compile_check=lambda d, s: True)
    assert site.cls == "comparison"
    with pytest.raises(ablation.Refused):
        ablation.plant(task, tmp_path / "e", seed=0, cls="equality", compile_check=lambda d, s: True)


def test_plant_draws_another_site_when_the_mutant_does_not_compile(project, tmp_path):
    repo, _pre, _build = project
    task = ablation.find_tasks(repo)[0]
    seen = []

    def compiles(dest, site):
        seen.append((site.line, site.col))
        return len(seen) >= 2

    site = ablation.plant(task, tmp_path / "x", seed=3, compile_check=compiles)
    assert len(seen) == 2 and (site.line, site.col) == seen[1]
    text = (tmp_path / "x" / "src" / "clamp.py").read_text(encoding="utf-8").splitlines()
    assert sum(a != b for a, b in zip(text, CLAMP.splitlines())) == 1


def test_plant_refuses_when_no_mutant_compiles(project, tmp_path):
    repo, _pre, _build = project
    task = ablation.find_tasks(repo)[0]
    with pytest.raises(ablation.Refused):
        ablation.plant(task, tmp_path / "y", seed=0, compile_check=lambda d, s: False)


def test_default_compile_check_refuses_a_broken_python_file(tmp_path):
    (tmp_path / "a.py").write_text("def f(:\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 1\n", encoding="utf-8")
    bad = ablation.Site(path="a.py", line=1, cls="constant", col=0, old="1", new="2", function=None)
    good = ablation.Site(path="b.py", line=1, cls="constant", col=4, old="1", new="2", function=None)
    assert ablation.default_compile_check(tmp_path, bad, "python") is False
    assert ablation.default_compile_check(tmp_path, good, "python") is True


def test_plant_refuses_a_destination_inside_a_git_work_tree(project):
    repo, _pre, _build = project
    task = ablation.find_tasks(repo)[0]
    with pytest.raises(ablation.Refused):
        ablation.plant(task, repo / "inside", seed=0, compile_check=lambda d, s: True)


def test_plant_refuses_a_non_empty_destination(project, tmp_path):
    repo, _pre, _build = project
    task = ablation.find_tasks(repo)[0]
    dest = tmp_path / "full"
    dest.mkdir()
    (dest / "x").write_text("x", encoding="utf-8")
    with pytest.raises(ablation.Refused):
        ablation.plant(task, dest, seed=0, compile_check=lambda d, s: True)


# ----------------------------------------------------------- sessions and CLI


def test_session_extra_args_name_the_tools_each_station_needs():
    style = ablation.session_extra_args("review-style")
    assert style[style.index("--allowedTools") + 1] == "Read,Grep,Glob"
    assert style[style.index("--model") + 1] == "sonnet"
    tester = ablation.session_extra_args("tester-post")
    assert tester[tester.index("--allowedTools") + 1] == "Read,Grep,Glob,Bash,Write,Edit"
    assert tester[tester.index("--agent") + 1] == "tester"
    validator = ablation.session_extra_args("validator")
    assert validator[validator.index("--allowedTools") + 1] == "Read,Grep,Glob,Bash"
    assert validator[validator.index("--agent") + 1] == "validator"
    with pytest.raises(ValueError):
        ablation.session_extra_args("tester-pre")


def test_a_session_runs_through_the_launcher_with_strict_mcp_config(fake_reply, tmp_path):
    fake_reply.reply("FINDING none\n")
    folder = tmp_path / "work"
    folder.mkdir()
    reply = ablation.run_station_session(
        "review-style", folder, "review this", private_root=tmp_path / "private", claude_cmd=fake_reply.command,
    )
    assert reply == "FINDING none\n"
    argv = fake_reply.calls()[-1]["argv"]
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Read,Grep,Glob"


def test_a_usage_limit_raises_usage_limit(fake_reply, tmp_path):
    fake_reply.mode("limit")
    folder = tmp_path / "work"
    folder.mkdir()
    with pytest.raises(ablation.UsageLimit):
        ablation.run_station_session("validator", folder, "x", private_root=tmp_path / "private",
                                     claude_cmd=fake_reply.command)


def test_out_inside_a_git_work_tree_is_refused(project, capsys):
    repo, _pre, _build = project
    code = ablation.main(["run", "--projects-root", str(repo.parent), "--out", str(repo / "out"),
                          "--per-letter", "1", "--seed", "0", "--dry-run"])
    assert code != 0
    assert "work tree" in capsys.readouterr().err


def test_progress_from_another_configuration_is_refused(project, tmp_path, capsys):
    repo, _pre, _build = project
    out = tmp_path / "out"
    out.mkdir()
    (out / "progress.json").write_text(json.dumps({"config": {"seed": 99, "per_letter": 5}, "done": {}}),
                                       encoding="utf-8")
    code = ablation.main(["run", "--projects-root", str(repo.parent), "--out", str(out),
                          "--per-letter", "1", "--seed", "0", "--dry-run"])
    assert code != 0
    assert "configuration" in capsys.readouterr().err


def test_pick_command_lists_the_picked_task(project, capsys):
    repo, _pre, _build = project
    assert ablation.main(["pick", "--projects-root", str(repo.parent), "--per-letter", "2", "--seed", "0"]) == 0
    out = capsys.readouterr().out
    assert "proj-aaaaaa" in out and "TASK-001" in out and "S" in out


def test_report_holds_no_source_text(tmp_path, capsys):
    out = tmp_path / "out"
    out.mkdir()
    done = {
        "proj-aaaaaa|TASK-001": {
            "project": "proj-aaaaaa", "task": "TASK-001", "letter": "S", "lang": "python",
            "site": {"path": "src/clamp.py", "line": 3, "cls": "comparison", "col": 13, "old": "<", "new": "<=",
                     "function": "clamp", "text": "    if value < low:"},
            "caught": {"tester-pre": True, "builder-review": False, "tester-post": True, "validator": False},
            "rows": {},
        },
    }
    (out / "progress.json").write_text(json.dumps({"config": {"seed": 0, "per_letter": 1}, "done": done}),
                                       encoding="utf-8")
    assert ablation.main(["report", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "TASK-001" in printed and "comparison" in printed
    assert "value < low" not in printed
