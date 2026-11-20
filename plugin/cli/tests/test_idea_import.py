"""Tests for `compass idea import <file>`.

Adversarial themes: a hand-made table is read the way a person wrote it (CRLF
or mixed line endings, a byte-order mark, accented Portuguese, escaped pipes,
quotes inside quotes, a separator row with alignment colons, prose between a
heading and its table); each `## ` heading becomes a category folder, an empty
section included, and an existing folder is left byte for byte alone; a row
with other than four cells is skipped and reported; his words are copied
exactly and never altered beyond one surrounding pair of straight quotes; a
number taken by another idea is remapped, never overwritten; the status maps
`decided` to `adopted` and anything outside the six to `exploring` while the
cell text survives; dry-run is the default and writes nothing; a second
`--apply` writes nothing; every file the importer writes is LF.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402

CLI = Path(__file__).resolve().parents[1] / "compass"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "idea_backfill" / "backfill_table.md"

DOMAIN_INDEX = (
    "---\ntitle: Puzzles\ntype: domain\nstatus: active\ntags: [puzzles]\n---\n\n"
    "## Scope\n\nClass here: locks, keys and riddles (hand-written scope text)\n"
)

MAP = "what if the map remembers where you died, like a scar on the ground"
TIDES = "tides that pull the player toward the shore | and away from it"
MOON = "wait... what if the moon is a door..."
RAIN = "rain that stains cloth until it dries"
ACCENTS = "só um mapa onde o chão guarda cicatrizes, ação e coração"
SMITH = "a mute blacksmith who forges only at night"
SECOND = "a second idea that reuses the number"
SAID = 'he said "go" and left'
OPENING = '"only an opening quote'
CURLY = "“curly quotes stay”"
WHISTLE = "the player may whistle to call a heron"
LAMP = "a lamp that follows you"
KEYS = "an unrelated puzzle about keys"
COMPOUND = "spec approved, research running"

# words -> expected record. `number` is None when the table number cannot be
# kept (taken by another idea) and the importer must pick another free one.
# `raw` is None where the plan leaves raw_status open (a case-only difference).
EXPECTED = {
    MAP: dict(number=7, category="world-building", status="adopted", raw="",
              led={"SPEC-004-world-memory"},
              note="[[SPEC-004-world-memory]] scars fade after a day", cell="adopted"),
    TIDES: dict(number=2, category="world-building", status="parked", raw=None,
                led=set(), note="", cell="Parked"),
    MOON: dict(number=12, category="world-building", status="adopted", raw="decided",
               led={"SPEC-006-combat"}, note="[[SPEC-006-combat|combat rules]]",
               cell="decided"),
    RAIN: dict(number=5, category="world-building", status="done", raw="",
               led=set(), note="[[SPEC-999-never-written]]", cell="done"),
    ACCENTS: dict(number=1, category="world-building", status="new", raw="",
                  led=set(), note="", cell="new"),
    SMITH: dict(number=3, category="characters", status="exploring", raw=COMPOUND,
                led={"SPEC-004-world-memory"},
                note="[[SPEC-004-world-memory]] and [[SPEC-009-twin]]", cell=COMPOUND),
    SECOND: dict(number=None, category="characters", status="dropped", raw="",
                 led=set(), note="see the sketchbook, page 4", cell="dropped"),
    SAID: dict(number=15, category="characters", status="new", raw="",
               led=set(), note="", cell="new"),
    OPENING: dict(number=16, category="characters", status="new", raw="",
                  led=set(), note="", cell="new"),
    CURLY: dict(number=17, category="characters", status="new", raw="",
                led=set(), note="", cell="new"),
    WHISTLE: dict(number=None, category="puzzles", status="exploring", raw="someday",
                  led=set(), note="", cell="someday"),
}
NEW_IDEA_COUNT = len(EXPECTED)


def idea_text(number, words, status="new"):
    """A hand-made idea file in the documented record shape."""
    quote = vaultlib.yaml_double_quote
    return (
        "---\n"
        f"title: {quote(f'IDEA-{number:03d}: {words[:40]}')}\n"
        "type: idea\n"
        f"status: {status}\n"
        f"words: {quote(words)}\n"
        "led_to: []\n"
        'led_to_note: ""\n'
        'raw_status: ""\n'
        'source: "made up"\n'
        "tags: [idea]\n"
        "created: 2026-01-02\n"
        "updated: 2026-01-02\n"
        "---\n\n"
        f"> {words}\n\n"
        "## History\n\n"
        f"- 2026-01-02: {status} (filed)\n"
    )


def doc_text(doc_type, title):
    return (f'---\ntitle: "{title}"\ntype: {doc_type}\nstatus: approved\n'
            "tags: [sample]\n---\n\nbody\n")


class ImportVault(unittest.TestCase):
    def setUp(self):
        self.new_vault()

    def new_vault(self):
        """Build a fresh temporary vault: one existing category with a scope
        text and two ideas, four linkable documents (two share one stem)."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        puzzles = self.root / "ideas" / "puzzles"
        puzzles.mkdir(parents=True)
        (puzzles / "index.md").write_text(DOMAIN_INDEX, encoding="utf-8", newline="\n")
        (puzzles / "IDEA-050-a-lamp-that-follows.md").write_bytes(
            idea_text(50, LAMP, "parked").encode("utf-8"))
        (puzzles / "IDEA-021-an-unrelated-puzzle-about.md").write_bytes(
            idea_text(21, KEYS).encode("utf-8"))
        for rel, doc_type, title in (
            ("specs/SPEC-004-world-memory.md", "spec", "World memory"),
            ("specs/SPEC-006-combat.md", "spec", "Combat"),
            ("specs/learning/SPEC-009-twin.md", "spec", "Twin one"),
            ("specs/world/SPEC-009-twin.md", "spec", "Twin two"),
        ):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(doc_text(doc_type, title), encoding="utf-8", newline="\n")
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def idea(self, args):
        from commands import idea
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = idea.run(args)
        return code, out.getvalue(), err.getvalue()

    def run_import(self, path=FIXTURE, apply=False):
        args = ["import", str(path)] + (["--apply"] if apply else [])
        return self.idea(args)

    def snapshot(self):
        state = {}
        for path in self.root.rglob("*"):
            rel = path.relative_to(self.root).as_posix()
            if rel == "meta/usage.yaml":
                continue
            state[rel] = path.read_bytes() if path.is_file() else None
        return state

    def idea_files(self):
        return sorted((self.root / "ideas").rglob("IDEA-*.md"))

    def number_of(self, path):
        return int(re.match(r"IDEA-(\d+)-", path.name).group(1))

    def imported(self):
        """The files the importer wrote, keyed by his words: (path, vault
        reader frontmatter, text). Ideas the vault held beforehand are left
        out."""
        found = {}
        for path in self.idea_files():
            data, error = vaultlib.parse_frontmatter(path)
            self.assertIsNone(error, path)
            if data["words"] in (LAMP, KEYS):
                continue
            self.assertNotIn(data["words"], found, "the same words filed twice")
            found[data["words"]] = (path, data, path.read_bytes().decode("utf-8"))
        return found

    def apply_fixture(self):
        code, out, err = self.run_import(apply=True)
        self.assertEqual(code, 0, out + err)
        return out, self.imported()

    def led_stems(self, data):
        return {re.match(r"\[\[([^\]|#]+)", entry).group(1) for entry in data["led_to"]}


