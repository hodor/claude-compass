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
    ("sync", "Regenerate index.md + tag-index.yaml, check caps, clean tmp logs. Hook entry point."),
    ("validate", "Check wikilinks, frontmatter, and the hot-path cap. Non-zero exit on any defect."),
    ("fix-frontmatter", "Add missing frontmatter / core fields to artifacts (dry-run; --apply to write)."),
    ("next-num", "Print the next local artifact number for a type."),
    ("tree", "Render the hierarchical spec/folder tree."),
    ("hot-path", "Print the hot-path token count against the cap."),
    ("promote", "Move a flat spec into a folder and rewrite inbound wikilinks."),
    ("unit-check", "Report unit-promotion candidates: 3+ artifact types tracing to one spec via depends_on."),
    ("make-unit", "Create a unit folder and git-move named artifacts into it, rewriting the root index (dry-run; --apply to write)."),
    ("clean-tmp", "Delete extraction logs older than 30 days."),
    ("touched", "Record a working-set marker for admission control."),
    ("admit-check", "Exit 0/1 for whether a spec may enter the hot path."),
    ("capture-bug", "Record a Compass bug locally (deduped by fingerprint) for later filing."),
    ("file-bugs", "File captured Compass bugs as deduplicated GitHub issues (dry-run; --apply to create)."),
    ("resolve-model", "Print an agent's resolved model and effort (result on stdout, warnings on stderr)."),
    ("models", "Print the full resolved model/effort roster with the winning source per agent."),
    ("apply-models", "Rewrite model:/effort: frontmatter of the installed Compass agent files from the resolved table."),
    ("decisions", "List a document's D-NN decisions with trackable flags; exit 1 on a format mismatch."),
    ("coverage", "Check a plan claims every trackable decision of its sources; exit 1 on any gap."),
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
    return module.run(args)


def main(argv=None):
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
