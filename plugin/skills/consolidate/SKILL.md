---
name: consolidate
description: Long-horizon merge, prune, and demote pass over the lessons set. Runs only when a hard-cap warning is present (proves bloat triggered). Merges near-duplicates the per-phase dedup missed, rewrites verbose bodies, archives stale baseline-score lessons, trims seen arrays, rebuilds the catalog and the index Lessons section. Never archives escalated lessons; flags them for human review.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit]
argument-hint: "(no arguments; uses warning state)"
when_to_use: "Run /compass:consolidate when the next session's hot path surfaces a cap-exceeded warning. Do not run on a fixed cadence - the bloat trigger is the contract."
---

# /compass:consolidate - Lessons Consolidation

Long-horizon cleanup. Runs only when needed. Never archives lessons silently.

## Pre-check

Read `.compass/index.md` and `.compass/meta/lessons-catalog.yaml`. Look for any of these warning markers:

- `<!-- WARNING: index.md exceeded cap.`
- `# WARNING: catalog exceeded cap.`
- `# WARNING: lesson count exceeded 50.`

If none present, exit: `no consolidation needed (no cap warning)`. The bloat trigger is the contract; do not run unprompted.

## Protocol

### 1. Load every lesson

Glob `.compass/lessons/*.md`. Read each file's full frontmatter and body. Build an in-memory list with: filename, category, area, tags, score, summary, body, created, updated, seen, escalated.

### 2. Surface escalated lessons FIRST

For each lesson with `escalated:` in its frontmatter:

- Surface to the human as a separate report section before any merge/prune happens
- Format: "[[LESSON-name]] - escalated <date> - reason: <escalation_reason> - score: <N> - propose: reword OR fix retrieval"
- These do NOT participate in the rest of consolidation. They wait for human review.

If any escalated lessons exist, pause for human input before continuing. The human either rewords the lesson (clearing `escalated`) or accepts the flag and tells you to continue.

### 3. Merge near-duplicates

For each pair of non-escalated lessons, judge overlap:

- Same `category` AND `area` AND >=2 shared tags AND summaries semantically equivalent
- OR: bodies say the same rule with different phrasing

If a pair matches, merge:

- Keep the lesson with higher `score` (or earlier `created` if tied)
- Sum the `score` values, cap at 10
- Union the `tags`
- Union the `seen` arrays, then trim per step 5
- The losing lesson becomes `status: archived`, its filename is added to the kept lesson's frontmatter as `merged_from: ["LESSON-loser.md"]`
- The body of the kept lesson is preserved unchanged unless the loser had nuance worth absorbing; if so, compress and fit under the 5-line cap

Report every merge for the human's audit.

### 4. Rewrite verbose bodies

For each lesson body longer than 5 lines: compress to <=5 lines. Keep the rule + reason; drop specific instances. Use judgment, not mechanical truncation.

Report every rewrite with before/after for the human's audit.

### 5. Trim seen arrays

For each lesson with `seen: [...]` of more than 3 entries: keep the 3 most recent dates. Drop the rest.

### 6. Archive stale baseline lessons

For each non-escalated lesson where ALL of these hold:

- `score == 5` (never been reinforced)
- `seen: []` (never recurred)
- `updated` was more than 90 days ago

Move to `.compass/archive/lessons/` (create dir if needed). Set `status: archived` in the file's frontmatter. Update its catalog row to `status: archived`.

Report every archive for the human's audit.

### 7. Rebuild lessons-catalog.yaml

Generate a fresh catalog from the resulting lesson set:

```yaml
lessons:
  - file: "LESSON-foo.md"
    status: active
    category: process
    area: workflow
    tags: [yaml, frontmatter]
    score: 8
    summary: "YAML values with colons must be quoted"
```

Active lessons first (sorted by score descending, then alpha by filename). Archived lessons after, separated by a `# Archived below` comment.

Remove any catalog rows pointing to files that no longer exist (mark as `# stale entry removed: <file>` in a report-only log).

### 8. Rebuild the Lessons section of index.md

Replace the `## Lessons` section with one line per active lesson, sorted by score descending, then alpha:

```markdown
## Lessons
- [[LESSON-foo]] - YAML values with colons must be quoted (score 8)
- [[LESSON-bar]] - Users need batch export, not single-file (score 6)
```

Do not touch other sections of `index.md`.

### 9. Remove warning markers

Once consolidation completes, strip the WARNING comments from `index.md` and `lessons-catalog.yaml`. The caps may still be exceeded if the active set is genuinely large; if so, the next `index-sync` will re-add the warning, which is the correct signal that consolidation was not enough and a human design decision is needed (raise the cap, or be more aggressive in pruning).

### 10. Final report

```markdown
## Consolidation Report - YYYY-MM-DD

### Escalated lessons (REQUIRES HUMAN REVIEW)
- [[LESSON-foo]] - reason: <escalation_reason> - propose: <action>

### Merged
- [[LESSON-bar]] <- absorbed [[LESSON-baz]] (same rule, different phrasing)

### Rewritten (length)
- [[LESSON-qux]] - 8 lines -> 5 lines

### Archived (baseline + stale)
- [[LESSON-old]] - score 5, no recurrence, last updated 2026-01-15

### Trimmed seen arrays
- 3 lessons trimmed (oldest dates dropped)

### Caps after consolidation
- index.md: <N> lines (cap 200)
- catalog: <N> lines (cap 200)
- lessons/: <N> active files (cap 50)
```

## Failure modes worth naming

- Archiving an escalated lesson. Escalated lessons need human attention, not silent removal.
- Merging across categories. process and domain stay separate; merging blurs the Reinertsen split.
- Rewriting a body to grow past 5 lines while compressing. The cap is the cap.
- Removing the warning without actually reducing the cap. The warning reflects reality; if reality is still over the cap, the warning should re-appear on the next sync.
- Running on a fixed cadence. The contract is the warning. Do not run unprompted.
- Deleting lesson files. Archive moves them to `.compass/archive/lessons/`; consolidation never `rm`s.
