"""Edge tests for `compass idea import` found by reading the importer: the
header row is read by position and never filed; a run of `|` lines with no
separator row is reported with its heading instead of vanishing; a heading
with no table still makes its category; two tables under one heading both
import into that category.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_idea_import import ImportVault  # noqa: E402

HEAD = "| # | His words | Status | Where it led |\n|---|---|---|---|\n"


class TableShapeTests(ImportVault):
    def write_table(self, text):
        path = self.project / "table.md"
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def words_filed(self):
        return {data["words"]: data for _, data, _ in self.imported().values()}

    def test_columns_are_read_by_position_whatever_the_header_names_say(self):
        """Adversarial where: a table whose header lists the columns in
        another order is read by header name (words taken from the wrong
        cell), or its header row is filed as an idea. The documented contract
        is position only: cell 2 is the words, cell 3 the status."""
        path = self.write_table(
            "## Audio\n\n"
            "| Where it led | Status | His words | # |\n|---|---|---|---|\n"
            "| 31 | a hum under the floor | parked | [[SPEC-006-combat]] |\n")
        code, out, err = self.run_import(path, apply=True)
        self.assertEqual(code, 0, out + err)
        filed = self.words_filed()
        self.assertEqual(list(filed), ["a hum under the floor"])
        idea = filed["a hum under the floor"]
        self.assertEqual(idea["status"], "parked")
        self.assertEqual(idea["led_to_note"], "[[SPEC-006-combat]]")
        self.assertNotIn("His words", filed)
        self.assertNotIn("Status", filed)

    def test_a_table_without_a_separator_row_is_reported_with_its_heading_and_files_nothing(self):
        """Adversarial where: a table missing its `|---|` row is ignored with
        no word, so the human believes the section imported. The report
        names the heading and the line; the neighbour table with a separator
        still imports; the same holds when the loose table is the last thing
        in the file with no trailing newline."""
        path = self.write_table(
            "## Audio\n\n"
            "| # | His words | Status | Where it led |\n"
            '| 40 | "a hum under the floor" | new | |\n\n'
            "## Textures\n\n" + HEAD +
            '| 41 | "grain that moves with the wind" | new | |\n\n'
            "## Lighting\n\n"
            "| # | His words | Status | Where it led |\n"
            '| 42 | "light that pools at doorways" | new | |')
        code, out, err = self.run_import(path, apply=True)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(list(self.words_filed()), ["grain that moves with the wind"])
        skipped = out.split("skipped rows")[1]
        self.assertIn("Audio", skipped)
        self.assertIn("Lighting", skipped)
        self.assertNotIn("Textures", skipped)
        self.assertIn("separator", skipped)
        self.assertIn("line 3:", skipped)
        self.assertIn("line 14:", skipped)

    def test_a_row_after_a_blank_line_is_reported_not_swallowed_as_a_header(self):
        """Adversarial where: a blank line inside a table ends it, so the next
        `|` line is read as a new header and the idea on it is lost without a
        word. It must show up under skipped rows."""
        path = self.write_table(
            "## Audio\n\n" + HEAD +
            '| 40 | "a hum under the floor" | new | |\n\n'
            '| 41 | "a bell that rings underwater" | new | |\n')
        code, out, err = self.run_import(path, apply=True)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(list(self.words_filed()), ["a hum under the floor"])
        self.assertIn("bell that rings", out.split("skipped rows")[1])

    def test_a_heading_with_no_table_makes_its_category_and_does_not_steal_the_next_rows(self):
        """Adversarial where: a heading followed by prose only is dropped, or
        its slug stays current so the next heading's rows land in the wrong
        folder, or the prose line starting with a word is read as a table."""
        path = self.write_table(
            "## Story\n\nStill to be written.\n\n## Audio\n\n" + HEAD +
            '| 40 | "a hum under the floor" | new | |\n')
        code, out, err = self.run_import(path, apply=True)
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.root / "ideas" / "story" / "index.md").is_file())
        (found,) = self.imported().values()
        self.assertEqual(found[0].parent.name, "audio")
        self.assertNotIn("skipped rows", out)

    def test_two_tables_under_one_heading_both_import_and_the_second_header_is_not_filed(self):
        """Adversarial where: only the first table under a heading is read,
        or the second table's header row is filed as an idea, or the second
        table's rows are filed under no category."""
        path = self.write_table(
            "## Audio\n\n" + HEAD +
            '| 40 | "a hum under the floor" | new | |\n\n'
            "Later additions:\n\n" + HEAD +
            '| 41 | "a bell that rings underwater" | parked | |\n')
        code, out, err = self.run_import(path, apply=True)
        self.assertEqual(code, 0, out + err)
        files = self.imported()
        self.assertEqual(sorted(files), ["a bell that rings underwater", "a hum under the floor"])
        self.assertEqual({p.parent.name for p, _, _ in files.values()}, {"audio"})
        self.assertNotIn("skipped rows", out)


if __name__ == "__main__":
    unittest.main()
