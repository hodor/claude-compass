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

> [!IMPORTANT]
> You decide: accept or reject run 6. Three research bullets leave the always-loaded rules (every finding names its source; a grade only after you were told and could refuse; a gap becomes another research pass, never a plan) and move to a new `evidence-rules.md` in the `research` skill, which links it. The `researcher` agent now carries the sourcing rule itself, and the `research` skill already enforces the other two in its steps 6 and 10. Recommended: accept. Approve accepts it; Needs changes rejects it, and your note joins `feedback.md`.

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

Every increment is reviewed before the next run: the full suite and `compass validate` pass, then `compass loop review LOOP-003 <run-id> accept|reject`.

## Step 7: Flow control

`wip_limit` 1; $0.50 per actuator run plus $0.15 per judge run; $5 in total; halts after 2 harmful runs, 3 actuator failures or 5 runs without help.

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
