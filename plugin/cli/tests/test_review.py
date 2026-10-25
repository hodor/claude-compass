"""Tests for `compass review` and `reviewlib`: a request goes out only when the
document sits in an Obsidian vault that Obsidian lists and whose Compass
Review plugin is on; the wait ends on a well-formed verdict for that request
and prints the document as the human left it.

Adversarial themes: configuration that is almost right (vault unlisted, plugin
files present but disabled, a corrupt vault list), verdict files that are
half-written, for another request, or carry an unknown verdict, a timeout,
the never-exit-2 contract, and the pending set the guard reads.

Every test runs in a temp project with `COMPASS_OBSIDIAN_CONFIG` pointing at
a temp vault list, and stubs the URI opener and the focus probe, so no test
touches the real Obsidian.
"""

import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewlib  # noqa: E402
from review_surfaces import obsidian as obsidian_surface  # noqa: E402


class ReviewProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / ".compass"
        (self.vault / "specs").mkdir(parents=True)
        self.doc = self.vault / "specs" / "SPEC-001-x.md"
        self.doc.write_text("---\ntitle: x\n---\n\n# X\n", encoding="utf-8")
        self.config = self.tmp / "obsidian.json"
        env = {"COMPASS_OBSIDIAN_CONFIG": str(self.config), "CLAUDE_PROJECT_DIR": str(self.tmp)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.opened = []
        for target, value in [("open_uri", self.opened.append), ("has_focus", lambda: False)]:
            p = mock.patch.object(obsidian_surface, target, value)
            p.start()
            self.addCleanup(p.stop)

    def configure(self, listed=True, plugin="on"):
        obsidian = self.vault / ".obsidian"
        obsidian.mkdir(exist_ok=True)
        vaults = {"abc123": {"path": str(self.vault)}} if listed else {"zzz": {"path": str(self.tmp / "other")}}
        self.config.write_text(json.dumps({"vaults": vaults}), encoding="utf-8")
        if plugin in ("on", "off"):
            d = obsidian / "plugins" / obsidian_surface.PLUGIN_ID
            d.mkdir(parents=True, exist_ok=True)
            (d / "main.js").write_text("//", encoding="utf-8")
            enabled = ["other-plugin"] + ([obsidian_surface.PLUGIN_ID] if plugin == "on" else [])
            (obsidian / "community-plugins.json").write_text(json.dumps(enabled), encoding="utf-8")

    def review(self, *args):
        module = importlib.import_module("commands.review")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = module.run(list(args))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def answer_later(self, verdict, delay=0.3, raw=None, rid=None):
        """Write a verdict for the first request that appears, after `delay`."""
        directory = reviewlib.review_dir(self.vault)

        def write():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                requests = list(directory.glob("*.request.json")) if directory.is_dir() else []
                if requests:
                    time.sleep(delay)
                    req = json.loads(requests[0].read_text(encoding="utf-8"))
                    target = reviewlib.verdict_path(requests[0])
                    body = raw if raw is not None else json.dumps(
                        {"id": rid or req["id"], "file": req["file"], "verdict": verdict, "notes": "n", "at": "t"})
                    target.write_text(body, encoding="utf-8")
                    return
                time.sleep(0.05)

        thread = threading.Thread(target=write, daemon=True)
        thread.start()
        return thread


class Configuration(ReviewProject):
    def test_no_obsidian_folder_is_not_configured(self):
        code, out, _ = self.review(str(self.doc), "--no-wait")
        self.assertEqual(code, 1)
        self.assertTrue(out.startswith("not configured: no Obsidian vault"), out)
        self.assertEqual(self.opened, [])

    def test_vault_obsidian_does_not_list(self):
        self.configure(listed=False)
        code, out, _ = self.review(str(self.doc), "--no-wait")
        self.assertEqual(code, 1)
        self.assertIn("does not list", out)
        self.assertFalse(reviewlib.review_dir(self.vault).exists(), "no request may be written")

    def test_plugin_installed_but_off(self):
        self.configure(plugin="off")
        code, out, _ = self.review(str(self.doc), "--no-wait")
        self.assertEqual(code, 1)
        self.assertIn("plugin is off", out)
        self.assertIn("compass doctor", out)

    def test_plugin_absent(self):
        self.configure(plugin="absent")
        self.assertEqual(obsidian_surface.plugin_state(self.vault), "absent")

    def test_corrupt_vault_list_reads_as_unlisted(self):
        self.configure()
        self.config.write_text("{not json", encoding="utf-8")
        code, out, _ = self.review(str(self.doc), "--no-wait")
        self.assertEqual(code, 1)
        self.assertIn("does not list", out)

    def test_vault_path_matches_across_case_and_separators(self):
        self.configure()
        alt = str(self.vault).upper() if sys.platform == "win32" else str(self.vault) + os.sep
        self.config.write_text(json.dumps({"vaults": {"v9": {"path": alt}}}), encoding="utf-8")
        self.assertEqual(obsidian_surface.vault_id(self.vault), "v9")

    def test_missing_file(self):
        self.configure()
        code, out, _ = self.review(str(self.vault / "nope.md"), "--no-wait")
        self.assertEqual(code, 1)
        self.assertIn("is not a file", out)


class Request(ReviewProject):
    def test_no_wait_writes_request_and_opens_link(self):
        self.configure()
        code, out, _ = self.review(str(self.doc), "--title", "Spec one", "--no-wait")
        self.assertEqual(code, 0)
        first = out.splitlines()[0].split()
        self.assertEqual(first[0], "requested")
        self.assertEqual(first[2], "specs/SPEC-001-x.md")
        request = json.loads((reviewlib.review_dir(self.vault) / f"{first[1]}.request.json").read_text())
        self.assertEqual(request, {"id": first[1], "surface": "obsidian", "file": "specs/SPEC-001-x.md", "title": "Spec one", "return": True})
        self.assertEqual(len(self.opened), 1)
        self.assertTrue(self.opened[0].startswith("obsidian://compass-review?vault=abc123&request="))
        self.assertIn("tmp%2Freview%2F" + first[1] + ".request.json", self.opened[0])

    def test_focus_in_obsidian_means_no_step_aside(self):
        self.configure()
        with mock.patch.object(obsidian_surface, "has_focus", lambda: True):
            code, out, _ = self.review(str(self.doc), "--no-wait")
        rid = out.split()[1]
        request = json.loads((reviewlib.review_dir(self.vault) / f"{rid}.request.json").read_text())
        self.assertIs(request["return"], False)

    def test_two_requests_in_one_second_get_distinct_ids(self):
        self.configure()
        ids = {self.review(str(self.doc), "--no-wait")[1].split()[1] for _ in range(5)}
        self.assertEqual(len(ids), 5)


class Wait(ReviewProject):
    def test_verdict_mid_wait_prints_verdict_then_human_text(self):
        self.configure()
        self.answer_later("approved")
        self.doc.write_text("---\ntitle: x\n---\n\n# X\n\nhuman edit\n", encoding="utf-8")
        code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("requested "))
        self.assertIn('"verdict": "approved"', out)
        marker = lines.index("--- specs/SPEC-001-x.md as the human left it ---")
        self.assertIn("human edit", "\n".join(lines[marker + 1:]))

    def test_half_written_verdict_is_not_taken(self):
        self.configure()
        self.answer_later(None, raw='{"id": "')
        code, out, _ = self.review(str(self.doc), "--timeout", "1.5")
        self.assertEqual(code, 1)
        self.assertTrue(out.splitlines()[-1].startswith("timeout "), out)

    def test_verdict_for_another_request_is_not_taken(self):
        self.configure()
        self.answer_later("approved", rid="someone-else")
        code, out, _ = self.review(str(self.doc), "--timeout", "1.5")
        self.assertEqual(code, 1)

    def test_unknown_verdict_word_is_not_taken(self):
        self.configure()
        self.answer_later("maybe")
        code, _, _ = self.review(str(self.doc), "--timeout", "1.5")
        self.assertEqual(code, 1)

    def test_changes_verdict_is_taken(self):
        self.configure()
        self.answer_later("changes")
        code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0)
        self.assertIn('"verdict": "changes"', out)


