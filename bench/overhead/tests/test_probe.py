"""Tests for probe.py: ground-truth probes over recorded compaction points.

Interface the tests pin (module `probe`, importable as `import probe`)
-----------------------------------------------------------------------
Files read-only: Claude Code transcripts (`*.jsonl`, one JSON object per line).
Files written: under `<private root>/probes/` only; `Refused` when that folder
would sit inside a git work tree (checked before any write).

    find(project_dir) -> [point, ...]
        one dict per compaction boundary in the `*.jsonl` files directly inside
        `project_dir` and in its `*/subagents/` folders: {"point": str, "transcript": str, "boundary": int,
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
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import fake_claude
import probe
import topics
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
    rows = _main_rows(text)
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


# implementation-revealed defect classes -------------------------------------


def _ask_question(index, question, answer_text, answers=None):
    """An assistant AskUserQuestion call and the user record that answers it."""
    call = assistant(index, "", ("AskUserQuestion", {"questions": [{"question": question}]}))
    reply = tool_result(index + 1, answer_text)
    if answers is not None:
        reply["toolUseResult"] = {"answers": answers}
    return [call, reply]


def _decision_records(question, answer_text):
    edit = assistant(1, "", ("Edit", {"file_path": "a/b.py", "old_string": "x", "new_string": "y"}))
    return [user(0, "go"), edit, tool_result(2, "ok"), *_ask_question(3, question, answer_text),
            boundary(5), summary(6)]


def test_decision_question_text_does_not_contain_the_chosen_option(tmp_path, private_root):
    """Adversarial where: the decision probe quotes the AskUserQuestion text
    verbatim, and a question that lists its own options ("Flat files or a
    database?") hands the grader's expected answer to the model under test."""
    question = "Which storage do we use, Flat files or a database?"
    folder = tmp_path / "p"
    folder.mkdir()
    text = f'User has answered your questions: "{question}"="Flat files". You can now continue.'

    _, built = build_point(folder, _decision_records(question, text), private_root=private_root)

    decision = probe_by_id(built)["decision"]
    assert decision["expected"] == "Flat files"
    assert decision["expected"].casefold() not in decision["question"].casefold()


def test_decision_answer_with_a_backslash_does_not_abort_the_whole_build(tmp_path, private_root):
    """Adversarial where: the fallback parser of the answer text feeds the raw
    capture to json.loads, so an answer such as `C:\\dir` (an invalid JSON
    escape) raises and one odd answer costs the point every probe."""
    folder = tmp_path / "p"
    folder.mkdir()
    text = 'User has answered your questions: "Where do the logs go?"="C:\\dir\\logs". You can now continue.'

    _, built = build_point(folder, _decision_records("Where do the logs go?", text), private_root=private_root)

    assert "artifact" in probe_by_id(built)


def test_decision_is_read_from_structured_answers_when_present_and_skips_declined_questions(
        tmp_path, private_root):
    """Adversarial where: the structured `toolUseResult.answers` ignored in favor
    of text, or a declined question (is_error) taken as the user's choice."""
    folder = tmp_path / "p"
    folder.mkdir()
    declined = _ask_question(3, "Second question?", "The user declined")
    declined[1]["message"]["content"][0]["is_error"] = True
    records = [
        user(0, "go"),
        *_ask_question(1, "First question?", "irrelevant text", answers={"First question?": "Option Alpha"}),
        *declined,
        boundary(5), summary(6),
    ]

    _, built = build_point(folder, records, private_root=private_root)

    decision = probe_by_id(built)["decision"]
    assert decision["expected"] == "Option Alpha"
    assert "Second question" not in decision["question"]


def test_edit_paths_are_cwd_relative_deduplicated_and_exclude_reads_and_sidechains(tmp_path, private_root):
    """Adversarial where: absolute or backslash spellings of one file counted as
    several paths, a Read or a sidechain edit counted as an edit, or a path
    outside the working folder mangled by the cwd prefix strip."""
    folder = tmp_path / "p"
    folder.mkdir()
    cwd = "C:\\work\\proj"
    edit = {"old_string": "x", "new_string": "y"}
    first = assistant(1, "", ("Edit", {"file_path": "C:\\work\\proj\\src\\a.py", **edit}))
    again = assistant(2, "", ("Write", {"file_path": "c:/WORK/proj/src/a.py", "content": "z"}))
    outside = assistant(3, "", ("MultiEdit", {"file_path": "C:\\work\\project2\\b.py", "edits": []}))
    read = assistant(4, "", ("Read", {"file_path": "C:\\work\\proj\\read-only.py"}))
    side = assistant(5, "", ("Edit", {"file_path": "C:\\work\\proj\\side.py", **edit}))
    side["isSidechain"] = True
    blank = assistant(6, "", ("Edit", {"file_path": "   ", **edit}))
    for item in (first, again, outside, read, side, blank):
        item["cwd"] = cwd
    records = [user(0, "go"), first, again, outside, read, side, blank, boundary(7), summary(8)]

    _, built = build_point(folder, records, private_root=private_root)

    assert probe_by_id(built)["artifact"]["expected"] == ["src/a.py", "C:/work/project2/b.py"]


def test_grade_matches_an_absolute_reply_path_below_the_working_folder(tmp_path, repo, private_root, fake_reply):
    """Adversarial where: the key holds cwd-relative paths but a reply that names
    the same files by absolute path, in either slash direction and any case of
    the folder, scores 0, while a path outside the folder or a bare suffix of a
    deeper file still counts as a miss."""
    folder = tmp_path / "p"
    folder.mkdir()
    cwd = r"C:\work\proj"
    edit = {"old_string": "x", "new_string": "y"}
    first = assistant(1, "", ("Edit", {"file_path": r"C:\work\proj\src\a.py", **edit}))
    second = assistant(2, "", ("Edit", {"file_path": r"C:\work\proj\tests\test_a.py", **edit}))
    for item in (first, second):
        item["cwd"] = cwd
    point, built = build_point(folder, [user(0, "go"), first, second, boundary(3), summary(4)], private_root=private_root)
    assert built["cwd"] == cwd
    fake_reply.reply(json.dumps({"artifact": ["c:/WORK/proj/src/a.py", r"C:\other\tests\test_a.py", "test_a.py"]}))
    _ask(point, "host-summary", repo, private_root, fake_reply)

    graded = probe.grade(point, private_root=private_root)["host-summary"]

    assert graded["scores"]["artifact"]["recall"] == pytest.approx(0.5)
    assert graded["scores"]["artifact"]["precision"] == pytest.approx(1 / 3, abs=0.01)


def test_grade_reads_the_working_folder_from_the_transcript_when_the_key_has_none(
        tmp_path, repo, private_root, fake_reply):
    """Adversarial where: a key frozen before the working folder was stored grades
    absolute reply paths as misses instead of reading the folder from its transcript."""
    folder = tmp_path / "p"
    folder.mkdir()
    edit = {"old_string": "x", "new_string": "y"}
    first = assistant(1, "", ("Edit", {"file_path": "/work/proj/src/a.py", **edit}))
    first["cwd"] = "/work/proj"
    point, built = build_point(folder, [user(0, "go"), first, boundary(2), summary(3)], private_root=private_root)
    key_file = probe._point_dir(point, private_root) / "key.json"
    key = json.loads(key_file.read_text(encoding="utf-8"))
    del key["cwd"]
    key_file.write_text(json.dumps(key), encoding="utf-8")
    fake_reply.reply(json.dumps({"artifact": ["/work/proj/src/a.py"]}))
    _ask(point, "host-summary", repo, private_root, fake_reply)

    graded = probe.grade(point, private_root=private_root)["host-summary"]

    assert graded["scores"]["artifact"] == {"precision": 1.0, "recall": 1.0}


def test_a_subagent_transcript_point_is_found_and_built_from_its_sidechain_records(tmp_path, private_root):
    """Adversarial where: a finder that never looks in a session's subagents
    folder, or a history reader that drops every record of a subagent transcript
    because each one is marked as a sidechain, so its point builds no probe."""
    folder = tmp_path / "p"
    (folder / "sess" / "subagents").mkdir(parents=True)
    edit = {"old_string": "x", "new_string": "y"}
    records = [
        user(0, "go"),
        assistant(1, "working on TASK-9", ("Edit", {"file_path": "sub.py", **edit})),
        boundary(2),
        summary(3),
    ]
    for item in records:
        item["isSidechain"] = True
    main_side = assistant(4, "TASK-1", ("Edit", {"file_path": "main.py", **edit}))
    write_transcript(folder / "sess" / "subagents", "agent-x.jsonl", records + [main_side])
    write_transcript(folder, "sess.jsonl", [user(0, "hi"), assistant(1, "hello")])

    (found,) = probe.find(folder)
    built = probe.build(found["point"], private_root=private_root)

    assert Path(found["transcript"]).name == "agent-x.jsonl"
    assert probe_by_id(built)["artifact"]["expected"] == ["sub.py"]
    assert probe_by_id(built)["continuation"]["expected"] == "TASK-9"
    assert probe._carried_text(found["point"]).startswith("SUMTEXT")


@pytest.mark.parametrize("reply", [
    "[]", '"TASK-12"', "42", "null", "", "   ", "{not json", "```json\n[1, 2]\n```",
])
def test_grade_counts_a_reply_without_a_json_object_as_unparsed(point, repo, private_root, fake_reply, reply):
    """Adversarial where: a reply that is valid JSON but not an object (array,
    string, number, null) or is empty slips past the parser as a parsed reply
    and a crash or a stray score follows."""
    graded = _graded(point, repo, private_root, fake_reply, lambda built: reply)

    assert graded["unparsed"] is True
    assert all(
        (score == {"precision": 0.0, "recall": 0.0}) if isinstance(score, dict) else score == 0.0
        for score in graded["scores"].values())


def test_grade_wrong_value_types_score_zero_without_raising(point, repo, private_root, fake_reply):
    """Adversarial where: a model that answers an artifact probe with a string
    (or a list holding non-strings) and string probes with numbers or lists, so
    the scorer iterates characters or raises on a non-string."""
    def reply(built):
        return {"artifact": "src/app/main.py", "recall-1": 7, "recall-2": ["3 failed"],
                "continuation": 12, "decision": None}

    graded = _graded(point, repo, private_root, fake_reply, reply)

    assert graded["unparsed"] is False
    assert graded["scores"]["artifact"] == {"precision": 0.0, "recall": 0.0}
    assert [graded["scores"][k] for k in ("recall-1", "recall-2", "continuation", "decision")] == [0.0] * 4


def test_grade_artifact_list_with_junk_entries_and_duplicates_does_not_inflate_precision(
        point, repo, private_root, fake_reply):
    """Adversarial where: non-string and blank entries counted in the denominator
    or the same path listed twice counted as two hits."""
    def reply(built):
        path = built["probes"][0]["expected"][0]
        assert built["probes"][0]["id"] == "artifact"
        return {"artifact": [path, f"./{path}", path.replace("/", "\\"), "", "  ", 5, None]}

    graded = _graded(point, repo, private_root, fake_reply, reply)

    assert graded["scores"]["artifact"]["precision"] == 1.0
    assert round(graded["scores"]["artifact"]["recall"], 2) == 0.33


def test_grade_continuation_is_case_insensitive_but_two_ids_in_one_answer_score_zero(
        point, repo, private_root, fake_reply):
    """Adversarial where: an answer that hedges with every id it can think of
    scoring as a hit, or a lower-case id missed on spelling."""
    built = probe.build(point, private_root=private_root)
    expected = probe_by_id(built)["continuation"]["expected"]
    fake_reply.reply(json.dumps({"continuation": expected.lower()}))
    _ask(point, "host-summary", repo, private_root, fake_reply)
    fake_reply.reply(json.dumps({"continuation": f"{expected} or PLAN-999"}))
    _ask(point, "none", repo, private_root, fake_reply)

    graded = probe.grade(point, private_root=private_root)

    assert graded["host-summary"]["scores"]["continuation"] == 1.0
    assert graded["none"]["scores"]["continuation"] == 0.0


def test_grade_decision_needs_the_whole_option_not_a_fragment_of_a_longer_word(
        point, repo, private_root, fake_reply):
    """Adversarial where: the decision match is a bare substring, so the option
    `Flat` is credited for an answer that names `Flatten`."""
    built = probe.build(point, private_root=private_root)
    expected = probe_by_id(built)["decision"]["expected"]
    fake_reply.reply(json.dumps({"decision": f"{expected}ter"}))
    _ask(point, "host-summary", repo, private_root, fake_reply)
    fake_reply.reply(json.dumps({"decision": f"  The user chose  {expected.upper()}  indeed"}))
    _ask(point, "none", repo, private_root, fake_reply)

    graded = probe.grade(point, private_root=private_root)

    assert graded["host-summary"]["scores"]["decision"] == 0.0
    assert graded["none"]["scores"]["decision"] == 1.0


def test_grade_refuses_a_private_root_inside_a_git_work_tree_without_writing(point, repo):
    """Adversarial where: grade files, which hold the reply text, written into a
    repository when the refusal is checked only on build and ask."""
    inside = repo / "overhead"

    with pytest.raises(probe.Refused):
        probe.grade(point, private_root=inside)
    assert probe.main(["--private-root", str(inside), "grade", point]) == 2

    assert not (inside / "probes").exists()


def test_a_not_yet_existing_private_root_below_a_git_work_tree_is_refused(point, repo):
    """Adversarial where: the work-tree check stops at the first missing folder,
    so a private root several levels below the repository passes."""
    deep = repo / "a" / "b" / "c"

    with pytest.raises(probe.Refused):
        probe.build(point, private_root=deep)

    assert not (repo / "a").exists()


def test_a_build_that_finds_no_probe_source_leaves_nothing_frozen(tmp_path, private_root):
    """Adversarial where: a failed build leaves a key file behind, so the retry
    after the transcript is fixed is refused as already frozen."""
    folder = tmp_path / "p"
    folder.mkdir()
    write_transcript(folder, "t.jsonl", [user(0, "hi"), assistant(1, "just talk"), boundary(2), summary(3)])
    (found,) = probe.find(folder)

    with pytest.raises(ValueError):
        probe.build(found["point"], private_root=private_root)
    edited = [user(0, "hi"), assistant(1, "x", ("Edit", {"file_path": "a.py"})), boundary(2), summary(3)]
    write_transcript(folder, "t.jsonl", edited)
    built = probe.build(found["point"], private_root=private_root)

    assert [item["id"] for item in built["probes"]] == ["artifact"]


def test_build_of_an_index_that_is_not_a_boundary_is_refused_and_writes_nothing(point, private_root):
    """Adversarial where: a point whose index was shifted by one (or is out of
    range) builds a key from the wrong split of the history."""
    transcript, _, number = point.rpartition("#")

    for bad in (f"{transcript}#{int(number) + 1}", f"{transcript}#9999", transcript, f"{transcript}#x"):
        with pytest.raises(ValueError):
            probe.build(bad, private_root=private_root)

    assert not (private_root / "probes").exists() or not list((private_root / "probes").rglob("*.json"))


def test_ask_host_summary_does_not_carry_a_summary_of_a_later_compaction(
        tmp_path, repo, private_root, fake_reply):
    """Adversarial where: a summary of a later compaction (past the next
    boundary) is carried instead of failing, so the arm is scored on text that
    belongs to another point."""
    folder = tmp_path / "p"
    folder.mkdir()
    records = [
        user(0, "go"), assistant(1, "x", ("Edit", {"file_path": "a.py"})),
        boundary(2), user(3, "more work"),
        boundary(4), summary(5, "LATERSUMMARY"),
    ]
    write_transcript(folder, "t.jsonl", records)
    first_point = probe.find(folder)[0]["point"]
    probe.build(first_point, private_root=private_root)

    with pytest.raises(probe.NoSummary):
        _ask(first_point, "host-summary", repo, private_root, fake_reply)

    assert fake_reply.calls() == []


def test_ask_stores_nothing_when_the_session_does_not_end_done(point, repo, private_root, fake_reply):
    """Adversarial where: a usage-limit or crashed session stores an empty reply
    that grade later counts as an unparsed answer of the arm."""
    probe.build(point, private_root=private_root)
    fake_reply.mode("limit")

    assert probe.main(
        ["--private-root", str(private_root), "ask", point, "--arm", "none"],
        claude_cmd=fake_reply.command, repo_root=repo) == 1

    assert not list((private_root / "probes").rglob("ask-*.json"))
    assert probe.grade(point, private_root=private_root) == {}


def test_report_carried_tokens_are_the_input_over_the_floor_clamped_at_zero(private_root):
    """Adversarial where: carried tokens computed as the raw input total, a
    negative difference shown, or the floor arm given a non-zero cost."""
    probes = private_root / "probes"

    def grade_file(folder, arm, tokens, scores):
        (probes / folder).mkdir(parents=True, exist_ok=True)
        (probes / folder / f"grade-{arm}.json").write_text(json.dumps(
            {"arm": arm, "unparsed": False, "scores": scores, "input_tokens": tokens}), encoding="utf-8")

    scores = {"artifact": {"precision": 1.0, "recall": 0.5}, "recall-1": 1.0, "recall-2": 0.0}
    grade_file("one", "none", 100, scores)
    grade_file("one", "host-summary", 700, scores)
    grade_file("two", "none", 500, scores)
    grade_file("two", "host-summary", 300, scores)
    grade_file("three", "host-summary", 900, scores)

    rows = _main_rows(probe.report(private_root=private_root))

    assert rows[("host-summary", "artifact")][2:] == ["3", "0.50", "0", "300"]
    assert rows[("host-summary", "recall")][3] == "0.50"
    assert rows[("none", "artifact")][2:] == ["2", "0.50", "0", "0"]


def test_report_on_an_empty_private_root_is_the_header_alone(private_root):
    """Adversarial where: a report over a store that holds no grades raises on
    the missing folder or divides by zero."""
    lines = probe.report(private_root=private_root).splitlines()

    assert len(lines) == 2 and lines[0].startswith("| arm |")


# more implementation-revealed branches ----------------------------------------


def _plain_edit(index, path, tool="Edit"):
    return assistant(index, "", (tool, {"file_path": path, "old_string": "x", "new_string": "y"}))


def _pair(index, text="", structured=None):
    call = assistant(index, "", ("AskUserQuestion", {"questions": []}))
    result = tool_result(index + 1, text)
    if structured is not None:
        result["toolUseResult"] = {"answers": structured}
    return [call, result]


def _with_summary(*middle):
    """An edit, then `middle`, then a boundary and a summary."""
    records = [user(0, "go"), _plain_edit(1, "a.py"), tool_result(2, "ok"), *middle]
    n = len(records)
    return records + [boundary(n), summary(n + 1)]


def _new_folder(tmp_path, name="p"):
    path = tmp_path / name
    path.mkdir()
    return path


@pytest.mark.parametrize("answer", ["Flat files", "first line\nsecond line", "D:\\new\\table"])
def test_decision_answer_is_kept_verbatim_from_the_text_form(tmp_path, private_root, answer):
    """Adversarial where: the text-form answer decoded with json.loads, so a free-text
    answer holding a raw newline raises out of build and `D:\\new\\table` silently
    becomes a newline and a tab, freezing a corrupted expected answer."""
    text = f'User has answered your questions: "Which store?"="{answer}". You can now continue.'
    records = _with_summary(*_pair(3, text=text))

    _, built = build_point(_new_folder(tmp_path), records, private_root=private_root)

    assert probe_by_id(built)["decision"]["expected"] == answer


def test_recall_reads_only_error_results_strips_the_pytest_prefix_and_text_blocks(tmp_path, private_root):
    """Adversarial where: an exception line read from a successful result (a Read of
    a log), a pytest `E   ` prefix left in the literal, a `raise X: ...` source line
    taken for an exception line, or text-block content ignored."""
    blocks = [{"type": "text", "text": "E   AssertionError: assert 1 == 2"}, {"type": "text", "text": "2 failed, 1 passed"}]
    records = _with_summary(
        assistant(3, "read", ("Read", {"file_path": "log"})),
        tool_result(4, "KeyError: not-an-error\n9 failed", is_error=False),
        assistant(5, "run", ("Bash", {"command": "pytest"})),
        tool_result(6, "    raise ValueError: source line", is_error=True),
        assistant(7, "run", ("Bash", {"command": "pytest"})),
        tool_result(8, blocks, is_error=True),
    )

    _, built = build_point(_new_folder(tmp_path), records, private_root=private_root)

    recalls = [item for item in built["probes"] if item["type"] == "recall"]
    assert [item["expected"] for item in recalls] == ["AssertionError: assert 1 == 2", "2 failed"]
    assert "exception" in recalls[0]["question"] and "N failed" in recalls[1]["question"]


def test_a_lone_failed_count_is_asked_with_the_count_question(tmp_path, private_root):
    """Adversarial where: a failed-count recall literal paired with the exception-line
    question because the literal sits in the first recall slot."""
    records = _with_summary(
        assistant(3, "run", ("Bash", {"command": "pytest"})), tool_result(4, "5 failed, 1 passed", is_error=True))

    _, built = build_point(_new_folder(tmp_path), records, private_root=private_root)

    recalls = [item for item in built["probes"] if item["type"] == "recall"]
    assert [(i["id"], i["expected"]) for i in recalls] == [("recall-1", "5 failed")]
    assert "N failed" in recalls[0]["question"]


def test_continuation_ignores_thinking_tool_inputs_user_text_sidechains_and_lowercase(tmp_path, private_root):
    """Adversarial where: the continuation id taken from a thinking block, a tool
    input, a user message, a subagent record or a lowercase mention instead of the
    last id the assistant named in its visible text."""
    thinking = _record("assistant", 4, message={"role": "assistant", "model": FIXTURE_MODEL, "content": [
        {"type": "thinking", "thinking": "maybe TASK-99"}]})
    side = assistant(8, "now TASK-96")
    side["isSidechain"] = True
    records = [
        user(0, "work on TASK-97"), assistant(1, "Next is PLAN-3 then TASK-7"), _plain_edit(2, "a.py"),
        tool_result(3, "ok"), thinking, assistant(5, "", ("Bash", {"command": "echo TASK-98"})),
        user(6, "what about TASK-95"), assistant(7, "lowercase task-94 only"), side,
        boundary(9), summary(10),
    ]

    _, built = build_point(_new_folder(tmp_path), records, private_root=private_root)

    assert probe_by_id(built)["continuation"]["expected"] == "TASK-7"


def test_build_uses_the_last_usable_model_id(tmp_path, private_root):
    """Adversarial where: a `<synthetic>` or space-bearing model id of the last
    assistant record becomes the `--model` argument of every probe session."""
    odd = assistant(3, "late")
    odd["message"]["model"] = "<synthetic>"
    spaced = assistant(4, "later")
    spaced["message"]["model"] = "claude-haiku-4-5 --dangerous"

    _, built = build_point(_new_folder(tmp_path), _with_summary(odd, spaced), private_root=private_root)

    assert built["model"] == FIXTURE_MODEL


def test_a_git_file_marks_a_linked_worktree_and_is_refused(point, tmp_path):
    """Adversarial where: only a `.git` folder is recognised, so a linked worktree
    (whose `.git` is a file) takes probe files."""
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")

    with pytest.raises(probe.Refused):
        probe.build(point, private_root=linked / "root")

    assert not (linked / "root").exists()


def test_a_private_root_reaching_a_work_tree_through_dotdot_is_refused(point, repo, tmp_path):
    """Adversarial where: a `..` segment hides the work tree from a lexical parent
    check, so build writes the key into the repository."""
    sneaky = tmp_path / "elsewhere" / ".." / "repo" / "o"

    with pytest.raises(probe.Refused):
        probe.build(point, private_root=sneaky)

    assert not (repo / "o").exists()


def test_concurrent_builds_of_one_point_freeze_exactly_one_key(point, private_root):
    """Adversarial where: an exists-then-write check with no exclusive create, so
    simultaneous builds both pass the check and the later one replaces the key."""
    gate = threading.Barrier(8)

    def attempt(_):
        gate.wait()
        try:
            probe.build(point, private_root=private_root)
            return "built"
        except probe.AlreadyFrozen:
            return "refused"

    with ThreadPoolExecutor(8) as pool:
        outcomes = list(pool.map(attempt, range(8)))

    assert (outcomes.count("built"), outcomes.count("refused")) == (1, 7)


def test_cli_turns_a_missing_transcript_and_unbuilt_points_into_exit_two(
        tmp_path, repo, private_root, fake_reply, capsys):
    """Adversarial where: a point naming a transcript that no longer exists raises a
    traceback instead of exit status 2, or ask and grade of an unbuilt point do."""
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", _with_summary())
    (found,) = probe.find(folder)
    root = str(private_root)

    codes = [
        probe.main(["--private-root", root, "build", f"{folder / 'gone.jsonl'}#3"]),
        probe.main(["--private-root", root, "grade", found["point"]]),
        probe.main(["--private-root", root, "ask", found["point"], "--arm", "none"],
                   claude_cmd=fake_reply.command, repo_root=repo),
        probe.main(["find", "--project-dir", str(folder / "nope")]),
    ]

    assert codes == [2, 2, 2, 2]
    assert "Traceback" not in capsys.readouterr().err
    assert fake_reply.calls() == []


def test_ask_carries_the_first_non_blank_summary_after_its_boundary_and_nothing_else(
        tmp_path, repo, private_root, fake_reply):
    """Adversarial where: a blank summary, a subagent's summary or ordinary text after
    the boundary taken as the carried text, or block-list summary content dropped."""
    blocks = _record("user", 7, message={"role": "user", "content": [
        {"type": "text", "text": "REALSUMMARY part one"}, {"type": "text", "text": "part two"}]},
        isCompactSummary=True)
    side = summary(5, "SIDESUMMARY")
    side["isSidechain"] = True
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", [
        user(0, "go"), _plain_edit(1, "a.py"), boundary(2),
        user(3, "AFTERTEXT go on"), summary(4, "   "), side, blocks])
    (found,) = probe.find(folder)
    probe.build(found["point"], private_root=private_root)
    fake_reply.reply("{}")

    _ask(found["point"], "host-summary", repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert "REALSUMMARY part one\npart two" in call["stdin"]
    for absent in ("SIDESUMMARY", "AFTERTEXT"):
        assert absent not in call["stdin"]


def test_a_transcript_without_a_summary_fails_the_host_arm_and_still_runs_the_floor(
        tmp_path, repo, private_root, fake_reply):
    """Adversarial where: the host arm sending its questions with nothing carried, or
    the floor arm requiring a summary it never uses."""
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", [user(0, "go"), _plain_edit(1, "a.py"), boundary(2), user(3, "next")])
    (found,) = probe.find(folder)
    probe.build(found["point"], private_root=private_root)
    fake_reply.reply("{}")

    with pytest.raises(probe.NoSummary):
        _ask(found["point"], "host-summary", repo, private_root, fake_reply)
    assert probe.main(["--private-root", str(private_root), "ask", found["point"], "--arm", "host-summary"],
                      claude_cmd=fake_reply.command, repo_root=repo) == 2
    assert fake_reply.calls() == []
    _ask(found["point"], "none", repo, private_root, fake_reply)

    assert len(fake_reply.calls()) == 1


def test_crlf_bom_invalid_bytes_and_non_ascii_text_survive_build_ask_and_grade(
        tmp_path, repo, private_root, fake_reply):
    """Adversarial where: CRLF endings or a BOM shifting the boundary index, invalid
    UTF-8 in an unrelated line aborting the read, or a non-ASCII path or question
    mangled on its way into the key, the prompt or the grade."""
    path_text = "src/café/日本.py"
    records = [
        user(0, "go"), _plain_edit(1, path_text), tool_result(2, "ok"),
        *_pair(3, structured={"Qual armazenamento café?": "Só arquivos"}),
        boundary(5), summary(6, "SUMTEXT café"),
    ]
    folder = _new_folder(tmp_path)
    body = "\r\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\r\n"
    raw = b"\xef\xbb\xbf" + body.encode("utf-8").replace(b'"go"', b'"g\xffo"')
    (folder / "t.jsonl").write_bytes(raw)
    (found,) = probe.find(folder)
    assert found["boundary"] == 5

    built = probe.build(found["point"], private_root=private_root)

    assert probe_by_id(built)["artifact"]["expected"] == [path_text]
    key_file = probe._point_dir(found["point"], private_root) / "key.json"
    assert json.loads(key_file.read_bytes().decode("utf-8"))["probes"] == built["probes"]
    fake_reply.reply(json.dumps({"artifact": ["./src/café/日本.py"], "decision": "Só arquivos"}, ensure_ascii=False))
    _ask(found["point"], "host-summary", repo, private_root, fake_reply)
    (call,) = fake_reply.calls()
    assert "Qual armazenamento café?" in call["stdin"] and "SUMTEXT café" in call["stdin"]
    graded = probe.grade(found["point"], private_root=private_root)["host-summary"]
    assert graded["scores"]["artifact"] == {"precision": 1.0, "recall": 1.0}
    assert graded["scores"]["decision"] == 1.0


@pytest.mark.parametrize("value, expected, precision, recall", [
    (["src/./app//main.py/"], ["src/app/main.py"], 1.0, 1.0),
    (["src/app/../app/main.py"], ["src/app/main.py"], 1.0, 1.0),
    (["a.py"], ["./a.py", "a.py"], 1.0, 1.0),
    (["/a.py"], ["a.py"], 0.0, 0.0),
    (["../a.py"], ["a.py"], 0.0, 0.0),
    (["a.py", "b.py"], ["a.py", "b.py", "c.py", "d.py"], 1.0, 0.5),
])
def test_artifact_scoring_identity_table(value, expected, precision, recall):
    """Adversarial where: dot segments, a doubled slash, a trailing slash, an
    expected side that keeps a leading `./`, or an absolute or parent-relative
    lookalike changing which paths count as the same file."""
    assert probe._score_artifact(value, expected) == {"precision": precision, "recall": recall}


@pytest.mark.parametrize("value, expected, whole, score", [
    ("The  LOG said\n bad frame width 17", "Bad frame width 17", False, 1.0),
    ("C++ it is", "C++", True, 1.0),
    ("só ARQUIVOS", "Só arquivos", True, 1.0),
    ("(Recommended) Flat files", "(Recommended) Flat files", True, 1.0),
    ("anything", "", True, 0.0),
    ("TASK-12", "TASK-12", False, 1.0),
])
def test_text_scoring_normalization_table(value, expected, whole, score):
    """Adversarial where: whitespace or case folding missing, a pattern built from an
    option holding regex metacharacters (`C++`, parentheses) raising or mismatching,
    and an empty expected answer matching everything."""
    assert probe._score_text(value, expected, whole) == score


@pytest.mark.parametrize("value, expected, score", [
    ("TASK-123", "TASK-12", 0.0),
    ("TASK-1", "TASK-12", 0.0),
    ("PLAN-12", "TASK-12", 0.0),
    ("TASK 12", "TASK-12", 0.0),
    ("It is TASK-12.", "TASK-12", 1.0),
    (["TASK-12"], "TASK-12", 0.0),
])
def test_continuation_scoring_table(value, expected, score):
    """Adversarial where: an id matched as a prefix or inside a longer number, the
    same number under another prefix, or a non-string value accepted."""
    assert probe._score_id(value, expected) == score


def test_recall_count_is_not_credited_for_a_different_count_sharing_its_digits():
    """Adversarial where: the substring grader credits `13 failed` for the frozen
    literal `3 failed`, so a wrong count earns full marks on the likeliest recall
    literal."""
    assert probe._score_text("13 failed", "3 failed", False) == 0.0


# latest-stretch artifact, shortened error quotes, pooled state, paired intervals ----

TWO_BOUNDARIES = Path(__file__).resolve().parent / "fixtures" / "probe-two-boundaries.jsonl"
FIRST_EDITS = ["src/alpha.py", "src/beta.py"]
ALL_EDITS = ["src/alpha.py", "src/beta.py", "src/gamma.py", "docs/delta.md"]
RECENT_EDITS = ["src/gamma.py", "docs/delta.md", "src/alpha.py"]
FIXTURE_STRINGS = (
    "alpha.py", "beta.py", "gamma.py", "delta.md", "epsilon", "zeta", "work/sample", "widgets",
    "FIXSUMMARY", "claude-haiku",
)


@pytest.fixture
def two_points(tmp_path):
    """The two boundary points of the two-boundary fixture, earlier one first."""
    folder = tmp_path / "two-boundaries"
    folder.mkdir()
    shutil.copy(TWO_BOUNDARIES, folder / "probe-two-boundaries.jsonl")
    found = probe.find(folder)
    assert [item["boundary"] for item in found] == [5, 15]
    return [item["point"] for item in found]


def _store_reply(point, private_root, arm, reply):
    """Store the raw reply of `arm` the way `ask` stores it, without a session."""
    text = reply if isinstance(reply, str) else json.dumps(reply)
    stored = {"point": point, "arm": arm, "reply": text, "tokens": {}}
    topics.write_json(probe._point_dir(point, private_root) / f"ask-{arm}.json", stored)


def _score_value(score):
    """The number of a score: an artifact-style score reads as its recall."""
    return score["recall"] if isinstance(score, dict) else score


def _write_grade(private_root, folder, arm, scores):
    target = private_root / "probes" / folder
    target.mkdir(parents=True, exist_ok=True)
    topics.write_json(target / f"grade-{arm}.json", {
        "point": folder, "arm": arm, "unparsed": False, "scores": scores, "input_tokens": 0})


def _table_blocks(text):
    """The markdown tables of `text`, each a list of its lines, first table first."""
    blocks, current = [], []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _paired_row(text, kind):
    """(cells, line) of the row for probe type `kind` in a table after the first one."""
    for block in _table_blocks(text)[1:]:
        for line in block:
            if kind in _cells(line):
                return _cells(line), line
    raise AssertionError(f"no paired row for {kind}:\n{text}")


def _decimals(line):
    return [float(number) for number in re.findall(r"[-+]?\d+\.\d+", line)]


def _main_rows(text):
    return {(_cells(line)[0], _cells(line)[1]): _cells(line) for line in _table_blocks(text)[0][2:]}


# build: expected_recent

def test_build_stores_the_edits_made_since_the_previous_boundary(two_points, private_root):
    """Adversarial where: expected_recent taken as the whole trail, as only the paths
    new since the earlier boundary (dropping a path edited again), as including a
    Read path or an edit after the boundary, or as cut by an earlier boundary only
    when one exists (the first point must keep every edit)."""
    first = probe_by_id(probe.build(two_points[0], private_root=private_root))["artifact"]
    second_key = probe.build(two_points[1], private_root=private_root)
    second = probe_by_id(second_key)["artifact"]

    assert sorted(first["expected"]) == sorted(FIRST_EDITS)
    assert sorted(first["expected_recent"]) == sorted(FIRST_EDITS)
    assert sorted(second["expected"]) == sorted(ALL_EDITS)
    assert sorted(second["expected_recent"]) == sorted(RECENT_EDITS)
    stored = topics.read_json(probe._point_dir(two_points[1], private_root) / "key.json")
    assert sorted(probe_by_id(stored)["artifact"]["expected_recent"]) == sorted(RECENT_EDITS)
    assert "zeta" not in json.dumps(second_key) and "epsilon" not in json.dumps(second_key)


def _three_boundaries():
    return [
        user(0, "go"), _plain_edit(1, "a.py"), tool_result(2, "ok"), boundary(3), summary(4),
        _plain_edit(5, "b.py"), tool_result(6, "ok"), boundary(7), summary(8),
        _plain_edit(9, "c.py", "Write"), tool_result(10, "ok"), boundary(11), summary(12),
    ]


def _sidechain_boundary_between_edits():
    marker = boundary(2)
    marker["isSidechain"] = True
    return [user(0, "go"), _plain_edit(1, "a.py"), marker, _plain_edit(3, "b.py"), tool_result(4, "ok"),
            boundary(5), summary(6)]


def _quoted_marker_between_edits():
    quote = 'log line {"type": "system", "subtype": "compact_boundary"} was printed'
    return [user(0, "go"), _plain_edit(1, "a.py"), user(2, quote), _plain_edit(3, "b.py"),
            tool_result(4, "ok"), boundary(5), summary(6)]


@pytest.mark.parametrize("name, records, boundary_index, expected, recent", [
    ("middle of three boundaries", _three_boundaries(), 7, ["a.py", "b.py"], ["b.py"]),
    ("last of three boundaries", _three_boundaries(), 11, ["a.py", "b.py", "c.py"], ["c.py"]),
    ("sidechain boundary is another side", _sidechain_boundary_between_edits(), 5, ["a.py", "b.py"],
     ["a.py", "b.py"]),
    ("quoted marker is no boundary", _quoted_marker_between_edits(), 5, ["a.py", "b.py"], ["a.py", "b.py"]),
])
def test_recent_window_starts_after_the_last_earlier_boundary_on_the_points_side(
        tmp_path, private_root, name, records, boundary_index, expected, recent):
    """Adversarial where: the window cut at the first boundary instead of the last
    earlier one, cut by a subagent's boundary or by text that quotes the marker, or
    one that keeps the edits made before the cut."""
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", records)
    (found,) = [item for item in probe.find(folder) if item["boundary"] == boundary_index]

    artifact = probe_by_id(probe.build(found["point"], private_root=private_root))["artifact"]

    assert sorted(artifact["expected"]) == sorted(expected), name
    assert sorted(artifact["expected_recent"]) == sorted(recent), name


def test_build_on_a_key_without_expected_recent_adds_it_and_changes_nothing_else(two_points, private_root):
    """Adversarial where: a migrating build that re-derives the whole key (and so
    replaces the frozen questions, model or expected paths the stored replies were
    graded against), rewrites stored replies, or leaves the key open to a further
    build once the field is back."""
    probe.build(two_points[1], private_root=private_root)
    folder = probe._point_dir(two_points[1], private_root)
    legacy = topics.read_json(folder / "key.json")
    artifact = probe_by_id(legacy)["artifact"]
    del artifact["expected_recent"]
    artifact["question"] = "FROZEN WORDING of the artifact question"
    artifact["expected"] = ["src/alpha.py", "docs/delta.md"]
    legacy["model"] = "claude-opus-4-1"
    topics.write_json(folder / "key.json", legacy)
    _store_reply(two_points[1], private_root, "host-summary", {"artifact": ["src/alpha.py"]})
    reply_before = (folder / "ask-host-summary.json").read_bytes()

    probe.build(two_points[1], private_root=private_root)

    migrated = topics.read_json(folder / "key.json")
    assert sorted(probe_by_id(migrated)["artifact"]["expected_recent"]) == sorted(RECENT_EDITS)
    del probe_by_id(migrated)["artifact"]["expected_recent"]
    assert migrated == legacy
    assert (folder / "ask-host-summary.json").read_bytes() == reply_before
    with pytest.raises(probe.AlreadyFrozen):
        probe.build(two_points[1], private_root=private_root)


# grade: artifact-recent

def test_grade_scores_the_one_reply_against_the_whole_trail_and_against_the_recent_edits(
        two_points, private_root):
    """Adversarial where: artifact-recent scored against the whole trail (the same
    number as artifact), against the paths new since the boundary, or a reply naming
    only an old edit credited on the latest stretch."""
    probe.build(two_points[1], private_root=private_root)
    _store_reply(two_points[1], private_root, "host-summary", {"artifact": RECENT_EDITS})
    _store_reply(two_points[1], private_root, "none", {"artifact": ["src/beta.py"]})

    graded = probe.grade(two_points[1], private_root=private_root)

    host, floor = graded["host-summary"]["scores"], graded["none"]["scores"]
    assert _score_value(host["artifact-recent"]) == 1.0
    assert host["artifact"]["recall"] == 0.75 and host["artifact"]["precision"] == 1.0
    assert _score_value(floor["artifact-recent"]) == 0.0
    assert floor["artifact"]["recall"] == 0.25


def test_a_point_with_no_edit_since_the_earlier_boundary_has_no_artifact_recent_score(
        tmp_path, private_root):
    """Adversarial where: an empty recent set scored as a perfect or a zero score
    (0/0 reported as 1.0 or 0.0), so the arm is rewarded or punished for a probe the
    point never had; the artifact score must stay."""
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", [
        user(0, "go"), _plain_edit(1, "a.py"), tool_result(2, "ok"), boundary(3), summary(4),
        user(5, "next"), assistant(6, "reading", ("Read", {"file_path": "a.py"})), tool_result(7, "ok"),
        boundary(8), summary(9)])
    (found,) = [item for item in probe.find(folder) if item["boundary"] == 8]
    built = probe_by_id(probe.build(found["point"], private_root=private_root))["artifact"]
    _store_reply(found["point"], private_root, "host-summary", {"artifact": ["a.py"]})

    graded = probe.grade(found["point"], private_root=private_root)["host-summary"]

    assert not built.get("expected_recent")
    assert graded["scores"]["artifact"] == {"precision": 1.0, "recall": 1.0}
    assert "artifact-recent" not in graded["scores"]
    assert "artifact-recent" not in probe.report(private_root=private_root)


