"""Tests for TASK-080: sizing decisions record themselves.

`plugin/cli/commands/sizing.py` does not exist yet, and `make_unit.run`,
`promote.run`, `demote.run` do not yet parse or require `--reason`, write
rows to `.compass/meta/sizing-log.yaml`, or stamp `sizing_id` into a
subject's own frontmatter. `sizing` itself is dispatched only through
`maincli.main(["sizing", ...])`, never imported directly (matching
`test_demote.py`'s own established technique), so collection never trips on
a missing module - `maincli` already reports "unknown command" for anything
it does not recognize, which is itself part of today's expected red result.
`make_unit`, `promote`, and `demote` already exist and are called directly,
matching each module's own established `<module>.run(args)` convention
across this test suite.

Row-schema caution: the task names the row's semantic contents ("shape, id,
reason, the volatile decisions named, ... a human or an agent") but never a
concrete field-name schema for `.compass/meta/sizing-log.yaml`. Tests below
that need to reason about row *count* or row *identity* do so by searching
the raw log text for the `sizing_id` value itself (a concrete, ADR-given
format: `sz-<date>-<n>`) rather than by parsing a guessed key layout, so a
row-schema choice the builder makes cannot itself fail an unrelated test.
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
from commands import demote, make_unit, promote, validate  # noqa: E402

SIZING_ID_RE = r"^sz-\d{4}-\d{2}-\d{2}-\d+$"

FLAT_SPEC = (
    "---\ntitle: Tile spec\ntype: spec\nstatus: approved\narea: x\n"
    "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n"
    'summary: "a promotable spec"\n---\n\nbody\n'
)

# A folder spec that already carries a sizing_id, simulating a prior
# promote decision, without depending on promote itself having run. The id
# is a concrete, non-default value (not "sz-2026-01-01-1" or any value a
# counter starting fresh would produce) so a test asserting it survived
# cannot pass by accident against a freshly-minted id that happens to
# collide with a default.
PRIOR_SIZING_ID = "sz-2026-08-01-7"
FOLDER_SPEC_WITH_ID = (
    "---\ntitle: Tile spec\ntype: spec\nstatus: approved\narea: x\n"
    "tags: [a]\ncreated: 2026-07-24\nupdated: 2026-07-24\n"
    "children_count: 0\n"
    f"sizing_id: {PRIOR_SIZING_ID}\n"
    'summary: "a folder spec pending demote"\n---\n\nbody\n'
)

BOM = b"\xef\xbb\xbf"


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    (root / "meta").mkdir(parents=True)
    return root


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
    normal return gives."""
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


def log_path(root):
    return root / "meta" / "sizing-log.yaml"


def log_text(root):
    path = log_path(root)
    if not path.is_file():
        return ""
    return vaultlib.read_vault_text(path)


def frontmatter(path):
    data, error = vaultlib.parse_frontmatter(path)
    return data, error


