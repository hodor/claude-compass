"""Planting never lands inside a string or comment that spans several lines:
a line-by-line reading sees a docstring's inner line as code."""

from pathlib import Path

import ablation
from test_ablation import _commit, _git


PY_SOURCE = '''"""The map grid.

Coordinates run 0-79 across and 0-20 down, x < 80.
"""

HELP = """usage:
  limit < 10 or more
"""


def inside(x, y):
    return 0 <= x < 80 and 0 <= y < 21
'''

GO_SOURCE = '''package grid

/* Bounds: x < 80
   and y < 21 */
const usage = `limit < 10
or more`

// a < b on one line
func Inside(x, y int) bool {
	return x >= 0 && x < 80
}
'''


def test_python_multiline_strings_cover_their_lines():
    covered = ablation.multiline_text_lines(PY_SOURCE, "python")
    assert {1, 2, 3, 4, 6, 7, 8} <= covered
    assert 12 not in covered and 11 not in covered


def test_go_raw_strings_and_block_comments_cover_their_lines():
    covered = ablation.multiline_text_lines(GO_SOURCE, "go")
    assert {3, 4, 5, 6} <= covered
    assert not covered & {1, 8, 9, 10}


def test_a_one_line_string_covers_nothing():
    assert ablation.multiline_text_lines('x = "a < b"\ny = 1\n', "python") == set()
    assert ablation.multiline_text_lines('x := "a < b"\n', "go") == set()


def test_an_untokenizable_python_file_offers_no_line():
    source = 'x = """never closed\ny = 1 < 2\n'
    assert ablation.multiline_text_lines(source, "python") >= {1, 2}


def test_plant_draws_only_from_code_lines(tmp_path):
    repo = tmp_path / "projects" / "proj-dddddd"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "--initial-branch=main")
    plan = "- [x] TASK-001: Grid - complexity: S, files: [grid/core.py]\n"
    _commit(repo, {"pyproject.toml": "", ".compass/plans/PLAN-001-x.md": plan}, "Seed")
    _commit(repo, {"tests/test_core.py": "def test_x():\n    pass\n"},
            "test(TASK-001): failing tests before implementation")
    _commit(repo, {"grid/core.py": PY_SOURCE}, "TASK-001: grid")
    task = ablation.find_tasks(repo)[0]
    for seed in range(12):
        site = ablation.plant(task, tmp_path / ("p%d" % seed), seed=seed, compile_check=lambda d, s: True)
        assert site.line == 12, (seed, site)
        assert site.function == "inside"
