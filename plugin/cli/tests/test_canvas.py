"""Tests for `compass canvas` - the spec tree written as `.compass/specs.canvas`.

Adversarial classes: the canvas must hold exactly one file card per spec file
(folder specs by their index.md) with an edge from each folder spec to its
direct children only; card paths are vault-relative with forward slashes; the
file must satisfy the JSON Canvas 1.0 shape Obsidian loads; a rerun must keep
every surviving card's position and size (including a card dragged to the
origin) while adding and dropping cards, without leaving duplicate cards or
edges that point at a card that left; and a card path rewritten by
`compass move` must meet the rerun as the same card.

`canvas` is dispatched through `maincli.main`, never imported directly, so
collection does not depend on the module existing.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402


def spec_body(name):
    return (
        f"---\ntitle: {name}\ntype: spec\nstatus: approved\narea: w\ntags: [x]\n"
        f'summary: "{name} spec"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n'
    )


def domain_body(name):
    return (
        f"---\ntitle: {name}\ntype: domain\nstatus: active\ntags: []\n"
        f'summary: "{name} things"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n'
        f"# {name}\n\n## Scope\n\nClass here: {name} things\n"
    )


FLAT = "specs/SPEC-001-flat.md"
PACK = "specs/SPEC-002-pack/index.md"
INNER = "specs/SPEC-002-pack/SPEC-001-inner.md"
DEEP = "specs/SPEC-002-pack/SPEC-002-deep/index.md"
LEAF = "specs/SPEC-002-pack/SPEC-002-deep/SPEC-001-leaf.md"
TREE_FILES = {FLAT, PACK, INNER, DEEP, LEAF}
TREE_EDGES = {(PACK, INNER), (PACK, DEEP), (DEEP, LEAF)}


class CanvasFixture(unittest.TestCase):
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
        self.canvas_path = self.root / "specs.canvas"

    def write_spec(self, rel):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(spec_body(p.stem), encoding="utf-8")

    def write_tree(self):
        for rel in sorted(TREE_FILES):
            self.write_spec(rel)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = maincli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def canvas(self):
        return json.loads(self.canvas_path.read_text(encoding="utf-8"))

    def cards(self):
        """file path -> (x, y, width, height) for every file card."""
        return {
            n["file"]: (n["x"], n["y"], n["width"], n["height"])
            for n in self.canvas()["nodes"]
        }

    def edges(self):
        """Set of (parent file, child file) pairs, resolved through node ids."""
        data = self.canvas()
        by_id = {n["id"]: n["file"] for n in data["nodes"]}
        return {(by_id[e["fromNode"]], by_id[e["toNode"]]) for e in data["edges"]}

    def hand_edit(self, placements):
        """Rewrite specs.canvas the way Obsidian does after a drag or resize."""
        data = self.canvas()
        for node in data["nodes"]:
            if node["file"] in placements:
                node["x"], node["y"], node["width"], node["height"] = placements[node["file"]]
        self.canvas_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")


class WriteTreeTests(CanvasFixture):
    def test_one_card_per_spec_file_and_edges_from_folder_specs_to_direct_children(self):
        """Adversarial where: a tree walk that skips folder specs' index.md,
        counts a folder as its own extra card, emits an edge from a folder
        spec to a grandchild, links siblings, reverses an edge, or writes
        Windows backslashes into card paths yields a canvas whose cards or
        edges differ from the spec tree."""
        self.write_tree()
        code, out, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        data = self.canvas()
        files = [n["file"] for n in data["nodes"]]
        self.assertEqual(sorted(files), sorted(TREE_FILES))
        self.assertFalse(any("\\" in f for f in files), files)
        self.assertEqual(self.edges(), TREE_EDGES)
        self.assertEqual(len(data["edges"]), len(TREE_EDGES))

    def test_spec_below_a_topic_folder_gets_a_card(self):
        """Adversarial where: a scan that lists only the top level of
        specs/ and folder-spec children drops specs filed under a topic
        folder, so a spec moved into a topic folder vanishes from the canvas."""
        self.write_spec("specs/net/SPEC-002-cache.md")
        (self.root / "specs" / "net" / "index.md").write_text(
            domain_body("net"), encoding="utf-8")
        self.write_spec(FLAT)
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        self.assertIn("specs/net/SPEC-002-cache.md", self.cards())
        self.assertIn(FLAT, self.cards())

    def test_file_is_json_canvas(self):
        """Adversarial where: Obsidian refuses or blanks a canvas whose nodes
        lack integer geometry, repeat an id, or whose edges name a node that
        does not exist; these shape faults are invisible to a test that only
        counts cards."""
        self.write_tree()
        self.cli("canvas")
        data = json.loads(self.canvas_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data["nodes"], list)
        self.assertIsInstance(data["edges"], list)
        ids = [n["id"] for n in data["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        for n in data["nodes"]:
            with self.subTest(card=n.get("file")):
                self.assertIsInstance(n["id"], str)
                self.assertEqual(n["type"], "file")
                for key in ("x", "y", "width", "height"):
                    self.assertIs(type(n[key]), int, key)
                self.assertGreater(n["width"], 0)
                self.assertGreater(n["height"], 0)
        edge_ids = [e["id"] for e in data["edges"]]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))
        for e in data["edges"]:
            self.assertIn(e["fromNode"], ids)
            self.assertIn(e["toNode"], ids)
            self.assertNotEqual(e["fromNode"], e["toNode"])


class RerunTests(CanvasFixture):
    def test_rerun_keeps_every_cards_position_and_size(self):
        """Adversarial where: a rerun that regenerates the layout, treats a
        zero coordinate as missing (a card dragged to the origin), or
        appends a second card for a spec it already holds discards the
        arrangement the human made in Obsidian."""
        self.write_tree()
        self.cli("canvas")
        self.hand_edit({FLAT: (-7777, 31337, 123, 45), INNER: (0, 0, 333, 77)})
        before = self.cards()
        edges_before = self.edges()
        self.assertEqual(before[FLAT], (-7777, 31337, 123, 45))
        self.assertEqual(before[INNER], (0, 0, 333, 77))
        for round_number in (1, 2):
            with self.subTest(rerun=round_number):
                code, _, err = self.cli("canvas")
                self.assertEqual(code, 0, err)
                self.assertEqual(len(self.canvas()["nodes"]), len(TREE_FILES))
                self.assertEqual(self.cards(), before)
                self.assertEqual(self.edges(), edges_before)

    def test_rerun_adds_new_specs_and_drops_departed_ones(self):
        """Adversarial where: a rerun that only appends leaves a card for a
        deleted spec (a dead link in Obsidian) and an edge to it, or that
        rebuilds from scratch loses the hand-placed position of the cards
        that stayed."""
        self.write_tree()
        self.cli("canvas")
        self.hand_edit({PACK: (-4242, 9001, 410, 190)})
        (self.root / INNER).unlink()
        shutil.rmtree(self.root / "specs" / "SPEC-002-pack" / "SPEC-002-deep")
        new_flat = "specs/SPEC-003-new.md"
        new_child = "specs/SPEC-002-pack/SPEC-003-added.md"
        self.write_spec(new_flat)
        self.write_spec(new_child)
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        cards = self.cards()
        self.assertEqual(set(cards), {FLAT, PACK, new_flat, new_child})
        self.assertEqual(cards[PACK], (-4242, 9001, 410, 190))
        self.assertEqual(self.edges(), {(PACK, new_child)})
        data = self.canvas()
        ids = {n["id"] for n in data["nodes"]}
        for e in data["edges"]:
            self.assertIn(e["fromNode"], ids)
            self.assertIn(e["toNode"], ids)

    def test_zero_specs_at_both_ends_of_the_lifecycle(self):
        """Adversarial where: an empty specs/ makes the writer crash or skip
        the file, and removing the last spec leaves its card behind because
        the 'nothing left' case short-circuits before pruning."""
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            (self.canvas()["nodes"], self.canvas()["edges"]), ([], []),
            "empty specs/ should write an empty canvas")
        self.write_spec(FLAT)
        self.cli("canvas")
        self.assertEqual(set(self.cards()), {FLAT})
        (self.root / FLAT).unlink()
        self.cli("canvas")
        self.assertEqual(
            (self.canvas()["nodes"], self.canvas()["edges"]), ([], []),
            "removing the last spec should empty the canvas")


class MoveRoundTripTests(CanvasFixture):
    def test_card_rewritten_by_move_is_the_same_card_on_rerun(self):
        """Adversarial where: after `compass move` rewrites a card's path, a
        rerun that matches cards by the old path duplicates the card at the
        default position and orphans the hand-placed one, so a move silently
        undoes the human's arrangement."""
        self.write_spec(FLAT)
        self.write_spec(PACK)
        self.write_spec(INNER)
        (self.root / "specs" / "net").mkdir()
        (self.root / "specs" / "net" / "index.md").write_text(
            domain_body("net"), encoding="utf-8")
        self.cli("canvas")
        self.hand_edit({FLAT: (-7777, 31337, 123, 45)})
        code, _, err = self.cli("move", "SPEC-001-flat", "specs/net", "--apply")
        self.assertEqual(code, 0, err)
        moved = "specs/net/SPEC-001-flat.md"
        self.assertEqual(self.cards()[moved], (-7777, 31337, 123, 45),
                         "move should keep the card's geometry")
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        files = [n["file"] for n in self.canvas()["nodes"]]
        self.assertEqual(files.count(moved), 1)
        self.assertNotIn(FLAT, files)
        self.assertEqual(self.cards()[moved], (-7777, 31337, 123, 45),
                         "rerun should keep the moved card's geometry")


