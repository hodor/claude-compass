---
title: Briefs for orchestrating subagents must require foreground spawns
type: lesson
status: active
category: process
area: workflow
tags: [subagents, orchestration, background, foreground, stall]
created: 2026-11-21
updated: 2026-11-21
score: 5
summary: "A lead agent that spawns background children ends its turn 'waiting' with no live children and stalls; briefs must require foreground spawns"
source: extract-lessons:OPP-20261122T064628500999Z
seen: []
---

A lead subagent that spawns its children in the background ends its turn to wait for them, but nothing wakes it: no live children remain and the lead stalls.
Every brief for a subagent that spawns its own subagents must require foreground spawns, so the lead holds its turn until each child returns.
