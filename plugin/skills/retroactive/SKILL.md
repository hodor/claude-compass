---
name: retroactive
description: Create vault artifacts (specs, tasks, ADRs, lessons) for work that already happened without Compass. Interviews the human one question at a time to document the intent behind existing commits.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, AskUserQuestion]
when_to_use: "Use when bringing existing work into the vault. Triggers: 'document this commit', 'add retroactive spec', 'we did X but never specced it', 'backfill compass'."
argument-hint: "[<commit-hash> | <start>..<end>]"
---

# Retroactive — Document Work After the Fact

Create vault artifacts for commits that exist without corresponding specs, plans, or tasks. Interview the human about intent. Never fabricate. The human did the work — your job is documentation, not judgment.

## Protocol

### 1. Identify the work

If a commit hash was given, use it. Otherwise `git log --oneline -20`, present the commits, ask which to document.

### 2. Read the hot path

`.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`, `.compass/meta/config.yaml`.

### 3. Analyze the commits yourself

```bash
git show <hash> --stat
git show <hash>
git log --oneline <hash>~1..<hash>
```

For a range: `git log --oneline <start>..<end>` and `git diff <start>..<end> --stat`.

Build your own understanding before asking questions. Don't rely on commit messages alone.

### 4. Interview, one question at a time

**Q1:** "What problem did this solve?" → Problem section.
**Q2:** "What does success look like now?" → Desired Outcome + acceptance criteria.

If the change involved an architectural choice:
> "Was there a key decision here future developers should know about? (If yes, I'll create an ADR.)"

If the human doesn't know an answer, mark it as unknown. Don't invent.

### 5. Create the retroactive spec

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

### 6. Create the retroactive task

Increment the TASK counter. Add under "Recently Completed" in `active.md`:

```markdown
- [x] TASK-NNN: [Description] — complexity: [S/M/L], retroactive
  - Automated verification: [inferred]
  - Manual verification: [from Q2]
  - Spec: [[SPEC-NNN-name]]
  - Commit: `<hash>`
```

### 7. Create ADR (if applicable)

Only if the human confirmed a significant decision. Increment the ADR counter, create `ADR-NNN-descriptive-name.md` with decision, context, and reasoning.

### 8. Update the vault — REQUIRED

1. `.compass/index.md` — add the new spec under `## Specs` and any ADR under `## Decisions`. Documents not in `index.md` are invisible next session.
2. Confirm the new task is in `active.md` under "Recently Completed".
3. Counters in `config.yaml` should already be incremented.

### 9. Capture lessons (if applicable)

> "Did this work reveal any lessons or patterns future developers should know?"

If yes, create a lesson in `.compass/lessons/` and append to `lessons-catalog.yaml`.

### 10. Offer plan traceability

> "No plan existed for this work. Should I create a retroactive PLAN for traceability? (Usually only worth it for M or L complexity.)"

If yes, create a minimal plan with `status: done (retroactive)`.

## Output format

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

## Failure modes worth naming

- Dumping multiple questions at once to "speed up" the interview.
- Inventing acceptance criteria because the human is uncertain. Mark unknown.
- Skipping the git diff and trusting commit messages.
- Creating an ADR for every change. Only when the human confirms a real decision.
- Judging the code quality. Not your job.
- Skipping the hot path and creating duplicate specs.
- Guessing the problem statement from the code instead of asking.
