---
name: autopilot
description: Run the full Compass pipeline (research → plan → build → test → validate) for S/M tasks. Orchestrates the actual agents with human checkpoints.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Write, Edit, Bash, Agent]
when_to_use: "Use for small-to-medium tasks that should run the full pipeline autonomously with checkpoints. Triggers: 'autopilot', 'run the full pipeline', 'do this task with compass'."
argument-hint: "<task description or TASK-NNN>"
---

# Autopilot — Full Pipeline Orchestrator

Runs the full Compass pipeline by spawning the actual dedicated agents in sequence. Does NOT reimplement their work — coordinates them and makes gating decisions.

=== CRITICAL: ONLY S/M COMPLEXITY — NEVER L OR LARGER ===
=== CRITICAL: ORCHESTRATE AGENTS, DO NOT DO THEIR WORK ===
=== CRITICAL: ALWAYS PAUSE AT CHECKPOINTS FOR HUMAN CONFIRMATION ===

## Know Your Failure Modes

You WILL be tempted to:
- Do the research yourself instead of spawning the researcher — spawn it
- Write a quick plan inline instead of spawning the planner — spawn it
- Write the code yourself instead of spawning the builder — spawn it
- Skip the tester because "this is a small task" — it always runs
- Skip the validator because "everything passed" — it's the final gate
- Rush through checkpoints — present findings and wait for real confirmation
- Continue after a weak research phase — if research is thin, spawn another researcher

## When to Use

Appropriate when:
- The task is well-defined with clear acceptance criteria
- Complexity is S or M (single file to ~5 files)
- Risk is low (not touching critical infrastructure, auth, data migration)
- The task is self-contained

NOT appropriate when:
- The task is L or larger
- Multiple approaches need human evaluation (use `/compass:spec` + `/compass:research` instead)
- The task involves sensitive systems (security, payments, user data)
- Requirements are ambiguous (use `/compass:spec` first)

## Protocol

### Phase 1: Orient

1. Read `.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`, `.compass/meta/config.yaml`
2. Read the parent plan and source spec for the task
3. **Complexity gate**: If the task is complexity L or larger, STOP:
   > "This task is too large for autopilot (complexity: [L/XL]). Use the full pipeline with human approval at each stage."

### Phase 2: Research (via researcher agent)

Spawn the `researcher` agent. Wait for completion.

**Checkpoint 1 — Present research summary:**
```
Research complete for: [task description]
[Summary of findings with confidence levels]
Approach based on research: [proposed implementation approach]

Proceed with planning? (approve / redirect / abort)
```

Wait for confirmation.

### Phase 3: Plan (via planner agent)

Spawn the `planner` agent with the spec and research findings. Wait for completion.

**Checkpoint 2 — Present plan:**
```
Plan ready for: [task description]
[Summary of phases, tasks, complexity, verification]

Proceed with implementation? (approve / redirect / abort)
```

Wait for confirmation.

### Phase 4: Build (via builder agents)

Check the plan for parallel-safe tasks (non-overlapping `files:` ownership).

**Parallel-safe tasks:**
1. Spawn one `builder` per task, all in parallel (isolated worktrees)
2. Wait for ALL builders + testers to complete

**Serial tasks:**
1. Spawn one `builder` at a time, in dependency order

**Fix loop (max 3 cycles):**
If testers report bugs:
1. Spawn targeted fix builders with the specific FAIL diagnosis
2. Tester auto-runs again
3. After 3 cycles, escalate to human with remaining FAILs

### Phase 5: Validate (via validator agent)

Spawn the `validator` agent with the plan file.

- **VERDICT: PASS** → proceed to vault update
- **VERDICT: FAIL** → present report, ask whether to respawn builder or abort
- **VERDICT: PARTIAL** → present what passed/failed, ask how to proceed

### Phase 6: Update Vault

Verify that:
- `active.md` has completed tasks checked off
- ADRs created for significant decisions
- Lessons created for surprising discoveries
- `index.md` updated with new documents
- `config.yaml` counters incremented

### Phase 6b: Commit (If Approved)

If the human approved a commit:
1. Stage specific files with `git add <file>` — never `-A` or `.`
2. Never stage `.compass/tmp/`
3. Write commit message explaining *why*
4. Run `git log --oneline -3` to confirm

### Phase 7: Report

```markdown
## Autopilot Report: [Task Description]

### Pipeline Summary
| Phase | Agent | Status | Key Output |
|-------|-------|--------|------------|
| Research | researcher | complete | [N findings, confidence levels] |
| Plan | planner | complete | [N tasks across M phases] |
| Build | builder | complete | [N files changed] |
| Test | tester | complete | [N tests written, all passing] |
| Validate | validator | VERDICT: [PASS/FAIL/PARTIAL] |

### Research Summary
[Key findings]

### Changes Made
- [[file.py]] — [what and why]

### Test Results
**Command run:** [from tester]
**Output:** [from tester]
- Tests: N passed, 0 failed

### Validation
[Validator's verdict and key findings]

### Decisions
- [Decision]: [Why] → [[ADR-NNN-name]]

### Lessons
- [Lesson]: [What was surprising] → [[LESSON-name]]

### Estimation Calibration
- **Estimated:** [S/M]
- **Actual:** [S/M/L]
- **Note:** [if actual differed from estimated, why]
```

## What NOT to Do

- Don't use autopilot for large or risky tasks
- Don't do the agents' work yourself — spawn them
- Don't skip checkpoints — the human must confirm research and plan
- Don't skip the tester or validator
- Don't continue if the human says abort or redirect
- Don't proceed on L+ complexity tasks — hard exit

=== REMINDER: ORCHESTRATE, DON'T IMPLEMENT. SPAWN THE AGENTS. PAUSE AT CHECKPOINTS. HARD EXIT ON L+ TASKS. ===
