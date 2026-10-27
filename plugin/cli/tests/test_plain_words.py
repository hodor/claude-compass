"""Tests for the plain words `compass doctor`, `compass unit-check` and the
command list speak.

Adversarial themes: a coined house term surviving in one row, one detail
string, one fix hint or one help line while the rest were reworded; a
rewording that touched a command name or an exit code; a replacement word that
reached the code a program reads instead of the sentence a person reads.
Terms and their replacements come from the Terms table of the plain-words
research page; command names, flags, file names and backticked commands are
read by programs and stay.
"""

import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
import hostlib  # noqa: E402
import maincli  # noqa: E402
from commands import doctor, unit_check  # noqa: E402

# A coined term and the pattern that finds it in prose a person reads. The
# lookarounds keep command names (`make-unit`, `unit-check`), file names
# (`hooks.json`) and identifiers with underscores out of the match.
REPLACED_TERMS = [
    ("unit-promotion", re.compile(r"unit[- ]promotion", re.I)),
    ("unit", re.compile(r"(?<![\w-])units?(?![\w-])", re.I)),
    ("type-spread", re.compile(r"type[- ]spread", re.I)),
    ("capture posture", re.compile(r"capture posture", re.I)),
    ("ledger", re.compile(r"ledger", re.I)),
    ("materialization", re.compile(r"materializ", re.I)),
    ("host", re.compile(r"(?<![\w-])hosts?(?![\w-])", re.I)),
    ("overlay", re.compile(r"overlay", re.I)),
    ("NEVER USED", re.compile(r"NEVER USED")),
    ("capture opportunity", re.compile(r"capture opportunit", re.I)),
    ("capture signal", re.compile(r"capture signal", re.I)),
    ("detached worker", re.compile(r"detached[- ]worker", re.I)),
    ("hook", re.compile(r"(?<!\w)hooks?(?![\w.])", re.I)),
    ("sweep", re.compile(r"sweep", re.I)),
    ("admission control", re.compile(r"admission control", re.I)),
    ("elaborat", re.compile(r"elaborat", re.I)),
    ("rolling wave", re.compile(r"rolling wave", re.I)),
    ("surfaced-but-uncited", re.compile(r"surfaced-but-uncited", re.I)),
    ("trackable", re.compile(r"trackable", re.I)),
]

# Programs read these: backticked commands, `compass <command>` mentions and
# `--flags` keep their words.
PROGRAM_READ = [
    re.compile(r"`[^`]*`"),
    re.compile(r"\bcompass [a-z][a-z-]*"),
    re.compile(r"(?<![\w-])--[\w-]+"),
]


def person_text(text):
    for pattern in PROGRAM_READ:
        text = pattern.sub(" ", text)
    return text


def coined_terms_in(text):
    visible = person_text(text)
    return [label for label, pattern in REPLACED_TERMS if pattern.search(visible)]


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def set_env(test_case, name, value):
    old = os.environ.get(name)
    os.environ[name] = value
    test_case.addCleanup(
        lambda: os.environ.__setitem__(name, old) if old is not None else os.environ.pop(name, None)
    )


def pin_dsh(test_case, present):
    test_case.addCleanup(setattr, hostlib, "dsh_available", hostlib.dsh_available)
    hostlib.dsh_available = lambda: present


HOOK_COMMANDS = {
    "PreToolUse": "guard",
    "PostToolUse": "sync",
    "Stop": "capture-check",
    "SubagentStop": "capture-signal",
    "TeammateIdle": "capture-signal",
}


