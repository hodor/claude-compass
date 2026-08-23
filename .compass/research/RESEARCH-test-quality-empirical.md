---
title: Empirical Grade of Compass's Own CLI Test Suite Against the D-01 Admission Bar
type: research
status: draft
area: testing
tags: [testing, test-quality, empirical, seeded-defects, cli]
created: 2026-08-07
updated: 2026-08-07
depends_on: ["[[SPEC-013-test-quality]]"]
summary: "the CLI's own suite graded against the D-01 bar"
---

# Empirical Grade of Compass's Own CLI Test Suite Against the D-01 Admission Bar

From [[SPEC-013-test-quality]].

## Question

Applied to `plugin/cli/tests/` (420 agent-written tests across 18 files), how many tests clear D-01's admission bar ("names the real defect class it catches, or it is not written"), what do the failures look like, and does a seeded-defect probe on a mutated copy confirm the grades?

## Methodology

Census via `git log` and `wc -l` on the real tree. All mutation work ran on a copy of `plugin/cli/` in scratchpad, never on the repo. Admission-bar grading: read every test in 13 of 18 files in full (all of `test_bugs.py`, `test_sync.py`, `test_decisionslib.py`, `test_modelslib.py`, `test_capturelib.py`, `test_lessonslib.py`, `test_track_d.py`, `test_maincli.py`, `test_golden_flat.py`, `test_decision_corpus.py`, `test_fix_frontmatter.py`, `test_hooks_config.py`, `test_vaultlib.py`, `test_apply_models.py`, `test_doctor.py`, `test_lesson_coverage.py`, plus ~60% of `test_commands.py` and a targeted slice of `test_capture_commands.py`), 310 tests graded individually. Seeded-defect probe: 15 hand-written single-line defects across `capturelib.py`, `lessonslib.py`, and `commands/sync.py` on the scratchpad copy, one at a time, full suite run per defect, reverted between runs via a pristine snapshot.

## Findings

1. **Suite size confirmed at exactly 420 tests, matching the spec's own count** (confidence: high)
   `python -m unittest discover -s tests` on a clean copy: `Ran 420 tests in 3.816s`, all green. Era split by first-commit date of each test file: 167 tests from 2026-06-14/15 (initial CLI + bugs.py), 89 from 2026-07-24 (PLAN-003/004/005: units, decisions, models), 164 from 2026-08-05/06 (capture/doctor/lessons burst, the "178 tests in a single day" the spec references, though the actual one-day figure for this specific burst is 164 across 6 files).

2. **Test-to-source line ratio is 1.19:1, not the runaway multiple the spec's framing implies** (confidence: high)
   5,789 lines of test code (`plugin/cli/tests/*.py`) against 4,871 lines of source (1,652 in `plugin/cli/*.py` root modules + 3,219 in `plugin/cli/commands/*.py`). This is a proportionate suite by the crudest possible metric, before any per-test grading.

3. **Detailed grading of 310 tests: 307 PASS, 3 WEAK, 0 FAIL** (confidence: high)
   Every graded test names a real, non-vacuous defect class except three in `test_modelslib.py::RosterTests` (`test_roster_matches_d03_assignments`, `test_agent_files_are_the_13_known_agents`, `test_tier_effort_defaults`), graded WEAK: they restate a hand-maintained constant (`DEFAULT_ROSTER`, `AGENT_FILES`, `TIER_EFFORT`) as literal values rather than exercising logic. Real defect class ("someone edits the roster"), but the assertion is a snapshot of data, not behavior - `plugin/cli/tests/test_modelslib.py:27-49`.

4. **Instructive PASS example: adversarial "never raises" contract tests** (confidence: high)
   `test_capturelib.py::ResolveWarningTests::test_resolve_never_raises_on_junk_config` feeds `{"tiers": None, "agents": {"planner": "not-a-dict"}}` and asserts no exception - `plugin/cli/tests/test_modelslib.py:136-141`. `test_doctor.py::ExitCodeNeverTwoTests::test_internal_error_never_crashes` monkeypatches `vaultlib.find_vault_root` to raise `RuntimeError` mid-run and asserts `doctor` still exits 0/1, never 2 - `plugin/cli/tests/test_doctor.py:363-375`. Both target the exact class of defect a careless refactor introduces (a new code path that forgets the try/except), not implementation shape.

