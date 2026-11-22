---
title: "A Task-Difficulty Class Is Judged Under a Written Rubric and Recorded by the Harness, Never Scored"
type: decision
status: accepted
confidence: medium
area: methodology
tags: [difficulty, checking, sizing, harness, tokens]
created: 2026-11-21
updated: 2026-11-21
author: "orchestrator"
depends_on: ["[[ADR-011-sizing-is-a-procedure-not-a-score]]", "[[specs/tooling/SPEC-027-compass-uses-fewer-tokens/SPEC-034-checking-cost-follows-task-and-model]]", "[[research/whole-overhead/checking-cost/REVIEW-checking-cost]]"]
summary: "ADR-011 D-01 bans numeric scores and computed metrics only; a difficulty class a planner assigns by judgment under a written rubric, with the harness owning the trigger and the record, is allowed"
---

# A Task-Difficulty Class Is Judged Under a Written Rubric and Recorded by the Harness, Never Scored

## Context

[[specs/tooling/SPEC-027-compass-uses-fewer-tokens/SPEC-034-checking-cost-follows-task-and-model]] asks that how much checking a task gets follow the task's difficulty and the model doing it. Doing that needs a difficulty key known before the build. The one pre-build difficulty field today is the planner's `complexity:` letter (S, M or L): assigned by judgment, read by no code, and loose against its own rubric (the review found 59 of 96 S tasks listing more than one file and 20 of 31 L tasks listing fewer than five).

[[ADR-011-sizing-is-a-procedure-not-a-score]] D-01 reads: "No numeric threshold, no computed sizing metric, and no 'count the sub-concerns' rule ships." It was written for the shape of a spec, and its evidence is the failure of a computed cohesion metric. Whether it also covers a difficulty class for checking depth was left open by [[research/whole-overhead/checking-cost/REVIEW-checking-cost]], and the plan for SPEC-034 cannot be shaped before it is ruled.

## Decision

- **D-01:** [[ADR-011-sizing-is-a-procedure-not-a-score]] D-01 reaches numeric scores and computed metrics. It does not reach a difficulty class that a planner assigns by judgment under a written rubric. Such a class is allowed.
- **D-02:** The harness owns the trigger and the record; the planner owns the judgment. This is [[ADR-011-sizing-is-a-procedure-not-a-score]] D-03 applied to tasks: the harness requires the class on every task and writes it down, and the planner decides which class a task is.
- **D-03:** Every assigned class, and every later correction of one, is recorded, as [[ADR-011-sizing-is-a-procedure-not-a-score]] D-08 requires of sizing decisions. A class nobody can compare with what the build showed cannot be found wrong.
- **D-04:** No numeric difficulty score, no threshold over a computed value, and no rule deriving the class from a count (such as the number of files a task lists) ships under this ruling. A proposal of one is a new fork and needs its own evidence under [[ADR-011-sizing-is-a-procedure-not-a-score]] D-01.

## Rationale

D-01 of the earlier ADR is forced by evidence about computing a judgment over code, and its text names scores, thresholds and computed metrics. A class assigned by reading a task against a written rubric is the procedure that ADR chose for spec shape (a directed judgment the harness triggers and records), applied to a new object. Reading the ban wider than its words would also bar the letter Compass already assigns by judgment.

Recording is what makes the judgment correctable. The review found that reading a class back from a plan is deterministic and assigning it is not, so the weak step is the assignment, and the record is how that step is measured.

## Consequences

Good:
- Checking depth can key on a class known before the build, so the rule for [[specs/tooling/SPEC-027-compass-uses-fewer-tokens/SPEC-034-checking-cost-follows-task-and-model]] has an input that needs no new instrument to read.
- The class sits in the plan, so the same task on the same model gets the same checking level, and the choice is visible for review.
- The ruling stays inside the earlier ADR's own reasoning (harness triggers and records, agent judges) instead of exempting this case from it.

Bad:
- A judged class can drift between planners and between runs; whether a planner's letter is repeatable is untested, and the review names the same open risk for sizing. The repeatability test in TASK-350 of [[PLAN-034-checking-cost-follows-task-and-model]] measures it, and its result may show the rubric is too loose to key anything on.
- A class that drifts toward easy under-checks hard tasks. The escalation rule in the plan (a failing test or fix cycle raises the task to full checking) is the guard, and it is itself unbuilt.
- Judgment in prose costs prompt tokens that a mechanical key would not; this follows the trade [[ADR-011-sizing-is-a-procedure-not-a-score]] accepted.

## Alternatives Considered

The review held three options live for this fork:

**1. D-01 bans numeric scores only; a judged class under a written rubric, recorded by the harness, is allowed (chosen).** It fits D-03 and D-08 of the earlier ADR as written.

**2. D-01 reaches any difficulty key; checking depth follows only observed failure, never a predicted class.** Rejected: it removes the pre-build key, so every task starts at full checking and only a failure can lower or raise anything, which leaves the cost of easy tasks unchanged. It stays available as the fallback if the repeatability test shows no class can be assigned consistently.

**3. D-01 reaches computed keys such as the `files:` count too, and a new ADR states this before planning.** Rejected: the `files:` count is the mechanical signal, and the review's evidence is that it disagrees with the letter in both directions, so it is no firmer a key. It also widens the ban past what its evidence supports.
