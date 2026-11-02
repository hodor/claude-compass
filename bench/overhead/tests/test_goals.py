"""Tests for goals.py: frozen goal lists and hidden briefs.

The interface is documented at the top of `test_topics.py`.

Adversarial themes: a goal list that can change after a build has started stops
being a fixed target; a build that starts without goals cannot be judged; a goal
session that shares a build's folder, names Compass, or sees another topic
biases the measurement; a half-written goal list passes as complete.
"""

from pathlib import Path

import pytest

import goals
import topic_helpers as helpers
import topics
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)

OTHER_ID = "t-ffffffff"
OTHER_TEXT = "A zzother spreadsheet importer for yearly ledgers"


def goals_reply(**overrides):
    payload = {
        "items": [
            {"text": "It prints a pitch in hertz", "command": "python tuner.py note.wav"},
            {"text": "It rejects a file that is not a wav", "command": None},
            {"text": "It documents its options in the readme"},
        ],
        "brief": "You also want the beat rate between two strings printed",
    }
    payload.update(overrides)
    return helpers.reply_json(payload)


@pytest.fixture
def pool(private_root):
    helpers.write_pool(private_root, [
        helpers.topic_entry(),
        helpers.topic_entry(OTHER_ID, title="Other", description=OTHER_TEXT),
    ])


def write(repo, private_root, fake_reply, topic_id=helpers.TOPIC_ID):
    return goals.write_goals(
        topic_id, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)


def test_write_goals_freezes_items_and_brief_for_the_requested_topic(repo, private_root, fake_reply, pool):
    """Adversarial where: ids that depend on the reply, an optional command field
    that crashes the parse, a brief stored with the items, or a prompt that carries
    another topic or names Compass, break the frozen target."""
    fake_reply.reply(goals_reply())
    result = write(repo, private_root, fake_reply)

    assert [(i["id"], i["text"], i["command"]) for i in result["items"]] == [
        ("g1", "It prints a pitch in hertz", "python tuner.py note.wav"),
        ("g2", "It rejects a file that is not a wav", None),
        ("g3", "It documents its options in the readme", None),
    ]
    assert goals.load_goals(helpers.TOPIC_ID, private_root)["items"] == result["items"]
    assert goals.load_brief(helpers.TOPIC_ID, private_root) == "You also want the beat rate between two strings printed"
    assert "brief" not in goals.load_goals(helpers.TOPIC_ID, private_root)

    (call,) = fake_reply.calls()
    assert helpers.TOPIC_TEXT in call["stdin"]
    assert OTHER_TEXT not in call["stdin"]
    assert "compass" not in call["stdin"].lower()
    assert Path(call["cwd"]).resolve().is_relative_to(private_root.resolve())
    assert not Path(call["cwd"]).resolve().is_relative_to(repo.resolve())
    argv = call["argv"]
    assert argv[argv.index("--model") + 1] == goals.MODEL

    assert [(r["role"], r["outcome"]) for r in helpers.read_records(private_root)] == [("goal", "done")]
    text = helpers.records_text(private_root)
    for secret in ("hertz", "beat rate", "tuner.py", "wav"):
        assert secret not in text


def test_require_goals_blocks_a_build_until_list_and_brief_both_exist(private_root, pool):
    """Adversarial where: a build starting with no goal list, with a list but no
    hidden brief, with a brief but no list, or with only another topic's files
    cannot be judged or answered for."""
    assert issubclass(goals.GoalsMissing, LookupError)

    with pytest.raises(goals.GoalsMissing):
        goals.require_goals(helpers.TOPIC_ID, private_root)

    helpers.write_goal_files(private_root, topic_id=OTHER_ID)
    with pytest.raises(goals.GoalsMissing):
        goals.require_goals(helpers.TOPIC_ID, private_root)

    for missing in ("briefs", "goals"):
        helpers.write_goal_files(private_root)
        (helpers.topics_dir(private_root) / missing / f"{helpers.TOPIC_ID}.json").unlink()
        with pytest.raises(goals.GoalsMissing):
            goals.require_goals(helpers.TOPIC_ID, private_root)

    items = helpers.write_goal_files(private_root)
    assert goals.require_goals(helpers.TOPIC_ID, private_root)["items"] == items


