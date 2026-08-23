---
title: A validation must be able to fail before it is worth running
type: lesson
status: active
category: process
area: methodology
tags: [falsification, pre-registration, baseline, control-arm, prototypes]
created: 2026-08-23
updated: 2026-08-23
score: 5
summary: "Score the constant-answer baseline, fix the threshold, and check the stop verdict can fire and end the plan"
seen: []
---

[[PLAN-009-sizing-mechanism]] TASK-081 pre-registered agreement bands over this vault's specs: a corpus of 16 flat, 0 folder and 1 unit, where answering "flat" to every item scores about 94% and ships the procedure unchanged.
It carried no control arm, no number dividing "high" from "low" agreement, and a stop band hinging on the undefined word "coherent" that fluent model justifications satisfy by construction, so the unfavorable verdict could not fire.
Worse, the plan's own completion gate - `coverage --strict` exits 0 - is failed by that stop band, so declaring the unfavorable verdict was structurally penalized as well as unreachable.
The same shape appears without an experiment: a bare correction count has no denominator, and "the shape was right" and "nobody reverts" both predict the low number the log will show.
Before running any validation, score what a constant or do-nothing answer gets on the real corpus, fix the statistic and its threshold in advance, and confirm the stop verdict can occur and counts as a legitimate completion.
