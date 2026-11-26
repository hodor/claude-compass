"""Tests for the authored-id branches of `requirementslib` and `compass requirements`.

Adversarial themes: the id pattern's edges (digits followed by letters, case,
spacing, a second prefix, a prefix from another section); where a bullet's id
may sit (nested bullet, numbered bullet, unbulleted paragraph, text on the
following line); what hides an id (tilde fence, HTML comment, Decisions
section); how duplicates are reported (line numbers on CR and CRLF text, a
first-spelling label, three holders, two ids at once); that the hash of
authored text equals the hash of the same words unauthored.
"""

import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requirementslib  # noqa: E402
from commands import requirements  # noqa: E402


def spec_with(outcome="", success="", decisions=""):
    parts = ["# Sample\n"]
    if outcome:
        parts.append("## Desired Outcome\n\n" + outcome)
    if success:
        parts.append("## Success Criteria\n\n" + success)
    if decisions:
        parts.append("## Decisions\n\n" + decisions)
    return "\n".join(parts)


def pairs(text):
    return [(r["id"], r["text"]) for r in requirementslib.extract_requirements(text)]


class AuthoredIdPatternTest(unittest.TestCase):
    def test_near_miss_id_spellings_stay_text_and_take_a_derived_id(self):
        """Adversarial where: `**O-1a:**`, lowercase, a space before the
        colon, the colon outside the bold, a space after the opening stars,
        a `K` prefix, underscores, an en dash and a checkbox with no space
        before the id are not authored ids; each must stay in the text of a
        derived `O-1` row. A loosened pattern would read them as authored."""
        near_misses = [
            "**O-1a:** x",
            "**o-01:** x",
            "**O-01 :** x",
            "**O-01**: x",
            "** O-01:** x",
            "**K-01:** x",
            "__O-01:__ x",
            "**O\u201301:** x",
            "[ ]**O-02:** x",
        ]
        for miss in near_misses:
            with self.subTest(miss=miss):
                self.assertEqual(pairs(spec_with(outcome=f"- {miss}\n")), [("O-1", miss)])

    def test_id_prefix_of_another_section_is_text(self):
        """Adversarial where: `**S-01:**` under Desired Outcome belongs to
        another section; it must stay text of a derived `O-1` and reserve
        no `S` number, so a real `S` bullet below still derives `S-1`."""
        text = spec_with(outcome="- **S-01:** Misplaced.\n", success="- Real success.\n")
        self.assertEqual(
            pairs(text), [("O-1", "**S-01:** Misplaced."), ("S-1", "Real success.")]
        )

    def test_spacing_after_the_id_is_free_and_text_is_normalized(self):
        """Adversarial where: `\\s*` after the id means no space and many
        spaces both give authored `O-01` with text `x`; a required single
        space would turn the no-space form into plain text."""
        for body in ("- **O-01:**x\n", "- **O-01:**     x\n", "-   **O-01:**\tx\n"):
            with self.subTest(body=body):
                self.assertEqual(pairs(spec_with(outcome=body)), [("O-01", "x")])

    def test_text_on_the_line_after_the_id_belongs_to_the_row(self):
        """Adversarial where: an id alone on its line with the words on the
        continuation line must give authored `O-01` with those words;
        splitting the id off before joining continuation lines would drop
        them."""
        text = spec_with(outcome="- **O-01:**\n  continued words\n- next\n")
        self.assertEqual(pairs(text), [("O-01", "continued words"), ("O-2", "next")])

    def test_id_only_bullet_yields_no_empty_requirement_row(self):
        """Adversarial where: a bullet that is only `**O-01:**` carries no
        requirement words; a row with empty text and the empty-string hash
        would make an unverifiable requirement. A bullet with no text is
        dropped everywhere else, so it must be dropped here too."""
        rows = requirementslib.extract_requirements(spec_with(outcome="- **O-01:**\n- next\n"))
        self.assertNotIn("", [r["text"] for r in rows])

    def test_numbered_bullet_carries_an_authored_id(self):
        """Adversarial where: `1. **O-01:** text` is a list item the bullet
        pattern accepts; it must read as authored, with the derived row after
        it skipping 1."""
        text = spec_with(outcome="1. **O-01:** num\n2. plain\n")
        self.assertEqual(pairs(text), [("O-01", "num"), ("O-2", "plain")])

    def test_unbulleted_paragraph_is_never_authored(self):
        """Adversarial where: a prose paragraph opening `**O-01:**` is not a
        bullet, so the id stays in its text and the row derives `O-1`."""
        self.assertEqual(
            pairs(spec_with(outcome="**O-01:** para\n")), [("O-1", "**O-01:** para")]
        )

    def test_nested_bullet_is_part_of_its_parent_and_never_authored(self):
        """Adversarial where: an indented child bullet holding an id folds
        into the parent's text; it must not become a second authored row
        nor a duplicate of the parent's id."""
        text = spec_with(outcome="- **O-01:** a\n  - **O-01:** nested\n")
        self.assertEqual(pairs(text), [("O-01", "a **O-01:** nested")])
        self.assertIsNone(requirementslib.duplicate_report(text))

    def test_authored_id_before_kpi_words_is_not_a_kpi_row(self):
        """Adversarial where: `- **O-01:** KPI: x` opens with the id, so it
        is an outcome row whose text is `KPI: x`; the KPI check runs on the
        full bullet and must not turn it into `K-1`."""
        self.assertEqual(
            pairs(spec_with(outcome="- **O-01:** KPI: x\n")), [("O-01", "KPI: x")]
        )

    def test_zero_and_huge_authored_numbers_are_ids(self):
        """Adversarial where: `O-0` and a 25-digit number are authored ids
        that reserve exactly their own number; the derived bullets must still
        count from 1."""
        text = spec_with(
            outcome="- **O-0:** zero\n- **O-" + "9" * 25 + ":** huge\n- p1\n- p2\n"
        )
        self.assertEqual(
            [r["id"] for r in requirementslib.extract_requirements(text)],
            ["O-0", "O-" + "9" * 25, "O-1", "O-2"],
        )

    def test_uppercase_checkbox_mark_is_accepted(self):
        """Adversarial where: `- [X] **O-02:**` must read as authored with
        the box mark off the text."""
        self.assertEqual(
            pairs(spec_with(outcome="- [X] **O-02:** boxed\n")), [("O-02", "boxed")]
        )


