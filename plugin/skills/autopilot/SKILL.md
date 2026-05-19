---
name: autopilot
description: Run the full Compass pipeline (research → plan → build → test → validate) for S/M tasks. Orchestrates the actual agents with human checkpoints.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, Agent]
when_to_use: "Use for small-to-medium tasks that should run the full pipeline autonomously with checkpoints. Triggers: 'autopilot', 'run the full pipeline', 'do this task with compass'."
argument-hint: "<task description or TASK-NNN>"
---

# Autopilot - Full Pipeline Orchestrator

Runs the full Compass pipeline by spawning the dedicated agents in sequence. You orchestrate; you don't reimplement their work.

S/M complexity only - hard exit on L or larger. Spawn the agents. Pause at checkpoints for real human confirmation.

## When to use

Appropriate when the task has clear acceptance criteria, complexity is S or M (single file to ~5 files), risk is low (not auth, payments, data migration), and it is self-contained.

Not appropriate for L+ tasks, ambiguous requirements (run `/compass:spec` first), or sensitive systems.

## Protocol

### 1. Orient

Read `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`, `.compass/meta/config.yaml`. Read the parent plan and source spec. If complexity is L+, exit:

> "This task is too large for autopilot (complexity: [L/XL]). Use the full pipeline with human approval at each stage."

### 2. Research

Spawn the `researcher` agent. Wait for completion.

**Checkpoint 1:**
```
Research complete for: [task description]
[Summary of findings with confidence levels]
Approach based on research: [proposed implementation approach]

Proceed with planning? (approve / redirect / abort)
```

If research is thin, spawn another researcher instead of moving on.

### 3. Plan

Spawn the `planner` agent with the spec and research. Wait for completion.

**Checkpoint 2:**
```
Plan ready for: [task description]
[Summary of phases, tasks, complexity, verification]

Proceed with implementation? (approve / redirect / abort)
```

### 4. Build

Delegate to `/compass:build`. It spawns one builder per task (each in its own worktree per `builder.md`'s `isolation: worktree`), runs the fix loop, then merges task branches back in `depends_on` order with a smoke check after each merge. Halts and escalates if a merge conflicts (would only happen if `files:` ownership was wrong).

### 5. Validate

Spawn the `validator` agent with the plan file.

- **PASS** → proceed to vault update.
- **FAIL** → present report, ask whether to respawn builder or abort.
- **PARTIAL** → present what passed/failed, ask how to proceed.

### 6. Update the vault

Verify `active.md` has completed tasks checked off, ADRs exist for significant decisions, lessons captured for surprises, `index.md` includes any new documents, `config.yaml` counters incremented.

### 7. Commit (if the human approved)

1. Stage specific files with `git add <file>` - never `-A` or `.`.
2. Never stage `.compass/tmp/`.
3. Commit message explains *why*.
4. `git log --oneline -3` to confirm.

### 8. Report

Field lengths: one line per change, one line per decision/lesson. Omit Decisions, Lessons, Estimation Calibration if empty.

```markdown
## Autopilot Report: [Task]

### Pipeline
| Phase | Agent | Status | Key Output |
|-------|-------|--------|------------|
| Research | researcher | complete | [N findings] |
| Plan | planner | complete | [N tasks / M phases] |
| Build | builder | complete | [N files changed] |
| Test | tester | complete | [N tests pass] |
| Validate | validator | [PASS/FAIL/PARTIAL] |

### Changes
- [[file.py]] - [one line]

### Test Results
`<command>` - [verbatim ≤125 char excerpt]

### Decisions
- [decision] → [[ADR-NNN-name]]

### Lessons
- [surprise] → [[LESSON-name]]

### Estimation Calibration
Estimated [S/M] | Actual [S/M/L] | [one line why if differed]
```

## Failure modes worth naming

- Doing the research yourself instead of spawning the researcher.
- Writing a quick inline plan instead of spawning the planner.
- Writing code yourself instead of spawning the builder.
- Skipping the tester because "this is small." It always runs.
- Skipping the validator because "everything passed." It's the final gate.
- Rushing checkpoints - present findings and wait for real confirmation.
- Continuing past a weak research phase instead of respawning.
- Proceeding on an L+ task instead of hard-exiting.
