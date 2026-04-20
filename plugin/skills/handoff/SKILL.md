---
name: handoff
description: Create a handoff at end of session, or resume from one at start. Create compresses context into a portable document. Resume verifies state and presents a situational report.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion]
when_to_use: "Use at session boundaries. Triggers: 'create handoff', 'end session', 'resume from handoff', 'continue from where we left off', 'what was I doing'."
argument-hint: "[create | resume <path>]"
---

# Handoff — Session Continuity

Two modes:
- **`create`** (or no argument when ending work) — save context for next session
- **`resume <path>`** (or no path to pick most recent) — verify state and continue

---

## Mode: Create

=== CRITICAL: FILE:LINE REFERENCES, NOT CODE SNIPPETS ===
=== CRITICAL: SELF-CONTAINED — A READER WITH NO CONTEXT MUST BE ABLE TO RESUME ===
=== CRITICAL: DISTINGUISH COMPLETED WORK FROM REMAINING WORK ===

### CRITICAL CONSTRAINTS

- NEVER include excessive code snippets — use `file:line` references instead
- NEVER omit in-progress work state — the whole point is continuity
- ALWAYS capture git state (branch, last commit hash)
- ALWAYS distinguish completed from remaining work
- ALWAYS note surprises, blockers, decisions
- Self-contained — reader with zero context must be able to resume
- Only save what is NOT derivable from the current project state — focus on ephemeral state

### Know Your Failure Modes (Create)

You WILL be tempted to:
- Write verbose prose — handoffs should be lean
- Include large code snippets "for context" — use file:line references
- Skip uncommitted changes — uncommitted work is the most fragile state
- Omit failed approaches — they save the most future time
- Rush the Artifacts section — it's the most valuable part for resuming
- Assume the reader has session context — they have zero
- Write a handoff for a trivial session — don't, see Step 2b

### Protocol (Create)

#### Step 1: Read Hot Path

Read `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`

#### Step 2: Gather Git State

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git log --oneline -5
git status --short
git diff --stat
```

#### Step 2b: Check for Meaningful Work

Assess whether meaningful work was done:
- Tasks advanced, completed, or blocked?
- Decisions made or discoveries uncovered?
- Files created or modified?

If not: report "This session had no meaningful work to hand off" and STOP. Don't create empty handoffs.

#### Step 3: Gather Session Context

Identify:
1. **Tasks worked on** (note parent plan and phase)
2. **Changes made** (file:line references)
3. **Decisions made**
4. **Learnings** (surprises, non-obvious findings)
5. **Blockers**
6. **Action items**
7. **Artifacts** (documents needed to resume, in load order)

#### Step 4: Write Handoff

Save to `.compass/handoffs/YYYY-MM-DD_HH-MM-SS_description.md`:

```markdown
---
title: "Handoff: [brief description]"
type: handoff
status: active
area: <area>
tags: [tag1, tag2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
git_branch: <branch>
git_commit: <short hash>
---

# Handoff: [Description]

## Session Summary
[2-3 sentences: goal + progress]

## Tasks
| Task | Status | Notes |
|------|--------|-------|
| [Task] | done/in-progress/blocked | [note] |

## Critical References
- `file:line` — [why this matters]

## Recent Changes
- `file:line` — [what changed]

## Artifacts (Load in Order)
1. [[SPEC-NNN-name]] — source spec
2. [[PLAN-NNN-name]] — plan being executed (Phase N)
3. [[RESEARCH-name]] — key findings

## Decisions Made
- [Decision]: [Why] — consider ADR if significant

## Learnings
- [Surprise/insight] — consider lesson if broadly applicable

## Blockers
- [What stopped or slowed progress]

## Uncommitted Changes
[git status --short and diff --stat output]

## Action Items (Next Session)
1. [ ] [First thing]
2. [ ] [Second thing]

## Context for Resuming
[Nuance that would be lost — edge cases, abandoned approaches, almost-working state]
```

#### Step 5: Update Vault

1. Update `.compass/active.md` for status changes
2. Add handoff link to `.compass/index.md`
3. If a plan was being executed, annotate it:
   ```
   > **Last session:** YYYY-MM-DD — ended mid-Phase N. See handoff [[YYYY-MM-DD_HH-MM-SS_description]] for context.
   ```
4. `git add .compass/handoffs/<filename>.md`. Remind human to commit.

---

## Mode: Resume

=== CRITICAL: NEVER START WORK WITHOUT VERIFYING STATE ===
=== CRITICAL: HANDOFF IS A SNAPSHOT — TRUST CURRENT STATE OVER HANDOFF ===

### CRITICAL CONSTRAINTS (Resume)

- NEVER start working without verifying state
- NEVER assume the handoff is current — check git state and file existence
- ALWAYS present a situational report before taking action
- ALWAYS flag divergences
- ALWAYS load relevant lessons
- A handoff naming a specific file/function is a claim about when it was written — verify before acting

### Know Your Failure Modes (Resume)

You WILL be tempted to:
- Skip state verification because the handoff "looks recent" — verify anyway
- Classify a diverged codebase as "clean" to avoid reconciliation — be honest
- Ignore uncommitted changes that don't match — investigate them
- Trust file references without checking existence — check every reference
- Present the situational report as a formality — wait for real confirmation
- Skip lesson search — new lessons may have been created since the handoff

### Protocol (Resume)

#### Step 0: Resolve Handoff Path

If no handoff path provided:
1. Run `ls -t .compass/handoffs/*.md | head -5`
2. Present the five most recent with filenames
3. Ask which to resume

#### Step 1: Read Hot Path

Read `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`

#### Step 2: Load Handoff

Read the handoff document. Extract git branch/commit, tasks, critical file references, action items, blockers, uncommitted changes.

Read all documents listed under 'Critical References' and 'Artifacts' IN THIS THREAD (not via sub-agent).

When reading plans, look for `> **Last session:**` breadcrumbs.

#### Step 3: Verify Current State

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
git log --oneline <handoff_commit>..HEAD
git status --short
```

For each critical file: does it still exist? Modified since the handoff?

#### Step 4: Classify Scenario

**A. Clean continuation** — Same branch, same/ahead commit, no unexpected changes → resume from action items

**B. Diverged codebase** — Different branch OR commits by others since handoff → flag, show what changed, ask how to reconcile

**C. Incomplete work** — Uncommitted changes not in handoff → flag, present, ask for intent

**D. Stale handoff** — >7 days old OR >20 commits since → use handoff as historical context only, recommend fresh summary

#### Step 5: Present Situational Report

```markdown
## Handoff Resume: [handoff title]

### State Check
- **Scenario**: [A/B/C/D]
- **Handoff age**: [N days]
- **Branch**: [current] (handoff: [branch])
- **Commit**: [current] (handoff: [hash])
- **Commits since handoff**: N
- **Plan breadcrumb**: [if found]

### Divergences
[What changed that the handoff didn't expect]

### File Verification
| File | Handoff State | Current | Match? |
|------|---------------|---------|--------|
| `file.py` | Modified at :42 | Unchanged | Yes |

### Action Items from Handoff
1. [ ] [Item 1] — [still relevant?]

### Recommended Approach
[Based on scenario]

### Relevant Lessons
[Lessons that apply]
```

#### Step 6: Update State (After Human Confirms)

1. Mark handoff `status: done`
2. Update `.compass/active.md` if task statuses need correction
3. Proceed with the first action item (or hand control back)

=== REMINDER: CREATE — FILE:LINE, SELF-CONTAINED, CAPTURE GIT STATE. RESUME — VERIFY BEFORE ACTING, TRUST CURRENT STATE. ===