class AuthoredIdHidingTest(unittest.TestCase):
    def test_tilde_fence_and_comment_hide_authored_ids(self):
        """Adversarial where: an authored id inside a `~~~` fence or an HTML
        comment is not a row and not a duplicate of a live id."""
        text = spec_with(
            outcome="- **O-1:** live\n~~~\n- **O-1:** fenced\n~~~\n"
            "<!--\n- **O-1:** commented\n-->\n- plain\n"
        )
        self.assertEqual(pairs(text), [("O-1", "live"), ("O-2", "plain")])
        self.assertIsNone(requirementslib.duplicate_report(text))

    def test_decision_section_ids_of_other_prefixes_do_not_collide(self):
        """Adversarial where: `**O-01:**` bullets repeated in the Decisions
        section are decision-section text, not requirement rows; they must
        not produce a duplicate report or reserve a number."""
        text = spec_with(outcome="- plain\n", decisions="- **O-01:** a\n- **O-01:** b\n")
        self.assertIsNone(requirementslib.duplicate_report(text))
        self.assertEqual(pairs(text)[0], ("O-1", "plain"))


class DuplicateReportTest(unittest.TestCase):
    def test_line_numbers_agree_across_line_ending_styles(self):
        """Adversarial where: the same two-holder spec in LF, CRLF and lone
        CR endings must name the same lines; counting `\\r` and `\\n` as two
        breaks would shift the numbers on CRLF text."""
        lf = spec_with(outcome="- **O-01:** a\n- **O-01:** b\n")
        expected = requirementslib.duplicate_report(lf)
        self.assertEqual(expected, "duplicate requirement id O-01 on lines 5 and 6")
        for ending in ("\r\n", "\r"):
            with self.subTest(ending=repr(ending)):
                self.assertEqual(
                    requirementslib.duplicate_report(lf.replace("\n", ending)), expected
                )

    def test_row_is_located_at_its_first_line_when_it_wraps(self):
        """Adversarial where: a holder whose bullet wraps over two lines is
        reported at its first line; reporting the last line would point at
        the wrong bullet."""
        text = spec_with(outcome="- p\n- **O-01:** a\n  more\n- **O-01:** b\n")
        self.assertEqual(
            requirementslib.duplicate_report(text),
            "duplicate requirement id O-01 on lines 6 and 8",
        )

    def test_three_holders_and_two_ids_are_all_named(self):
        """Adversarial where: three spellings of one number read `5, 6 and
        7`, and a second duplicated id in another section is joined by `; `;
        reporting only the first pair would hide the rest."""
        three = spec_with(outcome="- **O-5:** a\n- **O-05:** b\n- **O-005:** c\n")
        self.assertEqual(
            requirementslib.duplicate_report(three),
            "duplicate requirement id O-5 on lines 5, 6 and 7",
        )
        two = spec_with(
            outcome="- **O-1:** a\n- **O-1:** b\n", success="- **S-2:** a\n- **S-2:** b\n"
        )
        report = requirementslib.duplicate_report(two)
        self.assertIn("O-1 on lines 5 and 6", report)
        self.assertIn("; duplicate requirement id S-2", report)

    def test_second_section_with_the_same_title_still_counts_as_a_holder(self):
        """Adversarial where: two `## Desired Outcome` headings each holding
        `O-01` are one id space; a per-heading scan would miss the clash."""
        text = spec_with(outcome="- **O-01:** a\n") + "\n## Desired Outcome\n\n- **O-01:** b\n"
        self.assertIn("duplicate requirement id O-01", requirementslib.duplicate_report(text))

    def test_non_string_and_empty_input_report_nothing(self):
        """Adversarial where: `None`, `''` and a non-string must return None
        without raising, as `extract_requirements` does."""
        for value in (None, "", 7, b"- **O-1:** a"):
            with self.subTest(value=value):
                self.assertIsNone(requirementslib.duplicate_report(value))


