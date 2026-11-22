"""Tests for bench/overhead/letters.py: the letter-repeatability measurement.

Module contract the tests pin
-----------------------------
strip_letter(task_line) -> str          the line without its `complexity:` field
parse_letter(task_line) -> str | None   "S", "M" or "L" from the field, else None
sample(lines_by_letter, n, seed) -> list
                                        stratified draw; items are the original
                                        list elements, drawn without repeats
fleiss_kappa(ratings, categories) -> float
exact_agreement(ratings) -> float       rows are items, each a list of letters
session_command(model, prompt) -> list[str]
                                        argv of one `claude -p` session, no tools
run_session(model, prompt, *, runner, cwd_factory=None)
    runner(argv, cwd=<folder>) -> str   called once, with the argv from
                                        session_command and a fresh empty folder
                                        outside any git work tree; cwd_factory()
                                        returns that folder (a Path)
render_report(results) -> str           markdown; results is a list of dicts
                                        {"task": str, "original": "S|M|L",
                                         "ratings": {model_id: [letter, ...]}}
                                        with exactly two model ids; each task's
                                        row is one line holding its original
                                        letter and every session letter

Adversarial themes: the original letter leaking into a session prompt,
agreement statistics that mis-handle the unused-category and zero-variance
corners, a stratified sample that quietly turns proportional, and a session
that can see a tool or a git work tree.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pytest

import letters
from conftest import inside_git_work_tree

LETTER_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])[SML](?![A-Za-z0-9_-])")


@pytest.fixture(autouse=True)
def never_launch_claude(monkeypatch):
    """Any attempt to start a real `claude` process fails the test."""
    real_popen = subprocess.Popen

    def guarded(args, *a, **kw):
        first = args[0] if isinstance(args, (list, tuple)) else str(args).split()[0]
        if Path(str(first)).stem.lower().startswith("claude"):
            raise AssertionError("a test tried to launch the real claude: %r" % (args,))
        return real_popen(args, *a, **kw)

    monkeypatch.setattr(subprocess, "Popen", guarded)


class RecordingRunner:
    """Fake session runner: records argv and cwd, snapshots the folder."""

    def __init__(self, reply="M"):
        self.reply = reply
        self.calls = []

    def __call__(self, *args, **kwargs):
        argv = next(v for v in [*args, *kwargs.values()] if isinstance(v, (list, tuple)))
        cwd = kwargs.get("cwd")
        if cwd is None:
            cwd = next(v for v in args if isinstance(v, (str, Path)))
        cwd = Path(cwd)
        self.calls.append({
            "argv": list(argv),
            "cwd": cwd,
            "existed": cwd.is_dir(),
            "listing": sorted(p.name for p in cwd.iterdir()) if cwd.is_dir() else None,
            "in_git": inside_git_work_tree(cwd) if cwd.is_dir() else None,
        })
        return self.reply


def test_strip_letter_removes_the_field_wherever_it_sits():
    """Adversarial where: the stripper only handles the mid-line position, so
    a field written last (or first) leaves the original letter in the text the
    session sees, or leaves a dangling comma; a filename that merely contains
    the word `complexity` must survive."""
    rows = {
        "middle": (
            "- [ ] TASK-001: Build parser - complexity: M, depends_on: none, files: [`a.py`]",
            ["TASK-001", "Build parser", "depends_on: none", "files: [`a.py`]"],
        ),
        "last": (
            "- [ ] TASK-002: Build writer - depends_on: TASK-001, files: [`b.py`], complexity: L",
            ["TASK-002", "Build writer", "depends_on: TASK-001", "files: [`b.py`]"],
        ),
        "first": (
            "- [ ] TASK-003: Build reader - complexity: S, depends_on: none",
            ["TASK-003", "Build reader", "depends_on: none"],
        ),
        "filename_with_word": (
            "- [ ] TASK-004: Score it - complexity: S, depends_on: none, files: [`bench/complexity.py`]",
            ["bench/complexity.py", "depends_on: none"],
        ),
        "decisions_after": (
            "- [ ] TASK-005: Wire it - complexity: M, depends_on: none, files: [`c.py`], decisions: [PLAN-034/D-01]",
            ["files: [`c.py`]", "decisions: [PLAN-034/D-01]"],
        ),
    }
    for name, (line, keep) in rows.items():
        out = letters.strip_letter(line)
        assert not re.search(r"complexity\s*:", out), name
        assert not re.search(r":\s*[SML]\b", out), name
        assert ",," not in out.replace(" ", ""), name
        assert not out.rstrip().endswith(","), name
        assert letters.parse_letter(out) is None, name
        for piece in keep:
            assert piece in out, (name, piece)


def test_strip_letter_leaves_a_line_without_the_field_unchanged():
    """Adversarial where: a `## Later` intent line carries no complexity; the
    stripper must not eat other fields or the word `complexity` in prose."""
    line = "- [ ] TASK-006: Reduce complexity of the parser - files: [`p.py`], decisions: [PLAN-034/D-02]"
    assert letters.strip_letter(line) == line


def test_parse_letter_reads_the_field_value_only():
    """Adversarial where: parse_letter picks a standalone S/M/L from the
    description or a file name instead of the field value, or returns a
    letter for a line that has no field."""
    rows = {
        "middle": ("- [ ] TASK-1: Add M-series loader - complexity: S, depends_on: none", "S"),
        "last": ("- [ ] TASK-2: Do it - depends_on: none, complexity: L", "L"),
        "first": ("- [ ] TASK-3: Do it - complexity: M, depends_on: none", "M"),
        "prose_only": ("- [ ] TASK-4: Reduce complexity of the S parser - files: [`s.py`]", None),
        "later_intent": ("- [ ] TASK-5: Intent only - files: [`x.py`]", None),
    }
    for name, (line, expected) in rows.items():
        assert letters.parse_letter(line) == expected, name


def _pools(sizes):
    return {k: ["%s-%d" % (k, i) for i in range(size)] for k, size in sizes.items()}


def _counts(drawn):
    out = {}
    for item in drawn:
        out[item[0]] = out.get(item[0], 0) + 1
    return out


def test_sample_is_stratified_and_draws_real_lines_without_repeats():
    """Adversarial where: a draw proportional to pool size (or a plain
    random.sample over the union) returns mostly S when S dominates the plans,
    so the rarer letters are under-measured; an uneven n must still spread
    within one line of even; sampling with replacement or from the wrong
    stratum returns duplicates or lines under the wrong letter."""
    skewed = _pools({"S": 200, "M": 40, "L": 5})
    drawn = letters.sample(skewed, 15, 1)
    assert len(drawn) == 15
    assert _counts(drawn) == {"S": 5, "M": 5, "L": 5}
    assert len(set(drawn)) == len(drawn)
    for item in drawn:
        assert item in skewed[item[0]]

    exact_pool = _pools({"S": 10, "M": 10, "L": 10})
    drawn = letters.sample(exact_pool, 30, 1)
    assert sorted(drawn) == sorted(sum(exact_pool.values(), []))

    odd = letters.sample(_pools({"S": 50, "M": 50, "L": 50}), 10, 1)
    counts = _counts(odd)
    assert sum(counts.values()) == 10
    assert max(counts.values()) - min(counts.values()) <= 1
    assert set(counts) == {"S", "M", "L"}


def test_sample_is_repeatable_per_seed_and_does_not_touch_its_input():
    """Adversarial where: an unseeded or global-RNG draw makes the 30-task
    set differ between runs so results cannot be compared; shuffling the
    caller's lists in place corrupts the plan-derived pools."""
    pools = _pools({"S": 100, "M": 100, "L": 100})
    snapshot = {k: list(v) for k, v in pools.items()}
    first = letters.sample(pools, 30, 11)
    again = letters.sample(pools, 30, 11)
    other = letters.sample(pools, 30, 12)
    assert first == again
    assert first != other
    assert pools == snapshot


