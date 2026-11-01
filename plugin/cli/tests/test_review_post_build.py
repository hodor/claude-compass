"""Tests for the branches the editor-check and delivery-confirmation code
contains beyond its stated contract: the report that must not install, the
Obsidian install that fails, the per-editor listing kept for one review, the
waiter's re-check before it withdraws, the sweep of old claims, unreadable
shipped files, version text that is not a plain number, and the Windows `.cmd`
shim that now receives a listing and an install.

Adversarial themes: a status report that changes the machine it describes; an
exception that leaves "do not install" switched on; one editor's listing used
for another; a claim landing between the waiter's last look and its withdrawal;
a sweep that stops at the first entry it cannot remove; a shipped package that
cannot be read; version text with a suffix, a prefix or nothing at all; an
editor path that cmd.exe splits.

No editor is started: the VS Code and Cursor command lines are recorded by the
fakes of `test_review_vscode.py` and the Obsidian opener is stubbed by
`ReviewProject`. The Windows shim tests run a real `.cmd` stand-in for the
editor and only on Windows.
"""

import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import review_surfaces  # noqa: E402
import reviewlib  # noqa: E402
import test_review_unconfirmed as un  # noqa: E402
import test_review_vscode as vs  # noqa: E402
from review_surfaces import obsidian as obsidian_surface  # noqa: E402
from test_review import ReviewProject  # noqa: E402


def vscode_module():
    return importlib.import_module("review_surfaces.vscode")


class ReportsStayReadOnly(un.Editors):
    def test_the_editor_report_never_installs_an_extension_and_releases_the_switch(self):
        """Adversarial where: `compass doctor` installs the extension it is
        only meant to describe (the check that makes a review install is the
        same one the report runs), or an error raised while checking leaves
        installing switched off for every later review in the process."""
        project, _ = self.make_project()
        vault = project / ".compass"
        with self.fakes():
            self.put_on_path("code")
            self.installed = []
            for setting in (None, "vscode"):
                with self.subTest(setting=setting), mock.patch.object(reviewlib, "review_editor", lambda v: setting):
                    self.launched.clear()
                    status, detail, _ = reviewlib.editor_report(vault)
                    self.assertNotIn("install", self.ops())
                    self.assertEqual(self.installed, [])
                    self.assertTrue(review_surfaces.may_install())
                    self.assertEqual(status, "WARN" if setting else "OK", detail)
            self.installed = [(vs.extension_id(), un.shipped_version())]
            with mock.patch.object(reviewlib, "review_editor", lambda v: None):
                status, detail, _ = reviewlib.editor_report(vault)
            self.assertEqual((status, detail), ("OK", "reviews open in vscode"))
            boom = mock.patch.object(vscode_module(), "configuration", side_effect=RuntimeError("boom"))
            with boom, mock.patch.object(reviewlib, "review_editor", lambda v: None):
                with self.assertRaises(RuntimeError):
                    reviewlib.editor_report(vault)
            self.assertTrue(review_surfaces.may_install())


class ObsidianInstallFailures(ReviewProject):
    def review_obsidian(self, *args):
        with mock.patch.object(review_surfaces, "SURFACES", [obsidian_surface]):
            return self.review(str(self.doc), *args)

    def test_an_install_that_cannot_complete_leaves_the_vault_not_configured_and_never_raises(self):
        """Adversarial where: the plugin folder cannot be created, the plugin
        list cannot be read, or the shipped files are missing, and the error
        escapes the review (a traceback instead of the terminal fallback), or
        the vault is called configured and a request is written for a plugin
        that is not there."""
        rows = {}

        def folder_is_a_file():
            self.configure(plugin="absent")
            (self.vault / ".obsidian" / "plugins").write_text("not a folder", encoding="utf-8")

        def list_is_a_folder():
            self.configure(plugin="absent")
            (self.vault / ".obsidian" / "community-plugins.json").mkdir()

        def nothing_shipped():
            self.configure(plugin="absent")
            empty = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
            patcher = mock.patch.object(obsidian_surface, "shipped_plugin_dir", lambda: empty)
            patcher.start()
            self.addCleanup(patcher.stop)

        rows["plugins path is a file"] = (folder_is_a_file, "could not be installed")
        rows["plugin list is a folder"] = (list_is_a_folder, "off")
        rows["no shipped files"] = (nothing_shipped, "absent")
        for name, (arrange, word) in rows.items():
            with self.subTest(row=name):
                shutil.rmtree(self.vault / ".obsidian", ignore_errors=True)
                arrange()
                context, reason = obsidian_surface.configuration(self.doc)
                self.assertIsNone(context)
                self.assertIn(word, reason)
        self.configure(plugin="absent")
        (self.vault / ".obsidian" / "plugins").write_text("not a folder", encoding="utf-8")
        code, out, err = self.review_obsidian("--no-wait")
        self.assertEqual(code, 1, out + err)
        self.assertTrue(out.startswith("not configured:"), out)
        directory = reviewlib.review_dir(self.vault)
        self.assertEqual(list(directory.glob("*")) if directory.is_dir() else [], [])

    def test_a_check_only_pass_leaves_an_absent_plugin_absent(self):
        """Adversarial where: the read-only pass creates the plugin folder or
        lists the plugin as enabled while describing the vault."""
        self.configure(plugin="absent")
        before = sorted(p.relative_to(self.vault).as_posix() for p in self.vault.rglob("*"))
        with review_surfaces.check_only():
            context, reason = obsidian_surface.configuration(self.doc)
        self.assertIsNone(context)
        self.assertIn("absent", reason)
        after = sorted(p.relative_to(self.vault).as_posix() for p in self.vault.rglob("*"))
        self.assertEqual(before, after)


