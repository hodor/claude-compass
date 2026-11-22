"""Tests for probe.py: ground-truth probes over recorded compaction points.

Interface the tests pin (module `probe`, importable as `import probe`)
-----------------------------------------------------------------------
Files read-only: Claude Code transcripts (`*.jsonl`, one JSON object per line).
Files written: under `<private root>/probes/` only; `Refused` when that folder
would sit inside a git work tree (checked before any write).

    find(project_dir) -> [point, ...]
        one dict per compaction boundary in the `*.jsonl` files directly inside
        `project_dir`: {"point": str, "transcript": str, "boundary": int,
        "trigger": str, "pre_tokens": int, "post_tokens": int or None}.
        `boundary` is the 0-based line index of the `system/compact_boundary`
        record; `point["point"]` is the POINT string every other command takes
        (format `<transcript path>#<boundary>`; the tests treat it as opaque).
    build(point, *, private_root=None) -> {"point": str, "model": str, "probes": [probe, ...]}
        freezes the probe set; a second build of the point raises `AlreadyFrozen`.
        probe = {"id": str, "type": str, "question": str, "expected": ...}
          id "artifact"        type "artifact"      expected: list of edited paths
          id "recall-1"/"-2"   type "recall"        expected: str literal
          id "continuation"    type "continuation"  expected: "TASK-12" style id
          id "decision"        type "decision"      expected: the chosen option text
        `model` is the model of the last assistant record before the boundary.
        Probes with no source in the history are absent. `question` never holds `expected`.
    ask(point, arm, *, repo_root, private_root=None, claude_cmd=None, parent_env=None)
        -> {"point": str, "arm": str, "reply": str, "tokens": {model: {kind: int}}}
        arm "host-summary" | "none" (ValueError otherwise); `NotBuilt` (a
        LookupError) when the point was never built. Session started through
        launch.run_session with `--tools ""` and `--model <probe set model>`, in
        a fresh sandbox.new_project below the private root.
        stdin = carried text (the `isCompactSummary` record's content, or
        nothing for "none") + every question + a request for one JSON object whose
        keys are the probe ids ("artifact" holds a list of paths, the others strings).
    grade(point, *, private_root=None) -> {arm: {"point", "arm", "unparsed": bool, "scores": {id: score}}}
        for every arm already asked. score: float 0.0 / 1.0, except "artifact":
        {"precision": float, "recall": float}. A reply that is no JSON object
        gives unparsed True and 0 on every id; a missing key scores 0 alone.
        The grades are stored for `report`.
    report(*, private_root=None) -> str
        markdown table, header `| arm | probe | points | mean score | unparsed | mean carried tokens |`,
        one row per arm and probe type (recall's two probes of a point count as one
        point, its score their mean; artifact's score is its recall), scores with
        two decimals, `unparsed` the arm's unparsed points, no path, prompt,
        id or answer text.
    main(argv, *, claude_cmd=None, repo_root=None, parent_env=None) -> int
        `--private-root DIR` before the subcommand; `find --project-dir DIR`
        prints one line per point (POINT, trigger, pre tokens, post tokens);
        `build POINT`, `ask POINT --arm ARM`, `grade POINT`, `report`;
        exit 0, 2 for Refused / AlreadyFrozen / NotBuilt / ValueError.

Adversarial themes: history after the boundary leaking into the answer key; a
key that over-includes (Read paths, user-typed ids); a question that hands over
its own answer; a floor arm that carries text; a private store inside git;
a grader that rewards paths by spelling instead of identity; a report that
leaks session content; a grep-style boundary finder fooled by quoted markers.
"""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

import fake_claude
import probe
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "probe-session.jsonl"
FIXTURE_MODEL = "claude-haiku-4-5"
SUMMARY_MARK = "ZQSUMMARY"
EDITED = ["src/app/main.py", "docs/notes.md", "src/app/util.py"]
SECRETS = (
    "src/app/main.py", "docs/notes.md", "probe-session", "TASK-12", "TASK-4", "PLAN-7",
    "Flat files", "3 failed", "bad frame width", SUMMARY_MARK, "decoder strategy", "frame cache",
    "ZQ", "claude-haiku",
)


