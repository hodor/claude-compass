---
title: "Axis 4: a difficulty-keyed checking rule and its record"
type: research
status: complete
confidence: medium
area: tooling
tags: [tokens, cost, verification, routing, difficulty, models, adr]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
depends_on: ["[[SPEC-034-checking-cost-follows-task-and-model]]", "[[research/llm-research/REVIEW-llm-research-for-compass]]"]
summary: "Prior art for choosing checking depth from difficulty and model (predictors, cascades, adaptive verification) and the Compass ADRs that bound a recorded rule table; most numbers are abstract-level, and no source keys checking depth rather than model choice"
---

# Axis 4: a difficulty-keyed checking rule and its record

From [[SPEC-034-checking-cost-follows-task-and-model]]. Index: [[research/whole-overhead/checking-cost/index]].

## Question

What prior art says how to choose verification depth from task difficulty and model, how difficulty is estimated before the run, and how the choice can be recorded as a deterministic rule; and what Compass already decided on these?

## Methodology

Technology landscape / comparative evaluation (DESMET-style feature analysis, case-study mode): the candidates are difficulty predictors, cascade routers, adaptive-verification schemes and Compass's own decision records, compared on what each keys on and what it costs. Fits because the axis asks which of several concrete mechanisms exist and what each gives, with no experiment run here.

Grading: allowed. Marks are on every finding. Citation counts were not retrieved (no Semantic Scholar pass); retraction status was not checked beyond noting none appeared in search results. Every 2026 arXiv item below was read at abstract level only (abstract pages fetched, full text not read), so numbers past the abstract are unverified. Some abstract pages came back with small words missing; quotes are kept to short phrases.

Reused first: the existing survey [[research/llm-research/REVIEW-llm-research-for-compass]] claim 8 and item A4 (not re-researched). New here: difficulty prediction, cascades, adaptive verification, and the vault decision grep.

## Findings

### Already established in the vault (reused, not re-verified)

1. **Checks pay at the edge of ability, overhead inside it (survey claim 8, 4 of 4 axes, 3 families).** On Opus 4.6 the evaluator was overhead for in-capability parts and kept lift on hard parts; QA rounds cost $3 to $4 against build rounds $36 to $71. Above a 45% single-agent baseline more agents gave negative returns; agent-written tests moved no resolve rate at 33-49% more input tokens. (confidence: medium)
   - `.compass/research/llm-research/REVIEW-llm-research-for-compass.md:138-144` - A4 evidence list, grades copied from axis files.
   - Marks: vendor post plus preprints, measured on the vendor's own runs; not retracted per survey; preprint status mixed; citation count not retrieved; convergence 4 of 4 axes, 3 families.
   - Grade: medium (vendor numbers are one-run case studies; the preprint numbers are on SWE-bench-style tasks).

### Estimating "inside the model's ability" before the task runs

2. **Item-response-theory difficulty from task text predicts pass or fail per agent (Agent Psychometrics).** A logistic IRT model splits an agent's ability into an LLM part and a scaffold part and predicts a task's difficulty from the issue statement, repository context, solution and test cases. Reported AUROC 0.841 on held-out SWE-bench Verified tasks (0.786 with the problem statement alone); the numbers come from a search-result summary, not the abstract page, which had none. It claims transfer to unseen LLM-scaffold combinations and to other benchmarks. (confidence: medium)
   - https://arxiv.org/abs/2604.00594 - preprint v2, Jul 2026; a search result lists a COLM 2026 citation, unconfirmed on the page.
   - Marks: preprint (venue unconfirmed), measured; no retraction seen; citation count not retrieved; convergence with finding 3 on "difficulty is predictable ex ante, with limits".
   - Grade: medium. The model-versus-scaffold split matches the two keys SPEC-034 names (model and host).

