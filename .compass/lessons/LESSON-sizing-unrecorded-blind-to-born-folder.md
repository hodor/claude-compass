---
title: "validate's sizing_unrecorded check can't tell born-folder from unreconciled promote"
type: lesson
status: active
category: domain
area: methodology
tags: [sizing, validate, reconciliation, born-folder]
created: 2026-08-28
updated: 2026-08-28
score: 5
summary: "sizing_unrecorded fires on every spec since SPEC-016 D-06 made folder the birth shape, drowning real reconciliation failures"
source: "extract-lessons:signal:OPP-20260828T192024669919Z"
seen: []
---

TASK-081's `sizing_unrecorded` check flags any spec whose frontmatter lacks a `sizing_id`. SPEC-016 D-06 made every spec born a folder, so born-folder specs never get one and can never satisfy it. The check has no way to tell a legitimately born-folder spec apart from a promote that skipped recording its `sizing_id`. Result: the warning now fires on every spec, drowning the one signal it exists to catch.
