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

Pipeline state: research DONE (3 docs) -> ADR-006/007/008 DONE -> PLAN-003/004/005 approved 2026-07-24 -> BUILDING. [[SPEC-009-configurable-pipeline-workflows]] deferred to [[backlog]].

### Done: [[PLAN-003-hybrid-hierarchy]] (all 9 tasks, 2026-07-24)

- [x] TASK-013: Golden fixtures of current sync/validate (S) - 87 tests green, goldens hand-verified, committed 4c44a05 (2026-07-24)
- [x] TASK-014: Unit-aware discovery + resolvable_names_map in vaultlib (L) - flat records field-identical, zero real-vault regressions, committed 4c44a05 (2026-07-24)
- [x] TASK-015: sync path-qualified emission + unit sections + lessons aggregation (L) - 10 new tests, goldens regenerated per D-02 amendment; orchestrator ratified folder-path link form (`[[<unit>/<type>/<folder>]]`, map extended) (2026-07-24)
- [x] TASK-016: validate ambiguity map + unified resolution + unclassified report (M) - 109 green, real-vault output byte-identical, committed 68ff9ef (2026-07-24)
- [x] TASK-017: tree / next-num / fix-frontmatter unit-awareness (M) - 4 new tests, traversal scopes rejected, type-invention bug fixed (2026-07-24)
- [x] TASK-018: compass unit-check (type-spread detection, report-only) (M) - finds the compass-cli set on the real vault, committed 68ff9ef (2026-07-24)
- [x] TASK-019: compass make-unit (migration operation) (L) - dry-run default, refusals exit 1, git history preserved, committed dda2d7f (2026-07-24)
- [x] TASK-020: path-qualified links in wikilinks rule + obsidian/methodology skills (M) - documents landed behavior only (2026-07-24)
- [x] TASK-021: Migrate the compass-cli set (dogfood, acceptance) (M) - .compass/compass-cli/ live, validate clean, history preserved (2026-07-24)

### Queued: [[PLAN-004-decision-coverage]] (parallel with 005 after 003)

- [x] TASK-022/023/024: strip_fenced_code + decisionslib parser + real-vault corpus - 47 new tests, legacy ADRs none-present proven (2026-07-24)
- [ ] TASK-025 compass decisions (M) | TASK-026 compass coverage (L) | TASK-027 planner gate + decisions: field (M) | TASK-028 validator audit (M) | TASK-029 convention docs + dogfood (M)

### Queued: [[PLAN-005-model-table]] (parallel with 004 after 003)

- [x] TASK-030/031/032: modelslib + resolve-model/models + apply-models - 58 new tests, planner->opus high, vault-locator->haiku low (2026-07-24)
- [ ] TASK-033 normalize 13 templates (S) | TASK-034 setup/update integration (M) | TASK-035 dogfood verification (S)

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
