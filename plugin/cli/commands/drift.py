"""`compass drift [--print | --apply] [--base-from blame|add]` - find vault text that no
longer matches the source it restates.

Three scans run against the vault of the current project (`driftlib`): code
references (`path:N`) against git history, index lines against the `summary`
of the document each links, and lesson-catalog rows against their lesson
files. Every record the scans return is a finding except the classes
`unchanged` and `changed-elsewhere`.

A run with findings writes `.compass/archive/drift/DRIFT-<UTC>.md`: a count
per class followed by one table row per finding (citing file, line, base
commit, what is cited, old text, current text, proposal). A report file is
created exclusively, so no run replaces an earlier report.

Every run, clean or not, appends one JSON line to
`.compass/archive/drift/log.jsonl`: the run time, the HEAD commit, the count
per class and the report's file name or the word `clean`, so a run that found
nothing differs from a run that never happened. The log is only appended to.

`--print` writes the report text to stdout and writes no file and no log row.

`--apply` first rewrites what the scans prove (`driftlib.apply_fixes`: a
shifted or renamed code reference at its new place, an index description from
its target's summary), then reports. The report gains an `## Applied` table
with the old and the new text of every rewrite and a `## Skipped` list naming
each citing document left alone for its uncommitted changes; what was not
rewritten stays under `## Findings` and in the counts. A run that applied
something writes a report even when no finding is left.

Exit 0 whatever the scans find; exit 1, with one line on stderr, when the
project has no vault or git is unavailable.

`latest_open_report` reads the log for `compass validate`.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import vaultlib

USAGE = """usage: compass drift [--print | --apply] [--base-from blame|add]

Check vault code references, index lines and catalog rows against git and the
files they describe. With findings, write .compass/archive/drift/DRIFT-<UTC>.md;
every run appends one row to .compass/archive/drift/log.jsonl. --print writes
the report to stdout only. --apply first rewrites the references and index
descriptions that git proves stale, listing each old and new text under
"Applied" in the report; a citing file with uncommitted changes is skipped.
Exit 1 only when git or the vault is unavailable.
"""

DRIFT_DIR = ("archive", "drift")
LOG_NAME = "log.jsonl"
CLEAN = "clean"
NOT_FINDINGS = ("unchanged", "changed-elsewhere")
CLASS_ORDER = (
    "shifted", "changed", "moved", "missing", "unclassifiable", "malformed",
    "index-drift", "no-summary", "unresolved-link", "ambiguous-link",
    "catalog-drift",
)
COLUMNS = ("Class", "File", "Line", "Base", "Cites", "Old text",
           "Current text", "Proposal")
APPLIED_COLUMNS = ("Class", "File", "Line", "Old", "New")


class DriftError(Exception):
    """A condition that stops the run with exit 1 and one stderr line."""


def drift_folder(vault_root):
    return os.path.join(vault_root, *DRIFT_DIR)


def latest_open_report(vault_root):
    """`(report file name, finding count)` when the newest parseable row of
    the run log names a report, else None (no log, no row, or `clean`)."""
    path = os.path.join(drift_folder(vault_root), LOG_NAME)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        report = row.get("report")
        if not isinstance(report, str) or not report or report == CLEAN:
            return None
        counts = row.get("counts")
        total = sum(n for n in counts.values() if isinstance(n, int)) \
            if isinstance(counts, dict) else 0
        applied = row.get("applied")
        if total == 0 and isinstance(applied, int) and applied > 0:
            return None
        return report, total
    return None


# Git and the vault --------------------------------------------------------


def _git(project, *args):
    try:
        done = subprocess.run(["git", "-C", project, *args],
                              capture_output=True)
    except OSError as exc:
        raise DriftError(f"git is not available ({exc})")
    return done.returncode, done.stdout.decode("utf-8", "replace").strip()


def _repo_root(project):
    """The work tree's top directory, spelled as `project` spells it."""
    code, out = _git(project, "rev-parse", "--show-cdup")
    if code != 0:
        raise DriftError(f"git finds no repository at {project}")
    return os.path.normpath(os.path.join(project, out)) if out else project


