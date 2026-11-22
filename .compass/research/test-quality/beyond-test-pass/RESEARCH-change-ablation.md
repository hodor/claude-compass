---
title: "Research: change-ablation (do the tests depend on the change)"
type: research
status: complete
confidence: medium
area: testing
tags: [research, testing, ablation, mutation, fail-to-pass, verification]
created: 2026-11-21
updated: 2026-11-21
author: researcher
git_branch: "master"
git_commit: "6faced1"
summary: "stub or revert a task's diff and see which tests flip: what Compass already checks, prior art, measured cost on a real plugin commit, failure modes"
---

# Research: change-ablation

From [[SPEC-034-verification-beyond-test-pass]]. Builds on [[research/llm-research/REVIEW-llm-research-for-compass]] A3 and [[research/test-quality/RESEARCH-test-quality-tooling]] (mutation tools, costs, Stryker/PIT incremental), not repeated here.

## Question
Can Compass cheaply show that a task's tests fail when the task's code is removed, and what does that cost and miss?

## Methodology
Repository mining (empirical study of the artifact: a real plugin commit ablated in a scratch worktree) plus a technology-landscape read of prior art. No grading line from the brief beyond `grading: allowed`; grades given per finding.

## Findings

### What plugin/ already does (file:line)

1. **Pre-build red evidence already proves "tests fail without the change", but only once, before the build.** The tester runs the suite with no implementation present and records the command and verbatim failing output (`plugin/templates/agents/tester.md:49-52`). An import or collection error counts as red, labelled as such, because a test that only failed to import "has not yet been seen to fail for its own reason" (`tester.md:56`). Grade: asserted in agent text, no measurement. Confidence: high (read).
2. **`compass test-checkpoint` makes that red tamper-evident and proves the same tests later pass.** `record` stores commit SHA, per-file hashes and test ids; `verify --against-run` requires every checkpointed id to pass in the supplied run (`plugin/cli/commands/test_checkpoint.py:1-60`, `:909`). This is a pass-to-pass-style check on test text, not an ablation of the diff. Confidence: high.
3. **Nothing re-derives the fail from the final diff.** The tester post-build mode runs the full suite and verifies the checkpoint (`tester.md:66-73`); the validator runs `test-checkpoint verify` and at least one adversarial probe (`plugin/templates/agents/validator.md:89`, `:114-144`). Neither reverts the builder's diff. Tests the tester adds post-build, and any pre-build test that the builder later edits around, have no recorded fail-without-change. Confidence: high (grep of tester.md and validator.md for ablate/revert/without-the-change found nothing).
4. **Mutation is deliberately not a gate.** Methodology text: mutation is an on-demand diagnostic, `compass mutate` unbuilt (`plugin/skills/methodology/SKILL.md`, Testing mandate item 3). Confidence: high.


### Prior art

5. **SWE-bench defines the check as two test lists validated against the gold patch.** An instance carries FAIL_TO_PASS (fail before the gold patch, pass after) and PASS_TO_PASS (pass on both sides). `get_eval_report` marks resolved only when both ratios are 1; a missing or skipped FAIL_TO_PASS test counts as failed, a skipped PASS_TO_PASS test counts as maintained (`swebench/harness/grading.py`, read from raw GitHub: `get_eval_tests_report`, `test_failed`, `test_maintained`, `get_resolution_status`). This is change-ablation done once, offline, with the human's patch as the ablation. Compass's pre-build red evidence (finding 1) is the same idea with the tests authored first. Grade: source code read, measured behavior. Confidence: high.
   - https://raw.githubusercontent.com/SWE-bench/SWE-bench/main/swebench/harness/grading.py
   - Marks: source code, not retracted, not a preprint, citations n/a, convergence with finding 1

6. **Fail-to-pass alone does not prove the tests are strong.** SWE-ABS (Feb 2026, preprint) reports about one in five patches passing SWE-bench Verified are wrong, adds coverage-driven and mutation-driven tests, rejects 19.71% of passing patches and lowers the top score from 78.80% to 62.20%. UTBoost (ACL 2025) found 345 erroneous patches labelled as passed through insufficient tests. Both attack the other half of the question: tests that pass the right change also pass wrong ones. Grade: preprint plus peer-reviewed, measured, one benchmark. Confidence: medium.
   - https://arxiv.org/abs/2603.00520 ; https://arxiv.org/pdf/2506.09289 (figures from a search summary and the SWE-ABS abstract page, UTBoost full text not read)
   - Marks: preprint (SWE-ABS) and peer-reviewed (UTBoost), no retraction known, citations not checked, convergence 2 sources agree

