"""Tests for probe_judge.py, the judge of the probes' free-text answers.

Interface assumed:

    probe_judge.items_of(point, *, private_root) -> [item]
        One item per distinct answer an arm's current reply gives to a recall,
        continuation or decision probe of the point: {"label": "1", "probe": id,
        "type": type, "arms": [arm, ...], "answer": text}. Labels run 1..n in
        prompt order; the order is fixed per point and does not follow the arm
        order. Arms with a no-state ask file, or none, give no item.
    probe_judge.judge(point, *, repo_root, private_root, claude_cmd) -> dict|None
        One tool-less session on probe_judge.MODEL whose prompt holds every
        question, its reference answer and the labelled answers, and no arm name.
        Stores <point dir>/judge.json: {"point", "model", "verdicts": [{"arm",
        "probe", "verdict", "score"}], "tokens"}; a verdict is right (1.0),
        partly (0.5) or wrong (0.0). A point with no free-text probe starts no
        session and returns None. A reply missing a label raises JudgeError and
        stores nothing. An existing judge.json moves to superseded/<n>/.
    probe_judge.report(*, private_root) -> markdown text
    probe_judge.sample(*, private_root, size) -> sheet path
        <private root>/probe-judge-sample/sheet.md with `mark N:` lines and no
        arm name or judge verdict; the map in <private root>/probe-judge-sample-key.json.
    probe_judge.agreement(*, private_root) -> {"marked", "agree", "pending", ...}
"""

import json
import re
from pathlib import Path

import pytest

import probe
import probe_judge
import topics
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)

POINT = "C:/nowhere/session.jsonl#12"
PROBES = [
    {"id": "artifact", "type": "artifact", "question": "Which files?", "expected": ["a.py"]},
    {"id": "recall-1", "type": "recall", "question": "Quote the error.", "expected": "ValueError: bad frame width"},
    {"id": "continuation", "type": "continuation", "question": "Which task?", "expected": "TASK-12"},
    {"id": "decision", "type": "decision", "question": "Which option?", "expected": "Flat files"},
]


def seed_point(private_root, replies, probes=PROBES, no_state=()):
    folder = probe._point_dir(POINT, private_root)
    folder.mkdir(parents=True, exist_ok=True)
    topics.write_json(folder / "key.json", {"point": POINT, "model": "claude-haiku-4-5", "cwd": None,
                                            "probes": probes})
    for arm, reply in replies.items():
        topics.write_json(folder / f"ask-{arm}.json", {"point": POINT, "arm": arm, "reply": json.dumps(reply)})
    for arm in no_state:
        topics.write_json(folder / f"ask-{arm}.json", {"point": POINT, "arm": arm, "no_state": True})
    return folder


REPLIES = {
    "host-summary": {"artifact": ["a.py"], "recall-1": "ValueError: bad frame width", "continuation": "TASK-12",
                     "decision": "flat files layout"},
    "mechanical": {"artifact": [], "recall-1": "ValueError", "continuation": "TASK-11", "decision": "Flat files"},
    "none": {"artifact": [], "recall-1": "not available", "continuation": "TASK-12", "decision": "unknown"},
}


def reply_for(items, verdicts):
    """A judge reply giving `verdicts[(probe, answer)]`, defaulting to wrong."""
    return json.dumps({item["label"]: verdicts.get((item["probe"], item["answer"]), "wrong") for item in items})


def run_judge(private_root, repo, fake_reply, verdicts=None, items=None):
    items = items if items is not None else probe_judge.items_of(POINT, private_root=private_root)
    fake_reply.reply(reply_for(items, verdicts or {}))
    return probe_judge.judge(POINT, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)


def test_items_dedupe_equal_answers_across_arms_and_skip_artifact_and_no_state(private_root):
    """Adversarial where: the artifact list is sent to the judge, a no-state arm gives an
    item, or two arms with the same answer cost two verdicts that could disagree."""
    seed_point(private_root, REPLIES, no_state=("compass",))
    items = probe_judge.items_of(POINT, private_root=private_root)
    assert {item["type"] for item in items} == {"recall", "continuation", "decision"}
    assert all(item["probe"] != "artifact" for item in items)
    same = [item for item in items if item["probe"] == "continuation" and item["answer"] == "TASK-12"]
    assert len(same) == 1 and sorted(same[0]["arms"]) == ["host-summary", "none"]
    assert [item["label"] for item in items] == [str(n) for n in range(1, len(items) + 1)]
    assert not any("compass" in item["arms"] for item in items)


