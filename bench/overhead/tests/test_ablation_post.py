"""Tests for ablation.py written against its implementation: tokenizer edges,
the test-run oracle on a real pytest run, the tester's changed-file scan, the
report's pending rows, and one whole `run` on a fake `claude`."""

import json
import sys
from pathlib import Path

import pytest

import ablation
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)
from test_ablation import CLAMP, _commit, _git


@pytest.mark.parametrize("text,lang,expected", [
    ("for i := 0; i < n; i++ {", "go", {("comparison", "<"), ("constant", "0")}),
    ("x := y >> 2 << 1", "go", {("constant", "2"), ("constant", "1")}),
    ("v = 1e-3", "python", set()),
    ("arr[i] = 1_000", "python", set()),
    ("t = 007", "go", set()),
    ("x = '#' if a < 1 else 2  # c < 3", "python", {("comparison", "<"), ("constant", "1"), ("constant", "2")}),
    ('s = f"{a < b}"', "python", set()),
    ("if a!==b", "python", set()),
    ("ok := a <= b && c >= d", "go", {("comparison", "<="), ("comparison", ">="), ("logic", "&&")}),
])
def test_mutation_site_edges(text, lang, expected):
    assert {(cls, old) for cls, _col, old, _new in ablation.mutation_sites(text, lang)} == expected


def test_every_site_applies_to_its_own_line():
    for text in ("if a < b and c >= 10:", "return x == 2 or y != 3", "for i := 0; i <= n && ok; i++ {"):
        lang = "go" if ":=" in text else "python"
        for cls, col, old, new in ablation.mutation_sites(text, lang):
            out = ablation.apply_site(text, col, old, new)
            assert out != text
            assert out[:col] == text[:col] and out[col + len(new):] == text[col + len(old):]


def test_added_lines_ignores_no_newline_marker():
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1,2 @@\n-x = 1\n\\ No newline at end of file\n"
        "+x = 2\n+y = 3\n\\ No newline at end of file\n"
    )
    assert ablation.added_lines(diff) == {"a.py": [(1, "x = 2"), (2, "y = 3")]}


def test_names_site_accepts_a_windows_path_and_refuses_a_longer_name():
    site = ablation.Site(path="src/game/combat.py", line=40, cls="comparison", col=0, old="<", new="<=",
                         function=None)
    assert ablation.names_site(r"src\game\combat.py:41 admits a tie", site)
    assert not ablation.names_site("mycombat.py:40", site)
    assert not ablation.names_site("combat.pyc:40", site)


def test_failing_tests_reads_a_collection_error_without_a_node():
    out = "ERROR tests/test_a.py - ModuleNotFoundError: no module named x\n"
    assert ablation.failing_tests(out, "python") == {"tests/test_a.py"}


def _python_project(root):
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'p'\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "clamp.py").write_text(CLAMP, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_clamp.py").write_text(
        "from src.clamp import clamp\n\n\ndef test_edge():\n    assert clamp(0, 0, 10) == 0\n\n\n"
        "def test_inside():\n    assert clamp(5, 0, 10) == 5\n", encoding="utf-8")
    return root


def test_run_tests_on_a_real_pytest_run_tells_a_planted_bound_apart(tmp_path):
    clean = _python_project(tmp_path / "clean")
    planted = _python_project(tmp_path / "planted")
    text = (planted / "src" / "clamp.py").read_text(encoding="utf-8")
    (planted / "src" / "clamp.py").write_text(text.replace("value < low", "value <= low").replace(
        "return low", "return low - 1"), encoding="utf-8")
    files = ["tests/test_clamp.py"]
    clean_failing = ablation.run_tests(clean, files, "python")
    planted_failing = ablation.run_tests(planted, files, "python")
    assert clean_failing == set()
    assert planted_failing == {"tests/test_clamp.py::test_edge"}
    assert ablation.caught_by_tests(clean_failing, planted_failing)


def test_run_tests_with_no_existing_file_fails_nothing(tmp_path):
    assert ablation.run_tests(tmp_path, ["tests/missing.py"], "python") == set()


def test_changed_test_files_lists_new_and_edited_tests_only(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, {"src/a.py": "A = 1\n", "tests/test_a.py": "def test_a():\n    pass\n"}, "seed")
    (repo / "tests" / "test_a.py").write_text("def test_a():\n    assert False\n", encoding="utf-8")
    (repo / "tests" / "test_new.py").write_text("def test_n():\n    pass\n", encoding="utf-8")
    (repo / "src" / "a.py").write_text("A = 2\n", encoding="utf-8")
    (repo / "tests" / "notes.txt").write_text("x\n", encoding="utf-8")
    assert ablation._changed_test_files(repo, "python") == ["tests/test_a.py", "tests/test_new.py"]


