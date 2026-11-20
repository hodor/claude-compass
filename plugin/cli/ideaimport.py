"""Import of a hand-made idea table: `compass idea import <file>`.

The file holds one section per category, each a `## <Category>` heading
followed by a markdown table:

    ## World Building

    | # | <Name>'s words | Status | Where it led |
    |---|---|---|---|
    | 7 | "what if the map remembers where you died" | adopted | [[SPEC-004-world-memory]] |

A table is a header row, a separator row, then rows; the header row is read by
position only. Each heading names a category folder `ideas/<slug>`, created
with the heading text as its title when it is missing, an empty section
included. Cells split on a `|` not preceded by `\\`, and `\\|` reads back as
`|`. A row with other than four cells is skipped and reported.

Columns by position: number, his words, status, where it led.

- words: one surrounding pair of straight double quotes is removed, nothing
  else; the cell text is stored as written.
- number: the table number becomes the IDEA number when it is free, else the
  next free number above every number in use (a remap).
- status: one of the six values in any letter case; `decided` reads as
  `adopted`; anything else reads as `exploring`. `raw_status` keeps the cell
  text whenever it differs from the stored status.
- where it led: each `[[link]]` that resolves to one document in the vault
  goes to `led_to`; broken and ambiguous links are reported; the whole
  unescaped cell is `led_to_note`.
- a row whose words equal an existing idea's words, or an earlier row's, is
  reported as present and writes nothing.

`plan` reads the vault and the table and decides every file; `apply` writes
the plan. Numbers are claimed through `idealib.claim_number`, the same
reservation `compass idea add` uses. Every file is written LF.
"""

import io
import re
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

import idealib
import vaultlib
from commands import make_domain

HEADING = re.compile(r"^##[ \t]+(\S.*)$")
SEPARATOR_CELL = re.compile(r"^:?-+:?$")
NUMBER_CELL = re.compile(r"^(?:IDEA-)?(\d{1,9})$", re.IGNORECASE)
LINK = re.compile(r"\[\[([^\[\]]+)\]\]")
COLUMNS = 4
SLUG_LENGTH = 60
RESERVED_NAMES = {"con", "prn", "aux", "nul", "clock$"} | {f"com{n}" for n in range(1, 10)} | {f"lpt{n}" for n in range(1, 10)}
PREVIEW = 60
SOURCE = "compass idea import"
EXISTING_NUMBER = re.compile(r"^IDEA-(\d+)-")


@dataclass
class Entry:
    """One idea to write."""
    line: int
    slug: str
    words: str
    cell_status: str
    status: str
    raw_status: str
    led_to: list
    note: str
    table_number: int = 0
    number: int = 0
    broken: list = field(default_factory=list)
    ambiguous: list = field(default_factory=list)
    resolved: int = 0

    @property
    def label(self):
        return f"IDEA-{self.number:03d}"


@dataclass
class Plan:
    entries: list = field(default_factory=list)
    create: list = field(default_factory=list)
    blocked: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    present: list = field(default_factory=list)
    remaps: list = field(default_factory=list)


def category_slug(heading):
    """Folder name for a heading: ASCII lower-case, accents folded, one hyphen
    between runs of other characters, at most 60 characters; empty when
    nothing survives or the name is one a Windows filesystem reserves."""
    folded = unicodedata.normalize("NFKD", heading)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower())[:SLUG_LENGTH].strip("-")
    return "" if slug in RESERVED_NAMES else slug


