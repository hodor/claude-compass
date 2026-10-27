"""Tests for the three-outcome decision parser."""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decisionslib  # noqa: E402
from commands import coverage, decisions as decisions_command  # noqa: E402


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


class CalloutDecisionTests(unittest.TestCase):
    def test_bullets_in_a_callout_parse_at_any_depth(self):
        """Adversarial where: the parser matches `- **D-NN:**` only at line
        start, so a bullet behind one or more `>` markers reads as prose and
        a callout holding every decision of a spec is `none-present` or
        `could-not-parse`. Rows vary the quote depth, the spacing after the
        marker, continuation lines, mixing with plain bullets and CRLF,
        since each is a different way a prefix strip can be off by one."""
        head = "## Decisions\n\n"
        rows = [
            ("one level, header line above",
             head + "> [!important] You decide\n"
             "> - **D-01:** First.\n> - **D-02:** Second.\n> - **D-03:** Third.\n",
             ["D-01", "D-02", "D-03"], ["First.", "Second.", "Third."], [4, 5, 6]),
            ("two levels, spaced",
             head + "> > - **D-01:** Deep.\n", ["D-01"], ["Deep."], [3]),
            ("two levels, compact",
             head + ">> - **D-01:** Deep.\n", ["D-01"], ["Deep."], [3]),
            ("three levels, mixed spacing",
             head + "> >> - **D-01:** Deeper.\n", ["D-01"], ["Deeper."], [3]),
            ("no space after the marker",
             head + ">- **D-01:** Tight.\n", ["D-01"], ["Tight."], [3]),
            ("continuation line inside the callout joins the text",
             head + "> - **D-01:** First line\n>   continues here.\n",
             ["D-01"], ["First line continues here."], [3]),
            ("bullet outside and bullet inside the same section",
             head + "- **D-01:** Plain.\n\n> - **D-02:** Quoted.\n",
             ["D-01", "D-02"], ["Plain.", "Quoted."], [3, 5]),
            ("CRLF line endings",
             "## Decisions\r\n\r\n> - **D-01:** Windows.\r\n",
             ["D-01"], ["Windows."], [3]),
        ]
        for name, text, ids, texts, lines in rows:
            with self.subTest(name=name):
                found, outcome = extract(text)
                self.assertEqual(outcome, "parsed")
                self.assertEqual([d["id"] for d in found], ids)
                self.assertEqual([d["text"] for d in found], texts)
                self.assertEqual([d["line"] for d in found], lines)

    def test_callout_bullet_keeps_tags_and_stops_at_the_section_end(self):
        """Adversarial where: a callout reader that scans the whole document
        for quoted bullets would collect a `> - **D-99:**` that sits under a
        later heading, and one that drops tag handling would leave a
        `[deferred]` callout decision trackable, so a plan is failed for
        not covering a parked ruling."""
        text = (
            "## Decisions\n\n"
            "> - **D-01:** Tracked.\n"
            "> - **D-02 [deferred]:** Parked.\n"
            "\n"
            "## Alternatives considered\n\n"
            "> - **D-99:** outside the section.\n"
        )
        found, outcome = extract(text)
        self.assertEqual(outcome, "parsed")
        self.assertEqual([d["id"] for d in found], ["D-01", "D-02"])
        self.assertEqual([d["trackable"] for d in found], [True, False])
        self.assertEqual(found[1]["tags"], ["deferred"])

    def test_trailing_block_id_is_dropped_from_the_decision_text(self):
        """Adversarial where: a cited line carries ` ^d-01` so the link
        `[[doc#^d-01]]` can reach it; if the id stays in the text, every
        listing sees `Ship it. ^d-01` instead of the ruling. Rows bound the
        strip: only an id at the very end of the decision goes, a caret
        inside the sentence stays, and trailing spaces or a continuation
        line ending in the id do not hide it."""
        head = "## Decisions\n\n"
        rows = [
            ("plain bullet", head + "- **D-01:** Ship it. ^d-01\n", "Ship it."),
            ("callout bullet", head + "> - **D-01:** Ship it. ^d-01\n", "Ship it."),
            ("trailing spaces after the id",
             head + "- **D-01:** Ship it. ^d-01   \n", "Ship it."),
            ("id on the last continuation line",
             head + "- **D-01:** Ship it\n  in two lines. ^d-01\n",
             "Ship it in two lines."),
            ("id with digits and hyphens only",
             head + "- **D-01:** Ship it. ^a-9-b\n", "Ship it."),
            ("caret glued to a word is not an id",
             head + "- **D-01:** Raise x^2 on the way.\n", "Raise x^2 on the way."),
            ("id mid-sentence is not trailing",
             head + "- **D-01:** Ship ^d-01 it.\n", "Ship ^d-01 it."),
            ("no id at all", head + "- **D-01:** Ship it.\n", "Ship it."),
        ]
        for name, text, expected in rows:
            with self.subTest(name=name):
                found, outcome = extract(text)
                self.assertEqual(outcome, "parsed")
                self.assertEqual(found[0]["text"], expected)

    def test_callout_inside_a_code_fence_is_not_a_decision(self):
        """Adversarial where: stripping the `>` prefix before the fence mask
        is applied would make an authoring example (a callout shown inside
        a fenced block) read as a real decision, or as an unparsed one that
        fails the file. A fenced callout beside a real one must leave only
        the real one."""
        callout = "> [!important] You decide\n> - **D-01:** Example only.\n"
        rows = [
            ("backtick fence, no heading",
             "# Guide\n\n```markdown\n" + callout + "```\n"),
            ("backtick fence under a Decisions heading",
             "## Decisions\n\n```markdown\n" + callout + "```\n"),
            ("tilde fence under a Decisions heading",
             "## Decisions\n\n~~~\n" + callout + "~~~\n"),
        ]
        for name, text in rows:
            with self.subTest(name=name):
                self.assertEqual(extract(text)[1], "none-present")
        mixed = (
            "## Decisions\n\n> - **D-01:** Real.\n\n"
            "```markdown\n> - **D-99:** Example.\n```\n"
        )
        found, outcome = extract(mixed)
        self.assertEqual(outcome, "parsed")
        self.assertEqual([d["id"] for d in found], ["D-01"])

    def test_malformed_callout_bullet_poisons_good_neighbours(self):
        """Adversarial where: the malformed-bullet check runs on unquoted
        lines only, so a `> - **D-` with a broken bold close inside a callout
        passes silently and the decision vanishes from coverage without a
        failure. One bad bullet among good ones, in and out of the callout,
        must fail loud and still report the good ones."""
        rows = [
            ("one bad among good callout bullets",
             "## Decisions\n\n> - **D-01:** Good.\n> - **D-02:* Broken close.\n"
             "> - **D-03:** Also good.\n", ["D-01", "D-03"]),
            ("bad callout bullet beside a good plain bullet",
             "## Decisions\n\n- **D-01:** Good.\n> - **D-02 no separator\n",
             ["D-01"]),
            ("every callout bullet malformed",
             "## Decisions\n\n> - **D-01 no separator\n", []),
        ]
        for name, text, ids in rows:
            with self.subTest(name=name):
                found, outcome = extract(text)
                self.assertEqual(outcome, "could-not-parse")
                self.assertEqual([d["id"] for d in found], ids)


