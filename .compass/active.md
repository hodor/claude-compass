---
title: Active Tasks
updated: 2026-08-23
---

# Active Tasks

Completed initiatives are one line each; their detail lives in the named plan.

## Shipped

- [x] [[PLAN-001-lessons-and-index-implementation]] - 12 tasks (2026-05-24)
- [x] [[PLAN-002-compass-cli-implementation]] - CLI + command-hook cutover, ~99.8% bookkeeping-token reduction (2026-06-14)
- [x] [[PLAN-003-hybrid-hierarchy]], [[PLAN-004-decision-coverage]], [[PLAN-005-model-table]] - 23/23 tasks, validator BATCH PASS (2026-07-24)
- [x] [[PLAN-006-learning-loop]] - v0.5.0, 16 tasks, VALIDATED 9/9 probes, fleet-wide 2026-08-06. Root cause found en route: hooks load only from settings files ([[LESSON-hooks-load-only-from-settings]]), so no Compass hook had ever fired anywhere before that date.
- [x] [[PLAN-007-test-quality]] - v0.6.0-v0.6.3, 12 live tasks (Phase C parked behind named unpark triggers). The paired experiment validated the bar: Arm B 15/15 vs Arm A 13/15 on 77 tests vs 109 ([[RESEARCH-test-quality-bar-validation]]).
- [x] [[PLAN-008-rolling-wave]] - v0.7.0, 12 tasks across 3 waves + 2 live elaborations, fleet-wide in 48/48 vaults 2026-08-11.

## Sizing + discoverability initiative (Roger, 2026-08-23)

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [x] [[SPEC-016-sizing-work-beyond-one-spec]] APPROVED, D-01..D-05. Both creation paths ship; Compass sizes and acts without asking; the notice is said once and silenceable; internal vocabulary never surfaced; configurable and callable.
- [x] [[SPEC-017-capabilities-are-reachable-and-measured]] APPROVED, D-01..D-02. Adopt both hermes mechanisms (progressive-disclosure index + usage measurement). Audit: `make-unit`, `unit-check`, `admit-check`, `touched`, `resolve-model` reachable from nothing; `clean-tmp` and `tree` redundant with `sync`. Admission control from [[ADR-004-hierarchical-specs-with-facets]] has never run in any vault.
- [x] Two consolidate-gate defects fixed in passing: its trigger markers did not match the literals `sync` writes, and the aggregate hot-path cap had no marker or responder at all. `sync` now writes a hot-path marker carrying a per-file breakdown.
- [ ] NEXT: research both specs, then one ADR. Open axes: SPEC-016's mechanism (skill step vs hook vs CLI gate), SPEC-017's index location.
- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-014-update-safe-customizations]] approval + research (issue #6).
- [ ] [[SPEC-011-vault-graph-queries]] pipeline: research/ADR on substrate, then planner consumer.
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (iwyc-unreal), 4 were push-rejected behind their remotes (3 ue5-editor-mcp checkouts + wt-spec056) and need a human pull/rebase call. pg-jira-exporter's remote no longer exists.
