"""Edge tests for records.py found by reading its code: how unknown fields and
malformed values are filtered, how a stretch boundary is decided, how model ids
are priced, and which folders count as inside a work tree.

Adversarial themes: any key or string the allowlist does not name must be
ignored, never copied; a malformed count must zero only its own field; the
stretch rule fires on a strict fall, not on equal totals; a prefix price table
must not price a model it does not list; a records folder reached through a
link into a work tree is still inside it.
"""

import calendar
import copy
import json
import os
import random
import re
import subprocess
import sys
import time

import pytest

import fake_claude
import records
from conftest import run_git

MAIN = fake_claude.MAIN_MODEL
SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
KINDS = ("input", "output", "cache_read", "cache_write")


def record(events, private_root, **overrides):
    arguments = {"role": "build", "outcome": "done", "arm": "compass", "plugin_sha": SHA, "private_root": private_root}
    arguments.update(overrides)
    return records.record_session(events, **arguments)


def stable(row):
    return {key: value for key, value in row.items() if key != "recorded_at"}


def records_text(private_root):
    folder = private_root / "records"
    return "".join(path.read_text(encoding="utf-8") for path in folder.glob("*.jsonl")) if folder.exists() else ""


def add_noise(value, rng, secrets, *, inside_model_usage=False):
    """A deep copy of `value` with extra keys carrying `secrets` in every dict."""
    if isinstance(value, list):
        return [add_noise(item, rng, secrets) for item in value]
    if not isinstance(value, dict):
        return value
    noisy = {key: add_noise(item, rng, secrets, inside_model_usage=(key == "modelUsage")) for key, item in value.items()}
    for number in range(rng.randint(1, 3)):
        secret = rng.choice(secrets)
        shape = rng.choice(["text", "list", "number"] if inside_model_usage else ["text", "list", "map", "number"])
        noisy[f"zz_{number}_{secret}"] = {
            "text": secret, "list": [secret, {"nested": secret}], "map": {secret: secret}, "number": 7,
        }[shape]
    return noisy


def test_a_stream_with_unknown_keys_and_non_event_entries_gives_the_same_row_and_leaks_nothing(project, private_root):
    """Metamorphic: adding arbitrary extra keys (carrying distinctive strings) to
    every object of a stream, and non-object entries between its events, must not
    change the row beyond its timestamp.

    Adversarial where: a record built by copying fields from events instead of
    picking allowlisted ones carries any field a later Claude Code version adds,
    and a reader that assumes every entry is an object breaks on one that is not."""
    secrets = ["harpsichord-tuner", "D:/data/secret-project", "/srv/secret-proj", "sk-ant-0123456789"]
    base = fake_claude.events_for("subagent", project)
    expected = stable(record(base, private_root / "base"))
    for seed in range(8):
        rng = random.Random(seed)
        noisy = add_noise(copy.deepcopy(base), rng, secrets)
        for junk in (None, 5, "free text harpsichord-tuner", [1, 2], True):
            noisy.insert(rng.randrange(len(noisy) + 1), junk)
        root = private_root / f"noisy-{seed}"

        row = record(noisy, root)

        assert stable(row) == expected
        text = records_text(root)
        assert not [secret for secret in secrets if secret in text]


MALFORMED_COUNTS = [
    ("negative", -5), ("string", "7"), ("boolean", True), ("null", None), ("list", [3]), ("object", {"a": 3}),
]


@pytest.mark.parametrize("label,bad", MALFORMED_COUNTS, ids=[row[0] for row in MALFORMED_COUNTS])
def test_one_malformed_count_zeroes_that_field_only(label, bad, project, private_root):
    """Adversarial where: validation done per entry rather than per field drops the
    three good counts along with the bad one (or raises), and validation that
    lets `True` through counts a boolean as one token."""
    usage = {"inputTokens": 1000, "outputTokens": bad, "cacheReadInputTokens": 30, "cacheCreationInputTokens": 4}
    events = [fake_claude.init_event("s-1", project),
              {"type": "result", "subtype": "success", "is_error": False, "modelUsage": {MAIN: usage}}]

    row = record(events, private_root)

    assert row["models"] == {MAIN: {"input": 1000, "output": 0, "cache_read": 30, "cache_write": 4}}


def test_a_model_entry_that_is_not_an_object_is_skipped_and_its_neighbour_counted(project, private_root):
    """Adversarial where: one malformed `modelUsage` entry beside a good one must
    not discard the good one."""
    good = {"inputTokens": 9, "outputTokens": 8, "cacheReadInputTokens": 7, "cacheCreationInputTokens": 6}
    events = [fake_claude.init_event("s-1", project),
              {"type": "result", "modelUsage": {fake_claude.SUB_MODEL: "garbage", MAIN: good}}]

    row = record(events, private_root)

    assert row["models"] == {MAIN: {"input": 9, "output": 8, "cache_read": 7, "cache_write": 6}}


