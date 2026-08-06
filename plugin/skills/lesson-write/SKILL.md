---
name: lesson-write
description: Write or update a lesson in the .compass/ vault. Loads the catalog as a dedup manifest, applies the anti-list filter, enforces the 5-line body cap, and atomically updates the lesson file plus catalog plus index. Handles recurrence escalation. Called by extract-lessons and /compass:learned. Never call directly from prose.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit]
when_to_use: "Called programmatically by extract-lessons skill or /compass:learned slash command. Not a user-facing skill."
---

# Lesson Write

Single entry point for creating or updating a lesson. Every write goes through this skill so the catalog and index never drift from the filesystem.

## Inputs

The calling skill provides:

- `category` - `process` or `domain`. Required.
- `area` - one of the standard areas (architecture, frontend, backend, testing, devops, infra, docs, workflow, methodology). Required.
- `tags` - list of 1-5 short tags. Required.
- `summary` - one line, <=120 characters. Required.
- `body` - free-form markdown, <=5 lines. Required.
- `source` - string describing what produced this lesson (e.g. `extract-lessons:phase-2`, `/compass:learned`). Required for the audit trail.
- `intent` - `write` (default) or `archive`. An archive request needs only `intent`, `target`, `body`, and `source` - `category`/`area`/`tags`/`summary` are not required, since the target lesson's own frontmatter already carries them.
- `target` - existing lesson filename (e.g. `LESSON-foo.md`) naming the lesson to retire. Required only when `intent: archive`.

If any input is missing or exceeds limits, halt and report. Do not invent values.

## Anti-list

Before any write, check whether the lesson falls into any of these buckets. If yes, do not write. Return `rejected: <bucket>` to the caller.

- Code patterns, conventions, architecture, file paths, or project structure - readable from the codebase.
- Git history, recent changes, or who-changed-what - `git log` and `git blame` are authoritative.
- Debugging recipes whose fix is in the code - the commit message is the right home.
- Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md.
- Standard patterns from framework or library official docs.
- Personal style preferences.
- Things obvious once you know the technology.
- Ephemeral session state - handoffs are the right home.
- Environment-dependent failures - specific to one machine, install, or transient environment state; it does not generalize.
- Negative tool claims - "tool X cannot do Y" from a single failed attempt; these harden into standing refusals that outlive the actual limitation.
- Unresolved or untested approaches - a "recommended approach" never validated in this session; recording it as proven turns a guess into standing guidance.

**These exclusions apply even when the user explicitly says to save.**

## Protocol

### 1. Load the catalog

Read `.compass/meta/lessons-catalog.yaml`. If it does not exist, halt and report - the vault is malformed.

Build the dedup manifest as a list, one line per active lesson:

```
- LESSON-foo.md (process / workflow, score 8): YAML values with colons must be quoted
- LESSON-bar.md (domain / backend, score 5): Users need batch export not single-file
```

Skip lessons with `status: archived`.

If `intent: archive`, skip steps 2 and 3 and go straight to step 4d. An archive request retires a specific lesson the caller has already named; it is not new content to filter or dedup-judge.

### 2. Apply the anti-list

Compare the input against every bucket above. If any matches, return `rejected` with the bucket name. Stop here.

### 3. Judge dedup

Read the manifest. Pick one of three branches based on overlap with existing lessons:

(A fourth branch, archive, exists at step 4d - it is reached directly from step 1 for an `intent: archive` payload, never from this judgment.)

**Recurrence** - same rule, new instance. Indicators: tags overlap >=2, summary semantically equivalent, body would say the same thing. Action: go to step 4a.

**Refinement** - rule generalizes or adds nuance to an existing lesson. Indicators: same area + tags, but the new context shows the rule applies more broadly or has a subtler condition. Action: go to step 4b.

**Genuinely new rule** - distinct from every existing lesson. Action: go to step 4c.

If unsure between recurrence and refinement, pick refinement. If unsure between refinement and new, pick new. Bias toward keeping signal.

### 4a. Write recurrence

Read the matched lesson file's frontmatter.

If `seen` array has fewer than 3 entries: append today's date (YYYY-MM-DD) to `seen`, increment `score` by 1 (cap at 10), update `updated`. Body unchanged. Return `recurrence: <existing-filename>`.