def test_a_key_frozen_before_expected_recent_existed_still_grades_without_that_score(
        two_points, private_root):
    """Adversarial where: a stored key without the field makes grade raise or invent
    a score, so the pilot's replies cannot be regraded."""
    probe.build(two_points[1], private_root=private_root)
    folder = probe._point_dir(two_points[1], private_root)
    legacy = topics.read_json(folder / "key.json")
    del probe_by_id(legacy)["artifact"]["expected_recent"]
    topics.write_json(folder / "key.json", legacy)
    _store_reply(two_points[1], private_root, "host-summary", {"artifact": ALL_EDITS})

    graded = probe.grade(two_points[1], private_root=private_root)["host-summary"]

    assert graded["scores"]["artifact"] == {"precision": 1.0, "recall": 1.0}
    assert "artifact-recent" not in graded["scores"]


# grade: shortened error quote

NAMED = "ValueError: the point is not a compaction boundary, line 12"


@pytest.mark.parametrize("literal, reply, score", [
    (NAMED, "ValueError: the point is not a compaction boundary", 1.0),
    (NAMED, NAMED, 1.0),
    (NAMED, "A ValueError was raised because the point is not a compaction boundary", 1.0),
    (NAMED, "ValueError", 0.0),
    (NAMED, "the point is not a compaction boundary", 0.0),
    (NAMED, "NotValueError: the point is not a compaction boundary", 0.0),
    (NAMED, "KeyError: the point is not a compaction boundary", 0.0),
    (NAMED, "ValueError: the point is not a compaction", 0.0),
    ("KeyError: ghost", "KeyError: ghost", 1.0),
    ("KeyError: ghost", "KeyError", 0.0),
    ("AttributeError: no attribute", "AttributeError: no", 0.0),
    ("ValueError: pre-built frame", "ValueError: pre-built frame", 1.0),
    ("ValueError: pre-built frame", "ValueError: pre", 0.0),
    ("ValueError: foo(bar)", "ValueError: foo(bar)", 1.0),
    ("ValueError: foo(bar)", "ValueError: foo", 0.0),
    ("TypeError: expected int (got str)", "TypeError: expected int", 1.0),
    ("RuntimeError: stalled - giving up", "RuntimeError: stalled", 1.0),
    ("OSError: cannot open: file x", "OSError: cannot open", 1.0),
    (r"PermissionError: C:\data\x denied", "PermissionError: C", 0.0),
    (r"PermissionError: C:\data\x denied", r"PermissionError: C:\data\x denied", 1.0),
    ("KeyError: a:b, c", "KeyError: a:b", 1.0),
    ("KeyError: bad key; retry later", "KeyError: bad key", 1.0),
    ("ValueError: a, b; c", "ValueError: a", 1.0),
    ("KeyError: a+b*c", "KeyError: a+b*c", 1.0),
    ("KeyError: a+b*c", "KeyError: aabbc", 0.0),
    ("3 failed", "3 failed, 2 passed", 1.0),
    ("3 failed", "13 failed", 0.0),
    ("3 failed", "3", 0.0),
])
def test_recall_scores_the_error_name_and_the_messages_first_clause(
        tmp_path, private_root, literal, reply, score):
    """Adversarial where: a quote that stops short of the last clause scored 0 (the
    pilot's miss), the name or the message alone credited, a name that is only the
    tail of a longer word credited, a separator that is not one (`-` without
    spaces, `(` without a space) cutting the message early, a message without
    separator accepted by a prefix, regex characters in the message mismatching,
    or the `N failed` literal changed by the new rule."""
    text = f"{literal}, 1 passed in 0.10s" if literal.endswith(" failed") else literal
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", [
        user(0, "run it"), assistant(1, "running", ("Bash", {"command": "pytest"})),
        tool_result(2, text, is_error=True), boundary(3), summary(4)])
    (found,) = probe.find(folder)
    built = probe.build(found["point"], private_root=private_root)
    assert [item["expected"] for item in built["probes"]] == [literal]
    _store_reply(found["point"], private_root, "host-summary", {"recall-1": reply})

    graded = probe.grade(found["point"], private_root=private_root)["host-summary"]

    assert graded["scores"]["recall-1"] == score


