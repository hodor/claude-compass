"""Tests for the review core's surface interface: a second surface registered
beside Obsidian takes a request and returns a verdict through `compass
review`, `guard`, `doctor` and `--install` with no change to the core, and
the core holds nothing specific to any one surface.

Adversarial themes: a surface that is configured only for some documents,
every surface unconfigured, a request naming an unregistered surface, a
surface that raises its focus flag, requests from two surfaces pending
for different files at once, and a project setting that names the surface
reviews go to: spelled in every way a YAML file allows, naming a surface that
is not set up or that does not exist, read from the document's own project,
and reported by `compass doctor`.
"""

import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

CLI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLI))

import review_surfaces  # noqa: E402
import reviewlib  # noqa: E402
from review_surfaces import obsidian as obsidian_surface  # noqa: E402


def fake_surface(name, accepts, focus=False, answers=False):
    """A surface that shows any document under an `accepts` folder. With
    `answers`, delivery writes an `approved` verdict as a human would."""
    surface = SimpleNamespace(NAME=name, delivered=[], installed=[])

    def configuration(document):
        root = Path(document).resolve()
        for candidate in root.parents:
            if candidate.name == accepts:
                return {"root": candidate.parent.parent}, None
        return None, f"{name} shows only {accepts}/"

    def deliver(context, request_path):
        surface.delivered.append((context, Path(request_path)))
        if not answers:
            return
        request = json.loads(Path(request_path).read_text(encoding="utf-8"))
        reviewlib.verdict_path(request_path).write_text(json.dumps(
            {"id": request["id"], "file": request["file"], "verdict": "approved",
             "notes": f"from {name}", "at": "t"}), encoding="utf-8")

    def resolve(request, compass_vault):
        return Path(compass_vault).parent / request["file"]

    def install(compass_vault, shipped_root=None):
        surface.installed.append((Path(compass_vault), shipped_root))
        return "installed nothing"

    surface.configuration = configuration
    surface.deliver = deliver
    surface.has_focus = lambda: focus
    surface.resolve = resolve
    surface.install = install
    surface.doctor = lambda compass_vault: ("WARN", f"{name} is not running", f"start {name}")
    return surface


class SurfaceProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / ".compass"
        (self.vault / "specs").mkdir(parents=True)
        (self.vault / "plans").mkdir()
        self.spec = self.vault / "specs" / "SPEC-001-x.md"
        self.spec.write_text("# X\n", encoding="utf-8")
        self.plan = self.vault / "plans" / "PLAN-001-y.md"
        self.plan.write_text("# Y\n", encoding="utf-8")
        (self.tmp / "gitconfig").write_text("", encoding="utf-8")
        env = {
            "COMPASS_OBSIDIAN_CONFIG": str(self.tmp / "obsidian.json"),
            "CLAUDE_PROJECT_DIR": str(self.tmp),
            "GIT_CEILING_DIRECTORIES": str(self.tmp.parent),
            "GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for args in (["init", "-q"], ["config", "user.name", "Tester"],
                     ["config", "user.email", "tester@example.invalid"],
                     ["add", ".compass"], ["commit", "-q", "-m", "first"]):
            subprocess.run(["git", *args], cwd=self.tmp, check=True, capture_output=True)
        for target, value in [("open_uri", lambda uri: None), ("has_focus", lambda: False)]:
            p = mock.patch.object(obsidian_surface, target, value)
            p.start()
            self.addCleanup(p.stop)

    def register(self, *surfaces):
        p = mock.patch.object(review_surfaces, "SURFACES", list(surfaces))
        p.start()
        self.addCleanup(p.stop)

    def run_cli(self, command, *args):
        module = importlib.import_module(f"commands.{command}")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(list(args))
        return code, out.getvalue(), err.getvalue()


