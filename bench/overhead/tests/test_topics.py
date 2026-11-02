"""Tests for topics.py: the pool of agent-picked build topics.

Interface the tests pin (topics.py, goals.py, judge.py)
-------------------------------------------------------
Every session below runs through `launch.run_session` (isolated config, clean
`plugin/` required) from a fresh empty folder under `private_root`, never from
the repository or a build project, and appends one `records.record_session` row
whose role is "topic", "goal" or "judge". A session that ends `failed` or
`usage-limit` also gets its row, then raises `topics.SessionError` (`.status` is
"failed" or "usage-limit"); goals.py and judge.py re-export the same class. Every
function takes the keywords `repo_root`, `private_root=None` (default
`~/.compass/overhead`), `claude_cmd=None`, `parent_env=None`. `Refused` is raised,
before any session starts, when a file it would write sits inside a git work tree.
Each module has a `MODEL` constant and passes `--model <MODEL>` to its sessions.

Private files, all under `<private_root>/topics/`:

    pool.json                {"topics": [entry, ...]}
        entry = {"id": "t-" + 8 hex digits, random, never derived from the title,
                 "form": "seeded" | "unseeded", "seed": int | None,
                 "title": str, "description": str,
                 "kind": str in KINDS, "size": str in SIZES, "language": str in LANGUAGES}
    goals/<topic id>.json    {"topic_id": str, "items": [{"id": "g1", "text": str,
                                                          "command": str | None}, ...]}
    briefs/<topic id>.json   {"topic_id": str, "brief": str}
    verdicts/*.json          one file per judged project (see test_judge.py)

topics.py
    KINDS, SIZES, LANGUAGES                tuples of distinct str, code-defined
    seed_attributes(seed) -> {"kind", "size", "language"}
                                           pure function of the int seed; touches no
                                           global random state
    pick_topic(*, seeded, seed=None, repo_root, ...) -> entry
                                           runs a topic session and appends the entry to
                                           the pool. Seeded needs an int seed (0 is valid)
                                           and puts the attributes of seed_attributes(seed)
                                           in the prompt; the entry carries those
                                           attributes, whatever the reply says. Unseeded
                                           takes kind, size and language from the reply.
                                           The reply holds one JSON object (optionally in a
                                           fenced block) with string fields title,
                                           description, kind, size, language, each
                                           non-blank. A reply that does not parse, lacks a
                                           field, has a blank one, or places an unseeded
                                           pick outside KINDS, SIZES or LANGUAGES raises
                                           ValueError and leaves the pool unchanged.
    load_pool(private_root=None) -> [entry]
    distinct_classes(entries) -> int       number of distinct (kind, language) pairs
    choose_form(entries) -> "seeded" | "unseeded"
                                           the form whose entries fill more distinct
                                           classes; "unseeded" on a tie or no entries
    main(argv, *, claude_cmd=None, repo_root=None, parent_env=None) -> int
                                           `pick --form seeded|unseeded [--seed N]` prints
                                           the topic id; `list` prints the pool's ids one
                                           per line. Seeded without --seed returns 2;
                                           SessionError returns 1.

goals.py
    write_goals(topic_id, *, repo_root, ...) -> {"items": [...], "brief": str}
                                           a goal session, separate from any build, turns
                                           the pool entry into a frozen goal list and a
                                           hidden brief. The reply is one JSON object
                                           {"items": [{"text": str, "command": str|null}],
                                           "brief": str}; ids g1..gN are assigned in order.
                                           ValueError (nothing stored) when items is empty,
                                           any item text is blank or the brief is blank.
    load_goals(topic_id, private_root=None) -> {"topic_id", "items"}
    load_brief(topic_id, private_root=None) -> str
    require_goals(topic_id, private_root=None) -> goal dict
                                           raises GoalsMissing (a LookupError) unless the
                                           goal list and the brief both exist
    UnknownTopic (LookupError), AlreadyFrozen (Exception)

judge.py
    judge_project(project, topic_id, *, repo_root, builder_tests=None,
                  validator_verdict=None, command_timeout=60, ...) -> verdict dict
                                           see test_judge.py
    make_copy(project, dest) -> Path
    parse_verdict(text, goal_ids) -> {id: {"score", "reason"}}   raises InvalidVerdict
"""

import os
import random
import re
from pathlib import Path

import pytest

import topic_helpers as helpers
import topics
from fake_reply_claude import fake_reply  # noqa: F401  (pytest fixture)

ID_SHAPE = re.compile(r"t-[0-9a-f]{8}")


def pick_reply(**overrides):
    payload = {
        "title": "Quuxlathe synth",
        "description": "A zzquux wavetable synthesiser driven from the terminal",
        "kind": topics.KINDS[0],
        "size": topics.SIZES[0],
        "language": topics.LANGUAGES[0],
    }
    payload.update(overrides)
    return payload


