---
title: "Terminal Output: Mockup"
type: research
status: draft
confidence: low
area: methodology
tags: [terminal, cli, plain-language, mockup, human-surface]
depends_on: ["[[PLAN-024-working-in-compass-is-visual]]", "[[research/human-surface/RESEARCH-plain-words-mockup]]"]
summary: "what bare compass, tree, unit-check, doctor and validate print today beside a shorter plain-text version, with line and byte counts for each"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
git_commit: "7a19724"
author: "builder"
---

# Terminal Output: Mockup

Five commands print the most a person reads in the terminal. This page shows what each prints today beside a shorter version in the words of [[research/human-surface/RESEARCH-plain-words-mockup]]. The terminal stays plain text: no color, no symbols. It belongs to [[specs/human-surface/SPEC-031-working-in-compass-is-visual]].

## Counts

Every file is in `F:\claude\plugins\compass\.compass\tmp\mockups\terminal\`, with LF line endings. Run `wc -lc *.before.txt *.after*.txt` in that folder to reproduce each number. The "before" files are the command output captured at commit 7a19724 with the Windows carriage returns removed (`python .claude/cli/compass <command> | tr -d '\r'`); `tree`, `unit-check` and `doctor` print the vault as it stands, so a later run differs.

| Command | Before: lines | Before: bytes | After: lines | After: bytes | Lines | Bytes |
|---|---|---|---|---|---|---|
| `compass` | 134 | 8,400 | 64 | 4,175 | -52% | -50% |
| `compass tree` | 246 | 40,536 | 86 | 5,155 | -65% | -87% |
| `compass unit-check` | 513 | 54,138 | 31 | 2,828 | -94% | -95% |
| `compass doctor` | 19 | 2,136 | 17 | 1,176 | -11% | -45% |
| `compass validate` | 3 | 314 | 3 | 305 | 0% | -3% |
| Total | 915 | 105,524 | 201 | 13,639 | -78% | -87% |

Files: `compass.before.txt`, `compass.after.txt`, `tree.before.txt`, `tree.after.txt`, `unit-check.before.txt`, `unit-check.after.txt`, `doctor.before.txt`, `doctor.after.txt`, `validate.before.txt`, `validate.after.txt`. `tree.after-full.txt` is a second `tree` version: 246 lines, 15,643 bytes.

## Bare `compass`

One list holds every command, the hook entry points mixed in among the commands a person runs, each description wrapped over up to four lines. After: the commands a person runs come first, grouped by purpose, then the automatic steps and agent-only commands apart. All 47 commands remain, one line each.

Before (first 12 of 134 lines):

```text
usage: compass [-h] <command> ...

Compass vault bookkeeping CLI.

positional arguments:
  <command>
    guard            PreToolUse hook: deny a tool call that would delete or
                     discard (Bash rm/git discard, a Write that empties or
                     guts, a blanking Edit).
    sync             Regenerate index.md + tag-index.yaml, sweep done tasks
                     out of active.md, check caps, clean tmp logs. Hook entry
                     point.
```

After (lines 1 to 14 and 44 to 53 of 64):

```text
Usage: compass <command> [options]

Commands you run

  Check
    validate         Check links, properties and the start-here size limit. Exits 1 on a defect.
    doctor           Check the install: automatic steps, agents, skills, lessons. Exits 1 on a FAIL.
    hot-path         Show the size of the start-here files against their limit.
    usage            Show which commands have run, and which never have.
    lesson-coverage  Show which lessons a plan cites, and which relevant ones it does not.
    coverage         Check a plan carries every decision it must. Exits 1 on a gap.

  Look up
    tree             List every document with its summary, indented by folder.

...

Run by hooks and agents

  Automatic steps (hooks)
    guard            Refuse a tool call that would delete or discard.
    sync             Rebuild indexes, move finished tasks, check size limits, clean logs.
    self-update      At session start, refresh this install from its source if it changed.
    capture-check    Each turn, decide whether to open a moment to record a lesson.
    capture-signal   When a subagent finishes, record a hint that a lesson may be worth recording.
    capture-worker   Background helper that runs the lesson-recording pass for one moment opened by capture-check.
    context-check    At 80% and 95% of the context window, halt once and suggest a handoff.
