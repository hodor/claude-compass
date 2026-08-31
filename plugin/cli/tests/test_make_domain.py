"""Tests for `compass make-domain` and the taxonomy checks in validate.

Adversarial classes: creation must refuse without its scope line, sibling
collisions must refuse while cross-branch name reuse succeeds, the ceiling
must fire at 13 and stay silent at 12 and never touch exempt dirs, an empty
Scope must warn, pending hints must surface, and none of it may move the
exit code off warnings-only.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402
from commands import make_domain  # noqa: E402
from commands import validate as validate_cmd  # noqa: E402


def spec_body(name):
    return (
        f"---\ntitle: {name}\ntype: spec\nstatus: approved\narea: w\n"
        f"tags: [x]\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n"
    )


class DomainFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "specs").mkdir()
        (self.root / "research").mkdir()
        (self.root / "lessons").mkdir()
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def run_cmd(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = make_domain.run(args)
        return code, out.getvalue(), err.getvalue()

    def make(self, path, class_here="what belongs here"):
        return self.run_cmd([path, "--apply", "--reason", "test", "--class-here", class_here])

    def write(self, rel, body):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


class CreateTests(DomainFixture):
    def test_dry_run_default_creates_nothing(self):
        code, out, _ = self.run_cmd(["specs/network"])
        self.assertEqual(code, 0)
        self.assertIn("would create", out)
        self.assertFalse((self.root / "specs" / "network").exists())

    def test_apply_requires_reason_and_class_here(self):
        code, _, err = self.run_cmd(["specs/network", "--apply", "--class-here", "x"])
        self.assertEqual(code, 1)
        self.assertIn("--reason", err)
        code, _, err = self.run_cmd(["specs/network", "--apply", "--reason", "r"])
        self.assertEqual(code, 1)
        self.assertIn("--class-here", err)
        self.assertFalse((self.root / "specs" / "network").exists())

    def test_apply_creates_domain_index_with_scope_and_sizing(self):
        code, out, _ = self.make("specs/network", "routing, transport, cache design")
        self.assertEqual(code, 0)
        doc = (self.root / "specs" / "network" / "index.md").read_text(encoding="utf-8")
        self.assertIn("type: domain", doc)
        self.assertIn("status: active", doc)
        self.assertIn("sizing_id: sz-", doc)
        self.assertIn("## Scope", doc)
        self.assertIn("Class here: routing, transport, cache design", doc)
        self.assertIn("routing, transport, cache design", doc.split("---")[1])  # summary digest
        log = (self.root / "meta" / "sizing-log.yaml").read_text(encoding="utf-8")
        self.assertIn("shape: domain", log)
        self.assertIn("action: decision", log)

    def test_nested_creation_under_existing_domain(self):
        self.make("specs/network")
        code, _, _ = self.make("specs/network/cache", "hot paths and eviction")
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "specs" / "network" / "cache" / "index.md").is_file())

    def test_missing_parent_refuses(self):
        code, _, err = self.make("specs/network/cache")
        self.assertEqual(code, 1)
        self.assertIn("parent", err)

    def test_sibling_collision_refuses_but_cross_branch_reuse_creates(self):
        self.make("specs/network")
        self.make("specs/network/cache")
        code, _, err = self.make("specs/network/cache")
        self.assertEqual(code, 1)
        code, _, _ = self.make("specs/gpu-hardware")
        self.assertEqual(code, 0)
        code, _, _ = self.make("specs/gpu-hardware/cache", "gpu-side caches")
        self.assertEqual(code, 0)
        resolve = vaultlib.resolvable_names_map(self.root)
        self.assertEqual(len(resolve.get("specs/network/cache", [])), 1)
        self.assertEqual(len(resolve.get("specs/gpu-hardware/cache", [])), 1)

    def test_unknown_type_dir_refuses(self):
        code, _, err = self.make("gadgets/network")
        self.assertEqual(code, 1)

    def test_undo_removes_empty_domain_and_logs_correction(self):
        self.make("specs/network")
        code, _, _ = self.run_cmd(["--undo", "specs/network", "--apply", "--reason", "scratch"])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "specs" / "network").exists())
        log = (self.root / "meta" / "sizing-log.yaml").read_text(encoding="utf-8")
        self.assertIn("action: correction", log)

    def test_undo_refuses_when_domain_has_members(self):
        self.make("specs/network")
        self.write("specs/network/SPEC-001-a.md", spec_body("A"))
        code, _, err = self.run_cmd(["--undo", "specs/network", "--apply", "--reason", "x"])
        self.assertEqual(code, 1)
        self.assertTrue((self.root / "specs" / "network" / "SPEC-001-a.md").is_file())


class ValidateTaxonomyTests(DomainFixture):
    def _warnings(self):
        errors, warnings = validate_cmd.check_vault(self.root)
        return errors, warnings

    def test_ceiling_fires_at_13_not_12_on_type_dir(self):
        for n in range(12):
            self.write(f"specs/SPEC-{n:03}-s{n}.md", spec_body(f"S{n}"))
        _, warnings = self._warnings()
        self.assertFalse(any(w.startswith("folder_over_ceiling") for w in warnings))
        self.write("specs/SPEC-012-s12.md", spec_body("S12"))
        _, warnings = self._warnings()
        self.assertTrue(any(w.startswith("folder_over_ceiling: specs") for w in warnings))

    def test_ceiling_governs_lessons_and_decisions_too(self):
        # Lessons and decisions taxonomize like everything else (SPEC-022
        # D-12), so a flat pile of them past the ceiling is a standing
        # split suggestion, not an exemption.
        for n in range(14):
            self.write(
                f"lessons/LESSON-l{n}.md",
                f"---\ntitle: L{n}\ntype: lesson\nstatus: active\ncategory: process\n"
                f"area: w\ntags: [x]\nscore: 5\nsummary: \"s\"\n"
                f"created: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n",
            )
        _, warnings = self._warnings()
        self.assertTrue(any(w.startswith("folder_over_ceiling: lessons") for w in warnings))

    def test_ceiling_never_fires_on_exempt_dirs(self):
        for n in range(14):
            self.write(
                f"handoffs/2026-08-{n:02}_00-00-00_h{n}.md",
                f"---\ntitle: H{n}\ntype: handoff\nstatus: done\narea: w\n"
                f"tags: [x]\nsummary: \"s\"\n"
                f"created: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n",
            )
        _, warnings = self._warnings()
        self.assertFalse(any("handoffs" in w and w.startswith("folder_over_ceiling") for w in warnings))

    def test_empty_scope_warns_and_filled_scope_does_not(self):
        self.make("specs/network")
        doc = self.root / "specs" / "network" / "index.md"
        _, warnings = self._warnings()
        self.assertFalse(any(w.startswith("empty_scope") for w in warnings))
        text = doc.read_text(encoding="utf-8").replace("Class here:", "Class nowhere:")
        doc.write_text(text, encoding="utf-8")
        _, warnings = self._warnings()
        self.assertTrue(any(w.startswith("empty_scope") for w in warnings))

    def test_pending_hints_surface_with_filenames(self):
        _, warnings = self._warnings()
        self.assertFalse(any(w.startswith("taxonomy_hints") for w in warnings))
        self.write(
            "specs/SPEC-001-lost.md",
            "---\ntitle: Lost\ntype: spec\nstatus: draft\narea: w\ntags: [x]\n"
            "taxonomy_hint: \"maybe belongs with capture\"\n"
            "created: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n",
        )
        _, warnings = self._warnings()
        hint_lines = [w for w in warnings if w.startswith("taxonomy_hints")]
        self.assertEqual(len(hint_lines), 1)
        self.assertIn("1 pending", hint_lines[0])
        self.assertIn("SPEC-001-lost", hint_lines[0])

    def test_warnings_never_change_exit_code(self):
        for n in range(14):
            self.write(f"specs/SPEC-{n:03}-s{n}.md", spec_body(f"S{n}"))
        out, err = io.StringIO(), io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.project)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = validate_cmd.run([])
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()


class LinkAmbiguityTests(DomainFixture):
    """Same-named domains on different branches are the supported case;
    the proof obligations are that a bare link to the shared name warns as
    ambiguous, path-qualified links to both stay clean, and unique bare
    stems never warn."""

    def setUp(self):
        super().setUp()
        self.make("specs/network")
        self.make("specs/gpu-hardware")
        self.make("specs/network/cache", "cpu-side caching")
        self.make("specs/gpu-hardware/cache", "gpu-side caching")
        self.write("specs/SPEC-001-solo.md", spec_body("Solo"))

    def _warnings_for(self, body):
        plan = (
            "---\ntitle: P\ntype: plan\nstatus: active\narea: w\ntags: [x]\n"
            "created: 2026-08-30\nupdated: 2026-08-30\n---\n\n" + body + "\n"
        )
        self.write("plans/PLAN-001-p.md", plan)
        _, warnings = validate_cmd.check_vault(self.root)
        return warnings

    def test_bare_link_to_shared_name_warns_ambiguous(self):
        warnings = self._warnings_for("see [[cache]]")
        self.assertTrue(any(w.startswith("ambiguous_wikilink") and "[[cache]]" in w
                            for w in warnings))

    def test_path_qualified_links_to_both_stay_clean(self):
        warnings = self._warnings_for(
            "see [[specs/network/cache]] and [[specs/gpu-hardware/cache]]"
        )
        self.assertFalse(any("ambiguous_wikilink" in w or "broken_wikilink" in w
                             for w in warnings))

    def test_unique_bare_stem_stays_warning_free(self):
        warnings = self._warnings_for("see [[SPEC-001-solo]]")
        self.assertFalse(any(
            ("ambiguous_wikilink" in w or "broken_wikilink" in w) and "SPEC-001-solo" in w
            for w in warnings
        ))


if __name__ == "__main__":
    unittest.main()