def test_report_lists_pending_stations_and_leaves_incomplete_defects_out_of_the_table():
    data = {"done": {
        "p|TASK-001": {"letter": "S", "lang": "python", "site": {"cls": "constant"},
                       "caught": {"tester-pre": True}},
        "p|TASK-002": {"letter": "M", "lang": "go", "site": {"cls": "logic"},
                       "caught": {s: False for s in ablation.STATIONS}},
    }}
    text = ablation.render_report(data)
    assert "defects with every station read: 1 of 2" in text
    assert "| p|TASK-001 | S | python | constant | caught | pending | pending | pending |" in text
    table_rows = [ln for ln in text.splitlines() if ln.startswith("| S |") or ln.startswith("| M |")]
    assert len(table_rows) == 1 and table_rows[0].startswith("| M | 1 | 1 |")


REPLY = """Review and validation.

FINDING src/clamp.py:3: the lower bound admits the edge value

VERDICT: FAIL

### Phase Results

| Task | Status | Checks |
|---|---|---|
| TASK-001 | FAIL | 1/2 |

The bound at src/clamp.py:3 is wrong.
"""

PLAN = "---\ntitle: p\ndepends_on: []\n---\n\n- [x] TASK-001: Clamp a value - complexity: S, files: [src/clamp.py]\n"


def test_a_whole_run_on_a_fake_claude_fills_every_station_and_resumes(tmp_path, fake_reply, capsys):
    root = tmp_path / "projects"
    repo = root / "proj-bbbbbb"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "--initial-branch=main")
    _commit(repo, {"pyproject.toml": "[project]\nname='p'\n", ".compass/plans/PLAN-001-x.md": PLAN,
                   "src/__init__.py": ""}, "Seed")
    _commit(repo, {"tests/test_clamp.py": "from src.clamp import clamp\n\n\ndef test_inside():\n"
                                          "    assert clamp(5, 0, 10) == 5\n"},
            "test(TASK-001): failing tests before implementation")
    _commit(repo, {"src/clamp.py": CLAMP}, "TASK-001: clamp a value")
    fake_reply.reply(REPLY)
    out = tmp_path / "out"
    argv = ["run", "--projects-root", str(root), "--out", str(out), "--per-letter", "1", "--seed", "0",
            "--private-root", str(tmp_path / "private")]
    assert ablation.main(argv, claude_cmd=fake_reply.command) == 0
    data = json.loads((out / "progress.json").read_text(encoding="utf-8"))
    entry = data["done"]["proj-bbbbbb|TASK-001"]
    assert set(entry["caught"]) == set(ablation.STATIONS)
    assert entry["caught"]["builder-review"] is True
    assert entry["caught"]["validator"] is True
    assert entry["caught"]["tester-post"] is False
    assert entry["rows"]["validator"]["result"] == "FAIL"
    calls = fake_reply.calls()
    assert len(calls) == 4
    assert all("--strict-mcp-config" in call["argv"] for call in calls)
    agents = sorted(call["argv"][call["argv"].index("--agent") + 1] for call in calls if "--agent" in call["argv"])
    assert agents == ["tester", "validator"]
    assert all("TASK-001" in call["stdin"] for call in calls)
    assert any("```diff" in call["stdin"] for call in calls)
    printed = capsys.readouterr().out
    assert "value < low" not in printed and "value > high" not in printed
    assert ablation.main(argv, claude_cmd=fake_reply.command) == 0
    assert len(fake_reply.calls()) == 4


def test_a_usage_limit_mid_run_exits_3_and_keeps_progress(tmp_path, fake_reply):
    root = tmp_path / "projects"
    repo = root / "proj-cccccc"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "--initial-branch=main")
    _commit(repo, {"pyproject.toml": "[project]\nname='p'\n", ".compass/plans/PLAN-001-x.md": PLAN,
                   "src/__init__.py": ""}, "Seed")
    _commit(repo, {"tests/test_clamp.py": "def test_x():\n    assert True\n"},
            "test(TASK-001): failing tests before implementation")
    _commit(repo, {"src/clamp.py": CLAMP}, "TASK-001: clamp a value")
    fake_reply.mode("limit")
    out = tmp_path / "out"
    argv = ["run", "--projects-root", str(root), "--out", str(out), "--per-letter", "1", "--seed", "0",
            "--private-root", str(tmp_path / "private")]
    assert ablation.main(argv, claude_cmd=fake_reply.command) == ablation.EXIT_USAGE_LIMIT
    data = json.loads((out / "progress.json").read_text(encoding="utf-8"))
    entry = data["done"]["proj-cccccc|TASK-001"]
    assert "tester-pre" in entry["caught"]
    assert not entry.get("sessions")