def make_project(test_case, dsh=False):
    """A project whose install passes every doctor row: plugin.yaml, lessons
    catalog, registered hooks, a CLI with the hook commands, agents, skills."""
    pin_dsh(test_case, dsh)
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    base = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, base, True)
    (base / "home").mkdir()
    (base / "cfg").mkdir()
    write_text(base / "cfg" / "settings.json", json.dumps({"cleanupPeriodDays": 3650}))
    set_env(test_case, "HOME", str(base / "home"))
    set_env(test_case, "USERPROFILE", str(base / "home"))
    set_env(test_case, "CLAUDE_CONFIG_DIR", str(base / "cfg"))
    set_env(test_case, "CLAUDE_PROJECT_DIR", str(tmp))
    set_env(test_case, "COMPASS_OBSIDIAN_CONFIG", str(base / "no-obsidian.json"))
    set_env(test_case, "DSH_HOME", str(base / "dsh-home"))

    write_text(tmp / ".compass" / "meta" / "plugin.yaml",
               "plugin:\n  name: compass\n  version: 0.4.0\n")
    write_text(tmp / ".compass" / "meta" / "lessons-catalog.yaml", "lessons: []\n")
    events = {
        event: [{"hooks": [{"type": "command", "command":
                 f'python "$CLAUDE_PROJECT_DIR/.claude/cli/compass" {cmd} --hook'}]}]
        for event, cmd in HOOK_COMMANDS.items()
    }
    write_text(tmp / ".claude" / "settings.json", json.dumps({"hooks": events}))
    write_text(tmp / ".claude" / "hooks" / "hooks.json", json.dumps({"hooks": {}}))
    cli = tmp / ".claude" / "cli"
    names = sorted(set(HOOK_COMMANDS.values()))
    write_text(cli / "commands" / "__init__.py", "")
    write_text(cli / "maincli.py", "COMMAND_SPECS = [\n"
               + "\n".join(f'    ("{n}", "help"),' for n in names) + "\n]\n")
    for name in names:
        write_text(cli / "commands" / (name.replace("-", "_") + ".py"),
                   "def run(args):\n    return 0\n")
    write_text(tmp / ".claude" / "agents" / "builder.md", "")
    (tmp / ".claude" / "skills" / "build").mkdir(parents=True)
    return tmp


def vault_doc(type_, deps=()):
    dep_items = ", ".join(f'"[[{d}]]"' for d in deps)
    return (f"---\ntitle: T\ntype: {type_}\nstatus: active\n"
            f"depends_on: [{dep_items}]\n---\n\nbody\n")


def add_unit_candidate(project):
    vault = project / ".compass"
    write_text(vault / "specs" / "SPEC-001-core.md",
               "---\ntitle: Core\ntype: spec\nstatus: approved\n---\n\nbody\n")
    write_text(vault / "plans" / "PLAN-001-impl.md", vault_doc("plan", ["SPEC-001-core"]))
    write_text(vault / "decisions" / "ADR-001-choice.md",
               vault_doc("decision", ["SPEC-001-core"]))
    write_text(vault / "research" / "RESEARCH-notes.md",
               vault_doc("research", ["SPEC-001-core"]))


def add_usage_record(project):
    write_text(project / ".compass" / "meta" / "usage.yaml",
               "since: 2020-01-01\nusage:\n  sync:\n    count: 3\n    last: 2020-01-02\n")


def add_local_overlay(project):
    write_text(project / ".compass" / "meta" / "local" / "agents" / "builder.md",
               "Project-local addendum.\n")


def add_worker_ledger(project):
    root = project / ".compass"
    for opp in ("alpha", "beta", "gamma"):
        capturelib.log_event(root, "worker-started", id=f"OPP-{opp}", pid=1)
    capturelib.log_event(root, "worker-finished", id="OPP-alpha")
    capturelib.log_event(root, "worker-failed", id="OPP-beta", reason="exit 1")
    capturelib.log_event(root, "fallback-fired", id="OPP-gamma", channel="quiet")
    state = capturelib.load_state(root)
    state["no_headless_at"] = capturelib._iso(capturelib._now())
    capturelib.save_state(root, state)


def run_doctor(args=()):
    out = io.StringIO()
    with redirect_stdout(out):
        code = doctor.run(list(args))
    return code, out.getvalue()


def doctor_rows(args=("--json",)):
    code, out = run_doctor(args)
    return code, json.loads(out)["checks"]


