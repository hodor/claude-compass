"""Tests for the text that runs the approval loop of a spec, plan or research
document: with a review surface (a markdown editor set up to receive reviews)
the document itself reaches the human and the terminal says one line; without
one, the plain-text walkthrough and the `AskUserQuestion` gates hold.

Adversarial themes: a chat walkthrough that stays unconditional ahead of the
review branch, a research axes gate with no review-surface branch, a terminal
line that omits the title, id or commit, a changes verdict that never opens
with a "Since your last review" callout, a "You decide" callout that stays in
an approved file, and an edit that grows an always-loaded file."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PIPELINE = REPO / "plugin" / "templates" / "rules" / "compass-pipeline.md"
SPEC_SKILL = REPO / "plugin" / "skills" / "spec" / "SKILL.md"
PLAN_SKILL = REPO / "plugin" / "skills" / "plan" / "SKILL.md"
RESEARCH_SKILL = REPO / "plugin" / "skills" / "research" / "SKILL.md"
PLANNER = REPO / "plugin" / "templates" / "agents" / "planner.md"

# Line counts of the five edited files before the approval-loop change: an
# edit may remove more lines than it adds, never the reverse.
LINE_CEILINGS = {
    PIPELINE: 141,
    SPEC_SKILL: 126,
    PLAN_SKILL: 158,
    RESEARCH_SKILL: 84,
    PLANNER: 172,
}

# A phrase that qualifies text as belonging to the case with no review surface.
NO_SURFACE = r"without a review surface|no review surface|not configured|otherwise|fallback"
SURFACE = r"review surface|compass review|editor"


def read(path):
    return path.read_text(encoding="utf-8")


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


def blocks(text):
    """Blank-line separated blocks, whitespace squashed and lowercased."""
    return [squash(b) for b in re.split(r"\n\s*\n", text) if b.strip()]


def has_block(text, *patterns):
    return any(all(re.search(p, b) for p in patterns) for b in blocks(text))


def section(text, heading, next_heading):
    """The text from `heading` up to the next `next_heading` at the same level."""
    return text.split(heading, 1)[1].split(next_heading, 1)[0]


def gate_sections():
    return {
        "spec": section(read(SPEC_SKILL), "### 7. Present for approval", "\n### "),
        "plan": section(read(PLAN_SKILL), "## New plan", "\n## "),
        "research": section(read(RESEARCH_SKILL), "### 7. The gate", "\n### "),
    }


class ApprovalLoopTextTest(unittest.TestCase):
    def test_each_gate_sends_the_document_for_review_and_keeps_the_ask_fallback(self):
        """Adversarial where: one of the three skills (research is the one that
        has no branch today) sends its gate only through `AskUserQuestion`, or a
        skill swaps the question for the review and loses the fallback that
        holds when no review surface is configured."""
        for name, body in gate_sections().items():
            with self.subTest(skill=name):
                self.assertIn("compass review", body, "gate has no review-surface branch")
                self.assertIn("AskUserQuestion", body, "gate lost its fallback")

    def test_spec_chat_walkthrough_belongs_to_the_case_without_a_surface(self):
        """Adversarial where: step 7 of the spec skill still shows the Problem
        and Desired Outcome in chat before the review branch, so a human with a
        review surface reads the spec twice; or the walkthrough is deleted and
        the plain-text fallback with the guess marked inline goes with it."""
        body = gate_sections()["spec"]
        self.assertTrue(
            has_block(body, r"problem", r"desired outcome", NO_SURFACE),
            "the chat walkthrough is not tied to the case without a review surface",
        )
        self.assertTrue(
            has_block(body, r"guess", r"inline"),
            "the guess marked inline is no longer taught",
        )

    def test_plan_gate_and_planner_template_are_conditional_on_no_surface(self):
        """Adversarial where: the plan skill says the planner "presents it for
        approval" with no surface qualifier, or the planner's step 5 prints the
        full plan template in chat ahead of any statement that a review surface
        carries the plan as its draft file instead."""
        plan_body = gate_sections()["plan"]
        for sentence in re.split(r"(?<=[.!?])\s+", squash(plan_body)):
            if re.search(r"\bpresent\w*\b.*approval", sentence):
                with self.subTest(sentence=sentence[:80]):
                    self.assertRegex(sentence, SURFACE + r"|file|document|" + NO_SURFACE)
        planner_step = section(read(PLANNER), "### 5. Present for approval", "\n### ")
        template_at = planner_step.index("[Full plan content]")
        before_template = squash(planner_step[:template_at])
        self.assertRegex(before_template, NO_SURFACE, "template printed with no no-surface condition before it")

    def test_research_axes_are_a_draft_document_with_questions_and_grading_box(self):
        """Adversarial where: the research gate keeps the axes and the grading
        disclosure as chat text, so the human has nowhere to write his own
        questions, no checkbox for grading, and no meaning for an unticked box."""
        body = gate_sections()["research"]
        self.assertTrue(has_block(body, r"draft", r"research document", r"compass review"), "no draft research document sent for review")
        self.assertIn("Your questions", body, "no Your questions section")
        self.assertTrue(has_block(body, r"checkbox|check box|tick", r"grad"), "no grading checkbox")
        self.assertTrue(has_block(body, r"unticked|unchecked|untick|uncheck", r"refus"), "an unticked box does not mean grading refused")

    def test_pipeline_rules_axes_bullet_names_the_review_surface(self):
        """Adversarial where: the always-loaded research rule tells every
        agent to present the planned axes "in chat" with no mention that a
        review surface carries them as a draft research document."""
        bullets = [l for l in read(PIPELINE).splitlines() if "planned axes" in l]
        self.assertEqual(len(bullets), 1, "expected one rule bullet about the planned axes")
        self.assertRegex(squash(bullets[0]), SURFACE + r"|draft research document")

    def test_a_changes_verdict_returns_a_document_opening_with_since_your_last_review(self):
        """Adversarial where: a revised document goes back for review with no
        change list at the top, so the human re-reads the whole document to
        find what moved. The phrase may live in the shared review rule or in
        every gate."""
        in_rules = "Since your last review" in read(PIPELINE)
        in_every_gate = all("Since your last review" in b for b in gate_sections().values())
        self.assertTrue(in_rules or in_every_gate, "no text opens a returned document with the callout")

    def test_the_you_decide_callout_leaves_the_file_at_approval(self):
        """Adversarial where: nothing in the approval text removes the
        "You decide" callout, so an approved file keeps asking a question it
        has already been answered."""
        pattern = (r"you decide", r"remov|leav|delet|drop", r"approv")
        in_rules = has_block(read(PIPELINE), *pattern)
        in_every_gate = all(has_block(b, *pattern) for b in gate_sections().values())
        self.assertTrue(in_rules or in_every_gate, "no text removes the callout at approval")

    def test_the_terminal_line_names_title_id_and_commit(self):
        """Adversarial where: the one terminal line names the document only by
        file name, or omits the commit, so the human cannot match the review to
        the version he is asked about."""
        body = read(PIPELINE).split("**Review in a visual surface.**", 1)[1].split("\n\n", 1)[0]
        match = re.search(r"one line([^;.]*)", body)
        self.assertIsNotNone(match, "the review rule states no one-line terminal message")
        clause = match.group(1).lower()
        self.assertIn("title", clause)
        self.assertRegex(clause, r"\bid\b|identifier|\b(spec|plan|research)-\d+")
        self.assertIn("commit", clause)

    def test_no_edited_file_grows_beyond_its_line_ceiling(self):
        """Adversarial where: the loop is described by adding text on top of
        the chat walkthroughs it replaces, growing files every session loads."""
        for path, ceiling in LINE_CEILINGS.items():
            with self.subTest(file=path.name, ceiling=ceiling):
                self.assertLessEqual(len(read(path).splitlines()), ceiling)


if __name__ == "__main__":
    unittest.main()
