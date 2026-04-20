---
name: plan
description: Create a new implementation plan or iterate on an existing one. For new plans, spawns the planner agent. For iterations, handles the surgical editing flow inline with confirmation gates.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, Agent, AskUserQuestion]
when_to_use: "Use when the user wants to plan work or modify an existing plan. Triggers: 'create a plan', 'plan this', 'make a plan', 'update the plan', 'iterate on the plan', 'change the plan'."
argument-hint: "[new | iterate <PLAN-NNN>]"
---

# Plan — Create or Iterate Implementation Plans

Two modes:
- **`new`** (or no argument) — spawn the `planner` agent to create a new plan from an approved spec
- **`iterate <PLAN-NNN>`** — surgically edit an existing plan with confirmation gates

## Mode: New Plan

Spawn the `planner` agent. It will:
- Read the approved spec and research findings
- Propose an outline (waits for approval)
- Create a detailed plan with ordered tasks
- Present the full plan for approval

## Mode: Iterate

Surgical plan editing. DO NOT rewrite the plan — make targeted changes with ripple-checks.

=== CRITICAL: NEVER REWRITE THE PLAN — SURGICAL EDITS ONLY ===
=== CRITICAL: ALWAYS CONFIRM UNDERSTANDING BEFORE EDITING ===
=== CRITICAL: ALWAYS RIPPLE-CHECK CONSISTENCY ACROSS ALL AFFECTED SECTIONS ===

### CRITICAL CONSTRAINTS

- NEVER rewrite the plan from scratch — use Edit for surgical changes only
- ALWAYS confirm your understanding before editing
- ALWAYS ripple-check: if one section changes, propagate to all affected sections
- NEVER leave open questions in a finalized plan
- NEVER accept vague requests at face value
- ALWAYS preserve two-tier success criteria (automated + manual verification) on every task
- Be SKEPTICAL: question whether the requested change actually improves the plan

### Know Your Failure Modes

You WILL be tempted to:
- Rewrite the entire plan because it's faster than surgical edits — use Edit instead
- Skip the confirmation step because the change seems obvious — always confirm
- Ignore ripple effects in sections far from the edit — check the whole document
- Accept vague feedback ("make it better") without pushing back
- Remove two-tier verification criteria to simplify — every task needs both
- Skip reading the full plan — partial reads cause inconsistent edits
- Keep patching a plan that's been iterated 4+ times — flag whether re-planning would be better

### Protocol

#### Step 1: Identify Plan and Changes

Progressive fallback:
1. **Plan path provided + specific changes described** — proceed directly
2. **Plan path provided, changes unclear** — read the plan, ask: "What do you want changed?"
3. **Neither provided** — read `.compass/active.md` and `.compass/index.md` to identify the active plan, then ask

#### Step 2: Read Hot Path

Read `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`, `.compass/meta/config.yaml`

#### Step 3: Read the Full Plan

Understand: goal, prerequisites, all phases and tasks, depends_on chains, risks, open questions, non-goals.

#### Step 4: Conditional Research

If the change introduces new technology/dependencies not in the plan:
- Use Grep/Glob/Read to verify feasibility (lightweight)
- OR spawn a researcher if deeper investigation is needed

#### Step 5: Check Lessons

Look for lessons that conflict with the requested change. Surface them.

#### Step 6: Confirm Before Editing

Present your understanding:

```
I understand the requested change:
- What changes: [sections/tasks affected]
- What stays the same: [sections not touched]
- Ripple effects: [other sections needing updates]
- Concerns: [conflicts, feasibility issues]

I'll make these edits:
1. [Edit 1]
2. [Edit 2]
3. [Ripple update]

Confirm?
```

Wait for confirmation.

**If rejected** → ask what's wrong, revise, re-present.
**If partial approval** → apply only approved edits, re-present the rest.

#### Step 7: Apply Surgical Edits

Use Edit for every change:
- One Edit call per logical change
- Preserve formatting exactly
- New tasks use provisional TASK-NNN from the counter
- Every task needs automated + manual verification

After all edits, append to the plan's `## Revision Log`:
```
- YYYY-MM-DD: [What changed] — [Why, from human feedback]
```

#### Step 8: Ripple-Check Consistency

| If this changed... | Check and update... |
|---------------------|---------------------|
| Scope / goal | "What We're NOT Doing" / non-goals |
| Task added/removed | Phase structure, depends_on chains, numbering |
| Approach / technology | Prerequisites, risks, relevant tasks |
| Prerequisites | Phase ordering |
| Task complexity | Whether task should split or merge |
| Phase removed | Backlog entries, depends_on references |

Apply ripple updates via Edit.

#### Step 9: Assess Research Needs

If the change introduces unresearched technology:
1. Flag: "This change introduces [X] with no existing research."
2. Add a research task to `active.md` or `backlog.md`
3. Mark affected tasks as `blocked_by: research` if needed

#### Step 10: No Open Questions

Review Open Questions:
- Resolved? Check off `[x]`
- New uncertainty? Resolve now or escalate
- A finalized plan has zero unchecked open questions

#### Step 11: Update Vault (If Task Structure Changed)

- Update `.compass/active.md`
- Update `.compass/meta/config.yaml` (TASK counter)
- Update `.compass/index.md` only if title/scope changed significantly
- Move tasks between active.md and backlog.md if phases changed

### Output Format

```markdown
## Plan Iteration Report

### Plan
[[PLAN-NNN-name]]

### Changes Applied
1. [Section]: [What changed and why]
2. [Section]: [What changed and why]

### Ripple Updates
- [Section]: [Updated because X changed]

### Open Questions
- [Resolved / added / unchanged]

### Vault Updates
- [x] Plan file edited
- [ ] active.md updated
- [ ] config.yaml counter incremented
- [ ] index.md updated

### Warnings
- [Concerns about the changes]
```

=== REMINDER: SURGICAL EDITS ONLY. CONFIRM BEFORE EDITING. RIPPLE-CHECK EVERYTHING. NO UNRESOLVED QUESTIONS. ===
