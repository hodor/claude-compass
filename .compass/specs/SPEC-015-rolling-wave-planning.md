---
title: Plans Elaborate Progressively - Detail Tracks Proximity, Not the Whole Plan Upfront
type: spec
status: approved
approved: 2026-08-11
confidence: high
area: methodology
tags: [planning, rolling-wave, progressive-elaboration, plan-approval, feedback-loop]
created: 2026-08-11
updated: 2026-08-11
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]"]
summary: "plan detail tracks proximity; waves elaborate from completed-task knowledge (draft)"
---

# Plans Elaborate Progressively - Detail Tracks Proximity, Not the Whole Plan Upfront

## Problem

Compass plans specify every task at full detail before any task runs, and the human approves the whole plan at once. But every completed task produces knowledge the plan's later tasks were written without - so far-away tasks are specified at a precision the planner does not actually have, the human approves detail that is partly fiction, and when reality diverges the choice is a plan-iteration ceremony or silent drift. The observed cost: builders hitting "the codebase contradicts the plan" stops on tasks specced many tasks ago, and plan amendments landing mid-build to re-litigate detail that was never really known. (Roger, 2026-08-11: "every task we complete will give us more knowledge to make the plan better... focus on what's in front of us with more details, and things that are far away we put less details on.")

## Who is affected

- The planner, forced to invent uniform detail for tasks whose ground it cannot see yet.
- The human, who approves a wall of speculative detail once instead of a sequence of informed, small commitments.
- Builders, who execute stale far-task specifications or stop on mismatches.
- The plan document, which drifts from reality unless ceremonially re-approved.

## Decisions (made by the human)

- **D-02:** The near, detailed work includes prototype tasks when a question blocks later detail: a prototype exists to answer a named question, and its answer is elaboration input like any other completed-work knowledge. (Roger, 2026-08-11.)
- **D-03:** A wave is what can be worked on right now within one coherent phase or concern. No numeric cap and no size budget - agents judge the boundary themselves. Size-rationing is a human-era planning concept; AI build speed makes it noise. (Roger, 2026-08-11.)
- **D-04:** Two detail tiers only: fully detailed now, one-line intent later. No formal middle band - the loop elaborates a one-liner the lap before it is built. (Roger, 2026-08-11, accepting the synthesis recommendation.)

## Desired Outcome

A plan commits detail in proportion to proximity: the next task or wave is fully specified (files, verification, sizes); later work is scoped at decreasing precision down to named intent. As tasks complete, the knowledge they produce elaborates the next wave, and the human's approval attaches to the near detail plus the far shape - never to speculative fine print. Re-elaboration is a normal, cheap pipeline step, not a plan-amendment ceremony.

## Needs

- A plan format expressing graduated detail: full specification near, scope-and-intent far, with the boundary explicit.
- Prototype tasks are first-class near work: named question in, answer out, the answer feeding the next elaboration.
- An elaboration step at wave completion that turns new knowledge into the next wave's full detail, traceable to what was learned.
- Approval semantics matching the gradient: approving a plan approves the near detail and the far shape; each elaborated wave is presented at its turn without re-approving the whole.
- Decision and lesson coverage still hold: D-NN and lessons: citations bind at the detail level when a wave elaborates, so tracing never weakens.
- The existing plan-iteration flow remains for genuine shape changes (scope, phases); elaboration is distinct from amendment.
- Works with the existing build flow (test-first station, checkpoints, fix loop) unchanged.

## Hypothesis (falsifiable)

If detail tracks proximity and waves elaborate from completed-task knowledge, then mid-build plan amendments and codebase-contradicts-plan stops drop, without loss of decision coverage or verification rigor in the tasks actually executed.

## Falsification criteria

- Far-task under-specification degenerates into improvisation: builders start without the full detail a near wave requires.
- Elaboration becomes its own approval ceremony as heavy as the plan approval it replaces.
- Coverage gates (decisions, lessons) weaken because citations defer past the point where the work happens.

## Success criteria

- A real plan runs its full life with at least two elaboration steps, zero whole-plan re-approvals, and coverage gates PASS at completion.
- A knowledge item from a completed wave demonstrably changes a later wave's detail (traceable in the elaboration record).
- Human approval touchpoints per plan do not increase versus today.

## Non-Goals

- Pipeline shape configuration ([[SPEC-009-configurable-pipeline-workflows]], deferred) - this changes detail gradient within a plan, not which phases exist.
- The human-review-model redesign (backlog, 2026-06-14) - adjacent: it asks WHERE review lands; this spec asks what detail exists to review. The research phase should read them together.
- Removing plan approval as a gate.

## Open questions (for research, after approval)

- Wave boundary in practice: how the planner states "one coherent phase or thing" so builders and the coverage gate agree where the wave ends (D-03 rules out numeric caps).
- Where the elaboration record lives (plan appendix vs per-wave section) and what the build skill's wave boundary triggers.
- How the coverage gate treats far tasks whose citations are not yet elaborated (deferred-but-tracked vs uncovered).
- What the planner's brief changes from "specify all tasks" to "specify the frontier, scope the rest".
