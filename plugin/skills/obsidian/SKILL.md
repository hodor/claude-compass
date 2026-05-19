---
name: obsidian
description: Obsidian-compatible formatting conventions - YAML frontmatter schema, wikilinks, file naming, vault search patterns, and document templates for the .compass/ vault
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
---

# Obsidian - Vault Formatting & Conventions

Reference for reading and writing `.compass/` documents. Obsidian-compatible markdown with YAML frontmatter and wikilinks.

## The one linking rule

When you mention a vault document in prose, use `[[wikilinks]]`. Every time. No exceptions.

- Write: "This plan implements [[SPEC-001-project-setup]]"
- Not: "This plan implements the project setup spec"
- Not: "This plan implements `.compass/specs/SPEC-001-project-setup.md`"

Wikilinks are how documents connect - for agents (grep finds them) and for humans (Obsidian renders the graph). Frontmatter `depends_on` is for structured queries. Inline wikilinks are for navigation.

## YAML frontmatter

Every vault document needs frontmatter:

```yaml
---
title: "Human-readable title"                    # REQUIRED - all
type: spec | research | plan | task | lesson | decision | handoff  # REQUIRED - all
status: draft | review | approved | active | done | archived  # REQUIRED - all
confidence: low | medium | high                  # REQUIRED for spec, research, decision
category: process | domain                       # REQUIRED for lesson
area: architecture | frontend | backend | testing | devops | infra | docs | workflow  # REQUIRED - all
tags: [tag1, tag2]                               # REQUIRED - all
created: YYYY-MM-DD                              # REQUIRED - all
updated: YYYY-MM-DD                              # REQUIRED - update on every edit
git_branch: "branch-name"                        # REQUIRED for research, handoff, plan
git_commit: "abc1234"                            # REQUIRED for research, handoff, plan
author: "human or agent name"                    # REQUIRED for research, handoff, plan, decision
blocked_by: "description or [[link]]"            # OPTIONAL - tasks only
depends_on: ["[[link1]]", "[[link2]]"]           # OPTIONAL - any document
supersedes: "[[link]]"                           # OPTIONAL - replacing an older document
---
```

### Status lifecycle

```
draft → review → approved → active → done → archived
```

- `draft` - work in progress, not for review.
- `review` - ready for human review.
- `approved` - human approved, not yet started.
- `active` - currently being worked on.
- `done` - completed.
- `archived` - no longer relevant, kept for history.

## Wikilinks

| Syntax | Use |
|--------|-----|
| `[[filename]]` | Link to another vault document (omit `.md`) |
| `[[filename#Section]]` | Link to a section within a document |
| `[[filename\|Display Text]]` | Link with custom display text |

Always wikilinks for cross-references. Never relative markdown links.

## File naming

Pattern: `TYPE-NNN-descriptive-name.md`

| Type | Pattern | Example |
|------|---------|---------|
| Spec | `SPEC-NNN-descriptive-name.md` | `SPEC-001-compass-vision-and-architecture.md` |
| ADR | `ADR-NNN-descriptive-name.md` | `ADR-001-obsidian-over-structured-db.md` |
| Research | `RESEARCH-descriptive-name.md` | `RESEARCH-plugin-system-capabilities.md` |
| Plan | `PLAN-NNN-descriptive-name.md` | `PLAN-001-mvp-implementation.md` |
| Lesson | `LESSON-descriptive-name.md` | `LESSON-yaml-frontmatter-quoting.md` |
| Handoff | `YYYY-MM-DD_HH-MM-SS_descriptive-name.md` | `2026-03-12_14-30-00_implement-auth-flow.md` |

`NNN` numbers come from `meta/config.yaml` counters. Names must be self-descriptive - `SPEC-001.md` is never acceptable. Lowercase kebab-case for the descriptive part. Research files omit the number.

## Vault search patterns

```
# by tag
Grep pattern: "tags:.*\\btarget-tag\\b" in .compass/ glob: "*.md"

# by area
Grep pattern: "area: target-area" in .compass/ glob: "*.md"

# by status
Grep pattern: "status: active" in .compass/ glob: "*.md"

# backlinks
Grep pattern: "\\[\\[SPEC-001" in .compass/ glob: "*.md"

# by type
Grep pattern: "type: spec" in .compass/ glob: "*.md"
```

## Document templates

Writing rule for all templates: short, sweet, long only when needed, never verbose. Omit empty optional sections - don't stub them. Research is the exception (captures evidence).

### Spec

Compass spec template is the default, but use an alternative format (Rust RFC, Python PEP, Go Proposal) when it fits the domain better. The alternative must still include the YAML frontmatter and at minimum **Problem** and **Desired Outcome**.

In the Compass template, only **Problem** and **Desired Outcome** are required. Omit others freely.

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
What exists today that's relevant? What has been tried?

## User Scenarios
- As a [role], I want [goal], so that [benefit]

## Desired Outcome
What does success look like when this is done?

## Success Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Constraints
Hard limits - technical, legal, organizational, time.

## Assumptions & Dependencies
What are we betting on? What must be true for this to work?

## Non-Goals
Explicitly out of scope.

## Risks
- Risk 1: [mitigation]

