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

## Building: [[PLAN-002-compass-cli-implementation]] (approved 2026-06-14)

### Phase 1 - Foundation (dispatch + shared library)

- [x] TASK-001: Build `plugin/cli/` package skeleton - `vaultlib.py` + argparse dispatch + exit helpers (never-exit-2). 17 tests pass. (2026-06-14)

### Phase 2 - All commands (parallel tracks, after Phase 1)

- [x] TASK-002: `compass next-num` | TASK-003: `compass tree` + `hot-path` (read-only track) - clean on real vault (2026-06-14)
- [x] TASK-004/005/006: `compass sync` core + caps/cleanup + hook mode - idempotent on real vault, found+fixed missing handoff in index (2026-06-14)
- [x] TASK-007: `compass validate` - zero false positives on real vault, exit 0 (2026-06-14)
- [x] TASK-008: `compass promote` + `clean-tmp` | TASK-009: `compass touched` + `admit-check` (2026-06-14)

### Phase 3 - Cutover, measurement, lessons (after Phase 2)

- [x] **Pre-req: `.gitattributes` with `eol=lf`** added; `git check-attr` confirms LF, CRLF churn warning gone (2026-06-14)
- [x] TASK-010: hooks.json PostToolUse → `type: command` running `compass sync`. Verified via faithful hook simulation (vault write → suppressOutput; own-output + non-vault → no-op; all exit 0). (2026-06-14)
- [x] TASK-011: shrunk `index-sync` (262→~45 lines), `vault-health`, `promote-spec` to CLI wrappers; grep checks pass (2026-06-14)
- [x] TASK-012: [[RESEARCH-cli-token-reduction-measurement]] - ~99.8% reduction (target >=80%), integrity preserved + improved. Hypothesis CONFIRMED. (2026-06-14)

### Done (deployment)

- [x] Live dogfood cutover CONFIRMED (2026-06-14, post-restart): a throwaway vault Write auto-fired `compass sync` via the command hook - index.md + tag-index updated with zero agent tokens, no blocking prompt. Mid-session hook edits do not reload; a restart loads them.
- [x] `/compass:bootstrap` now copies `plugin/cli/` -> `.claude/cli/`, installs `.claude/hooks/hooks.json` from the plugin, checks for python3, and the shipped hook runs `python3 "$CLAUDE_PROJECT_DIR/.claude/cli/compass" sync --hook`. Verified end-to-end by simulating a fresh self-contained install into a temp project (hook syncs, own-output no-ops, validate clean). So on other repos: `/compass:bootstrap update` + restart is now sufficient (python3 required).
- [x] Fixed two CLI bugs the deployment test surfaced: `sync` hung on stdin in non-interactive shells (now gated behind `--hook`, see [[LESSON-hook-cli-gate-stdin-on-flag]]); argparse rejected pass-through flags (now argv split manually).

### Note for human

- bootstrap step 2b previously documented (but never actually installed - no settings.json exists in the dogfood) an old `SubagentStop` "run tester after builder" hook. The rewrite drops it; testing is handled by `/compass:build`'s fix loop now. Flag if you want that auto-tester hook back.

### Deferred (optional)

- [ ] Live two-session A/B to convert the per-fire token floor into an end-to-end measured number.

## Today (2026-07-23): SPEC-007 + SPEC-008 + SPEC-010 to built-and-validated

Batch approved by Roger. Full pipeline per spec: research -> ADR -> plan (human approves) -> build -> test -> validate. [[SPEC-009-configurable-pipeline-workflows]] explicitly deferred to [[backlog]].

- [ ] Research: SPEC-010 hierarchy impact on CLI/skills/hooks | SPEC-007 decision parser + gates | SPEC-008 model resolution surface
- [ ] ADRs from research (expected ADR-006/007/008)
- [ ] Plans (human approves before task distribution)
- [ ] Build + tests + validate

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
