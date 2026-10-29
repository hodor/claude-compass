"""Tests for the writing rules the obsidian skill teaches and the one pointer
line the pipeline rules carry: the five callout types, the byte rule, the
agreed plain words, the decision and embed forms, and the pipeline rules'
line budget.

Adversarial themes: a rule that names a sixth callout type, a vocabulary table
that lost rows, a pointer that grew the always-loaded rules file."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "plugin" / "skills" / "obsidian" / "SKILL.md"
PIPELINE = REPO / "plugin" / "templates" / "rules" / "compass-pipeline.md"
WORDS = REPO / ".compass" / "research" / "human-surface" / "RESEARCH-plain-words-mockup.md"

GITHUB_CALLOUTS = {"note", "tip", "important", "warning", "caution"}
# The pipeline rules' line budget: the writing forms live in the obsidian
# skill, and the always-loaded rules point to it within this many lines.
PIPELINE_MAX_LINES = 141


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


def blocks(text):
    """Blank-line separated blocks, whitespace squashed and lowercased."""
    return [squash(b) for b in re.split(r"\n\s*\n", text) if b.strip()]


def has_block(text, *patterns):
    return any(all(re.search(p, b) for p in patterns) for b in blocks(text))


def section(text, heading):
    """The body under a `## heading`, up to the next `## ` heading."""
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def line_count(path):
    return len(path.read_text(encoding="utf-8").splitlines())


def say_instead_phrases():
    """Plain phrases from the third column of the mockup's Terms table,
    skipping rows settled as `keep`."""
    text = WORDS.read_text(encoding="utf-8")
    section = text.split("## Terms", 1)[1].split("\n## ", 1)[0]
    phrases = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[2].lower().startswith("keep") or set(cells[2]) <= set("-: "):
            continue
        if cells[2].lower() == "say instead":
            continue
        for piece in re.split(r",\s+|;\s+", cells[2]):
            head = piece.split(":")[0].strip().strip("`")
            if head:
                phrases.append((cells[0], head))
    return phrases


class WritingRulesTest(unittest.TestCase):
    def test_skill_names_the_five_github_callout_types_and_no_other(self):
        """Adversarial where: the skill teaches an Obsidian-only callout type
        (`[!info]`, `[!question]`, `[!example]`) that GitHub draws as a plain
        quote, or leaves one of the five GitHub types unnamed."""
        text = SKILL.read_text(encoding="utf-8")
        used = {m.lower() for m in re.findall(r"\[!([A-Za-z][A-Za-z-]*)\]", text)}
        self.assertEqual(used - GITHUB_CALLOUTS, set(), "types beyond the five GitHub draws")
        self.assertEqual(GITHUB_CALLOUTS - used, set(), "GitHub types the skill never names")

    def test_skill_states_the_byte_rule(self):
        """Adversarial where: the skill teaches visuals without the cost
        condition, so a picture that adds more bytes than it removes stays
        without the human having chosen it."""
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(
            has_block(text, r"visual", r"bytes?", r"remov", r"\badd", r"human", r"cost"),
            "no block ties a visual to the bytes it removes, adds and the human's choice",
        )

    def test_skill_carries_every_say_instead_word(self):
        """Adversarial where: the skill carries only part of the agreed word
        list, so one coined term keeps reaching the human for lack of its plain
        replacement."""
        phrases = say_instead_phrases()
        self.assertGreaterEqual(len(phrases), 40, "Terms table parse found too few rows")
        skill = squash(SKILL.read_text(encoding="utf-8"))
        for term, plain in phrases:
            with self.subTest(term=term, plain=plain):
                self.assertIn(plain.lower(), skill)

    def test_skill_teaches_the_document_forms(self):
        """Adversarial where: one of the agreed forms is missing from the
        skill (the You decide callout, decisions inside a callout under the
        Decisions heading, citation by heading link, block ids for cited lines
        outside callouts, embed instead of copy), so authors fall back to
        copying sections and citing ids a callout cannot hold."""
        text = SKILL.read_text(encoding="utf-8")
        rows = {
            "you-decide callout": (r"you decide", r"callout"),
            "decisions sit in a callout under the heading": (r"decision", r"callout", r"decisions heading|## decisions"),
            "citation links the heading": (r"\[\[[^\]]*#decisions\]\]",),
            "block id marks a cited line outside a callout": (r"block id", r"\^[a-z0-9-]+", r"outside"),
            "section embedded never copied": (r"!\[\[", r"embed", r"copied|copy"),
            "opening picture": (r"picture", r"spec", r"plan", r"research"),
        }
        for name, patterns in rows.items():
            with self.subTest(form=name):
                self.assertTrue(has_block(text, *patterns), f"no block teaches: {name}")

    def test_skill_keeps_program_read_words_unchanged(self):
        """Adversarial where: the word list is written without the exception,
        so an agent renames a field name, warning code or heading grammar a
        program parses and the file stops validating."""
        text = SKILL.read_text(encoding="utf-8")
        self.assertTrue(
            has_block(text, r"unchanged", r"field name", r"code", r"heading", r"program"),
            "no block says program-read words stay unchanged in their files",
        )

    def test_pipeline_rules_point_to_the_skill_without_growing(self):
        """Adversarial where: the pointer line is added on top of the existing
        text, growing the always-loaded rules file, or lands outside the
        Document Writing section where a writer never meets it."""
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertLessEqual(line_count(PIPELINE), PIPELINE_MAX_LINES, "pipeline rules grew")
        body = section(text, "## Document Writing")
        self.assertRegex(squash(body), r"obsidian")

class AgentViewRulesTest(unittest.TestCase):
    def test_skill_teaches_the_agent_written_view(self):
        """Adversarial where: the skill lets an agent write a view script
        without the folder it must live in, the `view:` property that names it,
        the order of choice (a ready-made view first, an agent's own only for a
        picture none of them draws), or the commit rule that puts the script in
        the review's `git diff` where the human reads it."""
        text = SKILL.read_text(encoding="utf-8")
        rows = {
            "the views folder holds the script": (r"`views/", r"\.js|script"),
            "the view property names the script": (r"`view: views/", r"frontmatter|propert"),
            "a ready-made view comes first": (r"ready-made view", r"agent", r"only|none of them|no ready-made"),
            "the script is committed with the document": (r"script", r"commit", r"document", r"git diff"),
        }
        for name, patterns in rows.items():
            with self.subTest(rule=name):
                self.assertTrue(has_block(text, *patterns), f"no block teaches: {name}")


if __name__ == "__main__":
    unittest.main()
