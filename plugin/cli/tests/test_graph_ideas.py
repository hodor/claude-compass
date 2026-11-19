"""Tests for `ideas:` links in the vault graph.

A spec, plan or decision record that lists an idea in its `ideas:` property is
a `citation` edge to that idea, so `compass graph impact <idea>` lists the
documents that adopted it.

Adversarial themes: the property is read in both list spellings, a body line
that merely looks like the property is not a citation, and an entry naming no
idea neither crashes the graph nor produces a dangling edge.
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


def idea(n, slug):
    return (
        f'---\ntitle: "IDEA-{n:03d}: {slug}"\ntype: idea\nstatus: new\n'
        f'words: "{slug} words"\nled_to: []\nled_to_note: ""\nraw_status: ""\n'
        f'source: "test"\ntags: [idea]\ncreated: 2026-11-01\nupdated: 2026-11-01\n---\n\n'
        f"> {slug} words\n\n## History\n\n- 2026-11-01: new (added)\n"
    )


def artifact(title, typ, ideas=None, form="inline", body="body"):
    props = ""
    if ideas is not None:
        if form == "inline":
            props = "ideas: [" + ", ".join(f'"{x}"' for x in ideas) + "]\n"
        else:
            props = "ideas:\n" + "".join(f'  - "{x}"\n' for x in ideas)
    return (
        f"---\ntitle: {title}\ntype: {typ}\nstatus: approved\narea: w\ntags: [x]\n"
        f"{props}created: 2026-11-01\nupdated: 2026-11-01\n---\n\n{body}\n"
    )


class IdeaGraphFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        for d in ("specs", "plans", "decisions", "meta", "ideas/world-building"):
            (self.root / d).mkdir(parents=True)
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")
        self.write("ideas/world-building/IDEA-001-scar.md", idea(1, "scar"))

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def kinds(self, src_frag, dst_frag):
        return [e["kind"] for e in vaultgraph.build_graph(self.root)["edges"]
                if src_frag in e["src"] and dst_frag in e["dst"]]

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


class IdeasCitationTests(IdeaGraphFixture):
    def test_ideas_property_is_a_citation_edge_in_both_list_spellings(self):
        """Adversarial where: only the inline spelling is read, or the edge
        is typed wikilink or depends_on instead of citation."""
        self.write("specs/SPEC-004-a.md", artifact("A", "spec", ["[[IDEA-001-scar]]"]))
        self.write("plans/PLAN-004-b.md",
                   artifact("B", "plan", ["[[IDEA-001-scar]]"], form="block"))
        self.assertEqual(self.kinds("SPEC-004-a", "IDEA-001-scar"), ["citation"])
        self.assertEqual(self.kinds("PLAN-004-b", "IDEA-001-scar"), ["citation"])

    def test_impact_on_an_idea_lists_every_adopting_document(self):
        """Adversarial where: impact lists only one document type or omits
        the edge that produced each hit."""
        self.write("specs/SPEC-004-a.md", artifact("A", "spec", ["[[IDEA-001-scar]]"]))
        self.write("plans/PLAN-004-b.md", artifact("B", "plan", ["[[IDEA-001-scar]]"]))
        self.write("decisions/ADR-004-c.md",
                   artifact("C", "decision", ["[[IDEA-001-scar]]"]))
        code, out = self.run_cmd(["impact", "IDEA-001-scar"])
        self.assertEqual(code, 0)
        for stem in ("SPEC-004-a", "PLAN-004-b", "ADR-004-c"):
            self.assertIn(stem, out)
        self.assertIn("-[citation]->", out)

    def test_a_body_line_that_looks_like_the_property_is_no_citation(self):
        """Adversarial where: the reader scans the whole file for `ideas:`
        instead of the frontmatter, so prose or a fence becomes a citation."""
        body = "ideas: [[IDEA-001-scar]]\n\n```\nideas: [[IDEA-001-scar]]\n```"
        self.write("specs/SPEC-004-a.md", artifact("A", "spec", body=body))
        self.assertNotIn("citation", self.kinds("SPEC-004-a", "IDEA-001-scar"))

    def test_an_entry_naming_no_idea_makes_no_edge_and_spares_the_good_one(self):
        """Adversarial where: a ghost id in the list crashes the graph build
        or makes it drop the valid entry that follows it."""
        self.write("specs/SPEC-004-a.md",
                   artifact("A", "spec", ["[[IDEA-999-ghost]]", "[[IDEA-001-scar]]"]))
        edges = vaultgraph.build_graph(self.root)["edges"]
        self.assertEqual(self.kinds("SPEC-004-a", "IDEA-001-scar"), ["citation"])
        self.assertFalse([e for e in edges if "ghost" in e["dst"]])


if __name__ == "__main__":
    unittest.main()
