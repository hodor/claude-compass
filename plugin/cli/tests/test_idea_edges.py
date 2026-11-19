"""Edge tests for the idea record that only the written code reveals.

Adversarial themes: the frontmatter reader closes a block on an unindented
`---` line only, for every line ending, trailing blank and byte-order mark a
Windows editor can leave; the prompt log is read as bytes and split on `\\n`
alone, so a large log, a torn tail, invalid UTF-8 and Unicode line separators
inside a prompt never hide or merge rows; `find` ranks ties by idea number and
counts distinct words once; the slug survives punctuation, accents, ligatures
and emoji; a category folder may be a domain with its own `index.md`, possibly
nested, and never a path that leaves `ideas/`; `status` edits hand-written
files in every layout a human uses; numbers stay unique when several `add`
commands run at once.
"""

import difflib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import idealib  # noqa: E402
import vaultlib  # noqa: E402

CLI_DIR = Path(__file__).resolve().parents[1]
CLI = CLI_DIR / "compass"
TODAY = date.today().isoformat()
DOMAIN_INDEX = (
    "---\ntitle: world-building\ntype: domain\nstatus: active\ntags: [world-building]\n---\n\n"
    "## Scope\n\nClass here: worlds and maps\n"
)


def hand_idea(number, words_lines, extra="", history="- 2026-01-02: new (filed)\n", status="new"):
    """An idea file as a person might lay it out, `words_lines` in a `|-` block."""
    block = "\n".join(("  " + line) if line else "" for line in words_lines)
    quote = "\n".join("> " + line for line in words_lines)
    return (
        "---\n"
        f'title: "IDEA-{number:03d}: {words_lines[0][:30]}"\n'
        "type: idea\n"
        f"status: {status}\n"
        f"words: |-\n{block}\n"
        f"{extra}"
        "created: 2026-01-02\n"
        "updated: 2026-01-02\n"
        "---\n\n"
        f"{quote}\n\n"
        "## History\n\n"
        f"{history}"
    )


class IdeaVault(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.tmp = tmp
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        for category in ("world-building", "characters"):
            self.make_category(category)
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def make_category(self, category):
        folder = self.root / "ideas" / category
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "index.md").write_text(DOMAIN_INDEX, encoding="utf-8")
        return folder

    def idea(self, args):
        from commands import idea
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = idea.run(args)
        return code, out.getvalue(), err.getvalue()

    def write_idea(self, category, number, slug, text, raw=None):
        path = self.root / "ideas" / category / f"IDEA-{number:03d}-{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw if raw is not None else text.encode("utf-8"))
        return path

    def idea_files(self):
        return sorted((self.root / "ideas").rglob("IDEA-*.md"))

    def write_log_bytes(self, data):
        path = self.root / "tmp" / "prompt-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def log_row(rid, prompt):
    return json.dumps(
        {"id": rid, "at": "2026-11-19T10:00:00Z", "session_id": rid.split(":")[0],
         "prompt": prompt}, ensure_ascii=False)


