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


# ---------------------------------------------------------------------------
# Implementation-revealed cases: reply parsing, Later-section exclusion, the
# prompt's letter hygiene, resume and usage-limit halt, aggregate-only report,
# and the default runner's exit-code handling.
# ---------------------------------------------------------------------------

def _read_json(path):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _plan_table():
    return "| Size | Scope |\n|---|---|\n| S | Single file |\n| M | 2-5 files |\n| L | 5+ files |"


def test_parse_reply_reads_the_session_letter_and_words_lines_only():
    """Adversarial where: a session echoing the template (`letter: X`), writing
    markdown bold, lower case, CRLF line ends, or a prose sentence containing
    `letter: M` mid-line gets a wrong letter or a letter taken from a word like
    `Medium`; the parser must return the last real line-start `letter: S|M|L`
    and None otherwise."""
    rows = {
        "plain": ("letter: M\nwords: 2-5 files", ("M", "2-5 files")),
        "lower_case": ("letter: m\nwords: a", ("M", "a")),
        "bold_letter": ("**letter:** L\nwords: 5+ files", ("L", "5+ files")),
        "template_echo_then_answer": ("`letter: X`\nletter: S\nwords: single file", ("S", "single file")),
        "last_wins": ("letter: M\nletter: L\nwords: w", ("L", "w")),
        "crlf": ("letter: S\r\nwords: abc\r\n", ("S", "abc")),
        "word_not_letter": ("letter: Medium\nwords: x", (None, "x")),
        "mid_line_prose": ("My letter: M\nwords: x", (None, "x")),
        "template_only": ("letter: X\nwords: y", (None, "y")),
        "empty": ("", (None, "")),
        "none": (None, (None, "")),
    }
    for name, (reply, expected) in rows.items():
        assert letters.parse_reply(reply) == expected, name


def _write_plan(folder, stem, text):
    path = Path(folder) / ("%s.md" % stem)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def _task(n, letter="M"):
    return "- [ ] TASK-%d: thing %d - complexity: %s, depends_on: none\n" % (n, n, letter)


def test_plan_tasks_leaves_out_lines_under_a_later_heading(tmp_path):
    """Adversarial where: the `## Later` intent section is sampled as if it
    were detailed (it is still a task line with a letter), or the exclusion
    never ends and swallows the tasks of the next sibling section, or a
    `## Later` written inside a code fence switches it on; every row names the
    task numbers that must remain."""
    rows = {
        "later_to_end": ("## Goal\ng\n\n## Tasks\n" + _task(1) + "\n## Later (intent only)\n" + _task(2), [1]),
        "resumes_at_sibling": ("## Later\n" + _task(1) + "\n## Next\n" + _task(2), [2]),
        "subheading_stays_later": ("## Later\n### Wave\n" + _task(1) + "\n## Next\n" + _task(2), [2]),
        "h3_later_ends_at_h3": ("## Wave\n### Later\n" + _task(1) + "### Other\n" + _task(2), [2]),
        "fenced_later_is_not_a_heading": ("## A\n```\n## Later\n```\n" + _task(3), [3]),
        "crlf_file": (
            ("## Later\n" + _task(1) + "## B\n" + _task(2)).replace("\n", "\r\n"),
            [2],
        ),
        "checked_task_counts": ("## A\n- [x] TASK-5: done - complexity: S, depends_on: none\n", [5]),
    }
    for name, (text, expected) in rows.items():
        path = _write_plan(tmp_path, "PLAN-900-%s" % name, text)
        found = letters.plan_tasks(path)
        got = sorted(int(t.id.rsplit("TASK-", 1)[1]) for t in found)
        assert got == expected, name
        assert all(t.id.startswith("PLAN-900/") for t in found), name


def test_plan_tasks_keeps_a_heading_that_only_starts_with_later(tmp_path):
    """Adversarial where: the Later check is a prefix match, so `## Lateral
    thinking` hides its detailed tasks from the sample."""
    path = _write_plan(tmp_path, "PLAN-901-x", "## Lateral thinking\n" + _task(7))
    assert [t.id for t in letters.plan_tasks(path)] == ["PLAN-901/TASK-7"]


