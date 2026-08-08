"""`compass test-smells <path>... [--json] [--advisory-only]` - the
decidable admission filter over Python test files.

Runs the four checks in `testsmellslib` (empty test, duplicate assert,
literal-only assertion - all gate; assertion-free - advisory) over every
file resolved from the given paths. A file argument is checked directly; a
directory argument is walked and a `.py` file inside it is checked only
when it carries the content signal `testsmellslib.discover` requires - it
defines at least one `test_*` function or a `unittest.TestCase` subclass
(LESSON-type-dir-discovery-needs-content-signal). A file that fails to
parse is reported as a `parse-error` finding (gate) rather than skipped or
crashing.

Output is one row per finding: file, line, test, check, severity, and an
optional detail. `--json` prints the finding list as JSON and nothing
else, so the stdout stream is valid JSON on its own; the default is an
aligned table followed by a `summary:` line. `--advisory-only` reports the
same findings but never fails the run - useful for reporting rather than
gating.

Exit 1 when any gate finding is present and `--advisory-only` was not
given; exit 0 otherwise (a clean tree, or `--advisory-only` regardless of
what was found). Never exits 2.
"""

import json
import sys

import testsmellslib

USAGE = "usage: compass test-smells <path>... [--json] [--advisory-only]"


def _parse_args(args):
    """Parse flags into an options dict. Returns `(options, error)`, with
    exactly one side set."""
    paths, json_out, advisory_only = [], False, False
    for arg in args:
        if arg == "--json":
            json_out = True
        elif arg == "--advisory-only":
            advisory_only = True
        elif arg.startswith("--"):
            return None, f"unknown flag {arg}"
        else:
            paths.append(arg)
    if not paths:
        return None, "at least one path is required"
    return {"paths": paths, "json": json_out, "advisory_only": advisory_only}, None


def format_report(findings):
    if not findings:
        return "compass test-smells: no findings"
    header = ("file", "line", "test", "check", "severity", "detail")
    table = [header]
    for f in findings:
        table.append((
            str(f["file"]), str(f["line"]), f["test"] or "-",
            f["check"], f["severity"], f["detail"] or "",
        ))
    widths = [max(len(row[c]) for row in table) for c in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip()
        for row in table
    )


def run(args):
    options, error = _parse_args(args)
    if error:
        sys.stderr.write(f"compass test-smells: {error}\n{USAGE}\n")
        return 1

    findings = testsmellslib.run_checks(options["paths"])
    gate_findings = [f for f in findings if f["severity"] == testsmellslib.GATE]
    fails = bool(gate_findings) and not options["advisory_only"]

    if options["json"]:
        sys.stdout.write(json.dumps(findings) + "\n")
        return 1 if fails else 0

    advisory_count = len(findings) - len(gate_findings)
    status = "FAIL" if fails else "PASS"
    sys.stdout.write(format_report(findings) + "\n")
    sys.stdout.write(
        f"summary: {len(findings)} finding(s) ({len(gate_findings)} gate, "
        f"{advisory_count} advisory) -> {status}\n"
    )
    return 1 if fails else 0
