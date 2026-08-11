---
title: Match use, not mention - in matchers and in edit anchors
type: lesson
status: active
category: process
area: workflow
tags: [validation, content-aware, parsing, self-reference, edit-anchors]
created: 2026-05-27
updated: 2026-08-11
score: 5
summary: "Match use, not mention - matchers and edit anchors alike: bind to grammar position, never a substring prose repeats"
seen: []
---

Markdown writers use `[[NAME]]` inside backticks as examples; a naive resolver flagged 7 false positives to 1 real bug, so validators strip fenced blocks and inline code spans before resolving.
Stripping code is not enough. A document that describes a mechanism carries that mechanism's trigger tokens as plain prose: PLAN-008's `commit-upfront` rule matched the bare word anywhere in a task line, and two of its own intent lines mention the flag while describing it, which classifies them detailed and makes the plan's own acceptance test unpassable.
The same hazard hits writes: a scripted replace anchored on the string `## Later (intent only)` matched a backticked prose mention of that heading and spliced a promoted wave mid-paragraph.
Match use, not mention, reading or writing: bind to the token's grammar position (a `field:` in the fields segment, a heading at line start), never to the word appearing anywhere in a line that also carries free prose.
Content-aware matchers must respect code-block scope, quoted regions, and self-reference.
