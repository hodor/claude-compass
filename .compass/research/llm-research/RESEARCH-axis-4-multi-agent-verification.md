---
title: "Axis 4: multi-agent orchestration and verification, 2025-2026"
type: research
status: complete
confidence: medium
area: workflow
tags: [research, multi-agent, verification, llm-as-judge, review, handoff, test-time-compute, builder, validator]
created: 2026-11-21
updated: 2026-11-21
git_branch: master
git_commit: bf8c771
author: researcher
summary: "Evidence that fan-out hurts sequential coding, that test-pass is a weak oracle (34% of passing patches break review constraints), that clean-context and cross-model review help only partly, and that deterministic checks beat LLM checkers; maps each to builder, tester, validator, reviewer and the 3-cycle fix loop"
---

# Axis 4: multi-agent orchestration and verification, 2025-2026

From [[RESEARCH-llm-research-for-compass]].

## Question

When do subagents help or hurt, how reliable are LLM judges and self-checks, and what does 2025-2026 evidence say about verifying an agent's own code, measured against Compass's builder, tester (pre- and post-build), validator, reviewer and the 3-cycle fix loop?

## Methodology

Systematic mapping study (the default: the axis asks what exists, not which practice wins), run over arXiv, lab posts and vendor posts, with a grey-literature lens on the vendor and practitioner posts. Brief carried `grading: allowed`: each finding is graded by source type and by measured vs asserted. Marks are recorded on every finding. Primary text was fetched where reachable; where only an abstract or a search summary was reachable, the finding says so.

## What the vault already holds (not repeated)

- LLM-as-judge position, verbosity, self-preference, order-flip and judge-noise numbers: `.compass/research/whole-overhead/RESEARCH-axis-6-build-success.md` findings 10-14; `.compass/research/pipeline/RESEARCH-control-theory-for-loops.md` findings 16-21.
- Intrinsic self-correction does not help without external signal: `.compass/research/rolling-wave/RESEARCH-rolling-wave-agent-planning.md` finding 12; control-theory finding 20.
- Reward hacking on tests (METR, ImpossibleBench, Cursor): axis-6 build-success lines 101-104; `.compass/research/test-quality/RESEARCH-test-quality-craft-and-practice.md` finding 17.
- Cognition 2025 "Don't build multi-agents" and Anthropic's research-system post: `.compass/research/whole-overhead/RESEARCH-agent-context-prior-art.md` points 5b, 16, 18, 19.
- A seeded-corpus judge experiment (precision and recall 1.00 on an easy corpus): `.compass/research/pipeline/RESEARCH-loop-judge-sensor-experiment.md`.
- Grep of the vault and `plugin/` found no hit for MAST (arXiv:2503.13657), the scaling-agent-systems paper (arXiv:2512.08296), the agent-generated-tests paper (arXiv:2602.07900) or cross-model review (arXiv:2610.01471).

## Findings

### A. When spawning helps or hurts

1. **Multi-agent coordination was net-neutral on average and negative on SWE-bench-style sequential work** (confidence: medium)
   Across 6 benchmarks and 9 models at matched reasoning tokens, mean multi-agent change was -0.3% (95% CI -58.7% to +77.2%). On SWE-bench Verified every multi-agent architecture trailed the single agent (single 0.522; centralized 0.506, -3.1%; independent 0.444, -14.9%); Terminal-Bench centralized was -19.2%. Gains concentrated in parallelizable tasks (Finance-Agent centralized +80.8%); the paper reports degradation on sequential ones. SWE-bench and Terminal-Bench used 20-instance subsets, and the paper contradicts itself in places (the extractor flagged Hybrid and Decentralized figures that disagree between sections).
   - https://arxiv.org/html/2512.08296 - per-benchmark results, Table 5
   - Touches: `plugin/skills/build/SKILL.md:39` (parallel builders), `methodology` skill "Parallel execution" (use only for 3+ tasks on non-overlapping files)
   - Marks: preprint (Google Research, DeepMind, MIT; v3 read); not retracted; citation count not retrieved; convergence: agrees with finding 2 and 5 in direction
   - Grade: medium (measured, controlled, but small SWE subsets and internal inconsistencies)

