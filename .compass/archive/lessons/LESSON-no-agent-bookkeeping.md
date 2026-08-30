---
title: Mechanical bookkeeping belongs in scripts or hooks, not agent protocol steps
type: lesson
status: archived
category: process
area: methodology
tags: [token-efficiency, automation, hooks, skill-design, jit]
created: 2026-05-26
updated: 2026-05-26
score: 5
summary: "Mechanical bookkeeping (counters, indexes, catalogs) belongs in scripts/hooks/JIT, not agent steps"
seen: []
---

If an agent's protocol step is purely "read N, do arithmetic, write N+1" with no judgment, automate it.
Compass moved index updates to a PostToolUse hook and counter increments to JIT glob+max+1.
Test: can the work be reduced to "read filesystem, compute output, write file" without judgment? If yes, automate.
Agent tokens are for judgment, dedup decisions, anti-list filtering - not for incrementing integers.
Counter-style state files invite drift; the filesystem is already the source of truth.
