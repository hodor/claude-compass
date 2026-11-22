"""Text drift checks in `driftlib`: index lines against their target's
summary, and lesson-catalog rows against their lesson files.

Public API under test
---------------------
``driftlib.scan_index_lines(repo_root, vault_dir)``
``driftlib.scan_catalog(repo_root, vault_dir)``

* ``repo_root``: ``pathlib.Path`` of a git repository.
* ``vault_dir``: ``pathlib.Path`` of the vault directory inside it.

Both return a list of dict records sorted by ``(file, line)``. Only
findings are returned: a line or row that agrees with its source yields no
record. Every record carries exactly these keys:

- ``file``: the document holding the checked text (an index, or the
  catalog), repo-relative with ``/`` separators.
- ``line``: 1-based line number of the checked text inside ``file``.
- ``class``: the finding class, see below.
- ``target``: repo-relative path of the file the text was compared with
  (the linked document, or the lesson file), ``None`` when none resolved.
- ``field``: the catalog field that differs (``score``, ``summary``,
  ``status``, ``category``, ``area``, ``tags``, ``escalated``); ``None`` for
  index-line records and for ``missing``.
- ``old_text``: the text as written in ``file`` (the index description, or
  the catalog value as text), ``None`` when there is no such text.
- ``current_text``: the text in ``target`` (its ``summary``, or the lesson
  file's field value as text), ``None`` when there is none.
- ``newer``: for ``index-drift`` only, ``"target"`` when the commit that
  last changed the target's ``summary:`` line is strictly later (committer
  time) than the commit that last changed the index line, ``"index"`` when
  strictly earlier, ``None`` when the times are equal or either side has no
  commit time (uncommitted line, untracked file). ``None`` for every other
  class.

Index lines (``scan_index_lines``)
  Every ``index.md`` under ``vault_dir`` (``archive/`` and ``tmp/`` at the
  vault root are skipped) is read. A line shaped as sync's entry pattern
  (bullet, one wikilink, optional ``(folder, N children)``, optional
  dash-separated description; plain, em and en dashes all separate) is
  checked. Link targets drop ``#heading`` and ``|alias``; resolution is
  ``vaultlib.resolvable_names_map`` plus ``vaultlib.resolve_link`` against
  ``vault_dir``. Classes:

  - ``index-drift``: description differs from the target's ``summary``
    (exact string comparison after the frontmatter value is unquoted).
  - ``no-summary``: the target resolved but has no ``summary`` or an empty
    one. Never ``index-drift``, whatever the description says.
  - ``unresolved-link``: the link resolves to no file.
  - ``ambiguous-link``: the link resolves to more than one file.
  A line with no description, and any line not shaped as an entry, yields
  no record.

Catalog (``scan_catalog``)
  Rows of ``<vault_dir>/meta/lessons-catalog.yaml`` are compared with the
  lesson file of the same filename found anywhere under
  ``<vault_dir>/lessons``. Classes:

  - ``catalog-drift``: one record per differing field; ``line`` is the
    catalog line of that field. A row's ``escalated`` that the file lacks
    is not drift; a file's ``escalated`` that the row lacks is. ``tags``
    compare as ordered lists.
  - ``missing``: no lesson file carries the row's filename; ``line`` is the
    row's ``- file:`` line.
  A lesson file without a row yields no record. No catalog file yields [].
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import driftlib  # noqa: E402

KEYS = {
    "file", "line", "class", "target", "field",
    "old_text", "current_text", "newer",
}
EPOCH = 1_700_000_000
INDEX = ".compass/index.md"
CATALOG = ".compass/meta/lessons-catalog.yaml"
SPEC = ".compass/specs/SPEC-001-alpha.md"
EM = chr(0x2014)
EN = chr(0x2013)


def git(repo, *args, env=None):
    done = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
        env=dict(os.environ, **(env or {})),
    )
    return done.stdout.strip()


def write(repo, rel, lines):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def commit(repo, message, *paths, at=EPOCH):
    """Commit `paths` with author and committer time `at` (epoch seconds)."""
    if paths:
        git(repo, "add", "-A", "--", *paths)
    stamp = f"{at} +0000"
    git(repo, "commit", "-q", "--allow-empty", "-m", message,
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})


def new_repo(case):
    repo = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, repo, True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Tester")
    git(repo, "config", "user.email", "tester@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def doc(summary_line, body="Body."):
    """A vault document; `summary_line` is the raw frontmatter line, or None."""
    front = ["---", "title: Alpha"]
    if summary_line is not None:
        front.append(summary_line)
    return front + ["---", "", body]


def index_doc(*entries):
    return ["# Index", "", "## Specs", "", *entries]


def vault(case, index_lines, docs=None, at=EPOCH):
    """Committed repo: `.compass/index.md` plus `docs` {rel: lines}."""
    repo = new_repo(case)
    write(repo, INDEX, index_lines)
    for rel, lines in (docs or {}).items():
        write(repo, rel, lines)
    commit(repo, "seed", ".compass", at=at)
    return repo


def scan_index(repo):
    return driftlib.scan_index_lines(repo, Path(repo) / ".compass")


def scan_catalog(repo):
    return driftlib.scan_catalog(repo, Path(repo) / ".compass")


def entry(name, desc, extra=""):
    return f"- [[{name}]]{extra} - {desc}"


class IndexLineDriftTests(unittest.TestCase):
    def test_description_versus_summary_is_exact_string_comparison(self):
        """Adversarial where: a comparison that normalises (strip, casefold,
        prefix match) or that only fires on large edits would miss a
        one-character difference, while an unquoting bug in the frontmatter
        value would report a faithful sync-written line as drift."""
        rows = {
            "one char differs": (
                "summary: Alpha does X", entry("SPEC-001-alpha", "Alpha does Y"),
                ("Alpha does Y", "Alpha does X"),
            ),
            "case differs": (
                "summary: Alpha does X", entry("SPEC-001-alpha", "alpha does X"),
                ("alpha does X", "Alpha does X"),
            ),
            "description is a prefix": (
                "summary: Alpha does X", entry("SPEC-001-alpha", "Alpha does"),
                ("Alpha does", "Alpha does X"),
            ),
            "interior double space": (
                "summary: Alpha does X", entry("SPEC-001-alpha", "Alpha  does X"),
                ("Alpha  does X", "Alpha does X"),
            ),
            "double-quoted summary differs": (
                'summary: "Alpha, does X"', entry("SPEC-001-alpha", "Alpha, does Y"),
                ("Alpha, does Y", "Alpha, does X"),
            ),
        }
        for name, (summary, line, (old, current)) in rows.items():
            with self.subTest(name):
                repo = vault(self, index_doc(line), {SPEC: doc(summary)})
                found = scan_index(repo)
                self.assertEqual(len(found), 1, found)
                rec = found[0]
                self.assertEqual(set(rec), KEYS)
                self.assertEqual(rec["class"], "index-drift")
                self.assertEqual(rec["file"], INDEX)
                self.assertEqual(rec["line"], 5)
                self.assertEqual(rec["target"], SPEC)
                self.assertIsNone(rec["field"])
                self.assertEqual(rec["old_text"], old)
                self.assertEqual(rec["current_text"], current)

    def test_agreeing_lines_yield_no_record(self):
        """Adversarial where: an agreeing line reported as drift floods the
        report with false positives; sync-written quoting and every accepted
        separator and link form must read as agreement."""
        quoted_summary = 'summary: "He said \\"go\\" now"'
        rows = {
            "plain": ("summary: Alpha does X", entry("SPEC-001-alpha", "Alpha does X")),
            "em dash separator": (
                "summary: Alpha does X", f"- [[SPEC-001-alpha]] {EM} Alpha does X"),
            "en dash separator": (
                "summary: Alpha does X", f"- [[SPEC-001-alpha]] {EN} Alpha does X"),
            "escaped quotes in summary": (
                quoted_summary, entry("SPEC-001-alpha", 'He said "go" now')),
            "single-quoted summary": (
                "summary: 'It''s fine'", entry("SPEC-001-alpha", "It's fine")),
            "alias and heading in link": (
                "summary: Alpha does X",
                "- [[SPEC-001-alpha#Goals|Alpha]] - Alpha does X"),
            "abbreviated stem resolving uniquely": (
                "summary: Alpha does X", entry("SPEC-001", "Alpha does X")),
            "path-qualified link": (
                "summary: Alpha does X", entry("specs/SPEC-001-alpha", "Alpha does X")),
            "trailing spaces after description": (
                "summary: Alpha does X", "- [[SPEC-001-alpha]] - Alpha does X   "),
        }
        for name, (summary, line) in rows.items():
            with self.subTest(name):
                repo = vault(self, index_doc(line), {SPEC: doc(summary)})
                self.assertEqual(scan_index(repo), [])

    def test_folder_line_compares_description_after_the_child_count(self):
        """Adversarial where: a parser that keeps `(folder, 3 children)` in
        the description, or fails to strip the `|alias` of a folder link,
        reports every folder line as drift or unresolved."""
        folder_index = ".compass/specs/SPEC-002-beta/index.md"
        docs = {folder_index: doc("summary: Beta family")}
        agree = "- [[specs/SPEC-002-beta/index|SPEC-002-beta]] (folder, 3 children) - Beta family"
        differ = "- [[specs/SPEC-002-beta/index|SPEC-002-beta]] (folder, 3 children) - Beta clan"
        self.assertEqual(scan_index(vault(self, index_doc(agree), docs)), [])
        found = scan_index(vault(self, index_doc(differ), docs))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["class"], "index-drift")
        self.assertEqual(found[0]["target"], folder_index)
        self.assertEqual(found[0]["old_text"], "Beta clan")
        self.assertEqual(found[0]["current_text"], "Beta family")

    def test_dash_separator_is_not_part_of_the_reported_description(self):
        """Adversarial where: splitting only on an ASCII dash leaves an em or
        en dash glued to the description, so old_text carries a stray
        separator and an agreeing hand-authored line is reported."""
        for name, line in (("em", f"- [[SPEC-001-alpha]] {EM} Alpha does Y"),
                           ("en", f"- [[SPEC-001-alpha]] {EN} Alpha does Y")):
            with self.subTest(name):
                repo = vault(self, index_doc(line),
                             {SPEC: doc("summary: Alpha does X")})
                found = scan_index(repo)
                self.assertEqual([r["old_text"] for r in found], ["Alpha does Y"])

    def test_unverifiable_lines_get_their_own_class_never_drift(self):
        """Adversarial where: a missing summary, a dead link or a link naming
        two files compared as if it were a description mismatch would send a
        resync to overwrite text with nothing, or with the wrong file's."""
        dup_a = ".compass/specs/dup.md"
        dup_b = ".compass/plans/dup.md"
        rows = {
            "no summary key": (
                entry("SPEC-001-alpha", "Alpha does X"),
                {SPEC: doc(None)}, "no-summary", SPEC),
            "empty summary": (
                entry("SPEC-001-alpha", "Alpha does X"),
                {SPEC: doc("summary:")}, "no-summary", SPEC),
            "unresolved link": (
                entry("SPEC-099-ghost", "Alpha does X"),
                {SPEC: doc("summary: Alpha does X")}, "unresolved-link", None),
            "ambiguous link": (
                entry("dup", "Alpha does X"),
                {dup_a: doc("summary: Alpha does X"),
                 dup_b: doc("summary: Alpha does X")}, "ambiguous-link", None),
        }
        for name, (line, docs, cls, target) in rows.items():
            with self.subTest(name):
                repo = vault(self, index_doc(line), docs)
                found = scan_index(repo)
                self.assertEqual(len(found), 1, found)
                self.assertEqual(set(found[0]), KEYS)
                self.assertEqual(found[0]["class"], cls)
                self.assertEqual(found[0]["line"], 5)
                self.assertEqual(found[0]["target"], target)
                self.assertIsNone(found[0]["newer"])

    def test_path_qualified_link_disambiguates_a_shared_stem(self):
        """Adversarial where: treating every shared stem as ambiguous, even
        when the link is path-qualified, hides real drift behind a class
        that cannot be acted on."""
        docs = {".compass/specs/dup.md": doc("summary: Spec text"),
                ".compass/plans/dup.md": doc("summary: Plan text")}
        repo = vault(self, index_doc(entry("plans/dup", "Spec text")), docs)
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["class"], "index-drift")
        self.assertEqual(found[0]["target"], ".compass/plans/dup.md")
        self.assertEqual(found[0]["current_text"], "Plan text")

    def test_only_entry_shaped_lines_with_a_description_are_checked(self):
        """Adversarial where: scanning prose that merely mentions a link, a
        heading, or a bullet with no description reports text that was never
        an index entry."""
        docs = {SPEC: doc("summary: Alpha does X")}
        lines = index_doc(
            "See [[SPEC-001-alpha]] - something else entirely",
            "- [[SPEC-001-alpha]]",
            "- Alpha does Y [[SPEC-001-alpha]] - Alpha does Y",
            "## [[SPEC-001-alpha]] - Alpha does Y",
        )
        self.assertEqual(scan_index(vault(self, lines, docs)), [])

    def test_only_the_leading_link_decides_the_target(self):
        """Adversarial where: resolving the last or every link in the line
        compares the description against the wrong file."""
        docs = {SPEC: doc("summary: Alpha does X"),
                ".compass/specs/SPEC-003-gamma.md": doc("summary: Gamma")}
        line = "- [[SPEC-001-alpha]] - Alpha does Y, see [[SPEC-003-gamma]]"
        found = scan_index(vault(self, index_doc(line), docs))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["target"], SPEC)

    def test_nested_index_files_are_scanned_and_archive_is_skipped(self):
        """Adversarial where: scanning only the root index misses every
        domain index; scanning archive/ reports frozen pointer lists."""
        lesson = ".compass/lessons/hooks/LESSON-x.md"
        docs = {
            lesson: doc("summary: Real summary"),
            ".compass/lessons/hooks/index.md": index_doc(
                entry("LESSON-x", "Stale summary")),
            ".compass/archive/index.md": index_doc(
                entry("LESSON-x", "Stale summary")),
        }
        found = scan_index(vault(self, ["# Index"], docs))
        self.assertEqual([(r["file"], r["class"], r["target"]) for r in found],
                         [(".compass/lessons/hooks/index.md", "index-drift", lesson)])

    def test_records_are_sorted_with_correct_line_numbers(self):
        """Adversarial where: a line counter that restarts, skips fenced or
        blank lines, or sorts by link name misnumbers the finding the human
        must open."""
        docs = {SPEC: doc("summary: Alpha does X"),
                ".compass/specs/SPEC-004-delta.md": doc("summary: Delta does X")}
        lines = index_doc(
            entry("SPEC-004-delta", "Delta does Y"),
            "",
            entry("SPEC-001-alpha", "Alpha does X"),
            entry("SPEC-099-ghost", "x"),
            entry("SPEC-001-alpha", "Alpha does Z"),
        )
        found = scan_index(vault(self, lines, docs))
        self.assertEqual([(r["line"], r["class"]) for r in found],
                         [(5, "index-drift"), (8, "unresolved-link"),
                          (9, "index-drift")])

    def test_vault_without_an_index_has_no_findings(self):
        """Adversarial where: assuming a root index exists raises on a fresh
        vault instead of reporting nothing."""
        repo = new_repo(self)
        write(repo, SPEC, doc("summary: Alpha does X"))
        commit(repo, "seed", ".compass")
        self.assertEqual(scan_index(repo), [])


