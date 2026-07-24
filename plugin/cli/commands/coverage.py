"""`compass coverage <plan> [--against <doc>...]` - the decision coverage gate.

Checks that a plan claims every trackable decision of its sources. Sources
default to the plan's `depends_on` documents whose frontmatter type is a
workflow source type (specs and decisions); `--against` replaces the default
set. Handoffs and every other document type are never scanned.

A claim is a source-qualified citation `<doc-name>/D-NN` in the plan body,
where `<doc-name>` resolves - through the same name resolution wikilinks
use - to the source document. Bare `D-NN` tokens never claim (local IDs
collide across documents by design); fenced code blocks and inline code
spans are quoted documentation and never claim.

Output is an aligned `source | decision | trackable | status` table plus a
count summary. Exit 1 when any trackable decision is uncovered or any source
could not be parsed - an unparseable source surfaces in the report and fails
the gate even when every other source is fully covered. Exit 0 otherwise.
Never exits 2.
"""

import re
import sys

import decisionslib
import vaultlib
from commands.decisions import resolve_doc

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")

# A source-qualified citation: a document name (bare stem, or path-qualified
# with slashes) joined by a slash to a D-NN id. The boundary guards keep a
# longer hyphenated token from claiming through a shorter name inside it.
CITATION = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"([A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)*)"
    r"/(D-[A-Za-z0-9][A-Za-z0-9_-]*)"
    r"(?![A-Za-z0-9_-])"
)

# A bare decision id with no qualifying document name. Claims nothing; its
# presence is reported so an author learns why the citation did not count.
BARE_ID = re.compile(r"(?<![A-Za-z0-9_/-])D-[0-9]+(?![A-Za-z0-9_-])")


def workflow_binding():
    """The workflow's coverage binding: which frontmatter types bear
    decisions (`source_types`), which artifact role must claim them
    (`target_type`), and which status transition carries the gate
    (`gate_transition`).

    Every coverage role is read through this one lookup, so a workflow
    configuration can rebind sources, target, and transition in a single
    place. The returned value is the shipped default pipeline: spec and
    decision documents, covered by plans, gated when a plan moves from
    review to approved.
    """
    return {
        "source_types": ("spec", "decision"),
        "target_type": "plan",
        "gate_transition": "review->approved",
    }


def _default_sources(vault_root, plan_data, resolve, notes):
    """Source paths from the plan's `depends_on`, keeping only documents
    whose frontmatter type is a workflow source type. A target that does
    not resolve uniquely is noted and skipped: only declared, resolvable
    sources are ever scanned."""
    source_types = set(workflow_binding()["source_types"])
    deps = plan_data.get("depends_on")
    if isinstance(deps, str):
        deps = [deps]
    sources = []
    for item in deps or []:
        for raw in WIKILINK.findall(item):
            target = raw.split("#")[0].split("|")[0].strip()
            if not target:
                continue
            paths = resolve.get(target, [])
            if len(paths) != 1:
                notes.append(
                    f"depends_on target not uniquely resolvable, skipped: {target}"
                )
                continue
            data, error = vaultlib.parse_frontmatter(vault_root / paths[0])
            if not error and data.get("type") in source_types:
                sources.append(vault_root / paths[0])
    return sources


def _claims(plan_text, resolve):
    """Scan the plan body for citations.

    Returns `(claims, bare_count)`: `claims` maps `(source_rel_path,
    decision_id)` to the 1-based line of the first claiming citation, and
    `bare_count` is the number of unqualified D-NN tokens found. Fenced
    blocks and inline code are stripped first (line count preserved), so
    quoted examples never claim.
    """
    stripped, _ = vaultlib.strip_fenced_code(plan_text)
    stripped = vaultlib.strip_inline_code(stripped)
    claims = {}
    bare = 0
    for number, line in enumerate(stripped.split("\n"), start=1):
        for match in CITATION.finditer(line):
            paths = resolve.get(match.group(1), [])
            if len(paths) == 1:
                claims.setdefault((paths[0], match.group(2)), number)
        bare += len(BARE_ID.findall(line))
    return claims, bare