class UnitAndIdentityTests(CanvasFixture):
    def make_unit(self, name):
        (self.root / name).mkdir()
        (self.root / name / "index.md").write_text(
            f"---\ntitle: {name}\ntype: unit\nstatus: active\ntags: []\n---\n",
            encoding="utf-8")

    def test_unit_specs_get_cards_and_edges_that_never_cross_into_root_specs(self):
        """Adversarial where: root and unit numbering are both local, so
        `specs/SPEC-002-pack/index.md` and `cli/specs/SPEC-002-pack/index.md`
        share every name part; a parent lookup keyed by stem or by path
        within the type dir wires a unit child to the root folder spec (or
        drops the unit's specs altogether)."""
        self.make_unit("cli")
        unit_pack = "cli/specs/SPEC-002-pack/index.md"
        unit_inner = "cli/specs/SPEC-002-pack/SPEC-001-inner.md"
        unit_flat = "cli/specs/SPEC-001-flat.md"
        self.write_tree()
        for rel in (unit_pack, unit_inner, unit_flat):
            self.write_spec(rel)
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        self.assertEqual(set(self.cards()), TREE_FILES | {unit_pack, unit_inner, unit_flat})
        self.assertEqual(self.edges(), TREE_EDGES | {(unit_pack, unit_inner)})

    def test_node_id_that_equals_a_generated_one_is_not_reused(self):
        """Adversarial where: a hand-made node already holding the id the
        hash of a new card's path would produce makes two nodes share an id,
        and Obsidian then binds every edge of one to the other."""
        import hashlib
        self.write_spec(FLAT)
        taken = hashlib.sha1(FLAT.encode("utf-8")).hexdigest()[:16]
        self.canvas_path.write_text(json.dumps({
            "nodes": [{"id": taken, "type": "text", "text": "mine",
                       "x": 9, "y": 9, "width": 50, "height": 50}],
            "edges": [],
        }), encoding="utf-8")
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        nodes = self.canvas()["nodes"]
        ids = [n["id"] for n in nodes]
        self.assertEqual(len(ids), len(set(ids)))
        text = [n for n in nodes if n["type"] == "text"]
        self.assertEqual(text[0]["id"], taken)
        self.assertEqual(text[0]["text"], "mine")

    def test_unicode_filename_is_written_unescaped_and_a_rerun_is_byte_identical(self):
        """Adversarial where: a writer that ASCII-escapes card paths
        (backslash-u00e9) differs from what Obsidian writes, and one whose
        output varies run to run (set ordering, regenerated ids) rewrites the
        file, and its sync conflict, on every invocation."""
        rel = "specs/SPEC-001-café-テスト.md"
        self.write_spec(rel)
        self.write_spec(PACK)
        self.write_spec(INNER)
        self.cli("canvas")
        first = self.canvas_path.read_bytes()
        self.assertIn(rel.encode("utf-8"), first)
        self.assertNotIn(b"\\u00e9", first)
        self.cli("canvas")
        self.assertEqual(self.canvas_path.read_bytes(), first)


