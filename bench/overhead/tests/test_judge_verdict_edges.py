"""Tests for judge.parse_verdict on shapes a model reply takes when it is almost
right: score spellings, mistyped fields, ill-formed containers and one bad item
among many.

Adversarial themes: a reply that is accepted with a score outside the three
values breaks the counts; a mistyped field that raises a bare TypeError escapes
the callers that catch only InvalidVerdict; a defect hidden among many good
items passes a check that looks only at the first.
"""

import json

import pytest

import judge

IDS = ["g1", "g2", "g3"]


def reply(items):
    return json.dumps({"items": items})


def item(goal_id, score="met", reason="src/app.py shows it"):
    return {"id": goal_id, "score": score, "reason": reason}


GOOD = [item("g1"), item("g2", "partly met"), item("g3", "not met")]


@pytest.mark.parametrize(
    "spelling",
    [
        "Met",
        "MET",
        "Partly met",
        "partly  met",
        " met",
        "met\n",
        "partlymet",
        "not-met",
    ],
)
def test_a_score_in_another_spelling_is_rejected_or_mapped_to_its_own_value(spelling):
    """Adversarial where: a spelling the judge model is likely to produce is
    accepted as-is and stored, so `_counts` fails later on a score outside the
    three, or it is silently mapped to a different score than it names."""
    items = [item("g1", spelling), item("g2"), item("g3")]
    try:
        parsed = judge.parse_verdict(reply(items), IDS)
    except judge.InvalidVerdict:
        return
    assert parsed["g1"]["score"] in judge.SCORES
    assert parsed["g1"]["score"] == spelling.strip().lower().replace("  ", " ")


@pytest.mark.parametrize(
    "field, value",
    [
        ("score", ["met"]),
        ("score", None),
        ("score", True),
        ("score", 1),
        ("score", {"v": "met"}),
        ("id", ["g1"]),
        ("id", {"x": 1}),
        ("id", None),
        ("id", 1),
        ("id", "G1"),
        ("id", " g1"),
        ("id", "g1 "),
        ("reason", 5),
        ("reason", None),
        ("reason", ["why"]),
        ("reason", "   "),
        ("reason", "\n\t"),
        ("reason", ""),
    ],
)
def test_a_mistyped_item_field_raises_invalid_verdict_not_a_bare_error(field, value):
    """Adversarial where: an unhashable or non-string field (a list for the score,
    a dict for the id) raises TypeError out of a set or dict lookup, and a
    near-miss id ("G1", "g1 ") is taken for a goal item."""
    bad = dict(item("g1"), **{field: value})
    with pytest.raises(judge.InvalidVerdict):
        judge.parse_verdict(reply([bad, item("g2"), item("g3")]), IDS)


@pytest.mark.parametrize(
    "items",
    [
        {"g1": "met"},
        "met",
        None,
        3,
        [],
        ["g1"],
        [None],
        [[item("g1")]],
        [item("g1"), "g2", item("g3")],
    ],
)
def test_a_container_of_the_wrong_shape_raises_invalid_verdict(items):
    """Adversarial where: `items` as a dict, a string, a number or a list holding a
    non-object raises AttributeError or TypeError from the parser instead of the
    one error the callers handle."""
    with pytest.raises(judge.InvalidVerdict):
        judge.parse_verdict(reply(items), IDS)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   \n",
        "no json at all",
        '{"items": [',
        '{"items": [{"id": "g1", "score": "met"',
        "[" + json.dumps(item("g1")) + "]",
        '{"items": null}',
        "null",
        "{" * 5000,
        '{"a":' * 3000,
    ],
)
def test_text_that_holds_no_verdict_object_raises_invalid_verdict(text):
    """Adversarial where: an empty, truncated or deeply nested reply surfaces as a
    JSON or recursion error, or an array of items without the wrapping object is
    taken for a verdict."""
    with pytest.raises(judge.InvalidVerdict):
        judge.parse_verdict(text, IDS)


@pytest.mark.parametrize("position", ["first", "middle", "last"])
@pytest.mark.parametrize(
    "defect", ["bad score", "duplicate of the first", "unknown extra", "blank reason"]
)
def test_one_defect_among_many_good_items_is_found_wherever_it_sits(position, defect):
    """Adversarial where: a check that stops at the first few items, or compares
    only counts, misses one bad item among forty well-formed ones (a repeated id
    cancelling a missing one, an extra id padding the count)."""
    ids = [f"g{n}" for n in range(1, 41)]
    items = [item(goal_id) for goal_id in ids]
    slot = {"first": 0, "middle": 20, "last": 39}[position]
    if defect == "bad score":
        items[slot]["score"] = "mostly"
    elif defect == "blank reason":
        items[slot]["reason"] = " "
    elif defect == "duplicate of the first":
        items[slot] = item(ids[0] if slot else ids[1])
    else:
        items.insert(slot, item("g41"))
    with pytest.raises(judge.InvalidVerdict):
        judge.parse_verdict(reply(items), ids)


def test_a_repeated_id_cannot_stand_in_for_a_missing_one():
    """Adversarial where: g1 scored twice and g3 absent has the right number of
    items, so a count check accepts it."""
    items = [item("g1"), item("g2"), item("g1", "not met")]
    with pytest.raises(judge.InvalidVerdict):
        judge.parse_verdict(reply(items), IDS)


def test_extra_item_fields_and_order_do_not_change_the_parsed_scores():
    """Adversarial where: scores keyed by position instead of id, or an unknown
    field on an item (a confidence, a file list), changes or rejects an otherwise
    complete verdict."""
    shuffled = [
        dict(item("g3", "not met"), confidence=0.9),
        item("g1", reason="  padded reason "),
        item("g2", "partly met"),
    ]
    parsed = judge.parse_verdict(
        "Verdict follows.\n```json\n" + reply(shuffled) + "\n```\nDone.", IDS
    )
    assert parsed == {
        "g1": {"score": "met", "reason": "  padded reason "},
        "g2": {"score": "partly met", "reason": "src/app.py shows it"},
        "g3": {"score": "not met", "reason": "src/app.py shows it"},
    }
