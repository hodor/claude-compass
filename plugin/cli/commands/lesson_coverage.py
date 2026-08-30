"""`compass lesson-coverage <plan>` - the lesson-citation audit.

Mirrors `compass coverage` (decisions), grammar and posture both, but audits
instead of gating: a decision left uncovered fails a plan's approval; a
lesson left uncited never does. Compass's own citation obligation lives in
`plugin/cli/decisionslib.py`'s docstring and `commands/coverage.py` - this
module is the same idea one field over.

Plan task lines gain an optional `lessons: [name, name.md, ...]` field, in
the same position as `decisions:` on the task's own line (after `files:`).
Each entry is a lesson catalog filename, with or without the `.md` suffix -
both resolve to the same row. Fenced code blocks and inline code spans are
quoted documentation and never claim, exactly as `coverage` treats
`decisions:` examples.

Every citation resolves against `.compass/meta/lessons-catalog.yaml`
(`lessonslib.load_catalog`), archived rows included - citing an archived
lesson is a legal, informative citation, not a mistake. Separately, this
module computes what `compass lessons --for <plan>` would surface for the
plan's own `area`/`tags` (`lessonslib.rank`, top 5, the command's default),
so a lesson ranked highly for this plan but never cited shows up as an
advisory row.

`planlib.classify_lines` reads which detail region each task line sits in.
A citation from a detailed task line resolves `cited`; a citation whose only
claim comes from a `## Later` intent line resolves `scoped` - the lesson
binds work that is named but not yet elaborated. A lesson cited from both
regions collapses to one `cited` row: a detailed claim always wins. A
citation sitting in a `## Wave N elaborated` record region claims nothing -
the record region names no obligation for any citation it quotes.

Output is a `lesson | cited by | status` table with four statuses:

- `cited` - a citation on a detailed task line resolved to a catalog row.
  `cited by` lists every detailed task that cited it.
- `scoped` - a citation resolved to a catalog row, but only from a `## Later`
  intent line. Not yet built, and never a failure.
- `surfaced-but-uncited` - the lesson ranks for this plan's area/tags but no
  task cited it. Advisory only: a lesson an author read and correctly judged
  irrelevant is a normal outcome, not a defect.
- `unresolvable` - a citation names no catalog row, a typo the author can
  fix, whichever region it sits in.

Exit 1 only when an unresolvable citation exists. A plan with no `lessons:`
fields anywhere exits 0 with an explicit "no citations" summary line rather
than treating the absence as a gap. A plan with no `## Later` section
produces the same output as before region-awareness existed - no `scoped`
count is added when nothing in the plan could ever be scoped. When
`classify_lines` reports an unterminated fence, the command prints a note
that the regions could not be read and every line was treated as detailed,
rather than passing silently. Never exits 2.
"""

import json
import re
import sys

import lessonslib
import planlib
import vaultlib
from commands.decisions import resolve_doc

# The lessons: field, wherever it sits on that same task line.
LESSONS_FIELD = re.compile(r"lessons:\s*\[([^\]]*)\]")

_DEFAULT_TOP = 5


def _normalize(name):
    """Strip surrounding quotes and a trailing `.md`, so a citation resolves
    the same way with or without the suffix."""
    name = name.strip()
    if len(name) >= 2 and name[0] in "\"'" and name[-1] == name[0]:
        name = name[1:-1]
    if name.lower().endswith(".md"):
        name = name[:-3]
    return name


def _parse_citations(plan_text, regions):
    """Scan the plan body for `lessons:` citations on task lines.

    Returns a list of `{task, raw, line, region}` dicts, one per cited
    entry, in the order they appear. `region` is `"detailed"`, `"scoped"`,
    or `"record"`, read from `regions` (a line absent from the map is
    detailed, per `planlib.classify_lines`'s sparse convention). Fenced
    blocks and inline code are stripped first (line count preserved), so
    quoted examples never claim.
    """
    stripped, _ = vaultlib.strip_fenced_code(plan_text)
    stripped = vaultlib.strip_inline_code(stripped)
    citations = []
    for number, line in enumerate(stripped.split("\n"), start=1):
        task_match = planlib.TASK_LINE.match(line)
        if not task_match:
            continue
        field_match = LESSONS_FIELD.search(line)
        if not field_match:
            continue
        task_id = task_match.group(1)
        region = regions.get(number, "detailed")
        for raw in field_match.group(1).split(","):
            raw = raw.strip()
            if raw:
                citations.append(
                    {"task": task_id, "raw": raw, "line": number, "region": region}
                )
    return citations


def _archived_row(vault_root, norm):
    """Resolve a citation against lesson files on disk when no catalog row
    matches. The catalog holds active rows only; an archived lesson keeps
    its full file in `archive/lessons/` (or, mid-transition, `lessons/`), so
    a citation to it is a resolved historical claim, not a typo."""
    filename = norm if norm.endswith(".md") else f"{norm}.md"
    for rel in (f"archive/lessons/{filename}", f"lessons/{filename}"):
        if (vault_root / rel).is_file():
            return {"file": filename, "status": "archived"}
    return None


