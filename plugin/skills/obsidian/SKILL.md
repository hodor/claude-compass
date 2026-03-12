---
name: obsidian
description: Obsidian-compatible formatting conventions — YAML frontmatter schema, wikilinks, file naming, vault search patterns, and document templates for the .compass/ vault
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
---

# Obsidian — Vault Formatting & Conventions

Reference for reading and writing `.compass/` vault documents. All vault files are Obsidian-compatible markdown with YAML frontmatter and wikilinks.

## YAML Frontmatter Schema

Every `.compass/` document MUST have frontmatter. Fields by applicability:

```yaml
---
title: "Human-readable title"                    # REQUIRED — all documents
type: spec | research | plan | task | lesson | decision  # REQUIRED — all documents
status: draft | review | approved | active | done | archived  # REQUIRED — all documents
confidence: low | medium | high                  # REQUIRED for spec, research, decision
area: architecture | frontend | backend | testing | devops | infra | docs | workflow  # REQUIRED — all documents
tags: [tag1, tag2]                               # REQUIRED — all documents (used for lesson matching)
created: YYYY-MM-DD                              # REQUIRED — all documents
updated: YYYY-MM-DD                              # REQUIRED — all documents (update on every edit)
blocked_by: "description or [[link]]"            # OPTIONAL — tasks only
depends_on: ["[[link1]]", "[[link2]]"]           # OPTIONAL — any document
supersedes: "[[link]]"                           # OPTIONAL — when replacing an older document
---
```

### Status Transitions

```
draft → review → approved → active → done → archived
```

- `draft`: Work in progress, not ready for review
- `review`: Ready for human review
- `approved`: Human has approved, not yet started
- `active`: Currently being worked on
- `done`: Completed
- `archived`: No longer relevant, kept for history

## Wikilink Conventions

| Syntax | Use |
|--------|-----|
| `[[filename]]` | Link to another vault document (omit `.md` extension) |
| `[[filename#Section]]` | Link to a specific section within a document |
| `[[filename\|Display Text]]` | Link with custom display text |

Always use wikilinks for cross-references within the vault. Never use relative markdown links.

## File Naming

All vault documents follow this pattern: `TYPE-NNN-descriptive-name.md`

| Type | Pattern | Example |
|------|---------|---------|
| Spec | `SPEC-NNN-descriptive-name.md` | `SPEC-001-compass-vision-and-architecture.md` |
| ADR / Decision | `ADR-NNN-descriptive-name.md` | `ADR-001-obsidian-over-structured-db.md` |
| Research | `RESEARCH-descriptive-name.md` | `RESEARCH-plugin-system-capabilities.md` |
| Plan | `PLAN-NNN-descriptive-name.md` | `PLAN-001-mvp-implementation.md` |
| Lesson | `LESSON-descriptive-name.md` | `LESSON-yaml-frontmatter-quoting.md` |

Rules:
- Numbers (`NNN`) provide ordering and are managed by `meta/config.yaml` counters
- Names MUST be self-descriptive — `SPEC-001.md` is NEVER acceptable
- Use lowercase kebab-case for the descriptive part
- Research files omit the number (no ordering needed)

## Vault Search Patterns

### Find documents by tag

```
Grep pattern: "tags:.*\\btarget-tag\\b" in .compass/ glob: "*.md"
```

### Find documents by area

```
Grep pattern: "area: target-area" in .compass/ glob: "*.md"
```

### Find documents by status

```
Grep pattern: "status: active" in .compass/ glob: "*.md"
```

### Find backlinks to a document

```
Grep pattern: "\\[\\[SPEC-001" in .compass/ glob: "*.md"
```

### Find documents by type

```
Grep pattern: "type: spec" in .compass/ glob: "*.md"
```

## Document Templates

### Spec

```markdown
---
title: "Title"
type: spec
status: draft
confidence: low
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Title

## Problem

What problem does this solve? Why does it matter?

## Context

What existing context is relevant? What has been tried before?

## Decision Drivers

- Driver 1
- Driver 2

## Desired Outcome

What does success look like?

## Constraints

- Constraint 1
- Constraint 2

## Non-Goals

- Explicitly out of scope item 1

## Considered Options

### Option A: ...
- Pro: ...
- Con: ...

### Option B: ...
- Pro: ...
- Con: ...

## Consequences

What follows from the decisions made here?

## Open Questions

- [ ] Question 1
- [ ] Question 2
```

### Research

```markdown
---
title: "Title"
type: research
status: draft
confidence: low
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Title

## Question

What are we investigating?

## Methodology

How was this research conducted?

## Findings

1. **Finding** (confidence: high/medium/low) — Description

## Evidence

- `file:line` — what it shows
- URL — what it shows

## Contradictions

Any conflicting evidence found.

## Gaps

What we still don't know.
```

### Plan

```markdown
---
title: "Title"
type: plan
status: draft
confidence: medium
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
depends_on: ["[[SPEC-NNN-name]]"]
---

# Title

## Goal

What this plan achieves.

## Prerequisites

What must be true before starting.

## Phases

### Phase 1: ...

- [ ] TASK-NNN: Description — complexity: S/M/L, depends_on: none
  - Acceptance criteria: ...
- [ ] TASK-NNN: Description — complexity: S/M/L, depends_on: TASK-NNN
  - Acceptance criteria: ...

### Phase 2: ...

...
```

### Lesson

```markdown
---
title: "Title"
type: lesson
status: active
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
score: 5
---

# Title

## Context

When does this apply? What were you doing?

## Problem

What went wrong or was surprising?

## Solution

What is the correct approach?

## Tags

Redundant with frontmatter, but useful for human scanning: `tag1`, `tag2`
```

### Decision (ADR)

```markdown
---
title: "Title"
type: decision
status: approved
confidence: high
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
supersedes: "[[ADR-NNN-name]]"
---

# Title

## Status

Approved / Superseded by [[ADR-NNN-name]]

## Context

What is the issue that we're seeing that is motivating this decision?

## Decision

What is the change that we're proposing and/or doing?

## Consequences

What becomes easier or more difficult to do because of this change?
```
