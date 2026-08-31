---
name: extract-lessons
description: Retrospectively extract lessons from a capture opportunity. Reads opportunity.json from .compass/tmp/capture-opportunities/OPP-<UTC>/, checks the binary triggers against the opportunity's kind and evidence, applies the anti-list, hands survivors to lesson-write, and may revise or archive a lesson through lesson-write when opportunity evidence contradicts it. Writes an audit log of every candidate considered (aged into archive/logs/ after 30 days) and closes the opportunity via `compass capture-close`. Never invoked directly by humans.
version: 2.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
when_to_use: "Invoked against a capture opportunity directory - most often the one named in the Stop hook's block decision. /compass:build's phase-completion path builds the same opportunity shape from its phase report. Not user-facing."
---

# Extract Lessons

Retrospective lesson capture at a capture opportunity. No introspection prompts. The triggers are binary; the anti-list is the filter; `lesson-write` is the writer.

The pass runs in a SPAWNED SUBAGENT, never in the main conversation's context: the evidence reading and candidate judgment cost thousands of tokens that belong in a disposable context, and the durable record is the extraction log plus the capture-log row, not conversation text. The subagent's entire report back is step 9's one `extracted:` line; the orchestrator relays that line and nothing else. Narrating candidates, verdicts, or rationale into the conversation is context pollution - the logs hold all of it.

## Inputs

This skill takes one argument: the path to a capture opportunity directory, e.g. `.compass/tmp/capture-opportunities/OPP-20260805T142200123456Z`. If no argument is given, it reads the most recently modified `.compass/tmp/capture-opportunities/*/opportunity.json` whose `outcome` field is still `null`.

Directory contents:

```
.compass/tmp/capture-opportunities/<opp-id>/
└── opportunity.json        # kind, fired triggers, evidence paths, outcome
```

`opportunity.json` fields:

```json
{
  "id": "OPP-20260805T142200123456Z",
  "kind": "phase",
  "triggers": ["phase-summary"],
  "evidence": ["tmp/phase-reports/PHASE-001-plan-001"],
  "opened_at": "2026-08-05T14:22:00.123456Z",
  "closed_at": null,
  "outcome": null
}
```

`kind` is one of `phase`, `signal`, or `interval`. `triggers` names the signal kinds that made the opportunity due. `evidence` is a list of vault-relative paths the extractor reads; which paths and how many depends on `kind`:

- **`phase`** - one path, a `.compass/tmp/phase-reports/<phase-id>/` directory. Read `phase-summary.yaml` from it exactly as before, plus the per-task report files it names.
- **`signal`** - one or more paths: a `tmp/subagent-captures/` file (a validator or debug subagent's captured report, or an agent's `capture-note` observation) and/or a `handoffs/` path when a `handoff-written` trigger fired.
- **`interval`** - one or more paths recorded in the window that reached the turn interval: `tmp/subagent-captures/` files and/or whatever vault artifact a `vault-write` trigger names.

If `opportunity.json` does not exist or is malformed, halt and write a single-line extraction log entry: `error: opportunity.json missing or malformed at <path>`. Do not improvise.

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

## Protocol

### 1. Mutex check

If `opportunity.json`'s `outcome` field is already set (not `null`), exit silently - a prior pass already closed this opportunity. For a `phase` kind opportunity, also check `.compass/tmp/phase-reports/<phase-id>/.processed`: its presence is the same backstop collision this check has always guarded against, from the legacy path where the phase-report directory carried its own mutex before opportunities existed.

### 2. Read the opportunity

Parse `opportunity.json` for `kind`, `triggers`, and `evidence`. For a `phase` kind, also read `phase-summary.yaml` from the evidence directory (see structure above). For `signal` and `interval` kinds, `triggers` already names the fired signal kinds directly - there is no separate structured signal file to parse.

### 3. Binary trigger check

For a `phase` kind opportunity, check each of these against `phase-summary.yaml`. If any fires, set `triggered: true`. Otherwise `triggered: false`.

