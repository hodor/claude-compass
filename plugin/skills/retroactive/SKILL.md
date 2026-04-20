---
name: retroactive
description: Create vault artifacts (specs, tasks, ADRs, lessons) for work that already happened without Compass. Interviews the human one question at a time to document the intent behind existing commits.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion]
when_to_use: "Use when bringing existing work into the vault. Triggers: 'document this commit', 'add retroactive spec', 'we did X but never specced it', 'backfill compass'."
argument-hint: "[<commit-hash> | <start>..<end>]"
---

# Retroactive — Document Work After the Fact

Create vault artifacts for commits that exist without corresponding specs/plans/tasks. Interview the human about intent, never fabricate.

=== CRITICAL: ONE QUESTION AT A TIME — NEVER DUMP A LIST ===
=== CRITICAL: NEVER FABRICATE — IF THE HUMAN DOESN'T KNOW, MARK AS UNKNOWN ===
=== CRITICAL: YOUR JOB IS DOCUMENTATION, NOT JUDGMENT ===

## CRITICAL CONSTRAINTS

- Ask ONE question at a time — never dump a list
- NEVER fabricate answers — if the human doesn't know, mark as unknown
- ALWAYS read the git history to understand what actually changed before asking
- ALWAYS create artifacts with `status: done (retroactive)` to distinguish from normal workflow
- ALWAYS read + increment counters from `meta/config.yaml`
- The human did the work already — respect that. Document, don't judge.

## Know Your Failure Modes

You WILL be tempted to:
- Ask multiple questions to speed up the interview — one at a time
- Invent acceptance criteria because the human is uncertain — mark as unknown
- Skip reading the git diff — always read it, don't rely on commit messages
- Create an ADR for every change — only if the human confirms a significant decision
- Judge the code quality — not your job
- Skip the hot path — read vault context first to avoid duplicates
- Guess at the problem statement from the code — ask, the human knows why

## Protocol

### Step 1: Identify the Work

Progressive fallback:
1. **Commit hash provided** → use it
2. **No hash** → `git log --oneline -20`, present commits, ask which to document

### Step 2: Read Hot Path

Read `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`, `.compass/meta/config.yaml`

### Step 3: Analyze the Commits

```bash
git show <hash> --stat
git show <hash>
git log --oneline <hash>~1..<hash>
```

For a range:
```bash
git log --oneline <start>..<end>
git diff <start>..<end> --stat
```

Build your own understanding before asking questions.

### Step 4: Interview (One Question at a Time)

**Q1:** "What problem did this solve?" → Problem section
**Q2:** "What does success look like now?" → Desired Outcome + acceptance criteria

If the change involved architectural choice, also ask:
> "Was there a key decision here that future developers should know about? (If yes, I'll create an ADR.)"

### Step 5: Create Retroactive Spec

Increment the SPEC counter in `config.yaml`. Create `SPEC-NNN-descriptive-name.md`:

```markdown
---
title: "Title"
type: spec
status: done (retroactive)
confidence: high
area: <area>
tags: [tag1, tag2, retroactive]
created: YYYY-MM-DD
updated: YYYY-MM-DD
git_commit: <hash>
---

# Title

## Problem
<from Q1>

## Context
<from git diff analysis — what existed before, what changed>

## Desired Outcome
<from Q2>

## Implementation
This spec was created retroactively. Implementation already exists at commit `<hash>`.

### Files Changed
<from git diff --stat>
```

### Step 6: Create Retroactive Task

Increment the TASK counter. Add to `.compass/active.md` under "Recently Completed":

```markdown
### Recently Completed

- [x] TASK-NNN: [Description] — complexity: [S/M/L], retroactive
  - Automated verification: [inferred]
  - Manual verification: [from Q2]
  - Spec: [[SPEC-NNN-name]]
  - Commit: `<hash>`
```

### Step 7: Create ADR (If Applicable)

Only if the human confirmed a significant decision:
1. Increment ADR counter
2. Create `ADR-NNN-descriptive-name.md`
3. Include decision, context, reasoning

### Step 8: Update Vault

1. Update `.compass/index.md` — add links to new spec and ADR
2. Ensure `active.md` has the new task
3. Counters in `config.yaml` should already be incremented

### Step 8b: Create Lessons (If Applicable)

Ask:
> "Did this work reveal any lessons or patterns future developers should know?"

If yes, create a lesson in `.compass/lessons/` and append to `lessons-catalog.yaml`.

### Step 9: Offer Plan Traceability

> "No plan existed for this work. Should I create a retroactive PLAN for traceability? (Usually only worth it for M or L complexity.)"

If yes, create a minimal plan with `status: done (retroactive)`.

## Output Format

```markdown
## Retroactive Report

### Commits Documented
- `<hash>`: [message]

### Artifacts Created
- [[SPEC-NNN-name]] — status: done (retroactive)
- TASK-NNN in active.md — [x] completed
- [[ADR-NNN-name]] (if applicable)

### Vault Updates
- [x] config.yaml counters incremented
- [x] index.md updated
- [x] active.md updated

### Open Items
- [ ] Create retroactive plan? (awaiting human decision)
```

=== REMINDER: ONE QUESTION AT A TIME. NO FABRICATION. DOCUMENTATION, NOT JUDGMENT. ===
