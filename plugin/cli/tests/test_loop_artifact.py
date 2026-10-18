"""Tests for `loops` as a vault artifact type.

A loop is a folder `loops/LOOP-NNN-name/` whose `index.md` is the only
artifact; `feedback.md`, `golden/*.md`, `ledger.jsonl` and the rest are loop
parts. Adversarial themes: every shape-sensitive vault surface (numbering,
scanning, validation, type-dir discovery, frontmatter repair, the root index)
must treat the folder as one flat artifact, never as a folder spec with
children and never as a pile of unrelated records.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402
from commands import fix_frontmatter, next_num, sync as sync_cmd, validate  # noqa: E402

LOOP_INDEX = (
    "---\ntitle: Remove bad pattern\ntype: loop\nstatus: active\narea: workflow\n"
    "tags: [loops]\ncreated: 2026-10-18\nupdated: 2026-10-18\n"
    'summary: "drives the bad pattern count to zero"\n---\n\n# Loop\n'
)

SPEC_OK = (
    "---\ntitle: T\ntype: spec\nstatus: approved\narea: x\ntags: [a]\n"
    'created: 2026-06-14\nupdated: 2026-06-14\nsummary: "a spec"\n---\n\nbody\n'
)

ROOT_INDEX = """# Index

## Specs

## Plans

## Research

## Decisions

## Lessons

