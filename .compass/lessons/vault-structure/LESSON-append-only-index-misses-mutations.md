---
title: Append-only derived indexes miss source mutations
type: lesson
status: active
category: process
area: methodology
tags: [derived-index, sync, append-only, staleness, catalog]
created: 2026-08-06
updated: 2026-08-31
score: 6
summary: "Derived-index repair must be active, and every prune gated on provable coverage, or self-healing self-destroys."
seen: [2026-08-24]
---

A derived index that only appends rows never reflects mutations to its sources; a field set on a source after its row exists silently never propagates.
Either the regenerator rewrites existing rows, or the writer that mutates a source owns updating its row - one of the two must hold for every field consumers key on.
The same active-repair drive cuts both ways: a pruner must gate every drop on the dropped text provably existing elsewhere (summary/title match), or self-healing becomes self-destroying.
Success must be recorded from the observed change, never from having attempted it, and byte-identical duplicates already present must be collapsed too, not just guarded against on add.

## Record (preserved)

Seen twice in one day with the lessons catalog: a revised summary and an escalation flag both stalled in stale rows until the mutating writer took ownership.
Ownership is not enough when success is recorded on attempt: a heal pass whose in-place rewrite matched nothing still counted the rewrite and marked the record indexed, so the stale entry was never revisited and the breakage became permanent.
A second writer's byte-identical duplicate row is invisible to append-side dedup entirely - the healer must also collapse duplicates already present, not just guard what it is about to add.
