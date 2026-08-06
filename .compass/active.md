---
title: Active Tasks
updated: 2026-05-24
---

# Active Tasks

## Done

- [x] Finalize vision spec — resolve open questions in [[SPEC-001-compass-vision-and-architecture]]
- [x] Set up plugin structure — create agents and skills
- [x] TASK-001: Build `lesson-write` skill — `plugin/skills/lesson-write/SKILL.md` (2026-05-24)
- [x] TASK-002: Trim `lessons/SKILL.md` + update obsidian Lesson template — `plugin/skills/lessons/SKILL.md`, `plugin/skills/obsidian/SKILL.md` (2026-05-24)
- [x] TASK-003: Build `index-sync` skill — `plugin/skills/index-sync/SKILL.md` (2026-05-24)
- [x] TASK-004: PostToolUse hook + hook config location spike resolved (`plugin/hooks/hooks.json`) (2026-05-24)
- [x] TASK-005: Build `/compass:learned` slash command skill - `plugin/skills/learned/SKILL.md` (2026-05-24)
- [x] TASK-006: Build `extract-lessons` skill - `plugin/skills/extract-lessons/SKILL.md` (2026-05-24)
- [x] TASK-007: Modify `build/SKILL.md` step 6 to persist phase reports + invoke extract-lessons (2026-05-24)
- [x] TASK-008: Stop hook backstop for extract-lessons added to `plugin/hooks/hooks.json` (2026-05-24)
- [x] TASK-009: Removed lesson-creation language from `builder.md`, `validator.md`, `reviewer.md` (2026-05-24)
- [x] TASK-010: Removed per-agent index-update instructions from `builder.md`, `planner.md`, `researcher.md`, `reviewer.md` (2026-05-24)
- [x] TASK-011: Hard-cap detection added to `index-sync/SKILL.md` step 6 (2026-05-24)
- [x] TASK-012: Build `/compass:consolidate` command skill - `plugin/skills/consolidate/SKILL.md` (2026-05-24)
- [x] [[PLAN-001-lessons-and-index-implementation]] complete - all 12 tasks done (2026-05-24)

## In Progress

- [ ] TASK-001: Review and approve all plugin files (21 files) — human approves each file one by one
  - Progress: 3/21 files approved (all 3 skills done, agents next)
  - File 1: `plugin/skills/obsidian/SKILL.md` — APPROVED (session 2)
  - File 2: `plugin/skills/lessons/SKILL.md` — APPROVED (session 3)
    - Added `status` field to catalog schema + search filter
    - Replaced inline template with reference to obsidian skill
    - Search algorithm rewritten: AI judgment instead of mechanical tag matching
    - Added file naming convention (`LESSON-<descriptive-slug>.md`)
    - Added "When to Search" section
  - File 3: `plugin/skills/methodology/SKILL.md` — APPROVED (session 3)
    - No changes needed — handoff timestamp convention confirmed correct
  - Duplication audit: found heavy duplication across agents (templates inlined instead of referencing skills). Will dedup selectively during agent review — keep alignment-critical reminders inline, replace full template copies with references.
  - Files 4-21: not started (15 agents + 3 vault structure files)
  - Next file: agents (file 4 onward)
  - Handoff: [[2026-03-12_23-50-59_session-3-skills-approved]]

## Blocked

_None._

## Done: [[PLAN-002-compass-cli-implementation]] (all 12 tasks + deployment, 2026-06-14)

CLI built, command-hook cutover live, ~99.8% bookkeeping-token reduction confirmed ([[RESEARCH-cli-token-reduction-measurement]]). Details in the plan and [[2026-06-19_10-33-39_cli-shipped-spec005-on-hold]].

### Note for human

- bootstrap step 2b previously documented (but never actually installed - no settings.json exists in the dogfood) an old `SubagentStop` "run tester after builder" hook. The rewrite drops it; testing is handled by `/compass:build`'s fix loop now. Flag if you want that auto-tester hook back.

### Deferred (optional)

- [ ] Live two-session A/B to convert the per-fire token floor into an end-to-end measured number.

## Batch (approved 2026-07-23): SPEC-007 + SPEC-008 + SPEC-010 to built-and-validated

Pipeline state: COMPLETE AND VALIDATED (2026-07-24). Research -> ADR-006/007/008 -> PLAN-003/004/005 -> build -> validator BATCH PASS: 23/23 tasks, 13/13 automated checks, 6/6 adversarial probes, 242 tests green. Two non-blocking findings: audit-baseline framing (validator used the correct 7b5b5a8); unit-check SPEC-001 hub inflates one candidate (future heuristic). Manual checklist pending human review (validator report, this session). [[SPEC-009-configurable-pipeline-workflows]] deferred to [[backlog]].

### Done: [[PLAN-003-hybrid-hierarchy]] (all 9 tasks, 2026-07-24)

All 9 tasks done and validated: unit-aware CLI, make-unit migration, compass-cli unit live. Details in the plan; commits 4c44a05..fcbd291.

