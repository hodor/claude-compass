---
title: Verify worktree isolation is real before parallel writes
type: lesson
status: active
category: process
area: workflow
tags: [worktree, isolation, subagents, orchestration, silent-failure]
created: 2026-08-23
updated: 2026-08-23
score: 5
summary: "Worktree isolation can silently not exist; confirm the path is in `git worktree list` before parallel writers run"
seen: []
---

A builder spawned with `isolation: worktree` wrote every file into the main checkout: the spawn handed back a worktree path git had never registered, and nothing surfaced the failure until the task stalled (PLAN-009 wave 1, TASK-083).
Isolation is an assumption to verify, not a property to trust: before parallel writers run, confirm each worktree appears in `git worktree list` and that the builder's first write lands under its path.
A silent fallback to the shared checkout defeats file-ownership partitioning exactly when overlapping writers depend on it.