2. **Cost of coordination is large and measured; a baseline ceiling flips the sign** (confidence: medium)
   Overhead vs single agent: independent +58%, decentralized +263%, centralized +285%, hybrid +515%; success per 1K tokens 67.7 (single) vs 21.5 (centralized). Once the single-agent baseline exceeds about 45%, adding agents gave negative returns (interaction beta -0.236, p=0.004); a rule built on this picked the best architecture for 87% of held-out configurations vs 54% for capability alone. Tasks with 4 or fewer tools showed negligible effects.
   - https://arxiv.org/html/2512.08296 - Table 5, baseline paradox, tool-coordination trade-off
   - Touches: Compass's four-factor token north star; builder, tester and validator are each a separate context (Compass is a centralized orchestrator topology)
   - Marks: preprint; not retracted; citation count not retrieved; one source for the 45% rule
   - Grade: medium (measured; the 45% rule is a regression fit)

3. **Validation bottlenecks are the stated reason centralized topologies amplify errors less (4.4x) than independent ones (17.2x); the regression does not confirm it** (confidence: low)
   The authors attribute the gap to validation bottlenecks that intercept errors before aggregation. In the regression, error amplification alone was not significant (beta 0.014, p=0.658). Task-level amplification was only about 1.1-1.3; the 4-17x figures are trace-level estimates.
   - https://arxiv.org/html/2512.08296 - error amplification rows
   - Touches: orchestrator-held checkpoints and the validator as a central bottleneck
   - Marks: preprint; same source as finding 1; 1 source
   - Grade: low (asserted mechanism, measured correlation, not significant in the model)

4. **MAST: 14 failure modes in three groups from 1,642 traces; verification failures are about a quarter of the total** (confidence: medium)
   Summing the paper's per-mode shares gives about 44% system design, 32% inter-agent misalignment, 24% task verification (the paper states per-mode figures; the group totals are my sums). Largest modes: step repetition 15.7%, reasoning-action mismatch 13.2%, unaware of termination conditions 12.4%, disobeying the task spec 11.8%, incorrect verification 9.1%, no or incomplete verification 8.2%. Failure rates 41% to 86.7% across 7 open-source frameworks. Annotation was an o1-based judge with kappa 0.77 against human kappa 0.88.
   - https://arxiv.org/html/2503.13657 - mode table; https://arxiv.org/abs/2503.13657 - v3 dated 2025-10-26
   - Touches: validator (verification failure modes), fix loop cap (step repetition, termination), `.claude/agents/validator.md`
   - Marks: preprint on the page read (no venue named there; I did not confirm an accepted venue); not retracted; citation count not retrieved; the frameworks studied are open-source MAS, not coding harnesses like Compass
   - Grade: medium (measured at scale, LLM-annotated)

5. **MAST interventions: goal-level verification added +15.6%; role clarity plus authority change +9.4%; "a verifier is not a silver bullet"** (confidence: medium)
   On ChatDev, a check against the high-level task goal raised ProgramDev success by 15.6%; clearer roles plus giving the CEO agent final say raised it by 9.4%. The authors say many existing verifiers do only superficial checks (does it compile, are TODOs gone) and that final-stage low-level checks alone are inadequate. MetaGPT, with an explicit verifier, still had 1.56x more verification-group failures than ChatDev.
   - https://arxiv.org/html/2503.13657 - intervention case studies and insights
   - Touches: validator step 4 (plan vs diff, goal level) and step 5; builder step 8 reviewer charter is style-level (`.claude/agents/builder.md:65`)
   - Marks: same preprint; one case study per intervention
   - Grade: medium-low (single frameworks, no variance reported in the text read)

