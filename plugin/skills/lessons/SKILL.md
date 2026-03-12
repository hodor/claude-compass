---
name: lessons
description: How to search, apply, and create lessons in the .compass/ vault — catalog structure, search algorithm, creation criteria, and catalog update protocol
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
---

# Lessons — Search, Apply & Create

Lessons capture hard-won knowledge: surprising bugs, counter-intuitive patterns, misleading docs. They prevent the same mistake from being made twice.

## Catalog Structure

The lessons catalog lives at `.compass/meta/lessons-catalog.yaml`. It provides O(1) tag lookup instead of O(n) grep across all lesson files.

```yaml
# meta/lessons-catalog.yaml
lessons:
  - file: "LESSON-yaml-frontmatter-quoting.md"
    area: workflow
    tags: [yaml, frontmatter, quoting]
    score: 8
    summary: "YAML frontmatter values with colons must be quoted"
  - file: "LESSON-glob-pattern-escaping.md"
    area: tooling
    tags: [glob, patterns, escaping]
    score: 5
    summary: "Glob patterns with braces need escaping on Windows"
```

Fields:
- `file`: Filename of the lesson in `.compass/lessons/`
- `area`: Matches the frontmatter `area` field
- `tags`: List of tags for matching
- `score`: 1-10, higher = more broadly applicable. Starts at 5, adjusted over time.
- `summary`: One-line description for quick scanning

## Search Algorithm

When looking for relevant lessons:

1. **Read catalog**: Load `.compass/meta/lessons-catalog.yaml`
2. **Filter by area**: Keep lessons matching the current work area
3. **Filter by tags**: Keep lessons with at least one overlapping tag with the current task
4. **Sort by score**: Highest score first
5. **Load top 3-5**: Read the full lesson files for the top matches
6. **Apply**: Incorporate relevant lessons into your approach

If the catalog doesn't exist or is empty, fall back to:
```
Glob: .compass/lessons/*.md
Grep: tags matching current work area/tags
```

## When to Create Lessons

Create a lesson when you encounter:

- **Surprising bugs**: Something that behaved differently than expected, especially if the fix was non-obvious
- **Counter-intuitive patterns**: The correct approach was the opposite of what seemed natural
- **Misleading documentation**: Official docs were wrong, incomplete, or led you astray
- **Environment-specific gotchas**: Something that works on one platform but not another
- **Tool quirks**: Unexpected behavior in tools, libraries, or frameworks
- **Performance traps**: Code that looked fine but caused performance issues

Do NOT create lessons for:
- Standard patterns documented in official docs
- Personal preferences or style choices
- Things that are obvious once you know the technology

## Lesson File Format

Lessons live in `.compass/lessons/` and follow the template from the obsidian skill:

```markdown
---
title: "Descriptive title of the lesson"
type: lesson
status: active
area: <area>
tags: [specific, relevant, tags]
created: YYYY-MM-DD
updated: YYYY-MM-DD
score: 5
---

# Descriptive Title

## Context

When does this apply? What were you doing when you hit this?

## Problem

What went wrong? What was surprising? Be specific — include error messages, unexpected behavior, etc.

## Solution

What is the correct approach? Include code examples if applicable.

## Tags

`tag1`, `tag2`, `tag3`
```

## Catalog Update Protocol

The catalog is **append-only** (entries are never deleted, only marked as archived):

1. Create the lesson file in `.compass/lessons/`
2. Append an entry to `meta/lessons-catalog.yaml` with:
   - `file`: the lesson filename
   - `area`: from the lesson frontmatter
   - `tags`: from the lesson frontmatter
   - `score`: start at 5 (default)
   - `summary`: one-line description
3. Never reorder existing entries
4. To retire a lesson, set its status to `archived` in both the file and catalog — do not delete

## Score Adjustment

Scores can be adjusted over time:
- **Increase** (+1 to +3) when a lesson prevents a repeated mistake or applies broadly
- **Decrease** (-1 to -3) when a lesson turns out to be environment-specific or no longer relevant
- Range: 1-10, never go below 1 or above 10
