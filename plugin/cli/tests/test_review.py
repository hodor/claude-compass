"""Tests for `compass review` and `reviewlib`: a request goes out only when the
document sits in an Obsidian vault that Obsidian lists and whose Compass
Review plugin is on; the wait ends on a well-formed verdict for that request
and prints the document as the human left it.

Adversarial themes: configuration that is almost right (vault unlisted, plugin
files present but disabled, a corrupt vault list), verdict files that are
half-written, for another request, or carry an unknown verdict, a timeout,
the never-exit-2 contract, and the pending set the guard reads.

Every test runs in a temp project that is a committed git repository (a
document goes out only when committed), with `COMPASS_OBSIDIAN_CONFIG`
pointing at a temp vault list outside it, and stubs the URI opener and the
focus probe, so no test touches the real Obsidian. The git side of a review
(the dirty-document refusal, the recorded commit, the changes section) is
tested in `test_review_git.py`; here the repository is clean, so the changes
section is its header alone.
"""

import importlib
import io
import json
import os
import shutil
import subprocess
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
    """A temp directory holding `project/` (a git repository whose first
    commit holds the `.compass` vault and its spec) beside the Obsidian vault
    list and an empty git config, both outside the repository."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.tmp = self.base / "project"
        self.vault = self.tmp / ".compass"
        (self.vault / "specs").mkdir(parents=True)
        self.doc = self.vault / "specs" / "SPEC-001-x.md"
        self.doc.write_text("---\ntitle: x\n---\n\n# X\n", encoding="utf-8")
        self.config = self.base / "obsidian.json"
        (self.base / "gitconfig").write_text("", encoding="utf-8")
        env = {
            "COMPASS_OBSIDIAN_CONFIG": str(self.config),
            "CLAUDE_PROJECT_DIR": str(self.tmp),
            "GIT_CEILING_DIRECTORIES": str(self.base),
            "GIT_CONFIG_GLOBAL": str(self.base / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        (self.tmp / ".gitignore").write_text(".compass/tmp/\n.compass/.obsidian/\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Tester")
        self.git("config", "user.email", "tester@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "first")
        self.commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.opened = []
        for target, value in [("open_uri", self.opened.append), ("has_focus", lambda: False)]:
            p = mock.patch.object(obsidian_surface, target, value)
            p.start()
            self.addCleanup(p.stop)

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.tmp, capture_output=True,
                                text=True, encoding="utf-8")
        if result.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
        return result

    @property
    def changes_header(self):
        return f"--- changes since {self.commit[:reviewlib.SHORT_SHA]} ---"

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

    def answer_later(self, verdict, delay=0.3, raw=None, rid=None, during=None):
        """Write a verdict for the first request that appears, after `delay`;
        `during` runs first, standing for the human's edits while reviewing."""
        directory = reviewlib.review_dir(self.vault)

        def write():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                requests = list(directory.glob("*.request.json")) if directory.is_dir() else []
                if requests:
                    time.sleep(delay)
                    req = json.loads(requests[0].read_text(encoding="utf-8"))
                    if during:
                        during()
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
        self.assertEqual(request, {"id": first[1], "surface": "obsidian", "file": "specs/SPEC-001-x.md", "title": "Spec one", "return": True, "commit": self.commit})
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
        self.answer_later("approved", during=lambda: self.doc.write_text(
            "---\ntitle: x\n---\n\n# X\n\nhuman edit\n", encoding="utf-8"))
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

    def test_without_timeout_the_wait_outlasts_days(self):
        self.configure()
        module = importlib.import_module("commands.review")
        ticks = iter(range(10 ** 9))
        clock = mock.Mock(monotonic=lambda: next(ticks) * 86400.0, sleep=time.sleep)
        self.answer_later("approved", delay=1.0)
        with mock.patch.object(module, "time", clock):
            code, out, _ = self.review(str(self.doc))
        self.assertEqual(code, 0, out)
        self.assertIn('"verdict": "approved"', out)
        self.assertNotIn("timeout ", out)


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


