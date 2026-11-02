"""Tests for how the pool, goal and brief files are written, guarded and read,
past the plain cases of test_topics.py and test_goals.py.

Adversarial themes: a write that fails half way must leave either the old file or
none, never a partial or frozen-but-incomplete topic; a refusal inside a git work
tree must leave nothing behind however the folder is reached; a pool or goal file
damaged on disk must stop a build or a pick before money is spent, and as a clean
error; a reply cannot choose the entry's id, form or seed.
"""

import json
import os
import re

import pytest

import goals
import topic_helpers as helpers
import topics
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)

PICK = {
    "title": "Harpsichord tuner",
    "description": "Tunes a harpsichord from a recorded note.",
    "kind": "cli-tool",
    "size": "small",
    "language": "python",
}
GOAL_REPLY = {
    "items": [{"text": "It prints a pitch", "command": "python tuner.py"}],
    "brief": "You want a pitch",
}


def pick_unseeded(repo, private_root, fake_reply):
    return topics.pick_topic(
        seeded=False,
        repo_root=repo,
        private_root=private_root,
        claude_cmd=fake_reply.command,
    )


def freeze(repo, private_root, fake_reply):
    return goals.write_goals(
        helpers.TOPIC_ID,
        repo_root=repo,
        private_root=private_root,
        claude_cmd=fake_reply.command,
    )


def goal_paths(private_root):
    folder = helpers.topics_dir(private_root)
    return (
        folder / "goals" / f"{helpers.TOPIC_ID}.json",
        folder / "briefs" / f"{helpers.TOPIC_ID}.json",
    )


def test_a_failed_pool_replace_leaves_the_earlier_pool_readable(
    repo, private_root, fake_reply, monkeypatch
):
    """Adversarial where: a pool written in place is left truncated when the write
    fails at the last step, losing every earlier pick."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    before = (helpers.topics_dir(private_root) / "pool.json").read_bytes()
    fake_reply.reply(helpers.reply_json(PICK))

    def refuse(*args, **kwargs):
        raise OSError("disk went away")

    monkeypatch.setattr(topics.os, "replace", refuse)
    with pytest.raises(OSError):
        pick_unseeded(repo, private_root, fake_reply)
    assert (helpers.topics_dir(private_root) / "pool.json").read_bytes() == before


def test_an_exclusive_write_that_fails_part_way_leaves_no_file(tmp_path, monkeypatch):
    """Adversarial where: a goal, brief or verdict file created and then written
    leaves an empty or partial file when the write fails; the topic then reads as
    frozen with an unreadable file, for good."""
    target = tmp_path / "out" / "goals.json"
    real_open = open

    class Failing:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._handle.close()
            return False

        def write(self, text):
            self._handle.write(text[:5])
            raise OSError("disk full")

    monkeypatch.setattr(
        topics, "open", lambda *a, **k: Failing(real_open(*a, **k)), raising=False
    )
    with pytest.raises(OSError):
        topics.write_json(target, {"items": list(range(50))}, exclusive=True)
    assert not target.exists()


def test_a_failure_writing_the_goal_list_does_not_freeze_a_half_topic(
    repo, private_root, fake_reply, monkeypatch
):
    """Adversarial where: the brief is stored first and the goal list second, so a
    failure between them leaves a brief with no goal list; `AlreadyFrozen` then
    blocks a retry while `require_goals` blocks every build, for good."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    fake_reply.reply(helpers.reply_json(GOAL_REPLY))
    real = topics.write_json
    calls = []

    def second_write_fails(path, data, exclusive=False):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("disk went away")
        return real(path, data, exclusive=exclusive)

    monkeypatch.setattr(topics, "write_json", second_write_fails)
    with pytest.raises(OSError):
        freeze(repo, private_root, fake_reply)
    monkeypatch.setattr(topics, "write_json", real)

    goal_path, brief_path = goal_paths(private_root)
    assert goal_path.exists() == brief_path.exists()
    frozen = freeze(repo, private_root, fake_reply) if not goal_path.exists() else None
    goals.require_goals(helpers.TOPIC_ID, private_root)
    assert frozen is None or frozen["items"][0]["id"] == "g1"


