"""Edge tests for `compass placement` and the bare-stem resolution in
`compass promote`, covering branches the implementation introduced.

Adversarial themes: a hint token that abbreviates several files; the many
spellings of an artifact path (trailing slash, backslashes, absolute,
`.compass/` prefix, folder `index.md`); artifacts with missing, unterminated
or BOM/CRLF frontmatter; wikilinks inside code or inside a table cell; an
empty vault and a missing vault; domain indexes carrying a hint; several
`Class elsewhere:` lines; a sibling whose stem extends the subject's; console
encodings narrower than the output; promote of a stem inside a unit, a
folder spec's child, and a path that is not a spec.
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402
from tests.test_placement import (  # noqa: E402
    ALMANAC,
    SUBJECT,
    PlacementCase,
    doc,
    domain_doc,
    lines_naming,
    unit_doc,
)
from tests.test_promote_nested import (  # noqa: E402
    NestedPromoteCase,
    domain,
    snapshot,
    spec,
)

CLI_DIR = Path(__file__).resolve().parent.parent


class HintTokenTests(PlacementCase):
    def test_hint_token_matching_several_files_lists_all_and_credits_none(self):
        """Adversarial where: a short id such as `SPEC-029` that abbreviates
        two files is resolved to the first match, so the hint section names
        only one and a candidate is credited "the subject's hint names it"
        for a file the author may not have meant. Also a token that is only a
        character prefix (`SPEC-029` vs `SPEC-0290-...`) must not match."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"], hint="belongs under SPEC-029"))
        self.add("specs/SPEC-029-alpha.md", doc("Alpha", tags=["oceanography"]))
        self.add("specs/net/index.md", domain_doc("net", "routing"))
        self.add("specs/net/SPEC-029-beta.md", doc("Beta", tags=["oceanography"]))
        self.add("specs/SPEC-0290-gamma.md", doc("Gamma", tags=["oceanography"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        hint = out[out.index("hint:"):]
        self.assertIn("specs/SPEC-029-alpha.md", hint)
        self.assertIn("specs/net/SPEC-029-beta.md", hint)
        self.assertNotIn("SPEC-0290-gamma", hint)
        for stem in ("SPEC-029-alpha", "SPEC-029-beta", "SPEC-0290-gamma"):
            with self.subTest(candidate=stem):
                self.assertNotIn("hint names it", lines_naming(
                    [line for line in out.splitlines() if line.strip().startswith("[[")], stem))

    def test_unique_short_id_in_a_hint_credits_the_one_file_it_abbreviates(self):
        """Adversarial where: a unique abbreviation (`SPEC-029` for one
        `SPEC-029-...` file) is dropped because only exact stems are
        compared, so the hint contributes no evidence."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"], hint="belongs under SPEC-029"))
        self.add("specs/SPEC-029-alpha.md", doc("Zebra husbandry", tags=["unrelated"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        row = [line for line in out.splitlines()
               if "[[SPEC-029-alpha]]" in line and "evidence" in line]
        self.assertTrue(row, out)
        self.assertIn("hint names it", row[0])


class WeakEvidenceTests(PlacementCase):
    def test_one_shared_word_is_dropped_beside_a_stronger_candidate(self):
        """Adversarial where: a candidate whose only evidence is one common
        word ("reading") is listed beside a candidate with a shared tag, and
        the noise ranks as a parent the human must wade through."""
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading", tags=["oceanography"]))
        self.add("specs/SPEC-030-strong.md", doc("Wave heights", tags=["oceanography"]))
        self.add("specs/SPEC-031-weak.md", doc("Palm reading", tags=["unrelated"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        self.assertIn("[[SPEC-030-strong]]", out)
        self.assertNotIn("SPEC-031-weak", out)

    def test_one_shared_word_is_kept_when_nothing_stronger_exists(self):
        """Adversarial where: the weak-evidence filter empties the report for
        a subject whose only signal is a shared word."""
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading"))
        self.add("specs/SPEC-031-weak.md", doc("Palm reading", tags=["unrelated"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        self.assertIn("[[SPEC-031-weak]]", out)


class ResolutionTests(PlacementCase):
    def test_every_spelling_of_one_artifact_path_resolves_to_it(self):
        """Adversarial where: path normalisation handles `specs/X.md` but not
        a folder spec given with a trailing slash, with backslashes (Windows
        tab completion), as its `index.md`, absolute, or with the
        `.compass/` prefix; each would report "not found" for a real file."""
        self.add("specs/SPEC-011-harbor-ops/index.md",
                 doc("Harbor operations", tags=["oceanography"]))
        self.add("specs/SPEC-011-harbor-ops/SPEC-001-child.md",
                 doc("Child", tags=["oceanography"]))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        index_abs = str(self.root / "specs" / "SPEC-011-harbor-ops" / "index.md")
        rows = {
            "stem": "SPEC-011-harbor-ops",
            "folder-path": "specs/SPEC-011-harbor-ops",
            "trailing-slash": "specs/SPEC-011-harbor-ops/",
            "index-md": "specs/SPEC-011-harbor-ops/index.md",
            "backslashes": "specs\\SPEC-011-harbor-ops\\index.md",
            "compass-prefix": ".compass/specs/SPEC-011-harbor-ops/index.md",
            "absolute": index_abs,
        }
        for name, arg in rows.items():
            with self.subTest(spelling=name):
                code, out, err = self.run_placement([arg])
                self.assertEqual(code, 0, err)
                self.assertIn("SPEC-011-harbor-ops", out.splitlines()[0])
                self.assertIn(ALMANAC, out)
                self.assertNotIn("SPEC-001-child", out)

    def test_domain_index_path_is_refused_with_exit_one_and_no_report(self):
        """Adversarial where: a domain folder's `index.md` is a vault record
        but not an artifact; naming it must exit 1 with a message, not
        print a placement report for a topic folder or raise."""
        self.add("specs/net/index.md", domain_doc("net", "routing"))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        for arg in ("specs/net/index.md", "specs/net", "net"):
            with self.subTest(arg=arg):
                code, out, err = self.run_placement([arg])
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn("not found", err)

    def test_output_paths_use_forward_slashes(self):
        """Adversarial where: a Windows `Path` stringified into the report
        prints backslashes, so a hint path or wikilink cannot be pasted
        into the vault."""
        self.add("specs/net/index.md", domain_doc("net", "routing"))
        self.add("specs/net/SPEC-029-beta.md", doc("Beta", tags=["oceanography"]))
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"], hint="see SPEC-029-beta"))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        self.assertNotIn("\\", out)
        self.assertIn("specs/net/SPEC-029-beta.md", out)


class MalformedArtifactTests(PlacementCase):
    def test_malformed_frontmatter_never_aborts_the_report(self):
        """Adversarial where: one artifact among good ones has no
        frontmatter, an unterminated block, a scalar `tags:`, or a BOM and
        CRLF line endings; a parser that raises on the bad file takes the
        whole report down, and one that mis-reads the BOM/scalar silently
        drops its tag evidence."""
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading", tags=["oceanography"]))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        self.add("specs/SPEC-050-nofm.md", "just prose, no frontmatter at all\n")
        self.add("specs/SPEC-051-open.md", "---\ntitle: \"never closed\"\ntags: [oceanography]\n")
        self.add("specs/SPEC-052-scalar.md",
                 "---\ntitle: \"Scalar\"\ntype: spec\ntags: oceanography\n---\n\nbody\n")
        bom_text = doc("Bom doc", tags=["oceanography"]).replace("\n", "\r\n")
        path = self.root / "specs" / "SPEC-053-bom.md"
        path.write_bytes(b"\xef\xbb\xbf" + bom_text.encode("utf-8"))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        self.assertIn(ALMANAC, out)
        for stem in ("SPEC-052-scalar", "SPEC-053-bom"):
            with self.subTest(candidate=stem):
                self.assertIn("shared tag oceanography", lines_naming(
                    [line for line in out.splitlines() if "evidence" in line], stem))
        for stem in ("SPEC-050-nofm", "SPEC-051-open", "SPEC-053-bom"):
            with self.subTest(subject=stem):
                code, out, err = self.run_placement([stem])
                self.assertEqual(code, 0, err)
                self.assertTrue(out.startswith(f"placement: {stem}"), out)

    def test_tags_match_regardless_of_case(self):
        """Adversarial where: tags compared verbatim, so `Oceanography` and
        `oceanography` (folksonomy drift the vault tolerates) share nothing."""
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading", tags=["Oceanography"]))
        self.add(f"specs/{ALMANAC}.md", doc("Zebra husbandry", tags=["oceanography"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        self.assertIn("shared tag oceanography", lines_naming(
            [line for line in out.splitlines() if "evidence" in line], ALMANAC))

    def test_subject_with_a_hint_list_or_blank_hint_still_reports(self):
        """Adversarial where: `taxonomy_hint` written as a block list or as
        a blank string is treated as text of the wrong type and raises, or a
        blank hint counts as pending in `--hints`."""
        self.add(f"specs/{SUBJECT}.md",
                 "---\ntitle: \"Tide\"\ntype: spec\ntags: [a]\ntaxonomy_hint:\n"
                 "  - see SPEC-010\n---\n\nbody\n")
        self.add(f"specs/{ALMANAC}.md", doc("Almanac", tags=["a"], hint=""))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        code, out, err = self.run_placement(["--hints"])
        self.assertEqual(code, 0, err)
        self.assertIn(f"placement: {SUBJECT}", out)
        self.assertNotIn(f"placement: {ALMANAC}", out)


class LinkEvidenceTests(PlacementCase):
    def test_links_in_code_do_not_count_and_links_in_table_cells_do(self):
        """Adversarial where: a wikilink shown as an example in a fenced or
        inline code span is read as a real link and creates evidence, while
        the `[[stem\\|alias]]` form Obsidian requires inside a table cell is
        cut at the backslash and resolves to nothing."""
        body = "\n".join([
            "```", "[[SPEC-020-fenced]]", "```",
            "inline `[[SPEC-021-inline]]` example",
            "| col |", "|---|", "| [[SPEC-022-table\\|Alias]] |",
            "[[SPEC-023-hash#Problem|alias]]",
        ])
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"], body=body))
        titles = {"SPEC-020-fenced": "Zebra husbandry", "SPEC-021-inline": "Quantum ledger",
                  "SPEC-022-table": "Pottery glazing", "SPEC-023-hash": "Falconry basics"}
        for stem, title in titles.items():
            self.add(f"specs/{stem}.md", doc(title, tags=[f"t{stem[-5:].lower()}"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        parents = out[out.index("parents:"):out.index("pairs:")]
        self.assertNotIn("SPEC-020-fenced", parents)
        self.assertNotIn("SPEC-021-inline", parents)
        self.assertIn("SPEC-022-table", parents)
        self.assertIn("SPEC-023-hash", parents)


class ScopeAndDomainTests(PlacementCase):
    def test_each_class_elsewhere_line_of_a_domain_is_honoured(self):
        """Adversarial where: only the first `Class elsewhere:` line of a
        domain's scope is read, so a redirect written on the second line
        never fires."""
        text = domain_doc("seafaring", "harbour approaches",
                          elsewhere="billing invoices -> [[specs/finance/index|finance]]")
        text = text.rstrip("\n") + "\nClass elsewhere: tide charts -> [[specs/maps/index|maps]]\n"
        self.add("specs/seafaring/index.md", text)
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading", tags=["oceanography"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        redirect = [line for line in out.splitlines() if line.startswith("redirect:")]
        self.assertEqual(len(redirect), 1, out)
        self.assertIn("maps", redirect[0])
        self.assertNotIn("finance", out)

    def test_sibling_whose_stem_extends_the_subjects_is_still_a_candidate(self):
        """Adversarial where: descendants of a folder-spec subject are
        excluded by a string-prefix test, so a sibling named
        `<subject-stem>-extras` is dropped along with the real children."""
        self.add(f"specs/{SUBJECT}/index.md", doc("Tide chart reading", tags=["oceanography"]))
        self.add(f"specs/{SUBJECT}/SPEC-001-kid.md", doc("Kid", tags=["oceanography"]))
        self.add(f"specs/{SUBJECT}-extras.md", doc("Extras", tags=["oceanography"]))
        code, out, err = self.run_placement([SUBJECT])
        self.assertEqual(code, 0, err)
        self.assertIn(f"{SUBJECT}-extras", out)
        self.assertNotIn("SPEC-001-kid", out)

    def test_hints_flag_lists_artifacts_only_never_domain_indexes(self):
        """Adversarial where: `--hints` walks every scanned record, so a
        domain `index.md` that carries a `taxonomy_hint` is reported as an
        artifact with a pending hint."""
        text = domain_doc("seafaring", "harbour approaches").replace(
            "type: domain", 'type: domain\ntaxonomy_hint: "see SPEC-010"')
        self.add("specs/seafaring/index.md", text)
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["x"]))
        code, out, err = self.run_placement(["--hints"])
        self.assertEqual(code, 0, err)
        self.assertIn("0 artifact(s)", out)
        self.assertNotIn("placement: seafaring", out)


class EmptyAndMissingVaultTests(PlacementCase):
    def test_empty_vault_reports_nothing_pending_and_unknown_stem_exits_one(self):
        """Adversarial where: a vault with no artifacts (type dirs present,
        or no type dirs at all) crashes the scan or `--hints`, instead of
        exit 0 with a zero count and exit 1 for an unknown name."""
        import shutil
        for variant in ("empty-type-dirs", "no-type-dirs"):
            with self.subTest(vault=variant):
                if variant == "no-type-dirs":
                    for child in list(self.root.iterdir()):
                        if child.name != "meta":
                            shutil.rmtree(child)
                code, out, err = self.run_placement(["--hints"])
                self.assertEqual(code, 0, err)
                self.assertIn("0 artifact(s)", out)
                code, out, err = self.run_placement(["SPEC-001-anything"])
                self.assertEqual(code, 1)
                self.assertEqual(out, "")

    def test_no_vault_at_all_exits_one_through_the_cli(self):
        """Adversarial where: run outside any project, the command lets
        `FileNotFoundError` escape as a traceback or exit 2 instead of the
        one-line exit 1 the contract promises."""
        bare = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(bare, True))
        old_cwd = os.getcwd()
        old_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(bare)
        os.chdir(bare)
        self.addCleanup(os.chdir, old_cwd)
        self.addCleanup(os.environ.__setitem__, "CLAUDE_PROJECT_DIR", old_env or "")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = maincli.main(["placement", "SPEC-001-anything"])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")


class ConsoleEncodingTests(PlacementCase):
    def test_non_ascii_hint_prints_under_a_cp1252_console(self):
        """Adversarial where: the report echoes the author's hint verbatim;
        a hint holding a character cp1252 lacks (an arrow, CJK) raises
        `UnicodeEncodeError` on a Windows console and the report is lost."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"],
            hint="mover para SPEC-010 → maré 潮"))
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project),
                   PYTHONIOENCODING="cp1252")
        result = subprocess.run(
            [sys.executable, str(CLI_DIR / "maincli.py"), "placement", SUBJECT],
            capture_output=True, env=env, cwd=str(self.project))
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertIn(b"own: mover para SPEC-010", result.stdout)