3. **Ex-ante difficulty prediction across 17 agentic benchmarks works only partly out of distribution.** 5,230 tasks, 497 agent configurations, 216 models; task features, especially token-entropy structure, carry a signal, but the abstract states a clear divide between in- and out-of-distribution performance and warns AUC can hide poor calibration. A cited OpenAI audit found 59.4% of 138 frequently failed SWE-bench Verified tasks had material test or description defects. (confidence: medium)
   - https://arxiv.org/abs/2608.05797 - preprint, Aug 2026 (v3 Oct 2026); abstract page read, which names only the entropy feature.
   - Marks: preprint, measured; no retraction seen; citations not retrieved; convergence with finding 2.
   - Grade: medium. The calibration warning bears directly on any threshold keyed to a predicted score.

4. **Task text alone has a Bayes-error floor; a few cheap exploratory turns lift the signal (SWE-Router).** Same-looking issues can be a typo fix or a multi-module refactor, so the router lets a cheap model run a few turns, then a value head reads the partial trajectory and decides continue or escalate. Search summary: Route-AUC 0.780 on SWE-bench Verified against 0.627 for a non-temporal router; the abstract page itself gave no numbers. (confidence: medium-low)
   - https://arxiv.org/abs/2607.00053 - ICML 2026 Deep Learning for Code workshop paper (workshop, not main track).
   - Marks: workshop preprint, measured; no retraction seen; citations not retrieved; convergence: finding 7 reports the nested-solve-set view that pre-run routing is hard.
   - Grade: medium-low (workshop, abstract-level, numbers from a secondary summary).

5. **Past outcomes per task update the difficulty estimate (DAAO).** A VAE estimates query difficulty, a self-adjusting policy updates the estimate from workflow success, and easy queries get simpler workflows, hard ones more complex ones, with a cost- and performance-aware router over heterogeneous LLMs. Reported: up to 11.21% improvement over prior multi-agent systems on six benchmarks; the abstract page gives no per-benchmark numbers or what depth changes at each level. (confidence: medium-low)
   - https://arxiv.org/abs/2509.11079 - accepted WWW 2026 per the page comments; v5 Feb 2026.
   - Marks: peer-reviewed (WWW 2026), measured on general reasoning and code benchmarks, abstract-level; citations not retrieved; convergence with finding 8 on "depth should follow difficulty".
   - Grade: medium. It is the closest match to "workflow depth follows difficulty and model", though it varies generation workflow, not post-hoc checking stations.

6. **Run-level variance is separate from task difficulty.** Two 2026 papers separate task difficulty (pre-execution, IRT labels) from run-level failure on repeated attempts; a blog summary cites runs on one SWE-bench Verified task differing by up to 30x in total tokens. Read at title and search-snippet level only. (confidence: low)
   - https://arxiv.org/html/2610.05572v1 and https://arxiv.org/pdf/2611.08285 - titles and snippets only, full text not read.
   - https://getunblocked.com/blog/model-routing-coding-agents/ - practitioner blog, listed in search results, not opened.
   - Marks: preprints and a practitioner post, claims asserted via secondary summary; citations not retrieved; convergence untested.
   - Grade: low.

### Cascade and routing results for coding agents

7. **Solve sets are largely nested; the handoff, not the routing decision, carried the result (Scrouting / SuperScout).** A 7B searcher explores the repository first and writes a sandbox-checked handoff; on 266 SWE-bench Pro Python tasks the system solved 159 against 158 for the best single model at about a fifth of cost per solve. A no-router variant sending everything to the cheapest fixer matched it; per-fixer effects are "directional only" at N=99. The search summary also reports no learned router reliably beats always calling the strongest model; that sentence is not on the abstract page. (confidence: medium-low)
   - https://arxiv.org/abs/2608.04804 - preprint v2, Nov 2026.
   - Marks: preprint, measured on one benchmark slice; no retraction seen; citations not retrieved; convergence: partly against finding 4 (routing signal) and with finding 8 (simple cascade is strong).
   - Grade: medium-low.