class SecondSurface(SurfaceProject):
    def test_a_second_surface_takes_the_review_and_its_verdict_returns(self):
        vscode = fake_surface("vscode", "specs", answers=True)
        self.register(obsidian_surface, vscode)
        code, out, _ = self.run_cli("review", str(self.spec), "--timeout", "5")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("requested "), out)
        self.assertIn('"notes": "from vscode"', out)
        self.assertIn("--- .compass/specs/SPEC-001-x.md as the human left it ---", out)
        (context, request_path), = vscode.delivered
        request = json.loads(request_path.read_text(encoding="utf-8"))
        self.assertEqual(request["surface"], "vscode")
        self.assertEqual(request["file"], ".compass/specs/SPEC-001-x.md")
        self.assertIs(request["return"], True)

    def test_the_first_configured_surface_in_order_wins(self):
        a, b = fake_surface("a", "specs"), fake_surface("b", "specs")
        self.register(a, b)
        self.run_cli("review", str(self.spec), "--no-wait")
        self.assertEqual((len(a.delivered), len(b.delivered)), (1, 0))

    def test_a_surface_that_does_not_show_the_document_is_passed_over(self):
        specs_only, plans_only = fake_surface("a", "specs"), fake_surface("b", "plans")
        self.register(specs_only, plans_only)
        self.run_cli("review", str(self.plan), "--no-wait")
        self.assertEqual((len(specs_only.delivered), len(plans_only.delivered)), (0, 1))

    def test_no_surface_configured_names_every_reason_and_sends_nothing(self):
        a, b = fake_surface("a", "nowhere"), fake_surface("b", "elsewhere")
        self.register(a, b)
        code, out, _ = self.run_cli("review", str(self.spec), "--no-wait")
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "not configured: a shows only nowhere/; b shows only elsewhere/")
        self.assertFalse(reviewlib.review_dir(self.vault).exists())

    def test_no_surface_registered_is_not_configured(self):
        self.register()
        code, out, _ = self.run_cli("review", str(self.spec), "--no-wait")
        self.assertEqual((code, out.strip()), (1, "not configured: no review surface is registered"))

    def test_a_surface_with_focus_is_asked_to_stay_in_front(self):
        vscode = fake_surface("vscode", "specs", focus=True)
        self.register(vscode)
        self.run_cli("review", str(self.spec), "--no-wait")
        request = json.loads(vscode.delivered[0][1].read_text(encoding="utf-8"))
        self.assertIs(request["return"], False)


class PendingAcrossSurfaces(SurfaceProject):
    def test_guard_protects_each_surface_document_and_names_its_surface(self):
        a, b = fake_surface("a", "specs"), fake_surface("b", "plans")
        self.register(a, b)
        self.run_cli("review", str(self.spec), "--no-wait")
        self.run_cli("review", str(self.plan), "--no-wait")
        guard = importlib.import_module("commands.guard")
        for doc, name in ((self.spec, "a"), (self.plan, "b")):
            reason = guard._review_reason({"file_path": str(doc)}, self.tmp)
            self.assertIsNotNone(reason, doc)
            self.assertIn(f"under review in {name}", reason)
        other = self.vault / "specs" / "SPEC-002-z.md"
        other.write_text("z", encoding="utf-8")
        self.assertIsNone(reviewlib.under_review(self.vault, other))

    def test_a_request_for_an_unregistered_surface_is_resolved_by_every_surface(self):
        a = fake_surface("a", "specs")
        self.register(a)
        directory = reviewlib.review_dir(self.vault)
        directory.mkdir(parents=True)
        (directory / "r1.request.json").write_text(json.dumps(
            {"id": "r1", "surface": "gone", "file": ".compass/specs/SPEC-001-x.md"}), encoding="utf-8")
        self.assertEqual(reviewlib.under_review(self.vault, self.spec)["id"], "r1")


class InstallAndDoctor(SurfaceProject):
    def test_install_runs_every_surface_with_the_shipped_root(self):
        a, b = fake_surface("a", "specs"), fake_surface("b", "plans")
        self.register(a, b)
        self.assertEqual(reviewlib.install(self.vault, "ROOT"), ["a: installed nothing", "b: installed nothing"])
        self.assertEqual(a.installed, [(self.vault, "ROOT")])
        code, out, _ = self.run_cli("review", "--install")
        self.assertEqual((code, out), (0, "a: installed nothing\nb: installed nothing\n"))

    def test_doctor_gives_one_row_per_surface(self):
        self.register(obsidian_surface, fake_surface("vscode", "specs"))
        doctor = importlib.import_module("commands.doctor")
        rows = [c.to_dict() for c in doctor._review_surface_checks(self.vault)]
        self.assertEqual([r["check"] for r in rows], ["obsidian review", "vscode review"])
        self.assertEqual(rows[1], {"check": "vscode review", "status": "WARN",
                                   "detail": "vscode is not running", "fix": "start vscode"})


def editor(name, root, set_up=True):
    """A review surface called `name` that shows every document under `root`
    when `set_up`, else none. Its doctor row never mentions its own name."""
    surface = fake_surface(name, "nowhere")
    surface.configuration = (
        (lambda document: ({"root": root}, None)) if set_up
        else (lambda document: (None, f"{name} is not set up")))
    surface.doctor = lambda compass_vault: ("OK", "ready", None)
    return surface


PLUGIN_YAML = (
    "plugin:\n"
    "  name: compass\n"
    "  version: 0.30.0\n"
    "  installed_mode: auto-update\n"
    "  notes: |\n"
    "    This vault is the Compass plugin's own development vault.\n"
)


