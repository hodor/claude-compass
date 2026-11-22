"""Tests for `planlib.task_complexity`, the reader of a task line's
`complexity:` letter. Adversarial themes: the letter is taken from the wrong
place (a prefix of a longer letter, a stray word in the description), a
missing field is invented as a letter, and the id capture of `TASK_LINE`
shifts while the letter reader is added."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import planlib  # noqa: E402

# A real detailed line of a plan: the letter sits between the description and
# a trailing field list that carries commas, brackets and a lesson citation.
REAL_LINE = (
    "- [ ] TASK-345: The builder's review attributed. `token_profile.py` reads "
    "`parentAgentId` from each subagent's `.meta.json` - complexity: S, "
    "depends_on: none, files: [bench/overhead/token_profile.py, "
    "bench/overhead/tests/test_token_profile.py]"
)


class TaskComplexityTests(unittest.TestCase):
    def test_letter_per_line_shape(self):
        """Adversarial where: a line shape moves the letter out of reach of the
        reader. One behavior (`task_complexity` returning the letter as
        written, or None), one row per shape: letter mid-line before a comma,
        letter last on the line, field absent, `XS` (whose tail is the valid
        letter `S`), a checked and indented line, trailing whitespace, a
        description that merely says the word complexity, and an empty value."""
        rows = {
            "mid-line before a comma": (
                "- [ ] TASK-101: do a thing - complexity: M, depends_on: none, files: [a.py]", "M"),
            "last on the line": (
                "- [ ] TASK-102: do a thing - depends_on: none, complexity: M", "M"),
            "field absent": (
                "- [ ] TASK-103: do a thing - depends_on: none, files: [a.py]", None),
            "XS is kept whole, not read as S": (
                "- [ ] TASK-104: do a thing - complexity: XS, depends_on: none", "XS"),
            "XS last on the line": (
                "- [ ] TASK-105: do a thing - complexity: XS", "XS"),
            "L mid-line": (
                "- [ ] TASK-106: do a thing - complexity: L, depends_on: TASK-101", "L"),
            "checked and indented line": (
                "  - [x] TASK-107: do a thing - complexity: L, depends_on: none", "L"),
            "trailing whitespace after the letter": (
                "- [ ] TASK-108: do a thing - complexity: S  ", "S"),
            "the word complexity in the description is no field": (
                "- [ ] TASK-109: Reduce the complexity of the parser - depends_on: none", None),
            "word in the description, real field later": (
                "- [ ] TASK-110: Reduce the complexity of the parser - complexity: S, depends_on: none", "S"),
            "real task line with a long trailing field list": (REAL_LINE, "S"),
        }
        for name, (line, expected) in rows.items():
            with self.subTest(name=name):
                self.assertEqual(planlib.task_complexity(line), expected)

    def test_task_line_id_capture_is_unchanged(self):
        """Adversarial where: adding the letter reader widens `TASK_LINE` so the
        id group swallows the field, or stops matching a line shape it matched
        before. The id capture must stay the bare `TASK-<id>`."""
        rows = {
            "mid-line letter": ("- [ ] TASK-345: x - complexity: M, depends_on: none", "TASK-345"),
            "XS letter": ("- [ ] TASK-346: x - complexity: XS", "TASK-346"),
            "no letter": ("- [ ] TASK-347: x - depends_on: none", "TASK-347"),
            "checked and indented": ("    - [X] TASK-348: x - complexity: L", "TASK-348"),
        }
        for name, (line, expected_id) in rows.items():
            with self.subTest(name=name):
                match = planlib.TASK_LINE.match(line)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), expected_id)


if __name__ == "__main__":
    unittest.main()
