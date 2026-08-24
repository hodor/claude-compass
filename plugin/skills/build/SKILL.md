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

3. **Test-first station.** For each selected task whose `files:` include executable source:
   - Spawn the `tester` in pre-build mode, handing it exactly the task body, the plan's acceptance criteria, and the task's automated-verification bullets. No diff exists yet and none is given.
   - Commit the test files it wrote on the working branch: `git commit -m "test(TASK-NNN): failing tests before implementation"`.
   - Run `compass test-checkpoint record TASK-NNN <files> --commit <sha> --red-evidence <path>`, pointing `--red-evidence` at the tester's recorded red-run output.
   - Only then spawn the builder for that task. The checkpoint commit must exist on the working branch before the builder's worktree forks from it, or the fork will not contain it ([[LESSON-subagent-worktrees-fork-stale]]).

   A task whose `files:` carry no executable source runs `compass test-checkpoint record TASK-NNN --not-required` instead of skipping the command outright, so "the station correctly did not apply" and "the station never ran" stay distinguishable later.

   In a parallel phase, every selected task's pre-build pass and checkpoint completes before any builder in that phase spawns. The station is a wave of its own, not interleaved with the build wave it gates.

4. **Execute:**
   - Parallel-safe tasks (non-overlapping `files:`): spawn one builder per task in parallel. Each builder runs in an isolated worktree (`isolation: worktree` in `builder.md`); the Agent SDK returns the worktree path and branch when the agent finishes. Record the (task, branch, worktree) tuple for each. The builder's first action, before writing any code, is to fast-forward its worktree branch to the working branch and confirm the checkpointed test files from step 3 exist; it halts loudly and reports if they do not. Once a builder finishes, spawn the `tester` in post-build mode against its diff.
   - Serial tasks: spawn one at a time in dependency order, wait for the builder and its post-build tester before the next.

5. **Fix loop.** If testers report bugs, ask: "Tester found N issues in TASK-NNN. Fix? (yes / skip / abort)". On yes, spawn a targeted fix builder against the same branch with the bug diagnosis (not the full task). Then run `compass test-checkpoint verify TASK-NNN --tree <worktree path> --expect-checkpoint` against that builder's worktree - without `--tree` the check reads the orchestrator's own checkout, where nothing in the fix loop is changing, and stays silent through the entire cycle. A `modified` result is surfaced to the human before the cycle continues, naming the changed assertion, rather than folded silently into the next one. Spawn the tester in post-build mode again to confirm the fix. Green at fix-loop entry and at every cycle after means **no failures outside `compass test-checkpoint open-ids`** - the checkpointed tests of tasks not yet landed are expected reds, not new bugs. Max 3 cycles per task, then escalate.

6. **Merge branches back.** Once all builders + testers for a phase pass - pass meaning green as defined above, no failures outside `compass test-checkpoint open-ids` - merge each task branch into the orchestrator's branch in `depends_on` order:
   ```bash
   git merge --no-ff <task-branch> -m "Merge TASK-NNN: <description>"
   ```
   After each merge, spawn the `tester` agent on the merged state to catch cross-task integration issues, then run the mandatory post-merge `compass test-checkpoint verify TASK-NNN` against the merged branch for that task - the only check that sees what actually landed rather than what a worktree contained mid-build. Do not run tests yourself; the tester handles all test execution. If a merge conflicts, halt and present the list of remaining branches to the human - planner enforces file exclusivity so conflicts mean either a planner bug or a builder that wrote outside its `files:`.

