---
name: consolidate
description: The long-horizon consolidation pass, textual and structural in one skill. Runs only when a hard-cap warning is present (proves bloat triggered). Lessons half: merges near-duplicates, rewrites verbose bodies preserving the displaced text in-file, archives stale baseline lessons, rebuilds the catalog. Structure half (consolidation is also taxonomy, SPEC-022): when the weight is non-redundant index lines, proposes domain groupings - similar specs and research folded under folder specs/units, recursively - as a diff the human approves; the root index then says one line per broad area. Never archives escalated lessons; never destroys information.
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

The hot-path marker is the aggregate one: `index.md`, `active.md`, and the lessons catalog together exceed the cap even though each component cap passes. It carries a per-file token breakdown. Read it before starting, because the lessons pass only reaches the catalog and the index's Lessons section. If the breakdown names `active.md` as the dominant contributor, the sweep owns that file; report it. If it names the index and the lines are non-redundant, that is structural weight: run the lessons half for its share, then run the Structure pass below - consolidation is also taxonomy (SPEC-022 D-01), and grouping, never trimming, is the remedy for an index of flat lines.

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

Active lessons only, sorted by score descending, then alpha by filename. An archived lesson has no row: its file in `.compass/archive/lessons/` carries every field the row would copy, the row is derived and regenerable, and the catalog loads on the hot path - dropping the row is tiering, not loss. (The orphaned-row rule below covers only rows whose FILE is missing.)

A catalog row pointing to a file that no longer exists signals corruption (nothing in Compass deletes lesson files); move such rows under a trailing `# Orphaned rows (file missing)` comment block rather than removing them, and name each in the report - the row's summary may be the only surviving trace of the lesson.

### 8. The Lessons section of index.md is a pointer

Lessons are indexed by the catalog, which already loads with the hot path; listing them again in `index.md` puts every summary in the hot path twice. Replace whatever the `## Lessons` section holds with the single pointer:

```markdown
## Lessons

Indexed in [[lessons-catalog|meta/lessons-catalog.yaml]] (loaded with the hot path); files in `lessons/`, archived ones in `archive/lessons/`.
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


## Structure pass (consolidation is also taxonomy)

The lessons half above shrinks textual redundancy. This half shrinks structural weight: a root index listing every artifact flat. The remedy is grouping into domains - "the same way you organize mathematics into subdomains", recursively - so the root index says one line per broad area (ADR-021: children of a folder artifact are not listed at the root; the folder line with its child count is the pointer).

### S1. Inventory

First collect the hints: grep `taxonomy_hint:` across `specs/` and `research/`. Each is a placement judgment recorded at creation by the agent that understood the artifact best, and together they are this pass's work queue. Acting on one clears it - the move happens, or the placement is confirmed fine - and the frontmatter line is removed either way.

Glob every flat root artifact in scope (specs and research first; plans mirror their specs). Read frontmatter (title, area, tags, summary, status) and record outbound wikilinks. `compass graph hubs` and `compass graph impact` give the link structure cheaply.

### S2. Propose domains

Group artifacts that share tags, a title theme, or a dependency neighborhood under a proposed domain: related flat specs fold as children into a folder spec (`compass promote` on the natural parent, or a new parent folder); research docs fold into a folder named for the domain; a domain that is a genuine ongoing workstream is a unit (`compass make-unit`). Subdomains nest inside domains at any depth. Spawn an agent sub-task for the grouping judgment when the corpus is large - it is heuristic work and benefits from a fresh context.

While proposing, also flag tag-vocabulary repairs (synonyms to one canonical form, tags on a single artifact, artifacts with no tags) - the facets are what multi-domain retrieval uses.

### S3. Present the proposal as a diff, and stop

One block per proposed domain: the folder to create, the files that move into it (exact `git mv` paths), the one index line that replaces their N lines, and the rationale. Domains are the human's knowledge's shape - only his approval moves files. Without approval this pass is read-only.

### S4. Apply after approval

Execute with the existing commands - `compass promote --apply`, `compass make-unit --apply`, `git mv` into folder specs - so every shape change lands in the sizing log where those commands write it. Wikilinks keep resolving (bare stems stay unique or become path-qualified per the linking rule); run `compass validate` after each domain and stop on any broken link. Nothing is deleted, ever: grouping moves files.

### S5. Report

Domains created, files moved per domain, index lines before -> after, validate clean.

## Failure modes worth naming

- Archiving an escalated lesson. Escalated lessons need human attention, not silent removal.
- Merging across categories. process and domain stay separate; merging blurs the Reinertsen split.
- Rewriting a body to grow past 5 lines while compressing. The cap is the cap - and the displaced text goes under `## Record (preserved)`, never out of the file.
- Destroying information to fit a cap. Consolidation shrinks the hot representation (summaries, catalog rows, index lines); the data itself always survives in the file or the archive. Too big for its tier means break it up or move it colder, never delete it.
- Removing the warning without actually reducing the cap. The warning reflects reality; if reality is still over the cap, the warning should re-appear on the next sync.
- Running on a fixed cadence. The contract is the warning. Do not run unprompted.
- Moving files in the Structure pass without the human's approval of the proposal. His knowledge, his shape.
- Deleting lesson files. Archive moves them to `.compass/archive/lessons/`; consolidation never `rm`s.
