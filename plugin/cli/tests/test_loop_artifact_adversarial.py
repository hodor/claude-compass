"""Adversarial tests for `loops` as a vault artifact type.

Themes: malformed loop-folder shapes must be ignored without crashing any
vault surface; a loop inside a unit is the same flat artifact with a
path-qualified identity; wikilinks to a loop resolve in every spelling;
the graph, tree and index caps treat a loop as one artifact; and the
folder-reshaping commands (`demote`, `move`, `make-domain`) never move a
loop to a place the scanner cannot see.
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

import vaultgraph  # noqa: E402
import vaultlib  # noqa: E402
from commands import (  # noqa: E402
    demote,
    graph as graph_cmd,
    make_domain,
    move,
    next_num,
    sync as sync_cmd,
    tree,
    validate,
)

LOOP_INDEX = (
    "---\ntitle: Remove bad pattern\ntype: loop\nstatus: active\narea: workflow\n"
    "tags: [loops]\ncreated: 2026-10-18\nupdated: 2026-10-18\n"
    'summary: "drives the bad pattern count to zero"\n---\n\n# Loop\n'
)

UNIT_INDEX = "---\ntitle: Unit U\ntype: unit\nstatus: active\n---\n\n# Unit U\n"


def spec_linking(*targets):
    """A valid spec whose body wikilinks every given target."""
    links = " ".join(f"[[{t}]]" for t in targets)
    return (
        "---\ntitle: S\ntype: spec\nstatus: approved\narea: x\ntags: [a]\n"
        f'created: 2026-06-14\nupdated: 2026-06-14\nsummary: "a spec"\n---\n\n{links}\n'
    )


class Vault(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "index.md").write_text("# Index\n\n## Specs\n", encoding="utf-8")
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

    def loop_records(self):
        return [r for r in vaultlib.scan_artifacts(self.root) if r["type_dir"] == "loops"]

    def run_cmd(self, module, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(args)
        return code, out.getvalue(), err.getvalue()


class MalformedLoopShapeTests(Vault):
    def test_misshapen_entries_under_loops_are_skipped_and_never_crash(self):
        """Adversarial where: a loop folder with no `index.md`, a folder not
        named LOOP-NNN-slug (wrong case, no slug, no number), a flat
        `LOOP-NNN-x.md` file, a bare `loops/index.md`, or an `index.md` one
        level too deep being scanned as a loop (or raising), while one valid
        loop beside each of them is still found. Sync, validate and tree must
        survive every shape."""
        shapes = {
            "folder without index.md": "loops/LOOP-003-z/feedback.md",
            "lowercase prefix": "loops/loop-004-w/index.md",
            "no slug after the number": "loops/LOOP-005/index.md",
            "no number": "loops/LOOP-x-slug/index.md",
            "flat file named like a loop": "loops/LOOP-006-flat.md",
            "bare type-dir index": "loops/index.md",
            "index one level too deep": "loops/LOOP-007-deep/sub/index.md",
            "stray file named LOOP-009 without slug": "loops/LOOP-009.md",
        }
        for name, rel in shapes.items():
            with self.subTest(name):
                shutil.rmtree(self.root / "loops", ignore_errors=True)
                self.write("loops/LOOP-001-ok/index.md", LOOP_INDEX)
                self.write(rel, LOOP_INDEX)
                self.assertEqual(
                    [r["rel"] for r in self.loop_records()], ["LOOP-001-ok/index.md"]
                )
                sync_cmd.sync(self.root)
                errors, _ = validate.check_vault(self.root)
                self.assertEqual(errors, [])
                lines = tree.render(self.root).splitlines()
                self.assertEqual(
                    [ln for ln in lines if ln.startswith("  ")],
                    ["  LOOP-001-ok - drives the bad pattern count to zero"],
                )

    def test_next_num_ignores_a_numberless_stem_file_but_counts_numbered_folders(self):
        """Adversarial where: `LOOP-009.md` (no trailing slug dash) being read
        as number 9, or a numbered folder lacking `index.md` being skipped so
        its number is handed out twice."""
        self.write("loops/LOOP-002-a/index.md", LOOP_INDEX)
        self.write("loops/LOOP-009.md", LOOP_INDEX)
        self.assertEqual(self.run_cmd(next_num, ["loop"])[:2], (0, "003\n"))
        self.write("loops/LOOP-004-no-index/feedback.md", "# f\n")
        self.assertEqual(self.run_cmd(next_num, ["loop"])[:2], (0, "005\n"))


class LoopInsideUnitTests(Vault):
    def setUp(self):
        super().setUp()
        self.write("u/index.md", UNIT_INDEX)
        self.write("u/loops/LOOP-001-x/index.md", LOOP_INDEX)
        self.write("u/loops/LOOP-001-x/feedback.md", "# no frontmatter\n")
        self.write("u/loops/LOOP-001-x/golden/a.md", "# golden\n")

    def test_unit_loop_is_one_flat_path_qualified_artifact(self):
        """Adversarial where: the loop branch of the scanner forgetting the
        unit prefix (name `LOOP-001-x` instead of `u/loops/LOOP-001-x`),
        leaking the unit loop's parts, or the root index line linking a form
        that does not resolve."""
        records = self.loop_records()
        self.assertEqual(
            [(r["name"], r["unit"], r["rel"]) for r in records],
            [("u/loops/LOOP-001-x", "u", "LOOP-001-x/index.md")],
        )
        sync_cmd.sync(self.root)
        text = (self.root / "index.md").read_text(encoding="utf-8")
        self.assertIn("[[u/loops/LOOP-001-x]]", text)
        self.assertNotIn("feedback", text)
        errors, warnings = validate.check_vault(self.root)
        self.assertEqual(errors, [])
        self.assertEqual([w for w in warnings if w.startswith("broken_wikilink")], [])

    def test_unit_and_root_loop_numbering_are_independent(self):
        """Adversarial where: `next-num loop <unit>` counting root loops (or
        the reverse), so a unit-local LOOP-001 is skipped."""
        self.write("loops/LOOP-007-root/index.md", LOOP_INDEX)
        self.assertEqual(self.run_cmd(next_num, ["loop", "u"])[:2], (0, "002\n"))
        self.assertEqual(self.run_cmd(next_num, ["loop"])[:2], (0, "008\n"))
        self.assertEqual(self.run_cmd(next_num, ["loop", "u\\"])[0], 0)

    def test_unit_loop_renders_under_the_unit_without_a_folder_header(self):
        """Adversarial where: the tree's loop branch emitting a `LOOP-001-x/`
        folder header, or indenting the unit's loop at the wrong depth."""
        self.assertEqual(
            tree.render(self.root).splitlines(),
            ["u", "  LOOP-001-x - drives the bad pattern count to zero"],
        )


