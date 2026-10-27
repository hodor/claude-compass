---
title: Active Tasks
updated: 2026-09-13
---

# Active Tasks

## Sizing + discoverability initiative

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Per-domain organization initiative

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

## PLAN-021 Wave 2: judge, schedule, ast-grep sensor, skill, release

Plan: [[PLAN-021-control-loops]].

- [ ] TASK-161: A code loop end to end: an ast-grep sensor adapter, then a loop that removes a bad pattern from a real repository the human names, run to its stop - complexity: L, depends_on: TASK-158, TASK-159
- [ ] TASK-160: `/compass:loop`: guided creation through steps 0 to 7 - complexity: M, depends_on: TASK-158, TASK-159, TASK-161
- [ ] TASK-162: The Maya recipe on the local lane, marked untested on this machine - complexity: S, depends_on: TASK-160
- [ ] TASK-163: Teach the vault conventions about loops and ship the next minor release - complexity: M, depends_on: TASK-158, TASK-159, TASK-160, TASK-161, TASK-162

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).

## PLAN-024: working in Compass is visual

Plan: [[PLAN-024-working-in-compass-is-visual]].

- [ ] TASK-190: Trial B, Mermaid charts - after: TASK-189
- [ ] TASK-191: Trial C, bundled Vega-Lite - after: TASK-189
- [ ] TASK-192: Trial D, reading a `.jsonl` ledger - after: TASK-189
- [ ] TASK-193: Trial E, a canvas Compass rewrites - after: TASK-192
- [ ] TASK-195: Mockup: documents - after: TASK-194
- [ ] TASK-196: Mockup: terminal output - after: TASK-194

## PLAN-022: review documents in Obsidian

Plan: [[PLAN-022-review-in-obsidian]] (files and verification per task).

- [ ] TASK-168: setup/update install the plugin; doctor walks the human through enabling it - complexity: M, depends_on: TASK-165
- [ ] TASK-169: review inbox and lessons table as Bases - complexity: S, depends_on: none
