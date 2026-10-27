"""Tests for the plain words `compass validate`, `compass make-unit`'s report
and the hook status lines speak.

Adversarial themes: a finding that still leads with its code; a code left out
of the rendering because it was added to `validate.py` after the word list
was written; a rendering that matches a code by prefix instead of exactly;
a rewording that leaked into the findings `check_vault` returns to programs;
a report path (`make-unit`) that kept the old form while `validate` changed;
a hook status text that kept a coined term, or a rewrite that touched a
status text carrying none.

Words come from the Warning codes table of the plain-words research page and
moment 10 of the terminal-output research page.
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import make_unit, validate  # noqa: E402

PLUGIN = Path(__file__).resolve().parents[2]
VALIDATE_SOURCE = PLUGIN / "cli" / "commands" / "validate.py"
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"

SPEC_OK = (
    "---\ntitle: T\ntype: spec\nstatus: approved\narea: x\ntags: [a]\n"
    "created: 2026-06-14\nupdated: 2026-06-14\nsummary: \"a spec\"\n---\n\n"
)

# Every code the Warning codes table names, plus the block-link code validate
# also emits. The collector test below proves the source holds no others.
KNOWN_CODES = {
    "broken_wikilink", "ambiguous_wikilink", "frontmatter_error",
    "frontmatter_missing_field", "cap_exceeded", "active_done",
    "sizing_unrecorded", "sizing_orphaned_id", "folder_over_ceiling",
    "empty_scope", "taxonomy_hints", "unclassified_root_folder",
    "loop_misshapen", "broken_block_link",
}

# What the table's sentence for a code must say, as a lowercase fragment that
# separates it from the sentences of its neighbours. broken_block_link has no
# table row, so it carries no fragment.
SENTENCE_FRAGMENT = {
    "broken_wikilink": "does not exist",
    "ambiguous_wikilink": "more than one",
    "frontmatter_error": "cannot be read",
    "frontmatter_missing_field": "lacks",
    "cap_exceeded": "size limit",
    "active_done": "finished tasks",
    "sizing_unrecorded": "shape record",
    "sizing_orphaned_id": "shape record",
    "folder_over_ceiling": "propose",
    "empty_scope": "belongs",
    "taxonomy_hints": "filing hint",
    "unclassified_root_folder": "workstream",
    "loop_misshapen": "loop",
}

# Coined terms the Terms table replaces, found in prose a person reads.
COINED = [
    ("wikilink", re.compile(r"wikilink", re.I)),
    ("frontmatter", re.compile(r"frontmatter", re.I)),
    ("hot path", re.compile(r"hot[- ]path", re.I)),
    ("domain", re.compile(r"domain", re.I)),
    ("unit", re.compile(r"(?<![\w-])units?(?![\w-])", re.I)),
    ("sizing", re.compile(r"sizing", re.I)),
    ("taxonomy", re.compile(r"taxonomy", re.I)),
    ("sweep", re.compile(r"sweep", re.I)),
    ("Class here", re.compile(r"class[- ]here", re.I)),
]

TRAILING_CODE = re.compile(r"\s*\(([a-z]+(?:_[a-z]+)+)\)\s*$")


def codes_in_source():
    """Every `<code>: ` finding prefix validate.py's source can emit."""
    text = VALIDATE_SOURCE.read_text(encoding="utf-8")
    return set(re.findall(r'f?"([a-z]+(?:_[a-z]+)+): ', text))


def coined_in(text):
    return [label for label, pattern in COINED if pattern.search(text)]


def finding_lines(stream_text, label):
    """Lines of a report that carry one finding, label stripped."""
    out = []
    for line in stream_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(label):
            out.append(stripped[len(label):].strip())
    return out


