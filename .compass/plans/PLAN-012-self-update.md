---
title: "Self-Update (compass self-update, the SessionStart entry, plugin.yaml commit field)"
type: plan
status: done
completed: 2026-08-28
approved: 2026-08-28
confidence: high
area: methodology
tags: [update, hooks, session-start, cli, distribution]
created: 2026-08-28
updated: 2026-08-28
author: "orchestrator"
summary: "implement ADR-015: self_update command with sha gate and local-source mode, SessionStart(startup) hook entry, setup/update skill alignment, live acceptance in this repo"
depends_on: ["[[SPEC-020-compass-updates-itself]]", "[[ADR-015-self-update-on-session-start]]", "[[RESEARCH-self-update-surfaces]]"]
---

# Self-Update

## Goal

Every session starts on current Compass with zero human action. Implements every D of [[ADR-015-self-update-on-session-start]].

Approved 2026-08-28 under Roger's blanket go ("spec it and gogogo like before"); stations collapsed into the main thread, tests still written red-first.

## Tasks

- [x] TASK-095: `commands/self_update.py` - plugin.yaml read/write, sha gate + throttle, local-source detection, staged apply (copy set, retired-skill removal, settings merge, apply-models), log; `compass self-update` registered (L)
  - Automated: `tests/test_self_update.py` red-first covering gate/throttle/local-mode/merge idempotence/never-nonzero; full suite green.
  - Manual: dry inspection of an apply into a scratch project dir.
- [x] TASK-096: hooks manifest gains SessionStart(startup) self-update entry, 60s timeout; setup + update skills record `commit:` and mention the auto-updater (S, after 095)
  - Automated: manifest parses; doctor still passes.
- [x] TASK-097: live acceptance - run `compass self-update` in this repo (local-source mode applies from plugin/), verify settings.json registration, doctor clean, log row written (S, after 096)
