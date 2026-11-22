"""Structural tests over the consolidate and lesson-write skill text.

The skills tell an agent how a lesson body changes: displaced lines move
verbatim into `## Record (preserved)`, `compass lesson-check` verifies the
edit, a body change reaches a lesson only through a reviewed proposal, and
the catalog is never hand-edited. Each test locates a section by its heading
number and asserts the order of the instructions inside it, not their exact
wording.
"""

import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2] / "skills"
CONSOLIDATE = SKILLS / "consolidate" / "SKILL.md"
LESSON_WRITE = SKILLS / "lesson-write" / "SKILL.md"

RECORD = "Record (preserved)"
LESSON_CHECK = "compass lesson-check"
REVIEW = "compass review"

HEADING = re.compile(r"^(#{1,6})\s", re.MULTILINE)
# A sentence that changes a lesson body: names the body and uses a verb that
# applies a change to it.
APPLY_VERB = re.compile(
    r"\b(appl(?:y|ies|ied)|rewrit\w*|replac\w*|edit\w*|compress\w*|"
    r"distill\w*|overwrit\w*|mov(?:e|es|ed))\b",
    re.IGNORECASE,
)
BODY_NOUN = re.compile(r"\b(body|bodies)\b", re.IGNORECASE)
# Sentences describing the proposal and its gate are not applications.
GATE_WORDS = re.compile(r"proposal|review|tick|checkbox|checked", re.IGNORECASE)


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, number):
    """Body of the heading line starting `<hashes> <number>.`, up to the next
    heading of the same or a higher level, heading line excluded."""
    start = re.search(
        r"^(#{1,6})\s+" + re.escape(number) + r"\.[^\n]*\n", text, re.MULTILINE
    )
    if start is None:
        raise AssertionError(f"no heading numbered {number!r}")
    level = len(start.group(1))
    rest = text[start.end():]
    for nxt in HEADING.finditer(rest):
        if len(nxt.group(1)) <= level:
            return rest[: nxt.start()]
    return rest


def sentences(text):
    flat = re.sub(r"\s+", " ", text)
    return [s.strip() for s in re.split(r"(?<=[.;:!?])\s+", flat) if s.strip()]


class ConsolidateDeltaEditTests(unittest.TestCase):
    def setUp(self):
        self.text = read(CONSOLIDATE)

    def test_lesson_check_follows_the_record_move_in_merge_and_rewrite(self):
        """Adversarial where: the skill names `compass lesson-check` before
        (or without) the sentence moving displaced lines into
        `## Record (preserved)`, so the check would run against an edit not
        yet made; or step 3 (merge) never mentions the Record at all and
        absorbed loser text is dropped."""
        for step in ("3", "4"):
            with self.subTest(step=step):
                body = section(self.text, step)
                record_at = body.find(RECORD)
                check_at = body.find(LESSON_CHECK)
                self.assertNotEqual(record_at, -1, f"step {step} never names {RECORD}")
                self.assertNotEqual(check_at, -1, f"step {step} never names {LESSON_CHECK}")
                self.assertGreater(
                    check_at, record_at, f"step {step}: {LESSON_CHECK} precedes the Record move"
                )
                tail = body[check_at: check_at + 400]
                self.assertRegex(
                    tail, r"(?i)pass", f"step {step}: no fix-until-it-passes instruction"
                )

    def test_review_proposal_precedes_every_body_application(self):
        """Adversarial where: a sentence applying a body change (rewrite,
        compress, move displaced text) sits ahead of the `compass review`
        step, so a body changes before the human has ticked it; or the
        proposal under `.compass/tmp/proposals/` is missing from steps 3 and
        4, or lacks old text, new text, evidence or a checkbox."""
        region = section(self.text, "3") + "\n" + section(self.text, "4")
        review_at = region.find(REVIEW)
        self.assertNotEqual(review_at, -1, f"steps 3 and 4 never name {REVIEW}")
        self.assertIn(".compass/tmp/proposals/", region)
        for needed in ("old", "new", "evidence", "checkbox"):
            self.assertRegex(region, rf"(?i)\b{needed}\b", f"proposal never mentions {needed}")
        self.assertRegex(region, r"(?i)tick|\[x\]|checked", "no applied-only-where-ticked rule")

        for sentence in sentences(region[:review_at]):
            if BODY_NOUN.search(sentence) and APPLY_VERB.search(sentence):
                if not GATE_WORDS.search(sentence):
                    self.fail(f"body change applied before the review step: {sentence!r}")

    def test_drift_report_body_changes_take_the_same_review_path(self):
        """Adversarial where: only consolidation's own edits are gated, and
        a body change prompted by a drift report is applied without a
        proposal."""
        region = section(self.text, "3") + "\n" + section(self.text, "4")
        self.assertRegex(region, r"(?i)drift", "steps 3 and 4 never mention drift reports")


class LessonWriteDeltaEditTests(unittest.TestCase):
    def setUp(self):
        self.text = read(LESSON_WRITE)

    def test_refinement_runs_lesson_check_after_the_edit(self):
        """Adversarial where: 4b never runs `compass lesson-check`, or names
        it ahead of the sentence that edits the body, so a refinement that
        drops text or grows past 5 lines lands unchecked."""
        body = section(self.text, "4b")
        check_at = body.find(LESSON_CHECK)
        self.assertNotEqual(check_at, -1, f"4b never names {LESSON_CHECK}")
        edit = re.search(r"(?i)\bedit", body)
        self.assertIsNotNone(edit, "4b has no edit sentence")
        self.assertGreater(check_at, edit.start())

    def test_recurrence_and_refinement_do_not_hand_edit_the_catalog(self):
        """Adversarial where: 4a still tells the agent to add `escalated` to
        a catalog row, or 4b to edit a row in place, though sync now owns
        every row; or a leftover 'never rewrites' claim contradicts that."""
        for step in ("4a", "4b"):
            with self.subTest(step=step):
                body = section(self.text, step)
                self.assertNotIn("lessons-catalog", body)
                self.assertNotRegex(body, r"(?i)never rewrites")


class DashTests(unittest.TestCase):
    def test_skill_files_carry_no_em_or_en_dash(self):
        """Adversarial where: an edited sentence introduces U+2014 or U+2013,
        which the project forbids in every output."""
        banned = (chr(0x2014), chr(0x2013))
        for path in (CONSOLIDATE, LESSON_WRITE):
            with self.subTest(file=path.parent.name):
                text = read(path)
                for ch in banned:
                    self.assertNotIn(ch, text, f"U+{ord(ch):04X} in {path.parent.name}")


if __name__ == "__main__":
    unittest.main()
