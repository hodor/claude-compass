---
title: "Test-Suite Quality Measurement and LLM Test-Generation Literature"
type: research
status: complete
confidence: high
area: testing
tags: [testing, test-quality, mutation-testing, test-smells, llm-test-generation, fault-based-testing]
created: 2026-08-07
updated: 2026-08-07
git_branch: "master"
git_commit: "cdda7e1"
author: "researcher (Claude)"
depends_on: ["[[SPEC-013-test-quality]]"]
summary: "suite-quality measurement and LLM test-generation literature"
---

# Test-Suite Quality Measurement and LLM Test-Generation Literature

## Question

What does the research literature and industry practice know about (a) measuring test-suite quality/power and (b) making AI/LLM agents generate genuinely good tests rather than numerous shallow ones? Scoped to [[SPEC-013-test-quality]]'s D-01 (per-test admission bar: a test exists only if it can name the defect class it catches) and its four open questions on measurement, LLM overproduction causes, proportionality baselines, and retroactive grading.

## Methodology

WebSearch/WebFetch across arXiv, ACM/IEEE DL abstracts, and engineering literature. Prioritized primary sources (papers, not secondary blog summaries) and fetched full abstracts/PDFs where search snippets were insufficient. No sub-agents spawned per brief.

## Findings

### Axis 1: Measuring test-suite power