def test_build_prompt_never_carries_the_original_letter_or_refuses():
    """Adversarial where: the field is stripped from the common positions but
    a second `complexity: X` mentioned inside the description, or the field at
    the very end, stays in what the session reads; a prose mention the
    stripper cannot remove must stop the batch (Refused) rather than reach a
    session."""
    for name, line in {
        "middle": "- [ ] TASK-9: Build it - complexity: L, depends_on: none, files: [`a.py`]",
        "last": "- [ ] TASK-9: Build it - depends_on: none, complexity: L",
        "last_after_dash": "- [ ] TASK-9: Build it - files: [`a.py`] - complexity: L",
        "twice": "- [ ] TASK-9: Sizing (complexity: L) here - complexity: L, depends_on: none",
    }.items():
        task = letters.Task("PLAN-902/TASK-9", "L", line, "the plan goal")
        prompt = letters.build_prompt(task, _plan_table())
        assert not re.search(r"complexity:\s*[SML]", prompt), name
        assert "the plan goal" in prompt and _plan_table() in prompt, name
        assert "TASK-9:" in prompt, name

    stuck = letters.Task(
        "PLAN-902/TASK-9", "M", "- [ ] TASK-9: see `complexity: M` rule - complexity: M, depends_on: none", "g"
    )
    with pytest.raises(letters.Refused):
        letters.build_prompt(stuck, _plan_table())


class ScriptedRunner:
    """Fake runner. `replies` is a list cycled through, or a function of
    (call index, argv); raises UsageLimit once `limit_after` calls were served."""

    def __init__(self, replies, limit_after=None):
        self.replies = replies
        self.limit_after = limit_after
        self.calls = 0

    def __call__(self, argv, cwd):
        if self.limit_after is not None and self.calls >= self.limit_after:
            raise letters.UsageLimit("usage limit reached")
        if callable(self.replies):
            reply = self.replies(self.calls, argv)
        else:
            reply = self.replies[self.calls % len(self.replies)]
        self.calls += 1
        return reply


def _batch_tasks():
    return [
        letters.Task(
            "PLAN-903/TASK-%d" % i, "SML"[i % 3],
            "- [ ] TASK-%d: t%d - complexity: %s, a: b" % (i, i, "SML"[i % 3]), "goal",
        )
        for i in range(1, 5)
    ]


def test_run_batch_resumes_after_a_usage_limit_without_repeating_finished_sessions(tmp_path):
    """Adversarial where: a halt at the usage limit loses the finished
    sessions (so a resume repeats and re-bills them), or the resumed run
    returns different letters from the ones recorded before the halt. The halt
    falls at 7 of 24 sessions, an index that is not a task or model boundary."""
    tasks = _batch_tasks()
    models = ["strong-a", "balanced-b"]
    config = {"ids": [t.id for t in tasks], "models": models, "sessions": 3, "seed": 5}
    progress = tmp_path / "state" / "p.json"
    cycle = ["letter: S\nwords: a", "letter: M\nwords: b", "letter: L\nwords: c"]

    halted = ScriptedRunner(lambda n, argv: cycle[n % 3], limit_after=7)
    with pytest.raises(letters.UsageLimit):
        letters.run_batch(tasks, models, 3, _plan_table(), runner=halted, progress_path=progress, config=config)
    assert len(_read_json(progress)["done"]) == 7

    resumed = ScriptedRunner(["letter: M\nwords: z"])
    results = letters.run_batch(tasks, models, 3, _plan_table(), runner=resumed, progress_path=progress, config=config)
    assert resumed.calls == 24 - 7
    assert [r["task"] for r in results] == [t.id for t in tasks]
    assert all(len(r["ratings"][m]) == 3 for r in results for m in models)
    assert results[0]["ratings"]["strong-a"] == ["S", "M", "L"]


def test_run_batch_refuses_a_progress_file_of_another_configuration(tmp_path):
    """Adversarial where: resuming a progress file written for other tasks,
    models, session counts or seed mixes two measurements into one report; a
    refusal must come before any session runs."""
    tasks = _batch_tasks()
    progress = tmp_path / "p.json"
    base = {"ids": [t.id for t in tasks], "models": ["a", "b"], "sessions": 3, "seed": 5}
    letters.run_batch(
        tasks[:1], ["a", "b"], 3, _plan_table(), runner=ScriptedRunner(["letter: M"]), progress_path=progress, config=base
    )
    for name, change in {"seed": {"seed": 6}, "sessions": {"sessions": 4}, "models": {"models": ["a", "c"]}}.items():
        runner = ScriptedRunner(["letter: M"])
        with pytest.raises(letters.Refused):
            letters.run_batch(
                tasks, ["a", "b"], 3, _plan_table(), runner=runner, progress_path=progress, config={**base, **change}
            )
        assert runner.calls == 0, name


