"""Requirement rows read from a spec body.

A spec's requirements are the items under four sections:

- `## Desired Outcome`: `O-n` rows, plus `K-n` for a `KPI:` line.
- `## Success Criteria`: `S-n` rows.
- `## Constraints`: `C-n` rows.
- the decisions section: `D-NN` rows, read by `decisionslib`, each keeping
  its own id, text and bracket tags.

Inside a section every top-level bullet is one row, an indented or
unindented follow-on line belongs to the bullet above it, and a paragraph of
prose with no bullets is one row. Numbers follow the order of the rows in
their section and restart per section.

A bullet in the O, S or C sections may open with an authored id in the
decision-bullet shape, `- **O-01:** text`, or `- [ ] **S-01:** text` for a
checkbox bullet, the prefix matching its section. The row keeps that id as
written and its text is the bullet text with the id removed, so an id and
its hash survive a bullet inserted above it. Ids compare by prefix and
number, `O-3` and `O-03` being one id; a derived id takes the next number its
prefix does not hold as an authored id. An authored id inside a fenced
block, or anywhere but the start of a bullet, is text. `duplicate_report`
names the lines of rows holding the same id.

Each row is a dict with `id`, `section`, `text` and `hash`; a decision row
also carries `tags`. `text` has its whitespace collapsed to single spaces,
and `hash` is the first 12 hex digits of the sha256 of that text, so an
edit to one requirement moves only that row's hash while line endings and
wrapping move none. Rows come back in document order.

Fenced code blocks never open a section or yield a row, and a heading quoted
inside inline code is not a heading because a heading starts its line.

Pure standard library apart from `decisionslib` and `vaultlib`; no side
effects.
"""

import hashlib
import re

import decisionslib
import vaultlib

# Requirement sections, matched on the title of a two-hash heading:
# (title pattern, section name, id prefix).
_SECTIONS = (
    (re.compile(r"desired\s+outcomes?$", re.IGNORECASE), "Desired Outcome", "O"),
    (re.compile(r"success\s+criteri(?:a|on)$", re.IGNORECASE), "Success Criteria", "S"),
    (re.compile(r"constraints?$", re.IGNORECASE), "Constraints", "C"),
)