class StatusAndPending(ReviewProject):
    def test_status_lists_only_unanswered(self):
        self.configure()
        a = self.review(str(self.doc), "--no-wait")[1].split()[1]
        b = self.review(str(self.doc), "--no-wait")[1].split()[1]
        (reviewlib.review_dir(self.vault) / f"{a}.verdict.json").write_text("{}", encoding="utf-8")
        code, out, _ = self.review("--status")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), f"pending {b} specs/SPEC-001-x.md")

    def test_under_review_matches_only_the_reviewed_file(self):
        self.configure()
        self.review(str(self.doc), "--no-wait")
        other = self.vault / "specs" / "SPEC-002-y.md"
        other.write_text("y", encoding="utf-8")
        self.assertIsNotNone(reviewlib.under_review(self.vault, self.doc))
        self.assertIsNone(reviewlib.under_review(self.vault, other))
        self.assertIsNone(reviewlib.under_review(self.vault, self.tmp / "outside.md"))


class Install(ReviewProject):
    def setUp(self):
        super().setUp()
        self.src = self.tmp / "shipped"
        self.src.mkdir()
        for name in obsidian_surface.PLUGIN_FILES:
            (self.src / name).write_text(f"// {name}", encoding="utf-8")

    def test_no_obsidian_folder_is_left_alone(self):
        msg = obsidian_surface.install_plugin(self.vault, self.src)
        self.assertTrue(msg.startswith("skipped"), msg)
        self.assertFalse((self.vault / ".obsidian").exists())
        self.assertFalse((self.tmp / ".obsidian").exists())

    def test_a_vault_above_the_project_is_never_touched(self):
        outer = self.tmp / "outer"
        project = outer / "proj"
        (project / ".compass").mkdir(parents=True)
        (outer / ".obsidian").mkdir()
        msg = obsidian_surface.install_plugin(project / ".compass", self.src)
        self.assertTrue(msg.startswith("skipped"), msg)
        self.assertFalse((outer / ".obsidian" / "plugins").exists())

    def test_installs_and_keeps_other_plugins(self):
        obsidian = self.vault / ".obsidian"
        obsidian.mkdir()
        (obsidian / "community-plugins.json").write_text('["dataview", "kanban"]', encoding="utf-8")
        msg = obsidian_surface.install_plugin(self.vault, self.src)
        self.assertTrue(msg.startswith("installed"), msg)
        self.assertEqual(json.loads((obsidian / "community-plugins.json").read_text()),
                         ["dataview", "kanban", obsidian_surface.PLUGIN_ID])
        for name in obsidian_surface.PLUGIN_FILES:
            self.assertEqual((obsidian / "plugins" / obsidian_surface.PLUGIN_ID / name).read_text(), f"// {name}")
        obsidian_surface.install_plugin(self.vault, self.src)
        self.assertEqual(json.loads((obsidian / "community-plugins.json").read_text()).count(obsidian_surface.PLUGIN_ID), 1)

    def test_project_root_vault_is_used_when_compass_has_none(self):
        (self.tmp / ".obsidian").mkdir()
        obsidian_surface.install_plugin(self.vault, self.src)
        self.assertTrue((self.tmp / ".obsidian" / "plugins" / obsidian_surface.PLUGIN_ID / "main.js").is_file())
        self.assertEqual(json.loads((self.tmp / ".obsidian" / "community-plugins.json").read_text()), [obsidian_surface.PLUGIN_ID])

    def test_unparseable_list_is_left_untouched(self):
        obsidian = self.vault / ".obsidian"
        obsidian.mkdir()
        (obsidian / "community-plugins.json").write_text("{oops", encoding="utf-8")
        msg = obsidian_surface.install_plugin(self.vault, self.src)
        self.assertIn("does not parse", msg)
        self.assertEqual((obsidian / "community-plugins.json").read_text(), "{oops")

    def test_missing_shipped_files_installs_nothing(self):
        (self.vault / ".obsidian").mkdir()
        (self.src / "main.js").unlink()
        msg = obsidian_surface.install_plugin(self.vault, self.src)
        self.assertIn("missing", msg)
        self.assertFalse((self.vault / ".obsidian" / "plugins").exists())

    def test_bases_are_added_once_and_never_replace_an_edited_one(self):
        (self.vault / ".obsidian").mkdir()
        bases = self.tmp / "bases"
        bases.mkdir()
        for name in obsidian_surface.BASE_FILES:
            (bases / name).write_text(f"shipped {name}", encoding="utf-8")
        (self.vault / "lessons.base").write_text("mine", encoding="utf-8")
        msg = obsidian_surface.install_plugin(self.vault, self.src, bases)
        self.assertIn("added review-inbox.base", msg)
        self.assertNotIn("lessons.base", msg)
        self.assertEqual((self.vault / "lessons.base").read_text(), "mine")
        self.assertEqual((self.vault / "review-inbox.base").read_text(), "shipped review-inbox.base")
        self.assertNotIn("added", obsidian_surface.install_plugin(self.vault, self.src, bases))

    def test_bases_go_to_compass_even_when_the_vault_is_the_project(self):
        (self.tmp / ".obsidian").mkdir()
        obsidian_surface.install_plugin(self.vault, self.src, obsidian_surface.shipped_bases_dir())
        for name in obsidian_surface.BASE_FILES:
            self.assertTrue((self.vault / name).is_file(), name)
            self.assertFalse((self.tmp / name).exists(), name)

    def test_shipped_plugin_dir_resolves_in_the_source_tree(self):
        self.assertTrue((obsidian_surface.shipped_plugin_dir() / "main.js").is_file())


class Usage(ReviewProject):
    def test_usage_errors_exit_1_never_2(self):
        for args in (["--status", "--install"], [], ["--timeout"], ["--timeout", "x", "f"], ["--timeout", "0", "f"], ["--bogus", "f"], ["a", "b"]):
            code, _, err = self.review(*args)
            self.assertEqual(code, 1, args)
            self.assertIn("usage:", err)

    def test_registered_in_cli(self):
        import maincli
        self.assertIn("review", maincli.VALID_COMMANDS)


if __name__ == "__main__":
    unittest.main()
