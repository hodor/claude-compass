---
title: Glob requires `**/` prefix to traverse hidden directories
type: lesson
status: active
category: process
area: workflow
tags: [glob, hidden-dirs, vault-traversal, tool-quirks]
created: 2026-05-24
updated: 2026-05-24
score: 5
summary: "Glob tool needs `**/` prefix to traverse hidden dirs like .compass/"
seen: []
---

Glob does NOT traverse hidden directories (those starting with `.`) by default.
Pattern `.compass/specs/*.md` returns zero results.
Pattern `**/.compass/specs/*.md` works.
Every skill that globs `.compass/` must use the `**/` prefix.
