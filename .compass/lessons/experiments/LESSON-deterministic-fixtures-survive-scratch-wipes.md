---
title: "Deterministic fixtures survive scratch wipes"
type: lesson
status: archived
category: process
area: methodology
tags: [experiments, scratchpad, determinism, fixtures]
created: 2026-08-31
updated: 2026-08-31
score: 5
summary: "Build experiment fixtures deterministically so a wiped scratchpad can be rebuilt identically mid-session"
source: extract-lessons:signal-OPP-20260831T012647797932Z
seen: []
---

TASK-119's scratch fixtures were wiped mid-session between writes; the run survived only because the fixture-building scripts were deterministic and results were already recorded in the plan as they landed. Build experiment fixtures from deterministic scripts, not hand-assembled scratch state, and write results into the durable document as soon as they land rather than trusting scratch state to persist.
Superseded: this finding was already documented in PLAN-016-domain-taxonomy.md line 183 before this lesson was written; should have been rejected by the anti-list bucket "already documented in a plan." Caught within the same extract-lessons pass, OPP-20260831T012647797932Z.
