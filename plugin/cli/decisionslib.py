"""Decision extraction from vault documents.

A decision is a `- **D-NN:** text` bullet (continuation lines indented under
it) inside a decisions section: a two- or three-hash heading whose first word
is Decision/Decisions, case-insensitive, any suffix - `## Decision`,
`## Decisions (made by the human)`, `### decisions`.

`extract_decisions` returns one of three outcomes, so a format mismatch can
never pass as a clean "nothing to check":

- `parsed`: at least one decision extracted and every decision-shaped bullet
  understood.
- `none-present`: no decision signals anywhere in the document.
- `could-not-parse`: decision-shaped content the grammars could not read.
  One malformed `- **D-` bullet poisons the whole extraction even when other
  bullets parsed, because silently dropping one decision is the exact failure
  this module exists to prevent. With zero extractions, a bare `D-` token, an
  ID-shaped bold-lead-in bullet, or an unterminated code fence is evidence of
  real entries the parser could not read.

Opt-outs: an `[informational]` or `[deferred]` bracket tag on the bullet, or
placement under a discretion subheading, marks the decision non-trackable.
It is still parsed and recorded, never gate-checked.

Fenced code blocks and inline code spans are never decision content, so a
document quoting the convention as an example parses clean.

Pure standard library, no side effects.
"""

import re

import vaultlib

# A decisions section heading: two or three hashes, then Decision/Decisions,
# then anything (suffixes like "(made by the human)").
DECISIONS_HEADING = re.compile(r"^(#{2,3})\s*Decisions?\b", re.IGNORECASE)

# Any heading line; a decisions section ends at the next heading whose level
# is the same as or higher than the section's own.
_ANY_HEADING = re.compile(r"^(#{1,6})\s")

# Bullet grammars, tried in order. All accept an optional bracket tag list
# after the ID. Colon form: `- **D-NN:** text` - the separator colon is the
# only colon permitted before the closing bold.
_BULLET_COLON = re.compile(
    r"^\s*-\s+\*\*D-([A-Za-z0-9][A-Za-z0-9_-]*)(?:\s*\[([^\]]+)\])?[^:*]*:\*\*\s*(.*)$"
)
# Em-dash form: `- **D-NN — title** body`. Compass-authored prose never uses
# em-dashes, but pasted-in content may; accepts U+2014 and U+2013.
_BULLET_EMDASH = re.compile(
    r"^\s*-\s+\*\*D-([A-Za-z0-9][A-Za-z0-9_-]*)(?:\s*\[([^\]]+)\])?"
    r"[^*]*[—–][^*]*\*\*\s*(.*)$"
)
# Titled-colon form: `- **D-NN: Title.** body`. A strict superset of the
# colon form, so it is checked last and only catches bullets the others miss.
_BULLET_TITLED_COLON = re.compile(
    r"^\s*-\s+\*\*D-([A-Za-z0-9][A-Za-z0-9_-]*)(?:\s*\[([^\]]+)\])?[^:*]*:[^:*]*\*\*\s*(.*)$"
)
_BULLET_GRAMMARS = (_BULLET_COLON, _BULLET_EMDASH, _BULLET_TITLED_COLON)

# A line shaped like a decision bullet regardless of grammar. Failing every
# grammar above makes it a parse miss.
_BULLET_SHAPED = re.compile(r"^\s*-\s+\*\*D-")

# Evidence that unparsed content holds real decision entries: a D- token...
_D_TOKEN = re.compile(r"\bD-[A-Za-z0-9]")
# ...or a bullet whose bold lead-in is an ID-shaped token (uppercase prefix,
# optional digits, hyphen, alphanumeric). Matches `D-01` / `DEC-01`, not
# prose labels like `- **Scope:**` - a false could-not-parse would hard-block
# the coverage gate on a legitimate prose section.
_BOLD_ID_BULLET = re.compile(r"^\s*-\s+\*\*[A-Z]+[0-9]*-[A-Za-z0-9]", re.MULTILINE)

# Subheadings inside a decisions section switch the discretion state.
_SUBHEADING = re.compile(r"^#{3,6}\s+(.+?)\s*$")

# Quote characters normalized away before the discretion match, so
# "Claude's Discretion" matches under any quote rendering.
_QUOTE_CHARS = re.compile("[‘’‚‛“”„‟'\"`]")

