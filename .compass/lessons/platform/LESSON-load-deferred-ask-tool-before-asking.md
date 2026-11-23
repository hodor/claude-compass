---
title: Load a deferred AskUserQuestion before asking
type: lesson
status: active
category: process
area: workflow
tags: [askuserquestion, toolsearch, deferred-tools, claude-code, gates]
created: 2026-10-30
updated: 2026-10-30
score: 5
summary: "AskUserQuestion can be a deferred tool in Claude Code; load it with ToolSearch before a gate question or the question silently degrades to plain text"
source: extract-lessons:OPP-20261030T151159005530Z
seen: []
---

Claude Code can list `AskUserQuestion` among deferred tools: only its name is known and its schema is not loaded, so calling it fails.
An agent that skips the load falls back to plain text, and the pipeline's one-question-per-call numbered-options gate is lost.
Before the first gate question, run `ToolSearch` with `select:AskUserQuestion`; fall back to numbered text lines only when no such tool exists.
