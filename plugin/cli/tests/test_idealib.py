"""Tests for the idea record: `idealib.verbatim` and the file shape that
`compass idea` writes through `idealib`.

Adversarial themes: his words must reach the file byte for byte and read back
identically through both frontmatter readers (the vault's own and a real YAML
parser) for every hard character; `verbatim` accepts only an exact substring,
so one changed character, a curly quote, collapsed whitespace or a different
Unicode normalization form is rejected; a status change edits only the lines
`idealib` owns and leaves everything a human added; `led_to` only grows.

`idealib` names no function besides `verbatim` in its contract, so the writers
are reached through `commands.idea.run`, the way production reaches them.
"""

import difflib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402

DATE = r"\d{4}-\d{2}-\d{2}"
DOMAIN_INDEX = (
    "---\ntitle: world-building\ntype: domain\nstatus: active\ntags: [world-building]\n---\n\n"
    "## Scope\n\nClass here: worlds and maps\n"
)


def split_front(text):
    """Return (frontmatter text, body text); the closing fence is the first
    unindented `---` line."""
    lines = text.split("\n")
    assert lines[0] == "---", "file does not open with a frontmatter fence"
    end = lines.index("---", 1)
    return "\n".join(lines[1:end]), "\n".join(lines[end + 1:])


def idea_text(number, words, status="new", title=None, led_to=(), note="",
              history=None, extra_fm="", extra_body="", after_history=""):
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
        f"{extra_fm}"
        "---\n\n"
        f"{blockquote}\n\n"
        f"{extra_body}"
        "## History\n\n"
        + "\n".join(history) + "\n"
        + after_history
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

    def read_both(self, path):
        """Parse one file with the vault reader and with PyYAML."""
        text = path.read_bytes().decode("utf-8")
        front, body = split_front(text)
        vault, error = vaultlib.parse_frontmatter(path)
        self.assertIsNone(error)
        return vault, yaml.safe_load(front), body, text


class VerbatimTests(unittest.TestCase):
    def test_verbatim_accepts_only_an_exact_substring(self):
        """Adversarial where: `verbatim` is true for words that are close to
        the source but not in it (one changed character, a curly quote swapped
        for a straight one, whitespace added, trimmed or collapsed, a different
        Unicode normalization form, a different case), which lets an altered
        sentence be filed as his own words."""
        import idealib
        nfc = "a\u00e7\u00e3o"
        nfd = unicodedata.normalize("NFD", nfc)
        cases = [
            ("whole source", "abc", "abc", True),
            ("inside the source", "map remembers", "the map remembers deaths", True),
            ("accents identical", "cora\u00e7\u00e3o", "o meu cora\u00e7\u00e3o d\u00f3i", True),
            ("leading space present in source", " now", "go now", True),
            ("trailing space present in source", "go now ", "go now please", True),
            ("newline present in source", "a\nb", "x\na\nb\ny", True),
            ("one character changed", "map remembars", "the map remembers", False),
            ("one character dropped", "map remembrs", "the map remembers", False),
            ("case changed", "Map", "the map", False),
            ("curly apostrophe in source, straight in words", "don't", "I don\u2019t go", False),
            ("straight apostrophe in source, curly in words", "don\u2019t", "I don't go", False),
            ("curly double quotes in source", 'say "hi"', "say \u201chi\u201d", False),
            ("trailing space added", "go now ", "go now", False),
            ("internal whitespace collapsed", "a b", "a  b", False),
            ("newline replaced by space", "a b", "a\nb", False),
            ("composed words against decomposed source", nfc, f"x {nfd} y", False),
            ("decomposed words against composed source", nfd, f"x {nfc} y", False),
            ("words longer than source", "abc def", "abc", False),
            ("empty source", "a", "", False),
        ]
        for name, words, source, expected in cases:
            with self.subTest(name):
                self.assertEqual(bool(idealib.verbatim(words, source)), expected)


HARD_WORDS = {
    "double quote": 'she said "go now" twice',
    "backslash with trailing backslash": "path C:\\temp\\new and a trailing backslash\\",
    "backslash then n as two characters": "a\\nb is not a newline",
    "colon space": "note: this is a thing",
    "hash": "ideas # not a comment",
    "bracket": "[not a list] really",
    "leading dash": "- not a list item",
    "ellipsis alone": "...",
    "ellipsis inside": "wait... what",
    "single quote": "it's a map",
    "portuguese accents": "n\u00e3o \u00e9 a\u00e7\u00e3o, cora\u00e7\u00e3o e p\u00f4r do sol",
    "yaml null lookalike": "null",
    "yaml number lookalike": "12345",
    "newline": 'first line\nsecond: line "q"\n- third # x',
    "newline around a fence lookalike": "above\n---\nbelow",
    "newline with an indented line": "top\n    indented step\nbottom",
}