class ListingKeptPerEditor(un.Editors):
    def test_a_listing_is_kept_for_its_own_editor_only_and_a_failed_one_is_kept_too(self):
        """Adversarial where: one editor's answer stands in for the other's
        (so Cursor is judged by VS Code's extension list), a listing taken
        before an install is trusted after it, a failed listing is asked for
        again by every file of one review, a kept answer outlives the block, or
        an error inside the block leaves the cache switched on."""
        _, spec = self.make_project()
        code, cursor = vs.surface("vscode"), vs.surface("cursor")
        with self.fakes():
            self.put_on_path("code", "cursor")
            self.installed = [(vs.extension_id(), un.shipped_version())]
            with review_surfaces.shared_listings():
                self.assertIsNone(code.configuration(spec)[1])
                self.installed = []
                self.assertIsNone(cursor.configuration(spec)[1])
                self.assertEqual(self.ops(), ["list", "list", "install"])
                self.assertIsNone(code.configuration(spec)[1])
                self.assertEqual(self.ops(), ["list", "list", "install"])
                self.assertIsNone(cursor.configuration(spec)[1])
                self.assertEqual(self.ops(), ["list", "list", "install", "list"])
            self.assertIsNone(review_surfaces.listing_cache())
            self.launched.clear()
            self.rules = {(None, "list"): {"exit": 1, "stderr": "boom"}}
            with review_surfaces.shared_listings():
                first = code.configuration(spec)
                second = code.configuration(spec)
            self.assertEqual(self.ops(), ["list"])
            self.assertIsNone(first[0])
            self.assertEqual(first, second)
            code.configuration(spec)
            self.assertEqual(self.ops(), ["list", "list"])
            with self.assertRaises(RuntimeError):
                with review_surfaces.shared_listings():
                    raise RuntimeError("stop")
            self.assertIsNone(review_surfaces.listing_cache())

    def test_a_review_that_fails_on_a_later_file_does_not_leave_its_listing_behind(self):
        """Adversarial where: `_prepare` raises for a missing second file and
        the listing taken for the first stays, so the next review judges the
        editor by a stale answer."""
        project, spec = self.make_project()
        (self.tmp / "gitconfig").write_text("", encoding="utf-8")
        env = {"CLAUDE_PROJECT_DIR": str(project), "GIT_CEILING_DIRECTORIES": str(self.tmp),
               "GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1"}
        module = importlib.import_module("commands.review")
        out, err = io.StringIO(), io.StringIO()
        with self.fakes(), mock.patch.dict(os.environ, env), \
                mock.patch.object(review_surfaces, "SURFACES", [vs.surface("vscode")]), \
                redirect_stdout(out), redirect_stderr(err):
            self.put_on_path("code")
            self.installed = [(vs.extension_id(), un.shipped_version())]
            code = module.run([str(spec), str(spec.with_name("missing.md")), "--no-wait"])
        self.assertEqual(code, 1, out.getvalue() + err.getvalue())
        self.assertIsNone(review_surfaces.listing_cache())