class LoopWikilinkTests(Vault):
    def test_every_spelling_of_a_loop_link_resolves_and_a_wrong_one_does_not(self):
        """Adversarial where: only the bare folder name resolving to the loop
        document, so the piped path form Obsidian generates, the folder path,
        an `#heading` suffix or a unique number prefix report as broken; and
        a nonexistent loop must still report broken (the control that the
        check is live)."""
        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX)
        self.write("loops/LOOP-001-x/feedback.md", "# f\n")
        good = [
            "LOOP-001-x",
            "loops/LOOP-001-x/index|Remove bad",
            "loops/LOOP-001-x/index",
            "loops/LOOP-001-x",
            "loops/LOOP-001-x/index#Step 1",
            "LOOP-001",
        ]
        self.write("specs/SPEC-001-good.md", spec_linking(*good))
        self.write("specs/SPEC-002-bad.md", spec_linking("loops/LOOP-099-nope"))
        errors, warnings = validate.check_vault(self.root)
        self.assertEqual(errors, [])
        broken = [w for w in warnings if w.startswith("broken_wikilink")]
        self.assertEqual(len(broken), 1, broken)
        self.assertIn("SPEC-002-bad", broken[0])


class LoopGraphTests(Vault):
    def test_graph_sees_inbound_links_to_the_loop_index_and_hides_loop_parts(self):
        """Adversarial where: a link to a loop landing on no node (so the
        loop reads as an orphan despite an inbound wikilink), or `feedback.md`
        and `golden/a.md` appearing as orphaned artifacts."""
        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX)
        self.write("loops/LOOP-001-x/feedback.md", "# f\n")
        self.write("loops/LOOP-001-x/golden/a.md", "# g\n")
        self.write("loops/LOOP-002-lonely/index.md", LOOP_INDEX)
        self.write("specs/SPEC-001-a.md", spec_linking("LOOP-001-x"))
        code, out, _ = self.run_cmd(graph_cmd, ["orphans"])
        self.assertEqual(code, 0)
        self.assertIn("loops/LOOP-002-lonely/index.md", out)
        self.assertNotIn("loops/LOOP-001-x/index.md", out)
        self.assertNotIn("feedback", out)
        self.assertNotIn("golden", out)
        code, out, _ = self.run_cmd(graph_cmd, ["impact", "LOOP-001-x"])
        self.assertEqual(code, 0)
        self.assertIn("specs/SPEC-001-a.md -[wikilink]-> loops/LOOP-001-x/index.md", out)
        edges = vaultgraph.build_graph(self.root)["edges"]
        self.assertIn(
            {"src": "loops/LOOP-001-x/index.md",
             "dst": "loops/LOOP-001-x/feedback.md", "kind": "containment"},
            edges,
        )


