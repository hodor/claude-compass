---
title: Active Tasks
updated: 2026-05-24
---

# Active Tasks

## Done (through 2026-07-24, details in the named plans)

- [x] [[PLAN-001-lessons-and-index-implementation]] - all 12 tasks (2026-05-24)
- [x] [[PLAN-002-compass-cli-implementation]] - CLI + command-hook cutover, ~99.8% bookkeeping-token reduction (2026-06-14); deferred optional: live two-session A/B for the per-fire token floor
- [x] SPEC-007/008/010 batch via [[PLAN-003-hybrid-hierarchy]], [[PLAN-004-decision-coverage]], [[PLAN-005-model-table]] - 23/23 tasks, validator BATCH PASS (2026-07-24); [[SPEC-009-configurable-pipeline-workflows]] deferred to [[backlog]]

## In Progress (stale, pre-pipeline era)

- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12 ([[2026-03-12_23-50-59_session-3-skills-approved]]); largely superseded by the per-file reviews every subsequent plan performed

## Blocked

_None._

## Done: Learning-loop initiative (Roger, 2026-07-25/26) - SHIPPED as v0.5.0

[[SPEC-012-learning-loop]] specced, planned ([[PLAN-006-learning-loop]], 16 tasks), built, VALIDATED (PASS, 9/9 adversarial probes), and distributed fleet-wide 2026-08-05/06. Root-cause discovery en route: hooks load ONLY from settings files, never bare hooks.json ([[LESSON-hooks-load-only-from-settings]]) - so no Compass hook had ever fired anywhere before 2026-08-06. All 42 vaults now doctor-clean at v0.5.0 with registered hooks; capture/retrieval/audit live everywhere; multiple organic capture firings same-day at benchmark quality. Details in the plan, the validation record, and [[2026-08-06_06-02-00_phase2-live-hooks-first-firing]].

- [ ] NEXT: SPEC-011 pipeline (research/ADR on substrate, planner), then SPEC-006 hosts (hermes first). Watch capture-stats across the fleet - SPEC-012's falsification test is running everywhere.

## Rolling-wave initiative (Roger, 2026-08-11): SPEC-015 -> ADR-009 -> PLAN-008

- [x] [[SPEC-015-rolling-wave-planning]] approved with D-02..D-04; 4 research docs; [[ADR-009-rolling-wave-mechanism]] D-01..D-07; [[PLAN-008-rolling-wave]] drafted in its own format, 3-lens reviewed (21 findings applied), APPROVED 2026-08-11.
- [x] Wave 1 COMPLETE + ELABORATED (2026-08-11): TASK-066..070 landed through the full station flow (checkpoints, --against-run verifies); gate after-image exact (6c/4s/0u pre-elaboration); prototype answered (prose cannot upgrade, but can manufacture - constraint recorded); three unittest -v formats pinned in the verifier en route. Elaboration 7d promoted wave 2 (071 planner brief, 072 plan skill, 077 template) with TASK-070s answer folded in; post-elaboration gate 9c/1s/0u.
- [x] PLAN-008 COMPLETE (2026-08-11): all 12 tasks across 3 waves + 2 live elaborations. Acceptance from the installed copy: suite green, doctor clean, coverage --strict 10c/0s/0u PASS, lesson-coverage PASS, all four regression pins PASS. Two elaboration laps ran with per-line changed-or-held records; knowledge demonstrably flowed (prototype answer -> planner brief; wave-2 review findings -> build-skill discipline). Human touchpoints: one approval + two read-only deltas, zero mid-build amendments.
- Later (intent): wave 2 authoring (071 planner brief, 072 plan skill, 077 obsidian template), wave 3 consuming (073 build 7d, 074 validator, 075 methodology) + 076 acceptance.

## Test-quality initiative (Roger, 2026-08-07): "only really good and meaningful tests"

