# Extraction log format

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

For a `signal` or `interval` kind opportunity, use `## Opportunity <opp-id> (<kind>) - <timestamp>` in place of the `## Phase <phase-id> - <plan-id> - <timestamp>` header, and extend the `### Triggers` checklist with whichever of these fired:

- validator-finished / debug-finished (signal): yes/no [(which subagent capture)]
- handoff-written (signal): yes/no
- interval reached with signal(s): yes/no [(trigger kinds present)]

A contradiction candidate's entry uses the same `### Candidates` format as any other; its `**Outcome:**` line states `revised: LESSON-foo.md` or `archived: LESSON-foo.md`.