def test_run_batch_retries_a_reply_without_a_letter_then_gives_up(tmp_path):
    """Adversarial where: a reply with no `letter:` line is recorded as a
    letter (or as None), or retried forever; it gets a bounded number of
    fresh sessions and then stops the batch with nothing saved for it."""
    task = _batch_tasks()[:1]
    config = {"ids": [task[0].id], "models": ["a", "b"], "sessions": 2, "seed": 0}

    flaky = ScriptedRunner(lambda n, argv: "I think medium" if n == 0 else "letter: L\nwords: w")
    results = letters.run_batch(
        task, ["a", "b"], 2, _plan_table(), runner=flaky, progress_path=tmp_path / "ok.json", config=config
    )
    assert flaky.calls == 5
    assert results[0]["ratings"] == {"a": ["L", "L"], "b": ["L", "L"]}

    hopeless = ScriptedRunner(["no letter here"])
    with pytest.raises(letters.SessionFailed):
        letters.run_batch(
            task, ["a", "b"], 2, _plan_table(), runner=hopeless, progress_path=tmp_path / "bad.json", config=config
        )
    assert hopeless.calls == letters.ATTEMPTS
    bad = tmp_path / "bad.json"
    assert not bad.exists() or _read_json(bad)["done"] == {}


def _vault_plans(folder):
    plans = Path(folder) / "plans"
    plans.mkdir()
    body = "## Goal\nGOALSENTINEL for this plan.\n\n## Tasks\n"
    for i, letter in enumerate("SSSMMMLLL", start=1):
        body += "- [ ] TASK-%d: TITLESENTINEL%d work - complexity: %s, depends_on: none\n" % (i, i, letter)
    (plans / "PLAN-904-x.md").write_text(body, encoding="utf-8")
    return plans


def _run_args(tmp_path, plans, name="out.md", progress="prog/p.json", extra=()):
    return [
        "--n", "6", "--seed", "3", "--plans", str(plans),
        "run", "--out", str(tmp_path / name), "--strong", "model-strong-x", "--balanced", "model-balanced-y",
        "--private-root", str(tmp_path / "priv"), "--progress", str(tmp_path / progress), *extra,
    ]


def test_main_run_exits_3_on_a_usage_limit_then_resumes_to_a_report_without_task_text(tmp_path):
    """Adversarial where: the usage-limit halt exits 1 (or 0 with a partial
    report) so the operator cannot tell to rerun; the resumed run leaves the
    finished sessions out of the report; or the report leaks the task title,
    the plan goal, or the text a session quoted in its `words:` line."""
    plans = _vault_plans(tmp_path)
    args = _run_args(tmp_path, plans)
    out = tmp_path / "out.md"

    halted = ScriptedRunner(["letter: M\nwords: QUOTEDSENTINEL 2-5 files"], limit_after=9)
    assert letters.main(args, runner=halted) == letters.EXIT_USAGE_LIMIT == 3
    assert not out.exists()
    assert len(_read_json(tmp_path / "prog" / "p.json")["done"]) == 9

    resumed = ScriptedRunner(["letter: S\nwords: QUOTEDSENTINEL single file"])
    assert letters.main(args, runner=resumed) == 0
    assert resumed.calls == 6 * 2 * 3 - 9

    report = out.read_text(encoding="utf-8")
    for leaked in ("TITLESENTINEL", "GOALSENTINEL", "QUOTEDSENTINEL", "depends_on"):
        assert leaked not in report, leaked
    assert len(set(re.findall(r"PLAN-904/TASK-\d+", report))) == 6
    assert "model-strong-x" in report and "model-balanced-y" in report


def test_main_run_refuses_a_foreign_progress_file_and_equal_models(tmp_path):
    """Adversarial where: a changed seed silently reuses another draw's
    progress, or two identical model names produce a 'between models' figure
    that compares a model with itself; both must exit 1 before any session."""
    plans = _vault_plans(tmp_path)
    assert letters.main(_run_args(tmp_path, plans), runner=ScriptedRunner(["letter: M\nwords: w"])) == 0

    runner = ScriptedRunner(["letter: M\nwords: w"])
    changed_seed = _run_args(tmp_path, plans)
    changed_seed[changed_seed.index("--seed") + 1] = "4"
    assert letters.main(changed_seed, runner=runner) == 1

    same = _run_args(tmp_path, plans, progress="other.json")
    same[same.index("--balanced") + 1] = "model-strong-x"
    assert letters.main(same, runner=runner) == 1
    assert runner.calls == 0


