---
title: "Rolling-Wave Planning: Cross-Axis Synthesis and Recommended Mechanism"
type: research
status: complete
confidence: high
area: methodology
tags: [planning, rolling-wave, progressive-elaboration, plan-approval, synthesis, wave-sizing, coverage-gate]
created: 2026-08-11
updated: 2026-08-11
git_branch: "master"
git_commit: "268aebc"
author: "reviewer (Claude)"
depends_on:
 - "[[SPEC-015-rolling-wave-planning]]"
 - "[[RESEARCH-rolling-wave-flow-theory]]"
 - "[[RESEARCH-rolling-wave-software-practice]]"
 - "[[RESEARCH-rolling-wave-agent-planning]]"
summary: "cross-axis synthesis and recommended mechanism"
---

# Rolling-Wave Planning: Cross-Axis Synthesis and Recommended Mechanism

## Question

Three research axes answered [[SPEC-015-rolling-wave-planning]]'s four open questions from different literatures. Where do they converge, where do they genuinely conflict, and what is the smallest mechanism the ADR stage should specify?

## Inputs

Three axes, cited throughout as **Flow-N**, **Practice-N**, **Agent-N** (the numbered findings in each source document):

| Axis | Document | Literature |
|---|---|---|
| Flow | [[RESEARCH-rolling-wave-flow-theory]] | Reinertsen, Toyota SBCE, Last Planner System, PMBOK, Poppendieck, Real Options, Boehm |
| Practice | [[RESEARCH-rolling-wave-software-practice]] | XP, Scrum, Kanban/Anderson, Shape Up, Highsmith ASD, Cynefin, refinement anti-patterns |
| Agent | [[RESEARCH-rolling-wave-agent-planning]] | MPC/receding horizon, Flare, HTN, plan repair, Horizon Gap survey, Anthropic context engineering |

## Convergence matrix

Read "agree" as: the axis makes a claim pointing the same direction, not that it uses the same words.

### Open question 1: Wave sizing

| Claim | Flow | Practice | Agent | Agreement |
|---|---|---|---|---|
| Fixed-N-tasks per wave is the wrong rule | AGREE (Flow-1 flat-bottom batch curve; Flow-3 cost of delay beats file order) | AGREE (Practice-8, Practice-20: fixed timeboxes draw converging criticism from inside and outside Kanban) | AGREE (Agent-2 adaptive horizon; Agent-8 deviation-triggered beats fixed-cadence) | 3/3 |
| Wave sizing is a judgment/frontier rule, not a constant | AGREE (Flow-11 constraint clearance gates eligibility) | AGREE (Practice mapping: dependency-frontier or judgment has the stronger practitioner support) | AGREE (Agent-2 settling time; Agent-5 HTN decompose-on-arrival) | 3/3 |
| Some lookahead beyond the immediately-next task is required | SILENT | PARTIAL (Practice-7 Kanban argues the opposite: pure per-item pull, no batch) | AGREE, strongest form (Agent-3, Flare Prop 3.1 proves step-wise-greedy is arbitrarily suboptimal for horizon >= 2) | 2/3, one real dissent |
| The fixed dimension should be cost, not scope or count | SILENT (Flow-1 gives the economics but names no unit) | AGREE (Practice-9 Shape Up appetite is the only surveyed mechanism making low far-detail safe by construction) | SILENT | 1/3, unopposed |
| Elaborate on cost-of-delay priority, not strict sequence | AGREE (Flow-3, and Flow contradiction 1 resolves to WSJF) | PARTIAL (Practice-16 IFM sequences by ROI, flagged as less transferable) | SILENT | 1.5/3 |
| Literature yields no numeric wave size | AGREE (Flow gap: explicit) | AGREE (Practice gap: no quantitative outcome data anywhere) | AGREE (Agent gaps: no validated trigger rule; open even for HTN/MCTS, Agent-16) | 3/3 |

### Open question 2: Elaboration record

