---
title: Tag index gives directed retrieval, not automatic token reduction
type: lesson
status: active
category: process
area: methodology
tags: [tag-index, retrieval, cost, hypothesis-falsified, empirical]
created: 2026-06-10
updated: 2026-06-10
score: 5
summary: "Tag index makes agents more thorough and faster wall-time, but does not automatically reduce tokens; the cost win depends on the query shape"
seen: []
---

A facet/tag index changes the agent access pattern toward directed retrieval (read tag-index then fetch tagged files), not toward fewer files read.
Empirical A/B on a vault question gave +23% tokens and +17% tool calls for the tag-index arm, despite -25% wall-time and more comprehensive recall.
The directional win is in thoroughness and speed; the cost win is conditional on the query - it materializes when the no-tag arm would do many false-positive greps OR when the index title list is too thin to navigate.
Falsifies the SPEC-003 hypothesis of automatic 30% token reduction; the design still has value but the claim must be reframed around directed retrieval and recall, not raw cost.
N=1 measurement; needs a wider sweep across query shapes (single-tag, multi-tag, broad-survey, narrow-lookup) before any general statement about expected cost behavior.
