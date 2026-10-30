"""Tests for the text that makes every choice put to the human a numbered list:
the pipeline rules' asking paragraph, the AGENTS.md section dsh loads from it,
the size budget of the always-loaded rules file, and the option bullets of the
skills and agent templates.

Adversarial themes: a rule that numbers the options but never says a bare
number replies, a rule that leaves the labels free to carry their own number
(so the tool shows it twice), a text form with no `1.` lines, a subagent that
returns its question unnumbered, an AGENTS.md that lost the sentence, and an
option bullet whose label starts with a digit."""

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
SKILLS = sorted((REPO / "plugin" / "skills").glob("*/SKILL.md"))
AGENTS = sorted((REPO / "plugin" / "templates" / "agents").glob("*.md"))

MAX_LINES = 141
MAX_BYTES = 12419
NEGATION = r"\b(no|none|not|never|without|neither|nor|don't|do not)\b"


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


def line_count(path):
    return len(path.read_text(encoding="utf-8").splitlines())


def byte_count(path):
    return len(path.read_bytes())


def sentences(block):
    return re.split(r"(?<=[.!?])\s+", block)


def ask_block(text):
    """The squashed paragraph of the "When to Stop and Ask" section that
    teaches asking through `AskUserQuestion`, one question per call."""
    body = text.split("## When to Stop and Ask", 1)[1].split("\n## ", 1)[0]
    for raw in re.split(r"\n\s*\n", body):
        block = squash(raw)
        if "askuserquestion" in block and re.search(r"one question per call", block):
            return block
    raise AssertionError("no paragraph teaches asking through AskUserQuestion")


def has_sentence(block, *patterns):
    return any(all(re.search(p, s) for p in patterns) for s in sentences(block))


def option_labels(text):
    """Labels of `- **Label...:**` bullets: bold text closed by a colon
    inside the bold span, the form every option bullet takes."""
    return [
        m.group(1).strip() for m in re.finditer(r"(?m)^\s*- \*\*([^*]+?):\*\*", text)
    ]


class NumberedChoicesTextTest(unittest.TestCase):
    def test_asking_paragraph_teaches_the_numbered_choice_concepts(self):
        """Adversarial where: the rule numbers the options but omits one half
        of the contract: the recommended option is not first, a reply of just
        a number is not said to pick it, the labels are left free to carry
        their own number (shown twice beside the tool's), or the text form
        has no `1.` lines for a host without the tool."""
        block = ask_block(PIPELINE.read_text(encoding="utf-8"))
        rows = {
            "options are a numbered list": (r"numbered", r"option|choice|list"),
            "recommended option is first": (
                r"numbered",
                r"recommended",
                r"first|\b1\b|top",
            ),
            "a reply of just a number picks the option": (
                r"reply|answer",
                r"\b(just|only|bare|alone)\b",
                r"number",
                r"pick|select|choos|take",
            ),
            "labels carry no number": (r"\blabels?\b", r"number", NEGATION),
        }
        for name, patterns in rows.items():
            with self.subTest(concept=name):
                self.assertTrue(
                    has_sentence(block, *patterns), f"no sentence teaches: {name}"
                )
        with self.subTest(concept="text form uses 1. lines"):
            self.assertRegex(
                block,
                r"\btext\b.{0,150}1\.[^.]{0,6}2\.|1\.[^.]{0,6}2\..{0,150}\btext\b",
            )

    def test_subagent_sentence_says_the_returned_options_are_numbered(self):
        """Adversarial where: the subagent clause still returns "its options
        and the recommended one marked" with no numbering, so the orchestrator
        asks a numbered question from an unnumbered list and the numbers it
        shows disagree with the ones the subagent wrote."""
        block = ask_block(PIPELINE.read_text(encoding="utf-8"))
        self.assertTrue(
            has_sentence(block, r"subagent", r"option", r"numbered"),
            "the subagent sentence does not say its options are numbered",
        )

    def test_pipeline_rules_stay_within_the_line_and_byte_budget(self):
        """Adversarial where: the numbering rule is added on top of the text it
        sits among, growing the file every session loads; the byte bound is
        checked separately because a long line passes a line count."""
        self.assertLessEqual(line_count(PIPELINE), MAX_LINES)
        self.assertLessEqual(byte_count(PIPELINE), MAX_BYTES)

    def test_dsh_instructions_carry_the_numbered_list_sentence(self):
        """Adversarial where: the rule reaches `.claude/rules` but the AGENTS.md
        section dsh loads (a host with no AskUserQuestion, where every choice
        is text) is built from other text and never says options are numbered."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            hostlib.materialize_dsh_instructions(project, RULES_DIR)
            agents_md = (project / "AGENTS.md").read_text(encoding="utf-8")
        block = ask_block(agents_md)
        self.assertTrue(
            has_sentence(block, r"numbered", r"option|choice|list"),
            "AGENTS.md carries no sentence saying choices are numbered",
        )

    def test_no_option_bullet_label_starts_with_a_digit(self):
        """Adversarial where: a skill or agent writes its options as
        `- **1. Approve:**`, so the tool, which numbers its options, shows the
        number twice. Only `- **Label:**` bullets count; numbered protocol
        steps and bold bullets that close the colon outside the bold do not."""
        found = 0
        for path in SKILLS + AGENTS:
            labels = option_labels(path.read_text(encoding="utf-8"))
            found += len(labels)
            for label in labels:
                with self.subTest(file=f"{path.parent.name}/{path.name}", label=label):
                    self.assertFalse(
                        label[0].isdigit(), "option label starts with a digit"
                    )
        self.assertGreaterEqual(
            found, 20, "the bullet pattern found too few option bullets"
        )


GUIDE = REPO / "plugin" / "skills" / "guide" / "SKILL.md"
GUIDE_MAX_LINES = 87
GUIDE_MAX_BYTES = 4132


def respond_section(text):
    """The body of the guide's "### 2. Respond" step, up to the next step."""
    return text.split("### 2. Respond", 1)[1].split("\n### ", 1)[0]