DECISIONS_SECTION = "Decisions"

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_KPI = re.compile(r"^\**KPI\s*:\**\s*(.*)$", re.IGNORECASE)
_AUTHORED_ID = re.compile(r"^(?:\[[ xX]\]\s+)?\*\*([OSC])-(\d+):\*\*\s*(.*)$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_DECISIONS_CITATION = re.compile(r"decisions:\s*\[([^\[\]]*)\]")


def normalize_text(text):
    """The text with every run of whitespace collapsed to one space."""
    return " ".join(text.split())


def text_hash(text):
    """The first 12 hex digits of the sha256 of the normalized text."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()[:12]


def _make_row(row_id, section, text):
    text = normalize_text(text)
    return {"id": row_id, "section": section, "text": text, "hash": text_hash(text)}


def _section_for(title):
    """`(section name, id prefix)` for a requirement section title, else None."""
    for pattern, name, prefix in _SECTIONS:
        if pattern.match(title.strip()):
            return name, prefix
    return None


def _scan_sections(stripped_text):
    """Rows for the O, S, C and K ids as `(line, row, authored_number)`.

    `line` is the 1-based line the row starts on; `authored_number` is the
    number of an authored id, else None. Derived rows are numbered after the
    scan, skipping the numbers authored ids hold.
    """
    entries = []
    section = None
    item = None
    in_comment = False

    def flush():
        nonlocal item
        if item is None:
            return
        start, parts, is_bullet = item
        item = None
        text = normalize_text(" ".join(parts))
        if not text:
            return
        kpi = _KPI.match(text)
        if kpi:
            text = kpi.group(1)
            if not text.strip():
                return
            entries.append((start, "K", None, None, section[0], text))
            return
        prefix = section[1]
        authored = _AUTHORED_ID.match(text) if is_bullet else None
        if authored and authored.group(1) == prefix:
            if not authored.group(3).strip():
                return
            token = f"{prefix}-{authored.group(2)}"
            entries.append(
                (start, prefix, int(authored.group(2)), token, section[0], authored.group(3))
            )
            return
        entries.append((start, prefix, None, None, section[0], text))

    for number, line in enumerate(stripped_text.split("\n"), 1):
        trimmed = line.strip()

        if in_comment:
            if "-->" in trimmed:
                in_comment = False
            continue
        if trimmed.startswith("<!--"):
            flush()
            in_comment = "-->" not in trimmed
            continue

        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            if level <= 2:
                section = _section_for(heading.group(2)) if level == 2 else None
            elif decisionslib.DECISIONS_HEADING.match(line):
                section = None
            continue

        if section is None:
            continue
        if not trimmed or _RULE.match(line) or trimmed.startswith(">"):
            flush()
            continue

        if _KPI.match(trimmed):
            flush()
            item = (number, [trimmed], False)
            continue

        bullet = _BULLET.match(line)
        if bullet and (item is None or (len(bullet.group(1)) < 2 and "\t" not in bullet.group(1))):
            flush()
            item = (number, [bullet.group(2)], True)
            continue
        if item is None:
            item = (number, [trimmed], False)
        else:
            item[1].append(bullet.group(2) if bullet else trimmed)

    flush()
    return _number_rows(entries)


def _number_rows(entries):
    """`(line, row, authored_number)` triples with derived ids assigned.

    A derived id counts up from 1 per prefix, passing over every number an
    authored id of that prefix holds.
    """
    held = {}
    for _, prefix, number, _, _, _ in entries:
        if number is not None:
            held.setdefault(prefix, set()).add(number)
    counters = {}
    found = []
    for line, prefix, number, token, section_name, text in entries:
        if number is None:
            current = counters.get(prefix, 0) + 1
            while current in held.get(prefix, ()):
                current += 1
            counters[prefix] = current
            token = f"{prefix}-{current}"
        found.append((line, _make_row(token, section_name, text), number))
    return found


def _unfenced(text):
    """`(text with line endings as LF, the same text with fenced blocks blanked)`."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped, _ = vaultlib.strip_fenced_code(text)
    return text, stripped


def duplicate_report(text):
    """A message naming the lines of every authored id two rows hold, else None.

    `O-3` and `O-03` are one id. The message reads
    `duplicate requirement id O-03 on lines 12 and 14`.
    """
    if not text or not isinstance(text, str):
        return None
    _, stripped = _unfenced(text)
    holders = {}
    for line, row, number in _scan_sections(stripped):
        if number is not None:
            holders.setdefault((row["id"][0], number), []).append((line, row["id"]))
    messages = []
    for group in holders.values():
        if len(group) < 2:
            continue
        lines = [str(line) for line, _ in group]
        named = f"{', '.join(lines[:-1])} and {lines[-1]}"
        messages.append(f"duplicate requirement id {group[0][1]} on lines {named}")
    return "; ".join(messages) or None


def extract_requirements(text):
    """Every requirement row of a spec body, in document order.

    An empty or non-string `text`, and a spec without requirement sections,
    give an empty list.
    """
    if not text or not isinstance(text, str):
        return []
    text, stripped = _unfenced(text)

    located = [(line, row) for line, row, _ in _scan_sections(stripped)]
    decisions, _ = decisionslib.extract_decisions(text)
    for decision in decisions:
        row = _make_row(decision["id"], DECISIONS_SECTION, decision["text"])
        row["tags"] = list(decision["tags"])
        located.append((decision["line"], row))

    located.sort(key=lambda pair: pair[0])
    return [row for _, row in located]


def _cited_decisions(plan_text, task_id, spec_stem):
    """The `D-NN` ids the task's plan line cites from the spec named `spec_stem`."""
    stripped, _ = vaultlib.strip_fenced_code(plan_text.replace("\r\n", "\n").replace("\r", "\n"))
    task_line = re.compile(
        r"^\s*-\s+\[[ xX]\]\s+" + re.escape(task_id) + r"(?![A-Za-z0-9_-])"
    )
    prefix = spec_stem + "/"
    cited = set()
    for line in stripped.split("\n"):
        if not task_line.match(line):
            continue
        for field in _DECISIONS_CITATION.finditer(line):
            for entry in field.group(1).split(","):
                entry = entry.strip().strip("`")
                if entry.startswith(prefix):
                    cited.add(entry[len(prefix):])
    return cited


def rows_for_task(rows, plan_text, task_id, spec_stem):
    """The rows a task owes: every non-decision row, plus the decision rows
    its plan line cites as `decisions: [<spec_stem>/D-NN, ...]`.

    The task line is `- [ ] <task_id>: ...` (or `- [x]`); the id matches
    whole, so `TASK-1` never reads the line of `TASK-10`. A decision cited
    from another document is never claimed.
    """
    cited = _cited_decisions(plan_text, task_id, spec_stem)
    return [
        row
        for row in rows
        if not row["id"].startswith("D-") or row["id"] in cited
    ]
