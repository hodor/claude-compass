---
title: Paired Seeded-Defect Validation of the Test-Design Admission Bar
type: research
status: draft
area: testing
tags: [testing, test-quality, empirical, seeded-defects, cli, paired-experiment]
created: 2026-08-07
updated: 2026-08-07
depends_on: ["[[SPEC-013-test-quality]]", "[[RESEARCH-test-quality-empirical]]", "[[PLAN-007-test-quality]]"]
---

# Paired Seeded-Defect Validation of the Test-Design Admission Bar

From [[SPEC-013-test-quality]], TASK-063 of [[PLAN-007-test-quality]].

## Verdict, up front

**Arm B (bar-authored) caught 15/15 seeded defects; Arm A (pre-bar) caught 13/15.** Both predicted movers - L3 (asymmetric bracket in `lessonslib._parse_tags`) and S2 (exact-boundary cap in `sync._check_caps`) - flipped from HOLE to CAUGHT. No defect moved the other direction. This is **not** SPEC-013's falsification criterion firing (that would require Arm B below Arm A). Read this verdict together with the validity caveats below, in particular the non-blinded-authorship caveat, before treating 15/15 as a clean measurement of the bar's own effect.

## Question

On the same three modules Arm A measured (`capturelib.py`, `lessonslib.py`, `commands/sync.py`), do tests re-authored under the `test-design` skill's admission bar catch more, fewer, or the same seeded defects as the tests that existed before any bar - and specifically, do the two documented holes (L3, S2) move?

## Methodology