class RecordShapeTests(IdeaVault):
    def test_hard_words_round_trip_through_both_readers(self):
        """Adversarial where: a writer that escapes only some characters, or
        a reader pair that disagree, alters his words in the property (a `\\n`
        turned into a newline, a `#` read as a comment, `null` read as no
        value, a `---` line closing the frontmatter early); the body
        blockquote, the one-line double-quoted form, the `|-` block form for a
        newline, LF line endings and UTF-8 bytes are all checked."""
        for name, words in HARD_WORDS.items():
            with self.subTest(name):
                for existing in self.idea_files():
                    existing.unlink()
                code, out, err = self.idea(
                    ["add", "--category", "world-building", "--words", words, "--apply"])
                self.assertEqual(code, 0, out + err)
                (path,) = self.idea_files()
                vault, real, body, text = self.read_both(path)
                self.assertEqual(vault["words"], words)
                self.assertEqual(real["words"], words)
                self.assertEqual(vault["type"], "idea")
                self.assertEqual(real["type"], "idea")
                self.assertEqual(vault["status"], real["status"])
                self.assertEqual(vault["title"], real["title"])
                self.assertTrue(real["title"].startswith("IDEA-001:"), real["title"])
                self.assertNotIn("\n", real["title"])
                quoted = [line for line in body.split("\n") if line.startswith(">")]
                self.assertEqual("\n".join(line[2:] for line in quoted), words)
                raw_lines = text.split("\n")
                if "\n" in words:
                    self.assertIn("words: |-", raw_lines)
                else:
                    (words_line,) = [line for line in raw_lines if line.startswith("words:")]
                    self.assertTrue(words_line.startswith('words: "'), words_line)
                self.assertNotIn(b"\r", path.read_bytes())

    def test_a_new_idea_ends_with_a_history_section_holding_a_dated_line(self):
        """Adversarial where: a new idea written with no `## History` section
        or with an undated line, so the first status change has nowhere to
        append and the idea's first date is lost."""
        code, out, err = self.idea(
            ["add", "--category", "characters", "--words", "a mute blacksmith", "--apply"])
        self.assertEqual(code, 0, out + err)
        (path,) = self.idea_files()
        _, _, body, _ = self.read_both(path)
        self.assertIn("## History", body)
        history = body.split("## History", 1)[1]
        self.assertRegex(history, rf"(?m)^- {DATE}: ")


