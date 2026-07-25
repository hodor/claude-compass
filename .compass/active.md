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