# report: rows, state, intervals

def _state_point(tmp_path, private_root, name, middle, reply):
    folder = _new_folder(tmp_path, name)
    records = [user(0, "go"), _plain_edit(1, "a.py"), tool_result(2, "ok"), *middle]
    records += [boundary(len(records)), summary(len(records) + 1)]
    write_transcript(folder, "t.jsonl", records)
    (found,) = probe.find(folder)
    built = probe.build(found["point"], private_root=private_root)
    _store_reply(found["point"], private_root, "host-summary", reply)
    probe.grade(found["point"], private_root=private_root)
    return built


def test_state_score_pools_recall_continuation_and_decision_per_point(tmp_path, private_root):
    """Adversarial where: the state of a point averaged over its probes (a recall
    pair counted twice) instead of over the three types, a point with no recall,
    continuation or decision probe given a state of 0 or 1, or the artifact score
    mixed in."""
    decided = [assistant(3, "Next is TASK-5."), *_pair(4, structured={"Which storage?": "Flat files"})]
    _state_point(tmp_path, private_root, "a", decided, {"continuation": "TASK-5", "decision": "Other"})
    recalled = [
        assistant(3, "Now on TASK-8."), assistant(4, "", ("Bash", {"command": "pytest"})),
        tool_result(5, "KeyError: alpha9\n3 failed, 1 passed", is_error=True),
        *_pair(6, structured={"Which storage?": "Flat files"})]
    _state_point(tmp_path, private_root, "c", recalled, {
        "recall-1": "KeyError: alpha9", "recall-2": "9 failed", "continuation": "TASK-8",
        "decision": "Flat files"})
    _state_point(tmp_path, private_root, "b", [], {"artifact": ["a.py"]})

    rows = _main_rows(probe.report(private_root=private_root))

    assert rows[("host-summary", "state")][2:4] == ["2", "0.67"]
    assert rows[("host-summary", "artifact")][2] == "3"
    assert rows[("host-summary", "continuation")][2] == "2"