class DoctorPlainWordsTests(unittest.TestCase):
    def test_no_doctor_row_name_detail_or_fix_uses_a_replaced_term(self):
        """Adversarial where: one doctor row, detail string or fix hint keeps
        a coined term (unit-promotion, worker ledger, capture posture, host
        materializations, overlay, NEVER USED, detached worker) while its
        neighbours were reworded. Every state that changes a row's text is a
        fixture: a clean install, a candidate, a usage record, a local
        addition, a populated run log, a two-tool install with nothing
        installed for the second tool, and a broken install. The plain
        `doctor` listing and the `--json` rows are both checked, since each
        renders the text separately."""

        def clean(test):
            return make_project(test)

        def with_candidate(test):
            project = make_project(test)
            add_unit_candidate(project)
            return project

        def with_usage(test):
            project = make_project(test)
            add_usage_record(project)
            return project

        def with_overlay(test):
            project = make_project(test)
            add_local_overlay(project)
            return project

        def with_run_log(test):
            project = make_project(test)
            add_worker_ledger(project)
            return project

        def two_tools_uninstalled(test):
            return make_project(test, dsh=True)

        def broken(test):
            project = make_project(test)
            (project / ".claude" / "settings.json").unlink()
            (project / ".compass" / "meta" / "plugin.yaml").unlink()
            return project

        fixtures = {
            "clean install": clean,
            "unit candidate": with_candidate,
            "usage record": with_usage,
            "local addition": with_overlay,
            "run log with failure, fallback and latch": with_run_log,
            "second tool uninstalled": two_tools_uninstalled,
            "broken install": broken,
        }
        for name, build in fixtures.items():
            with self.subTest(fixture=name):
                build(self)
                _, rows = doctor_rows()
                self.assertTrue(rows)
                offenders = [
                    (row["check"], field, coined_terms_in(str(row.get(field, ""))))
                    for row in rows for field in ("check", "detail", "fix")
                    if coined_terms_in(str(row.get(field, "")))
                ]
                self.assertEqual(offenders, [])
                _, listing = run_doctor(())
                self.assertEqual(coined_terms_in(listing), [], listing)

    def test_rows_that_named_a_coined_term_carry_the_agreed_replacement(self):
        """Adversarial where: the coined term is dropped but the row loses the
        meaning the plain words carry, or the replacement lands on the wrong
        row. Each row below is found by the replacement phrase in its name,
        so a row reworded to some other phrase, or a row deleted, is caught."""
        project = make_project(self, dsh=True)
        add_unit_candidate(project)
        add_usage_record(project)
        add_local_overlay(project)
        add_worker_ledger(project)
        _, rows = doctor_rows()
        names = [row["check"].lower() for row in rows]
        expected = [
            "workstreams that could get their own folder",
            "commands you have not run",
            "local additions",
            "background helper log",
            "how lesson recording is set up",
            "install for each tool",
        ]
        for phrase in expected:
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    sum(phrase in name for name in names), 1,
                    f"{phrase!r} not the name of exactly one row in {names}")

    def test_unit_candidate_row_keeps_its_candidate_names_and_unit_check_hint(self):
        """Adversarial where: rewording the row swallows the program-read
        parts of it: the fix hint must still name the `compass unit-check`
        command and the detail must still name the candidate (`core`), so a
        reader can act on the row."""
        project = make_project(self)
        add_unit_candidate(project)
        _, rows = doctor_rows()
        row = next(r for r in rows if "workstream" in r["check"].lower())
        self.assertEqual(row["status"], "WARN")
        self.assertIn("compass unit-check", row["fix"])
        self.assertIn("core", row["detail"])

    def test_doctor_exit_codes_are_unchanged_on_clean_and_broken_installs(self):
        """Adversarial where: rewording a row's status or message changes
        which rows count as FAIL. A clean install must still exit 0 with no
        FAIL row, and an install missing its hook registration and
        plugin.yaml must still exit 1 with FAIL rows."""
        make_project(self)
        code, rows = doctor_rows()
        self.assertEqual(code, 0)
        self.assertNotIn("FAIL", [row["status"] for row in rows])

        project = make_project(self)
        (project / ".claude" / "settings.json").unlink()
        (project / ".compass" / "meta" / "plugin.yaml").unlink()
        code, rows = doctor_rows()
        self.assertEqual(code, 1)
        self.assertIn("FAIL", [row["status"] for row in rows])


