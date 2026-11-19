"""Tests for `idea` as a numbered artifact type.

Adversarial themes: numbering must span every category folder under `ideas/`
and stay clear of other types' numbers; an `ideas/` holding no numbered
artifact yet (absent, empty, only empty category folders, only a domain index)
must classify as a type dir and never as an unclassified root folder; domain
creation must work inside it; the name `ideas` must stay reserved against
`make-unit`.
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
from commands import make_domain, make_unit, next_num, validate  # noqa: E402

IDEA_FILE = "---\ntitle: An idea\ntype: idea\nstatus: held\n---\n\nbody\n"
DOMAIN_INDEX = (
    "---\ntitle: world\ntype: domain\nstatus: active\ntags: [world]\n---\n\n"
    "## Scope\n\nClass here: worlds\n"
)


class IdeaVault(unittest.TestCase):
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

    def write(self, rel, body=IDEA_FILE):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def clear(self):
        for child in self.root.iterdir():
            if child.name != "meta":
                shutil.rmtree(child) if child.is_dir() else child.unlink()

    def run_cmd(self, module, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(args)
        return code, out.getvalue(), err.getvalue()

    def snapshot(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))


class NextNumIdeaTests(IdeaVault):
    def test_numbers_one_past_the_highest_idea_across_category_folders(self):
        """Adversarial where: `next-num idea` is refused as an unnumbered
        type, restarts at 001 per category folder, counts only the first
        category folder it walks, treats other types' numbers or non-IDEA
        files as ideas, or reads past a three-digit width."""
        cases = {
            "ideas dir absent": ([], "001"),
            "ideas dir empty": (["ideas"], "001"),
            "only an empty category folder": (["ideas/world"], "001"),
            "highest sits in the first category": (
                ["ideas/aaa/IDEA-012-a.md", "ideas/zzz/IDEA-007-b.md"], "013",
            ),
            "highest sits in the last category": (
                ["ideas/aaa/IDEA-007-a.md", "ideas/zzz/IDEA-012-b.md"], "013",
            ),
            "width boundary 099 to 100": (["ideas/aaa/IDEA-099-a.md"], "100"),
            "spec numbers are a separate number space": (
                ["ideas/aaa/IDEA-002-a.md", "specs/SPEC-050-big.md"], "003",
            ),
            "domain index beside ideas is not an idea": (
                ["ideas/aaa/index.md", "ideas/aaa/IDEA-004-a.md"], "005",
            ),
            "non-IDEA file inside a category is not counted": (
                ["ideas/aaa/SPEC-050-stray.md"], "001",
            ),
            "hidden category folder is skipped": (
                ["ideas/aaa/IDEA-003-a.md", "ideas/.hidden/IDEA-099-x.md"], "004",
            ),
        }
        for name, (files, expected) in cases.items():
            with self.subTest(name):
                self.clear()
                for rel in files:
                    if rel.endswith(".md"):
                        self.write(rel)
                    else:
                        (self.root / rel).mkdir(parents=True, exist_ok=True)
                code, out, _ = self.run_cmd(next_num, ["idea"])
                self.assertEqual((code, out.strip()), (0, expected))


class IdeaClassificationTests(IdeaVault):
    def test_ideas_dir_without_numbered_files_is_a_type_dir(self):
        """Adversarial where: an `ideas/` holding only category folders (empty,
        or with just a domain index) is classified as nothing, so validate
        warns `unclassified_root_folder` and type-dir discovery skips it; the
        control keeps a genuinely unknown folder unclassified so the fix is not
        a blanket."""
        cases = {
            "ideas dir empty": ["ideas"],
            "only an empty category folder": ["ideas/world"],
            "category holding only a domain index": ["ideas/world/index.md"],
        }
        for name, files in cases.items():
            with self.subTest(name):
                self.clear()
                for rel in files:
                    if rel.endswith(".md"):
                        self.write(rel, DOMAIN_INDEX)
                    else:
                        (self.root / rel).mkdir(parents=True, exist_ok=True)
                layout = vaultlib.classify_root_dirs(self.root)
                self.assertIn("ideas", layout["type_dirs"])
                self.assertNotIn("ideas", layout["unclassified"])
                self.assertIn("ideas", vaultlib.discover_type_dirs(self.root))
                _, warnings = validate.check_vault(self.root)
                self.assertFalse(
                    [w for w in warnings if w.startswith("unclassified_root_folder: ideas")],
                    warnings,
                )
        self.clear()
        self.write("weird_folder/stray.md", "# stray\n")
        (self.root / "ideas" / "world").mkdir(parents=True)
        self.assertIn("weird_folder", vaultlib.classify_root_dirs(self.root)["unclassified"])


class MakeDomainInIdeasTests(IdeaVault):
    def test_make_domain_creates_a_category_folder_inside_ideas(self):
        """Adversarial where: `make-domain ideas/world-building` refused
        because `ideas` is not a known type dir, either on an empty `ideas/`
        or beside another category folder, or nested under an existing
        category; the created index must carry `type: domain` and the scope
        text."""
        cases = {
            "ideas dir empty": ([], "ideas/world-building"),
            "beside an empty sibling category": (["ideas/characters"], "ideas/world-building"),
            "nested under an existing category": (
                ["ideas/world-building/index.md"], "ideas/world-building/magic",
            ),
        }
        for name, (pre, target) in cases.items():
            with self.subTest(name):
                self.clear()
                (self.root / "ideas").mkdir()
                for rel in pre:
                    if rel.endswith(".md"):
                        self.write(rel, DOMAIN_INDEX)
                    else:
                        (self.root / rel).mkdir(parents=True, exist_ok=True)
                code, _, err = self.run_cmd(
                    make_domain,
                    [target, "--class-here", "x", "--reason", "y", "--apply"],
                )
                self.assertEqual(code, 0, err)
                data, error = vaultlib.parse_frontmatter(self.root / target / "index.md")
                self.assertIsNone(error)
                self.assertEqual(data["type"], "domain")
                text = (self.root / target / "index.md").read_text(encoding="utf-8")
                self.assertIn("Class here: x", text)

    def test_domain_index_in_ideas_is_not_numbered_and_leaves_ideas_classified(self):
        """Adversarial where: the category folder's own `index.md` created by
        make-domain being counted as an idea (next-num stops returning 001) or
        the vault turning up an unclassified-folder warning for `ideas`."""
        (self.root / "ideas").mkdir()
        code, _, err = self.run_cmd(
            make_domain,
            ["ideas/world-building", "--class-here", "x", "--reason", "y", "--apply"],
        )
        self.assertEqual(code, 0, err)
        code, out, _ = self.run_cmd(next_num, ["idea"])
        self.assertEqual((code, out.strip()), (0, "001"))
        _, warnings = validate.check_vault(self.root)
        self.assertFalse(
            [w for w in warnings if w.startswith("unclassified_root_folder: ideas")],
            warnings,
        )


class MakeUnitReservesIdeasTests(IdeaVault):
    SPEC = "---\ntitle: Core\ntype: spec\nstatus: approved\n---\n\nbody\n"

    def test_make_unit_refuses_ideas_as_a_unit_name(self):
        """Adversarial where: `ideas` missing from the reserved unit names, so
        `make-unit ideas` creates a unit that shadows the type dir, whether
        `ideas/` is absent, already present, or the call carries an artifact
        to move; every refusal leaves the vault byte-for-byte untouched."""
        reason = ["--reason", "grouping the idea work"]
        cases = {
            "ideas dir absent, apply": (False, reason + ["--apply"], []),
            "ideas dir present, apply": (True, reason + ["--apply"], []),
            "with an artifact to move": (
                False, reason + ["--apply"], ["specs/SPEC-001-core.md"],
            ),
        }
        for name, (ideas_present, flags, artifacts) in cases.items():
            with self.subTest(name):
                self.clear()
                self.write("specs/SPEC-001-core.md", self.SPEC)
                if ideas_present:
                    (self.root / "ideas" / "world").mkdir(parents=True)
                before = self.snapshot()
                code, _, err = self.run_cmd(make_unit, ["ideas"] + artifacts + flags)
                self.assertEqual(code, 1)
                if not ideas_present:
                    self.assertIn("reserved name: ideas", err)
                self.assertEqual(before, self.snapshot())
                self.assertFalse((self.root / "ideas" / "index.md").exists())


if __name__ == "__main__":
    unittest.main()