def test_report_rows_keep_artifact_and_artifact_recent_apart(two_points, private_root):
    """Adversarial where: artifact-recent folded into the artifact row (its probe id
    shares the `artifact` prefix) so both rows read the same, or a point with no
    state probe given a state row."""
    probe.build(two_points[1], private_root=private_root)
    _store_reply(two_points[1], private_root, "host-summary", {"artifact": RECENT_EDITS})
    _store_reply(two_points[1], private_root, "none", {"artifact": ["src/beta.py"]})
    probe.grade(two_points[1], private_root=private_root)

    rows = _main_rows(probe.report(private_root=private_root))

    assert rows[("host-summary", "artifact")][2:4] == ["1", "0.75"]
    assert rows[("host-summary", "artifact-recent")][2:4] == ["1", "1.00"]
    assert rows[("none", "artifact")][2:4] == ["1", "0.25"]
    assert rows[("none", "artifact-recent")][2:4] == ["1", "0.00"]
    assert ("host-summary", "state") not in rows


def _recall_pair(host, arm):
    return ({"recall-1": host[0], "recall-2": host[1]}, {"recall-1": arm[0], "recall-2": arm[1]})


def test_paired_interval_lies_above_zero_when_the_arm_wins_every_point(private_root):
    """Adversarial where: an interval that includes 0 for 12 points that all favour
    the arm, a sign flipped (host minus arm), or a count and mean taken over
    something other than the 12 points graded in both arms."""
    pairs = [_recall_pair((0.0, 0.0), (1.0, 1.0 if number < 6 else 0.0)) for number in range(12)]
    for number, (host, arm) in enumerate(pairs):
        _write_grade(private_root, f"point-{number:02d}", "host-summary", host)
        _write_grade(private_root, f"point-{number:02d}", "none", arm)

    cells, line = _paired_row(probe.report(private_root=private_root), "recall")

    assert "12" in cells and "too few points" not in line
    numbers = _decimals(line)
    assert len(numbers) >= 3 and all(number > 0 for number in numbers)
    assert any(abs(number - 0.75) < 1e-9 for number in numbers)


def test_paired_interval_spans_zero_on_a_balanced_split_and_repeats_exactly(private_root):
    """Adversarial where: an interval that is the min and max of the differences, the
    point estimate alone, or one that changes between two runs of the same input
    (an unseeded generator)."""
    for number in range(12):
        host, arm = (1.0, 0.0) if number % 2 else (0.0, 1.0)
        _write_grade(private_root, f"point-{number:02d}", "host-summary", {"continuation": host})
        _write_grade(private_root, f"point-{number:02d}", "none", {"continuation": arm})

    first = probe.report(private_root=private_root)
    second = probe.report(private_root=private_root)

    assert first == second
    numbers = sorted(_decimals(_paired_row(first, "continuation")[1]))
    assert len(numbers) >= 3
    assert -0.9 < numbers[0] <= -0.4 and 0.4 <= numbers[-1] < 0.9
    assert any(abs(number) < 1e-9 for number in numbers)


@pytest.mark.parametrize("paired", [9, 10])
def test_paired_interval_needs_ten_points_graded_in_both_arms(private_root, paired):
    """Adversarial where: the too-few-points cut at 9 or 11 instead of 10, a point
    graded in one arm only (or lacking the probe type in one arm) counted as a pair,
    or a mean over the arm's own points instead of the paired differences (the arm
    carries 4 extra points scoring 0, so a mean of means reads 0.71 rather than 1.00)."""
    for number in range(paired):
        _write_grade(private_root, f"paired-{number:02d}", "host-summary", {"continuation": 0.0})
        _write_grade(private_root, f"paired-{number:02d}", "none", {"continuation": 1.0})
    for number in range(4):
        _write_grade(private_root, f"arm-only-{number}", "none", {"continuation": 0.0})
    for number in range(3):
        _write_grade(private_root, f"host-only-{number}", "host-summary", {"continuation": 1.0})
    for number in range(2):
        _write_grade(private_root, f"lacking-{number}", "host-summary", {"continuation": 1.0})
        _write_grade(private_root, f"lacking-{number}", "none", {"recall-1": 1.0})

    cells, line = _paired_row(probe.report(private_root=private_root), "continuation")

    assert str(paired) in cells
    if paired < 10:
        assert "too few points" in line
    else:
        assert "too few points" not in line
        numbers = _decimals(line)
        assert len(numbers) >= 3 and all(abs(number - 1.0) < 1e-9 for number in numbers)


