---
title: Settings-file hook `if` clause works; `||` inside it is untested
type: lesson
status: active
category: process
area: workflow
tags: [hooks, if-clause, permission-rules, plugin-config]
created: 2026-05-24
updated: 2026-11-21
score: 5
summary: "Settings-file hooks support an `if` clause (verified on 2.1.330); `||` inside it is untested, use a pipe matcher"
seen: []
---

Settings-file hook entries accept an `if` clause: on Claude Code 2.1.330 `"if": "Write(*.md)"` fired for a.md and not a.txt.
Whether `||` works inside `if` is untested; select several tools with a pipe matcher (`Write|Edit|MultiEdit`).
Path filtering can still live in the command itself (the compass CLI self-filters non-vault paths and exits 0).

## Record (preserved)
Earlier wording: "Settings-file hook entries have no `if` clause; the documented schema is matcher/command/args/timeout/statusMessage. An `if:` field in a hooks.json manifest is not part of the settings schema; entries registered in settings run on every matcher hit regardless of it." Contradicted by the 2.1.330 trial in [[RESEARCH-axis-2b-host-features-gap]] C3.
