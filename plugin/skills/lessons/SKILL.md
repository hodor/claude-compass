---
name: lessons
description: How to search, apply, and create lessons in the .compass/ vault — catalog structure, search algorithm, creation criteria, and catalog update protocol
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
---

# Lessons — Search, Apply & Create

Lessons capture hard-won knowledge that prevents the same mistake from being made twice.

Per Reinertsen (*The Principles of Product Development Flow*), product development generates two distinct types of knowledge:

- **Process lessons** (`category: process`): Knowledge about *how* to build — methods, tools, techniques, workflow. Example: "Mocking the DB in integration tests hides migration bugs."
- **Domain lessons** (`category: domain`): Knowledge about *what* to build — the product, users, requirements, the problem space. Example: "Users need batch export, not single-file export."

Both types are equally valuable but serve different purposes. Process lessons improve how agents work. Domain lessons improve what agents build.

## Catalog Structure

The lessons catalog lives at `.compass/meta/lessons-catalog.yaml`. It provides O(1) tag lookup instead of O(n) grep across all lesson files.

```yaml
# meta/lessons-catalog.yaml
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
- `file`: Filename of the lesson in `.compass/lessons/` — named as `LESSON-<descriptive-slug>.md`
- `status`: `active` or `archived`
- `category`: `process` (how to build) or `domain` (what to build)
- `area`: Matches the frontmatter `area` field
- `tags`: List of tags for matching
- `score`: 1-10, higher = more broadly applicable. Starts at 5, adjusted over time.
- `summary`: One-line description for quick scanning

## When to Search for Lessons

Search for relevant lessons before **making plans**, **implementing plans**, or **starting any task that changes code or vault structure**. The catalog is cheap to read — when in doubt, check it.

## Search Algorithm

When looking for relevant lessons:

1. **Read catalog**: Load `.compass/meta/lessons-catalog.yaml`
2. **Filter out archived**: Skip entries with `status: archived`
3. **Judge relevance**: Read the summaries, tags, areas, and categories. Use your judgment to decide which lessons are relevant to the current task — don't rely on mechanical tag matching. Consider the intent of the work, not just keyword overlap.
4. **Load relevant lessons**: Read the full lesson files for the ones you judged relevant (typically 3-5 max)
5. **Apply**: Incorporate relevant lessons into your approach

For large catalogs (20+ entries), spawn a subagent to review the catalog and return the relevant filenames — this keeps the main context clean.

If the catalog doesn't exist or is empty, fall back to:
```
Glob: .compass/lessons/*.md
Grep: tags matching current work area/tags
```

## When to Create Lessons

### Process lessons (how to build)

Create when you encounter:

- **Surprising bugs**: Something that behaved differently than expected, especially if the fix was non-obvious
- **Counter-intuitive patterns**: The correct approach was the opposite of what seemed natural
- **Misleading documentation**: Official docs were wrong, incomplete, or led you astray
- **Environment-specific gotchas**: Something that works on one platform but not another
- **Tool quirks**: Unexpected behavior in tools, libraries, or frameworks
- **Performance traps**: Code that looked fine but caused performance issues

### Domain lessons (what to build)

Create when you discover:

- **Requirement corrections**: What users actually need vs. what was assumed
- **Domain model insights**: A concept was misunderstood or modeled incorrectly
- **User behavior surprises**: Users interact with the system differently than expected
- **Constraint discoveries**: A business rule, regulation, or technical constraint that wasn't known at design time
- **Integration realities**: An external system or API behaves differently than its docs suggest

### Do NOT create lessons for

- Standard patterns documented in official docs
- Personal preferences or style choices
- Things that are obvious once you know the technology
- Ephemeral information (use handoffs for session context)

## Lesson File Format

Lessons live in `.compass/lessons/` and follow the Lesson template defined in the **obsidian** skill (`plugin/skills/obsidian/SKILL.md` → Templates → Lesson).

## Catalog Update Protocol

The catalog is **append-only** (entries are never deleted, only marked as archived):

1. Create the lesson file in `.compass/lessons/`
2. Append an entry to `meta/lessons-catalog.yaml` with:
   - `file`: the lesson filename (`LESSON-<descriptive-slug>.md`)
   - `status`: `active`
   - `category`: `process` or `domain` from the lesson frontmatter
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
