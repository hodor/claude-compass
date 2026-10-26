"""Edges of the git side of `compass review` that only the implementation
reveals: how the diff text is split into lines, a vault whose temp folder is
not ignored, a document under a path with spaces and non-ASCII letters, and a
request commit that no longer exists in the repository.

Every test builds the real temporary git repository of `GitReviewBase`.
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_review_git import GitReviewBase  # noqa: E402


def _changes_block(out):
    """The raw text between the `--- changes since` header and the document marker."""
    start = out.index("--- changes since ")
    end = out.index(" as the human left it ---")
    end = out.rindex("\n--- ", start, end)
    return out[start:end]


class DiffTextIsKeptVerbatim(GitReviewBase):
    def test_diff_lines_keep_carriage_returns_and_unicode_separators(self):
        """Adversarial where: the diff is split with `str.splitlines`, which
        also breaks on a bare CR, the CR of a CRLF pair, form feed and U+2028,
        so a line-ending-only change prints as two identical-looking lines and
        a changed line holding a separator is cut in two with the second half
        missing its `+`/`-` prefix."""
        rows = {
            "crlf conversion": ("crlf.md", "one\ntwo\n", "one\r\ntwo\r\n", "+one\r"),
            "line separator inside a line": ("sep.md", "a b\n", "a b\n", "+a b"),
            "form feed inside a line": ("ff.md", "a b\n", "a\x0cb\n", "+a\x0cb"),
        }
        for name, (rel, before, after, expected) in rows.items():
            with self.subTest(name):
                path = self.root / rel
                self.put(path, before)
                self.commit_all(f"add {rel}")

                def edit(path=path, after=after):
                    self.put(path, after)

                code, out, _ = self.run_review(during=edit)
                self.assertEqual(code, 0, out)
                self.assertIn(expected, _changes_block(out))


class TempFolderNotIgnored(GitReviewBase):
    def test_only_the_reviews_own_files_are_hidden_from_the_untracked_list(self):
        """Adversarial where: the request and verdict files appear as untracked
        when the repository does not ignore `.compass/tmp/`, or the hiding
        prefix is too wide and also hides a sibling such as `tmp/review-old/`
        or `tmp/other.txt`."""
        self.put(self.root / ".gitignore", "*.tmp\n")
        self.commit_all("stop ignoring the vault temp folder")
        tmp = self.vault / "tmp"

        def create():
            self.put(tmp / "other.txt", "x\n")
            self.put(tmp / "review-old" / "a.json", "{}\n")

        code, out, _ = self.run_review(during=create)
        self.assertEqual(code, 0, out)
        block = _changes_block(out).splitlines()
        untracked = sorted(line for line in block if line.startswith("untracked "))
        self.assertEqual(untracked, sorted([
            f"untracked {self.rel(tmp / 'other.txt')}",
            f"untracked {self.rel(tmp / 'review-old' / 'a.json')}",
        ]))


class UnusualPaths(GitReviewBase):
    SUB = "my pröject dir"

    def test_a_document_under_spaces_and_non_ascii_names_is_requested_and_diffed(self):
        """Adversarial where: the repository-relative path of the document is
        mangled by spaces or non-ASCII letters (`--show-prefix` quoting, a
        split on whitespace), so the dirty check refuses a clean document, the
        recorded commit is wrong, or the diff and untracked names are lost."""
        doc = self.vault / "specs" / "SPEC 002 ünï.md"
        self.put(doc, "# spaced\n")
        self.commit_all("spaced document")
        self.doc = doc
        head = self.head()

        def edit():
            self.put(doc, "# spaced\nedited\n")
            self.put(self.vault / "specs" / "new one.md", "n\n")

        code, out, _ = self.run_review(during=edit)
        self.assertEqual(code, 0, out)
        block = _changes_block(out)
        self.assertIn(f"--- changes since {head[:10]} ---", block)
        self.assertIn("+edited", block)
        self.assertIn(f"untracked {self.rel(self.vault / 'specs' / 'new one.md')}", block)


class RequestCommitNoLongerExists(GitReviewBase):
    def test_a_commit_that_was_pruned_still_delivers_the_verdict_and_the_document(self):
        """Adversarial where: when the request's commit has been rebased away
        and collected, the failed `git diff` aborts the command (traceback,
        exit 2, no document text) instead of reporting the failure in the
        changes block and carrying on."""
        def rewrite_history():
            run = lambda *a: subprocess.run(["git", *a], cwd=self.root, capture_output=True, check=True)
            run("commit", "--amend", "-q", "-m", "second, rewritten", "--allow-empty")
            run("commit", "--amend", "-q", "--date=2001-01-01T00:00:00", "-m", "second, rewritten again")
            run("reflog", "expire", "--expire=now", "--all")
            run("gc", "--prune=now", "-q")

        original = self.head()
        code, out, _ = self.run_review(during=rewrite_history)
        self.assertNotEqual(self.head(), original)
        self.assertEqual(code, 0, out)
        self.assertIn(f"--- changes since {original[:10]} ---", out)
        self.assertIn("(git diff failed:", out)
        self.assertIn("--- specs/SPEC-001-x.md as the human left it ---", out)
        self.assertTrue(out.rstrip().endswith("# X"), out)


class DiffOutputIsBounded(GitReviewBase):
    def test_a_huge_diff_prints_the_cap_and_names_the_rest(self):
        """Adversarial where: a change of thousands of lines floods the
        session; the diff stops at the cap and one line names what is left."""
        import reviewlib
        path = self.root / "big.md"
        self.put(path, "start\n")
        self.commit_all("add big.md")

        def edit(path=path):
            self.put(path, "".join(f"line {n}\n" for n in range(reviewlib.MAX_DIFF_LINES * 2)))

        code, out, _ = self.run_review(during=edit)
        self.assertEqual(code, 0, out)
        block = _changes_block(out).split("\n")
        self.assertLessEqual(len(block), reviewlib.MAX_DIFF_LINES + 3)
        self.assertRegex(block[-1] if block[-1] else block[-2], r"^\(\d+ more diff lines: git diff [0-9a-f]+\)$")


class UndecodableDocument(GitReviewBase):
    def test_a_document_with_invalid_utf8_still_prints_after_the_verdict(self):
        """Adversarial where: the document text is read strictly as UTF-8
        and a stray byte the human pasted crashes the waiter after the
        verdict landed."""
        doc = self.doc

        def edit(doc=doc):
            doc.write_bytes(doc.read_bytes() + b"\xff\xfe stray\n")

        code, out, _ = self.run_review(during=edit)
        self.assertEqual(code, 0, out)
        self.assertIn("stray", out.split(" as the human left it ---", 1)[1])


if __name__ == "__main__":
    unittest.main()
