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
summary: "one-line summary"                      # REQUIRED for lesson
seen: [YYYY-MM-DD, ...]                          # OPTIONAL for lesson - recurrence dates, cap 3
escalated: YYYY-MM-DD                            # OPTIONAL for lesson - set when seen would exceed 3
escalation_reason: "..."                         # OPTIONAL for lesson - paired with escalated
score: 5                                         # REQUIRED for lesson, range 1-10
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
| `[[filename]]` | Link to a root artifact (omit `.md`) |
| `[[unit/specs/SPEC-001-name]]` | Link to an artifact inside a unit folder (path-qualified) |
| `[[filename#Section]]` | Link to a section within a document |
| `[[filename\|Display Text]]` | Link with custom display text |

Always wikilinks for cross-references. Never relative markdown links. See "Unit folders" below for when a link must be path-qualified.

## Math (LaTeX)

**Scope: `.md` files only.** LaTeX rules below apply to vault documents written to disk. Never use LaTeX in chat output, terminal responses, or agent reports surfaced to the user - the terminal does not render MathJax, so `$x^2$` displays as literal characters. For chat, use plain prose or unicode (≤, ≥, →, ∑, π, σ) or code-fenced expressions like `O(n log n)`.

Both Obsidian and GitHub render LaTeX math via MathJax. Use it when prose would be less clear than a formula. Especially common in research documents (statistical analysis, complexity, ML, probability) and in plans or specs that quantify behavior.

| Syntax | Use | Example |
|--------|-----|---------|
| `$...$` | Inline math | `the cost is $O(n \log n)$` |
| `$$...$$` | Block / display math | `$$P(A \cap B) = P(A) \cdot P(B \mid A)$$` |
| `\$` | Literal dollar sign in prose | `the budget was \$500` |

Rules:

- Use LaTeX standard syntax (`\frac`, `\sum`, `\sqrt`, `\cdot`, `\mid`, `\to`, Greek letters, etc.).
- Inline math goes inside one sentence. If the expression spans multiple lines or needs to be referenced, use block math.
- Escape literal `$` as `\$` to avoid the parser treating it as a math delimiter.
- Do NOT use math notation to dress up prose. If the formula does not add precision a sentence cannot, drop it.
- Research is the type most likely to need it; specs and plans use it sparingly; lessons and handoffs rarely.

Examples in context:

```markdown
The dedup judgment runs in $O(n)$ over the catalog where $n$ is the active lesson count.

Bayes update for relevance score:

$$P(\text{relevant} \mid \text{tags}) = \frac{P(\text{tags} \mid \text{relevant}) \cdot P(\text{relevant})}{P(\text{tags})}$$

Convergence threshold across $N$ agents is $\geq 0.8$ before promoting a finding.
```

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

`NNN` numbers are computed JIT at creation, not stored anywhere. There is NO counter file. Numbers are LOCAL to each folder (resets at each level). See [[ADR-003-drop-counter-file-jit-compute]] for the rationale and [[ADR-004-hierarchical-specs-with-facets]] for the hierarchy rules.

**JIT compute rule (the single source of truth):**

| Artifact | Next-number rule |
|---|---|
| SPEC | `max(N from glob '**/.compass/specs/SPEC-N-*.md') + 1`, default 1 |
| ADR | `max(N from glob '**/.compass/decisions/ADR-N-*.md') + 1`, default 1 |
| PLAN | `max(N from glob '**/.compass/plans/PLAN-N-*.md') + 1`, default 1 |
| TASK | `max(N) + 1` across `grep -oE 'TASK-([0-9]+)' .compass/active.md .compass/backlog.md`, default 1 |
| RESEARCH | no number; descriptive name only |
| LESSON | no number; descriptive slug only |
| Handoff | no number; `YYYY-MM-DD_HH-MM-SS_name` timestamp |

The filesystem is the source of truth. Skip the `**/` prefix and Glob returns zero (see [[LESSON-glob-hidden-dirs-prefix]]).

Inside a unit folder the same rule scopes to the unit's own type dir: `compass next-num spec <unit>` computes max+1 over `<unit>/specs/`. Root numbering (`compass next-num spec`) never counts unit artifacts, and vice versa.

Names must be self-descriptive - `SPEC-001.md` is never acceptable. Lowercase kebab-case for the descriptive part.

## Hierarchical specs and plans (folders)

A flat spec is a single `.md` file. A complex spec is a **folder** whose `index.md` is the parent spec at that level. Children inside the folder follow the same convention recursively. Path is identity; numbering resets per folder.

**A spec earns its own folder when** it has 3+ sub-concerns OR its body would exceed roughly 2,000 tokens. Below the threshold the extra hop costs more than the split saves; above it, leaving content flat creates a mid-context blob that triggers the documented "lost in the middle" penalty (Liu et al. TACL 2024, 20-30 point accuracy hit).

```
.compass/specs/
├── SPEC-001-flat-thing.md                   leaf
├── SPEC-002-tile-editor/                    folder = complex spec
│   ├── index.md                             the parent spec at this level
│   ├── SPEC-001-master-material.md          child (local numbering resets)
│   ├── SPEC-002-brush-system/               sub-complex = nested folder
│   │   ├── index.md
│   │   ├── SPEC-001-stroke-rendering.md
│   │   └── SPEC-002-blending-modes.md
│   └── SPEC-003-tile-grid.md
```

Same convention for `plans/`. Plans typically map to specs and inherit the spec's structure.

### Wikilinks across folders

Obsidian wikilinks accept slashes. Reference a child spec by its full path inside the type root:

- `[[SPEC-002-tile-editor]]` resolves to `SPEC-002-tile-editor/index.md`
- `[[SPEC-002-tile-editor/SPEC-001-master-material]]` resolves to the child
- `[[SPEC-002-tile-editor/SPEC-002-brush-system/SPEC-001-stroke-rendering]]` for nested

### Folder-level index.md (the warm tier branch summary)

A folder's `index.md` is the parent spec body PLUS a RAPTOR-style summary of its children. Required structure for folder index.md:

```markdown
---
title: "..."
type: spec | plan
status: ...
area: ...
tags: [...]            # REQUIRED - facets for this branch
children_count: N      # REQUIRED - synced by index-sync
summary: "..."         # REQUIRED - one-line representation of the branch
---

[Parent spec body. Hold decisions and concerns that stay at this level. Delegate sub-concerns to children.]

## Children

- [[SPEC-001-master-material]] — one-line summary of what the child covers
- [[SPEC-002-brush-system]] — one-line summary
- [[SPEC-003-tile-grid]] — one-line summary
```

When the children change, the `## Children` section must be refreshed (`/compass:consolidate` does this).

## Unit folders (the hybrid root)

The vault root is hybrid. Type-first dirs (`specs/`, `plans/`, ...) hold standalone work; a large unit of work gets its own folder at the vault root, named for the work itself, holding its own type subdirs:

```
.compass/
├── specs/                            root type dir - standalone work
├── plans/
├── compass-cli/                      unit folder - one large unit of work
│   ├── index.md                      type: unit marker, title, children listing
│   ├── specs/
│   │   └── SPEC-001-cli-contract.md  numbering local to the unit
│   ├── plans/
│   ├── research/
│   └── lessons/                      aggregated into meta/lessons-catalog.yaml by sync
└── ...
```

A unit declares itself with `type: unit` in the frontmatter of its own `index.md`. The marker is what classifies the folder: a non-reserved root folder without it is ignored by the CLI and reported by `compass validate` as `unclassified_root_folder`, never guessed at. The unit `index.md` carries the title (used as the unit's section header in the root index) and a one-line-per-child listing, refreshed by `/compass:consolidate`.

Inside a unit, folder specs follow the same [[ADR-004-hierarchical-specs-with-facets]] rules as at the root. Unit `lessons/` stay on the hot path: `compass sync` aggregates them into `meta/lessons-catalog.yaml` (filename is the row key, so lesson filenames must be unique vault-wide).

### Bare stems vs path-qualified links

Numbering is local per unit, so `SPEC-001-...` can exist at the root and inside any unit - bare stems are genuinely ambiguous across units. The link form depends on where the target lives:

| Target | Link form | Example |
|--------|-----------|---------|
| Root flat artifact | bare stem | `[[SPEC-004-mechanical-work-off-the-agent-budget]]` |
| Root folder spec | folder name | `[[SPEC-002-tile-editor]]` |
| Unit artifact | path-qualified `<unit>/<type-dir>/<stem>` | `[[compass-cli/specs/SPEC-001-cli-contract]]` |
| Folder spec inside a unit | folder's vault-relative path | `[[compass-cli/specs/SPEC-002-brush-system]]` |

Always author unit-artifact links path-qualified. `compass sync` emits exactly these forms in the root index, and `compass validate` warns `ambiguous_wikilink` when a bare stem resolves to more than one file; the path-qualified form resolves to exactly one.

### Where a new artifact goes

Before creating an artifact, resolve its destination root: if the work belongs to an existing unit (its spec, plan, or research lives under `.compass/<unit>/`), create the artifact in that unit's type dir, number it with `compass next-num <type> <unit>`, and link it path-qualified. Otherwise create it in the root type dir with a bare-stem link. Detection of root artifact sets that have outgrown the flat layout is mechanical (`compass unit-check` reports candidates when 3+ artifact types trace to one spec); promotion is the human's decision.

## Facet tags (the multi-parent layer)

Every spec, plan, lesson, ADR, and research doc has a `tags: [...]` frontmatter field. Tags are folksonomy - free-form, not a controlled vocabulary. A spec belongs to whatever facets describe it. A master material spec is `tags: [rendering, tile-editor, materials, shaders]` even though its folder is `tile-editor/`.

Tags are the multi-parent retrieval primitive. The agent reaches multi-perspective specs by reading `.compass/meta/tag-index.yaml`, not by crawling folders.

### Tag index file (auto-generated)

`.compass/meta/tag-index.yaml` is regenerated by `index-sync` whenever a tagged file is written. Format:

```yaml
tags:
  rendering:
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
    - specs/SPEC-002-tile-editor/SPEC-002-brush-system/SPEC-001-stroke-rendering.md
  tile-editor:
    - specs/SPEC-002-tile-editor/index.md
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
    - specs/SPEC-002-tile-editor/SPEC-002-brush-system/index.md
  materials:
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
```

The tag index is NOT in the hot path. The agent reads it only when answering a multi-tag question. This is the cold-tier retrieval primitive.

### Tag hygiene

Folksonomy invites synonyms (`tile-editor`, `tileEditor`, `tile_editor`) and typos. `/compass:consolidate` runs a vocabulary pass that proposes merges and rewrites all spec frontmatter atomically. Human approves.

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

Lessons are never authored by agents in prose. Creation goes through the `lesson-write` skill, invoked by `extract-lessons` (auto at phase boundary) or `/compass:learned` (manual). Both paths share dedup, anti-list filtering, and the 5-line cap.

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