class FrontmatterFenceTests(unittest.TestCase):
    def test_the_closing_fence_is_an_unindented_line_in_every_line_ending(self):
        """Adversarial where: the closing-fence search treats an indented
        `---` inside a block scalar (words that hold a `---` line) as the end
        of the frontmatter, truncating the value and dropping every later key;
        or the stricter rule rejects a real fence that carries trailing
        spaces, a tab or a CRLF."""
        block_words = "words: |-\n  before\n  ---\n  after\nstatus: new\n"
        rows = [
            ("indented fence inside a literal block is content",
             f"---\n{block_words}---\nbody\n",
             ({"words": "before\n---\nafter", "status": "new"}, None)),
            ("indented fence inside a folded block is content",
             "---\nsummary: >\n  one\n  ---\n  two\nstatus: new\n---\n",
             ({"summary": "one --- two", "status": "new"}, None)),
            ("CRLF line endings keep the indented fence as content",
             "---\r\n" + block_words.replace("\n", "\r\n") + "---\r\nbody\r\n",
             ({"words": "before\n---\nafter", "status": "new"}, None)),
            ("trailing spaces after the real fence still close it",
             f"---\n{block_words}---   \nbody\n",
             ({"words": "before\n---\nafter", "status": "new"}, None)),
            ("a trailing tab after the real fence still closes it",
             "---\nstatus: new\n---\t\nbody\n", ({"status": "new"}, None)),
            ("block ends on its fence-looking line, the real fence follows",
             "---\nwords: |-\n  a\n  ---\n---\nbody\n", ({"words": "a\n---"}, None)),
            ("an indented fence alone does not close the block",
             "---\nstatus: new\n  ---\nbody\n", ({}, "unterminated frontmatter")),
            ("a tab-indented fence alone does not close the block",
             "---\nstatus: new\n\t---\nbody\n", ({}, "unterminated frontmatter")),
            ("one unparseable line before the fence leaves the rest read",
             "---\n???\nstatus: new\n---\n", ({"status": "new"}, None)),
        ]
        for name, text, (expected, error) in rows:
            with self.subTest(name):
                data, got_error = vaultlib.parse_frontmatter_text(text)
                self.assertEqual(got_error, error)
                for key, value in expected.items():
                    self.assertEqual(data.get(key), value)

    def test_a_file_saved_by_a_windows_editor_reads_with_bom_and_crlf(self):
        """Adversarial where: a hand-edited idea saved with a byte-order mark
        and CRLF endings (Notepad, PowerShell `Out-File`) loses its
        frontmatter or its multi-line words because the fence rule runs
        before the vault reader normalizes the bytes; a status change on it
        must keep the words and leave LF-only bytes."""
        words_lines = ["line one", "---", "line three"]
        text = hand_idea(1, words_lines)
        raw = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        path = tmp / "IDEA-001-x.md"
        path.write_bytes(raw)
        data, error = vaultlib.parse_frontmatter(path)
        self.assertIsNone(error)
        self.assertEqual(data["words"], "\n".join(words_lines))
        self.assertEqual(data["status"], "new")
        loaded = idealib.load(path, tmp)
        self.assertEqual(loaded["words"], "\n".join(words_lines))
        self.assertEqual(loaded["history"], ["- 2026-01-02: new (filed)"])


class PromptLogTests(IdeaVault):
    def test_the_row_is_found_by_exact_id_in_a_large_damaged_log(self):
        """Adversarial where: a lookup over a big log matches an id by
        prefix or by the text `"id": "<id>"` quoted inside another prompt,
        stops at a torn or non-UTF-8 line, splits a row on a Unicode line
        separator inside a prompt (so the tail of a prompt hides the row), or
        returns the wrong row at the first or last position."""
        target = "sess-t:7"
        rows = [log_row("sess-t:1", "first row"), log_row("sess-t:70", "prefix of the target id"),
                log_row("sess-t:8", f'quoted {{"id": "{target}", "prompt": "forged"}}')]
        rows += [log_row(f"filler:{n}", "line\u2028separator and\x85nel " + "x" * 120)
                 for n in range(30000)]
        rows.append(log_row(target, "the real target \u2028 with a separator"))
        data = ("\n".join(rows[:100]).encode("utf-8") + b"\n"
                + b'{"id": "torn:1", "prompt": "cut\xff\xfe in the middle\n'
                + ("\n".join(rows[100:])).encode("utf-8") + b"\n" + b'{"id": "sess-t:7", "pro')
        self.assertGreater(len(data), 4_000_000)
        self.write_log_bytes(data)
        cases = [
            ("exact id past a torn line and invalid bytes", target,
             "the real target \u2028 with a separator"),
            ("first row", "sess-t:1", "first row"),
            ("prefix id is its own row", "sess-t:70", "prefix of the target id"),
            ("an id that only prefixes another is absent", "sess-t:", None),
            ("an id that is only quoted inside a prompt is that quoting row's own id",
             "forged", None),
            ("different case is a different id", "SESS-T:7", None),
        ]
        for name, rid, expected in cases:
            with self.subTest(name):
                self.assertEqual(idealib.prompt_text(self.root, rid), expected)

    def test_add_with_source_reads_words_out_of_a_crlf_log(self):
        """Adversarial where: a log written by a Windows hook with CRLF row
        endings leaves a `\\r` on each JSON line or in the matched prompt, so
        verbatim words from the prompt are refused or the row is not found."""
        words = "o mapa n\u00e3o esquece"
        rows = [log_row("w:1", "intro"), log_row("w:2", f"{words}, nunca")]
        self.write_log_bytes(("\r\n".join(rows) + "\r\n").encode("utf-8"))
        code, out, err = self.idea(
            ["add", "--category", "characters", "--words", words, "--source", "w:2", "--apply"])
        self.assertEqual(code, 0, out + err)
        (path,) = self.idea_files()
        data, error = vaultlib.parse_frontmatter(path)
        self.assertIsNone(error)
        self.assertEqual(data["words"], words)
        self.assertIn("filed from prompt w:2", path.read_text(encoding="utf-8"))