8. **A timeout cascade (small model first, escalate on failure or timeout) cut cost with no accuracy loss and nearly matched an oracle router.** 36 open-weight models on SWE-bench Verified; up to 33% GPU-hour reduction on a subset and 16.4% on all tasks (the page is missing words, so the subset is unclear); the remaining small-large gap is concentrated on hard tasks. Needs no trained router. (confidence: medium-low)
   - https://arxiv.org/abs/2611.24324 - preprint, Nov 2026, 3 days old at fetch.
   - Marks: preprint, measured, open-weight models and GPU-hour cost (not API tokens); no retraction seen; citations not retrieved; convergence with finding 5 and finding 9.
   - Grade: medium-low (very new, abstract-level, cost metric differs from token spend).

9. **After a cheap model fails, choosing among reflect, replan and escalate beat both binary cascade and always-escalate.** With GPT-5.4-nano and GPT-5.4 the three-action router reached 0.717 solve rate against 0.636 for a binary cascade at comparable cost and 0.686 for always-escalate at about 35% of the latter's cost; on medium-difficulty problems the strong model was no more reliable than the cheap one. Seen only in a search summary. (confidence: low)
   - https://arxiv.org/abs/2607.19338 - preprint; abstract page not opened.
   - Marks: preprint, measured; citations not retrieved; convergence with finding 8.
   - Grade: low (secondary summary only).

10. **Router cost claims mostly ignore prompt caching.** TurnCost states AgentRouter, SWE-Router and MTRouter use cache-unaware accounting; AgentRouter is reported at 71.8% cost reduction retaining 97.3% of frontier quality. Ties routing savings to [[SPEC-033-prompt-cache-is-a-design-input]]. (confidence: low)
    - https://arxiv.org/pdf/2610.15093 - search summary only, not opened.
    - Marks: preprint, asserted in a survey paragraph; citations not retrieved; convergence untested.
    - Grade: low.

### Adaptive verification depth (the checking half)

11. **Theory: fine-grained verification wins when the problem is hard or budget is large, coarse wins on easy problems at low budget (GRACE).** A phase transition is proved; a variant picks the level per problem. This is a model of answer verifiers, not coding agents. (confidence: low-medium)
    - https://arxiv.org/pdf/2606.19354 - search snippet only.
    - Marks: preprint, theory with experiments reported in the snippet; citations not retrieved; convergence with finding 12 and finding 1.
    - Grade: low-medium.

12. **Adaptive allocation: certify easy and medium questions first, spend heavily only on hard ones.** Budgeted multi-attribute verification and BudgetVerify (a trained router picks a verification tier per answer, in financial QA) both set verification effort by instance difficulty and budget. Neither concerns agents or code. (confidence: low)
    - https://arxiv.org/html/2609.34322v1 and https://arxiv.org/pdf/2609.33052 - search snippets only.
    - Marks: preprints, domain QA, asserted via snippet; citations not retrieved; convergence with finding 11.
    - Grade: low.

13. **Verification competes with generation for the same budget.** A 2025 paper cites prior work where verifiers needed up to 8x compute to match self-consistency, and its discriminative-verifier plus self-consistency mix gained up to 15.3% on AIME2025 at fixed compute. Math, not code. (confidence: low-medium)
    - https://arxiv.org/abs/2510.14913 - preprint, Oct 2025, snippet only.
    - Marks: preprint, measured; citations not retrieved; convergence with finding 1 (checks have a price).
    - Grade: low-medium.

### What Compass already decided

14. **Compass's model policy keys on the agent, not on the task.** [[ADR-008-model-resolution-table]] maps each agent to a tier (`strong`: planner, validator, reviewer, debug; `balanced`: builder, researcher, tester; `cheap`: locators) and resolves it at install time with `compass apply-models`; precedence is built-in default, then `.compass/meta/models.yaml`, then environment. No spawn-time query (D-02: it costs agent tokens and relies on prose compliance). There is no difficulty key. (confidence: high)
    - `.compass/decisions/distribution/ADR-008-model-resolution-table.md:25-30` - D-01 to D-05.
    - `plugin/cli/modelslib.py:207-280` - `resolve` precedence code (env, then agent config, then tier, then built-in).
    - Marks: vault decision plus code read; not applicable for retraction, preprint or citations; convergence: matches grep of `.compass/decisions`.
    - Grade: high (read directly).