| Claim | Flow | Practice | Agent | Agreement |
|---|---|---|---|---|
| The record is a separate lightweight artifact, not the approval record | AGREE (Flow-12 should/can/will/did/learn is its own loop) | AGREE, strongest form (Practice-13 hill chart is explicitly distinct from and cheaper than the betting table) | AGREE (Agent-15 structured note-taking persisted outside the context window; Claude Code's to-do list cited as precedent) | 3/3 |
| It must carry WHY detail changed, not that it changed | AGREE, strongest form (Flow-13 PPC is documented as failing exactly this way when reduced to a score) | AGREE (Practice-18 tickets nobody but the author understands) | AGREE (Agent-12 grounding is what makes a correction useful) | 3/3 |
| Elaborating wave N must not silently rewrite far waves | SILENT | PARTIAL (Practice-13 absorbs discovered scope inside the cycle, but says nothing about untouched far items) | AGREE, only explicit statement (Agent-10 task-decoupled planning exists precisely to stop cross-task error propagation) | 2/3, unopposed |
| The record closes a promise-vs-actual loop | AGREE (Flow-12) | AGREE (Practice-14 ASD's "learn" phase is an explicit end-of-cycle activity) | AGREE (Agent-13 Reflexion-style episodic feedback, with efficacy caveat) | 3/3 |

### Open question 3: Coverage of far tasks

| Claim | Flow | Practice | Agent | Agreement |
|---|---|---|---|---|
| Far tasks are deferred-but-tracked, never uncovered-and-invisible | AGREE (Flow-16 deferral is a tracked decision with a named expiry, not an absence) | AGREE (Practice mapping: epics and un-bet pitches are visible but not committed) | AGREE (Agent-5 HTN: "not yet decomposed" is a legitimate distinct state) | 3/3 |
| Coverage needs three states, not two | SILENT (Flow-10 gives a three-TIER detail precedent, which is a different axis) | SILENT | AGREE, only explicit statement (Agent-5) | 1/3, unopposed |
| Deferral must have a named conversion trigger or it decays into default decisions | AGREE, strongest form (Flow-15 Poppendieck: past the last responsible moment, decisions get made by accident) | AGREE (Practice-19 under-elaboration is a documented named anti-pattern cluster) | AGREE (Agent-3 zero-lookahead is provably bad) | 3/3 |
| No precedent exists for a formal citation/traceability gate over graded detail | SILENT | AGREE, explicit gap (Practice gap 1: surveyed methodologies handle traceability informally or not at all) | AGREE, explicit gap (Agent gap 4: nothing evaluates coverage-gate semantics) | 2/3, and both flag it as novel |

### Open question 4: Planner brief

| Claim | Flow | Practice | Agent | Agreement |
|---|---|---|---|---|
| Far detail = mission + boundary conditions, not method | AGREE, strongest form (Flow-7 Boeing 777 decision rule; Flow-9 SBCE communicates sets that narrow without retraction) | AGREE (Practice-10 breadboarding debates topology while making implementation detail inexpressible) | AGREE (Agent-15 lightweight identifiers, load just in time) | 3/3 |
| Imprecision should be structural, not left to planner discipline | SILENT | AGREE, only explicit statement (Practice-10 fat marker sketch: detail is difficult or impossible to add) | PARTIAL (Agent-11 supports the motive: far detail is actively harmful in context, so a cap has a second payoff) | 2/3, unopposed |
| Over-detailing far tasks has a real cost, not merely zero benefit | AGREE (Flow-4 DIP earns nothing until executed; Flow-2 long horizons create decaying inventory) | AGREE (Practice-12 Basecamp's psychological grooming cost) | AGREE, strongest form (Agent-11 lost-in-the-middle plus non-plan-aware compaction actively mangles it) | 3/3 |
| Some tasks should opt out and be fully detailed upfront | AGREE, strongest form (Flow-18 Boehm and Flow-19 rolling-wave practitioners name the same limit from independent literatures) | SILENT | AGREE, different reason (Agent-8 full-horizon planning matched step-wise accuracy at 2-3x fewer tokens for well-understood tasks) | 2/3, unopposed |
| Detail should track uncertainty; proximity is only a proxy | SILENT (implied by Flow-11 constraint clearance) | PARTIAL, and split on the reason (Practice contradiction 2: ASD/Cynefin say unknowable, Scrum DoR says merely unwritten) | AGREE, explicit (Agent-7: the right amount of decomposition is a property of the task's uncertainty, not a free efficiency gain) | 2/3 |

## Resolving the named tensions

### Tension 1: what fixes the wave boundary

Five positions were in play: fixed cadence (Scrum, XP), no fixed wave at all (Kanban, Anderson), fixed appetite with flexible scope (Shape Up), adaptive horizon tuned to settling time (MPC), and two-signal proximity-plus-cost-of-delay (Reinertsen's WSJF).

Two of the five are eliminated by evidence rather than preference:

- **Fixed cadence is dead** (confidence: high). Practice-8 and Practice-20 document the same failure shape from inside and outside the Kanban camp, and Compass has no timebox for a cadence to attach to anyway. Nothing in any axis defends it.
- **Pure per-item, zero-lookahead commitment is dead** (confidence: high). This is Kanban's position (Practice-7) and it is the one place a research axis is directly contradicted by another: Agent-3 cites a proof (Flare Prop 3.1) that step-wise-greedy policies are arbitrarily suboptimal once the horizon reaches 2. A Compass wave of exactly one task would be provably the wrong shape.

The remaining three are not competitors. They answer different questions, and they compose:

- **Adaptive horizon (MPC, Agent-2) answers where the wave ENDS**: at the point where a decision's consequences have not yet become visible.
- **Constraint clearance (Flow-11, Agent-5) answers which tasks are ELIGIBLE**: those whose prerequisite knowledge already exists.
- **Appetite (Practice-9) answers how big the commitment is allowed to GET**: a cost cap, so an over-wide frontier cannot produce a giant speculative wave.
- **Cost of delay (Flow-3) answers ORDER within the eligible set**, not size.

**Recommended wave-sizing rule for Compass** (confidence: medium-high; the composition is forced by the evidence, the appetite cap is the judgment call):

> A wave is the set of tasks whose preconditions are already satisfied by completed, verified work (the dependency frontier), bounded by a size budget rather than a task count, and ordered within itself by urgency. It ends at the first task whose specification depends on an outcome not yet observed. It is never one task alone.

Reasoning: the frontier is the only sizing signal all three axes independently support (Flow-11 look-ahead constraint removal, Agent-5 HTN precondition-at-decomposition, Practice's finding that dependency-frontier sizing has the strongest practitioner support). It is also self-correcting in a way fixed-N is not: when the graph is wide the wave is naturally large and cheap to detail, when the graph is a chain the wave is naturally short. The size budget is Shape Up's appetite (Practice-9), imported because a wide frontier plus no cap reintroduces exactly the speculative-batch problem the spec exists to kill; Compass already carries per-task sizes, so the budget has a unit. Cost-of-delay ordering (Flow-3) is included in the rule but is the weakest-supported element (1.5 of 3 axes) and is flagged below as a decision for the human.

The **trigger** is separate from the sizing and is not in dispute: elaboration fires when a wave's tasks complete and their verification passes (Agent-12, Flow-11), never on cadence and never on the planner rereading itself.

### Tension 2: full-upfront-beats-stepwise versus the gradient thesis

Agent-8 reports that full-horizon planning with on-demand replanning matched step-by-step monitoring accuracy at 2-3x fewer tokens for well-understood tasks. Read naively this contradicts SPEC-015's premise.

It does not, and the resolving finding is in the same axis: **Agent-7 states the gradient is over uncertainty, and proximity is a proxy for uncertainty rather than its cause** (confidence: high that this is the correct reading; the two findings are adjacent in one document and the source's own contradictions section resolves them this way).

Folded into the recommendation, this produces one mechanism where a naive reading would produce two:

1. **The default gradient stands.** For the work Compass actually does, proximity is a good proxy for uncertainty, because most far-task uncertainty is precisely "what will the completed near tasks teach us." Agent-11 adds a cost the human-ceremony argument does not have: a fully detailed far task sits in the discard-prone middle of context and is mangled by any compaction pass that is not plan-aware, so over-specification is a real cost, not a neutral one.
2. **The proxy can be overridden per task, in both directions.** A task whose uncertainty is low may be fully specified at plan time even if it is far. A near task with low execution uncertainty should not be over-decomposed either (Agent-7 cautions against this explicitly, which the spec does not currently anticipate).
3. **The override and the "structurally expensive to change late" escape hatch are the same mechanism.** Flow-18 and Flow-19 argue for upfront detail where late change is expensive; Agent-8 argues for it where uncertainty is low. Different justifications, identical mechanism: a per-task flag that says "commit this now" plus the reason. The ADR should specify one flag, not two.

There is a second-order finding worth carrying into the ADR (confidence: medium, this is a cross-axis inference not stated in any single document): **Compass's existing testing mandate is what makes the gradient safe.** Flow-18 says Boehm's curve flattens where modular architecture and automated testing exist; Flow-17 says testable, refactorable code is what manufactures the option to defer. Compass already requires tests on every code change. The gradient is therefore not a bet Compass is taking on faith; it rests on a property the methodology already enforces. Where that property does not hold (a task touching a data migration, a public contract, a security path), the opt-out flag is the designed response.

### Tension 3: epistemic far-ness versus workload far-ness

Practice contradiction 2 is unresolved in its own document: ASD and Cynefin treat far detail as unknowable in principle (Practice-14, Practice-15), Scrum's Definition of Ready treats it as knowable but not yet written (Practice-4). SPEC-015 does not distinguish them.

The frontier rule resolves this without a new concept (confidence: medium-high). A task blocked on knowledge that does not exist yet is outside the frontier and must stay scoped. A task whose knowledge exists but has not been written up is inside the frontier and should simply be elaborated now. That is exactly the Last Planner look-ahead function (Flow-11): the stage exists to clear constraints so a task becomes eligible, not to write detail. The distinction is real and it is already encoded in "is this task on the frontier," so it needs no separate field, though the human may want it named explicitly in the planner brief.

## Agreements strong enough to bind the ADR

Each of these is 3/3 or unopposed-with-explicit-support, and each has at least one axis stating it in strong form.

1. **Approval is coarse, elaboration is fine and frequent, and detail is never re-approved** (confidence: high). Practice's approval-semantics map surveys six methodologies and finds zero that re-run approval when detail is added; every one runs a cheaper, different-shaped step instead. Agent-6 supplies the formal counterpart: Fox et al.'s plan stability metric shows repair (preserving unaffected structure) beats replanning from scratch. Flow-9 adds the property that makes this coherent: SBCE communication stays valid as a set narrows, so nothing needs retraction, only supplementation. SPEC-015 Need 3 is not a novel invention; it is the industry norm.

2. **Far detail is mission plus boundary conditions, and the format should make finer detail hard to write** (confidence: high). Flow-7 (Boeing 777: any of 5,000 engineers could spend up to $300 per unit to save a pound, a decision rule instead of an instruction) and Flow-9 (SBCE sets) give the content shape. Practice-10 gives the enforcement mechanism: a fat marker sketch makes detail difficult or impossible to add, so imprecision is structural rather than a discipline the planner must sustain. Agent-11 supplies the independent second reason to cap it: excess far detail actively degrades under lost-in-the-middle and compaction.

3. **Elaboration triggers on grounded signals from completed, verified work, never on the planner's own second-guessing** (confidence: high). Agent-12 is the strongest single finding in the entire set: intrinsic self-correction shows an accuracy-correction paradox where stronger models self-correct less usefully, while externally grounded correction (tool result, test run, human review) performs better. Flow-11 says the same thing from the construction-planning side: eligibility is constraint clearance, not calendar proximity.

4. **Far-task coverage is three-state, not binary** (confidence: medium-high; only Agent-5 states it explicitly, but nothing opposes it and both other axes support the underlying deferred-but-tracked stance). The states: elaborated and covered, scoped and not yet decomposed, elaborated but uncovered. Only the third is a gate failure. Practice's mapping reaches the same conclusion by a different route: no surveyed methodology treats far items as either fully covered or silently dropped, they are visible but not committed.

5. **An explicit per-task opt-out for work that is structurally expensive to change late** (confidence: high). Flow-18 (Boehm's lineage) and Flow-19 (rolling-wave practitioner literature) name the same boundary condition from independent literatures, which is unusually strong evidence. Agent-8 arrives at the same mechanism from the token-cost side. This is a designed escape hatch, not an admission of weakness in the technique.

6. **The elaboration record carries why the detail changed, not that it changed** (confidence: high). Flow-13 is a documented cautionary precedent rather than a prediction: Percent Plan Complete's stated purpose is root-cause learning and it is widely reported as degenerating into a punitive score, with teams that omit the variance reasons getting no improvement value. A "waves elaborated: 3" counter reproduces a failure the literature has already observed. Practice-13's hill chart and Agent-15's structured note-taking both put this record outside the approval artifact.

7. **Both failure directions are real and need separate checks** (confidence: high). Over-elaboration (Practice-18: "too detailed refinements" is a named anti-pattern) and improvisation decay (Practice-19: "unprepared" and "rare" refinements) are independently documented clusters. Flow-15 gives the sharp version of the second: past the last responsible moment, decisions are made by default rather than staying open. Agent-3 gives the formal version: zero lookahead is provably suboptimal. SPEC-015's falsification criteria should keep testing both; guarding one does not guard the other.

## Open points for the human

Four decisions the evidence does not settle.

1. **Does a Compass wave carry a size budget?** The frontier rule sizes the wave by dependency structure. Shape Up's appetite (Practice-9) is the only surveyed mechanism that makes low far-detail safe by construction rather than by hope, and it is 1-of-3 support with nothing opposing it. Adding a per-wave size budget bounds a pathologically wide frontier; omitting it keeps the plan format simpler. Recommendation: include it, since Compass already carries task sizes so the unit is free.

2. **Two detail tiers or three?** SPEC-015 assumes two (full near, scope-and-intent far). Flow-10 argues from the Last Planner System that three has industrial precedent (strategic shape, constraint-cleared and ready, committed), with the middle tier's job being constraint removal rather than detail writing. Practice's methodologies mostly use two (XP's two meetings, Shape Up's pitch and tasks). This is a real design split and it changes the plan format. Recommendation: two tiers, because the frontier rule already performs the middle tier's constraint-clearance function without needing a document tier to hold it. the human should rule.

3. **Is cost-of-delay reordering in scope?** Flow-3 argues the planner should be able to pull a far but urgent task forward rather than always detailing in sequence. Support is 1.5 of 3 axes and the concept may not transfer: Compass plans are dependency-ordered and cost of delay is not something a planner agent can currently measure. Recommendation: leave it out of the first mechanism as unmeasurable, and revisit if plans start showing sequence-driven detail waste.

4. **Where exactly does the elaboration record live?** All three axes agree it is out-of-band, lightweight, and distinct from the approval record, and none picks a file layout for a Compass vault. The options remain a plan appendix, a per-wave section, or a separate document. Note the constraint this must satisfy: Agent-10 says elaborating wave N must not rewrite the stated intent of unrelated far waves, which rules out an approach where elaboration edits the plan body in place, but does not rule out appending an elaborated wave section to the plan.

## Recommended mechanism shape for the ADR

The smallest set of changes that discharges the binding agreements. Five pieces.

1. **Plan format: per-task detail tier plus an opt-out flag.** Each task is `elaborated` (files, verification, size, citations, exactly as today) or `scoped` (mission and boundary conditions only, in a length-capped field that structurally cannot hold a file list). A task may additionally carry a commit-upfront flag with its reason, which forces full detail regardless of distance. Traces to: Flow-7, Flow-9 (content shape), Practice-10 (structural cap), Agent-11 (context cost), Flow-18, Flow-19, Agent-8 (the single opt-out flag serving both justifications).

2. **Planner brief: specify the frontier, scope the rest.** The frontier is the set of tasks whose preconditions are satisfied by completed, verified work, bounded by a size budget, never a single task. Scoped tasks state what must be true when they are elaborated and what constrains them, and the planner does not invent file paths for them. Traces to: Flow-11, Agent-5 (frontier definition), Agent-3 (never one task), Practice-9 (budget), Flow-7 (what scoped content says).

3. **Build-skill wave boundary: elaboration fires on grounded completion.** When the last task of a wave completes and its verification passes, the next wave elaborates from what that work produced. Not on a cadence, not on the planner's own doubt, not on a readiness checklist. Traces to: Agent-12 (the strongest finding in the set), Flow-11, Agent-8 (deviation-triggered, not fixed-cadence).

4. **Coverage gate: three states, one failure mode.** Elaborated-and-covered passes; scoped-and-not-yet-decomposed is reported as deferred-but-tracked and does not fail the gate; elaborated-but-uncovered fails exactly as today. Citations bind at elaboration time, which is the point where the work is actually specified. Traces to: Agent-5, Flow-16 (deferral as a tracked decision with a named expiry), Practice mapping (visible but not committed).

5. **Elaboration record: append-only, carries the why.** One entry per elaboration: what completed, what it taught, what changed in the next wave's detail, and because of what. Lives outside the approval record. It never rewrites the intent of far tasks the dependency graph does not connect to the completed work. Traces to: Flow-13 (why, not a counter), Flow-12 (promise-versus-actual loop), Practice-13 (separate cheap artifact), Agent-15 (persisted structured notes), Agent-10 (no cross-task rewrites).

### Do NOT build

Each item here is killed by evidence, not by taste.

- **Per-wave re-approval.** Zero of six surveyed methodologies re-run approval when detail is added (Practice approval-semantics map). It is also SPEC-015's own falsification criterion 2.
- **Fixed-N-task waves.** Rejected by all three axes independently: Practice-8 and Practice-20 (converging criticism of fixed boundaries from inside and outside Kanban), Agent-2 and Agent-8 (adaptive horizon, deviation triggers), and the Flow gap confirming the literature yields no wave count.
- **Single-task waves / pure Kanban per-item pull.** Agent-3: step-wise-greedy is provably arbitrarily suboptimal for horizon >= 2.
- **Inline plan-body rewrites as the elaboration record.** Agent-10 (cross-task error propagation), Flow-13 (a changelog without the why is the documented PPC failure), Practice-13 (the update artifact is separate from the approval artifact by design).
- **A Definition-of-Ready style formal readiness checklist as an elaboration gate.** Practice-4: Scrum.org deliberately kept DoR out of the Scrum Guide because over-formalizing readiness becomes a heavyweight gate in itself, which is SPEC-015's falsification criterion 2 almost verbatim.
- **A bare "waves elaborated: N" metric.** Flow-13: this is the observed PPC failure mode, not a hypothetical one.
- **A quantified detail-decay function by horizon distance.** No source in any axis measures this for software task graphs (Agent gap 1, Flow gap 4). Any formula would be invented, not derived.
- **Pre-elaborating tasks that may never be reached, or maintaining a fully-detailed backlog.** Practice-12 (Basecamp's grooming-cost argument), Flow-4 (design-in-process inventory earns nothing until executed).

## Gaps carried forward from all three axes

- **The citation/traceability gate over graded detail has no precedent anywhere.** Practice gap 1 and Agent gap 4 independently report finding nothing. SPEC-015 Need 4 is a genuine Compass-specific design point, so mechanism piece 4 above is reasoned from adjacent structures (HTN decomposition states) rather than from a working example. Treat it as the highest-risk piece of the mechanism.
- **No quantitative outcome data exists for rolling-wave planning in any surveyed literature.** All evidence across three axes is qualitative or practitioner-report. SPEC-015's success criteria will be the first measurement, which raises the value of actually running them.
- **Agent-8's primary study was never located** (the survey does not name it). It is load-bearing for the "well-understood tasks can be front-loaded" half of Tension 2. The conclusion also rests on Flow-18 and Flow-19 independently, so the opt-out mechanism survives if Agent-8 does not, but the token-cost justification for it would weaken.
- **Reinertsen's principle codes were never obtained from a primary source** (Flow gap 1, expired TLS certificate on the compendium). The substance is confirmed by multiple independent secondaries; do not quote numbered codes in the ADR.

CONVERGENCE: HIGH on approval semantics, far-task content shape, elaboration triggers, and the record's contents. MIXED on wave sizing (composable rather than contested) and tier count. The single genuine cross-axis contradiction is Kanban's zero-lookahead position against Flare's proof that zero lookahead is suboptimal, and the proof wins.