7. **Extreme mutation (Descartes) is function-body ablation, and "pseudo-tested" is its verdict.** A method is pseudo-tested when the suite executes it and no test fails once its body is removed (void method: empty body; typed method: constant return). Descartes is a PIT engine. The replication study covered over 28,000 methods, found pseudo-tested methods in every subject, and reports developers mostly would not pay the testing price to fix them. Grade: peer-reviewed (Empirical Software Engineering 2019, ASE 2018 tool demo), measured. Confidence: high for the definition; the ratio and runtime are not in the abstract and the full-text fetch returned binary, so none is quoted.
   - https://arxiv.org/abs/1807.05030 ; https://link.springer.com/article/10.1007/s10664-018-9653-2
   - Marks: peer-reviewed, not retracted, arXiv and journal versions, citations not checked, convergence with finding 12

8. **Diff-scoped mutation exists in JS and Java, not confirmed for Python tools.** Stryker `--incremental` re-runs only mutants whose code or tests changed against a saved report; Stryker.NET `since` targets mutants changed since a git ref; PIT has `withHistory` for incremental runs and a commercial add-on with git integration (`+GIT(from[HEAD~1])`). The PIT Maven quickstart does not document `scmMutationCoverage`, so that goal is unverified here. mutmut 3 tracks changes per function but a since-commit flag was not found. Costs, the WSL requirement and the 393-mutant measurement are in [[research/test-quality/RESEARCH-test-quality-tooling]] findings 1-4 and 13-14. Grade: vendor docs, asserted. Confidence: medium.
   - https://pitest.org/quickstart/maven/ ; https://stryker-mutator.io/blog/announcing-incremental-mode/
   - Marks: vendor docs, n/a, n/a, n/a, convergence with the existing tooling document

### Worked case: ablating a real plugin/cli commit

Subject: the commit that added `compass idea import` (non-test diff: 4 files, +446/-52, 10 hunks, one new file). Its 14 tests were committed earlier as a failing-tests-first commit. The commit was checked out as a detached scratch worktree under `.claude/worktrees/`, ablated, and the worktree removed. Tests selected: the 6 `test_idea*.py` files that exist at that commit (58 test ids: 57 pass, 1 red at baseline). Python 3.13, pytest 9, Windows. Scratch scripts were kept outside the repo.

9. **Whole-diff revert flipped 12 of 14 import tests and no others.** `git apply -R` of the non-test diff restores the parent commit's code; 12 tests went pass to fail. Of the 2 that did not: one was already red at the commit (a launcher test asserting an unchanged vault snapshot, broken by a usage-log write that a later commit fixes), so a baseline red cannot flip; the other (`test_unreadable_input_fails_cleanly_and_writes_nothing`) passes with and without the change because its assertions (nonzero exit, vault untouched) also hold when the subcommand does not exist. Grade: own measurement, n=1. Confidence: medium.
   - `git apply -R --ignore-whitespace` was needed: the checkout had CRLF and the stored diff LF, so plain apply failed on every file
   - Marks: own run, n/a, n/a, n/a, single observation

10. **Cost on this case.** The matching 58 tests ran in 6.4-6.9 s (baseline) and 5.6 s (reverted), quiet machine; the new-tests file alone 1.5 s. One whole-diff ablation is one extra run of the matching set. The full suite at that commit (2,459 tests, 28 of them expected reds from tests committed ahead of their implementation) took 661 s, measured while other runs shared the machine, so the figure is inflated. Name selection (`test_idea*`) picked about 2.4% of tests. Grade: own measurement. Confidence: medium.

11. **Per-file and per-hunk reverts make half-applied states that flip unrelated tests.** Reverting only `ideaimport.py` flipped 41 (the dispatcher in `commands/idea.py` still imports it, so add, status and find break too); only `idealib.py` 26; only `commands/idea.py` 12; `maincli.py` 0. Per hunk: 4 of 5 `idea.py` hunks flipped 12-15, one `idea.py` hunk 0, `idealib.py` hunks 26, 26 and 2, the one-line `maincli.py` hunk 0. The 41 and 26 count dependents of a broken module, not tests of the change. An earlier run reported 11/29/21 because pytest subtest failures were not parsed; the figures here are from the corrected run. Grade: own measurement. Confidence: medium.

12. **Function-body stubbing found no pseudo-tested function, but 14 of 14 new-module functions flipped the same 12 tests.** 22 functions overlapping changed lines were stubbed with `raise NotImplementedError`, one at a time (4.4-8.3 s each). Every function in the new module flipped the same 12 end-to-end tests, down to the one-line `Entry.label` and `_is_separator`; dispatcher `run` flipped 41; `idealib` helpers flipped 14 to 27. The verdict is "reached and asserted by something"; it does not say which test covers which function. Grade: own measurement. Confidence: medium.

13. **Wall time scales with hunks or functions, not with the suite.** 1 whole-diff, 4 per-file, 10 per-hunk and 22 per-function runs made 37 matching-set runs in about 4 minutes (about 6.5 s each, under load from the concurrent full-suite run). Whole-diff is 1 run; per-function is N runs for N changed functions. Grade: own measurement. Confidence: medium.

