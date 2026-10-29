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

- [ ] TASK-129: Run the completeness scorer on a real spec and research
- [ ] TASK-131: Exercise every shipped retriever against its live source
- [ ] TASK-135: Autopilot research calls the research entry point

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

## PLAN-022: review documents in Obsidian

Plan: [[PLAN-022-review-in-obsidian]] (files and verification per task).

- [ ] TASK-168: setup/update install the plugin; doctor walks the human through enabling it - complexity: M, depends_on: TASK-165
- [ ] TASK-169: review inbox and lessons table as Bases - complexity: S, depends_on: none

## PLAN-024 Wave 5: views agents write, and a real plan

Plan: [[PLAN-024-working-in-compass-is-visual]].

- [x] TASK-207: A view an agent writes, named by `view:` and kept under `views/` - complexity: M

## PLAN-026 Stage 1: local additions tell the truth

Plan: [[PLAN-026-local-additions-tell-the-truth]].

- [x] TASK-229: `compass overlay` knows four states per addition, and `--apply` replaces an out-of-date block - complexity: M
- [x] TASK-230: The doctor row reads the four states - complexity: S, depends_on: TASK-229
- [x] TASK-231: The update notice names what it re-applied - complexity: S, depends_on: TASK-229
- [ ] TASK-232: dsh gets local additions - complexity: M, depends_on: TASK-231
- [ ] TASK-233: Release build and offline round-trip - complexity: S, depends_on: TASK-230, TASK-232
