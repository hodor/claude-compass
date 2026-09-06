# Extraction log 2026-08-06

## Opportunity OPP-20260806T060218436787Z (signal) - 2026-08-06T06:10Z

### Triggers
- validator-finished / debug-finished (signal): no
- handoff-written (signal): yes (handoffs/PLAN-006-learning-loop/2026-08-06_06-02-00_phase2-live-hooks-first-firing.md)
- interval reached with signal(s): no (strong signal fired below interval; vault-write also in window)

### Candidates
1. **Source:** handoff Learnings - hooks-never-loaded discovery
   **Finding:** Claude Code loads hooks only from settings files or registered plugins; a bare .claude/hooks/hooks.json is inert and fails silently
   **Anti-list:** passed (not framework usage docs: an install trap that cost 5 months x 40 vaults; the plan documents this project's fix, the lesson is the general rule)
   **Outcome:** `lesson-write` returned `created: LESSON-hooks-load-only-from-settings.md`

2. **Source:** handoff Learnings - orchestration delivery quirk, ~6 occurrences this session
   **Finding:** a spawned agent's final plain text never reaches the orchestrator; only SendMessage delivers, so briefs must mandate it
   **Anti-list:** passed (repeatable, cross-project, verified fix embedded in every later brief this session)
   **Outcome:** `lesson-write` returned `created: LESSON-subagent-reports-need-sendmessage.md`

3. **Source:** contradiction check (4a) - documented settings hook schema vs LESSON-hook-if-clause-no-or
   **Finding:** settings hook entries carry no `if` clause at all; the lesson's rule presupposed one and its original in-repo verification predates the discovery that hooks never fired here
   **Anti-list:** n/a (contradiction-revise path)
   **Outcome:** `revised: LESSON-hook-if-clause-no-or.md` (matcher advice kept; claim corrected to the documented schema; catalog row and index line updated per lesson-write 4b)

4. **Source:** handoff Learnings - SubagentStop not firing for teammate-style agents
   **Finding:** teammate-style agents did not emit SubagentStop despite docs; TeammateIdle registered as workaround
   **Anti-list:** matched bucket "Unresolved or untested approaches" (single observation contradicting docs; TeammateIdle payload unverified - handoff action item 2 owns the follow-up)
   **Outcome:** rejected

5. **Source:** hooks-guide research - settings hooks reload live without restart
   **Anti-list:** matched bucket "Standard patterns from framework or library official docs" (verified core survives as one body line of candidate 1's lesson)
   **Outcome:** rejected

### Summary
Candidates: 5 | Written: 3 | Rejected: 2 | Errors: 0

## Opportunity OPP-20260806T064658971891Z (interval) - 2026-08-06T06:48Z

### Triggers
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (vault-write, subagent-finished)

### Candidates
1. **Source:** the Phase 3-4 build window (escalated-flag gap + revised-summary staleness, two instances)
   **Finding:** append-only derived indexes never reflect source mutations; the mutating writer must own the row update
   **Anti-list:** passed (design rule not documented anywhere as a rule; two independent same-day instances)
   **Outcome:** `lesson-write` returned `created: LESSON-append-only-index-misses-mutations.md`

2. **Source:** TeammateIdle payload discovery
   **Finding:** TeammateIdle carries teammate_name only
   **Anti-list:** matched bucket "Code patterns... readable from the codebase" (encoded in capture_signal.py + manifest description)
   **Outcome:** rejected

3. **Source:** build-047 protocol slips (vault edits, review sub-agent despite brief)
   **Finding:** spawn briefs get partially overridden by agent-definition protocol
   **Anti-list:** matched bucket "Unresolved or untested approaches" (single instance, no validated fix)
   **Outcome:** rejected

4. **Source:** top-N backfill noise in compass lessons
   **Finding:** ranked top-N needs a relevance floor when criteria exist
   **Anti-list:** matched bucket "Code patterns... readable from the codebase" (lessonslib docstring documents it)
   **Outcome:** rejected

### Summary
Candidates: 4 | Written: 1 | Rejected: 3 | Errors: 0

## Opportunity OPP-20260806T154837847390Z (interval) - 2026-08-06T15:55Z

### Triggers
- validator-finished / debug-finished (signal): no
- handoff-written (signal): no
- interval reached with signal(s): yes (vault-write, subagent-finished; turn 12 supplied by a validator probe, signals genuine)

### Candidates
1. **Source:** validator probe incident (read-only validation mutated real capture state)
   **Finding:** CLAUDE_PROJECT_DIR redirection requires the target to contain .compass; empty scratch dirs silently fall back to the enclosing vault
   **Anti-list:** passed (silent failure, real incident, generalizes to fleet hooks in nested dirs; the operational isolation rule is not readable from the flag name)
   **Outcome:** `lesson-write` returned `created: LESSON-scratch-vaults-need-compass-dir.md`

2. **Source:** validation report - TASK-038 plan self-contradiction (mutex wording vs re-emit design)
   **Anti-list:** matched bucket "Ephemeral session state" (a plan-text inconsistency, resolved by reading the plan's own design section; nothing to carry forward)
   **Outcome:** rejected

3. **Source:** Phase 5 build window (lesson-coverage, validator step, docs)
   **Anti-list:** matched bucket "Anything already documented in a spec, ADR, plan..." (the shipped skills document the mechanism)
   **Outcome:** rejected

### Summary
Candidates: 3 | Written: 1 | Rejected: 2 | Errors: 0
