---
title: Long-running subagents can stop mid-run with a progress line; a resume message completes them
type: lesson
status: active
category: process
area: workflow
tags: [subagents, orchestration, stall, resume, turn-limits, monitoring]
created: 2026-07-24
updated: 2026-08-23
score: 6
summary: "A subagent completion notice whose final text reads like mid-task narration is a stall, not a result; resume it with 'continue from exactly where you stopped' instead of respawning"
seen: [2026-08-23]
---

A long-running subagent (many tool calls) can terminate with its last emitted line being mid-task narration ("now running X on all three...") rather than the deliverable report - a stall at a turn boundary, not a completion.
Detect it by reading the final message as a contract: if the brief demanded a structured report and the text is progress prose, the work is unfinished no matter what the completion status says.
Resume the same agent with a message naming where it stopped and restating the remaining deliverables; it continues with full context and finishes. Respawning from scratch loses the accumulated work and context.
The orchestrator owns this check on every completion notice; treating a stall line as a result silently drops the tail of the task.