class FindRankingTests(IdeaVault):
    def numbers_printed(self, query):
        code, out, err = self.idea(["find", query])
        self.assertEqual(code, 0, err)
        return [line.split()[0] for line in out.splitlines() if line.startswith("IDEA-")]

    def test_tied_scores_print_in_number_order_and_cut_at_five(self):
        """Adversarial where: ideas sharing the same number of words with the
        query come out in folder-name or file-system order instead of idea
        number order, the cut at five keeps the wrong five, or a number past
        999 sorts before 999 as text."""
        placements = [  # (category, number): category order is the reverse of number order
            ("world-building", 4), ("world-building", 1), ("characters", 7),
            ("characters", 2), ("world-building", 1000), ("characters", 999),
            ("characters", 3),
        ]
        for category, number in placements:
            self.write_idea(category, number, "tie", "", raw=hand_idea(
                number, [f"lantern keeper number {number}"]).encode("utf-8"))
        shown = self.numbers_printed("xylophone zebra")
        self.assertEqual(shown, [], "no shared word at all means no hit")
        shown = self.numbers_printed("lantern flicker")
        self.assertEqual(shown, ["IDEA-001", "IDEA-002", "IDEA-003", "IDEA-004", "IDEA-007"])
        for number in (1, 2, 3, 4, 7):
            for category in ("world-building", "characters"):
                for path in (self.root / "ideas" / category).glob(f"IDEA-{number:03d}-*.md"):
                    path.unlink()
        shown = self.numbers_printed("lantern flicker")
        self.assertEqual(shown, ["IDEA-999", "IDEA-1000"])

    def test_shared_words_are_counted_once_and_only_from_three_characters(self):
        """Adversarial where: a word repeated inside one idea, or two-letter
        words, inflate its score so a worse match outranks a better one; a
        query made only of short words matches everything."""
        self.write_idea("world-building", 1, "rep", "", raw=hand_idea(
            1, ["fire fire fire fire fire fire"]).encode("utf-8"))
        self.write_idea("world-building", 2, "two", "", raw=hand_idea(
            2, ["fire and smoke together"]).encode("utf-8"))
        self.write_idea("world-building", 3, "short", "", raw=hand_idea(
            3, ["it is on to be or no"]).encode("utf-8"))
        self.assertEqual(self.numbers_printed("fire smoke ash"), ["IDEA-002", "IDEA-001"])
        self.assertEqual(self.numbers_printed("to no it"), [])

    def test_substring_hits_are_all_printed_in_number_order(self):
        """Adversarial where: the five-hit cap of the word-overlap fallback
        leaks into the substring path, hiding the sixth and later ideas that
        hold the exact text."""
        for number in (6, 5, 4, 3, 2, 1, 7):
            self.write_idea("characters", number, "s", "", raw=hand_idea(
                number, [f"a Wandering Merchant {number}"]).encode("utf-8"))
        self.assertEqual(
            self.numbers_printed("wandering MERCHANT"),
            [f"IDEA-{n:03d}" for n in range(1, 8)])