## Handoffs
"""


class LoopVault(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "index.md").write_text(ROOT_INDEX, encoding="utf-8")
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old)
            if old else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def write(self, rel, body):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def full_loop(self, name="LOOP-001-remove-bad", index=LOOP_INDEX):
        """A loop folder carrying every kind of part the vault must ignore."""
        self.write(f"loops/{name}/index.md", index)
        self.write(f"loops/{name}/feedback.md", "# Feedback\n\nno frontmatter here\n")
        self.write(f"loops/{name}/golden/a.md", "# golden pattern\n\nbefore/after\n")
        self.write(f"loops/{name}/ledger.jsonl", '{"event": "run"}\n')
        self.write(f"loops/{name}/loop.json", "{}\n")


class LoopNumberingTests(LoopVault):
    def next_loop_number(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = next_num.run(["loop"])
        return code, out.getvalue().strip()

    def test_next_num_loop_numbers(self):
        """Adversarial where: `next-num` rejecting prefix LOOP, restarting at
        001 when LOOP-002 exists, or counting loop parts (a nested numbered
        file, a gap) instead of the top-level loop folders."""
        cases = {
            "no loops dir": ([], "001"),
            "empty loops dir": (["loops"], "001"),
            "beside LOOP-002-x": (["loops/LOOP-002-x/index.md"], "003"),
            "gap after LOOP-001 and LOOP-005": (
                ["loops/LOOP-001-a/index.md", "loops/LOOP-005-b/index.md"], "006",
            ),
            "numbered file nested inside a loop folder": (
                ["loops/LOOP-002-x/index.md", "loops/LOOP-002-x/golden/LOOP-009-p.md"],
                "003",
            ),
        }
        for name, (files, expected) in cases.items():
            with self.subTest(name):
                shutil.rmtree(self.root / "loops", ignore_errors=True)
                for rel in files:
                    if rel == "loops":
                        (self.root / "loops").mkdir()
                    else:
                        self.write(rel, LOOP_INDEX)
                code, printed = self.next_loop_number()
                self.assertEqual((code, printed), (0, expected))


class LoopScanTests(LoopVault):
    def test_scanner_yields_only_loop_index_files(self):
        """Adversarial where: a loop's `feedback.md`, `golden/a.md` or a
        stray non-LOOP folder under `loops/` leaking out of the scanner as
        records, which would drag them through validation and indexing."""
        self.full_loop()
        self.write("loops/draft-notes/index.md", "---\ntype: loop\n---\nx\n")
        rels = {
            r["rel"].replace("\\", "/")
            for r in vaultlib.scan_artifacts(self.root)
            if r["type_dir"] == "loops"
        }
        self.assertEqual(rels, {"LOOP-001-remove-bad/index.md"})

    def test_typeless_loops_dir_is_a_type_dir_not_unclassified(self):
        """Adversarial where: a `loops/` folder whose only index lacks
        `type:` falling to `unclassified` (no content signal at depth 1)
        instead of being a reserved core type dir."""
        self.write(
            "loops/LOOP-001-x/index.md",
            "---\ntitle: X\nstatus: active\n---\nbody\n",
        )
        layout = vaultlib.classify_root_dirs(self.root)
        self.assertIn("loops", layout["type_dirs"])
        self.assertNotIn("loops", layout["unclassified"])
        self.assertIn("loops", vaultlib.discover_type_dirs(self.root))
        _, warnings = validate.check_vault(self.root)
        self.assertFalse(
            [w for w in warnings if w.startswith("unclassified_root_folder")]
        )


class LoopValidateTests(LoopVault):
    def test_loop_folder_with_parts_validates_clean(self):
        """Adversarial where: validation treating `feedback.md` (no
        frontmatter), `golden/a.md` or `ledger.jsonl` as artifacts that need
        frontmatter, or flagging the loop folder `sizing_unrecorded` as if it
        were a unit or folder spec; plus a control that a real folder spec
        beside it still draws the warning, so the suppression is not blanket."""
        self.full_loop()
        self.write("specs/SPEC-002-pack/index.md", SPEC_OK)
        self.write("specs/SPEC-002-pack/SPEC-001-inner.md", SPEC_OK)
        errors, warnings = validate.check_vault(self.root)
        findings = errors + warnings
        self.assertEqual(errors, [])
        self.assertFalse([f for f in findings if "LOOP-001" in f and "sizing_unrecorded" in f])
        self.assertFalse(
            [f for f in findings if "feedback" in f or "golden" in f or "ledger" in f]
        )
        self.assertTrue(
            [w for w in warnings if w.startswith("sizing_unrecorded") and "SPEC-002-pack" in w]
        )

    def test_loop_index_missing_field_is_a_warning_naming_it(self):
        """Adversarial where: `EXPECTED_FIELDS["loop"]` absent or short one
        field, so a loop index missing summary, area, tags, created or
        updated validates silently; each field is removed alone (one bad
        field, the rest good) and must warn, never error."""
        for field in ("summary", "area", "tags", "created", "updated"):
            with self.subTest(field):
                lines = [
                    ln for ln in LOOP_INDEX.splitlines(keepends=True)
                    if not ln.startswith(f"{field}:")
                ]
                self.write("loops/LOOP-001-remove-bad/index.md", "".join(lines))
                errors, warnings = validate.check_vault(self.root)
                self.assertEqual(errors, [])
                hits = [w for w in warnings if field in w and "LOOP-001" in w]
                self.assertTrue(hits, f"no warning for missing {field}: {warnings}")

    def test_complete_loop_index_draws_no_field_warning(self):
        """Adversarial where: the field check firing on a fully populated
        loop index, which would make the missing-field warning meaningless."""
        self.write("loops/LOOP-001-remove-bad/index.md", LOOP_INDEX)
        errors, warnings = validate.check_vault(self.root)
        self.assertEqual((errors, [w for w in warnings if "LOOP-001" in w]), ([], []))


class LoopFixFrontmatterTests(LoopVault):
    def test_fix_frontmatter_touches_only_the_loop_index(self):
        """Adversarial where: `fix-frontmatter --apply` prepending
        frontmatter to `feedback.md` or `golden/a.md` (loop parts), or
        deriving the wrong type for a bare loop index."""
        self.full_loop(index="# Loop without frontmatter\n\nbody\n")
        parts = {
            rel: (self.root / rel).read_bytes()
            for rel in (
                "loops/LOOP-001-remove-bad/feedback.md",
                "loops/LOOP-001-remove-bad/golden/a.md",
                "loops/LOOP-001-remove-bad/ledger.jsonl",
            )
        }
        with redirect_stdout(io.StringIO()):
            fix_frontmatter.run(["--apply"])
        for rel, before in parts.items():
            with self.subTest(rel):
                self.assertEqual((self.root / rel).read_bytes(), before)
        data, error = vaultlib.parse_frontmatter(
            self.root / "loops/LOOP-001-remove-bad/index.md"
        )
        self.assertIsNone(error)
        self.assertEqual(data["type"], "loop")


class LoopIndexSyncTests(LoopVault):
    def test_root_index_line_for_loop_is_flat(self):
        """Adversarial where: sync counting a loop folder as a folder spec
        with children, so its root index line gains "(folder, N children)"
        (N counting feedback.md, golden/a.md...) or its frontmatter gains
        `children_count`."""
        self.full_loop()
        sync_cmd.sync(self.root)
        text = (self.root / "index.md").read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if "LOOP-001-remove-bad" in ln]
        self.assertEqual(len(lines), 1, text)
        self.assertNotIn("(folder", lines[0])
        self.assertNotIn("children", lines[0])
        data, _ = vaultlib.parse_frontmatter(
            self.root / "loops/LOOP-001-remove-bad/index.md"
        )
        self.assertNotIn("children_count", data)
        self.assertNotIn("feedback", text)
        self.assertNotIn("golden", text)


if __name__ == "__main__":
    unittest.main()