## Open Questions
- [ ] Question 1
```

### Research

Compass research is a survey of what already exists - not original research. Pick the approach that fits the question:

| Approach | When to use | Primary output |
|----------|------------|----------------|
| **Scoping Review** (Arksey & O'Malley) | Broad, exploratory - "What is the extent and nature of X?" | Narrative synthesis with gap analysis |
| **Systematic Literature Review** (Kitchenham) | Focused, evidence-based - "What is the evidence for/against X?" | Synthesized evidence with quality ratings |
| **Systematic Mapping Study** (Petersen et al.) | Structuring a known field - "What approaches exist and how do they relate?" | Classification scheme + visual map |
| **Technology Landscape** (Gartner/ThoughtWorks) | Evaluating options - "What tools exist and how do they compare?" | Per-item profiles + comparison matrix |

State the chosen approach in Methodology. Only **Question** and **Findings** are required.

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
git_branch: "branch-name"
git_commit: "abc1234"
author: "name"
---

# Title

## Question
What are we investigating? What would constitute a complete answer?

## Scope
What is included and excluded.

## Methodology
How the survey was conducted - search terms, sources, tools, inclusion/exclusion criteria. State the chosen approach (scoping review, systematic mapping, technology landscape) and why.

## Findings
1. **Finding title** (confidence: high/medium/low)
   Description with specifics.
   - Evidence: `file:line` - what it shows
   - Evidence: [URL] - what it shows
   - Caveat: [why confidence is not higher, if applicable]

Confidence:
- **High** - multiple independent sources agree, directly verified.
- **Medium** - single reliable source, or minor inconsistencies, not directly tested.
- **Low** - inferred from indirect evidence, conflicting information.

## Taxonomy
Classification scheme - categories, subcategories, relationships. Core deliverable of a mapping study. Scoping reviews use thematic groupings; landscapes use comparison dimensions.

## Prior Art
How others have solved this. Per-entity narratives with lessons.

## Contradictions
Conflicting evidence surfaced, not hidden.

## Gaps
What is missing. What additional investigation would help.

## Raw Evidence
<details>
<summary>Full evidence log</summary>

All file:line references, URLs, command outputs, search queries, and inclusion/exclusion decisions.

</details>
```

### Plan

A plan's `status` may not move to `approved` while open questions remain.

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
git_branch: "branch-name"
git_commit: "abc1234"
author: "name"
depends_on: ["[[SPEC-NNN-name]]"]
---

# Title

## Goal
What this plan achieves.

## Current State
What exists today. Reference specific files and lines.
- `path/to/file:line` - what it does / what's missing

## Desired End State
Concrete, verifiable. Not aspirational - testable.

## Not Doing
Explicitly out of scope.

## Prerequisites
What must be true before starting.

## Phases

### Phase 1: ...
- [ ] TASK-NNN: Description - files: [path/to/file], complexity: S/M/L, depends_on: none
  - Automated verification: [commands/tests]
  - Manual verification: [human checks]
- [ ] TASK-NNN: Description - files: [path/to/file], complexity: S/M/L, depends_on: TASK-NNN
  - Automated verification: [commands/tests]
  - Manual verification: [human checks]

> **Pause here for human confirmation before proceeding to next phase.**

### Phase 2: ...

## Testing Strategy
Overall testing approach - new fixtures, integration test needs, performance benchmarks. Per-task verification covers details.

## Open Questions
- [ ] Question 1

> **All open questions must be resolved before `approved` status.**
```

### Lesson

Two types (per Reinertsen's *Principles of Product Development Flow*):

- **Process** (`category: process`) - how to build. "Mocking the DB in tests hides migration bugs."
- **Domain** (`category: domain`) - what to build. "Users need batch export, not single-file."

```markdown
---
title: "Title"
type: lesson
status: active
category: process | domain
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
score: 5
---

# Title

## Context
What were you doing? What was the goal or expected behavior?

## What Happened
What actually happened? What was surprising?

## Why
Root cause or contributing factors.

## Lesson
What is the correct approach or understanding?

## Applicability
When should this be recalled? What signals make it relevant?
```

### Handoff

```markdown
---
title: "Handoff: Brief description"
type: handoff
status: active
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
git_branch: "branch-name"
git_commit: "abc1234"
author: "name"
---

# Handoff: Brief Description

## Session Summary
What was the goal and how far did we get?

## Tasks
| Task | Status | Notes |
|------|--------|-------|
| Task description | done / in-progress / blocked | notes |

## Current Phase
[If working from a plan: "Phase X of Y in [[PLAN-NNN-name]]"]

## Artifacts
Documents produced or updated this session:
- `[[SPEC-NNN-name]]` - what's relevant
- `[[RESEARCH-name]]` - what's relevant

## Code Changes
- `path/to/file` - what was changed and why

## Decisions Made
- Decision: reasoning

## Learnings
- What was surprising

## Blockers
- What stopped or slowed progress

## Action Items (Next Session)
1. [ ] First thing to do when resuming

## Uncommitted Changes
[`git status --short` + `git diff --stat`, or "None"]

## Context for Resuming
[Nuance lost without this - edge cases, approaches tried and abandoned, "almost works"]
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
git_branch: "branch-name"
git_commit: "abc1234"
author: "name"
supersedes: "[[ADR-NNN-name]]"
---

# Title

## Status
Approved / Superseded by [[ADR-NNN-name]]

## Context
What is the issue motivating this decision?

## Decision
What is the change we're proposing or doing?

## Consequences
What becomes easier or harder because of this change?
```
