"""Tests for what the guide skill must keep after its closing questions moved
to `AskUserQuestion`: the next-step chain of "After any action", the port
entry's question form, and the entries and frontmatter the rewrite touched
around them.

Adversarial themes: a prose rewrite of a bullet list that silently drops or
reverses a hand-off, a port entry whose tool-use clause lost one of its
parts, and a response entry that kept its question but lost the content
presented before it."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GUIDE = REPO / "plugin" / "skills" / "guide" / "SKILL.md"


def squash(text):
    return re.sub(r"\s+", " ", text).lower()


def step_three(text):
    """The body of "### 3. After any action", up to the next heading."""
    return text.split("### 3. After any action", 1)[1].split("\n## ", 1)[0]


def entry(text, header):
    """The squashed text of the Respond entry whose bold header contains
    `header`, through to the next bold entry, fenced block or step."""
    body = text.split("### 2. Respond", 1)[1].split("\n### ", 1)[0]
    match = re.search(
        rf"(?ms)^\*\*{header}.*?(?=^\*\*|^```|\Z)", body, flags=re.IGNORECASE
    )
    if match is None:
        raise AssertionError(f"no response entry matches {header!r}")
    return squash(match.group(0))


class GuideRetainedContentTest(unittest.TestCase):
    def setUp(self):
        self.text = GUIDE.read_text(encoding="utf-8")

    def test_after_any_action_keeps_every_handoff_in_order(self):
        """Adversarial where: rewriting the seven-bullet list into one
        sentence drops a hand-off, reverses one (`research -> spec`), or
        loses the `tester already ran` note, and a count of arrows would
        still pass; each source/target pair is checked as an ordered pair
        inside the step, with the step bounded by the next section so the
        pipeline table's arrows elsewhere cannot satisfy it."""
        body = squash(step_three(self.text))
        pairs = [
            ("spec", "research"),
            ("research", "plan"),
            ("plan", "build"),
            ("build", "validate"),
            ("validate", "pr description"),
            ("checkup", "help fix the issues"),
        ]
        for source, target in pairs:
            with self.subTest(handoff=f"{source} -> {target}"):
                self.assertRegex(
                    body, rf"\b{re.escape(source)}\s*(→|->)\s*{re.escape(target)}"
                )
        with self.subTest(handoff="build -> validate keeps the tester note"):
            self.assertRegex(body, r"tester already ran")
        with self.subTest(handoff="handoff create is a safe place to end"):
            self.assertRegex(body, r"handoff create.{0,40}safe to end")
        with self.subTest(handoff="the step still offers the next step"):
            self.assertRegex(body, r"offer the next step")

    def test_port_entry_keeps_the_full_question_form(self):
        """Adversarial where: the port entry was trimmed (it lost its `one
        question per call` and `never batch` clauses to the shared lead
        paragraph) and the remaining clauses decay unnoticed: the tool name,
        recommended-first labelling, one-line options, the open `Other`,
        and the forward-looking follow-up with `Yes` ahead of `Not now`
        (asymmetric: recommended option must come first, not merely
        appear)."""
        port = entry(self.text, r"D\b")
        with self.subTest(clause="uses the tool for the commit question"):
            self.assertRegex(port, r"which commits to document through `?askuserquestion`?")
        with self.subTest(clause="recommended option first and labelled"):
            self.assertRegex(port, r"recommended option first.{0,20}\(recommended\)")
        with self.subTest(clause="each option one short line"):
            self.assertRegex(port, r"each option one short line")
        with self.subTest(clause="other left open for free text"):
            self.assertRegex(port, r'"other" left open for free text')
        with self.subTest(clause="retroactive runs per piece"):
            self.assertIn("/compass:retroactive", port)
        with self.subTest(clause="forward-looking question lists Yes before Not now"):
            self.assertRegex(
                port,
                r"write a forward-looking spec\?.*yes, start the spec \(recommended\).*not now",
            )

    def test_untouched_content_around_the_edited_entries_survives(self):
        """Adversarial where: the edit to the closing questions also deletes
        what the entries present before asking (the active-work summary,
        the setup description) or what the file declares (the tool in
        `allowed-tools`, the failure modes), so the skill asks its question
        with nothing to ask it about or no permission to ask it."""
        frontmatter = self.text.split("---", 2)[1]
        with self.subTest(part="AskUserQuestion stays in allowed-tools"):
            self.assertRegex(frontmatter, r"allowed-tools:.*\bAskUserQuestion\b")
        active = entry(self.text, r"C\b")
        with self.subTest(part="active work presents in-progress, blocked, completed"):
            self.assertRegex(
                active, r"in-progress \+ blocked \+ recently completed"
            )
        setup = entry(self.text, r"A\b")
        with self.subTest(part="no-Compass entry still names setup and vision"):
            self.assertIn("/compass:setup", setup)
            self.assertIn("/compass:vision", setup)
        with self.subTest(part="no-Compass entry still ends in a question"):
            self.assertTrue(setup.rstrip().endswith("?"))
        empty = entry(self.text, r"B - Empty vault")
        with self.subTest(part="empty-vault entry still ends in a question"):
            self.assertTrue(empty.rstrip().endswith("?"))
        with self.subTest(part="failure modes survive"):
            self.assertIn("Spawning agents without confirmation.", self.text)

    def test_guide_text_carries_no_dash_characters(self):
        """Adversarial where: the rewritten prose introduces an em-dash or
        en-dash (the repo bans both in every output), which a byte-budget or
        wording check never sees."""
        for char, name in ((chr(0x2014), "em-dash"), (chr(0x2013), "en-dash")):
            with self.subTest(char=name):
                self.assertNotIn(char, self.text)


if __name__ == "__main__":
    unittest.main()
