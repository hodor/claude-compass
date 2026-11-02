---
name: extract-lessons
description: Retrospectively extract lessons from a capture opportunity. Reads opportunity.json from .compass/tmp/capture-opportunities/OPP-<UTC>/, checks the binary triggers against its kind and evidence, applies the anti-list, hands survivors to lesson-write (also to revise or archive a lesson the evidence contradicts), writes an audit log of every candidate (aged into archive/logs/ after 30 days) and closes the opportunity via `compass capture-close`. Never invoked directly by humans.
version: 2.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
when_to_use: "Invoked against a capture opportunity directory - most often the one named in the Stop hook's block decision. /compass:build's phase-completion path builds the same opportunity shape from its phase report. Not user-facing."
---

# Extract Lessons

Retrospective lesson capture at a capture opportunity. No introspection prompts. The triggers are binary; the anti-list is the filter; `lesson-write` is the writer.

This skill is consumed as a file: the agent reads this document and follows its steps in place. A Skill-tool invocation hangs when the caller is a subagent or a headless worker, so no prompt ever routes here through the Skill tool.

The pass runs in a SPAWNED SUBAGENT, never in the main conversation's context. The subagent's entire report back is step 9's one `extracted:` line; the orchestrator relays that line and nothing else. Why the pass is isolated and what the report excludes: `report-and-close.md` in this skill's folder, section "Why the pass runs in a subagent".

## Inputs

This skill takes one argument: the path to a capture opportunity directory, e.g. `.compass/tmp/capture-opportunities/OPP-20260805T142200123456Z`. If no argument is given, it reads the most recently modified `.compass/tmp/capture-opportunities/*/opportunity.json` whose `outcome` field is still `null`.

The directory holds `opportunity.json` (`kind`, fired `triggers`, `evidence` paths, `outcome`). Its fields and which evidence paths each `kind` (`phase`, `signal`, `interval`) carries: `opportunity-format.md` in this skill's folder; read it before step 2.

If `opportunity.json` does not exist or is malformed, halt and write a single-line extraction log entry: `error: opportunity.json missing or malformed at <path>`. Do not improvise.

## Phase-summary.yaml structure

For a `phase` kind opportunity, read `phase-summary.yaml` from the phase-report directory in `evidence`; its schema and the halt rule when it is missing or malformed are in `phase-summary.md`, in this skill's folder.

## Protocol

### 1. Mutex check

If `opportunity.json`'s `outcome` field is already set (not `null`), exit silently - a prior pass already closed this opportunity. The extra `.processed` check for a `phase` kind opportunity: `phase-marker.md` in this skill's folder; read it before this step.

### 2. Read the opportunity

Parse `opportunity.json` for `kind`, `triggers`, and `evidence`. For a `phase` kind, also read `phase-summary.yaml` from the evidence directory (see structure above). For `signal` and `interval` kinds, `triggers` already names the fired signal kinds directly - there is no separate structured signal file to parse.

### 3. Binary trigger check

For a `phase` kind opportunity, the five phase triggers (checked against `phase-summary.yaml`; any one firing sets `triggered: true`, none sets `triggered: false`) and the table of every trigger with its evidence are in `triggers.md`, in this skill's folder; read it before this step.

For a `signal` or `interval` kind opportunity, `triggered` is always `true`: `compass capture-check` only opens one of these when its own arithmetic already found a due condition (a strong signal, or the interval reached with at least one signal in the window), so the opportunity's existence is the trigger.

If `triggered: false` (only possible for a `phase` kind opportunity whose `phase-summary.yaml` carries no fired condition), there are zero candidates: proceed straight to step 7's "no candidates" log entry, then steps 8 and 9.

### 4. Gather candidate findings

For each fired trigger, read the evidence the table in `triggers.md` names. What to scan for under each trigger (fix-loop, validator deviation, debug, STOP-and-report, plan revised, handoff, agent noted, interval): `candidate-gathering.md` in this skill's folder; read it before gathering.

A candidate is a discrete finding: one rule, one why. Do not group multiple findings into one. If the evidence has 3 findings, emit 3 candidates.

The payload draft prepared for each candidate (summary, body, category, area, tags): `candidate-gathering.md`, section "Payload draft".

### 4a. Contradiction check

For each candidate, and for evidence that produced none, check whether it shows an existing active lesson to be wrong, and route a revise or archive through lesson-write. The procedure and the rule for counting `revised` and `archived`: `contradiction-check.md` in this skill's folder; read it before this step.

### 5. Anti-list filter

For each candidate, apply the anti-list (the buckets are listed once, in the "Anti-list" section of `lesson-write/SKILL.md`; read that section before this step). Reject candidates that fall in any bucket.

Then check the memory of prior passes: `prior-passes.md` in this skill's folder; read it before this step.

For each candidate, record the anti-list outcome: passed, or matched bucket `<name>`.

### 6. Hand survivors to lesson-write

For each candidate that passed the anti-list, read `.claude/skills/lesson-write/SKILL.md` and follow its steps with the candidate's payload - in place, never through the Skill tool. Record the return value.

### 7. Write the extraction log

Write the extraction log to `.compass/tmp/extraction-log-YYYY-MM-DD.md`. Its format (headers, triggers checklist, candidate entries, the no-candidates entry, signal and interval headers, contradiction outcomes) is in `extraction-log.md` in this skill's folder; read it before writing.

### 8. Mutex marker

For a `phase` kind opportunity, write the `.processed` marker so the backstop path skips this phase; a `signal` or `interval` kind has none and is closed by step 9. Details: `phase-marker.md` in this skill's folder; read it before this step.

### 9. Report to caller

Return one structured line to the calling skill (build or the Stop hook):

```
extracted: opportunity=<opp-id> kind=<phase|signal|interval> triggered=<bool> candidates=<N> created=<C> recurrence=<U> refined=<F> revised=<V> archived=<A> rejected=<R> errors=<E>
```

What each count means and the `compass capture-close` call that closes the opportunity so nothing re-opens it: `report-and-close.md` in this skill's folder; read it before reporting.

## Failure modes worth naming

The failure modes to avoid (introspection prompts, bypassing `lesson-write`, a missing extraction log, invented candidates, a missing `.processed` marker, a missing `compass capture-close`): `failure-modes.md` in this skill's folder; read it before step 3.
