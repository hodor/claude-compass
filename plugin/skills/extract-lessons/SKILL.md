---
name: extract-lessons
description: Retrospectively extract lessons at the end of a phase. Reads phase-summary.yaml and per-task reports from .compass/tmp/phase-reports/, checks 5 binary triggers, applies the anti-list, hands survivors to lesson-write. Writes an audit log of every candidate considered (kept 30 days). Invoked by /compass:build step 6 and by the Stop hook backstop. Never invoked directly by humans.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit]
when_to_use: "Invoked by /compass:build at the phase pause, or by the Stop hook backstop when a phase-summary.yaml exists without a .processed marker. Not user-facing."
---

# Extract Lessons

Retrospective lesson capture at phase boundary. No introspection prompts. The triggers are binary; the anti-list is the filter; `lesson-write` is the writer.

## Inputs

This skill takes one argument: the path to a phase report directory, e.g. `.compass/tmp/phase-reports/PHASE-001-plan-001`. If no argument is given, it scans `.compass/tmp/phase-reports/` for the most recently modified directory that lacks a `.processed` marker.

Expected directory contents (written by `/compass:build` before invoking this skill):

```
.compass/tmp/phase-reports/<phase-id>/
├── phase-summary.yaml      # structured signal for trigger check
├── task-<NNN>-build.md     # per-task builder reports
├── task-<NNN>-test.md      # per-task tester reports
├── task-<NNN>-debug.md     # only if debug agent was invoked for that task
└── validator.md            # only if validator ran
```

## Phase-summary.yaml structure

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

## Protocol

### 1. Mutex check

If `.compass/tmp/phase-reports/<phase-id>/.processed` exists, exit silently. The phase has already been processed; this is the backstop colliding with the primary path.

### 2. Read phase-summary.yaml

Parse the structured signal.

### 3. Binary trigger check

Check each of these. If any fires, set `triggered: true`. Otherwise exit (after writing the log).

- **fix-loop >=2:** any task in `fix_loop_cycles` has value >= 2.
- **validator Deviation (problem):** any entry in `validator_deviations` has `kind: problem`.
- **debug invoked:** `debug_invocations` is non-empty.
- **STOP-and-report:** `stop_and_report_events` is non-empty.
- **plan revised:** `plan_revisions` is non-empty.

If `triggered: false`: write the extraction log entry `triggered: false - no candidates considered`, write the `.processed` marker, exit.

### 4. Gather candidate findings

For each fired trigger, read the corresponding report files:

- fix-loop >=2 → read `task-<NNN>-build.md` for the task that looped. Scan for what was unexpected.
- validator deviation → read `validator.md`. Scan the Deviation (problem) entries for what broke the plan-vs-reality match.
- debug invoked → read `task-<NNN>-debug.md`. The "Root Cause" + "Remediation" sections are candidate sources.
- STOP-and-report → read the build report with the STOP event. The "Found" vs "Expected" mismatch is a candidate.
- plan revised → read the plan diff or revision note. The revision rationale is a candidate.

A candidate is a discrete finding: one rule, one why. Do not group multiple findings into one. If the report has 3 findings, emit 3 candidates.

For each candidate, prepare a payload draft:
- Tentative summary (<=120 chars)
- Tentative body (<=5 lines)
- Tentative category (process likely - extraction lives in the build pipeline)
- Tentative area (read from the parent plan's `area` frontmatter)
- Tentative tags (extract from the task description and the finding)

### 5. Anti-list filter

For each candidate, apply the anti-list (defined in `lesson-write/SKILL.md`). Reject candidates that fall in any bucket:

- Code patterns, conventions, architecture, file paths, project structure
- Git history or who-changed-what
- Debugging recipes whose fix is in the code
- Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md
- Standard patterns from framework or library docs
- Personal style preferences
- Things obvious once you know the technology
- Ephemeral session state

For each candidate, record the anti-list outcome: passed, or matched bucket `<name>`.

### 6. Hand survivors to lesson-write

For each candidate that passed the anti-list, call `lesson-write` with its payload. Record the return value.

### 7. Write the extraction log

To `.compass/tmp/extraction-log-YYYY-MM-DD.md` (one file per day; append if it already exists).

Format:

```markdown
## Phase <phase-id> - <plan-id> - <timestamp>

### Triggers
- fix-loop >=2: yes/no [(which tasks)]
- validator Deviation (problem): yes/no [(count)]
- debug invoked: yes/no [(which tasks)]
- STOP-and-report: yes/no
- plan revised: yes/no

### Candidates
1. **Source:** task-<NNN>-debug.md
   **Finding:** <one line>
   **Anti-list:** passed
   **Outcome:** `lesson-write` returned `created: LESSON-foo.md`

2. **Source:** task-<MMM>-build.md
   **Finding:** <one line>
   **Anti-list:** matched bucket "Debugging recipes whose fix is in the code"
   **Outcome:** rejected

### Summary
Candidates: <N> | Written: <W> | Rejected: <R> | Errors: <E>
```

If no candidates were considered (triggered: false), write a single short entry:

```markdown
## Phase <phase-id> - <timestamp>

triggered: false (no binary triggers fired)
```

### 8. Mutex marker

Write `.compass/tmp/phase-reports/<phase-id>/.processed` (empty file) so the backstop path skips this phase.

### 9. Report to caller

Return one structured line to the calling skill (build or the Stop hook):

```
extracted: phase=<id> triggered=<bool> candidates=<N> created=<C> recurrence=<U> refined=<F> rejected=<R> errors=<E>
```

Where:
- `created` = new lessons written via lesson-write branch 4c
- `recurrence` = existing lessons score-bumped via branch 4a (includes escalations)
- `refined` = existing lessons body-edited via branch 4b
- `rejected` = candidates matched by the anti-list
- `errors` = candidates that returned `body_too_long` or other errors

## Failure modes worth naming

- Asking the model "did anything surprise you?" The triggers are binary; do not introspect.
- Writing lessons without going through `lesson-write`. The single writer enforces dedup, anti-list, and the cap.
- Skipping the extraction log when no lesson is written. The log records `triggered: false` or `all rejected`; absence of log = bug.
- Inventing a candidate to justify the run. If the anti-list rejects everything, the right number of lessons is zero.
- Forgetting the `.processed` marker. The Stop hook will re-extract the same phase on the next turn.
- Treating the trigger list as the candidate list. A trigger fires the run; candidates come from reading the reports.