class ParsesTheTableTests(ImportVault):
    def test_each_heading_becomes_a_category_folder_and_existing_ones_stay_untouched(self):
        """Adversarial where: a section with no table (an empty `## Audio`)
        creates no folder, a heading with a space or capital becomes a folder
        spelled differently from its lower-case hyphen slug, the created
        index does not carry the heading text as its title, or the existing
        `puzzles` category is recreated or has its scope text rewritten."""
        scope_before = (self.root / "ideas" / "puzzles" / "index.md").read_bytes()
        self.apply_fixture()
        cases = [("world-building", "World Building"), ("characters", "Characters"),
                 ("audio", "Audio")]
        for slug, title in cases:
            with self.subTest(slug):
                index = self.root / "ideas" / slug / "index.md"
                self.assertTrue(index.is_file(), sorted(self.snapshot()))
                data, error = vaultlib.parse_frontmatter(index)
                self.assertIsNone(error)
                self.assertEqual(data["title"], title)
                self.assertEqual(data["type"], "domain")
        self.assertEqual((self.root / "ideas" / "puzzles" / "index.md").read_bytes(),
                         scope_before)
        categories = sorted(p.name for p in (self.root / "ideas").iterdir() if p.is_dir())
        self.assertEqual(categories, ["audio", "characters", "puzzles", "world-building"])

    def test_rows_with_other_than_four_cells_are_skipped_and_reported(self):
        """Adversarial where: a five-cell row (an unescaped pipe in a cell) or
        a three-cell row is shifted into the columns and filed with the
        wrong words or status, silently dropped without a report, or the one
        bad row aborts the rows around it; the neighbours of each bad row
        must still import."""
        out, found = self.apply_fixture()
        self.assertNotIn("five cells in this row", found)
        self.assertNotIn("only three cells", found)
        self.assertNotIn("extra", [d["words"] for _, d, _ in found.values()])
        self.assertEqual(len(found), NEW_IDEA_COUNT)
        self.assertIn("skipped", out.lower())
        fixture_lines = FIXTURE.read_text(encoding="utf-8").splitlines()
        for marker in ("five cells in this row", "only three cells"):
            with self.subTest(marker):
                line_no = 1 + next(i for i, line in enumerate(fixture_lines) if marker in line)
                self.assertTrue(
                    marker in out or f"line {line_no}" in out or f":{line_no}" in out,
                    f"skipped row not identified in report: {out}")

    def test_words_are_copied_exactly_with_one_outer_straight_quote_pair_removed(self):
        """Adversarial where: the words column is altered beyond one surrounding
        pair of straight double quotes: inner quotes stripped, an opening
        quote alone removed, curly quotes straightened, accents mangled by a
        non-UTF-8 read, `\\|` left escaped, the `...` inside quotes cut,
        or cell padding kept; every imported `words` must equal the cell's
        inner text byte for byte through both YAML readers."""
        _, found = self.apply_fixture()
        self.assertEqual(set(found), set(EXPECTED))
        for words, (path, data, text) in found.items():
            with self.subTest(words):
                front = text.split("\n---\n", 1)[0].removeprefix("---\n")
                self.assertEqual(data["words"], words)
                self.assertEqual(yaml.safe_load(front)["words"], words)
                self.assertIn("> " + words, text.split("## History")[0])

    def test_files_are_named_from_the_number_and_the_first_five_words(self):
        """Adversarial where: the importer names the file by row position or
        slugs more or fewer than five words, so `compass idea find` and
        sync see a different name from `compass idea add`."""
        _, found = self.apply_fixture()
        self.assertEqual(found[MAP][0].name, "IDEA-007-what-if-the-map-remembers.md")
        self.assertEqual(found[TIDES][0].name, "IDEA-002-tides-that-pull-the-player.md")