- **fix-loop >=2:** any task in `fix_loop_cycles` has value >= 2.
- **validator Deviation (problem):** any entry in `validator_deviations` has `kind: problem`.
- **debug invoked:** `debug_invocations` is non-empty.
- **STOP-and-report:** `stop_and_report_events` is non-empty.
- **plan revised:** `plan_revisions` is non-empty.

For a `signal` or `interval` kind opportunity, `triggered` is always `true`: `compass capture-check` only opens one of these when its own arithmetic already found a due condition (a strong signal, or the interval reached with at least one signal in the window), so the opportunity's existence is the trigger. The widened binary trigger set this generalizes to:

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

If `triggered: false` (only possible for a `phase` kind opportunity whose `phase-summary.yaml` carries no fired condition), there are zero candidates: proceed straight to step 7's "no candidates" log entry, then steps 8 and 9.

### 4. Gather candidate findings

For each fired trigger, read the corresponding evidence from the table above:

- fix-loop >=2 → scan the looping task's build report for what was unexpected.
- validator deviation (phase) → scan `validator.md`'s Deviation (problem) entries for what broke the plan-vs-reality match. validator deviation (signal) → scan the named subagent-capture file the same way.
- debug invoked (phase) → the "Root Cause" + "Remediation" sections of the task's debug report are candidate sources. debug invoked (signal) → the same sections in the named subagent-capture file.
- STOP-and-report → the "Found" vs "Expected" mismatch in the build report carrying the event is a candidate.
- plan revised → the revision rationale in the plan diff or revision note is a candidate.
- handoff written → what the handoff records as open work or a surprising finding is a candidate source.
- agent noted → the note body is one candidate as stated: the agent already judged it worth remembering, so the anti-list and dedup in steps 5-6 are the only filters. A note that names the incident but not the rule still yields a candidate; state the rule the incident implies.
- interval reached with signal(s) → read every evidence file in the window. An interval opportunity fires on volume, not on one strong signal, so a finding only becomes a candidate if it would independently justify a lesson - the anti-list in step 5 is the filter that keeps this permissive read from flooding the catalog.

A candidate is a discrete finding: one rule, one why. Do not group multiple findings into one. If the evidence has 3 findings, emit 3 candidates.

For each candidate, prepare a payload draft:
- Tentative summary (<=120 chars)
- Tentative body (<=5 lines)
- Tentative category (process likely - extraction lives in the build pipeline)
- Tentative area (read from the parent plan's `area` frontmatter when the evidence traces to one; otherwise from the vault's active plan or spec)
- Tentative tags (extract from the task description and the finding)

### 4a. Contradiction check

For each candidate, and independently for evidence that produced no candidate of its own, check whether it shows an existing active lesson's claim to be wrong: grep `.compass/meta/lessons-catalog.yaml` for rows whose `area`/`tags` overlap the finding, and read any that match. Two outcomes:

- **Revise** - the lesson's rule still holds in general, but this evidence shows it needs a correction or a narrower condition than currently written. Prepare a lesson-write payload naming the correction; `source` records `extract-lessons:contradiction-revise`. Handing this to lesson-write in step 6 the normal way is enough - the tag/area overlap that flagged the contradiction is the same overlap lesson-write's own dedup judgment (its step 3) uses to route the call to its refinement branch (4b), which edits the matched lesson's body in place.
- **Archive** - the evidence flatly falsifies the lesson: the rule it states no longer holds, or never held the way it was captured. Prepare a payload with `intent: archive` and `target: <lesson-filename>`; `source` records `extract-lessons:contradiction-archive`, and the body states plainly that the lesson is superseded by the falsifying evidence. lesson-write's step 4d performs the retirement.

Route both through lesson-write in step 6, exactly like any other candidate - the single-writer rule applies to a contradiction resolution as much as a new candidate; extract-lessons never edits a lesson file directly. A candidate matched here is not also submitted as a fresh new-lesson candidate. Count a revise outcome under `revised` and an archive outcome under `archived` in step 9's return line, based on which branch produced the call, not solely on lesson-write's return string: an archive request does surface distinctly as lesson-write's own `archived: <filename>` return, but a revise still returns the same `refined: <filename>` string an ordinary non-contradiction refinement would, so revise must be counted from the branch that produced the call.

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
- Environment-dependent failures
- Negative tool claims that would harden into standing refusals
- Unresolved or untested "recommended approaches" recorded as if validated