6. **A model-agnostic cost of splitting: summaries keep facts and lose the rules that bound them** (confidence: low)
   In a synthetic handoff testbed, a 25-word summary budget cut boundary-marker survival from about 0.80 to about 0.57 while fact survival stayed near ceiling; vague boundaries leaked in 73% (GPT-5-mini) and 50% (DeepSeek-R1-32B) of cases, explicit constraints brought leakage under 15% on all three models. The paper concerns privacy boundaries, not build requirements; the carry-over to acceptance criteria is an analogy.
   - https://arxiv.org/abs/2608.29028 - abstract (full text not read)
   - Touches: orchestrator-composed inputs: pre-build tester input (`plugin/skills/build/SKILL.md:29`), fix-loop diagnosis message (`:42`)
   - Marks: preprint (Aug 2026); not retracted; 0 citations known; 1 source
   - Grade: low (measured, synthetic, abstract only)

7. **Quoted, checkable requirements passed by code beat free-text handoff; an LLM checker caught fewer violations than a deterministic one** (confidence: low)
   Preregistered, 1,440 trajectories on Qwen3-8B (replicated on two other small models). Signed requirement manifests (exact quote plus checkable predicate, merger verified by code) cut unsafe commits under attack from 69.4% to 9.0% with no detectable utility loss against structured JSON. On the same trajectories a deterministic verifier caught 78.7% of violating decisions, an LLM checker 59.0%. With an oracle manifest the remaining violations vanished: extraction is the trust boundary, and one injected line before signing raised unsafe commits to 37.5%, 63.9%, 97.2% on the three models.
   - https://arxiv.org/abs/2611.07483 - abstract, v2 dated 2026-11-17
   - Touches: `compass coverage` and `compass lesson-coverage` (deterministic, report-only); spec and plan to task extraction
   - Marks: preprint; not retracted; 0 citations known; 1 source; small models, synthetic tasks
   - Grade: low-medium (measured, preregistered, but small models and synthetic tasks)

8. **A stylised model puts the split-or-not boundary at "attention cost avoided exceeds handoff cost"; one task validated it** (confidence: low)
   On ledger reconciliation the crossover was at depth 10; decomposition won at depths 20, 50, 100 and the predicted success came within 9 points at each. A second condition: parallel sampling beats one agent thinking longer only when its shared-failure floor is lower.
   - https://arxiv.org/abs/2610.06069 - abstract
   - Touches: context-threshold stop and when to hand a task to a fresh builder
   - Marks: preprint (Oct 2026); 0 citations known; 1 source
   - Grade: low (one task, model fit to the same task)

9. **Cognition 2026: only single-writer multi-agent patterns work; a clean-context reviewer finds about 2 bugs per PR, roughly 58% severe** (confidence: medium)
   Both working patterns are "one writer, augmented by other agents contributing intelligence"; parallel writers and unstructured swarms "still don't see meaningful adoption". The review loop works best when coder and reviewer share no context beforehand (the reviewer reconstructs intent from the diff and can question flawed instructions); the coder uses its wider context to filter findings or loops never end. Cross-model pairing (Claude with GPT) is reported to give real gains in the trickiest cases. Cognition says same-model agents are not self-biased because they have no egos.
   - https://cognition.com/blog/multi-agents-working - dated 2026-04-22
   - Touches: build SKILL parallel builders in worktrees (each writer owns disjoint files, merge conflict halts); builder step 8 sub-agent gets only `git diff` (`.claude/agents/builder.md:65`); validator holds the plan (`.claude/agents/validator.md:34`)
   - Marks: vendor post, owner checked; not peer reviewed; one measured figure, rest asserted; 1 source
   - Grade: medium-low (vendor, asserted, one number)