def test_one_paired_table_per_arm_other_than_host_summary(private_root):
    """Adversarial where: a paired table for the reference arm against itself, or none
    for the other arm."""
    _write_grade(private_root, "only", "host-summary", {"continuation": 1.0})
    alone = probe.report(private_root=private_root)
    _write_grade(private_root, "only", "none", {"continuation": 0.0})

    both = probe.report(private_root=private_root)

    assert len(_table_blocks(alone)) == 1
    assert len(_table_blocks(both)) == 2
    assert _cells(_table_blocks(both)[0][0])[:2] == ["arm", "probe"]


def test_report_with_paired_tables_holds_no_fixture_path_prompt_or_answer(two_points, private_root, tmp_path):
    """Adversarial where: the new tables print a path, a prompt, a summary line, a
    model name, the point string or a quoted answer from the two-boundary fixture."""
    for point in two_points:
        probe.build(point, private_root=private_root)
        _store_reply(point, private_root, "host-summary", {"artifact": ALL_EDITS})
        _store_reply(point, private_root, "none", {"artifact": ["src/beta.py"], "decision": "ANSWERLEAK"})
        probe.grade(point, private_root=private_root)

    text = probe.report(private_root=private_root)

    assert len(_table_blocks(text)) >= 2
    for secret in (*FIXTURE_STRINGS, str(tmp_path), "ANSWERLEAK", *two_points):
        assert secret not in text


# implementation-revealed branches of the grading rules ----------------------------

WINDOWS_ERROR = r"PermissionError: C:\data\x denied"


@pytest.mark.parametrize("literal, reply, score", [
    ("KeyError: , tail", "KeyError: , tail", 1.0),
    ("KeyError: , tail", "KeyError", 0.0),
    ("KeyError: ;; x", "KeyError: ;; x", 1.0),
    (WINDOWS_ERROR, WINDOWS_ERROR, 1.0),
    ("KeyError: [a-z]+ here", "KeyError: a here", 0.0),
    ("KeyError: [a-z]+ here", "KeyError: [a-z]+ here", 1.0),
    ("ValueError: x", "builtins.ValueError: x", 1.0),
    ("ValueError: x", "ValueErrors: x", 0.0),
    ("ValueError: x y", "VALUEERROR:   X\n  Y", 1.0),
    ("ValueError: a, b; c - d (e)", "ValueError: a", 1.0),
    ("ValueError: a-b", "ValueError: a", 0.0),
    ("ValueError: a(b) c", "ValueError: a", 0.0),
    ("ValueError: a (b) c", "ValueError: a", 1.0),
    ("ValueError: first", "Something else failed first. Later a ValueError appeared.", 1.0),
    ("ValueError: first", "ValueError only", 0.0),
])
def test_error_scoring_separator_edges_metacharacters_and_word_boundaries(
        tmp_path, private_root, literal, reply, score):
    """Adversarial where: a message that opens with a separator leaving an empty first
    clause (crash, or credit for the name alone), a regex character in the message
    or a backslash path read as a pattern, a name matched inside a longer word,
    case or whitespace differences refused, a `(` or `-` without its space cutting
    the message early, or the name and the clause credited when only one of them
    is in the reply."""
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", [
        user(0, "run it"), assistant(1, "running", ("Bash", {"command": "pytest"})),
        tool_result(2, literal, is_error=True), boundary(3), summary(4)])
    (found,) = probe.find(folder)
    built = probe.build(found["point"], private_root=private_root)
    assert [item["expected"] for item in built["probes"]] == [literal]
    _store_reply(found["point"], private_root, "host-summary", {"recall-1": reply})

    graded = probe.grade(found["point"], private_root=private_root)["host-summary"]

    assert graded["scores"]["recall-1"] == score


def test_state_score_over_the_types_a_point_has(tmp_path):
    """Adversarial where: the pooled score averaged over the three types when a point
    holds only some of them (absent types counted as 0), a recall pair counted once
    per probe, artifact-recent or artifact mixed in, or a point of only artifact
    probes given a state row."""
    artifact = {"precision": 1.0, "recall": 1.0}
    rows = {
        "only-recall": ({"recall-1": 1.0, "recall-2": 0.0}, "0.50"),
        "only-decision": ({"decision": 1.0}, "1.00"),
        "recall-pair-counts-once": (
            {"recall-1": 1.0, "recall-2": 1.0, "continuation": 0.0, "decision": 0.0,
             "artifact": artifact, "artifact-recent": 1.0}, "0.33"),
        "none-of-the-three": ({"artifact": artifact, "artifact-recent": 1.0}, None),
    }
    for name, (scores, state) in rows.items():
        root = tmp_path / name
        _write_grade(root, "point", "host-summary", scores)

        table = _main_rows(probe.report(private_root=root))

        if state is None:
            assert ("host-summary", "state") not in table, name
        else:
            assert table[("host-summary", "state")][2:4] == ["1", state], name


def _paired_for(tmp_path, name, differences):
    """Report text where `none` minus `host-summary` on `continuation` is each of
    `differences`, one point apiece."""
    root = tmp_path / name
    for number, difference in enumerate(differences):
        host = 1.0 if difference < 0 else 0.0
        _write_grade(root, f"point-{number:02d}", "host-summary", {"continuation": host})
        _write_grade(root, f"point-{number:02d}", "none", {"continuation": host + difference})
    return probe.report(private_root=root)


def test_interval_at_exactly_ten_pairs_keeps_its_order_and_its_sign(tmp_path):
    """Adversarial where: the first interval printed at the 10-pair boundary has its
    ends swapped, sits off the mean, or reads above 0 when the arm loses every
    point, or a constant difference widens into a spread."""
    lost = _paired_for(tmp_path, "lost", [-1.0] * 10)
    mixed = _paired_for(tmp_path, "mixed", [1.0] * 6 + [0.0] * 4)

    lost_cells, lost_line = _paired_row(lost, "continuation")
    mixed_cells, mixed_line = _paired_row(mixed, "continuation")

    assert "10" in lost_cells and "too few points" not in lost_line
    assert all(abs(number + 1.0) < 1e-9 for number in _decimals(lost_line))
    mean, low, high = _decimals(mixed_line)[-3:]
    assert "10" in mixed_cells
    assert abs(mean - 0.6) < 1e-9 and 0.0 <= low <= mean <= high <= 1.0


def test_a_probe_type_only_one_arm_holds_gets_no_paired_row(tmp_path):
    """Adversarial where: a probe type present in the arm and missing from
    host-summary printed as a paired row from a default of 0, so a type with no
    pairs reads as a difference (`state` pairs through continuation and stays)."""
    root = tmp_path / "root"
    for number in range(11):
        _write_grade(root, f"point-{number:02d}", "host-summary", {"continuation": 1.0})
        _write_grade(root, f"point-{number:02d}", "none", {"continuation": 0.0, "decision": 1.0})

    text = probe.report(private_root=root)

    paired = [line for block in _table_blocks(text)[1:] for line in block]
    assert any("continuation" in _cells(line) for line in paired)
    assert not any("decision" in _cells(line) for line in paired)


# migrating build ------------------------------------------------------------------


def test_migrating_build_of_a_point_whose_transcript_is_gone_fails_and_keeps_the_key(
        two_points, private_root):
    """Adversarial where: the migration, which re-reads the transcript, truncates or
    rewrites the stored key when the transcript can no longer be read, or lets the
    failure escape the command line as a traceback instead of exit 2."""
    probe.build(two_points[1], private_root=private_root)
    folder = probe._point_dir(two_points[1], private_root)
    legacy = topics.read_json(folder / "key.json")
    del probe_by_id(legacy)["artifact"]["expected_recent"]
    topics.write_json(folder / "key.json", legacy)
    before = (folder / "key.json").read_bytes()
    Path(two_points[1].rpartition("#")[0]).unlink()

    code = probe.main(["--private-root", str(private_root), "build", two_points[1]])

    assert code == 2
    assert (folder / "key.json").read_bytes() == before


def test_build_with_no_artifact_probe_cannot_be_migrated_and_keeps_the_key(tmp_path, private_root):
    """Adversarial where: the migration invents an artifact probe, or rewrites the
    key, for a point that never had edits (its key holds no artifact probe, so there
    is nothing to add)."""
    folder = _new_folder(tmp_path)
    write_transcript(folder, "t.jsonl", [
        user(0, "work on TASK-3"), assistant(1, "On TASK-3 now."), boundary(2), summary(3)])
    (found,) = probe.find(folder)
    built = probe.build(found["point"], private_root=private_root)
    path = probe._point_dir(found["point"], private_root) / "key.json"
    before = path.read_bytes()

    assert [item["type"] for item in built["probes"]] == ["continuation"]
    with pytest.raises(probe.AlreadyFrozen):
        probe.build(found["point"], private_root=private_root)
    assert path.read_bytes() == before


def test_recent_window_of_a_subagent_point_is_cut_by_its_own_earlier_boundary_only(
        tmp_path, private_root):
    """Adversarial where: the recent window of a subagent transcript ignores the
    subagent's earlier boundary (every record is a sidechain record, so a side test
    that drops sidechain boundaries keeps them all) or is cut by a main-side
    boundary written into the same file."""
    folder = tmp_path / "p"
    (folder / "sess" / "subagents").mkdir(parents=True)

    def side(record):
        record["isSidechain"] = True
        return record

    records = [
        side(user(0, "go")), side(_plain_edit(1, "old.py")), side(tool_result(2, "ok")),
        side(boundary(3)), side(summary(4)),
        side(_plain_edit(5, "mid.py")),
        boundary(6),
        side(_plain_edit(7, "new.py")), side(tool_result(8, "ok")),
        side(boundary(9)), side(summary(10)),
    ]
    write_transcript(folder / "sess" / "subagents", "agent-x.jsonl", records)
    write_transcript(folder, "sess.jsonl", [user(0, "hi"), assistant(1, "hello")])
    (found,) = [item for item in probe.find(folder) if item["boundary"] == 9]

    artifact = probe_by_id(probe.build(found["point"], private_root=private_root))["artifact"]

    assert sorted(artifact["expected"]) == ["mid.py", "new.py", "old.py"]
    assert sorted(artifact["expected_recent"]) == ["mid.py", "new.py"]


# mechanical and compass arms --------------------------------------------------
#
# These tests run the real `plugin/cli/compass session-state` (through a copy of
# plugin/cli committed in a temporary repository, which `ask` receives as its
# repo_root) over a temporary git repository holding a committed
# `.compass/active.md`. The fake `claude` is the only stand-in.

import os  # noqa: E402
import subprocess  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

PLUGIN_CLI = Path(__file__).resolve().parents[3] / "plugin" / "cli"
BLOCK_TITLE = "Compass session state"
STATE_SUMMARY = "ZQCARRIEDSUMMARY"
OPEN_TASK = "ZQOPENTASK"
SIDE_TASK = "ZQSIDETASK"
LATER_TASK = "ZQLATERTASK"
ORPHAN_TASK = "ZQORPHANTASK"
EDITED_PATH = "src/zq_edited.py"
LATER_EDIT = "src/zq_after.py"
UNCOMMITTED_FILE = "zq-uncommitted.txt"


def _utc(hour, minute=0, second=0, micro=0):
    return datetime(2026, 2, 1, hour, minute, second, micro, tzinfo=timezone.utc)


FIRST_COMMIT = _utc(0, 30)
SIDE_COMMIT = _utc(1, 0)
LATE_BRANCH_COMMIT = _utc(3, 0)
SECOND_COMMIT = _utc(5, 0)
BOUNDARY_STAMP = _utc(2, 0, 0, 789000)


def _iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _git_at(cwd, *args, moment=None):
    """Run git in `cwd`; with `moment`, author and committer dates are that instant."""
    env = dict(os.environ)
    if moment is not None:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"{int(moment.timestamp())} +0000"
    command = [
        "git", "-c", "user.name=tester", "-c", "user.email=tester@example.invalid",
        "-c", "commit.gpgsign=false", *args,
    ]
    subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=True)


def _commit_active(work, task, moment):
    (work / ".compass").mkdir(exist_ok=True)
    (work / ".compass" / "active.md").write_text(
        f"# Active\n\n- [ ] TASK-1: {task} the committed open task\n- [x] TASK-2: finished\n", encoding="utf-8")
    _git_at(work, "add", ".compass/active.md")
    _git_at(work, "commit", "-q", "-m", task, moment=moment)


@pytest.fixture(scope="module")
def cli_repo(tmp_path_factory):
    """A committed repository whose plugin/cli is a copy of this repository's, so
    `plugin/cli/compass` is the real command and plugin/ is clean for `launch`."""
    root = tmp_path_factory.mktemp("cli-repo")
    shutil.copytree(PLUGIN_CLI, root / "plugin" / "cli", ignore=shutil.ignore_patterns(
        "__pycache__", "tests", "*.pyc"))
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    _git_at(root, "init", "-q")
    _git_at(root, "add", ".")
    _git_at(root, "commit", "-q", "-m", "plugin cli", moment=FIRST_COMMIT)
    return root


