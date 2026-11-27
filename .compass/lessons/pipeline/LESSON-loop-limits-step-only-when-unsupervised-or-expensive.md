---
title: A loop's limits and escalation step matters when it runs unsupervised or costly
type: lesson
status: active
category: domain
area: workflow
tags: [loops, flow-control, escalation, cost]
created: 2026-11-27
updated: 2026-11-27
score: 5
summary: A loop's step 7 (limits and escalation) is set when the loop runs unsupervised or each run is costly; a cheap hand-run loop keeps the defaults
source: clone-old:20261127T194235328024Z
seen: []
---

The human ruled that a loop needs its own limits and escalation only when it runs without him watching, or when a run costs more than tokens (cloud GPUs).
A cheap loop he runs by hand keeps loop.json's defaults, and its index.md says so in step 7.
Loops do not yet report a run's cost beyond tokens, so a costly loop names that cost in step 7 by hand.