@pytest.fixture
def project_dir(tmp_path):
    folder = tmp_path / "claude-project"
    folder.mkdir()
    shutil.copy(FIXTURE, folder / "probe-session.jsonl")
    return folder


@pytest.fixture
def point(project_dir):
    (found,) = probe.find(project_dir)
    return found["point"]


def _record(kind, index, **extra):
    base = {
        "type": kind, "uuid": f"e{index:03d}", "timestamp": "2026-02-01T00:00:00.000Z",
        "sessionId": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "isSidechain": False,
    }
    base.update(extra)
    return base


def user(index, text):
    return _record("user", index, message={"role": "user", "content": text})


def assistant(index, text="", tool=None):
    content = [{"type": "text", "text": text}] if text else []
    if tool:
        content.append({"type": "tool_use", "id": f"tt{index}", "name": tool[0], "input": tool[1]})
    return _record("assistant", index, message={
        "id": f"m{index}", "role": "assistant", "model": FIXTURE_MODEL, "content": content})


def tool_result(index, text, is_error=False):
    return _record("user", index, message={"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": f"tt{index - 1}", "content": text, "is_error": is_error}]})


def boundary(index, trigger="manual", pre=90000):
    return _record("system", index, subtype="compact_boundary", content="Conversation compacted",
                   compactMetadata={"trigger": trigger, "preTokens": pre})


def summary(index, text="SUMTEXT edited a.py"):
    return _record("user", index, message={"role": "user", "content": text}, isCompactSummary=True)


def write_transcript(folder, name, records):
    path = Path(folder) / name
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


def build_point(folder, records, name="t.jsonl", private_root=None):
    write_transcript(folder, name, records)
    (found,) = probe.find(folder)
    return found["point"], probe.build(found["point"], private_root=private_root)


def probe_by_id(built):
    return {item["id"]: item for item in built["probes"]}


def key_answers(built, **overrides):
    """The reply that answers every probe with its frozen expected value."""
    answers = {item["id"]: item["expected"] for item in built["probes"]}
    answers.update(overrides)
    return answers


# find -----------------------------------------------------------------------


def test_find_lists_the_fixtures_single_boundary_with_its_metadata(project_dir):
    """Adversarial where: a finder that counts the summary record or the lookalike
    markers inside text as boundaries, or drops trigger and token metadata."""
    found = probe.find(project_dir)

    assert len(found) == 1
    item = found[0]
    assert (item["boundary"], item["trigger"], item["pre_tokens"], item["post_tokens"]) == (19, "auto", 150000, 20000)
    assert Path(item["transcript"]).name == "probe-session.jsonl"


def test_find_ignores_quoted_boundary_markers_and_counts_each_real_one(tmp_path):
    """Adversarial where: a substring scan treats a user message that quotes
    "compact_boundary" or "isCompactSummary" as a boundary, or merges two real
    boundaries of one transcript."""
    folder = tmp_path / "p"
    folder.mkdir()
    records = [
        user(0, 'note: {"subtype": "compact_boundary", "isCompactSummary": true} is how it looks'),
        assistant(1, "the record has subtype compact_boundary"),
        boundary(2, "manual", 80000),
        summary(3),
        user(4, "go on"),
        boundary(5, "auto", 120000),
        summary(6),
    ]
    write_transcript(folder, "t.jsonl", records)

    found = probe.find(folder)

    assert [(f["boundary"], f["trigger"], f["pre_tokens"]) for f in found] == [(2, "manual", 80000), (5, "auto", 120000)]
    assert len({f["point"] for f in found}) == 2
    assert found[0]["post_tokens"] is None


def test_find_skips_transcripts_without_boundary_and_other_files(tmp_path):
    """Adversarial where: a folder scan that crashes on, or lists, a transcript
    with no compaction, a non-jsonl file, or an empty folder."""
    folder = tmp_path / "p"
    folder.mkdir()
    write_transcript(folder, "plain.jsonl", [user(0, "hi"), assistant(1, "hello")])
    (folder / "notes.txt").write_text(json.dumps(boundary(0)), encoding="utf-8")

    assert probe.find(folder) == []