class LoopIndexAndCapTests(Vault):
    def test_sync_is_idempotent_skips_archived_and_keeps_paths_posix(self):
        """Adversarial where: a second sync duplicating loop lines, an
        archived loop being listed, or the tag index carrying a Windows
        backslash path for a loop (which no consumer could resolve)."""
        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX)
        self.write(
            "loops/LOOP-002-old/index.md",
            LOOP_INDEX.replace("status: active", "status: archived"),
        )
        sync_cmd.sync(self.root)
        first = (self.root / "index.md").read_text(encoding="utf-8")
        sync_cmd.sync(self.root)
        second = (self.root / "index.md").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertEqual(first.count("[[LOOP-001-x]]"), 1)
        self.assertNotIn("LOOP-002-old", first)
        tag_index = (self.root / "meta" / "tag-index.yaml").read_text(encoding="utf-8")
        self.assertIn("  - loops/LOOP-001-x/index.md", tag_index)
        self.assertNotIn("\\", tag_index)
        self.assertEqual(
            [r["rel"] for r in self.loop_records()],
            ["LOOP-001-x/index.md", "LOOP-002-old/index.md"],
        )

    def test_many_loops_trip_the_index_line_cap_and_loop_bodies_do_not_count(self):
        """Adversarial where: loops being invisible to the index cap (251
        loop lines never warn), or a loop's own huge parts and body inflating
        the hot-path measure, which counts only index.md, active.md and
        lessons/index.md."""
        for n in range(1, 260):
            self.write(f"loops/LOOP-{n:03d}-l/index.md", LOOP_INDEX)
        sync_cmd.sync(self.root)
        text = (self.root / "index.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(sync_cmd.INDEX_WARNING))
        _, warnings = validate.check_vault(self.root)
        self.assertTrue([w for w in warnings if w.startswith("cap_exceeded: index.md over 250 lines")])

    def test_loop_body_size_does_not_move_the_hot_path_measure(self):
        """Adversarial where: the hot-path measure walking `loops/` so one
        large loop folder (a 40,000-character ledger note and golden pattern)
        pushes the vault over the 5,000-token cap."""
        from commands import hot_path

        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX + "word " * 8000)
        self.write("loops/LOOP-001-x/golden/a.md", "pattern " * 8000)
        sync_cmd.sync(self.root)
        before = hot_path.measure(self.root)
        self.assertLess(before, hot_path.HOT_PATH_CAP)