def make_work_tree(tmp_path, git, how):
    work_tree = tmp_path / "wt"
    work_tree.mkdir()
    if how == "git file":
        (work_tree / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
        return work_tree / "a" / "b" / "overhead"
    git(work_tree, "init", "-q")
    if how == "deep and missing":
        return work_tree / "a" / "b" / "c" / "overhead"
    link = tmp_path / "linked-root"
    try:
        os.symlink(work_tree, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be created here")
    return link / "overhead"


@pytest.mark.parametrize(
    "how", ["deep and missing", "git file", "symlink into the tree"]
)
def test_a_pick_inside_a_work_tree_is_refused_whatever_the_route_and_leaves_nothing(
    tmp_path, repo, git, fake_reply, how
):
    """Adversarial where: a work tree reached through a missing deep path, a `.git`
    file (a linked checkout) or a symbolic link is not recognised, and the pool,
    the sessions folder or a record lands where a commit can pick it up."""
    root = make_work_tree(tmp_path, git, how)
    fake_reply.reply(helpers.reply_json(PICK))
    with pytest.raises(topics.Refused):
        pick_unseeded(repo, root, fake_reply)
    assert fake_reply.calls() == []
    tree = tmp_path / "wt"
    created = [
        p.relative_to(tree).as_posix()
        for p in tree.rglob("*")
        if ".git" not in p.relative_to(tree).parts
    ]
    assert created == []


@pytest.mark.parametrize(
    "text",
    [
        '{"topics": [{"id": "t-0a1b2c3d", "ti',
        "{}",
        '{"topics": "x"}',
        "[]",
        "null",
        "﻿",
    ],
)
def test_a_damaged_pool_stops_a_pick_before_a_session_is_paid_for_and_exits_cleanly(
    repo, private_root, fake_reply, text
):
    """Adversarial where: the pool is read only after the session, so a truncated
    or mis-shaped pool.json costs a paid pick and then raises KeyError or a JSON
    error out of the command line, losing the pick."""
    folder = helpers.topics_dir(private_root)
    folder.mkdir(parents=True)
    (folder / "pool.json").write_text(text, encoding="utf-8")
    fake_reply.reply(helpers.reply_json(PICK))

    code = topics.main(
        ["--private-root", str(private_root), "pick", "--form", "unseeded"],
        claude_cmd=fake_reply.command,
        repo_root=repo,
    )
    assert code == 2
    assert fake_reply.calls() == []
    assert (folder / "pool.json").read_text(encoding="utf-8") == text


def test_a_reply_cannot_choose_the_entrys_id_form_or_seed_and_text_survives_the_file(
    repo, private_root, fake_reply
):
    """Adversarial where: an entry built by merging the reply into the record lets
    the model set its own id, form and seed (a collision with another topic, a
    forged seeded entry), and a non-ASCII title is lost or changed on its way
    through the pool file."""
    title = "Café 日本 \U0001f600 tuner"
    reply = dict(PICK, title=title, id="t-deadbeef", form="seeded", seed=7, extra="x")
    fake_reply.reply(helpers.reply_json(reply))
    entry = pick_unseeded(repo, private_root, fake_reply)

    assert re.fullmatch(r"t-[0-9a-f]{8}", entry["id"]) and entry["id"] != "t-deadbeef"
    assert (entry["form"], entry["seed"]) == ("unseeded", None)
    assert set(entry) == {
        "id",
        "form",
        "seed",
        "title",
        "description",
        "kind",
        "size",
        "language",
    }
    assert topics.load_pool(private_root) == [entry]
    assert topics.load_pool(private_root)[0]["title"] == title


GOAL_FILE_ROWS = {
    "no items key": {"topic_id": helpers.TOPIC_ID},
    "empty items": {"topic_id": helpers.TOPIC_ID, "items": []},
    "items a string": {"topic_id": helpers.TOPIC_ID, "items": "g1"},
    "item without id": {
        "topic_id": helpers.TOPIC_ID,
        "items": [{"text": "a", "command": None}],
    },
    "item without text": {
        "topic_id": helpers.TOPIC_ID,
        "items": [{"id": "g1", "command": None}],
    },
    "a list at the top": [{"id": "g1", "text": "a", "command": None}],
}


@pytest.mark.parametrize("name", sorted(GOAL_FILE_ROWS))
def test_a_goal_file_without_usable_items_blocks_the_build(private_root, name):
    """Adversarial where: the gate checks only that the file parses and the brief
    exists, so a goal file holding no items lets a build start, and the judge then
    fails on a KeyError or scores nothing after the build has been paid for."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    helpers.write_goal_files(private_root)
    goal_path, _ = goal_paths(private_root)
    goal_path.write_text(json.dumps(GOAL_FILE_ROWS[name]), encoding="utf-8")
    with pytest.raises(goals.GoalsMissing):
        goals.require_goals(helpers.TOPIC_ID, private_root)


@pytest.mark.parametrize("kind", ["not utf-8", "a folder", "brief not text"])
def test_an_unreadable_goal_or_brief_file_blocks_the_build(private_root, kind):
    """Adversarial where: bytes that are not UTF-8, a folder in place of the file,
    or a brief that is not text raise UnicodeDecodeError, IsADirectoryError or
    TypeError out of the gate instead of the one error that stops a build."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    helpers.write_goal_files(private_root)
    goal_path, brief_path = goal_paths(private_root)
    if kind == "not utf-8":
        goal_path.write_bytes(b'{"topic_id": "caf\xe9"}')
    elif kind == "a folder":
        brief_path.unlink()
        brief_path.mkdir()
    else:
        brief_path.write_text(
            json.dumps({"topic_id": helpers.TOPIC_ID, "brief": ["a"]}), encoding="utf-8"
        )
    with pytest.raises(goals.GoalsMissing):
        goals.require_goals(helpers.TOPIC_ID, private_root)


def test_goal_items_are_numbered_by_position_and_commands_are_normalised(
    repo, private_root, fake_reply
):
    """Adversarial where: an id or an unknown field supplied by the model reaches
    the frozen item, an empty command string is kept as a command to run, and a
    padded command keeps its padding."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    fake_reply.reply(
        helpers.reply_json(
            {
                "items": [
                    {
                        "id": "zz",
                        "text": "  It prints a pitch  ",
                        "command": "",
                        "weight": 9,
                    },
                    {
                        "id": "g1",
                        "text": "It rejects a bad file",
                        "command": "  python tuner.py bad  ",
                    },
                    {"text": "It has a readme", "command": None},
                ],
                "brief": "  You want a pitch  ",
            }
        )
    )
    result = freeze(repo, private_root, fake_reply)

    assert result["items"] == [
        {"id": "g1", "text": "It prints a pitch", "command": None},
        {"id": "g2", "text": "It rejects a bad file", "command": "python tuner.py bad"},
        {"id": "g3", "text": "It has a readme", "command": None},
    ]
    assert goals.load_goals(helpers.TOPIC_ID, private_root)["items"] == result["items"]
    assert goals.load_brief(helpers.TOPIC_ID, private_root) == "You want a pitch"