class StatusChangeTests(IdeaVault):
    SOURCE_ID = "sx:2"

    def make_human_edited(self):
        text = idea_text(
            1, "what if the map remembers where you died", status="new",
            extra_fm="custom: keep me\n",
            extra_body="My own note: this came from the Tuesday call.\n\n",
            history=["- 2026-01-02: new (filed)", "- note to self: ask about scars"],
            after_history="\n## Notes\n\nHuman text after the history.\n",
        )
        return self.write_idea("world-building", 1, "what-if-the-map-remembers", text), text

    def test_status_change_with_his_sentence_edits_only_the_owned_lines(self):
        """Adversarial where: a status change rewrites the whole file and loses
        what a human added (an extra property, a note above the history, a
        hand-written history line, a section after the history), drops or
        rewrites the old history line instead of keeping it, adds more than
        one new line, appends past the next section, or leaves his sentence
        out of the new line's reason."""
        path, old = self.make_human_edited()
        self.write_prompt_log([(self.SOURCE_ID, "ok, no, drop it, thanks")])
        code, out, err = self.idea(
            ["status", "IDEA-001", "dropped", "--words", "no, drop it",
             "--source", self.SOURCE_ID, "--apply"])
        self.assertEqual(code, 0, out + err)
        new = path.read_bytes().decode("utf-8")
        vault, real, _, _ = self.read_both(path)
        self.assertEqual(vault["status"], "dropped")
        self.assertEqual(real["status"], "dropped")
        self.assertEqual(real["custom"], "keep me")

        old_lines, new_lines = old.split("\n"), new.split("\n")
        removed, added = [], []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, old_lines, new_lines).get_opcodes():
            if tag != "equal":
                removed += old_lines[i1:i2]
                added += new_lines[j1:j2]
        self.assertTrue(
            all(line.split(":")[0] in ("status", "updated") for line in removed), removed)
        history_lines = [line for line in added if re.match(rf"^- {DATE}: ", line)]
        self.assertEqual(len(history_lines), 1, added)
        self.assertTrue(
            all(line.split(":")[0] in ("status", "updated") or line in history_lines
                for line in added), added)
        self.assertRegex(
            history_lines[0], rf"^- {DATE}: new -> dropped \(.*no, drop it.*\)$")

        position = new_lines.index(history_lines[0])
        self.assertGreater(position, new_lines.index("- note to self: ask about scars"))
        self.assertLess(position, new_lines.index("## Notes"))
        self.assertIn("- 2026-01-02: new (filed)", new_lines)
        self.assertNotIn(b"\r", path.read_bytes())

    def test_status_change_without_his_sentence_still_appends_one_formatted_line(self):
        """Adversarial where: the `<old> -> <new> (<reason>)` history line only
        exists when `--words` is given, so a plain status change appends an
        unformatted line or none, or names the wrong old status."""
        text = idea_text(1, "a mute blacksmith", status="exploring",
                         history=["- 2026-01-02: new -> exploring (talked about it)"])
        path = self.write_idea("characters", 1, "a-mute-blacksmith", text)
        code, out, err = self.idea(["status", "IDEA-001", "parked", "--apply"])
        self.assertEqual(code, 0, out + err)
        lines = path.read_bytes().decode("utf-8").split("\n")
        history = lines[lines.index("## History") + 1:]
        entries = [line for line in history if line.startswith("- ")]
        self.assertEqual(entries[0], "- 2026-01-02: new -> exploring (talked about it)")
        self.assertEqual(len(entries), 2, entries)
        self.assertRegex(entries[1], rf"^- {DATE}: exploring -> parked \(.*\)$")

    def test_led_to_only_grows(self):
        """Adversarial where: appending a link replaces the list, drops the
        earlier link, reorders it, or a later status change with no `--led-to`
        clears it; the list must read back identically through both readers."""
        cases = [
            ("empty list gains one", [], ["[[SPEC-004-world-memory]]"]),
            ("existing link kept first", ["[[SPEC-004-world-memory]]"],
             ["[[SPEC-004-world-memory]]", "[[PLAN-009-scars]]"]),
            ("alias link", ["[[A-doc]]"], ["[[A-doc]]", "[[SPEC-005-x|the x spec]]"]),
        ]
        for name, start, expected in cases:
            with self.subTest(name):
                for existing in self.idea_files():
                    existing.unlink()
                path = self.write_idea(
                    "world-building", 1, "map",
                    idea_text(1, "the map remembers", led_to=start))
                new_link = expected[-1]
                code, out, err = self.idea(
                    ["status", "IDEA-001", "adopted", "--led-to", new_link, "--apply"])
                self.assertEqual(code, 0, out + err)
                vault, real, _, _ = self.read_both(path)
                self.assertEqual(vault["led_to"], expected)
                self.assertEqual(real["led_to"], expected)
                code, out, err = self.idea(["status", "IDEA-001", "done", "--apply"])
                self.assertEqual(code, 0, out + err)
                vault, real, _, _ = self.read_both(path)
                self.assertEqual(vault["led_to"], expected)
                self.assertEqual(real["led_to"], expected)

    def test_hard_words_survive_a_later_status_rewrite(self):
        """Adversarial where: a status change re-serializes the frontmatter
        through a lossy writer, so words that survived `add` (a block scalar
        with a `---` line, backslashes, quotes) come back altered, or the
        blockquote body is reflowed."""
        words = 'say "no"\n---\nC:\\temp\\new: yes # ok'
        code, out, err = self.idea(
            ["add", "--category", "world-building", "--words", words, "--apply"])
        self.assertEqual(code, 0, out + err)
        (path,) = self.idea_files()
        before_body = self.read_both(path)[2].split("## History")[0]
        code, out, err = self.idea(["status", "IDEA-001", "exploring", "--apply"])
        self.assertEqual(code, 0, out + err)
        vault, real, body, text = self.read_both(path)
        self.assertEqual(vault["words"], words)
        self.assertEqual(real["words"], words)
        self.assertEqual(body.split("## History")[0], before_body)
        self.assertIn("words: |-", text.split("\n"))


if __name__ == "__main__":
    unittest.main()
