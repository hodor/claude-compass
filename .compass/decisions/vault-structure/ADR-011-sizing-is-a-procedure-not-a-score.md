---
title: "Sizing Is a Judgment Procedure the Harness Triggers and Records, Never a Score"
type: decision
status: accepted
confidence: high
area: methodology
tags: [sizing, decomposition, units, vision, harness, observability]
created: 2026-08-23
updated: 2026-08-23
author: "orchestrator"
depends_on: ["[[SPEC-016-sizing-work-beyond-one-spec]]", "[[RESEARCH-decomposition-criteria-for-sizing]]", "[[ADR-004-hierarchical-specs-with-facets]]", "[[ADR-006-hybrid-hierarchy-implementation]]"]
summary: "the changeability walk, harness-triggered and recorded; no sizing metric ships"
---

# Sizing Is a Judgment Procedure the Harness Triggers and Records, Never a Score

## Context

[[SPEC-016-sizing-work-beyond-one-spec]] requires Compass to notice that a need is too big for one spec and give it the bigger shape, without asking, without naming the machinery, once, and reversibly. [[RESEARCH-decomposition-criteria-for-sizing]] establishes what is and is not available to build that on.

The constraint that shapes everything below: there is no validated mechanical signal for depth versus breadth, and the one serious attempt to compute the analogous judgment over code failed to predict what it was built to predict.

## Decision

- **D-01:** The sizing judgment is a directed procedure, never a score. No numeric threshold, no computed sizing metric, and no "count the sub-concerns" rule ships. Any future proposal of one is labeled an unvalidated invention and justified on its own evidence.
- **D-02:** The procedure is Parnas's changeability walk. Name the volatile or unresolved decisions in the need, then for each ask how many candidate sub-problems must move together if it moves. Entangled with the same one or two decisions, plus shared context they would each otherwise restate, means depth. Independent decisions and nothing shared but a label means breadth.
- **D-03:** The harness owns the trigger and the record; the agent owns the judgment. This is the only split available, because [[LESSON-remove-context-before-adding]] prefers a harness gate over added prose while D-01 forbids mechanizing the judgment itself. Prose carries the criteria because it must; the harness carries everything that does not require judgment.
- **D-04:** Both creation paths ship. `compass make-unit` accepts zero artifacts, so a workspace can be declared up front, and it keeps its existing behavior of carrying named artifacts in, so a flat spec can be converted later.
- **D-05:** Sizing classifies what the human actually said. Acting on unstated, inferred future scope is forbidden: that is forecasting, and [[RESEARCH-hierarchical-knowledge-base-design]] Finding 11 governs it. This boundary is what makes acting at vision time defensible at all.
- **D-06:** The parent holds decisions shared by every child; a child exists to diverge on something the parent left open. Divergence with no shared root decision above it is a sibling, not a child. This is the authoring template for a folder or unit `index.md`, from Parnas 1976, and it is checkable by reading.
- **D-07:** Whether the work will be driven as one continuous thread is a second, independent input. A unit grants a full pipeline, which is a workflow boundary, so this can point differently from the content answer and must be weighed rather than collapsed into it.
- **D-08:** Every sizing decision and every later correction is recorded. A correction that is never observed is indistinguishable from a correction that was never needed.
- **D-09:** The notice says the shape is provisional and how to change it. A structure Compass chose must be as easy to question as one the human chose.
- **D-10:** `compass unit-check` keeps its reactive role as a backstop for shapes that grow into needing promotion after the fact, and it gets an actual caller. Proactive sizing at vision time and reactive detection later are complements.
- **D-11:** The inverse of each shape change ships alongside it. A shape that can be created without asking must be reversible by one command, because cheap reversal is the premise that licenses acting without asking. Until the inverse exists, the premise is asserted rather than demonstrated.

## Rationale

D-01 is forced by evidence rather than taste. Woodward found 163 trained raters disagreeing when applying the cohesion ladder to one program; Chidamber & Kemerer built LCOM to remove exactly that subjectivity by computing it; Basili, Briand & Melo then found LCOM did not predict fault-proneness while five sibling metrics did. Mechanizing the judgment over the most favorable possible domain did not rescue it, so mechanizing it over prose would be inventing, not inheriting.

D-02 and D-06 are the constructive half. Parnas 1972 gives an operational test that is judgment against explicit criteria rather than a scan of surface text, and Parnas 1976 gives the decision-graph that says what belongs in a parent versus a child.

D-04 and D-09 rest on the reversal cost. Real options says the value of waiting collapses when late exercise costs about what early exercise costs, and `compass make-unit` is a `git mv` with derived state regenerated and no caller whose behavior could regress. That is the precondition every framework that would otherwise counsel deferral attaches to acting on judgment.

That precondition is currently half-verified, and D-11 exists to close it. The inspection behind it covered creating a shape, not undoing one: no inverse of `make-unit` or `promote` exists today, so reverting means a hand `git mv` and manual index repair. Acting without asking is licensed by cheap reversal, so the reverse path is not a convenience - it is what makes D-02's whole posture defensible.

D-08 and D-09 exist because cheap reversal answers the mechanical objection and not the social one. Metz's mechanism is that an early-imposed shape acquires normative weight and gets bent rather than reverted; the undo being trivial does not help if nobody calls it. The failure to watch for is anyone saying, in effect, that it is already a unit so we may as well live with it.

D-05 is the boundary the axis C verdict depends on. The vault's prohibition on predictive promotion does not reach classification of information already stated, and it does reach inference about scope nobody stated.

## Consequences

Sizing becomes a normal, unremarkable act that the human does not have to know a vocabulary to receive. That is the point of the spec.

The judgment stays in prose, which is a cost. [[LESSON-remove-context-before-adding]] warns that added prose must be net-negative, and the mitigation is that the harness takes the trigger and the record so the prose carries only what genuinely requires judgment.

Recording sizing decisions creates the falsification test the initiative currently lacks: if corrections never happen, either the judgment is perfect or the shapes are being lived with, and only one of those is good news. This mirrors [[SPEC-017-capabilities-are-reachable-and-measured]] D-03 on the retrieval side.

An open risk stays open and is not closed by this decision: whether an LLM agent executes the changeability walk consistently across runs and across agents is untested, and the literature predates the question entirely. It is empirical and belongs in the plan as a measurement, not an assumption.

## Alternatives Considered

**A computed sizing score, threshold-driven.** Rejected on the LCOM evidence. It would have been the tidiest mechanism and there is no support for it.

**Reactive detection only, extending `unit-check` and dropping proactive sizing.** This is what Compass has today, and it is the failure the spec exists to fix: `unit-check` cannot fire until three artifact types already trace to a spec, which is several stages after the sizing decision was needed. Kept as a backstop under D-10, rejected as the whole answer.

**Ask the human at vision time.** Rejected by [[SPEC-016-sizing-work-beyond-one-spec]] D-02, and independently by the two-way-door argument: applying escalation weight to a decision that reverses with one command is the wrong process weight.

**Defer sizing to the research or plan stage, when evidence exists.** Genuinely tempting, and rejected on the last-responsible-moment argument. The alternative eliminated by waiting is the shape of every artifact authored in between, and the observed default when nobody decides is a monster spec.
