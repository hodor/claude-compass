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

## Rolling-wave format

A plan may carry a `## Later (intent only)` section instead of detailing every task upfront - the shape [[ADR-009-rolling-wave-mechanism]] fixes. Every line sits in one of three detail regions, decided by which heading it falls under:

- **Detailed** - the default: every line not inside a Later or record region. That's everything before the first `## Later` heading, and everything under any later level-1 or level-2 heading that is itself neither `## Later` nor `## Wave N elaborated` - a `## Risks` or `## Verification` section past the Later region is detailed again. Task lines here claim their decisions in full. A promoted `### Wave N (detailed)` section belongs under `## Phases`, above `## Later`: a level-3 heading doesn't close a Later region by itself, so the same section placed below `## Later` would classify scoped instead.
- **Scoped** - the `## Later (intent only)` region itself, running to the next level-1 or level-2 heading. One line per future task, in the same head grammar as a detailed task line but bare: `- [ ] TASK-NNN: intent - files: [...], decisions: [...], lessons: [...]`, with no `complexity`, no `depends_on`, and no verification bullets. A scoped task line still claims its decisions; `compass coverage` counts it `scoped`, and the default gate never fails on `scoped`.
- **Record** - a `## Wave N elaborated` section (the canonical heading; `## Wave 1 - elaborated (date)` and similar shapes also match). It records what a wave learned and claims nothing: any citation inside it, including a quoted intent line, is discarded outright by `compass coverage` and `compass lesson-coverage`. Quote a superseded intent line only inside a fence or backtick span - unfenced it still claims nothing, but it reads as a live, unclaimed task to a human, and to any tool that scans for the task-line grammar.

`commit-upfront:` is the one override: inside `## Later`, a task line whose trailing comma-separated fields include one beginning with the `commit-upfront:` token classifies detailed despite sitting in the Later region - for detail that's genuinely known now or too expensive to leave for later. Convention writes the field last, so its reason text can carry commas without swallowing the fields after it.

The two gates read `scoped` differently. `compass coverage`'s summary always carries a scoped count, zero when the plan has no `## Later` region; `--strict` turns that count into failures too, which makes it the plan-*completion* gate rather than the approval one - a `scoped` row still reads `scoped` under `--strict`, only the exit code and the verdict's `FAIL (strict)` suffix move. `compass lesson-coverage` has no `--strict` flag; its scoped clause appears in the summary only when the plan actually has a `## Later` region.

## Iterate

Surgical edits only - never rewrite the plan. Confirm understanding before editing. Ripple-check across all affected sections.

Iterate and elaborate are different mechanisms with different owners. Iterate is a shape change - scope, dropped goals, new phases - and always goes through the human gate: this skill handles it. Promoting a `## Later` intent line into a detailed task is elaboration, not iteration - it's the build flow's own step, it presents a delta (what was learned, what the next wave is), and it never re-approves the plan. A request that only wants an intent line promoted, with nothing else about the plan changing, isn't an iterate-mode edit.

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
- `decisions: [<doc-stem>/D-NN, ...]` mirrors `files:` - optional, source-qualified citations of the decisions a task implements. Every decision the plan intends to build belongs in some task line's `decisions:` field, detailed or intent - never only in prose. Prose that discusses a decision names it bare (`D-04`) or backticked, either of which claims nothing - the hazard is prose *manufacturing* a claim: a source-qualified citation appearing only in prose, for a decision no task line names anywhere, reads `covered` from that prose alone and passes even `--strict` with nothing committed to build it.

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
| Task `decisions:` field or citations | Re-run `compass coverage <plan>` before closing the iteration |
| Task `lessons:` field or citations | Re-run `compass lesson-coverage <plan>` and note the summary line - advisory only, so unlike `decisions:` this never blocks the iteration |
| An unpromoted `## Later` intent line no longer matches the change | Supersede it in the `## Wave N elaborated` record section - quote the old line inside a fence - never edit it in place |

If the change adds, removes, or recites decisions differently, re-run `compass coverage <plan>` after the edits and note the resulting summary line in the iteration report - iterate mode doesn't gate on it, but a plan already `approved` should not silently regress to an uncovered state.

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
