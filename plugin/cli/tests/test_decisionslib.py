"""Tests for the three-outcome decision parser."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decisionslib  # noqa: E402


def extract(text):
    return decisionslib.extract_decisions(text)


class ColonFormTests(unittest.TestCase):
    def test_basic_bullet(self):
        decisions, outcome = extract(
            "## Decisions\n\n- **D-01:** Ship the parser first.\n"
        )
        self.assertEqual(outcome, "parsed")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["id"], "D-01")
        self.assertEqual(decisions[0]["text"], "Ship the parser first.")
        self.assertTrue(decisions[0]["trackable"])
        self.assertEqual(decisions[0]["tags"], [])

    def test_line_numbers_are_document_absolute(self):
        text = "---\ntype: spec\n---\n\n## Decisions\n\n- **D-01:** First.\n- **D-02:** Second.\n"
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "parsed")
        self.assertEqual([d["line"] for d in decisions], [7, 8])

    def test_heading_suffix_and_case_insensitive(self):
        decisions, outcome = extract(
            "## DECISIONS (made by the human)\n\n- **D-01:** Yes.\n"
        )
        self.assertEqual(outcome, "parsed")
        self.assertEqual(decisions[0]["id"], "D-01")

    def test_three_hash_heading_matches(self):
        _, outcome = extract("### Decision\n\n- **D-01:** Yes.\n")
        self.assertEqual(outcome, "parsed")

    def test_one_hash_heading_is_not_a_section(self):
        decisions, outcome = extract("# Decisions\n\n- **D-01:** Yes.\n")
        # No section, but the D- token is decision-shaped content.
        self.assertEqual(outcome, "could-not-parse")
        self.assertEqual(decisions, [])

    def test_continuation_lines_join_text(self):
        text = (
            "## Decisions\n"
            "\n"
            "- **D-01:** First line\n"
            "  continues here\n"
            "\tand with a tab.\n"
        )
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "parsed")
        self.assertEqual(
            decisions[0]["text"], "First line continues here and with a tab."
        )

    def test_colon_inside_text_after_separator(self):
        decisions, outcome = extract(
            "## Decisions\n\n- **D-02:** Resolution happens at install time: setup runs it.\n"
        )
        self.assertEqual(outcome, "parsed")
        self.assertIn("install time", decisions[0]["text"])


class TaggedAndDiscretionTests(unittest.TestCase):
    def test_deferred_tag_parses_non_trackable(self):
        decisions, outcome = extract(
            "## Decisions\n\n- **D-03 [deferred]:** Later.\n"
        )
        self.assertEqual(outcome, "parsed")
        self.assertFalse(decisions[0]["trackable"])
        self.assertEqual(decisions[0]["tags"], ["deferred"])
        self.assertEqual(decisions[0]["id"], "D-03")

    def test_informational_tag_parses_non_trackable(self):
        decisions, _ = extract(
            "## Decisions\n\n- **D-04 [informational]:** Context only.\n"
        )
        self.assertFalse(decisions[0]["trackable"])

    def test_unknown_tag_stays_trackable(self):
        decisions, _ = extract("## Decisions\n\n- **D-05 [security]:** Do it.\n")
        self.assertTrue(decisions[0]["trackable"])
        self.assertEqual(decisions[0]["tags"], ["security"])

    def test_discretion_subheading_marks_non_trackable(self):
        text = (
            "## Decisions\n"
            "\n"
            "- **D-01:** Tracked.\n"
            "\n"
            "### Claude's Discretion\n"
            "\n"
            "- **D-02:** Agent's call.\n"
        )
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "parsed")
        by_id = {d["id"]: d for d in decisions}
        self.assertTrue(by_id["D-01"]["trackable"])
        self.assertFalse(by_id["D-02"]["trackable"])

    def test_curly_quote_discretion_heading(self):
        text = "## Decisions\n\n### Claude’s Discretion\n\n- **D-01:** Free.\n"
        decisions, _ = extract(text)
        self.assertFalse(decisions[0]["trackable"])

    def test_non_discretion_subheading_resets_state(self):
        text = (
            "## Decisions\n"
            "\n"
            "### Builder discretion\n"
            "- **D-01:** Free.\n"
            "\n"
            "### Binding\n"
            "- **D-02:** Tracked.\n"
        )
        decisions, _ = extract(text)
        by_id = {d["id"]: d for d in decisions}
        self.assertFalse(by_id["D-01"]["trackable"])
        self.assertTrue(by_id["D-02"]["trackable"])


class OtherGrammarTests(unittest.TestCase):
    def test_titled_colon_form(self):
        decisions, outcome = extract(
            "## Decisions\n\n- **D-01: Parser first.** The rest follows.\n"
        )
        self.assertEqual(outcome, "parsed")
        self.assertEqual(decisions[0]["id"], "D-01")
        self.assertEqual(decisions[0]["text"], "The rest follows.")

    def test_em_dash_form(self):
        decisions, outcome = extract(
            "## Decisions\n\n- **D-01 — Parser first** pasted content.\n"
        )
        self.assertEqual(outcome, "parsed")
        self.assertEqual(decisions[0]["id"], "D-01")
        self.assertEqual(decisions[0]["text"], "pasted content.")

    def test_alphanumeric_id(self):
        decisions, outcome = extract("## Decisions\n\n- **D-INFRA-01:** Works.\n")
        self.assertEqual(outcome, "parsed")
        self.assertEqual(decisions[0]["id"], "D-INFRA-01")


class NonePresentTests(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(extract(""), ([], "none-present"))

    def test_none_input(self):
        self.assertEqual(extract(None), ([], "none-present"))

    def test_prose_without_signals(self):
        self.assertEqual(extract("# Title\n\nJust prose.\n"), ([], "none-present"))

    def test_heading_with_prose_only(self):
        text = "## Decision\n\nAdopt a four-part architecture for the vault.\n"
        self.assertEqual(extract(text), ([], "none-present"))

    def test_heading_with_prose_bold_bullets(self):
        text = (
            "## Decision\n"
            "\n"
            "- **Scope:** the whole vault.\n"
            "- **Hot tier (always in context):** pointers only.\n"
        )
        self.assertEqual(extract(text), ([], "none-present"))

    def test_fenced_examples_only_are_ignored(self):
        text = (
            "# Authoring guide\n"
            "\n"
            "```markdown\n"
            "- **D-01:** example decision\n"
            "```\n"
        )
        self.assertEqual(extract(text), ([], "none-present"))

    def test_inline_code_token_is_ignored(self):
        text = "# Guide\n\nCite decisions as `SPEC-007/D-03` tokens.\n"
        self.assertEqual(extract(text), ([], "none-present"))

    def test_fenced_example_inside_section_with_real_bullets(self):
        text = (
            "## Decisions\n"
            "\n"
            "- **D-01:** The format is fixed.\n"
            "\n"
            "```markdown\n"
            "- **D-99:** fenced example, not a decision\n"
            "```\n"
        )
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "parsed")
        self.assertEqual([d["id"] for d in decisions], ["D-01"])


class CouldNotParseTests(unittest.TestCase):
    def test_one_malformed_bullet_poisons_two_good_ones(self):
        text = (
            "## Decisions\n"
            "\n"
            "- **D-01:** Good.\n"
            "- **D-02:* Broken bold close.\n"
            "- **D-03:** Also good.\n"
        )
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "could-not-parse")
        # The good bullets are still reported alongside the failure.
        self.assertEqual([d["id"] for d in decisions], ["D-01", "D-03"])

    def test_d_token_in_prose_with_no_heading(self):
        text = "# Notes\n\nWe agreed on D-07 informally.\n"
        self.assertEqual(extract(text), ([], "could-not-parse"))

    def test_section_with_token_but_zero_bullets(self):
        text = "## Decisions\n\nSee D-01 in the other document.\n"
        self.assertEqual(extract(text), ([], "could-not-parse"))

    def test_section_with_id_shaped_bold_bullet(self):
        text = "## Decisions\n\n- **DEC-01:** unknown prefix grammar.\n"
        self.assertEqual(extract(text), ([], "could-not-parse"))

    def test_unterminated_fence_swallowing_bullets_fails_loud(self):
        text = (
            "## Decisions\n"
            "\n"
            "```\n"
            "- **D-01:** swallowed by the broken fence\n"
        )
        self.assertEqual(extract(text), ([], "could-not-parse"))

    def test_unterminated_fence_with_no_heading(self):
        text = "# Doc\n\n```\nD-01 vanished here\n"
        self.assertEqual(extract(text), ([], "could-not-parse"))

    def test_adr_reference_is_not_a_d_token(self):
        # The D inside ADR-004 has no word boundary before it.
        text = "# Notes\n\nPer ADR-004 the tiers are fixed.\n"
        self.assertEqual(extract(text), ([], "none-present"))


class MultipleSectionTests(unittest.TestCase):
    def test_two_sections_both_collected(self):
        text = (
            "## Decision\n"
            "\n"
            "- **D-01:** First section.\n"
            "\n"
            "## Middle\n"
            "\n"
            "prose\n"
            "\n"
            "## Decisions (follow-up)\n"
            "\n"
            "- **D-02:** Second section.\n"
        )
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "parsed")
        self.assertEqual([d["id"] for d in decisions], ["D-01", "D-02"])

    def test_section_ends_at_same_level_heading(self):
        text = (
            "## Decisions\n"
            "\n"
            "- **D-01:** In scope.\n"
            "\n"
            "## Alternatives considered\n"
            "\n"
            "- **D-99:** outside the section, never parsed.\n"
        )
        decisions, outcome = extract(text)
        # D-99 sits outside the section; the parsed section wins the outcome.
        self.assertEqual(outcome, "parsed")
        self.assertEqual([d["id"] for d in decisions], ["D-01"])


class LineEndingTests(unittest.TestCase):
    def test_crlf_input_parses_with_clean_text(self):
        text = "## Decisions\r\n\r\n- **D-01:** Windows text.\r\n"
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "parsed")
        self.assertEqual(decisions[0]["text"], "Windows text.")


class QualifiedCrossReferenceTests(unittest.TestCase):
    def test_space_separated_document_stem_reference_is_not_evidence(self):
        """Adversarial where: a D-NN token immediately preceded by a
        document stem (SPEC-015 D-02) cites another document's decision.
        Treating it as unparsed local evidence would poison the
        zero-extraction check on every cross-document reference."""
        text = (
            "## Decision\n"
            "\n"
            "We are adopting rolling-wave planning per SPEC-015 D-02 "
            "and SPEC-015 D-03.\n"
        )
        self.assertEqual(extract(text), ([], "none-present"))

    def test_wikilink_reference_is_not_evidence(self):
        """Adversarial where: a D-NN token fully inside a [[wikilink]] is
        a cross-document citation. Stripping only space/slash-qualified
        forms and missing the wikilink form would still poison this."""
        text = (
            "## Decision\n"
            "\n"
            "See [[ADR-009-rolling-wave-mechanism/D-03]] for the original "
            "call.\n"
        )
        self.assertEqual(extract(text), ([], "none-present"))

    def test_bare_token_still_poisons_alongside_qualified_references(self):
        """Adversarial where: qualified-reference stripping must target
        only qualified tokens. A genuinely bare D-01 sitting in the same
        text as two qualified citations must still poison the outcome,
        not get swept away with them."""
        text = (
            "## Decision\n"
            "\n"
            "We are adopting rolling-wave planning per SPEC-015 D-02 "
            "and SPEC-015 D-03. See D-01 for the original decision.\n"
        )
        self.assertEqual(extract(text), ([], "could-not-parse"))

    def test_malformed_bullet_poisons_alongside_qualified_reference(self):
        """Adversarial where: qualified-reference stripping runs over the
        same text as malformed-bullet detection. It must not swallow the
        malformed bullet or the good bullets around it, so decisions-so-far
        and the could-not-parse outcome stay intact."""
        text = (
            "## Decisions\n"
            "\n"
            "- **D-01:** Good.\n"
            "- **D-02:* Broken bold close.\n"
            "\n"
            "See SPEC-015 D-03 for background.\n"
        )
        decisions, outcome = extract(text)
        self.assertEqual(outcome, "could-not-parse")
        self.assertEqual([d["id"] for d in decisions], ["D-01"])

    def test_slash_separated_document_stem_reference_is_not_evidence(self):
        """Adversarial where: the qualifying separator can be a slash,
        not only a space. A stripper that only recognizes the space form
        would still poison SPEC-007-.../D-03 style citations."""
        text = "## Decision\n\nTracked by SPEC-007-decision-coverage-tracing/D-03.\n"
        self.assertEqual(extract(text), ([], "none-present"))

    def test_non_stem_prefix_does_not_qualify(self):
        """Adversarial where: a token that merely contains "SPEC-" as a
        substring without starting with it (XSPEC-015) is not a document
        stem. A stripper that matches the substring anywhere, rather than
        requiring the stem prefix to start the preceding token, would
        wrongly qualify this and swallow a bare D-02."""
        text = "## Decisions\n\nSee XSPEC-015 D-02 in the other document.\n"
        self.assertEqual(extract(text), ([], "could-not-parse"))


if __name__ == "__main__":
    unittest.main()
