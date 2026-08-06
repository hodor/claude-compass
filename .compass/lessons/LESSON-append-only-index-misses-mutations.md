---
title: Append-only derived indexes miss source mutations
type: lesson
status: active
category: process
area: methodology
tags: [derived-index, sync, append-only, staleness, catalog]
created: 2026-08-06
updated: 2026-08-06
score: 5
summary: "Append-only derived indexes miss source mutations; the mutator must update the row or the field never propagates"
seen: []
---

A derived index that only appends rows never reflects mutations to its sources; a field set on a source after its row exists silently never propagates.
Either the regenerator rewrites existing rows, or the writer that mutates a source owns updating its row - one of the two must hold for every field consumers key on.
Seen twice in one day with the lessons catalog: a revised summary and an escalation flag both stalled in stale rows until the mutating writer took ownership.
