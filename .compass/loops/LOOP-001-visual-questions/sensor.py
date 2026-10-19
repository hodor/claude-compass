"""Sensor for LOOP-001-visual-questions.

Finds every point in the shipped skills, agent templates and rules where the
agent asks the human something, and reports the points whose markdown section
does not route the question through the AskUserQuestion tool, one question
per call. An agent template runs as a subagent, which cannot call
AskUserQuestion; its point is satisfied when the section returns the question
to the orchestrator, which asks it.

Item identity: <posix path>:<heading text>:<matched text trimmed to 80 chars>.
Prints {"valid": true, "value": N, "items": [...]} or {"valid": false, "reason": ...}.
Pass --list to print every match with its line number and satisfied state.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GLOBS = [
    "plugin/skills/*/SKILL.md",
    "plugin/templates/agents/*.md",
    "plugin/templates/rules/*.md",
]
AGENT_PREFIX = "plugin/templates/agents/"

# A line is a point where the agent asks the human when any of these match.
ASK_PATTERNS = [
    re.compile(r"Approve\?"),
    re.compile(r"\b[Aa]sks? the human\b"),
    re.compile(r"\bBlock on the reply\b"),
    re.compile(r"\bfor approval\b"),
    re.compile(r"\b[Ww]ait for (the )?human\b(?! review)"),
    re.compile(r"\b[Aa]sk:"),
    re.compile(r"\b[Aa]sk (once|one|whether|which|how|what|why|for|if)\b"),
    re.compile(r"\b[Aa]sk(\.| -|$)"),
    re.compile(r"\boffer: \""),
    re.compile(r"\bconfirm before\b"),
    re.compile(r"\bonly his approval\b"),
    re.compile(r"\*\*Q\d+:\*\*"),
    # A question with its answer options spelled out: "Fix? (yes / skip / abort)".
    re.compile(r"\?\s*\([^)]*/[^)]*\)"),
    # A numbered or labelled question quoted inside a list item.
    re.compile(r"^\s*\d+\.\s+\*\*[^*]+:\*\*\s+\"[^\"]*\?\""),
]
# A blockquote line that holds a question or a free-text prompt to the human.
BLOCKQUOTE_QUESTION = re.compile(r"^\s*>.*\?\s*\"?\s*$")
BLOCKQUOTE_PROMPT = re.compile(r"^\s*>\s*\"Tell me\b")
# A line inside a fenced block that ends in a question shown to the human.
FENCED_QUESTION = re.compile(r"\?\s*(\([^)]*\))?\s*$")

# Lines that match a pattern above but are not a question to the human.
EXCLUDE = [
    re.compile(r"\b([Dd]on't|[Dd]o not|[Nn]ever|without)\b[^.]{0,20}\bask"),
    re.compile(r"\bno approval is asked\b"),
    re.compile(r"For each (Need|Decision), ask\b"),
    re.compile(r"\bthink to ask\b"),
]
# Fenced lines that end in "?" but are a tool checklist or a report line.
FENCED_EXCLUDE = re.compile(r"^\s*(Glob|Read|Grep|Bash):|^\s*- \[[ x]\]")
# Files whose fenced "?" lines are document templates for the author.
FENCED_EXCLUDE_FILES = {"plugin/skills/obsidian/SKILL.md"}

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")

ONE_PER_CALL = re.compile(
    r"one question (per|at a time|in each|each)|exactly one question|"
    r"single question|never batch", re.IGNORECASE)
TO_ORCHESTRATOR = re.compile(r"return\w*\b.{0,80}\borchestrator\b", re.IGNORECASE | re.DOTALL)


def strip_frontmatter(lines):
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def parse(path):
    """Yield (line_no, line, in_fence, heading_index) and the heading list."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = strip_frontmatter(lines)
    headings = []  # (line_index, level, text)
    rows = []
    in_fence = False
    current = None
    for i in range(start, len(lines)):
        line = lines[i]
        if FENCE.match(line):
            in_fence = not in_fence
            rows.append((i, line, True, current, True))
            continue
        m = None if in_fence else HEADING.match(line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2)))
            current = len(headings) - 1
            rows.append((i, line, False, current, False))
            continue
        rows.append((i, line, in_fence, current, False))
    return lines, start, headings, rows


def section_text(lines, start, headings, idx):
    if idx is None:
        end = headings[0][0] if headings else len(lines)
        return "\n".join(lines[start:end])
    line_i, level, _ = headings[idx]
    end = len(lines)
    for j in range(idx + 1, len(headings)):
        if headings[j][1] <= level:
            end = headings[j][0]
            break
    return "\n".join(lines[line_i:end])


def is_point(rel, line, in_fence, is_fence_marker):
    if is_fence_marker:
        return False
    if any(p.search(line) for p in EXCLUDE):
        return False
    if line.lstrip().startswith("|"):
        return False
    if in_fence:
        if rel in FENCED_EXCLUDE_FILES or FENCED_EXCLUDE.search(line):
            return False
        return bool(line.strip()) and bool(FENCED_QUESTION.search(line.strip()))
    if BLOCKQUOTE_QUESTION.match(line) or BLOCKQUOTE_PROMPT.match(line):
        return True
    return any(p.search(line) for p in ASK_PATTERNS)


def satisfied(rel, section):
    if rel.startswith(AGENT_PREFIX):
        return bool(TO_ORCHESTRATOR.search(section))
    return "AskUserQuestion" in section and bool(ONE_PER_CALL.search(section))


def scan():
    points = []
    for pattern in GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            lines, start, headings, rows = parse(path)
            for i, line, in_fence, idx, marker in rows:
                if not is_point(rel, line, in_fence, marker):
                    continue
                heading = headings[idx][2] if idx is not None else "(top)"
                text = " ".join(line.strip().lstrip(">").split())[:80]
                ok = satisfied(rel, section_text(lines, start, headings, idx))
                points.append((rel, i + 1, heading, text, ok))
    return points


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        points = scan()
        if not points:
            raise RuntimeError("no question points found; the file globs or patterns are broken")
        if "--list" in sys.argv:
            for rel, n, heading, text, ok in points:
                print(f"{'OK ' if ok else 'BAD'} {rel}:{n} [{heading}] {text}")
            return
        items = sorted({f"{rel}:{heading}:{text}" for rel, _, heading, text, ok in points if not ok})
        print(json.dumps({"valid": True, "value": len(items), "items": items}))
    except Exception as exc:  # noqa: BLE001 - any failure is an invalid reading
        print(json.dumps({"valid": False, "reason": f"{type(exc).__name__}: {exc}"}))


if __name__ == "__main__":
    main()
