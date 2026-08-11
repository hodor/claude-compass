---
title: "Progressive/Receding-Horizon Planning for AI Agents: What Is Different When Planner and Executor Are LLMs"
type: research
status: complete
confidence: high
area: methodology
tags: [planning, rolling-wave, progressive-elaboration, agents, context-engineering, replanning]
created: 2026-08-11
updated: 2026-08-11
depends_on: ["[[SPEC-015-rolling-wave-planning]]"]
---

# Progressive/Receding-Horizon Planning for AI Agents

## Question

What is known about progressive/receding-horizon planning for AI agents specifically, and what does it imply for a Compass plan as an artifact LLM agents write, elaborate, and execute? (One of three axes on [[SPEC-015-rolling-wave-planning]]; this axis covers what is different when the planner and executors are LLM agents, not general lean/PM theory.)

## Methodology

WebSearch/WebFetch across arXiv (control theory, LLM-agent planning surveys), classical AI planning literature (plan repair vs replanning), and Anthropic engineering blog posts on context engineering and agent design. No sub-agents spawned, per brief. Provenance marked per finding; several full-text fetches returned only partial extraction (noted where it limits confidence).

## Findings

### Formal lineage

1. **Receding-horizon control (MPC) is the literal mathematical form of "detail near, shape far"** (confidence: high)
   MPC computes an optimal trajectory over a prediction horizon, executes only the first step(s), then re-solves from the new state. The theoretical justification is explicit: this "limits the impact of early mistakes" and "corrects for model mismatch, noise, and other unexpected errors" that a plan committed to once cannot.
   - [Receding Horizon Approach - EmergentMind](https://www.emergentmind.com/topics/receding-horizon-approach)
   - [LLMPC: Large Language Model Predictive Control](https://www.mdpi.com/2073-431X/14/3/104) - names LLM planners as "approximate cost function optimizers" solving via iterative short-horizon steps, an explicit LLM-planning application of MPC.

2. **MPC horizon-length theory gives a real, if rough, answer to wave sizing** (confidence: medium)
   Rule of thumb: prediction horizon should span roughly 20-30 sample times of the *transient response* (i.e., cover the time it takes disturbances/decisions to play out), not a fixed count of steps. Horizon length trades control performance against compute cost and reactivity to disturbance; "Adaptive Horizon MPC" varies the horizon length as the process evolves rather than fixing it. Applied to Compass: wave size should track how many tasks it takes for a decision to reveal its consequences (the task-dependency "settling time"), not a constant N.
   - [What is the Prediction Horizon in MPC?](https://picontrolsolutions.wixsite.com/picontrol-solutions/post/what-is-the-prediction-horizon-in-model-predictive-control)
   - [Adaptive Horizon Model Predictive Control](https://arxiv.org/pdf/1602.08619)
   - Confidence held at medium: the 20-30 rule is a controls-engineering heuristic for physical systems, not independently validated for software task graphs.

3. **A named LLM-planning framework (Flare) directly implements receding-horizon commitment** (confidence: high)
   Flare performs explicit lookahead simulating counterfactual future trajectories, propagates trajectory-level outcomes backward to inform early decisions, but commits only to the next action under a receding-horizon scheme - "by committing only to the next action and replanning after each transition, Flare limits the impact of early mistakes" (Prop. 3.1 in the paper proves step-wise-greedy policies are arbitrarily suboptimal for horizon >=2, i.e. *some* lookahead is required, not zero).
   - `arxiv.org/pdf/2605.22138` §3.2, §4.3 ("Efficient Agentic Reasoning Through Self-Regulated Simulative Planning")
   - Gap: the paper does not study how planning *precision* should decay with depth, only that commitment should be short.

4. **Rolling-wave planning (PMBOK) is the pre-existing project-management name for exactly this shape** (confidence: high, provenance: secondary but consistent across multiple PM sources)
   "Rolling wave planning is an iterative planning technique in which the work to be accomplished in the near term is planned in detail, while work further in the future is planned at a higher level... a form of progressive elaboration." This predates LLM agents entirely; SPEC-015 is importing an established PM pattern into an agent-authored artifact, not inventing a new one.
   - [Rolling-wave planning - Wikipedia](https://en.wikipedia.org/wiki/Rolling-wave_planning)
   - [PM Study Circle - Rolling Wave Planning](https://pmstudycircle.com/rolling-wave-planning/)

5. **Hierarchical Task Networks (HTN) already answer the "contract at milestone" question SPEC-015 asks about** (confidence: medium)
   HTN planning decomposes abstract compound tasks into primitive actions via *methods*, and a method's applicability preconditions are checked only when that task is reached for decomposition - not when the parent plan is first authored. This is a 1990s-era formalization of "commit only what you can verify now, decompose the rest when you get there." Recent work integrates LLMs as heuristic generators inside this structure, using HTN to keep procedural knowledge explicit and reduce LLM query frequency up to 75% while preserving plan soundness.
   - [Hierarchical Task Network Planning with LLM-Generated Heuristics](https://arxiv.org/abs/2605.07707)
   - [HTN Planning overview - ScienceDirect Topics](https://www.sciencedirect.com/topics/computer-science/hierarchical-task-network)
   - Direct mapping to SPEC-015 open question 4 (coverage of far tasks): an HTN task is legitimately "not yet decomposed," distinct from "decomposed but uncovered" - a three-state model (elaborated+covered / scoped-not-yet-elaborated / elaborated-but-uncovered) rather than a binary covered/not.

6. **Plan repair vs. full replanning is a settled classical-AI distinction with a stability metric, not just an efficiency choice** (confidence: high)
   Fox, Gerevini, Long & Serina (ICAPS 2006) define *plan stability* as the measurable difference a repair/replan process induces between the original and new plan, and show plan repair (patching the existing plan, preserving unaffected structure) produces more stable results than replanning from scratch, and can be more efficient when minimizing plan makespan is not the goal. This is the classical-planning ancestor of Compass's stated distinction between "elaboration" (repair-like, cheap) and "amendment" (replan-like, ceremony).
   - [Fox et al. 2006, Plan Stability: Replanning versus Plan Repair](https://strathprints.strath.ac.uk/2776/1/strathprints002776.pdf)
   - Van der Krogt & de Weerdt (2005) extend planning techniques specifically to support repair as a first-class operation, not a fallback.

### LLM-specific evidence

7. **A recent survey frames the "how much decomposition" question as an uncertainty property, not a free efficiency win** (confidence: medium)
   "More elaborate decomposition can itself introduce misalignment between the guidance a step receives and what execution actually needs, so the right amount of decomposition is a property of the task's uncertainty, not a free efficiency gain." This directly cautions against over-specifying detail even for *near* tasks if their execution uncertainty is low - detail-per-task should track uncertainty, and proximity is a proxy for uncertainty, not the cause of it.
   - "The Horizon Gap" survey, arXiv:2608.06663, §3 (synthesized from ~1,547 papers 2024-2026)

8. **"Full-horizon planning with on-demand replanning" empirically matched step-by-step monitoring accuracy at 2-3x fewer tokens** for well-defined tasks (confidence: medium, single study cited secondhand via survey, not independently verified)
   This is direct counter-evidence to "always plan minimally and replan often" - for tasks where the task structure is already well-understood, planning the whole horizon upfront and only replanning on-demand (triggered by deviation, not every step) was cheaper without an accuracy cost. Implies wave-boundary triggers should be deviation-based, not fixed-cadence, for low-uncertainty plan segments.
   - "The Horizon Gap" survey, arXiv:2608.06663, §3, citing an unnamed empirical comparison (survey does not name the primary study; verify before treating as load-bearing).

9. **PIVOT names the exact reframe SPEC-015 needs: treat the plan as a refinable object, not a one-time commitment** (confidence: medium)
   PIVOT (cited in the Horizon Gap survey) treats "the plan itself as an object to be refined against execution feedback rather than committed to once," enabling trajectory refinement through repeated environment interaction. This is the LLM-era restatement of plan repair (finding 6) - the mechanism differs (context-window refinement vs. classical-planner patching) but the design stance is identical.
   - "The Horizon Gap" survey, arXiv:2608.06663, §3, §5

10. **Task-decoupled planning replaces one shared reasoning history with a DAG of scoped sub-goals specifically to stop error propagation across unrelated far tasks** (confidence: medium)
    "A shared history lets an error made on one sub-task propagate into otherwise-unrelated decisions" - the fix decouples planning per sub-goal so a mistake in an elaborated near wave cannot silently corrupt the *scope* of an unrelated far wave. Relevant to SPEC-015's elaboration record: elaboration of wave N should not rewrite the stated intent of wave N+2 unless the dependency graph actually connects them.
    - "Beyond Entangled Planning: Task-Decoupled Planning for Long-Horizon Agents," arXiv:2601.07577 (per Horizon Gap survey §5)

11. **Long plans are a measured, not theoretical, context/token burden - "lost in the middle" plus generic summarization actively destroys needed detail** (confidence: high)
    Two distinct failure modes are documented: (a) information placed away from the context edges is used less reliably ("lost in the middle" - matches Compass's own ADR-004 rationale for the hot-path cap); (b) generic summarization "compresses away details a later step needs, so the compression policy itself has to be aware of what downstream steps will require" (ACON). A full-detail plan for far tasks is not just wasted tokens; it is actively harder for the agent to use correctly than no detail at all, because it sits in the discard-prone middle of context and gets mangled by any compaction pass that isn't plan-aware.
    - "The Horizon Gap" survey, arXiv:2608.06663, §4 (Memory & Context Management)

12. **"Intrinsic" self-correction (an agent revising its own plan from its own doubt, with no external grounding) does not reliably help and can hurt** (confidence: high, survey-reported meta-finding)
    Self-correction without external grounding shows an "accuracy-correction paradox": weaker models correct themselves more often than stronger models, because stronger models' errors are structurally deeper and less accessible to self-critique. Self-correction that *is* externally grounded (checked against a tool result, a test run, a human review) performs better. Direct implication for Compass's elaboration step: elaboration must be grounded in the *completed* task's actual output/verification result, not the planner's own re-reading of its earlier plan text.
    - "The Horizon Gap" survey, arXiv:2608.06663, §5

13. **Reflexion-style episodic feedback is the dominant documented mechanism for turning execution results into future plan changes, but efficacy evidence for it "at scale" is sparse** (confidence: medium)
    Reflexion converts a failed attempt into natural-language self-feedback stored in an episodic buffer, conditioning the next attempt on it. The survey explicitly flags that "evidence distinguishing which feedback mechanisms improve success for long horizons remains sparse" - this pattern is widely adopted but not strongly validated for the long-horizon case SPEC-015 targets.
    - "The Horizon Gap" survey, arXiv:2608.06663, §5

14. **Anthropic's own agent-design guidance favors iterative feedback loops over extensive upfront planning, but stops short of quantifying detail-vs-distance** (confidence: high for the stated pattern, but the "how much detail" question is explicitly unaddressed by the source)
    "Building Effective Agents" describes orchestrator-worker decomposition happening dynamically at execution time (not predefined upfront) and states "it's crucial for the agents to gain 'ground truth' from the environment at each step... to assess its progress," recommending explicit stopping conditions (max iterations) to bound otherwise-open planning. The source does not specify a detail gradient by horizon distance - it argues for adaptive planning generally, which is compatible with rolling-wave but doesn't independently derive it.
    - [Anthropic - Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)

15. **Anthropic's context-engineering guidance gives three concrete, load-bearing mechanisms for an elaboration record: structured note-taking, just-in-time reference loading, and detail-aware compaction** (confidence: high)
    - Structured note-taking: "the agent regularly writes notes persisted to memory outside of the context window... pulled back into the context window at later times," citing Claude Code's own to-do list as the canonical example. This is a direct existing-practice precedent for a plan-appendix-style elaboration record living outside the main plan body.
    - Just-in-time loading: agents "maintain lightweight identifiers (file paths, stored queries, web links) and use these references to dynamically load data into context at runtime," trading exploration latency for storage efficiency and progressive disclosure - the retrieval-side analogue of "scope far tasks by named intent, elaborate on arrival."
    - Compaction: preserves "architectural decisions, unresolved bugs, and implementation details" while discarding "redundant tool outputs" - i.e., production agent systems already draw the same near/far distinction Compass wants, just for conversation history rather than a plan document. The blog gives no explicit rule for *how much* to preserve by horizon distance; it is tuned empirically ("maximize recall, then iterate to improve precision").
    - [Anthropic - Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

16. **HTN-LLM hybrids report replanning is still an open research question even in the structured-planning world**, not a solved efficiency knob (confidence: medium)
    "Determining when to replan and how to make good use of the planning tree of the last plan" is named as a live hot spot for future study in HTN/MCTS replanning work, even with explicit symbolic structure available. This tempers any expectation that Compass can adopt a fixed, provably-optimal wave-boundary trigger; the wider field has not solved this either.
    - [ICAPS Workshop on Hierarchical Planning Proceedings 2025](https://icaps25.icaps-conference.org/files/HPlan/HPlanProceedings-2025.pdf) (per search synthesis; proceedings not independently fetched in full - confidence held at medium)

## Contradictions

- Finding 2 (MPC: shorter horizon reacts faster to disturbance, tune horizon to settling time) sits in tension with finding 8 (empirical LLM result: full-horizon upfront planning with on-demand replanning matched step-wise monitoring at lower cost for well-understood tasks). Resolution implied by finding 7: the right amount of far-detail is a function of *task uncertainty*, not a universal preference for either short or long horizons - low-uncertainty plans can front-load detail cheaply; high-uncertainty plans cannot.
- Finding 12 (grounded correction good, intrinsic self-correction unreliable) argues elaboration must be triggered by verified execution results. Finding 9/6 (PIVOT/plan-repair: treat plan as continuously refinable) could be read as license for the planner to revise on its own judgment more freely. The synthesis: refinement mechanism should stay repair-like and cheap (finding 6), but the *trigger* for a refinement must be an external/verified signal (finding 12), not the planner second-guessing itself.

## Gaps

- No source directly measures how planning-detail precision should decay as a mathematical function of horizon distance for *software task* graphs specifically (all quantitative horizon-length guidance found is from physical-systems MPC, finding 2).
- No source gives a validated trigger rule for wave-boundary timing (fixed N vs. dependency-frontier vs. judgment) beyond "deviation-triggered beats fixed-cadence for well-understood tasks" (finding 8, single secondhand-cited study) and "even HTN/MCTS hybrids consider this an open problem" (finding 16).
- Finding 8's primary study was not independently located or fetched; treat as suggestive, not confirmed, until traced to source.
- Nothing found specifically evaluates coverage-gate semantics (SPEC-015 open question 3: how citations/decisions coverage should treat not-yet-elaborated far tasks) in any agent-planning literature; the closest analogue is the HTN precondition-check-at-decomposition-time pattern (finding 5), which is a structural answer, not an evaluated one.

## Design takeaways for Compass

- Wave sizing has no universal constant; the literature converges on "size the wave to how long it takes a decision's consequences to become visible" (MPC settling-time analogue, finding 2) and "detail should track task uncertainty, not raw distance" (finding 7) - both argue against a fixed N and for a judgment/dependency-frontier rule, with deviation-triggered re-elaboration (finding 8) rather than fixed-cadence.
- The elaboration record has direct production precedent as an out-of-band, persisted note structure (Claude Code's own to-do list is the cited example, finding 15) rather than inline plan-body edits - consistent with SPEC-015's "plan appendix vs per-wave section" framing.
- Elaboration should be triggered by grounded, verified signals from the completed wave (test results, build output), not by the planner's own re-reading of its earlier intent (finding 12) - this gives a concrete gate for "what counts as new knowledge" in the elaboration record.
- Far-task coverage is better modeled as a three-state system (elaborated+covered / scoped-but-not-yet-decomposed / elaborated-but-uncovered) than a binary, following the HTN precondition-at-decomposition pattern (finding 5) - this may directly answer SPEC-015 open question 3.
- A fully-detailed far-task plan is not neutral; it actively degrades under "lost in the middle" and non-plan-aware compaction (finding 11), so over-specifying far tasks is a cost with no offsetting accuracy benefit for high-uncertainty work, reinforcing the spec's core hypothesis from the LLM-context-mechanics side, independent of the human-approval-ceremony argument already in the spec.