STRETCHES = [
    ("equal totals, same session, are one stretch", [(100, 10, 1000, 50), (100, 10, 1000, 50)], (100, 10, 1000, 50)),
    ("one token lower on one kind starts a stretch", [(100, 10, 1000, 50), (100, 10, 999, 50)], (200, 20, 1999, 100)),
    ("one kind falling while the others rise starts a stretch", [(100, 10, 1000, 50), (500, 9, 2000, 90)],
     (600, 19, 3000, 140)),
    ("every kind rising is one stretch", [(100, 10, 1000, 50), (101, 11, 1001, 51)], (101, 11, 1001, 51)),
]


@pytest.mark.parametrize("label,totals,expected", STRETCHES, ids=[row[0] for row in STRETCHES])
def test_a_stretch_starts_on_a_strict_fall_of_any_kind_and_not_on_equal_totals(
    label, totals, expected, project, private_root
):
    """Adversarial where: comparing with `<=` instead of `<` counts a repeated
    result as a new stretch and doubles it; comparing only the sum, or only one
    kind, misses a restart that raised the other kinds."""
    events = [fake_claude.init_event("s-1", project)]
    events += [fake_claude.result_event("s-1", {MAIN: snapshot}) for snapshot in totals]

    row = record(events, private_root)

    assert row["models"] == {MAIN: dict(zip(KINDS, expected))}


def test_a_stretch_without_a_result_event_between_two_initializations_counts_nothing_extra(project, private_root):
    """Adversarial where: an init with a new session id and no result before it
    must not close an empty stretch or drop the totals already gathered."""
    events = [
        fake_claude.init_event("s-1", project),
        fake_claude.result_event("s-1", {MAIN: (10, 1, 100, 5)}),
        fake_claude.init_event("s-2", project),
        fake_claude.init_event("s-3", project),
        fake_claude.result_event("s-3", {MAIN: (4, 1, 8, 2)}),
    ]

    row = record(events, private_root)

    assert row["models"] == {MAIN: {"input": 14, "output": 2, "cache_read": 108, "cache_write": 7}}


UNSAFE_MODEL_IDS = [
    "/srv/secret-project",
    r"D:\data\secret-project",
    "claude-opus-5-5/../../secret",
    "claude-opus-5-5 D:/data/secret-project",
    "claude-opus-5-5\n",
    "Claude-Opus-5-5",
    "claude-\u00f3pus-5-5",
    "harpsichord tuner",
    "",
]


def test_model_ids_outside_the_allowed_shape_are_counted_under_one_placeholder_and_never_stored(project, private_root):
    """Adversarial where: a model id is a key in the row; one holding a path, a
    newline, a space or non-ASCII letters must be replaced by the placeholder
    before it is stored, its tokens still counted, and the placeholder named
    unpriced rather than priced as some other model."""
    usage = {"inputTokens": 3, "outputTokens": 1, "cacheReadInputTokens": 2, "cacheCreationInputTokens": 1}
    events = [fake_claude.init_event("s-1", project),
              {"type": "result", "modelUsage": {model: dict(usage) for model in UNSAFE_MODEL_IDS}}]

    row = record(events, private_root)

    count = len(UNSAFE_MODEL_IDS)
    assert row["models"] == {records.UNKNOWN_MODEL: {"input": 3 * count, "output": count, "cache_read": 2 * count,
                                                     "cache_write": count}}
    assert row["unpriced_models"] == [records.UNKNOWN_MODEL]
    assert row["weighted"] == 0
    text = records_text(private_root)
    assert not [model for model in UNSAFE_MODEL_IDS if model.strip() and model in text]


PRICED = [
    ("claude-opus-5-5", 0.05), ("claude-opus-5-5[1m]", 0.05), ("claude-sonnet-5-5", 0.05),
    ("claude-fable-5-1", 0.025), ("claude-mythos-5-1", 0.025),
    ("claude-opus-4-1-20250805", 0.1), ("claude-sonnet-4-5", 0.1), ("claude-haiku-4-5", 0.1),
]
UNPRICED = ["claude-opus-5-1", "claude-opus-5", "claude-opus", "claude-haiku-3-5", "claude-3-5-haiku",
            "claude-mythos-5-2", "claude-fable-5"]


@pytest.mark.parametrize("model,read_weight", PRICED, ids=[row[0] for row in PRICED])
def test_each_listed_family_is_priced_with_its_own_cache_read_weight(model, read_weight, project, private_root):
    """Adversarial where: the four counts are all different, so a swapped weight
    for any kind, or one family's cache-read weight applied to another, gives a
    different total."""
    usage = {"inputTokens": 3, "outputTokens": 7, "cacheReadInputTokens": 1000, "cacheCreationInputTokens": 11}
    events = [fake_claude.init_event("s-1", project), {"type": "result", "modelUsage": {model: usage}}]

    row = record(events, private_root)

    assert row["weighted"] == pytest.approx(3 + 5 * 7 + read_weight * 1000 + 1.25 * 11)
    assert row["unpriced_models"] == []