class IndexLineNewerSideTests(unittest.TestCase):
    def seeded(self, target_at, index_at):
        repo = new_repo(self)
        write(repo, SPEC, doc("summary: Target text"))
        commit(repo, "target", ".compass", at=target_at)
        write(repo, INDEX, index_doc(entry("SPEC-001-alpha", "Index text")))
        commit(repo, "index", ".compass", at=index_at)
        return repo

    def test_newer_side_follows_commit_times_down_to_one_second(self):
        """Adversarial where: comparing with <= instead of <, comparing dates
        instead of times, or swapping the sides tells a resync to overwrite
        the wrong text; equal times must be undecided, not a guess."""
        rows = {
            "target one second newer": (EPOCH + 1, EPOCH, "target"),
            "index one second newer": (EPOCH, EPOCH + 1, "index"),
            "equal times": (EPOCH, EPOCH, None),
            "target days newer": (EPOCH + 3 * 86400, EPOCH, "target"),
        }
        for name, (target_at, index_at, expected) in rows.items():
            with self.subTest(name):
                found = scan_index(self.seeded(target_at, index_at))
                self.assertEqual(len(found), 1, found)
                self.assertEqual(found[0]["class"], "index-drift")
                self.assertEqual(found[0]["newer"], expected)

    def test_uncommitted_index_line_has_no_newer_side(self):
        """Adversarial where: treating an uncommitted edit as time zero or
        as newest invents a verdict from a commit time that does not exist."""
        repo = self.seeded(EPOCH, EPOCH + 100)
        write(repo, INDEX, index_doc(entry("SPEC-001-alpha", "Edited, uncommitted")))
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["old_text"], "Edited, uncommitted")
        self.assertIsNone(found[0]["newer"])

    def test_target_time_is_the_summary_line_not_any_edit_to_the_file(self):
        """Adversarial where: using the target file's last commit makes a
        later body-only edit flip the verdict to "target", so a resync would
        overwrite a hand-edited index line that is newer than the summary."""
        repo = new_repo(self)
        write(repo, SPEC, doc("summary: Target text"))
        commit(repo, "target", ".compass", at=EPOCH)
        write(repo, INDEX, index_doc(entry("SPEC-001-alpha", "Hand edited")))
        commit(repo, "index", ".compass", at=EPOCH + 100)
        write(repo, SPEC, doc("summary: Target text", body="Body edited later."))
        commit(repo, "body", ".compass", at=EPOCH + 200)
        found = scan_index(repo)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["newer"], "index")