def situation_entry(section, pattern):
    """The text of the response entry whose bold header line matches `pattern`,
    through to the next bold entry or the end of the section."""
    match = re.search(
        rf"(?ms)^\*\*{pattern}.*?(?=^\*\*|\Z)", section, flags=re.IGNORECASE
    )
    if match is None:
        raise AssertionError(f"no response entry matches {pattern!r}")
    return squash(match.group(0))


class GuideClosingQuestionsTextTest(unittest.TestCase):
    """The guide skill ends its responses with a question; each one goes
    through the tool the pipeline rules number, with the options named."""

    def setUp(self):
        self.text = GUIDE.read_text(encoding="utf-8")

    def test_respond_step_routes_every_closing_question_through_the_tool(self):
        """Adversarial where: the Respond step names `AskUserQuestion` only
        inside the Port entry (it already does), so a check on the whole step
        or file passes while the other entries still end in a free-text
        question; the rule must stand in a paragraph of its own, outside the
        situation entries, saying each response's question uses the tool and
        asks one question per call."""
        section = respond_section(self.text)
        lead = [
            squash(raw)
            for raw in re.split(r"\n\s*\n", section)
            if raw.strip() and not re.match(r"\s*\*\*[A-E]\b", raw)
        ]
        with self.subTest(concept="a paragraph names the tool for every question"):
            self.assertTrue(
                any(
                    has_sentence(
                        block, r"askuserquestion", r"\b(each|every|any|all)\b", r"question"
                    )
                    for block in lead
                ),
                "no paragraph outside the entries says every closing question uses AskUserQuestion",
            )
        with self.subTest(concept="that paragraph says one question per call"):
            self.assertTrue(
                any(
                    "askuserquestion" in block
                    and re.search(r"one question per call", block)
                    for block in lead
                ),
                "no paragraph outside the entries says one question per call",
            )

    def test_vision_without_specs_asks_which_roadmap_item_first(self):
        """Adversarial where: the response still quotes the roadmap into prose
        (`Spec roadmap: [list from vision.md]`) and asks a free-text question,
        or drops the placeholder but never says the roadmap items are the
        options, so the tool is asked with nothing to choose from."""
        self.assertNotIn("[list from vision.md]", self.text.lower())
        entry = situation_entry(
            respond_section(self.text), r"B\b[^\n]*vision but no specs"
        )
        with self.subTest(concept="asks which roadmap item first"):
            self.assertRegex(entry, r"which roadmap item first\s*\?")
        with self.subTest(concept="the roadmap items are the options"):
            self.assertRegex(
                entry, r"roadmap items?\b.{0,80}\boptions?\b|\boptions?\b.{0,80}roadmap items?"
            )

    def test_active_work_asks_what_next_with_the_five_named_options(self):
        """Adversarial where: `list options` is deleted but the five choices
        go with it, or only some survive (here every name is checked, not a
        count), or the entry stops asking what comes next; the phrase must
        be gone from the whole file, not only from the one entry."""
        self.assertNotIn("list options", squash(self.text))
        entry = situation_entry(respond_section(self.text), r"C\b")
        with self.subTest(concept="asks what next"):
            self.assertRegex(entry, r"what\b.{0,20}\bnext\b")
        with self.subTest(concept="the choices are options"):
            self.assertRegex(entry, r"\boptions?\b")
        for name in ("continue building", "validate", "new task", "handoff", "checkup"):
            with self.subTest(option=name):
                self.assertIn(name, entry)

    def test_guide_stays_within_the_line_and_byte_budget(self):
        """Adversarial where: the question lines are added on top of the text
        they sit among, growing a skill loaded on every guide run; the byte
        bound is checked separately because a long line passes a line count,
        and both bounds sit exactly at today's size so one added byte fails."""
        self.assertLessEqual(line_count(GUIDE), GUIDE_MAX_LINES)
        self.assertLessEqual(byte_count(GUIDE), GUIDE_MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