class ReviewEditorSetting(SurfaceProject):
    def setUp(self):
        super().setUp()
        self.obsidian = editor("obsidian", self.tmp)
        self.vscode = editor("vscode", self.tmp)
        self.cursor = editor("cursor", self.tmp)

    def write_setting(self, content, vault=None):
        path = Path(vault or self.vault) / "meta" / "plugin.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))

    def sent_to(self, *surfaces):
        """The names of the surfaces `compass review` delivered to."""
        for surface in surfaces:
            surface.delivered.clear()
        self.register(*surfaces)
        code, out, _ = self.run_cli("review", str(self.spec), "--no-wait")
        self.assertEqual(code, 0, out)
        return [s.NAME for s in surfaces if s.delivered]

    def test_the_setting_picks_the_editor_among_those_set_up(self):
        """Adversarial where: `review_editor` is read by a pattern that misses
        a legal spelling of the line (quotes, a trailing comment, CRLF line
        ends, a byte-order mark, no final newline, a position before the
        `plugin:` block) or that counts a commented-out line, so reviews go
        to the first editor, or to the wrong one, with the setting in place."""
        rows = {
            "no setting picks the first set up": (PLUGIN_YAML, "obsidian"),
            "setting naming the third": (PLUGIN_YAML + "review_editor: cursor\n", "cursor"),
            "setting naming the second": (PLUGIN_YAML + "review_editor: vscode\n", "vscode"),
            "setting before the plugin block": ("review_editor: cursor\n" + PLUGIN_YAML, "cursor"),
            "double quoted value": (PLUGIN_YAML + 'review_editor: "cursor"\n', "cursor"),
            "single quoted value": (PLUGIN_YAML + "review_editor: 'cursor'\n", "cursor"),
            "trailing comment": (PLUGIN_YAML + "review_editor: cursor   # for the demo\n", "cursor"),
            "CRLF line endings": ((PLUGIN_YAML + "review_editor: cursor\n").replace("\n", "\r\n"), "cursor"),
            "byte-order mark on the first line": ("﻿review_editor: cursor\n" + PLUGIN_YAML, "cursor"),
            "no newline after the setting": (PLUGIN_YAML + "review_editor: cursor", "cursor"),
            "commented-out setting": (PLUGIN_YAML + "# review_editor: cursor\n", "obsidian"),
        }
        for name, (content, expected) in rows.items():
            with self.subTest(name):
                self.write_setting(content)
                self.assertEqual(self.sent_to(self.obsidian, self.vscode, self.cursor), [expected])

    def test_a_setting_that_cannot_be_honoured_leaves_the_usual_order(self):
        """Adversarial where: a setting naming an editor that is not set up,
        one no surface has, one set up only for other documents, or a
        plugin.yaml that cannot be read raises or sends nothing instead of
        falling back to the first editor set up."""
        cursor_off = editor("cursor", self.tmp, set_up=False)
        rows = {
            "names an editor that is not set up": (
                PLUGIN_YAML + "review_editor: cursor\n", [self.obsidian, self.vscode, cursor_off], "obsidian"),
            "names an editor no surface has": (
                PLUGIN_YAML + "review_editor: emacs\n", [self.obsidian, self.vscode, self.cursor], "obsidian"),
            "names an editor set up for other documents only": (
                PLUGIN_YAML + "review_editor: vscode\n",
                [fake_surface("vscode", "plans"), fake_surface("cursor", "specs")], "cursor"),
        }
        for name, (content, surfaces, expected) in rows.items():
            with self.subTest(name):
                self.write_setting(content)
                self.assertEqual(self.sent_to(*surfaces), [expected])
        with self.subTest("a plugin.yaml that is not text"):
            self.write_setting(b"\xff\xfe\x00review_editor: cursor\n\x80\x81")
            self.register(self.obsidian, self.vscode, self.cursor)
            surface, _, reason = reviewlib.choose(self.spec)
            self.assertIsNone(reason)
            self.assertIn(surface.NAME, ("obsidian", "cursor"))

    def test_the_setting_is_read_from_the_documents_own_project(self):
        """Adversarial where: the setting is looked up from the session's
        project (`CLAUDE_PROJECT_DIR`) instead of the vault holding the
        reviewed document, so one project's editor choice applies to another
        project's reviews; a document outside any vault raises instead of
        reaching the 'outside a .compass vault' report."""
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        (other / ".compass" / "specs").mkdir(parents=True)
        other_doc = other / ".compass" / "specs" / "SPEC-001-o.md"
        other_doc.write_text("# O\n", encoding="utf-8")
        outside = other / "loose.md"
        outside.write_text("# L\n", encoding="utf-8")
        self.register(editor("obsidian", other.parent), editor("cursor", other.parent))
        with self.subTest("the session's project names cursor, the document's project does not"):
            self.write_setting(PLUGIN_YAML + "review_editor: cursor\n")
            self.write_setting(PLUGIN_YAML, vault=other / ".compass")
            self.assertEqual(reviewlib.choose(other_doc)[0].NAME, "obsidian")
        with self.subTest("the document's project names cursor, the session's project does not"):
            self.write_setting(PLUGIN_YAML)
            self.write_setting(PLUGIN_YAML + "review_editor: cursor\n", vault=other / ".compass")
            self.assertEqual(reviewlib.choose(other_doc)[0].NAME, "cursor")
        with self.subTest("a document outside any vault"):
            self.assertEqual(reviewlib.choose(outside)[0].NAME, "obsidian")


