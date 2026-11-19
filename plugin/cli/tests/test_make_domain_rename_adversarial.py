"""Implementation-revealed edge cases for `compass make-domain --rename`,
`--undo` archiving and `--title`.

Adversarial themes: the index rewrite parses frontmatter by hand, so quoting
and line-ending forms of `title:`/`tags:` are its failure surface; the undo
moves through `git mv` then removes a directory, so a tracked folder is a
different path than an untracked one; the rename accepts path strings, so a
unit prefix, a `..` segment and a non-domain folder reach branches the
spec's refusal list never named.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_make_domain_rename as base  # noqa: E402
import vaultlib  # noqa: E402


def git(project, *args):
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args], cwd=project,
        capture_output=True, text=True, check=True).stdout


class RetargetIndexTests(base.DomainFixture):
    def rename_index(self, raw, old="network", new="web"):
        self.put(f"specs/{old}/index.md", raw)
        code, _, err = self.run_cmd(
            ["--rename", f"specs/{old}", f"specs/{new}", "--apply", "--reason", "r"])
        self.assertEqual(code, 0, err)
        return (self.root / "specs" / new / "index.md").read_bytes()

    def test_rename_handles_each_title_and_tag_frontmatter_form(self):
        """Adversarial where: the hand-written frontmatter edit only knows
        the generated shape, so a single-quoted title, an escaped-quote
        title (the heading then keeps the old text), a block-list `tags:`,
        a quoted first tag, an empty `tags: []`, or a missing `title:` line
        leaves the index parsing to the wrong title/tag or not at all."""
        scope = b"## Scope\n\nClass here: net.\n"
        head = "---\n{title}type: domain\nstatus: active\n{tags}created: 2026-08-30\n---\n\n"
        cases = {
            "single-quoted title": ("title: 'network'\n", "tags: [network]\n", "# network\n\n"),
            "escaped-quote title": (
                'title: "He said \\"hi\\""\n', "tags: [network]\n", '# He said "hi"\n\n'),
            "backslash title": (
                'title: "a\\\\b"\n', "tags: [network]\n", "# a\\b\n\n"),
            "block tags": ("title: network\n", "tags:\n  - network\n  - extra\n", "# network\n\n"),
            "quoted first tag": ("title: network\n", 'tags: ["network", "extra"]\n', "# network\n\n"),
            "empty tags": ("title: network\n", "tags: []\n", "# network\n\n"),
            "missing title": ("", "tags: [network]\n", "# network\n\n"),
        }
        for name, (title, tags, heading) in cases.items():
            with self.subTest(name=name):
                shutil.rmtree(self.root / "specs", ignore_errors=True)
                raw = (head.format(title=title, tags=tags) + heading).encode() + scope
                out = self.rename_index(raw)
                path = self.root / "specs" / "web" / "index.md"
                data, error = vaultlib.parse_frontmatter(path)
                self.assertIsNone(error)
                self.assertEqual(data.get("title"), "web")
                self.assertEqual(data.get("tags")[0], "web")
                self.assertTrue(out.endswith(b"\n\n" + scope), "Scope text changed")
                self.assertIn(b"\n# web\n", out, "first heading kept the old title")

    def test_rename_of_crlf_frontmatter_keeps_every_line_ending(self):
        """Adversarial where: rewriting frontmatter lines drops their `\\r`
        (or the inserted `sizing_id` line lacks one), so a CRLF index comes
        back with mixed line endings."""
        raw = (
            "---\r\ntitle: network\r\ntype: domain\r\nstatus: active\r\n"
            "tags: [network, extra]\r\nupdated: 2026-08-30\r\n---\r\n\r\n"
            "# network\r\n\r\n## Scope\r\n\r\nClass here: net.\r\n"
        ).encode()
        out = self.rename_index(raw)
        self.assertNotIn(b"\n", out.replace(b"\r\n", b""), "a bare LF line ending appeared")
        self.assertIn(b"sizing_id: sz-", out)
        self.assertIn(b'title: "web"\r\n', out)
        self.assertIn(b"tags: [web, extra]\r\n", out)

    def test_rename_stamps_the_logged_sizing_id_into_an_unstamped_index(self):
        """Adversarial where: an index without `sizing_id` is renamed and
        the id minted for the log row is never written into the file, so the
        domain's own record and its sizing history cannot be joined."""
        raw = (
            b"---\ntitle: network\ntype: domain\nstatus: active\ntags: [network]\n"
            b"updated: 2026-08-30\n---\n\n## Scope\n\nClass here: net.\n"
        )
        out = self.rename_index(raw)
        data, _ = vaultlib.parse_frontmatter(self.root / "specs" / "web" / "index.md")
        stamped = data.get("sizing_id")
        self.assertTrue(stamped)
        log = (self.root / "meta" / "sizing-log.yaml").read_text(encoding="utf-8")
        self.assertIn(f"id: {stamped}", log)
        self.assertEqual(out.count(b"sizing_id:"), 1)

    def test_rename_refuses_an_index_with_no_frontmatter_changing_nothing(self):
        """Adversarial where: an index.md with no frontmatter block is moved
        anyway (or half-rewritten) because the retarget returns nothing the
        caller checks before the move."""
        self.put("specs/network/index.md", b"# network\n\n## Scope\n\nClass here.\n")
        before = self.snapshot()
        code, _, err = self.run_cmd(
            ["--rename", "specs/network", "specs/web", "--apply", "--reason", "r"])
        self.assertEqual(code, 1, err)
        self.assertEqual(self.snapshot(), before)