def test_items_order_is_fixed_and_does_not_follow_the_arm_order(private_root):
    """Adversarial where: labels follow the arm order, so a judge can learn which label
    is the host summary, or the order changes from one call to the next."""
    seed_point(private_root, REPLIES)
    first = probe_judge.items_of(POINT, private_root=private_root)
    assert first == probe_judge.items_of(POINT, private_root=private_root)
    many = {arm: {"recall-1": f"answer {arm}"} for arm in probe.ARMS}
    seed_point(private_root, many)
    arms = [item["arms"][0] for item in probe_judge.items_of(POINT, private_root=private_root)]
    assert arms != sorted(arms) and arms != list(probe.ARMS)


def test_a_missing_or_non_string_answer_is_judged_as_its_text_or_no_answer(private_root):
    """Adversarial where: an unparsed reply or a list answer crashes the judge or is
    dropped, so the arm escapes a wrong verdict."""
    seed_point(private_root, {"host-summary": {"continuation": ["TASK-12", "TASK-3"]}})
    folder = probe._point_dir(POINT, private_root)
    topics.write_json(folder / "ask-none.json", {"point": POINT, "arm": "none", "reply": "no json here"})
    items = probe_judge.items_of(POINT, private_root=private_root)
    answers = {(item["probe"], tuple(item["arms"])): item["answer"] for item in items}
    assert answers[("continuation", ("host-summary",))] == '["TASK-12", "TASK-3"]'
    assert answers[("continuation", ("none",))] == probe_judge.NO_ANSWER
    assert answers[("recall-1", ("host-summary",))] == probe_judge.NO_ANSWER


def test_judge_prompt_holds_questions_references_and_labels_but_no_arm_name(private_root, repo, fake_reply):
    """Adversarial where: the judge sees which arm gave an answer, misses the reference
    answer, runs with tools, or on another model than the judge's."""
    seed_point(private_root, REPLIES)
    run_judge(private_root, repo, fake_reply)
    (call,) = fake_reply.calls()
    prompt, argv = call["stdin"], call["argv"]
    for item in PROBES[1:]:
        assert item["question"] in prompt and item["expected"] in prompt
    for arm in probe.ARMS:
        assert arm not in prompt
    assert "Which files?" not in prompt
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == probe_judge.MODEL
    assert "--strict-mcp-config" in argv


def test_judge_stores_one_verdict_per_arm_and_probe_with_its_score(private_root, repo, fake_reply):
    """Adversarial where: a deduplicated answer's verdict reaches only one of its arms, or
    partly is scored as right."""
    seed_point(private_root, REPLIES)
    stored = run_judge(private_root, repo, fake_reply, {
        ("continuation", "TASK-12"): "right", ("decision", "flat files layout"): "right",
        ("recall-1", "ValueError"): "partly", ("recall-1", "ValueError: bad frame width"): "right"})
    by = {(v["arm"], v["probe"]): v for v in stored["verdicts"]}
    assert by[("host-summary", "continuation")]["score"] == 1.0
    assert by[("none", "continuation")]["score"] == 1.0
    assert by[("mechanical", "recall-1")] == {"arm": "mechanical", "probe": "recall-1", "verdict": "partly",
                                              "score": 0.5}
    assert by[("mechanical", "continuation")]["score"] == 0.0
    assert len(stored["verdicts"]) == 3 * 3
    on_disk = topics.read_json(probe._point_dir(POINT, private_root) / "judge.json")
    assert on_disk["verdicts"] == stored["verdicts"] and on_disk["model"] == probe_judge.MODEL
    assert isinstance(on_disk["tokens"], dict)


