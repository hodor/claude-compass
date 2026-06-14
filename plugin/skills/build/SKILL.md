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
- `all-phases` - same as `all` but skip the per-phase pause for manual verification. Run end-to-end, pause only after the last phase.
- (no argument) - list available tasks and ask which

## Protocol

1. **Read** `.compass/active.md` and `.compass/index.md`. Identify unchecked tasks, their parent plan, `depends_on` chains, and `files:` ownership.

2. **Select** tasks per the argument. Prerequisites: parent plan must be `approved` or `active`; `depends_on` tasks must be `[x]`. If blocked, report and stop.

3. **Execute:**
   - Parallel-safe tasks (non-overlapping `files:`): spawn one builder per task in parallel. Each builder runs in an isolated worktree (`isolation: worktree` in `builder.md`); the Agent SDK returns the worktree path and branch when the agent finishes. Record the (task, branch, worktree) tuple for each. The `tester` auto-spawns after each builder via the `SubagentStop` hook.
   - Serial tasks: spawn one at a time in dependency order, wait for builder + auto-spawned tester before the next.

4. **Fix loop.** If testers report bugs, ask: "Tester found N issues in TASK-NNN. Fix? (yes / skip / abort)". On yes, spawn a targeted fix builder against the same branch with the bug diagnosis (not the full task). The tester re-runs automatically. Max 3 cycles per task, then escalate.

5. **Merge branches back.** Once all builders + testers for a phase pass, merge each task branch into the orchestrator's branch in `depends_on` order:
   ```bash
   git merge --no-ff <task-branch> -m "Merge TASK-NNN: <description>"
   ```
   After each merge, spawn the `tester` agent on the merged state to catch cross-task integration issues. Do not run tests yourself; the tester handles all test execution. If a merge conflicts, halt and present the list of remaining branches to the human - planner enforces file exclusivity so conflicts mean either a planner bug or a builder that wrote outside its `files:`.

6. **Phase pause.** When all tasks in a phase are done and the post-merge tester reports passing:

   **6a. Assemble phase reports from SubagentStop captures.** The SubagentStop hook has already captured each subagent's final message to `.compass/tmp/subagent-captures/<timestamp>_<agent_type>.md`. For this phase:

   1. List captures created since this phase started (orchestrator knows the phase start time from when it began Phase N).
   2. For each capture, match the agent_type and the spawn history to a task. Rename and move into `.compass/tmp/phase-reports/<phase-id>/`:
      - builder capture → `task-<NNN>-build.md`
      - tester capture → `task-<NNN>-test.md`
      - debug capture → `task-<NNN>-debug.md`
      - validator capture → `validator.md`
   3. Write `phase-summary.yaml` with structured signals: `phase_id`, `plan`, `tasks` list, `completed_at`, `fix_loop_cycles` per task, `validator_deviations`, `debug_invocations`, `stop_and_report_events`, `plan_revisions`. See `extract-lessons/SKILL.md` for the exact schema.

   Only `phase-summary.yaml` is original content the orchestrator writes; the per-task reports are just renames of hook-captured files. This is the [[LESSON-no-agent-bookkeeping]] principle applied to subagent reports.

   **6b. Invoke extract-lessons.** Run the `extract-lessons` skill with the phase report directory as argument. It checks binary triggers, applies the anti-list, hands survivors to `lesson-write`. Surface its summary line to the human as part of the pause.

   **6c. Pause for human.** Present manual verification items from the plan, plus the extract-lessons summary. Wait for human confirmation before proceeding to next phase.

   Skip the pause (but NOT 6a and 6b) in `all-phases` mode; pause only after the last phase. Reports and extraction still run between phases so lessons are captured incrementally.

7. **Validate (optional).** Offer to spawn the validator with the plan file.

8. **Vault.** Verify builders updated `active.md` and `index.md`. If any skipped, do it now. The SDK auto-cleans worktrees once their branches are merged.

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
