---
name: plan
description: Create a new implementation plan or iterate on an existing one. For new plans, spawns the planner agent. For iterations, handles the surgical editing flow inline with confirmation gates.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, Agent, AskUserQuestion]
when_to_use: "Use when the user wants to plan work or modify an existing plan. Triggers: 'create a plan', 'plan this', 'make a plan', 'update the plan', 'iterate on the plan', 'change the plan'."
argument-hint: "[new | iterate <PLAN-NNN>]"
---

# Plan - Create or Iterate Implementation Plans

Two modes:

- **`new`** (or no argument) - spawn the `planner` agent to create a new plan from an approved spec.
- **`iterate <PLAN-NNN>`** - surgically edit an existing plan.

## New plan

Spawn the `planner` agent. It reads the approved spec and research, drafts the full plan, and presents it for approval.

## Iterate

Surgical edits only - never rewrite the plan. Confirm understanding before editing. Ripple-check across all affected sections.

### Protocol

#### 1. Identify the plan and the changes

- Plan path + specific changes → proceed.
- Plan path, changes unclear → read it, ask: "What do you want changed?"
- Neither → read `.compass/active.md` and `index.md` to find the active plan, then ask.

#### 2. Read the hot path

`.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`.

#### 3. Read the full plan

Goal, prerequisites, all phases and tasks, depends_on chains, risks, open questions, non-goals.

#### 4. Conditional research

If the change introduces new tech/dependencies not in the plan, verify feasibility with Grep/Glob/Read. Spawn a researcher only if deeper investigation is needed.

#### 5. Check lessons

Surface any lessons that conflict with the requested change.

#### 6. Surface concerns first (only if needed)

If the change is ambiguous, conflicts with a lesson, or has feasibility issues, raise it before editing. Be specific about the trade-off. Propose what you'll do unless told otherwise. Don't ask "approve?" for things you already know the answer to.

#### 7. Apply surgical edits

- One Edit call per logical change.
- Preserve formatting exactly.
- New tasks use provisional TASK-NNN computed JIT (`max(N) + 1` across active.md + backlog.md).
- Every task keeps automated + manual verification.

Append to `## Revision Log`:
```
- YYYY-MM-DD: [What changed] - [Why, from human feedback]
```

#### 8. Ripple-check

| If this changed... | Check and update... |
|---------------------|---------------------|
| Scope / goal | "What We're NOT Doing" / non-goals |
| Task added/removed | Phase structure, depends_on chains, numbering |
| Approach / technology | Prerequisites, risks, relevant tasks |
| Prerequisites | Phase ordering |
| Task complexity | Whether the task should split or merge |
| Phase removed | Backlog entries, depends_on references |

#### 9. Assess research needs

If the change introduces unresearched technology:
1. Flag: "This change introduces [X] with no existing research."
2. Add a research task to `active.md` or `backlog.md`.
3. Mark affected tasks `blocked_by: research` if needed.

#### 10. No open questions

Resolve or escalate every unchecked open question. A finalized plan has zero.

#### 11. Update the vault

- `active.md` - task list reflects the changes.
- `index.md` - only if title/scope changed significantly.
- Move tasks between `active.md` and `backlog.md` if phases changed.

### Output format

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
- [ ] index.md updated

### Warnings
- [Concerns about the changes]
```

## Failure modes worth naming

- Rewriting the plan because it's faster than surgical edits. Use Edit.
- Skipping confirmation because the change "seems obvious."
- Ignoring ripple effects in sections far from the edit.
- Accepting vague feedback ("make it better") without pushing back.
- Removing two-tier verification to simplify. Every task needs both.
- Partial reads causing inconsistent edits.
- Patching a plan iterated 4+ times instead of flagging re-planning as the better option.
