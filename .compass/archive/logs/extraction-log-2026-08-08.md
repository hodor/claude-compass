# Extraction log 2026-08-08

## Opportunity OPP-20260808T004030357648Z (interval) - 2026-08-08T00:45Z

### Triggers
- interval reached with signal(s): yes (vault-write, subagent-finished; window spans PLAN-007 draft, 3-lens review, amendment pass, payload capture)

### Candidates
1. **Source:** two payload-shape incidents (TeammateIdle empty shells; SubagentStop empty agent_type shipped fleet-wide as dead code)
   **Finding:** hook code keyed on assumed payload fields ships silently dead; observe one real payload first
   **Anti-list:** passed (two instances, silent failure class, one-line prevention, generalizes beyond Compass)
   **Outcome:** `lesson-write` returned `created: LESSON-hook-payloads-observe-before-coding.md`

2. **Source:** SPEC-011 rescope + PLAN-007 review outcomes (5 blocking mechanism bugs found pre-build; measured calibration retired 2 tasks)
   **Finding:** multi-lens adversarial review before approval, with reviewers measuring against the real corpus
   **Anti-list:** passed (two instances, not documented as practice anywhere, changes how the next spec/plan is handled)
   **Outcome:** `lesson-write` returned `created: LESSON-adversarial-plan-review-before-build.md`

3. **Source:** TASK-057's fitted ground truth (check designed from the 3 positives it is then asserted to find)
   **Anti-list:** matched bucket "Anything already documented..." (the amended plan text now carries the regression-pin framing and the unfitting probe)
   **Outcome:** rejected

### Summary
Candidates: 3 | Written: 2 | Rejected: 1 | Errors: 0

## Opportunity OPP-20260808T011534384816Z (interval) - 2026-08-08T01:20Z

### Triggers
- interval reached with signal(s): yes (vault-write, subagent-finished; window spans Phase A build TASK-052..056, census, active/index trim)

### Candidates
1. **Source:** TASK-065 negative census (the 841 project unfindable across 39 vaults)
   **Finding:** a spec's motivating observation must be pinned to its source at capture time
   **Anti-list:** passed (real incident, cheap prevention, generalizes to every future spec)
   **Outcome:** `lesson-write` returned `created: LESSON-pin-the-motivating-datum.md`

2. **Source:** consolidate declining while the hot path sat 60% over its token cap
   **Finding:** the token cap has no owning reduction mechanism (consolidate triggers on different caps)
   **Anti-list:** matched bucket "Anything already documented..." after recording it as the design-decision backlog item it actually is (a Compass defect to fix, not a portable rule)
   **Outcome:** rejected as lesson; backlog item added

3. **Source:** Phase A per-task briefs carrying committed predecessors' real CLI shapes forward
   **Anti-list:** matched bucket "Things obvious once you know the technology" (ordinary orchestration practice)
   **Outcome:** rejected

### Summary
Candidates: 3 | Written: 1 | Rejected: 2 | Errors: 0

## Opportunity OPP-20260808T021611062608Z (interval) - 2026-08-08T02:20Z

### Triggers
- interval reached with signal(s): yes (vault-write, subagent-finished; window spans Phase B build + gate ruling + TASK-062)

### Candidates
1. **Source:** build-047 and build-057 both violating the no-sub-agents brief to run their review station, both catching real defects (057: 7 bugs pre-delivery)
   **Finding:** spawn briefs must not strip an agent definition's own quality stations; scope restrictions to uninstructed fan-out
   **Anti-list:** passed (two instances, validated by outcomes, orchestrator behavior already corrected mid-stream)
   **Outcome:** `lesson-write` returned `created: LESSON-dont-strip-agent-quality-stations.md`

2. **Source:** the unfitting probe on TASK-057's fitted ground truth
   **Anti-list:** dedup - [[LESSON-adversarial-plan-review-before-build]] already carries the unfitting rule in its body
   **Outcome:** rejected (recurrence-adjacent, not new)

3. **Source:** Assertion Roulette threshold choice (8 vs 3 for report scannability)
   **Anti-list:** matched bucket "Code patterns... readable from the codebase" (documented at the constant)
   **Outcome:** rejected

### Summary
Candidates: 3 | Written: 1 | Rejected: 2 | Errors: 0

## Opportunity OPP-20260808T204736352710Z (interval) - 2026-08-08T20:47Z

