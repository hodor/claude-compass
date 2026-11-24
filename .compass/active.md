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

- [ ] TASK-161: The ast-grep sensor adapter, pinned to saved scan output - complexity: M, depends_on: TASK-158, TASK-159, TASK-236
- [ ] TASK-160: `/compass:loop`: guided creation through steps 0 to 7 - complexity: M, depends_on: TASK-158, TASK-159, TASK-161
- [ ] TASK-162: The Maya recipe on the local lane, marked untested on this machine - complexity: S, depends_on: TASK-160
- [ ] TASK-163: Teach the vault conventions about loops and ship the next minor release - complexity: M, depends_on: TASK-158, TASK-159, TASK-160, TASK-161, TASK-162, TASK-236

## PLAN-028 Wave 1: the pilot

Plan: [[PLAN-028-whole-overhead-on-real-projects]]; each task's full text, files and checks are there.

- [ ] TASK-249: You grade four pilot builds - complexity: S, depends_on: TASK-248
## PLAN-031 Wave 1: prove screenplays on real editors

Plan: [[PLAN-031-screenplays-in-the-vault]]; each task's full text, files and checks are there.

- [ ] TASK-287: Live check 1, round-trip hashes - complexity: S, depends_on: TASK-286
- [ ] TASK-288: Live check 2, links on the current Obsidian build - complexity: S, depends_on: TASK-286
- [ ] TASK-289: Live check 3, an agent's edit reloads in both editors - complexity: S, depends_on: TASK-286
- [ ] TASK-290: Live check 4, install the way Compass will - complexity: S, depends_on: TASK-286
- [ ] TASK-291: Live check 5, the two previews side by side - complexity: S, depends_on: TASK-286

## PLAN-034 Wave 1: checking cost follows task and model

Plan: [[PLAN-034-checking-cost-follows-task-and-model]]; each task's full text, files and checks are there.

- [ ] TASK-350: Letter repeatability, measured - complexity: M, depends_on: none
- [ ] TASK-351: Two smoke builds on the subscription, one at a time - complexity: S, depends_on: TASK-343, TASK-346, TASK-349
- [ ] TASK-352: The per-part spread pilot - complexity: M, depends_on: TASK-344, TASK-345, TASK-351

## PLAN-036 Wave 1: verification beyond test-pass

Plan: [[PLAN-036-verification-beyond-test-pass]]; each task's full text, files and checks are there.

- [ ] TASK-412: The planted-defect probe, the spec's KPI. `bench/verification/planted.py` builds a throwaway Python project in a temp folder with its... - complexity: M, depends_on: TASK-411

## PLAN-033 Wave 4: the task in progress and the judge

Plan: [[PLAN-033-compaction-keeps-the-session-state]]; each task's full text, files and checks are there. The human approved the subscription runs with the arm comparison.

- [ ] The human marks the 40 answers of the judge's grading sheet under the probe's private root; `python bench/overhead/probe_judge.py agreement` then prints the agreement.

## PLAN-033 Wave 5: the summary names the task in progress

Plan: [[PLAN-033-compaction-keeps-the-session-state]]; each task's full text, files and checks are there. The human approved this wave and its subscription runs on 2026-11-24.

- [x] TASK-438: The PreCompact instructions name the task in progress - complexity: S, depends_on: TASK-437
- [ ] TASK-439: The probe gains two re-compaction arms, `recompact-task` and its control `recompact` - complexity: M, depends_on: TASK-438
- [ ] TASK-440: Run both arms on every point; results on the reference-arms page - complexity: S, depends_on: TASK-439

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
