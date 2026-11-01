"""Tests for the per-file verdict of a several-file `compass review`: the
optional `verdict` of each `files` entry (`approved` or `changes`), its
validation, the `file <path> approved|changes read|unread ...` line printed
after the answer, the fallback to the top-level verdict for an entry that has
none, and the module docstring and pipeline rule that describe it.

Adversarial themes: a value outside the two words slipping through (or only the
first bad entry being caught), the top-level verdict painted on every file
when entries carry their own, an older answer with no per-file verdict losing
its lines, the verdict word printed in the wrong place on the line, and a
one-file review gaining lines it never had.

The fixture is the several-file project of `test_review_files.py`: a committed
temp project with three documents, a stubbed opener and no real Obsidian.
"""

import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from commands import review as review_command  # noqa: E402
from tests.test_review_files import MultiFileProject  # noqa: E402

PLAN = "plans/PLAN-001-z.md"
SPEC1 = "specs/SPEC-001-x.md"
SPEC2 = "specs/SPEC-002-y.md"
PIPELINE_RULE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             "templates", "rules", "compass-pipeline.md")


def entry(file, verdict=None, read=True, note=None):
    out = {"file": file, "read": read}
    if verdict is not None:
        out["verdict"] = verdict
    if note is not None:
        out["note"] = note
    return out


class PerFileVerdictValidation(MultiFileProject):
    def test_valid_verdict_accepts_exactly_approved_and_changes_per_file(self):
        """Adversarial where: any string is accepted as a per-file verdict,
        the check is case-blind or trims space, a non-string (number, boolean,
        list) passes, only the first entry is checked so one good entry
        excuses a bad one, or an entry without the field is rejected (an
        older add-on's answer must stay valid)."""
        request = {"id": "r1", "file": "a.md", "files": [{"file": "a.md"}, {"file": "b.md"}]}
        base = {"id": "r1", "verdict": "changes"}
        good = entry("a.md", "approved")
        rows = [
            ("approved", [entry("a.md", "approved"), entry("b.md", "approved")], True),
            ("changes", [entry("a.md", "changes"), entry("b.md", "changes")], True),
            ("one of each", [entry("a.md", "approved"), entry("b.md", "changes")], True),
            ("no per-file verdict at all", [entry("a.md"), entry("b.md")], True),
            ("only the second has one", [entry("a.md"), entry("b.md", "changes")], True),
            ("maybe", [entry("a.md", "maybe"), entry("b.md", "approved")], False),
            ("empty string", [entry("a.md", ""), entry("b.md", "approved")], False),
            ("capitalised", [entry("a.md", "Approved"), entry("b.md", "approved")], False),
            ("trailing space", [entry("a.md", "changes "), entry("b.md", "approved")], False),
            ("the word needs-changes", [entry("a.md", "needs changes"), entry("b.md", "approved")], False),
            ("a number", [{"file": "a.md", "read": True, "verdict": 1}], False),
            ("true", [{"file": "a.md", "read": True, "verdict": True}], False),
            ("a list", [{"file": "a.md", "read": True, "verdict": ["approved"]}], False),
            ("first good, second maybe", [good, entry("b.md", "maybe")], False),
            ("first maybe, second good", [entry("a.md", "maybe"), entry("b.md", "approved")], False),
        ]
        for name, files, ok in rows:
            with self.subTest(name):
                self.assertIs(bool(reviewlib.valid_verdict({**base, "files": files}, request)), ok)

    def test_the_waiter_does_not_take_a_verdict_with_an_unknown_per_file_verdict(self):
        """Adversarial where: the waiter prints marks built from an entry
        whose verdict is neither word, instead of waiting on for a valid
        answer."""
        self.answer([entry(PLAN, "approved"), entry(SPEC1, "maybe"), entry(SPEC2, "approved")])
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "1.5")
        self.assertEqual(code, 1)
        self.assertTrue(out.splitlines()[-1].startswith("timeout "), out)
        self.assertNotIn("file specs", out)