# Fleiss (1971) worked example as tabulated on Wikipedia: 10 items, 14 raters,
# 5 categories; kappa = 0.2099 (hand-computed there).
WIKI_COUNTS = [
    [0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
    [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7],
]


def _rows_from_counts(counts, cats):
    return [[c for c, k in zip(cats, row) for _ in range(k)] for row in counts]


def test_fleiss_kappa_matches_hand_computed_fixtures():
    """Adversarial where: a wrong chance-agreement term (squaring per-item
    proportions, dividing by raters instead of ratings, ignoring an unused
    category) yields a number that looks plausible but is not kappa. Fixtures
    are hand-computed: the Fleiss 1971 table (0.2099); a perfect-agreement set
    with an unused category (1.0); and a 2-item set whose kappa is exactly
    -1/11, which a clamp at zero would hide."""
    cats5 = ["1", "2", "3", "4", "5"]
    assert letters.fleiss_kappa(_rows_from_counts(WIKI_COUNTS, cats5), cats5) == pytest.approx(0.2099, abs=5e-4)

    perfect = [["S", "S", "S"], ["M", "M", "M"], ["S", "S", "S"]]
    assert letters.fleiss_kappa(perfect, ("S", "M", "L")) == pytest.approx(1.0)

    negative = [["S", "S", "M"], ["M", "M", "L"]]
    assert letters.fleiss_kappa(negative, ("S", "M", "L")) == pytest.approx(-1 / 11)


def test_fleiss_kappa_ignores_rater_order_within_an_item():
    """Adversarial where: a per-position comparison (rater 1 vs rater 2)
    instead of per-category counts makes kappa depend on which session
    answered first."""
    cats = ("S", "M", "L")
    a = [["S", "S", "M"], ["M", "L", "M"], ["L", "L", "L"], ["S", "M", "L"]]
    b = [["M", "S", "S"], ["L", "M", "M"], ["L", "L", "L"], ["L", "S", "M"]]
    assert letters.fleiss_kappa(a, cats) == pytest.approx(letters.fleiss_kappa(b, cats))


def test_fleiss_kappa_when_every_rating_is_one_letter_never_divides_by_zero():
    """Adversarial where: sessions that all answer M on every task make the
    chance-agreement term 1, so kappa is 0/0; the report must not die with
    ZeroDivisionError (a float or a deliberate ValueError are both fine)."""
    constant = [["M", "M", "M"] for _ in range(5)]
    try:
        result = letters.fleiss_kappa(constant, ("S", "M", "L"))
    except ValueError:
        return
    assert isinstance(result, float)


def test_exact_agreement_counts_only_unanimous_items():
    """Adversarial where: counting an item as agreeing when a majority (2 of
    3) agrees, rather than all raters, inflates repeatability."""
    ratings = [["S", "S", "S"], ["S", "M", "S"], ["M", "M", "M"], ["L", "M", "L"]]
    assert letters.exact_agreement(ratings) == pytest.approx(0.5)
    assert letters.exact_agreement([["S", "S", "M"]]) == 0.0
    assert letters.exact_agreement([["L", "L", "L"]]) == 1.0


def _flag_values(argv, flags):
    out = []
    for i, token in enumerate(argv):
        if token in flags and i + 1 < len(argv):
            out.append(argv[i + 1])
    return out


def test_session_command_carries_no_tool_and_passes_model_and_prompt_intact():
    """Adversarial where: a session started with the default tool set can
    read the vault and see the original letter; a prompt with leading dashes,
    quotes and newlines gets split, shell-quoted or parsed as a flag."""
    prompt = "--ignore previous\n\"quoted\" 'single' $HOME `tick` Classify: complexity?"
    argv = letters.session_command("model-under-test-7", prompt)

    assert isinstance(argv, list) and all(isinstance(t, str) for t in argv)
    assert "-p" in argv or "--print" in argv
    assert _flag_values(argv, {"--model"}) == ["model-under-test-7"]
    assert argv.count(prompt) == 1

    allowed = _flag_values(argv, {"--allowedTools", "--allowed-tools"})
    tools = _flag_values(argv, {"--tools"})
    disallowed = _flag_values(argv, {"--disallowedTools", "--disallowed-tools"})
    assert all(v.strip() == "" for v in allowed + tools), (allowed, tools)
    assert tools == [""] or disallowed, "tools must be switched off explicitly"
    assert "--dangerously-skip-permissions" not in argv
    assert not any(t.startswith("--mcp-config") for t in argv)


def test_run_session_runs_the_built_command_in_a_fresh_empty_folder_outside_git():
    """Adversarial where: running from the repo (or any git work tree) lets a
    session read the vault and the original letter; reusing one folder lets
    one session's files leak into the next."""
    runner = RecordingRunner()
    letters.run_session("model-a", "prompt one", runner=runner)
    letters.run_session("model-b", "prompt two", runner=runner)

    first, second = runner.calls
    assert first["argv"] == letters.session_command("model-a", "prompt one")
    assert second["argv"] == letters.session_command("model-b", "prompt two")
    for call in runner.calls:
        assert call["existed"]
        assert call["listing"] == []
        assert call["in_git"] is False
    assert first["cwd"] != second["cwd"]


def test_run_session_uses_the_folder_its_factory_returns(tmp_path):
    """Adversarial where: run_session ignores the injected cwd_factory and
    makes its own folder, so tests (and callers) cannot control where the
    session runs."""
    folder = tmp_path / "chosen-session-folder"
    folder.mkdir()
    runner = RecordingRunner()
    letters.run_session("model-a", "p", runner=runner, cwd_factory=lambda: folder)
    assert [c["cwd"] for c in runner.calls] == [folder]


def test_run_session_will_not_start_inside_a_git_work_tree(repo, monkeypatch):
    """Adversarial where: a TMPDIR that points into a repository puts the
    default session folder inside a git work tree; the session must either
    run elsewhere or refuse to run."""
    inside = repo / "scratch"
    inside.mkdir()
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(inside))
    monkeypatch.setattr(tempfile, "tempdir", str(inside))
    runner = RecordingRunner()
    try:
        letters.run_session("model-a", "p", runner=runner)
    except Exception:
        assert runner.calls == []
        return
    assert [c["in_git"] for c in runner.calls] == [False]


