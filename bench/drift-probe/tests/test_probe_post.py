"""Tests for the private helpers of the drift probe seeder and scorer.

Adversarial themes: a line edit that breaks the YAML quoting or the line ending
turns a seeded change into a parse error instead of a detectable edit; a score
bump that mishandles carry or whitespace seeds nothing; catalog controls that do
not alternate between the two watched fields leave one field unguarded; a scorer
keyed on file and line alone credits one reference for another cited on the
same citing line.
"""

import sys
from pathlib import Path

import pytest

PROBE_DIR = Path(__file__).resolve().parent.parent
if str(PROBE_DIR) not in sys.path:
    sys.path.insert(0, str(PROBE_DIR))

import score  # noqa: E402
import seed  # noqa: E402

MARK = seed.EDIT_MARKER


@pytest.mark.parametrize("line, want", [
    ('summary: "abc"', f'summary: "abc{MARK}"'),
    ("summary: 'abc'", f"summary: 'abc{MARK}'"),
    ("summary: abc", f"summary: abc{MARK}"),
    ("summary: abc  ", f"summary: abc{MARK}  "),
    ("summary: abc\r", f"summary: abc{MARK}\r"),
    ('summary: "abc"\r', f'summary: "abc{MARK}"\r'),
    ('summary: "abc"  \r', f'summary: "abc{MARK}"  \r'),
    ('summary: "a: b"', f'summary: "a: b{MARK}"'),
    ("summary: 'it''s'", f"summary: 'it''s{MARK}'"),
])
def test_append_to_value_keeps_quote_whitespace_and_line_ending(line, want):
    """Adversarial where: the marker lands outside a closing quote or after a
    CR, so the seeded line is no longer valid YAML or loses its line ending."""
    assert seed._append_to_value(line) == want


def test_append_to_value_changes_the_line():
    """Adversarial where: an empty-valued line comes back unchanged, so a
    seeded summary edit is a no-op and the item can never be detected."""
    for line in ('summary: ""', "summary:", "summary: x"):
        assert seed._append_to_value(line) != line


@pytest.mark.parametrize("line, want", [
    ("score: 0", "score: 1"),
    ("score: 9", "score: 10"),
    ("score: 99", "score: 100"),
    ("score:   7", "score:   8"),
    ("score: 5 \r", "score: 6 \r"),
    ("score: 5\r", "score: 6\r"),
])
def test_bump_score_increments_and_keeps_spacing(line, want):
    """Adversarial where: a digit carry (9 to 10) or trailing whitespace or CR
    is mishandled, so the bumped score equals the old one or the line shape
    changes."""
    assert seed._bump_score(line) == want


@pytest.mark.parametrize("line", ["score: x", "  score: 3", "score: 3 # note", "scores: 3"])
def test_bump_score_rejects_lines_that_are_not_a_plain_score(line):
    """Adversarial where: a non-score line is edited silently, damaging a lesson
    file the scan reads differently."""
    with pytest.raises(Exception):
        seed._bump_score(line)


def _catalog_item(i, stale, change=None):
    return {"id": f"c{i}", "kind": "catalog", "stale": stale, "change": change,
            "file": "cat.yaml", "line": 0, "score_line": 100 + i, "summary_line": 200 + i}


def test_finalize_catalog_lines_alternates_controls_and_follows_change_for_stale():
    """Adversarial where: controls all watch the same field, or a stale item
    points at the wrong field's line, so the drift record never lands on it."""
    items = [_catalog_item(0, False), _catalog_item(1, True, "summary"),
             _catalog_item(2, False), _catalog_item(3, True, "score"),
             _catalog_item(4, False), _catalog_item(5, False)]
    seed_list = seed.finalize_catalog_lines({"seed": 1, "items": items})
    lines = {item["id"]: item["line"] for item in seed_list["items"]}
    assert lines == {"c0": 100, "c1": 201, "c2": 202, "c3": 103, "c4": 104, "c5": 205}


def test_finalize_catalog_lines_leaves_other_kinds_untouched():
    """Adversarial where: index or ref items get their line overwritten by the
    catalog pass."""
    ref = {"id": "r0", "kind": "ref", "stale": False, "file": "a.md", "line": 7}
    out = seed.finalize_catalog_lines({"seed": 1, "items": [ref]})
    assert out["items"][0]["line"] == 7


def _ref(id_, ref_path, stale=False, line=5):
    return {"id": id_, "kind": "ref", "stale": stale, "change": "shifted" if stale else None,
            "expected_class": "shifted" if stale else None,
            "file": "doc.md", "line": line, "ref_path": ref_path}


def test_score_distinguishes_two_references_on_the_same_citing_line():
    """Adversarial where: records keyed on file and line only credit the stale
    reference for its clean neighbour, or flag the control for its neighbour."""
    seeds = {"items": [_ref("stale", "a/x.py", stale=True), _ref("ctl", "b/y.py")]}
    only_neighbour = [{"file": "doc.md", "line": 5, "ref_path": "b/y.py", "class": "shifted"}]
    result = score.score(seeds, only_neighbour)
    assert (result["detected"], result["missed"], result["false_positives"]) == (0, 1, 1)
    assert result["passed"] is False


def test_score_ignores_ref_path_on_index_and_catalog_items():
    """Adversarial where: an index item carrying a stray ref_path key never
    matches the record the scan emits for it, so it counts as missed."""
    item = {"id": "i0", "kind": "index", "stale": True, "change": "text-edited",
            "expected_class": "changed", "file": ".compass/index.md", "line": 3,
            "ref_path": "ignored.md"}
    record = {"file": ".compass/index.md", "line": 3, "class": "changed"}
    assert score.score({"items": [item]}, [record])["detected"] == 1


def test_score_wrong_class_is_detected_but_not_failed():
    """Adversarial where: a wrong-class report counts as missed (or fails the
    probe), contradicting the documented pass rule."""
    seeds = {"items": [_ref("s", "a/x.py", stale=True)]}
    record = {"file": "doc.md", "line": 5, "ref_path": "a/x.py", "class": "changed"}
    result = score.score(seeds, [record])
    assert (result["detected"], result["wrong_class"], result["passed"]) == (1, 1, True)
    assert result["wrong_class_ids"] == ["s expected shifted got changed"]


def test_score_expected_class_reported_alongside_another_class_is_not_wrong_class():
    """Adversarial where: two records for one item, one of the expected class,
    mark it wrong class because only one record is consulted."""
    seeds = {"items": [_ref("s", "a/x.py", stale=True)]}
    records = [{"file": "doc.md", "line": 5, "ref_path": "a/x.py", "class": "changed"},
               {"file": "doc.md", "line": 5, "ref_path": "a/x.py", "class": "shifted"}]
    assert score.score(seeds, records)["wrong_class"] == 0

