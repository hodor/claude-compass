---
title: "A code sweep for a duplicated config value misses copies embedded in skill prose"
type: lesson
status: active
category: process
area: workflow
tags: [hooks, config-duplication, code-sweep, skill-templates]
created: 2026-09-05
updated: 2026-09-05
score: 5
summary: "A code sweep for a duplicated config value misses copies embedded in skill prose or templates"
source: "extract-lessons:signal:OPP-20260905T222650145324Z"
seen: []
---

TASK-014 swept three copies of the PostToolUse matcher pattern; a fourth lived in the update skill's own translation script, embedded in prose rather than structured config.
A sweep tuned to config-file shapes misses copies inside skill markdown or generator templates.
Search prose and template text too when deduplicating a value, not only config files.
