---
title: Decisions Made in Specs and Discussion Must Survive Into Plans and Validation
type: spec
status: approved
confidence: high
area: methodology
tags: [decision-coverage, traceability, accuracy, gates, planning, validation]
created: 2026-07-22
updated: 2026-07-23
approved: 2026-07-23
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[RESEARCH-gsd-core-improvements-for-compass]]"]
---

# Decisions Made in Specs and Discussion Must Survive Into Plans and Validation

## Problem

A decision made early in the pipeline can silently vanish before it is built. A spec resolves an open question, an ADR settles a trade-off, a research doc rules an approach out - and nothing in Compass mechanically checks that the decision is carried into the plan, executed, and confirmed at validation. The pipeline trusts each stage to remember what the previous stage decided, but memory across stages is exactly what fails: the planner reads the spec and plans most of it, one decision is dropped, the builder never sees it, and the validator has no list of decisions to check against. The loss is invisible until the built thing contradicts a decision everyone thought was settled.

This is the single most common accuracy failure mode in a multi-stage AI pipeline, and it strikes directly at north-star goal 1 (Accuracy) and goal 2 (Perfect memory): a decision that does not reach the plan is a fact the vault silently forgot.

## Who is affected

- The human, who decides something in a spec or ADR and later finds the build ignored it, with no early signal that it was dropped.
- The planner and builder agents, which have no authoritative, checkable list of the decisions their work must honor.
- The validator, which today verifies against the plan and the code but has no decision ledger to audit coverage against.

## Desired Outcome

Every decision recorded in the pipeline is traceable from where it was made, through the plan that must honor it, to the validation that confirms it. When a decision is not accounted for by any plan, the gap is surfaced before build - not discovered after. A decision may be deliberately deferred or delegated, but that must be an explicit, recorded choice, never a silent omission.

## Needs (what a solution must satisfy)

- Decisions in Compass artifacts (specs, ADRs, and the discussion that precedes a plan) are identifiable as discrete, referenceable units - not buried in prose where nothing can point at them.
- A mechanical check can determine whether each decision is covered by the plan, and report the uncovered ones.
- Deliberate non-coverage is expressible and recorded (a decision can be explicitly deferred, delegated to agent discretion, or marked informational) so the check distinguishes "dropped by accident" from "chose not to plan this now."
- The check runs off the agent token budget (it is mechanical bookkeeping, per [[ADR-005-compass-cli-for-mechanical-work]]), and its blocking-vs-warning behavior is a deliberate choice, not agent judgment.
- The mechanism degrades safely: if it cannot parse the decisions it must fail loud (report "could not read decisions"), never silently pass as though there were none to check.
- Validation can audit decision coverage as part of its final gate.

## Decisions (made by the human)

- **D-01:** ADRs are in scope as decision sources. The rulings inside an ADR's Decision section become discrete ID'd units, not only prose; citing the ADR document is not coverage of its individual rulings.
- **D-02:** The fail-loud parsing contract is required: "decisions present but unparseable" must be distinguishable from "no decisions present" and must never pass silently.
- **D-03:* The blocking coverage gate fires at the plan boundary: a plan is not approved while a trackable decision is unclaimed.
- **D-04:** Coverage extends to task level as citation and audit, not as gates: tasks cite the decision IDs they implement, and validation audits each task's cited IDs; there is no mid-build per-task blocking.
- **D-05:** Because statuses and phases are user-configurable ([[SPEC-009-configurable-pipeline-workflows]]), a workflow must declare which status transition carries the coverage gate; the gate is bound to a transition, not hardcoded to one phase name.
- **D-06:** The source and target of coverage are workflow-declared roles, not fixed artifact types: a workflow names which phase's artifacts bear decisions and which phase's artifacts must cover them. The shipped default is specs/ADRs covered by plans/tasks; a custom workflow (e.g. one with no Plan phase, or with a Design phase producing its own decision-bearing docs) binds the same mechanism to its own artifacts.

## Hypothesis (falsifiable)

If decisions are recorded as discrete referenceable units and a mechanical coverage check runs between planning and build (and again at validation), then a decision dropped between stages is caught before it ships, at negligible token cost, without forcing the human to hand-audit every plan against every spec.

## Falsification criteria

The spec's premise is wrong if any hold after implementation:
- A decision recorded in a spec/ADR can be dropped from the plan and reach a passing validation with no warning at any stage.
- The coverage check cannot distinguish a deliberately deferred/delegated decision from an accidentally dropped one, forcing either false alarms or missed drops.
- A malformed or unparseable decision list causes the check to report "nothing to check" (a silent pass) instead of failing loud.
- The check costs meaningful agent tokens rather than running as mechanical work.
- Honoring the check requires so much authoring ceremony that authors stop recording decisions as discrete units.

## Success criteria

- Every decision in a spec/ADR/discussion is a discrete, referenceable unit a tool can enumerate.
- Running the coverage check reports, for a given plan set, which decisions are covered and which are not.
- A deliberately deferred/delegated/informational decision is recorded as such and does not register as an accidental gap.
- The check runs off the token budget and its blocking behavior is configured, not improvised per run.
- An unparseable decision set fails loud, never a silent pass.
- The validator includes decision coverage in its final audit.

## Constraints

- Mechanical work lives in the `compass` CLI, off the agent budget ([[ADR-005-compass-cli-for-mechanical-work]]).
- Reuses existing vault conventions (frontmatter, markdown, wikilinks) rather than inventing a parallel decision database.
- Cross-platform, LF line endings, `python`/`python3`, per existing Compass constraints.
- Must not turn spec/plan authoring into heavyweight ceremony; recording a decision as a discrete unit should be nearly as light as writing the sentence.

## Non-Goals

- Choosing the decision-ID grammar, the coverage-check algorithm, or where exactly the gate fires - that is the research/ADR/plan phase.
- Tracking every sentence in a spec. Only genuine decisions (a resolved question, a chosen trade-off, a ruled-out option) are in scope.
- A general requirements-management system. This is decision survival across the Compass pipeline, nothing broader.

## Open questions (for research, after approval)

- The decision-unit format: how a decision is marked as a discrete, referenceable unit inside a spec/ADR without heavy ceremony (an ID convention, a frontmatter list, a tagged block). GSD's `<decisions>` block with `D-NN` / `D-AREA-NN` IDs and a `trackable` flag is direct prior art worth studying - see [[RESEARCH-gsd-core-improvements-for-compass]] and the verified source (`src/decisions.cts`, `src/gap-checker.cts`).
- How "deliberately not covered" is expressed (GSD uses a `### Claude's Discretion` heading plus `informational`/`folded`/`deferred` tags).
- How existing ADRs migrate: whether rulings in already-approved ADRs get IDs retroactively or only from now on.
- How a configured workflow names the status transition that carries the blocking gate (per D-05).
- The fail-loud contract: how the check tells "no decisions present" apart from "decisions present but unparseable" so a format mismatch can never masquerade as a clean pass.
- How this composes with Compass's existing ADR and spec templates, and whether lessons/handoffs also carry decisions worth tracing.
- Whether decision coverage belongs in `compass validate`, a new `compass decisions` subcommand, or both.
