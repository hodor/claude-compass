---
title: Hook `if` clause does not support `||` boolean OR
type: lesson
status: active
category: process
area: workflow
tags: [hooks, if-clause, permission-rules, plugin-config]
created: 2026-05-24
updated: 2026-08-06
score: 5
summary: "Settings hook entries have no `if` clause; select tools via matcher, filter paths in the command"
seen: []
---

Settings-file hook entries have no `if` clause; the documented schema is matcher/command/args/timeout/statusMessage.
Select tools with a pipe matcher (`Write|Edit|MultiEdit`); filter paths inside the command itself (the compass CLI self-filters non-vault paths and exits 0).
An `if:` field in a hooks.json manifest is not part of the settings schema; entries registered in settings run on every matcher hit regardless of it.
