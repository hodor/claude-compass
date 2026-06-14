"""Held-out tests for merge_sorted_lists. Not shown to the agent during the task."""
import sys
import os
import pytest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../../../runs/_arm_under_test/")
from merge import merge_sorted_lists


def test_floats():
    assert merge_sorted_lists([1.0, 2.5, 3.0], [2.0, 4.0]) == [1.0, 2.0, 2.5, 3.0, 4.0]


def test_mixed_int_and_float():
    result = merge_sorted_lists([1, 2.5], [2, 3])
    assert result == [1, 2, 2.5, 3]


def test_very_long_inputs():
    a = list(range(0, 100000, 2))
    b = list(range(1, 100000, 2))
    result = merge_sorted_lists(a, b)
    assert result == list(range(100000))


def test_strings():
    """Strings are sortable - implementation should work."""
    assert merge_sorted_lists(["apple", "cherry"], ["banana", "date"]) == [
        "apple", "banana", "cherry", "date"
    ]


def test_single_element_lists():
    assert merge_sorted_lists([5], [3]) == [3, 5]
    assert merge_sorted_lists([3], [5]) == [3, 5]


def test_all_equal():
    assert merge_sorted_lists([5, 5, 5], [5, 5]) == [5, 5, 5, 5, 5]


def test_unsorted_a_raises():
    with pytest.raises(ValueError):
        merge_sorted_lists([5, 4, 3], [1, 2])


def test_unsorted_b_raises():
    with pytest.raises(ValueError):
        merge_sorted_lists([1, 2], [5, 4, 3])


def test_unsorted_caught_at_boundary():
    """A single inversion at the end must still raise."""
    with pytest.raises(ValueError):
        merge_sorted_lists([1, 2, 3, 0], [4, 5])