class MakeUnitSizingTests(unittest.TestCase):
    """`compass make-unit --apply` is one of the shape-changing triggers
    that must require `--reason` and record itself."""

    def _vault(self):
        root = make_vault(self)
        (root / "meta" / "lessons-catalog.yaml").write_text("lessons:\n", encoding="utf-8")
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def test_apply_without_reason_exits_one_zero_changes_no_row(self):
        """Adversarial where: the plan requires --reason specifically at
        --apply time, not at every invocation; an implementation that
        forgets the gate entirely would let a real shape change through
        completely unrecorded, silently defeating ADR-011 D-08's audit
        requirement on the very first call site it touches."""
        root = self._vault()
        code, _, err = run_module(make_unit, ["core", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("reason", err.lower())
        self.assertFalse((root / "core").exists())
        self.assertEqual(log_text(root), "")

    def test_dry_run_without_reason_still_succeeds(self):
        """Adversarial where: --reason is required "on --apply", never on
        every invocation; an implementation that requires it universally
        would break the fleet's existing no-reason dry-run preview calls,
        including this module's own pre-existing green test suite, since
        dry-run plans nothing permanent and has nothing to audit yet."""
        root = self._vault()
        code, out, _ = run_module(make_unit, ["core"])
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertFalse((root / "core").exists())
        self.assertEqual(log_text(root), "")

    def test_apply_with_reason_writes_exactly_one_row_and_stamps_sizing_id(self):
        """Adversarial where: "exactly one row" is the claim - an
        implementation that writes once per moved artifact, or once for
        the create event and again while stamping the id, would silently
        inflate the audit log on every single shape change from day one,
        corrupting every count `sizing stats` ever reports."""
        root = self._vault()
        code, _, _ = run_module(make_unit, ["core", "--reason", "grouping the tile work", "--apply"])
        self.assertEqual(code, 0)
        index_path = root / "core" / "index.md"
        self.assertTrue(index_path.is_file())
        data, error = frontmatter(index_path)
        self.assertIsNone(error)
        sizing_id = data.get("sizing_id")
        self.assertIsNotNone(sizing_id)
        self.assertRegex(sizing_id, SIZING_ID_RE)
        text = log_text(root)
        self.assertEqual(text.count(sizing_id), 1)
        errors, _ = validate.check_vault(root)
        self.assertEqual(errors, [])

    def test_zero_artifact_creation_also_records_a_row(self):
        """Adversarial where: TASK-078's zero-artifact unit path is a
        separate branch (`if not artifacts:`) from the artifact-moving
        path in the same function; an implementation that wires --reason
        and row-writing only into the artifact-moving branch would leave
        the empty-unit creation path - itself a real shape change -
        silently unrecorded."""
        root = self._vault()
        code, _, err = run_module(make_unit, ["core", "--apply"])
        self.assertEqual(code, 1, f"expected the reason gate to fire; got {err}")
        code, _, _ = run_module(make_unit, ["core", "--reason", "reserve the workspace", "--apply"])
        self.assertEqual(code, 0)
        data, error = frontmatter(root / "core" / "index.md")
        self.assertIsNone(error)
        sizing_id = data.get("sizing_id")
        self.assertIsNotNone(sizing_id)
        self.assertRegex(sizing_id, SIZING_ID_RE)
        self.assertEqual(log_text(root).count(sizing_id), 1)


class PromoteSizingTests(unittest.TestCase):
    """`compass promote` is grouped with `make-unit` and `demote` as one of
    the three shape-changing triggers throughout the task body and ADR-011
    D-03/D-08, and the automated-verification bullet explicitly promises
    `promote --apply` behavior parallel to `make-unit --apply`."""

    def _vault(self):
        root = make_vault(self)
        write(root, "specs/SPEC-002-tile.md", FLAT_SPEC)
        (root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-002-tile]] - Tile spec\n", encoding="utf-8"
        )
        with_vault_env(self, root)
        return root

    def test_apply_without_reason_exits_one_zero_changes_no_row(self):
        """Adversarial where: today's `promote.py` has no dry-run gate at
        all and executes unconditionally (`promote.run(["SPEC-002-tile"])`
        already promotes in the pre-existing green suite); the reason gate
        must refuse the write outright, not merely warn after the fact,
        so a missing --reason leaves the flat file untouched."""
        root = self._vault()
        code, _, err = run_module(promote, ["SPEC-002-tile", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("reason", err.lower())
        self.assertTrue((root / "specs" / "SPEC-002-tile.md").is_file())
        self.assertFalse((root / "specs" / "SPEC-002-tile").exists())
        self.assertEqual(log_text(root), "")

    def test_apply_with_reason_writes_one_row_and_stamps_sizing_id(self):
        """Adversarial where: promote's own `git mv` moves the subject to
        a new path in the same operation that must stamp its id - an
        implementation that stamps the flat file before the move, rather
        than the folder's `index.md` after it, would leave the id on a
        path that no longer exists once the move completes."""
        root = self._vault()
        code, _, _ = run_module(
            promote, ["SPEC-002-tile", "--reason", "splitting into sub-concerns", "--apply"]
        )
        self.assertEqual(code, 0)
        dest = root / "specs" / "SPEC-002-tile" / "index.md"
        self.assertTrue(dest.is_file())
        data, error = frontmatter(dest)
        self.assertIsNone(error)
        sizing_id = data.get("sizing_id")
        self.assertIsNotNone(sizing_id)
        self.assertRegex(sizing_id, SIZING_ID_RE)
        self.assertEqual(log_text(root).count(sizing_id), 1)


class DemoteCorrectionTests(unittest.TestCase):
    """`compass demote` is the inverse of `promote`, and its own row is
    documented as a correction carrying the same id as the decision it
    reverses (ADR-011 D-08: "a correction that is never observed is
    indistinguishable from a correction that was never needed")."""

    def _clean_vault(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def test_apply_without_reason_exits_one_zero_changes_no_row(self):
        root = self._clean_vault()
        write(root, "specs/SPEC-002-tile/index.md", FOLDER_SPEC_WITH_ID)
        code, _, err = run_module(demote, ["SPEC-002-tile", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("reason", err.lower())
        self.assertTrue((root / "specs" / "SPEC-002-tile" / "index.md").is_file())
        self.assertFalse((root / "specs" / "SPEC-002-tile.md").exists())
        self.assertEqual(log_text(root), "")

    def test_apply_with_reason_writes_correction_row_carrying_original_id(self):
        """Adversarial where: a naive implementation could mint a *new*
        id for the correction instead of reusing the id already recorded
        on the subject, which would sever the join key the audit trail
        depends on - the correction must reference `PRIOR_SIZING_ID`
        verbatim, not a freshly generated one."""
        root = self._clean_vault()
        write(root, "specs/SPEC-002-tile/index.md", FOLDER_SPEC_WITH_ID)
        code, _, _ = run_module(demote, ["SPEC-002-tile", "--reason", "reverting the split", "--apply"])
        self.assertEqual(code, 0)
        self.assertIn(PRIOR_SIZING_ID, log_text(root))

    def test_promote_then_demote_round_trip_yields_one_decision_and_one_correction(self):
        """Adversarial where: a round trip through two independently
        implemented commands (promote's decision row, demote's correction
        row) must land exactly two rows sharing the same id - an
        off-by-one in either command (skipping its own row, or writing an
        extra one) would surface only here, since each command's own
        isolated test above cannot see the other command's output."""
        root = self._clean_vault()
        write(root, "specs/SPEC-003-round.md", FLAT_SPEC.replace("Tile spec", "Round spec"))
        code, _, _ = run_module(
            promote, ["SPEC-003-round", "--reason", "splitting into sub-concerns", "--apply"]
        )
        self.assertEqual(code, 0)
        data, error = frontmatter(root / "specs" / "SPEC-003-round" / "index.md")
        self.assertIsNone(error)
        sizing_id = data.get("sizing_id")
        self.assertIsNotNone(sizing_id)

        code, _, _ = run_module(demote, ["SPEC-003-round", "--reason", "reverting the split", "--apply"])
        self.assertEqual(code, 0)
        self.assertTrue((root / "specs" / "SPEC-003-round.md").is_file())
        self.assertEqual(log_text(root).count(sizing_id), 2)


class SizingIdSurvivesRenameTests(unittest.TestCase):
    """The stable id's whole purpose (ADR-011 D-08, TASK-080's own second
    bullet) is to be a join key that outlives the `git mv`s these commands
    perform. Each test below isolates one rename direction."""

    def test_id_survives_demote_rename(self):
        """Adversarial where: demote rewrites the frontmatter block to
        drop `children_count` by deleting one specific line
        (`demote.py:_drop_children_count`) rather than round-tripping the
        whole block - an implementation of the *new* id-preservation
        requirement that instead re-serializes frontmatter wholesale, or
        that reads the id from the pre-move file object after the move
        already happened, could silently drop or blank the field."""
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        write(root, "specs/SPEC-002-tile/index.md", FOLDER_SPEC_WITH_ID)
        code, _, _ = run_module(demote, ["SPEC-002-tile", "--reason", "reverting the split", "--apply"])
        self.assertEqual(code, 0)
        restored = root / "specs" / "SPEC-002-tile.md"
        self.assertTrue(restored.is_file())
        data, error = frontmatter(restored)
        self.assertIsNone(error)
        self.assertEqual(data.get("sizing_id"), PRIOR_SIZING_ID)

    def test_id_survives_a_later_unrelated_shape_change(self):
        """Adversarial where: the id must survive not only the command
        that minted it but any *later, unrelated* shape change that moves
        the same file again - here promote mints the id, and a separate
        make-unit absorption performs a second, independent `git mv`. An
        implementation that regenerates the subject's frontmatter during
        the second move (rather than carrying the existing block through
        untouched) could overwrite the earlier id with a new one, or lose
        it, breaking the audit trail's join key across compound moves."""
        root = make_vault(self)
        (root / "meta" / "lessons-catalog.yaml").write_text("lessons:\n", encoding="utf-8")
        write(root, "specs/SPEC-002-tile.md", FLAT_SPEC)
        (root / "index.md").write_text(
            "# Index\n\n## Specs\n\n- [[SPEC-002-tile]] - Tile spec\n", encoding="utf-8"
        )
        with_vault_env(self, root)

        code, _, _ = run_module(
            promote, ["SPEC-002-tile", "--reason", "splitting into sub-concerns", "--apply"]
        )
        self.assertEqual(code, 0)
        data, error = frontmatter(root / "specs" / "SPEC-002-tile" / "index.md")
        self.assertIsNone(error)
        original_id = data.get("sizing_id")
        self.assertIsNotNone(original_id)

        code, _, _ = run_module(
            make_unit,
            ["core", "specs/SPEC-002-tile/index.md", "--reason", "grouping into a unit", "--apply"],
        )
        self.assertEqual(code, 0)
        moved = root / "core" / "specs" / "SPEC-002-tile" / "index.md"
        self.assertTrue(moved.is_file())
        data, error = frontmatter(moved)
        self.assertIsNone(error)
        self.assertEqual(data.get("sizing_id"), original_id)


class SizingStatsTests(unittest.TestCase):
    """`compass sizing stats` is dispatched only through `maincli.main`
    (see module docstring) so a missing `commands/sizing.py` never trips
    collection."""

    def _vault(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def test_stats_on_empty_log_reports_zero_without_raising(self):
        """Adversarial where: a fresh vault has never run a single
        shape-changing command, so `.compass/meta/sizing-log.yaml` does
        not exist at all - an implementation that assumes the file is
        always present (e.g. opens it unconditionally) would raise
        FileNotFoundError on the very first run in every new vault."""
        root = self._vault()
        code, out, err = run_cli(["sizing", "stats"])
        self.assertEqual(code, 0)
        self.assertNotIn("Traceback", out + err)
        self.assertIn("0", out)

    def test_stats_never_exits_two_on_unknown_subcommand(self):
        root = self._vault()
        code, _, _ = run_cli(["sizing", "not-a-real-subcommand"])
        self.assertNotEqual(code, 2)
        self.assertEqual(code, 1)

    def test_stats_states_zero_correction_rate_is_uninterpretable(self):
        """Adversarial where: the task explicitly promises the output
        must *not* let a zero correction rate read as good news on its
        own - an implementation that prints a bare "0 corrections (0%)"
        without qualification would technically report the number
        correctly while still producing the exact misleading impression
        the task calls out by name."""
        root = self._vault()
        code, _, _ = run_module(
            make_unit, ["core", "--reason", "reserve the workspace", "--apply"]
        )
        self.assertEqual(code, 0)
        code, out, _ = run_cli(["sizing", "stats"])
        self.assertEqual(code, 0)
        lowered = out.lower()
        self.assertTrue(
            "denominator" in lowered or "uninterpretable" in lowered,
            f"zero-correction stats output does not qualify itself: {out!r}",
        )


class SizingLogResilienceTests(unittest.TestCase):
    """The log is read-modify-write via `vaultlib.read_vault_text` /
    `write_text_lf` (LF-only, BOM-tolerant), and a malformed row must not
    take down the shape-changing commands - stated explicitly as a
    deliberate divergence from `lessonslib.load_catalog`, which raises on
    the first malformed row."""

    def _vault(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def test_corrupt_row_does_not_take_down_later_shape_commands(self):
        """Adversarial where: this is the divergence TASK-080 states by
        name - `lessonslib.load_catalog` raises `MalformedRow` on the
        first bad row and takes its caller down with it. An
        implementation that copies that nearest precedent instead of
        inverting it (the task's own stated risk) would turn one corrupt
        line anywhere in the log into an outage for every later
        make-unit/promote/demote/stats call, not just a bad read."""
        root = self._vault()
        code, _, _ = run_module(make_unit, ["a", "--reason", "first", "--apply"])
        self.assertEqual(code, 0, msg="fixture setup: first apply must succeed to seed a real row")
        data, _ = frontmatter(root / "a" / "index.md")
        id_a = data.get("sizing_id")
        self.assertIsNotNone(id_a, msg="fixture setup: the first apply must stamp a sizing_id")

        path = log_path(root)
        self.assertTrue(path.is_file(), msg="fixture setup: the first apply must have created the log")
        with open(path, "ab") as handle:
            handle.write(b"\n  - :::not-a-row:::\n")

        code, _, err = run_module(make_unit, ["b", "--reason", "second", "--apply"])
        self.assertEqual(code, 0, msg=f"a corrupt earlier row must not block a later shape change: {err}")
        data, _ = frontmatter(root / "b" / "index.md")
        id_b = data.get("sizing_id")
        self.assertIsNotNone(id_b, msg="the second apply must still stamp its own sizing_id")
        self.assertNotEqual(id_a, id_b, msg="the two decisions must mint distinct ids")

        stats_code, stats_out, stats_err = run_cli(["sizing", "stats"])
        self.assertEqual(stats_code, 0, msg=f"stats must not crash on a corrupt row: {stats_err}")
        self.assertNotIn(
            "Traceback", stats_out + stats_err, msg="stats must not raise on a corrupt row"
        )

        text = log_text(root)
        self.assertIn(id_a, text, msg="the earlier valid row must survive the corruption untouched")
        self.assertIn(
            id_b, text, msg="the later valid row must still be appended after the corruption"
        )

    def test_log_round_trips_bom_fixture_and_writes_lf_only(self):
        """Adversarial where: Windows tooling (PowerShell's `Out-File`
        among them) writes a leading BOM and CRLF line endings by default.
        A plain `open(path).read()` keeps the BOM as a literal `\\ufeff`
        character, which is not whitespace and defeats any pattern
        anchored at the start of the text - the same failure mode
        documented for frontmatter parsing in `vaultlib.read_vault_text`
        and `test_bom.py`, here applied to the read-modify-write path a
        shape command uses to append its own row."""
        root = self._vault()
        code, _, _ = run_module(make_unit, ["a", "--reason", "first", "--apply"])
        self.assertEqual(code, 0, msg="fixture setup: first apply must succeed to seed a real row")
        data, _ = frontmatter(root / "a" / "index.md")
        id_a = data.get("sizing_id")
        self.assertIsNotNone(id_a, msg="fixture setup: the first apply must stamp a sizing_id")

        path = log_path(root)
        existing = path.read_text(encoding="utf-8")
        bom_crlf = BOM + existing.replace("\n", "\r\n").encode("utf-8")
        path.write_bytes(bom_crlf)

        code, _, err = run_module(make_unit, ["b", "--reason", "second", "--apply"])
        self.assertEqual(code, 0, msg=f"a BOM'd/CRLF'd log must still round-trip: {err}")
        data, _ = frontmatter(root / "b" / "index.md")
        id_b = data.get("sizing_id")
        self.assertIsNotNone(id_b, msg="the second apply must still stamp its own sizing_id")

        raw = path.read_bytes()
        self.assertFalse(raw.startswith(BOM), msg="the written log must not carry a BOM")
        self.assertNotIn(b"\r\n", raw, msg="the written log must be LF-only")
        text = raw.decode("utf-8")
        self.assertIn(id_a, text, msg="the pre-existing row must survive the BOM/CRLF round trip")
        self.assertIn(id_b, text, msg="the newly appended row must be present after the round trip")


class NeverExitsTwoOnReasonParsingTests(unittest.TestCase):
    """`--reason` is new, hand-parsed surface (`test_checkpoint.py`'s
    pattern, per the task's own note) on three independently implemented
    modules; a stock `argparse.ArgumentParser` reaching for its own
    `.error()` would raise `SystemExit(2)` straight past `maincli.py`'s
    `except Exception` clamp, since `SystemExit` is not an `Exception` -
    the same failure class `test_demote.py`'s
    `test_never_exits_2_on_malformed_input` exists to catch, applied here
    to the argument this task newly introduces rather than to input
    already covered by that existing test."""

    def _make_unit_vault(self):
        root = make_vault(self)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def _promotable_vault(self):
        root = make_vault(self)
        write(root, "specs/SPEC-002-tile.md", FLAT_SPEC)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def _demotable_vault(self):
        root = make_vault(self)
        write(root, "specs/SPEC-002-tile/index.md", FOLDER_SPEC_WITH_ID)
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        with_vault_env(self, root)
        return root

    def test_reason_flag_with_no_value_never_exits_two(self):
        # Each case gets its own fresh vault: today's `promote.py` and
        # `demote.py` already apply unconditionally on any `--apply`-bearing
        # invocation regardless of `--reason`, so a shared vault would let
        # one case's real mutation contaminate the next case's fixture.
        cases = {
            "make_unit": lambda: run_module(make_unit, ["core", "--reason"]),
            "promote": lambda: run_module(promote, ["SPEC-002-tile", "--reason"]),
            "demote": lambda: run_module(demote, ["SPEC-002-tile", "--reason"]),
        }
        builders = {
            "make_unit": self._make_unit_vault,
            "promote": self._promotable_vault,
            "demote": self._demotable_vault,
        }
        for label, invoke in cases.items():
            with self.subTest(name=label):
                builders[label]()
                code, _, _ = invoke()
                self.assertNotEqual(code, 2)
                self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