@pytest.fixture
def state_repo(tmp_path):
    """The project folder of the compacted session: `main` holds a commit at
    00:30 and a later one at 05:00, `side` a commit at 01:00, and `late` (an
    orphan branch) one commit at 03:00. HEAD is `main`; one file is untracked."""
    work = tmp_path / "work"
    (work / ".compass").mkdir(parents=True)
    _git_at(work, "init", "-q", "-b", "main")
    _commit_active(work, OPEN_TASK, FIRST_COMMIT)
    _git_at(work, "switch", "-q", "-c", "side")
    _commit_active(work, SIDE_TASK, SIDE_COMMIT)
    _git_at(work, "switch", "-q", "main")
    _commit_active(work, LATER_TASK, SECOND_COMMIT)
    _git_at(work, "switch", "-q", "--orphan", "late")
    _commit_active(work, ORPHAN_TASK, LATE_BRANCH_COMMIT)
    _git_at(work, "switch", "-q", "main")
    (work / UNCOMMITTED_FILE).write_text("scratch\n", encoding="utf-8")
    return work


def _boundary_state_point(tmp_path, private_root, cwd, *, branch="main", stamp=BOUNDARY_STAMP,
                 subagent=False, with_summary=True, name="state-point"):
    """Freeze a point whose boundary record carries `branch`, `cwd` and `stamp`:
    an edit before it, a summary after it (when `with_summary`) and a second edit
    after the summary. With `subagent`, every record belongs to a subagent transcript."""
    folder = tmp_path / name
    folder.mkdir()

    def mark(record):
        record["cwd"] = str(cwd)
        if branch is not None:
            record["gitBranch"] = branch
        if subagent:
            record["isSidechain"] = True
        return record

    stamped = boundary(3)
    stamped["timestamp"] = _iso(stamp)
    records = [mark(user(0, "go")), mark(_plain_edit(1, EDITED_PATH)), mark(tool_result(2, "ok")), mark(stamped)]
    if with_summary:
        records.append(mark(summary(4, f"{STATE_SUMMARY} the session edited the decoder.")))
    records.append(mark(_plain_edit(5, LATER_EDIT)))
    if subagent:
        (folder / "sess" / "subagents").mkdir(parents=True)
        write_transcript(folder / "sess" / "subagents", "agent-x.jsonl", records)
        write_transcript(folder, "sess.jsonl", [user(0, "hi"), assistant(1, "hello")])
    else:
        write_transcript(folder, "t.jsonl", records)
    (found,) = probe.find(folder)
    assert found["boundary"] == 3
    probe.build(found["point"], private_root=private_root)
    return found["point"]


def _ask_state(point, arm, cli_repo, private_root, fake_reply, parent_env=None):
    return probe.ask(
        point, arm, repo_root=cli_repo, private_root=private_root,
        claude_cmd=fake_reply.command, parent_env=parent_env)


def _stored_ask(point, private_root, arm):
    return topics.read_json(probe._point_dir(point, private_root) / f"ask-{arm}.json")


