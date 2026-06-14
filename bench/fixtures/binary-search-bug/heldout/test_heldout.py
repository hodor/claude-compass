"""Held-out tests for binary_search. Not shown to the agent during the task."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../../../runs/_arm_under_test/")
from search import binary_search


def test_single_element_found():
    assert binary_search([42], 42) == 0


def test_single_element_missing():
    assert binary_search([42], 7) == -1


def test_two_elements_found_first():
    assert binary_search([1, 2], 1) == 0


def test_two_elements_found_second():
    assert binary_search([1, 2], 2) == 1


def test_two_elements_missing():
    assert binary_search([1, 2], 3) == -1
    assert binary_search([1, 2], 0) == -1


def test_index_actually_contains_target():
    """If a duplicate exists, the returned index must contain the target."""
    arr = [1, 2, 2, 2, 3]
    idx = binary_search(arr, 2)
    assert idx != -1
    assert arr[idx] == 2


def test_strings():
    assert binary_search(["alpha", "beta", "gamma"], "beta") == 1
    assert binary_search(["alpha", "beta", "gamma"], "delta") == -1


def test_large_array_found():
    arr = list(range(0, 10000, 3))
    target = 9999
    idx = binary_search(arr, target)
    assert idx == arr.index(target)


def test_large_array_missing():
    arr = list(range(0, 10000, 3))
    assert binary_search(arr, 10001) == -1


def test_negative_numbers():
    assert binary_search([-10, -5, -1, 0, 3], -5) == 1
    assert binary_search([-10, -5, -1, 0, 3], -100) == -1
