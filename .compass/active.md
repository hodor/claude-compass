---
title: Active Tasks
updated: 2026-08-24
---

# Active Tasks

## GitHub issues from live v0.17 use (filed 2026-08-31)

- [ ] Fix and test #14 - sync lists depth>0 folder children in the root index (ADR-021 D-01)
- [ ] Fix and test #15 - make-domain refuses unit-internal paths
- [ ] Fix and test #16 - fix-frontmatter cannot add `summary:` although validate warns on it
- [ ] Fix and test #17 - `_sync_index` is append-only, never prunes relocated entries
- [ ] Fix and test #18 - no link-preserving move for domain grouping in make-domain
- [ ] Fix and test #19 - validate flags abbreviated bare-stem wikilinks that rules/wikilinks.md sanctions
- [ ] Fix and test #20 - consolidate skill states a false premise that destroys information (Step 7)

## Sizing + discoverability initiative

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Per-domain organization initiative

- [ ] D-13 follow-up: grep across all indexes made the most obvious first move for agents (capability + rule nudge; folds into TASK-119's strategy work)
- [ ] v0.15.0's premature skill/sync edits were reverted; index depth-0 rule stays (shipped); everything further waits on the plan.

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (iwyc-unreal), 4 were push-rejected behind their remotes (3 ue5-editor-mcp checkouts + wt-spec056) and need a human pull/rebase call. pg-jira-exporter's remote no longer exists.
