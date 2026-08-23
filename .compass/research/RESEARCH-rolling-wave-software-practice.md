---
title: "Rolling-Wave Planning: How Software Methodologies Operationalize the Detail Gradient"
type: research
status: complete
confidence: high
area: methodology
tags: [planning, rolling-wave, progressive-elaboration, plan-approval, agile, shape-up, scrum, kanban]
created: 2026-08-11
updated: 2026-08-11
git_branch: "master"
git_commit: "268aebc"
author: "researcher (Claude)"
depends_on: ["[[SPEC-015-rolling-wave-planning]]"]
summary: "how methodologies operationalize the detail gradient"
---

# Rolling-Wave Planning: How Software Methodologies Operationalize the Detail Gradient

## Question

How do real software methodologies express near-detail/far-sketch planning, what mechanics made it work or fail in practice, and what transfers to Compass's plan format and approval semantics? Scoped to the software-practice axis: how methodologies operationalize the gradient (not the general flow-theory/lean justification, covered elsewhere).

## Methodology

WebSearch and WebFetch across primary sources (Basecamp's Shape Up book, PMI/PMBOK glossary entries, Scrum.org, David J. Anderson School of Management) and secondary summaries where primaries were unavailable. No sub-agents spawned per brief. Six areas covered: XP/Scrum/Kanban granularity mechanics, Shape Up's betting/shaping/hill-chart system, Highsmith ASD and Cynefin, practitioner-reported failure modes, approval-semantics mapping, and open-question mapping.

## Findings

### Terminology anchor

1. **"Rolling wave planning" is a named, formal PMBOK technique, not an XP/Agile-only concept** (confidence: high)
   PMBOK defines it as "an iterative planning technique in which the work to be accomplished in the near term is planned in detail, while work further in the future is planned at a higher level... a form of progressive elaboration applicable to work packages, planning packages, and release planning when using an Agile or Waterfall approach." It predates and spans both paradigms, which is useful framing: SPEC-015 is reviving a pre-Agile PM technique, not inventing agile-adjacent process.
   - [PM Study Circle - Rolling Wave Planning](https://pmstudycircle.com/rolling-wave-planning/)
   - [PMI - Rolling Wave Approach](https://www.pmi.org/learning/library/rolling-wave-approach-project-management-10514)

### XP Planning Game

2. **XP splits granularity into two distinct meetings (release vs. iteration), not one document with mixed precision** (confidence: high)
   Release planning fixes high-level vision, scope, and story priority (value/risk-ordered) for the whole release. Iteration planning (1-2 week horizon) takes only the next slice, breaks it into tasks, and estimates at a finer grain. The mechanic: precision is a function of *which meeting you're in*, not a field on every story. This maps directly onto SPEC-015's "boundary explicit" need - XP makes the boundary an event (a meeting), not a marker inside a single artifact.
   - [ZenTao - XP Planning Game](https://www.zentao.pm/blog/Extreme-Programming-the-Planning-Game-805.html)

3. **XP's iteration planning has three phases: exploration, commitment, guidance** (confidence: medium)
   Exploration breaks stories into tasks and estimates; commitment is where each developer *voluntarily claims* tasks and finalizes estimates (the human/team approval point); guidance is execution (pairing, TDD, CI). Commitment is per-task and per-person, not a single blanket sign-off - a more granular approval unit than Compass's current whole-plan approval.
   - [ZenTao - XP Planning Game](https://www.zentao.pm/blog/Extreme-Programming-the-Planning-Game-805.html)

### Scrum backlog refinement

4. **"Definition of Ready" is the near-wave elaboration gate, and it is explicitly NOT part of the Scrum Guide** (confidence: high)
   DoR is a "complementary practice," team-invented, used to decide when a backlog item has enough detail to enter a sprint. Unlike Definition of Done (which is codified in the Scrum Guide as an artifact commitment), DoR is deliberately left out. Scrum.org's own reasoning: over-formalizing readiness risks becoming a heavyweight gate in itself - a documented tension directly relevant to SPEC-015's falsification criterion "elaboration becomes its own approval ceremony."
   - [Scrum.org - Why isn't DoR in the Scrum Guide?](https://www.scrum.org/resources/blog/why-isnt-definition-ready-described-scrum-guide)
   - [Agile Ambition - The DoR Is Not Part of Scrum](https://www.agileambition.com/Atomic-Notes/The-Definition-of-Ready-Is-Not-Part-of-Scrum)

5. **Epic-to-story decomposition is a gradient, and the "just enough" phrasing appears verbatim in practitioner sources** (confidence: medium)
   "An Epic should have already been refined by the team with just enough details and clarity to be taken up in the near-future Sprints and hence should have been broken down into consumable & estimable Stories." Epics = far/coarse; stories = near/fine. Refinement is continuous and precedes sprint planning, not concurrent with it - refinement and commitment are separate ceremonies.
   - [Public Agile - Story Refinement](https://publicagile.org/agile-playbook/scrum-events/story-refinement/)

6. **Sprint commitment (Sprint Planning) is the near-wave approval act; it commits only what's in the sprint, nothing beyond** (confidence: high)
   "Refinement ensures the highest priority Stories meet DoR... this preparation ensures your team can confidently select and commit to work they understand." The backlog beyond the sprint is never "approved" - it's prioritized and roughly sized, but commitment is scoped strictly to the wave about to execute.
   - [monday.com - Backlog Refinement Guide](https://monday.com/blog/rnd/backlog-grooming/)

### Kanban

7. **Kanban defers commitment further than Scrum: no backlog at all, a "pool of options," with the commitment point as an explicit line, not a ceremony** (confidence: high)
   "In a true Kanban system, you won't have a backlog - you will have a pool of options, and commitment will be made at the replenishment meeting as you pull work into your kanban system." The commitment point is described as a literal line on the board: work left of it is a droppable option, work right of it is a delivery promise. Kanban shops commonly run *two* commitment points (work-start commitment, then delivery commitment) - a two-phase-commit pattern, finer than a single approve/reject gate.
   - [businessmap.io - Commitment Points in Kanban](https://businessmap.io/blog/what-are-commitment-points-in-kanban)
   - [Medium/Cuenca - Commitment, Real Options & Kanban](https://medium.com/@fernando.a.cuenca/commitment-real-options-kanban-392e0ad12a2f)

8. **Kanban's critique of fixed timeboxes (David J. Anderson) is a direct argument against forcing uniform elaboration onto a schedule boundary** (confidence: high)
   Anderson's three failure modes of sprint-boundary rigidity: (1) requirements analysis burden - shorter boxes force artificial task-type splitting ("architecture story," "design story") that creates false cross-sprint dependencies instead of coherent slices; (2) estimation overhead - fitting work into a box forces "big estimation up front," which he names as an anti-pattern; (3) dependency crisis - the deadline pressure turns normal cross-team dependencies into cross-sprint coordination failures. His fix is WIP-limited continuous flow instead of a time-boxed wave. This is a documented counter-position to wave-based elaboration itself: fixed-size waves reproduce sprint-boundary problems at the plan-wave level if wave sizing is naive.
   - [DJAA - Tyranny of the Timebox Revisited](https://djaa.com/tyranny-of-the-timebox-revisited/)

### Shape Up (Basecamp)

9. **Appetite inverts the estimate: it fixes time and lets scope flex, which is what makes far-task under-specification safe rather than reckless** (confidence: high)
   "Instead of asking 'how long will this take?' you ask 'how much time is this worth?' That becomes the time box." Because the *cost* is fixed by appetite and only the *scope* is negotiable, an under-specified far task never turns into an open-ended estimate risk - it turns into a scope-cut risk, which is contained by design. This is the mechanism, not just a philosophy: it's what makes low far-detail non-dangerous.
   - [UXCam - Shape Up Methodology Guide](https://uxcam.com/blog/shape-up-methodology/)

10. **Fat marker sketches are a physical-constraint mechanism for enforcing imprecision, not a discipline the author has to self-impose** (confidence: high)
    "A fat marker sketch is a sketch made with such broad strokes that adding detail is difficult or impossible." Breadboarding (places/affordances/connection lines, borrowed from electrical engineering notation) forces debate about functional topology while making visual/implementation detail *impossible to express* in the notation. The lesson for Compass: SPEC-015's "far shape" tier could benefit from a format that structurally can't hold fine detail (e.g., a scope-and-intent field with a length/field-shape cap), rather than relying on the planner's discipline not to over-specify.
    - [Basecamp - Shape Up ch. 4, Shaping](https://basecamp.com/shapeup/1.3-chapter-04)

11. **The betting table is a single, scheduled, all-or-nothing approval event per cycle - approve the shaped pitch as a whole, or don't** (confidence: high)
    Only pitches (pre-shaped, appetite-bounded, "No Gos" scoped) are eligible; nothing else reaches the table. Decision is binary per pitch: bet (enters next cycle) or release (dropped, no central backlog tracking - an advocate must re-lobby fresh later). This is the approval gate for the *whole bet at appetite-level granularity* - it does not approve individual tasks inside the bet; those are discovered during the cycle itself.
    - [Basecamp - Shape Up ch. 7, Bets Not Backlogs](https://basecamp.com/shapeup/2.1-chapter-07)

12. **No backlog is a deliberate rejection of speculative elaboration, justified by psychological cost, not just process cost** (confidence: high)
    "Dozens and eventually hundreds of tasks pile up that we all know we'll never have time for." Basecamp's stated reason for no shared backlog is that maintaining one creates constant "reviewing, grooming and organizing old ideas" - overhead spent on work that will likely never happen. Individuals keep private idea lists; nothing is centrally pre-elaborated. This is the strongest documented case against Compass planning (eloborating) tasks that may never be reached.
    - [Basecamp - Shape Up ch. 7, Bets Not Backlogs](https://basecamp.com/shapeup/2.1-chapter-07)

13. **Hill charts let teams report and update true progress mid-bet without re-triggering the betting-table approval** (confidence: high)
    A hill chart is "a diagram showing the status of work on a spectrum from unknown to known to done," split into an uphill "figuring out" phase (unknowns, unsolved problems) and a downhill "execution" phase (known, remaining is just building). Newly discovered scope during the uphill phase is *absorbed inside the fixed cycle* and shown by moving the scope marker - it does not require going back to stakeholders. This is the closest published analogue to Compass's "elaboration without re-approval": the update mechanism (hill chart) is distinct from and cheaper than the approval mechanism (betting table).
    - [Basecamp - Shape Up ch. 11, Hill Charts / Showing Progress](https://basecamp.com/shapeup/3.2-chapter-11)

### Highsmith ASD / Cynefin

14. **Highsmith's Adaptive Software Development names "speculate" (not "plan") as the deliberate word choice for the far-detail phase** (confidence: medium)
    "In traditional models, teams 'plan.' In ASD, they speculate... it's impossible to foresee every detail in advance." The three-phase cycle is speculate -> collaborate -> learn, repeated per iteration; "learn" is an explicit end-of-cycle activity (customer focus groups, technical reviews, post-mortems) that feeds the next speculation. The naming itself functions as an epistemic honesty marker: don't call far-detail a "plan" if it isn't one - name it as a hypothesis.
    - [Airfocus - What Is ASD?](https://airfocus.com/glossary/what-is-adaptive-software-development/)

15. **Cynefin's probe-sense-respond gives the epistemic justification for why far-task detail cannot be known upfront in complex domains** (confidence: high)
    "In the complex domain, one can perceive the relationship between cause and effect only in retrospect, but not in advance." The prescribed response is small, fail-safe experiments (probes), sensing the outcome, then responding - explicitly not "plan the solution and execute." This underwrites SPEC-015's hypothesis that far-task detail is fiction the planner cannot actually possess yet, as opposed to detail that's merely inconvenient to write.
    - [ModelThinkers - Cynefin Framework](https://modelthinkers.com/mental-model/cynefin-framework)

16. **Denne/Cleland-Huang's Incremental Funding Method decomposes work into Minimum Marketable Features (MMFs) sequenced by ROI, not into a single big plan with graded detail** (confidence: medium)
    IFM's contribution is scheduling *self-contained* value-bearing chunks (MMFs) rather than task-level detail gradation; it's a sequencing/ordering discipline layered on top of decomposition, oriented at financial ROI rather than knowledge-elaboration. Less directly transferable to SPEC-015's wave-elaboration mechanic than ASD or Shape Up - it answers "in what order" more than "how much detail per wave."
    - [ResearchGate - The Incremental Funding Method](https://www.researchgate.net/publication/3248118_The_incremental_funding_method_Data-driven_software_development)

### Dual-track (adjacent, discovery/delivery split)

17. **Jeff Patton's dual-track agile runs discovery and delivery as parallel continuous tracks with the same people, not sequential phases** (confidence: medium)
    "Two tracks, not two teams" - the same people alternate between discovery activities (interviews, probing the "why") and delivery (building what discovery validated). This is the named practitioner answer to SPEC-015's own non-goal reference to the "human-review-model redesign... WHERE review lands": dual-track shows discovery-track output (validated understanding) feeding delivery-track input continuously, rather than a single upfront discovery phase gating all delivery.
    - [Academy4PM - Dual Track Agile, Jeff Patton](https://academy4pm.org/lessons/dual-track-agile/)

### Failure modes

18. **"Refinement theater" as a named phrase is not established in the literature; the underlying anti-patterns are, and they cluster on frequency, not depth** (confidence: medium)
    Practitioner sources (age-of-product.com's widely cited "28 anti-patterns" piece) document "too detailed refinements" as a distinct, named anti-pattern alongside "not enough" and "too many" refinements - confirming the *decay toward over-elaboration* SPEC-015 worries about is a recognized, real failure mode in the field, even without the exact "theater" label. A second named anti-pattern: refinement done by individuals in isolation rather than the whole team, producing tickets nobody but the author understands - relevant if Compass's elaboration step is a solo builder pass rather than a checked step.
    - [age-of-product.com - 28 Product Backlog and Refinement Anti-Patterns](https://age-of-product.com/28-product-backlog-anti-patterns/)

19. **The improvisation-decay failure mode (no one elaborates, work starts anyway) is the documented flip side of "too detailed"** (confidence: medium)
    The same anti-pattern taxonomy lists "unprepared refinements" (PO lacks necessary detail going in) and "rare refinement" (infrequent sessions leave items unclear) as the under-elaboration counterpart. Both directions are named failure clusters, which supports SPEC-015 treating "degenerates into improvisation" as a real, not hypothetical, risk requiring its own falsification check rather than being dismissed as unlikely once over-elaboration is guarded against.
    - [age-of-product.com - 28 Product Backlog and Refinement Anti-Patterns](https://age-of-product.com/28-product-backlog-anti-patterns/)

20. **Sprint-boundary rigidity is independently documented outside Kanban's own literature** (confidence: medium)
    Practitioner criticism (Medium, "Why Sprints Are Useless") echoes Anderson's DJAA argument from outside the Kanban camp: fixed timeboxes cause rushed hasty implementations near boundary close, or padding of low-priority work to fill the box, and force cross-team dependency friction at sprint edges. Converging independent sources on the same failure shape raises confidence that *any* fixed-size wave (not just Scrum sprints) risks this failure if Compass's wave sizing is naive fixed-N-tasks.
    - [Medium - Why Sprints are Useless for Agile Teams](https://medium.com/@shub-sharma/why-sprints-might-be-useless-for-your-truly-agile-team-d4dbd9629273)

## Approval-semantics map

| Methodology | What the authority figure approves | When | Granularity of the approval | Re-approval needed for later detail? |
|---|---|---|---|---|
| XP | Task claims (self-selected by developer) at iteration commitment | Start of each 1-2 week iteration | Per-task, per-person | Next iteration is a fresh commitment cycle, not a re-approval of prior scope |
| Scrum | Sprint Backlog (stories meeting DoR) at Sprint Planning | Start of each sprint | Per-sprint, all committed stories | No - refinement of future items happens continuously, off the sprint approval |
| Kanban | Individual work item at the commitment-point line (pull) | Continuous (replenishment meeting or on-demand pull) | Per-item, no batch | N/A - there is no batch to re-approve; each item commits independently |
| Shape Up | The shaped pitch as a whole, at appetite-level scope | Once per 6-week cycle, at the betting table | Whole-bet (not per-task) | No - task-level detail is discovered inside the cycle via hill charts, never re-bet |
| ASD (Highsmith) | The speculation (direction), reviewed at cycle-end learn phase | End of each collaborate/learn cycle, feeding next speculate | Whole-cycle direction, not task detail | Re-speculation is a normal cycle step, not a special ceremony |
| Compass (SPEC-015 target) | Near-wave full detail + far-wave shape, at plan approval | Once at plan approval | Near wave: task-level. Far wave: shape-level | No - each elaborated wave presents at its turn without re-approving the whole plan |

The pattern across every methodology surveyed: **the approval event is binary/coarse (approve the batch/cycle/bet), and it is the ELABORATION event that is fine-grained and frequent** - never the reverse. No surveyed methodology re-runs the approval ceremony when detail is added; they run a *cheaper*, different-shaped step (iteration commitment, hill-chart update, replenishment pull, next speculation) for that. This directly supports SPEC-015's Need #3 ("each elaborated wave is presented at its turn without re-approving the whole") as consistent with how every surveyed methodology actually operates, not a novel invention.

## Mapping to SPEC-015's open questions

- **Wave sizing (fixed horizon vs. dependency-frontier vs. planner judgment):** No surveyed methodology uses a pure fixed-N-tasks horizon without complaint. Scrum's fixed-timebox sprint draws direct, converging criticism (findings 8, 20) for forcing artificial decomposition and dependency friction at the boundary. Shape Up uses a fixed *time* appetite but explicitly flexible *scope* inside it (finding 9) - the fixed dimension is cost, not task count. Kanban uses no fixed horizon at all, just a WIP-limited pull (finding 7). This suggests dependency-frontier or planner-judgment sizing (scope flexes, something else is fixed) has stronger practitioner support than a rigid fixed-N-tasks wave.

- **Where the elaboration record lives:** Shape Up's hill chart is the clearest published analogue - a lightweight, visible, separately-updated artifact distinct from the approval record (the pitch/bet). It is not a new approval document; it's a status/scope-discovery log. This favors a per-wave section or log distinct from the plan's approval metadata, updated as its own step, not folded back into re-approval.

- **Coverage gate on unelaborated far tasks (deferred-but-tracked vs. uncovered):** No methodology surveyed treats far-scope items as either "covered" or silently dropped - Scrum's epics and Shape Up's un-bet pitches are both explicitly *visible but not committed* (epic exists and is named; pitch is stored/re-lobbied, finding 12). This favors "deferred-but-tracked" over "uncovered": far tasks should exist as named, scoped placeholders whose citations attach when elaborated, not as absent from coverage until then.

- **Planner's brief change ("specify the frontier, scope the rest"):** XP's release-vs-iteration meeting split (finding 2) and Shape Up's fat-marker/breadboard notation (finding 10) both suggest the brief change should be structural, not just instructional - i.e., the far-tier's *format itself* should be incapable of holding fine detail (a capped scope-and-intent field), rather than relying on planner discipline alone to under-specify voluntarily.

## Contradictions

- Kanban (findings 7, 8) argues against *any* fixed-size wave/timebox, favoring continuous per-item commitment. Scrum and XP (findings 2-6) argue fixed-cadence waves work fine given a strong Definition-of-Ready gate. Shape Up (finding 9) resolves this by fixing cost (appetite) instead of scope or task-count, which sidesteps both positions. SPEC-015's wave-sizing open question sits exactly on this fault line; the surveyed sources don't converge on one answer, they converge on "don't fix task-count naively."
- Highsmith's ASD (finding 14) and Cynefin (finding 15) treat far-detail as fundamentally unknowable in advance (epistemic claim: cause-effect only visible in retrospect). Scrum's Definition of Ready (finding 4) treats far-detail as knowable-but-not-yet-elaborated (a workload claim, not an epistemic one). These imply different failure interpretations for SPEC-015's falsification criterion: is under-specification of far tasks a fact about the world (can't know yet) or a fact about effort (haven't looked yet)? The sources split; SPEC-015 does not currently distinguish the two.

## Gaps

- No source found that documents a *software-planning* methodology combining detail-gradient AND a formal multi-tier coverage/citation gate (Compass's D-NN/lessons binding requirement) - all surveyed methodologies handle traceability informally or not at all. SPEC-015's Need #4 (citations bind at the detail level) appears to be a Compass-specific requirement without a direct precedent in the surveyed practice; would need either deeper literature search into regulated/compliance software methodologies (e.g., DO-178C traceability practices) or treatment as a genuine novel design point.
- "Refinement theater" as an exact named term was not found in a primary or frequently-cited source; the underlying anti-patterns are well documented (finding 18) but the label itself may be informal shorthand introduced elsewhere (possibly in the SPEC-015 author's own vocabulary or a source not indexed by search). Worth checking with the human whether the term has a specific origin they're recalling.
- Did not find quantitative outcome data (e.g., "teams using rolling-wave planning reduced mid-project amendments by X%") for any surveyed methodology - all evidence found is qualitative/practitioner-report, consistent with the general scarcity of controlled studies in software-process research.

## Design takeaways for Compass

- Approval semantics: every methodology surveyed keeps the approval event coarse and the elaboration event fine and frequent, never the reverse (see Approval-semantics map). SPEC-015's Need #3 matches this pattern exactly.
- Structural imprecision beats disciplined imprecision: Shape Up's fat-marker sketches and breadboarding notation make over-specification physically impossible rather than relying on planner restraint (finding 10) - worth considering for the far-tier plan format.
- Fix cost, not scope, at the far tier: Shape Up's appetite (finding 9) is the one surveyed mechanism that makes low far-detail safe by construction rather than by hope - contrast with Scrum/XP where fixed timeboxes without an appetite-like cost cap draw the sprint-boundary-rigidity criticism (findings 8, 20).
- Elaboration needs its own lightweight artifact separate from the approval record (Shape Up's hill chart, finding 13) - not a re-run of the plan-approval step.
- Both failure directions (over-elaboration and improvisation-decay) are independently documented as real, named anti-patterns (findings 18, 19) - SPEC-015's falsification criteria should keep checking both, not assume guarding one guards the other.