class AuthoredHashTest(unittest.TestCase):
    def test_hash_of_authored_text_equals_hash_of_the_same_words_unauthored(self):
        """Adversarial where: the hash covers the words only, so an authored
        bullet with extra spacing must hash as the plain bullet and as the
        sha256 of the normalized words; hashing the id token would make
        every authoring edit change the hash."""
        authored = requirementslib.extract_requirements(
            spec_with(outcome="- **O-07:**    Same   words.\n")
        )[0]
        plain = requirementslib.extract_requirements(spec_with(outcome="- Same words.\n"))[0]
        expected = hashlib.sha256(b"Same words.").hexdigest()[:12]
        self.assertEqual(authored["hash"], plain["hash"])
        self.assertEqual(authored["hash"], expected)


class DuplicateCommandTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.spec = self.root / "SPEC-001-x.md"

    def run_command(self, body, *extra):
        self.spec.write_text(body, encoding="utf-8", newline="")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = requirements.run([str(self.spec), *extra])
        return code, out.getvalue(), err.getvalue()

    def test_duplicate_exits_one_with_no_listing_in_every_mode(self):
        """Adversarial where: the duplicate check must fire before any
        output in plain, `--json` and `--for-task` modes, on a CRLF file;
        a check placed after listing would print rows then fail."""
        body = spec_with(outcome="- **O-01:** a\n- **O-1:** b\n").replace("\n", "\r\n")
        plan = self.root / "PLAN-001.md"
        plan.write_text("- [ ] TASK-1: x\n", encoding="utf-8")
        for extra in ((), ("--json",), ("--for-task", "TASK-1", "--plan", str(plan))):
            with self.subTest(extra=extra):
                code, out, err = self.run_command(body, *extra)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn("duplicate requirement id O-01 on lines 5 and 6", err)

    def test_distinct_authored_ids_still_list_and_exit_zero(self):
        """Adversarial where: the duplicate gate must not trip on distinct
        numbers or on the same number under two prefixes."""
        body = spec_with(outcome="- **O-01:** a\n- **O-02:** b\n", success="- **S-01:** c\n")
        code, out, err = self.run_command(body)
        self.assertEqual(code, 0, err)
        self.assertEqual([line.split()[0] for line in out.splitlines()], ["O-01", "O-02", "S-01"])


class AuthoredDocsTest(unittest.TestCase):
    def test_shipped_skill_text_shows_the_authored_shape(self):
        """Adversarial where: the obsidian template and the spec skill are
        the only places an author learns the id shape; each must still carry
        it."""
        root = Path(__file__).resolve().parents[2] / "skills"
        self.assertIn("**O-01:**", (root / "obsidian" / "templates.md").read_text(encoding="utf-8"))
        self.assertIn("never renumbered", (root / "spec" / "SKILL.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
