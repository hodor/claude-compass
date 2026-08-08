---
title: Spawn briefs must not strip an agent definition's own quality stations
type: lesson
status: active
category: process
area: workflow
tags: [subagents, briefs, code-review, agent-protocol, orchestration]
created: 2026-08-08
updated: 2026-08-08
score: 5
summary: "A blanket no-sub-agents ban in a spawn brief strips the builder's review station; twice violated, both violations caught real bugs"
seen: []
---

An agent definition's built-in quality stations (the builder's code-review pass) are load-bearing; a spawn brief's blanket "no sub-agents" ban strips them along with the noise it targets.
Observed twice: builders violated the ban to run their review station anyway, and both reviews caught real defects pre-delivery - once seven bugs including a false-positive source inflating a filter's findings 17 to 7.
Scope brief restrictions to what they mean: forbid uninstructed fan-out, permit the definition's own stations by name.
