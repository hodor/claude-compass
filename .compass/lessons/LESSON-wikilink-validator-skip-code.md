---
title: Matchers must match use, not mention
type: lesson
status: active
category: process
area: workflow
tags: [validation, false-positives, content-aware, parsing, self-reference]
created: 2026-05-27
updated: 2026-08-11
score: 5
summary: "Match use, not mention: strip code spans and anchor to grammar position; a doc describing a mechanism trips its trigger"
seen: []
---

Markdown writers use `[[NAME]]` inside backticks as examples; a naive resolver flagged 7 false positives to 1 real bug, so validators strip fenced blocks and inline code spans before resolving.
Stripping code is not enough. A document that describes a mechanism carries that mechanism's trigger tokens as plain prose: PLAN-008's `commit-upfront` rule matched the bare word anywhere in a task line, and two of its own intent lines mention the flag while describing it, which classifies them detailed and makes the plan's own acceptance test unpassable.
Match use, not mention: anchor to the token's position in the grammar (a `field:` in the fields segment), never to the word appearing anywhere in a line that also carries free prose.
Content-aware matchers must respect code-block scope, quoted regions, and self-reference.