# Bracket tags that make a decision non-trackable.
NON_TRACKABLE_TAGS = {"informational", "deferred"}


def _is_discretion_heading(heading_text):
    """True when a subheading delegates its bullets to agent discretion
    (`### Claude's Discretion`, `### Builder discretion`, ...)."""
    normalized = _QUOTE_CHARS.sub("", heading_text).strip().lower()
    return normalized.endswith("discretion")


def _decision_sections(stripped_text):
    """Locate every decisions section in fence-stripped text.

    Returns `(start_line, body_lines)` pairs; `start_line` is the 1-based
    line number of the first body line. Fence stripping preserves the line
    count, so these numbers hold for the original text.
    """
    lines = stripped_text.split("\n")
    sections = []
    i = 0
    while i < len(lines):
        match = DECISIONS_HEADING.match(lines[i])
        if not match:
            i += 1
            continue
        level = len(match.group(1))
        body_start = i + 1
        j = body_start
        while j < len(lines):
            heading = _ANY_HEADING.match(lines[j])
            if heading and len(heading.group(1)) <= level:
                break
            j += 1
        sections.append((body_start + 1, lines[body_start:j]))
        i = j
    return sections


def _parse_decision_lines(body_lines, start_line):
    """Parse decision bullets from a section body.

    Returns `(decisions, parse_misses)`. Each decision is a dict with `id`,
    `text`, `trackable`, `tags`, and `line`. Subheadings switch the
    discretion state; an indented non-bullet line continues the current
    decision's text; a blank line or unrelated content closes it.
    """
    decisions = []
    misses = 0
    in_discretion = False
    current = None

    def flush():
        nonlocal current
        if current is not None:
            current["text"] = current["text"].strip()
            decisions.append(current)
            current = None

    for offset, line in enumerate(body_lines):
        trimmed = line.strip()

        heading = _SUBHEADING.match(trimmed)
        if heading:
            flush()
            in_discretion = _is_discretion_heading(heading.group(1))
            continue

        matched = None
        for grammar in _BULLET_GRAMMARS:
            matched = grammar.match(line)
            if matched:
                break
        if matched:
            flush()
            tags = []
            if matched.group(2):
                tags = [
                    tag.strip().lower()
                    for tag in matched.group(2).split(",")
                    if tag.strip()
                ]
            current = {
                "id": "D-" + matched.group(1),
                "text": matched.group(3) or "",
                "tags": tags,
                "trackable": not in_discretion
                and not any(tag in NON_TRACKABLE_TAGS for tag in tags),
                "line": start_line + offset,
            }
            continue

        if _BULLET_SHAPED.match(line):
            flush()
            misses += 1
            continue

        if (
            current is not None
            and trimmed
            and not trimmed.startswith("-")
            and line[:1] in (" ", "\t")
        ):
            current["text"] += " " + trimmed
            continue

        if not trimmed:
            flush()

    flush()
    return decisions, misses


def extract_decisions(text):
    """Extract decisions from a document's full text.

    Returns `(decisions, outcome)`. Each decision is a dict with `id`
    (`D-NN`), `text`, `trackable`, `tags`, and `line` (1-based in the
    original text); `outcome` is `parsed`, `none-present`, or
    `could-not-parse` per the module contract.
    """
    if not text or not isinstance(text, str):
        return [], "none-present"
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    stripped, unterminated = vaultlib.strip_fenced_code(text)
    sections = _decision_sections(stripped)

    if sections:
        decisions = []
        misses = 0
        bodies = []
        for start_line, body_lines in sections:
            found, missed = _parse_decision_lines(body_lines, start_line)
            decisions.extend(found)
            misses += missed
            bodies.append("\n".join(body_lines))
        if misses > 0:
            return decisions, "could-not-parse"
        if decisions:
            return decisions, "parsed"
        evidence = vaultlib.strip_inline_code("\n".join(bodies))
        if (
            _D_TOKEN.search(evidence)
            or _BOLD_ID_BULLET.search(evidence)
            or unterminated
        ):
            return [], "could-not-parse"
        return [], "none-present"

    evidence = vaultlib.strip_inline_code(stripped)
    if unterminated or _D_TOKEN.search(evidence):
        return [], "could-not-parse"
    return [], "none-present"