class ShippedExtensionProblems(un.Editors):
    def point_at(self, folder):
        patcher = mock.patch.object(vscode_module(), "shipped_extension_dir", lambda shipped_root=None: folder)
        patcher.start()
        self.addCleanup(patcher.stop)

    def folder_with(self, package=None, vsix=False):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        if package is not None:
            (folder / "package.json").write_text(package, encoding="utf-8")
        if vsix:
            (folder / "compass-review-9.9.9.vsix").write_bytes(b"PK")
        return folder

    def test_an_unreadable_shipped_package_or_a_missing_vsix_is_not_configured_with_a_reason(self):
        """Adversarial where: a shipped `package.json` that is absent, not
        JSON, not an object or lacking its version raises out of the check, or
        is read as "extension missing" and followed by an install of the wrong
        thing; a missing `.vsix` is reported as installed."""
        _, spec = self.make_project()
        good = json.dumps({"publisher": "Compass", "name": "compass-review", "version": "9.9.9"})
        rows = (
            ("no package.json", None, False, "package.json", []),
            ("not JSON", "{oops", False, "package.json", []),
            ("a list", "[]", False, "package.json", []),
            ("no version", json.dumps({"publisher": "a", "name": "b"}), False, "package.json", []),
            ("no .vsix shipped", good, False, "did not work", ["list"]),
        )
        with self.fakes():
            self.put_on_path("code")
            for label, package, vsix, word, ops in rows:
                with self.subTest(row=label):
                    self.point_at(self.folder_with(package, vsix))
                    self.launched.clear()
                    self.installed = []
                    context, reason = vs.surface("vscode").configuration(spec)
                    self.assertIsNone(context)
                    self.assertIn(word, reason)
                    self.assertEqual(self.ops(), ops)

    def test_version_text_is_compared_by_its_leading_dotted_number(self):
        """Adversarial where: a listed version with a trailing `.0`, a
        pre-release suffix, a `v` prefix, nothing at all, or a single part is
        compared as text or raises, so a current extension is reinstalled on
        every review or an unreadable version is taken as current."""
        _, spec = self.make_project()
        shipped = un.shipped_version()
        rows = (
            ("extra zero part", shipped + ".0", False),
            ("pre-release suffix", shipped + "-beta.1", False),
            ("single larger part", "1", False),
            ("v prefix", "v" + shipped, True),
            ("empty", "", True),
            ("words", "latest", True),
        )
        with self.fakes():
            self.put_on_path("code")
            for label, listed, installs in rows:
                with self.subTest(row=label):
                    self.launched.clear()
                    self.installed = [(vs.extension_id(), listed)]
                    context, reason = vs.surface("vscode").configuration(spec)
                    self.assertIsNone(reason)
                    self.assertEqual(self.ops(), ["list", "install"] if installs else ["list"])


