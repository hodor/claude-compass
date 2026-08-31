---
title: "Three Instruments, Three Answers: Reconciling the Test-Quality Research"
type: research
status: complete
confidence: high
area: testing
tags: [testing, test-quality, synthesis, mutation-testing, admission-bar, convergence]
created: 2026-08-07
updated: 2026-08-07
author: "reviewer (Claude)"
depends_on:
 - "[[SPEC-013-test-quality]]"
 - "[[RESEARCH-test-quality-literature]]"
 - "[[RESEARCH-test-quality-tooling]]"
 - "[[RESEARCH-test-quality-empirical]]"
summary: "three instruments reconciled; station model recommendation"
---

# Three Instruments, Three Answers: Reconciling the Test-Quality Research

Consolidation of three parallel research axes for [[SPEC-013-test-quality]]: literature (22 findings), tooling (15 findings plus measured local probes), empirical (grading and seeded-defect probe on this repo's own CLI suite). This document does not add new research. It maps where the axes agree, reconciles the one place they appear to contradict each other, and recommends the shape of the mechanism the combined evidence supports.

## 1. Convergence matrix

Per major question, what each axis says. "Silent" means the axis did not address the question, not that it disagreed.

| Question | Literature | Tooling | Empirical | Verdict |
|---|---|---|---|---|
| **What predicts real defect detection?** | Mutation score correlates on bug-free code (branch coverage r=0.861) but the correlation collapses on already-buggy code, across every analysis perspective (F1, F2). RIPR gives the formal four-condition test per fault (F8). Fault-based adequacy is 30-year-old theory (F7, F21) | Did not evaluate predictive validity; measured what tools cost to run | Seeded defects caught 13/15 (86.7%). D-01 per-test grading gave 307 PASS / 3 WEAK / 0 FAIL on 310 tests (F3, F7) | **Agree, no contradiction.** No axis claims mutation score is a trustworthy standalone predictor in Compass's regime |
| **Why do LLM tests go bad?** | Misguidance effect: buggy code in the prompt biases the model toward asserting actual, not intended, behavior; measured mitigation is to prompt from a spec instead of the source (F15). Self-deception cycle (F14). Shallow assertions overfit syntax (F16). LLM-specific redundant-test bloat named independently (F17) | Silent | Silent on causes, but observed a correlate: every file that opens with an explicit "Adversarial where..." docstring naming the claim before any test code graded uniformly PASS (takeaway 1) | **Agree.** Literature supplies the mechanism, empirical supplies a local correlate pointing the same direction |
| **What measurement is feasible on this fleet?** | Assertion-free and smell detection are cheap, mechanical, zero-LLM-cost with tool precedent at 85-100% precision (F9, F10). No cheap retroactive fleet-wide grading technique exists (Gap 3) | mutmut refuses to run on Windows, WSL mandatory, directly probed (F1). Mull likewise (F15). cosmic-ray unverified (F5). A stdlib-`ast` mutation harness has complete academic prior art (F7). Cost is dominated by test scope, not tool: 3.8 min module-scoped vs 9.1 h full-suite-per-mutant (F4) | Ran a 15-defect seeded probe by hand on a scratch copy in one session; full suite runs in 3.8 s | **Agree.** Windows-first rules out mutmut/Mull as mandatory deps; in-house stdlib path is viable; scoping is the cost lever |
| **Is our own suite good?** | Silent (no repo access) | 63.6% mutation kill on `capturelib.py`, 129 survivors, and explicitly reads this as evidence that "self-described adversarial intent does not guarantee mutation-detection power" (F2) | 99.0% PASS on the D-01 bar, 86.7% seeded-defect kill, 1.19:1 test-to-source ratio, "not an example of the bloat pattern SPEC-013 describes" (F2, F3, F7, takeaway 1) | **Apparent contradiction.** Reconciled in section 2 |
| **What should the admission bar be?** | Defect-class-first has real lineage (F21), but no prior art exists for a per-test *admission* rule as opposed to a post-hoc filter (F22). Meta needed a mechanical filter discarding ~75% of candidates; prompt-only was insufficient (F12). ACH validates few-targeted-tests over volume (F13) | Supplies the smell vocabulary the bar can name (F10, F11, F12) and the runnable-mechanism options | D-01 alone is insufficient: a suite can be 99% bar-clean and still miss defects, because the bar grades individual tests, not a function's input space (takeaway 2) | **Agree, with an important addition.** All three support D-01 plus mechanism; empirical adds that D-01 needs a second, complementary criterion |
| **Proportionality baseline?** | No source addresses it; ACH argues against a mechanical formula, for defect-class enumeration instead (Gap 4) | Silent | 1.19:1 test-to-source, offered as an observation, not validated as a baseline (F2) | **Unanswered.** See section 4 |

Confidence in the matrix as a whole: high. Every cell traces to a numbered finding in a source document.

## 2. The central tension, reconciled

**The apparent contradiction.** Three instruments were pointed at the same artifact, `plugin/cli/capturelib.py` and `tests/test_capturelib.py`, and returned three numbers:

- Tooling: **63.6% mutation kill**, 129 surviving mutants of 393.
- Empirical, per-test D-01 grading: **100% PASS** on that file's tests.
- Empirical, seeded defects: **13/15 caught (86.7%)** across three modules including this one, with all five `capturelib` defects caught.

The tooling axis read its own number as a warning ("self-described adversarial intent does not guarantee mutation-detection power"). Taken at face value, one axis says the suite is weak and another says it is close to the ideal D-01 asks for.

**What I did.** The tooling axis's mutation run persisted. `mutants/capturelib.py.meta` holds a per-mutant exit code for all 393 mutants and `mutants/capturelib.py` holds every mutant's source. I reconstructed the survivor set from the exit codes (0 = survived, 1 = killed, 33 = no covering test), confirmed it reproduces the axis's reported 250/129/14 split exactly, and read a sample of roughly 40 surviving mutant bodies across every function with survivors. The findings below are read off that data, not inferred from the write-ups. Confidence: high.

Persisted at `C:\Users\rtgasi\AppData\Local\Temp\claude\F--claude-plugins-compass\a53dc5f3-060b-4130-8322-58329bf4afa6\scratchpad\tq-tooling\mut-minimal-wsl\mutants\`. Scratchpad, so treat as transient.

### 2a. Where the 129 survivors actually are

| Function | Survived / total | What the survivors are |
|---|---|---|
| `close_opportunity` | 46 / 81 | Dominated by the seven optional count kwargs (`candidate`, `written`, `recurrence`, `rejected`, `error`, `revised`, `archived`) whose dict keys get string-mutated. The three module-scoped tests never pass any of them, so `if value is not None` filters them out and the key name is unobservable |
| `open_opportunity` | 23 / 72 | Same shape: `opportunity.json` record field names and log-row payload |
| `_log_event` | 19 / 32 | Log row key names (`"XXatXX"`, `"XXeventXX"`), `mkdir` flags, and `open("a", ...)` writing to a file literally named `a` |
| `due` | 13 / 47 | Analyzed in 2c below |
| `load_state` | 6 / 20 | Missing-key defaults |
| `_opportunities_dir`, `_log_path` | 4 / 7 each | Path string literals only (`"tmp"` to `"XXtmpXX"` / `"TMP"`) |
| `_iso` | 3 / 7 | Timestamp suffix literals |
| `_write_json`, `bump_turn` | 3 each | Mixed |
| `load_config`, `record_signal` | 2 each | Mixed |
| `_now` | 1 / 1 | `datetime.now(None)`: silently local time instead of UTC |
| `_config_path`, `_state_path`, `_default_state`, `save_state` | **0 survivors** | 100% kill |
| `due_and_log` | 14 uncovered | No test in this file reaches it |

Roughly 99 of the 129 survivors (77%) sit in the trace and path layer: log rows, `opportunity.json` payload fields, and path string literals. The decision logic and state handling are where the kills concentrate, including four functions at 100%.

### 2b. The largest single cause is a scoping artifact, not a suite gap

`test_capturelib.py` never opens the capture log. Grepping it for `capture-log`, `_log_path`, `log_event`, or `jsonl` returns **zero matches**. But `test_capture_commands.py` has a dedicated `CaptureLogLifecycleTests` class that calls `capturelib.open_opportunity` and `capturelib.close_opportunity` directly and reads back the log rows, and `test_sync.py` exercises the log as well: 23 occurrences across the two files.

The tooling axis scoped each mutant to its owning module's own test file. That was the correct cost decision, and it is exactly the decision its own finding 4 identifies as the difference between 3.8 minutes and 9.1 hours. But it excluded the test file that covers the behavior where 77% of the survivors live.

**This generalizes, and it is the most consequential thing in this synthesis** (confidence: high): per-module test scoping systematically over-reports surviving mutants for any module whose behavior is verified cross-file. Cost and accuracy trade against each other along precisely the axis that decides whether mutation testing is affordable. Any mutation mechanism Compass builds must report survivors as candidates for triage, never as a score, because the score is a function of the scoping choice as much as of the tests.

### 2c. What survives that is genuinely worth fixing

Stripping the scoping artifacts and the untested-optional-parameter mutants, a real residue remains. It is small, specific, and none of it was visible to the other two instruments.

1. **A fixture value that aliases the hardcoded default** (confidence: high). Every `DueTests` case calls `self._config(interval=12)`, and `DEFAULT_CONFIG["interval"]` is also 12. So mutants 24, 28 and 29, which mutate the lookup key (`config.get(None, ...)`, `"XXintervalXX"`, `"INTERVAL"`) and therefore make `due()` silently ignore the configured interval and fall back to the default, are unobservable. The tunable could stop working entirely and the suite would stay green. Fix cost: change one number in the fixture. Generalizable rule: when testing a configurable lookup, never use a fixture value equal to the fallback.

2. **A sanitized fallback tested far from the boundary** (confidence: high). Mutant 42 changes the wrong-type guard from `turns = 0` to `turns = 1`. At `interval=12` both are below the interval, so the result is identical. Only a fixture near the boundary distinguishes them.

3. **An unpinned environmental contract** (confidence: high). `_now()` mutated to `datetime.datetime.now(None)` survived: UTC silently becomes local time. Nothing in the suite pins the timezone. This is a genuine defect class, and it is the single clearest example of something mutation found that neither D-01 grading nor the hand-seeded probe surfaced.

Items 1 and 2 are the same family as the two holes the seeded-defect probe found on its own (empirical F9: asymmetric malformed input, exact-boundary cap value). **Two independent instruments, using unrelated methods, converged on one gap class: boundary and fixture-value selection.** That is the strongest convergent signal in the entire body of evidence.

### 2d. Confirmed equivalent and near-equivalent mutants

The literature's equivalent-mutant problem (F3) is present and visible. `_log_event` mutant 27 changes `encoding="utf-8"` to `"UTF-8"`, which is exactly equivalent since Python codec names are case-insensitive. The `"TMP"` and `"CAPTURE-LOG.JSONL"` path-case mutations are equivalent on Windows' case-insensitive filesystem but not under WSL where the probe ran, so the same mutant is equivalent or not depending on the platform the measurement runs on. A further large group (the missing-key default variants in `due` and `load_state`) is unreachable in production because `load_config` and `load_state` guarantee every key is present before `due()` ever sees the dict: not formally equivalent, but unreachable under the module's caller contract.

### 2e. Verdict

**These are not three answers to one question. They are three answers to three different questions** (confidence: high).

- **D-01 per-test grading measures intent legibility**: can a reader name the defect class this test targets. It grades a test against its own stated purpose, in isolation. It is structurally blind to gaps *between* tests, to input-space coverage of a function, and to fixture values that happen to alias a constant.
- **Seeded defects measure realistic-defect detection**, but only over defects someone thought to seed. All 15 were plausible refactor mistakes in decision logic. Zero were seeded in the trace and log payload layer, which is where mutation put 77% of its survivors. It measures the suite against the imagination of the seeder.
- **Mutation score measures exhaustive syntactic perturbation over one module under one test-selection scope.** It is uniform over the AST, so it weights a log row's key name exactly as heavily as the due-check arithmetic, and it inherits whatever scoping you chose for cost reasons.

The 63.6% and the 99%/86.7% are consistent once decomposed. The suite is strong on decision logic and genuinely thin on the trace layer *as seen from inside its own file*; most of that thinness is covered by a neighbouring test file the measurement could not see.

**Which measurement should the admission bar trust? None of them as a gate** (confidence: high). They belong at different stations:

| Instrument | Role | Why |
|---|---|---|
| D-01 per-test criterion | The **authoring-time bar**. What the tester agent applies before a test exists | It is the only one of the three that operates before the test is written, which is what D-01 asks for |
| Mechanical smell/AST filter | The **admission gate**. Cheap, deterministic, runs every time | Literature F12: prompt-only quality bars were insufficient even at Meta's resourcing |
| Mutation | An **on-demand diagnostic**, human- or agent-triaged, never a score with a threshold | Its output is 77% noise at the scope that makes it affordable, and the residue is valuable but needs judgment to extract |
| Seeded defects | The **validation instrument for the bar itself**, run occasionally | It is how you answer "did the bar actually help", which is SPEC-013's own falsifiable hypothesis |

## 3. Agreements strong enough to build on

1. **Mechanism beats prose. A written rule in an agent prompt is not sufficient on its own.** (confidence: high) Literature F12: Meta's TestGen-LLM shipped a mechanical assurance filter that discards roughly 75% of raw candidates before a human sees them, and this was necessary at Meta's resourcing level. Independently, SPEC-013's own D-02 states this as a premise. No axis dissents.

2. **Tests should be authored from intended behavior, not from the implementation just written.** (confidence: high) Literature F15 isolates the misguidance effect and reports a measured mitigation: replace the source in the prompt with a specification. F14 names the self-deception cycle, F2 shows the proxy metrics collapse in exactly this regime, and F19 points at the same shape from a third direction (mechanical process decides *what* to test, LLM decides *how* to assert). Empirical takeaway 1 supplies a local correlate: the files that name the adversarial claim in a docstring before any test code are the ones that graded uniformly PASS. Four independent lines, one direction.

3. **Boundary values and fixture selection are the dominant residual gap class, and D-01 alone will not catch them.** (confidence: high) Empirical F9 found both seeded-defect holes there. My mutation decomposition (2c) found the same family independently. Empirical takeaway 2 states the reason: the bar grades individual tests, not a function's input space. This needs to be a second, explicit criterion alongside D-01, not an afterthought.

4. **Cheap mechanical checks exist today and are the lowest-hanging piece.** (confidence: high) Literature F9 and F10 (assertion-free detection, Assertion Roulette, Duplicate Assert, Empty Test; tsDetect reports 85-100% precision), tooling F10 through F12 (the same vocabulary, plus the Python-specific tools), and empirical takeaway 3 (a pattern-match on "assertion target is a module-level literal" would have flagged the only three WEAK tests found). All three axes point at the same cheap first pass.

5. **Windows-first rules out the mainstream mutation tools as mandatory dependencies, and an in-house stdlib path is real.** (confidence: high) Tooling F1 is a direct probe, not a doc claim: mutmut refuses to run natively. F15 says the same for Mull, F5 leaves cosmic-ray unverified. F7 documents a complete `ast`-only harness with academic prior art and F6 documents a second Windows-portable technique. Nothing in the other axes conflicts.

6. **Scope, not tool choice, decides whether mutation is affordable.** (confidence: high) Tooling F4 measures the gap at 3.8 minutes versus 9.1 hours. My section 2b adds the cost of the cheap option: the scoping that buys the 3.8 minutes is what produced 77% of the false signal.

## 4. Disagreements and open questions for the human

**Q1. Does SPEC-013's problem statement still hold for this fleet? (The one that changes the plan's shape.)**

The spec's motivating evidence is bloat: "841 tests in a suite", "178 tests in a single day", "nobody can say which of those tests earn their keep". The empirical axis went and looked. This repo's suite is 420 tests at a 1.19:1 test-to-source line ratio, 99.0% clean against the D-01 bar with zero FAIL grades, catching 13 of 15 hand-seeded realistic defects, and the "178 in a day" burst is actually 164 tests across 6 files in a suite the axis calls "close to the outcome D-01 asks for already" (empirical F1, F2, F3, F7, takeaway 1).

This is not a disagreement between axes. It is a disagreement between the spec's premise and the measurement. It does not weaken D-01 as policy, and the 841-test suite the spec cites was not measured here. But it changes what the mechanism is *for*: a guard that prevents regression and keeps the current discipline legible, rather than a cleanup that prunes accumulated bloat. Those two framings produce materially different plans, and only the human can rule on which SPEC-013 is buying. **My reading: build the guard, not the cleanup.** (confidence: high on the measurement, medium on the recommendation, since it rests on one repo's suite.)

**Q2. Is the trace and observability layer in scope for the admission bar?**

Mutation says `capturelib`'s log-row construction is the least-pinned code in the module. D-01 grading never asked the question. If capture-log rows are a contract (and they look like one: `sync` prunes them, the capture commands read them), they deserve tests and the current coverage is thinner than the headline grade suggests. If they are debug output, the survivors there are correctly ignored and mutation is over-weighting them. This determines whether the residue in section 2c is a small backlog or a non-issue. (confidence: high that the question is real; the answer is a judgment about intent that I should not make.)

**Q3. May a mutation result ever block?**

I recommend diagnostic-only, never a gate and never on a hook path, for the reasons in 2b and 2e. the human owns whether the validator may ever fail a task on it.

**Q4. Where does the mechanism live?**

A `compass` CLI subcommand invoked by the validator, a hook, or a step inside the tester agent. The cost profiles differ sharply and hooks have a latency budget. The evidence does not decide this; Compass's north-star goal 4 (mechanical work off the agent token budget) argues for the CLI.

**Q5. Language scope.** SPEC-013's Needs asks for a language-agnostic core with language-specific edges. Every local probe in all three axes was Python. The tooling axis surveyed JS, Java and C++ tools but ran nothing. Unresolved, and it matters if the mechanism ships to users whose fleets are not Python.

## 5. Recommended shape for the ADR and plan

A clear primary recommendation, not a menu. Four mechanisms, ordered by evidence strength divided by cost. **Mechanisms 1 and 4 are prose-only, cost nothing at runtime, and carry most of the value. Build them first and independently of the tooling.**

**1. Spec-derived test authoring. The tester agent writes from intended behavior, not from the builder's diff.** (confidence: high)
Traced to literature F15 (misguidance effect with a measured mitigation), F14, F2 (the proxy collapse happens in exactly the regime where an agent tests code a peer just wrote), F19; corroborated by empirical takeaway 1. Compass already has the artifact the mitigation calls for: the plan task's description and acceptance criteria. Point the tester at those, and require the "Adversarial where..." docstring naming the claim under test before any test code, which the empirical axis found correlates with the uniformly-PASS files.
Cost: agent-definition text. Zero runtime, zero tokens beyond the prompt.

**2. A mechanical admission filter in the CLI, off the agent token budget.** (confidence: high)
Traced to literature F12 (prompt-only was insufficient at Meta), F10 (assertion-free detection is an AST walk at zero LLM cost), F9 (85-100% precision precedent), tooling F10 through F12 (vocabulary), empirical takeaway 3.
Scope it to what a stdlib `ast` walk can decide with no judgment: assertion-free tests, Assertion Roulette, Duplicate Assert, Empty Test, and the "assertion target is a module-level dict or list literal defined in the same module" pattern that flags exactly the three WEAK tests the empirical axis found and nothing else.
Cost: one CLI subcommand, milliseconds, no third-party install, no WSL.

**3. Diff-scoped mutation as an on-demand diagnostic. In-house, stdlib `ast`, never a gate.** (confidence: high on the shape, medium on the build estimate)
Traced to tooling F7 (complete `ast`-only prior art), F6 (bytecode-swap as a second Windows-portable technique), F1 and F15 (mutmut and Mull are unavailable natively on a Windows-first fleet), F4 (scope is the cost lever), F13 and F14 (incremental precedent in the JS and Java ecosystems); constrained by literature F2 and F3 and by section 2b of this document.
Three non-negotiable design constraints fall out of the reconciliation: **(a)** report surviving mutants as candidate gaps for triage, never as a percentage with a threshold; **(b)** run the *full* suite, not the owning module's test file, or explicitly label the result as scope-limited, because module scoping is what produced 77% of the noise here; **(c)** scope to the diff, not the codebase, which is what keeps (b) affordable.
Cost: real engineering. Defer behind 1, 2 and 4.

**4. A boundary-and-fixture criterion, stated alongside D-01 rather than folded into it.** (confidence: high)
Traced to empirical F9 and takeaway 2 (both seeded-defect holes were boundary or asymmetric-malformation), plus my independent mutation residue in 2c (fixture aliases the default; fallback tested far from the boundary). Two unrelated instruments converged here, which is the strongest signal in the evidence base.
Concretely, three rules the tester can apply per test: exercise the exact boundary value and not only values comfortably either side of it; never let a fixture value equal the constant it is meant to override; supply asymmetrically malformed input, not only well-formed and fully-malformed input.
Cost: rubric text. Zero runtime. This is the highest value-per-token item in the entire synthesis.

## 6. What the evidence does not support building

| Do not build | Killed by |
|---|---|
| **A mutation-score threshold or gate** ("must reach N%") | Literature F2 (the proxy is unreliable exactly when the code under test may be buggy, which is always the case here) and F3 (equivalent mutants have no complete solution). Killed directly by section 2c: 63.6% was measured on a suite that is genuinely strong, and the number is dominated by scoping artifacts and trace-layer string mutations |
| **mutmut, Mull or any WSL-requiring tool as a required dependency** | Tooling F1, a direct probe: mutmut refuses to start on Windows and the blocker is architectural (`fork()`, `RLIMIT_CPU`). F15 for Mull. F5 leaves cosmic-ray unverified, which is not a pass |
| **Coverage-overlap-based test deduplication or pruning** | Literature F6: minimization by coverage overlap "can severely compromise the fault-detection effectiveness" of the reduced suite, because coverage overlap is a far weaker signal than fault-detection overlap. Confirmed locally by empirical F8: one seeded defect failed 20 tests at once and looked exactly like redundancy, but three other defects in the same file were caught by disjoint subsets of 2, 1 and 3 tests. Those 20 tests are not redundant; they share an entry point. This is the intuitive thing to build and the evidence specifically kills it |
| **Retroactive LLM grading of every existing test, fleet-wide** | Literature Gap 3: no cheap retroactive technique exists in the literature, and the axis flags this as a genuine gap rather than a search failure. Empirical F3 gives the yield: grading 310 tests by hand surfaced 3 WEAK and 0 FAIL, about 1%. The token cost cannot be justified against that hit rate |
| **A proportionality formula** (tests per branch, per public method, per behavior) | Literature Gap 4: no source addresses it, and ACH's pattern argues against a mechanical formula in favour of defect-class enumeration (F13). Empirical F2: at 1.19:1 test-to-source there is no bloat for a formula to catch. SPEC-013 D-01 already forbids suite-size judgment in either direction, so a formula would contradict the spec it serves |
| **Mandating property-based testing** | Literature F20 is medium-confidence and carries its own caveat: LLMs do measurably worse when the specification is abstract rather than concrete, so PBT raises the reasoning bar rather than removing it. Fine to allow, not enough evidence to require |

## Gaps in the combined evidence

- **Non-Python fleets.** Every local probe across all three axes was Python. The tooling axis surveyed StrykerJS, PIT and Mull but ran none of them. SPEC-013's Needs asks for a language-agnostic core; nothing here validates one.
- **The proportionality baseline** (SPEC-013 open question 3) is genuinely unanswered. Literature found no source, empirical offered a ratio without validating it as a baseline. My reading is that the combined evidence argues the question is malformed and defect-class enumeration replaces it, but that is an inference, not a finding (confidence: medium).
- **Retroactive fleet-wide grading** (SPEC-013 open question 4) is unanswered and, per literature Gap 3, unanswered in the literature too.
- **The 841-test suite the spec cites was never measured.** All empirical work was on this repo's 420-test CLI suite. Q1 above rests on that one sample.
- **The WEAK-versus-PASS cross-check was not run** (empirical F10): no defect was seeded in `modelslib.py`, where the only three WEAK tests live, so whether they carry marginal coverage is still unknown.
- **My survivor classification sampled roughly 40 of 129 mutant bodies**, chosen to span every function with survivors. The per-function distribution in 2a is exact (read from all 393 exit codes); the characterization of what the survivors *are* is a sample (confidence: high for the clusters described, medium for the precise proportion of genuinely-equivalent mutants).

CONVERGENCE: HIGH