### Triggers
- interval reached with signal(s): yes (vault-write, subagent-finished; window spans v0.6.3 ship + issues #2/#3, the defold 44-test review, v0.6.4's generic bar fix, RESEARCH-test-quality-bar-validation, PLAN-007 close-out)

### Candidates
1. **Source:** [[RESEARCH-test-quality-bar-validation]] caveat 2 (non-blinded authorship)
   **Finding:** the agent that read the seeded-defect table to replay it also authored the arm under test, so 15/15 measures the author's knowledge, not the bar
   **Anti-list:** passed (named in the research as the consequential caveat and absent from the task text; no spec/ADR/plan/CLAUDE.md carries the role-split rule)
   **Outcome:** `lesson-write` returned `created: LESSON-blind-the-author-in-self-validation.md`

2. **Source:** defold 44-test review (2 behaviors, 44 tests, helper deletable with a green suite, production input type never exercised), corroborated by the 77-vs-109 paired counts
   **Finding:** bloat and critical holes coexist; a high test-per-behavior ratio predicts holes rather than ruling them out, so a delete list is half a review
   **Anti-list:** passed (the v0.6.4 skill sections are authoring rules; this is the review-time inference, documented nowhere)
   **Outcome:** `lesson-write` returned `created: LESSON-suite-size-is-not-coverage.md`

3. **Source:** v0.6.4 test-design additions ("Cases are rows, not tests"; "Test the public contract")
   **Anti-list:** matched bucket "Anything already documented..." - shipped verbatim as standing guidance in `plugin/skills/test-design/SKILL.md`
   **Outcome:** rejected

4. **Source:** [[RESEARCH-test-quality-bar-validation]] thin-spec findings (`_check_caps`, `_sync_index`, `_catalog_row` untraceable to PLAN-006 task text)
   **Anti-list:** matched bucket "Unresolved or untested approaches" - the research records that no gap suppressed a catch, so the re-document-what-you-modify rule has no demonstrated consequence behind it
   **Outcome:** rejected

5. **Source:** v0.6.3 capture-check O_EXCL run lock (issue #2 read-decide-write race)
   **Anti-list:** matched bucket "Debugging recipes whose fix is in the code" - the commit message carries it
   **Outcome:** rejected

6. **Source:** v0.6.3 abandon grace period (a re-emit budget used as a time proxy abandoned a live pass at 38s; close now supersedes abandon)
   **Anti-list:** matched bucket "Debugging recipes whose fix is in the code"
   **Outcome:** rejected

### Contradiction check (4a)
No revise, no archive. Checked the catalog for testing/measurement/methodology overlap: [[LESSON-test-driven-tasks-dont-discriminate]] is the only test-adjacent lesson and this window confirms it - its "absent test suite forcing the agent to surface edge cases" discriminating condition is exactly what the paired arms exercised. [[LESSON-adversarial-plan-review-before-build]] and [[LESSON-dont-strip-agent-quality-stations]] are both reinforced by the defold reviewer catching real holes. Nothing falsified or narrowed.

### Summary
Candidates: 6 | Written: 2 | Rejected: 4 | Errors: 0

## Opportunity OPP-20260808T233838405732Z (signal) - 2026-08-08T23:45Z

### Triggers
- debug-finished (signal): yes (2026-08-08T23-28-35_debug.md)
- subagent-finished (signal): yes (tester + reviewer captures, 23-29-56 / 23-30-29)
- vault-write (signal): yes (two lessons from the prior pass, extraction log)
- window: v0.6.5 fixing three field-reported CLI bugs (catalog empty-marker corruption, sync crash on missing index.md, loose-nested wikilink form mismatch), reviewed by debug + tester + 3-lens reviewer before ship

### Candidates
1. **Source:** tester capture (revert experiment: 16 of 23 new tests fail on a reverted fix, 7 pass both), corroborated by the reviewer's vacuous-test rows
   **Finding:** two regression tests pinned to the reported repros passed on the buggy code - one borrowed the tolerant production reader as its oracle, one pinned the reporter's literal repro, which never reproduced
   **Anti-list:** passed (no revert/discrimination check in test-design, tester.md, build, validate, or any plan; red-green does not cover post-hoc regression tests written after the fix)
   **Outcome:** `lesson-write` returned `created: LESSON-revert-to-prove-a-regression-test.md`

2. **Source:** debug + reviewer capture, `sync.py:214-223` legacy rewrite
   **Finding:** the heal's in-place replace matched nothing for alias/anchor link forms, yet `indexed_paths.add` and `rewrites += 1` fired anyway, so the record was marked indexed, never re-appended, and the breakage became permanent
   **Anti-list:** passed as a rule (the specific match fix is in the code and the commit; "record success from the observed change" is not)
   **Outcome:** `lesson-write` returned `refined: LESSON-append-only-index-misses-mutations.md`

3. **Source:** issue #1 root cause - sync emitted bare stems for loose nested docs while validate resolved path-qualified
   **Anti-list:** matched bucket "Things obvious once you know the technology" - round-tripping a producer's output through its consumer is standard contract testing, and the vault already had exactly that test; what it lacked was discrimination, which candidate 1 covers
   **Outcome:** rejected

4. **Source:** debug capture, `_sync_index` returns only `added` so a rewrite-only run reports nothing
   **Anti-list:** matched bucket "Code patterns... readable from the codebase"
   **Outcome:** rejected

5. **Source:** debug + reviewer capture, `LESSONS_EMPTY_MARKER` `\s*$` greedy under MULTILINE
   **Anti-list:** matched bucket "Things obvious once you know the technology" (regex MULTILINE semantics)
   **Outcome:** rejected

### Contradiction check (4a)
No revise, no archive. Checked catalog rows overlapping sync/derived-index/staleness and hooks/integration: [[LESSON-append-only-index-misses-mutations]]'s claim holds and gained a subtler condition (candidate 2, ordinary refinement, not a correction). [[LESSON-hook-payloads-observe-before-coding]] is untouched - the link-form mismatch is two writers reading one prose convention differently, not logic keyed on an unobserved payload. [[LESSON-suite-size-is-not-coverage]] is reinforced: 23 tests, 2 vacuous, holes named in the coverage list.

### Summary
Candidates: 5 | Written: 2 | Rejected: 3 | Errors: 0
