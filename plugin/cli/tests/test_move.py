"""Tests for `compass move` - the link-preserving domain move.

Adversarial classes: path-qualified inbound links must be rewritten while
bare stems and code-quoted mentions stay untouched; folder moves must carry
every descendant's link identity; refusals (missing dest, non-domain dest,
collisions, ambiguity, type mismatch, self-nesting) must change nothing;
dry-run must change nothing; and the healed index must not resurrect the
moved artifact's old line.
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
from commands import move  # noqa: E402


def spec_body(name, summary):
    return (
        f"---\ntitle: {name}\ntype: spec\nstatus: approved\narea: w\ntags: [x]\n"
        f'summary: "{summary}"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n'
    )


def domain_body(name):
    return (
        f"---\ntitle: {name}\ntype: domain\nstatus: active\ntags: []\n"
        f'summary: "{name} things"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n'
        f"# {name}\n\n## Scope\n\nClass here: {name} things\n"
    )


class MoveFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "specs").mkdir()
        (self.root / "index.md").write_text("# Index\n\n## Specs\n", encoding="utf-8")
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def write(self, rel, body):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def run_cmd(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = move.run(args)
        return code, out.getvalue(), err.getvalue()


class FlatMoveTests(MoveFixture):
    def setUp(self):
        super().setUp()
        self.write("specs/net/index.md", domain_body("net"))
        self.write("specs/SPEC-002-cache.md", spec_body("Cache", "cache spec"))
        self.write("plans/PLAN-001-x.md", (
            "---\ntitle: P\ntype: plan\nstatus: active\narea: w\ntags: [x]\n"
            'summary: "p"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n'
            "Path link [[specs/SPEC-002-cache]] and stem link "
            "[[SPEC-002-cache]] and alias [[specs/SPEC-002-cache|the cache]].\n"
            "Quoted `[[specs/SPEC-002-cache]]` stays.\n"
            "```\n[[specs/SPEC-002-cache]]\n```\n"
        ))

    def test_apply_moves_file_and_rewrites_path_links(self):
        code, out, err = self.run_cmd(
            ["SPEC-002-cache", "specs/net", "--apply"])
        self.assertEqual(code, 0, err)
        self.assertFalse((self.root / "specs" / "SPEC-002-cache.md").exists())
        self.assertTrue(
            (self.root / "specs" / "net" / "SPEC-002-cache.md").is_file())
        plan = self.read("plans/PLAN-001-x.md")
        self.assertIn("[[specs/net/SPEC-002-cache]]", plan)
        self.assertIn("stem link [[SPEC-002-cache]]", plan)
        self.assertIn("[[specs/net/SPEC-002-cache|the cache]]", plan)
        self.assertIn("Quoted `[[specs/SPEC-002-cache]]` stays.", plan)
        self.assertIn("```\n[[specs/SPEC-002-cache]]\n```", plan)

    def test_moved_links_validate_clean(self):
        self.run_cmd(["SPEC-002-cache", "specs/net", "--apply"])
        from commands import validate as validate_cmd
        _, warnings = validate_cmd.check_vault(self.root)
        self.assertFalse(any("broken_wikilink" in w and "SPEC-002-cache" in w
                             for w in warnings))

    def test_dry_run_changes_nothing(self):
        before = self.read("plans/PLAN-001-x.md")
        code, out, _ = self.run_cmd(["SPEC-002-cache", "specs/net"])
        self.assertEqual(code, 0)
        self.assertIn("would move", out)
        self.assertTrue((self.root / "specs" / "SPEC-002-cache.md").is_file())
        self.assertEqual(self.read("plans/PLAN-001-x.md"), before)

    def test_move_back_to_type_dir_root(self):
        self.run_cmd(["SPEC-002-cache", "specs/net", "--apply"])
        code, _, err = self.run_cmd(
            ["specs/net/SPEC-002-cache.md", "specs", "--apply"])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "specs" / "SPEC-002-cache.md").is_file())
        self.assertIn("[[specs/SPEC-002-cache]]", self.read("plans/PLAN-001-x.md"))

    def test_index_does_not_resurrect_old_entry(self):
        (self.root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-002-cache]] - cache spec\n",
            encoding="utf-8")
        self.run_cmd(["SPEC-002-cache", "specs/net", "--apply"])
        index = self.read("index.md")
        self.assertNotIn("- [[SPEC-002-cache]]", index)
        self.assertIn("[[specs/net/index|net]]", index)


class FolderMoveTests(MoveFixture):
    def setUp(self):
        super().setUp()
        self.write("specs/net/index.md", domain_body("net"))
        self.write("specs/SPEC-003-pack/index.md", spec_body("Pack", "pack spec"))
        self.write("specs/SPEC-003-pack/SPEC-001-inner.md",
                   spec_body("Inner", "inner spec"))
        self.write("research/R-001-notes.md", (
            "---\ntitle: R\ntype: research\nstatus: done\narea: w\ntags: [x]\n"
            'summary: "r"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n'
            "Folder [[specs/SPEC-003-pack]] and child "
            "[[specs/SPEC-003-pack/SPEC-001-inner]] and index "
            "[[specs/SPEC-003-pack/index|Pack]].\n"
        ))

    def test_folder_move_rewrites_descendant_links(self):
        code, _, err = self.run_cmd(["SPEC-003-pack", "specs/net", "--apply"])
        self.assertEqual(code, 0, err)
        self.assertTrue(
            (self.root / "specs" / "net" / "SPEC-003-pack" / "index.md").is_file())
        research = self.read("research/R-001-notes.md")
        self.assertIn("[[specs/net/SPEC-003-pack]]", research)
        self.assertIn("[[specs/net/SPEC-003-pack/SPEC-001-inner]]", research)
        self.assertIn("[[specs/net/SPEC-003-pack/index|Pack]]", research)


class RefusalTests(MoveFixture):
    def setUp(self):
        super().setUp()
        self.write("specs/net/index.md", domain_body("net"))
        self.write("specs/SPEC-002-cache.md", spec_body("Cache", "cache spec"))

    def test_missing_dest_refuses(self):
        code, _, err = self.run_cmd(["SPEC-002-cache", "specs/nowhere", "--apply"])
        self.assertEqual(code, 1)
        self.assertTrue((self.root / "specs" / "SPEC-002-cache.md").is_file())

    def test_grouping_subfolder_without_index_refuses(self):
        (self.root / "specs" / "loose").mkdir()
        code, _, err = self.run_cmd(["SPEC-002-cache", "specs/loose", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("index.md", err)

    def test_collision_at_dest_refuses(self):
        self.write("specs/net/SPEC-002-cache.md", spec_body("Other", "other"))
        code, _, err = self.run_cmd(
            ["specs/SPEC-002-cache.md", "specs/net", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("exists", err)
        self.assertTrue((self.root / "specs" / "SPEC-002-cache.md").is_file())

    def test_cross_type_dir_refuses(self):
        self.write("research/topic/index.md", domain_body("topic"))
        code, _, err = self.run_cmd(["SPEC-002-cache", "research/topic", "--apply"])
        self.assertEqual(code, 1)

    def test_folder_into_its_own_subtree_refuses(self):
        self.write("specs/SPEC-003-pack/index.md", spec_body("Pack", "pack"))
        self.write("specs/SPEC-003-pack/sub/index.md", domain_body("sub"))
        code, _, err = self.run_cmd(
            ["SPEC-003-pack", "specs/SPEC-003-pack/sub", "--apply"])
        self.assertEqual(code, 1)

    def test_ambiguous_artifact_refuses(self):
        self.write("unita/index.md", "---\ntitle: A\ntype: unit\n---\n")
        self.write("unita/specs/SPEC-002-cache.md", spec_body("Cache", "c"))
        code, _, err = self.run_cmd(["SPEC-002-cache", "specs/net", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", err)

    def test_already_in_dest_refuses(self):
        code, _, err = self.run_cmd(["SPEC-002-cache", "specs", "--apply"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