class SlugTests(IdeaVault):
    def test_the_file_name_slug_survives_punctuation_accents_ligatures_and_emoji(self):
        """Adversarial where: the slug keeps a character a file name cannot
        carry, leaves a leading, trailing or doubled hyphen, gives words that
        reduce to nothing an empty name (`IDEA-001-.md`), exceeds sixty
        characters, or counts a sixth word."""
        cases = [
            ("accents fold", "Caf\u00e9 r\u00e9sum\u00e9 na\u00efve", "cafe-resume-naive"),
            ("punctuation drops", "Hello, World! (again)", "hello-world-again"),
            ("underscores and plus signs separate", "snake_case_word C++ and C#", "snake-case-word-c-and-c"),
            ("leading dash", "-rf flag now", "rf-flag-now"),
            ("ligature expands", "\ufb01ne map", "fine-map"),
            ("dotted capital I folds", "\u0130stanbul nights", "istanbul-nights"),
            ("emoji token vanishes", "mapa \U0001F525 lembra", "mapa-lembra"),
            ("only emoji", "\U0001F525\U0001F525\U0001F525", "idea"),
            ("only punctuation", "!!! ??? ---", "idea"),
            ("only CJK", "\u65e5\u672c\u8a9e \u306e\u30c6\u30b9\u30c8", "idea"),
            ("six words keep five", "one two three four five six", "one-two-three-four-five"),
            ("sixty characters kept whole", "a" * 60, "a" * 60),
            ("sixty-one characters cut", "a" * 61, "a" * 60),
            ("cut that lands on a hyphen drops it", "a" * 59 + " bbb", "a" * 59),
        ]
        for name, words, expected in cases:
            with self.subTest(name):
                for path in self.idea_files():
                    path.unlink()
                code, out, err = self.idea(
                    ["add", "--category", "characters", "--words", words, "--apply"])
                self.assertEqual(code, 0, out + err)
                (path,) = self.idea_files()
                self.assertEqual(path.name, f"IDEA-001-{expected}.md")
                self.assertEqual(idealib.load(path, self.root / "ideas")["words"], words)


class CategoryFolderTests(IdeaVault):
    def test_a_category_may_be_a_domain_with_an_index_and_nest_below_one(self):
        """Adversarial where: the domain's `index.md` is read as an idea or
        shifts the numbering, a nested domain loses its path in the loaded
        category or tags the idea with the whole path, a loose idea directly
        under `ideas/` is missed by the numbering, or a trailing slash puts
        the file outside the folder."""
        self.make_category("world-building/maps")
        (self.root / "ideas" / "index.md").write_text(DOMAIN_INDEX, encoding="utf-8")
        self.write_idea(".", 9, "loose", hand_idea(9, ["a loose idea"]))
        code, out, err = self.idea(
            ["add", "--category", "world-building/maps/", "--words", "river of names", "--apply"])
        self.assertEqual(code, 0, out + err)
        path = self.root / "ideas" / "world-building" / "maps" / "IDEA-010-river-of-names.md"
        self.assertTrue(path.is_file(), [p.name for p in self.idea_files()])
        text = path.read_text(encoding="utf-8")
        self.assertIn("tags: [idea, maps]", text.split("\n"))
        data = idealib.load_all(self.root)
        self.assertEqual([i["number"] for i in data], [9, 10])
        self.assertEqual([i["category"] for i in data], ["", "world-building/maps"])
        code, out, err = self.idea(["find", "IDEA-010"])
        self.assertEqual(code, 0, err)
        self.assertIn("IDEA-010  world-building/maps  new", out)

    def test_a_category_that_leaves_ideas_or_is_not_a_folder_name_is_refused_with_nothing_made(self):
        """Adversarial where: a category such as `..`, a doubled slash, a
        backslash path or a name with a space is accepted, so a file lands
        outside `ideas/` or a folder is created implicitly."""
        before = sorted(p.relative_to(self.project).as_posix() for p in self.project.rglob("*"))
        for category in ("..", "../characters", "characters/../world-building",
                         "characters//x", "world building", "characters\\x", ".hidden",
                         "-lead", "", "/"):
            with self.subTest(repr(category)):
                code, out, err = self.idea(
                    ["add", "--category", category, "--words", "escape attempt", "--apply"])
                self.assertEqual(code, 1, out)
                self.assertTrue(err.startswith("compass idea:"), err)
        after = sorted(p.relative_to(self.project).as_posix() for p in self.project.rglob("*"))
        self.assertEqual(before, after)

    def test_numbers_past_999_keep_counting_and_resolve_by_id(self):
        """Adversarial where: the highest number is found by text order so
        IDEA-999 outranks IDEA-1000, the three-digit label truncates the
        fourth digit, or `find` and `status` cannot resolve a four-digit id."""
        self.write_idea("characters", 999, "old", hand_idea(999, ["the old one"]))
        code, out, err = self.idea(
            ["add", "--category", "characters", "--words", "the new one", "--apply"])
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.root / "ideas" / "characters" / "IDEA-1000-the-new-one.md").is_file())
        code, out, err = self.idea(["add", "--category", "characters", "--words", "and another", "--apply"])
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.root / "ideas" / "characters" / "IDEA-1001-and-another.md").is_file())
        code, out, err = self.idea(["status", "IDEA-1000", "parked", "--apply"])
        self.assertEqual(code, 0, out + err)
        code, out, err = self.idea(["find", "idea-1000"])
        self.assertIn("IDEA-1000  characters  parked", out)