def lesson_file(status="active", score=6, summary="Plain summary",
                tags="[a, b]", escalated=None):
    front = [
        "---", f"status: {status}", "category: process", "area: testing",
        f"tags: {tags}", f"score: {score}", f"summary: {summary}",
    ]
    if escalated is not None:
        front.append(f"escalated: {escalated}")
    return front + ["---", "", "Body."]


def catalog_row(filename, status="active", score=6, summary='"Plain summary"',
                tags="[a, b]", escalated=None):
    row = [
        f'  - file: "{filename}"', f"    status: {status}",
        "    category: process", "    area: testing",
        f"    tags: {tags}", f"    score: {score}", f"    summary: {summary}",
    ]
    if escalated is not None:
        row.append(f"    escalated: {escalated}")
    return row


def catalog_vault(case, rows, lessons):
    """Repo whose catalog holds `rows` (line lists) and `lessons` {rel: lines}."""
    repo = new_repo(case)
    write(repo, CATALOG, ["lessons:"] + [line for row in rows for line in row])
    for rel, lines in lessons.items():
        write(repo, rel, lines)
    commit(repo, "seed", ".compass")
    return repo


LESSON_A = ".compass/lessons/LESSON-a.md"
LESSON_B = ".compass/lessons/hooks/LESSON-b.md"