@pytest.mark.parametrize("model", UNPRICED)
def test_a_model_next_to_a_listed_family_but_not_in_the_table_adds_no_weight_and_is_named(model, project, private_root):
    """Adversarial where: matching by a short prefix prices an unlisted version
    (`claude-opus-5-1`) at a neighbour's weight; it must add nothing, keep its
    tokens, and appear in `unpriced_models` beside a priced model that still counts."""
    usage = {"inputTokens": 100, "outputTokens": 100, "cacheReadInputTokens": 100, "cacheCreationInputTokens": 100}
    priced = {"inputTokens": 10, "outputTokens": 0, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}
    events = [fake_claude.init_event("s-1", project),
              {"type": "result", "modelUsage": {model: usage, MAIN: priced}}]

    row = record(events, private_root)

    assert row["weighted"] == 10
    assert row["unpriced_models"] == [model]
    assert row["models"][model] == dict.fromkeys(KINDS, 100)


def test_a_session_given_as_a_one_shot_iterator_records_the_same_row_as_a_list(project, private_root):
    """Adversarial where: the events are read in several passes (tokens, version,
    results, durations); an iterator or generator is spent by the first pass and
    the row silently reports no version, no results and no duration."""
    events = fake_claude.events_for("clean", project)

    from_list = record(events, private_root / "list")
    from_iterator = record(iter(events), private_root / "iterator")

    assert stable(from_iterator) == stable(from_list)
    assert from_list["results"] == 1 and from_list["duration_ms"] > 0


PLUGIN_SHAS = [
    ("seven digits", "abcdef1", True), ("six digits", "abcdef", False),
    ("sixty-four digits", "a" * 64, True), ("sixty-five digits", "a" * 65, False),
    ("upper case", "ABCDEF1234", True), ("non-hex letter", "abcdefg", False),
    ("trailing newline", "abcdef1\n", False), ("empty", "", False), ("integer", 1234567, False),
]


@pytest.mark.parametrize("label,sha,accepted", PLUGIN_SHAS, ids=[row[0] for row in PLUGIN_SHAS])
def test_plugin_sha_is_accepted_from_seven_to_sixty_four_hex_digits_and_stored_lower_case(
    label, sha, accepted, project, private_root
):
    """Adversarial where: the length bounds sit exactly at 7 and 64; a regex that
    ends with `$` lets a trailing newline through, and a rejected value must
    leave no records folder behind."""
    events = fake_claude.events_for("clean", project)

    if accepted:
        assert record(events, private_root, plugin_sha=sha)["plugin_sha"] == sha.lower()
    else:
        with pytest.raises(ValueError):
            record(events, private_root, plugin_sha=sha)
        assert not (private_root / "records").exists()


def test_the_timestamp_is_utc_with_a_z_suffix(project, private_root):
    """Adversarial where: stamping local time under a `Z` suffix puts a row hours
    away from its true moment on any machine whose zone is not UTC."""
    before = time.time()

    row = record(fake_claude.events_for("clean", project), private_root)

    stamp = row["recorded_at"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)
    moment = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    assert before - 2 <= moment <= time.time() + 2


def test_a_records_folder_reached_through_a_link_into_a_work_tree_is_refused(tmp_path, project):
    """Adversarial where: the work-tree test looks at the path it is given; a
    private root that is a link (symlink or junction) into a checkout must be
    resolved first, or records land in the checkout and can be committed."""
    checkout = tmp_path / "checkout"
    (checkout / "inner").mkdir(parents=True)
    run_git(checkout, "init", "-q")
    link = tmp_path / "shortcut"
    if sys.platform == "win32":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(checkout / "inner")],
                              capture_output=True, text=True)
        if done.returncode != 0:
            pytest.skip("cannot create a junction")
    else:
        os.symlink(checkout / "inner", link, target_is_directory=True)

    with pytest.raises(records.Refused):
        record(fake_claude.events_for("clean", project), link / "overhead")

    assert not (checkout / "inner" / "overhead").exists()


def test_a_private_root_under_missing_folders_outside_any_work_tree_is_created_and_written(tmp_path, project):
    """Adversarial where: the work-tree walk starts from folders that do not exist
    yet; refusing them, or failing to create the missing parents, stops the first
    record of a fresh machine."""
    root = tmp_path / "fresh" / "a" / "b" / "overhead"

    row = record(fake_claude.events_for("clean", project), root)

    assert json.loads(records_text(root).splitlines()[0])["role"] == row["role"]