Then check the memory of prior passes - by SUBJECT, never by filename, since a re-drafted candidate arrives reworded: grep the audit logs (`tmp/extraction-log-*.md`, `archive/logs/`) and `archive/lessons/` for the candidate's subject. A candidate an earlier pass rejected or judged already-documented is rejected again, citing that pass's log line, unless the new evidence states why the old judgment no longer holds. Never write a lesson only to self-archive it in the same pass - a candidate that would arrive archived is a rejection.

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

For a `signal` or `interval` kind opportunity, use `## Opportunity <opp-id> (<kind>) - <timestamp>` in place of the `## Phase <phase-id> - <plan-id> - <timestamp>` header, and extend the `### Triggers` checklist with whichever of these fired:

- validator-finished / debug-finished (signal): yes/no [(which subagent capture)]
- handoff-written (signal): yes/no
- interval reached with signal(s): yes/no [(trigger kinds present)]

A contradiction candidate's entry uses the same `### Candidates` format as any other; its `**Outcome:**` line states `revised: LESSON-foo.md` or `archived: LESSON-foo.md`.

### 8. Mutex marker

Write `.compass/tmp/phase-reports/<phase-id>/.processed` (empty file) so the backstop path skips this phase.

For a `signal` or `interval` kind opportunity, there is no phase-report directory to mark; step 9's `compass capture-close` call is what closes the opportunity and stops a later pass from picking it up again.

### 9. Report to caller

Return one structured line to the calling skill (build or the Stop hook):

```
extracted: opportunity=<opp-id> kind=<phase|signal|interval> triggered=<bool> candidates=<N> created=<C> recurrence=<U> refined=<F> revised=<V> archived=<A> rejected=<R> errors=<E>
```

Where:
- `created` = new lessons written via lesson-write branch 4c
- `recurrence` = existing lessons score-bumped via branch 4a (includes escalations)
- `refined` = existing lessons body-edited via branch 4b, for a candidate that was not a contradiction
- `revised` = existing lessons body-edited via the 4a contradiction check's revise branch
- `archived` = existing lessons retired via the 4a contradiction check's archive branch
- `rejected` = candidates matched by the anti-list
- `errors` = candidates that returned `body_too_long` or other errors

Then close the opportunity so nothing re-opens it:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" capture-close <opp-id> --outcome fired \
  --candidates <N> --written <C+F+V> --recurrence <U> --rejected <R> \
  --revised <V> --archived <A> --errors <E>
```

`--written` is `created + refined + revised` - every candidate that produced or updated active lesson content. `--archived` stays out of `--written`: retiring a lesson is not adding or updating one. Omit a count flag entirely when its value is `0` and no candidate of that kind was considered at all (e.g. an opportunity with no contradiction candidates omits `--revised` and `--archived`) - `capture-close` records only what it is given, so an omitted flag and an explicit `0` are different rows. This call replaces the bare mutex-marker-only ending the legacy phase path used before opportunities existed; for a `phase` kind opportunity, step 8's `.processed` marker is written first, same as before, and this call closes the opportunity on top of it.

## Failure modes worth naming

- Asking the model "did anything surprise you?" The triggers are binary; do not introspect.
- Writing lessons without going through `lesson-write`. The single writer enforces dedup, anti-list, and the cap.
- Skipping the extraction log when no lesson is written. The log records `triggered: false` or `all rejected`; absence of log = bug.
- Inventing a candidate to justify the run. If the anti-list rejects everything, the right number of lessons is zero.
- Forgetting the `.processed` marker on a `phase` kind opportunity. The Stop hook backstop will re-extract the same phase on the next turn.
- Treating the trigger list as the candidate list. A trigger fires the run; candidates come from reading the evidence.
- Inventing a contradiction to justify revising or archiving a lesson. The 4a check runs against real tag/area overlap and real falsifying evidence, same discipline as any other candidate.
- Skipping `compass capture-close`. Without it the opportunity never closes, and `capture-stats` cannot tell "reviewed and found nothing" apart from "never ran."
