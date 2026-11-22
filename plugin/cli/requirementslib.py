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
    """Rows for the O, S, C and K ids, each paired with its 1-based line."""
    counters = {"O": 0, "S": 0, "C": 0, "K": 0}
    found = []
    section = None
    item = None
    in_comment = False

    def flush():
        nonlocal item
        if item is None:
            return
        start, parts = item
        item = None
        text = normalize_text(" ".join(parts))
        if not text:
            return
        kpi = _KPI.match(text)
        if kpi:
            prefix = "K"
            text = kpi.group(1)
            if not text.strip():
                return
        else:
            prefix = section[1]
        counters[prefix] += 1
        found.append((start, _make_row(f"{prefix}-{counters[prefix]}", section[0], text)))

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
            item = (number, [trimmed])
            continue

        bullet = _BULLET.match(line)
        if bullet and (item is None or (len(bullet.group(1)) < 2 and "\t" not in bullet.group(1))):
            flush()
            item = (number, [bullet.group(2)])
            continue
        if item is None:
            item = (number, [trimmed])
        else:
            item[1].append(bullet.group(2) if bullet else trimmed)

    flush()
    return found


def extract_requirements(text):
    """Every requirement row of a spec body, in document order.

    An empty or non-string `text`, and a spec without requirement sections,
    give an empty list.
    """
    if not text or not isinstance(text, str):
        return []
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped, _ = vaultlib.strip_fenced_code(text)

    located = _scan_sections(stripped)
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