# build ----------------------------------------------------------------------


def test_build_freezes_the_expected_answer_key_for_the_fixture(point, private_root):
    """Adversarial where: an artifact set that includes Read paths, duplicate Edit
    paths or history after the boundary; a continuation id taken from a user message
    or from after the boundary; an older AskUserQuestion; recall literals that miss
    the error line or the failing-test summary."""
    built = probe.build(point, private_root=private_root)
    probes = probe_by_id(built)

    assert built["model"] == FIXTURE_MODEL
    assert sorted(probes["artifact"]["expected"]) == sorted(EDITED)
    assert len(probes["artifact"]["expected"]) == 3
    assert probes["continuation"]["expected"] == "TASK-12"
    assert probes["decision"]["expected"] == "Flat files"
    recalls = [item["expected"] for item in built["probes"] if item["type"] == "recall"]
    assert len(recalls) == 2
    assert any("bad frame width 17" in text for text in recalls)
    assert any("3 failed" in text for text in recalls)
    everything = json.dumps(built)
    for after in ("after/ignored.py", "TASK-99", "ghost", "5 failed", "README.md", "TASK-50", "Alpha"):
        assert after not in everything


def test_build_questions_never_carry_their_own_answer(point, private_root):
    """Adversarial where: a decision question that lists its options, a recall
    question that quotes the literal, or an artifact question naming the paths hands
    the answer to the model that is being tested."""
    built = probe.build(point, private_root=private_root)

    for item in built["probes"]:
        expected = item["expected"] if isinstance(item["expected"], list) else [item["expected"]]
        for answer in expected:
            assert answer not in item["question"], item["id"]
    assert "frame cache" in probe_by_id(built)["decision"]["question"]


def test_build_stores_under_the_private_root_and_leaves_the_transcript_untouched(point, private_root, project_dir):
    """Adversarial where: a builder that rewrites the transcript it reads or
    writes its key outside the private probes folder."""
    transcript = project_dir / "probe-session.jsonl"
    before = hashlib.sha256(transcript.read_bytes()).hexdigest()

    probe.build(point, private_root=private_root)

    assert hashlib.sha256(transcript.read_bytes()).hexdigest() == before
    stored = [p for p in (private_root / "probes").rglob("*") if p.is_file()]
    assert stored
    assert all(p.resolve().is_relative_to((private_root / "probes").resolve()) for p in stored)
    assert [p for p in project_dir.iterdir()] == [transcript]


def test_second_build_of_a_point_is_refused_and_keeps_the_first_key(point, private_root):
    """Adversarial where: a rebuild that silently replaces a frozen answer key,
    so the arms are graded against different keys."""
    probe.build(point, private_root=private_root)
    files = sorted(p for p in (private_root / "probes").rglob("*") if p.is_file())
    before = [(p, p.read_bytes()) for p in files]

    with pytest.raises(probe.AlreadyFrozen):
        probe.build(point, private_root=private_root)

    files_after = sorted(p for p in (private_root / "probes").rglob("*") if p.is_file())
    assert before and [(p, p.read_bytes()) for p in files_after] == before


def test_point_without_question_error_or_ids_yields_the_artifact_probe_alone(tmp_path, private_root):
    """Adversarial where: skipped probe types that still appear with an empty
    question or a None answer, so a floor arm is graded on nothing."""
    folder = tmp_path / "p"
    folder.mkdir()
    records = [
        user(0, "do it"),
        assistant(1, "editing now", ("Edit", {"file_path": "a/b.py", "old_string": "x", "new_string": "y"})),
        tool_result(2, "ok"),
        boundary(3),
        summary(4),
    ]

    _, built = build_point(folder, records, private_root=private_root)

    assert [item["id"] for item in built["probes"]] == ["artifact"]
    assert built["probes"][0]["expected"] == ["a/b.py"]