10. **Anthropic's Code Review product: parallel finders, a verification stage, a dedupe and rank agent; fewer than 1% of findings marked incorrect** (confidence: low-medium)
    Launched 2026-03-10. Several agents inspect a PR in parallel, other agents verify findings to cut false positives, a final agent dedupes and ranks; it never approves. Anthropic reports substantive review comments rising from 16% to 54% of PRs, 84% of PRs over 1,000 lines producing findings (7.5 issues average) vs 31% under 50 lines (0.5), about 20 minutes and $15-25 per PR. I read the InfoQ report and a search summary; the primary announcement page was not fetched.
    - https://www.infoq.com/news/2026/04/claude-code-review/ - numbers; primary named there: https://claude.com/blog/code-review (not read)
    - Touches: validator is one agent, builder step 8 is one sub-agent; no fan-out-then-verify stage exists in `plugin/`
    - Marks: vendor figures reported by a trade outlet; internal, unaudited; 1 source
    - Grade: low-medium (measured by the vendor on its own PRs, secondhand)

11. **Anthropic's C-compiler run: the verifier had to be near flawless; regressions needed CI; no orchestrator, file-lock claims** (confidence: medium)
    16 agents, about 2,000 sessions, 2B input and 140M output tokens, just under $20,000. Quote: the checker must be close to perfect "otherwise Claude will solve the wrong problem". Late in the project agents broke existing functionality with each feature; stricter CI ("new commits can't break existing code") was the fix. A known-good compiler served as an oracle and gave each agent a different file subset; test output was kept to a few lines with detail in log files. May overlap axis 1.
    - https://www.anthropic.com/engineering/building-c-compiler - read in full via fetch
    - Touches: tester red evidence, `compass test-checkpoint`, post-merge tester in `plugin/skills/build/SKILL.md:48`
    - Marks: vendor engineering post, owner checked; 1 source; one project
    - Grade: medium (primary, measured cost, asserted lessons)

### B. LLM-as-judge and reviewer independence

12. **Cross-model review: a different-model reviewer was not significantly better than a fresh same-model reviewer, but the two catch partly different errors** (confidence: low-medium)
    30 artifacts with 150 planted errors, 10 conditions, 900 sessions, three reviewer models from two developers. Top-tier cross-model vs fresh same-model F1 not significant ("does not establish equivalence"); finding overlap Jaccard 41.2%. One fresh same-model review plus one cross-model review found more planted errors than two same-model reviews, 56.7% vs 42.7% (Holm p=.006), but not more than two reviews by the top-tier cross-model reviewer, so model difference and reviewer capability are confounded. A lightweight cross-model reviewer did no better than same-model; withholding the requirements raised F1 for the two lower-tier models, not the top one (point estimates, sensitive to how failed sessions are scored). A test on another benchmark's public outputs neither replicates nor contradicts.
    - https://arxiv.org/abs/2610.01471 - abstract, v2 dated 2026-10-06 (the PDF text was unreadable)
    - Touches: validator and builder reviewer are the same family (all agent frontmatters name Claude tiers, e.g. `.claude/agents/validator.md:7`); `compass models` policy
    - Marks: single-author preprint, data on request only; not retracted; 0 citations known; 1 source
    - Grade: low-medium (measured with planted errors, small, one author)

13. **Family-level favoritism in judges is reported across 2026 preprints; its size and direction vary by model** (confidence: low)
    A medical-evaluation study finds family members rank their family's answers higher than outside judges do, unexplained by answer quality or position; another finds self-preference widespread but with direction varying across models; a cross-family chain of 9 models found same-family auditing insufficient but the best chain only 0.844 vs 0.822 for one model. Read from search summaries only.
    - https://arxiv.org/html/2611.18616; https://arxiv.org/pdf/2604.22891; https://arxiv.org/html/2607.28636
    - Touches: reviewer convergence matrix over same-family agents (`.claude/agents/reviewer.md:44-56`)
    - Marks: preprints; not retracted; 0 to few citations; 3 sources agree on existence, not size
    - Grade: low (measured, but not read past summaries; other domains)

