---
title: "Flow and Lean Product-Development Theory Behind Rolling-Wave Planning"
type: research
status: complete
confidence: high
area: methodology
tags: [planning, rolling-wave, progressive-elaboration, flow, lean, reinertsen, cost-of-delay, batch-size]
created: 2026-08-11
updated: 2026-08-11
git_branch: "master"
git_commit: "268aebc"
author: "researcher (Claude)"
depends_on: ["[[SPEC-015-rolling-wave-planning]]"]
summary: "flow and lean product-development theory behind it"
---

# Flow and Lean Product-Development Theory Behind Rolling-Wave Planning

## Question

What do Reinertsen and the flow/lean product-development lineage establish about committing plan detail progressively rather than upfront, and what transfers to Compass's plan format, elaboration step, and approval semantics? Scoped to [[SPEC-015-rolling-wave-planning]]'s Needs and open questions on wave sizing, elaboration-record placement, coverage handling of far tasks, and the planner's brief.

## Methodology

WebSearch across primary and near-primary sources (Reinertsen's own frameworks via book-summary sites and a dedicated principles compendium, PMI/PMBOK definitions, Lean Construction Institute material on the Last Planner System, MIT Sloan Management Review on Toyota SBCE, Poppendieck/Matts primary concepts). One WebFetch attempt against a primary Reinertsen principles list failed (expired TLS cert, noted in Gaps); a secondary WebFetch against a book-summary site substituted. No sub-agents spawned per brief.

## Findings

### Axis 1: Reinertsen - batch size, WIP, cost of delay, decentralized control

1. **Batch size economics is a U-curve, and plan detail is a batch** (confidence: high)
 Reinertsen's central economic argument: batch size trades off Transaction Cost (fixed cost paid per batch, falls per-unit as batch grows) against Holding Cost (cost of carrying unfinished work, rises with batch size - capital tied up, delayed feedback, obsolescence risk). The optimum is an intermediate value, not zero or infinity, and the curve has a flat bottom so a range of batch sizes performs near-equivalently. Applied to planning: writing detail for many tasks in one pass is a large batch (low per-task transaction cost, high holding cost because far detail is carried unused and may go stale before it's read); writing detail for one task at a time is the opposite extreme.
 - [The Principles of Product Development Flow book review/summary](https://ardalis.com/principles-of-product-development-flow-book-review/)
 - [se-trends.de: The 175 flow principles](https://www.se-trends.de/en/the-175-flow-principles-why-product-development-is-often-slower-than-necessary/)

2. **"Shorter planning horizons produce more stable requirements; extended planning horizons create inventory of changing specifications"** (confidence: medium)
 Direct paraphrase of Reinertsen's Second Generation Lean Product Development framework: the further out a specification is written, the more likely it is to be invalidated before it's acted on, so extending the planning horizon does not add value proportionally, it adds inventory that decays. This is the single most direct load-bearing finding for SPEC-015's premise that far-task detail is speculative.
 - [Hans Samios: Second Generation Lean Product Development summary](https://www.hanssamios.com/dokuwiki/second_generation_lean_product_development_by_don_reinertsen)
 - Confidence held at medium: sourced from a structured secondary summary, not a page-cited primary quote (see Gaps).

3. **Cost of Delay is the principle for deciding what gets full detail first, not just a prioritization metric** (confidence: high)
 Reinertsen: "If you only quantify one thing, quantify the cost of delay" - most organizations (his figure: 85%) lack this number and substitute proxies (schedule, efficiency, quality) that don't answer the economic question. For a rolling-wave plan, cost of delay is the criterion for wave sizing: the next wave should be whatever work has the highest cost-of-delay-weighted urgency to be fully specified now, not simply "the next N tasks in file order."
 - [se-trends.de: The 175 flow principles](https://www.se-trends.de/en/the-175-flow-principles-why-product-development-is-often-slower-than-necessary/)
 - [Product Economics guide, agility-at-scale.com](https://agility-at-scale.com/principles/product-economics/)

4. **Design-in-process inventory (DIP) is the product-development analogue of manufacturing WIP, and it is unusually expensive to carry** (confidence: high)
 From *Managing the Design Factory*: DIP is the sum of investment in incomplete designs/specifications, which earns nothing until completed. Reinertsen's point: manufacturing plants turn inventory 50+ times a year; development processes rarely turn DIP more than once a year, so DIP levels compound in cost far more than factory WIP does. A fully-detailed far-future task is DIP: capital (planner effort, human review attention) invested in a "recipe" that produces no value until executed, and may need to be re-done before it ever is.
 - [Amazon/publisher listing, Managing the Design Factory](https://www.amazon.com/Managing-Design-Factory-Donald-Reinertsen/dp/0684839911)

5. **WIP constraints control lead time; Little's Law is the mechanism** (confidence: high)
 "Limit WIP to control lead time" - queue size divided by processing rate gives wait time (Little's Law); doubling the amount of concurrently-open work roughly doubles wait times. Applied to planning: a plan that opens (fully details) many tasks at once before any executes is high planning-WIP, and each of those tasks waits longer (in calendar time before build) for the knowledge that would let it be re-validated.
 - [se-trends.de: The 175 flow principles](https://www.se-trends.de/en/the-175-flow-principles-why-product-development-is-often-slower-than-necessary/)

6. **Queue economics: utilization near 100% drives queue size toward infinity** (confidence: high)
 Reinertsen's queueing formula ρ/(1-ρ) shows queue size explodes non-linearly as utilization (ρ) approaches 1; manufacturing systems typically cap around 85% utilization for this reason. This is the formal reason "specify everything now" back-loads risk: it maximizes utilization of planning effort in the short run at the cost of an exploding backlog of detail that must be revisited when reality diverges.
 - [Hans Samios: Second Generation Lean Product Development summary](https://www.hanssamios.com/dokuwiki/second_generation_lean_product_development_by_don_reinertsen)

7. **Decentralized control: state the mission and boundary conditions, let the executor fill in method** (confidence: high)
 Boeing 777 example: any of 5,000 engineers could unilaterally spend up to $300 per unit to save a pound of weight - a decision rule, not a detailed instruction, that let local actors make system-optimal trade-offs without escalation. Reinertsen's framing: "Describe the mission and boundary conditions, not the detailed plan." This is the direct analogue for far-wave scope-and-intent: state what the far task must accomplish and its constraints, not its file-level implementation, and let the wave that elaborates it fill in the method with then-current knowledge.
 - [Product Economics guide, agility-at-scale.com](https://agility-at-scale.com/principles/product-economics/)
 - [se-trends.de: The 175 flow principles](https://www.se-trends.de/en/the-175-flow-principles-why-product-development-is-often-slower-than-necessary/)

8. **Variability is not uniformly bad - it is the source of innovation and must be economically managed, not eliminated** (confidence: high)
 Reinertsen explicitly rejects Six-Sigma-style variance elimination as a universal good: "without variability, there is no innovation." His prescribed responses are to reduce the *consequences* of variability (buffers trade money for variability absorption) or substitute cheap variability for expensive variability, not to drive variance to zero. Applied to planning: a plan that pre-commits far-task detail is implicitly trying to eliminate the variability of "what we'll know later," which forecloses the option value that variability (new information) creates.
 - [Exploiting Variability: A Principle of Product Development Flow](https://agilecomplexificationinverter.blogspot.com/2017/05/exploiting-variability-principle-of.html)
 - [se-trends.de: The 175 flow principles](https://www.se-trends.de/en/the-175-flow-principles-why-product-development-is-often-slower-than-necessary/)

### Axis 2: The surrounding lineage

9. **Toyota's Second Paradox: delaying convergence produces faster, not slower, cycles** (confidence: high)
 Set-Based Concurrent Engineering (SBCE): Toyota maps a broad design space per functional group, communicates *sets* of solutions (not single point designs), and eliminates alternatives only when proven inferior or infeasible - narrowing gradually via "integration by intersection" and "establishment of feasibility before commitment." All communication about the set stays valid as it narrows; nothing needs retraction, only supplementation. This is the closest engineering-process analogue to a plan's far-wave staying a valid *scope* statement while its detail narrows.
 - [Toyota's Principles of Set-Based Concurrent Engineering, MIT Sloan Management Review](https://sloanreview.mit.edu/article/toyotas-principles-of-setbased-concurrent-engineering/)
 - [Second Toyota Paradox, Open Source Ecology](https://wiki.opensourceecology.org/wiki/Second_Toyota_Paradox)

10. **Last Planner System: a five-stage cascade from strategic shape to executable commitment, each stage narrowing scope and expanding detail** (confidence: high)
 LPS's five deliverables, each filtering from the one above: master schedule (macro strategic baseline: phases, zones, milestones, buffers - no task-level detail), pull plan, look-ahead (6-8 weeks: constraint identification and removal, work made "ready"), weekly work plan (specific people commit to specific tasks, only after constraints are cleared), day plan. This is the most directly transferable industrial analogue for SPEC-015's near/far gradient: it names three concrete detail tiers (strategic, prepared, committed) rather than a single fixed cutoff.
 - [Last Planner System, Lean Construction Institute](https://leanconstruction.org/lean-topics/last-planner-system/)
 - [Understanding the Last Planner System, Procore](https://www.procore.com/library/last-planner-system)

11. **LPS's look-ahead stage is explicitly a constraint-removal function, not a detail-writing function** (confidence: high)
 The 6-8 week look-ahead window exists to identify and resolve constraints (missing materials, permits, prerequisite work) *before* a task is allowed into the weekly commitment stage - a task only becomes eligible for full commitment once its constraints are cleared. This maps onto an elaboration-step design question SPEC-015 raises: elaboration should be gated on "is this task's precondition knowledge now available," not purely on calendar/task-count proximity.
 - [Elevate Constructionist: Lookahead Planning](https://elevateconstructionist.com/last-planner-in-construction-lookahead-planning-make-ready-planning-explained/)

12. **LPS commitment is structured as five conversations: should, can, will, did, learn** (confidence: high)
 The weekly work plan is framed as a sequence of speech-acts (what should be done -> what can be done given constraints -> what we will commit to -> what we did -> what we learned), and Percent Plan Complete (PPC, the fraction of weekly promises kept) is the closing metric of the loop. This is a candidate structure for an elaboration record: it names promise-vs-actual as the unit that closes the loop, not just "detail was added."
 - [Last Planner System, Lean Construction Institute](https://leanconstruction.org/lean-topics/last-planner-system/)

13. **PPC is widely reported as misused as a punitive score rather than a learning signal** (confidence: medium)
 Practitioner sources converge that PPC's stated purpose is root-cause learning (why a promise wasn't kept), but in practice it is frequently treated as a pass/fail team score, and teams that don't record variances/reasons alongside the percentage get no improvement value from it. This is a direct cautionary precedent for SPEC-015's elaboration record: a bare completion percentage or "waves elaborated" count would repeat this failure; what must be captured is *why* the estimate changed, not just that it did.
 - [Last Planner System PPC, Elevate Constructionist](https://elevateconstructionist.com/what-is-the-last-planner-system-ppc/)
 - [5 Major Mistakes Teams Make Implementing the Last Planner System](https://www.linkedin.com/pulse/5-major-mistakes-teams-make-implementing-last-planner-susan)

14. **PMI formalizes the general case (progressive elaboration) and the specific technique (rolling wave)** (confidence: high)
 PMBOK: progressive elaboration is "continuously improving and detailing a plan as more detailed and specific information and more accurate estimates become available" - the general principle. Rolling wave planning is PMI's named technique under that principle, specifically time-phased: "work to be accomplished in the near term is planned in detail, while work further in the future is planned at a higher level," applicable to work packages, planning packages, and release planning under either agile or waterfall. SPEC-015's "plan format expressing graduated detail" need is this technique applied to Compass's task list.
 - [Rolling-wave planning, Wikipedia](https://en.wikipedia.org/wiki/Rolling-wave_planning)
 - [PM Study Circle: Rolling Wave Planning](https://pmstudycircle.com/rolling-wave-planning/)

15. **Poppendieck's Last Responsible Moment: defer, but do not drift past the point where an option disappears** (confidence: high)
 Definition: the last responsible moment is "the moment at which failing to make a decision eliminates an important alternative." The Poppendiecks explicitly warn against the failure mode SPEC-015's falsification criteria also name: "if commitments are delayed beyond the last responsible moment, then decisions are made by default" - i.e., undecided detail doesn't stay open-ended for free, it silently forecloses into whatever happens by accident. Their stated practice: start development with partial requirements, work in short iterations, let the system's feedback complete the specification.
 - [The Last Responsible Moment, Coding Horror](https://blog.codinghorror.com/the-last-responsible-moment/)
 - [Lean Software Development, Poppendieck summary](https://williammeller.com/lean-software-development-mary-tom-poppendieck/)

16. **Real Options formalizes *why* deferral is economically rational, not just prudent: options have value, options expire, never commit early unless you know why** (confidence: high)
 Chris Matts and Olav Maassen's real-options framing (borrowed from financial option theory) treats an undecided design/plan choice as an asset with time value: keeping it open has a price (the option's premium: some ongoing ambiguity cost) but exercising it too early destroys optionality with no compensating benefit. Their compressed rule - "Options have value. Options expire. Never commit early unless you know why." - gives SPEC-015 a decision criterion to answer "why commit this task to full detail now" other than "it's next in the list": commit when the option to defer would expire before the task is reached, not merely when it becomes chronologically closest.
 - [ProjectManagement.com: Chris Matts on Real Options](https://www.projectmanagement.com/blog-post/7710/chris-matts-on-real-options-and-commitment---the-graphic-novel-about-managing-project-risk)
 - [Real Options with Chris Matts, DevOpsChat](https://www.devopschat.net/2017/04/19/real-options/)

17. **Real Options names TDD/refactoring-enabled design as a concrete mechanism that creates deferral options in code, not just in planning** (confidence: medium)
 The same source material states that test-driven development and behavior-driven development "provide options by enabling refactoring, which removes the need for design commitments and allows design choices to be deferred until after coding has started" - i.e., the option to defer a decision is not free-floating, it has to be manufactured by how the surrounding system is built (testable, refactorable code creates option value; brittle code destroys it). This is adjacent evidence, not a plan-format finding, but bears on whether Compass's far-task scope-only tasks are safe to leave underspecified: they're safer under-specified if the codebase they touch is well-tested and refactor-safe, riskier if not.
 - [ProjectManagement.com: Chris Matts on Real Options](https://www.projectmanagement.com/blog-post/7710/chris-matts-on-real-options-and-commitment---the-graphic-novel-about-managing-project-risk)

### Axis 3: Critiques and boundary conditions

18. **Boehm's cost-of-change curve is the classic argument FOR upfront detail, but it does not hold uniformly, and Boehm himself walked it back** (confidence: high)
 Boehm's 1970s-80s TRW/IBM data showed defect-fix cost rising up to ~100x from requirements to post-deployment, historically used to justify waterfall's heavy upfront specification (the physical-construction framing: "you can't pour the foundation, decide midway the bridge should be 20% longer"). Two caveats found directly bear on where rolling-wave planning is the wrong tool: the curve is steep specifically where change is physically or contractually expensive to make later (irreversible construction, fixed-price contracts, safety-certified systems), and current commentary (including characterizations of Boehm's own 2001 revision) notes the curve is "far flatter than most people assume" once modular architecture, automated testing, and CI exist to cheapen late change. The boundary condition for Compass: rolling-wave detail deferral assumes the codebase and task structure make late elaboration cheap (test coverage, modularity); where a plan's far tasks touch something structurally hard to change late, more upfront detail is the economically correct call, not a process failure.
 - [Boehm Cost of Change Curve: What the 1981 Data Actually Shows](https://reworkcost.com/boehm-cost-of-change-curve)
 - [The Cost of Change Curve Is Outdated, Mountain Goat Software](https://www.mountaingoatsoftware.com/blog/the-cost-of-change-curve-is-outdated)

19. **Rolling-wave planning's named risk: unresolved far-term uncertainty can surface as an unmanaged shock, not a graceful re-elaboration** (confidence: medium)
 Practitioner sources on rolling-wave planning name its central risk plainly: because far-out work is intentionally under-specified, the project "can face unexpected huge issues or costs" when that work is finally reached, and the same sources recommend against the technique specifically for "critical and huge projects where the money invested is so high that any risk can represent massive losses" or where mistakes carry environmental/safety/political impact - explicitly recommending upfront full-detail planning for those. The technique is recommended instead for exactly the profile "uncertainty and innovation needs, such as software development and R&D projects" - which is Compass's actual domain, but the sources' own boundary condition should be stated, not assumed away.
 - [How to Use Rolling Wave Planning for Dealing with Huge Projects, LinkedIn](https://www.linkedin.com/pulse/how-use-rolling-wave-planning-dealing-huge-projects-eduardo-levenfeld)
 - Confidence held at medium: these are practitioner blog-level sources, not peer-reviewed or primary PMI text, though they converge with the LPS/SBCE material's safety-critical caveat.

20. **Last Planner System's own literature names coordination-heavy dependency structures as the place the system is hardest to run well** (confidence: medium)
 The reviewed LPS material does not name outright failure conditions as explicitly as the rolling-wave sources, but the repeated emphasis on constraint identification/removal as the load-bearing function of the look-ahead stage (Finding 11) implies the corollary: where a task's constraints (upstream dependencies, cross-team coordination) cannot be resolved within the look-ahead window, or where many tasks share tangled interdependencies, the near/far split degrades, because a "near" task that still has unresolved cross-cutting dependencies isn't actually ready for full commitment no matter how close it is in sequence. This is an inference from the constraint-removal framing (Finding 11), not a directly quoted failure-mode statement, hence medium confidence.

## Contradictions

- Finding 6 (Reinertsen: high utilization drives queues toward infinity, so keep planning-WIP low) and Finding 3 (cost of delay should drive what gets detailed first) can pull in different directions on wave sizing: a strict WIP cap says "detail only what's next," while a cost-of-delay-first rule could argue for detailing a far-but-urgent task ahead of a near-but-low-value one. Reinertsen's own framework resolves this via WSJF (Weighted Shortest Job First - a queuing discipline that combines both cost-of-delay and job-size), not by picking one signal exclusively; SPEC-015's wave-sizing answer should account for both dimensions rather than pure sequence order or pure urgency alone.
- Finding 18 (Boehm: upfront detail is right for high-change-cost, safety-critical, contractual work) and Finding 19 (rolling-wave sources: avoid it on huge/high-risk projects) state the same boundary condition from opposite literatures (software engineering measurement vs. project-management practice), which is convergence, not contradiction, but is worth flagging as two independent bodies of work agreeing on the same limit rather than one echoing the other.

## Gaps

- No primary-source access to Reinertsen's actual numbered principle codes (B-series for batch size, W-series for WIP, Q-series for queues, D-series for decentralized control, etc., as referenced in the assignment brief) was achieved in this pass. The one dedicated compendium found (`lpd2.com/sample-page/the-175-principles-of-flow/`) failed to fetch (expired TLS certificate); a secondary attempt via `se-trends.de`'s summary of that same compendium returned prose paraphrases of the principles without their numeric codes. All Reinertsen findings above are confirmed in substance (multiple independent secondary sources agree) but not tied to the book's own numbering scheme. Worth a direct attempt to obtain a physical/PDF copy of *The Principles of Product Development Flow* or `lpd2.com` via a different fetch path if the exact B-NN/W-NN/D-NN codes are needed for citation-grade precision.
- The specific Reinertsen chapter/page for "Planning Detail vs. Waste" (Finding 2, the single most directly load-bearing claim for SPEC-015) traces to one structured secondary summary, not a page-cited primary quote. It is stated with enough independent conceptual support (Findings 1, 4, 5, 6 all point the same direction from the batch/DIP/WIP/queue angles) that the underlying economics is not in doubt, but the exact wording should be treated as a paraphrase, not a verbatim citation, if quoted in a spec or ADR.
- Toyota SBCE (Finding 9) and LPS (Findings 10-13) were surveyed via secondary/tertiary sources (MIT Sloan Management Review summary, Lean Construction Institute practitioner pages), not the original Ward/Sobek SBCE paper or Ballard's original LPS thesis. Sufficient for design-transfer purposes at this confidence level; a deeper academic pass would go to Sobek, Ward & Liker (1999, Sloan Management Review, the SBCE original) and Ballard's 2000 dissertation directly.
- No source in this pass gave a quantified or formal answer to "how many waves ahead should stay near-detail" (wave sizing as a number, not a principle) - Reinertsen's queueing math (Finding 6) and WSJF (implied by Contradiction 1) are the closest formal levers found, but neither yields a concrete wave-count recommendation; this remains a design decision for the planner, not something the literature answers directly.

## Design takeaways for Compass

- **Wave sizing is not purely sequential.** Reinertsen's WSJF logic (Contradiction 1) argues the next wave should be chosen by cost-of-delay-weighted priority, not strict task order; SPEC-015's planner brief should let the planner reorder or pull forward a high-cost-of-delay far task rather than mechanically always detailing "the next N tasks."
- **The elaboration record should capture the reason detail changed, not just that it changed.** LPS's PPC misuse pattern (Finding 13) is a direct warning: a bare "waves elaborated: 3" counter without the *why* (what was learned, what estimate moved and because of what) reproduces PPC's documented failure to produce learning value. The elaboration record's minimum shape, per this literature, is closer to LPS's should/can/will/did/learn structure than a changelog line.
- **A three-tier detail gradient (not two) has industrial precedent.** LPS names three: master-schedule (strategic shape, no task detail), look-ahead (constraint-cleared, ready but not yet committed), weekly-commitment (full detail, person-assigned). SPEC-015's "full near / scope-and-intent far" binary could instead be a near / ready-but-not-committed / far three-tier structure, with the middle tier's job being explicitly constraint-removal (Finding 11) rather than detail-writing.
- **Elaboration should be gated on constraint-clearance, not just proximity.** Finding 11's look-ahead function (identify and resolve blockers before a task is eligible for full commitment) suggests the trigger for "elaborate this task now" is "its prerequisite knowledge now exists," which may not line up perfectly with "it's next in sequence" - a near task blocked on an unresolved dependency is not actually ready for full detail even though it's close.
- **Decentralized control gives language for what "far" detail should say.** Reinertsen's Boeing 777 example (Finding 7) and SBCE's set-communication (Finding 9) both point to the same shape for scope-only far tasks: state the mission/boundary conditions/decision rule (what must be true when this task is elaborated, what constraints bound it), not a method. This is a concrete answer to SPEC-015's open question about what "scope and intent" should contain structurally.
- **Real Options gives an explicit commit-or-defer test, not just "wait as long as possible."** Matts/Maassen's rule (Finding 16) - commit only when you know why - and Poppendieck's last-responsible-moment (Finding 15) both name the failure mode SPEC-015's falsification criteria already anticipate (drift into improvisation / silent default-decisions): the literature's answer is that deferral must be a tracked decision with a named trigger for when it converts to commitment, not an indefinite absence of detail.
- **The boundary conditions are explicit in the literature, not just inferred.** Both Boehm's lineage (Finding 18: high change cost, contractual, safety-critical work) and rolling-wave practitioner literature (Finding 19: very high-stakes/irreversible projects) name the same limiting case independently. Compass's plan format should probably let a plan (or a specific task within it) opt out of the gradient and require full upfront detail when the task touches something structurally expensive to change late (e.g., a data-migration-shaped task, a public API contract, a security-sensitive path) - this is a designed escape hatch, not a gap in the technique.
