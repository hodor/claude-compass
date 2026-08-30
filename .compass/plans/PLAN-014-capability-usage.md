---
title: "Capability Index and Usage Record (usage.py, dispatch recording, doctor row, retirements)"
type: plan
status: done
completed: 2026-08-29
approved: 2026-08-29
confidence: high
area: architecture
tags: [discoverability, usage-measurement, cli, dead-code]
created: 2026-08-29
updated: 2026-08-29
author: "orchestrator"
summary: "implement ADR-017: usage recording in dispatch, compass usage report with explicit never-used group, doctor advisory, clean-tmp/tree retirement, reachability line and methodology note; ship v0.12.0 via push + fleet self-update"
depends_on: ["[[SPEC-017-capabilities-are-reachable-and-measured]]", "[[ADR-017-capability-index-and-usage-record]]"]
---

# Capability Index and Usage Record

## Goal

Implements every D of [[ADR-017-capability-index-and-usage-record]]. Approved 2026-08-29 under the standing go ("continue with the other specs until we're done"); stations collapsed into the main thread, tests red-first.

## Tasks

- [x] TASK-101: `commands/usage.py` - `record()` wired into `maincli.dispatch`, `compass usage` report with hook/judgment/never-used groups; adversarial tests red-first (M)
- [x] TASK-102: doctor advisory row for never-used commands (S, after 101)
- [x] TASK-103: retire `clean-tmp` and `tree`; reachability line in compass-agent-patterns rule; methodology capability note naming resolve-model/touched/admit-check and `compass usage` (S, after 101)
- [x] TASK-104: suite green, v0.12.0, push, fleet vault pull verified (S, after 102/103)