def run(args):
    positional, against, in_against = [], [], False
    for arg in args:
        if arg == "--against":
            in_against = True
        elif arg.startswith("--"):
            sys.stderr.write(f"compass coverage: unknown flag {arg}\n")
            return 1
        elif in_against:
            against.append(arg)
        else:
            positional.append(arg)
    if len(positional) != 1 or (in_against and not against):
        sys.stderr.write("usage: compass coverage <plan> [--against <doc>...]\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    resolve = vaultlib.resolvable_names_map(vault_root)
    plan_path, error = resolve_doc(vault_root, positional[0], resolve)
    if error:
        sys.stderr.write(f"compass coverage: {error}\n")
        return 1
    plan_rel = plan_path.relative_to(vault_root).as_posix()
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_data, _ = vaultlib.parse_frontmatter_text(plan_text)

    notes = []
    binding = workflow_binding()
    if plan_data.get("type") and plan_data["type"] != binding["target_type"]:
        notes.append(
            f"target document type '{plan_data['type']}' is not the workflow "
            f"coverage target '{binding['target_type']}'"
        )

    if against:
        sources = []
        for arg in against:
            path, error = resolve_doc(vault_root, arg, resolve)
            if error:
                sys.stderr.write(f"compass coverage: {error}\n")
                return 1
            sources.append(path)
    else:
        sources = _default_sources(vault_root, plan_data, resolve, notes)
    # A source named twice would double its rows and counts; keep first mention.
    sources = list(dict.fromkeys(sources))

    claims, bare = _claims(plan_text, resolve)
    if bare:
        notes.append(
            f"{bare} bare D-NN token(s) in {plan_rel} claim nothing; a "
            "citation is source-qualified: <doc-name>/D-NN"
        )

    rows = [("source", "decision", "trackable", "status")]
    trackable_total = covered = uncovered = unparseable = 0
    for source in sources:
        source_rel = source.relative_to(vault_root).as_posix()
        decisions, outcome = decisionslib.extract_decisions(
            source.read_text(encoding="utf-8")
        )
        if outcome == "could-not-parse":
            unparseable += 1
            rows.append((source.stem, "-", "-", "COULD NOT PARSE"))
            continue
        for decision in decisions:
            line = claims.get((source_rel, decision["id"]))
            if decision["trackable"]:
                trackable_total += 1
                if line is not None:
                    covered += 1
                else:
                    uncovered += 1
            status = f"covered (line {line})" if line is not None else "NOT COVERED"
            rows.append((
                source.stem,
                decision["id"],
                "yes" if decision["trackable"] else "no",
                status,
            ))

    sys.stdout.write(f"compass coverage: {plan_rel}\n")
    if len(rows) > 1:
        widths = [max(len(row[col]) for row in rows) for col in range(4)]
        for row in rows:
            line = "  ".join(cell.ljust(w) for cell, w in zip(row, widths))
            sys.stdout.write(line.rstrip() + "\n")

    if not sources:
        summary = "no sources: depends_on names no spec or decision documents"
    elif trackable_total == 0 and unparseable == 0:
        summary = f"no trackable decisions in {len(sources)} source(s)"
    else:
        summary = (
            f"{trackable_total} trackable decision(s) in {len(sources)} "
            f"source(s): {covered} covered, {uncovered} uncovered"
        )
        if unparseable:
            summary += f", {unparseable} source(s) could not be parsed"
    ok = uncovered == 0 and unparseable == 0
    sys.stdout.write(f"summary: {summary} -> {'PASS' if ok else 'FAIL'}\n")
    for note in notes:
        sys.stderr.write(f"compass coverage: note: {note}\n")
    return 0 if ok else 1
