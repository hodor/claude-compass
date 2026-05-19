---
name: lessons
description: How to search, apply, and create lessons in the .compass/ vault - catalog structure, search algorithm, creation criteria, and catalog update protocol
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
---

# Lessons - Search, Apply & Create

Lessons capture hard-won knowledge that prevents the same mistake twice. Per Reinertsen (*Principles of Product Development Flow*), two types:

- **Process** (`category: process`) - how to build. "Mocking the DB in integration tests hides migration bugs."
- **Domain** (`category: domain`) - what to build. "Users need batch export, not single-file."

Process lessons improve how agents work. Domain lessons improve what agents build.

## Catalog

`.compass/meta/lessons-catalog.yaml` provides O(1) tag lookup instead of grepping every lesson file.

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
- `file` - lesson filename in `.compass/lessons/`.
- `status` - `active` or `archived`.
- `category` - `process` or `domain`.
- `area` - from frontmatter.
- `tags` - for matching.
- `score` - 1-10, higher = more broadly applicable. Starts at 5.
- `summary` - one-line description.

## When to search

Before making plans, implementing plans, or starting any task that changes code or vault structure. The catalog is cheap to read - when in doubt, check it.

## Search algorithm

1. Load `.compass/meta/lessons-catalog.yaml`.
2. Skip `status: archived`.
3. Judge relevance from summaries, tags, areas, categories. Use judgment about the intent of the work, not just keyword overlap.
4. Read the full lesson files for the ones you judged relevant (3-5 max).
5. Apply.

For large catalogs (20+ entries), spawn a subagent to filter and return just the relevant filenames - keeps the main context clean.

If the catalog doesn't exist:
```
Glob: .compass/lessons/*.md
Grep: tags matching current work area/tags
```

## When to create

### Process lessons (how to build)

- Surprising bugs where the fix was non-obvious.
- Counter-intuitive patterns - the right approach was the opposite of natural.
- Misleading documentation.
- Environment-specific gotchas.
- Tool quirks.
- Performance traps.

### Domain lessons (what to build)

- Requirement corrections - what users actually need vs. what was assumed.
- Domain model insights - a concept was misunderstood.
- User behavior surprises.
- Constraint discoveries - a business rule, regulation, or technical constraint not known at design time.
- Integration realities - an external system behaves differently than its docs suggest.

### Don't create lessons for

- Standard patterns in official docs.
- Personal preferences or style.
- Things obvious once you know the technology.
- Ephemeral session context (use handoffs).

## File format

Lessons live in `.compass/lessons/`. Use the Lesson template from the obsidian skill.

## Catalog update protocol

Append-only - entries are never deleted, only archived.

1. Create the lesson file in `.compass/lessons/`.
2. Append an entry to `meta/lessons-catalog.yaml` with: `file`, `status: active`, `category`, `area`, `tags`, `score: 5`, `summary`.
3. Never reorder existing entries.
4. To retire, set `status: archived` in both the file and the catalog. Don't delete.

## Score adjustment

- Increase (+1 to +3) when a lesson prevents a repeated mistake or applies broadly.
- Decrease (-1 to -3) when a lesson turns out to be environment-specific or no longer relevant.
- Range: 1-10.
