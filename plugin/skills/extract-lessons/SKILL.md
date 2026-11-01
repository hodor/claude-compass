---
name: extract-lessons
description: Retrospectively extract lessons from a capture opportunity. Reads opportunity.json from .compass/tmp/capture-opportunities/OPP-<UTC>/, checks the binary triggers against the opportunity's kind and evidence, applies the anti-list, hands survivors to lesson-write, and may revise or archive a lesson through lesson-write when opportunity evidence contradicts it. Writes an audit log of every candidate considered (aged into archive/logs/ after 30 days) and closes the opportunity via `compass capture-close`. Never invoked directly by humans.
version: 2.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
when_to_use: "Invoked against a capture opportunity directory - most often the one named in the Stop hook's block decision. /compass:build's phase-completion path builds the same opportunity shape from its phase report. Not user-facing."
---

# Extract Lessons

Retrospective lesson capture at a capture opportunity. No introspection prompts. The triggers are binary; the anti-list is the filter; `lesson-write` is the writer.

This skill is consumed as a file: the agent reads this document and follows its steps in place. A Skill-tool invocation hangs when the caller is a subagent or a headless worker, so no prompt ever routes here through the Skill tool.

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

For a `phase` kind opportunity, read `phase-summary.yaml` from the phase-report directory in `evidence`; its schema and the halt rule when it is missing or malformed are in `phase-summary.md`, in this skill's folder.

## Protocol

### 1. Mutex check

If `opportunity.json`'s `outcome` field is already set (not `null`), exit silently - a prior pass already closed this opportunity. For a `phase` kind opportunity, also check `.compass/tmp/phase-reports/<phase-id>/.processed`: its presence is the same backstop collision this check has always guarded against, from the legacy path where the phase-report directory carried its own mutex before opportunities existed.

### 2. Read the opportunity

Parse `opportunity.json` for `kind`, `triggers`, and `evidence`. For a `phase` kind, also read `phase-summary.yaml` from the evidence directory (see structure above). For `signal` and `interval` kinds, `triggers` already names the fired signal kinds directly - there is no separate structured signal file to parse.

### 3. Binary trigger check

For a `phase` kind opportunity, the five phase triggers (checked against `phase-summary.yaml`; any one firing sets `triggered: true`, none sets `triggered: false`) and the table of every trigger with its evidence are in `triggers.md`, in this skill's folder; read it before this step.

For a `signal` or `interval` kind opportunity, `triggered` is always `true`: `compass capture-check` only opens one of these when its own arithmetic already found a due condition (a strong signal, or the interval reached with at least one signal in the window), so the opportunity's existence is the trigger.

If `triggered: false` (only possible for a `phase` kind opportunity whose `phase-summary.yaml` carries no fired condition), there are zero candidates: proceed straight to step 7's "no candidates" log entry, then steps 8 and 9.

### 4. Gather candidate findings

For each fired trigger, read the evidence the table in `triggers.md` names. What to scan for under each trigger (fix-loop, validator deviation, debug, STOP-and-report, plan revised, handoff, agent noted, interval): `candidate-gathering.md` in this skill's folder; read it before gathering.

A candidate is a discrete finding: one rule, one why. Do not group multiple findings into one. If the evidence has 3 findings, emit 3 candidates.

For each candidate, prepare a payload draft:
- Tentative summary (<=120 chars)
- Tentative body (<=5 lines)
- Tentative category (process likely - extraction lives in the build pipeline)
- Tentative area (read from the parent plan's `area` frontmatter when the evidence traces to one; otherwise from the vault's active plan or spec)
- Tentative tags (extract from the task description and the finding)

### 4a. Contradiction check

For each candidate, and for evidence that produced none, check whether it shows an existing active lesson to be wrong, and route a revise or archive through lesson-write. The procedure and the rule for counting `revised` and `archived`: `contradiction-check.md` in this skill's folder; read it before this step.

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

For each candidate that passed the anti-list, read `.claude/skills/lesson-write/SKILL.md` and follow its steps with the candidate's payload - in place, never through the Skill tool. Record the return value.

### 7. Write the extraction log

Write the extraction log to `.compass/tmp/extraction-log-YYYY-MM-DD.md`. Its format (headers, triggers checklist, candidate entries, the no-candidates entry, signal and interval headers, contradiction outcomes) is in `extraction-log.md` in this skill's folder; read it before writing.

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
