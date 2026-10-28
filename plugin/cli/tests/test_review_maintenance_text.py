"""Tests for the text that runs the approval points of `/compass:consolidate`
and `/compass:vault-health`: with a review surface (a markdown editor set up to
receive reviews) the structure proposal and the bulk fix reach the human as a
document sent through `compass review`; without one, the `AskUserQuestion`
gates hold.

Adversarial themes: an approval point that stays `AskUserQuestion`-only, a
review branch that replaces the fallback instead of sitting beside it, a
proposal with no per-folder checkbox or no meaning for an unticked box, a
proposal written somewhere other than `.compass/tmp/proposals/`, a proposal
with no before-and-after picture or "You decide" callout, and an edit that
grows an always-loaded skill file."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CONSOLIDATE = REPO / "plugin" / "skills" / "consolidate" / "SKILL.md"
VAULT_HEALTH = REPO / "plugin" / "skills" / "vault-health" / "SKILL.md"

# Line counts of the two skill files before the review branch was added: an
# edit may add at most ten lines beyond what it removes.
LINES_BEFORE = {CONSOLIDATE: 196, VAULT_HEALTH: 82}
ALLOWED_GROWTH = 10

# A phrase that qualifies text as belonging to the case with no review surface.
NO_SURFACE = r"without a review surface|no review surface|not configured|otherwise|fallback"
WITH_SURFACE = r"review surface"


def read(path):
    return path.read_text(encoding="utf-8")


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


def blocks(text):
    """Blank-line separated blocks, whitespace squashed and lowercased."""
    return [squash(b) for b in re.split(r"\n\s*\n", text) if b.strip()]


def has_block(text, *patterns):
    return any(all(re.search(p, b) for p in patterns) for b in blocks(text))


class ReviewMaintenanceTextTest(unittest.TestCase):
    def test_each_skill_sends_its_approval_for_review_and_keeps_the_ask_fallback(self):
        """Adversarial where: a skill still takes its approval only through
        `AskUserQuestion`, or it swaps the question for the review and loses
        the gate that holds when no review surface is configured, or the
        review is described with no condition on a surface being set."""
        for name, path in (("consolidate", CONSOLIDATE), ("vault-health", VAULT_HEALTH)):
            body = read(path)
            with self.subTest(skill=name):
                self.assertTrue(
                    has_block(body, r"compass review", WITH_SURFACE),
                    "no block sends the approval through compass review when a surface is set",
                )
                self.assertTrue(
                    has_block(body, r"askuserquestion", NO_SURFACE),
                    "the AskUserQuestion gate is not tied to the case without a review surface",
                )
                self.assertIn("(Recommended)", body, "the recommended-option rule left the gate")

    def test_consolidate_proposal_is_a_draft_with_a_checkbox_per_folder(self):
        """Adversarial where: the structure proposal lands outside
        `.compass/tmp/proposals/`, has no checkbox per proposed folder, gives
        an unticked box no meaning (the human cannot leave one folder's files
        flat while approving the rest), or gives a written note no meaning."""
        body = read(CONSOLIDATE)
        self.assertIn(".compass/tmp/proposals/", body, "the proposal's place is not named")
        self.assertTrue(
            has_block(body, r"checkbox|check box|tick", r"folder"),
            "no checkbox per proposed folder",
        )
        self.assertTrue(
            has_block(body, r"ticked", r"approv"),
            "a ticked box does not mean the folder is approved",
        )
        self.assertTrue(
            has_block(body, r"unticked|unchecked", r"flat"),
            "an unticked box does not mean the files stay flat",
        )
        self.assertTrue(
            has_block(body, r"\bnote\b", r"revis"),
            "a note does not mean the folder's proposal is revised",
        )

    def test_consolidate_proposal_sections_and_opening(self):
        """Adversarial where: a proposal section omits the files that move,
        the index line that replaces theirs, or the reason, so the human
        approves a folder without seeing what it does; or the document opens
        with no before-and-after picture of the folders or no "You decide"
        callout."""
        body = read(CONSOLIDATE)
        self.assertTrue(
            has_block(body, r"section", r"files", r"index line", r"reason"),
            "no block names the folder, files, index line and reason of a proposal section",
        )
        self.assertTrue(
            has_block(body, r"before", r"after", r"picture|diagram|mermaid"),
            "no picture of the folders before and after",
        )
        self.assertIn("You decide", body, "the proposal has no You decide callout")

    def test_vault_health_bulk_fix_is_a_document_listing_each_file_and_change(self):
        """Adversarial where: the bulk fix is approved through a one-line
        "Apply fix all N files?" question with no document naming which file
        gets which change, so the human approves a count, not the edits."""
        body = read(VAULT_HEALTH)
        self.assertTrue(
            has_block(body, r"document", r"each file", r"change", r"compass review"),
            "no block sends a document listing each file and its change through compass review",
        )

    def test_no_edited_skill_grows_beyond_its_line_ceiling(self):
        """Adversarial where: the review branch is described by adding text on
        top of the question text it sits beside, growing skill files by more
        than ten lines."""
        for path, before in LINES_BEFORE.items():
            ceiling = before + ALLOWED_GROWTH
            with self.subTest(file=path.parent.name, ceiling=ceiling):
                self.assertLessEqual(len(read(path).splitlines()), ceiling)


if __name__ == "__main__":
    unittest.main()
