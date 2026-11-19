"""Adversarial tests for `idea` as an artifact type, aimed at the commands
that enumerate type dirs and map a type dir to a `type` value.

Adversarial themes: every place that derives an artifact's `type` from its
directory name must say `idea` for `ideas/`; commands that walk type dirs
(sync, tree, validate, scan) must see ideas nested in category folders and in
unit folders, and must not let a category folder's own `index.md` pose as an
idea.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402
from commands import fix_frontmatter, make_unit, next_num, sync, tree, validate  # noqa: E402


def idea_doc(title="An idea"):
    return (
        f"---\ntitle: {title}\ntype: idea\nstatus: held\narea: workflow\n"
        'tags: [x]\nsummary: "one idea"\ncreated: 2026-11-19\nupdated: 2026-11-19\n---\n\nbody\n'
    )


DOMAIN_INDEX = (
    "---\ntitle: world\ntype: domain\nstatus: active\ntags: [world]\n"
    'created: 2026-11-19\nupdated: 2026-11-19\nsummary: "worlds"\n---\n\n'
    "## Scope\n\nClass here: worlds\n"
)


class IdeaEnumerationVault(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
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

    def run_cmd(self, module, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(args)
        return code, out.getvalue(), err.getvalue()


class IdeaTypeValueTests(IdeaEnumerationVault):
    def test_fix_frontmatter_stamps_the_singular_idea_type(self):
        """Adversarial where: `fix-frontmatter` derives `type` from the type
        dir through its own plural-to-singular table; if `ideas` is missing
        there it stamps `type: ideas` (the directory name) on an idea file
        whose frontmatter lacks `type` or is absent, and the file then never
        matches `type: idea`."""
        cases = {
            "frontmatter absent": "# A thought\n\nbody\n",
            "frontmatter present but type missing": (
                "---\ntitle: A thought\nstatus: held\n---\n\nbody\n"
            ),
        }
        for name, body in cases.items():
            with self.subTest(name):
                p = self.write("ideas/world-building/IDEA-001-a-thought.md", body)
                code, _, err = self.run_cmd(fix_frontmatter, ["--apply"])
                self.assertEqual(code, 0, err)
                data, error = vaultlib.parse_frontmatter(p)
                self.assertIsNone(error)
                self.assertEqual(data["type"], "idea")
                p.unlink()


class IdeaEnumerationTests(IdeaEnumerationVault):
    def test_scan_artifacts_finds_ideas_in_category_folders(self):
        """Adversarial where: `scan_artifacts` reaching only `ideas/*.md` and
        missing ideas nested in a category folder, or reporting the category
        folder's `index.md` as an idea file instead of a folder index."""
        self.write("ideas/world-building/IDEA-001-a.md", idea_doc("A"))
        self.write("ideas/world-building/IDEA-002-b.md", idea_doc("B"))
        self.write("ideas/world-building/index.md", DOMAIN_INDEX)
        self.write("ideas/characters/IDEA-003-c.md", idea_doc("C"))
        records = [r for r in vaultlib.scan_artifacts(self.root) if r["type_dir"] == "ideas"]
        by_rel = {r["path"].relative_to(self.root).as_posix(): r["kind"] for r in records}
        self.assertEqual(
            sorted(p for p, k in by_rel.items() if k != "folder-index"),
            [
                "ideas/characters/IDEA-003-c.md",
                "ideas/world-building/IDEA-001-a.md",
                "ideas/world-building/IDEA-002-b.md",
            ],
        )
        self.assertEqual(by_rel["ideas/world-building/index.md"], "folder-index")

    def test_sync_lists_ideas_under_an_ideas_section_and_validate_stays_clean(self):
        """Adversarial where: sync leaves `ideas/` out of the root index (type
        dir not discovered) or lists the category folder with the wrong child
        count, or the vault validates with an error or an
        unclassified-folder warning once ideas exist only under a category
        folder."""
        self.write("index.md", "---\ntitle: Index\ntype: index\nstatus: active\n---\n\n# Index\n")
        self.write("ideas/world-building/index.md", DOMAIN_INDEX)
        self.write("ideas/world-building/IDEA-001-sky-islands.md", idea_doc("Sky islands"))
        code, _, err = self.run_cmd(sync, [])
        self.assertEqual(code, 0, err)
        text = (self.root / "index.md").read_text(encoding="utf-8")
        self.assertIn("## Ideas", text)
        self.assertIn("[[ideas/world-building/index|world-building]] (folder, 1 children)", text)
        errors, warnings = validate.check_vault(self.root)
        self.assertEqual(errors, [])
        self.assertFalse(
            [w for w in warnings if "ideas" in w and "unclassified" in w], warnings
        )

    def test_tree_renders_an_idea_beneath_its_category_folder(self):
        """Adversarial where: `compass tree` omitting the `ideas` top level or
        rendering the idea at the wrong depth when its only parent is a
        category folder."""
        self.write("ideas/world-building/index.md", DOMAIN_INDEX)
        self.write("ideas/world-building/IDEA-001-sky-islands.md", idea_doc("Sky islands"))
        lines = tree.render(self.root).split("\n")
        self.assertIn("ideas", lines)
        self.assertIn("  world-building/ - worlds", lines)
        self.assertIn("    IDEA-001-sky-islands - one idea", lines)


class IdeaInUnitTests(IdeaEnumerationVault):
    UNIT = "---\ntitle: Story\ntype: unit\nstatus: active\n---\n\nbody\n"

    def test_unit_with_its_own_ideas_dir_numbers_locally_and_classifies(self):
        """Adversarial where: a unit's own `ideas/` classified as nothing, or
        unit-scoped `next-num idea <unit>` counting the root vault's ideas
        (numbers are local per folder)."""
        self.write("story/index.md", self.UNIT)
        (self.root / "story" / "ideas" / "world").mkdir(parents=True)
        self.write("ideas/world/IDEA-040-root.md", idea_doc("Root"))
        layout = vaultlib.classify_root_dirs(self.root / "story")
        self.assertIn("ideas", layout["type_dirs"])
        self.assertNotIn("ideas", layout["unclassified"])
        code, out, err = self.run_cmd(next_num, ["idea", "story"])
        self.assertEqual((code, out.strip()), (0, "001"), err)

    def test_make_unit_refuses_ideas_spelled_with_a_slash_or_other_case(self):
        """Adversarial where: the reserved-name check bypassed by a trailing
        slash or case variant of `ideas`, creating a unit that shadows the
        type dir (on a case-insensitive filesystem the same folder)."""
        self.write("ideas/world/IDEA-001-a.md", idea_doc("A"))
        for name in ("ideas/", "Ideas"):
            with self.subTest(name):
                code, _, _ = self.run_cmd(
                    make_unit, [name, "--reason", "grouping", "--apply"]
                )
                self.assertEqual(code, 1)
                self.assertFalse((self.root / "ideas" / "index.md").exists())


if __name__ == "__main__":
    unittest.main()