class CalloutCommandTests(unittest.TestCase):
    CALLOUT_SPEC = (
        "---\ntitle: Source spec\ntype: spec\nstatus: approved\n---\n\n"
        "## Decisions\n\n"
        "> [!important] You decide\n"
        "> - **D-01:** first ruling ^d-01\n"
        "> - **D-02:** second ruling\n"
        "> - **D-03:** third ruling\n"
    )

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".compass").mkdir()
        self.root = tmp / ".compass"
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)
        if old is None:
            self.addCleanup(os.environ.pop, "CLAUDE_PROJECT_DIR", None)
        else:
            self.addCleanup(os.environ.__setitem__, "CLAUDE_PROJECT_DIR", old)

    def write(self, rel, body):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def plan(self, cited):
        items = ", ".join(f"SPEC-001-src/{d}" for d in cited)
        return (
            "---\ntitle: P\ntype: plan\nstatus: approved\n"
            'depends_on: ["[[SPEC-001-src]]"]\n---\n\n## Phases\n\n'
            f"- [ ] TASK-001: a - decisions: [{items}]\n"
        )

    def run_command(self, module, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(args)
        return code, out.getvalue(), err.getvalue()

    def test_plan_citing_callout_decisions_is_judged_by_coverage(self):
        """Adversarial where: the spec's decisions are all in a callout, so
        a reader blind to callouts reports `no decisions present` and
        `compass coverage` passes a plan that cites none of them, and the
        listing shows `^d-01` glued to the ruling. Citing all three must
        pass; citing two must fail naming the third."""
        self.write("specs/SPEC-001-src.md", self.CALLOUT_SPEC)

        code, out, _ = self.run_command(decisions_command, ["SPEC-001-src"])
        self.assertEqual(code, 0)
        self.assertIn("3 decision(s)", out)
        self.assertNotIn("^d-01", out)

        self.write("plans/PLAN-001-p.md", self.plan(["D-01", "D-02", "D-03"]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 0)
        self.assertIn("3 covered, 0 scoped, 0 uncovered", out)

        self.write("plans/PLAN-001-p.md", self.plan(["D-01", "D-02"]))
        code, out, _ = self.run_command(coverage, ["PLAN-001-p"])
        self.assertEqual(code, 1)
        d3 = next(line for line in out.splitlines() if "D-03" in line)
        self.assertIn("NOT COVERED", d3)


if __name__ == "__main__":
    unittest.main()