BAD_GOAL_REPLIES = {
    "prose": "no json here",
    "no-items-key": helpers.reply_json({"brief": "b"}),
    "empty-items": goals_reply(items=[]),
    "items-not-a-list": goals_reply(items="one thing"),
    "one-blank-text-of-three": goals_reply(items=[
        {"text": "good one", "command": None}, {"text": "   ", "command": None}, {"text": "good two"}]),
    "text-not-a-string": goals_reply(items=[{"text": "good one"}, {"text": 5}]),
    "command-not-a-string": goals_reply(items=[{"text": "good one", "command": ["a", "b"]}]),
    "blank-brief": goals_reply(brief=" "),
    "missing-brief": helpers.reply_json({"items": [{"text": "good one"}]}),
}


@pytest.mark.parametrize("reply", list(BAD_GOAL_REPLIES.values()), ids=list(BAD_GOAL_REPLIES))
def test_write_goals_rejects_malformed_replies_and_stores_nothing(repo, private_root, fake_reply, pool, reply):
    """Adversarial where: a half-valid reply stored anyway leaves a goal list that
    passes require_goals but cannot be judged."""
    fake_reply.reply(reply)
    with pytest.raises(ValueError):
        write(repo, private_root, fake_reply)
    with pytest.raises(goals.GoalsMissing):
        goals.require_goals(helpers.TOPIC_ID, private_root)
    assert not (helpers.topics_dir(private_root) / "goals" / f"{helpers.TOPIC_ID}.json").exists()
    assert not (helpers.topics_dir(private_root) / "briefs" / f"{helpers.TOPIC_ID}.json").exists()


def test_goals_cannot_be_rewritten_once_frozen(repo, private_root, fake_reply, pool):
    """Adversarial where: a second run that overwrites the list moves the target
    after builds have been measured against it, and pays for a session first."""
    fake_reply.reply(goals_reply())
    write(repo, private_root, fake_reply)
    before = goals.load_goals(helpers.TOPIC_ID, private_root)
    brief = goals.load_brief(helpers.TOPIC_ID, private_root)

    fake_reply.reply(goals_reply(items=[{"text": "something else entirely"}], brief="another brief"))
    with pytest.raises(goals.AlreadyFrozen):
        write(repo, private_root, fake_reply)
    assert len(fake_reply.calls()) == 1
    assert goals.load_goals(helpers.TOPIC_ID, private_root) == before
    assert goals.load_brief(helpers.TOPIC_ID, private_root) == brief


@pytest.mark.parametrize("topic_id", ["t-deadbeef", "", "../topics/pool", "t-0a1b2c3d/../../x"])
def test_unknown_topic_starts_no_session_and_writes_nothing(repo, private_root, fake_reply, pool, topic_id):
    """Adversarial where: an id absent from the pool, or one shaped like a path,
    must be refused before a session runs and never name a file outside goals/."""
    fake_reply.reply(goals_reply())
    with pytest.raises(goals.UnknownTopic):
        write(repo, private_root, fake_reply, topic_id)
    assert issubclass(goals.UnknownTopic, LookupError)
    assert fake_reply.calls() == []
    written = sorted(p.relative_to(private_root).as_posix() for p in private_root.rglob("*") if p.is_file())
    assert written == ["topics/pool.json"]


@pytest.mark.parametrize("mode, status", [("limit", "usage-limit"), ("crash", "failed")])
def test_goal_session_failure_raises_and_stores_nothing(repo, private_root, fake_reply, pool, mode, status):
    """Adversarial where: a usage-limit session read as an empty reply would freeze
    an empty goal list."""
    fake_reply.mode(mode)
    with pytest.raises(topics.SessionError) as raised:
        write(repo, private_root, fake_reply)
    assert raised.value.status == status
    with pytest.raises(goals.GoalsMissing):
        goals.require_goals(helpers.TOPIC_ID, private_root)
    assert [r["outcome"] for r in helpers.read_records(private_root)] == [status]


def test_goal_files_are_refused_inside_a_git_work_tree(repo, tmp_path, git, fake_reply):
    """Adversarial where: goal and brief files under a git work tree can be
    committed by accident; the refusal comes before the session."""
    work_tree = tmp_path / "wt"
    work_tree.mkdir()
    git(work_tree, "init", "-q")
    inside = work_tree / "overhead"
    helpers.write_pool(inside, [helpers.topic_entry()])
    fake_reply.reply(goals_reply())
    with pytest.raises(goals.Refused):
        write(repo, inside, fake_reply)
    assert fake_reply.calls() == []
    assert not (inside / "topics" / "goals").exists()
