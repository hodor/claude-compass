"""Tests for what `compass sync` does with idea files.

An idea is `ideas/<category>/IDEA-NNN-slug.md`. A spec, plan or decision
record that names an idea in its `ideas:` property moves the idea to
`adopted` (forward only), appends the document to `led_to`, and appends one
history line. Sync also writes each category's `## Ideas` listing and the
`ideas/index.md` overview.

Adversarial themes: the status machine never moves backward or rewrites a
status the human set later; every repeated sync leaves every byte alone; a
malformed `ideas:` entry never blocks a good one; hard characters in his
words survive a rewrite; a listing is recomputed after the status move and
after a hand edit, never only appended to.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402
from commands import sync  # noqa: E402

DATE = r"\d{4}-\d{2}-\d{2}"


def idea_text(n, slug, status="new", words="a scar on the ground", led_to=(),
              omit_led_to=False, history=None, tail="", note=""):
    """An idea file in the record shape the plan gives."""
    if "\n" in words:
        words_yaml = "|-\n" + "".join(f"  {line}\n" for line in words.split("\n"))
        words_yaml = words_yaml.rstrip("\n")
        quote = "\n".join(f"> {line}" for line in words.split("\n"))
    else:
        words_yaml = json.dumps(words, ensure_ascii=False)
        quote = f"> {words}"
    led = ""
    if not omit_led_to:
        led = "led_to: [" + ", ".join(f'"{x}"' for x in led_to) + "]\n"
    hist = history if history is not None else ["2026-11-01: new (added)"]
    hist_block = "".join(f"- {h}\n" for h in hist)
    return (
        f'---\ntitle: "IDEA-{n:03d}: {slug}"\ntype: idea\nstatus: {status}\n'
        f"words: {words_yaml}\n{led}"
        f'led_to_note: "{note}"\nraw_status: ""\nsource: "test"\n'
        f"tags: [idea, gameplay]\ncreated: 2026-11-01\nupdated: 2026-11-01\n---\n\n"
        f"{quote}\n\n## History\n\n{hist_block}{tail}"
    )


def artifact_text(title, typ, status, ideas=None, form="inline"):
    props = ""
    if ideas is not None:
        if form == "inline":
            props = "ideas: [" + ", ".join(f'"{x}"' for x in ideas) + "]\n"
        else:
            props = "ideas:\n" + "".join(f'  - "{x}"\n' for x in ideas)
    return (
        f"---\ntitle: {title}\ntype: {typ}\nstatus: {status}\narea: gameplay\n"
        f"tags: [x]\nsummary: \"{title} summary\"\n{props}"
        f"created: 2026-11-01\nupdated: 2026-11-01\n---\n\nbody\n"
    )


def domain_index(name, summary):
    return (
        f"---\ntitle: {name}\ntype: domain\nstatus: active\ntags: [domain]\n"
        f'summary: "{summary}"\ncreated: 2026-11-01\nupdated: 2026-11-01\n---\n\n'
        f"# {name}\n\n## Scope\n\nClass here: {summary}\n"
    )


class IdeaVault(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        for d in ("specs", "plans", "decisions", "meta", "ideas/world-building"):
            (self.root / d).mkdir(parents=True)
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")
        (self.root / "active.md").write_text("# Active\n", encoding="utf-8")
        (self.root / "meta" / "lessons-catalog.yaml").write_text(
            "lessons: []\n", encoding="utf-8"
        )
        self.write("ideas/world-building/index.md",
                   domain_index("world-building", "ideas about the world"))

    def write(self, rel, body):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8", newline="")

    def read(self, rel):
        return (self.root / rel).read_bytes().decode("utf-8")

    def sync(self):
        return sync.sync(self.root)

    def idea(self, n, slug, **kw):
        rel = f"ideas/world-building/IDEA-{n:03d}-{slug}.md"
        self.write(rel, idea_text(n, slug, **kw))
        return rel

    @staticmethod
    def fm(text):
        return vaultlib.parse_frontmatter_text(text)[0]

    @staticmethod
    def history(text):
        lines = text.split("## History", 1)[1].splitlines()[1:]
        out = []
        for line in lines:
            if line.startswith("## "):
                break
            if line.startswith("- "):
                out.append(line)
        return out


class AdoptionTests(IdeaVault):
    def test_unadopted_idea_moves_forward_for_each_document_type(self):
        """Adversarial where: adoption fires for only one document type, or
        skips a draft document, or fails to record the old status in the
        history line."""
        rows = [
            ("new", "specs/SPEC-004-world.md", "spec", "draft"),
            ("exploring", "specs/SPEC-005-other.md", "spec", "approved"),
            ("new", "plans/PLAN-004-world.md", "plan", "draft"),
            ("exploring", "decisions/ADR-004-world.md", "decision", "approved"),
        ]
        for i, (old, rel, typ, doc_status) in enumerate(rows, start=1):
            with self.subTest(old=old, doc=rel):
                slug = f"scar{i}"
                stem = Path(rel).stem
                irel = self.idea(i, slug, status=old)
                self.write(rel, artifact_text("Doc", typ, doc_status,
                                              [f"[[IDEA-{i:03d}-{slug}]]"]))
                self.sync()
                text = self.read(irel)
                self.assertEqual(self.fm(text)["status"], "adopted")
                self.assertIn(f"[[{stem}]]", str(self.fm(text)["led_to"]))
                moves = [h for h in self.history(text) if "->" in h]
                self.assertEqual(len(moves), 1, moves)
                self.assertRegex(
                    moves[0],
                    rf"^- {DATE}: {old} -> adopted \(\[\[{re.escape(stem)}\]\] names it\)$",
                )
                self.assertIn("2026-11-01: new (added)", self.history(text)[0])

    def test_statuses_that_never_move_back_get_a_named_by_line_once(self):
        """Adversarial where: a parked, dropped, done or already adopted idea
        is dragged to adopted (or back), or gets a history line on every
        sync instead of once."""
        for i, status in enumerate(["parked", "dropped", "done", "adopted"], start=1):
            with self.subTest(status=status):
                slug = f"s{i}"
                irel = self.idea(i, slug, status=status)
                self.write(f"specs/SPEC-10{i}-doc.md",
                           artifact_text("Doc", "spec", "approved",
                                         [f"[[IDEA-{i:03d}-{slug}]]"]))
                self.sync()
                self.sync()
                text = self.read(irel)
                self.assertEqual(self.fm(text)["status"], status)
                hist = self.history(text)
                self.assertEqual(
                    [h for h in hist if "->" in h], [], hist)
                named = [h for h in hist if "named by [[SPEC-10%d-doc]]" % i in h]
                self.assertEqual(len(named), 1, hist)
                self.assertRegex(named[0], rf"^- {DATE}: named by \[\[SPEC-10{i}-doc\]\]$")
                self.assertIn(f"[[SPEC-10{i}-doc]]", str(self.fm(text)["led_to"]))

    def test_repeat_syncs_change_no_byte(self):
        """Adversarial where: a second or third sync re-appends a led_to
        entry or history line, or rewrites the file with different bytes."""
        i1 = self.idea(1, "moved", status="new")
        i2 = self.idea(2, "kept", status="dropped")
        i3 = self.idea(3, "blocklist", status="exploring")
        self.write("specs/SPEC-004-a.md",
                   artifact_text("A", "spec", "draft",
                                 ["[[IDEA-001-moved]]", "[[IDEA-002-kept]]"]))
        self.write("plans/PLAN-004-b.md",
                   artifact_text("B", "plan", "active", ["[[IDEA-003-blocklist]]"],
                                 form="block"))
        self.sync()
        snap = {r: self.read(r) for r in (i1, i2, i3, "ideas/world-building/index.md",
                                          "specs/SPEC-004-a.md", "plans/PLAN-004-b.md")}
        self.sync()
        self.sync()
        for rel, before in snap.items():
            with self.subTest(file=rel):
                self.assertEqual(before, self.read(rel))
        self.assertEqual(self.fm(snap[i3])["status"], "adopted")

    def test_status_the_human_sets_after_adoption_survives_the_next_sync(self):
        """Adversarial where: sync re-adopts or overwrites an idea the human
        dropped after it was adopted, because the document still names it."""
        irel = self.idea(1, "scar", status="new")
        self.write("specs/SPEC-004-a.md",
                   artifact_text("A", "spec", "approved", ["[[IDEA-001-scar]]"]))
        self.sync()
        adopted = self.read(irel)
        human = adopted.replace("status: adopted", "status: dropped") \
            + "- 2026-11-20: adopted -> dropped (he decided against it)\n"
        self.write(irel, human)
        self.sync()
        self.sync()
        text = self.read(irel)
        self.assertEqual(self.fm(text)["status"], "dropped")
        self.assertEqual(len([h for h in self.history(text) if "-> adopted" in h]), 1)
        self.assertIn("he decided against it", text)

    def test_removing_the_property_later_leaves_status_and_history(self):
        """Adversarial where: sync treats the vanished `ideas:` property as
        an un-adoption and reverts the status or prunes history and led_to."""
        irel = self.idea(1, "scar", status="new")
        self.write("specs/SPEC-004-a.md",
                   artifact_text("A", "spec", "approved", ["[[IDEA-001-scar]]"]))
        self.sync()
        before = self.read(irel)
        self.write("specs/SPEC-004-a.md", artifact_text("A", "spec", "approved"))
        self.sync()
        text = self.read(irel)
        self.assertEqual(self.fm(text)["status"], "adopted")
        self.assertEqual(self.history(before), self.history(text))
        self.assertIn("[[SPEC-004-a]]", str(self.fm(text)["led_to"]))

    def test_two_documents_naming_one_idea_give_two_led_to_and_one_move(self):
        """Adversarial where: the second document re-fires the status move
        (two `-> adopted` lines) or is dropped from led_to."""
        irel = self.idea(1, "scar", status="new")
        self.write("specs/SPEC-004-a.md",
                   artifact_text("A", "spec", "approved", ["[[IDEA-001-scar]]"]))
        self.write("plans/PLAN-004-b.md",
                   artifact_text("B", "plan", "draft", ["[[IDEA-001-scar]]"]))
        self.sync()
        self.sync()
        text = self.read(irel)
        led = str(self.fm(text)["led_to"])
        self.assertEqual(led.count("[[SPEC-004-a]]"), 1, led)
        self.assertEqual(led.count("[[PLAN-004-b]]"), 1, led)
        hist = self.history(text)
        self.assertEqual(len([h for h in hist if "-> adopted" in h]), 1, hist)
        for stem in ("SPEC-004-a", "PLAN-004-b"):
            self.assertTrue(any(f"[[{stem}]]" in h for h in hist), (stem, hist))

    def test_bad_entries_are_reported_and_good_entries_still_apply(self):
        """Adversarial where: one unknown id (or a link to a non-idea
        document) in the middle of the list aborts the sync or silently
        swallows the rest of the list, or creates a stub idea file."""
        irel = self.idea(1, "scar", status="new")
        spec = artifact_text("A", "spec", "approved",
                             ["[[IDEA-999-ghost]]", "[[IDEA-001-scar]]", "[[SPEC-004-a]]"])
        self.write("specs/SPEC-004-a.md", spec)
        report = self.sync()
        self.assertEqual(self.fm(self.read(irel))["status"], "adopted")
        self.assertIn("IDEA-999-ghost", json.dumps(report, default=str))
        self.assertEqual(list((self.root / "ideas").rglob("IDEA-999*")), [])
        self.assertEqual(spec, self.read("specs/SPEC-004-a.md"))

    def test_an_idea_naming_another_idea_adopts_nothing(self):
        """Adversarial where: the adoption scan treats an idea file's own
        `ideas:` property as a document naming an idea, adopting its target."""
        self.idea(1, "target", status="new")
        two = idea_text(2, "pointer", status="new")
        two = two.replace("tags: [idea, gameplay]",
                          'tags: [idea, gameplay]\nideas: ["[[IDEA-001-target]]"]')
        self.write("ideas/world-building/IDEA-002-pointer.md", two)
        self.sync()
        text = self.read("ideas/world-building/IDEA-001-target.md")
        self.assertEqual(self.fm(text)["status"], "new")
        self.assertEqual(self.fm(text)["led_to"], [])

    def test_rewrite_touches_only_the_lines_sync_owns(self):
        """Adversarial where: adoption re-serializes the whole file and
        mangles his words (quote, backslash, accents, colon, hash, a block
        scalar), or lands the history line after a following section."""
        cases = {
            "hard": 'say "hi" \\ não: #1 [a] - você...',
            "block": "linha um\nlinha dois: ainda",
        }
        for n, (key, words) in enumerate(cases.items(), start=1):
            with self.subTest(words=key):
                slug = f"w{n}"
                irel = self.idea(n, slug, status="new", words=words,
                                 note="[[SPEC-001-x]]: a note", led_to=["[[SPEC-001-x]]"],
                                 tail="\n## Notes\n\nhand written notes stay\n")
                self.write(f"specs/SPEC-20{n}-a.md",
                           artifact_text("A", "spec", "approved",
                                         [f"[[IDEA-{n:03d}-{slug}]]"]))
                before = self.read(irel).splitlines()
                self.sync()
                text = self.read(irel)
                after = text.splitlines()
                owned = ("status:", "led_to:", "updated:")
                added = re.compile(rf"^- {DATE}: .*(adopted|named by)")
                keep_before = [l for l in before if not l.startswith(owned)]
                keep_after = [l for l in after
                              if not l.startswith(owned) and not added.match(l)]
                self.assertEqual(keep_before, keep_after)
                self.assertEqual(self.fm(text)["words"].replace("\n", "|"),
                                 words.replace("\n", "|"))
                self.assertLess(text.index("-> adopted"), text.index("## Notes"))

    def test_led_to_shapes_each_gain_exactly_one_entry(self):
        """Adversarial where: a missing led_to key, an empty list, a list
        already holding another link, or already holding this document each
        break the append (crash, drop the old entry, or duplicate)."""
        rows = {
            "missing": dict(omit_led_to=True),
            "empty": dict(led_to=[]),
            "other": dict(led_to=["[[SPEC-001-x]]"]),
            "already": dict(led_to=["[[SPEC-004-a]]"]),
        }
        for n, (name, kw) in enumerate(rows.items(), start=1):
            with self.subTest(shape=name):
                slug = f"l{n}"
                irel = self.idea(n, slug, status="new", **kw)
                self.write(f"specs/SPEC-30{n}-a.md",
                           artifact_text("A", "spec", "approved",
                                         [f"[[IDEA-{n:03d}-{slug}]]"]))
                if name == "already":
                    self.write("specs/SPEC-004-a.md",
                               artifact_text("A", "spec", "approved",
                                             [f"[[IDEA-{n:03d}-{slug}]]"]))
                self.sync()
                led = self.fm(self.read(irel))["led_to"]
                led = led if isinstance(led, list) else [led]
                self.assertEqual(len(led), len(set(led)), led)
                self.assertIn(f"[[SPEC-30{n}-a]]", led)
                if name == "other":
                    self.assertIn("[[SPEC-001-x]]", led)

    def test_unchanged_idea_is_not_reported_as_written(self):
        """Adversarial where: the report names an idea file as rewritten on
        a sync that left its bytes alone."""
        self.idea(1, "scar", status="new")
        self.write("specs/SPEC-004-a.md",
                   artifact_text("A", "spec", "approved", ["[[IDEA-001-scar]]"]))
        self.sync()
        second = self.sync()
        self.assertNotIn("IDEA-001-scar", json.dumps(second, default=str))


class ListingTests(IdeaVault):
    def test_category_index_lists_each_idea_in_the_line_format(self):
        """Adversarial where: the listing drops dropped ideas, mangles
        accents, loses the hand-written Scope text, or doubles the heading on
        a second sync."""
        self.idea(1, "scar", status="new", words="o mapa lembra onde você caiu")
        self.idea(2, "gone", status="dropped", words="a tower")
        self.sync()
        self.sync()
        text = self.read("ideas/world-building/index.md")
        self.assertEqual(text.count("## Ideas"), 1)
        self.assertIn('- [[IDEA-001-scar]] - new - "o mapa lembra onde você caiu"', text)
        self.assertIn('- [[IDEA-002-gone]] - dropped - "a tower"', text)
        self.assertIn("Class here: ideas about the world", text)

    def test_listing_shows_the_status_after_the_adoption_move(self):
        """Adversarial where: the listing is computed before adoption runs
        in the same sync, so a freshly adopted idea reads `new` until the
        next sync."""
        self.idea(1, "scar", status="new")
        self.write("specs/SPEC-004-a.md",
                   artifact_text("A", "spec", "approved", ["[[IDEA-001-scar]]"]))
        self.sync()
        self.assertIn('- [[IDEA-001-scar]] - adopted - "a scar on the ground"',
                      self.read("ideas/world-building/index.md"))

    def test_words_are_cut_at_one_hundred_characters(self):
        """Adversarial where: the cut falls one character early or late, so
        a 100-character sentence gains an ellipsis or a 101-character one
        shows whole; or multi-line words break the one-line-per-idea rule."""
        hundred = "abcdefghij" * 10
        self.idea(1, "exact", words=hundred)
        self.idea(2, "over", words=hundred + "k")
        self.idea(3, "multi", words="line one\nline two")
        self.sync()
        lines = [l for l in self.read("ideas/world-building/index.md").splitlines()
                 if "[[IDEA-" in l]
        by = {k: next(l for l in lines if f"IDEA-00{k}" in l) for k in (1, 2, 3)}
        self.assertIn(f'"{hundred}"', by[1])
        self.assertNotIn("...", by[1])
        self.assertNotIn(hundred + "k", by[2])
        self.assertIn("...", by[2])
        self.assertIn(hundred[:97], by[2])
        self.assertEqual(len(lines), 3, lines)
        self.assertIn("line one", by[3])

    def test_listing_follows_a_hand_edit_and_a_deletion(self):
        """Adversarial where: the listing is append-only, so a changed status
        or changed words leave the stale line behind and a deleted idea
        keeps its line."""
        irel = self.idea(1, "scar", status="new", words="first words")
        gone = self.idea(2, "gone", status="new")
        self.sync()
        self.write(irel, idea_text(1, "scar", status="parked", words="second words"))
        (self.root / gone).unlink()
        self.sync()
        text = self.read("ideas/world-building/index.md")
        self.assertIn('- [[IDEA-001-scar]] - parked - "second words"', text)
        self.assertNotIn("first words", text)
        self.assertNotIn("IDEA-002-gone", text)

    def test_ideas_overview_counts_categories_then_lists_uncategorized(self):
        """Adversarial where: ideas/index.md is not created when missing,
        omits an empty category, miscounts, or lists loose ideas before the
        categories."""
        (self.root / "ideas" / "empty-cat").mkdir()
        self.write("ideas/empty-cat/index.md", domain_index("empty-cat", "nothing yet"))
        self.idea(1, "a", status="new")
        self.idea(2, "b", status="parked")
        self.write("ideas/IDEA-009-loose.md", idea_text(9, "loose", words="loose words"))
        self.assertFalse((self.root / "ideas" / "index.md").exists())
        self.sync()
        text = self.read("ideas/index.md")
        cat = next(l for l in text.splitlines() if "world-building" in l)
        self.assertIn("2 ideas", cat)
        self.assertIn("new", cat)
        self.assertIn("parked", cat)
        self.assertIn("ideas about the world", cat)
        self.assertIn("empty-cat", text)
        self.assertGreater(text.index("IDEA-009-loose"), text.index("world-building"))
        self.assertGreater(text.index("IDEA-009-loose"), text.index("empty-cat"))
        before = text
        self.sync()
        self.assertEqual(before, self.read("ideas/index.md"))

    def test_no_overview_for_a_vault_without_idea_files(self):
        """Adversarial where: sync invents ideas/index.md for an ideas
        folder holding only an empty category."""
        self.sync()
        self.assertFalse((self.root / "ideas" / "index.md").exists())

    def test_idea_files_stay_out_of_the_root_index_but_folder_lines_stay(self):
        """Adversarial where: every idea floods the root index (hot path), or
        the category folder line disappears with them."""
        self.idea(1, "scar")
        self.write("specs/SPEC-004-a.md", artifact_text("A", "spec", "approved"))
        self.sync()
        root_index = self.read("index.md")
        self.assertNotIn("IDEA-001-scar", root_index)
        self.assertIn("SPEC-004-a", root_index)
        self.assertIn("ideas/world-building/index", root_index)


if __name__ == "__main__":
    unittest.main()
