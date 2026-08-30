---
title: "Active Sweep (compass sweep, the sync step, drift warning, doc alignment)"
type: plan
status: done
completed: 2026-08-28
approved: 2026-08-28
confidence: high
area: methodology
tags: [active-tasks, sweep, sync, cli, hot-path]
created: 2026-08-28
updated: 2026-08-28
author: "orchestrator"
summary: "implement ADR-014: sweep module with dry-run CLI command, wired into sync, validate drift warning, builder/build/checkup doc updates, live acceptance on this vault"
depends_on: ["[[SPEC-019-active-holds-only-active-work]]", "[[ADR-014-active-sweep-on-sync]]", "[[RESEARCH-active-set-prior-art]]"]
---

# Active Sweep

## Goal

`active.md` holds only active work. Implements every D of [[ADR-014-active-sweep-on-sync]].

Approved 2026-08-28 by the standing go ("don't ask"); stations collapsed into the main thread on that instruction - tests still written adversarially before the implementation.

## Tasks

- [x] TASK-091: `commands/sweep.py` - parser + sweep engine + `compass sweep` (dry-run default, `--apply`) (M)
 - Automated: new adversarial tests in `tests/test_sweep.py` red-first, then green; full suite green.
 - Manual: dry-run output on a copy of this vault's active.md names the expected sections/items.
- [x] TASK-092: wire sweep into `sync()` + report line; `validate` gains `active_done` warning (S, after 091)
 - Automated: sync tests prove the step runs in both modes and self-reports; validate test proves warning fires and exit code unchanged.
- [x] TASK-093: doc alignment - builder.md checkoff wording, build SKILL step 9, checkup task hygiene, CLAUDE.md vault tree (S, after 092)
 - Automated: grep proves no doc still claims `[x]` lines persist in active.md.
 - Manual: read-through.
- [x] TASK-094: local install refresh + live acceptance on this vault (S, after 093)
 - Automated: `compass sweep` dry-run then `--apply` (via sync) on the real active.md; `compass validate` 0 errors; hot-path breakdown shows active.md shrunk.
 - Manual: active.md reads as only-active; done.md holds every reaped line verbatim.