class ObsidianKeysTests(CanvasFixture):
    def test_rerun_keeps_keys_the_tool_does_not_own_on_cards_and_canvas(self):
        """Adversarial where: a rerun that rebuilds each card from a fixed
        field list drops the `color`, `subpath` and any unknown key Obsidian
        stored on a card, and the canvas-level keys, so recolouring a card
        or pinning it to a heading is undone by the next `compass canvas`."""
        self.write_tree()
        self.cli("canvas")
        data = self.canvas()
        for node in data["nodes"]:
            node["color"] = "3"
            node["subpath"] = "#Problem"
            node["futureKey"] = {"k": [1, 2]}
        data["metadata"] = {"version": "1.0", "frontmatter": {}}
        self.canvas_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        after = self.canvas()
        self.assertEqual(after["metadata"], data["metadata"])
        for node in after["nodes"]:
            with self.subTest(card=node["file"]):
                self.assertEqual(node["color"], "3")
                self.assertEqual(node["subpath"], "#Problem")
                self.assertEqual(node["futureKey"], {"k": [1, 2]})

    def test_rerun_keeps_color_label_and_sides_the_human_set_on_a_tree_line(self):
        """Adversarial where: lines between spec cards are regenerated from
        the folder structure, so a line the human recoloured, labelled or
        re-anchored in Obsidian is rebuilt bare on the next run, and the
        styling is lost although the line it styles still exists."""
        self.write_tree()
        self.cli("canvas")
        data = self.canvas()
        styled = {"color": "4", "label": "owns", "fromSide": "right", "toSide": "left"}
        for edge in data["edges"]:
            edge.update(styled)
        self.canvas_path.write_text(json.dumps(data, indent="\t"), encoding="utf-8")
        self.cli("canvas")
        for edge in self.canvas()["edges"]:
            with self.subTest(edge=edge["id"]):
                for key, value in styled.items():
                    self.assertEqual(edge.get(key), value, key)

    def test_hand_drawn_line_survives_while_one_to_a_departed_card_goes(self):
        """Adversarial where: a rerun that clears every edge not prefixed
        `tree-` is fine for generated lines but erases lines the human drew;
        one that keeps all of them leaves a line to a card that left, which
        Obsidian draws to nowhere."""
        self.write_tree()
        self.write_spec("specs/SPEC-009-gone.md")
        self.cli("canvas")
        data = self.canvas()
        ids = {n["file"]: n["id"] for n in data["nodes"]}
        data["nodes"].append({"id": "note", "type": "text", "text": "n",
                              "x": 1, "y": 1, "width": 10, "height": 10})
        data["edges"] += [
            {"id": "mine-keep", "fromNode": "note", "toNode": ids[FLAT]},
            {"id": "mine-dead", "fromNode": "note", "toNode": ids["specs/SPEC-009-gone.md"]},
        ]
        self.canvas_path.write_text(json.dumps(data), encoding="utf-8")
        (self.root / "specs" / "SPEC-009-gone.md").unlink()
        self.cli("canvas")
        edge_ids = {e["id"] for e in self.canvas()["edges"]}
        self.assertIn("mine-keep", edge_ids)
        self.assertNotIn("mine-dead", edge_ids)


class CanvasEncodingTests(CanvasFixture):
    def test_bom_canvas_is_read_and_written_back_without_the_bom(self):
        """Adversarial where: PowerShell's `Out-File` and some editors save
        JSON with a UTF-8 BOM; a reader that does not strip it reports the
        canvas as invalid and never reconciles it, and a writer that keeps
        it makes Obsidian's JSON parser reject the file."""
        self.write_spec(FLAT)
        self.canvas_path.write_bytes(
            "﻿{\"nodes\": [], \"edges\": []}".encode("utf-8"))
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 0, err)
        raw = self.canvas_path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(set(self.cards()), {FLAT})

    def test_utf16_canvas_is_refused_and_left_byte_identical(self):
        """Adversarial where: a canvas saved as UTF-16 (Windows PowerShell 5
        redirection) is not decodable as UTF-8; a command that falls back to
        an empty canvas overwrites the human's arrangement instead of
        reporting the file."""
        self.write_spec(FLAT)
        original = '{"nodes": [], "edges": []}'.encode("utf-16")
        self.canvas_path.write_bytes(original)
        code, _, err = self.cli("canvas")
        self.assertEqual(code, 1)
        self.assertIn("specs.canvas", err)
        self.assertEqual(self.canvas_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