def _head(project):
    code, out = _git(project, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    return out if code == 0 and out else None


# Findings ------------------------------------------------------------------


def _span(start, end):
    return str(start) if start == end else f"{start}-{end}"


def _proposal(record):
    proposal = record.get("proposal")
    if not proposal:
        if record.get("newer"):
            return f"{record['newer']} changed last"
        return ""
    if "new_line" in proposal:
        length = record["ref_end"] - record["ref_start"]
        return (f"{record['ref_path']}:"
                f"{_span(proposal['new_line'], proposal['new_line'] + length)}")
    path = proposal["new_path"]
    where = f"{path}:{_span(record['ref_start'], record['ref_end'])}"
    return (f"{where} (renamed in {proposal['rename_commit'][:7]}, "
            f"similarity {proposal['similarity']})")


def _finding(record):
    """One report row, as a dict keyed by `COLUMNS`, from a scanner record."""
    if "ref_path" in record:
        cites = f"{record['ref_path']}:{_span(record['ref_start'], record['ref_end'])}"
    elif record.get("field"):
        cites = f"{record['field']} of {record['target']}"
    else:
        cites = record.get("target") or ""
    base = record.get("base")
    return {
        "Class": record["class"], "File": record["file"],
        "Line": str(record["line"]), "Base": base[:7] if base else "",
        "Cites": cites, "Old text": record.get("old_text") or "",
        "Current text": record.get("current_text") or "",
        "Proposal": _proposal(record),
    }


def collect_records(repo, vault, base_from="blame"):
    """Every finding record of the three scans, ordered by class then file
    and line."""
    import driftlib

    records = [r for r in driftlib.scan_refs(repo, vault, base_from)
               if r["class"] not in NOT_FINDINGS]
    records += driftlib.scan_index_lines(repo, vault)
    records += driftlib.scan_catalog(repo, vault)
    rank = {name: n for n, name in enumerate(CLASS_ORDER)}
    records.sort(key=lambda r: (rank.get(r["class"], len(rank)), r["file"], r["line"]))
    return records


def collect_findings(repo, vault, base_from="blame"):
    """Every finding of the three scans as report rows."""
    return [_finding(r) for r in collect_records(repo, vault, base_from)]


def count_classes(findings):
    """A count for every class in `CLASS_ORDER` (zero when none was found),
    plus any other class a finding carries."""
    counts = {name: 0 for name in CLASS_ORDER}
    for row in findings:
        counts[row["Class"]] = counts.get(row["Class"], 0) + 1
    return counts


# Report ----------------------------------------------------------------------


def _cell(text):
    return (text.replace("\r\n", "\n").replace("\r", "\n")
            .replace("\n", "<br>").replace("|", "\\|"))


def _applied_section(applied):
    lines = [
        "",
        f"## Applied ({len(applied)})",
        "",
        "| " + " | ".join(APPLIED_COLUMNS) + " |",
        "|" + "---|" * len(APPLIED_COLUMNS),
    ]
    for item in applied:
        cells = (item["class"], item["file"], str(item["line"]),
                 item["old"], item["new"])
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return lines


def _skipped_section(skipped):
    lines = ["", f"## Skipped ({len(skipped)})", ""]
    for item in skipped:
        noun = "correction" if item["count"] == 1 else "corrections"
        lines.append(f"- `{item['file']}`: skipped, {item['reason']} "
                     f"({item['count']} {noun} not applied)")
    return lines


def render_report(findings, counts, head, stamp, applied=(), skipped=()):
    """The report text: a count per class, the applied rewrites and skipped
    documents of an `--apply` run, then one table row per finding."""
    short = head[:7] if head else "no commit"
    lines = [
        f"# Drift report {stamp}",
        "",
        f"Run at {stamp} UTC against HEAD {short}.",
        "",
        f"## Counts ({len(findings)} findings)",
        "",
    ]
    lines += [f"- {name}: {n}" for name, n in counts.items()]
    if applied:
        lines += _applied_section(applied)
    if skipped:
        lines += _skipped_section(skipped)
    lines += [
        "",
        "## Findings",
        "",
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
    ]
    for row in findings:
        lines.append("| " + " | ".join(_cell(row[c]) for c in COLUMNS) + " |")
    return "\n".join(lines) + "\n"


def _write_report(folder, text):
    """Create a new report file under `folder`; return its file name. An
    existing file is never opened for writing: a name taken moves the stamp on."""
    os.makedirs(folder, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        name = f"DRIFT-{stamp}.md"
        try:
            with open(os.path.join(folder, name), "x", encoding="utf-8",
                      newline="\n") as handle:
                handle.write(text)
        except FileExistsError:
            continue
        return name


def _append_log(folder, row):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, LOG_NAME)
    prefix = ""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell():
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    prefix = "\n"
    except OSError:
        pass
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + json.dumps(row, ensure_ascii=False) + "\n")