@pytest.mark.parametrize("bad", [
    "not json", '{"1": "right"}', None,
])
def test_a_reply_missing_a_label_or_with_an_unknown_verdict_stores_nothing(private_root, repo, fake_reply, bad):
    """Adversarial where: a partial or malformed judge reply is stored with the missing
    labels counted as wrong, or an unknown verdict word is accepted."""
    seed_point(private_root, REPLIES)
    items = probe_judge.items_of(POINT, private_root=private_root)
    text = bad if bad is not None else json.dumps({item["label"]: "maybe" for item in items})
    fake_reply.reply(text)
    with pytest.raises(probe_judge.JudgeError):
        probe_judge.judge(POINT, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)
    assert not (probe._point_dir(POINT, private_root) / "judge.json").exists()


def test_verdict_words_are_read_case_and_space_insensitively(private_root, repo, fake_reply):
    """Adversarial where: `Right` or ` partly ` from the judge is refused."""
    seed_point(private_root, {"host-summary": {"continuation": "TASK-12"}})
    (item,) = probe_judge.items_of(POINT, private_root=private_root)
    fake_reply.reply(json.dumps({item["label"]: " Right "}))
    stored = probe_judge.judge(POINT, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)
    assert stored["verdicts"][0]["score"] == 1.0


def test_a_point_with_no_free_text_probe_starts_no_session(private_root, repo, fake_reply):
    seed_point(private_root, {"host-summary": {"artifact": ["a.py"]}}, probes=PROBES[:1])
    assert probe_judge.judge(POINT, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command) is None
    assert fake_reply.calls() == []


def test_a_second_judge_moves_the_first_aside(private_root, repo, fake_reply):
    """Adversarial where: a rerun overwrites the first verdicts, losing them."""
    folder = seed_point(private_root, REPLIES)
    run_judge(private_root, repo, fake_reply)
    run_judge(private_root, repo, fake_reply)
    run_judge(private_root, repo, fake_reply)
    assert (folder / "judge.json").is_file()
    assert (folder / "superseded" / "1" / "judge.json").is_file()
    assert (folder / "superseded" / "2" / "judge.json").is_file()


def test_judge_refuses_a_private_root_inside_a_git_work_tree(repo, fake_reply):
    with pytest.raises(probe.Refused):
        probe_judge.judge(POINT, repo_root=repo, private_root=repo / "inside", claude_cmd=fake_reply.command)
    assert fake_reply.calls() == []


def test_report_gives_judged_means_and_script_agreement_without_answer_text(private_root, repo, fake_reply):
    """Adversarial where: the report leaks an answer or reference, pools artifact into the
    judged state score, or counts a partly verdict as agreeing with a script 0."""
    seed_point(private_root, REPLIES)
    probe.grade(POINT, private_root=private_root)
    run_judge(private_root, repo, fake_reply, {
        ("continuation", "TASK-12"): "right", ("decision", "flat files layout"): "right",
        ("decision", "Flat files"): "right", ("recall-1", "ValueError: bad frame width"): "right",
        ("recall-1", "ValueError"): "partly"})
    text = probe_judge.report(private_root=private_root)
    for secret in ("bad frame width", "Flat files", "TASK-12", "TASK-11", "flat files layout", "session.jsonl"):
        assert secret not in text
    rows = {tuple(c.strip() for c in line.strip("|").split("|"))[:2]: line for line in text.splitlines()
            if line.startswith("| ")}
    assert "| 1.00 |" in rows[("host-summary", "decision")]
    assert "| 0.50 |" in rows[("mechanical", "recall")]
    assert ("host-summary", "artifact") not in rows
    state_hs = rows[("host-summary", "state")]
    assert "| 1.00 |" in state_hs
    agree = re.search(r"judge and script agree on (\d+) of (\d+)", text)
    assert agree is not None
    folder = probe._point_dir(POINT, private_root)
    judged = topics.read_json(folder / "judge.json")["verdicts"]
    same = sum(1 for v in judged
               if topics.read_json(folder / f"grade-{v['arm']}.json")["scores"][v["probe"]] == v["score"])
    assert agree.groups() == (str(same), "9")
    assert 0 < same < 9


