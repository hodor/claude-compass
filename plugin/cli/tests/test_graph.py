"""Tests for `compass graph` - orphans, hubs, impact (ADR-018).

Adversarial classes: a wikilink inside a fence or inline code must create no
edge, the root index.md catalog row must not rescue an orphan, ambiguous
names must resolve to no edge, impact must stay depth-bounded and print the
edges that produced each hit, and a folder artifact's children must be
reachable through containment.
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

import vaultgraph  # noqa: E402
from commands import graph as graph_cmd  # noqa: E402


def doc(title, deps=(), body=""):
    dep_line = ""
    if deps:
        quoted = ", ".join(f'"[[{d}]]"' for d in deps)
        dep_line = f"depends_on: [{quoted}]\n"
    return (
        f"---\ntitle: {title}\ntype: spec\nstatus: approved\narea: w\n"
        f"tags: [x]\n{dep_line}created: 2026-08-29\nupdated: 2026-08-29\n---\n\n{body}\n"
    )


class GraphFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        (self.root / "specs").mkdir(parents=True)
        (self.root / "meta").mkdir()
        (self.root / "index.md").write_text(
            "# Index\n\n- [[SPEC-001-core]] - core\n- [[SPEC-002-leaf]] - leaf\n"
            "- [[SPEC-003-orphan]] - orphan\n",
            encoding="utf-8",
        )
        self.write("specs/SPEC-001-core.md", doc("Core"))
        self.write("specs/SPEC-002-leaf.md", doc("Leaf", deps=["SPEC-001-core"]))
        self.write("specs/SPEC-003-orphan.md", doc("Orphan"))

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def graph(self):
        return vaultgraph.build_graph(self.root)

    def run_cmd(self, args):
        cwd = os.getcwd()
        os.chdir(self.root.parent)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = graph_cmd.run(args)
        finally:
            os.chdir(cwd)
        return code, buf.getvalue()


class EdgeParsingTests(GraphFixture):
    def kinds_between(self, src_frag, dst_frag):
        return [
            e["kind"]
            for e in self.graph()["edges"]
            if src_frag in e["src"] and dst_frag in e["dst"]
        ]

    def test_depends_on_edge_typed(self):
        self.assertIn("depends_on", self.kinds_between("SPEC-002-leaf", "SPEC-001-core"))

    def test_body_wikilink_edge_typed(self):
        self.write("specs/SPEC-004-body.md", doc("Body", body="see [[SPEC-001-core]]"))
        self.assertIn("wikilink", self.kinds_between("SPEC-004-body", "SPEC-001-core"))

    def test_fenced_wikilink_is_not_an_edge(self):
        self.write(
            "specs/SPEC-005-fence.md",
            doc("Fence", body="```\n[[SPEC-003-orphan]]\n```\nand `[[SPEC-003-orphan]]`"),
        )
        self.assertEqual(self.kinds_between("SPEC-005-fence", "SPEC-003-orphan"), [])

    def test_prose_bare_name_is_not_an_edge(self):
        self.write("specs/SPEC-006-prose.md", doc("Prose", body="SPEC-003-orphan matters"))
        self.assertEqual(self.kinds_between("SPEC-006-prose", "SPEC-003-orphan"), [])

    def test_ambiguous_name_creates_no_edge(self):
        self.write("specs/SPEC-007-a/index.md", doc("A"))
        self.write("specs/SPEC-007-a/SPEC-001-dupe.md", doc("Dupe"))
        self.write("specs/SPEC-008-b/index.md", doc("B"))
        self.write("specs/SPEC-008-b/SPEC-001-dupe.md", doc("Dupe2"))
        self.write("specs/SPEC-009-linker.md", doc("Linker", body="[[SPEC-001-dupe]]"))
        self.assertEqual(self.kinds_between("SPEC-009-linker", "dupe"), [])

    def test_containment_edge_from_folder_index_to_child(self):
        self.write("specs/SPEC-010-folder/index.md", doc("Folder"))
        self.write("specs/SPEC-010-folder/SPEC-001-child.md", doc("Child"))
        kinds = self.kinds_between("SPEC-010-folder/index.md", "SPEC-001-child")
        self.assertIn("containment", kinds)

    def test_root_index_edges_are_typed_index(self):
        kinds = self.kinds_between("index.md", "SPEC-003-orphan")
        self.assertEqual(kinds, ["index"])


class OrphanTests(GraphFixture):
    def test_catalog_row_does_not_rescue_an_orphan(self):
        code, out = self.run_cmd(["orphans"])
        self.assertEqual(code, 0)
        self.assertIn("SPEC-003-orphan", out)

    def test_linked_artifact_is_not_an_orphan(self):
        _, out = self.run_cmd(["orphans"])
        self.assertNotIn("SPEC-001-core\n", out)

    def test_hot_path_inbound_counts_as_linked(self):
        self.write("active.md", "# Active\n\n- [ ] work on [[SPEC-003-orphan]]\n")
        _, out = self.run_cmd(["orphans"])
        self.assertNotIn("SPEC-003-orphan", out)

    def test_clean_vault_reports_none(self):
        self.write("active.md", "# Active\n\n[[SPEC-003-orphan]] [[SPEC-002-leaf]]\n")
        _, out = self.run_cmd(["orphans"])
        self.assertIn("no orphans", out)


class HubTests(GraphFixture):
    def test_ranking_orders_by_inbound_depends_on(self):
        self.write("specs/SPEC-004-d1.md", doc("D1", deps=["SPEC-001-core"]))
        self.write("specs/SPEC-005-d2.md", doc("D2", deps=["SPEC-001-core", "SPEC-002-leaf"]))
        code, out = self.run_cmd(["hubs", "--top", "2"])
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines() if "SPEC-" in l]
        self.assertIn("SPEC-001-core", lines[0])
        self.assertIn("3", lines[0])  # leaf + d1 + d2

    def test_wikilink_and_depends_on_counted_separately(self):
        self.write("specs/SPEC-004-w.md", doc("W", body="[[SPEC-001-core]]"))
        _, out = self.run_cmd(["hubs", "--top", "1"])
        top = next(l for l in out.splitlines() if "SPEC-001-core" in l)
        self.assertRegex(top, r"depends_on\s*[:=]?\s*1")
        self.assertRegex(top, r"wikilink\s*[:=]?\s*1")


class ImpactTests(GraphFixture):
    def setUp(self):
        super().setUp()
        # chain: SPEC-004 -> SPEC-002 -> SPEC-001; SPEC-005 -> SPEC-004
        self.write("specs/SPEC-004-mid.md", doc("Mid", deps=["SPEC-002-leaf"]))
        self.write("specs/SPEC-005-far.md", doc("Far", deps=["SPEC-004-mid"]))

    def test_depth_two_default_finds_two_hops_not_three(self):
        code, out = self.run_cmd(["impact", "SPEC-001-core"])
        self.assertEqual(code, 0)
        self.assertIn("SPEC-002-leaf", out)
        self.assertIn("SPEC-004-mid", out)
        self.assertNotIn("SPEC-005-far", out)

    def test_depth_flag_extends_the_bound(self):
        _, out = self.run_cmd(["impact", "SPEC-001-core", "--depth", "3"])
        self.assertIn("SPEC-005-far", out)

    def test_every_hit_names_its_edge(self):
        _, out = self.run_cmd(["impact", "SPEC-001-core"])
        self.assertIn("-[depends_on]->", out)

    def test_catalog_row_is_not_impact(self):
        _, out = self.run_cmd(["impact", "SPEC-003-orphan"])
        self.assertIn("no inbound impact", out)

    def test_unresolvable_name_exits_one(self):
        code, _ = self.run_cmd(["impact", "SPEC-999-nothing"])
        self.assertEqual(code, 1)


class OrphanExemptionAndCitationTests(GraphFixture):
    def test_lessons_and_handoffs_never_reported_as_orphans(self):
        self.write("lessons/LESSON-uncited.md",
                   "---\ntitle: L\ntype: lesson\nstatus: active\ncategory: process\n"
                   "area: w\ntags: [x]\nscore: 5\nsummary: \"s\"\n"
                   "created: 2026-08-29\nupdated: 2026-08-29\n---\n\nbody\n")
        self.write("handoffs/2026-08-29_snap.md",
                   "---\ntitle: H\ntype: handoff\nstatus: done\narea: w\ntags: [x]\n"
                   "created: 2026-08-29\nupdated: 2026-08-29\n---\n\nbody\n")
        _, out = self.run_cmd(["orphans"])
        self.assertNotIn("LESSON-uncited", out)
        self.assertNotIn("2026-08-29_snap", out)

    def test_lessons_frontmatter_citation_is_an_edge(self):
        self.write("lessons/LESSON-cited.md",
                   "---\ntitle: L\ntype: lesson\nstatus: active\ncategory: process\n"
                   "area: w\ntags: [x]\nscore: 5\nsummary: \"s\"\n"
                   "created: 2026-08-29\nupdated: 2026-08-29\n---\n\nbody\n")
        self.write("plans/PLAN-001-p.md",
                   "---\ntitle: P\ntype: plan\nstatus: active\narea: w\ntags: [x]\n"
                   "lessons: [\"[[LESSON-cited]]\"]\n"
                   "created: 2026-08-29\nupdated: 2026-08-29\n---\n\nbody\n")
        kinds = [e["kind"] for e in self.graph()["edges"]
                 if "PLAN-001-p" in e["src"] and "LESSON-cited" in e["dst"]]
        self.assertIn("citation", kinds)


class HubDominanceGuardTests(GraphFixture):
    def artifact(self, title, type_, dep):
        return (
            f"---\ntitle: {title}\ntype: {type_}\nstatus: active\narea: w\n"
            f'tags: [x]\ndepends_on: ["[[{dep}]]"]\n'
            f"created: 2026-08-29\nupdated: 2026-08-29\n---\n\nbody\n"
        )

    def test_dominant_hub_stops_seeding_candidates(self):
        from commands import unit_check

        # SPEC-001-core gains HUB_INBOUND_CAP direct dependents spanning
        # three types: dominance, not cohesion - it must not seed.
        dirs = [("research", "RESEARCH", "research"), ("plans", "PLAN", "plan"),
                ("decisions", "ADR", "decision")]
        for n in range(unit_check.HUB_INBOUND_CAP):
            d, prefix, type_ = dirs[n % 3]
            self.write(
                f"{d}/{prefix}-{100 + n}-t{n}.md",
                self.artifact(f"T{n}", type_, "SPEC-001-core"),
            )
        seeds = [spec for spec, _, _ in unit_check.find_candidates(self.root)]
        self.assertNotIn("specs/SPEC-001-core.md", seeds)

    def test_below_cap_spread_still_seeds(self):
        from commands import unit_check

        self.write("research/RESEARCH-001-r.md",
                   self.artifact("R", "research", "SPEC-002-leaf"))
        self.write("plans/PLAN-001-p.md",
                   self.artifact("P", "plan", "SPEC-002-leaf"))
        seeds = [spec for spec, _, _ in unit_check.find_candidates(self.root)]
        self.assertIn("specs/SPEC-002-leaf.md", seeds)


if __name__ == "__main__":
    unittest.main()