def run_promote(args):
    """Run promote through its module, mapping an escaping exception to exit 1
    the way the dispatcher does."""
    from commands import promote
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = promote.run(args)
        except Exception as exc:  # noqa: BLE001
            err.write(f"raised: {exc!r}")
            code = 1
    return code, out.getvalue(), err.getvalue()


class PromoteEdgeTests(NestedPromoteCase):
    def test_stem_inside_a_unit_promotes_beside_the_file_with_posix_output(self):
        """Adversarial where: stem resolution scans only the root type dirs,
        so a spec inside a unit is "not found"; or the printed move uses
        backslashes on Windows."""
        self.add("orbit-lab/index.md",
                 '---\ntitle: "orbit-lab"\ntype: unit\nstatus: active\n'
                 "created: 2026-08-30\nupdated: 2026-08-30\n---\n\nunit\n")
        self.add("orbit-lab/specs/SPEC-007-burn.md", spec("Burn"))
        code, out, err = run_promote(["SPEC-007-burn", "--apply", "--reason", "grew"])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "orbit-lab/specs/SPEC-007-burn/index.md").is_file())
        self.assertFalse((self.root / "orbit-lab/specs/SPEC-007-burn.md").exists())
        self.assertIn("orbit-lab/specs/SPEC-007-burn.md -> "
                      "orbit-lab/specs/SPEC-007-burn/index.md", out)
        self.assertNotIn("\\", out)

    def test_same_stem_at_root_and_in_a_unit_is_refused_untouched(self):
        """Adversarial where: numbering is local per unit so `SPEC-008-dup`
        exists at the root and in a unit; the first scan hit is promoted
        instead of the pair refused."""
        self.add("orbit-lab/index.md",
                 '---\ntitle: "orbit-lab"\ntype: unit\nstatus: active\n'
                 "created: 2026-08-30\nupdated: 2026-08-30\n---\n\nunit\n")
        self.add("specs/SPEC-008-dup.md", spec("Dup root"))
        self.add("orbit-lab/specs/SPEC-008-dup.md", spec("Dup unit"))
        before = snapshot(self.root)
        code, _, err = run_promote(["SPEC-008-dup", "--apply", "--reason", "r"])
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", err)
        self.assertIn("orbit-lab/specs/SPEC-008-dup.md", err)
        self.assertEqual(snapshot(self.root), before)

    def test_child_of_a_folder_spec_promotes_and_a_folder_spec_stem_does_not(self):
        """Adversarial where: the `child` kind is dropped from stem
        resolution so a folder spec's flat child cannot be promoted, or the
        folder spec's own stem is accepted and its index moved."""
        self.add("specs/SPEC-002-tile/index.md", spec("Tile"))
        self.add("specs/SPEC-002-tile/SPEC-001-brush.md", spec("Brush"))
        before = snapshot(self.root)
        code, _, _ = run_promote(["SPEC-002-tile", "--apply", "--reason", "r"])
        self.assertEqual(code, 1)
        self.assertEqual(snapshot(self.root), before)
        code, _, err = run_promote(["SPEC-001-brush", "--apply", "--reason", "r"])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "specs/SPEC-002-tile/SPEC-001-brush/index.md").is_file())

    def test_existing_folder_index_is_never_overwritten_by_a_promote(self):
        """Adversarial where: a stale `SPEC-003-routing/index.md` already
        sits beside the flat `SPEC-003-routing.md`; `rename` overwrites it on
        POSIX, destroying a spec."""
        self.add("specs/SPEC-003-routing.md", spec("Flat routing"))
        self.add("specs/SPEC-003-routing/index.md", spec("Existing folder routing"))
        before = snapshot(self.root)
        code, _, _ = run_promote(["SPEC-003-routing", "--apply", "--reason", "r"])
        self.assertEqual(code, 1)
        self.assertEqual(snapshot(self.root), before)

    def test_a_path_that_is_not_a_spec_is_refused(self):
        """Adversarial where: the path branch accepts any existing file, so
        `active.md`, a meta file, or a file outside the vault is moved into
        a folder as if it were a flat spec."""
        self.add("active.md", "# Active\n")
        self.add("meta/notes.md", "notes\n")
        outside = self.project / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        for arg in ("active.md", "meta/notes.md", "../outside.md"):
            with self.subTest(path=arg):
                before = snapshot(self.project)
                code, _, _ = run_promote([arg, "--apply", "--reason", "r"])
                self.assertEqual(code, 1)
                self.assertEqual(snapshot(self.project), before)


if __name__ == "__main__":
    unittest.main()
