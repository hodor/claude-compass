---
title: "Loop: session-context"
type: loop
status: active
area: workflow
tags: [loop]
created: 2026-10-31
updated: 2026-10-31
summary: "Shrinks the text Compass adds to every Claude Code session, as far as it goes with Compass working as well as before."
---

# Loop: session-context

Shrinks the text Compass loads into every Claude Code session, the need of [[specs/tooling/SPEC-027-compass-uses-fewer-tokens]].

## Step 0: End state

The always-loaded text (rules files whole, skill and agent `name`/`description`/`when_to_use`, the setup CLAUDE.md block) is as small as it can be while Compass works as well as before. No fixed number: the loop runs until five runs in a row save nothing, or the budget ends.

## Step 1: Sensor

`compass loop sense-context`: estimated tokens (UTF-8 bytes / 4) over the always-loaded sources, one item per source. `direction` down, `target` 0, which is never reached, so the stop is the no-progress halt.

## Step 2: Stabilize

`compass loop baseline LOOP-003` commits today's sources; a new always-loaded source is a new item, which the loop judges harmful.

## Step 3: Controller

`controller.py` ranks the sources by estimated tokens, largest first; the actuator takes the first one `feedback.md` does not rule out.

## Step 4: Actuator

Sonnet, Read/Edit/Write/Glob/Grep, one passage per run moved out of an always-loaded source into the skill or agent body that does that work, never deleted (`actuator.md`, `golden/`). An advisory Haiku judge checks `judge-rules.md`: removed text is still reachable, and no gate is weakened.

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