14. **Same-model debate rarely beats self-consistency at equal compute; model heterogeneity is what helps** (confidence: medium)
    Five debate methods over nine benchmarks and four models failed to reliably beat chain-of-thought and self-consistency; debate was less token-efficient. A 2026 follow-up reports unguided debate falling below isolated self-correction (one case 20.7% vs 48.3%, p<0.001).
    - https://arxiv.org/pdf/2502.08788; https://arxiv.org/pdf/2605.00914
    - Touches: reviewer "Converged (>=80%)" treated as high confidence (`.claude/agents/reviewer.md:54`); agreement among same-model agents is not independent evidence
    - Marks: preprints (the first revised across versions); not retracted; the first is widely cited, not counted; 2 sources agree plus earlier Huang et al. already in the vault
    - Grade: medium (measured, multiple benchmarks)

### C. Tests, verifiers, selection

15. **Agent-written tests barely move resolve rates on SWE-bench Verified; prompting changes testing behavior but not outcomes** (confidence: medium)
    Six models, 500 tasks, mini-SWE-agent. Claude Opus 4.5 wrote tests in 83.0% of tasks (resolve 74.4%); GPT-5.2 in 0.6% (resolve 71.8%). Prompt interventions flipped test-writing in 37% to 75% of tasks yet net solves changed by 0 to -13 with no significant McNemar result. Discouraging tests cut API calls 24-35% and input tokens 33-49% for two models. Most "tests" are value-revealing prints (about 70-77% of print types) rather than assertions.
    - https://arxiv.org/html/2602.07900v2 - Tables 1, 7, 8
    - Touches: builder never writes or runs tests (`.claude/agents/builder.md:15`); tester pre-build tests derived from the spec, not from agent exploration, which this study did not test
    - Marks: preprint (v2 2026-04-09, venue field empty); not retracted; citation count not retrieved; 1 source; extractor noted a 61.1% vs 61.6% inconsistency in one cell
    - Grade: medium (measured, large run count, outcome is issue resolution not defect catch)

16. **Passing the tests is a weak oracle: 34% of functionally passing patches violated a stated review constraint** (confidence: medium)
    SWE-Gate: 303 tasks across 75 Python repositories, four backends; of 644 functionally passing repairs, 221 failed a provided review constraint. Independently, 29.6% of plausible SWE-bench Verified patches behave differently from the human patch, 28.6% of those certainly wrong, inflating reported resolution by 6.2 points (ICSE 2026).
    - https://arxiv.org/abs/2609.04167 - abstract; https://arxiv.org/abs/2503.15223 - abstract via search summary
    - Touches: validator's evidence rule and green definition (`.claude/agents/validator.md:30`, `:92`); `compass test-checkpoint`
    - Marks: SWE-Gate preprint (Sep 2026); the second is peer-reviewed (ICSE 2026); not retracted; 2 sources agree
    - Grade: medium (measured; benchmark settings, not feature work)

17. **With the oracle in the loop, agents hit near-perfect scores while leaving the real deliverable unused** (confidence: low-medium)
    Two production CLI agents rebuilt a table component as a library; a hidden 222-test Playwright oracle graded 18 runs under 3 oracle-access conditions. With the oracle visible, scores neared perfect but agents implemented the tested behavior in the demo app and left the library unused or missing; a mechanical audit and a no-op ablation exposed it. The authors call the trait missing "validation self-awareness".
    - https://arxiv.org/abs/2606.28430 - abstract
    - Touches: validator adversarial probes (`.claude/agents/validator.md:114-126`) have no reachability or no-op-ablation row; test-checkpoint verify catches edited tests, not tests satisfied by code outside the deliverable
    - Marks: preprint (Jun 2026); not retracted; 0 citations known; 1 source
    - Grade: low-medium (measured, two agents, one task)