15. **ADR-008 names the missing test as a load-bearing risk.** "The cheap-tier quality claim ... is unmeasured" and per-invocation model overrides at spawn "exist in the platform but are untested in this repo". The `models.yaml` override is the stated escape hatch. (confidence: high)
    - `.compass/decisions/distribution/ADR-008-model-resolution-table.md:44-47`.
    - Marks: vault decision, read; convergence with finding 14.
    - Grade: high.

16. **ADR-011 forbids a computed score or numeric threshold for sizing judgments.** D-01: no numeric threshold or computed metric ships, and a future proposal "is labeled an unvalidated invention"; the evidence is that LCOM, built to mechanize a cohesion judgment, did not predict faults. D-03: the harness owns the trigger and the record, the agent owns the judgment. D-08: every decision and every correction is recorded. D-05: classify what was said, never infer scope. A difficulty class that a plan assigns by judgment and a harness records fits D-03 and D-08; a numeric difficulty score with a cut-off falls under D-01. (confidence: high)
    - `.compass/decisions/vault-structure/ADR-011-sizing-is-a-procedure-not-a-score.md:25-34` - D-01 to D-08; line 59 leaves open whether an LLM runs the procedure consistently.
    - Marks: vault decision, read; convergence: finding 3 (calibration warning) points the same way as D-01.
    - Grade: high.
    - Open (not decided): ADR-011 covers sizing for spec shape, not task difficulty for checking depth; whether D-01 extends to the latter is a call for the human.

17. **Lessons and other ADRs hold nothing on difficulty-keyed checking.** A keyword grep for difficulty, complexity, per-model, model policy, resolve-model, cascade and ablat in `.compass/lessons` returned no files. In `.compass/decisions`, the terms difficulty, complexity, cascade and routing matched only ADR-002 (line 71, hook complexity), ADR-003 (line 54, counter-file hook complexity) and ADR-016 (line 28, "the routing moves words", about rerouting spec content); none concerns checking depth or task difficulty. A broader pattern (adding per-model, resolve-model, ablat) additionally matched ADR-008 and ADR-017 as expected. (confidence: medium)
    - Grep of `.compass/decisions` and `.compass/lessons`, 2026-11-21; keyword match, not proof of absence.
    - Marks: grep result; convergence with the survey's "Covered: no" for A4 (`REVIEW-llm-research-for-compass.md:143`).
    - Grade: medium.

### Recording the choice so the same task and model always get the same answer

18. **A decision table keyed by (difficulty class, model id) has a Compass precedent in shape: ADR-008's built-in table plus project override plus environment.** The precedence code already returns a value per (agent, tier) with a source label (`built-in`, config, env) and never raises. A checking-level table would be a second lookup with the same precedence; determinism follows because the lookup is pure over the table and the recorded class. (confidence: medium)
    - `plugin/cli/modelslib.py:207-280` - resolution returns `(model, effort, source)` deterministically.
    - `.compass/decisions/distribution/ADR-008-model-resolution-table.md:28` - D-04 precedence.
    - Marks: code read plus inference (the table shape is an inference from the existing code, not a documented design); convergence: none from the literature.
    - Grade: medium (code verified, extension is inference; flagged as a question for the planner, not a finding of the source).

19. **No source records the routing rule itself; the literature recorded learned scores, not tables.** DAAO, SWE-Router and SuperScout use trained estimators (VAE, value head, hidden-state router); the timeout cascade uses a fixed rule (small model first, escalate on failure or timeout) with no trained component. A learned score gives the same output for the same input only if the model weights and inputs are frozen; none of the abstracts discuss recording the choice. (confidence: medium-low)
    - https://arxiv.org/abs/2509.11079, https://arxiv.org/abs/2607.00053, https://arxiv.org/abs/2608.04804, https://arxiv.org/abs/2611.24324 - abstract pages.
    - Marks: preprints plus one peer-reviewed, absence claim from abstracts only; convergence 4 of 4 abstracts silent on recording.
    - Grade: low-medium (absence-of-evidence from abstract-level reading).

