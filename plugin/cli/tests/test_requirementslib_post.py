"""Tests for the parsing branches of `requirementslib` and `commands.requirements`.

Adversarial themes: bullet markers and continuation rules that decide where
one requirement row ends and the next begins; heading forms that open or close
a requirement section; document order of decision rows against the other rows;
whitespace normalization of non-ASCII spaces; task-line matching in a plan
(checked boxes, CRLF, fenced copies, spec stems sharing a prefix); and the
command's handling of byte-order marks, undecodable bytes and directories.
"""

import contextlib
import hashlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requirementslib  # noqa: E402
from commands import requirements  # noqa: E402


def texts(spec_text):
    return [(row["id"], row["text"]) for row in requirementslib.extract_requirements(spec_text)]


def ids_for_task(plan_text, task_id="TASK-1", stem="SPEC-1"):
    rows = [{"id": "D-01"}, {"id": "D-02"}, {"id": "O-1"}]
    return [row["id"] for row in requirementslib.rows_for_task(rows, plan_text, task_id, stem)]


def run_command(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = requirements.run(args)
    return code, out.getvalue(), err.getvalue()


class SectionParsingTest(unittest.TestCase):
    def test_bullet_markers_and_continuations_split_rows_where_the_rules_say(self):
        """Adversarial where: a numbered, starred or plus bullet, a tab-indented
        continuation, a nested bullet, a blockquote or a comment mis-splits or
        merges rows, moving every later id."""
        cases = {
            "numbered and symbol markers each open a row": (
                "## Desired Outcome\n1. one\n2) two\n* three\n+ four\n",
                [("O-1", "one"), ("O-2", "two"), ("O-3", "three"), ("O-4", "four")],
            ),
            "nested bullet and tab line join the bullet above": (
                "## Desired Outcome\n- a\n   - nested\n\ttabbed\n- b\n",
                [("O-1", "a nested tabbed"), ("O-2", "b")],
            ),
            "blockquote ends the row and is never a row": (
                "## Constraints\n- a\n> quoted\n- b\n",
                [("C-1", "a"), ("C-2", "b")],
            ),
            "multi-line comment hides its bullets": (
                "## Constraints\n- a\n<!-- start\n- hidden\n-->\n- b\n",
                [("C-1", "a"), ("C-2", "b")],
            ),
            "fenced block hides its bullets": (
                "## Constraints\n- a\n```\n- hidden\n```\n- b\n",
                [("C-1", "a"), ("C-2", "b")],
            ),
            "rule line ends a prose paragraph": (
                "## Desired Outcome\nprose one\nprose two\n---\nprose three\n",
                [("O-1", "prose one prose two"), ("O-2", "prose three")],
            ),
        }
        for name, (spec, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(texts(spec), expected)

    def test_headings_open_and_close_requirement_sections(self):
        """Adversarial where: a closed ATX heading, a top-level heading, a
        repeated section heading or a level-3 decisions heading inside a
        requirement section leaves the wrong section active."""
        cases = {
            "closing hashes still open the section": (
                "## Desired Outcome ##\n- a\n",
                [("O-1", "a")],
            ),
            "level-1 heading ends the section": (
                "## Constraints\n- a\n# Top\n- b\n",
                [("C-1", "a")],
            ),
            "repeated heading continues numbering": (
                "## Constraints\n- a\n## Constraints\n- b\n",
                [("C-1", "a"), ("C-2", "b")],
            ),
            "plural heading title matches": (
                "## Desired Outcomes\n- a\n",
                [("O-1", "a")],
            ),
            "longer title does not match": (
                "## Constraints and Notes\n- a\n",
                [],
            ),
            "level-3 decisions heading ends the section": (
                "## Constraints\n- a\n### Decisions\n- plain bullet\n",
                [("C-1", "a")],
            ),
        }
        for name, (spec, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(texts(spec), expected)

    def test_kpi_lines_take_k_ids_in_any_requirement_section(self):
        """Adversarial where: a bold or bulleted KPI line, a KPI with no text,
        or a second KPI is numbered as a section row or dropped."""
        spec = "## Success Criteria\n- KPI: first\n- **KPI:** second\n- KPI:\n- plain\n"
        self.assertEqual(
            texts(spec),
            [("K-1", "first"), ("K-2", "second"), ("S-1", "plain")],
        )

    def test_decision_rows_sit_in_document_order_among_other_rows(self):
        """Adversarial where: decisions are appended after the other rows, or
        a fenced block before them shifts their line numbers, so a decisions
        section placed first or after a fence lists out of order."""
        spec = (
            "## Decisions\n\n- **D-01:** first\n\n"
            "```\nfenced\nlines\n```\n\n"
            "## Desired Outcome\n- outcome\n"
        )
        self.assertEqual(texts(spec), [("D-01", "first"), ("O-1", "outcome")])

    def test_hash_normalizes_non_ascii_spaces_and_encodes_utf8(self):
        """Adversarial where: a no-break space or an accented letter hashes
        differently from its plain form, so an invisible edit moves the hash."""
        plain = requirementslib.extract_requirements("## Constraints\n- café au lait\n")[0]
        spaced = requirementslib.extract_requirements(
            "## Constraints\n- café  au lait\n"
        )[0]
        self.assertEqual(plain["hash"], spaced["hash"])
        self.assertEqual(
            plain["hash"], hashlib.sha256("café au lait".encode("utf-8")).hexdigest()[:12]
        )


class RowsForTaskTest(unittest.TestCase):
    def test_task_line_and_citation_forms(self):
        """Adversarial where: a checked box, CRLF endings, backticked entries,
        a stem that is a prefix of another stem, a fenced copy of the task line,
        or a second `decisions:` field changes which decisions a task claims."""
        cases = {
            "checked box": ("- [x] TASK-1: a, decisions: [SPEC-1/D-01]\n", ["D-01", "O-1"]),
            "crlf line endings": (
                "- [ ] TASK-1: a, decisions: [SPEC-1/D-01]\r\n- [ ] TASK-2: b\r\n",
                ["D-01", "O-1"],
            ),
            "backticked entry": ("- [ ] TASK-1: a, decisions: [`SPEC-1/D-01`]\n", ["D-01", "O-1"]),
            "no space after comma": (
                "- [ ] TASK-1: a, decisions: [SPEC-1/D-01,SPEC-1/D-02]\n",
                ["D-01", "D-02", "O-1"],
            ),
            "stem prefix of another stem": (
                "- [ ] TASK-1: a, decisions: [SPEC-10/D-02]\n",
                ["O-1"],
            ),
            "fenced copy of the task line": (
                "```\n- [ ] TASK-1: a, decisions: [SPEC-1/D-01]\n```\n",
                ["O-1"],
            ),
            "two decisions fields on one line": (
                "- [ ] TASK-1: a, decisions: [SPEC-1/D-01], lessons: [x], decisions: [SPEC-1/D-02]\n",
                ["D-01", "D-02", "O-1"],
            ),
            "task absent from the plan": ("- [ ] TASK-2: b, decisions: [SPEC-1/D-01]\n", ["O-1"]),
        }
        for name, (plan, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(ids_for_task(plan), expected)


class RequirementsCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def write(self, name, data):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_unreadable_inputs_exit_one_with_a_message_and_no_rows(self):
        """Adversarial where: an undecodable byte, a directory in place of the
        spec, or a missing plan raises a traceback or exits 0 with empty output."""
        bad_bytes = self.write("bad.md", b"## Constraints\n- \xff\xfe\n")
        good = self.write("good.md", b"## Constraints\n- a\n")
        missing = os.path.join(self.dir, "none.md")
        cases = {
            "undecodable spec": [bad_bytes],
            "directory as spec": [self.dir],
            "missing plan": [good, "--for-task", "TASK-1", "--plan", missing],
            "task without plan": [good, "--for-task", "TASK-1"],
            "second positional": [good, "extra"],
        }
        for name, args in cases.items():
            with self.subTest(name):
                code, out, err = run_command(args)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("compass requirements:", err)

    def test_bom_and_crlf_spec_lists_the_same_rows_as_plain_utf8(self):
        """Adversarial where: a byte-order mark glued to the first heading hides
        the section, so a spec saved by a Windows editor lists zero rows."""
        plain = self.write("plain.md", b"## Constraints\n- a\n")
        bom = self.write("bom.md", b"\xef\xbb\xbf## Constraints\r\n- a\r\n")
        self.assertEqual(run_command([bom]), run_command([plain]))
        self.assertEqual(run_command([plain])[1].split()[0], "C-1")

    def test_folder_spec_is_cited_by_its_folder_name(self):
        """Adversarial where: a folder spec's `index.md` stem is used as the
        spec name, so a plan citing `<folder>/D-NN` claims nothing."""
        spec = self.write(
            "SPEC-9-x/index.md",
            b"## Constraints\n- a\n## Decisions\n- **D-01:** x\n- **D-02:** y\n",
        )
        plan = self.write("plan.md", b"- [ ] TASK-5: t, decisions: [SPEC-9-x/D-02]\n")
        code, out, _ = run_command([spec, "--for-task", "TASK-5", "--plan", plan])
        self.assertEqual(
            (code, [line.split()[0] for line in out.splitlines()]), (0, ["C-1", "D-02"])
        )

    def test_flag_given_as_option_value_is_a_usage_error(self):
        """Adversarial where: `--for-task --json` takes `--json` as the task id,
        so the command exits 0 with a plain listing for a task named `--json`."""
        spec = self.write("spec.md", b"## Constraints\n- a\n")
        plan = self.write("plan.md", b"- [ ] TASK-1: t\n")
        code, _, _ = run_command([spec, "--plan", plan, "--for-task", "--json"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
