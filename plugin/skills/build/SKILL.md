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

- `TASK-NNN` - execute that specific task
- `next` - pick the first unchecked task with no unmet dependencies
- `all` - execute all ready tasks (respecting dependencies, parallel when files don't overlap)
- `all-phases` - same as `all` but tell each builder `consecutive_phases: true` so they don't pause between phases. Runs end-to-end with only a final pause.
- (no argument) - list available tasks and ask which

## Protocol

1. **Read** `.compass/active.md` and `.compass/index.md`. Identify unchecked tasks, their parent plan, `depends_on` chains, and `files:` ownership.

2. **Select** tasks per the argument. Prerequisites: parent plan must be `approved` or `active`; `depends_on` tasks must be `[x]`. If blocked, report and stop.

3. **Execute:**
   - Parallel-safe tasks (non-overlapping `files:`): spawn one builder per task in parallel. Each builder runs in an isolated worktree (`isolation: worktree` in `builder.md`); the Agent SDK returns the worktree path and branch when the agent finishes. Record the (task, branch, worktree) tuple for each.
   - Serial tasks: spawn one at a time in dependency order, wait for builder + auto-spawned tester before the next. Serial builders still run in their own worktree but you merge after each, not at the end.
   - For `all-phases` mode: include `consecutive_phases: true` in the brief so builders skip the per-phase pause.

4. **Fix loop.** If testers report bugs, ask: "Tester found N issues in TASK-NNN. Fix? (yes / skip / abort)". On yes, spawn a targeted fix builder against the same branch with the bug diagnosis (not the full task). Max 3 cycles per task, then escalate.

5. **Merge branches back.** Once all builders + testers for a phase pass, merge each task branch into the orchestrator's branch in `depends_on` order:
   ```bash
   git merge --no-ff <task-branch> -m "Merge TASK-NNN: <description>"
   ```
   After every merge, re-run the project's smoke check (`make test`, `pytest`, etc.) to catch cross-task integration issues. If a merge conflicts, halt and present the list of remaining branches to the human - planner enforces file exclusivity so conflicts mean either a planner bug or a builder that wrote outside its `files:`.

6. **Validate (optional).** Offer to spawn the validator with the plan file.

7. **Vault.** Verify builders updated `active.md` and `index.md`. If any skipped, do it now. The SDK auto-cleans worktrees once their branches are merged.

## Report

```markdown
## Build Report

| Task | Builder | Tester | Status |
|------|---------|--------|--------|
| TASK-NNN: [desc] | complete | 5 tests pass | DONE |
| TASK-NNN: [desc] | complete | 3 tests, 1 fail → fixed (cycle 1) | DONE |
| TASK-NNN: [desc] | blocked | - | BLOCKED by TASK-NNN |

Next: run validator? Manual verification items from the plan?
```
