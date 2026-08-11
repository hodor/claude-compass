"""Plan detail-region classification.

A rolling-wave plan carries three kinds of line: detailed (the current
wave, fully specified), scoped (a "## Later" intent line naming work not
yet elaborated), and record (a "## Wave N elaborated" section, which
quotes past intent and claims nothing). `classify_lines` reads a plan's
full text and reports which state each line sits in.

`regions` is sparse: it maps a 1-based line number to `"scoped"` or
`"record"` only. A line absent from the map is detailed - the state every
line has always had, so a plan written entirely in the old fully-detailed
shape (no `## Later` heading anywhere) classifies as an empty map.

Region rules: a Later region opens on a `## Later` heading (case
insensitive, word-bounded so `## Latergrade` does not match) and closes at
the next level-1 or level-2 heading, or EOF; a level-3-or-deeper heading
stays inside it. A record region opens on a `## Wave(s) ... elaborated`
heading and closes the same way. The two kinds are independent - a record
region earlier in the document does not prevent a Later region from
opening after it, and a promoted `## Wave N (detailed)` heading, carrying
no "elaborated" token, opens neither.

Inside a Later region, a task line's `commit-upfront:` field overrides the
line back to detailed: one of its trailing comma-separated fields must
*begin* with the `commit-upfront:` token, checked after inline code spans
are stripped, so a bare or backticked mid-sentence mention never triggers
it. The override covers the task line's indented continuation lines and a
blank line inside them; it ends at the next task line or the next
non-blank unindented line.

Both the Later and record regions are read from fence-stripped,
inline-code-stripped text, so an example quoted inside a fenced block
never opens a region and a mention inside backticks never triggers the
override. Fence stripping preserves the line count, so the reported
numbers index the original text. A fence that never closes blanks
everything after it; the caller receives `unterminated_fence=True` and,
because the blanked text carries no headings, an empty region map -
callers must report the plan as unreadable rather than treat that
emptiness as "nothing scoped."

`TASK_LINE` is the one regex the whole CLI uses to recognize a task line
(`- [ ] TASK-NNN: ...`); this module owns it because both `coverage` and
`lesson-coverage` read the region map built from it.

Pure standard library, no side effects.
"""

import re

import vaultlib

# A task line: an optional leading indent, a checkbox, then TASK-<id>:.
TASK_LINE = re.compile(r"^\s*-\s+\[[ xX]\]\s+(TASK-[A-Za-z0-9_-]+):")

# Any heading line, with its hash count in group(1).
_ANY_HEADING = re.compile(r"^(#{1,6})\s")

# A Later-region heading: exactly two hashes, "Later", then a word boundary
# so "## Latergrade" does not match.
_LATER_HEADING = re.compile(r"^##\s+Later\b", re.IGNORECASE)

# A record-region heading: exactly two hashes, "Wave" or "Waves", then
# "elaborated" somewhere after it on the same line.
_RECORD_HEADING = re.compile(r"^##\s+Waves?\b.*\belaborated\b", re.IGNORECASE)

# The commit-upfront override token. A trailing comma-separated field on a
# task line must begin with this, after inline code stripping, to trigger.
_COMMIT_UPFRONT_TOKEN = "commit-upfront:"


def _triggers_commit_upfront(line):
    """True if one of `line`'s comma-separated fields begins with the
    commit-upfront token. A mid-sentence mention - bare or backticked - is
    never a field start, so it never triggers."""
    return any(
        field.lstrip().startswith(_COMMIT_UPFRONT_TOKEN)
        for field in line.split(",")
    )


def _classify_content_line(line, state, override_active, line_no, regions):
    """Assign `line_no` its state (or leave it absent, i.e. detailed) and
    return the override state that carries into the next line.

    `state` is the region the line sits in (`None`, `"scoped"`, or
    `"record"`); `override_active` is whether a `commit-upfront:` block is
    still open from a prior line. Only the scoped region tracks an
    override - a record region claims nothing regardless of what a task
    line inside it might say.
    """
    if state is None:
        return False
    if state == "record":
        regions[line_no] = "record"
        return False

    if TASK_LINE.match(line):
        if _triggers_commit_upfront(line):
            return True
        regions[line_no] = "scoped"
        return False

    if line.strip() == "":
        if override_active:
            return True
        regions[line_no] = "scoped"
        return False

    indented = line[:1] in (" ", "\t")
    if override_active and indented:
        return True

    regions[line_no] = "scoped"
    return False


def classify_lines(text):
    """Classify every line of a plan's text into its detail region.

    Returns `(regions, unterminated_fence)`. See the module docstring for
    the region rules, the sparse-map convention, and the commit-upfront
    override.
    """
    if not isinstance(text, str) or not text:
        return {}, False

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped, unterminated_fence = vaultlib.strip_fenced_code(text)
    stripped = vaultlib.strip_inline_code(stripped)

    regions = {}
    state = None
    override_active = False

    for offset, line in enumerate(stripped.split("\n")):
        line_no = offset + 1
        heading = _ANY_HEADING.match(line)
        if heading and len(heading.group(1)) <= 2:
            if _LATER_HEADING.match(line):
                state = "scoped"
            elif _RECORD_HEADING.match(line):
                state = "record"
            else:
                state = None
            override_active = False
            continue
        override_active = _classify_content_line(
            line, state, override_active, line_no, regions
        )

    return regions, unterminated_fence
