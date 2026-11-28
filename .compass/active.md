---
title: Active Tasks
updated: 2026-09-13
---

# Active Tasks

## PLAN-018 Wave 3: how a run detects its own gap

Plan: [[PLAN-018-research-covers-the-whole-spec]].

- [x] TASK-130: The reviewer's spec coverage table checks every Need and Decision against a finding; an empty row is a gap

## PLAN-019: stop and suggest a handoff at 80% context

Plan: [[PLAN-019-stop-at-80-percent-context]]. TASK-137 and TASK-138 shipped as v0.26.0.

- [ ] TASK-139: Live acceptance in an interactive Claude Code session - the human watches the stop and the handoff (`COMPASS_CONTEXT_THRESHOLD` lowers the line).

## PLAN-028 Wave 1: the pilot

Plan: [[PLAN-028-whole-overhead-on-real-projects]]; each task's full text, files and checks are there.

- [ ] TASK-249: You grade four pilot builds - complexity: S, depends_on: TASK-248

## PLAN-031 pause point: the human confirms the live checks

Plan: [[PLAN-031-screenplays-in-the-vault]]. Checks 1 to 5 passed and sit in [[RESEARCH-screenplays-in-the-vault#Live check results]]; the Later tasks are detailed once the human confirms them.

- [x] The human confirms the five live check results.

## PLAN-033 Wave 4: the task in progress and the judge

Plan: [[PLAN-033-compaction-keeps-the-session-state]]; each task's full text, files and checks are there. The human approved the subscription runs with the arm comparison.

- [ ] The human marks the 40 answers of the judge's grading sheet under the probe's private root; `python bench/overhead/probe_judge.py agreement` then prints the agreement.

## PLAN-034 Wave 3: the station ablation by planted defects

Plan: [[PLAN-034-checking-cost-follows-task-and-model]]; the task's full text, files and checks are there. TASK-354 ran and its candidate rubric was not kept.

- [ ] Resume the station-ablation batch after the usage limit resets on 2026-11-30 16:00: 56 of the 100 approved defects are unread; the run commands resume from their progress files
