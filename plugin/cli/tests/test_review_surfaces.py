"""Tests for the review core's surface interface: a second surface registered
beside Obsidian takes a request and returns a verdict through `compass
review`, `guard`, `doctor` and `--install` with no change to the core, and
the core holds nothing specific to any one surface.

Adversarial themes: a surface that is configured only for some documents,
every surface unconfigured, a request naming an unregistered surface, a
surface that raises its focus flag, and requests from two surfaces pending
for different files at once.
"""

import importlib
import io
import json
import os
import re
import shutil
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
        env = {"COMPASS_OBSIDIAN_CONFIG": str(self.tmp / "obsidian.json"), "CLAUDE_PROJECT_DIR": str(self.tmp)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
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