If `seen` already has 3 entries: do NOT add a 4th date. Instead set `escalated: <today>` and `escalation_reason: "recurred 3 times despite being captured - lesson worded too vaguely OR search retrieval failing"`. Increment `score` by 1. Return `escalated: <existing-filename>`.

Do not touch the catalog or index for recurrences - they already point at the same file.

### 4b. Write refinement

Edit the matched lesson file's body in place. The new body must still fit within 5 lines. If the refinement would push past 5 lines, compress: keep the most general statement of the rule and drop the most specific instance. Update `updated` in frontmatter.

If the refinement changes the summary, also update the matching catalog row.

Return `refined: <existing-filename>`.

### 4c. Write new lesson

ONE write: the lesson file. The catalog row and index entry are added automatically by the PostToolUse hook running `index-sync` after this write completes. Do NOT write them yourself - that would duplicate the hook's work.

**Write: the lesson file.**

Filename: `LESSON-<descriptive-kebab-slug>.md` derived from the summary. Path: `.compass/lessons/`.

Frontmatter:

```yaml
---
title: <human-readable title from summary>
type: lesson
status: active
category: <process|domain>
area: <area>
tags: [<tag1>, <tag2>, ...]
created: <today YYYY-MM-DD>
updated: <today YYYY-MM-DD>
score: 5
summary: <one-line summary>
seen: []
---
```

Body: the input body verbatim, written immediately after the closing `---` of frontmatter (preceded by exactly one blank line). No `# Title` H1 - the frontmatter `title` field is canonical. No template sections. **Hard cap: 5 physical lines, blank lines included.**

After the Write completes, the PostToolUse hook fires `index-sync`. That hook reads the lesson's frontmatter, appends a row to `.compass/meta/lessons-catalog.yaml`, and appends a line to the `## Lessons` section of `.compass/index.md`. You do NOT do those writes here - they are automated. See [[LESSON-no-agent-bookkeeping]] for the principle.

Return `created: <new-filename>`.

### 4d. Write archive

Reached only from an `intent: archive` payload naming a `target` lesson (a contradiction-archive call from `extract-lessons`, or an explicit human instruction). Never reached through the step 3 dedup judgment.

Never archives an escalated lesson - a lesson carrying `escalated:` in its frontmatter carries human weight; flag it for human review instead of retiring it autonomously (the same rule `consolidate` applies). Return `error: cannot autonomously archive an escalated lesson`.

Otherwise:

- Read the `target` lesson file's frontmatter. Set `status: archived`, update `updated` to today. Do not move or delete the file.
- Append the input `body` (the superseding reason) to the lesson body on a new line, prefixed `Superseded:`. This edit is exempt from the 5-line body cap - an archived lesson is retired reference material, not active guidance competing for read budget.
- Update the matching row in `.compass/meta/lessons-catalog.yaml` to `status: archived`.

Return `archived: <target-filename>`.

## Body cap enforcement

Body = everything after the closing `---` of frontmatter (and after the one mandatory blank line that separates frontmatter from body). It does NOT include any H1 header (lessons must not have one - the frontmatter `title` is canonical).

Count physical text lines. Blank lines count. Wrapped soft-wrap lines count as one. If body exceeds 5 lines, halt and report `body_too_long: <line-count>`. The caller must compress and retry.

## Return value

Always return one of these strings to the caller:

- `created: <filename>` - new file, catalog row, index entry written
- `recurrence: <filename>` - existing lesson bumped, seen appended
- `escalated: <filename>` - existing lesson hit the 3-date cap, escalation flag set
- `refined: <filename>` - existing lesson body edited
- `archived: <filename>` - existing lesson retired, status set in file and catalog
- `rejected: <bucket>` - anti-list matched, no write
- `body_too_long: <N>` - body exceeds 5 lines, no write
- `error: <description>` - any other failure mode (caller halts)

## Failure modes worth naming

- Writing without consulting the manifest. Always load and judge first.
- Skipping the anti-list because the input "obviously is a lesson." The anti-list is the filter that does the real work.
- Writing the lesson file but skipping the catalog or index update. All three or none.
- Treating the 5-line cap as a guideline. Reject and ask the caller to compress.
- Adding a 4th seen date. Escalate instead.
- Editing a body to grow past 5 lines during a refinement. Compress.
- Archiving an escalated lesson autonomously. Flag it for human review instead.
- Deleting a lesson file on archive. Set `status: archived` and leave the file in place.
