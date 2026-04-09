---
name: build
description: Execute tasks from active.md by spawning builder agents. Handles parallel execution for non-overlapping tasks, fix loops, and validation.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Bash, Agent, Write, Edit]
when_to_use: "Use when the user wants to execute planned tasks. Triggers: 'build this', 'execute the tasks', 'run the plan', 'start building', 'implement this'."
argument-hint: "[TASK-NNN | next | all]"
---

# Build — Task Execution Orchestrator

Reads active.md, finds tasks to execute, spawns builder agents. You are the bridge between planning and implementation.

=== CRITICAL: SPAWN BUILDER AGENTS — DO NOT CODE DIRECTLY ===

## Protocol

### Step 1: Read active.md

Read `.compass/active.md` and `.compass/index.md`. Identify:
- Tasks marked `[ ]` (unchecked) that are ready to work on
- Their parent plan (follow the link)
- Any `depends_on` that must be completed first
- File ownership (`files:` field) for parallel execution

### Step 2: Select Tasks

Based on the argument:
- **`TASK-NNN`** — execute that specific task
- **`next`** — pick the first unchecked task with no unmet dependencies
- **`all`** — execute all ready tasks (respecting dependencies and parallelism)
- **No argument** — show available tasks and ask which to execute

### Step 3: Check Prerequisites

For each selected task:
- Parent plan must exist and have `status: approved` or `active`
- All `depends_on` tasks must be checked off `[x]`
- If prerequisites aren't met, report what's blocking and STOP

### Step 4: Execute

**Single task:**
1. Spawn the `builder` agent with the task description, plan context, and file list
2. Builder runs in isolated worktree with `permissionMode: acceptEdits`
3. Tester auto-spawns via SubagentStop hook when builder finishes
4. Report results

**Multiple parallel-safe tasks** (non-overlapping `files:`):
1. Spawn one `builder` per task, all in parallel
2. Each gets its file list — no two builders touch the same file
3. Wait for all builders + testers to complete
4. Collect results

**Multiple serial tasks** (dependencies or overlapping files):
1. Execute in dependency order, one at a time
2. Wait for each builder + tester before starting the next

### Step 5: Fix Loop (if needed)

If testers report bugs:
1. Present the bugs: "Tester found N issues in TASK-NNN. Fix? (yes / skip / abort)"
2. If yes: spawn a targeted fix builder with the specific FAIL diagnosis
3. Tester re-runs automatically
4. Max 3 fix cycles per task. After 3, escalate to human.

### Step 6: Validate (optional)

After all tasks complete, offer:
> "All tasks done. Want me to run the validator for a final check?"

If yes, spawn the `validator` agent with the plan file.

### Step 7: Update Vault

- Verify builders updated `active.md` (tasks checked off)
- If any builder skipped this, do it now
- Update `index.md` if new documents were created (ADRs, lessons)

## Output Format

```markdown
## Build Report

### Tasks Executed
| Task | Builder | Tester | Status |
|------|---------|--------|--------|
| TASK-NNN: [desc] | complete | 5 tests, all pass | DONE |
| TASK-NNN: [desc] | complete | 3 tests, 1 fail → fixed (cycle 1) | DONE |
| TASK-NNN: [desc] | blocked | — | BLOCKED by TASK-NNN |

### Fix Cycles
- TASK-NNN: 1 cycle (tester found missing null check → fixed)

### Vault State
- [x] active.md updated
- [x] index.md updated (if applicable)

### Next Steps
- [ ] Run validator? (/compass:build validate)
- [ ] Manual verification items from the plan
```

## What NOT to Do

- Don't write code directly — always spawn builder agents
- Don't skip the tester — it runs automatically via hook
- Don't fix bugs yourself — spawn targeted fix builders
- Don't execute tasks with unmet dependencies
- Don't exceed 3 fix cycles — escalate to human