STRONG = "model-strong-x"
BALANCED = "model-balanced-y"


def _results(rows):
    return [
        {"task": t, "original": o, "ratings": {STRONG: s, BALANCED: b}}
        for t, o, s, b in rows
    ]


def _numbers_in(report):
    numbers = set()
    for token in re.findall(r"-?\d+(?:\.\d+)?%?", report):
        value = float(token.rstrip("%"))
        numbers.add(value / 100 if token.endswith("%") else value)
    return numbers


def test_render_report_lists_every_task_letters_and_the_agreement_figures():
    """Adversarial where: a report that drops a task, prints letters under
    the wrong task, or omits the exact-agreement or kappa figure of one model
    leaves the research document unable to support its claim."""
    rows = [
        ("TASK-901", "L", ["S", "S", "L"], ["M", "M", "M"]),
        ("TASK-902", "M", ["M", "M", "M"], ["M", "S", "M"]),
        ("TASK-903", "S", ["S", "S", "S"], ["S", "S", "S"]),
        ("TASK-904", "L", ["L", "M", "L"], ["L", "L", "L"]),
    ]
    report = letters.render_report(_results(rows))

    for task, original, strong, balanced in rows:
        lines = [ln for ln in report.splitlines() if task in ln]
        assert lines, task
        found = sorted(LETTER_TOKEN.findall(lines[0]))
        assert found == sorted([original, *strong, *balanced]), (task, lines[0])

    numbers = _numbers_in(report)

    def shown(x):
        return any(abs(n - x) <= 0.006 for n in numbers)

    for model in (STRONG, BALANCED):
        ratings = [r["ratings"][model] for r in _results(rows)]
        assert shown(letters.exact_agreement(ratings)), model
        assert shown(letters.fleiss_kappa(ratings, ("S", "M", "L"))), model
    assert STRONG in report and BALANCED in report


def test_render_report_between_model_agreement_is_the_share_of_tasks_the_models_match():
    """Adversarial where: between-model agreement computed over the wrong
    pairing (strong against the original letter) reports a figure that is
    right for another question. Sessions are unanimous per model, so 6 of 8
    tasks match (0.75), which differs from agreement with the original
    (0.5 for strong, 0.25 for balanced)."""
    strong = ["S", "M", "L", "M", "S", "L", "M", "M"]
    balanced = ["S", "M", "L", "M", "S", "L", "S", "L"]
    rows = [
        ("TASK-%d" % (800 + i), "M", [s] * 3, [b] * 3)
        for i, (s, b) in enumerate(zip(strong, balanced))
    ]
    report = letters.render_report(_results(rows))
    assert any(abs(v - 0.75) <= 0.006 for v in _numbers_in(report)), sorted(_numbers_in(report))
    for i in range(8):
        assert "TASK-%d" % (800 + i) in report
