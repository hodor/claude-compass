"""Adversarial tests for sync's idea handling, written against the built code.

Sync runs after every vault write in every project, so these probe what the
listing and adoption code does with input a person types or a Windows tool
writes: link syntax and backticks inside his words, a cut at 100 characters
that lands inside a link, BOM and CRLF idea files, `ideas:` entries that
name a file that is not an idea record, categories nested two deep, a
block-scalar `words` holding a `---` line, and the cost of a large idea set.
"""

import os
import re
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vaultgraph  # noqa: E402
from commands import sync, validate  # noqa: E402
from test_sync_ideas import (  # noqa: E402
    IdeaVault, artifact_text, domain_index, idea_text,
)

LISTING_LINE = re.compile(r'^- \[\[(IDEA-\d+-[^\]|]+)\]\] - (\w+) - "(.*)"$')


def idea_lines(text):
    return [l for l in text.splitlines() if l.startswith("- [[IDEA-")]


class ListingHardCharacterTests(IdeaVault):
    def test_link_syntax_in_his_words_never_becomes_a_live_link(self):
        """Adversarial where: a `[[...]]` typed in his words is copied into
        the listing line verbatim, so the category index gains a wikilink he
        never made: a graph edge to a real document, and a broken-link
        warning for a name that is only prose. The 100-character cut that
        lands inside `[[` leaves a dangling opener that a multi-line link
        scan pairs with the next line's link."""
        rows = {
            "link-to-real-doc": "see [[SPEC-004-a]] for the map",
            "link-to-nothing": "he said [[Nonexistent Thing]] is cool",
            "aliased-link": "try [[SPEC-004-a|the plan]] soon",
            "cut-inside-opener": "x" * 97 + "[[SPEC-004-a]] tail",
            "cut-inside-target": "x" * 90 + "[[SPEC-004-a]] tail",
            "cut-inside-closer": "x" * 85 + "[[SPEC-004-a]] and more words",
        }
        self.write("specs/SPEC-004-a.md", artifact_text("A", "spec", "draft"))
        for n, (name, words) in enumerate(rows.items(), start=1):
            self.idea(n, name, words=words)
        self.sync()
        index = self.read("ideas/world-building/index.md")
        lines = idea_lines(index)
        self.assertEqual(len(lines), len(rows), lines)
        for line in lines:
            with self.subTest(line=line):
                match = LISTING_LINE.match(line)
                self.assertIsNotNone(match, line)
                self.assertNotIn("[[", match.group(3))
        links = [m for m in sync.WIKILINK.findall(index)]
        self.assertEqual(
            links, [f"IDEA-{n:03d}-{name}" for n, name in enumerate(rows, 1)],
            "the only links in the listing are the leading idea links",
        )
        errors, warnings = validate.check_vault(self.root)
        broken = [w for w in warnings
                  if w.startswith("broken_wikilink: ideas/world-building/index.md")]
        self.assertEqual(broken, [])
        graph = vaultgraph.build_graph(self.root)
        into_spec = [e for e in graph["edges"]
                     if e["src"] == "ideas/world-building/index.md"
                     and e["dst"].startswith("specs/")]
        self.assertEqual(into_spec, [])

    def test_pipe_backtick_hash_and_quote_stay_verbatim_on_one_line(self):
        """Adversarial where: an unbalanced backtick, a `|`, a `#`, a `^id`
        tail or an inner double quote in his words is dropped, escaped or
        splits the listing line, so the line no longer matches the
        `- [[id]] - status - "words"` shape other tooling reads."""
        rows = {
            "backtick-open": "run `compass sync and wait",
            "pipe": "a | b | c",
            "hash": "# not a heading",
            "block-id": "ends like a block id ^abc123",
            "quotes": 'he said "go" twice',
            "trailing-backslash": "ends with a slash \\",
        }
        for n, (name, words) in enumerate(rows.items(), start=1):
            self.idea(n, name, words=words)
        self.sync()
        lines = idea_lines(self.read("ideas/world-building/index.md"))
        self.assertEqual(len(lines), len(rows), lines)
        for n, (name, words) in enumerate(rows.items(), start=1):
            with self.subTest(name=name):
                self.assertIn(
                    f'- [[IDEA-{n:03d}-{name}]] - new - "{words}"', lines)


