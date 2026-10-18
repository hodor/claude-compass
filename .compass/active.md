---
title: Active Tasks
updated: 2026-09-13
---

# Active Tasks

## Sizing + discoverability initiative

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Per-domain organization initiative

- [ ] D-13 follow-up: grep across all indexes made the most obvious first move for agents (capability + rule nudge; folds into TASK-119's strategy work)
- [ ] v0.15.0's premature skill/sync edits were reverted; index depth-0 rule stays (shipped); everything further waits on the plan.

## Research covers the whole spec (SPEC-023)

- [ ] [[specs/pipeline/SPEC-024-walled-sources-through-the-browser]] awaits the human's ruling.
- [ ] Open: a text-and-data-mining request to ACM is the human's to send if wanted.

## PLAN-018 Wave 2: prove the stop rule, exercise the list, close the autopilot gap

Plan: [[PLAN-018-research-covers-the-whole-spec]]. Wave 1 shipped as v0.24.0 on 2026-09-14; its manual checks await the human. Wave 2 starts on his word.

- [ ] TASK-129: Run the completeness scorer against a real spec and a real research document and record whether it detects a gap a human agrees is a gap - files: [.compass/research/pipeline/RESEARCH-spec-coverage-experiment.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-05], commit-upfront: the experiment's shape is inferred from the code contract and fixed now, because a later change to it would invalidate everything written against its result
- [ ] TASK-131: Exercise every shipped retriever against its live source and record the result beside the entry - complexity: S, depends_on: none, files: [plugin/cli/sources.yaml, plugin/cli/tests/test_sourceslib.py], decisions: [SPEC-023-research-covers-the-whole-spec/D-09, SPEC-023-research-covers-the-whole-spec/D-03]
- [ ] TASK-135: Make the autopilot research step call the entry point, so a pipeline run gets the derivation, the axis gate and the grading disclosure - complexity: S, depends_on: none, files: [plugin/skills/autopilot/SKILL.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-01, SPEC-023-research-covers-the-whole-spec/D-05]

## PLAN-019: stop and suggest a handoff at 80% context

Plan: [[PLAN-019-stop-at-80-percent-context]]. TASK-137 and TASK-138 shipped as v0.26.0.

- [ ] TASK-139: Live acceptance in an interactive Claude Code session - the human watches the stop and the handoff (`COMPASS_CONTEXT_THRESHOLD` lowers the line).

## PLAN-020: clone old sessions to harvest their lessons

Plan: [[PLAN-020-clone-old-sessions]].

- [ ] TASK-146: Live acceptance on this repo

## PLAN-021 Wave 1: control loops

Plan: [[PLAN-021-control-loops]].

- [x] TASK-147: `loops` becomes a vault artifact type
- [x] TASK-148: `looplib`: definition, state machine, state file, ledger and lock
- [ ] TASK-149: `sensorlib`: result event, domain sensor, budget sums, change judgment
- [ ] TASK-150: `compass loop` new, status, activate, pause, resume, review
- [ ] TASK-151: `looprunner`: one iteration, the dry run and the dampener
- [ ] TASK-152: The fix loop tells a helpful cycle from a harmful one
- [ ] TASK-157: Ship 0.28.0 and run a loop live in a scratch project

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (private-project-e), 4 were push-rejected behind their remotes (3 private-project-f checkouts + wt-spec056) and need a human pull/rebase call. private-project-g's remote no longer exists.
