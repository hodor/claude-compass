"""Tests for human.py: the simulated human that holds a hidden brief.

The interface is described at the top of test_drive.py.

Adversarial themes: the brief leaking whole into a prompt that should hold one
item, a budget that resets between hook processes, gate approvals eating the
question budget, a done flag parsed from a truthy string, and a human that
shares the build's environment or tokens.
"""

import json
import os

import pytest

import fake_claude
import fake_session_claude as fake
import human
from conftest import CREDENTIAL_VARS

BRIEF = {
    "items": [
        {"id": "G1", "name": "csv export", "detail": "DETAIL-ALPHA the export writes a header row"},
        {"id": "G2", "name": "dark mode", "detail": "DETAIL-BRAVO the toggle persists across restarts"},
        {"id": "G3", "name": "offline sync", "detail": "DETAIL-CHARLIE conflicts keep the newest edit"},
    ]
}
DETAILS = {"ALPHA": "DETAIL-ALPHA", "BRAVO": "DETAIL-BRAVO", "CHARLIE": "DETAIL-CHARLIE"}


def say(text, done=False):
    return json.dumps({"text": text, "done": done})


def make(tmp_path, repo, private_root, replies, *, arm="baseline", budget=2, readme=None, state="state.json",
         usage=None, name="human"):
    spec = {"mode": "oneshot", "replies": replies}
    if usage:
        spec["usage"] = usage
    cmd = fake.command(spec, tmp_path / f"{name}-specs")
    folder = tmp_path / f"{name}-folder"
    folder.mkdir(exist_ok=True)
    who = human.SimulatedHuman(
        BRIEF, folder=folder, repo_root=repo, arm=arm, state_file=tmp_path / state,
        private_root=private_root, claude_cmd=cmd, budget=budget, readme=readme,
    )
    return who, cmd, folder


def prompts(cmd):
    return [entry["text"] for entry in fake.read_log(cmd) if entry["kind"] == "stdin"]


def revealed(prompt):
    return sorted(key for key, marker in DETAILS.items() if marker in prompt)