class NumbersAndStatusTests(ImportVault):
    def test_table_number_is_kept_when_free_and_remapped_when_taken(self):
        """Adversarial where: a table number that another idea already holds
        (IDEA-021 in the vault, a second `3` inside the file) overwrites that
        idea or is filed twice under one number; two remaps in one import get
        the same replacement; a free out-of-order number (`7` before `2`,
        `1` last) is renumbered by row position; the remap is not reported."""
        out, found = self.apply_fixture()
        numbers = [self.number_of(path) for path in self.idea_files()]
        self.assertEqual(len(numbers), len(set(numbers)), numbers)
        self.assertEqual(len(numbers), NEW_IDEA_COUNT + 2)
        for words, expected in EXPECTED.items():
            with self.subTest(words):
                number = self.number_of(found[words][0])
                if expected["number"] is not None:
                    self.assertEqual(number, expected["number"])
        self.assertNotEqual(self.number_of(found[SECOND][0]), 3)
        self.assertNotEqual(self.number_of(found[WHISTLE][0]), 21)
        self.assertEqual(self.number_of(found[SMITH][0]), 3)
        self.assertEqual(
            vaultlib.parse_frontmatter(
                self.root / "ideas" / "puzzles" / "IDEA-021-an-unrelated-puzzle-about.md")[0]["words"],
            KEYS)
        self.assertIn("remap", out.lower())

    def test_status_maps_decided_to_adopted_and_anything_else_to_exploring(self):
        """Adversarial where: `decided` stays as written, a compound cell
        (`spec approved, research running`) or an unknown word (`someday`)
        is dropped, kept as the status, or matched by its first word; a
        capitalised known value (`Parked`) is treated as unknown; the cell
        text is lost instead of kept in `raw_status`."""
        _, found = self.apply_fixture()
        for words, expected in EXPECTED.items():
            with self.subTest(words):
                data = found[words][1]
                self.assertEqual(data["status"], expected["status"])
                if expected["raw"] is not None:
                    self.assertEqual(data["raw_status"], expected["raw"])
                self.assertEqual(found[words][0].parent.name, expected["category"])

    def test_every_row_with_a_non_matching_status_is_reported(self):
        """Adversarial where: the report lists only unknown words and leaves
        out the `decided` rewrite, or lists only the first non-matching row;
        the cell text must appear so he can review each one."""
        out, _ = self.apply_fixture()
        for cell in ("decided", "someday", COMPOUND):
            with self.subTest(cell):
                self.assertIn(cell, out)


