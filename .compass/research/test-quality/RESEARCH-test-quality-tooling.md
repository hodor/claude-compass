---
title: Test Quality Tooling - Mutation Testing, Cheaper Signals, and Windows/Stdlib Fit
type: research
status: draft
area: testing
tags: [testing, test-quality, mutation-testing, tooling, windows, stdlib]
depends_on: ["[[SPEC-013-test-quality]]"]
created: 2026-08-07
updated: 2026-08-07
summary: "mutation testing, cheaper signals, Windows/stdlib fit"
---

# Research: Test Quality Tooling

From [[SPEC-013-test-quality]].

## Question

What runnable tooling exists today to mechanically measure test quality, what does it cost, and what fits Compass's constraints (Python-stdlib-preferred CLI, Windows-first fleet, hooks that must stay fast)?

## Methodology

WebSearch/WebFetch across mutation-testing tools (Python, JS/TS, C++, Java/C#), coverage-per-test and test-smell tooling, and stdlib-AST prior art. Local probes run in `C:\Users\rtgasi\AppData\Local\Temp\claude\...\scratchpad\tq-tooling` using two isolated venvs: one native Windows venv (pytest-testmon), one WSL2 Ubuntu venv (mutmut, since it will not run natively on Windows). Mutation probe target: `plugin/cli/capturelib.py` (322 lines) + its existing test file `tests/test_capturelib.py` (310 lines, 32 tests), copied out of the repo, never edited in place. Full-suite baseline timed directly in the repo's `plugin/cli`.

## Findings

1. **mutmut has no native Windows support - WSL is mandatory** (confidence: high)
 Running `mutmut` in a native Windows venv fails immediately with "To run mutmut on Windows, please use the WSL." The GitHub issue tracking native support (#397, open, "enhancement") states the blocker is mutmut's reliance on `fork()` for performance and `resource.RLIMIT_CPU` for timeouts, both Unix-only; fixing it needs a `spawn`-based rewrite of process creation and IPC. No documented workaround short of WSL exists.
 - GitHub issue boxed/mutmut#397

2. **Real mutation-testing cost on this repo's own code, measured** (confidence: high)
 `capturelib.py` (322 lines) mutated with mutmut 3.7.0 inside WSL2 Ubuntu (Python 3.10.12), tests scoped to its own 32-test file:
 - Mutant generation: 393 mutants, 1362ms to generate
 - Full mutation run: 22.68s wall clock, reported throughput 25.94 mutations/second
 - Outcome: 250 killed (🎉), 129 survived (🙁), 14 no-tests/uncovered (🫥) → 63.6% raw kill rate, 65.9% among mutants any test could reach
 - Baseline (unmutated) run of the same 32 tests: 0.09-0.32s
 The 129 survivors are a concrete, mechanically-found gap in a suite whose own docstring calls itself adversarial ("corrupt files, wrong-typed fields, and a flood of signal writes") - direct evidence that self-described adversarial intent does not guarantee mutation-detection power.

3. **mutmut 3's execution model differs from mutmut 2 and affects git-diff scoping** (confidence: medium)
 mutmut 3+ generates one Python function per mutant (`x_close_opportunity__mutmut_37`, `..._38`, etc., all combined via a trampoline) rather than a full mutated file copy per mutant (mutmut 2's model). Docs state git-diff scoping only tracks non-Python file changes explicitly, because "Python files are excluded because their changes are already tracked per function" - implying function-level mutation is mutmut 3's native diff granularity, but the exact CLI flags for `--since`/diff-only runs were not found in the documentation excerpts retrieved.
 - https://github.com/boxed/mutmut/blob/main/HISTORY.rst

4. **Extrapolated cost for this repo's full plugin/cli codebase makes scoping the deciding factor, not the tool** (confidence: medium, extrapolated from one file)
 `plugin/cli` has 4,871 non-test lines. At the measured density (393 mutants / 322 lines ≈ 1.22 mutants/line) that's roughly 5,940 mutants codebase-wide.
 - If each mutant runs only its owning module's own test file (as in the probe, 25.94 mutations/sec): ≈ 229s (≈3.8 min) total.
 - If each mutant instead runs the full 420-test suite (measured baseline: 5.51s per full run, `plugin/cli/tests`): ≈ 5,940 × 5.51s ≈ 32,700s (≈9.1 hours).
 Per-module test scoping, not tool choice, is what separates a tractable measurement pass from an infeasible one at this codebase's scale.

5. **cosmic-ray is the most actively maintained pure-Python mutation tool, but its Windows story is unverified here** (confidence: medium)
 Latest release 8.4.6 (Apr 2, 2026), Python 3.9-3.13, PyPI classifier "4 - Beta." Uses a pluggable "distributor" architecture (local, HTTP-distributed, cloud) for parallel mutant execution. Direct verification of native-Windows compatibility (fork/multiprocessing dependency) was blocked by a repeated HTTP 429 from readthedocs during this session - this is a genuine gap, not an assumption of compatibility.
 - https://github.com/sixty-north/cosmic-ray

6. **mutatest is explicitly abandoned but documents a Windows-portable technique worth separating from the tool itself** (confidence: high on abandonment, medium on technique detail)
 Snyk's health advisor flags mutatest as inactive - no PyPI release in 12+ months, no recent PR/issue activity. Its documented mechanism, however, is notable: it mutates the AST in memory and writes only to `__pycache__` (compiled bytecode), leaving source files on disk untouched, then runs tests against the swapped bytecode. This avoids the fork()-per-mutant-subprocess pattern that blocks mutmut on Windows, since Python's bytecode-cache write/import path is identical on Windows and Unix.
 - https://github.com/EvanKepner/mutatest
 - https://snyk.io/advisor/python/mutatest

7. **A complete stdlib-only mutation-testing pattern has direct academic prior art** (confidence: high)
 The Fuzzing Book (Zeller et al.) documents a full hand-rolled mutation harness using nothing beyond `ast`:
 - `Mutator(ast.NodeTransformer)` subclass walks the tree, counting mutable statement locations
 - A `StmtDeletionMutator` example replaces target statements (`return`, assignment, assert, expr) with `pass`
 - Source is normalized via `ast.parse` → `ast.unparse` for clean diffs before mutation
 - A mutant is applied as a context manager: `__enter__` compiles the mutated source and injects it into `globals()`; `__exit__` catches exceptions to detect "killed," then restores the original
 - Documented limitation: equivalent mutants (syntactically different, semantically identical) make manual review infeasible past roughly 1,000 mutants, pushing toward statistical sampling (Chao's estimator) rather than exhaustive runs
 - https://www.fuzzingbook.org/html/MutationAnalysis.html

8. **pytest-testmon runs natively on Windows and answers a cheaper question than mutation** (confidence: high, directly tested)
 Installed and ran in a native Windows venv (no WSL) against `test_capturelib.py`: `pytest --testmon` completed in 1.79s for 32 tests (vs. 0.85s uninstrumented), building a coverage.py-backed dependency graph between tests and the lines they actually execute. It answers "which tests are affected by this diff" (change-impact selection), not "can any test detect this specific defect" - a materially cheaper and different signal than mutation score.
 - https://github.com/tarpas/pytest-testmon

9. **coverage.py's built-in "Who Tests What" gives per-test coverage for free, with a quantified storage cost** (confidence: high, official docs/maintainer writeup)
 Since coverage.py 5.0, `dynamic_context = test_function` records which test function executed each line; `--contexts` filters reports by test, `--show-contexts` annotates HTML per line. Storage is one bit-per-line string per file per context, so the data file grows roughly N× (N = number of tests) and combining data files slows roughly N× in step - a documented, non-hidden cost of turning this on fleet-wide.
 - https://nedbatchelder.com/blog/201810/who_tests_what_is_here
 - https://coverage.readthedocs.io/en/coverage-5.5/changes.html

10. **PyNose detects 16 Python test smells but is primarily a PyCharm plugin, CLI form unclear** (confidence: medium, single source)
 JetBrains Research's PyNose (ASE 2021 paper, 380 commits, listed as under active development) detects smells including Assertion Roulette, Duplicate Assert, Empty Test, Suboptimal Assert, Redundant Assertion, and Magic Number Test. The README references a `/cli` directory but its maturity and interface are not documented in what was retrieved; the primary shipped interface is the PyCharm 2021.3+ plugin.
 - https://github.com/JetBrains-Research/PyNose

11. **"Assertion Roulette" and "Conditional Test Logic" are the two most common test smells across studied Python and Java codebases** (confidence: medium, academic source)
 Independent of any specific tool, this is the vocabulary the smell-detection literature converges on for the two dominant defect classes in real test suites - directly relevant naming for an admission-bar rubric.
 - PyNose/AromaDr research summaries (arXiv:2108.04639)

12. **flake8-pytest-style catches pytest style/structure issues, not defect-detection power** (confidence: medium)
 A mature, widely-used flake8 plugin checking fixture scope, parametrize syntax, and mocking patterns. It is a style linter, not a quality-of-assertion or mutation-power tool - useful as a cheap first gate but answers a different question than "can this test catch a real defect."
 - https://github.com/m-burst/flake8-pytest-style

13. **StrykerJS (JS/TS) has the most mature documented incremental mode among the tools surveyed** (confidence: high, official docs)
 `--incremental`, available since Stryker 6.2, does a git-like diff of code and test files against a saved incremental report, matching mutants to their prior results. One documented run reused 3,731 of 3,965 mutant results, re-executing only 234; per-PR CI runs are reported to typically finish under 2 minutes. Stryker.NET's equivalent "since" feature is explicitly distinguished from incremental mode: "since" targets mutants changed/new since a prior git state, rather than reusing full prior results.
 - https://stryker-mutator.io/blog/announcing-incremental-mode/
 - https://github.com/stryker-mutator/stryker-js/blob/master/docs/incremental.md

14. **PIT (Java) supports scoped and cached incremental runs with a documented cost cut** (confidence: medium, secondary sources)
 PIT can be scoped to changed files only and caches mutation results locally, skipping classes/tests that haven't changed; documented as a 50-70% runtime cut on medium-sized projects for incremental runs. Guidance from the same sources: target 60-65% mutation score initially on a legacy codebase rather than 85% from day one.
 - https://javapro.io/2026/01/21/test-your-tests-mutation-testing-in-java-with-pit/

15. **Mull (C/C++, LLVM-based) has no official Windows support either** (confidence: medium)
 Mull mutates at the LLVM IR level (works for any LLVM-IR-compiling language: C, C++, Rust, Swift) and uses LLVM JIT to execute mutants without full recompilation per mutant. Documented as working under WSL only; no official native-Windows track.
 - https://mull.readthedocs.io/en/latest/HowMullWorks.html

## Cost Table (this session's measurements)

| Tool | Platform | Target | Result | Wall time |
|---|---|---|---|---|
| mutmut 3.7.0 | WSL2 Ubuntu (native Windows: refuses to run) | `capturelib.py`, 322 lines, 32 scoped tests | 393 mutants, 250 killed / 129 survived / 14 uncovered | 22.68s (25.94 mut/s) |
| pytest baseline | native Windows | same 32 tests | 32 passed | 0.85s (WSL) / 0.09-0.32s (varies) |
| pytest --testmon | native Windows | same 32 tests, first run (cold cache) | 32 passed | 1.79s |
| pytest (full suite) | native Windows | `plugin/cli/tests`, 420 tests | 420 passed | 5.51s |
| mutation, extrapolated, per-module test scoping | - | 4,871 lines, ~5,940 mutants | - | ≈3.8 min |
| mutation, extrapolated, full-suite-per-mutant | - | same | - | ≈9.1 hours |

## Gaps

- cosmic-ray's native-Windows compatibility (fork/multiprocessing dependency) could not be directly verified this session; readthedocs returned HTTP 429 on both fetch attempts. Needs a direct local probe or a GitHub issue-tracker search specifically for "windows."
- mutmut 3's exact CLI surface for diff-scoped/incremental runs (equivalent to Stryker's `--incremental` or PIT's cache) was not found in the documentation excerpts retrieved - only the general claim that function-level changes are tracked via git.
- PyNose's standalone CLI (distinct from the PyCharm plugin) was not verified to exist as a runnable, documented tool - the README mentions a `/cli` directory but no usage was confirmed.
- No direct local probe was run for cosmic-ray, StrykerJS, PIT, or Mull (Python-only probes in scope per the task fleet's language); their cost figures above are all secondary-source, not measured here.
- Coverage.py's Nx storage cost for dynamic contexts was not measured against this repo's own suite size (420 tests) - the multiplier is documented, not locally quantified.

## Design takeaways for Compass

These are the load-bearing facts from the findings above, organized for a planner's decision, not a recommendation:

- **Ruled out for the Windows-first fleet as a mandatory dependency:** mutmut (finding 1, confirmed by direct probe) and Mull (finding 15) both require WSL; cosmic-ray's status is an open gap (finding 5), not a confirmed pass.
- **Runs natively on Windows today, no WSL, no compiled dependency:** pytest-testmon (finding 8, directly verified) and coverage.py's dynamic-contexts feature (finding 9) - both are coverage.py-based change-impact/per-test signals, cheaper and weaker than mutation score, not substitutes for it.
- **A stdlib-only mutation harness is not speculative** - finding 7 documents a complete `ast`-only implementation pattern (NodeTransformer + parse/unparse + context-manager mutant injection) with academic prior art, and finding 6 documents mutatest's bytecode-swap technique as a second, Windows-portable mechanism, independent of the (abandoned) tool that shipped it. Both are candidate mechanisms for an in-house `compass` CLI mutation command that needs no third-party install.
- **Cost is dominated by test-scope, not by tool choice** (finding 4, extrapolated from a real 322-line/393-mutant measurement): running each mutant against only its owning module's tests keeps the whole `plugin/cli` codebase's mutation pass under 4 minutes; running the full 420-test suite per mutant pushes the same pass past 9 hours. Any mechanism chosen needs a per-module or per-diff test-scoping story to stay off the hook-latency budget.
- **Incremental/diff-scoped mutation is documented and mature in JS (StrykerJS, finding 13) and Java (PIT, finding 14) ecosystems**, with StrykerJS's git-diff-matching-against-a-saved-report approach the most concretely documented mechanism found; no equivalently documented mechanism was confirmed for Python tools in this session (finding 3 flags mutmut 3's function-level tracking as inferred, not confirmed via CLI docs).
- **Cheaper-than-mutation signals exist off the shelf** for a first admission-bar pass: coverage.py per-test contexts (finding 9) for duplicate-coverage detection, and test-smell vocabulary (findings 10-12) for the "classes of test that never qualify" language the spec's Needs section asks for (Assertion Roulette, Duplicate Assert, Empty Test map directly onto SPEC-013's "duplicated coverage," "framework tests," "restated happy paths").
