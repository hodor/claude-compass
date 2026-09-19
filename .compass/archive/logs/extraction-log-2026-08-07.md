# Extraction log 2026-08-07

## Opportunity OPP-20260807T230327876853Z (interval) - 2026-08-07T23:05Z

### Triggers
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (vault-write, subagent-finished; window spans SPEC-013 + 3 research docs)

### Candidates
1. **Source:** tooling vs empirical axis divergence (63.6% mutation kill vs 86.7% seeded-defect vs 100% grading on the same tests)
   **Finding:** different test-quality instruments give divergent verdicts on the same suite
   **Anti-list:** matched bucket "Unresolved or untested approaches" (the reviewer is reconciling this right now; recording an interpretation mid-flight would freeze a guess)
   **Outcome:** rejected

2. **Source:** RESEARCH-test-quality-tooling (mutmut refuses native Windows, WSL-only)
   **Finding:** mutation tooling constraint for the fleet
   **Anti-list:** matched bucket "Anything already documented..." (research doc is the canonical home; the SPEC-013 plan will consume it directly)
   **Outcome:** rejected

3. **Source:** empirical axis contradicting the spec's bloat narrative for this repo
   **Finding:** count-based bloat claims need quality measurement first
   **Anti-list:** matched bucket "Anything already documented..." (this IS SPEC-013's own D-01, recorded two days ago)
   **Outcome:** rejected

### Summary
Candidates: 3 | Written: 0 | Rejected: 3 | Errors: 0
