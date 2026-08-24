---
title: Append-only derived indexes miss source mutations
type: lesson
status: active
category: process
area: methodology
tags: [derived-index, sync, append-only, staleness, catalog]
created: 2026-08-06
updated: 2026-08-24
score: 6
summary: "Append-only derived indexes miss both stale mutations and second-writer duplicates; repair must be active, not assumed."
seen: [2026-08-24]
---

A derived index that only appends rows never reflects mutations to its sources; a field set on a source after its row exists silently never propagates.
Either the regenerator rewrites existing rows, or the writer that mutates a source owns updating its row - one of the two must hold for every field consumers key on.
Seen twice in one day with the lessons catalog: a revised summary and an escalation flag both stalled in stale rows until the mutating writer took ownership.
Ownership is not enough when success is recorded on attempt: a heal pass whose in-place rewrite matched nothing still counted the rewrite and marked the record indexed, so the stale entry was never revisited and the breakage became permanent - record the update from the observed change, never from having tried.
A third blind spot: a second writer's byte-identical duplicate row is invisible to append-side dedup entirely - the healer must also collapse duplicates already present, not just guard what it is about to add.