- [x] [[SPEC-013-test-quality]] APPROVED (2026-08-07) with D-01..D-06; 5 research docs complete 2026-08-07/08 (literature, tooling, empirical, synthesis, craft-and-practice) - see index; the synthesis's station model and the craft doc's adopted procedures bind the plan.
- [x] [[PLAN-007-test-quality]] drafted, 3-lens reviewed (30 amendments incl. 5 blocking mechanism fixes applied), APPROVED as recommended 2026-08-08 (R1-R5). 14 tasks: Phase A 6 live, Phase B 3 gated on TASK-065 census, Phase C 2 PARKED behind named unpark triggers, Phase D 3.
- [x] PLAN-007 Phase A COMPLETE (2026-08-08): TASK-052 checkpoint CLI, 053 test-design skill, 054 tester two-station rewrite, 055 build-flow station, 056 builder halt + methodology. TASK-065 census closed UNIDENTIFIED (841 project not on this machine; rerunnable).
- [x] PLAN-007 COMPLETE (2026-08-08): 12/12 live tasks (Phase C stays parked behind its unpark triggers). Phase B: test-smells at measured severities, Roger ruled literal-only stays gate. Phase D: validator audit 4f; the paired experiment VALIDATED the bar - Arm B 15/15 vs Arm A 13/15 with 77 tests vs 109, both predicted holes flipped ([[RESEARCH-test-quality-bar-validation]]; blinded rerun recommended). Acceptance battery PASS: suite 478, doctor clean (28 commands), plan's own test files zero gate findings, coverage 6/6, lesson-coverage PASS.
- [x] FLEET DISTRIBUTION v0.6.0 -> v0.6.2 (2026-08-08): 45/45 vaults doctor-clean; per-project git commits of Compass-owned paths only; 27-28 pushed per wave. v0.6.1: capture pass in a spawned subagent, one summary line. v0.6.2: no-verbiage rule in every vault. Race + premature-abandon fixed in v0.6.3 (issues #2 #3 closed). Not pushed: 7 no-git projects, 2 no-remote, 1 all-paths-gitignored (iwyc-unreal), 4 push-rejected (3 ue5-editor-mcp checkouts + wt-spec056 behind their remotes - need a human pull/rebase decision; pg-jira-exporter's remote no longer exists).
- [x] FLEET DISTRIBUTION v0.7.0 (2026-08-11): rolling-wave planning live in 48/48 vaults, 30 repos pushed.
- [ ] NEXT: SubagentStop typed-signal fix ([[backlog]]), SPEC-014 approval + research (update-safe customizations, issue #6), SPEC-011 pipeline, SPEC-006 hosts, blinded rerun of the bar experiment.
- [ ] Fleet-wide SubagentStop typed-signal fix queued in [[backlog]] (payload evidence captured: agent_type empty string).
- [ ] After PLAN-006: SPEC-011 pipeline (research/ADR on substrate + planner), distribute v0.4.0 across repos (19/40 vaults lack the backstop), then SPEC-006 hosts (hermes first, then Kimi Code/Codex)

## Sizing + discoverability initiative (Roger, 2026-08-23)

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong. Diagnosis found the sizing shapes unreachable at the moment sizing is decided, and then a wider audit found seven CLI commands with no caller at all.

- [x] [[SPEC-016-sizing-work-beyond-one-spec]] APPROVED 2026-08-23, D-01..D-05. Both creation paths ship; Compass sizes and acts without asking; the notice is said once and silenceable; internal vocabulary never surfaced; configurable and callable.
- [x] [[SPEC-017-capabilities-are-reachable-and-measured]] APPROVED 2026-08-23, D-01..D-02. Adopt both hermes mechanisms (progressive-disclosure index + usage measurement). Audit evidence: `make-unit`, `unit-check`, `admit-check`, `touched`, `resolve-model` unreachable; `clean-tmp` and `tree` redundant with `sync`. Admission control from [[ADR-004-hierarchical-specs-with-facets]] has never run in any vault.
- [ ] NEXT: research both specs, then one ADR. SPEC-016's mechanism question (skill step vs hook vs CLI gate) and SPEC-017's index-location question are the open axes.
- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Next Up

### Next: integration testing of PLAN-001 output

- [ ] Install the Compass plugin into a real Claude Code session and verify the PostToolUse hook fires on `.compass/**/*.md` writes (and that `index-sync` is invokable from the prompt hook context)
- [ ] Verify hook `if` clause supports `||` boolean OR in permission rule syntax; if not, split into 3 hook entries (Write, Edit, MultiEdit)
- [ ] Verify prompt-type hooks can invoke Skills via the Skill tool; if not, switch hook `type` from `prompt` to `agent`
- [ ] Run `/compass:learned "test"` end-to-end against the local `.compass/` vault, audit the lesson file + catalog row + index entry
- [ ] Simulate a phase with `phase-summary.yaml` showing fix-loop >=2, run `extract-lessons` manually, audit output
- [ ] Hit the 200-line index cap deliberately, run `/compass:consolidate`, audit merge/prune decisions

### Other

- [x] Create ADR-001 + ADR-002 - methodology as skill + vault; retrospective lessons subsystem (2026-05-24)
- [ ] Test bootstrap agent on a fresh project
- [ ] Test spec-writer agent interactively
- [ ] Push to GitHub repository
