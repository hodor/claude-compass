---
title: A spawned session inherits the project's hooks and re-enters its own machinery
type: lesson
status: active
category: process
area: architecture
tags: [hooks, headless, spawned-sessions, recursion, background-worker]
created: 2026-08-24
updated: 2026-08-24
score: 5
summary: "A spawned claude session inherits the project's hooks; a hook-spawned worker fires its own machinery unless gated"
seen: []
---

A `claude -p` session launched with cwd inside a hooked project loads that project's settings and fires every hook: Stop, SubagentStop, PostToolUse.
A worker spawned BY a hook therefore re-enters the machinery that spawned it - its Stop can block on the same opportunity it is processing, and its vault writes record the signals that make the next opportunity due: the loop feeds itself.
Any design that spawns a session inside a hooked project must gate the recursion explicitly, e.g. an env marker the hook commands check and exit 0 on.
Plan, ADR, and research for the detached capture worker all missed this; only adversarial mechanism review caught it.
