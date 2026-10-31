"""Tests that an editor is asked which extensions it holds once per review,
however many files the review lists.

Adversarial themes: a listing repeated for every file; an answer that outlives
one review (so a later review reads an old listing); an answer that survives
an install.
"""

import importlib
import io
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import review_surfaces  # noqa: E402
import test_review_unconfirmed as un  # noqa: E402
import test_review_vscode as vs  # noqa: E402


class ListingOncePerReview(un.Editors):
    def setUp(self):
        super().setUp()
        self.project, self.spec = self.make_project()
        self.others = []
        for name in ("SPEC-002-y.md", "SPEC-003-z.md"):
            other = self.project / ".compass" / "specs" / name
            other.write_text("# " + name + "\n", encoding="utf-8")
            self.others.append(other)
        (self.tmp / "gitconfig").write_text("", encoding="utf-8")
        env = {
            "CLAUDE_PROJECT_DIR": str(self.project),
            "GIT_CEILING_DIRECTORIES": str(self.tmp),
            "GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for args in (["init", "-q"], ["config", "user.name", "Tester"],
                     ["config", "user.email", "tester@example.invalid"],
                     ["add", ".compass"], ["commit", "-q", "-m", "first"]):
            vs.REAL_RUN(["git", *args], cwd=self.project, check=True, capture_output=True)
        self.module = importlib.import_module("commands.review")
        patcher = mock.patch.object(vs.surface("vscode"), "has_focus", lambda: False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def review(self, files):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(review_surfaces, "SURFACES", [vs.surface("vscode")]), \
                redirect_stdout(out), redirect_stderr(err):
            code = self.module.run([*map(str, files), "--no-wait"])
        return code, out.getvalue(), err.getvalue()

    def test_a_three_file_review_asks_the_editor_for_its_extensions_once(self):
        """Adversarial where: the listing runs once per file (three
        subprocesses for one review), or the shared answer is dropped before
        the second file is checked."""
        with self.fakes():
            self.put_on_path("code")
            self.installed = [(vs.extension_id(), un.shipped_version())]
            code, out, err = self.review([self.spec, *self.others])
            self.assertEqual(code, 0, out + err)
            self.assertEqual(self.ops().count("list"), 1, self.ops())
            self.assertEqual(self.ops().count("install"), 0)

    def test_a_second_review_asks_again(self):
        """Adversarial where: the answer outlives the review that learned it,
        so an extension installed or removed between two reviews is judged by
        the first review's listing."""
        with self.fakes():
            self.put_on_path("code")
            self.installed = [(vs.extension_id(), un.shipped_version())]
            self.assertEqual(self.review([self.spec])[0], 0)
            self.assertIsNone(review_surfaces.listing_cache())
            self.installed = []
            self.assertEqual(self.review([self.others[0]])[0], 0)
            self.assertEqual(self.ops().count("list"), 2, self.ops())
            self.assertEqual(self.ops().count("install"), 1, self.ops())

    def test_an_install_makes_the_next_file_ask_again(self):
        """Adversarial where: the listing taken before an install is still
        used afterwards, so a file checked later is judged by an extension
        list that no longer holds."""
        with self.fakes():
            self.put_on_path("code")
            self.installed = []
            code, out, err = self.review([self.spec, *self.others])
            self.assertEqual(code, 0, out + err)
            self.assertEqual(self.ops().count("install"), 1, self.ops())
            self.assertEqual(self.ops().count("list"), 2, self.ops())


if __name__ == "__main__":
    unittest.main()