### Done: [[PLAN-004-decision-coverage]] (all 8 tasks, 2026-07-24)

All 8 tasks done and validated: three-outcome parser, decisions/coverage commands, planner gate, validator audit. Commits e48e55f..df4c3e4.

### Done: [[PLAN-005-model-table]] (all 6 tasks, 2026-07-24)

All 6 tasks done and validated: modelslib, resolve-model/models/apply-models, 13 templates normalized, dogfood proven. Commits 96ac14b, f0f9e99.

## Learning-loop initiative (Roger, 2026-07-25/26): "Compass is a framework that learns"

Evidence base complete: [[RESEARCH-lesson-capture-failure]] (capture fired organically ONCE across 40 vaults; root cause = coupled to /compass:build phase pauses real sessions never cross), [[RESEARCH-hermes-agent-capabilities]], [[RESEARCH-hermes-vs-compass-fit]], [[RESEARCH-graph-engineering-for-compass]].

- [x] RESEARCH done: [[RESEARCH-hermes-memory-mechanics]] (21 findings; counter-triggered harness-owned capture, judgment-filtered content, no-verification anti-pattern flagged) (2026-08-05)
- [x] [[SPEC-012-learning-loop]] drafted and APPROVED (2026-08-05): 3 pillars (capture-fix, retrieval, application audit), D-01..D-04 recorded incl. hermes-memory research binding (D-03) and SPEC-011 gate (D-04)
- [x] SPEC-011 D-02 experiment done ([[RESEARCH-grep-vs-graph-experiment]], 2026-08-05); narrowed (D-03), then 3-lens review (all AMEND) drove consumer-first rescope (D-04); APPROVED 2026-08-05. Experiment's ripple ground truth wrong both directions; erratum in the research doc. Lesson retrieval confirmed graph-free.
- [x] [[PLAN-006-learning-loop]] APPROVED 2026-08-05: 16 tasks, 5 phases, coverage gate PASS
- [x] PLAN-006 Phase 1 COMPLETE (2026-08-05): TASK-036..040, suite 326/326, sequential in main tree (plan's parallel note undersold shared-file contact points).
- [x] PLAN-006 Phase 2 COMPLETE (2026-08-06): TASK-041..044. Live firing observed and human-approved: handoff-written strong signal -> Stop-hook block -> extraction pass -> 2 lessons created, 1 revised via contradiction check, 2 anti-list rejections, capture-close traced (capture-stats: 1/1/1). Root-cause discovery en route: hooks load ONLY from settings files, never bare hooks.json - fixed via .claude/settings.json, recorded in [[LESSON-hooks-load-only-from-settings]].
- [x] PLAN-006 Phase 3 COMPLETE (2026-08-06): TASK-045 doctor (6 checks, hook-registration core, 21 tests) + TASK-046 (setup/update register hooks in settings.json via manifest translation, checkup delegates to doctor). TeammateIdle payload observed live (teammate_name only) and capture-signal taught its shape; TeammateIdle shipped in the manifest. Suite 364/364; doctor runs clean from the installed CLI.
- [x] PLAN-006 Phase 4 in progress: TASK-047 `lessonslib` + `compass lessons` done (2026-08-06) - strict catalog-row parser (fails loud naming the row number), rank by escalated-first / tag overlap / area match / text overlap / score, `--for` resolves a document's frontmatter via `commands.decisions.resolve_doc`. Suite 391/391. Real-vault checks: `--for SPEC-012-learning-loop` and `--area methodology` both surface the relevant lessons (top hits are the retrieval and install-drift lessons). Note: the catalog writer (`sync.py:_catalog_row`) does not currently emit an `escalated` field even though `lesson-write` sets it on the lesson file at 3 recurrences - the ranking code is ready but the field never reaches a catalog row yet; out of TASK-047's file ownership, flagged for a follow-up task.
- [x] PLAN-006 COMPLETE (2026-08-06): all 16 tasks. Phase 4: TASK-048 retrieval trace + planner/builder call compass lessons. Phase 5: TASK-049 lesson-coverage (3 statuses, advisory), TASK-050 validator audit step 4e, TASK-051 docs + acceptance. Acceptance battery PASS: suite 420/420, doctor 0 FAIL on installed CLI (26 commands), capture-stats 2 opened / 2 fired / 2 written across two trigger types, decision coverage 4/4. Live evidence: two organic firings same-day (handoff-strong-signal and interval paths), 3 lessons created + 1 revised organically.
- [ ] NEXT: validator run over PLAN-006 (final quality gate), then fleet distribution (carries the hook-registration fix that turns the loop on across 40 vaults), then SPEC-011 pipeline, then SPEC-006 hosts.
- [ ] After PLAN-006: SPEC-011 pipeline (research/ADR on substrate + planner), distribute v0.4.0 across repos (19/40 vaults lack the backstop), then SPEC-006 hosts (hermes first, then Kimi Code/Codex)

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