20. **Difficulty and ability are separable keys in the prior art: IRT factors an agent into model ability and scaffold ability.** A key of (task difficulty class, model id) matches the first factor; host or scaffold version is the second key SPEC-034 names for re-measurement, and Agent Psychometrics treats it as a separate term. (confidence: medium)
    - https://arxiv.org/abs/2604.00594 - abstract page.
    - Marks: preprint, measured; convergence with finding 2 (same source, same claim).
    - Grade: medium.

## Contradictions

- Findings 4 and 7 differ on whether pre-run routing signals pay. SWE-Router says task text has a Bayes floor and a partial trajectory helps; Scrouting reports the handoff, not the router, drove the result and (per a search summary) that no learned router reliably beat the strongest model. Different benchmarks (Verified versus Pro), different routed object.
- Finding 8 (timeout cascade nearly matches an oracle) against finding 9 (binary cascade wastes cost on medium-difficulty problems where the strong model is no better): both preprints, different model pairs, no shared test.
- Finding 14 (the model key is per agent) and SPEC-034's outcome (per difficulty and model): not contradictory, but the current table has no difficulty axis.

## Gaps

- No source found keys the depth of post-build checking (tester, validator, builder review) on difficulty. The routing and cascade papers choose which model generates the patch; findings 11 to 13 are on answer verifiers in math, QA and finance. The transfer to coding-agent checking stations is untested; only survey claim 8 (finding 1) speaks to stations directly.
- Numbers for findings 4, 5, 8, 9, 10 rest on search summaries or abstracts; a full-text pass would verify them.
- Citation counts and retraction status not retrieved for any preprint (Semantic Scholar and Crossref not queried).
- No source on how stable a difficulty class assigned by an LLM planner is across runs; ADR-011 line 59 names the same open question for sizing. Axis 1's sizing signal bears on this (see [[RESEARCH-axis-1-task-difficulty-signal]]).
- Cost accounting in the routing papers is GPU-hours or cache-unaware dollars (finding 10), so their savings do not map onto Compass's token count.

## Candidate changes for Compass

Options, not a pick; ranked by the evidence above, each with the north star it serves.

1. **A checking-level rule table keyed by (difficulty class, model id), recorded in the vault.** North stars 1 and 4 (accuracy first, tokens second). Would change: a table file beside `.compass/meta/models.yaml` read by the build skill (`plugin/skills/build/SKILL.md`) and a resolve command beside `plugin/cli/modelslib.py`; the difficulty class comes from the plan's task field and is assigned by judgment under ADR-011 D-03, recorded under D-08. Already covered: no (finding 17); the shape precedent is ADR-008 (finding 18). Open for the human: whether ADR-011 D-01 reaches a task-difficulty score (finding 16).
2. **Escalate on observed failure instead of predicting difficulty.** Run the light check first, escalate to full validator or `strong` tier when the tester or a failing test signals it; the timeout cascade and CodeRescue are the prior art (findings 8 and 9). North stars 1 and 4. Would change the 3-cycle fix loop in the build skill. Already covered: partly, the fix loop escalates after 3 cycles but runs full stations first. Caveat: finding 9 found escalation wasted on medium-difficulty tasks.
3. **Record per-(class, model) outcome counts so the rule is earned by measurement.** Past pass rates feed DAAO's self-adjusting policy (finding 5) and match the spec's constraint that lighter checking is earned by measurement. North stars 1 and 2. Would change: `compass sizing` style log (`.compass/meta/sizing-log.yaml`) extended or a sibling file. Already covered: the sizing log records shape corrections, not check outcomes (axis 1 covers it).
4. **Key the table on host or scaffold version as well as model id.** Finding 20. North star 1; rows re-measured on a change, which links to axis 3. Already covered: no.
5. **Ablate the post-build tester and validator on a task sample first (survey measurement C4).** Finding 1 and finding 8's caveat say difficulty effects are benchmark-specific, so a Compass-owned measurement precedes any table values. North stars 1 and 4. Already covered: open as C4 in the survey.
