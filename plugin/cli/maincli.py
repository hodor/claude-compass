"""compass CLI entry point: argument dispatch and exit-code policy.

The hook runtime invokes `compass sync` in the path of the user's vault write.
A command hook that exits 2 *blocks that write*, so this module guarantees the
process never exits 2: argparse's own error exit is clamped, the exit helpers
clamp, and the dispatch catch-all returns 1 on any exception.
"""

import argparse
import sys

EXIT_OK = 0
EXIT_ERROR = 1

# (name, help) for every subcommand. Handlers live in `commands/<name>.py`
# and expose `run(args)`; a command whose module is absent reports
# not-implemented rather than crashing.
COMMAND_SPECS = [
    ("guard", "Automatic step before a tool runs: deny a tool call that would delete or discard "
              "(Bash rm/git discard, a Write that empties or guts, a blanking Edit)."),
    ("sync", "Regenerate index.md + tag-index.yaml, move done tasks from active.md to the done list, check size limits, clean tmp logs. Automatic-step entry point."),
    ("sweep", "Move finished tasks from active.md to the done list (archive/done.md), whole sections when fully done (dry-run; --apply to write)."),
    ("self-update", "Refresh this project's Compass install from its recorded source; sha-gated, throttled, silent unless it updated. SessionStart automatic-step entry point."),
    ("validate", "Check links, properties, and the start-here size limit. Non-zero exit on any defect."),
    ("fix-frontmatter", "Add missing properties / core fields to artifacts (dry-run; --apply to write)."),
    ("next-num", "Print the next local artifact number for a type."),
    ("usage", "Report the per-command invocation record: run by judgment, run by an automatic step, and commands you have not run."),
    ("graph", "orphans | hubs [--top N] | impact <name> [--depth N] - link-graph queries computed from the markdown at invocation, every answer naming its edges."),
    ("overlay", "List or re-apply local additions from .compass/meta/local/ onto shipped agents, rules, and skills (list-only; --apply to write)."),
    ("tree", "Render every artifact under every type dir and workstream folder with its summary, indented by depth - the whole vault at a glance, computed at invocation."),
    ("hot-path", "Print the start-here files' token count against the limit."),
    ("promote", "Turn a spec file into a folder and rewrite inbound links (dry-run; --apply to write)."),
    ("demote", "Turn a childless spec folder back into a file, the inverse of promote (dry-run; --apply to write)."),
    ("unit-check", "Report workstreams that could get their own folder: 3+ kinds of document tied to one spec via depends_on."),
    ("make-domain", "Create a topic folder with its index.md saying what belongs in it, inside a type dir, at any depth; --undo removes an empty one (dry-run; --apply to write)."),
    ("make-unit", "Create a workstream folder, optionally git-moving named artifacts into it and rewriting the root index; --undo reverses it (dry-run; --apply to write)."),
    ("move", "Git-move artifacts into a topic folder or back to a type-dir root, rewriting inbound path-qualified links vault-wide (dry-run; --apply to write)."),
    ("placement", "Report where an artifact could sit in its type dir's taxonomy: candidate parents, pairs, topic folders, redirects and hint paths, each with its evidence; --hints reports every pending filing hint (read-only)."),
    ("touched", "Record a working-set marker for the start-here size check."),
    ("admit-check", "Exit 0/1 for whether a spec may join the start-here files."),
    ("capture-bug", "Record a Compass bug locally (deduped by fingerprint) for later filing."),
    ("file-bugs", "File captured Compass bugs as deduplicated GitHub issues (dry-run; --apply to create)."),
    ("resolve-model", "Print an agent's resolved model and effort (result on stdout, warnings on stderr)."),
    ("models", "Print the full resolved model/effort roster with the winning source per agent."),
    ("apply-models", "Rewrite model:/effort: frontmatter of the installed Compass agent files from the resolved table."),
    ("decisions", "List a document's D-NN decisions with flags for which the plan must cover; exit 1 on a format mismatch."),
    ("coverage", "Check a plan carries every decision of its sources that it must cover; exit 1 on any gap."),
    ("capture-signal", "Record a subagent-captures file and a hint that a lesson is worth recording from SubagentStop event JSON. Automatic-step entry point."),
    ("capture-note", "Record an agent's in-flight observation as lesson evidence and a strong hint; the background helper judges it at the next Stop."),
    ("capture-check", "Bump the turn counter, evaluate due(), and emit the Stop block contract when it is a moment to record a lesson. Automatic-step entry point."),
    ("context-check", "Automatic step after a tool runs: measure the main session's context from its transcript and halt once at 80%% and once more at 95%% of the window, suggesting /compass:handoff."),
    ("capture-stats", "Report moments to record a lesson opened, fire rate, write rate, and per-trigger breakdown from the lesson recording trace log."),
    ("capture-close", "Close a moment to record a lesson with an outcome and candidate/written/recurrence/rejected/revised/archived/error counts."),
    ("capture-worker", "Run the extract-lessons pass against a moment to record a lesson in a spawned headless child; writes only worker-finished/worker-failed run log rows. Background helper entry point."),
    ("doctor", "Diagnose install drift: plugin.yaml, automatic step registration, CLI completeness, agents/skills, lessons catalog. Exit 1 on any FAIL."),
    ("lessons", "Ranked catalog rows for an area, tag set, free text, or a document. Exit 1 on a malformed catalog row or missing catalog."),
    ("lesson-coverage", "Report cited, relevant-but-not-cited, and unresolvable lesson citations for a plan's `lessons:` fields. Advisory: exit 1 only on an unresolvable citation."),
    ("test-checkpoint", "record | verify | open-ids | cycle for pre-build failing-test checkpoints, tamper-evident against git. Never exits 2."),
    ("test-smells", "AST-based test-smell checks over test files: empty test, duplicate assert, literal-only assertion (gate), assertion-free (advisory). Exit 1 on any gate finding, never 2."),
    ("sizing", "stats reports the sizing-log.yaml decision/correction record: by shape, by provenance, and a qualified correction rate."),
    ("sources", "Print the curated research-source catalog; --check classifies each scripted entry by response body shape (--live to probe for real)."),
    ("sessions", "list | show | record - rank the project's past sessions that finished a feature (read from Claude Code's transcripts in place), print a kept clone as text, log a clone run's outcome."),
    ("clone", "Run a headless, non-persisted fork of old sessions that writes the lessons each learned to a lesson file in ~/.compass/sessions; --discard keeps no transcript."),
    ("loop", "new | status | activate | pause | resume | review | run | check | baseline | schedule | reconcile - control loops: a sensor, a controller and an actuator that move the project toward an end state under a budget."),
    ("review", "Put a document in front of the human in Obsidian through the Compass Review plugin and wait for the verdict; --no-wait returns after sending, --status lists pending reviews."),
    ("retention","Report the effective cleanupPeriodDays (how long Claude Code keeps sessions); --set N writes it to the user's settings.json."),
]