### Language-agnostic mechanics

14. **Three granularities; only the last needs a parser.** Whole-diff: `git apply -R` on the non-test paths (a new file is deleted, a deleted file returns). Per hunk: split the diff on `@@`, keep each file header, `git apply -R --recount` one hunk at a time. Per function: parse the file (Python `ast` gave `lineno` and `end_lineno`) and replace the body with a throw or a typed constant; other languages need their own parser (tree-sitter would be one route, not tried). Restore between runs with `git checkout -- .` inside the scratch worktree. Grade: own measurement. Confidence: high for the git mechanics, low for the multi-language claim.

15. **Test selection is the cost lever.** Name or directory matching worked here (6 files). Coverage-per-test selection (pytest-testmon, coverage.py `dynamic_context = test_function`) is measured in [[research/test-quality/RESEARCH-test-quality-tooling]] (testmon 1.79 s versus 0.85 s for 32 tests). Confidence: medium.

### Failure modes seen or documented

16. **A baseline red cannot flip.** The one red test here (finding 9) was invisible to the ablation. SWE-bench validates the instance first for the same reason (finding 5). The ablation needs a green baseline per selected test and treats an unrelated red as no evidence. Confidence: high.
17. **A test that passes without the change.** Error-path tests whose assertion holds when the feature is absent (finding 9) do not flip, so ablation surfaces them, but it cannot tell a weak test from a correct "must keep failing cleanly" test. Confidence: high (seen once).
18. **Partial reverts cause collateral flips.** Removing one module of a connected change breaks its callers (finding 11), so per-hunk and per-file flips overstate dependence; whole-diff is the coherent state and per-function stubbing keeps the call graph intact. Confidence: medium.
19. **Import and collection errors read as flips.** Ablating additive code that tests import can turn a whole file into one collection error, so the count says "tests import the module", not "behaviors checked". The tester template already labels an import error red but "not yet seen to fail for its own reason" (`plugin/templates/agents/tester.md:56`). Not hit here, because the dispatcher imports the new module lazily. Confidence: medium (pytest behavior plus the template text).
20. **Refactors, flakiness, line endings.** A refactor-only task should flip zero tests, so a nonzero flip there is the signal; a flaky test flips at random, so a flip needs one repeat on the ablated tree (the plugin history shows tests reworked after load-dependent failures, commits `ac9b822` and `96def5c`); worktrees on this host check out CRLF while stored diffs are LF (lesson [[LESSON-autocrlf-churns-lf-writers]]). Confidence: medium.

## Candidate changes for Compass

Listed by impact, each with the north star served; none is chosen for the human.

1. **Whole-diff ablation at the validator or tester post-build station.** North star 1 (accuracy); cost about one extra run of the task's matching tests (finding 10). Revert the non-test paths of the task diff in a scratch worktree, run the tests the task added or checkpointed, report which stay green. Would change `plugin/templates/agents/validator.md` (probe section, `:114-144`), possibly a `compass` command wrapping worktree, apply and run. Covered: partly. Pre-build red evidence (`tester.md:49-56`) proves the fail once, before the build; nothing reruns it against the final diff, and tests added post-build have no recorded red.
2. **Store the red once, ablate only what lacks one.** North stars 1 and 4. `test-checkpoint` records SHA and ids of pre-build tests; ablation would cover post-build tests and any pre-build test whose red was an import or collection error (`tester.md:56`). Would change `plugin/cli/commands/test_checkpoint.py` (record the kind of failure) and `tester.md`. Covered: no (the red kind is free text in the report).
3. **Report unflipped tests with the baseline-red and import-error caveats.** North star 2. On a task that adds behavior, an unflipped new test is a finding (2 of 14 here); a refactor task flipping nonzero is a finding. Would change the validator report format. Covered: no.
4. **Per-function stub as an on-demand diagnostic, not a gate.** North star 1; N runs per task (finding 13). Fits the methodology rule that mutation is diagnostic only (`plugin/skills/methodology/SKILL.md`, Testing mandate item 3; `compass mutate` unbuilt). Covered: no; finding 12 shows it adds little where tests are end-to-end.

## Contradictions
- Finding 11 (41 and 26 flips on a half-reverted module) and finding 12 (the same 12 tests flip for every new function) both read as "dependence" but measure different things: dispatcher breakage and test fan-in on a shared path. Neither is per-test coverage.

## Gaps
- One commit, one language, one host: the flip counts are an example, not a rate. A second commit with a refactor-only change would test failure mode 20.
- cosmic-ray, mutmut 3 since-commit flags and PIT `scmMutationCoverage` not verified; Descartes full-text ratio and runtime not read; UTBoost full text not read.
- Full-suite time was measured under load; a quiet figure was not taken.
- Citation counts and retraction status of the cited papers were not queried.
- Body replacement for non-Python languages was not tried.