class CatalogDriftTests(unittest.TestCase):
    def test_each_differing_field_is_reported_with_both_values(self):
        """Adversarial where: comparing only some fields, comparing the score
        as a string with padding, or reporting the row once for several
        differences hides which field went stale; one-off score is the
        boundary."""
        rows = {
            "score one off": (
                {"score": 7}, {"score": 6}, "score", "6", "7"),
            "status": (
                {"status": "retired"}, {"status": "active"},
                "status", "active", "retired"),
            "tags drop one": (
                {"tags": "[a]"}, {"tags": "[a, b]"}, "tags", "[a, b]", "[a]"),
            "tags reordered": (
                {"tags": "[b, a]"}, {"tags": "[a, b]"}, "tags", "[a, b]", "[b, a]"),
            "summary one char": (
                {"summary": "Plain summarx"}, {"summary": '"Plain summary"'},
                "summary", "Plain summary", "Plain summarx"),
            "escalated added to file": (
                {"escalated": "2026-01-02"}, {}, "escalated", None, "2026-01-02"),
        }
        for name, (file_kw, row_kw, field, old, current) in rows.items():
            with self.subTest(name):
                repo = catalog_vault(
                    self, [catalog_row("LESSON-a.md", **row_kw)],
                    {LESSON_A: lesson_file(**file_kw)})
                found = scan_catalog(repo)
                self.assertEqual(len(found), 1, found)
                rec = found[0]
                self.assertEqual(set(rec), KEYS)
                self.assertEqual(rec["class"], "catalog-drift")
                self.assertEqual(rec["file"], CATALOG)
                self.assertEqual(rec["field"], field)
                self.assertEqual(rec["target"], LESSON_A)
                self.assertEqual(rec["old_text"], old)
                self.assertEqual(rec["current_text"], current)
                self.assertIsNone(rec["newer"])

    def test_catalog_line_points_at_the_differing_field(self):
        """Adversarial where: reporting the row start, or a line counted from
        the wrong base, sends the human to a field that is not the stale
        one; the second row proves the offset accumulates."""
        rows = [catalog_row("LESSON-a.md"), catalog_row("LESSON-b.md", score=5)]
        repo = catalog_vault(self, rows, {
            LESSON_A: lesson_file(), LESSON_B: lesson_file(score=6)})
        found = scan_catalog(repo)
        self.assertEqual([(r["line"], r["field"], r["target"]) for r in found],
                         [(14, "score", LESSON_B)])

    def test_several_stale_fields_give_one_record_each(self):
        """Adversarial where: stopping at the first differing field hides
        that a row is stale in more than one place."""
        repo = catalog_vault(
            self, [catalog_row("LESSON-a.md", score=5, status="active")],
            {LESSON_A: lesson_file(score=7, status="retired")})
        found = scan_catalog(repo)
        self.assertEqual(sorted(r["field"] for r in found), ["score", "status"])

    def test_agreeing_rows_yield_no_record(self):
        """Adversarial where: a catalog row written by sync (quoted summary
        with escaped quotes, inline tag list, escalated) reported as drift,
        or a row-only `escalated` treated as stale, flags every row; a row
        keeps its own escalated when the file has none."""
        quoted = 'He said \\"go\\" now'
        rows = {
            "plain": ([catalog_row("LESSON-a.md")], lesson_file()),
            "quoted summary": (
                [catalog_row("LESSON-a.md", summary=f'"{quoted}"')],
                lesson_file(summary=f'"{quoted}"')),
            "escalated on both": (
                [catalog_row("LESSON-a.md", escalated="2026-01-02")],
                lesson_file(escalated="2026-01-02")),
            "escalated only on the row": (
                [catalog_row("LESSON-a.md", escalated="2026-01-02")],
                lesson_file()),
            "tags with extra spaces": (
                [catalog_row("LESSON-a.md", tags="[a,   b]")], lesson_file()),
        }
        for name, (catalog, lesson) in rows.items():
            with self.subTest(name):
                repo = catalog_vault(self, catalog, {LESSON_A: lesson})
                self.assertEqual(scan_catalog(repo), [])

    def test_row_without_a_lesson_file_is_missing(self):
        """Adversarial where: a row whose lesson was deleted or renamed gets
        skipped, or reported as drift against nothing; a lesson with the same
        stem but another filename must not satisfy it."""
        rows = [catalog_row("LESSON-a.md"), catalog_row("LESSON-gone.md")]
        repo = catalog_vault(self, rows, {
            LESSON_A: lesson_file(),
            ".compass/lessons/LESSON-gone-2.md": lesson_file()})
        found = scan_catalog(repo)
        self.assertEqual(len(found), 1, found)
        rec = found[0]
        self.assertEqual(set(rec), KEYS)
        self.assertEqual(rec["class"], "missing")
        self.assertEqual(rec["file"], CATALOG)
        self.assertEqual(rec["line"], 9)
        self.assertIsNone(rec["target"])
        self.assertIsNone(rec["field"])

    def test_nested_lesson_files_match_by_filename(self):
        """Adversarial where: looking only in the top lessons directory
        reports every domain lesson as missing."""
        repo = catalog_vault(
            self, [catalog_row("LESSON-b.md", score=4)],
            {LESSON_B: lesson_file(score=5)})
        found = scan_catalog(repo)
        self.assertEqual([(r["class"], r["field"], r["target"]) for r in found],
                         [("catalog-drift", "score", LESSON_B)])

    def test_lesson_without_a_row_and_absent_catalog_yield_nothing(self):
        """Adversarial where: reporting unlisted lessons duplicates what sync
        appends, and assuming the catalog file exists raises on a vault with
        none."""
        repo = catalog_vault(self, [], {LESSON_A: lesson_file()})
        self.assertEqual(scan_catalog(repo), [])
        bare = new_repo(self)
        write(bare, LESSON_A, lesson_file())
        commit(bare, "seed", ".compass")
        self.assertEqual(scan_catalog(bare), [])


if __name__ == "__main__":
    unittest.main()