def read_records(private_root):
    rows = []
    for path in sorted((private_root / "records").glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return rows


@pytest.mark.parametrize(
    "message, expected, used",
    [
        ("Should the csv export include a header?", ["ALPHA"], 1),
        ("SHOULD THE CSV EXPORT HAVE A HEADER?", ["ALPHA"], 1),
        ("Do you want the csv export and dark mode in v1?", ["ALPHA", "BRAVO"], 1),
        ("How should data export work?", [], 0),
        ("csv", [], 0),
        ("Approve the plan?", [], 0),
    ],
    ids=["exact", "case-insensitive", "two-items-one-question", "partial-name", "name-prefix-only", "gate"],
)
def test_only_items_the_message_names_reach_the_prompt(tmp_path, repo, private_root, message, expected, used):
    """Adversarial where: a prompt that carries the whole brief lets the
    simulated human volunteer goals nobody asked about; a match on a fragment
    of a name ("export", "csv") reveals an item to a question that never named
    it; two items named in one question are still one question of budget."""
    who, cmd, _ = make(tmp_path, repo, private_root, [say("ok")], budget=5)

    reply = who.reply(message)

    sent = prompts(cmd)
    assert len(sent) == 1 and message in sent[0]
    assert revealed(sent[0]) == expected
    assert who.questions_used == used
    assert reply.text == "ok"


def test_budget_runs_out_after_exactly_budget_revealing_questions(tmp_path, repo, private_root):
    """Adversarial where: an off-by-one lets a third revealing question through
    a budget of 2 (or refuses the second); after the budget the human must not
    start a session, must not reveal the third item, and must write no row."""
    who, cmd, _ = make(tmp_path, repo, private_root, [say("a1"), say("a2"), say("a3")], budget=2)

    first = who.reply("Is the csv export needed?")
    second = who.reply("Is dark mode needed?")
    sessions_before = len(prompts(cmd))
    rows_before = len(read_records(private_root))
    third = who.reply("Is offline sync needed?")

    assert (first.text, second.text) == ("a1", "a2")
    assert third.text == "decide yourself"
    assert third.done is False
    assert list(third.events) == []
    assert len(prompts(cmd)) == sessions_before == 2
    assert len(read_records(private_root)) == rows_before == 2
    assert not any("DETAIL-CHARLIE" in p for p in prompts(cmd))
    assert who.questions_used == 2


def test_gate_approvals_and_continue_messages_never_use_budget(tmp_path, repo, private_root):
    """Adversarial where: counting every reply as a question spends a budget
    of 1 on the first gate, so the one question that matters is answered
    "decide yourself"; gates stay answerable after the budget is spent."""
    who, cmd, _ = make(tmp_path, repo, private_root, [say("ok")] * 8, budget=1)

    for message in ("Approve the plan?", "Continue?", "Ready for phase 2, proceed?"):
        assert who.reply(message).text == "ok"
    assert who.questions_used == 0
    assert who.reply("Is dark mode needed?").text == "ok"
    assert who.reply("Is csv export needed?").text == "decide yourself"
    assert who.reply("Approve the review gate?").text == "ok"
    assert who.questions_used == 1


def test_spent_budget_survives_a_new_process(tmp_path, repo, private_root):
    """Adversarial where: the hook answers each question in a fresh process; a
    counter held only in memory resets to zero there and the human answers
    without limit. A second instance on the same state file must see the
    spent budget."""
    first, _, _ = make(tmp_path, repo, private_root, [say("a1"), say("a2")], budget=2)
    first.reply("Is the csv export needed?")
    first.reply("Is dark mode needed?")

    second, cmd, _ = make(tmp_path, repo, private_root, [say("never")], budget=2, name="second")

    assert second.questions_used == 2
    assert second.reply("Is offline sync needed?").text == "decide yourself"
    assert prompts(cmd) == []


def test_answer_questions_keys_by_question_text_and_spends_budget_per_question(tmp_path, repo, private_root):
    """Adversarial where: three questions arrive in one picker call with a
    budget of 2; a human that counts the call, not the question, answers all
    three or none, and answers must be keyed by the exact question text the
    picker hands back."""
    who, cmd, _ = make(tmp_path, repo, private_root, [say("yes"), say("no")], budget=2)
    questions = [
        {"question": "Do you need csv export?", "multiSelect": False,
         "options": [{"label": "yes"}, {"label": "no"}]},
        {"question": "Do you need dark mode?", "multiSelect": False,
         "options": [{"label": "yes"}, {"label": "no"}]},
        {"question": "Do you need offline sync?", "multiSelect": False,
         "options": [{"label": "yes"}, {"label": "no"}]},
    ]

    answers = who.answer_questions(questions)

    assert answers == {
        "Do you need csv export?": "yes",
        "Do you need dark mode?": "no",
        "Do you need offline sync?": "decide yourself",
    }
    assert len(prompts(cmd)) == 2


def test_session_runs_isolated_from_its_own_folder_on_the_cheap_model(tmp_path, repo, private_root, monkeypatch):
    """Adversarial where: a human session that runs in the project, loads the
    plugin, keeps the parent's credentials or uses the build's model breaks the
    blinding the measurement depends on; its tokens must land in a role
    `human` row carrying the arm and nothing of the conversation."""
    for index, name in enumerate(CREDENTIAL_VARS):
        monkeypatch.setenv(name, f"parent-secret-{index}")
    who, cmd, folder = make(
        tmp_path, repo, private_root, [say("answer")], arm="compass", usage=[41, 42, 43, 44],
    )

    who.reply("Is the csv export needed?")

    entry = next(e for e in fake.read_log(cmd) if e["kind"] == "start")
    argv = entry["argv"]
    assert os.path.samefile(entry["cwd"], folder)
    assert argv[argv.index("--model") + 1] == "claude-sonnet-4-6"
    assert argv[argv.index("--setting-sources") + 1] == "project,local"
    assert "--strict-mcp-config" in argv
    assert "--plugin-dir" not in argv
    assert not set(CREDENTIAL_VARS) & set(entry["env"])
    assert os.path.samefile(entry["env"]["CLAUDE_CONFIG_DIR"], private_root / "claude-config")
    (row,) = read_records(private_root)
    assert row["role"] == "human" and row["arm"] == "compass" and row["outcome"] == "done"
    assert row["models"][fake_claude.MAIN_MODEL] == {
        "input": 41, "output": 42, "cache_read": 43, "cache_write": 44,
    }
    assert "answer" not in json.dumps(row)


@pytest.mark.parametrize(
    "raw, text, done",
    [
        (say("looks fine", True), "looks fine", True),
        (say("keep going", False), "keep going", False),
        ('{"text": "almost", "done": "false"}', "almost", False),
        ("plain words, not JSON", "plain words, not JSON", False),
        ('{"text": "half", "done": true', '{"text": "half", "done": true', False),
    ],
    ids=["done-true", "done-false", "done-as-string", "not-json", "truncated-json"],
)
def test_reply_text_and_done_flag_come_from_the_session_result(tmp_path, repo, private_root, raw, text, done):
    """Adversarial where: a done flag taken from truthiness ends the build when
    the model wrote the string "false"; a result that is not the agreed JSON
    must still come back as text, never raise or end the build."""
    who, _, _ = make(tmp_path, repo, private_root, [raw])

    reply = who.reply("Approve?")

    assert (reply.text, reply.done) == (text, done)
    assert reply.outcome == "done"


@pytest.mark.parametrize(
    "scripted, outcome",
    [({"limit": True}, "usage-limit"), ({"crash": True}, "failed")],
    ids=["usage-limit", "crash"],
)
def test_a_session_that_ends_badly_reports_its_outcome_without_a_done_flag(
    tmp_path, repo, private_root, scripted, outcome
):
    """Adversarial where: a human that crashes or hits the limit must not
    report done (the driver would stop the build as finished) and must not
    raise; the outcome tells the driver which halt it is."""
    who, _, _ = make(tmp_path, repo, private_root, [scripted])

    reply = who.reply("Approve?")

    assert reply.outcome == outcome
    assert reply.done is False
    assert [r["outcome"] for r in read_records(private_root)] == [outcome]


def test_readme_reaches_the_prompt_only_in_the_compass_arm(tmp_path, repo, private_root):
    """Adversarial where: the baseline arm's human knowing Compass commands (or
    the Compass arm's not knowing them) changes how the two arms are
    answered, so the difference would not be only Compass."""
    marker = "README-MARKER /compass:build runs the builder"
    compass, compass_cmd, _ = make(tmp_path, repo, private_root, [say("x")], arm="compass", readme=marker, name="c")
    baseline, baseline_cmd, _ = make(
        tmp_path, repo, private_root, [say("x")], arm="baseline", readme=marker, name="b", state="state-b.json",
    )

    compass.reply("Approve?")
    baseline.reply("Approve?")

    assert marker in prompts(compass_cmd)[0]
    assert marker not in prompts(baseline_cmd)[0]
