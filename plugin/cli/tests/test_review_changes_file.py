"""Tests for the change record `compass review` saves: when a review lists a
document an earlier review of this vault already listed, the request is
joined by `<id>.changes.diff` beside it, holding `git diff <sha> -- <file>`
for each listed file, `<sha>` being the commit that earlier review was sent
at (recorded in its request as `commit`). A first review and a file whose
content still equals what the earlier review showed write nothing, and the
record leaves with its request.

Adversarial themes: the baseline taken from the first review instead of the
latest one, the head commit used where the file's own earlier commit belongs
(an unrelated commit moves HEAD without touching the file), one file's
baseline applied to another, text-mode writes that turn line endings or
Unicode into something git did not print, and a record that outlives its
withdrawn request.

The fixture is the one `test_review.py` builds: a committed temp project, a
stubbed URI opener and focus probe, and no real Obsidian. Earlier reviews are
answered by writing a verdict file, so a later request does not withdraw them.
"""

import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from tests import test_review  # noqa: E402

DOC_REL = ".compass/specs/SPEC-001-x.md"
OTHER_REL = ".compass/specs/SPEC-002-y.md"


class ChangesFileProject(test_review.ReviewProject):
    def setUp(self):
        super().setUp()
        self.other = self.vault / "specs" / "SPEC-002-y.md"
        self.other.write_bytes(b"# Y\nother-one\nother-two\n")
        self.commit_all("second document")
        self.configure()

    def commit_all(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def send(self, *files):
        """Send a review of `files` without waiting; return its id."""
        code, out, err = self.review(*[str(f) for f in files], "--no-wait")
        self.assertEqual(code, 0, (out, err))
        return out.split()[1]

    def answer(self, rid):
        body = {"id": rid, "file": "x", "verdict": "approved", "notes": "", "at": "t"}
        reviewlib.verdict_path(self.request_path(rid)).write_text(json.dumps(body), encoding="utf-8")

    def request_path(self, rid):
        return reviewlib.review_dir(self.vault) / f"{rid}.request.json"

    def changes_path(self, rid):
        return reviewlib.review_dir(self.vault) / f"{rid}.changes.diff"

    def recorded_commit(self, rid):
        return json.loads(self.request_path(rid).read_text(encoding="utf-8"))["commit"]

    def git_diff(self, sha, rel):
        """The bytes `git diff <sha> -- <rel>` prints in the repository."""
        result = subprocess.run(["git", "diff", sha, "--", rel], cwd=self.tmp, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout, f"fixture error: {rel} does not differ from {sha}")
        return result.stdout

    def edit(self, path, data):
        path.write_bytes(data)


class ChangesRecordContent(ChangesFileProject):
    def test_second_review_of_a_changed_file_saves_git_diff_against_the_first_reviews_commit(self):
        """Adversarial where: the record is written as text, so CRLF line
        endings become CRCRLF or LF and Unicode is re-encoded; the diff is
        taken against HEAD or the working tree summary rather than the
        commit the earlier review recorded; or the record is not written
        for the second review at all."""
        first = self.send(self.doc)
        self.assertFalse(self.changes_path(first).exists(), "a first review writes no record")
        self.answer(first)
        first_sha = self.recorded_commit(first)
        self.assertEqual(first_sha, self.git("rev-parse", "HEAD").stdout.strip())

        self.edit(self.doc, "---\r\ntitle: x\r\n---\r\n\r\n# X\r\ncafé ☃ added\r\n".encode("utf-8"))
        self.commit_all("revise the document")
        second = self.send(self.doc)
        self.assertNotEqual(first_sha, self.recorded_commit(second))
        self.assertEqual(self.changes_path(second).read_bytes(), self.git_diff(first_sha, DOC_REL))

    def test_baseline_is_the_latest_earlier_review_not_the_first(self):
        """Adversarial where: the baseline is the oldest review that listed
        the file, so the third review shows edits the human already saw in
        the second."""
        first = self.send(self.doc)
        self.answer(first)
        self.edit(self.doc, b"---\ntitle: x\n---\n\n# X\nedit-one\n")
        self.commit_all("edit one")
        second = self.send(self.doc)
        self.answer(second)
        second_sha = self.recorded_commit(second)
        self.edit(self.doc, b"---\ntitle: x\n---\n\n# X\nedit-one\nedit-two\n")
        self.commit_all("edit two")
        third = self.send(self.doc)
        saved = self.changes_path(third).read_bytes()
        self.assertEqual(saved, self.git_diff(second_sha, DOC_REL))
        self.assertNotEqual(saved, self.git_diff(self.recorded_commit(first), DOC_REL))

    def test_each_listed_file_is_diffed_against_its_own_earlier_review(self):
        """Adversarial where: one baseline is applied to every file of a
        several-file review, a file never reviewed before gets a diff
        against another file's commit, or a file earlier reviewed only as the
        second file of a request is treated as new."""
        first = self.send(self.other, self.doc)
        self.answer(first)
        sha_first = self.recorded_commit(first)
        self.edit(self.doc, b"---\ntitle: x\n---\n\n# X\ndoc-edit-one\n")
        self.commit_all("doc edit one")
        second = self.send(self.other)
        self.answer(second)
        self.assertFalse(self.changes_path(second).exists(), "an unchanged file writes no record")
        sha_second = self.recorded_commit(second)
        self.edit(self.doc, b"---\ntitle: x\n---\n\n# X\ndoc-edit-one\ndoc-edit-two\n")
        self.edit(self.other, b"# Y\nother-one\nother-two\nother-edit\n")
        self.commit_all("both edited")

        third = self.send(self.doc, self.other)
        saved = self.changes_path(third).read_bytes()
        doc_part = self.git_diff(sha_first, DOC_REL)
        other_part = self.git_diff(sha_second, OTHER_REL)
        self.assertIn(doc_part, saved)
        self.assertIn(other_part, saved)
        self.assertEqual(len(saved), len(doc_part) + len(other_part))


class ChangesRecordAbsent(ChangesFileProject):
    def test_no_record_when_the_file_is_unchanged_even_though_head_moved(self):
        """Adversarial where: the record is written whenever an earlier
        review exists or HEAD differs from the recorded commit, instead of
        when the listed file differs; an unrelated commit between the
        reviews produces an empty or a spurious record. In a several-file
        review the unchanged file adds nothing beside the changed one."""
        first = self.send(self.doc, self.other)
        self.answer(first)
        sha = self.recorded_commit(first)
        side = self.vault / "specs" / "SPEC-003-unrelated.md"
        side.write_bytes(b"# Z\n")
        self.commit_all("unrelated document")
        self.assertNotEqual(sha, self.git("rev-parse", "HEAD").stdout.strip())

        second = self.send(self.doc, self.other)
        self.answer(second)
        self.assertFalse(self.changes_path(second).exists())

        self.edit(self.other, b"# Y\nother-one\nother-two\nonly-this-changed\n")
        self.commit_all("one document edited")
        third = self.send(self.doc, self.other)
        self.assertEqual(self.changes_path(third).read_bytes(),
                         self.git_diff(self.recorded_commit(second), OTHER_REL))


class ChangesRecordLifetime(ChangesFileProject):
    def pending_with_record(self):
        first = self.send(self.doc)
        self.answer(first)
        self.edit(self.doc, b"---\ntitle: x\n---\n\n# X\nrevised\n")
        self.commit_all("revise")
        second = self.send(self.doc)
        self.assertTrue(self.changes_path(second).exists(), "fixture error: no record to remove")
        return second

    def test_record_leaves_with_a_cancelled_request(self):
        """Adversarial where: `--cancel` removes the request file but the
        record stays in the review directory forever."""
        second = self.pending_with_record()
        code, out, err = self.review("--cancel", second)
        self.assertEqual(code, 0, (out, err))
        self.assertFalse(self.request_path(second).exists())
        self.assertFalse(self.changes_path(second).exists())

    def test_record_leaves_with_a_request_a_newer_review_replaces(self):
        """Adversarial where: a newer review of the same document withdraws
        the older request through a path that skips the record's removal,
        or removes the newer request's own record."""
        second = self.pending_with_record()
        third = self.send(self.doc)
        self.assertFalse(self.request_path(second).exists())
        self.assertFalse(self.changes_path(second).exists())
        self.assertTrue(self.request_path(third).exists())

    def test_withdrawing_through_reviewlib_removes_the_record(self):
        """Adversarial where: only the CLI flag removes the record, while
        `reviewlib.cancel`, the call every withdrawal goes through, leaves
        it."""
        second = self.pending_with_record()
        self.assertTrue(reviewlib.cancel(self.vault, second))
        self.assertFalse(self.changes_path(second).exists())


if __name__ == "__main__":
    unittest.main()