All work ran on a scratch copy of `plugin/` in scratchpad
(`C:\Users\rtgasi\AppData\Local\Temp\claude\...\task063\`), never on the
real repository tree, which was confirmed untouched (`git status`
clean) at the end of the run. Two snapshots were kept: `plugin_pristine`
(read-only reference, unittest-discover green at 478 tests, 0 errors -
the full `plugin/` tree had to be copied, not just `plugin/cli`, because
`test_hooks_config.py` resolves `plugin/hooks/hooks.json` via
`parents[2]`) and `plugin_work` (mutated during seeding, reverted from
`plugin_pristine` after every defect).

**Arm A** is the already-measured 13/15 result from
[[RESEARCH-test-quality-empirical]], restated here, not re-run.

**Arm B**, discard-and-replace on the identical three modules:
1. Wrote three new test files (`test_capturelib.py`, `test_lessonslib.py`,
   `test_sync.py`) from PLAN-006-learning-loop's TASK-036, TASK-039,
   TASK-040 and TASK-047 task specs and automated-verification bullets,
   under `test-design/SKILL.md`'s bar (docstring-first defect naming,
   boundary-and-fixture rule, equivalence classes before edges).
2. Resolved import/signature mismatches and thin-spec gaps by reading
   the modules directly - substantially more than a minimal signature
   peek; see Validity caveats.
3. Installed the three files into `plugin_work/cli/tests/`, replacing
   the originals. Every other test file (`test_capture_commands.py`,
   `test_maincli.py`, and 15 others) was left untouched in both the
   pristine and working trees - these are common background across both
   arms; see Scope decision below.
4. `python compass test-smells tests/test_capturelib.py
   tests/test_lessonslib.py tests/test_sync.py` - 0 findings (0 gate, 0
   advisory), PASS.
5. Full suite green on the unmodified swap: `python -m unittest discover
   -s tests` - 446 tests, OK (478 pristine total, minus 109 Arm A tests
   in the three replaced files, plus 77 Arm B tests).
6. Replayed the identical 15 defects one at a time against
   `plugin_work`, from the exact specifications in
   [[RESEARCH-test-quality-empirical]]'s seeded-defect table, each
   applied as a single source edit, full suite run
   (`python -m unittest discover -s tests`), verdict recorded, then
   reverted to the pristine file before the next defect. Final
   `diff -q` of all three source files against `plugin_pristine`
   confirmed a clean revert, and a closing full-suite run confirmed 446
   tests, OK.

**Scope decision.** "The same three modules" is read as the three test
files (`test_capturelib.py`, `test_lessonslib.py`, `test_sync.py`), not
`test_capture_commands.py` or any other file. Every non-swapped test
file is identical in both arms and runs unchanged in the full-suite
replay for both - background tests cannot bias the paired comparison
because they contribute the same catches (if any) to both arms. Only
the three swapped files can change a defect's verdict between arms. No
fresh, non-comparable probe against PLAN-007's own new modules was run
(explicitly optional in the task text; skipped for time).

## The paired result

| ID | Module | Defect | Arm A | Arm B | Moved? |
|---|---|---|---|---|---|
| C1 | capturelib.py | `due()`: `turns < interval` -> `<=` | CAUGHT (6) | CAUGHT | no |
| C2 | capturelib.py | `due()`: dropped zero-signals-not-due guard | CAUGHT (1) | CAUGHT | no |
| C3 | capturelib.py | `record_signal()`: dropped `MAX_SIGNALS` slice | CAUGHT (1) | CAUGHT | no |
| C4 | capturelib.py | `open_opportunity()`: dropped `signals = []` reset | CAUGHT (2) | CAUGHT | no |
| C5 | capturelib.py | `close_opportunity()`: `== "abandoned"` -> `!=` | CAUGHT (3) | CAUGHT | no |
| L1 | lessonslib.py | `rank()`: archived filter `==` -> `!=` | CAUGHT (20) | CAUGHT | no |
| L2 | lessonslib.py | `rank()`: escalated-first sort key flipped | CAUGHT (2) | CAUGHT | no |
| L3 | lessonslib.py | `_parse_tags()`: bracket check `and` -> `or` | **HOLE (0)** | **CAUGHT** | **yes** |
| L4 | lessonslib.py | `_finalize()`: dropped try/except around `int(score)` | CAUGHT (1) | CAUGHT | no |
| L5 | lessonslib.py | `parse_catalog()`: row_number incremented every line | CAUGHT (3) | CAUGHT | no |
| S1 | commands/sync.py | `_prune_capture_log()`: `at < cutoff` -> `>` | CAUGHT (3) | CAUGHT | no |
| S2 | commands/sync.py | `_check_caps()`: `lesson_count > CAP` -> `>=` | **HOLE (0)** | **CAUGHT** | **yes** |
| S3 | commands/sync.py | `_sync_index()`: dropped archived-record skip | CAUGHT (2) | CAUGHT | no |
| S4 | commands/sync.py | `_catalog_row()`: dropped `escalated` field write | CAUGHT (1) | CAUGHT | no |
| S5 | commands/sync.py | `_clean_logs()`: dropped `deleted += 1` | CAUGHT (2) | CAUGHT | no |

**Kill rates, as fractions:** Arm A 13/15. Arm B 15/15. Paired movement:
2 of 15 defects moved, both HOLE -> CAUGHT, both predicted in advance
by [[RESEARCH-test-quality-empirical]] finding 9. Zero defects moved
CAUGHT -> HOLE.

Each Arm B verdict is a direct `python -m unittest discover -s tests`
run against the seeded `plugin_work` tree, with the failing test name(s)
observed in the output before revert (not re-tabulated per-defect here;
representative excerpts below).

- C1: `AssertionError: False is not true` - the exact-boundary
  `test_at_interval_with_one_signal_is_due` failed (4 failures, 1 error
  total across the suite).
- L3: `AssertionError: ['a', ''] is not None` -
  `test_opening_bracket_only_is_rejected` failed - this is Arm A's
  documented hole, now caught by the boundary-and-fixture asymmetric-
  malformation test.
- S2: `AssertionError: 'lessons-catalog.yaml' unexpectedly found in
  [...]` - `test_lesson_count_exactly_at_cap_does_not_warn` failed -
  Arm A's other documented hole, now caught by the exact-boundary cap
  test.
- C5: `AssertionError: 0 != 1` on `test_fired_outcome_logs_a_fired_event_not_closed`
  - caught only by a test added after the initial draft; see caveat
  below.

## Test counts (an outcome, reported without judgment, per plan text)

| File | Arm A (pre-bar) | Arm B (bar-authored) |
|---|---|---|
| test_capturelib.py | 32 | 27 |
| test_lessonslib.py | 39 | 26 |
| test_sync.py | 38 | 24 |
| **Total** | **109** | **77** |

Arm B is smaller and caught two more defects. This is consistent with
D-01's premise that admission-bar discipline is not the same axis as
suite size, and with the plan's explicit instruction not to read size
as a judgment in either direction.

## Validity caveats

1. **Authorship caveat (stated in the task, restated here up front).**
   Arm A's tests were written by builders and orchestrators, not by a
   tester operating under any admission bar - this is established fact,
   not conjecture (PLAN-007 Risks: "The Arm A suite was written by
   builders and orchestrators, not by testers operating under any
   bar"). Arm B therefore compares "tests written under the bar"
   against "tests written with no tester station at all," which is
   real and useful but is not "bar versus no bar" with every other
   variable held equal.

2. **Non-blinded authorship - the more consequential caveat, not
   explicitly named in the task text.** The same agent that read
   [[RESEARCH-test-quality-empirical]]'s full seeded-defect table
   (required, to replay the defects faithfully) also authored Arm B's
   tests. Knowledge of L3 and S2's exact nature - an asymmetric bracket
   check and an exact-boundary cap comparison - existed *before* a
   single Arm B test was written. The boundary-and-fixture rule's
   asymmetric-malformation and exact-boundary clauses were applied
   mechanically to every bounded/formatted value found in the specs
   (the `due()` interval, the signal cap, the lesson-count cap, the
   bracket parse), not selectively aimed at L3/S2 alone - but a
   genuinely blind author (one who had not read the defect table)
   might have applied the rule less exhaustively, or missed one of
   these two specific spots. This experiment cannot distinguish "the
   bar organically surfaces this defect class" from "the author knew
   where to look." A future run with a second, unbriefed agent
   authoring Arm B from the specs alone (never shown the defect table)
   would isolate the effect this run cannot.

3. **Post-hoc test addition.** While verifying my own draft against
   TASK-039's "a full lifecycle produces the expected row sequence"
   bullet, I found `OpportunityLifecycleLogTests` had been omitted
   from the initial draft - the only test class capable of catching C5,
   since `close_opportunity`'s outcome-to-event-label inversion affects
   only the `capture-log.jsonl` trace row, not the `opportunity.json`
   record my other `close_opportunity` tests check. I added the two
   tests before running the replay, and only then confirmed they catch
   C5. This is a spec-derived addition (the bullet was already in my
   required reading), not one aimed at C5 specifically, but the order
   of operations - noticing a gap, then confirming it closes a known
   defect - is itself informed by defect-table knowledge under caveat 2.

4. **Signature peeks went well beyond "signatures only."** The task
   authorized resolving import/signature mismatches by reading
   signatures; in practice I read full docstrings and, for several
   functions, full bodies, before or while finalizing Arm B: `due()`,
   `record_signal()`, `open_opportunity()`, `close_opportunity()`
   (capturelib.py); `_parse_tags()`, `_finalize()`, `parse_catalog()`,
   `rank()` (lessonslib.py); `_check_caps()`, `_prune_capture_log()`,
   `_clean_logs()`, `sync()`, `run()`, `_record_write_signal()`,
   `_sync_index()`, `_catalog_row()` (commands/sync.py). This was
   necessary to write tests that import and run correctly against real
   interfaces with no live implementation to iterate against
   interactively, but it is a materially larger exposure than the
   pre-build tester protocol PLAN-007 describes ("no implementation in
   existence to be misguided by"). Treat Arm B as closer to "tests
   written with the bar and full implementation visibility" than to a
   faithful simulation of the pre-build station.

5. **Reconstruction caveats.** None required - every defect
   specification in [[RESEARCH-test-quality-empirical]]'s table named
   an exact source line and operator change, and each was located and
   applied verbatim (confirmed by reading the pristine source before
   seeding each one).

## Thin-spec findings

Per PLAN-007's instruction, a depressed or inflated arm caused by thin
specs is a measurement of the specs, not of the bar. Recorded, not
papered over:

- **`sync._check_caps` has no PLAN-006 task-spec coverage at all.**
  Neither TASK-039 nor TASK-040's text mentions cap-checking. The
  `LESSON_COUNT_CAP = 50` constant (S2's target) traces instead to
  **PLAN-001** TASK-011's hard-cap-detection spec ("Same check for
  `lessons/` directory file count (50 files); warning written to
  `lessons-catalog.yaml`"), predating PLAN-006 and describing an
  earlier `index-sync` skill later folded into `compass sync`. The
  Arm B tests for `_check_caps` (including the S2-catching boundary
  test) are derived from this cross-plan spec plus the function's own
  constants, not from the assigned PLAN-006 reading set.
- **`sync._sync_index`'s archived-record skip (S3's target) is not
  described in TASK-039 or TASK-040.** No spec document found states
  that an archived record must be excluded from indexing; the Arm B
  test for this (`SyncIndexArchivedSkipTests`) is derived from the
  function's own docstring and body.
- **`sync._catalog_row`'s escalated-field write (S4's target) is not
  described in TASK-039 or TASK-040 either.** TASK-047 documents that
  `lessonslib.rank()` reads an `escalated` field, but no PLAN-006 task
  documents that `sync` is the writer of that field or its exact
  syntax. The Arm B test is derived from the function's own body.
- **TASK-036's "counter increments and resets" bullet does not name
  which function performs the reset.** Inferred (and confirmed by
  reading `open_opportunity`) that the reset happens there, not in a
  dedicated function - `open_opportunity`'s docstring states it
  "clears `turns_since_capture` and `signals`."

None of these gaps suppressed a defect catch in Arm B - all three
(_check_caps/S2, _sync_index/S3, _catalog_row/S4) were caught - but
each required reading beyond the assigned PLAN-006 spec set to test at
all, which is itself a finding about PLAN-006's spec coverage of
pre-existing `sync.py` behavior it modified but did not fully
re-document.

## Design takeaways for Compass

- The two defects predicted to move (L3, S2) did move, in the
  predicted direction, using tests derived mechanically from the
  `test-design` skill's boundary-and-fixture rule applied to the exact
  values the specs describe as bounded or formatted (an interval, a
  cap, a bracketed list). This is consistent with
  [[RESEARCH-test-quality-empirical]] finding 9's claim that D-01 alone
  would not have caught either hole, and that boundary-value and
  malformed-input enumeration is the complementary check needed - the
  bar's second rule, not the first, is what closed both holes here.
- The clean 15/15 should not be read as proof the bar guarantees
  catching every boundary defect a spec implies; it is one paired run,
  on three modules, by a non-blinded author (caveat 2), with several
  functions read in more depth than the pre-build station's contract
  allows (caveat 4). It is evidence the mechanism works when applied
  as designed, not a measured hit rate.
- Arm B costing 77 tests to Arm A's 109 while catching two more
  defects is the concrete instance PLAN-007's "size is an outcome, not
  a target" instruction anticipates: a smaller, bar-authored suite
  outperformed a larger, undirected one on this seeded-defect measure.
  One paired run is not a general claim that bar-authored suites are
  always smaller or always better; it is what this run measured.

## Gaps

- No second, blinded author ran an independent Arm B from the same
  specs without having read the defect table - see caveat 2. This is
  the single most useful follow-up to strengthen this result.
- The optional standalone fresh probe against PLAN-007's own new
  modules (test_test_checkpoint.py, testsmellslib.py) was not run;
  explicitly optional in the task text and skipped for time.
- Whether the same 2-defect improvement would replicate on a fourth
  module not in this experiment is untested; the result is specific to
  `capturelib.py`, `lessonslib.py`, and `commands/sync.py`.
