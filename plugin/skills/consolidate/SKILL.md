---
name: consolidate
description: Long-horizon merge, prune, and demote pass over the lessons set. Runs only when a hard-cap warning is present (proves bloat triggered). Merges near-duplicates the per-phase dedup missed, rewrites verbose bodies preserving the displaced text in-file, archives stale baseline-score lessons, rebuilds the catalog and the index Lessons section. Never archives escalated lessons; flags them for human review.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit]
argument-hint: "(no arguments; uses warning state)"
when_to_use: "Run /compass:consolidate when the next session's hot path surfaces a cap-exceeded warning. Do not run on a fixed cadence - the bloat trigger is the contract."
---

# /compass:consolidate - Lessons Consolidation

Long-horizon cleanup. Runs only when needed. Never archives lessons silently.

## Pre-check

Read `.compass/index.md` and `.compass/meta/lessons-catalog.yaml`. Look for any of these warning markers:

- `<!-- WARNING: index.md exceeded hot-path cap.`
- `<!-- WARNING: hot path `
- `# WARNING: catalog exceeded cap.`

If none present, exit: `no consolidation needed (no cap warning)`. The bloat trigger is the contract; do not run unprompted.

The hot-path marker is the aggregate one: `index.md`, `active.md`, and the lessons catalog together exceed the cap even though each component cap passes. It carries a per-file token breakdown. Read it before starting, because the lessons pass only reaches the catalog and the index's Lessons section. If the breakdown names `active.md` or a non-Lessons index section as the dominant contributor, consolidation alone cannot clear the marker: run it for the lessons share, then report the breakdown and say plainly which file is carrying the weight and what would have to be cut. That is a human decision, not a silent trim.

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
- Union the `seen` arrays, keeping every date (step 5)
- The losing lesson becomes `status: archived`, its filename is added to the kept lesson's frontmatter as `merged_from: ["LESSON-loser.md"]`
- The body of the kept lesson is preserved unchanged unless the loser had nuance worth absorbing; if so, compress and fit under the 5-line cap

Report every merge for the human's audit.

### 4. Rewrite verbose bodies - never destroying the original

For each lesson body longer than 5 lines: distill the rule + reason into <=5 lines, and move the displaced text - the specific instances, the longer wording - into the same file under a `## Record (preserved)` heading below the body. That section is exempt from the 5-line cap, exactly as an archived lesson's `Superseded:` line is: the cap governs the active guidance competing for read budget, and the record below it is cold detail fetched only when someone opens the file. Nothing is dropped; the hot representation shrinks, the data stays.

Report every rewrite with before/after for the human's audit.

### 5. Seen arrays are never trimmed

`seen:` is the recurrence evidence - the dates a lesson proved itself again. It lives only in the lesson file's frontmatter, which no hot-path surface loads, so trimming saves nothing that matters and destroys history that does. Leave every date in place.

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

A catalog row pointing to a file that no longer exists signals corruption (nothing in Compass deletes lesson files); move such rows under a trailing `# Orphaned rows (file missing)` comment block rather than removing them, and name each in the report - the row's summary may be the only surviving trace of the lesson.

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

### Records preserved
- [[LESSON-qux]] - displaced body text moved under `## Record (preserved)`

### Caps after consolidation
- index.md: <N> lines (cap 200)
- catalog: <N> lines (cap 200)
- lessons/: <N> active files (cap 50)
```

## Failure modes worth naming

- Archiving an escalated lesson. Escalated lessons need human attention, not silent removal.
- Merging across categories. process and domain stay separate; merging blurs the Reinertsen split.
- Rewriting a body to grow past 5 lines while compressing. The cap is the cap - and the displaced text goes under `## Record (preserved)`, never out of the file.
- Destroying information to fit a cap. Consolidation shrinks the hot representation (summaries, catalog rows, index lines); the data itself always survives in the file or the archive. Too big for its tier means break it up or move it colder, never delete it.
- Removing the warning without actually reducing the cap. The warning reflects reality; if reality is still over the cap, the warning should re-appear on the next sync.
- Running on a fixed cadence. The contract is the warning. Do not run unprompted.
- Deleting lesson files. Archive moves them to `.compass/archive/lessons/`; consolidation never `rm`s.