def _try_capture(command, exc):
    """Record an unexpected CLI crash for later GitHub-issue filing. Best-effort:
    never let bug capture itself raise."""
    try:
        import bugs
        import vaultlib
        bugs.capture_exception(vaultlib.find_vault_root(), command, exc)
    except Exception:
        pass


def cli_ok(message=None):
    if message:
        sys.stdout.write(message + "\n")
    return EXIT_OK


def cli_err(message=None, code=EXIT_ERROR):
    # The one place the never-exit-2 rule lives for command results: exit 2
    # would block the user's write, so any caller asking for 2 gets 1.
    if code == 2:
        code = EXIT_ERROR
    if message:
        sys.stderr.write(message + "\n")
    return code


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that never exits 2, so a malformed invocation in the
    hook path cannot block the user's write."""

    def exit(self, status=0, message=None):
        if message:
            sys.stderr.write(message)
        if status == 2:
            status = EXIT_ERROR
        sys.exit(status)


VALID_COMMANDS = {name for name, _ in COMMAND_SPECS}


def build_parser():
    """Top-level parser, used only to render `compass --help`. Command args are
    not parsed here - they are passed to the command verbatim (see `main`), so a
    command can accept its own flags like `sync --hook`."""
    parser = _Parser(prog="compass", description="Compass vault bookkeeping CLI.")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, help_text in COMMAND_SPECS:
        sub.add_parser(name, help=help_text, add_help=False)
    return parser


def dispatch(name, args):
    module_name = "commands." + name.replace("-", "_")
    try:
        module = __import__(module_name, fromlist=["run"])
    except ImportError:
        return cli_err(f"compass {name}: not implemented yet")
    from commands import usage
    usage.record(name)
    return module.run(args)


def _escape_unencodable_output():
    """Print a character the console's encoding lacks as a backslash escape.
    A Windows console runs cp1252, which has no box-drawing or arrow glyph."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _escape_unencodable_output()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        build_parser().print_help()
        return EXIT_OK
    if argv[0] in ("-h", "--help"):
        build_parser().parse_args(["--help"])  # prints help, exits 0
        return EXIT_OK

    command, rest = argv[0], argv[1:]
    if command not in VALID_COMMANDS:
        cli_err(f"compass: unknown command '{command}'")
        build_parser().print_help(sys.stderr)
        return EXIT_ERROR
    try:
        return dispatch(command, rest)
    except Exception as exc:  # never surface as a crash/exit-2 that blocks a write
        _try_capture(command, exc)
        return cli_err(f"compass {command}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
