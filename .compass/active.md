---
title: Active Tasks
updated: 2026-08-24
---

# Active Tasks

## Sizing + discoverability initiative (Roger, 2026-08-23)

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] NEXT: research both specs, then one ADR. Open axes: SPEC-016's mechanism (skill step vs hook vs CLI gate), SPEC-017's index location.
- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Scaffolding-noise initiative (Roger, 2026-08-24)

- [ ] [[SPEC-018-scaffolding-invisible-to-the-human]] drafted, awaiting promotion. D-01 scaffolding stays hidden not removed; D-02 agents run the show between gates.

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-014-update-safe-customizations]] approval + research (issue #6).
- [ ] [[SPEC-011-vault-graph-queries]] pipeline: research/ADR on substrate, then planner consumer.
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (iwyc-unreal), 4 were push-rejected behind their remotes (3 ue5-editor-mcp checkouts + wt-spec056) and need a human pull/rebase call. pg-jira-exporter's remote no longer exists.
