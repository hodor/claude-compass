"""Tests for the branches the per-file verdict code contains beyond its stated
contract: the way an entry's verdict is looked up (by file name, falling back
to the top-level verdict), the validity check that tests whether the key is
present, and the printing of an answer whose per-file and top-level verdicts
disagree.

Adversarial themes: a verdict looked up by position instead of by name, an
answer that lists fewer entries than the request has files, a verdict key
that is present but empty, and an answer whose top-level verdict contradicts
its files.

The fixture is the several-file project of `test_review_files.py`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from tests.test_review_files import MultiFileProject  # noqa: E402

PLAN = "plans/PLAN-001-z.md"
SPEC1 = "specs/SPEC-001-x.md"
SPEC2 = "specs/SPEC-002-y.md"


def entry(file, verdict=None, read=True, note=None):
    out = {"file": file, "read": read}
    if verdict is not None:
        out["verdict"] = verdict
    if note is not None:
        out["note"] = note
    return out


class VerdictLookup(MultiFileProject):
    def printed(self, files, top):
        self.answer(files, extra={"verdict": top})
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        self.assertEqual(code, 0, out)
        return out

    def test_the_verdict_of_an_entry_is_looked_up_by_file_name_not_by_position(self):
        """Adversarial where: the answer lists its entries in another order than
        the request, or lists fewer entries than the request has files, and the
        verdict word of a line comes from the entry at the same position
        instead of the entry for the same file; or a file with no entry takes
        its neighbour's verdict instead of the top-level one."""
        rows = [
            ("entries in reverse order",
             "changes",
             [entry(SPEC2, "changes"), entry(SPEC1, "approved"), entry(PLAN, "approved")],
             [f"file {PLAN} approved read", f"file {SPEC1} approved read", f"file {SPEC2} changes read"]),
            ("the answer lists only the first file",
             "changes",
             [entry(PLAN, "approved")],
             [f"file {PLAN} approved read", f"file {SPEC1} changes unread", f"file {SPEC2} changes unread"]),
            ("the answer lists only the last file",
             "changes",
             [entry(SPEC2, "approved")],
             [f"file {PLAN} changes unread", f"file {SPEC1} changes unread", f"file {SPEC2} approved read"]),
            ("an extra entry beyond the request carries a verdict of its own",
             "changes",
             [entry(PLAN, "approved"), entry(SPEC1, "approved"), entry(SPEC2, "approved"),
              entry("specs/ghost.md", "changes", note="ghost note")],
             [f"file {PLAN} approved read", f"file {SPEC1} approved read", f"file {SPEC2} approved read"]),
        ]
        for name, top, files, expected in rows:
            with self.subTest(name):
                out = self.printed(files, top)
                lines = [ln for ln in out.splitlines() if ln.startswith("file ")]
                self.assertEqual(lines, expected)
                self.assertNotIn("ghost", "\n".join(lines))
                self.assertNotIn("as the human left it", out)

    def test_a_renamed_file_without_its_own_verdict_takes_the_top_level_one_before_the_read_mark(self):
        """Adversarial where: an older add-on's answer (no per-file verdict)
        for a file renamed during the review prints the verdict word after the
        `(renamed from ...)` tail, or prints no word at all."""
        renamed = self.spec2.with_name("SPEC-002-renamed.md")
        files = [entry(PLAN), entry(SPEC1), entry("specs/SPEC-002-renamed.md", note="moved")]
        self.answer(files, extra={"verdict": "changes"}, during=lambda: self.spec2.rename(renamed))
        code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
        renamed.rename(self.spec2)
        self.assertEqual(code, 0, out)
        self.assertIn(f"file specs/SPEC-002-renamed.md changes read note: moved (renamed from {SPEC2})",
                      out.splitlines())


class ContradictoryAnswers(MultiFileProject):
    def test_per_file_verdicts_are_printed_as_given_whatever_the_top_level_verdict_says(self):
        """Adversarial where: a top-level `approved` flattens a file's own
        `changes` into `approved` (or the reverse), or a document with a note
        is not printed again for the human's words because the top-level
        verdict is `approved`."""
        rows = [
            ("top-level approved, one file changes with a note", "approved",
             [entry(PLAN, "approved"), entry(SPEC1, "changes", note="fix"), entry(SPEC2, "approved")],
             f"file {SPEC1} changes read note: fix", f"--- {SPEC1} as the human left it ---"),
            ("top-level changes, every file approved, one with a note", "changes",
             [entry(PLAN, "approved"), entry(SPEC1, "approved", note="nice"), entry(SPEC2, "approved")],
             f"file {SPEC1} approved read note: nice", f"--- {SPEC1} as the human left it ---"),
        ]
        for name, top, files, line, reprint in rows:
            with self.subTest(name):
                self.answer(files, extra={"verdict": top})
                code, out, _ = self.review(*map(str, self.trio), "--timeout", "5")
                self.assertEqual(code, 0, out)
                self.assertIn(line, out.splitlines())
                self.assertIn(reprint, out.splitlines())
                self.assertEqual(len([ln for ln in out.splitlines() if ln.startswith("--- ") and "as the human left it" in ln]), 1)


class VerdictKeyPresence(MultiFileProject):
    def test_a_verdict_key_that_is_present_but_empty_is_invalid(self):
        """Adversarial where: the validity check tests the value's truth
        instead of the key's presence, so `null`, `false`, `0` or `{}` is
        taken as 'no per-file verdict' and the answer is accepted."""
        request = {"id": "r1", "file": "a.md", "files": [{"file": "a.md"}, {"file": "b.md"}]}
        base = {"id": "r1", "verdict": "changes"}
        for name, value in [("null", None), ("false", False), ("zero", 0), ("empty object", {}), ("empty list", [])]:
            with self.subTest(name):
                files = [{"file": "a.md", "read": True, "verdict": value}, entry("b.md", "approved")]
                self.assertFalse(reviewlib.valid_verdict({**base, "files": files}, request))