class RenamePathTests(base.DomainFixture):
    def test_rename_inside_a_unit_rewrites_unit_qualified_links(self):
        """Adversarial where: the type-dir prefix check only knows root type
        dirs, so a domain under `<unit>/specs/` is refused or its
        `[[unit/specs/...]]` links are left pointing at the old folder."""
        (self.root / "myunit" / "specs").mkdir(parents=True)
        self.put("myunit/index.md",
                 "---\ntitle: myunit\ntype: unit\nstatus: active\n---\n\n# myunit\n")
        self.put("myunit/specs/network/index.md", base.index_bytes("network", ["network"]))
        self.put("myunit/specs/network/SPEC-001-a.md", base.spec_body("A"))
        self.put("plans/PLAN-001-p.md",
                 "---\ntitle: P\ntype: plan\n---\n\n[[myunit/specs/network/SPEC-001-a]]\n")
        code, _, err = self.run_cmd(
            ["--rename", "myunit/specs/network", "myunit/specs/web", "--apply", "--reason", "r"])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "myunit" / "specs" / "web" / "SPEC-001-a.md").is_file())
        plan = (self.root / "plans" / "PLAN-001-p.md").read_text(encoding="utf-8")
        self.assertIn("[[myunit/specs/web/SPEC-001-a]]", plan)

    def test_rename_refuses_folders_that_are_not_topic_domains(self):
        """Adversarial where: the only source check is that `index.md`
        exists, so a spec that is itself a folder (index.md of `type: spec`),
        a type dir, or a target colliding with a `<name>.md` file is renamed
        as if it were a domain: its title and first tag are overwritten."""
        spec_index = (
            "---\ntitle: Routing\ntype: spec\nstatus: approved\narea: w\n"
            "tags: [routing]\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n")
        def seed():
            shutil.rmtree(self.root / "specs", ignore_errors=True)
            self.put("specs/SPEC-001-routing/index.md", spec_index)
            self.put("specs/web.md", base.spec_body("web file"))
            self.put("specs/network/index.md", base.index_bytes("network", ["network"]))

        cases = {
            "spec folder": ("specs/SPEC-001-routing", "specs/SPEC-001-paths"),
            "type dir": ("specs", "docs"),
            "target equals a md file": ("specs/network", "specs/web"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name=name):
                seed()
                before = self.snapshot()
                code, _, _ = self.run_cmd(
                    ["--rename", old, new, "--apply", "--reason", "r"])
                self.assertEqual(code, 1)
                self.assertEqual(self.snapshot(), before)

    def test_rename_with_dotdot_segments_is_refused_or_links_follow(self):
        """Adversarial where: `specs/../research/net` passes the type-dir
        and sibling checks as strings while naming a research folder, so the
        folder moves but its links (keyed on the `..` spelling) are never
        rewritten, leaving dead wikilinks."""
        self.put("research/net/index.md", base.index_bytes("net", ["net"]))
        self.put("research/net/RESEARCH-001-a.md", base.spec_body("R"))
        self.put("plans/PLAN-001-p.md",
                 "---\ntitle: P\ntype: plan\n---\n\n[[research/net/RESEARCH-001-a]]\n")
        code, _, _ = self.run_cmd(
            ["--rename", "specs/../research/net", "specs/../research/web",
             "--apply", "--reason", "r"])
        plan = (self.root / "plans" / "PLAN-001-p.md").read_text(encoding="utf-8")
        if code == 0:
            self.assertIn("[[research/web/RESEARCH-001-a]]", plan)
        else:
            self.assertTrue((self.root / "research" / "net").is_dir())

    def test_rename_rewrites_the_canvas_cards_of_moved_files(self):
        """Adversarial where: the rename sweeps wikilinks but forgets
        `specs.canvas`, so cards keep pointing at `specs/network/...` and
        render as missing files."""
        self.put("specs/network/index.md", base.index_bytes("network", ["network"]))
        self.put("specs/network/SPEC-001-a.md", base.spec_body("A"))
        card = {"nodes": [{"id": "1", "type": "file", "file": "specs/network/SPEC-001-a.md",
                           "x": 0, "y": 0, "width": 10, "height": 10},
                          {"id": "2", "type": "file", "file": "specs/other/X.md",
                           "x": 0, "y": 0, "width": 10, "height": 10}], "edges": []}
        self.put("specs.canvas", json.dumps(card))
        code, _, err = self.run_cmd(
            ["--rename", "specs/network", "specs/web", "--apply", "--reason", "r"])
        self.assertEqual(code, 0, err)
        files = [n["file"] for n in json.loads(
            (self.root / "specs.canvas").read_text(encoding="utf-8"))["nodes"]]
        self.assertEqual(files, ["specs/web/SPEC-001-a.md", "specs/other/X.md"])


@unittest.skipIf(shutil.which("git") is None, "git not available")
class UndoGitTests(base.DomainFixture):
    def test_undo_of_a_git_tracked_domain_archives_and_removes_the_folder(self):
        """Adversarial where: `git mv` of the only tracked file takes the
        now-empty folder with it (or leaves it), so the following `rmdir`
        raises on a tracked domain and the scope text is stranded half
        moved."""
        original = base.index_bytes("network", ["network"])
        self.put("specs/network/index.md", original)
        git(self.project, "init", "-q")
        git(self.project, "add", ".compass")

        code, out, err = self.run_cmd(
            ["--undo", "specs/network", "--apply", "--reason", "scratch"])
        self.assertEqual(code, 0, err)
        self.assertFalse((self.root / "specs" / "network").exists())
        archived = self.root / "archive" / "domains" / "specs" / "network" / "index.md"
        self.assertEqual(archived.read_bytes(), original)
        tracked = git(self.project, "ls-files", ".compass").split()
        self.assertIn(".compass/archive/domains/specs/network/index.md", tracked)

    def test_undo_collision_suffix_skips_taken_numbers_and_nested_parents(self):
        """Adversarial where: the numbered archive folder is chosen from the
        count of earlier archives instead of probing, so a taken `-2` is
        overwritten; or archiving `specs/a` after `specs/a/b` was archived
        reuses the parent folder that already holds `b`."""
        self.put("archive/domains/specs/network/index.md", b"first")
        self.put("archive/domains/specs/network-3/index.md", b"third")
        original = base.index_bytes("network", ["network"], b"## Scope\n\nSECOND.\n")
        self.put("specs/network/index.md", original)
        code, _, err = self.run_cmd(
            ["--undo", "specs/network", "--apply", "--reason", "s"])
        self.assertEqual(code, 0, err)
        landed = self.root / "archive" / "domains" / "specs" / "network-2" / "index.md"
        self.assertEqual(landed.read_bytes(), original)
        self.assertEqual(
            (self.root / "archive" / "domains" / "specs" / "network-3" / "index.md").read_bytes(),
            b"third")

        self.put("archive/domains/specs/a/b/index.md", b"nested")
        inner = base.index_bytes("a", ["a"], b"## Scope\n\nOUTER.\n")
        self.put("specs/a/index.md", inner)
        code, _, err = self.run_cmd(["--undo", "specs/a", "--apply", "--reason", "s"])
        self.assertEqual(code, 0, err)
        self.assertEqual(
            (self.root / "archive" / "domains" / "specs" / "a" / "b" / "index.md").read_bytes(),
            b"nested")
        self.assertEqual(
            (self.root / "archive" / "domains" / "specs" / "a-2" / "index.md").read_bytes(),
            inner)


class TitleEdgeTests(base.DomainFixture):
    def test_title_rejects_blank_and_multiline_and_non_create_modes(self):
        """Adversarial where: a blank or multi-line `--title` writes an
        empty/`\\n`-broken frontmatter value, or `--title` combined with
        `--undo`/`--rename` is silently ignored instead of refused."""
        self.put("specs/network/index.md", base.index_bytes("network", ["network"]))
        before = self.snapshot()
        cases = {
            "blank": ["specs/new", "--apply", "--reason", "r", "--class-here", "c", "--title", "   "],
            "multiline": ["specs/new", "--apply", "--reason", "r", "--class-here", "c",
                          "--title", "a\nb"],
            "carriage return": ["specs/new", "--apply", "--reason", "r", "--class-here", "c",
                                "--title", "a\rb"],
            "with rename": ["--rename", "specs/network", "specs/web", "--apply",
                            "--reason", "r", "--title", "T"],
            "with undo": ["--undo", "specs/network", "--apply", "--reason", "r", "--title", "T"],
            "undo and rename": ["--undo", "--rename", "specs/network", "specs/web"],
        }
        for name, args in cases.items():
            with self.subTest(name=name):
                code, _, _ = self.run_cmd(args)
                self.assertEqual(code, 1)
                self.assertEqual(self.snapshot(), before)

    def test_class_here_with_quotes_parses_back_unchanged(self):
        """Adversarial where: `--class-here` text holding a double quote or
        a backslash is written into `summary:` unescaped, so the new index
        no longer parses."""
        line = 'Class here: "quoted" paths like C:\\temp'
        code, _, err = self.run_cmd(
            ["specs/network", "--apply", "--reason", "r", "--class-here", line])
        self.assertEqual(code, 0, err)
        data, error = vaultlib.parse_frontmatter(self.root / "specs" / "network" / "index.md")
        self.assertIsNone(error)
        self.assertEqual(data.get("summary"), line)

    def test_rename_after_a_custom_title_resets_title_and_heading_to_new_name(self):
        """Adversarial where: a domain created with `--title` holding a
        quote keeps its old heading after rename, because the old title is
        compared with its YAML escapes still in place."""
        title = 'Network "core" routing'
        code, _, err = self.run_cmd(
            ["specs/network", "--apply", "--reason", "r", "--class-here", "c",
             "--title", title])
        self.assertEqual(code, 0, err)
        code, _, err = self.run_cmd(
            ["--rename", "specs/network", "specs/web", "--apply", "--reason", "r"])
        self.assertEqual(code, 0, err)
        text = (self.root / "specs" / "web" / "index.md").read_text(encoding="utf-8")
        self.assertIn("\n# web\n", text)
        self.assertNotIn("core", text.split("## Scope")[0])


if __name__ == "__main__":
    unittest.main()