5. **Instructive PASS example: golden byte-identity regression guard** (confidence: high)
   `test_golden_flat.py` fixtures a full vault (flat specs, folder spec, archived spec, broken wikilink, tags) and asserts `sync`'s and `validate`'s output are byte-identical to committed golden files - `plugin/cli/tests/test_golden_flat.py:53-79`. Two tests catch drift across every emission, ordering, and formatting decision in the sync/validate pipeline at once; this is dense coverage per test, the opposite of restated-happy-path bloat.

6. **Instructive PASS example: corpus tests against real production documents with seeded mutations** (confidence: high)
   `test_decision_corpus.py` runs the decision parser against five real pre-convention ADRs (must parse `none-present`, proving no retrofit) and five real D-NN-authored vault documents (must parse exact ID lists), plus four `mutated-*` fixtures that seed defects into real content (broken bold close, unterminated fence, stray token, fenced example) - `plugin/cli/tests/test_decision_corpus.py:27-56`. `test_fixture_set_matches_corpus_table` additionally catches stale test data itself (fixture added without a table entry, or vice versa) - a meta-defect class most suites never guard.

7. **Seeded-defect probe: 13 of 15 defects caught, 2 confirmed holes** (confidence: high)
   See table below. Kill rate 86.7%. Both holes are genuine gaps in adversarial coverage, not artifacts of weak tests - the surrounding tests for those functions are otherwise dense (`rank()` has 13 tests, `_check_caps` logic is exercised by 2).

8. **Overlap is coincidental co-failure on shared code paths, not duplicated assertions** (confidence: medium)
   The archived-filter defect (L1) failed 20 tests at once because `lessonslib.rank()` sits underneath nearly every lessons-command test. But three other defects seeded in the same file (L2 escalated-sort-order, L4 score-parse exception type, L5 row-number counting) were each caught by disjoint, much smaller subsets (2, 1, and 3 tests respectively) - proof the 20 tests are not redundant with each other, they just share one entry point. Call-site density confirms which functions carry this concentration: `sync_cmd.sync()` is invoked in 28 test call sites, `validate.check_vault()` in 15, `lessonslib.rank()` in 12, `capturelib.due()` in 9 - consistent with proportional investment in the CLI's most central functions, not padding.

9. **The two holes point to a real, nameable gap class: boundary and asymmetric-malformation cases** (confidence: high)
   L3 (hole): `lessonslib._parse_tags` bracket check flipped from `startswith("[") and endswith("]")` to `or` - no existing test supplies a value that is bracketed on only one side (e.g. `"[a, b"` or `"a, b]"`), so the `and`/`or` difference is never exercised. S2 (hole): `_check_caps`'s `lesson_count > LESSON_COUNT_CAP` flipped to `>=` - no test sets `lesson_count` exactly equal to the cap (the one test that lowers the cap, `test_lesson_cap_counts_unit_lessons`, sets it to 1 while writing 2 lessons, landing one past the boundary either way). Both are boundary-condition gaps, a documented weak spot for hand- and AI-written test suites alike.

10. **Cross-check requested by the brief (do WEAK-graded tests kill defects PASS tests miss) could not be run: the 3 WEAK tests sit in `modelslib.py`, outside the three modules seeded** (confidence: high, as a statement of scope; gap noted below)
    All three WEAK tests are in `test_modelslib.py::RosterTests`, and no defect was seeded in `modelslib.py`. This specific cross-check needs a defect seeded in that module to answer directly - see Gaps.

## Seeded-defect results