def test_sample_writes_a_sheet_without_arms_or_verdicts_and_keeps_the_map_apart(private_root, repo, fake_reply):
    """Adversarial where: the sheet shows the arm or the judge's verdict, so the human's
    grade is not independent, or the map sits inside the sheet folder."""
    seed_point(private_root, REPLIES)
    run_judge(private_root, repo, fake_reply, {("continuation", "TASK-12"): "right"})
    sheet = probe_judge.sample(private_root=private_root, size=4)
    assert sheet == private_root / "probe-judge-sample" / "sheet.md"
    text = sheet.read_text(encoding="utf-8")
    assert len(re.findall(r"^mark \d+:\s*$", text, re.MULTILINE)) == 4
    for arm in probe.ARMS:
        assert arm not in text
    assert "right" not in text.replace("right, partly or wrong", "")
    key = private_root / "probe-judge-sample-key.json"
    assert key.is_file() and not key.is_relative_to(sheet.parent)
    assert len(topics.read_json(key)["items"]) == 4


def test_sample_spreads_over_probe_types_and_is_capped_by_the_items(private_root, repo, fake_reply):
    """Adversarial where: the sample takes the first items, all of one type, or asks for
    more marks than there are judged items."""
    seed_point(private_root, REPLIES)
    run_judge(private_root, repo, fake_reply)
    probe_judge.sample(private_root=private_root, size=3)
    kinds = [item["type"] for item in topics.read_json(private_root / "probe-judge-sample-key.json")["items"]]
    assert sorted(kinds) == ["continuation", "decision", "recall"]
    sheet = probe_judge.sample(private_root=private_root, size=500, replace=True)
    marks = re.findall(r"^mark \d+:", sheet.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(marks) == len(probe_judge.items_of(POINT, private_root=private_root))


def test_sample_refuses_to_overwrite_a_sheet_unless_asked(private_root, repo, fake_reply):
    """Adversarial where: a second sample silently wipes marks the human already wrote."""
    seed_point(private_root, REPLIES)
    run_judge(private_root, repo, fake_reply)
    sheet = probe_judge.sample(private_root=private_root, size=2)
    sheet.write_text(sheet.read_text(encoding="utf-8").replace("mark 1:", "mark 1: right"), encoding="utf-8")
    with pytest.raises(probe_judge.JudgeError):
        probe_judge.sample(private_root=private_root, size=2)
    assert "mark 1: right" in sheet.read_text(encoding="utf-8")


def test_agreement_is_pending_on_an_unmarked_sheet_and_counts_marked_items(private_root, repo, fake_reply):
    """Adversarial where: an empty sheet reports 0 of 0 agreement as a result, an unknown
    mark is counted, or the comparison reads the wrong item's verdict."""
    seed_point(private_root, REPLIES)
    run_judge(private_root, repo, fake_reply, {("continuation", "TASK-12"): "right"})
    sheet = probe_judge.sample(private_root=private_root, size=3)
    assert probe_judge.agreement(private_root=private_root)["pending"] is True
    key = topics.read_json(private_root / "probe-judge-sample-key.json")["items"]
    verdicts = {}
    for v in topics.read_json(probe._point_dir(POINT, private_root) / "judge.json")["verdicts"]:
        verdicts[(v["arm"], v["probe"])] = v["verdict"]
    text = sheet.read_text(encoding="utf-8")
    first = verdicts[(key[0]["arms"][0], key[0]["probe"])]
    other = "wrong" if first != "wrong" else "right"
    text = text.replace("mark 1:", f"mark 1: {first}").replace("mark 2:", f"mark 2: {other}")
    text = text.replace("mark 3:", "mark 3: banana")
    sheet.write_text(text, encoding="utf-8")
    result = probe_judge.agreement(private_root=private_root)
    assert result["pending"] is False
    assert (result["marked"], result["agree"]) == (2, 1)
    assert result["unreadable"] == 1


def test_cli_judge_report_sample_agreement(private_root, repo, fake_reply, capsys):
    seed_point(private_root, REPLIES)
    items = probe_judge.items_of(POINT, private_root=private_root)
    fake_reply.reply(reply_for(items, {}))
    base = ["--private-root", str(private_root)]
    assert probe_judge.main([*base, "judge", POINT], claude_cmd=fake_reply.command, repo_root=repo) == 0
    assert probe_judge.main([*base, "report"]) == 0
    assert "judge and script agree" in capsys.readouterr().out
    assert probe_judge.main([*base, "sample", "--size", "2"]) == 0
    assert probe_judge.main([*base, "agreement"]) == 0
    assert "pending" in capsys.readouterr().out
    assert probe_judge.main([*base, "sample", "--size", "2"]) == 2