def _resolve_citations(citations, catalog, vault_root):
    """Match citations against catalog rows, falling back to lesson files
    on disk for archived lessons the active-only catalog no longer rows.

    Returns `(cited, scoped, unresolved)`. `cited` maps a canonical catalog
    filename to the ordered list of detailed-region tasks that cited it.
    `scoped` maps a filename to the ordered list of Later-region tasks that
    cited it, for lessons never claimed by a detailed task line - a detailed
    claim always wins, so a lesson present in `cited` never also appears in
    `scoped`. `unresolved` maps a normalized citation to `{"raw": <as
    written>, "tasks": [...]}` for entries naming no catalog row, gathered
    from either region. A citation sitting in a record region claims
    nothing and is discarded before resolution.
    """
    index = {_normalize(row["file"]): row for row in catalog}
    cited = {}
    scoped = {}
    unresolved = {}
    for citation in citations:
        if citation["region"] == "record":
            continue
        norm = _normalize(citation["raw"])
        row = index.get(norm) or _archived_row(vault_root, norm)
        if row is None:
            entry = unresolved.setdefault(norm, {"raw": citation["raw"], "tasks": []})
            if citation["task"] not in entry["tasks"]:
                entry["tasks"].append(citation["task"])
            continue
        file = row["file"]
        if citation["region"] == "detailed":
            tasks = cited.setdefault(file, [])
            if citation["task"] not in tasks:
                tasks.append(citation["task"])
            scoped.pop(file, None)
        elif file not in cited:
            tasks = scoped.setdefault(file, [])
            if citation["task"] not in tasks:
                tasks.append(citation["task"])
    return cited, scoped, unresolved


def run(args):
    positional, json_flag = [], False
    for arg in args:
        if arg == "--json":
            json_flag = True
        elif arg.startswith("--"):
            sys.stderr.write(f"compass lesson-coverage: unknown flag {arg}\n")
            return 1
        else:
            positional.append(arg)
    if len(positional) != 1:
        sys.stderr.write("usage: compass lesson-coverage <plan> [--json]\n")
        return 1

    vault_root = vaultlib.find_vault_root()
    resolve = vaultlib.resolvable_names_map(vault_root)
    plan_path, error = resolve_doc(vault_root, positional[0], resolve)
    if error:
        sys.stderr.write(f"compass lesson-coverage: {error}\n")
        return 1
    plan_rel = plan_path.relative_to(vault_root).as_posix()
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_data, _ = vaultlib.parse_frontmatter_text(plan_text)

    try:
        catalog = lessonslib.load_catalog(vault_root)
    except FileNotFoundError:
        sys.stderr.write(
            "compass lesson-coverage: lessons catalog not found - vault malformed\n"
        )
        return 1
    except lessonslib.MalformedRow as exc:
        sys.stderr.write(f"compass lesson-coverage: malformed catalog: {exc}\n")
        return 1

    regions, unterminated_fence = planlib.classify_lines(plan_text)
    has_later = any(status == "scoped" for status in regions.values())

    citations = _parse_citations(plan_text, regions)
    cited, scoped, unresolved = _resolve_citations(citations, catalog, vault_root)

    tags = plan_data.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    area = plan_data.get("area")
    surfaced = lessonslib.rank(catalog, area=area, tags=tags)[:_DEFAULT_TOP]
    surfaced_uncited = [
        row for row in surfaced if row["file"] not in cited and row["file"] not in scoped
    ]

    ok = not unresolved

    if json_flag:
        payload = {
            "plan": plan_rel,
            "cited": [
                {"lesson": file, "cited_by": tasks}
                for file, tasks in sorted(cited.items())
            ],
            "scoped": [
                {"lesson": file, "cited_by": tasks}
                for file, tasks in sorted(scoped.items())
            ],
            "unresolvable": [
                {"citation": entry["raw"], "cited_by": entry["tasks"]}
                for _, entry in sorted(unresolved.items())
            ],
            "surfaced_but_uncited": [row["file"] for row in surfaced_uncited],
            "has_citations": bool(citations),
            "ok": ok,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        if unterminated_fence:
            sys.stderr.write(
                f"compass lesson-coverage: note: unterminated code fence in "
                f"{plan_rel}; detail regions could not be read - every line "
                "treated as detailed\n"
            )
        return 0 if ok else 1

    rows = [("lesson", "cited by", "status")]
    for file in sorted(cited):
        rows.append((file, ", ".join(cited[file]), "cited"))
    for file in sorted(scoped):
        rows.append((file, ", ".join(scoped[file]), "scoped"))
    for _, entry in sorted(unresolved.items()):
        rows.append((entry["raw"], ", ".join(entry["tasks"]), "unresolvable"))
    for row in surfaced_uncited:
        rows.append((row["file"], "-", "surfaced-but-uncited (advisory)"))

    sys.stdout.write(f"compass lesson-coverage: {plan_rel}\n")
    if len(rows) > 1:
        widths = [max(len(row[col]) for row in rows) for col in range(3)]
        for row in rows:
            line = "  ".join(cell.ljust(w) for cell, w in zip(row, widths))
            sys.stdout.write(line.rstrip() + "\n")

    if citations:
        if has_later:
            summary = (
                f"{len(cited)} cited, {len(scoped)} scoped, "
                f"{len(unresolved)} unresolvable, "
                f"{len(surfaced_uncited)} surfaced-but-uncited (advisory)"
            )
        else:
            summary = (
                f"{len(cited)} cited, {len(unresolved)} unresolvable, "
                f"{len(surfaced_uncited)} surfaced-but-uncited (advisory)"
            )
    else:
        summary = (
            f"no citations: no lessons: field found in {plan_rel}; "
            f"{len(surfaced_uncited)} surfaced-but-uncited (advisory)"
        )
    sys.stdout.write(f"summary: {summary} -> {'PASS' if ok else 'FAIL'}\n")
    if unterminated_fence:
        sys.stderr.write(
            f"compass lesson-coverage: note: unterminated code fence in "
            f"{plan_rel}; detail regions could not be read - every line "
            "treated as detailed\n"
        )
    return 0 if ok else 1