class FileLines(MultiFileProject):
    def file_lines(self, files, top):
        self.answer(files, extra={"verdict": top})
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        self.assertEqual(code, 0, out)
        self.assertIn(f'"verdict": "{top}"', out)
        return [ln for ln in out.splitlines() if ln.startswith("file ")]

    def test_each_file_line_carries_its_own_verdict_right_after_the_path(self):
        """Adversarial where: the top-level verdict is printed on every line
        although entries carry their own, a mixed answer prints the first
        file's verdict for all, the word lands after `read|unread` or after
        the note, an entry without a verdict prints nothing (or the wrong
        word) beside entries that have one, a listed file the answer never
        marks loses its verdict word, or a whitespace-only note grows a
        `note:` tail."""
        rows = [
            ("one changes in the middle among approved, with a multi-line note",
             "changes",
             [entry(PLAN, "approved"), entry(SPEC1, "changes", read=False, note="needs:\n  work"), entry(SPEC2, "approved")],
             [f"file {PLAN} approved read", f"file {SPEC1} changes unread note: needs: work", f"file {SPEC2} approved read"]),
            ("changes only in the first position",
             "changes",
             [entry(PLAN, "changes"), entry(SPEC1, "approved"), entry(SPEC2, "approved")],
             [f"file {PLAN} changes read", f"file {SPEC1} approved read", f"file {SPEC2} approved read"]),
            ("changes only in the last position",
             "changes",
             [entry(PLAN, "approved"), entry(SPEC1, "approved"), entry(SPEC2, "changes")],
             [f"file {PLAN} approved read", f"file {SPEC1} approved read", f"file {SPEC2} changes read"]),
            ("every file changes",
             "changes",
             [entry(p, "changes") for p in (PLAN, SPEC1, SPEC2)],
             [f"file {p} changes read" for p in (PLAN, SPEC1, SPEC2)]),
            ("every file approved, one unread",
             "approved",
             [entry(PLAN, "approved"), entry(SPEC1, "approved", read=False), entry(SPEC2, "approved")],
             [f"file {PLAN} approved read", f"file {SPEC1} approved unread", f"file {SPEC2} approved read"]),
            ("older answer, top-level approved, no per-file verdicts",
             "approved",
             [entry(PLAN), entry(SPEC1, read=False, note="n"), entry(SPEC2)],
             [f"file {PLAN} approved read", f"file {SPEC1} approved unread note: n", f"file {SPEC2} approved read"]),
            ("older answer, top-level changes, no per-file verdicts",
             "changes",
             [entry(PLAN), entry(SPEC1), entry(SPEC2, read=False)],
             [f"file {PLAN} changes read", f"file {SPEC1} changes read", f"file {SPEC2} changes unread"]),
            ("only the first entry carries a verdict, the others take the top-level one",
             "changes",
             [entry(PLAN, "approved"), entry(SPEC1), entry(SPEC2)],
             [f"file {PLAN} approved read", f"file {SPEC1} changes read", f"file {SPEC2} changes read"]),
            ("a listed file the answer does not mark takes the top-level verdict and reads unread",
             "changes",
             [entry(PLAN, "approved"), entry(SPEC1, "approved"), entry("specs/ghost.md", "changes")],
             [f"file {PLAN} approved read", f"file {SPEC1} approved read", f"file {SPEC2} changes unread"]),
            ("a whitespace-only note",
             "changes",
             [entry(PLAN, "changes", note=" \n\t "), entry(SPEC1, "approved"), entry(SPEC2, "approved")],
             [f"file {PLAN} changes read", f"file {SPEC1} approved read", f"file {SPEC2} approved read"]),
        ]
        for name, top, files, expected in rows:
            with self.subTest(name):
                self.assertEqual(self.file_lines(files, top), expected)

    def test_a_renamed_file_keeps_its_verdict_between_the_path_and_the_read_mark(self):
        """Adversarial where: the per-file verdict is looked up by the
        request's old name so a file the human renamed in Obsidian prints the
        top-level verdict instead of its own, or the verdict word lands after
        the note and the `(renamed from ...)` tail."""
        renamed = self.spec2.with_name("SPEC-002-renamed.md")
        files = [entry(PLAN, "approved"), entry(SPEC1, "approved"),
                 entry("specs/SPEC-002-renamed.md", "changes", note="moved")]
        self.answer(files, extra={"verdict": "changes"}, during=lambda: self.spec2.rename(renamed))
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        renamed.rename(self.spec2)
        self.assertEqual(code, 0, out)
        self.assertIn(f"file specs/SPEC-002-renamed.md changes read note: moved (renamed from {SPEC2})",
                      out.splitlines())

    def test_a_one_file_review_prints_no_file_line_whatever_the_verdict(self):
        """Adversarial where: the per-file line leaks into a one-file review
        (which has never printed one) once the verdict word exists."""
        self.answer(None, extra={"verdict": "changes"})
        code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0, out)
        self.assertEqual([ln for ln in out.splitlines() if ln.startswith("file ")], [])
        self.assertIn('"verdict": "changes"', out)


class DocumentedShape(unittest.TestCase):
    def test_the_review_docstring_documents_the_per_file_verdict_and_the_new_line(self):
        """Adversarial where: the docstring keeps the old
        `file <path> read|unread` line shape (so the caller's reader of the
        contract is wrong)."""
        doc = inspect.getdoc(review_command)
        self.assertIn("approved|changes read|unread", doc)
        self.assertNotIn("`file <path> read|unread", doc)

    def test_the_pipeline_rule_applies_each_files_verdict_to_that_document_alone(self):
        """Adversarial where: the rule in the 'Review in a visual surface'
        paragraph still tells the caller to treat a several-document review
        as one approve or one send-back, so a document approved beside a
        revised one is revised again or the approved one waits."""
        with open(PIPELINE_RULE, encoding="utf-8") as fh:
            text = fh.read()
        paragraph = re.search(r"^\*\*Review in a visual surface\.\*\*.*$", text, re.M).group(0)
        self.assertIn("`file` line", paragraph)
        self.assertRegex(paragraph, r"\balone\b")
        self.assertRegex(paragraph, r"\bapproved document\b")
        self.assertRegex(paragraph, r"\bchanges document\b")


if __name__ == "__main__":
    unittest.main()