# Command ----------------------------------------------------------------------


def parse_options(args):
    """Return `(print_only, base_from, apply)` or raise `ValueError`."""
    print_only, base_from, apply, rest = False, "blame", False, list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--print":
            print_only = True
        elif arg == "--apply":
            apply = True
        elif arg == "--base-from":
            if not rest:
                raise ValueError("--base-from needs blame or add")
            base_from = rest.pop(0)
        elif arg.startswith("--base-from="):
            base_from = arg[len("--base-from="):]
        else:
            raise ValueError(f"unexpected argument {arg}")
    if base_from not in ("blame", "add"):
        raise ValueError(f"--base-from takes blame or add, not {base_from}")
    if apply and print_only:
        raise ValueError("--apply rewrites files and --print writes none; "
                         "use one of them")
    return print_only, base_from, apply


def parse_args(args):
    """Return `(print_only, base_from)` or raise `ValueError`."""
    print_only, base_from, _apply = parse_options(args)
    return print_only, base_from


def _fail(message):
    sys.stderr.write(f"compass drift: {message}\n")
    return 1


def run(args):
    try:
        print_only, base_from, apply = parse_options(args)
    except ValueError as exc:
        return _fail(f"{exc}\n{USAGE.rstrip()}")
    try:
        vault = vaultlib.find_vault_root()
    except FileNotFoundError:
        return _fail("no .compass vault found for this project")
    project = os.path.dirname(os.fspath(vault))
    try:
        repo = _repo_root(project)
        head = _head(project)
    except DriftError as exc:
        return _fail(str(exc))

    records = collect_records(repo, vault, base_from)
    applied, skipped = [], []
    if apply:
        import driftlib

        applied, skipped = driftlib.apply_fixes(repo, records)
        done = {id(item["record"]) for item in applied}
        records = [r for r in records if id(r) not in done]
    findings = [_finding(r) for r in records]
    counts = count_classes(findings)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    text = render_report(findings, counts, head, stamp, applied, skipped)

    if print_only:
        sys.stdout.write(text if findings else f"compass drift: {CLEAN}\n")
        return 0
    folder = drift_folder(vault)
    report = _write_report(folder, text) if findings or applied else CLEAN
    row = {
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "head": head,
        "counts": counts, "report": report,
    }
    if apply:
        row["applied"] = len(applied)
    _append_log(folder, row)
    if findings or applied:
        extra = (f", {len(applied)} applied, {len(skipped)} file(s) skipped"
                 if apply else "")
        sys.stdout.write(
            f"compass drift: {len(findings)} finding(s){extra}, report "
            f"{'/'.join(DRIFT_DIR)}/{report}\n")
    else:
        sys.stdout.write(f"compass drift: {CLEAN}\n")
    return 0