def split_row(line):
    """The cells of one table row: outer pipes dropped, split on a `|` not
    preceded by a backslash, `\\|` read back as `|`, each cell stripped."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", body)]


def _is_separator(cells):
    return bool(cells) and all(SEPARATOR_CELL.match(cell) for cell in cells)


def parse(text):
    """(sections, rows, loose) from the table text. `sections` maps each
    category slug to the first heading text that produced it; `rows` holds one
    dict per table row: line number, slug (None above any usable heading),
    heading text, cells and the line itself; `loose` holds one dict per run of
    `|` lines that never reached a separator row: first line number, heading
    text and the first line."""
    sections, rows, loose = {}, [], []
    slug, heading_text, state, first = None, None, None, None
    for number, line in enumerate(text.split("\n") + [""], 1):
        heading = HEADING.match(line)
        if heading or not line.lstrip().startswith("|"):
            if state == "header":
                loose.append({"line": first[0], "heading": heading_text, "text": first[1]})
            state = None
            if heading:
                heading_text = heading.group(1).strip()
                slug = category_slug(heading_text) or None
                if slug:
                    sections.setdefault(slug, heading_text)
            continue
        cells = split_row(line)
        if state == "rows":
            rows.append({"line": number, "slug": slug, "heading": heading_text,
                         "cells": cells, "text": line.strip()})
        elif state == "header" and _is_separator(cells):
            state = "rows"
        else:
            if state is None:
                first = (number, line.strip())
            state = "header"
    return sections, rows, loose


def unquote(cell):
    """The cell without one surrounding pair of straight double quotes."""
    if len(cell) >= 2 and cell[0] == '"' and cell[-1] == '"':
        return cell[1:-1]
    return cell


def map_status(cell):
    key = cell.lower()
    if key in idealib.STATUSES:
        return key
    return "adopted" if key == "decided" else "exploring"


def preview(text):
    return text[:PREVIEW]


def _numbers_in_use(ideas_root):
    numbers = set()
    if ideas_root.is_dir():
        for path in ideas_root.rglob("IDEA-*"):
            match = EXISTING_NUMBER.match(path.name)
            if match:
                numbers.add(int(match.group(1)))
    return numbers


def _links(cell, names):
    """(resolved, broken, ambiguous) link texts of a where-it-led cell."""
    resolved, broken, ambiguous = [], [], []
    for match in LINK.finditer(cell):
        raw = match.group(1)
        text = f"[[{raw}]]"
        target, _ = vaultlib.split_link(raw)
        found = vaultlib.resolve_link(names, target)
        bucket = resolved if len(found) == 1 else broken if not found else ambiguous
        if text not in bucket:
            bucket.append(text)
    return resolved, broken, ambiguous


def _row_problem(row, plan):
    """Why the row cannot be imported, or None."""
    if row["slug"] is None:
        if row["heading"]:
            return f"heading {row['heading']!r} has no usable folder name"
        return "no category heading above this row"
    if row["slug"] in plan.blocked:
        return f"ideas/{row['slug']} exists and is not a category folder"
    if len(row["cells"]) != COLUMNS:
        return f"{len(row['cells'])} cell(s), expected {COLUMNS}"
    return None


def plan(vault_root, text):
    """Everything the import would do with `text`, written nowhere."""
    vault_root = Path(vault_root)
    ideas_root = vault_root / "ideas"
    sections, rows, loose = parse(text)
    result = Plan()
    for table in loose:
        where = f"under {table['heading']!r}" if table["heading"] else "above any heading"
        result.skipped.append((table["line"], f"table {where} has no separator row",
                               preview(table["text"])))
    for slug, title in sections.items():
        folder = ideas_root / slug
        if folder.is_dir():
            continue
        if folder.exists() or folder.with_suffix(".md").exists():
            result.blocked[slug] = title
        else:
            result.create.append((slug, title))

    taken = _numbers_in_use(ideas_root)
    holders = {}
    for idea in idealib.load_all(vault_root):
        holders.setdefault(idea["words"], (idea["id"], idea["category"]))
    names = vaultlib.resolvable_names_map(vault_root)

    for row in rows:
        problem = _row_problem(row, result)
        if problem:
            result.skipped.append((row["line"], problem, preview(row["text"])))
            continue
        number_cell, words_cell, status_cell, led_cell = row["cells"]
        words = unquote(words_cell)
        problem = (idealib.storable_error(words)
                   or idealib.single_line_error(status_cell)
                   or idealib.single_line_error(led_cell))
        if problem:
            result.skipped.append((row["line"], problem, preview(row["text"])))
            continue
        status = map_status(status_cell)
        probe = idealib.render(1, words, status, row["slug"], SOURCE, "1970-01-01", "- x")
        if not idealib.round_trips(probe, words):
            result.skipped.append((row["line"], "the words do not read back unchanged from a property",
                                   preview(row["text"])))
            continue
        if words in holders:
            result.present.append((row["line"], words, holders[words]))
            continue
        resolved, broken, ambiguous = _links(led_cell, names)
        match = NUMBER_CELL.match(number_cell)
        entry = Entry(
            line=row["line"], slug=row["slug"], words=words, cell_status=status_cell,
            status=status, raw_status=status_cell if status_cell != status else "",
            led_to=resolved, note=led_cell, table_number=int(match.group(1)) if match else 0,
            broken=broken, ambiguous=ambiguous, resolved=len(resolved))
        result.entries.append(entry)
        holders[words] = entry

    for entry in result.entries:
        if entry.table_number and entry.table_number not in taken:
            entry.number = entry.table_number
            taken.add(entry.number)
    for entry in result.entries:
        if not entry.number:
            entry.number = max(taken, default=0) + 1
            taken.add(entry.number)
            result.remaps.append(entry)
    return result


def _holder_text(holder):
    if isinstance(holder, Entry):
        return f"{holder.label} ({holder.slug})"
    return f"{holder[0]} ({holder[1]})"


def report(result, source, applied):
    """The dry-run or apply report as printable lines."""
    mode = "" if applied else " (dry-run; pass --apply to write)"
    lines = [f"compass idea: import {source}{mode}"]
    for entry in result.entries:
        counts = f"links: {entry.resolved} resolved, {len(entry.broken)} broken"
        if entry.ambiguous:
            counts += f", {len(entry.ambiguous)} ambiguous"
        lines.append(f"{entry.label}  {entry.slug}  {entry.status}  {counts}  "
                     f"\"{preview(entry.words)}\"")
    if result.create:
        lines.append(f"categories {'created' if applied else 'to create'} ({len(result.create)}):")
        lines.extend(f"  {slug} ({title})" for slug, title in result.create)
    if result.remaps:
        lines.append(f"remaps ({len(result.remaps)}): the table number was taken or unusable")
        for entry in result.remaps:
            was = entry.table_number or "none"
            lines.append(f"  line {entry.line}: table number {was} -> {entry.label}")
    status_rows = [e for e in result.entries if e.raw_status]
    if status_rows:
        lines.append(f"status rows not matching as written ({len(status_rows)}):")
        for entry in status_rows:
            lines.append(f"  line {entry.line}: {entry.label} \"{entry.cell_status}\" -> {entry.status}")
    broken = [(e, link) for e in result.entries for link in e.broken]
    if broken:
        lines.append(f"broken links ({len(broken)}):")
        lines.extend(f"  line {e.line}: {e.label} {link} matches no document" for e, link in broken)
    ambiguous = [(e, link) for e in result.entries for link in e.ambiguous]
    if ambiguous:
        lines.append(f"ambiguous links ({len(ambiguous)}):")
        lines.extend(f"  line {e.line}: {e.label} {link} matches several documents" for e, link in ambiguous)
    if result.skipped:
        lines.append(f"skipped rows ({len(result.skipped)}):")
        lines.extend(f"  line {n}: {why}: {text}" for n, why, text in result.skipped)
    if result.present:
        lines.append(f"already present ({len(result.present)}):")
        lines.extend(f"  line {n}: {_holder_text(holder)}: \"{preview(words)}\""
                     for n, words, holder in result.present)
    if not (result.entries or result.create or result.skipped or result.present):
        lines.append("nothing to import")
    return lines


def apply(vault_root, result, today):
    """Create the missing category folders, then write every idea file.
    Returns (error text or None, lines noting numbers that moved at write
    time because another process took them)."""
    vault_root = Path(vault_root)
    ideas_root = vault_root / "ideas"
    if result.create or result.entries:
        ideas_root.mkdir(exist_ok=True)
    for slug, title in result.create:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = make_domain.run([
                f"ideas/{slug}",
                "--class-here", f"ideas the human filed under {title}",
                "--title", title,
                "--reason", "category heading in an imported idea table",
                "--apply",
            ])
        if code != 0:
            return f"could not create category ideas/{slug}: {err.getvalue().strip()}", []
    moved = []
    for entry in result.entries:
        number, claim = idealib.claim_number(ideas_root, preferred=entry.number)
        try:
            history = (f"- {today}: {entry.status} "
                       f"(imported; status as written: \"{entry.cell_status}\")")
            text = idealib.render(
                number, entry.words, entry.status, entry.slug, SOURCE, today, history,
                led_to=entry.led_to, led_to_note=entry.note, raw_status=entry.raw_status)
            path = ideas_root / entry.slug / f"IDEA-{number:03d}-{idealib.slug(entry.words)}.md"
            vaultlib.write_text_lf(path, text)
        finally:
            idealib.release(claim)
        if number != entry.number:
            moved.append(f"line {entry.line}: {entry.label} was taken by another process; "
                         f"written as IDEA-{number:03d}")
    return None, moved