class LedToTests(ImportVault):
    def test_links_that_resolve_go_to_led_to_and_the_whole_cell_is_the_note(self):
        """Adversarial where: a link followed by text loses its link or the
        text, a `[[doc\\|alias]]` cell is not unescaped before its target is
        looked up, a broken link or one naming two documents (`SPEC-009-twin`
        exists twice) is written to `led_to` anyway, a plain-text cell
        produces a link, or the note is the stripped link rather than the
        whole unescaped cell; broken and ambiguous links are reported."""
        out, found = self.apply_fixture()
        for words, expected in EXPECTED.items():
            with self.subTest(words):
                data = found[words][1]
                self.assertEqual(self.led_stems(data), expected["led"])
                self.assertEqual(data["led_to_note"], expected["note"])
        for reported in ("SPEC-999-never-written", "SPEC-009-twin"):
            with self.subTest(reported):
                self.assertIn(reported, out)


class HistoryTests(ImportVault):
    def test_history_line_records_the_status_and_the_cell_as_written(self):
        """Adversarial where: the history line shows the mapped status where
        the cell said something else, drops the `imported; status as
        written` clause, or normalises the cell (`Parked` to `parked`); a
        file gets more than one history line."""
        _, found = self.apply_fixture()
        for words, expected in EXPECTED.items():
            with self.subTest(words):
                text = found[words][2]
                history = text.split("## History", 1)[1]
                lines = [line for line in history.splitlines() if line.startswith("- ")]
                self.assertEqual(len(lines), 1, history)
                pattern = (r"- \d{4}-\d{2}-\d{2}: %s \(imported; status as written: \"%s\"\)"
                           % (re.escape(expected["status"]), re.escape(expected["cell"])))
                self.assertRegex(lines[0], "^" + pattern + "$")


class RepeatTests(ImportVault):
    def test_words_already_filed_are_reported_present_and_a_second_apply_writes_nothing(self):
        """Adversarial where: a row whose words an existing idea holds
        (`a lamp that follows you` is IDEA-050) is filed again, a row
        repeating the words of an earlier row in the same file is filed
        twice, or a second `--apply` of the whole file renumbers, rewrites or
        adds anything; the vault must be byte for byte as after the first
        apply."""
        out, found = self.apply_fixture()
        self.assertIn("present", out.lower())
        self.assertIn("IDEA-050", out)
        lamp_files = [p for p in self.idea_files() if p.name.startswith("IDEA-050-")]
        self.assertEqual(len(lamp_files), 1)
        tides = [p for p in self.idea_files()
                 if vaultlib.parse_frontmatter(p)[0]["words"] == TIDES]
        self.assertEqual(len(tides), 1)
        after_first = self.snapshot()
        code, out, err = self.run_import(apply=True)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), after_first)


class DryRunTests(ImportVault):
    def test_dry_run_is_the_default_writes_nothing_and_prints_each_row_and_the_report(self):
        """Adversarial where: import without `--apply` creates a category
        folder (the empty one included) or a file; a row line is missing its
        id, category or status, or prints more than the first 60 characters
        of the words; the report leaves out categories to create, remaps,
        broken links, skipped rows or already-present rows; the ids a
        dry-run prints differ from the ids `--apply` then writes."""
        before = self.snapshot()
        code, out, err = self.run_import(apply=False)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), before)
        self.assertGreater(len(MAP), 61)
        map_lines = [line for line in out.splitlines() if MAP[:60] in line]
        self.assertEqual(len(map_lines), 1, out)
        map_line = map_lines[0]
        self.assertNotIn(MAP[:61], map_line)
        self.assertIn("IDEA-007", map_line)
        self.assertIn("adopted", map_line)
        self.assertTrue("world-building" in map_line or "World Building" in map_line, map_line)
        lowered = out.lower()
        for keyword in ("create", "remap", "skipped", "present"):
            with self.subTest(keyword):
                self.assertIn(keyword, lowered)
        for category in ("audio", "characters", "world-building"):
            with self.subTest(category):
                self.assertIn(category, lowered)
        self.assertIn("SPEC-999-never-written", out)
        _, found = self.apply_fixture()
        for words, (path, _, _) in found.items():
            with self.subTest(words):
                self.assertIn(f"IDEA-{self.number_of(path):03d}", out)