7. **Phase pause.** When all tasks in a phase are done and the post-merge tester and post-merge verify both report passing, run 7a, then 7b, then 7d, then 7c in that order:

   **7a. Assemble phase reports from SubagentStop captures.** The SubagentStop hook has already captured each subagent's final message to `.compass/tmp/subagent-captures/<timestamp>_<agent_type>.md`. For this phase:

   1. List captures created since this phase started (orchestrator knows the phase start time from when it began Phase N).
   2. For each capture, match the agent_type and the spawn history to a task. Rename and move into `.compass/tmp/phase-reports/<phase-id>/`:
      - builder capture → `task-<NNN>-build.md`
      - tester capture → `task-<NNN>-test.md`
      - debug capture → `task-<NNN>-debug.md`
      - validator capture → `validator.md`
   3. Write `phase-summary.yaml` with structured signals: `phase_id`, `plan`, `tasks` list, `completed_at`, `fix_loop_cycles` per task, `validator_deviations`, `debug_invocations`, `stop_and_report_events`, `plan_revisions`. See `extract-lessons/SKILL.md` for the exact schema.

   Only `phase-summary.yaml` is original content the orchestrator writes; the per-task reports are just renames of hook-captured files. This is the [[LESSON-no-agent-bookkeeping]] principle applied to subagent reports.

   **7b. Invoke extract-lessons.** Run `compass capture-check --hook` so it detects the phase-summary.yaml just written and opens a `.compass/tmp/capture-opportunities/OPP-<UTC>/` directory for it - the same detection the Stop hook runs on every turn. The hook spawns the detached capture worker, which runs the pass off-conversation and records its result in the capture ledger. Do not run the pass in this session and do not narrate it; at the pause, read the ledger's one `extracted:` line for the phase and include it in the report. If the ledger shows the worker failed, the quiet channel has already handed the pass to a subagent.

   **7d. Elaborate the next wave.** For a plan written in the rolling-wave format (a plan carrying a `## Later (intent only)` section), this step runs after 7a's phase reports and 7b's lessons, and before 7c's pause. In `all-phases` mode it still runs when 7c's pause is skipped - it is the wave-promotion step itself, not the human checkpoint - and it completes before the next phase's step 3, so no tester is ever handed a task with no verification bullets to write against. For a plan with no `## Later` section, 7d is a no-op.

   Read the wave's verified outcomes: the phase reports 7a just assembled, `compass coverage` and `compass lesson-coverage`'s live output, and the recorded answer of any `kind: prototype` task in the phase - a prototype's deliverable is an answer rather than shipped code, and that answer lives in its own phase report (SPEC-015 D-02), not in the plan until this step transcribes it.

   Promote the next coherent set of intent lines into full task blocks. Land them under a new `### Wave N (detailed)` heading placed under `## Phases`, above the `## Later` heading - a level-3 heading does not close a Later region, so it is placement relative to the `## Later` boundary, not heading level, that keeps a promoted block detailed. Delete each consumed intent line from the Later region rather than editing it where it sits, and move its task id from `backlog.md` to `active.md` so the build flow's task selection can see it.

   Append a `## Wave N elaborated` section recording, for every promoted line, either what changed and which verified outcome changed it, or literally "unchanged - intent held". A promoted line with no entry is a defect, not a shortcut. Quote superseded intent lines only inside a fence or backtick span - unfenced it still claims nothing, but it reads as a live, unclaimed task to a human, and to any tool that scans for the task-line grammar.

   Present the delta (what was learned, what the next wave is) to the human as part of 7c's pause; do not re-approve the plan.

   **Editing discipline**, from a recorded incident of this kind: anchor structural edits (heading insertions, section moves, deletions) on whole heading lines, never on substring matches - a backticked mention of a heading in prose is not the heading, and a substring replace once spliced a plan's own Goal paragraph before its gates caught it.

   **7c. Pause for human.** Present manual verification items from the plan, plus the extract-lessons summary and 7d's elaboration delta if it ran. Wait for human confirmation before proceeding to next phase.

   Skip the pause (but NOT 7a, 7b or 7d) in `all-phases` mode; pause only after the last phase. Reports, extraction and elaboration still run between phases so lessons and wave promotion happen incrementally.

8. **Validate (optional).** Offer to spawn the validator with the plan file.

9. **Vault.** Verify builders updated `active.md` and `index.md`. If any skipped, do it now. The SDK auto-cleans worktrees once their branches are merged.

## Report

```markdown
## Build Report

| Task | Red Evidence | Builder | Tester | Status |
|------|--------------|---------|--------|--------|
| TASK-NNN: [desc] | recorded | complete | 5 tests pass | DONE |
| TASK-NNN: [desc] | not-required | complete | 3 tests, 1 fail → fixed (cycle 1) | DONE |
| TASK-NNN: [desc] | - | blocked | - | BLOCKED by TASK-NNN |

Next: run validator? Manual verification items from the plan?
```