class Carried(ReviewProject):
    """A verdict may carry `comments` (notes on other files) and `edited`
    (files the human changed); the waiter prints them for the session."""

    def answer_with(self, extra, delay=0.3):
        """Write an `approved` verdict plus `extra` fields for the first request
        that has no verdict yet."""
        directory = reviewlib.review_dir(self.vault)

        def write():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                requests = [p for p in sorted(directory.glob("*.request.json"))
                            if not reviewlib.verdict_path(p).exists()] if directory.is_dir() else []
                if requests:
                    time.sleep(delay)
                    req = json.loads(requests[0].read_text(encoding="utf-8"))
                    body = {"id": req["id"], "file": req["file"], "verdict": "approved", "notes": "n", "at": "t"}
                    body.update(extra)
                    reviewlib.verdict_path(requests[0]).write_text(json.dumps(body), encoding="utf-8")
                    return
                time.sleep(0.05)

        threading.Thread(target=write, daemon=True).start()

    def test_comments_then_edited_print_between_the_json_and_the_file_text(self):
        """Adversarial where: the carried lines are dropped, swapped (edited
        before comments), printed after the document text, or a note that itself
        contains `: ` is cut at its first colon."""
        self.configure()
        self.answer_with({
            "comments": [{"file": "specs/SPEC-002-y.md", "note": "why: unclear"},
                         {"file": "plans/PLAN-009-z.md", "note": "second"}],
            "edited": ["specs/SPEC-003-w.md", "specs/SPEC-001-x.md"],
        })
        code, out, _ = self.review(str(self.doc), "--timeout", "5")
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        marker = lines.index("--- specs/SPEC-001-x.md as the human left it ---")
        self.assertEqual(lines[marker - 1], self.changes_header, "nothing changed, so the section is its header")
        marker -= 1
        expected = [
            "comment specs/SPEC-002-y.md: why: unclear",
            "comment plans/PLAN-009-z.md: second",
            "edited specs/SPEC-003-w.md",
            "edited specs/SPEC-001-x.md",
        ]
        self.assertEqual(lines[marker - len(expected):marker], expected)
        self.assertEqual(lines[marker - len(expected) - 1], "}", "the verdict JSON ends before the carried lines")

    def test_only_one_of_the_two_fields_prints_only_its_lines(self):
        """Adversarial where: a verdict with `edited` but no `comments` (or the
        reverse) crashes on the missing key or prints an empty section line."""
        for name, extra, expected in [
            ("edited only", {"edited": ["specs/SPEC-003-w.md"]}, ["edited specs/SPEC-003-w.md"]),
            ("comments only", {"comments": [{"file": "a.md", "note": "b"}]}, ["comment a.md: b"]),
        ]:
            with self.subTest(name):
                shutil.rmtree(reviewlib.review_dir(self.vault), ignore_errors=True)
                self.configure()
                self.answer_with(extra)
                code, out, _ = self.review(str(self.doc), "--timeout", "5")
                self.assertEqual(code, 0, out)
                lines = out.splitlines()
                marker = lines.index("--- specs/SPEC-001-x.md as the human left it ---")
                self.assertEqual(lines[marker - 1], self.changes_header)
                marker -= 1
                self.assertEqual(lines[marker - len(expected):marker], expected)
                carried = [ln for ln in lines if ln.startswith(("comment ", "edited "))]
                self.assertEqual(carried, expected)

    def test_a_verdict_without_the_fields_prints_exactly_as_before(self):
        """Adversarial where: a verdict with no `comments`/`edited`, or with
        both empty, gains stray lines or a changed layout."""
        for name, extra in [("absent", {}), ("empty lists", {"comments": [], "edited": []})]:
            with self.subTest(name):
                shutil.rmtree(reviewlib.review_dir(self.vault), ignore_errors=True)
                self.configure()
                self.answer_with(extra)
                code, out, _ = self.review(str(self.doc), "--timeout", "5")
                self.assertEqual(code, 0, out)
                first, _, rest = out.partition("\n")
                self.assertTrue(first.startswith("requested "), first)
                verdict_file = next(reviewlib.review_dir(self.vault).glob("*.verdict.json"))
                shown = json.dumps(json.loads(verdict_file.read_text(encoding="utf-8")), indent=2)
                self.assertEqual(
                    rest,
                    shown + "\n" + self.changes_header + "\n--- specs/SPEC-001-x.md as the human left it ---\n"
                    + self.doc.read_text(encoding="utf-8"),
                )

    def test_valid_verdict_accepts_absent_or_list_fields_and_rejects_non_lists(self):
        """Adversarial where: `valid_verdict` rejects the old shape, accepts a
        non-list `comments`/`edited`, or checks only one of the two (one good
        field must not excuse the bad one)."""
        request = {"id": "r1"}
        base = {"id": "r1", "verdict": "changes"}
        good_comment = [{"file": "a.md", "note": "n"}]
        for name, extra, ok in [
            ("neither field", {}, True),
            ("both lists", {"comments": good_comment, "edited": ["a.md"]}, True),
            ("empty lists", {"comments": [], "edited": []}, True),
            ("comments string", {"comments": "a.md: n"}, False),
            ("comments object", {"comments": {"file": "a.md", "note": "n"}}, False),
            ("edited string", {"edited": "a.md"}, False),
            ("edited number", {"edited": 3}, False),
            ("comments good, edited bad", {"comments": good_comment, "edited": "a.md"}, False),
            ("comments bad, edited good", {"comments": "x", "edited": ["a.md"]}, False),
        ]:
            with self.subTest(name):
                self.assertIs(bool(reviewlib.valid_verdict({**base, **extra}, request)), ok)

    def test_a_malformed_comments_verdict_is_not_taken_by_the_waiter(self):
        """Adversarial where: the waiter accepts a verdict whose `comments` is
        not a list and then fails or prints garbage instead of waiting on."""
        self.configure()
        self.answer_with({"comments": "not a list"})
        code, out, _ = self.review(str(self.doc), "--timeout", "1.5")
        self.assertEqual(code, 1)
        self.assertTrue(out.splitlines()[-1].startswith("timeout "), out)
        self.assertNotIn("as the human left it", out)


