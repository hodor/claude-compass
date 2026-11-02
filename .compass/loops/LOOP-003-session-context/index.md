---
title: "Loop: session-context"
type: loop
status: active
area: workflow
tags: [loop]
created: 2026-10-31
updated: 2026-10-31
summary: "Shrinks the text Compass puts into Claude Code's context over all a session's work, as far as it goes with Compass working as well as before."
---

# Loop: session-context

## Step 0: End state

The text Compass puts into Claude Code's context over all the work a session does is as small as it can be while Compass works as well as before. No fixed number: the loop runs until five runs in a row save nothing, or the budget ends.

## Step 1: Sensor

`compass loop sense-context`: estimated tokens (UTF-8 bytes / 4) per average session. Rules files and every skill and agent's frontmatter count in full; skill bodies, skill folder files and agent bodies count times the share of sessions that load them. That share comes from `compass loop usage-scan`, which reads the Claude Code transcripts on each machine and writes only Compass source names and counts to `~/.compass/usage/`, outside the repository. `direction` down, `target` 0, never reached, so the stop is the no-progress halt.

## Step 2: Stabilize

`compass loop baseline LOOP-003` commits today's sources; a new always-loaded source is a new item, which the loop judges harmful.

## Step 3: Controller

`controller.py` ranks the sources by tokens per average session, largest first; the actuator takes the first one `feedback.md` does not rule out.

## Step 4: Actuator

Sonnet, Read/Edit/Write/Glob/Grep, one passage per run moved from where it loads often to where only the work that needs it loads it, never deleted (`actuator.md`, `golden/`). An advisory Haiku judge checks `judge-rules.md`: removed text is still reachable, and no gate is weakened.

## Step 5: Schedule

Run by hand from this repository (`compass loop run LOOP-003`), on the human's Claude subscription; the dollar caps limit how much of the plan's usage the loop takes.

## Step 6: Human on the loop

Each increment is checked automatically before the next run (text tests, `compass validate`, the protected rules sections unchanged, the full suite every fifth accepted run) and accepted or rejected with `compass loop review`; the human checks in on the batch.

## Step 7: Flow control

`wip_limit` 1; $0.50 per actuator run plus $0.15 per judge run; $12 in total; halts after 2 harmful runs, 3 actuator failures or 5 runs without help.

## Live record

### 2026-10-30: calibration before the loop

- Measured in scratch projects with `claude -p "hi" --model sonnet`: the first request's input was 29,140 tokens without Compass and 41,235 with it, so Compass adds 12,095 tokens.
- The sensor read 9,117 for the same content. The two agree in direction; the sensor counts only what Compass ships, not Claude Code's own handling of it.

### 2026-10-31: run 1 (RUN-20261031T223841214198Z)

- Sensor 9,121 -> 9,072 (-49, about 0.5%). Cost $0.22 of the $5 cap.
- The run first halted as `controls-changed`: Compass's usage record and Obsidian's app state changed during the judge, written by other processes. The runner now ignores those files (commit `70c6ce4`).
- The actuator's version pointed at a `plugin/...` path that an installed project lacks, and pushed the research skill past its line limit. Both were corrected by hand; `feedback.md` now carries both rules, plus "move a hundred tokens or more per run".
- Full test suite text checks and `compass validate` pass.

The change, in the rules every session loads (`compass-pipeline.md`, Research):

```diff
- ... otherwise they are plain text. His own questions lead the axis list; the spec's own listed questions are answered wherever an axis touches them, and never lead it. When he joins, research runs as a conversation: findings surface as they land and his readings steer the axes. When he passes, run and deliver as usual.
+ ... otherwise they are plain text. How his questions lead and how research runs once he joins: the `research` skill, step 4.
```

And in the `research` skill, step 4 "Fold in the human's own questions", which already said his questions lead:

```diff
  ... The spec's own Open Questions stay answered-where-touched and never lead.
+ When he joins, research runs as a conversation: findings surface as they land and his readings steer the axes. When he passes, run and deliver as usual.
```

Review of run 1 (changes): the loop is about the total context Compass uses to do everything, not only the text a session starts with. The run 1 change stays, since it shrinks both measures.

### 2026-11-01: the sensor weighs all of Compass's text by real use

- `compass loop usage-scan` on this machine: 1,477 sessions in the last 30 days loaded a Compass source; 27 sources were loaded at least once.
- Reading: 11,969 tokens per average session, of which 9,072 are the startup text. The heaviest on-demand source is the `extract-lessons` skill, loaded in 673 of 1,477 sessions (2,229 tokens per session), second only to the pipeline rules (3,056).

### 2026-11-01: run 2 (RUN-20261101T211918374970Z)

- 11,969 -> 11,761 per average session (-208, 1.7%). The judge found nothing. Text tests pass.
- The change: six paragraphs of the pipeline rules' Document Writing section move word for word to a new file, `plugin/skills/obsidian/writing-principles.md`. The rules keep one line pointing there, and the `obsidian` skill names the file under "Documents the human reads".
- Accepted. The `spec` skill's reviewer brief now points at `writing-principles.md` for the moved rules.

### 2026-11-01: run 3 (RUN-20261101T221426875569Z)