class EncodingTests(IdeaVault):
    def raw(self, rel, text, bom, crlf):
        data = text.replace("\n", "\r\n") if crlf else text
        payload = data.encode("utf-8")
        if bom:
            payload = b"\xef\xbb\xbf" + payload
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return payload

    def test_idea_needing_no_change_keeps_its_bytes_in_every_encoding(self):
        """Adversarial where: an idea whose history already names the
        document is re-read through the BOM/CRLF-normalizing reader and
        written back as LF without the BOM, so every sync dirties a file the
        human's editor keeps converting back."""
        rows = [(False, True), (True, False), (True, True)]
        for n, (bom, crlf) in enumerate(rows, start=1):
            with self.subTest(bom=bom, crlf=crlf):
                doc = f"SPEC-20{n}-named"
                rel = f"ideas/world-building/IDEA-{n:03d}-named{n}.md"
                before = self.raw(rel, idea_text(
                    n, f"named{n}", status="adopted", led_to=[f"[[{doc}]]"],
                    history=["2026-11-01: new (added)",
                             f"2026-11-02: new -> adopted ([[{doc}]] names it)"],
                ), bom, crlf)
                self.write(f"specs/{doc}.md", artifact_text(
                    "Doc", "spec", "draft", [f"[[IDEA-{n:03d}-named{n}]]"]))
                report = self.sync()
                self.assertEqual(report["ideas_changed"], [])
                self.assertEqual((self.root / rel).read_bytes(), before)

    def test_bom_and_crlf_idea_and_spec_still_adopt_and_list(self):
        """Adversarial where: a BOM defeats the `---` fence match, so the
        idea reads as having no frontmatter (or the spec's `ideas:` is never
        seen) and adoption or the listing silently skips the file."""
        irel = "ideas/world-building/IDEA-001-win.md"
        self.raw(irel, idea_text(1, "win", words="windows words"), True, True)
        self.raw("specs/SPEC-004-win.md",
                 artifact_text("Win", "spec", "draft", ["[[IDEA-001-win]]"]),
                 True, True)
        report = self.sync()
        self.assertEqual(report["ideas_unresolved"], [])
        self.assertEqual(len(report["ideas_changed"]), 1)
        self.assertEqual(self.fm(self.read(irel))["status"], "adopted")
        self.assertIn(
            '- [[IDEA-001-win]] - adopted - "windows words"',
            self.read("ideas/world-building/index.md"))


class NamedFileIsNotAnIdeaTests(IdeaVault):
    def test_entry_naming_an_unreadable_idea_file_is_reported_and_harmless(self):
        """Adversarial where: an `ideas:` entry that resolves to a file named
        like an idea but holding no readable record (no frontmatter, an
        unterminated fence) crashes sync, silently adopts nothing without a
        report line, rewrites the broken file, or blocks the good entry
        beside it."""
        bad = {
            "ideas/world-building/IDEA-010-nofm.md": "just prose, no fence\n",
            "ideas/world-building/IDEA-011-open.md":
                "---\ntitle: x\nstatus: new\n\n> words\n",
        }
        before = {}
        for rel, body in bad.items():
            self.write(rel, body)
            before[rel] = body
        good = self.idea(1, "fine", status="new")
        self.write("specs/SPEC-004-a.md", artifact_text(
            "A", "spec", "draft",
            ["[[IDEA-010-nofm]]", "[[IDEA-011-open]]", "[[IDEA-001-fine]]"]))
        report = self.sync()
        self.assertEqual(len(report["ideas_unresolved"]), 2,
                         report["ideas_unresolved"])
        joined = "\n".join(report["ideas_unresolved"])
        self.assertIn("IDEA-010-nofm", joined)
        self.assertIn("IDEA-011-open", joined)
        for rel, body in before.items():
            self.assertEqual(self.read(rel), body)
        self.assertEqual(self.fm(self.read(good))["status"], "adopted")
        self.sync()
        self.assertEqual(self.read("ideas/world-building/IDEA-010-nofm.md"),
                         before["ideas/world-building/IDEA-010-nofm.md"])

    def test_link_forms_all_reach_the_same_idea_once(self):
        """Adversarial where: a path-qualified link, an alias or a heading
        suffix on the `ideas:` entry fails to resolve (reported as broken),
        or the same idea named three ways gains three led_to entries and
        three history lines."""
        irel = self.idea(1, "top", status="new")
        self.write("specs/SPEC-004-a.md", artifact_text(
            "A", "spec", "draft",
            ["[[ideas/world-building/IDEA-001-top]]",
             "[[IDEA-001-top|his idea]]", "[[IDEA-001-top#History]]"]))
        report = self.sync()
        self.assertEqual(report["ideas_unresolved"], [])
        text = self.read(irel)
        self.assertEqual(self.fm(text)["led_to"], ["[[SPEC-004-a]]"])
        self.assertEqual(len([h for h in self.history(text) if "SPEC-004-a" in h]), 1)


