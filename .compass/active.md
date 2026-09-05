---
title: Active Tasks
updated: 2026-08-24
---

# Active Tasks

## PLAN-017 dsh host support - Wave 1 (approved 2026-09-05)

- [x] TASK-001: stand up a live dsh rig - install dsh, scratch dual-host project, record version + harness home ([[PLAN-017-dsh-host-support]])
- [x] TASK-002: hand-author the minimal Compass profile bundle; prove a vault write inside dsh fires compass sync
- [x] TASK-003: live probe - Stop-block contract, capture loop survival, SessionStart source literal
- [x] TASK-004: instruction-surface placement matrix - each host loads each instruction exactly once
- Pause point after Wave 1: human confirms manual verification before any Later wave elaborates.

## Sizing + discoverability initiative

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Per-domain organization initiative

- [ ] D-13 follow-up: grep across all indexes made the most obvious first move for agents (capability + rule nudge; folds into TASK-119's strategy work)
- [ ] v0.15.0's premature skill/sync edits were reverted; index depth-0 rule stays (shipped); everything further waits on the plan.

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (iwyc-unreal), 4 were push-rejected behind their remotes (3 ue5-editor-mcp checkouts + wt-spec056) and need a human pull/rebase call. pg-jira-exporter's remote no longer exists.
