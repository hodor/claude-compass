---
name: lessons
description: How to search and apply lessons from the .compass/ vault. Catalog structure and search algorithm. Creation is handled by the lesson-write skill, called by extract-lessons or /compass:learned - never created in agent prose.
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
---

# Lessons - Search & Apply

Lessons capture hard-won knowledge that prevents the same mistake twice. Per Reinertsen (*Principles of Product Development Flow*), two types:

- **Process** (`category: process`) - how to build. "Mocking the DB in integration tests hides migration bugs."
- **Domain** (`category: domain`) - what to build. "Users need batch export, not single-file."

Process lessons improve how agents work. Domain lessons improve what agents build.

## Catalog

`.compass/meta/lessons-catalog.yaml` is the O(1) tag lookup. Single source of truth for what lessons exist.

```yaml
lessons:
  - file: "LESSON-yaml-frontmatter-quoting.md"
    status: active
    category: process
    area: workflow
    tags: [yaml, frontmatter, quoting]
    score: 8
    summary: "YAML frontmatter values with colons must be quoted"
  - file: "LESSON-batch-export-user-need.md"
    status: active
    category: domain
    area: backend
    tags: [export, users, requirements]
    score: 6
    summary: "Users need batch export, not single-file export"
```

Fields:
- `file` - lesson filename in `.compass/lessons/`
- `status` - `active` or `archived`
- `category` - `process` or `domain`
- `area` - from the lesson's frontmatter
- `tags` - for matching
- `score` - 1-10, higher = more reinforced (bumped on recurrence by `lesson-write`)
- `summary` - one line, matches the lesson's own frontmatter `summary`

## When to search

Before making plans, implementing tasks, or starting any work that changes code or vault structure. The catalog is cheap to read - when in doubt, check it.

## Search algorithm

`compass lessons` is the primary retrieval path: it reads the catalog, ranks rows by tag overlap, area match, text overlap, and score (escalated rows always first), and skips `status: archived`. Nothing here re-implements that ranking by hand.

1. Run `compass lessons --for <doc>` (or `--area`/`--tags`/`--text`) with `--context <agent-or-skill-name>` naming the caller.
2. Read the full lesson files for the filenames it returns that you judge relevant (3-5 max) - the command surfaces candidates, it doesn't read bodies.
3. Apply.

Every run appends a row to `.compass/tmp/retrieval-log.jsonl` recording the query and what surfaced, so this step is auditable rather than asserted.

If the catalog does not exist (`compass lessons` exits 1 naming a malformed vault), fall back to a manual crawl:

```
Glob: .compass/lessons/*.md
Grep: tags matching current work area
```

This fallback is malformed-vault recovery only. The catalog should always exist.

## Escalated lessons

A lesson with `escalated: <date>` in its frontmatter has recurred 3 times despite being captured. Surface it with extra emphasis in the next session's hot path. The lesson is either worded too vaguely to apply, or the search algorithm is failing to retrieve it before work. Flag for human review.

`/compass:consolidate` does not archive escalated lessons. The human clears the flag after rewording or fixing the retrieval gap.

## Capture loop

Capture is harness-owned: no agent decides mid-conversation to go write a lesson. The `Stop` hook runs `compass capture-check` on every turn, bumping a turn counter and evaluating a due condition against the signals recorded so far - `SubagentStop` and `TeammateIdle` run `compass capture-signal`, which records a signal for a finishing subagent (`validator-finished`, `debug-finished`, `builder-finished`, or a weaker `subagent-finished`/idle signal) and, from the vault-write path, `handoff-written` or `vault-write`. An opportunity is due when the turn interval is reached with at least one signal in the window, or immediately on a strong signal alone (a handoff written, a validator or debug subagent finishing, an unprocessed build phase summary). Neither hook spawns an agent - `due()` is arithmetic over counters and signals, not a judgment call.

When due, `capture-check` opens `.compass/tmp/capture-opportunities/OPP-<UTC>/opportunity.json` and emits the Claude Code stop-hook block contract naming it, so the capture pass runs as a real turn instead of prose the model can skip. The `extract-lessons` skill reads the opportunity, checks its binary triggers (fix-loop >=2, validator deviation, debug invoked, STOP-and-report, plan revised, handoff written, interval-reached-with-signal), applies the anti-list, and hands survivors to `lesson-write`. It also runs a contradiction check against the catalog: evidence that falsifies or narrows an existing active lesson routes a revise or archive payload through `lesson-write` instead of a fresh candidate - revise edits the matched lesson's body, archive sets `status: archived` (never deletes). `compass capture-close` then closes the opportunity with its fired/written/rejected/revised/archived counts.

Every step of an opportunity's lifecycle - opened, skipped (with the arithmetic reason), fired, closed - appends a row to `.compass/tmp/capture-log.jsonl`, so "reviewed and found nothing" and "never ran" are always distinguishable rows rather than the same silence. `compass capture-stats` turns that log into fire rate, write rate, and a per-trigger breakdown.

## Creating lessons

Do NOT write lessons from agent prose. Creation goes through the `lesson-write` skill, called by:

- `extract-lessons` - retrospective capture at a capture opportunity (auto, see Capture loop above)
- `/compass:learned` - in-the-moment human capture (manual)

Both paths share dedup, anti-list filtering, atomic 3-file writes, and the 5-line body cap. See `lesson-write/SKILL.md` for the protocol.

## Application audit

`compass lesson-coverage <plan>` checks whether the lessons a plan surfaced were actually used. A plan task line carries an optional `lessons: [LESSON-slug, ...]` field, in the same position as `decisions:`. The command resolves each citation against the catalog (archived rows included - citing one is informative, not a mistake) and reports three statuses: `cited` (the citation resolved to a catalog row), `surfaced-but-uncited` (the lesson ranks for the plan's own area/tags but no task cited it - advisory, since reading a lesson and correctly judging it irrelevant is a normal outcome), and `unresolvable` (a citation naming no catalog row, a typo to fix). The validator runs it report-only as a standard protocol step; low or missing coverage is a finding in its report, never a block on the verdict.

## File format

Lessons live in `.compass/lessons/` as markdown files with YAML frontmatter. The body is free-form, hard-capped at 5 lines. See the Lesson template in `obsidian/SKILL.md` for the frontmatter schema.