class VaultCase(unittest.TestCase):
    def make_vault(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / ".compass"
        root.mkdir()
        (root / "index.md").write_text("# Index\n", encoding="utf-8")
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)
        if old is None:
            self.addCleanup(os.environ.pop, "CLAUDE_PROJECT_DIR", None)
        else:
            self.addCleanup(os.environ.__setitem__, "CLAUDE_PROJECT_DIR", old)
        return root

    def write(self, root, rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_validate(self, errors=None, warnings=None):
        """Run `validate.run`. With `errors`/`warnings` given, the vault check
        is replaced by those findings; otherwise the real check runs."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            if errors is None and warnings is None:
                code = validate.run([])
            else:
                with mock.patch.object(
                    validate, "check_vault", return_value=(errors or [], warnings or [])
                ):
                    code = validate.run([])
        return code, out.getvalue(), err.getvalue()


class ValidatePlainTests(VaultCase):
    def test_every_code_validate_can_emit_prints_as_a_sentence_ending_in_its_code(self):
        """Adversarial where: a code added to `validate.py` after the word
        list was written, or a code reworded only on the warning channel and
        not the error channel, keeps printing as `code: details`. The codes
        are collected from the source, so a new code that the rendering does
        not know fails here instead of staying jargon. Each row feeds one
        code through each channel and checks the line leads with its details
        or sentence, carries the table's sentence, holds no coined term, and
        ends with the code in brackets."""
        collected = codes_in_source()
        self.assertEqual(
            collected, KNOWN_CODES,
            "the source emits codes the word table does not name (or the collector lost one)",
        )
        for code in sorted(collected):
            for channel, label in (("warning", "warning"), ("error", "ERROR")):
                with self.subTest(code=code, channel=channel):
                    finding = f"{code}: probe/path.md"
                    errors = [finding] if channel == "error" else []
                    warnings = [finding] if channel == "warning" else []
                    _, _, err = self.run_validate(errors, warnings)
                    lines = finding_lines(err, label)
                    self.assertEqual(len(lines), 1, err)
                    line = lines[0]
                    self.assertFalse(line.startswith(code), line)
                    self.assertNotIn(f"{code}:", line)
                    tail = TRAILING_CODE.search(line)
                    self.assertIsNotNone(tail, f"no trailing (code) in: {line}")
                    self.assertEqual(tail.group(1), code)
                    self.assertIn("probe/path.md", line)
                    sentence = line[: tail.start()].replace("probe/path.md", " ")
                    self.assertGreaterEqual(len(sentence.split()), 4, line)
                    self.assertEqual(coined_in(sentence), [], line)
                    fragment = SENTENCE_FRAGMENT.get(code)
                    if fragment:
                        self.assertIn(fragment, sentence.lower(), line)

    def test_unrecognized_findings_print_unchanged(self):
        """Adversarial where: the rendering matches a code by prefix or
        rewrites every `word_word:` line, so a near-miss such as the plural
        `broken_wikilinks`, a code from another tool, or a finding with no
        code at all gets a sentence and a bracketed code it never earned.
        Rows are unknown findings and the exact text they must keep."""
        rows = [
            ("unknown code", "mystery_code: somewhere: odd"),
            ("plural near-miss of a known code", "broken_wikilinks: specs/a.md:1: [[x]]"),
            ("known code as a longer token", "broken_wikilink_extra: specs/a.md"),
            ("no code at all", "something went wrong in specs/a.md"),
        ]
        for name, finding in rows:
            for channel, label in (("warning", "warning"), ("error", "ERROR")):
                with self.subTest(row=name, channel=channel):
                    errors = [finding] if channel == "error" else []
                    warnings = [finding] if channel == "warning" else []
                    _, _, err = self.run_validate(errors, warnings)
                    self.assertEqual(finding_lines(err, label), [finding])

    def test_real_vault_findings_keep_location_exit_code_and_summary_line(self):
        """Adversarial where: the rewording drops the location the finding
        exists to give (file, line, link target), turns a warning into a
        failure or an error into a pass, or alters the `N error(s), M
        warning(s)` header and the `clean` line that scripts and humans
        already rely on. The vault holds one error and two kinds of warning,
        each with details a person needs to find the problem."""
        root = self.make_vault()
        self.write(root, "specs/SPEC-001-bad.md", "no frontmatter here\n")
        self.write(root, "specs/SPEC-002-src.md", SPEC_OK + "See [[SPEC-404-missing]].\n")
        self.write(root, "specs/SPEC-003-nosum.md", "---\ntitle: T\ntype: spec\nstatus: approved\n---\n")
        code, out, err = self.run_validate()
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("compass validate: 1 error(s), 6 warning(s)", err)

        errors = finding_lines(err, "ERROR")
        self.assertEqual(len(errors), 1, err)
        self.assertIn("specs/SPEC-001-bad.md", errors[0])
        self.assertTrue(errors[0].endswith("(frontmatter_error)"), errors[0])

        warnings = finding_lines(err, "warning")
        broken = [w for w in warnings if w.endswith("(broken_wikilink)")]
        self.assertEqual(len(broken), 1, warnings)
        self.assertIn("specs/SPEC-002-src.md", broken[0])
        self.assertIn("SPEC-404-missing", broken[0])
        missing = [w for w in warnings if w.endswith("(frontmatter_missing_field)")]
        self.assertEqual(len(missing), 5, warnings)
        for field in ("area", "tags", "created", "updated", "summary"):
            self.assertTrue(any(f"specs/SPEC-003-nosum.md" in w and field in w for w in missing), field)
        for finding in errors + warnings:
            self.assertIsNone(re.match(r"^[a-z]+(?:_[a-z]+)+:", finding), finding)

        only_warnings = self.make_vault()
        self.write(only_warnings, "specs/SPEC-002-src.md", SPEC_OK + "See [[SPEC-404-missing]].\n")
        code, out, err = self.run_validate()
        self.assertEqual(code, 0)
        self.assertIn("compass validate: 0 error(s), 1 warning(s)", err)

        clean = self.make_vault()
        self.write(clean, "specs/SPEC-001-ok.md", SPEC_OK)
        code, out, err = self.run_validate()
        self.assertEqual((code, out, err), (0, "compass validate: clean\n", ""))

    def test_check_vault_keeps_the_code_first_form_programs_read(self):
        """Adversarial where: the sentence is built where the finding is
        created instead of where it is printed, so every program reading
        `check_vault` (sync, make-unit, tests) loses the `code:` prefix it
        matches on. The vault produces one error and two codes of warning;
        each must still start with `<code>: ` and carry no trailing bracket."""
        root = self.make_vault()
        self.write(root, "specs/SPEC-001-bad.md", "no frontmatter here\n")
        self.write(root, "specs/SPEC-002-src.md", SPEC_OK + "See [[SPEC-404-missing]].\n")
        self.write(root, "specs/SPEC-003-nosum.md", "---\ntitle: T\ntype: spec\nstatus: approved\n---\n")
        errors, warnings = validate.check_vault(root)
        self.assertEqual(
            {f.split(":", 1)[0] for f in errors + warnings},
            {"frontmatter_error", "broken_wikilink", "frontmatter_missing_field"},
        )
        for finding in errors + warnings:
            self.assertIsNone(TRAILING_CODE.search(finding), finding)

    def test_make_unit_report_prints_the_sentences_validate_prints(self):
        """Adversarial where: `make-unit` keeps its own copy of the finding
        format, so the report shown right after a structural change still
        leads with `code:` while `compass validate` speaks plainly. A stray
        root folder gives a pre-existing finding; the make-unit line must
        equal the line `validate` prints for the same finding once the label
        is stripped."""
        root = self.make_vault()
        self.write(root, "weird_folder/stray.md", "# stray\n")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(
                make_unit.run(["core", "--reason", "grouping the tile work", "--apply"]), 0
            )
        report = out.getvalue()
        self.assertIn("validate:", report)
        self.assertNotIn("unclassified_root_folder:", report)
        unit_lines = [
            l for l in finding_lines(report, "warning") if "weird_folder" in l
        ]
        self.assertEqual(len(unit_lines), 1, report)
        self.assertTrue(unit_lines[0].endswith("(unclassified_root_folder)"), unit_lines[0])
        self.assertIn("workstream", unit_lines[0].lower())

        _, _, err = self.run_validate()
        validate_lines = [l for l in finding_lines(err, "warning") if "weird_folder" in l]
        self.assertEqual(unit_lines, validate_lines)

    def test_make_unit_report_renders_every_finding_channel(self):
        """Adversarial where: `make-unit` renders warnings through the new
        form but prints errors raw (or the reverse), since its report loop
        has one branch per channel. Both channels are fed one finding each."""
        root = self.make_vault()
        with mock.patch.object(
            validate, "check_vault",
            return_value=(["frontmatter_error: specs/a.md: no frontmatter"],
                          ["broken_wikilink: specs/a.md:3: [[gone]]"]),
        ):
            out = io.StringIO()
            with redirect_stdout(out):
                make_unit._report_vault_health(root)
        report = out.getvalue()
        self.assertIn("1 error(s), 1 warning(s)", report)
        errors = finding_lines(report, "ERROR")
        warnings = finding_lines(report, "warning")
        self.assertEqual(len(errors), 1, report)
        self.assertEqual(len(warnings), 1, report)
        self.assertTrue(errors[0].endswith("(frontmatter_error)"), errors[0])
        self.assertTrue(warnings[0].endswith("(broken_wikilink)"), warnings[0])
        self.assertIn("specs/a.md", errors[0])
        self.assertIn("gone", warnings[0])
        self.assertNotIn("frontmatter_error:", report)
        self.assertNotIn("broken_wikilink:", report)


class HookStatusTests(unittest.TestCase):
    def setUp(self):
        data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
        self.entries = []
        for event, groups in data.items():
            for group in groups:
                for hook in group.get("hooks", []):
                    self.entries.append(
                        (event, group.get("matcher"), hook.get("statusMessage"), hook)
                    )

    def status_for(self, event, matcher):
        found = [s for e, m, s, _ in self.entries if e == event and m == matcher]
        self.assertEqual(len(found), 1, f"{event}/{matcher}: {found}")
        return found[0]

    def test_loop_hook_lines_carry_the_agreed_wording_verbatim(self):
        """Adversarial where: the index-update and lesson-check status texts
        get a paraphrase near the agreed wording (a different verb, a
        trailing period, the old `.compass index`), so the loop shows a line
        the approved mockup never showed. Rows are the texts of moment 10;
        MultiEdit runs the same sync, so it reads the same as Write and
        Edit."""
        rows = [
            ("PostToolUse", "Write|write", "Updating the document index"),
            ("PostToolUse", "Edit|edit", "Updating the document index"),
            ("PostToolUse", "MultiEdit", "Updating the document index"),
            ("Stop", None, "Checking whether a lesson is worth recording"),
        ]
        for event, matcher, expected in rows:
            with self.subTest(event=event, matcher=matcher):
                self.assertEqual(self.status_for(event, matcher), expected)

    def test_status_texts_hold_no_coined_term_and_uncoined_ones_stay(self):
        """Adversarial where: a sweep over the status texts leaves one coined
        term behind (the teammate `signal`, the stranded `capture
        opportunity`) or rewrites a text that carried none (the guard, the
        context check, the update check, the subagent report), changing what
        the loop shows for no reason. Every hook keeps a status text and the
        count of hooks is unchanged."""
        self.assertEqual(len(self.entries), 10)
        coined = [
            ("capture opportunity", re.compile(r"capture opportunit", re.I)),
            ("signal", re.compile(r"signal", re.I)),
            (".compass index", re.compile(r"\.compass index", re.I)),
        ]
        for event, matcher, status, _ in self.entries:
            with self.subTest(event=event, matcher=matcher):
                self.assertTrue(status and status.strip(), "a hook lost its status text")
                for label, pattern in coined:
                    self.assertIsNone(pattern.search(status), f"{label} in {status!r}")
        unchanged = [
            ("PreToolUse", "Bash|Write|Edit|MultiEdit", "Compass guard"),
            ("PostToolUse", None, "Checking context usage"),
            ("SessionStart", "startup", "Checking for a Compass update"),
            (
                "SubagentStop",
                "builder|tester|debug|validator|planner|researcher|reviewer|spec-writer|pr-describe",
                "Capturing subagent report",
            ),
        ]
        for event, matcher, expected in unchanged:
            with self.subTest(event=event, matcher=matcher):
                self.assertEqual(self.status_for(event, matcher), expected)

    def test_rewording_status_texts_leaves_every_hook_command_alone(self):
        """Adversarial where: the edit that rewords a `statusMessage` also
        reaches the `command` beside it (a replace-all over the file), so a
        hook runs a subcommand that no longer exists. Every hook still runs
        a `compass` command, and the commands that produce the loop lines
        are the ones that did before."""
        for event, matcher, status, hook in self.entries:
            with self.subTest(event=event, matcher=matcher):
                self.assertEqual(hook.get("type"), "command")
                self.assertIn("/cli/compass", hook["command"])
        by_status = {s: h["command"] for _, _, s, h in self.entries}
        for status, subcommand in (
            ("Updating the document index", " sync --hook"),
            ("Checking whether a lesson is worth recording", " capture-check --hook"),
        ):
            with self.subTest(status=status):
                self.assertIn(status, by_status)
                self.assertIn(subcommand, by_status[status])


if __name__ == "__main__":
    unittest.main()
