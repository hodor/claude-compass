---
title: Spawned agents must deliver reports via SendMessage, not final text
type: lesson
status: active
category: process
area: workflow
tags: [subagents, orchestration, sendmessage, reports, briefs]
created: 2026-08-06
updated: 2026-08-06
score: 5
summary: "A spawned agent's final plain text is invisible to its orchestrator; briefs must mandate an explicit SendMessage delivery"
seen: []
---

An agent's final plain-text output is not delivered to the agent that spawned it; only an explicit SendMessage call is.
An agent that finishes and goes idle without one looks stalled while its work is complete - a different failure than a true mid-task stall, which resuming fixes.
Every spawn brief must state: "your plain text is invisible; deliver the report via SendMessage to <recipient>", including the recipient name.
