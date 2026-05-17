---
name: build
description: Execute tasks from active.md by spawning builder agents. Handles parallel execution for non-overlapping tasks, the fix loop, and optional validation.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Bash, Agent, Write, Edit]
when_to_use: "Use when the user wants to execute planned tasks. Triggers: 'build this', 'execute the tasks', 'run the plan', 'start building', 'implement this'."
argument-hint: "[TASK-NNN | next | all | all-phases]"
---

# Build

Spawn builder agents to execute tasks. The main conversation orchestrates; it does not code directly.

## Arguments

- `TASK-NNN` — execute that specific task
- `next` — pick the first unchecked task with no unmet dependencies
- `all` — execute all ready tasks (respecting dependencies, parallel when files don't overlap)
- `all-phases` — same as `all` but tell each builder `consecutive_phases: true` so they don't pause between phases. Runs end-to-end with only a final pause.
- (no argument) — list available tasks and ask which

## Protocol

1. **Read** `.compass/active.md` and `.compass/index.md`. Identify unchecked tasks, their parent plan, `depends_on` chains, and `files:` ownership.

2. **Select** tasks per the argument. Prerequisites: parent plan must be `approved` or `active`; `depends_on` tasks must be `[x]`. If blocked, report and stop.

3. **Execute:**
   - Parallel-safe tasks (non-overlapping `files:`): spawn one builder per task in parallel. Each gets its file list.
   - Serial tasks: spawn one at a time in dependency order, wait for builder + auto-spawned tester before the next.
   - For `all-phases` mode: include `consecutive_phases: true` in the brief so builders skip the per-phase pause.

4. **Fix loop.** If testers report bugs, ask: "Tester found N issues in TASK-NNN. Fix? (yes / skip / abort)". On yes, spawn a targeted fix builder with the bug diagnosis (not the full task). Max 3 cycles per task, then escalate.

5. **Validate (optional).** Offer to spawn the validator with the plan file.

6. **Vault.** Verify builders updated `active.md` and `index.md`. If any skipped, do it now.

## Report

```markdown
## Build Report

| Task | Builder | Tester | Status |
|------|---------|--------|--------|
| TASK-NNN: [desc] | complete | 5 tests pass | DONE |
| TASK-NNN: [desc] | complete | 3 tests, 1 fail → fixed (cycle 1) | DONE |
| TASK-NNN: [desc] | blocked | — | BLOCKED by TASK-NNN |

Next: run validator? Manual verification items from the plan?
```