class DoctorNamesTheReviewEditor(SurfaceProject):
    def checks_mentioning(self, name, content, off=()):
        """Doctor rows whose detail mentions `name`, with plugin.yaml as
        `content` and the editors in `off` not set up."""
        path = self.vault / "meta" / "plugin.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.register(*[editor(n, self.tmp, set_up=n not in off) for n in ("obsidian", "vscode", "cursor")])
        _, out, _ = self.run_cli("doctor", "--json")
        return [row for row in json.loads(out)["checks"] if name in row["detail"]]

    def test_doctor_names_the_editor_reviews_go_to(self):
        """Adversarial where: doctor stays silent about the editor, or names
        the first set up while a setting picked another, so the human cannot
        tell where a review will open."""
        for name, content, picked in (
            ("no setting", PLUGIN_YAML, "obsidian"),
            ("setting names the third", PLUGIN_YAML + "review_editor: cursor\n", "cursor"),
        ):
            with self.subTest(name):
                rows = self.checks_mentioning(picked, content)
                self.assertTrue([r for r in rows if r["status"] == "OK"], rows)
                self.assertEqual([r for r in rows if r["status"] != "OK"], [])

    def test_doctor_warns_once_for_an_editor_not_set_up_and_errors_for_an_unknown_one(self):
        """Adversarial where: a setting naming an editor that is not set up is
        reported as an error (or twice, or not at all), and a name no surface
        has is only a warning, so a typo in plugin.yaml goes unseen."""
        with self.subTest("named editor not set up"):
            rows = self.checks_mentioning("vscode", PLUGIN_YAML + "review_editor: vscode\n", off=("vscode",))
            self.assertEqual([r["status"] for r in rows], ["WARN"], rows)
        with self.subTest("named editor does not exist"):
            rows = self.checks_mentioning("emacs", PLUGIN_YAML + "review_editor: emacs\n")
            self.assertEqual([r["status"] for r in rows], ["FAIL"], rows)


class InstallWordingForPerUserEditors(SurfaceProject):
    def test_a_vscode_family_install_line_says_the_extension_installs_once_per_user(self):
        """Adversarial where: the install line for VS Code or Cursor reads like
        the project-level Obsidian install, so the human runs it in every
        project, or the wording leaks onto surfaces that do install per
        project."""
        self.register(*[editor(n, self.tmp) for n in ("obsidian", "vscode", "cursor")])
        lines = reviewlib.install(self.vault, "ROOT")
        self.assertEqual(lines[0], "obsidian: installed nothing")
        for line, name in zip(lines[1:], ("vscode", "cursor")):
            with self.subTest(name):
                self.assertTrue(line.startswith(f"{name}:"), line)
                self.assertRegex(line, re.compile(r"\bonce\b", re.IGNORECASE))
                self.assertRegex(line, re.compile(r"\buser\b", re.IGNORECASE))
        code, out, _ = self.run_cli("review", "--install")
        self.assertEqual((code, out.splitlines()), (0, lines))


class CoreHoldsNoSurface(unittest.TestCase):
    def test_reviewlib_names_no_surface(self):
        source = (CLI / "reviewlib.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"obsidian", source, re.IGNORECASE))

    def test_commands_reach_surfaces_only_through_the_core(self):
        surface_import = re.compile(r"^\s*(import|from)\s+review_surfaces\b", re.MULTILINE)
        self.assertRegex("    from review_surfaces import obsidian", surface_import)
        for name in ("review", "guard", "doctor", "self_update"):
            source = (CLI / "commands" / f"{name}.py").read_text(encoding="utf-8")
            self.assertNotRegex(source, surface_import, name)

    def test_every_registered_surface_has_the_whole_interface(self):
        for surface in review_surfaces.SURFACES:
            for attr in ("NAME", "configuration", "deliver", "has_focus", "resolve", "install", "doctor"):
                self.assertTrue(hasattr(surface, attr), f"{surface.NAME} lacks {attr}")


if __name__ == "__main__":
    unittest.main()
