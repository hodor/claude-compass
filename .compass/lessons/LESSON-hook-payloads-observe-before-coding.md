---
title: Hook integrations are built against an observed payload, never an assumed one
type: lesson
status: active
category: process
area: workflow
tags: [hooks, payloads, instrumentation, integration, evidence]
created: 2026-08-08
updated: 2026-08-08
score: 5
summary: "Capture one real event payload (tee to a file) before keying logic on its fields; assumed shapes ship dead code"
seen: []
---

Code keyed on an assumed hook-payload field ships silently dead: the branch never fires and nothing reports it.
Two same-week instances: TeammateIdle (assumed agent_type/message; carries only teammate_name) and SubagentStop (agent_type arrives as an empty string for teammate-style agents, no name field at all).
Before keying logic on any event field, capture one real payload - a `tee -a file.jsonl` prepended to the hook command costs one line and settles the shape.
Then pin a regression test to the observed shape, not the documented one.