class OldClaimSweep(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.vault = self.base / ".compass"
        self.directory = reviewlib.review_dir(self.vault)
        self.directory.mkdir(parents=True)
        self.document = self.base / "a.md"
        self.document.write_text("# A\n", encoding="utf-8")

    def age(self, path, seconds):
        stamp = time.time() - seconds
        os.utime(path, (stamp, stamp))

    def test_an_entry_the_sweep_cannot_remove_does_not_stop_it_or_the_new_request(self):
        """Adversarial where: an old `*.seen` that is a folder (or otherwise
        cannot be removed) raises out of `write_request`, or ends the sweep at
        the first such entry so the claims after it stay for ever; a claim
        whose request id contains dots is judged by the wrong request name."""
        stuck = self.directory / "aaa.seen"
        stuck.mkdir()
        self.age(stuck, reviewlib.ORPHAN_SECONDS * 2)
        old = self.directory / "zzz.seen"
        old.write_text("", encoding="utf-8")
        self.age(old, reviewlib.ORPHAN_SECONDS * 2)
        dotted_request = self.directory / "a.b.request.json"
        dotted_request.write_text("{}", encoding="utf-8")
        dotted = self.directory / "a.b.seen"
        dotted.write_text("", encoding="utf-8")
        self.age(dotted, reviewlib.ORPHAN_SECONDS * 2)
        _, path = reviewlib.write_request(self.vault, "vscode", self.base, self.document, commit="abc")
        self.assertTrue(path.is_file())
        self.assertFalse(old.exists())
        self.assertTrue(dotted.exists())


class WaiterReCheck(ReviewProject):
    """Drives `_wait` with a clock that jumps past the acknowledgement window
    on its second reading, running `at_window` at that moment."""

    def setUp(self):
        super().setUp()
        self.configure()
        self.module = importlib.import_module("commands.review")
        self.reads = 0
        self.at_window = lambda path, request: None

    def clock(self):
        self.reads += 1
        if self.reads == 1:
            return 0.0
        found = sorted(reviewlib.review_dir(self.vault).glob("*.request.json"))
        if self.reads == 2 and found:
            self.at_window(found[0], json.loads(found[0].read_text(encoding="utf-8")))
        return self.module.ACK_SECONDS + 1.0

    def run_review(self):
        fake = types.SimpleNamespace(monotonic=self.clock, sleep=lambda seconds: None)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(self.module, "time", fake), redirect_stdout(out), redirect_stderr(err):
            code = self.module.run([str(self.doc)])
        return code, out.getvalue(), err.getvalue()

    @staticmethod
    def answer(path, request):
        reviewlib.verdict_path(path).write_text(json.dumps(
            {"id": request["id"], "file": request["file"], "verdict": "approved", "notes": "n", "at": "t"}),
            encoding="utf-8")

    def test_a_claim_that_lands_as_the_window_closes_is_honoured(self):
        """Adversarial where: the waiter decides on the claim it saw at the
        start of the pass and withdraws a request whose `.seen` was written a
        moment before, so the human's open card loses its request."""
        def claim_and_answer(path, request):
            reviewlib.seen_path(path).write_text("", encoding="utf-8")
            self.answer(path, request)

        self.at_window = claim_and_answer
        code, out, err = self.run_review()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("not configured", out)
        self.assertIn('"verdict": "approved"', out)

    def test_a_request_withdrawn_as_the_window_closes_ends_as_withdrawn(self):
        """Adversarial where: a request removed by someone else at the moment
        the window closes is reported as an add-on that did not pick it up, so
        the human is told to reload an editor that did nothing wrong."""
        self.at_window = lambda path, request: path.unlink()
        code, out, err = self.run_review()
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("not configured", out)
        self.assertTrue(out.splitlines()[-1].startswith("withdrawn "), out)


SHIM_LISTING = (
    '@echo off\r\n'
    'echo ARGS=[%*]>>"%~dp0args.log"\r\n'
    'if "%~1"=="--list-extensions" (\r\n'
    '  echo ms-python.python@2025.1.0\r\n'
    '  echo {listed}\r\n'
    ')\r\n'
)


@unittest.skipUnless(sys.platform == "win32", "the editor command is a .cmd shim only on Windows")
class ThroughTheWindowsShim(unittest.TestCase):
    def shim_in(self, folder_name, listed=""):
        raw = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, raw, ignore_errors=True)
        folder = raw / folder_name
        folder.mkdir()
        shim = folder / "code.cmd"
        shim.write_bytes(SHIM_LISTING.format(listed=listed).encode("ascii"))
        return shim

    def test_the_listing_through_a_cmd_shim_reads_the_ids_and_versions(self):
        """Adversarial where: the listing run through a `.cmd` shim in a folder
        with a space is split at the space, its Windows line endings stick to
        the version, or its ids keep their case, so a current extension is
        reinstalled or a missing one is taken as present."""
        eid = vs.extension_id()
        shim = self.shim_in("bin dir", f"{eid.upper()}@{un.shipped_version()}")
        entries, problem = vscode_module().VSCODE.listed_extensions(str(shim))
        self.assertIsNone(problem)
        self.assertEqual(entries, [("ms-python.python", "2025.1.0"), (eid, un.shipped_version())])

    def test_a_shim_in_a_folder_with_cmd_metacharacters_still_lists_and_installs(self):
        """Adversarial where: the editor's own path contains `&` or `^`, the
        listing and the install hand it to cmd.exe unquoted, and the editor is
        reported as not configured (or runs a different command) although it
        works from the terminal."""
        for folder_name in ("R&D", "R^D"):
            with self.subTest(folder=folder_name):
                shim = self.shim_in(folder_name, "other.tool@1.0.0")
                entries, problem = vscode_module().VSCODE.listed_extensions(str(shim))
                self.assertIsNone(problem, problem)
                self.assertEqual(entries, [("ms-python.python", "2025.1.0"), ("other.tool", "1.0.0")])
                folder = shim.parent
                (folder / "package.json").write_text(
                    json.dumps({"publisher": "Compass", "name": "compass-review", "version": "9.9.9"}), encoding="utf-8")
                (folder / "compass-review-9.9.9.vsix").write_bytes(b"PK")
                with mock.patch.object(shutil, "which", lambda cmd, *a, **k: str(shim) if cmd == "code" else None), \
                        mock.patch.object(vscode_module(), "shipped_extension_dir", lambda root=None: folder):
                    done = vscode_module().VSCODE.install(folder)
                self.assertTrue(done.startswith("installed"), done)
                logged = (folder / "args.log").read_text(encoding="utf-8")
                self.assertIn("--install-extension", logged)
                self.assertIn("compass-review-9.9.9.vsix", logged)


if __name__ == "__main__":
    unittest.main()
