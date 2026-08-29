---
title: "Handoff: v0.9.0-v0.13.0 shipped in one arc; remaining queue sits at human gates"
type: handoff
status: active
area: methodology
tags: [handoff, release, sweep, self-update, humans-words, usage, graph]
created: 2026-08-29
updated: 2026-08-29
summary: "five specs shipped end to end (active sweep, self-update, capture-by-extraction, capability usage, graph queries), fleet self-updating; next: SPEC-006 research session, SPEC-014 promotion ruling, SubagentStop payload observation"
---

# Handoff: Five Releases, Queue at Human Gates

## Where things stand

Five pipelines ran spec-to-fleet across 2026-08-28/29, all committed and pushed, fleet verified on each:

- v0.9.0 [[SPEC-019-active-holds-only-active-work]] / [[ADR-014-active-sweep-on-sync]] - sync sweeps done tasks to archive/done.md.
- v0.10.0 [[SPEC-020-compass-updates-itself]] / [[ADR-015-self-update-on-session-start]] - SessionStart self-update, mandatory, sha-gated; last manual fleet wave ever (53/53 doctor-ok).
- v0.11.0 [[SPEC-021-capture-in-the-humans-words]] / [[ADR-016-capture-by-extraction]] - interview skills extract-and-arrange the human's sentences.
- v0.12.0 [[SPEC-017-capabilities-are-reachable-and-measured]] / [[ADR-017-capability-index-and-usage-record]] - dispatch-recorded usage, `compass usage`, doctor advisory, clean-tmp/tree retired.
- v0.13.0 [[SPEC-011-vault-graph-queries]] / [[ADR-018-graph-queries-jit-over-markdown]] - `compass graph` orphans/hubs/impact, unit-check hub guard, planner ripple step.

## Start here next session

1. **SubagentStop typed-signal fix** (backlog, evidence in `tmp/subagentstop-payloads.jsonl` note): FIRST observe whether an inline Agent-tool spawn populates `agent_type` - instrument, spawn one, read the payload ([[LESSON-hook-payloads-observe-before-coding]]). Then type from TeammateIdle side or retire SIGNAL_KINDS honestly.
2. **SPEC-006 multi-host (hermes first)**: needs its own research session - hermes host surface for Compass's hooks/CLI/skills. Big; treat as a fresh pipeline.
3. **Roger's gates**: [[SPEC-014-update-safe-customizations]] promotion ruling; pin the seven-monster-specs project ([[LESSON-pin-the-motivating-datum]]) - only he knows which project it was.

## Known small items

- doctor's unit-promotion labels show "index" for born-folder specs (capture-note filed 2026-08-28).
- Hot path still over aggregate cap (index 4.5K + catalog 3K); `/compass:consolidate` is the responder when Roger wants it.
- F:/Creative/calendar vault: 227 true orphans per the new query - that vault's own concern.