def test_main_run_rejects_a_single_session_before_spending_any(tmp_path):
    """Adversarial where: Fleiss' kappa needs at least two sessions per model,
    yet `--sessions 1` is accepted and every session runs before the report
    step raises; the check belongs before the first session."""
    plans = _vault_plans(tmp_path)
    runner = ScriptedRunner(["letter: M\nwords: w"])
    code = letters.main(_run_args(tmp_path, plans, extra=("--sessions", "1")), runner=runner)
    assert code == 1 and runner.calls == 0


def test_main_dry_run_prints_ids_and_one_prompt_without_the_original_letter(tmp_path, capsys, monkeypatch):
    """Adversarial where: the dry run launches a session, writes a progress
    file, or prints a prompt that still carries the first task's original
    letter."""
    plans = _vault_plans(tmp_path)

    def refuse(*a, **kw):
        raise AssertionError("dry run started a subprocess")

    import launch

    monkeypatch.setattr(launch, "_run", refuse)
    monkeypatch.setattr(launch, "run_session", refuse)
    assert letters.main(["--n", "6", "--seed", "3", "--plans", str(plans), "--dry-run"]) == 0
    shown = capsys.readouterr().out
    assert len(set(re.findall(r"^PLAN-904/TASK-\d+$", shown, re.MULTILINE))) == 6
    prompt = shown.split("prompt of", 1)[1]
    assert not re.search(r"complexity:\s*[SML]", prompt)
    assert "GOALSENTINEL" in prompt
    assert not (tmp_path / "prog").exists()


class _Done:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _stub_claude_on_path(folder):
    stub = Path(folder) / "bin"
    stub.mkdir()
    for name in ("claude.cmd", "claude.exe", "claude"):
        (stub / name).write_text("", encoding="utf-8")
        try:
            (stub / name).chmod(0o755)
        except OSError:
            pass
    return {"PATH": str(stub), "ANTHROPIC_API_KEY": "must-not-pass", "KEEP": "1"}


def _fake_launch_run(monkeypatch, queue, seen):
    """Replace launch._run, the one place a session process starts, with a
    queue of canned (returncode, stdout, stderr) results."""
    import launch

    def fake_run(command, prompt, cwd, env, timeout):
        seen.update(command=command, prompt=prompt, cwd=cwd, env=env, timeout=timeout)
        return queue.pop(0)

    monkeypatch.setattr(launch, "_run", fake_run)
    monkeypatch.setattr(launch, "check_plugin_clean", lambda repo_root, require_plugin=False: "sha0")


def test_default_runner_goes_through_launch_and_isolates_the_session(tmp_path, monkeypatch):
    """Adversarial where: the runner starts its own process instead of the
    bench's launcher (so no CREATE_NO_WINDOW, no process-tree kill at the
    timeout); the prompt rides on the command line; a flag the launcher
    already adds is passed twice; a zero-exit reply quoting the words `usage
    limit` is taken as a halt; a nonzero exit without a rejected rate-limit
    event is taken as a limit; the session inherits the operator's API key."""
    import json

    parent = _stub_claude_on_path(tmp_path)
    parent["ANTHROPIC_API_KEY"] = "must-not-pass"
    seen, queue = {}, []
    _fake_launch_run(monkeypatch, queue, seen)
    prompt = "--looks-like-a-flag\nrate this task"
    argv = letters.session_command("m", prompt)
    folder = tmp_path / "work"
    folder.mkdir()

    def events(*items):
        return "\n".join(json.dumps(item) for item in items) + "\n"

    answer = "letter: M\nwords: the usage limit text"
    queue.append((0, events({"type": "result", "is_error": False, "result": answer}), ""))
    reply = letters.default_runner(argv, folder, private_root=tmp_path / "priv", parent_env=parent)
    assert reply.startswith("letter: M")
    assert seen["cwd"] == str(folder)
    assert seen["prompt"] == prompt
    command = seen["command"]
    assert prompt not in command
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert seen["env"]["CLAUDE_CONFIG_DIR"].startswith(str(tmp_path / "priv"))
    assert command[command.index("--model") + 1] == "m"
    assert command[command.index("--tools") + 1] == ""
    for flag in ("--no-session-persistence", "--strict-mcp-config", "-p", "--verbose", "--setting-sources", "--output-format"):
        assert command.count(flag) == 1, flag
    assert "--" not in command
    assert seen["timeout"] == letters.SESSION_TIMEOUT

    queue.append((1, events({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1}}), ""))
    with pytest.raises(letters.UsageLimit):
        letters.default_runner(argv, folder, private_root=tmp_path / "priv", parent_env=parent)

    queue.append((1, "", "network down"))
    with pytest.raises(letters.SessionFailed) as caught:
        letters.default_runner(argv, folder, private_root=tmp_path / "priv", parent_env=parent)
    assert not isinstance(caught.value, letters.UsageLimit)

    queue.append((1, "", "Claude usage limit reached. Resets at 3pm"))
    with pytest.raises(letters.SessionFailed) as caught:
        letters.default_runner(argv, folder, private_root=tmp_path / "priv", parent_env=parent)
    assert not isinstance(caught.value, letters.UsageLimit)

    queue.append((None, "", ""))
    with pytest.raises(letters.SessionFailed):
        letters.default_runner(argv, folder, private_root=tmp_path / "priv", parent_env=parent)


