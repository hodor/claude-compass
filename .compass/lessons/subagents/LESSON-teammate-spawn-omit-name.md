---
title: Teammates spawning subagents must omit the name parameter
type: lesson
status: active
category: process
area: workflow
tags: [subagents, orchestration, teammate, agent-tool, spawn]
created: 2026-09-13
updated: 2026-09-13
score: 5
summary: "A teammate's Agent-tool call with `name` set fails outright; the roster is flat, so spawn plain subagents by omitting `name`"
source: "extract-lessons:OPP-20260913T214949623748Z"
seen: []
---

A teammate's Agent-tool call fails with "Teammates cannot spawn other teammates - the team roster is flat" whenever it passes `name`.
Omit `name` to spawn an ordinary, non-addressable subagent instead; only the top-level session creates named teammates.
Why: the roster is flat by design, so nesting a named teammate under a teammate is rejected outright, not degraded.
