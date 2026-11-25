---
title: "Checking-cost pilot: smoke builds and the per-part spread"
type: research
status: draft
confidence: low
area: tooling
tags: [tokens, cost, verification, measurement, bench, tester]
summary: "the post-tester variant survives a headless build once every post-build tester cue is removed, and its station rows reach the record; Compass builds of the pool topics run past the 150-minute wall cap, so the spread pilot's pairs are mostly equal-time pairs"
created: 2026-11-24
updated: 2026-11-24
author: "build-lead"
depends_on: ["[[PLAN-034-checking-cost-follows-task-and-model]]"]
---

# Checking-cost pilot

```mermaid
flowchart LR
  A["Smoke 1: variant build<br/>(first patch)"] -->|"one post-build tester<br/>still spawned"| B["Patch extended to the<br/>builder, tester and<br/>methodology text"]
  B --> C["Smoke 1 again:<br/>no post-build tester"]
  C --> D["Smoke 2: full Compass,<br/>context stop at 15%"]
  D --> E["Spread pilot:<br/>12 builds"]
```

Measured for [[PLAN-034-checking-cost-follows-task-and-model]] TASK-351 and TASK-352 with `bench/overhead/pilot.py` and `bench/overhead/spread.py`. Topics are pool topics with frozen goals, named by letter; no topic text, path or session id appears here.

## Smoke builds

### Smoke 1: one build in `compass-minus-post-tester`

The variant removes the post-build and post-merge tester from Compass. It ran twice on the same pool topic.

| Check | First run (patch on the build and autopilot skills) | Second run (patch also on the builder agent, the tester agent and the methodology skill) |
|---|---|---|
| The project's `.claude/` matches the variant after the start-of-session self-update | yes | yes |
| Post-build tester spawns | 1 (one tester in post-build mode for all eighteen tasks of the first stage) | 0 |
| Pre-build tester spawns | 7 | 6, and one tester asked to update tests pinned to numbers a balance task retuned |
| Station rows in the build's record | yes, 8 station and model keys | yes, 8 station and model keys |
| `build_model` in the record | the subagents' model (Sonnet), though the main session ran Opus | the main session's model (Opus) |
| How the build ended | wall-time cap (150 minutes), 31 turns | wall-time cap (150 minutes) |
| Goal items met, partly met, not met | 6, 3, 1 | 7, 2, 1 |

What the first run showed, and what changed:

- **The first patch left cues for a post-build tester.** The builder agent's closing line ("The orchestrator spawns the `tester` agent in post-build mode against your diff"), the tester agent's description of two stations, and the methodology skill's flow ("tester auto-runs on each", "spawning the tester after each merge") still described one. The orchestrator spawned one post-build tester when the first stage ended. The patch now edits those five files, and `tests/test_variants.py` fails if any of seven cue phrases remains after the patch.
- **`build_model` named the subagents' model.** `modelUsage` counts subagent usage, and the builders and testers, on Sonnet, wrote more output than the Opus main session. `records.build_model` now reads the main session's model from the first `system/init` event and falls back to the most-output rule only when that event names no model.
- **Some tester reports are free-form.** Of the 7 tester spawns in the second run, 5 left a station row: 1 `tester-pre` and 4 `unparsed`, whose reports skip the template's `### Mode` section. One spawn was still running at the cap and one ended with no final report. The spawn prompts all name their station, so the spawn counts above are read from the prompts, not from the station log.

### Smoke 2: one full Compass build with the context stop at 15%

Pending.