class StatusLayoutTests(IdeaVault):
    def run_status(self, text, args, name="x"):
        path = self.write_idea("characters", 1, name, "", raw=text.encode("utf-8"))
        code, out, err = self.idea(["status", "IDEA-001", *args, "--apply"])
        self.assertEqual(code, 0, out + err)
        return path, path.read_text(encoding="utf-8")

    def changed(self, before, after):
        return [line for line in difflib.unified_diff(
            before.split("\n"), after.split("\n"), lineterm="", n=0)
            if line[:1] in "+-" and line[:3] not in ("+++", "---")]

    def test_status_edits_only_owned_lines_in_each_hand_written_layout(self):
        """Adversarial where: a hand-written file laid out differently from
        the one `add` writes (a block-list `led_to`, a later `## Notes`
        section, an empty History, no History, no `led_to` or `status` key,
        words that quote property names and a `---` line) has a neighbour
        line eaten, the history line appended in the wrong section, or the
        words block rewritten."""
        trap = ["status: dropped", "updated: 1999-01-01", "led_to: []", "---", "## History"]
        block_list = hand_idea(
            1, ["a map"], extra='led_to:\n- "[[SPEC-1-a]]"\n- "[[SPEC-2-b]]"\nsource: "me"\n')
        layouts = [
            ("words that quote property names are left alone",
             hand_idea(1, trap), ["parked"]),
            ("a later section after History keeps the entry above it",
             hand_idea(1, ["a map"]) + "\n## Notes\n\nhuman note\n", ["parked"]),
            ("empty History gains the entry",
             hand_idea(1, ["a map"], history=""), ["parked"]),
            ("no History section at all gains one at the end",
             hand_idea(1, ["a map"]).split("## History")[0].rstrip("\n") + "\n", ["parked"]),
            ("missing led_to key is added on --led-to",
             hand_idea(1, ["a map"]), ["parked", "--led-to", "[[PLAN-3-c]]"]),
            ("missing status key is added",
             hand_idea(1, ["a map"]).replace("status: new\n", ""), ["parked"]),
            ("unindented block-list led_to is replaced whole",
             block_list, ["parked", "--led-to", "[[PLAN-3-c]]"]),
            ("a link already present leaves led_to untouched",
             hand_idea(1, ["a map"], extra='led_to: ["[[SPEC-1-a]]"]\n'),
             ["parked", "--led-to", "[[SPEC-1-a]]"]),
        ]
        for name, text, args in layouts:
            with self.subTest(name):
                for path in self.idea_files():
                    path.unlink()
                path, after = self.run_status(text, args)
                data, error = vaultlib.parse_frontmatter_text(after)
                self.assertIsNone(error)
                before = vaultlib.parse_frontmatter_text(text)[0]
                self.assertEqual(data["words"], before["words"])
                self.assertEqual(data["status"], args[0])
                self.assertEqual(
                    yaml.safe_load(after.split("\n---\n")[0][4:])["words"], before["words"])
                changes = self.changed(text, after)
                removed = [c[1:] for c in changes if c[0] == "-"]
                added = [c[1:] for c in changes if c[0] == "+"]
                for line in removed:
                    self.assertTrue(
                        line.startswith(("status:", "updated:", "led_to:", '- "[[')),
                        f"{name}: removed an unowned line {line!r}")
                for line in added:
                    self.assertTrue(
                        line == "" or line.startswith(
                            ("status:", "updated:", "led_to:", "## History", f"- {TODAY}:")),
                        f"{name}: added an unowned line {line!r}")
                self.assertEqual(
                    len([line for line in added if line.startswith(f"- {TODAY}:")]), 1, added)
                self.assertEqual(after.splitlines().count("## History"), 1)
                self.assertNotIn("\r", after)
                lines = after.split("\n")
                entry = max(i for i, line in enumerate(lines) if line.startswith(f"- {TODAY}:"))
                if "## Notes" in lines:
                    self.assertLess(entry, lines.index("## Notes"))
                else:
                    self.assertGreater(entry, lines.index("## History"))
                if "--led-to" in args:
                    link = args[args.index("--led-to") + 1]
                    earlier = list(before.get("led_to") or [])
                    self.assertEqual(data["led_to"], earlier + ([] if link in earlier else [link]))


