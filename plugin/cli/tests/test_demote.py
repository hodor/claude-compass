"""Tests for TASK-079: `compass demote` (the inverse of `promote`) and
`compass make-unit --undo` (the inverse of `make-unit`).

Neither `plugin/cli/commands/demote.py` nor a `--undo` flag on `make-unit`
exists yet. `demote` is dispatched through `maincli.main` (never imported
directly), so collection never trips on a missing module - `maincli`
already reports "not implemented yet" / "unknown command" for anything it
cannot import or does not recognize, which is itself the red result these
tests pin against until the command is built. `make-unit` already exists
and is called directly, matching this module's own established
`make_unit.run(args)` convention.
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

import maincli  # noqa: E402
import vaultlib  # noqa: E402
from commands import make_unit, validate  # noqa: E402


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass").mkdir()
    return tmp / ".compass"


def write(root, rel, body="---\ntype: spec\n---\n"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def with_vault_env(test_case, vault_root):
    """Point find_vault_root at this vault for the duration of the test."""
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(vault_root.parent)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def call_run(func, args):
    """Run a `run(args)` entry point, converting a raw SystemExit (a stock
    argparse's own exit, which bypasses maincli's `except Exception` clamp
    since SystemExit is not an Exception) into the same int-or-1 shape a
    normal return gives, so a test's exit-code assertion runs instead of
    the whole process aborting."""
    try:
        return func(args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = call_run(maincli.main, argv)
    return code, out.getvalue(), err.getvalue()


def run_module(module, args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = call_run(module.run, args)
    return code, out.getvalue(), err.getvalue()


# A childless folder spec is what `promote` produces from a flat spec: same
# frontmatter plus a `children_count` line, per this task's own description
# of `demote` as promote's inverse ("git mv <name>/index.md <name>.md,
# ... dropping children_count"). FOLDER_BODY minus its `children_count`
# line equals FLAT_BODY exactly - that equality is the round-trip contract
# under test, built from the spec text rather than from reading promote's
# own implementation.
FLAT_BODY = (
    "---\n"
    "title: Tile spec\n"
    "type: spec\n"
    "status: approved\n"
    "area: x\n"
    "tags: [a]\n"
    "created: 2026-07-24\n"
    "updated: 2026-07-24\n"
    'summary: "a demoted folder spec"\n'
    "---\n\n"
    "Folder spec body.\n"
)
FOLDER_BODY = (
    "---\n"
    "title: Tile spec\n"
    "type: spec\n"
    "status: approved\n"
    "area: x\n"
    "tags: [a]\n"
    "created: 2026-07-24\n"
    "updated: 2026-07-24\n"
    "children_count: 0\n"
    'summary: "a demoted folder spec"\n'
    "---\n\n"
    "Folder spec body.\n"
)
FOLDER_BODY_WITH_CHILD = FOLDER_BODY.replace("children_count: 0", "children_count: 1")

# A second, deliberately asymmetric fixture (quoted title with an embedded
# colon, a multi-item tag list, and trailing whitespace plus multiple blank
# lines in the body) for the round-trip test: content that a
# frontmatter-through-YAML round trip would be likely to normalize away,
# unlike the plain FLAT_BODY/FOLDER_BODY pair above.
FLAT_BODY_COMPLEX = (
    "---\n"
    'title: "Tile editor: brushes"\n'
    "type: spec\n"
    "status: approved\n"
    "area: x\n"
    "tags: [a, b]\n"
    "created: 2026-07-24\n"
    "updated: 2026-07-24\n"
    'summary: "a promoted folder spec, with punctuation: and stuff"\n'
    "---\n\n"
    "Body paragraph one.\n\n"
    "Refers to [[SPEC-001-target]] and has trailing spaces.   \n\n\n"
)
FOLDER_BODY_COMPLEX = FLAT_BODY_COMPLEX.replace(
    "updated: 2026-07-24\n", "updated: 2026-07-24\nchildren_count: 0\n"
)


class DemoteTests(unittest.TestCase):
    def _clean_vault(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def test_dry_run_default_makes_no_changes(self):
        """Adversarial where: demote is documented dry-run-by-default, like
        every other shape-changing command in this CLI ("mirroring
        make_unit.py's existing contract"); an implementation that treats
        the folder-spec argument alone as sufficient to act would silently
        git-mv a real vault file on a preview invocation."""
        root = self._clean_vault()
        write(root, "specs/SPEC-002-tile/index.md", FOLDER_BODY)
        index_before = (root / "index.md").read_text(encoding="utf-8")
        files_before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        code, out, _ = run_cli(["demote", "SPEC-002-tile"])
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertTrue((root / "specs" / "SPEC-002-tile" / "index.md").is_file())
        self.assertFalse((root / "specs" / "SPEC-002-tile.md").exists())
        self.assertEqual(index_before, (root / "index.md").read_text(encoding="utf-8"))
        files_after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        self.assertEqual(files_before, files_after)

    def test_apply_restores_flat_file_and_drops_children_count(self):
        """Adversarial where: demote's contract explicitly drops
        `children_count` on restore; an implementation that git-mv's the
        index back to a flat file but forgets to strip the field would
        leave a flat spec carrying a folder-only bookkeeping key that no
        other flat spec in the vault ever has."""
        root = self._clean_vault()
        write(root, "specs/SPEC-002-tile/index.md", FOLDER_BODY)
        code, _, _ = run_cli(["demote", "SPEC-002-tile", "--apply"])
        self.assertEqual(code, 0)
        restored = root / "specs" / "SPEC-002-tile.md"
        self.assertTrue(restored.is_file())
        self.assertEqual(restored.read_text(encoding="utf-8"), FLAT_BODY)
        self.assertFalse((root / "specs" / "SPEC-002-tile").exists())
        data, error = vaultlib.parse_frontmatter(restored)
        self.assertIsNone(error)
        self.assertNotIn("children_count", data)
        errors, _ = validate.check_vault(root)
        self.assertEqual(errors, [])

    def test_inbound_wikilinks_still_resolve_after_demote(self):
        """Adversarial where: the plan promises inbound links survive the
        shape change; a demote that regenerates the root index or otherwise
        touches link resolution as a side effect could leave an existing
        `[[SPEC-002-tile]]` reference dangling even though the file it
        names still exists, just at a different path."""
        root = self._clean_vault()
        write(root, "specs/SPEC-002-tile/index.md", FOLDER_BODY)
        write(
            root, "specs/SPEC-003-ref.md",
            "---\ntitle: Ref\ntype: spec\nstatus: approved\narea: x\n"
            "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n"
            'summary: "refers to the tile spec"\n---\n\n'
            "See [[SPEC-002-tile]] for details.\n",
        )
        code, _, _ = run_cli(["demote", "SPEC-002-tile", "--apply"])
        self.assertEqual(code, 0)
        self.assertTrue((root / "specs" / "SPEC-002-tile.md").is_file())
        errors, warnings = validate.check_vault(root)
        self.assertEqual(errors, [])
        self.assertFalse(any("SPEC-002-tile" in f for f in errors + warnings))

    def test_refuses_folder_with_children_zero_changes(self):
        """Adversarial where: the children boundary sits between 0 and 1 -
        the childless case (tested above) must succeed and the one-child
        case must refuse; a fencepost error in either direction would let a
        folder with real content vanish, or would block the legitimate
        childless case."""
        root = self._clean_vault()
        write(root, "specs/SPEC-004-haskids/index.md", FOLDER_BODY_WITH_CHILD)
        write(root, "specs/SPEC-004-haskids/SPEC-001-child.md", FLAT_BODY)
        index_before = (root / "index.md").read_text(encoding="utf-8")
        code, _, err = run_cli(["demote", "SPEC-004-haskids", "--apply"])
        self.assertEqual(code, 1)
        # Pins the refusal *reason*, not just the exit code: a demote that
        # exits 1 for an unrelated cause (e.g. today's "unknown command"
        # stub, or a future usage-error branch reached before the
        # children check ever runs) would otherwise satisfy every
        # assertion below without ever having inspected the folder's
        # contents.
        self.assertIn("children", err.lower())
        self.assertFalse((root / "specs" / "SPEC-004-haskids.md").exists())
        folder_index = root / "specs" / "SPEC-004-haskids" / "index.md"
        self.assertTrue(folder_index.is_file())
        self.assertEqual(folder_index.read_text(encoding="utf-8"), FOLDER_BODY_WITH_CHILD)
        self.assertTrue(
            (root / "specs" / "SPEC-004-haskids" / "SPEC-001-child.md").is_file()
        )
        self.assertEqual(index_before, (root / "index.md").read_text(encoding="utf-8"))

    def test_never_exits_2_on_malformed_input(self):
        """Adversarial where: maincli's own exit-2 clamp covers only its
        dispatch layer's own exceptions and its custom `_Parser`; a demote
        implementation that reaches for a bare `argparse.ArgumentParser`
        and lets it call `sys.exit(2)` on a bad invocation would slip a raw
        SystemExit(2) straight through - and a command in the hook path
        must never exit 2, since that would block the user's vault
        write."""
        root = self._clean_vault()
        cases = {
            "no_args": [],
            "nonexistent_folder": ["SPEC-999-none", "--apply"],
        }
        for label, extra in cases.items():
            with self.subTest(name=label):
                code, _, _ = run_cli(["demote"] + extra)
                self.assertNotEqual(code, 2)
                self.assertEqual(code, 1)
        self.assertFalse((root / "specs").exists())

    def test_promote_then_demote_round_trip_preserves_exact_bytes(self):
        """Adversarial where: the round-trip promise is byte-for-byte, not
        merely "the fields survive" - a demote that restores the flat file
        by re-serializing frontmatter through a YAML load/dump cycle
        (rather than deleting the single `children_count` line) would
        silently reorder keys, normalize quoting, or collapse the
        fixture's trailing blank lines and embedded colon in the title,
        none of which a naive field-presence check would catch."""
        root = self._clean_vault()
        write(
            root, "specs/SPEC-001-target.md",
            "---\ntitle: T\ntype: spec\nstatus: approved\narea: x\n"
            "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n"
            'summary: "a target"\n---\n\nbody\n',
        )
        write(root, "specs/SPEC-003-complex/index.md", FOLDER_BODY_COMPLEX)
        code, _, _ = run_cli(["demote", "SPEC-003-complex", "--apply"])
        self.assertEqual(code, 0)
        restored = root / "specs" / "SPEC-003-complex.md"
        self.assertTrue(restored.is_file())
        self.assertEqual(restored.read_text(encoding="utf-8"), FLAT_BODY_COMPLEX)


class MakeUnitUndoTests(unittest.TestCase):
    SPEC = (
        "---\ntitle: Core spec\ntype: spec\nstatus: approved\narea: x\n"
        "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n---\n\nbody\n"
    )
    PLAN = (
        "---\ntitle: Impl plan\ntype: plan\nstatus: active\narea: x\n"
        "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n"
        'depends_on: ["[[SPEC-001-core]]"]\n---\n\nbody\n'
    )
    MAKE_ARGS = ["core", "specs/SPEC-001-core.md", "plans/PLAN-001-impl.md"]

    def _unit_vault(self):
        root = make_vault(self)
        (root / "meta").mkdir()
        (root / "meta" / "lessons-catalog.yaml").write_text("lessons:\n", encoding="utf-8")
        write(root, "specs/SPEC-001-core.md", self.SPEC)
        write(root, "plans/PLAN-001-impl.md", self.PLAN)
        (root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-001-core]] - Core spec\n\n"
            "## Plans\n\n- [[PLAN-001-impl]] - Impl plan\n",
            encoding="utf-8",
        )
        with_vault_env(self, root)
        code, _, err = run_module(make_unit, self.MAKE_ARGS + ["--apply"])
        self.assertEqual(code, 0, f"fixture setup failed: {err}")
        return root

    def test_undo_dry_run_makes_no_changes(self):
        """Adversarial where: --undo is documented dry-run-by-default like
        every other shape-changing command in this module; an
        implementation that treats naming the unit alone as enough to act
        would git-mv real files back on a preview invocation."""
        root = self._unit_vault()
        files_before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        code, out, _ = run_module(make_unit, ["--undo", "core"])
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertTrue((root / "core").is_dir())
        files_after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
        self.assertEqual(files_before, files_after)

    def test_undo_apply_restores_artifacts_and_removes_folder(self):
        """Adversarial where: "restores every artifact" is plural - an
        implementation that only handles the first matched type
        subdirectory (e.g. only `specs/`) and silently drops the rest would
        still pass a single-artifact-type test."""
        root = self._unit_vault()
        code, _, _ = run_module(make_unit, ["--undo", "core", "--apply"])
        self.assertEqual(code, 0)
        restored_spec = root / "specs" / "SPEC-001-core.md"
        restored_plan = root / "plans" / "PLAN-001-impl.md"
        self.assertTrue(restored_spec.is_file())
        self.assertEqual(restored_spec.read_text(encoding="utf-8"), self.SPEC)
        self.assertTrue(restored_plan.is_file())
        self.assertEqual(restored_plan.read_text(encoding="utf-8"), self.PLAN)
        self.assertFalse((root / "core").exists())
        errors, _ = validate.check_vault(root)
        self.assertEqual(errors, [])

    def test_undo_refuses_when_restored_name_would_collide_at_root(self):
        """Adversarial where: only one of the two artifacts collides at the
        root (`specs/` gained a same-named file after the unit was made;
        `plans/` did not) - a partial-restore implementation would move the
        plan back while refusing the spec, leaving the vault in a
        half-migrated state neither `--undo` nor `make-unit` ever produces
        elsewhere. The refusal must be all-or-nothing: zero changes, both
        artifacts stay inside the unit."""
        root = self._unit_vault()
        write(root, "specs/SPEC-001-core.md", "---\ntype: spec\n---\n\nstray reused name\n")
        code, _, err = run_module(make_unit, ["--undo", "core", "--apply"])
        self.assertEqual(code, 1)
        # Pins the refusal to the actual colliding artifact, not just the
        # exit code: today's args, misparsed with no `--undo` support,
        # already exit 1 for an unrelated reason ("target exists: core",
        # from re-running make-unit's own existing-target guard against
        # the positional "core") - a message assertion is what keeps this
        # red until --undo's own collision check exists and names the
        # actual colliding file.
        self.assertIn("SPEC-001-core", err)
        self.assertTrue((root / "core" / "specs" / "SPEC-001-core.md").is_file())
        self.assertEqual(
            (root / "core" / "specs" / "SPEC-001-core.md").read_text(encoding="utf-8"),
            self.SPEC,
        )
        self.assertTrue((root / "core" / "plans" / "PLAN-001-impl.md").is_file())
        self.assertEqual(
            (root / "specs" / "SPEC-001-core.md").read_text(encoding="utf-8"),
            "---\ntype: spec\n---\n\nstray reused name\n",
        )

    def test_undo_apply_on_empty_unit_removes_folder(self):
        """Adversarial where: TASK-078 lets make-unit create a unit holding
        nothing but its `index.md` marker; --undo's "restore each artifact"
        loop has nothing to iterate for that shape, and an implementation
        that only removes the folder inside that loop's body (the same
        class of bug TASK-078 fixed for the forward direction's `mkdir`)
        would leave the empty marker folder behind."""
        root = make_vault(self)
        (root / "meta").mkdir()
        (root / "meta" / "lessons-catalog.yaml").write_text("lessons:\n", encoding="utf-8")
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        setup_code, _, setup_err = run_module(make_unit, ["core", "--apply"])
        self.assertEqual(setup_code, 0, f"fixture setup failed: {setup_err}")
        self.assertTrue((root / "core").is_dir())
        code, _, _ = run_module(make_unit, ["--undo", "core", "--apply"])
        self.assertEqual(code, 0)
        self.assertFalse((root / "core").exists())

    def test_undo_never_exits_2_on_missing_or_non_unit_name(self):
        """Adversarial where: hand-rolled arg parsing for --undo (TASK-080's
        own note that a stock argparse would raise SystemExit(2) straight
        through maincli's exception clamp applies here too) must still
        refuse cleanly for a name that resolves to nothing and for a name
        that resolves to an existing root type directory rather than a
        unit - neither is the exception path maincli's outer `except
        Exception` clamps, since a raised SystemExit(2) bypasses it
        entirely."""
        root = self._unit_vault()
        cases = {"missing_unit": "nosuch", "not_a_unit": "specs"}
        for label, name in cases.items():
            with self.subTest(name=label):
                code, _, _ = run_module(make_unit, ["--undo", name, "--apply"])
                self.assertNotEqual(code, 2)
                self.assertEqual(code, 1)
        self.assertTrue((root / "core").is_dir())


if __name__ == "__main__":
    unittest.main()
