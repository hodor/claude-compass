---
title: Compass Learns - the Loop from Capture to Retrieval to Application Closes
type: spec
status: approved
confidence: high
area: methodology
tags: [lessons, learning-loop, capture, retrieval, application-audit, triggers, install-drift]
created: 2026-08-05
updated: 2026-08-05
depends_on: ["[[SPEC-002-lessons-and-index-subsystem]]", "[[RESEARCH-lesson-capture-failure]]", "[[RESEARCH-hermes-memory-mechanics]]"]
summary: "capture on real events, retrieval at the work, application audited (approved, SHIPPED v0.5.0)"
---

# Compass Learns - the Loop from Capture to Retrieval to Application Closes

## Problem

Compass promises a framework that learns, but the learning loop is broken at every stage.

**Capture almost never happens.** Across 40 vaults, the automatic capture path has fired organically exactly once, ever ([[RESEARCH-lesson-capture-failure]]). The mechanism is proven good - when it fired, it worked flawlessly - but its only trigger is the `/compass:build` phase pause, an event real sessions almost never reach. Sessions run vision, spec, research, and plan inside Compass, then implement conversationally, and everything learned in the session evaporates. 26 of 40 vaults hold zero lessons; the two lesson-rich outliers bypassed the system entirely.

**Retrieval is unverified.** The lessons catalog rides the hot path, but nothing surfaces the specific lessons relevant to the work at hand, and nothing measures whether agents consult them.

**Application is invisible.** Even when a lesson is relevant and surfaced, no mechanism verifies it influenced the work - the same gap decision coverage ([[SPEC-007-decision-coverage-tracing]]) closed for spec decisions.

Two compounders make it worse: install drift (19/40 vaults cannot run the Stop-hook backstop at all; 3 run stale partial installs) and bypass schemas that drift from the canonical lesson format.

## Who is affected

- Every agent in every session, which repeats mistakes the fleet already paid for.
- The human, who observes the same failure classes recur across projects and must hand-write lessons (`/compass:learned`) for a system that was designed to capture them automatically.
- The lesson subsystem itself, whose retrieval and audit investments are worthless while capture produces no input.

## Decisions (made by the human)

- **D-01:** Compass becomes "a framework that learns" in the hermes sense but with Compass discipline: harness-owned triggers, anti-list quality gates, auditable output.
- **D-02:** Capture-fix is sequenced before retrieval and application - retrieval and audit are worthless until capture produces input.
- **D-03:** The design must be informed by a review of how hermes updates and retrieves its memory. [[RESEARCH-hermes-memory-mechanics]] is that review; its takeaways bind: the trigger decision is harness-owned arithmetic attached to events that occur in every session, model judgment is confined to what gets saved, and hermes's fire-and-forget blind spot (no trace distinguishing "reviewed, nothing to save" from "never ran") is the anti-pattern Compass must not replicate.
- **D-04:** Whether retrieval rides a graph substrate is gated on [[SPEC-011-vault-graph-queries]]'s grep-vs-graph experiment; this spec does not presuppose it.

## Desired Outcome

Real sessions - conversational ones, not just `/compass:build` runs - routinely produce lessons without the human asking, at the quality level of the one organic firing. Relevant lessons reach the agent doing related work. A coverage-style audit shows whether they changed anything. A future fleet audit can measure all of it from traces.

## Needs

**Pillar 1 - capture fires on events that actually occur:**
- Capture triggers attach to events real sessions demonstrably reach: session end/handoff, validation completion, debug resolution, conversational build waves - not solely the build phase pause.
- Whether a capture opportunity runs is decided by the harness deterministically; model judgment decides only what is worth saving, constrained by the existing anti-list.
- The proven extraction core is preserved: binary triggers, anti-list, dedup against the catalog, 5-line cap, single writer. The ai-songwriting firing is the quality benchmark any redesign must match.
- Every firing leaves a trace, so "reviewed and found nothing" is distinguishable from "never ran" and capture rate is measurable fleet-wide.
- Install verification (doctor-style) rides update/checkup so the drift classes the audit found are detected, not silently inert.

**Pillar 2 - retrieval reaches the work:**
- Lessons relevant to the current task surface to the agent at the point of work, off the agent's crawl budget.
- Surfacing is observable: which lessons surfaced in which contexts.

**Pillar 3 - application is audited:**
- A coverage-style check verifies surfaced lessons were considered or cited in the produced artifacts, analogous to decision coverage's D-NN tracing.

## Hypothesis (falsifiable)

If capture attaches to events that actually occur, with the trigger harness-owned and the quality gates unchanged, then organic firings become routine in real sessions across the fleet (from once-ever to a measurable rate) while precision holds (output quality matches the benchmark firing, no anti-list-violating trivia floods).

## Falsification criteria

- Heavy real sessions still end with zero organic firings after the redesign.
- Precision collapses: vaults fill with lessons the anti-list should have rejected.
- The trigger depends on agent prose remembering to act, rather than the harness.
- Mechanical capture work lands on the agent token budget (violates [[SPEC-004-mechanical-work-off-the-agent-budget]] and the north star).

## Success criteria

- Organic firings observed in real sessions across multiple fleet vaults, verified from traces, not anecdote.
- The audit trail supports a rerun of the 40-vault fleet measurement: fire rate and write rate per vault.
- Relevant-lesson surfacing works and is observable in at least the highest-value agent contexts.
- An application audit exists and runs in validation.
- update/checkup detect the install-drift classes the fleet audit found.

## Non-Goals

- Choosing the trigger mechanism (hook type, counter cadence, nudge text vs. spawned pass) - ADR/plan territory. Note hermes's forked-agent review is explicitly flagged as too token-heavy for Compass's north star; the plan weighs cheaper equivalents.
- The graph substrate decision - SPEC-011's experiment owns it (D-04).
- Migrating the outlier vaults' bespoke lesson schemas - a separate cleanup concern.
- External memory providers, embeddings, semantic retrieval - same deferral triggers as [[RESEARCH-rag-fit-for-large-vaults]].

## Open questions (for research/ADR, after approval)

- Which trigger sites ship first (handoff and validation are the most frequent events in the fleet trace data).
- What the capture-opportunity cadence counts (turns, tool calls, vault writes) and where the counter lives.
- How pillar 3's citation field binds to artifacts (parity with `decisions:` coverage - see backlog "Lesson-coverage parity").
- What retrieval keys on before SPEC-011 resolves (tags and area from the catalog are available today).
