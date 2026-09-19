# Extraction log - 2026-08-12

## Opportunity OPP-20260812T000302020845Z (interval) - 2026-08-12T00:03:02Z

### Triggers
- fix-loop >=2: no
- validator Deviation (problem): no
- debug invoked: no
- STOP-and-report: no
- plan revised: no
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (subagent-finished, vault-write)

### Candidates

1. **Source:** `plans/PLAN-008-rolling-wave.md:285` (Wave 2 elaborated) and `:157` (Wave 3 preamble), recording the TASK-072 prose review that corrected six factual claims against the wave-1 code
   **Finding:** Prose documenting freshly landed code must be verified claim-by-claim against the code, not against the plan task block that commissioned it.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" - twice. The global CLAUDE.md "No Assumptions" rule states the remedy directly ("if you're unsure how something works in this project, read the code first"), and this window's own evidence for the finding *is* the plan's record sections, which now document the episode and its consequences. Also not an independent recurrence: the reviewer capture behind it, `tmp/subagent-captures/2026-08-11T22-50-43_reviewer.md`, sits in the previous window and was weighed and rejected on the same CLAUDE.md ground at OPP-20260811T225127269851Z. This window contains no reviewer capture of its own, and the wave-3 commits (TASK-073/074/075) record no accuracy-drift corrections - only TASK-072's does.
   **Outcome:** rejected

2. **Source:** `plans/PLAN-008-rolling-wave.md:186` (TASK-076 manual verification) and commit 4bd95bd
   **Finding:** The rolling-wave loop cost one approval, two read-only deltas and zero mid-build amendments across three waves, meeting SPEC-015's success criterion 3.
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan, vision, or CLAUDE.md" - the measurement is TASK-076's own acceptance criterion, the number is the plan's closing record, and the criterion it answers is SPEC-015's. An outcome the plan was built to measure belongs to the plan.
   **Outcome:** rejected

3. **Source:** commit 01a0542, `tmp/subagent-captures/2026-08-11T23-02-53_unknown.md` ("distribute to all vaults and push")
   **Finding:** v0.7.0 reached 48 vaults.
   **Anti-list:** matched bucket "Ephemeral session state" - a distribution count is the state of the fleet on one day, carrying no rule.
   **Outcome:** rejected

### Contradiction check
Catalog rows overlapping the window's planning, review, workflow and methodology tags were read: `LESSON-adversarial-plan-review-before-build`, `LESSON-dont-strip-agent-quality-stations`, `LESSON-wikilink-validator-skip-code`, `LESSON-human-practice-rationing-assumes-human-scarcity`, `LESSON-no-agent-bookkeeping`. Nothing in the window falsifies an active lesson - the plan closed doing what its lessons predicted. No score bump either: `LESSON-dont-strip-agent-quality-stations` names the failure of *stripping* a review station, and every station here ran; a lesson bumps on recurrence of the failure it names, not on its absence. No revise or archive payload prepared.

### Notes
The fourteen 129-byte `tmp/subagent-captures/` files in the window are one-line human nudges ("continue", "distribute to all vaults and push") with no finding content. `lessons/LESSON-wikilink-validator-skip-code.md` in the evidence list is the previous pass's own write. No phase-report directory exists for waves 2 or 3; `tmp/phase-reports/` holds only `PLAN-008-wave-1` and `test-phase-001`.

### Summary
Candidates: 3 | Written: 0 | Rejected: 3 | Errors: 0
