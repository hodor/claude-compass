---
title: "validate's sizing_unrecorded check can't tell born-folder from unreconciled promote"
type: lesson
status: active
category: domain
area: methodology
tags: [sizing, validate, reconciliation, born-folder]
created: 2026-08-28
updated: 2026-08-29
score: 5
summary: "SPEC-016 D-06's folder shape breaks file-stem==spec-name assumptions: sizing check, doctor suggested-name"
source: "extract-lessons:signal:OPP-20260828T192024669919Z"
seen: []
---

TASK-081's `sizing_unrecorded` check flags any spec whose frontmatter lacks a `sizing_id`. SPEC-016 D-06 made every spec born a folder, so born-folder specs never get one and can never satisfy it. The check has no way to tell a legitimately born-folder spec apart from a promote that skipped recording its `sizing_id`. Result: the warning now fires on every spec, drowning the one signal it exists to catch.
Same root cause resurfaces in doctor's unit-promotion `_suggested_name`: it reads `spec_path.stem`, always literally `index` for a folder spec, so the candidate label degrades to "index" instead of the folder's descriptive name - any code deriving a spec's identity from its file path must resolve the containing folder for folder-shaped specs, not the artifact file's stem.