def test_mechanical_prompt_holds_the_state_block_at_the_boundary_and_no_summary(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: the mechanical arm that carries the compact summary
    instead of (or beside) the block, a block cut at the wrong line or taken from
    HEAD or the working tree instead of the boundary's commit, or an arm the
    command line does not accept."""
    point = _boundary_state_point(tmp_path, private_root, state_repo)
    fake_reply.reply("{}")

    code = probe.main(
        ["--private-root", str(private_root), "ask", point, "--arm", "mechanical"],
        claude_cmd=fake_reply.command, repo_root=cli_repo)

    assert code == 0
    (call,) = fake_reply.calls()
    prompt = call["stdin"]
    assert BLOCK_TITLE in prompt
    assert EDITED_PATH in prompt
    assert OPEN_TASK in prompt
    assert STATE_SUMMARY not in prompt
    for stale in (LATER_EDIT, LATER_TASK, SIDE_TASK, UNCOMMITTED_FILE):
        assert stale not in prompt


def test_a_key_frozen_without_cwd_renders_the_block_in_the_transcripts_folder(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a key frozen before keys carried `cwd` (the pilot's)
    makes every mechanical and compass ask a no-state record, though its
    transcript names the folder the session ran in."""
    point = _boundary_state_point(tmp_path, private_root, state_repo)
    key_path = probe._point_dir(point, private_root) / "key.json"
    key = topics.read_json(key_path)
    del key["cwd"]
    key_path.write_text(json.dumps(key), encoding="utf-8")
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert BLOCK_TITLE in call["stdin"] and OPEN_TASK in call["stdin"]
    assert not _stored_ask(point, private_root, "mechanical").get("no_state")


def test_compass_prompt_holds_the_summary_before_the_state_block(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a compass arm that drops the block, drops the summary,
    or puts the block first (the trial recorded the summary, then the hook's block)."""
    point = _boundary_state_point(tmp_path, private_root, state_repo)
    fake_reply.reply("{}")

    _ask_state(point, "compass", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    prompt = call["stdin"]
    assert STATE_SUMMARY in prompt and BLOCK_TITLE in prompt
    assert prompt.index(STATE_SUMMARY) < prompt.index(BLOCK_TITLE)
    block = prompt[prompt.index(BLOCK_TITLE):]
    assert EDITED_PATH in block and OPEN_TASK in block


def test_compass_prompt_at_a_subagent_point_holds_the_summary_and_no_block(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a block carried at a subagent compaction, where the
    hook prints nothing for an event carrying `agent_id`, so the arm would hold
    text the real session never received; or a summary dropped with it."""
    point = _boundary_state_point(tmp_path, private_root, state_repo, subagent=True)
    fake_reply.reply("{}")

    _ask_state(point, "compass", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    prompt = call["stdin"]
    assert STATE_SUMMARY in prompt
    assert BLOCK_TITLE not in prompt
    assert OPEN_TASK not in prompt


@pytest.mark.parametrize("branch, stamp, present, absent", [
    pytest.param("side", BOUNDARY_STAMP, SIDE_TASK, (OPEN_TASK, LATER_TASK, ORPHAN_TASK),
                 id="a-branch-other-than-head-is-the-one-searched"),
    pytest.param("deleted-worktree-branch", BOUNDARY_STAMP, OPEN_TASK, (SIDE_TASK, LATER_TASK),
                 id="an-absent-branch-falls-back-to-head"),
    pytest.param("HEAD", BOUNDARY_STAMP, OPEN_TASK, (SIDE_TASK, LATER_TASK),
                 id="a-detached-branch-name-reads-head"),
    pytest.param(None, BOUNDARY_STAMP, OPEN_TASK, (SIDE_TASK, LATER_TASK),
                 id="a-boundary-record-without-a-branch-reads-head"),
    pytest.param("main", FIRST_COMMIT, OPEN_TASK, (LATER_TASK,),
                 id="a-stamp-equal-to-a-commit-date-takes-that-commit"),
    pytest.param("main", SECOND_COMMIT - timedelta(seconds=1), OPEN_TASK, (LATER_TASK,),
                 id="a-stamp-one-second-before-a-commit-leaves-it-out"),
    pytest.param("main", SECOND_COMMIT + timedelta(milliseconds=500), LATER_TASK, (OPEN_TASK,),
                 id="a-stamp-half-a-second-after-a-commit-takes-it"),
    pytest.param("main", SECOND_COMMIT + timedelta(hours=1), LATER_TASK, (OPEN_TASK, SIDE_TASK),
                 id="a-stamp-after-every-commit-takes-the-last"),
])
def test_the_block_is_taken_at_the_last_commit_on_the_branch_by_the_boundary_stamp(
        tmp_path, private_root, state_repo, cli_repo, fake_reply, branch, stamp, present, absent):
    """Adversarial where: the commit chosen by the wrong branch (HEAD when the
    record names another), a missing branch that aborts instead of reading HEAD,
    an exclusive comparison at the boundary instant, a stamp with milliseconds
    that git misreads, or the first or newest commit taken whatever the stamp."""
    point = _boundary_state_point(tmp_path, private_root, state_repo, branch=branch, stamp=stamp)
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert present in call["stdin"]
    for other in absent:
        assert other not in call["stdin"]


@pytest.mark.parametrize("arm", ["mechanical", "compass"])
@pytest.mark.parametrize("where, branch, stamp", [
    pytest.param("repo", "main", FIRST_COMMIT - timedelta(seconds=1), id="boundary-before-the-first-commit"),
    pytest.param("repo", "late", BOUNDARY_STAMP, id="branch-with-no-commit-by-the-stamp"),
    pytest.param("plain", "main", BOUNDARY_STAMP, id="folder-that-is-no-repository"),
    pytest.param("gone", "main", BOUNDARY_STAMP, id="folder-that-no-longer-exists"),
])
def test_a_point_with_no_qualifying_commit_stores_a_no_state_record_and_starts_no_session(
        tmp_path, private_root, state_repo, cli_repo, fake_reply, arm, where, branch, stamp):
    """Adversarial where: a point with no commit by its stamp that falls back to
    HEAD (a commit that postdates nothing it knew), raises on a git failure
    instead of recording it, or starts a session that answers from no state and
    is graded as a failure of the arm."""
    cwd = {"repo": state_repo, "plain": tmp_path / "plain", "gone": tmp_path / "gone"}[where]
    if where == "plain":
        cwd.mkdir()
    point = _boundary_state_point(tmp_path, private_root, cwd, branch=branch, stamp=stamp)

    _ask_state(point, arm, cli_repo, private_root, fake_reply)

    assert fake_reply.calls() == []
    stored = _stored_ask(point, private_root, arm)
    assert stored["no_state"] is True
    assert not stored.get("reply")


@pytest.mark.parametrize("arm", ["mechanical", "compass"])
@pytest.mark.parametrize("through_parent_env", [False, True], ids=["process-environment", "parent-env-argument"])
def test_the_session_state_process_sees_no_claude_project_dir(
        tmp_path, private_root, state_repo, cli_repo, fake_reply, monkeypatch, arm, through_parent_env):
    """Adversarial where: a CLAUDE_PROJECT_DIR left in the child's environment
    redirects the command to another project's vault (the decoy), so the block is
    built from the wrong project or fails; or the variable is deleted from the
    caller's own environment instead of the child's."""
    decoy = tmp_path / "decoy"
    (decoy / ".compass").mkdir(parents=True)
    (decoy / ".compass" / "active.md").write_text("- [ ] TASK-99: ZQDECOYTASK\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(decoy))
    parent_env = dict(os.environ) if through_parent_env else None
    point = _boundary_state_point(tmp_path, private_root, state_repo)
    fake_reply.reply("{}")

    _ask_state(point, arm, cli_repo, private_root, fake_reply, parent_env=parent_env)

    (call,) = fake_reply.calls()
    assert OPEN_TASK in call["stdin"] and EDITED_PATH in call["stdin"]
    assert "ZQDECOYTASK" not in call["stdin"]
    assert os.environ["CLAUDE_PROJECT_DIR"] == str(decoy)
    if parent_env is not None:
        assert parent_env["CLAUDE_PROJECT_DIR"] == str(decoy)


@pytest.mark.parametrize("arm", ["mechanical", "compass"])
def test_the_ask_file_stores_the_carried_block_beside_the_reply(
        tmp_path, private_root, state_repo, cli_repo, fake_reply, arm):
    """Adversarial where: an ask file that keeps the reply but not the block the
    session was given, so a run cannot be audited without rendering the state
    again (and a re-rendering later would read a different repository), or a stored
    block that differs from the one in the prompt."""
    point = _boundary_state_point(tmp_path, private_root, state_repo)
    fake_reply.reply('{"artifact": []}')

    _ask_state(point, arm, cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    stored = _stored_ask(point, private_root, arm)
    blocks = [
        value for key, value in stored.items()
        if key != "reply" and isinstance(value, str) and BLOCK_TITLE in value
    ]
    assert len(blocks) == 1
    assert OPEN_TASK in blocks[0] and EDITED_PATH in blocks[0]
    assert blocks[0].strip() in call["stdin"]
    assert stored["reply"] == '{"artifact": []}'
    assert "tokens" in stored


def test_the_mechanical_arm_needs_no_compact_summary(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a mechanical arm that reads the host summary first and
    fails with NoSummary on a transcript that holds none, though its carried text
    is the block alone."""
    point = _boundary_state_point(tmp_path, private_root, state_repo, with_summary=False)
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert BLOCK_TITLE in call["stdin"] and OPEN_TASK in call["stdin"]


def test_grade_skips_a_no_state_record_and_still_grades_the_arms_beside_it(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a no-state record (no reply) graded as an unparsed
    answer and scored 0 in every probe, which charges the arm for a commit that
    does not exist, or a grade that raises on the record and loses the other arms."""
    point = _boundary_state_point(tmp_path, private_root, state_repo, stamp=FIRST_COMMIT - timedelta(seconds=1))
    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)
    _store_reply(point, private_root, "host-summary", {"artifact": [EDITED_PATH]})

    graded = probe.grade(point, private_root=private_root)

    assert set(graded) == {"host-summary"}
    folder = probe._point_dir(point, private_root)
    assert (folder / "grade-host-summary.json").is_file()
    assert not (folder / "grade-mechanical.json").exists()


def test_report_counts_the_no_state_points_of_each_arm_and_scores_none_of_them(two_points, private_root):
    """Adversarial where: no-state points missing from the report (a silent loss
    of data points), counted over all arms together instead of per arm, or scored
    as zero rows that drag the arm's means down."""
    first, second = two_points
    probe.build(first, private_root=private_root)
    _store_reply(first, private_root, "host-summary", {"artifact": ["src/app/main.py"]})
    probe.grade(first, private_root=private_root)
    for point, arm in ((first, "mechanical"), (first, "compass"), (second, "compass")):
        topics.write_json(
            probe._point_dir(point, private_root) / f"ask-{arm}.json",
            {"point": point, "arm": arm, "no_state": True})

    text = probe.report(private_root=private_root)

    rows = _main_rows(text)
    assert ("host-summary", "artifact") in rows
    assert not [key for key in rows if key[0] in ("mechanical", "compass")]
    assert re.search(r"no[- ]state", text, re.IGNORECASE)
    assert re.search(r"mechanical\D*\b1\b", text)
    assert re.search(r"compass\D*\b2\b", text)


# mechanical and compass arms: implementation-visible branches ------------------

def _fake_compass_source():
    return '''\
import json, os, sys, time
case = os.environ.get("ZQ_CASE", "ok")
log = os.environ.get("ZQ_LOG")
if log:
    with open(log, "w", encoding="utf-8") as handle:
        json.dump({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ)}, handle)
if case == "blank":
    sys.stdout.write("  \\n\\t\\n")
elif case == "fail":
    print("ZQFAILED partial block")
    sys.exit(3)
elif case == "padded":
    sys.stdout.buffer.write(b"\\n\\n  ZQPADDED first line\\n  second line\\n\\n\\n")
elif case == "bytes":
    sys.stdout.buffer.write(b"ZQBYTES \\xff\\xfe tail\\n")
elif case == "hang":
    time.sleep(60)
else:
    print("ZQFAKEBLOCK")
'''


def _fake_cli_repo(tmp_path):
    """A committed repository whose `plugin/cli/compass` is a script driven by ZQ_CASE."""
    root = tmp_path / "fake-cli-repo"
    (root / "plugin" / "cli").mkdir(parents=True)
    (root / "plugin" / "cli" / "compass").write_text(_fake_compass_source(), encoding="utf-8")
    _git_at(root, "init", "-q")
    _git_at(root, "add", ".")
    _git_at(root, "commit", "-q", "-m", "fake cli", moment=FIRST_COMMIT)
    return root


def _point_with_stamp(tmp_path, private_root, cwd, stamp, *, branch="main", name="stamp-point"):
    """A point whose boundary record carries `stamp` verbatim (None leaves the field out)."""
    folder = tmp_path / name
    folder.mkdir()
    stamped = boundary(3)
    if stamp is None:
        stamped.pop("timestamp", None)
    else:
        stamped["timestamp"] = stamp
    records = [user(0, "go"), _plain_edit(1, EDITED_PATH), tool_result(2, "ok"), stamped,
               summary(4, f"{STATE_SUMMARY} summary."), _plain_edit(5, LATER_EDIT)]
    for record in records:
        record["cwd"] = str(cwd)
        record["gitBranch"] = branch
    write_transcript(folder, "t.jsonl", records)
    (found,) = probe.find(folder)
    probe.build(found["point"], private_root=private_root)
    return found["point"]


@pytest.mark.parametrize("stamp, present, absent", [
    pytest.param("2026-02-01T05:00:00Z", LATER_TASK, (OPEN_TASK,), id="z-suffix-on-the-commit-second"),
    pytest.param("2026-02-01T07:00:00+02:00", LATER_TASK, (OPEN_TASK,), id="positive-offset-naming-the-commit-instant"),
    pytest.param("2026-02-01T06:59:59+02:00", OPEN_TASK, (LATER_TASK,), id="positive-offset-one-second-short"),
    pytest.param("2026-02-01T00:00:00-05:00", LATER_TASK, (OPEN_TASK,), id="negative-offset-naming-the-commit-instant"),
    pytest.param("2026-02-01T05:00:00.999999Z", LATER_TASK, (OPEN_TASK,), id="microseconds-past-the-commit-second"),
    pytest.param("2026-02-01T04:59:59.999999Z", OPEN_TASK, (LATER_TASK,), id="microseconds-just-short-of-the-commit"),
    pytest.param("2026-02-01T05:00:00", LATER_TASK, (OPEN_TASK,), id="no-zone-is-read-as-utc"),
])
def test_the_boundary_stamp_is_compared_as_an_instant_whatever_its_zone_or_fraction(
        tmp_path, private_root, state_repo, cli_repo, fake_reply, stamp, present, absent):
    """Adversarial where: a stamp compared as text or with its offset dropped
    (02:00+02:00 read as 07:00 or as 05:00), a fraction rounded up past the next
    second, or a zone-less stamp read in the machine's local zone, any of which
    picks a different commit by hours or by one second at the line."""
    point = _point_with_stamp(tmp_path, private_root, state_repo, stamp)
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert present in call["stdin"]
    for other in absent:
        assert other not in call["stdin"]


@pytest.mark.parametrize("stamp", [
    pytest.param(None, id="no-timestamp-field"),
    pytest.param("", id="empty-stamp"),
    pytest.param("yesterday at noon", id="not-a-time"),
    pytest.param("2026-13-45T99:00:00Z", id="out-of-range-fields"),
])
def test_a_boundary_with_no_usable_stamp_is_a_no_state_point_and_starts_no_session(
        tmp_path, private_root, state_repo, cli_repo, fake_reply, stamp):
    """Adversarial where: a missing or unparsable stamp that raises out of `ask`
    (losing the run) or falls back to HEAD, which would grade the arm on a state
    from after the compaction."""
    point = _point_with_stamp(tmp_path, private_root, state_repo, stamp)

    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

    assert fake_reply.calls() == []
    assert _stored_ask(point, private_root, "mechanical")["no_state"] is True


def test_branch_names_with_slashes_and_tag_namesakes_are_resolved_as_branches(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a slashed branch name (`feature/deep/name`) cut at its
    first slash or not found, a branch name that is also a tag (git reads the tag
    first for a bare name), and a branch name that is no valid ref at all (which
    must read HEAD, not abort)."""
    _git_at(state_repo, "switch", "-q", "-c", "feature/deep/name", "main~1")
    _commit_active(state_repo, "ZQSLASHTASK", _utc(1, 30))
    _git_at(state_repo, "switch", "-q", "main")
    _git_at(state_repo, "tag", "side", "main~1")
    rows = [
        ("feature/deep/name", "ZQSLASHTASK", OPEN_TASK),
        ("side", SIDE_TASK, "ZQSLASHTASK"),
        ("bad..name", OPEN_TASK, "ZQSLASHTASK"),
        ("with space", OPEN_TASK, "ZQSLASHTASK"),
    ]
    for number, (branch, present, absent) in enumerate(rows):
        point = _point_with_stamp(tmp_path, private_root, state_repo, _iso(BOUNDARY_STAMP),
                                  branch=branch, name=f"p{number}")
        fake_reply.reply("{}")
        before = len(fake_reply.calls())

        _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

        prompt = fake_reply.calls()[before]["stdin"]
        assert present in prompt, branch
        assert absent not in prompt, branch


def test_the_session_state_command_gets_the_boundary_arguments_the_working_folder_and_an_intact_environment(
        tmp_path, private_root, state_repo, fake_reply, monkeypatch):
    """Adversarial where: an argument list with the wrong index, commit or format,
    a command run in the caller's folder instead of the key's `cwd`, and an
    environment rebuilt from nothing (PATH and every other variable gone) while
    CLAUDE_PROJECT_DIR is removed."""
    fake = _fake_cli_repo(tmp_path)
    monkeypatch.setenv("ZQ_MARK", "kept")
    point = _boundary_state_point(tmp_path, private_root, state_repo)
    transcript = next((tmp_path / "state-point").glob("*.jsonl"))
    log = tmp_path / "state-command.json"
    parent_env = dict(os.environ, ZQ_LOG=str(log), CLAUDE_PROJECT_DIR=str(tmp_path / "decoy"))
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", fake, private_root, fake_reply, parent_env=parent_env)

    seen = json.loads(log.read_text(encoding="utf-8"))
    argv = seen["argv"]
    assert argv[0] == "session-state"
    flags = dict(zip(argv[1::2], argv[2::2]))
    assert set(flags) == {"--transcript", "--until", "--at", "--format"}
    assert Path(flags["--transcript"]).samefile(transcript)
    assert flags["--until"] == "3"
    assert flags["--format"] == "block"
    first = subprocess.run(["git", "-C", str(state_repo), "rev-parse", "main~1"],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert flags["--at"] == first
    assert Path(seen["cwd"]).samefile(state_repo)
    assert "CLAUDE_PROJECT_DIR" not in seen["env"]
    assert seen["env"].get("ZQ_MARK") == "kept"
    assert seen["env"].get("PATH") == os.environ.get("PATH")


@pytest.mark.parametrize("case, carried, stored_block", [
    pytest.param("padded", "ZQPADDED first line\n  second line", "ZQPADDED first line\n  second line",
                 id="outer-whitespace-trimmed-inner-kept"),
    pytest.param("bytes", "ZQBYTES", None, id="invalid-utf8-bytes-are-replaced-not-fatal"),
])
def test_the_block_is_the_commands_output_trimmed_and_decoded_leniently(
        tmp_path, private_root, state_repo, fake_reply, case, carried, stored_block):
    """Adversarial where: a trailing newline left in the stored block, an inner
    indent removed along with the outer whitespace, or a UnicodeDecodeError from
    stray bytes that loses the point."""
    fake = _fake_cli_repo(tmp_path)
    point = _boundary_state_point(tmp_path, private_root, state_repo)
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", fake, private_root, fake_reply,
               parent_env=dict(os.environ, ZQ_CASE=case))

    (call,) = fake_reply.calls()
    assert carried in call["stdin"]
    stored = _stored_ask(point, private_root, "mechanical")
    if stored_block is not None:
        assert stored["block"] == stored_block
    assert stored["block"] == stored["block"].strip()


@pytest.mark.parametrize("case", [
    pytest.param("blank", id="whitespace-only-output"),
    pytest.param("fail", id="non-zero-exit-with-partial-output"),
])
@pytest.mark.parametrize("arm", ["mechanical", "compass"])
def test_a_command_that_prints_nothing_usable_or_fails_leaves_a_no_state_record(
        tmp_path, private_root, state_repo, fake_reply, case, arm):
    """Adversarial where: whitespace-only output carried as an empty block (the
    session then answers from no state and is graded as the arm's failure), or the
    partial output of a failed command carried as if it were the block."""
    fake = _fake_cli_repo(tmp_path)
    point = _boundary_state_point(tmp_path, private_root, state_repo)

    _ask_state(point, arm, fake, private_root, fake_reply, parent_env=dict(os.environ, ZQ_CASE=case))

    assert fake_reply.calls() == []
    stored = _stored_ask(point, private_root, arm)
    assert stored["no_state"] is True
    assert "block" not in stored


def test_a_command_that_outlives_the_state_timeout_leaves_a_no_state_record(
        tmp_path, private_root, state_repo, fake_reply, monkeypatch):
    """Adversarial where: a hung `session-state` that stalls the whole probe run
    (no timeout) or escapes as a TimeoutExpired instead of a no-state record."""
    monkeypatch.setattr(probe, "STATE_TIMEOUT", 8)
    fake = _fake_cli_repo(tmp_path)
    point = _boundary_state_point(tmp_path, private_root, state_repo)

    _ask_state(point, "mechanical", fake, private_root, fake_reply,
               parent_env=dict(os.environ, ZQ_CASE="hang"))

    assert fake_reply.calls() == []
    assert _stored_ask(point, private_root, "mechanical")["no_state"] is True


def test_the_compass_arm_without_a_usable_summary_raises_before_any_session(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a compass arm whose summary is missing that runs on the
    block alone (and so is graded as the arm that holds both texts), or reaches
    the session with an empty first part."""
    point = _boundary_state_point(tmp_path, private_root, state_repo, with_summary=False)

    with pytest.raises(probe.NoSummary):
        _ask_state(point, "compass", cli_repo, private_root, fake_reply)

    assert fake_reply.calls() == []


def test_the_compass_arm_at_a_subagent_point_needs_no_repository_state(
        tmp_path, private_root, cli_repo, fake_reply):
    """Adversarial where: the repository lookup made before the subagent test, so
    a subagent point whose working folder is gone becomes a no-state point though
    its arm carries the summary alone and needs no state."""
    point = _boundary_state_point(tmp_path, private_root, tmp_path / "gone", subagent=True)
    fake_reply.reply("{}")

    _ask_state(point, "compass", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert STATE_SUMMARY in call["stdin"]
    stored = _stored_ask(point, private_root, "compass")
    assert "no_state" not in stored
    assert "block" not in stored


def test_the_mechanical_arm_at_a_subagent_point_renders_the_block_from_the_subagent_transcript(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: the subagent special case applied to the mechanical arm
    too (the arm is the block alone, so a subagent point would lose its only text),
    or `--until` indexing the wrong transcript for a subagent point."""
    point = _boundary_state_point(tmp_path, private_root, state_repo, subagent=True)
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert BLOCK_TITLE in call["stdin"] and OPEN_TASK in call["stdin"]
    assert STATE_SUMMARY not in call["stdin"]


def test_a_working_folder_inside_the_repository_resolves_the_same_commit(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a key `cwd` that is a subfolder of the repository (a
    session that had changed into `src/`) failing the commit lookup or the vault
    lookup, so most real points would be no-state points."""
    sub = state_repo / "src"
    sub.mkdir()
    point = _point_with_stamp(tmp_path, private_root, sub, _iso(BOUNDARY_STAMP))
    fake_reply.reply("{}")

    _ask_state(point, "mechanical", cli_repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    assert OPEN_TASK in call["stdin"]


def _graded_point(tmp_path, private_root, cwd, cli_repo, fake_reply, name, arms):
    point = _boundary_state_point(tmp_path, private_root, cwd, name=name)
    fake_reply.reply(json.dumps({"artifact": [EDITED_PATH]}))
    _store_reply(point, private_root, "host-summary", {"artifact": [EDITED_PATH]})
    for arm in arms:
        _ask_state(point, arm, cli_repo, private_root, fake_reply)
    probe.grade(point, private_root=private_root)
    return point


def test_report_over_graded_and_no_state_points_counts_each_apart_and_leaks_no_block(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a no-state point folded into an arm's `points` column or
    mean, one arm's no-state count charged to the other, the no-state line missing
    for the arm that has them, or the stored block (state text, paths, tasks)
    reaching the report."""
    _graded_point(tmp_path, private_root, state_repo, cli_repo, fake_reply, "graded", ("mechanical", "compass"))
    _graded_point(tmp_path, private_root, tmp_path / "gone", cli_repo, fake_reply, "stateless", ("mechanical", "compass"))

    text = probe.report(private_root=private_root)

    rows = _main_rows(text)
    assert rows[("mechanical", "artifact")][2] == "1"
    assert rows[("compass", "artifact")][2] == "1"
    assert rows[("host-summary", "artifact")][2] == "2"
    lines = text.splitlines()
    assert "no-state points, compass: 1" in lines
    assert "no-state points, mechanical: 1" in lines
    assert not [line for line in lines if line.startswith("no-state points, host-summary")]
    for secret in (BLOCK_TITLE, OPEN_TASK, EDITED_PATH, STATE_SUMMARY, UNCOMMITTED_FILE):
        assert secret not in text


def test_a_point_asked_again_into_no_state_drops_the_grade_of_its_earlier_reply(
        tmp_path, private_root, state_repo, cli_repo, fake_reply):
    """Adversarial where: a stale `grade-<arm>.json` left behind when a re-run of
    `ask` stores a no-state record (the commit no longer resolves), so the report
    scores the old reply and counts the same point as no-state too."""
    point = _graded_point(tmp_path, private_root, state_repo, cli_repo, fake_reply, "regraded", ("mechanical",))
    assert (probe._point_dir(point, private_root) / "grade-mechanical.json").is_file()
    topics.write_json(probe._point_dir(point, private_root) / "ask-mechanical.json",
                      {"point": point, "arm": "mechanical", "no_state": True})

    probe.grade(point, private_root=private_root)
    text = probe.report(private_root=private_root)

    assert ("mechanical", "artifact") not in _main_rows(text)
    assert "no-state points, mechanical: 1" in text.splitlines()


# superseded replies and the files-listed line ------------------------------------


def test_a_repeated_ask_moves_the_earlier_reply_and_grade_aside(point, repo, private_root, fake_reply):
    """Adversarial where: a rerun overwrites the first run's reply and grade, losing
    the data the comparison was drawn from, or numbers its folders past an existing one."""
    probe.build(point, private_root=private_root)
    folder = probe._point_dir(point, private_root)
    for round_number in (1, 2, 3):
        fake_reply.reply(json.dumps({"artifact": [f"round{round_number}.py"]}))
        _ask(point, "host-summary", repo, private_root, fake_reply)
        probe.grade(point, private_root=private_root)
    assert "round3.py" in topics.read_json(folder / "ask-host-summary.json")["reply"]
    assert "round1.py" in topics.read_json(folder / "superseded" / "1" / "ask-host-summary.json")["reply"]
    assert "round2.py" in topics.read_json(folder / "superseded" / "2" / "ask-host-summary.json")["reply"]
    assert (folder / "superseded" / "1" / "grade-host-summary.json").is_file()
    assert not (folder / "superseded" / "3").exists()
    rows = _main_rows(probe.report(private_root=private_root))
    assert rows[("host-summary", "artifact")][2] == "1"


def test_arms_rerun_one_after_another_share_the_first_superseded_folder(point, repo, private_root, fake_reply):
    """Adversarial where: the second arm's rerun counts the first arm's move and lands
    its earlier reply one folder further, so a round's replies scatter over folders."""
    probe.build(point, private_root=private_root)
    folder = probe._point_dir(point, private_root)
    for arm in ("host-summary", "none", "host-summary", "none"):
        fake_reply.reply("{}")
        _ask(point, arm, repo, private_root, fake_reply)
    assert (folder / "superseded" / "1" / "ask-host-summary.json").is_file()
    assert (folder / "superseded" / "1" / "ask-none.json").is_file()
    assert not (folder / "superseded" / "2").exists()


def test_report_counts_the_expected_files_the_stored_blocks_list(two_points, private_root):
    """Adversarial where: the files-listed line counts paths outside the files-edited
    section, misses a path spelled with `./` or backslashes, or counts an arm with no
    stored block."""
    first, second = two_points
    for point in (first, second):
        probe.build(point, private_root=private_root)
    key = topics.read_json(probe._point_dir(first, private_root) / "key.json")
    expected = next(p for p in key["probes"] if p["type"] == "artifact")["expected"]
    assert len(expected) >= 2
    block = "\n".join([
        "Compass session state", "", "## Files edited", "- ./" + expected[0],
        "- " + expected[1].replace("/", "\\"), "- not/expected.py", "", "## Files read",
        *[f"- {path}" for path in expected[2:]],
    ])
    stored = {"point": first, "arm": "mechanical", "reply": "{}", "tokens": {}, "block": block}
    topics.write_json(probe._point_dir(first, private_root) / "ask-mechanical.json", stored)
    probe.grade(first, private_root=private_root)
    text = probe.report(private_root=private_root)
    match = re.search(r"files listed by the stored blocks, mechanical: (\d+) of (\d+)", text)
    assert match, text
    assert match.groups() == ("2", str(len(expected)))
    assert "files listed by the stored blocks, compass" not in text


# rebuilt session ------------------------------------------------------------------


def test_rebuild_writes_the_history_before_the_boundary_as_a_session_of_the_project(
        point, private_root, tmp_path, project_dir):
    """Adversarial where: the rebuilt session carries records from after the
    boundary (the summary the answer must not see), keeps the recorded session id
    or working folder so the host files it under the original project, or writes
    into the transcript it reads."""
    source = Path(point.rpartition("#")[0])
    before_bytes = source.read_bytes()
    index = int(point.rpartition("#")[2])
    project = tmp_path / "sandbox-project"
    project.mkdir()

    session = probe.rebuild(point, project, private_root=private_root)

    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", session)
    folder = Path(private_root) / "claude-config" / "projects" / probe.launch.encode_cwd(project)
    written = [json.loads(line) for line in (folder / f"{session}.jsonl").read_text(encoding="utf-8").splitlines()]
    originals = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    assert [r["uuid"] for r in written] == [r["uuid"] for r in originals[:index]]
    assert not [r for r in written if r.get("isCompactSummary")]
    assert SUMMARY_MARK not in json.dumps(written)
    for record in written:
        assert record["sessionId"] == session
        if "cwd" in record:
            assert record["cwd"] == str(project)
    assert source.read_bytes() == before_bytes


def test_two_rebuilds_of_one_point_are_two_sessions(point, private_root, tmp_path):
    """Adversarial where: a fixed session id lets the second rebuild overwrite a session
    another ask is resuming."""
    project = tmp_path / "p2"
    project.mkdir()
    first = probe.rebuild(point, project, private_root=private_root)
    second = probe.rebuild(point, project, private_root=private_root)
    assert first != second


def test_rebuild_refuses_a_private_root_inside_a_git_work_tree(point, repo, tmp_path):
    """Adversarial where: the rebuilt history, which holds project content, lands in a
    repository."""
    project = tmp_path / "p3"
    project.mkdir()
    with pytest.raises(probe.Refused):
        probe.rebuild(point, project, private_root=repo / "inside")
    assert not (repo / "inside").exists()


def test_rebuild_cli_prints_the_session_id_of_a_new_sandbox_project(point, private_root, repo, capsys):
    """Adversarial where: the command line rebuilds into an existing folder or prints
    nothing a resume can use."""
    code = probe.main(["--private-root", str(private_root), "rebuild", point], repo_root=repo)
    assert code == 0
    session, project = capsys.readouterr().out.strip().split("\t")
    project = Path(project)
    assert project.is_relative_to(Path(private_root) / "probe-projects")
    folder = Path(private_root) / "claude-config" / "projects" / probe.launch.encode_cwd(project)
    assert (folder / f"{session}.jsonl").is_file()


# before arm -----------------------------------------------------------------------


def test_before_arm_resumes_the_rebuilt_history_with_no_tools_and_no_carried_text(
        point, repo, private_root, fake_reply):
    """Adversarial where: the before arm carries the summary or a rendered history in
    its prompt instead of resuming the history, keeps its tools, resumes a session the
    project does not hold, or runs in the repository."""
    built = probe.build(point, private_root=private_root)
    fake_reply.reply(json.dumps(key_answers(built)))

    stored = _ask(point, "before", repo, private_root, fake_reply)

    (call,) = fake_reply.calls()
    argv = call["argv"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == FIXTURE_MODEL
    session = argv[argv.index("--resume") + 1]
    project = Path(call["cwd"])
    assert project.resolve().is_relative_to(Path(private_root).resolve())
    rebuilt = Path(private_root) / "claude-config" / "projects" / probe.launch.encode_cwd(project) / f"{session}.jsonl"
    assert rebuilt.is_file()
    assert SUMMARY_MARK not in call["stdin"]
    assert "frame decoder" not in call["stdin"]
    for item in built["probes"]:
        assert item["question"] in call["stdin"]
    assert stored["arm"] == "before"
    assert "block" not in stored


def test_rebuild_of_a_subagent_point_writes_its_records_as_the_main_chain(tmp_path, private_root):
    """Adversarial where: a subagent point's records keep `isSidechain: true`, which a
    resumed main session skips, so the before arm would answer from nothing."""
    folder = tmp_path / "sub"
    (folder / "sess" / "subagents").mkdir(parents=True)
    records = [user(0, "go"), _plain_edit(1, "src/a.py"), tool_result(2, "ok"), boundary(3), summary(4)]
    for record in records:
        record["isSidechain"] = True
    write_transcript(folder / "sess" / "subagents", "agent-x.jsonl", records)
    write_transcript(folder, "sess.jsonl", [user(0, "hi")])
    (found,) = probe.find(folder)
    project = tmp_path / "proj"
    project.mkdir()
    session = probe.rebuild(found["point"], project, private_root=private_root)
    path = Path(private_root) / "claude-config" / "projects" / probe.launch.encode_cwd(project) / f"{session}.jsonl"
    written = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(written) == 3
    assert all(record["isSidechain"] is False for record in written)


def test_report_lists_the_before_arm_and_its_paired_table(point, private_root):
    """Adversarial where: the report drops an arm it does not know, or never compares
    the reference arm with the host summary."""
    probe.build(point, private_root=private_root)
    _store_reply(point, private_root, "host-summary", {"artifact": ["src/app/main.py"]})
    _store_reply(point, private_root, "before", {"artifact": EDITED})
    probe.grade(point, private_root=private_root)
    text = probe.report(private_root=private_root)
    rows = _main_rows(text)
    assert rows[("before", "artifact")][3] == "1.00"
    assert re.search(r"^\| before \| artifact \| 1 \| 0\.67 \|", text, re.MULTILINE)