class HardLinkTests(IdeaVault):
    def test_led_to_links_with_punctuation_read_back_identically(self):
        """Adversarial where: a link holding a comma, quote, backslash, `#`
        or closing bracket is split, unescaped or cut by the inline-list
        writer, so the vault reader and a real YAML parser disagree on
        `led_to` or the earlier link is damaged."""
        links = ['[[SPEC-1-a|x, y]]', '[[say "no"]]', '[[C:\\temp\\new]]',
                 '[[SPEC-2-b#Heading]]', '[[a]] ] [', '[[tail # not a comment]]']
        path = self.write_idea("characters", 1, "x", hand_idea(1, ["a map"], extra='led_to: ["[[first]]"]\n'))
        expected = ["[[first]]"]
        for link in links:
            code, out, err = self.idea(["status", "IDEA-001", "exploring", "--led-to", link, "--apply"])
            self.assertEqual(code, 0, out + err)
            expected.append(link)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(vaultlib.parse_frontmatter_text(text)[0]["led_to"], expected, link)
            self.assertEqual(yaml.safe_load(text.split("\n---\n")[0][4:])["led_to"], expected, link)


class ConcurrentAddTests(IdeaVault):
    RUNNER = (
        "import os, sys\n"
        "sys.path.insert(0, {cli!r})\n"
        "from commands import idea\n"
        "go = sys.argv[1]\n"
        "while not os.path.exists(go):\n"
        "    pass\n"
        "sys.exit(idea.run(sys.argv[2:]))\n"
    )

    def test_adds_started_together_never_share_a_number_or_lose_a_file(self):
        """Adversarial where: `add` reads the highest number, then writes, with
        no exclusive create, so processes started together all take the same
        next number and file different ideas under one id (a later `status
        IDEA-NNN` then changes whichever file sorts first); a lost write would
        show as fewer files than successful exits."""
        runner = self.tmp / "runner.py"
        runner.write_text(self.RUNNER.format(cli=str(CLI_DIR)), encoding="utf-8")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        total_succeeded = 0
        for round_number in range(2):
            go = self.tmp / f"go{round_number}"
            procs = [
                subprocess.Popen(
                    [sys.executable, str(runner), str(go), "add", "--category", "characters",
                     "--words", f"racer {round_number} lamp {k} distinct", "--apply"],
                    env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for k in range(6)
            ]
            time.sleep(1.5)
            go.write_text("go", encoding="utf-8")
            results = [(p.wait(), p.stdout.read(), p.stderr.read()) for p in procs]
            total_succeeded += len([r for r in results if r[0] == 0])
            numbers = [int(p.name.split("-")[1]) for p in self.idea_files()]
            self.assertEqual(len(numbers), len(set(numbers)),
                             f"round {round_number}: duplicate idea numbers {sorted(numbers)}")
            self.assertEqual(len(numbers), total_succeeded, results)


class EncodingTests(IdeaVault):
    def test_non_ascii_words_survive_the_launcher_and_land_as_utf8(self):
        """Adversarial where: the launcher's argv or stdout handling under a
        legacy Windows code page mangles accented or emoji words before they
        reach the file, so the stored words differ from what was typed."""
        words = "o mapa n\u00e3o esquece \U0001F525 nunca"
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        proc = subprocess.run(
            [sys.executable, str(CLI), "idea", "add", "--category", "characters",
             "--words", words, "--apply"],
            cwd=self.project, env=env, capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        (path,) = self.idea_files()
        self.assertEqual(vaultlib.parse_frontmatter(path)[0]["words"], words)
        raw = path.read_bytes()
        self.assertIn(words.encode("utf-8"), raw)
        self.assertNotIn(b"\r", raw)
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        proc = subprocess.run(
            [sys.executable, str(CLI), "idea", "find", "mapa"],
            cwd=self.project, env=env, capture_output=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(b"Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