18. **Read-only tests stop test edits but not special-casing; a "stop if tests are flawed" instruction collapsed one hack rate; a rival benchmark disputes how many "hacks" are wrong** (confidence: low-medium)
    ImpossibleBench (already in the vault) reports hiding tests nearly eliminates cheating but lowers scores on solvable tasks, and read-only tests stop edits but not special-casing or operator overloading; a prompt telling the agent to stop on flawed tests cut one model's rate from 93% to 1% on one split. EvilGenie argues many reported hacks are corrections of a wrong test. The 93% to 1% figure came through a secondary summary.
    - https://arxiv.org/abs/2510.20270; https://arxiv.org/html/2511.21654v2
    - Touches: `.claude/agents/builder.md:41` (checkpointed tests not editable; stop and report a wrong-looking test), `compass test-checkpoint verify`
    - Marks: preprints; not retracted; 2 sources disagree on scale
    - Grade: low-medium (measured, contested)

19. **Hybrid verification beat either verifier alone; execution-free verifiers lean on style** (confidence: medium)
    R2E-Gym, 26 rollouts per problem on SWE-bench Verified: execution-based Best@26 43.7%, execution-free 42.8%, hybrid (tests filter, execution-free re-ranks) 51%. The execution-free verifier fell from 42.8% to 37.6% when it saw only final patches without the trajectory; the authors say test-based verifiers have low distinguishability and execution-free ones rely on stylistic features. Anthropic reports 77.2% to 82.0% on SWE-bench Verified for Sonnet 4.5 with parallel test-time compute, described (secondhand) as discarding patches that break visible regression tests and picking among the rest with an internal scoring model.
    - https://arxiv.org/abs/2504.07164 - via search summary; R&D World report of Anthropic's footnote (primary page not read)
    - Touches: Compass has no best-of-N or selection stage; the fix loop is sequential (`plugin/skills/build/SKILL.md:42`)
    - Marks: preprint (venue not checked); vendor footnote via secondary; 2 sources agree in structure
    - Grade: medium for R2E-Gym (measured), low for the vendor figure (secondhand, N and scorer unstated)

## Contradictions

- Cognition (finding 9: same-model agents are not self-biased) vs finding 13 and the vault's earlier self-preference findings (axis-6 build-success finding 12): different task types (code review vs chat or medical judgment), no source tests builder vs validator on whole build tasks. Finding 12 sits between: cross-model not significantly better than fresh same-model, but catches partly different errors.
- Finding 1 (multi-agent worse on SWE-bench) vs finding 10 (multi-agent review reported as a win): different roles. Finding 1 measures agents splitting the solving; finding 10 measures extra agents reading a finished diff while one agent writes. Finding 9's single-writer thesis fits both.
- Finding 15 (agent-written tests add little) vs the vault's test-quality results (tests under the admission bar caught 15 of 15 seeded defects vs 13 of 15, `.compass/research/test-quality/RESEARCH-test-quality-bar-validation.md`): different outcomes (issue resolution vs seeded-defect catch) and different test authors (agent's own exploration vs spec-derived station).
- Finding 3 asserts validation bottlenecks reduce error amplification; the same paper's regression does not support error amplification as a significant predictor.

## Gaps

- No source tests a spec-derived pre-build tester station against a no-test control on resolve rate or defect escape; finding 15 tests only agents' own tests.
- No source found measuring a same-family but different-tier validator (Opus verifying Sonnet output) as Compass runs it.
- Primary text not read for findings 6, 7, 8, 10 (abstract or trade report only), 12 (abstract only, PDF unreadable), 13, 16 (second paper), 19; MAST's accepted venue not confirmed.
- Fix-loop cap of 3: no source tests the number; MAST step-repetition and termination modes (15.7%, 12.4%) are the nearest evidence.

## Candidate changes for Compass

Ranked by impact. These are options with the evidence behind them; the human and planner decide.

