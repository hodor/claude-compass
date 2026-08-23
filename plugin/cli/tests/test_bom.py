"""Tests for vault frontmatter integrity: BOM tolerance on reads, and the
`summary` field every type is expected to carry.

A `utf-8` read keeps a leading BOM as `﻿`. It is not whitespace, so it
survives `.strip()` and sits in front of the first character of the file,
defeating every pattern anchored at the start of the text. Windows tooling
writes BOMs by default. Both files under test here are read every session.
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lessonslib  # noqa: E402
import vaultlib  # noqa: E402
from commands import sync as sync_cmd  # noqa: E402

BOM = b"\xef\xbb\xbf"

ARTIFACT = "---\ntitle: X\ntype: spec\nstatus: approved\narea: w\ntags: [t]\n---\n\nbody\n"

LESSON = (
    "---\ntitle: Bom\ntype: lesson\nstatus: active\ncategory: process\n"
    "area: workflow\ntags: [c]\ncreated: 2026-06-14\nupdated: 2026-06-14\n"
    'score: 5\nsummary: "summary of Bom"\n---\n\nbody\n'
)


class BomFrontmatterTests(unittest.TestCase):
    """A BOM defeats the `---` frontmatter fence, so the artifact parses as
    having no frontmatter at all and loses its type, status and tags
    everywhere: scanning, indexing, tagging, validation."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.dir = tmp

    def test_bom_artifact_still_parses_its_frontmatter(self):
        """Adversarial where: the file is byte-identical to a good artifact
        except for three leading bytes. Losing `type` here silently removes
        the artifact from every type-driven pass in the vault."""
        path = self.dir / "SPEC-001-bom.md"
        path.write_bytes(BOM + ARTIFACT.encode("utf-8"))
        data, error = vaultlib.parse_frontmatter(path)
        self.assertIsNone(error)
        self.assertEqual(data.get("type"), "spec")
        self.assertEqual(data.get("tags"), ["t"])

    def test_plain_artifact_is_unaffected(self):
        path = self.dir / "SPEC-002-plain.md"
        path.write_bytes(ARTIFACT.encode("utf-8"))
        data, error = vaultlib.parse_frontmatter(path)
        self.assertIsNone(error)
        self.assertEqual(data.get("type"), "spec")

    def test_bom_alone_is_not_read_as_content(self):
        """A BOM-only file has no frontmatter for an honest reason, and must
        report that rather than raising."""
        path = self.dir / "SPEC-003-empty.md"
        path.write_bytes(BOM)
        data, error = vaultlib.parse_frontmatter(path)
        self.assertEqual(error, "no frontmatter")
        self.assertEqual(data, {})


class BomCatalogTests(unittest.TestCase):
    """The same BOM sits before `lessons:` and defeats the start-anchored
    empty-catalog marker `sync` substitutes."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "lessons").mkdir()
        (self.root / "specs").mkdir()
        (self.root / "index.md").write_text("# Index\n\n## Lessons\n", encoding="utf-8")
        (self.root / "lessons" / "LESSON-bom.md").write_text(LESSON, encoding="utf-8")

    def catalog(self):
        return (self.root / "meta" / "lessons-catalog.yaml").read_text(encoding="utf-8-sig")

    def test_bom_catalog_does_not_become_unparseable(self):
        """Adversarial where: the empty-catalog marker carries a BOM and a
        lesson exists to append. The substitution no-ops, the rows append
        anyway, and the file becomes `lessons: []` followed by indented
        `- file:` rows. That is unparseable YAML, and it takes `compass
        lessons` and the extract-lessons dedup manifest down with it."""
        path = self.root / "meta" / "lessons-catalog.yaml"
        path.write_bytes(BOM + b"lessons: []\n")
        sync_cmd.sync(self.root)
        self.assertNotIn("lessons: []", self.catalog())
        self.assertTrue(
            lessonslib.load_catalog(self.root),
            "catalog must parse after syncing a file that carried a BOM",
        )

    def test_plain_catalog_is_unaffected(self):
        path = self.root / "meta" / "lessons-catalog.yaml"
        path.write_bytes(b"lessons: []\n")
        sync_cmd.sync(self.root)
        self.assertNotIn("lessons: []", self.catalog())
        self.assertTrue(lessonslib.load_catalog(self.root))


class SummaryExpectedOnEveryTypeTests(unittest.TestCase):
    """The root index renders `summary` as an artifact's one-line description.
    A type that does not expect the field produces artifacts whose index line
    is the only copy of that description, so the index can never be shortened
    without losing it. Lessons had the field expected and were the only type at
    full coverage; every other type was at zero."""

    def test_every_known_type_expects_summary(self):
        from commands import validate
        for artifact_type, fields in validate.EXPECTED_FIELDS.items():
            with self.subTest(type=artifact_type):
                self.assertIn("summary", fields)

    def test_missing_summary_is_a_warning_not_an_error(self):
        """Adversarial where: existing vaults predate the field. Making it an
        error would fail every vault in the fleet on upgrade; making it silent
        would leave the gap invisible, which is the defect itself."""
        from commands import validate
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / ".compass"
        (root / "specs").mkdir(parents=True)
        (root / "specs" / "SPEC-001-x.md").write_text(
            "---\ntitle: X\ntype: spec\nstatus: approved\narea: w\ntags: [t]\n"
            "created: 2026-06-14\nupdated: 2026-06-14\n---\n\nbody\n",
            encoding="utf-8",
        )
        errors, warnings = validate.check_vault(root)
        joined_errors = " ".join(errors)
        joined_warnings = " ".join(warnings)
        self.assertNotIn("summary", joined_errors)
        self.assertIn("summary", joined_warnings)


if __name__ == "__main__":
    unittest.main()