class FileFormatTests(ImportVault):
    BOM_TABLE = (
        "## Characters\n\n"
        "| # | Her words | Status | Where it led |\n"
        "|---|---|---|---|\n"
        '| 1 | "a lantern that hums" | new | |\n'
    )

    def written_state(self):
        return {rel: data for rel, data in self.snapshot().items()
                if rel.startswith("ideas/") and data is not None}

    def test_line_endings_and_byte_order_mark_do_not_change_the_result_and_files_are_lf(self):
        """Adversarial where: a CRLF or mixed-ending file leaves a trailing
        carriage return in the words, status or note (so a status match
        fails), a byte-order mark before the first
        `## ` heading hides that heading so its category is lost, or the
        importer writes CRLF into the idea or category files; the result of
        every variant must equal the LF import byte for byte."""
        lf_text = FIXTURE.read_bytes().decode("utf-8").replace("\r\n", "\n")
        self.run_import(apply=True)
        baseline = self.written_state()
        mixed = "".join(
            line + ("\r\n" if i % 2 else "\n")
            for i, line in enumerate(lf_text.split("\n")[:-1])) + "\n"
        variants = [
            ("crlf", lf_text.replace("\n", "\r\n").encode("utf-8")),
            ("mixed endings", mixed.encode("utf-8")),
            ("bom and crlf", b"\xef\xbb\xbf" + lf_text.replace("\n", "\r\n").encode("utf-8")),
        ]
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        for name, payload in variants:
            with self.subTest(name):
                self.new_vault()
                source = scratch / f"{name.replace(' ', '-')}.md"
                source.write_bytes(payload)
                code, out, err = self.run_import(source, apply=True)
                self.assertEqual(code, 0, out + err)
                state = self.written_state()
                self.assertEqual(sorted(state), sorted(baseline))
                for rel, data in state.items():
                    self.assertNotIn(b"\r", data, rel)
                    self.assertEqual(data, baseline[rel], rel)
        with self.subTest("bom before the first heading"):
            self.new_vault()
            source = scratch / "bom-first-heading.md"
            source.write_bytes(b"\xef\xbb\xbf" + self.BOM_TABLE.encode("utf-8"))
            code, out, err = self.run_import(source, apply=True)
            self.assertEqual(code, 0, out + err)
            (path,) = [p for p in self.idea_files() if p.parent.name == "characters"]
            self.assertEqual(vaultlib.parse_frontmatter(path)[0]["words"], "a lantern that hums")
            self.assertNotIn(b"\r", path.read_bytes())
            self.assertTrue((self.root / "ideas" / "characters" / "index.md").is_file())


class BadInputTests(ImportVault):
    def test_unreadable_input_fails_cleanly_and_writes_nothing(self):
        """Adversarial where: a missing file, a directory in place of a file,
        or no file argument crashes with a traceback or exits 0 after
        creating a category folder; each must exit non-zero with a message
        and leave the vault byte for byte as it was, even with `--apply`."""
        cases = [
            ("missing file", ["import", str(self.project / "no-such-table.md"), "--apply"]),
            ("a directory", ["import", str(self.project), "--apply"]),
            ("no file argument", ["import", "--apply"]),
        ]
        for name, args in cases:
            with self.subTest(name):
                before = self.snapshot()
                code, out, err = self.idea(args)
                self.assertNotEqual(code, 0)
                self.assertNotIn("Traceback", out + err)
                self.assertTrue((out + err).strip())
                self.assertEqual(self.snapshot(), before)


class CommandWiringTests(ImportVault):
    def test_import_dispatches_through_the_launcher(self):
        """Adversarial where: the `import` subcommand works when called as
        `commands.idea.run` but the launcher cannot load the importer module
        (a missing path entry) or prints the report as bytes the console
        cannot decode (accented words under a legacy code page)."""
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project), PYTHONIOENCODING="utf-8")
        before = self.snapshot()
        proc = subprocess.run(
            [sys.executable, str(CLI), "idea", "import", str(FIXTURE)],
            cwd=self.project, env=env, capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(b"IDEA-007", proc.stdout)
        self.assertIn("só um mapa".encode("utf-8"), proc.stdout)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
