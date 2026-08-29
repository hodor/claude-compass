"""`compass sweep` - move completed tasks out of active.md (ADR-014).

active.md is hot-path: every agent turn re-pays its tokens, so a done task
line is a permanent tax once nobody removes it. The sweep is the mechanical
remover: a top-level `- [x]` item whose block has no unchecked descendant
leaves active.md, and a section whose every task is done moves wholesale -
heading, prose and all - so initiative context survives in the record.
Everything reaped is appended verbatim to `archive/done.md` under a per-day
heading naming its source section; removal is relocation, never destruction.

Membership is never judged: checkbox state, indentation and headings are the
whole grammar. Fenced code is opaque. Anything the grammar cannot classify
stays in place.

`compass sync` calls `sweep_active(apply=True)` on every run, which makes the
PostToolUse hook the guaranteed zero-token trigger. The standalone command
dry-runs by default; `--apply` performs the move.
"""

import datetime
import re
import sys

import vaultlib

ACTIVE_FILE = "active.md"
DONE_FILE = "archive/done.md"

TASK_LINE = re.compile(r"^- \[( |x|X)\] ")
ANY_TASK = re.compile(r"^\s*- \[( |x|X)\] ")
OPEN_TASK = re.compile(r"^\s*- \[ \] ")
FENCE = re.compile(r"^\s*```")

DONE_HEADER = """---
title: Done Log
summary: "completed tasks swept out of active.md by compass sweep, verbatim, newest day last"
---

# Done Log
"""


def _split_frontmatter(lines):
    """Return (frontmatter_lines, body_lines); frontmatter kept verbatim."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[: i + 1], lines[i + 1 :]
    return [], lines


def _parse_sections(body):
    """Split body lines into [(heading_line_or_None, lines)] where the first
    tuple is the preamble (heading None). Fence state is tracked so a `##`
    inside a code block never opens a section."""
    sections = [(None, [])]
    in_fence = False
    for line in body:
        if FENCE.match(line):
            in_fence = not in_fence
            sections[-1][1].append(line)
            continue
        if not in_fence and line.startswith("## "):
            sections.append((line, []))
            continue
        sections[-1][1].append(line)
    return sections


def _parse_items(lines):
    """Split a section's lines into blocks: (kind, lines) where kind is
    `text`, `open`, or `done`. An item block is a top-level task line plus
    every following indented or blank line up to the next top-level line;
    trailing blank lines stay with the block. A `done` block contains no
    unchecked descendant. Fenced lines are always `text` and end any item."""
    blocks = []
    current = None  # (kind, lines) being accumulated for an item
    in_fence = False

    def flush():
        nonlocal current
        if current:
            blocks.append(current)
            current = None

    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            flush()
            blocks.append(("text", [line]))
            continue
        if in_fence:
            flush()
            blocks.append(("text", [line]))
            continue
        match = TASK_LINE.match(line)
        if match:
            flush()
            kind = "open" if match.group(1) == " " else "done"
            current = (kind, [line])
            continue
        if current is not None and (line.startswith((" ", "\t")) or not line.strip()):
            current[1].append(line)
            continue
        flush()
        blocks.append(("text", [line]))
    flush()

    # A checked parent with an unchecked descendant is not done.
    resolved = []
    for kind, block in blocks:
        if kind == "done" and any(OPEN_TASK.match(l) for l in block[1:]):
            kind = "open"
        resolved.append((kind, block))
    return resolved


def _rstrip_blanks(lines):
    out = list(lines)
    while out and not out[-1].strip():
        out.pop()
    return out


def collect(vault_root):
    """Parse active.md and return (frontmatter, sections) where each section
    is a dict: heading (None for preamble), blocks, all_done (had at least
    one task and every task block is done)."""
    path = vault_root / ACTIVE_FILE
    if not path.is_file():
        return None, []
    lines = vaultlib.read_vault_text(path).split("\n")
    front, body = _split_frontmatter(lines)
    sections = []
    for heading, sec_lines in _parse_sections(body):
        blocks = _parse_items(sec_lines)
        kinds = [k for k, _ in blocks if k in ("open", "done")]
        sections.append(
            {
                "heading": heading,
                "blocks": blocks,
                "all_done": bool(kinds) and all(k == "done" for k in kinds)
                # The preamble is never moved wholesale: it holds the H1.
                and heading is not None,
            }
        )
    return front, sections


def sweep_active(vault_root, apply=True, today=None):
    """Reap done items (and fully-done sections) from active.md into
    archive/done.md. Returns {"items", "sections", "moved"} where moved is a
    list of human-readable descriptions. `apply=False` reports only."""
    today = today or datetime.date.today().isoformat()
    front, sections = collect(vault_root)
    if front is None and not sections:
        return {"items": 0, "sections": 0, "moved": []}

    kept = []
    archived = []  # (source_heading_text, lines) chunks for done.md
    items = swept_sections = 0
    moved = []

    for sec in sections:
        title = (sec["heading"] or "## (preamble)")[3:].strip()
        if sec["all_done"]:
            chunk = [sec["heading"].replace("##", "###", 1)]
            for _, block in sec["blocks"]:
                chunk.extend(block)
            archived.append(_rstrip_blanks(chunk))
            swept_sections += 1
            moved.append(f'section "{title}" (whole)')
            continue
        sec_kept = [sec["heading"]] if sec["heading"] else []
        sec_moved = []
        for kind, block in sec["blocks"]:
            if kind == "done":
                sec_moved.extend(_rstrip_blanks(block))
                items += 1
            else:
                sec_kept.extend(block)
        kept.extend(sec_kept)
        if sec_moved:
            archived.append([f"### {title}"] + sec_moved)
            moved.append(f'{sum(1 for k, _ in sec["blocks"] if k == "done")} item(s) from "{title}"')

    report = {"items": items, "sections": swept_sections, "moved": moved}
    if not archived or not apply:
        return report

    active_text = "\n".join(front + _rstrip_blanks(kept)) + "\n"
    vaultlib.write_text_lf(vault_root / ACTIVE_FILE, active_text)

    done_path = vault_root / DONE_FILE
    done_path.parent.mkdir(parents=True, exist_ok=True)
    done_text = vaultlib.read_vault_text(done_path) if done_path.is_file() else DONE_HEADER
    day_heading = f"## {today}"
    day_headings = [l for l in done_text.split("\n") if l.startswith("## ")]
    parts = [done_text.rstrip("\n")]
    if not day_headings or day_headings[-1] != day_heading:
        parts.append("\n" + day_heading)
    for chunk in archived:
        parts.append("\n" + "\n".join(chunk))
    vaultlib.write_text_lf(done_path, "\n".join(parts) + "\n")
    return report


def run(args):
    apply = "--apply" in args
    vault_root = vaultlib.find_vault_root()
    report = sweep_active(vault_root, apply=apply)
    verb = "swept" if apply else "would sweep"
    if not report["moved"]:
        sys.stdout.write("compass sweep: active.md is clean, nothing to sweep\n")
        return 0
    for desc in report["moved"]:
        sys.stdout.write(f"{verb}: {desc}\n")
    sys.stdout.write(
        f"compass sweep: {verb} {report['items']} item(s), "
        f"{report['sections']} whole section(s) -> {DONE_FILE}\n"
    )
    return 0
