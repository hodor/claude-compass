---
title: Rolling-Wave Plans - Frontier Waves, Grounded Elaboration, Three-State Coverage
type: decision
status: accepted
area: methodology
tags: [planning, rolling-wave, elaboration, coverage, plan-format]
created: 2026-08-11
updated: 2026-08-11
depends_on: ["[[SPEC-015-rolling-wave-planning]]", "[[RESEARCH-rolling-wave-synthesis]]"]
summary: "frontier waves, grounded elaboration at the merge gate, three-state coverage (detailed/scoped/uncovered)"
---

# Rolling-Wave Plans: Frontier Waves, Grounded Elaboration, Three-State Coverage

## Context

[[SPEC-015-rolling-wave-planning]] (approved, D-02..D-04 ruled) requires plan detail to track proximity, with a build-learn-elaborate loop. Research across flow theory, software practice, and agent planning ([[RESEARCH-rolling-wave-synthesis]]) converged on a composable rule set; the coverage-over-graded-detail piece has no precedent and is designed here from HTN decomposition states.

## Decision

- **D-01 (plan format):** A plan holds one **detailed wave** (tasks in today's full task-block form: files, decisions:, lessons:, verification, sizes) and a **later list**: one line per future task - intent plus, where known, the artifacts it touches. The boundary is a literal `## Later (intent only)` heading. A later line may carry `commit-upfront` with a one-line reason when detail is genuinely known now or late change is structurally expensive; such tasks are written in full despite distance.

- **D-02 (prototype tasks):** A near task may be `kind: prototype`: a named question in its block, the answer as its deliverable (recorded in the elaboration record, not shipped code). Prototypes satisfy the testing mandate by their nature - their output is an answer, not production behavior (SPEC-015 D-02).

- **D-03 (wave boundary):** A wave is what is workable now within one coherent phase or concern, judged by the planner (and re-judged at elaboration) - no numeric caps (SPEC-015 D-03). It ends at the first task whose specification depends on an outcome not yet observed; it is never a single task unless only one is workable.

- **D-04 (the loop):** When a wave's tasks complete and verify (the build flow's existing merge gate), the orchestrator runs the **elaboration step**: read the wave's verified outcomes (test results, reports, prototype answers), rewrite the next coherent set of later-lines into full task blocks, and append a `## Wave N elaborated` section to the plan recording what was learned and *why* any detail differs from the original intent line. Far intent lines are never edited in place; they are consumed (moved into the detailed wave) or explicitly superseded in the wave section. Elaboration fires only on verified completion - never on cadence, never on the planner re-reading its own text.

- **D-05 (approval):** The human approves the plan once: detailed wave + later list + the declared shape. Elaboration is presented as a short delta at the wave boundary (what was learned, what the next wave is) and proceeds without re-approval. Shape changes (scope, dropped goals, new phases) remain plan-iteration with the human gate, exactly as today.

- **D-06 (coverage):** `compass coverage` and `lesson-coverage` treat tasks by state: **detailed** tasks must cite as today (uncovered fails); **intent** lines are `scoped` - reported, never failing, but every spec decision must be claimed by at least one detailed-or-scoped task so nothing silently vanishes; a task that elaborates without its citations is an ordinary uncovered failure at that point. The gate output gains a `scoped` column.

- **D-07 (record):** The `## Wave N elaborated` sections are the elaboration record: wave outcomes consumed, lines elaborated, deviations from intent with reasons. `compass` needs no new command for v1; the validator's existing plan-vs-implementation audit reads the wave sections.

## Rejected

Per-wave re-approval; fixed-size or single-task waves; a formal middle detail tier; in-place rewriting of intent lines; readiness checklists (a Definition-of-Ready becomes the heavyweight gate the spec falsifies on); bare elaboration counters; any invented detail-decay formula; cost-of-delay ordering in v1.

## Consequences

- Planner brief changes from "specify all tasks" to "specify the current wave fully, list the rest as intent, flag commit-upfront exceptions".
- Build skill gains the elaboration step at its existing merge gate; fix loop, checkpoints, and test-first station unchanged.
- Coverage CLI learns the three states; plans with no `## Later` section behave exactly as today (fully-detailed plans remain valid).
- The gradient's safety rests on the testing mandate: verified waves are what make deferred detail cheap to add later.
