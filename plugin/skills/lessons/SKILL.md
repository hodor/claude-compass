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

1. Load `.compass/meta/lessons-catalog.yaml`.
2. Skip `status: archived`.
3. Judge relevance from summaries, tags, areas, categories. Use judgment about the intent of the work, not just keyword overlap.
4. Read the full lesson files for the ones you judged relevant (3-5 max).
5. Apply.

For large catalogs (20+ entries), spawn a subagent to filter and return just the relevant filenames - keeps the main context clean.

If the catalog does not exist:

```
Glob: .compass/lessons/*.md
Grep: tags matching current work area
```

This fallback is malformed-vault recovery only. The catalog should always exist.

## Escalated lessons

A lesson with `escalated: <date>` in its frontmatter has recurred 3 times despite being captured. Surface it with extra emphasis in the next session's hot path. The lesson is either worded too vaguely to apply, or the search algorithm is failing to retrieve it before work. Flag for human review.

`/compass:consolidate` does not archive escalated lessons. The human clears the flag after rewording or fixing the retrieval gap.

## Creating lessons

Do NOT write lessons from agent prose. Creation goes through the `lesson-write` skill, called by:

- `extract-lessons` - retrospective capture at phase boundary (auto)
- `/compass:learned` - in-the-moment human capture (manual)

Both paths share dedup, anti-list filtering, atomic 3-file writes, and the 5-line body cap. See `lesson-write/SKILL.md` for the protocol.

## File format

Lessons live in `.compass/lessons/` as markdown files with YAML frontmatter. The body is free-form, hard-capped at 5 lines. See the Lesson template in `obsidian/SKILL.md` for the frontmatter schema.