1. **Mutation score correlates with real fault detection, but the correlation is context-dependent, not universal** (confidence: high)
 A 2018 ICSE study directly asking "are mutation scores correlated with real fault detection?" found moderate-to-strong correlation in some settings. A 2024 AST paper titled "Mutation Coverage is Not Strongly Correlated with Mutation Coverage" complicates this. Most importantly, a 2026 replication study built specifically for LLM-generated suites found the relationship breaks down exactly where it matters most for Compass: when the code under test is already buggy.
 - [Are mutation scores correlated with real fault detection?](https://dl.acm.org/doi/10.1145/3180155.3180183) (ICSE'18)
 - [Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness?](https://arxiv.org/html/2607.22880) (replicability study)

2. **On bug-free code, mutation/coverage predict real-bug detection reasonably well across models; on buggy code, they don't** (confidence: high)
 The 2607.22880 replication study (Defects4J v3.0, 854 defects across 17 Java projects, 318 buggy focal methods, 101,000+ tests from 11 LLMs, PIT for mutation, CodeCover for statement/branch/MC coverage) found: inter-model comparison on bug-free code shows moderate-to-strong correlation (branch coverage r=0.861 against real-bug detection). On buggy-code input, correlations become uniformly weak across every analysis perspective, and within-model variation shows weak correlation regardless of aggregation method. The authors' explicit conclusion: mutation/coverage scores are unsuitable proxies "for the practically common scenario where the code-under-test may already be buggy" and recommend evaluating bug-detection capability directly rather than trusting the proxy.
 - `arxiv.org/html/2607.22880` (methodology + conclusion, fetched in full).
 - This is directly load-bearing for Compass: an agent typically writes tests for code it (or a peer agent) just wrote, which is exactly the "may already be buggy" scenario the proxy fails on.

3. **Mutation testing has real, unsolved cost and equivalence problems** (confidence: high)
 The equivalent-mutant problem (a mutant that is behaviorally identical to the original and thus can never be killed by any test) has no complete solution; the surviving fraction is hard to estimate without manual review. Cost-reduction survives via mutant sampling, selective mutation (a curated operator subset), higher-order mutation, and mutant clustering. A small constant random sample of mutants can yield statistically similar results to full mutation analysis regardless of program size, but uniform random selection can underperform expectation - selection strategy matters, not just sample count.
 - [Mutation Testing Cost Reduction Techniques: A Survey](https://www.researchgate.net/publication/224132836_Mutation_Testing_Cost_Reduction_Techniques_A_Survey)
 - [Reduction of Computational Cost in Mutation Testing by Sampling Mutants](https://link.springer.com/chapter/10.1007/978-3-319-00945-2_4)

4. **LLM-based equivalent-mutant detection is workable with simple pre-processing** (confidence: high)
 Meta's ACH system deploys an LLM agent to classify mutants as equivalent vs. killable: raw precision 0.79 / recall 0.47, rising to 0.95 / 0.96 with unspecified "simple pre-processing." This is direct evidence that LLM-in-the-loop equivalent-mutant triage is a solved-enough sub-problem to build production tooling on, provided the pre-processing step (not detailed in the abstract) is replicated.
 - [Mutation-Guided LLM-based Test Generation at Meta](https://arxiv.org/abs/2501.12862) (FSE'25 Industry).

5. **"Checked coverage" (Marick) predates and reframes the whole quality-vs-count debate** (confidence: medium)
 Brian Marick's classic critique of code coverage draws a distinction (not independently re-fetched in full text - the primary PDF's TLS cert did not resolve; captured secondhand via a course citation) between code merely *reached/executed* by a test and code whose *output was actually checked* by an assertion. His stated position: coverage tools are "only helpful if they're used to enhance thought, not replace it," and high line/reachability coverage can produce false confidence when nothing meaningful is asserted about what ran. This is the pre-mutation-testing-era articulation of exactly the problem SPEC-013 names (a test that executes code without verifying behavior earns no defect-detection credit).
 - [BBST: Brian Marick - How to misuse code coverage](https://bbst.courses/brian-marick-how-to-misuse-code-coverage/) (secondary citation; primary source `exampler.com/testing-com/writings/coverage.pdf` unreachable via WebFetch, TLS hostname mismatch).
 - Confidence held at medium because the exact "checked coverage" terminology and numbers were not verified against Marick's original text in this pass.

6. **Test-suite minimization by coverage overlap is an established, separately-studied problem with a known failure mode** (confidence: high)
 Redundancy detection treats two tests as redundant when the code-element sets they cover overlap; minimization techniques (mostly white-box, greedy heuristic or clustering-based) remove tests whose covered requirements are subsumed by others. The literature's explicit warning: minimization techniques "can severely compromise the fault-detection effectiveness" of the reduced suite, because coverage-overlap is a much weaker signal than fault-detection-overlap - two tests can cover the same lines while catching different mutants. A "selective redundancy" variant only drops a test once it is redundant against *two independent* requirement sets, not one.
 - [Test suite reduction with selective redundancy](https://www.semanticscholar.org/paper/Test-suite-reduction-with-selective-redundancy-Jeffrey-Gupta/b1accda8c3f562eb5d4d1efdab64820a504b8245)
 - Direct implication for SPEC-013's "duplicated coverage" admission-bar criterion: line/branch overlap is a cheap but weak dedup signal; mutation-kill-set overlap would be the correct but expensive one.

7. **Fault-based test adequacy criteria are decades-old formal theory, not a novel framing** (confidence: high)
 Zhu, Hall & May's 1997 ACM Computing Surveys paper ("Software Unit Test Coverage and Adequacy") classifies test adequacy criteria into structural (coverage-based), fault-based (error-seeding to estimate remaining-fault count), and error-based (boundary/domain analysis) families, and gives a framework for comparing criteria formally. Fault-based testing's core move - defining adequacy by the faults a suite can detect rather than the code it executes - is the direct academic ancestor of SPEC-013's "name the defect class" admission bar.
 - [Software unit test coverage and adequacy (ACM CSUR 1997)](https://dl.acm.org/doi/10.1145/267580.267590)

8. **RIPR gives a four-condition formal test for whether a single test CAN detect a given fault** (confidence: high)
 The Reachability-Infection-Propagation-Revealability model (Li & Offutt, extending Voas's PIE analysis) states a test detects a fault only if all four hold: (R) execution reaches the faulty location, (I) the fault produces a distinguishably wrong program state, (P) that wrong state propagates to an observable output, (R) the oracle actually checks and reports the propagated error. This is prior art with a name for exactly the operational question D-01 asks per test - not "does this code run" but "can a wrong version of this code make this test fail, and would the test notice."
 - [The Reachability, Infection, Propagation, and Revealability Model](https://www.researchgate.net/figure/The-Reachability-Infection-Propagation-and-Revealability-Model_fig1_305793864)
 - `cs.cornell.edu/courses/cs5154/2021fa/resources/MutationTesting.pdf` (course treatment cross-referencing RIPR to mutation testing directly).
 - Practical reading for an admission bar: a test that only satisfies R (reaches the code) but not I/P/Revealability is exactly Marick's "reachability without checked coverage" (Finding 5) restated in fault-injection terms.

### Axis 2: Test smells and low-value test taxonomies

9. **A stable, named taxonomy of low-value test patterns already exists and is machine-detectable** (confidence: high)
 Established smell categories: Assertion Roulette (multiple unlabeled assertions, can't tell which failed), Duplicate Assert, Magic Number Test, General Fixture (over-broad setup), Eager Test (one test exercising multiple behaviors), Conditional/Sleepy Test, Empty Test, Useless Test, Mystery Guest (hidden external dependency), Resource Optimism. Detection is dominantly rule-based static analysis (AST traversal, pattern matching on assertion usage) plus metric-based detectors (assertion density, fixture size, test cohesion) and, for state-pollution/unexecuted-assertion smells, dynamic taint-style instrumentation.
 - [Test Smell Detection Tools: A Systematic Mapping Study](https://arxiv.org/pdf/2104.14640) (ACM ESEM'21)
 - [tsDetect: an open source test smells detection tool](https://testsmells.org/assets/publications/FSE2020_TechnicalPaper.pdf) - covers 19 smells, reports 85-100% precision / 90-100% recall on open-source Android apps.

10. **"Assertion-free" is an explicit, cheaply-detectable admission-bar failure** (confidence: high)
 A concrete detector rule already in production tooling: a test method containing zero assertion statements and no `@Test(expected=...)`-style exception-expectation annotation is flagged outright; a second sub-category flags assertion-free tests that also lack a descriptive name (compounding the "what does this even check" problem). This maps directly onto SPEC-013's explicit non-qualifying class list and is mechanically checkable with zero LLM cost (an AST walk).
 - `arxiv.org/html/2501.18327v1` (PyExamine, Python-specific smell tool) and the tsDetect paper above (criteria definitions).

11. **Flaky tests are a distinct quality failure from shallow tests, with their own decades of root-cause taxonomy** (confidence: high)
 A stable 10-category root-cause taxonomy exists: async-wait, concurrency/test-order dependency, resource leak, network, time, I/O, randomness, floating-point, unordered-collection iteration, plus domain-specific additions (e.g., UI flakiness on Android). 63% of surveyed flakiness papers were published 2019-2021, i.e., this is an active, well-resourced subfield with both classical rerun-based detection and newer ML/LLM classifiers (Flakify, FlakyCat, NeuroFlake). Detecting flakiness is necessary but explicitly insufficient per this literature - multiple surveys note that root-cause diagnosis, not just flip/flag detection, is what's needed to actually fix a flaky test rather than just quarantine it.
 - [A Survey of Flaky Tests (ACM)](https://dl.acm.org/doi/fullHtml/10.1145/3476105)
 - [Test flakiness' causes, detection, impact and responses: A multivocal review](https://www.sciencedirect.com/science/article/pii/S0164121223002327)

### Axis 3: LLM test-generation research

12. **Meta's TestGen-LLM ships an "assurance" filter pipeline, not raw LLM output, and even so more than half of generated candidates are discarded** (confidence: high)
 TestGen-LLM (Meta, FSE'24 Industry) generates candidate test *improvements* to existing human-written tests and only accepts a candidate after it clears filters that guarantee measurable improvement over the original (build success, reliable repeated passing, and increased coverage over the baseline - exact per-filter pass-through counts were not extractable from the abstract/PDF text in this pass, see Gaps). Reported end-to-end yield: 75% of candidates build correctly, only 57% pass *reliably* (implying ~18 points of the "builds" bucket are flaky or non-reproducible), and only 25% actually increase coverage - i.e., three-quarters of everything the model proposes is discarded by the assurance pipeline before a human ever reviews it. Of what survives to human review, 73% was accepted for production and the tool improved 11.5% of classes it was applied to at Meta's test-a-thons.
 - [Automated Unit Test Improvement using Large Language Models at Meta (arXiv 2402.09171)](https://arxiv.org/abs/2402.09171)
 - Direct evidence for D-02: a large, resourced industrial deployment still needed a hard mechanical filter stage discarding ~75% of raw model output before human review - "ask the model to write good tests" alone was not the mechanism Meta shipped.

13. **Meta's follow-up system (ACH) targets specific undetected faults instead of maximizing test count, and reports strong engineer acceptance** (confidence: high)
 ACH (Automated Compliance Hardening, FSE'25) deliberately generates *few* mutants ("relatively few... compared to traditional mutation testing"), scoped to faults specific to a named concern (the paper's illustrative domain is privacy), then generates tests to kill exactly those mutants. Deployed on 10,795 Android Kotlin classes across 7 Meta platforms: 9,095 mutants generated, 571 privacy-hardening tests produced, 73% of generated tests accepted by engineers and 36% judged privacy-relevant. This is industrial validation of the proportionality principle SPEC-013's D-01 states in the abstract: fewer, targeted, named-defect-class tests over volume.
 - [Mutation-Guided LLM-based Test Generation at Meta (arXiv 2501.12862)](https://arxiv.org/abs/2501.12862)

14. **The "cycle of self-deception": LLM-written tests for LLM-written code share the same blind spots** (confidence: high)
 Documented failure mode with a name in the literature: when the same or a similarly-trained model writes both the code and its tests, the tests tend to reflect the same misunderstandings as the code, so they pass without exposing the actual defect. This is not hypothetical - a directly measured instantiation exists (Finding 15) with a quantified effect size.
 - [Use Property-Based Testing to Bridge LLM Code Generation and Validation](https://arxiv.org/html/2506.18315v1)

15. **The "misguidance effect": prompting an LLM with already-buggy code measurably steers it toward tests that validate the bug** (confidence: high)
 A dedicated 2026 study isolates this mechanism: when the code-under-test is buggy, LLMs are internally biased toward generating tests that assert the code's *actual* (wrong) behavior rather than its *intended* (correct) behavior - this simultaneously inflates "misguided tests" (tests that pass against a bug) and suppresses "effective tests" (tests that would catch it). Their tested mitigation - replace the buggy source in the prompt with an LLM-generated specification docstring, so the test-writer never sees the (possibly wrong) implementation - "effectively reduces misguided tests while substantially increasing effective tests" and "remains applicable to both buggy and bug-free code." This directly explains Finding 2's context-dependent correlation collapse: it is the same underlying mechanism (buggy code degrades the reliability of tests written against it) surfacing in two independent studies.
 - [Evaluating and Mitigating the Misguidance Effect of Buggy Code in LLM-Generated Unit Tests (arXiv 2607.22883)](https://arxiv.org/abs/2607.22883)
 - Direct implication for Compass: a tester agent that reads the builder's just-written implementation to write tests against it is structurally exposed to this effect; a tester agent that instead works from the task's stated behavior/spec (not the diff) would be closer to the paper's mitigation.

16. **Independent empirical work confirms LLM tests are shallow even when they compile and pass** (confidence: high)
 Multiple 2025-2026 studies converge: LLM-generated assertions are frequently shallow and "overfit syntactic patterns rather than exercising underlying semantics"; in one Python-suite quality assessment, assertion errors were the most common defect class (64% of identified errors) and "Lack of Cohesion of Test Cases" was the most frequent smell (41% of suites). The oracle problem - generating an assertion that would actually fail if the property under test were violated - is explicitly named as unsolved for LLM-based generation.
 - [Quality Assessment of Python Tests Generated by Large Language Models](https://arxiv.org/pdf/2506.14297)
 - [Do LLMs generate test oracles that capture the actual or the expected program behaviour?](https://arxiv.org/pdf/2410.21136)

17. **A four-way taxonomy of mitigation techniques exists, with measured but uneven effectiveness** (confidence: medium)
 A late-2026 survey ("Large Language Models for Unit Test Generation: Achievements, Challenges, and Opportunities," arXiv 2511.21382) groups the field into prompt-based, coverage-guided, mutation-guided, and agentic/iterative-repair approaches, and separately lists mitigation levers: retrieval-augmented prompting (feed similar existing tests as few-shot examples), iterative refinement with execution feedback, coverage-feedback loops, specification enrichment, and hybrid LLM+symbolic (e.g., constraint-solver) approaches. The survey explicitly names LLM-specific suite bloat as a problem distinct from human-authored bloat: "LLMs tend to generate excessive redundant test cases with overlapping coverage... without explicit deduplication mechanisms," increasing maintenance burden "without proportional fault-detection gains" - directly corroborating SPEC-013's problem statement from the literature side, independent of this repo's own 841-test and 178-in-a-day incidents.
 - `arxiv.org/pdf/2511.21382` (fetched in full; confidence held at medium because the fetch tool's summarization, not a direct read of the paper's tables, is the source for the specific percentages/claims above).

18. **Coverage-guided and mutation-guided iterative loops measurably beat one-shot prompting, and dialogue/iteration - not model size - drives the gain** (confidence: high)
 CoverUp (coverage-guided Python test generation) attributes roughly 40% of its successful generations to the iterative coverage-feedback dialogue specifically, not the base one-shot prompt. LLMloop runs five distinct iterative-repair loops (compilation errors, static-analysis issues, test failures, and mutation-driven quality improvement) rather than a single pass. A hybrid search-based + LLM system (EvoGPT) gets ~10% improvement in both coverage and mutation score over either an LLM-only baseline (TestART) or a pure search-based baseline (EvoSuite) alone - the combination, not either technique in isolation, wins.
 - [CoverUp: Coverage-Guided LLM-Based Test Generation](https://arxiv.org/html/2403.16218v3)
 - [EvoGPT: Leveraging LLM-Driven Seed Diversity to Improve Search-Based Test Suite Generation](https://arxiv.org/pdf/2505.12424)

19. **Pure search-based generation (EvoSuite) still wins on raw compile-reliability and mean mutation score; LLM generation wins on assertion quality where it does compile** (confidence: high)
 Head-to-head: EvoSuite 97.3% compilation rate vs. LLM-based 57.97%; EvoSuite mean mutation score 30.56% vs. best LLM-based mean 19.10% - but LLM-generated *assertions specifically* produced a higher mutation score than EvoSuite's auto-generated assertions on the test cases both approaches could execute (19.10% vs 17.32% in one comparison), suggesting LLMs write better checks once you already have a reliable input/structure generator, which is exactly the shape of the mutation-guided (Findings 13, 15, 18) and coverage-guided approaches: use a mechanical process to find WHAT to test, use the LLM for HOW to assert.
 - [Test Wars: A Comparative Study of SBST, Symbolic Execution, and LLM-Based Approaches to Unit Test Generation](https://arxiv.org/html/2501.10200)

20. **Property-based testing (PBT) is a proposed structural fix to the self-deception cycle, not just a different assertion style** (confidence: medium)
 Because PBT specifies a property/invariant that must hold across an input distribution rather than one input/output pair, it forces articulation of *what defect class* would violate the property - directly matching D-01's "name the defect class" requirement as a testing paradigm, not just a prompting trick. Caveat found in the same body of work: LLMs do measurably worse when the specification is abstract (an invariant that must hold globally) versus concrete (a single worked example) - PBT raises the bar for what the LLM must reason about correctly, it does not remove the reasoning burden.
 - [Use Property-Based Testing to Bridge LLM Code Generation and Validation](https://arxiv.org/html/2506.18315v1)
 - [Agentic Property-Based Testing: Finding Bugs Across the Python Ecosystem](https://arxiv.org/pdf/2510.09907) (Python-specific, Hypothesis-adjacent tooling; not independently re-verified beyond the search snippet).
 - Confidence held at medium: the "does worse on abstract specs" claim traces to a search-summary characterization, not a directly fetched primary quote, in this pass.

### Axis 4: Per-test admission framing and prior art

21. **"Name the defect class before writing the test" already has a rigorous formal analogue: RIPR-based test-goal derivation** (confidence: high, ties Findings 7-8)
 Fault-based testing theory's standard move is to start from a *fault model* (a space of possible faults, e.g. mutation operators) and derive test *goals* designed to satisfy R/I/P/Revealability for each fault in that model, rather than starting from the code and asking "what haven't I run yet." SPEC-013's D-01 ("a test that cannot name a defect class it catches is not written") is this same inversion applied at the single-test-authorship level instead of at the suite-adequacy-criterion level - the literature's version operates on a whole fault model, D-01's operates per test, but the directional move (defect-first, not code-first) is identical and has a 30+ year theoretical pedigree (Zhu/Hall/May 1997, Li/Offutt RIPR).

22. **No literature match found for "per-test admission bar" as a named methodology or product feature** (confidence: medium - absence claim)
 Searches for admission-bar framing, test-goal derivation as an authoring-time gate (rather than a post-hoc adequacy measurement), and "defect class per test" as an explicit LLM-prompting technique did not surface a named prior-art match. The closest analogues found are: (a) TestGen-LLM/ACH's post-hoc assurance *filter* (Findings 12-13) which rejects already-written candidates rather than gating authorship, and (b) mutation-guided generation (Findings 13, 18) which derives tests FROM a specific mutant, which is a defect-class-first generation order but is a generation *technique*, not an admission *policy* stated as a rule agents must follow before writing. This suggests SPEC-013's D-01, while theoretically grounded (Finding 21), would be a novel operationalization if built as a written per-test rule rather than an automated mutation-guided pipeline.

## Contradictions

- Finding 1 vs Finding 2: the 2018 ICSE study and the 2024 AST paper disagree on whether mutation score correlates with real fault detection at all, while the 2026 replication (Finding 2) resolves this by showing the answer is conditional on whether the code under test is already buggy - not a flat yes/no. Treat the ICSE'18 and AST'24 results as measuring different regimes rather than as a genuine disagreement.
- Finding 18 vs Finding 19: CoverUp/LLMloop/EvoGPT findings suggest iterative LLM+feedback loops are the strongest known configuration, while the "Test Wars" head-to-head (Finding 19) shows pure LLM generation still trails EvoSuite on raw reliability metrics (compilation rate, mean mutation score). These are not strictly contradictory - Finding 19 is a one-shot-ish comparison, Finding 18 is about iterative/hybrid configurations - but a reader skimming only mutation-score headline numbers could wrongly conclude LLMs are uniformly worse than search-based generation; the hybrid results (EvoGPT) are the strongest data point and beat both baselines.

## Gaps

- TestGen-LLM's exact per-filter pass-through counts (how many candidates entered vs. survived each of the build/reliability/coverage filters individually) were not extractable from the abstract or a garbled PDF fetch in this pass - only the cumulative 75%/57%/25% figures were recoverable. Would need the full paper body (tables, not abstract) to get precise mechanics of the assurance pipeline Compass might borrow from.
- Marick's original "checked coverage" terminology and any published percentage of typical suites that achieve reachability-without-checked-coverage were not independently verified - the source PDF (`exampler.com/testing-com/writings/coverage.pdf`) failed to fetch on a TLS hostname mismatch, and the finding rests on a secondary course citation. Worth a direct re-fetch attempt (different tool, or archive.org) before treating the "checked coverage" term as settled vocabulary for the plan.
- No retroactive-grading-of-an-existing-suite technique was found in the literature that is cheap enough to run fleet-wide without either (a) a full mutation-testing pass (expensive, Finding 3) or (b) an LLM review pass per test (token cost). SPEC-013's fourth open question ("how is retroactive grading made cheap enough to run fleet-wide?") is not answered by anything surfaced in this pass - this is a genuine literature gap, not just a search-effort gap, since the found mitigation techniques (Findings 12, 13, 15, 18) are all generation-time interventions, not grading-time ones.
- The exact numeric "proportionality baseline" SPEC-013 asks about (behavior count vs. branch count vs. public-surface size) was not directly addressed by any source found; the closest indirect evidence is ACH's demonstrated pattern of scoping test count to *named concerns* rather than any structural size metric (Finding 13), which argues against a purely mechanical proportionality formula and toward a defect-class enumeration as the sizing mechanism instead.
- Did not verify the tsDetect/PyExamine precision/recall figures (Finding 9-10) against the tools' current versions or confirm license/language compatibility with this repo's Python CLI suite - flagged for the tooling-axis researcher rather than re-investigated here.

## Design takeaways for Compass

**What the literature validates directly about SPEC-013's framing:**

- D-01's defect-class-first admission bar has genuine theoretical lineage (Findings 7, 8, 21: fault-based test adequacy theory, RIPR) - it is not an improvised heuristic, it is a per-test application of a 30-year-old suite-level idea. This strengthens confidence that D-01 is buildable into an operational rule, not just a slogan.
- SPEC-013's problem statement (large suites accumulate low-value tests; count is a bad proxy) is independently corroborated by an unrelated 2026 survey describing the exact same LLM-specific failure mode (Finding 17) - this is not a Compass-specific or repo-specific artifact.
- Industrial precedent exists for D-01's "quality over count" stance at scale: Meta's ACH deliberately generates few, targeted tests per concern rather than maximizing coverage or count (Finding 13), and reports strong (73%) engineer acceptance of what it produces.

**What the literature says about the measurement half of the open questions:**

- Mutation testing is the most literature-validated power metric, but Finding 2's context-dependent breakdown on buggy code is a serious caveat for Compass specifically, since agent-written tests are almost always written against code that was *just written and not yet proven correct* - precisely the regime where the correlation collapses. A mutation-score gate alone, applied naively, may not reliably predict whether Compass's agent-written tests would catch a real defect.
- Line/reachability coverage as a redundancy-dedup signal is cheap but literature-flagged as weak (Finding 6); mutation-kill-set overlap is the theoretically correct redundancy signal but expensive (Finding 3's cost problem). This is a genuine cost/accuracy trade the planner will have to make an explicit call on, not something the research resolves for free.
- Assertion-free and other named test smells (Findings 9-10) are cheap, mechanical, zero-LLM-cost admission-bar checks with existing tool precedent (tsDetect, PyExamine) - these are the lowest-hanging, already-solved piece of "measure it by mechanism, not agent assertion" (SPEC-013's stated need).

**What the literature says about the LLM-authorship-specific half:**

- The misguidance effect (Finding 15) and the self-deception cycle (Finding 14) are the most actionable, specific findings for Compass's tester-agent design: a tester agent that derives its tests from the builder's already-written implementation is structurally exposed to writing tests that validate whatever the implementation actually does, bugs included. The measured mitigation (write from a specification/intended-behavior artifact, not from reading the diff) maps directly onto something Compass already has - the plan's task description and acceptance criteria - as the artifact a tester agent could be pointed at instead of (or in addition to) the builder's diff.
- The industrial assurance-filter pattern (Finding 12: TestGen-LLM discards ~75% of raw candidates before human review) is evidence that "ask the model to apply a quality bar in its own prompt" was not sufficient even at Meta's resourcing level - a mechanical post-generation filter did the actual quality enforcement. This bears directly on D-02's premise that mechanism (not prose) is required, and suggests Compass's admission bar likely needs a mechanical check step in the tester/validator pipeline, not just instruction text in the tester agent's prompt.
- Mutation-guided and specification-based generation (Findings 13, 15, 18-19) point at the same design shape from three independent directions: derive the test target (which defect, which uncovered branch, which mutant) mechanically or from a spec artifact FIRST, then let the LLM write the assertion SECOND. This is the strongest convergent signal in this research for what "make AI write good tests" should look like mechanically, as distinct from D-01's authoring-time admission rule, which is a policy question about which tests get to exist at all.