def test_recall_is_capped_at_two_literals(tmp_path, private_root):
    """Adversarial where: every error line of a noisy tool result becomes a probe,
    so one point outweighs the others in the report."""
    folder = tmp_path / "p"
    folder.mkdir()
    noisy = "KeyError: alpha9\nTypeError: beta8\nValueError: gamma7\n4 failed, 2 passed in 1.00s"
    records = [
        user(0, "run it"),
        assistant(1, "running", ("Bash", {"command": "pytest"})),
        tool_result(2, noisy, is_error=True),
        boundary(3),
        summary(4),
    ]

    _, built = build_point(folder, records, private_root=private_root)

    recalls = [item for item in built["probes"] if item["type"] == "recall"]
    assert 1 <= len(recalls) <= 2
    assert all(item["expected"] in noisy for item in recalls)


def test_build_refuses_a_private_root_inside_a_git_work_tree(point, repo):
    """Adversarial where: probe sets, which hold session content, written into a
    repository that could be committed."""
    inside = repo / "overhead"

    with pytest.raises(probe.Refused):
        probe.build(point, private_root=inside)

    assert not (inside / "probes").exists()


# ask ------------------------------------------------------------------------


def _ask(point, arm, repo, private_root, fake_reply):
    return probe.ask(point, arm, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)


