"""Tests for the cross-references the numbered-choices edit leaves behind in the
pipeline rules: the Build line that points at the asking paragraph by section
name instead of repeating it, and the review-surface paragraph that points at
"the paragraph above".

Adversarial themes: a pointer whose target section was renamed or lost, a
shortened line that dropped the no-plan case or the tool name, a pointer
copied into AGENTS.md with its target missing, and an asking paragraph that
lost a clause when the Build copy of it was deleted."""

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hostlib  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
RULES_DIR = REPO / "plugin" / "templates" / "rules"
PIPELINE = RULES_DIR / "compass-pipeline.md"
ASK_HEADING = "## When to Stop and Ask"


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


def section(text, heading):
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def paragraphs(body):
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def ask_paragraph(text):
    for para in paragraphs(section(text, ASK_HEADING)):
        low = squash(para)
        if "askuserquestion" in low and "one question per call" in low:
            return para
    raise AssertionError("no asking paragraph")


def build_bullet(text):
    body = section(text, "## Build")
    for line in body.splitlines():
        if line.startswith("- Builders execute"):
            return line
    raise AssertionError("no Build bullet about builders")


class BuildReferenceTest(unittest.TestCase):
    def pipeline_and_agents_texts(self):
        pipeline = PIPELINE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            hostlib.materialize_dsh_instructions(project, RULES_DIR)
            agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        return {"compass-pipeline.md": pipeline, "AGENTS.md": agents}

    def test_build_bullet_keeps_the_no_plan_case_and_points_at_the_asking_section(self):
        """Adversarial where: the Build bullet is shortened to a pointer but
        loses the no-plan trigger, drops `AskUserQuestion` (so a builder with no
        plan asks in free text), or names a section that no longer exists, so
        the pointer leads nowhere in the always-loaded rules or in the AGENTS.md
        copy dsh loads."""
        for name, text in self.pipeline_and_agents_texts().items():
            with self.subTest(file=name):
                bullet = squash(build_bullet(text))
                self.assertIn("no approved plan", bullet)
                self.assertIn("do not improvise", bullet)
                self.assertIn("`askuserquestion`", bullet)
                self.assertIn("when to stop and ask", bullet)
                self.assertIn(ASK_HEADING, text)

    def test_build_bullet_does_not_restate_the_asking_rules(self):
        """Adversarial where: the pointer is added beside the old restatement
        instead of replacing it, so the one-question rule lives in two places
        that drift apart (the Build copy keeps the old un-numbered wording)."""
        bullet = squash(build_bullet(PIPELINE.read_text(encoding="utf-8")))
        for phrase in ("one question per call", "(recommended)", "\"other\"", "batched"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, bullet)

    def test_asking_paragraph_keeps_every_clause_the_build_copy_used_to_carry(self):
        """Adversarial where: deleting the Build restatement is paired with an
        edit of the asking paragraph that drops a clause only the two together
        used to guarantee: the "Other" free-text escape, the never-batched rule,
        or the wait-for-this-answer rule."""
        block = squash(ask_paragraph(PIPELINE.read_text(encoding="utf-8")))
        rows = {
            "recommended label": '"(recommended)"',
            "free-text escape": 'free-text "other" left open',
            "never batched": "never batched in one message or one call",
            "next question waits": "the next question waits for this answer",
            "one short line each": "one short line",
        }
        for name, needle in rows.items():
            with self.subTest(clause=name):
                self.assertIn(needle, block)

    def test_review_surface_paragraph_still_follows_the_asking_paragraph(self):
        """Adversarial where: the review paragraph says "ask ... as the
        paragraph above describes"; an insertion or reorder between the two
        paragraphs makes "above" name a different paragraph. The review
        paragraph's own gate text (`not configured` fallback, verdict
        handling) must also survive the edit untouched."""
        paras = paragraphs(section(PIPELINE.read_text(encoding="utf-8"), ASK_HEADING))
        ask_index = next(
            i
            for i, p in enumerate(paras)
            if "one question per call" in squash(p) and "askuserquestion" in squash(p)
        )
        review = paras[ask_index + 1]
        low = squash(review)
        self.assertTrue(review.startswith("**Review in a visual surface.**"))
        for needle in (
            "on `not configured`, the gate asks through `askuserquestion` as the paragraph above describes",
            "an approved verdict is the gate's recommended approve option",
            "a changes verdict applies the notes",
            "`compass review --cancel <id>`",
            "a host with no background wake-up runs the command in the foreground",
        ):
            with self.subTest(clause=needle[:40]):
                self.assertIn(needle, low)


if __name__ == "__main__":
    unittest.main()
