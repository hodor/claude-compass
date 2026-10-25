"""Tests for `compass promote <stem>` resolving a flat artifact at any depth.

A bare stem resolves a flat artifact anywhere under a type dir (inside
domain folders, at any nesting), and an ambiguous stem is refused rather
than guessed.

Adversarial themes: depth beyond one level, an exact stem that is also a
prefix of a sibling's stem, the same stem under two domains or at the root
and in a domain, a refusal that must leave the vault untouched even under
`--apply`, and a dry-run that must write nothing.
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

import vaultlib  # noqa: E402
from commands import promote  # noqa: E402


def spec(title):
    return (f'---\ntitle: "{title}"\ntype: spec\nstatus: approved\narea: workflow\n'
            "tags: [x]\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n")


def domain(name):
    return (f'---\ntitle: "{name}"\ntype: domain\nstatus: active\ntags: [{name}]\n'
            f'summary: "{name} things"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n'
            f"## Scope\n\nClass here: {name} things\n")


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(Path(root).rglob("*")) if p.is_file()
    }


class NestedPromoteCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "specs").mkdir()
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def add(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def promote(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = promote.run(args)
        return code, out.getvalue(), err.getvalue()


class ResolveNestedStemTests(NestedPromoteCase):
    def test_bare_stem_resolves_a_flat_spec_at_any_depth_and_dry_run_writes_nothing(self):
        """Adversarial where: resolution stops at the type dir's top level,
        so a spec one, two or three domains deep reports "spec not found"
        and can never be promoted by stem."""
        self.add("specs/network/index.md", domain("network"))
        self.add("specs/network/cache/index.md", domain("cache"))
        self.add("specs/network/cache/hot/index.md", domain("hot"))
        rows = {
            "one-deep": ("SPEC-003-routing", "specs/network/SPEC-003-routing"),
            "two-deep": ("SPEC-004-eviction", "specs/network/cache/SPEC-004-eviction"),
            "three-deep": ("SPEC-005-hot-keys", "specs/network/cache/hot/SPEC-005-hot-keys"),
        }
        for stem, base in rows.values():
            self.add(f"{base}.md", spec(stem))
        for name, (stem, base) in rows.items():
            with self.subTest(depth=name):
                before = snapshot(self.root)
                code, out, err = self.promote([stem])
                self.assertEqual(code, 0, err)
                self.assertIn(f"{base}.md", out)
                self.assertIn(f"{base}/index.md", out)
                self.assertEqual(snapshot(self.root), before)

    def test_apply_moves_nested_spec_into_its_own_folder_and_keeps_bare_links_resolving(self):
        """Adversarial where: --apply moves the file to a folder at the type
        dir root instead of beside its original location, leaves the flat
        file behind, or breaks `[[stem]]` links by leaving two names."""
        self.add("specs/network/index.md", domain("network"))
        self.add("specs/network/SPEC-003-routing.md", spec("Routing"))
        code, _, err = self.promote(["SPEC-003-routing", "--apply", "--reason", "grew a child"])
        self.assertEqual(code, 0, err)
        flat = self.root / "specs/network/SPEC-003-routing.md"
        index = self.root / "specs/network/SPEC-003-routing/index.md"
        self.assertFalse(flat.exists())
        self.assertTrue(index.is_file())
        self.assertFalse((self.root / "specs/SPEC-003-routing").exists())
        self.assertIn("children_count: 0", index.read_text(encoding="utf-8"))
        names = vaultlib.resolvable_names_map(self.root)
        self.assertEqual(names["SPEC-003-routing"],
                         ["specs/network/SPEC-003-routing/index.md"])

    def test_exact_stem_wins_over_a_longer_stem_that_starts_with_it(self):
        """Adversarial where: prefix matching (the abbreviated-wikilink
        rule) makes `SPEC-003-routing` match `SPEC-003-routing-extras` too,
        so a legitimate exact stem is wrongly refused as ambiguous or the
        longer sibling is promoted."""
        self.add("specs/network/index.md", domain("network"))
        self.add("specs/network/SPEC-003-routing.md", spec("Routing"))
        self.add("specs/network/SPEC-003-routing-extras.md", spec("Routing extras"))
        code, _, err = self.promote(["SPEC-003-routing", "--apply", "--reason", "r"])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "specs/network/SPEC-003-routing/index.md").is_file())
        self.assertTrue((self.root / "specs/network/SPEC-003-routing-extras.md").is_file())


class AmbiguousStemTests(NestedPromoteCase):
    def test_ambiguous_stem_is_refused_and_nothing_moves_even_with_apply(self):
        """Adversarial where: the first match wins (filesystem order), which
        promotes whichever copy sorts first. Covers the same stem under two
        domains and at the root plus in a domain, each with --apply."""
        rows = {
            "two-domains": ["specs/network/SPEC-003-routing.md",
                            "specs/storage/SPEC-003-routing.md"],
            "root-and-domain": ["specs/SPEC-004-dup.md",
                                "specs/network/SPEC-004-dup.md"],
        }
        stems = {"two-domains": "SPEC-003-routing", "root-and-domain": "SPEC-004-dup"}
        for name, files in rows.items():
            with self.subTest(case=name):
                for rel in files:
                    self.add(rel, spec(name))
                before = snapshot(self.root)
                code, _, err = self.promote([stems[name], "--apply", "--reason", "r"])
                self.assertEqual(code, 1)
                self.assertIn("ambiguous", err.lower())
                self.assertEqual(snapshot(self.root), before)