```

## `compass tree`

Each document prints as its file name and its full summary, and the longest line is 514 characters. After: a one-line key opens the output; each section names what its documents are for; a document prints as its title with its id after; a topic folder prints as one line with its document count and what belongs in it. `compass tree <folder>` would list one folder in full.

Before (lines 7 to 12 of 246):

```text
decisions
  ADR-001-methodology-as-skill-with-vault - Methodology lives in a skill; project state in per-project `.compass/` Obsidian-compatible vault
  ADR-017-capability-index-and-usage-record - the existing help listing is the progressive-disclosure index, made reachable by one resident rule line; maincli dispatch records every invocation to meta/usage.yaml; compass usage lists never-used commands explicitly; clean-tmp retires; the admission-control pair's fate is decided by the usage record
  distribution/ - rulings on installing, updating, and configuring Compass across projects
    ADR-008-model-resolution-table - Abstract Model Tiers Resolved at Install Time by compass apply-models
    ADR-015-self-update-on-session-start - SessionStart(startup) runs compass self-update: ls-remote sha gate, clone-and-apply replicating the update skill mechanically, dev repos copy from local plugin/, one context line on update, silence and exit 0 on every failure
```

After (lines 1 to 13 of 86):

```text
Topic folders end in / and show how many documents they hold; `compass tree <folder>` lists one folder in full.
compass-cli (a workstream folder)
  A Python `compass` CLI Owns All Mechanical Vault Work (ADR-005)
  Compass CLI Implementation (PLAN-002)
  How Claude Code Structures CLIs and the Command-Hook Contract
  Measuring SPEC-004's 80% Bookkeeping-Token Reduction
  Mechanical Vault Work Must Not Cost Agent Tokens (SPEC-004)
decisions (decision records, ADR: what we chose and why)
  Methodology as a skill, project state in an Obsidian-compatible vault (ADR-001)
  Bare compass Is the Capability Index (ADR-017)
  distribution/ (3)  rulings on installing, updating, and configuring Compass
  learning/ (5)  rulings on capture and feedback
  pipeline/ (3)  rulings on the development workflow stages and gates
  vault-structure/ (9)  rulings on how the vault organizes, bounds, and retrieves its own
```

A document's summary is not printed; the title carries the meaning and the document holds the summary. Collapsing the topic folders is what removes the lines. `tree.after-full.txt` keeps every document line in the title-and-id form: the same 246 lines, 61% fewer bytes.

## `compass unit-check`

Each of 25 groups prints its spec, every member path, and a full `make-unit` command repeating those paths, then a 67-line list of documents claimed by several groups. After: one line per group, one sentence on the overlap, and a pointer to the detail. `compass unit-check <name>` would print one group's documents and its `make-unit` command.

Before (lines 86 to 94 of 513):

```text
candidate: review-documents-open-in-obsidian (type-spread 3: plan, research, spec)
  spec: specs/human-surface/SPEC-030-review-documents-open-in-obsidian.md
  members:
    - plans/PLAN-022-review-in-obsidian.md
    - research/RESEARCH-review-in-obsidian.md
    - research/RESEARCH-review-mockup.md
    - specs/human-surface/SPEC-030-review-documents-open-in-obsidian.md
  suggested: compass make-unit review-documents-open-in-obsidian plans/PLAN-022-review-in-obsidian.md research/RESEARCH-review-in-obsidian.md research/RESEARCH-review-mockup.md specs/human-surface/SPEC-030-review-documents-open-in-obsidian.md
```

After (lines 1 to 8 and 29 to 31 of 31):

```text
25 specs have gathered enough related documents to earn their own workstream folder.
A group is the spec plus the plans, research and decision records that depend on it.