class NestedCategoryTests(IdeaVault):
    def test_idea_two_folders_deep_lists_only_in_its_own_folder_index(self):
        """Adversarial where: a nested category's idea shows in its parent's
        listing too (prefix match on the folder name), is counted twice in
        the overview, floods the root index, or is never adopted."""
        self.write("ideas/world-building/lore/index.md",
                   domain_index("lore", "deep lore"))
        self.idea(1, "top", words="top words")
        deep = "ideas/world-building/lore/IDEA-005-deep.md"
        self.write(deep, idea_text(5, "deep", words="deep words"))
        self.write("specs/SPEC-004-a.md", artifact_text(
            "A", "spec", "draft", ["[[IDEA-005-deep]]"]))
        self.sync()
        self.assertEqual(self.fm(self.read(deep))["status"], "adopted")
        parent = self.read("ideas/world-building/index.md")
        child = self.read("ideas/world-building/lore/index.md")
        overview = self.read("ideas/index.md")
        self.assertIn('- [[IDEA-005-deep]] - adopted - "deep words"', child)
        self.assertNotIn("IDEA-005-deep", parent)
        self.assertNotIn("IDEA-001-top", child)
        self.assertIn("(1 ideas: 1 new)", overview)
        self.assertIn("(1 ideas: 1 adopted)", overview)
        self.assertNotIn("IDEA-005-deep", self.read("index.md"))
        self.sync()
        self.assertEqual(child, self.read("ideas/world-building/lore/index.md"))


class WordsWithFenceLineTests(IdeaVault):
    def test_adoption_keeps_multiline_words_holding_a_fence_and_property_lines(self):
        """Adversarial where: a block-scalar `words` containing a `---` line,
        a blank line and lines shaped like `status:` or `updated:` is read as
        the end of the frontmatter, or the status/updated edit lands inside
        his words, so his words change when the idea is adopted."""
        words = "first\n\n---\nstatus: dropped\nupdated: 1999-01-01\nled_to: []"
        irel = self.idea(1, "fence", status="new", words=words)
        self.write("specs/SPEC-004-a.md", artifact_text(
            "A", "spec", "draft", ["[[IDEA-001-fence]]"]))
        self.sync()
        data = self.fm(self.read(irel))
        self.assertEqual(data["words"], words)
        self.assertEqual(data["status"], "adopted")
        self.assertEqual(data["led_to"], ["[[SPEC-004-a]]"])
        self.sync()
        self.assertEqual(self.fm(self.read(irel))["words"], words)

    def test_fence_line_in_words_makes_no_graph_edge_from_frontmatter(self):
        """Adversarial where: the graph's frontmatter splitter treats an
        indented `---` inside `words` as the closing fence, so the rest of
        the frontmatter (`led_to` links) is read as body text and becomes
        wikilink edges from the idea."""
        words = "first\n---\nsecond"
        self.write("specs/SPEC-004-a.md", artifact_text("A", "spec", "draft"))
        self.idea(1, "fence", words=words, led_to=["[[SPEC-004-a]]"])
        graph = vaultgraph.build_graph(self.root)
        edges = [e for e in graph["edges"]
                 if e["src"] == "ideas/world-building/IDEA-001-fence.md"
                 and e["dst"] == "specs/SPEC-004-a.md"]
        self.assertEqual(edges, [])


class VolumeTests(IdeaVault):
    def test_five_hundred_ideas_sync_in_bounded_time_and_settle(self):
        """Adversarial where: adoption or the listing re-reads every idea per
        document or per idea, so sync (which runs after every vault write)
        grows quadratically with the idea count; or a settled vault is
        rewritten on every pass."""
        count = 500
        for i in range(1, count + 1):
            self.write(f"ideas/world-building/IDEA-{i:03d}-s{i}.md",
                       idea_text(i, f"s{i}", words=f"words number {i} " + "w" * 60))
        for d in range(50):
            names = [f"[[IDEA-{i:03d}-s{i}]]" for i in range(1 + d * 10, 11 + d * 10)]
            self.write(f"specs/SPEC-{100 + d}-d.md",
                       artifact_text("D", "spec", "draft", names))
        self.sync()
        files = sorted((self.root / "ideas").rglob("*.md"))
        before = {p: p.read_bytes() for p in files}
        started = time.perf_counter()
        report = self.sync()
        elapsed = time.perf_counter() - started
        print(f"settled sync over {count} ideas: {elapsed:.2f}s")
        self.assertEqual(report["ideas_changed"], [])
        self.assertEqual(report["ideas_indexes"], 0)
        self.assertLess(elapsed, 15.0)
        self.assertEqual({p: p.read_bytes() for p in files}, before)
        listing = idea_lines(self.read("ideas/world-building/index.md"))
        self.assertEqual(len(listing), count)
        self.assertTrue(all(" - adopted - " in l for l in listing))


if __name__ == "__main__":
    unittest.main()