class UnitCheckPlainWordsTests(unittest.TestCase):
    def report(self, project):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(unit_check.run([]), 0)
        return out.getvalue()

    def test_candidate_report_uses_plain_words_and_keeps_the_make_unit_command(self):
        """Adversarial where: the report keeps `type-spread` or `unit`, or the
        rewording rewrites the runnable `compass make-unit <name> <paths>`
        line a person copies, which must keep the command name, the candidate
        name and every member path exactly."""
        project = make_project(self)
        add_unit_candidate(project)
        text = self.report(project)
        self.assertEqual(coined_terms_in(text), [], text)
        self.assertIn("kinds of document tied to one spec", text)
        self.assertIn(
            "compass make-unit core decisions/ADR-001-choice.md "
            "plans/PLAN-001-impl.md research/RESEARCH-notes.md "
            "specs/SPEC-001-core.md",
            text)

    def test_empty_and_conflicting_reports_use_plain_words(self):
        """Adversarial where: the two report shapes written apart from the
        candidate list keep a coined term: the line printed when no spec
        spreads over enough kinds of document, and the conflict note printed
        when two candidates claim the same member."""
        project = make_project(self)
        write_text(project / ".compass" / "specs" / "SPEC-001-core.md",
                   "---\ntitle: Core\ntype: spec\nstatus: approved\n---\n\nbody\n")
        empty = self.report(project)
        self.assertIn("no candidates", empty)
        self.assertEqual(coined_terms_in(empty), [], empty)

        vault = project / ".compass"
        for spec in ("SPEC-001-core", "SPEC-002-other"):
            write_text(vault / "specs" / f"{spec}.md",
                       "---\ntitle: S\ntype: spec\nstatus: approved\n---\n\nbody\n")
            write_text(vault / "plans" / f"PLAN-{spec[5:8]}-p.md", vault_doc("plan", [spec]))
            write_text(vault / "research" / f"RESEARCH-{spec[5:8]}.md",
                       vault_doc("research", [spec]))
        write_text(vault / "decisions" / "ADR-001-shared.md",
                   vault_doc("decision", ["SPEC-001-core", "SPEC-002-other"]))
        conflict = self.report(project)
        self.assertIn("conflict", conflict)
        self.assertIn("decisions/ADR-001-shared.md", conflict)
        self.assertEqual(coined_terms_in(conflict), [], conflict)


class CommandListPlainWordsTests(unittest.TestCase):
    def test_no_help_line_uses_a_replaced_term(self):
        """Adversarial where: one of the one-line helps keeps a coined term
        (sweep, overlay, hook, detached worker, capture opportunity, NEVER
        USED, ledger, admission control, unit) after the others were
        reworded. Each help line is judged on its own, so the failure names
        the command."""
        for name, help_line in maincli.COMMAND_SPECS:
            with self.subTest(command=name):
                self.assertEqual(coined_terms_in(help_line), [], help_line)

    def test_replaced_words_reach_the_help_of_the_commands_that_named_them(self):
        """Adversarial where: the coined term is deleted from a help line but
        the plain word is never written, leaving a line that no longer says
        what the command does. Each pair is a command and the agreed phrase
        its help carries in place of the coined term."""
        helps = dict(maincli.COMMAND_SPECS)
        expected = {
            "overlay": "local additions",
            "usage": "commands you have not run",
            "touched": "start-here size check",
            "admit-check": "start-here",
            "unit-check": "workstream",
            "sweep": "done list",
            "sync": "done list",
        }
        for command, phrase in expected.items():
            with self.subTest(command=command):
                self.assertIn(phrase, helps[command].lower())

    def test_command_names_and_the_printed_list_are_unchanged(self):
        """Adversarial where: rewording help lines renames or drops a command.
        Every name registered before the rewording must still be registered,
        in the same relative order, and `compass --help` must still print each
        one."""
        before = [
            "guard", "sync", "sweep", "self-update", "validate", "fix-frontmatter",
            "next-num", "usage", "graph", "overlay", "tree", "hot-path", "promote",
            "demote", "unit-check", "make-domain", "make-unit", "move", "placement",
            "touched", "admit-check", "capture-bug", "file-bugs", "resolve-model",
            "models", "apply-models", "decisions", "coverage", "capture-signal",
            "capture-note", "capture-check", "context-check", "capture-stats",
            "capture-close", "capture-worker", "doctor", "lessons", "lesson-coverage",
            "test-checkpoint", "test-smells", "sizing", "sources", "sessions", "clone",
            "loop", "review", "retention",
        ]
        now = [name for name, _ in maincli.COMMAND_SPECS]
        self.assertEqual([n for n in now if n in before], before)
        out = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(out):
            maincli.main(["--help"])
        text = out.getvalue()
        for name in before:
            with self.subTest(command=name):
                self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
