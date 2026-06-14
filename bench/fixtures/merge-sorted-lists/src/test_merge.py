import pytest
from merge import merge_sorted_lists


def test_both_empty():
    assert merge_sorted_lists([], []) == []


def test_one_empty():
    assert merge_sorted_lists([], [1, 2, 3]) == [1, 2, 3]
    assert merge_sorted_lists([1, 2, 3], []) == [1, 2, 3]


def test_basic():
    assert merge_sorted_lists([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]


def test_duplicates_within_one():
    assert merge_sorted_lists([1, 1, 2], [3]) == [1, 1, 2, 3]


def test_duplicates_across_lists():
    assert merge_sorted_lists([1, 2, 3], [2, 3, 4]) == [1, 2, 2, 3, 3, 4]


def test_negative_numbers():
    assert merge_sorted_lists([-5, -3, 0], [-4, -1, 2]) == [-5, -4, -3, -1, 0, 2]


def test_long_lists_stay_sorted():
    a = list(range(0, 1000, 2))
    b = list(range(1, 1000, 2))
    result = merge_sorted_lists(a, b)
    assert result == list(range(1000))


def test_preserves_existing_lists():
    a = [1, 3, 5]
    b = [2, 4]
    _ = merge_sorted_lists(a, b)
    assert a == [1, 3, 5]
    assert b == [2, 4]


def test_raises_on_unsorted():
    """Unsorted input violates the precondition; implementation should raise ValueError."""
    with pytest.raises(ValueError):
        merge_sorted_lists([3, 1, 2], [4, 5])