class LoopReshapingCommandTests(Vault):
    """A loop is always a folder and only a direct child of `loops/` is
    scanned; reshaping commands must refuse the moves that would hide it."""

    def test_demote_refuses_an_index_only_loop_folder(self):
        """Adversarial where: `compass demote loops/LOOP-001-x` on a freshly
        created loop (only `index.md`, no children yet) flattening it to
        `loops/LOOP-001-x.md`, a shape the scanner skips, so the loop vanishes
        from validate, tree and the index."""
        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX)
        code, _, _ = self.run_cmd(
            demote, ["loops/LOOP-001-x", "--reason", "r", "--apply"]
        )
        self.assertEqual(
            [r["rel"] for r in self.loop_records()], ["LOOP-001-x/index.md"],
            f"demote exit {code} left the loop unscannable",
        )

    def test_make_domain_refuses_loops(self):
        """Adversarial where: `make-domain loops/grp` creating a domain under
        `loops/`, where nothing placed inside it is ever scanned."""
        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX)
        code, _, _ = self.run_cmd(
            make_domain,
            ["loops/grp", "--class-here", "x", "--reason", "r", "--apply"],
        )
        self.assertNotEqual(code, 0)
        self.assertFalse((self.root / "loops" / "grp").exists())

    def test_move_refuses_to_bury_a_loop_in_a_loops_subfolder(self):
        """Adversarial where: `compass move` carrying `loops/LOOP-001-x` into
        a `loops/<folder>/` that has an index.md, after which the scanner
        returns no loop at all (and validate still prints `clean`)."""
        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX)
        self.write("loops/LOOP-001-x/feedback.md", "# f\n")
        self.write(
            "loops/grp/index.md",
            "---\ntitle: grp\ntype: domain\nstatus: active\ntags: [d]\n"
            'created: 2026-10-18\nupdated: 2026-10-18\nsummary: "d"\n---\n\n'
            "## Scope\n\nClass here: loops\n",
        )
        code, _, _ = self.run_cmd(move, ["LOOP-001-x", "loops/grp", "--apply"])
        self.assertEqual(
            [r["rel"] for r in self.loop_records()], ["LOOP-001-x/index.md"],
            f"move exit {code} buried the loop where the scanner cannot see it",
        )

    def test_reshaping_refusals_exit_one_with_a_reason_and_change_nothing(self):
        """Adversarial where: a refusal exiting 2 or 0, printing no reason,
        or leaving a half-made folder; and the same commands still working
        on a `specs/loops` domain, so the refusal is keyed to the `loops`
        type dir and not to the word."""
        self.write("loops/LOOP-001-x/index.md", LOOP_INDEX)
        self.write(
            "loops/grp/index.md",
            "---\ntitle: grp\ntype: domain\nstatus: active\ntags: [d]\n"
            'created: 2026-10-18\nupdated: 2026-10-18\nsummary: "d"\n---\n',
        )
        cases = {
            "demote": (demote, ["loops/LOOP-001-x", "--reason", "r", "--apply"]),
            "make-domain": (
                make_domain,
                ["loops/new", "--class-here", "x", "--reason", "r", "--apply"],
            ),
            "move": (move, ["LOOP-001-x", "loops/grp", "--apply"]),
        }
        for name, (module, args) in cases.items():
            with self.subTest(name):
                code, _, err = self.run_cmd(module, args)
                self.assertEqual(code, 1)
                self.assertTrue(err.strip(), "refusal printed no reason")
        self.assertTrue((self.root / "loops" / "LOOP-001-x" / "index.md").is_file())
        self.assertFalse((self.root / "loops" / "new").exists())
        self.write("specs/SPEC-001-s.md", spec_linking())
        code, _, _ = self.run_cmd(
            make_domain,
            ["specs/loops", "--class-here", "x", "--reason", "r", "--apply"],
        )
        self.assertEqual(code, 0)


class LoopMisshapenWarningTests(Vault):
    def test_validate_warns_about_each_entry_the_scanner_cannot_see(self):
        """Adversarial where: a flat `loops/LOOP-004-w.md`, a wrongly named
        folder, a loop folder lacking `index.md`, or a unit's misshapen loop
        entry vanishing silently from validate; and a well-formed loop plus
        its parts drawing no such warning."""
        self.write("u/index.md", UNIT_INDEX)
        self.write("loops/LOOP-001-ok/index.md", LOOP_INDEX)
        self.write("loops/LOOP-001-ok/feedback.md", "# f\n")
        self.write("loops/LOOP-004-w.md", LOOP_INDEX)
        self.write("loops/loop-005-x/index.md", LOOP_INDEX)
        self.write("loops/LOOP-006-noindex/feedback.md", "# f\n")
        self.write("u/loops/LOOP-002-u.md", LOOP_INDEX)
        errors, warnings = validate.check_vault(self.root)
        self.assertEqual(errors, [])
        flagged = sorted(
            w.split(": ")[1] for w in warnings if w.startswith("loop_misshapen")
        )
        self.assertEqual(
            flagged,
            [
                "loops/LOOP-004-w.md",
                "loops/LOOP-006-noindex",
                "loops/loop-005-x",
                "u/loops/LOOP-002-u.md",
            ],
        )

    def test_dot_entries_under_loops_draw_no_warning(self):
        """Adversarial where: `loops/.gitkeep` or a dot-folder drawing
        loop_misshapen, which would nag every vault that keeps an empty
        `loops/` in git; a visible stray file beside them still warns, so
        the skip is not blanket."""
        self.write("loops/.gitkeep", "")
        self.write("loops/.hidden/notes.md", "# n\n")
        self.write("loops/stray.md", "# s\n")
        _, warnings = validate.check_vault(self.root)
        flagged = [w.split(": ")[1] for w in warnings if w.startswith("loop_misshapen")]
        self.assertEqual(flagged, ["loops/stray.md"])


if __name__ == "__main__":
    unittest.main()
