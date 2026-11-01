# Binary trigger check

## Phase kind

For a `phase` kind opportunity, check each of these against `phase-summary.yaml`. If any fires, set `triggered: true`. Otherwise `triggered: false`.

- **fix-loop >=2:** any task in `fix_loop_cycles` has value >= 2.
- **validator Deviation (problem):** any entry in `validator_deviations` has `kind: problem`.
- **debug invoked:** `debug_invocations` is non-empty.
- **STOP-and-report:** `stop_and_report_events` is non-empty.
- **plan revised:** `plan_revisions` is non-empty.

## All kinds

The widened binary trigger set, with the evidence each trigger points the extractor at:

| Trigger | Kind | Evidence it points the extractor at |
|---|---|---|
| fix-loop >=2 | phase | `task-<NNN>-build.md` for the looping task |
| validator deviation | phase, signal (`validator-finished`) | `validator.md`, or the named `tmp/subagent-captures/` file |
| debug invoked | phase, signal (`debug-finished`) | `task-<NNN>-debug.md`, or the named `tmp/subagent-captures/` file |
| STOP-and-report | phase | the build report carrying the STOP event |
| plan revised | phase | the plan diff or revision note |
| handoff written | signal (`handoff-written`) | the named `handoffs/` file |
| agent noted | signal (`agent-noted`) | the named `tmp/subagent-captures/*_note.md` file, written by `compass capture-note` |
| interval reached with signal(s) | interval (`vault-write`, `builder-finished`, `subagent-finished`) | every evidence path in the window |
