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
type: spec | research | plan | task | lesson | decision | handoff  # REQUIRED — all documents
status: draft | review | approved | active | done | archived  # REQUIRED — all documents
confidence: low | medium | high                  # REQUIRED for spec, research, decision
category: process | domain                       # REQUIRED for lesson — process (how to build) or domain (what to build)
area: architecture | frontend | backend | testing | devops | infra | docs | workflow  # REQUIRED — all documents
tags: [tag1, tag2]                               # REQUIRED — all documents (used for lesson matching)
created: YYYY-MM-DD                              # REQUIRED — all documents
updated: YYYY-MM-DD                              # REQUIRED — all documents (update on every edit)
git_branch: "branch-name"                        # REQUIRED for research, handoff, plan. Current git branch.
git_commit: "abc1234"                            # REQUIRED for research, handoff, plan. Short commit hash.
author: "human or agent name"                    # REQUIRED for research, handoff, plan, decision. Who created this document.
blocked_by: "description or [[link]]"            # OPTIONAL — tasks only
depends_on: ["[[link1]]", "[[link2]]"]           # OPTIONAL — any document
supersedes: "[[link]]"                           # OPTIONAL — when replacing an older document
---
```

### Status Field Transitions

The `status` field follows this lifecycle for all vault documents:

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
| Handoff | `YYYY-MM-DD_HH-MM-SS_descriptive-name.md` | `2026-03-12_14-30-00_implement-auth-flow.md` |

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

The Compass spec template is the default, but agents MAY use an alternative format (Rust RFC, Python PEP, Go Proposal, or any established spec format) when it better fits the domain. The alternative format must still include the YAML frontmatter above and at minimum a **Problem** and **Desired Outcome** section.

When using the Compass template: only **Problem** and **Desired Outcome** are required. All other sections are included when relevant — omit freely if they don't apply.

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

What exists today that's relevant? What has been tried before?

## User Scenarios

Who benefits and how? Brief narratives or user stories.

- As a [role], I want [goal], so that [benefit]

## Desired Outcome

What does success look like when this is done?

## Success Criteria

How do we measure that we've achieved the desired outcome?

- [ ] Criterion 1
- [ ] Criterion 2

## Constraints

Hard limits — technical, legal, organizational, time.

- Constraint 1

## Assumptions & Dependencies

What are we betting on? What must be true or exist for this to work?

- Assumption 1

## Non-Goals

Explicitly out of scope — things that could be goals but are not.

- Non-goal 1

## Risks

What could go wrong? What are the rabbit holes?

- Risk 1: [mitigation]

## Open Questions

- [ ] Question 1
```

### Research

Compass research documents are surveys of what already exists — not original research. The agent MUST choose the approach that best fits the question being investigated:

| Approach | When to use | Primary output |
|----------|------------|----------------|
| **Scoping Review** (Arksey & O'Malley) | Broad, exploratory questions — "What is the extent and nature of X?" Map a domain you don't yet understand. | Narrative synthesis with gap analysis |
| **Systematic Literature Review** (Kitchenham) | Focused, evidence-based questions — "What is the evidence for/against X?" Requires rigorous inclusion/exclusion criteria and quality assessment. | Synthesized evidence with quality ratings |
| **Systematic Mapping Study** (Petersen et al.) | Structuring a known field — "What approaches exist for X and how do they relate?" | Classification scheme + visual map (tables, matrices) |
| **Technology Landscape** (Gartner/ThoughtWorks style) | Evaluating options — "What tools/libraries/patterns exist for X and how do they compare?" | Per-item profiles + comparison matrix |

The agent selects the approach based on the question, states the choice in the Methodology section, and follows the structural emphasis of that approach. All three share the same template — the difference is in emphasis and depth of each section.

Only **Question** and **Findings** are required. All other sections are included when relevant — omit freely.

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

What is included and excluded from this survey. Boundaries of the investigation.

## Methodology

How the survey was conducted — search terms, sources consulted, tools used, inclusion/exclusion criteria. State the chosen approach (scoping review, systematic mapping, or technology landscape) and why.

## Findings

1. **Finding title** (confidence: high/medium/low)
   Description with specifics.
   - Evidence: `file:line` — what it shows
   - Evidence: [URL] — what it shows
   - Caveat: [why confidence is not higher, if applicable]

Confidence criteria:
- **High**: Multiple independent sources agree, directly verified in code/docs
- **Medium**: Single reliable source, or minor inconsistencies, not directly tested
- **Low**: Inferred from indirect evidence, conflicting information found

## Taxonomy

Classification scheme organizing what was found — categories, subcategories, and how items relate. This is the core deliverable of a mapping study. For scoping reviews, use thematic groupings. For landscapes, use comparison dimensions.

## Prior Art

How others have solved this problem or addressed this domain. Per-entity narratives with lessons learned from each.

## Contradictions

Conflicting evidence surfaced, not hidden. Juxtapose contradictory findings side by side with possible explanations.

## Gaps

What is missing from the landscape. What we could not determine. What additional investigation would help.

## Raw Evidence

<details>
<summary>Full evidence log</summary>

All file:line references, URLs, command outputs, search queries, and inclusion/exclusion decisions.

</details>
```

### Plan

A plan's `status` MUST NOT move to `approved` while it has unresolved Open Questions.

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

What exists today that's relevant. Reference specific files and line numbers.

- `path/to/file:line` — what it does / what's missing

## Desired End State

Concrete, verifiable description of what "done" looks like. Not aspirational — testable.

## Not Doing

Explicitly out of scope for this plan. Prevents scope creep.

- Not doing X because Y

## Prerequisites

What must be true before starting.

## Phases

### Phase 1: ...

- [ ] TASK-NNN: Description — files: [path/to/file], complexity: S/M/L, depends_on: none
  - Automated verification: [commands/tests an agent can run]
  - Manual verification: [checks requiring a human]
- [ ] TASK-NNN: Description — files: [path/to/file], complexity: S/M/L, depends_on: TASK-NNN
  - Automated verification: [commands/tests]
  - Manual verification: [human checks]

> **Pause here for human confirmation before proceeding to next phase.**

### Phase 2: ...

...

## Testing Strategy

Overall testing approach for the plan — new fixtures needed, integration test requirements, performance benchmarks. Per-task verification handles the details; this section covers the big picture.

## Open Questions

- [ ] Question 1

> **All open questions must be resolved before this plan can move to `approved` status.**
```

### Lesson

Lessons capture two distinct types of knowledge (per Reinertsen's *Principles of Product Development Flow*):

- **Process** (`category: process`): How to build — methods, tools, techniques, workflow. "We learned that mocking the DB in tests hides migration bugs."
- **Domain** (`category: domain`): What to build — the product, users, requirements, the problem space. "We learned that users need batch export, not single-file export."

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

What actually happened? What was surprising or went wrong?

## Why

Root cause or contributing factors.

## Lesson

What is the correct approach or understanding?

## Applicability

When should this lesson be recalled? What signals or situations make it relevant?
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

[If working from a plan: "Phase X of Y in [[PLAN-NNN-name]]" — gives the next session immediate orientation]

## Artifacts

Documents produced or updated this session that should be read on resume:

- `[[SPEC-NNN-name]]` — what's relevant
- `[[RESEARCH-name]]` — what's relevant

## Code Changes

- `path/to/file` — what was changed and why

## Decisions Made

- Decision: reasoning

## Learnings

- What was surprising or non-obvious

## Blockers

- What stopped or slowed progress

## Action Items (Next Session)

1. [ ] First thing to do when resuming

## Uncommitted Changes

[Output of `git status --short` and `git diff --stat` if there are uncommitted changes, or "None" if clean]

## Context for Resuming

[Any nuance that would be lost without this note — edge cases discovered, approaches tried and abandoned, things that "almost work" but need one more fix]
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

What is the issue that we're seeing that is motivating this decision?

## Decision

What is the change that we're proposing and/or doing?

## Consequences

What becomes easier or more difficult to do because of this change?
```
