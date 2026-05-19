---
name: research
description: Router for research. Dispatches to /compass:research-codebase or /compass:research-papers depending on whether the question is about code or about an academic paper / algorithm.
version: 1.0.0
allowed-tools: [Read, Bash]
when_to_use: "Use when the user wants to research something but the type (code vs paper) isn't obvious. Triggers: 'research this', 'investigate', 'find out how X works', 'do some research'. If the user already said 'research the codebase' or 'research this paper', use the specific skill directly."
argument-hint: "[codebase | papers] <question>"
---

# Research - Router

Compass has two research skills with different shapes. Pick the right one.

| Skill | When | What it spawns |
|-------|------|----------------|
| `/compass:research-codebase` | "How does X work in the codebase?", "Where is Y handled?", "Trace this flow" | codebase-locator, codebase-analyzer, pattern-finder. Synthesizes a code-research doc. |
| `/compass:research-papers` | "Explain this paper", "What's the prior art for X", "Deep research on this algorithm" | Three researchers (Current / Backward / Forward) + reviewer. Synthesizes a paper-research doc with citation graph. |

## Protocol

### 1. Parse the argument

- `codebase <question>` → dispatch to `/compass:research-codebase`.
- `papers <topic | arXiv ID>` → dispatch to `/compass:research-papers`.
- No prefix → classify the question.

### 2. Classify if needed

If the question is ambiguous, ask once:

> Codebase or papers?
> - Codebase: how something in this repo works
> - Papers: an algorithm, technique, or academic paper

If the question clearly maps (e.g., mentions an arXiv ID, paper title, "algorithm", "technique"; or mentions a file path, function name, "where", "trace"), skip the question and dispatch.

### 3. Dispatch

Invoke the chosen skill with the question. Don't reimplement either skill's logic here.

## Failure modes worth naming

- Reimplementing one of the two research flows inline. This skill is a router.
- Forcing the user to clarify when the question is clearly one type or the other.
- Defaulting to codebase research when the user clearly asked about a paper (or vice versa).