multi-host-agent-cli-support                    48 documents (decision records, plans, research, spec)
central-model-resolution-table                   6 documents (decision records, plans, research, spec)
update-safe-customizations                       3 documents (decision records, research, spec)
compass-updates-itself                           6 documents (decision records, plans, research, spec)
review-documents-open-in-obsidian                4 documents (plans, research, spec)

...

67 documents belong to more than one group, so make one folder at a time and run this again.
Next: `compass unit-check <name>` lists a group's documents and the make-unit command that moves them.
```

## `compass doctor`

A 25-name list of specs sits inside one row, a closing `fixes:` block repeats advice that the rows could carry, and the Obsidian row prints its recovery hint even when it is OK. After: counts replace the list, each warning carries its next step, and a hint prints only when its row is not OK. Before is 19 lines and after is 17.

Before:

```text
status  check                      detail
OK      plugin.yaml                version 0.29.0
OK      hook registration          PreToolUse, PostToolUse, Stop, SubagentStop all registered
OK      CLI completeness           47 commands, all modules present
WARN    unit-promotion candidates  25 candidate(s): active-holds-only-active-work, capabilities-are-reachable-and-measured, capture-in-the-humans-words, ... (25 names in all)
WARN    capability usage           9 command(s) never used in 44 days of measurement
OK      worker ledger              86 started, 84 finished, 2 failed; last failure: exit 0 (opportunity not closed)
OK      obsidian review            Compass Review is on; if no review bar appears, in Obsidian, open Settings, then Community plugins; if it shows "Turn on community plugins" (restricted mode), click it; then switch on Compass Review
OK      host materializations      hosts: claude-code, dsh; dsh hooks, skills, bundle (0.29.0), rules section all present
OK      capture posture            claude on PATH - detached worker via claude

fixes:
  unit-promotion candidates: run `compass unit-check` for the member list
  capability usage: run `compass usage` for the NEVER USED list
```

(The rows for agents, skills, lessons catalog, local overlays and session retention are omitted here; they are in `doctor.before.txt`.)

After:

```text
Install check: no failures, 2 warnings.

status  check                                  detail
OK      plugin.yaml                            version 0.29.0
OK      automatic steps                        PreToolUse, PostToolUse, Stop, SubagentStop all set up
OK      commands                               47 present
OK      agents                                 13 present
OK      skills                                 34 present
OK      lessons list                           present
WARN    workstreams that could have a folder   25; run `compass unit-check` to see them
WARN    commands you have not run              9 in 44 days; run `compass usage` to see them
OK      local additions                        none
OK      background helper log                  86 started, 84 finished, 2 failed
OK      session retention                      Claude Code keeps sessions 3650 days
OK      Obsidian review                        Compass Review is on
OK      install for each tool                  claude-code and dsh: automatic steps, skills, bundle (0.29.0) and rules all present
OK      lesson recording                       set up; a background helper records lessons
```

## `compass validate`

The output is three lines, so the saving is small here. The warning form of [[research/human-surface/RESEARCH-plain-words-mockup]] (a sentence first, the code in brackets at the end) makes each line readable, and the saving grows with the number of warnings.

Before:

```text
compass validate: 0 error(s), 2 warning(s)
  warning sizing_unrecorded: compass-cli: predates the sizing log, no sizing_id recorded
  warning folder_over_ceiling: research/pipeline: 16 direct children (ceiling 12) - propose the grouping; the ceiling only triggers the proposal, domains form at their second member
```

After:

```text
compass validate: no errors, 2 warnings.
  warning: compass-cli was made before the shape record existed. (sizing_unrecorded)
  warning: research/pipeline holds 16 items, more than the 12 that read easily. Compass will propose topic folders; a topic folder needs at least two items. (folder_over_ceiling)
```

## What the human decides

- Whether `tree` collapses topic folders (86 lines) or keeps every document (246 lines).
- Whether `tree <folder>` and `unit-check <name>` exist to show what the short forms leave out.
- Whether `doctor` drops the recovery hint on OK rows.