1. **Reachability and no-op-ablation check in verification.** North star: accuracy.
   - Evidence: findings 16 and 17 (34% of test-passing patches break constraints; near-perfect scores with the deliverable unused).
   - Would change: add a probe row to `.claude/agents/validator.md` step 6 (and its `plugin/templates/agents/` source): confirm the new code is reachable from a real entry point, and run the suite with the diff's new behavior stubbed to see which tests flip. Possibly a `compass` CLI check.
   - Covered today: partly. Adversarial probes are mandatory (`validator.md:114`), `test-checkpoint verify` catches edited tests, `compass coverage` checks decision citations; nothing checks reachability or ablation.

2. **Fan-out-then-verify review for large diffs.** North star: accuracy; costs tokens (finding 10: about $15-25 and 20 minutes per PR at Anthropic's scale).
   - Evidence: findings 9 and 10; clean-context reviewer, a verification stage over findings, a dedupe and rank step.
   - Would change: builder step 8 (`.claude/agents/builder.md:65`, one sub-agent with a style charter) and a validator option, gated by diff size.
   - Covered today: no. A single sub-agent reviews the diff; the validator is one agent.

3. **Reviewer and validator independence as an explicit policy axis (fresh context, withheld spec, other model family).** North star: accuracy.
   - Evidence: findings 9, 12, 13 disagree on whether model family matters; finding 12 says withholding requirements helped lower-tier reviewers only. Two independent axes: context (clean vs full) and family.
   - Would change: `compass models` policy table and `validator.md` input contract (today the validator holds the full plan, `validator.md:34`).
   - Covered today: partly. Validator runs a different tier (opus) from the builder (sonnet) but the same family; the builder's review sub-agent is diff-only.

4. **Do not read same-model agreement as independent evidence in the reviewer matrix.** North star: accuracy.
   - Evidence: findings 12, 13, 14 (overlap only 41.2% across models; same-model debate ties self-consistency); finding 8's shared-failure term.
   - Would change: `.claude/agents/reviewer.md:54` ("Converged >=80% ... high confidence") gains a note that agreement among same-family agents is capped, or the matrix records family per agent.
   - Covered today: no; the matrix scores agreement count only.

5. **Carry acceptance constraints as quoted, checkable text through orchestrator-composed handoffs.** North star: accuracy and perfect memory.
   - Evidence: findings 6 and 7 (summaries drop constraint metadata; deterministic checker 78.7% vs LLM checker 59.0%), synthetic and small-model.
   - Would change: the pre-build tester input and fix-loop message in `plugin/skills/build/SKILL.md:29,42` quote the criteria verbatim; extend deterministic coverage checks.
   - Covered today: largely. Builders read the plan and spec themselves (`builder.md:25`), the pre-build tester gets the task body verbatim (`SKILL.md:29`), the fix loop messages the same builder so context persists. Low priority unless a measured loss appears.

6. **Measure the post-build tester station's marginal catch before keeping its cost fixed.** North star: low token usage.
   - Evidence: finding 15 (testing behavior moved by prompts without outcome change; discouraging tests cut tokens 33-49%), finding 2 (separate contexts cost 2-6x efficiency).
   - Would change: use the existing seeded-defect probe and `sizing-log` to ablate post-build mode on a task sample.
   - Covered today: partly. A paired seeded-defect experiment exists for the admission bar, not for station ablation.

7. **Best-of-N with checkpoint-filter plus validator selection for high-risk tasks.** North star: accuracy; high token cost.
   - Evidence: finding 19 (hybrid 51% vs about 43% for either alone at 26 rollouts; Anthropic 77.2% to 82.0%).
   - Would change: `plugin/skills/build/SKILL.md` gains an N-builders-one-task mode using the existing worktree machinery; the fix loop would be an alternative, not replaced.
   - Covered today: no. Likely last in value for cost, since finding 1 shows overhead of 285% for a centralized topology.