class Cancel(ReviewProject):
    def request_id(self):
        return self.review(str(self.doc), "--no-wait")[1].split()[1]

    def test_cancel_ends_a_live_waiter_with_withdrawn(self):
        """Adversarial where: a waiter keeps polling until its timeout after the
        request file is gone, or prints the document as if a verdict arrived."""
        self.configure()
        directory = reviewlib.review_dir(self.vault)
        cancelled = {}

        def cancel():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                requests = list(directory.glob("*.request.json")) if directory.is_dir() else []
                if requests:
                    time.sleep(0.3)
                    rid = requests[0].name.replace(".request.json", "")
                    cancelled["id"] = rid
                    module = importlib.import_module("commands.review")
                    cancelled["code"] = module.run(["--cancel", rid])
                    return
                time.sleep(0.05)

        threading.Thread(target=cancel, daemon=True).start()
        started = time.monotonic()
        code, out, _ = self.review(str(self.doc), "--timeout", "30")
        self.assertLess(time.monotonic() - started, 15, "the waiter must end on the withdrawal, not its timeout")
        self.assertEqual(code, 1, out)
        self.assertEqual(cancelled.get("code"), 0)
        self.assertIn(f"withdrawn {cancelled['id']}", out.splitlines())
        self.assertFalse(any(ln.startswith("timeout ") for ln in out.splitlines()), out)
        self.assertNotIn("as the human left it", out)
        self.assertEqual(list(directory.glob("*.request.json")), [])

    def test_cancel_removes_only_the_named_request_and_status_drops_it(self):
        """Adversarial where: `--cancel` clears every pending request, leaves
        the named one listed by `--status`, or fails to exit 0."""
        self.configure()
        a, b = self.request_id(), self.request_id()
        code, _, _ = self.review("--cancel", a)
        self.assertEqual(code, 0)
        directory = reviewlib.review_dir(self.vault)
        self.assertFalse((directory / f"{a}.request.json").exists())
        self.assertTrue((directory / f"{b}.request.json").exists())
        code, out, _ = self.review("--status")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), f"pending {b} specs/SPEC-001-x.md")
        self.assertEqual(self.review("--cancel", b)[0], 0)
        self.assertEqual(self.review("--status")[1].strip(), "")

    def test_cancel_of_an_unknown_id_exits_1_with_a_stderr_message_and_touches_nothing(self):
        """Adversarial where: an id that is only a prefix of a pending id, an
        id already cancelled, or a path-shaped id reaching a decoy outside
        `tmp/review/` is treated as a match, or the failure is silent."""
        self.configure()
        rid = self.request_id()
        decoy = self.vault / "specs" / "decoy.request.json"
        decoy.write_text("{}", encoding="utf-8")
        directory = reviewlib.review_dir(self.vault)
        for name, target in [
            ("never existed", "20990101T000000-abcdef"),
            ("prefix of a real id", rid[:-1]),
            ("path-shaped", "../../specs/decoy"),
            ("empty", ""),
        ]:
            with self.subTest(name):
                code, out, err = self.review("--cancel", target)
                self.assertEqual(code, 1, (out, err))
                self.assertNotEqual(err.strip(), "", "the reason goes on stderr")
                self.assertTrue((directory / f"{rid}.request.json").exists())
                self.assertTrue(decoy.exists())
        self.assertEqual(self.review("--cancel", rid)[0], 0)
        code, _, err = self.review("--cancel", rid)
        self.assertEqual(code, 1)
        self.assertNotEqual(err.strip(), "")

    def test_cancel_without_an_id_is_a_usage_error_exit_1(self):
        """Adversarial where: `--cancel` with no value raises IndexError or
        exits 2 instead of printing usage and exiting 1."""
        code, _, err = self.review("--cancel")
        self.assertEqual(code, 1)
        self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
