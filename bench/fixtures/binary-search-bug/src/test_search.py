from search import binary_search


def test_finds_first():
    assert binary_search([1, 2, 3, 4, 5], 1) == 0


def test_finds_middle():
    assert binary_search([1, 2, 3, 4, 5], 3) == 2


def test_finds_last():
    assert binary_search([1, 2, 3, 4, 5], 5) == 4


def test_missing_returns_minus_one():
    assert binary_search([1, 2, 3, 4, 5], 6) == -1


def test_empty():
    assert binary_search([], 1) == -1
