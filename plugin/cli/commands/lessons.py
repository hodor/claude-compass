"""`compass lessons` - ranked catalog rows for an area, tag set, free text,
or a document.

Reads `.compass/meta/lessons-catalog.yaml` rows only, never lesson bodies,
through `lessonslib.load_catalog` and ranks them with `lessonslib.rank`.
See `lessonslib` for the row-shape contract and the ranking order.

Flags:

- `--area <area>`
- `--tags a,b,c`
- `--text "..."`
- `--for <doc>` - resolves `<doc>` the way a wikilink resolves (a
  vault-relative path, or any name in the vault's resolution map) and
  reads its frontmatter `area`/`tags` as the query. Combines with an
  explicit `--area` (which takes precedence) and `--tags` (which extends
  the document's tags).
- `--top N` (default 5)
- `--json`

Exit 0 on a ranked result, and on an empty catalog (prints an explicit "no
lessons" line - a vault that has captured nothing yet is a valid state,
not an error). Exit 1 on a missing catalog (a malformed vault), a
malformed catalog row (names the row number), an unresolvable `--for`
document, or an unknown flag. Never exits 2.
"""

import json
import sys

import lessonslib
import vaultlib
from commands.decisions import resolve_doc


def _parse_args(args):
    """Parse flags into an options dict. Returns `(options, error)`, with
    exactly one side set."""
    options = {
        "area": None, "tags": [], "text": None, "for_doc": None,
        "top": 5, "json": False,
    }
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--json":
            options["json"] = True
            i += 1
            continue
        if arg not in ("--area", "--tags", "--text", "--for", "--top"):
            return None, f"unknown flag {arg}"
        if i + 1 >= len(args):
            return None, f"{arg} expects a value"
        value = args[i + 1]
        if arg == "--area":
            options["area"] = value
        elif arg == "--tags":
            options["tags"] = [t.strip() for t in value.split(",") if t.strip()]
        elif arg == "--text":
            options["text"] = value
        elif arg == "--for":
            options["for_doc"] = value
        elif arg == "--top":
            try:
                options["top"] = int(value)
            except ValueError:
                return None, "--top expects an integer"
            if options["top"] < 0:
                return None, "--top expects a non-negative integer"
        i += 2
    return options, None


def _resolve_for(vault_root, for_doc):
    """Resolve `--for <doc>` to its frontmatter `area`/`tags`. Returns
    `(area, tags, error)`."""
    resolve = vaultlib.resolvable_names_map(vault_root)
    path, error = resolve_doc(vault_root, for_doc, resolve)
    if error:
        return None, [], error
    data, fm_error = vaultlib.parse_frontmatter(path)
    if fm_error:
        return None, [], f"{for_doc}: {fm_error}"
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    return data.get("area"), tags, None


def format_report(rows):
    if not rows:
        return "compass lessons: no matching lessons"
    header = ("rank", "file", "area", "tags", "score", "summary")
    table = [header]
    for row in rows:
        marker = "[ESCALATED] " if row["escalated"] else ""
        table.append((
            str(row["rank"]),
            marker + row["file"],
            row["area"],
            ",".join(row["tags"]),
            str(row["score"]),
            row["summary"],
        ))
    widths = [max(len(r[c]) for r in table) for c in range(len(header))]
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip()
        for row in table
    )


def run(args):
    options, error = _parse_args(args)
    if error:
        sys.stderr.write(f"compass lessons: {error}\n")
        return 1

    vault_root = vaultlib.find_vault_root()

    area, tags = options["area"], list(options["tags"])
    if options["for_doc"]:
        for_area, for_tags, error = _resolve_for(vault_root, options["for_doc"])
        if error:
            sys.stderr.write(f"compass lessons: {error}\n")
            return 1
        if area is None:
            area = for_area
        for tag in for_tags:
            if tag not in tags:
                tags.append(tag)

    try:
        catalog = lessonslib.load_catalog(vault_root)
    except FileNotFoundError:
        sys.stderr.write("compass lessons: lessons catalog not found - vault malformed\n")
        return 1
    except lessonslib.MalformedRow as exc:
        sys.stderr.write(f"compass lessons: malformed catalog: {exc}\n")
        return 1

    if not catalog:
        sys.stdout.write("compass lessons: no lessons in catalog\n")
        return 0

    ranked = lessonslib.rank(catalog, area=area, tags=tags, text=options["text"])
    ranked = ranked[:options["top"]]

    if options["json"]:
        sys.stdout.write(json.dumps(ranked) + "\n")
    else:
        sys.stdout.write(format_report(ranked) + "\n")
    return 0
