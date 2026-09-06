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


class IndexHealTests(MoveFixture):
    """move owns its root-index residue (issue #23): a moved artifact's
    hand-written description lifts into its summary: so sync's covered-line
    prune can fire, and the outcome is reported."""

    def spec_no_summary(self, name):
        return (
            f"---\ntitle: {name}\ntype: spec\nstatus: approved\narea: w\n"
            f"tags: [x]\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n"
        )

    def setUp(self):
        super().setUp()
        self.write("specs/net/index.md", domain_body("net"))

    def test_hand_description_lifted_then_line_pruned(self):
        self.write("specs/SPEC-002-cache.md", self.spec_no_summary("Cache"))
        (self.root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-002-cache]] - hand-written note\n",
            encoding="utf-8")
        code, out, err = self.run_cmd(["SPEC-002-cache", "specs/net", "--apply"])
        self.assertEqual(code, 0, err)
        data, _ = vaultlib.parse_frontmatter(
            self.root / "specs" / "net" / "SPEC-002-cache.md")
        self.assertEqual(data["summary"], "hand-written note")
        index = self.read("index.md")
        self.assertNotIn("- [[SPEC-002-cache]]", index)
        self.assertIn("pruned", out)

    def test_conflicting_description_preserved_into_body_then_pruned(self):
        """GitHub #28: a description the artifact's summary contradicts used
        to keep its root line forever - re-running sync never cleared it, so
        humans deleted the line by hand, losing the text. The line's text
        now moves into the artifact's own body and the line prunes, per
        ADR-021's rule that a folder's children are never listed at root."""
        self.write("specs/SPEC-002-cache.md", spec_body("Cache", "official summary"))
        (self.root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-002-cache]] - a different note\n",
            encoding="utf-8")
        code, out, err = self.run_cmd(["SPEC-002-cache", "specs/net", "--apply"])
        self.assertEqual(code, 0, err)
        moved = self.root / "specs" / "net" / "SPEC-002-cache.md"
        data, _ = vaultlib.parse_frontmatter(moved)
        self.assertEqual(data["summary"], "official summary")
        self.assertIn("a different note", moved.read_text(encoding="utf-8"))
        index = self.read("index.md")
        self.assertNotIn("- [[SPEC-002-cache]]", index)
        self.assertIn("preserved", out)
        self.assertNotIn("kept", out)

    def test_multi_artifact_move_clears_every_root_line(self):
        """GitHub #28's reported shape: three specs moved in one invocation,
        one line pruned, two left behind. Every root line must clear in one
        pass whatever mix of matching, missing, and divergent descriptions
        the index carries."""
        self.write("specs/SPEC-002-cache.md", spec_body("Cache", "official summary"))
        self.write("specs/SPEC-004-warm.md", spec_body("Warm", "warm summary"))
        self.write("specs/SPEC-005-cold.md", self.spec_no_summary("Cold"))
        (self.root / "index.md").write_text(
            "# Index\n\n## Specs\n\n"
            "- [[SPEC-002-cache]] - stale divergent wording\n"
            "- [[SPEC-004-warm]] - warm summary\n"
            "- [[SPEC-005-cold]] - hand-written cold note\n",
            encoding="utf-8")
        code, out, err = self.run_cmd(
            ["SPEC-002-cache", "SPEC-004-warm", "SPEC-005-cold",
             "specs/net", "--apply"])
        self.assertEqual(code, 0, err)
        index = self.read("index.md")
        for stem in ("SPEC-002-cache", "SPEC-004-warm", "SPEC-005-cold"):
            self.assertNotIn(f"- [[{stem}]]", index)
        self.assertIn(
            "stale divergent wording",
            (self.root / "specs" / "net" / "SPEC-002-cache.md").read_text(
                encoding="utf-8"))
        cold, _ = vaultlib.parse_frontmatter(
            self.root / "specs" / "net" / "SPEC-005-cold.md")
        self.assertEqual(cold["summary"], "hand-written cold note")


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