class ConcurrentRunner:
    """Thread-safe fake runner that records the most sessions in flight at once."""

    def __init__(self, reply, hold=0.02, limit_after=None):
        import threading

        self.reply = reply
        self.hold = hold
        self.limit_after = limit_after
        self.lock = threading.Lock()
        self.calls = 0
        self.active = 0
        self.peak = 0

    def __call__(self, argv, cwd):
        import time

        with self.lock:
            if self.limit_after is not None and self.calls >= self.limit_after:
                raise letters.UsageLimit("usage limit reached")
            self.calls += 1
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.hold)
            return self.reply(argv) if callable(self.reply) else self.reply
        finally:
            with self.lock:
                self.active -= 1


def test_run_batch_with_jobs_runs_sessions_side_by_side_and_never_more_than_jobs(tmp_path):
    """Adversarial where: `jobs` is ignored (sessions still one at a time), it
    is exceeded, or the threads lose sessions or mix up which letter belongs
    to which task and model in the progress file."""
    tasks = _batch_tasks()
    models = ["strong-a", "balanced-b"]
    config = {"ids": [t.id for t in tasks], "models": models, "sessions": 3, "seed": 5}

    def reply(argv):
        model = argv[argv.index("--model") + 1]
        return "letter: %s\nwords: w" % ("S" if model == "strong-a" else "L")

    runner = ConcurrentRunner(reply)
    results = letters.run_batch(
        tasks, models, 3, _plan_table(), runner=runner, progress_path=tmp_path / "p.json", config=config, jobs=3
    )
    assert runner.calls == 24
    assert runner.peak == 3
    assert all(r["ratings"] == {"strong-a": ["S"] * 3, "balanced-b": ["L"] * 3} for r in results)
    assert len(_read_json(tmp_path / "p.json")["done"]) == 24


def test_run_batch_with_jobs_halts_at_a_usage_limit_keeping_every_finished_session(tmp_path):
    """Adversarial where: a usage limit in one thread is swallowed while other
    threads keep starting sessions, or the sessions that finished beside the
    halted one are not saved, so a resume re-bills them."""
    tasks = _batch_tasks()
    models = ["a", "b"]
    config = {"ids": [t.id for t in tasks], "models": models, "sessions": 3, "seed": 5}
    progress = tmp_path / "p.json"
    halted = ConcurrentRunner("letter: M\nwords: w", limit_after=8)
    with pytest.raises(letters.UsageLimit):
        letters.run_batch(tasks, models, 3, _plan_table(), runner=halted, progress_path=progress, config=config, jobs=3)
    assert halted.calls == 8
    assert len(_read_json(progress)["done"]) == 8

    resumed = ConcurrentRunner("letter: S\nwords: w")
    letters.run_batch(tasks, models, 3, _plan_table(), runner=resumed, progress_path=progress, config=config, jobs=3)
    assert resumed.calls == 24 - 8


def test_main_run_rejects_jobs_below_one_before_spending_any(tmp_path):
    plans = _vault_plans(tmp_path)
    """Adversarial where: `--jobs 0` starts nothing yet hangs, or a negative
    count reaches the thread pool and raises after the draw."""
    runner = ScriptedRunner(["letter: M\nwords: w"])
    assert letters.main(_run_args(tmp_path, plans, extra=("--jobs", "0")), runner=runner) == 1
    assert runner.calls == 0
