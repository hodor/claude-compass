"""Tests for `compass idea add|status|find`.

Adversarial themes: `add` and `status` refuse every bad input (unknown status,
missing category folder, empty words, words that are not verbatim in the
logged prompt, a duplicate of existing words) with no file touched; dry-run is
the default and only `--apply` writes; the source prompt is matched by exact
id and exact substring; `find` resolves an id, a case-insensitive substring in
three fields, and otherwise ranks by shared words and prints the top five; a
search that finds nothing is one line and exit 0 even in a vault with no
`ideas/` folder at all.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402

CLI = Path(__file__).resolve().parents[1] / "compass"
DOMAIN_INDEX = (
    "---\ntitle: world-building\ntype: domain\nstatus: active\ntags: [world-building]\n---\n\n"
    "## Scope\n\nClass here: worlds and maps\n"
)
STATUSES = ("new", "exploring", "parked", "adopted", "done", "dropped")
MAP_WORDS = "what if the map remembers where you died, like a scar on the ground"


def idea_text(number, words, status="new", title=None, led_to=(), note="", history=None):
    """A hand-made idea file in the documented record shape."""
    quote = vaultlib.yaml_double_quote
    if "\n" in words:
        words_fm = "words: |-\n" + "\n".join("  " + line for line in words.split("\n"))
    else:
        words_fm = "words: " + quote(words)
    led = "[" + ", ".join(quote(x) for x in led_to) + "]"
    history = history if history is not None else [f"- 2026-01-02: {status} (filed)"]
    title = title or f"IDEA-{number:03d}: {words.splitlines()[0][:40]}"
    blockquote = "\n".join("> " + line for line in words.split("\n"))
    return (
        "---\n"
        f"title: {quote(title)}\n"
        "type: idea\n"
        f"status: {status}\n"
        f"{words_fm}\n"
        f"led_to: {led}\n"
        f"led_to_note: {quote(note)}\n"
        'raw_status: ""\n'
        'source: "made up"\n'
        "tags: [idea]\n"
        "created: 2026-01-02\n"
        "updated: 2026-01-02\n"
        "---\n\n"
        f"{blockquote}\n\n"
        "## History\n\n"
        + "\n".join(history) + "\n"
    )


class IdeaVault(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        for category in ("world-building", "characters"):
            (self.root / "ideas" / category).mkdir(parents=True)
            (self.root / "ideas" / category / "index.md").write_text(
                DOMAIN_INDEX, encoding="utf-8")
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

    def add(self, words, category="world-building", extra=(), apply=True):
        args = ["add", "--category", category, "--words", words, *extra]
        return self.idea(args + (["--apply"] if apply else []))

    def write_idea(self, category, number, slug, text):
        path = self.root / "ideas" / category / f"IDEA-{number:03d}-{slug}.md"
        path.write_bytes(text.encode("utf-8"))
        return path

    def write_prompt_log(self, rows, raw_prefix=""):
        path = self.root / "tmp" / "prompt-log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = raw_prefix + "".join(
            json.dumps({"id": rid, "at": "2026-11-19T10:00:00Z",
                        "session_id": rid.split(":")[0], "prompt": prompt},
                       ensure_ascii=False) + "\n"
            for rid, prompt in rows
        )
        path.write_bytes(text.encode("utf-8"))

    def idea_files(self):
        return sorted((self.root / "ideas").rglob("IDEA-*.md"))

    def clear_ideas(self):
        for path in self.idea_files():
            path.unlink()

    def snapshot(self):
        state = {}
        for path in self.root.rglob("*"):
            rel = path.relative_to(self.root).as_posix()
            state[rel] = path.read_bytes() if path.is_file() else None
        return state

    def frontmatter(self, path):
        data, error = vaultlib.parse_frontmatter(path)
        self.assertIsNone(error)
        return data


class AddWritesTheRecordTests(IdeaVault):
    def test_add_numbers_across_categories_and_names_the_file_from_five_words(self):
        """Adversarial where: the new idea restarts at 001 per category or
        counts only its own category (a number clash with an idea elsewhere),
        takes more or fewer than five words for the file name, or writes
        status or type wrongly; a phrase shorter than five words must still
        name the file."""
        self.write_idea("characters", 7, "a-mute-blacksmith",
                        idea_text(7, "a mute blacksmith who forges only at night"))
        cases = [
            ("seven words, other category holds the highest",
             MAP_WORDS, "world-building", "IDEA-008-what-if-the-map-remembers.md"),
            ("two words", "dark mode", "characters", "IDEA-009-dark-mode.md"),
        ]
        for name, words, category, expected in cases:
            with self.subTest(name):
                code, out, err = self.add(words, category)
                self.assertEqual(code, 0, out + err)
                path = self.root / "ideas" / category / expected
                self.assertTrue(path.is_file(), [p.name for p in self.idea_files()])
                data = self.frontmatter(path)
                self.assertEqual(data["words"], words)
                self.assertEqual(data["type"], "idea")
                self.assertEqual(data["status"], "new")
                self.assertTrue(data["title"].startswith(expected[:8] + ":"), data["title"])

    def test_add_accepts_each_of_the_six_statuses(self):
        """Adversarial where: the status check knows only some of the six
        values, or ignores `--status` and always writes `new`."""
        for index, status in enumerate(STATUSES, start=1):
            with self.subTest(status):
                code, out, err = self.add(
                    f"idea number {index} for status {status}", "characters",
                    extra=["--status", status])
                self.assertEqual(code, 0, out + err)
                (path,) = [p for p in self.idea_files() if p.name.startswith(f"IDEA-{index:03d}-")]
                self.assertEqual(self.frontmatter(path)["status"], status)

    def test_dry_run_is_the_default_and_apply_writes(self):
        """Adversarial where: add or status writes without `--apply` (a
        dry-run that mutates), or `--apply` on add writes more than the one
        idea file."""
        before = self.snapshot()
        code, out, err = self.add("a dry run idea", apply=False)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), before)
        code, out, err = self.add("a dry run idea", apply=True)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.idea_files()), 1)
        written = self.idea_files()[0]
        before = self.snapshot()
        code, out, err = self.idea(["status", "IDEA-001", "dropped", "--led-to", "[[SPEC-001-x]]"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.frontmatter(written)["status"], "new")


class AddRefusalTests(IdeaVault):
    def test_add_refuses_bad_inputs_and_writes_nothing(self):
        """Adversarial where: an unknown status, a missing or escaping
        category folder, or empty or absent words is accepted and a file (or a
        category folder) appears; each refusal must exit non-zero and leave
        the vault byte for byte as it was, even with `--apply`."""
        (self.root / "specs").mkdir()
        cases = [
            ("unknown status", ["add", "--category", "characters", "--words", "x y",
                                "--status", "someday", "--apply"]),
            ("missing category folder", ["add", "--category", "no-such-category",
                                         "--words", "x y", "--apply"]),
            ("category escaping the ideas folder", ["add", "--category", "../specs",
                                                    "--words", "x y", "--apply"]),
            ("no category flag", ["add", "--words", "x y", "--apply"]),
            ("empty words", ["add", "--category", "characters", "--words", "", "--apply"]),
            ("no words flag", ["add", "--category", "characters", "--apply"]),
        ]
        for name, args in cases:
            with self.subTest(name):
                before = self.snapshot()
                code, _, _ = self.idea(args)
                self.assertNotEqual(code, 0)
                self.assertEqual(self.snapshot(), before)

    def test_duplicate_words_are_refused_naming_the_existing_idea(self):
        """Adversarial where: exact-duplicate words are filed a second time,
        or the refusal does not name the idea already holding them; the
        existing idea may sit in another category, hold the words as a `|-`
        block or with escaped characters (a reader that mis-parses them never
        matches), and the refusal holds in dry-run too. Words that differ by
        one character or by case are a different idea and are accepted."""
        self.write_idea("characters", 5, "multi",
                        idea_text(5, "first line\nsecond: line"))
        self.write_idea("characters", 6, "escaped",
                        idea_text(6, 'she said "go" in C:\\temp\\x'))
        code, out, err = self.add(MAP_WORDS, "world-building")
        self.assertEqual(code, 0, out + err)
        (mapped,) = [p for p in self.idea_files() if p.name.startswith("IDEA-007-")]
        refused = [
            ("same category", MAP_WORDS, "world-building", True, "IDEA-007"),
            ("other category", MAP_WORDS, "characters", True, "IDEA-007"),
            ("dry-run", MAP_WORDS, "world-building", False, "IDEA-007"),
            ("block scalar words", "first line\nsecond: line", "world-building", True, "IDEA-005"),
            ("escaped words", 'she said "go" in C:\\temp\\x', "world-building", True, "IDEA-006"),
        ]
        for name, words, category, apply, existing in refused:
            with self.subTest(name):
                before = self.snapshot()
                code, out, err = self.add(words, category, apply=apply)
                self.assertNotEqual(code, 0)
                self.assertIn(existing, out + err)
                self.assertEqual(self.snapshot(), before)
        self.assertTrue(mapped.is_file())
        for number, words in ((8, MAP_WORDS + "!"), (9, MAP_WORDS.upper())):
            with self.subTest(f"different words become IDEA-{number:03d}"):
                code, out, err = self.add(words)
                self.assertEqual(code, 0, out + err)
                self.assertTrue(
                    [p for p in self.idea_files() if p.name.startswith(f"IDEA-{number:03d}-")])


class AddSourceTests(IdeaVault):
    NFC = "a\u00e7\u00e3o"

    def test_source_must_hold_the_words_exactly_in_that_prompt(self):
        """Adversarial where: `--source` words are accepted when they are only
        close to the logged prompt (curly versus straight quote, a different
        Unicode form), when they appear in a different prompt (a prefix id
        such as `s1:1` matching `s1:10`), when the id is unknown or the log is
        absent; words that are an exact substring (also across a newline) are
        accepted even with a corrupt line earlier in the log."""
        rows = [
            ("s1:1", "I think we should add a map that remembers deaths. Don\u2019t forget audio"),
            ("s1:10", "unique tail words appear only here"),
            ("s1:2", f"intro\nline one\nline two\noutro {self.NFC}"),
            ("s1:3", "it's straight here"),
        ]
        cases = [
            ("exact substring mid-prompt", "s1:1", "map that remembers deaths", True, True),
            ("exact substring across a newline", "s1:2", "line one\nline two", True, True),
            ("curly in log, straight in words", "s1:1", "Don't forget audio", False, True),
            ("curly in words, straight in log", "s1:3", "it\u2019s straight here", False, True),
            ("decomposed accents against composed log", "s1:2",
             unicodedata.normalize("NFD", self.NFC), False, True),
            ("words only in the id that shares a prefix", "s1:1", "unique tail words", False, True),
            ("unknown prompt id", "s9:9", "map that remembers deaths", False, True),
            ("log file absent", "s1:1", "map that remembers deaths", False, False),
        ]
        for name, source, words, accepted, log_present in cases:
            with self.subTest(name):
                self.clear_ideas()
                if log_present:
                    self.write_prompt_log(rows, raw_prefix='{"id": "s0:1", "prompt": "torn\n')
                elif (self.root / "tmp" / "prompt-log.jsonl").exists():
                    (self.root / "tmp" / "prompt-log.jsonl").unlink()
                before = self.snapshot()
                code, out, err = self.add(words, "characters", extra=["--source", source])
                if accepted:
                    self.assertEqual(code, 0, out + err)
                    (path,) = self.idea_files()
                    self.assertEqual(self.frontmatter(path)["words"], words)
                else:
                    self.assertNotEqual(code, 0)
                    self.assertEqual(self.snapshot(), before)


class StatusRefusalTests(IdeaVault):
    def test_status_refuses_bad_inputs_and_changes_nothing(self):
        """Adversarial where: status accepts an unknown idea, an unknown
        status, or his sentence that is not verbatim in the logged prompt (a
        curly quote), and rewrites the file anyway; each refusal exits
        non-zero and leaves every byte untouched even with `--apply`."""
        self.write_idea("characters", 1, "a-mute-blacksmith",
                        idea_text(1, "a mute blacksmith"))
        self.write_prompt_log([("s1:1", "no, don\u2019t keep it")])
        cases = [
            ("unknown idea", ["status", "IDEA-099", "dropped", "--apply"]),
            ("unknown status", ["status", "IDEA-001", "someday", "--apply"]),
            ("no status given", ["status", "IDEA-001", "--apply"]),
            ("sentence with a straight quote where the log has a curly one",
             ["status", "IDEA-001", "dropped", "--words", "don't keep it",
              "--source", "s1:1", "--apply"]),
            ("sentence against an unknown prompt id",
             ["status", "IDEA-001", "dropped", "--words", "no", "--source", "s7:7", "--apply"]),
        ]
        for name, args in cases:
            with self.subTest(name):
                before = self.snapshot()
                code, _, _ = self.idea(args)
                self.assertNotEqual(code, 0)
                self.assertEqual(self.snapshot(), before)


class FindTests(IdeaVault):
    def seed(self):
        self.write_idea("world-building", 1, "map", idea_text(
            1, MAP_WORDS, status="adopted", led_to=["[[SPEC-004-world-memory]]"],
            note="[[SPEC-004-world-memory]]: scars fade after a day",
            history=["- 2026-01-02: new (filed)",
                     "- 2026-02-03: new -> adopted (the spec names it)"],
            title="IDEA-001: what if the map remembers where you died"))
        self.write_idea("characters", 2, "smith", idea_text(
            2, "a mute blacksmith who forges only at night", status="parked"))
        self.write_idea("characters", 3, "lights", idea_text(
            3, "traffic lights that argue with the player", status="dropped",
            note="tried in prototype, felt noisy", title="IDEA-003: zebra crossing"))

    def test_find_resolves_an_id_and_case_insensitive_substrings(self):
        """Adversarial where: an id lookup also prints other ideas or omits a
        field (id, category, status, his words, `led_to`, `led_to_note`, every
        history line); substring search is case sensitive or looks only at
        `words`, missing a hit that sits in `led_to_note` or only in the
        title, or drops one of two ideas matching the same text."""
        self.seed()
        code, out, err = self.idea(["find", "IDEA-001"])
        self.assertEqual(code, 0, err)
        for piece in ("IDEA-001", "world-building", "adopted", MAP_WORDS,
                      "[[SPEC-004-world-memory]]", "scars fade after a day",
                      "2026-01-02: new (filed)",
                      "2026-02-03: new -> adopted (the spec names it)"):
            self.assertIn(piece, out)
        self.assertNotIn("mute blacksmith", out)
        self.assertNotIn("traffic lights", out)

        cases = [
            ("uppercase query against lowercase words", "SCAR ON THE", {"IDEA-001"}),
            ("hit only in led_to_note", "fade after a day", {"IDEA-001"}),
            ("hit only in the title", "zebra", {"IDEA-003"}),
            ("hit in words of the other category", "Blacksmith", {"IDEA-002"}),
            ("one text matching two ideas", "ight", {"IDEA-002", "IDEA-003"}),
            ("one text matching all three ideas", "th", {"IDEA-001", "IDEA-002", "IDEA-003"}),
        ]
        for name, query, expected in cases:
            with self.subTest(name):
                code, out, err = self.idea(["find", query])
                self.assertEqual(code, 0, err)
                found = {i for i in ("IDEA-001", "IDEA-002", "IDEA-003") if i in out}
                self.assertEqual(found, expected, out)

    def test_find_without_a_substring_hit_ranks_by_shared_words_and_prints_five(self):
        """Adversarial where: with no substring hit the search prints nothing,
        prints every idea sharing a word, ranks by idea number instead of by
        words shared, or prints a sixth; seven ideas share 1 to 7 of the
        query's eight words in reversed order, so the top five are IDEA-007 to
        IDEA-003, most-shared first, and the idea sharing none is absent."""
        query_words = ["zorp", "blick", "quax", "fnord", "wibble", "gleep", "snarf", "plink"]
        for k in range(1, 8):
            words = " ".join(reversed(query_words[:k])) + f" and padding {k}x"
            self.write_idea("characters", k, f"shares-{k}", idea_text(k, words))
        self.write_idea("characters", 8, "unrelated", idea_text(8, "nothing in common here"))
        code, out, err = self.idea(["find", " ".join(query_words)])
        self.assertEqual(code, 0, err)
        positions = [out.find(f"IDEA-{k:03d}") for k in (7, 6, 5, 4, 3)]
        self.assertTrue(all(p >= 0 for p in positions), out)
        self.assertEqual(positions, sorted(positions), out)
        for absent in ("IDEA-001", "IDEA-002", "IDEA-008"):
            self.assertNotIn(absent, out)

    def test_find_with_nothing_to_find_is_one_line_and_exit_zero(self):
        """Adversarial where: a miss exits non-zero, prints a traceback, prints
        several lines, or crashes when the vault has no `ideas/` folder or
        only empty categories; an unknown id is a miss, not an error."""
        self.seed()
        cases = [
            ("no shared word", ["find", "qwertyuiop asdfghjkl"], True),
            ("unknown id", ["find", "IDEA-099"], True),
            ("empty categories only", ["find", "anything at all"], False),
            ("no ideas folder at all", ["find", "anything at all"], "gone"),
        ]
        for name, args, seeded in cases:
            with self.subTest(name):
                if seeded is False:
                    self.clear_ideas()
                if seeded == "gone":
                    shutil.rmtree(self.root / "ideas")
                code, out, err = self.idea(args)
                self.assertEqual(code, 0, err)
                lines = [line for line in (out + err).splitlines() if line.strip()]
                self.assertEqual(len(lines), 1, lines)
                self.assertNotIn("Traceback", lines[0])


class CommandWiringTests(IdeaVault):
    def run_cli(self, *args):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        return subprocess.run(
            [sys.executable, str(CLI), *args], cwd=self.project, env=env,
            capture_output=True, timeout=120)

    def test_idea_is_a_listed_command_that_dispatches_and_make_domain_help_names_the_new_flags(self):
        """Adversarial where: `idea` is missing from `COMMAND_SPECS` (so the
        launcher refuses it or the bare listing hides it), the make-domain
        help line does not mention `--rename` or that `--undo` archives, or the
        launcher path (not just `commands.idea.run`) fails to add and find."""
        import maincli
        specs = dict(maincli.COMMAND_SPECS)
        self.assertIn("idea", specs)
        self.assertIn("idea", maincli.VALID_COMMANDS)
        make_domain_help = specs["make-domain"].lower()
        self.assertIn("--rename", make_domain_help)
        self.assertIn("archiv", make_domain_help)

        proc = self.run_cli("idea", "add", "--category", "characters",
                            "--words", "a lamp that follows you", "--apply")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(self.idea_files()), 1)
        proc = self.run_cli("idea", "find", "lamp that")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(b"a lamp that follows you", proc.stdout)
        self.assertIn(b"IDEA-001", proc.stdout)
        shutil.rmtree(self.root / "ideas")
        proc = self.run_cli("idea", "find", "x")
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
