"""Edge tests for pilot.drive_brief found by reading its name search.

Adversarial themes: names built from tokens that never occur together in the
item's own wording, naming that fails for lists where a valid naming exists,
very long and very short goal lists, common-word names.
"""

import itertools
import random
import re
import time
from types import SimpleNamespace

import human
import pilot

VOCAB = ["export", "report", "csv", "the", "of", "a", "test", "code", "list", "total", "show", "monthly", "to", "and"]


def item(n, text):
    return {"id": f"g{n}", "text": text, "command": None}


def named(brief, message):
    """The ids the simulated human would reveal for `message`."""
    return [i["id"] for i in human.SimulatedHuman.named_items(SimpleNamespace(brief=brief), message)]


def windows(text):
    tokens = [t.lower() for t in re.findall(r"\w+", text)]
    return {
        " ".join(tokens[s:s + size])
        for size in (2, 3, 4)
        for s in range(len(tokens) - size + 1)
    }


def phrase_overlap(first, second):
    return f" {first} " in f" {second} " or f" {second} " in f" {first} "


def a_naming_exists(items):
    options = [sorted(windows(i["text"])) for i in items]
    for combo in itertools.product(*options):
        if all(not phrase_overlap(a, b) for a, b in itertools.combinations(combo, 2)):
            return True
    return False


def test_random_lists_are_named_apart_or_refused_only_when_no_naming_exists():
    """Adversarial where: the backtracking search gives up (or never backtracks)
    on a list that has a valid naming, refusing a goal list the human could
    answer, or returns names that reveal two items at once or none at all."""
    rng = random.Random(20241)
    checked = 0
    for _ in range(150):
        count = rng.randint(1, 3)
        items = [
            item(n, " ".join(rng.choice(VOCAB) for _ in range(rng.randint(2, 6))))
            for n in range(1, count + 1)
        ]
        distinct = len({tuple(re.findall(r"\w+", i["text"].lower())) for i in items}) == count
        try:
            brief = pilot.drive_brief(items, "ctx")
        except ValueError:
            assert not distinct or not a_naming_exists(items), items
            continue
        checked += 1
        names = [i["name"] for i in brief["items"]]
        for entry, name in zip(items, names):
            assert 2 <= len(name.split()) <= 4
            assert named(brief, name) == [entry["id"]], (items, names)
        for first, second in itertools.combinations([n.lower() for n in names], 2):
            assert not phrase_overlap(first, second), (items, names)
    assert checked > 50


def test_each_name_occurs_in_its_own_items_wording():
    """Adversarial where: a name stitched from words on either side of a comma,
    hyphen or apostrophe ('to do' for 'to-do', 'user s' for \"user's\") never
    occurs in what a person writes, so a question quoting the item's own words
    never reveals it."""
    items = [
        item(1, "Support the user's to-do list, with tags (colour coded)."),
        item(2, "Export every note: titles, bodies; and dates."),
        item(3, "Don't lose data when the app crashes - ever."),
    ]
    brief = pilot.drive_brief(items, "ctx")
    for entry, given in zip(items, brief["items"]):
        assert named({"items": [given]}, entry["text"]) == [entry["id"]], given["name"]


def test_nested_texts_get_names_that_do_not_contain_each_other():
    """Adversarial where: 'export report' naming one item while another item's
    name contains it, so one question reveals both goals."""
    items = [
        item(1, "Export report"),
        item(2, "Export report monthly"),
        item(3, "Monthly export report"),
    ]
    brief = pilot.drive_brief(items, "ctx")
    names = [i["name"].lower() for i in brief["items"]]
    assert len(set(names)) == 3
    for first, second in itertools.combinations(names, 2):
        assert not phrase_overlap(first, second), names
    for entry, name in zip(items, names):
        assert named(brief, name) == [entry["id"]]


def test_one_item_two_words_is_named_by_its_whole_text():
    """Adversarial where: the shortest legal list. A list of one two-word item
    refused, or named with a padded or empty name."""
    brief = pilot.drive_brief([item(1, "Print receipts")], "ctx")
    assert [i["name"].lower() for i in brief["items"]] == ["print receipts"]
    assert named(brief, "Do you want me to print receipts?") == ["g1"]


def test_one_item_prefers_a_name_without_filler_words():
    """Adversarial where: a one-item list named 'the project' or 'it is', a
    phrase that sits in almost every question the assistant asks."""
    brief = pilot.drive_brief([item(1, "Keep the project small and fast")], "ctx")
    name = brief["items"][0]["name"].lower()
    assert not set(name.split()) <= {"the", "and", "it", "is", "a", "of", "to"}, name
    assert name not in {"keep the", "the project", "small and"}


def test_thirty_items_sharing_a_template_are_named_apart_in_bounded_time():
    """Adversarial where: thirty goals written from one template give the
    backtracking search an exponential tree; it hangs, or raises for a list
    that has plenty of valid names."""
    colours = [f"colour{n}" for n in range(30)]
    items = [item(n, f"The app must show the {c} report in the main window") for n, c in enumerate(colours, 1)]
    started = time.perf_counter()
    brief = pilot.drive_brief(items, "ctx")
    assert time.perf_counter() - started < 20
    names = [i["name"].lower() for i in brief["items"]]
    assert len(set(names)) == 30
    for entry, name in zip(items, names):
        assert named(brief, name) == [entry["id"]], name


def test_thirty_items_all_built_from_common_words_stay_apart_or_are_refused():
    """Adversarial where: thirty goals made only of words that occur in every
    other goal (the, test, code) make the search run to its node limit; the
    call must come back in bounded time with a valid brief or a ValueError."""
    words = ["the", "test", "code", "run", "all"]
    rng = random.Random(7)
    seen, items = set(), []
    while len(items) < 30:
        text = " ".join(rng.choice(words) for _ in range(6))
        if text not in seen:
            seen.add(text)
            items.append(item(len(items) + 1, text))
    started = time.perf_counter()
    try:
        brief = pilot.drive_brief(items, "ctx")
    except ValueError:
        brief = None
    assert time.perf_counter() - started < 60
    if brief is not None:
        names = [i["name"].lower() for i in brief["items"]]
        for first, second in itertools.combinations(names, 2):
            assert not phrase_overlap(first, second)