def test_changed_test_files_skips_the_installed_harness(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _commit(repo, {"src/a.py": "A = 1\n"}, "seed")
    for rel in (".claude/cli/commands/test_checkpoint.py", ".compass/tmp/test_x.py"):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    assert ablation._changed_test_files(repo, "python") == []


def test_uv_runs_a_project_that_names_pytest_even_without_a_lock_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ablation.shutil, "which", lambda name: "uv")
    (tmp_path / "pyproject.toml").write_text("[project.optional-dependencies]\ndev = ['pytest']\n", encoding="utf-8")
    assert ablation._uv_python(tmp_path)[:2] == ["uv", "run"]
    assert "--frozen" not in ablation._uv_python(tmp_path)
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    assert "--frozen" in ablation._uv_python(tmp_path)


def test_a_project_naming_no_test_runner_uses_the_running_interpreter(tmp_path, monkeypatch):
    monkeypatch.setattr(ablation.shutil, "which", lambda name: "uv")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'p'\n", encoding="utf-8")
    assert ablation._uv_python(tmp_path) == [sys.executable]
    monkeypatch.setattr(ablation.shutil, "which", lambda name: None)
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    assert ablation._uv_python(tmp_path) == [sys.executable]


TESTER_REPORT = """## Test Report

### Mode
post-build

### Bugs Found
- **Inverted condition in `messageOf`:** `reader/fields.go:112-120`. The branch should be `==`.

### Coverage
- reader/other.go:114 is covered
"""


def _go_site():
    return ablation.Site(path="reader/fields.go", line=114, cls="equality", col=11, old="==", new="!=",
                         function=None)


def test_a_tester_bug_naming_the_site_is_a_catch():
    assert ablation.tester_caught(TESTER_REPORT, _go_site(), tests_caught=False)


def test_a_site_named_outside_bugs_found_is_no_catch():
    report = TESTER_REPORT.replace("reader/fields.go:112-120", "the reader")
    report = report.replace("reader/other.go:114", "reader/fields.go:114")
    assert not ablation.tester_caught(report, _go_site(), tests_caught=False)


def test_a_tester_report_with_no_bug_is_no_catch_unless_its_tests_tell_apart():
    report = TESTER_REPORT.replace("### Bugs Found\n", "### Notes\n")
    assert not ablation.tester_caught(report, _go_site(), tests_caught=False)
    assert ablation.tester_caught(report, _go_site(), tests_caught=True)


def test_rejudge_reads_the_saved_replies_and_refolds(tmp_path):
    out = tmp_path / "out"
    replies = out / "work" / "proj-a-TASK-004" / "replies"
    replies.mkdir(parents=True)
    (replies / "tester-post.md").write_text(TESTER_REPORT, encoding="utf-8")
    (replies / "review-style.md").write_text("FINDING none\n", encoding="utf-8")
    (replies / "review-correctness.md").write_text("FINDING reader/fields.go:115: inverted\n", encoding="utf-8")
    (replies / "validator.md").write_text("VERDICT: PASS\n", encoding="utf-8")
    site = {"path": "reader/fields.go", "line": 114, "cls": "equality", "col": 11, "old": "==", "new": "!=",
            "function": None, "text": "x"}
    sessions = {s: {"caught": False} for s in ablation.SESSIONS}
    entry = {"project": "proj-a", "task": "TASK-004", "letter": "S", "lang": "go", "site": site,
             "caught": {"tester-pre": True}, "rows": {}, "sessions": sessions}
    (out / "progress.json").write_text(json.dumps({"config": {}, "done": {"proj-a|TASK-004": entry}}),
                                       encoding="utf-8")
    data = ablation.rejudge(out)
    caught = data["done"]["proj-a|TASK-004"]["caught"]
    assert caught == {"tester-pre": True, "builder-review": True, "tester-post": True, "validator": False}
    assert data["done"]["proj-a|TASK-004"]["sessions"]["tester-post"]["tests_caught"] is False
