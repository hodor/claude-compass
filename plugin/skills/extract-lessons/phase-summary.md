## Phase-summary.yaml structure

Read from the phase-report directory named in a `phase` kind opportunity's `evidence` list:

```yaml
phase_id: PHASE-001-plan-001
plan: PLAN-001-lessons-and-index-implementation
tasks: [TASK-001, TASK-002, TASK-003]
completed_at: 2026-05-24T14:30:00Z
fix_loop_cycles:
  TASK-001: 0
  TASK-002: 2     # triggered: >=2
  TASK-003: 0
validator_deviations:
  - {task: TASK-002, kind: problem, description: "API contract mismatch"}
debug_invocations: [TASK-001]
stop_and_report_events: []
plan_revisions: []
```

If `phase-summary.yaml` does not exist or is malformed, halt and write a single-line extraction log entry: `error: phase-summary.yaml missing or malformed at <path>`. Do not improvise.