- 11,761 -> 11,651 per average session (-110). The judge found nothing. Text tests pass.
- The change: the pipeline rules' "Decisions (ADRs)" bullets become one line plus a pointer; the four bullets move word for word into the `methodology` skill's ADR section.
- Accepted, with the note that agents must still reach the full ADR rules when they need them. The two places that write an ADR, the `builder` agent and the `retroactive` skill, now name the `methodology` skill's ADR section, and the always-loaded rules point there for every other agent.

### 2026-11-01: run 4 (RUN-20261101T221953624975Z)

- 11,651 -> 11,573 per average session (-78). The judge found nothing. Text tests pass.
- The change: the Brevity, Research-length and Decisions-consolidate paragraphs of the pipeline rules' Document Writing section move word for word to `writing-principles.md`; the pointer line lists them.
- Accepted. The `spec`, `specs` and `vision` skills, which capture the human's words, each still state that his sentences are kept as spoken.

### 2026-11-01: run 5 (RUN-20261101T222323732795Z)

- 11,573 -> 11,477 per average session (-96). The judge found nothing. Text tests pass.
- The change: the pipeline rules' two indexing bullets become one line; the full text moves word for word to a new section of `writing-principles.md`.
- Accepted.

### 2026-11-01: run 6 (RUN-20261101T222624533925Z)

- 11,477 -> 11,425 per average session (-52). The judge found nothing. Text tests pass.
- The change: three Research bullets become one pointer line; they move word for word to `plugin/skills/research/evidence-rules.md`, linked from the skill's researcher brief step, and the sourcing rule is added to the `researcher` agent.
- Accepted.

### 2026-11-01: run 7 (RUN-20261101T223045987720Z)

- 11,425 -> 11,276 per average session (-149 on the sensor, about 0 in practice). The judge found nothing.
- The change: the extraction log format moves from the `extract-lessons` skill to `plugin/skills/extract-lessons/extraction-log.md`, which the skill tells every run to read.
- Accepted. The side file gains weight in later readings as `usage-scan` sees runs read it, so the sensor corrects itself after the next scan.

### 2026-11-01: run 8 (RUN-20261101T230917854302Z)

- 11,276 -> 11,083 per average session (-193 on the sensor, about 0 in practice). The judge found nothing.
- The change: the contradiction check moves from the `extract-lessons` skill to `plugin/skills/extract-lessons/contradiction-check.md`, which the skill tells every run to read.
- Accepted; the loop may keep moving a step a skill always runs into a side file it reads.

### 2026-11-01: run 9 (RUN-20261101T231924861842Z)

- Halted as `controls-changed`: `compass sync` rewrote `.compass/meta/tag-index.yaml` during the judge. The runner now skips every file under `.compass/meta/` (commit `c8c94b4`).
- Its change, moving the Data rule's enforcement paragraph out of the always-loaded rules, was not kept: the Data rule is an invariant every session carries. `feedback.md` now says so.

### 2026-11-01: run 10 (RUN-20261101T232653329926Z)

- 11,083 -> 11,027 per average session (-56). The judge found nothing. Text tests pass.
- The change: the phase summary schema moves word for word from `extract-lessons` to `plugin/skills/extract-lessons/phase-summary.md`; `extract-lessons` and `build` point to it.
- Accepted.

### 2026-11-01: run 11 (RUN-20261101T232943082396Z)

- 11,027 -> 10,996 per average session (-31). The judge found nothing.
- The change: the `compass tree` and `compass usage` hints move from the rules' Capabilities section to the `methodology` skill's capability index paragraph.
- Accepted.

### 2026-11-01: unattended batch

The human ruled the loop runs on its own, about 30 runs, checked automatically rather than reviewed one by one, with the usage cap raised to $12. The batch starts at tag `loop003-batch-start`.
- Batch runs 1 to 4 accepted (10,868 -> 10,641). Runs 5 and 6 were rejected because the batch's full-suite check counted the VS Code harness, which runs the pre-build tests of TASK-243 that are meant to fail until it merges; their rejection reasons were not about the changes, so they are not kept in `feedback.md`. The batch paused, TASK-243 merges first, then the batch continues.
- Batch resumed after TASK-243 merged: runs 1 to 15 accepted (10,515 -> 9,493), run 16 neutral (no move of 100+ tokens left in the top sources) and rejected, runs 17 to 23 throttled behind it. The last accepted runs moved 1 or 2 tokens each: the loop has reached its plateau.
- An audit of every moved passage found no lost text, protected sections unchanged, no added dashes; it found one wrong pointer (the document forms) and two steps naming a side file without saying to read it first, fixed in `a332f3a`.
- After a fresh `compass loop usage-scan` (1,540 sessions) the side files carry their real weight: 9,479 per average session, down from 11,969 at the loop's start (-21%).
- Full suite 2,226 passed; Obsidian 553 and VS Code 135 tests pass; `compass validate` 0 errors. Spend: $10.20 of the $12 cap.

### 2026-11-01: calibration at the stop

- The same scratch-project measure as before the loop (`claude -p "hi" --model sonnet`, first request's input), with Compass 0.34.5: 29,111 tokens without Compass and 38,396 with it, so Compass adds 9,285, down from 12,095 (-2,810, -23%). The sensor's -21% and this -23% agree.