def test_ask_host_summary_passes_no_tools_the_model_the_summary_and_every_question(
        point, repo, private_root, fake_reply):
    """Adversarial where: a session that keeps its tools and reads the repo, runs
    on another model than the compacted session, omits the summary or a question,
    or starts in the repository instead of a fresh project."""
    built = probe.build(point, private_root=private_root)
    reply_text = json.dumps(key_answers(built))
    fake_reply.reply(reply_text)

    result = _ask(point, "host-summary", repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    argv = call["argv"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == FIXTURE_MODEL
    assert f"{SUMMARY_MARK}: the session decoded frames" in call["stdin"]
    for item in built["probes"]:
        assert item["question"] in call["stdin"]
    assert "JSON" in call["stdin"]
    cwd = Path(call["cwd"]).resolve()
    assert cwd.is_relative_to(private_root.resolve())
    assert not cwd.is_relative_to(repo.resolve())
    assert (cwd / ".git").exists()
    assert result["reply"] == reply_text
    assert result["arm"] == "host-summary"
    assert result["tokens"][fake_claude.MAIN_MODEL]["input"] == 10
    assert result["tokens"][fake_claude.MAIN_MODEL]["output"] == 5


def test_ask_none_arm_carries_no_summary_and_no_answer(point, repo, private_root, fake_reply):
    """Adversarial where: the floor arm that still receives the summary or any
    expected answer through its questions, which erases the gap being measured."""
    built = probe.build(point, private_root=private_root)
    fake_reply.reply("{}")

    _ask(point, "none", repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    argv = call["argv"]
    assert argv[argv.index("--tools") + 1] == ""
    assert SUMMARY_MARK not in call["stdin"]
    assert "decoded frames" not in call["stdin"]
    for item in built["probes"]:
        assert item["question"] in call["stdin"]
        answers = item["expected"] if isinstance(item["expected"], list) else [item["expected"]]
        for answer in answers:
            assert answer not in call["stdin"]


def test_ask_rejects_an_unknown_arm_and_an_unbuilt_point_before_any_session(
        point, repo, private_root, fake_reply):
    """Adversarial where: an arm typo that runs a session with a half prompt, or an
    ask of a point with no frozen key that has nothing to be graded against."""
    with pytest.raises(LookupError):
        _ask(point, "none", repo, private_root, fake_reply)
    probe.build(point, private_root=private_root)
    with pytest.raises(ValueError):
        _ask(point, "oracle", repo, private_root, fake_reply)

    assert fake_reply.calls() == []


def test_ask_refuses_a_private_root_inside_a_git_work_tree(point, repo, fake_reply, tmp_path):
    """Adversarial where: raw model replies, which quote session content, stored
    in a repository, or a session started before the refusal."""
    inside = repo / "overhead"

    with pytest.raises(probe.Refused):
        probe.ask(point, "none", repo_root=repo, private_root=inside, claude_cmd=fake_reply.command)

    assert fake_reply.calls() == []
    assert not (inside / "probes").exists()


# grade ----------------------------------------------------------------------


def _graded(point, repo, private_root, fake_reply, reply_for, arm="host-summary"):
    """Build, ask with the reply `reply_for(built)` returns (a dict is sent as
    JSON, a string as is) and grade."""
    built = probe.build(point, private_root=private_root)
    reply = reply_for(built)
    fake_reply.reply(reply if isinstance(reply, str) else json.dumps(reply))
    _ask(point, arm, repo, private_root, fake_reply)
    return probe.grade(point, private_root=private_root)[arm]


def test_grade_scores_two_of_three_paths_plus_one_extra_at_two_thirds(point, repo, private_root, fake_reply):
    """Adversarial where: precision or recall computed against the wrong set
    size, so an extra path is free or a missed path is invisible."""
    def reply(built):
        return key_answers(built, artifact=["src/app/main.py", "docs/notes.md", "src/app/invented.py"])

    graded = _graded(point, repo, private_root, fake_reply, reply)

    assert graded["unparsed"] is False
    assert graded["scores"]["artifact"]["recall"] == pytest.approx(2 / 3, abs=0.01)
    assert graded["scores"]["artifact"]["precision"] == pytest.approx(2 / 3, abs=0.01)
    assert graded["scores"]["continuation"] == 1.0
    assert graded["scores"]["decision"] == 1.0
    recall_ids = [i for i in graded["scores"] if i.startswith("recall")]
    assert len(recall_ids) == 2 and all(graded["scores"][i] == 1.0 for i in recall_ids)


def test_grade_matches_paths_by_identity_not_by_spelling(point, repo, private_root, fake_reply):
    """Adversarial where: a leading `./` or a backslash separator turns a correct
    path into a miss and an extra, understating the host summary."""
    def reply(built):
        return key_answers(built, artifact=["./src/app/main.py", "docs\\notes.md", ".\\src\\app\\util.py"])

    graded = _graded(point, repo, private_root, fake_reply, reply)

    assert graded["scores"]["artifact"] == {"precision": 1.0, "recall": 1.0}


def test_grade_does_not_match_a_path_that_only_shares_a_basename(point, repo, private_root, fake_reply):
    """Adversarial where: basename matching credits `other/main.py` for
    `src/app/main.py`, rewarding a guess at the file name."""
    def reply(built):
        return key_answers(built, artifact=["other/main.py", "x/notes.md", "y/util.py"])

    graded = _graded(point, repo, private_root, fake_reply, reply)

    assert graded["scores"]["artifact"] == {"precision": 0.0, "recall": 0.0}


def test_grade_wrong_continuation_and_decision_score_zero_while_recall_is_a_substring_match(
        point, repo, private_root, fake_reply):
    """Adversarial where: an id compared as a prefix (TASK-1 for TASK-12), a wrong
    option accepted, or a recall literal needing an exact reply instead of a
    normalized substring."""
    def reply(built):
        first, second = [item for item in built["probes"] if item["type"] == "recall"]
        noisy = "  the log said  " + first["expected"].upper().replace(" ", "   ") + "  at line 3 "
        return key_answers(
            built, continuation="TASK-1", decision="Single database",
            **{first["id"]: noisy, second["id"]: "zzz nothing like it"})

    graded = _graded(point, repo, private_root, fake_reply, reply)

    scores = graded["scores"]
    assert scores["continuation"] == 0.0
    assert scores["decision"] == 0.0
    recall_scores = sorted(value for key, value in scores.items() if key.startswith("recall"))
    assert recall_scores == [0.0, 1.0]


def test_grade_non_json_reply_is_unparsed_and_zero_everywhere(point, repo, private_root, fake_reply):
    """Adversarial where: a prose reply scored by lucky substrings, or crashing
    the grader, instead of counting as unparsed with a zero on every probe."""
    prose = "I edited src/app/main.py, docs/notes.md and src/app/util.py; next is TASK-12, Flat files."

    graded = _graded(point, repo, private_root, fake_reply, lambda built: prose)

    assert graded["unparsed"] is True
    scores = graded["scores"]
    assert scores["artifact"] == {"precision": 0.0, "recall": 0.0}
    assert all(value == 0.0 for key, value in scores.items() if key != "artifact")
    assert set(scores) >= {"artifact", "continuation", "decision"}


def test_grade_reads_a_fenced_json_reply_and_scores_a_missing_key_zero_alone(
        point, repo, private_root, fake_reply):
    """Adversarial where: a fenced ```json reply counted as unparsed, or one missing
    key that fails the whole reply instead of its own probe."""
    def reply(built):
        answers = key_answers(built)
        del answers["decision"]
        return "Here you go:\n```json\n" + json.dumps(answers) + "\n```"

    graded = _graded(point, repo, private_root, fake_reply, reply)

    assert graded["unparsed"] is False
    assert graded["scores"]["decision"] == 0.0
    assert graded["scores"]["artifact"] == {"precision": 1.0, "recall": 1.0}
    assert graded["scores"]["continuation"] == 1.0


# report ---------------------------------------------------------------------


def _cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def test_report_gives_per_arm_rows_and_leaks_no_session_content(point, repo, private_root, fake_reply, tmp_path):
    """Adversarial where: a report that prints a path, a question, an id, an
    answer, a model name or the point string, or that mixes the arms into one row."""
    built = probe.build(point, private_root=private_root)
    fake_reply.reply(json.dumps(key_answers(built)))
    _ask(point, "host-summary", repo, private_root, fake_reply)
    fake_reply.reply("I do not remember any of it")
    _ask(point, "none", repo, private_root, fake_reply)
    probe.grade(point, private_root=private_root)

    text = probe.report(private_root=private_root)

    lines = [line for line in text.splitlines() if line.strip().startswith("|")]
    header = _cells(lines[0])
    assert header[:2] == ["arm", "probe"] and "carried" in lines[0].lower()
    rows = {(_cells(line)[0], _cells(line)[1]): _cells(line) for line in lines[2:]}
    for kind in ("artifact", "recall", "continuation", "decision"):
        host, floor = rows[("host-summary", kind)], rows[("none", kind)]
        assert host[2] == floor[2] == "1"
        assert host[3] == "1.00"
        assert floor[3] == "0.00"
        assert host[4] == "0" and floor[4] == "1"
    for secret in SECRETS + (str(tmp_path), str(point), "I do not remember"):
        assert secret not in text


def test_cli_build_ask_grade_report_chain_and_refusals_exit_two(
        point, repo, private_root, fake_reply, capsys):
    """Adversarial where: a command line that raises a traceback for a refused
    private root or a repeated build instead of returning exit status 2, or whose
    subcommands cannot hand the stored key to one another."""
    root = str(private_root)
    assert probe.main(["--private-root", root, "build", point]) == 0
    assert probe.main(["--private-root", root, "build", point]) == 2
    assert probe.main(["--private-root", str(repo / "overhead"), "build", point]) == 2
    with pytest.raises(SystemExit) as parse_error:
        probe.main(["--private-root", root, "ask", point, "--arm", "oracle"],
                   claude_cmd=fake_reply.command, repo_root=repo)
    assert parse_error.value.code == 2
    capsys.readouterr()

    fake_reply.reply("{}")
    code = probe.main(
        ["--private-root", root, "ask", point, "--arm", "host-summary"],
        claude_cmd=fake_reply.command, repo_root=repo)
    assert code == 0
    assert probe.main(["--private-root", root, "grade", point]) == 0
    capsys.readouterr()
    assert probe.main(["--private-root", root, "report"]) == 0

    out = capsys.readouterr().out
    assert re.search(r"\|\s*host-summary\s*\|\s*artifact\s*\|", out)


def test_find_cli_prints_the_point_with_trigger_and_token_counts(project_dir, point, capsys):
    """Adversarial where: a find command that prints nothing usable, so the next
    command cannot be given a POINT."""
    assert probe.main(["find", "--project-dir", str(project_dir)]) == 0

    out = capsys.readouterr().out
    (line,) = [line for line in out.splitlines() if line.strip()]
    assert point in line
    assert "auto" in line and "150000" in line and "20000" in line
