# Obsidian skill: document templates

The sections a Spec, Research, Plan, Lesson, Handoff and Decision (ADR) document can carry, with their required parts.

## Document templates

These show every section a document type CAN have, not what every document MUST have. Omit empty sections in the file you write - don't stub them. Only required sections are mandatory.

Required sections per type:
- **Spec:** Problem, Desired Outcome.
- **Research:** Question, Findings. (Research is the one type that may emit all sections - it captures evidence.)
- **Plan:** Goal, Phases.
- **Lesson:** none (body is free-form, hard-capped at 5 lines).
- **Handoff:** Session Summary, Start Here, Action Items.
- **Decision:** Context, Decision, Consequences.

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
summary: "<one line - the index copies this>"
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Title

<picture: Mermaid diagram of the problem, the outcome and the rulings>

> [!IMPORTANT]
> You decide: <the one question approving answers>

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

## Decisions (made by the human)
Explicit rulings made during the interview - a trade-off resolved, an approach chosen. Record each as a `- **D-NN:** text` bullet in a callout (see "Decision bullets" above), not as prose elsewhere in the spec.

> [!NOTE]
> - **D-01:** [ruling]

## Assumptions & Dependencies
What are we betting on? What must be true for this to work?

## Risks
- Risk 1: [mitigation]

## Open Questions
- [ ] A question the human left open, in his words; never one the agent minted
```

### Research

Compass research is a survey of what already exists - not original research. The `research-methods` skill (`plugin/skills/research-methods/SKILL.md`) catalogs eight conduct methodologies with a chooser that routes a question's shape to one. Load it and pick from there.

State the chosen methodology in Methodology. Only **Question** and **Findings** are required. Mark a code or blog source by naming its owner check - community signals, or identity and affiliation - and mark a preprint with its [Preprint] version and date, adding the published version once one exists.

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

<picture: Mermaid diagram of the findings by confidence and what they mean for the spec>

> [!IMPORTANT]
> You decide: <the one question approving answers>

## Question
What are we investigating? What would constitute a complete answer?

## Scope
What is included and excluded.

## Methodology
How the survey was conducted - search terms, sources, tools, inclusion/exclusion criteria. State the methodology chosen, by name, from the `research-methods` skill, and why it fits the question's shape.

## Findings
1. **Finding title** (confidence: high/medium/low)
   Description with specifics.
   - Evidence: `file:line` - what it shows
   - Evidence: [URL] - what it shows
   - Marks: evidence type, retraction status, preprint status, citation count, convergence, as terse tokens - for example `Marks: peer-reviewed; not retracted; preprint 2024-05, published 2025-02; 120 citations; 3 sources agree`, or for a repository `Marks: code, owner checked; 40 citations; 1 source`
   - Grade: how much the evidence type mark should weigh for this finding (high, medium, low), separate from the finding's own confidence above. Written whenever grading was disclosed at the gate: `grading: allowed` carries the grade, `grading: refused` carries no grade. The field is absent when no disclosure happened, meaning the findings are marked and ungraded
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

<picture: Mermaid diagram of the stages and the task dependencies>

> [!IMPORTANT]
> You decide: <the one question approving answers>

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
- [ ] TASK-NNN: Description - files: [path/to/file], complexity: S/M/L, depends_on: none, decisions: [<doc-stem>/D-NN, ...]
  - Automated verification: [commands/tests]
  - Manual verification: [human checks]
- [ ] TASK-NNN: Description - files: [path/to/file], complexity: S/M/L, depends_on: TASK-NNN, decisions: [<doc-stem>/D-NN, ...]
  - Automated verification: [commands/tests]
  - Manual verification: [human checks]

> **Pause here for human confirmation before proceeding to next phase.**

### Phase 2: ...

## Later (intent only)
Work named but not yet detailed - one head-grammar line each (the task line only, no indented verification bullets):

- [ ] TASK-NNN: Description - files: [path/to/file], decisions: [<doc-stem>/D-NN, ...]
- [ ] TASK-NNN: Description - files: [path/to/file], decisions: [<doc-stem>/D-NN, ...], commit-upfront: cost, risk, or dependency that makes this one worth detailing now

`## Wave N elaborated` sections are appended by the elaboration step as intent lines are promoted - never authored upfront.

## Testing Strategy
Overall testing approach - new fixtures, integration test needs, performance benchmarks. Per-task verification covers details.

## Open Questions
- [ ] Question 1

> **All open questions must be resolved before `approved` status.**
```

`decisions:` is optional and mirrors `files:` - source-qualified citations (`<doc-stem>/D-NN`, see "Decision bullets" above) of the decisions a task implements. `compass coverage <plan>` checks these against the plan's `depends_on` sources.

`lessons:` is optional and sits in the same position, after `files:` - catalog filenames (`LESSON-name` or `LESSON-name.md`) of the lessons a task applies. `compass lesson-coverage <plan>` resolves these against `.compass/meta/lessons-catalog.yaml`.

`decisions:` and `lessons:` are the citation home - the field where a task line stakes its own claim. For `lessons:` this is the only citation surface `compass lesson-coverage` reads. A decision can also be claimed by a source-qualified citation in prose when no task line claims it (see "Decision bullets" above); either way, naming a decision bare (`D-04`) or in backticks claims nothing.

### Lesson

Two types (per Reinertsen's *Principles of Product Development Flow*):

- **Process** (`category: process`) - how to build. "Mocking the DB in tests hides migration bugs."
- **Domain** (`category: domain`) - what to build. "Users need batch export, not single-file."

**Body is free-form, hard-capped at 5 lines.** No template sections. Compression is the discipline. Lessons longer than 5 lines must be rewritten before they can be written. The `lesson-write` skill enforces the cap.

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
summary: "One-line summary, <=120 characters"
seen: []                    # OPTIONAL - dates lesson was rediscovered, cap 3
escalated: YYYY-MM-DD       # OPTIONAL - set when seen would exceed 3
escalation_reason: "..."    # OPTIONAL - paired with escalated
---

Free-form markdown body. **Hard cap 5 physical lines including embedded blank lines.** No `# Title` H1 - the frontmatter `title` field is the canonical title. Common shape (not required): the rule, the reason, the trigger condition. Compress.
```

Lessons are never authored by agents in prose. Creation goes through the `lesson-write` skill, invoked by `extract-lessons` (auto at phase boundary) or `/compass:learned` (manual). Both paths share dedup, anti-list filtering, and the 5-line cap. An agent that notices a candidate mid-work runs `compass capture-note "<one sentence>"`; the capture pass judges it, and the human is never asked.

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
What is the change we're proposing or doing? Record each ruling as a `- **D-NN:** text` bullet in a callout (see "Decision bullets" above) so it can be traced through plans.

> [!NOTE]
> - **D-01:** [ruling]

## Consequences
What becomes easier or harder because of this change?
```