def under(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return True


def test_seed_attributes_are_pure_members_and_reach_every_value():
    """Adversarial where: a seed that drifts between calls, borrows the global
    random state, or can never reach some listed value makes the seeded pool
    unreplayable or biased."""
    for values in (topics.KINDS, topics.SIZES, topics.LANGUAGES):
        assert len(values) >= 2
        assert len(set(values)) == len(values)
        assert all(isinstance(v, str) and v.strip() for v in values)

    first = topics.seed_attributes(41)
    random.seed(99)
    random.random()
    assert topics.seed_attributes(41) == first

    random.seed(5)
    expected = random.random()
    random.seed(5)
    topics.seed_attributes(3)
    assert random.random() == expected

    seen = {"kind": set(), "size": set(), "language": set()}
    for seed in range(400):
        attrs = topics.seed_attributes(seed)
        assert set(attrs) == {"kind", "size", "language"}
        assert attrs["kind"] in topics.KINDS
        assert attrs["size"] in topics.SIZES
        assert attrs["language"] in topics.LANGUAGES
        for name, value in attrs.items():
            seen[name].add(value)
    assert seen["kind"] == set(topics.KINDS)
    assert seen["size"] == set(topics.SIZES)
    assert seen["language"] == set(topics.LANGUAGES)


def test_pick_topic_builds_entries_for_both_forms(repo, private_root, fake_reply):
    """Adversarial where: a seeded pick that ignores its seed, treats seed 0 as
    missing, lets the reply override the seeded classes, or an unseeded pick that
    leaks the seed into the entry, breaks the replayable pool."""
    fake_reply.reply(helpers.reply_json(pick_reply(kind=topics.KINDS[-1])))
    common = dict(repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)

    unseeded = topics.pick_topic(seeded=False, **common)
    assert ID_SHAPE.fullmatch(unseeded["id"])
    assert unseeded["form"] == "unseeded"
    assert unseeded["seed"] is None
    assert unseeded["title"] == "Quuxlathe synth"
    assert unseeded["kind"] == topics.KINDS[-1]

    for seed in (0, 17):
        attrs = topics.seed_attributes(seed)
        before = len(fake_reply.calls())
        entry = topics.pick_topic(seeded=True, seed=seed, **common)
        prompt = fake_reply.calls()[before]["stdin"]
        assert entry["form"] == "seeded"
        assert entry["seed"] == seed
        assert {k: entry[k] for k in ("kind", "size", "language")} == attrs
        for value in attrs.values():
            assert value in prompt, f"seed {seed}: {value!r} missing from the prompt"

    first_prompt = fake_reply.calls()[1]["stdin"]
    topics.pick_topic(seeded=True, seed=0, **common)
    assert fake_reply.calls()[-1]["stdin"] == first_prompt

    assert [e["id"] for e in topics.load_pool(private_root)] == [e["id"] for e in helpers.read_pool(private_root)]
    assert helpers.read_pool(private_root)[0]["id"] == unseeded["id"]
    with pytest.raises(ValueError):
        topics.pick_topic(seeded=True, **common)
    assert len(helpers.read_pool(private_root)) == 4


def test_pick_session_is_isolated_and_recorded_without_content(repo, private_root, fake_reply, monkeypatch):
    """Adversarial where: a topic session started from the repo, with the
    parent's credentials, or without its own model, or a record row carrying the
    picked topic, breaks isolation and privacy."""
    fake_reply.reply(helpers.reply_json(pick_reply()))
    parent = {**os.environ, "ANTHROPIC_API_KEY": "sk-should-not-travel"}
    topics.pick_topic(
        seeded=False, repo_root=repo, private_root=private_root,
        claude_cmd=fake_reply.command, parent_env=parent)

    (call,) = fake_reply.calls()
    assert under(call["cwd"], private_root)
    assert not under(call["cwd"], repo)
    assert call["listing"] == []
    assert call["env"]["CLAUDE_CONFIG_DIR"] == str(private_root / "claude-config")
    assert "ANTHROPIC_API_KEY" not in call["env"]
    argv = call["argv"]
    assert argv[argv.index("--model") + 1] == topics.MODEL

    rows = helpers.read_records(private_root)
    assert [(r["role"], r["outcome"]) for r in rows] == [("topic", "done")]
    text = helpers.records_text(private_root)
    for secret in ("Quuxlathe", "zzquux", "wavetable"):
        assert secret not in text


def without(field):
    payload = pick_reply()
    del payload[field]
    return helpers.reply_json(payload)


BAD_REPLIES = {
    "prose": "no json here at all",
    "array": "[1, 2, 3]",
    "truncated": '{"title": "cut off", "description": ',
    "missing-language": without("language"),
    "missing-description": without("description"),
    "blank-title": helpers.reply_json(pick_reply(title="   ")),
    "non-string-title": helpers.reply_json(pick_reply(title=7)),
    "kind-outside": helpers.reply_json(pick_reply(kind="no-such-kind")),
    "size-outside": helpers.reply_json(pick_reply(size="no-such-size")),
    "language-outside": helpers.reply_json(pick_reply(language="no-such-language")),
}


@pytest.mark.parametrize("reply", list(BAD_REPLIES.values()), ids=list(BAD_REPLIES))
def test_pick_topic_rejects_malformed_replies_and_keeps_the_pool(repo, private_root, fake_reply, reply):
    """Adversarial where: a reply with one bad field among good ones, or a pick
    placed outside the code-defined classes, must not land in the pool and must
    not erase what the pool already holds."""
    existing = helpers.topic_entry(note="kept")
    helpers.write_pool(private_root, [existing])
    fake_reply.reply(reply)
    with pytest.raises(ValueError):
        topics.pick_topic(seeded=False, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)
    assert helpers.read_pool(private_root) == [existing]


@pytest.mark.parametrize("mode, status", [("limit", "usage-limit"), ("crash", "failed"), ("error", "failed")])
def test_pick_topic_raises_session_error_and_keeps_the_pool(repo, private_root, fake_reply, mode, status):
    """Adversarial where: a usage-limit or crashed session must stop the pick with
    its status, not be read as an empty reply, and its tokens still get a row."""
    helpers.write_pool(private_root, [helpers.topic_entry()])
    fake_reply.mode(mode)
    with pytest.raises(topics.SessionError) as raised:
        topics.pick_topic(seeded=False, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)
    assert raised.value.status == status
    assert len(helpers.read_pool(private_root)) == 1
    assert [r["outcome"] for r in helpers.read_records(private_root)] == [status]


def test_pool_is_refused_inside_a_git_work_tree(repo, tmp_path, git, fake_reply):
    """Adversarial where: a pool written under a git work tree can be committed by
    accident; the refusal must come before any session is paid for."""
    work_tree = tmp_path / "wt"
    work_tree.mkdir()
    git(work_tree, "init", "-q")
    inside = work_tree / "overhead"
    fake_reply.reply(helpers.reply_json(pick_reply()))
    with pytest.raises(topics.Refused):
        topics.pick_topic(seeded=False, repo_root=repo, private_root=inside, claude_cmd=fake_reply.command)
    assert fake_reply.calls() == []
    assert not (inside / "topics" / "pool.json").exists()


def test_pool_appends_with_distinct_random_ids(repo, private_root, fake_reply):
    """Adversarial where: ids derived from the title, or an append that rewrites
    the pool, make topics collide or lose earlier picks."""
    fake_reply.reply(helpers.reply_json(pick_reply(title="Identical title for every pick")))
    ids = []
    for _ in range(8):
        ids.append(topics.pick_topic(
            seeded=False, repo_root=repo, private_root=private_root, claude_cmd=fake_reply.command)["id"])
    assert len(set(ids)) == 8
    assert [e["id"] for e in helpers.read_pool(private_root)] == ids
    assert not any("identical" in i or "title" in i for i in ids)


def entry_in(form, kind, language, size="small"):
    return helpers.topic_entry(form=form, kind=kind, language=language, size=size)


CHOOSE_ROWS = {
    "empty": ([], 0, "unseeded"),
    "size-is-not-a-class": ([entry_in("seeded", "game", "go", s) for s in ("small", "large")], 1, "seeded"),
    "language-splits": ([entry_in("seeded", "game", "go"), entry_in("seeded", "game", "rust")], 2, "seeded"),
    "tie-goes-unseeded": ([entry_in("seeded", "game", "go"), entry_in("unseeded", "cli", "go")], 2, "unseeded"),
    "many-in-one-class-lose": (
        [entry_in("unseeded", "cli", "go")] * 10 + [entry_in("seeded", "cli", "go"), entry_in("seeded", "game", "go")],
        2, "seeded"),
    "unseeded-wins": (
        [entry_in("unseeded", "cli", "go"), entry_in("unseeded", "game", "go"), entry_in("seeded", "cli", "go")],
        2, "unseeded"),
}


@pytest.mark.parametrize("entries, classes, form", list(CHOOSE_ROWS.values()), ids=list(CHOOSE_ROWS))
def test_choose_form_counts_distinct_kind_and_language_classes(entries, classes, form):
    """Adversarial where: counting entries instead of distinct (kind, language)
    classes, counting size as a class, or breaking the tie toward seeded, picks the
    wrong pool form (ruling 2)."""
    assert topics.distinct_classes(entries) == classes
    assert topics.choose_form(entries) == form


def test_cli_pick_and_list(repo, private_root, fake_reply, capsys):
    """Adversarial where: the command line printing topic text instead of the id,
    accepting a seeded pick with no seed, or reporting success after a failed
    session."""
    fake_reply.reply(helpers.reply_json(pick_reply()))
    common = dict(claude_cmd=fake_reply.command, repo_root=repo)

    assert topics.main(["pick", "--form", "unseeded"], **common) == 0
    printed = capsys.readouterr().out.strip()
    (entry,) = helpers.read_pool(private_root)
    assert printed == entry["id"]

    assert topics.main(["pick", "--form", "seeded"], **common) == 2
    capsys.readouterr()
    assert len(helpers.read_pool(private_root)) == 1

    assert topics.main(["pick", "--form", "seeded", "--seed", "0"], **common) == 0
    capsys.readouterr()
    assert topics.main(["list"], **common) == 0
    assert capsys.readouterr().out.split() == [e["id"] for e in helpers.read_pool(private_root)]

    fake_reply.mode("limit")
    assert topics.main(["pick", "--form", "unseeded"], **common) == 1
