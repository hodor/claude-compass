"""Tests for records.py: token counting, list-price weights and the private,
allowlisted record rows.

Adversarial themes: a record that carries any session content (topic, prompt,
path, session id, model output) breaks the privacy promise; a running total
summed instead of taken once, or a `/clear` mistaken for a continuation, makes
the overhead share wrong; a record written inside a git work tree can be
committed by accident.
"""

import json
import os
import re
import socket

import pytest

import fake_claude
import records
import sensorlib

MAIN = fake_claude.MAIN_MODEL
SUB = fake_claude.SUB_MODEL
KINDS = ("input", "output", "cache_read", "cache_write")
SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"

ALLOWED_SHAPES = [
    r"[a-z][a-z0-9_\-]*",
    r"claude-[a-z0-9.\-]+(\[[a-z0-9]+\])?",
    r"\d+\.\d+\.\d+",
    r"[0-9a-f]{7,64}",
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?",
]


def as_counts(totals):
    return dict(zip(KINDS, totals))


def read_rows(private_root):
    folder = private_root / "records"
    return [
        json.loads(line)
        for path in sorted(folder.glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def strings_in(value):
    """Every dict key and every string value, at any depth."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from strings_in(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            yield from strings_in(inner)
    elif isinstance(value, str):
        yield value


def record(events, private_root, **overrides):
    arguments = {"role": "build", "outcome": "done", "arm": "compass", "plugin_sha": SHA, "private_root": private_root}
    arguments.update(overrides)
    return records.record_session(events, **arguments)


@pytest.mark.parametrize(
    "name",
    ["clean", "subagent", "multiturn_clear", "limit_event", "limit_api_error", "crash"],
)
def test_a_record_holds_only_allowlisted_shapes_and_no_session_content(name, project, tmp_path, private_root):
    """Adversarial where: the topic, prompt, project path, session ids, tool
    paths and model output all sit in the stream a record is built from; any of
    them reaching a key or a value in the row, even as a fragment of a longer
    string, breaks the privacy promise, and a free-text field that is not one of
    the allowlisted shapes (enum token, model id, version, hex, timestamp) is a
    leak waiting for different input."""
    events = fake_claude.events_for(name, project)
    forbidden = {
        fake_claude.SECRET_TOPIC, "harpsichord", "quux", fake_claude.SECRET_TOOL_PATH,
        fake_claude.SECRET_PROMPT, fake_claude.SECRET_ASSISTANT_TEXT, fake_claude.SECRET_RESULT_TEXT,
        fake_claude.LIMIT_TEXT, "zq81xk", project.name, str(project), project.as_posix(),
        tmp_path.name, str(tmp_path), *fake_claude.SECRET_SESSION_IDS,
    }
    hostname = socket.gethostname()
    if hostname.lower() not in sensorlib.machine_id():
        forbidden.add(hostname)

    row = record(events, private_root)

    persisted = read_rows(private_root)
    assert persisted == [json.loads(json.dumps(row))]
    for text in strings_in(persisted[0]):
        for fragment in forbidden:
            assert fragment.lower() not in text.lower(), (fragment, text)
        assert any(re.fullmatch(shape, text) for shape in ALLOWED_SHAPES), text


def test_records_append_one_row_per_session_to_the_machine_file_and_write_nothing_else(isolated_home):
    """Adversarial where: overwriting instead of appending loses earlier
    sessions, naming the file by the raw host name leaks it, and a debug dump of
    the raw events anywhere in the home folder defeats the allowlist."""
    project = isolated_home / "work"
    first = records.record_session(
        fake_claude.events_for("clean", project), role="build", outcome="done", arm="baseline", plugin_sha=SHA,
    )
    first_line = (isolated_home / ".compass" / "overhead" / "records" / f"{sensorlib.machine_id()}.jsonl").read_text(
        encoding="utf-8"
    )
    second = records.record_session(
        fake_claude.events_for("subagent", project), role="human", outcome="failed",
    )

    files = [p for p in isolated_home.rglob("*") if p.is_file()]
    expected = isolated_home / ".compass" / "overhead" / "records" / f"{sensorlib.machine_id()}.jsonl"
    assert [os.path.normcase(str(p)) for p in files] == [os.path.normcase(str(expected))]
    lines = expected.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] + "\n" == first_line
    assert json.loads(lines[0]) == json.loads(json.dumps(first))
    assert json.loads(lines[1]) == json.loads(json.dumps(second))
    assert first["models"] != second["models"]


def _clear(*segments):
    return lambda cwd: fake_claude.stream_from_segments(list(segments), cwd)


COUNTING = [
    (
        "running totals within a segment are taken once, per model, across a clear",
        lambda cwd: fake_claude.events_for("multiturn_clear", cwd),
        {MAIN: (270, 210, 11600, 400), SUB: (40, 10, 0, 200)},
    ),
    (
        "a total after the clear that exceeds the total before it",
        _clear([{MAIN: (10, 5, 100, 20)}], [{MAIN: (500, 400, 9000, 700)}]),
        {MAIN: (510, 405, 9100, 720)},
    ),
    (
        "three running totals with no clear count the last one only",
        _clear([{MAIN: (10, 5, 100, 20)}, {MAIN: (30, 25, 400, 20)}, {MAIN: (60, 40, 900, 50)}]),
        {MAIN: (60, 40, 900, 50)},
    ),
    (
        "two clears, three segments",
        _clear(
            [{MAIN: (1, 1, 1, 1)}],
            [{MAIN: (20, 2, 200, 2)}, {MAIN: (25, 3, 260, 2)}],
            [{MAIN: (300, 30, 3000, 30)}],
        ),
        {MAIN: (326, 34, 3261, 33)},
    ),
    (
        "a model used only before the clear still counts",
        _clear([{MAIN: (10, 5, 100, 20), SUB: (7, 3, 50, 9)}], [{MAIN: (40, 4, 400, 40)}]),
        {MAIN: (50, 9, 500, 60), SUB: (7, 3, 50, 9)},
    ),
    (
        "identical totals on both sides of a clear are two sets of tokens",
        _clear([{MAIN: (100, 10, 1000, 50)}], [{MAIN: (100, 10, 1000, 50)}]),
        {MAIN: (200, 20, 2000, 100)},
    ),
    (
        "subagent usage comes from modelUsage once, not again from its assistant events",
        lambda cwd: fake_claude.events_for("subagent", cwd),
        {MAIN: (260, 90, 7000, 500), SUB: (60, 20, 0, 400)},
    ),
    (
        "a session that ended with no result event has no counted tokens",
        lambda cwd: fake_claude.events_for("crash", cwd),
        {},
    ),
]


@pytest.mark.parametrize("label,make_events,expected", COUNTING, ids=[row[0] for row in COUNTING])
def test_each_token_is_counted_once_per_model_and_kind(label, make_events, expected, project, private_root):
    """Adversarial where: summing every result event double counts the running
    totals, treating a clear as a continuation drops the segment before it,
    de-duplicating equal totals drops a real segment, and adding assistant-event
    usage on top of modelUsage double counts the subagent and repeated message
    ids."""
    row = record(make_events(project), private_root)

    assert row["models"] == {model: as_counts(totals) for model, totals in expected.items()}
    if not expected:
        assert row["weighted"] == 0


def test_weights_follow_the_list_price_order_of_the_token_kinds(project, private_root):
    """Adversarial where: weighting every token kind alike makes a cache-read
    heavy session look as costly as a fresh-input one; cache reads must weigh
    less than fresh input and cache writes more, with reads still above zero."""
    weighted = {}
    for kind_index, kind in enumerate(KINDS):
        totals = tuple(1000 if i == kind_index else 0 for i in range(4))
        events = fake_claude.stream_from_segments([[{MAIN: totals}]], project)
        weighted[kind] = record(events, private_root)["weighted"]

    assert 0 < weighted["cache_read"] < weighted["input"] < weighted["cache_write"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"role": "build of a harpsichord tuner"},
        {"outcome": "done: harpsichord tuner"},
        {"arm": "compass arm with notes"},
        {"plugin_sha": "harpsichord tuner"},
    ],
    ids=["role", "outcome", "arm", "plugin_sha"],
)
def test_free_text_in_an_enum_field_is_rejected_and_nothing_is_written(overrides, project, private_root):
    """Adversarial where: role, outcome, arm and plugin sha are the only values a
    caller supplies; accepting any string there is a path for topic text into a
    record."""
    with pytest.raises(ValueError):
        record(fake_claude.events_for("clean", project), private_root, **overrides)

    assert not (private_root / "records").exists() or list((private_root / "records").iterdir()) == []


def _repo_with_commit(tmp_path, git, name="inner"):
    root = tmp_path / name
    root.mkdir()
    git(root, "init", "-q")
    git(root, "commit", "-q", "--allow-empty", "-m", "initial")
    return root


@pytest.mark.parametrize("where", ["existing folder", "missing nested folder", "home inside the repo", "linked worktree"])
def test_records_inside_a_git_work_tree_are_refused_and_nothing_is_written(
    where, project, tmp_path, git, monkeypatch
):
    """Adversarial where: the check must resolve the nearest existing ancestor
    when the records folder does not exist yet, honour a default root derived
    from HOME, and recognise a linked worktree whose `.git` is a file."""
    repo = _repo_with_commit(tmp_path, git)
    events = fake_claude.events_for("clean", project)
    if where == "existing folder":
        (repo / "data").mkdir()
        root = repo / "data"
    elif where == "missing nested folder":
        root = repo / "a" / "b" / "c"
    elif where == "linked worktree":
        git(repo, "worktree", "add", "-q", "-b", "wt-branch", str(tmp_path / "linked"))
        root = tmp_path / "linked" / "data"
    else:
        monkeypatch.setenv("HOME", str(repo / "home"))
        monkeypatch.setenv("USERPROFILE", str(repo / "home"))
        root = None

    with pytest.raises(records.Refused):
        records.record_session(events, role="build", outcome="done", private_root=root)

    written = [
        p
        for folder in (repo, tmp_path / "linked")
        if folder.exists()
        for p in folder.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(folder).parts and p.name != ".git"
    ]
    assert written == []