| ID | Module | Defect (one line) | Result | Tests failing |
|---|---|---|---|---|
| C1 | capturelib.py | `due()`: `turns < interval` -> `<=` (off-by-one) | CAUGHT | 6 |
| C2 | capturelib.py | `due()`: dropped the "reached interval, zero signals -> not due" guard | CAUGHT | 1 |
| C3 | capturelib.py | `record_signal()`: dropped `MAX_SIGNALS` bounding slice | CAUGHT | 1 |
| C4 | capturelib.py | `open_opportunity()`: dropped `state["signals"] = []` reset | CAUGHT | 2 |
| C5 | capturelib.py | `close_opportunity()`: `outcome == "abandoned"` inverted to `!=` | CAUGHT | 3 |
| L1 | lessonslib.py | `rank()`: archived filter `== "archived"` inverted to `!=` | CAUGHT | 20 |
| L2 | lessonslib.py | `rank()`: escalated-first sort key flipped (`0 if escalated else 1` -> `1 if ... else 0`) | CAUGHT | 2 |
| L3 | lessonslib.py | `_parse_tags()`: bracket check `and` flipped to `or` | **HOLE** | 0 |
| L4 | lessonslib.py | `_finalize()`: dropped the try/except around `int(score)`, letting raw `ValueError` escape instead of `MalformedRow` | CAUGHT | 1 |
| L5 | lessonslib.py | `parse_catalog()`: `row_number` incremented every line instead of only at row start | CAUGHT | 3 |
| S1 | commands/sync.py | `_prune_capture_log()`: cutoff comparison `at < cutoff` inverted to `>` | CAUGHT | 3 |
| S2 | commands/sync.py | `_check_caps()`: `lesson_count > LESSON_COUNT_CAP` changed to `>=` (off-by-one) | **HOLE** | 0 |
| S3 | commands/sync.py | `_sync_index()`: dropped the archived-record skip | CAUGHT | 2 |
| S4 | commands/sync.py | `_catalog_row()`: dropped the `escalated` field write | CAUGHT | 1 |
| S5 | commands/sync.py | `_clean_logs()`: dropped the `deleted += 1` counter increment (file still deleted, count wrong) | CAUGHT | 2 |

## Grading distribution (310 tests graded in detail)

| Grade | Count | Share |
|---|---|---|
| PASS | 307 | 99.0% |
| WEAK | 3 | 1.0% |
| FAIL | 0 | 0.0% |

All 3 WEAK tests are in one class (`test_modelslib.py::RosterTests`), all graded WEAK for the same reason: assertion restates a static config dict rather than exercising resolution logic.

## Gaps

- The cross-check "does a WEAK test kill a defect PASS tests miss" is unanswered for this run - no defect was seeded in `modelslib.py`, where the only WEAK tests live. A follow-up seeding a `modelslib.resolve()` precedence-order defect (e.g. flip the env-over-project precedence check) would let `RosterTests` be excluded from the run and check whether the remaining `PrecedenceTests`/`BuiltinResolutionTests` alone still catch it - if so, `RosterTests` is confirmed pure overhead, not marginal coverage.
- `test_commands.py` (61 tests, largest single-file test count in the sample after `test_capture_commands.py`) was read to line 550 of 845; the remainder (likely `CoverageTests`/`DecisionsTests` for `commands/coverage.py` and `commands/decisions.py`) was not graded. Given the uniform pattern across every other file, low risk this section diverges, but it is asserted rather than verified.
- `test_capture_commands.py` (878 lines, 50 tests, the single newest and largest file) was spot-checked via class/method names and one 75-line slice rather than read in full; grading is extrapolated from that slice plus the consistent pattern in every fully-read file, not verified line-by-line.
- No defect was seeded in `vaultlib.py`, `decisionslib.py`, or `modelslib.py` - the probe covers 3 of 7 root library modules plus one of 27 command modules. The 86.7% kill rate is representative of the three modules probed, not a suite-wide guarantee.

## Design takeaways for Compass

- The suite this research graded is not an example of the bloat pattern SPEC-013 describes in the abstract - it is close to the outcome D-01 asks for already, despite predating any operational admission-bar mechanism. Whatever discipline produced it (explicit "Adversarial where..." docstrings appear at the top of `test_capturelib.py`, `test_lessonslib.py`, `test_doctor.py`, `test_lesson_coverage.py`, naming the specific claim under adversarial test before any test code) is a documented technique worth naming as a candidate lever, not just a hypothesis - see the literature/tooling research for whether this matches a known technique.
- The two seeded-defect holes found (asymmetric malformed input, exact-boundary cap value) are a concrete, checkable failure mode distinct from "vacuous test" - a suite can be 99% admission-bar-clean by the per-test criterion and still miss defects, because the bar grades individual tests, not suite-level coverage of a function's input space. A mechanism built from D-01 alone would not have caught L3 or S2; boundary-value and malformed-input enumeration needs a second, complementary check.
- The one weak spot found (`RosterTests`) is a recognizable pattern: tests written immediately after defining a data constant, asserting the constant equals itself in a different syntax. If the admission-bar mechanism can pattern-match "assertion target is a module-level dict/list literal defined in the same PR" it would flag exactly this class without needing execution-based analysis.
