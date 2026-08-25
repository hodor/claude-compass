---
title: "Handoff: PLAN-006 Phase 2 live; hooks fire from settings.json for the first time ever"
type: handoff
status: active
area: methodology
tags: [handoff, learning-loop, hooks]
created: 2026-08-06
updated: 2026-08-06
git_branch: master
git_commit: fc02b9c
plan: [[PLAN-006-learning-loop]]
summary: "Handoff: PLAN-006 Phase 2 live; hooks fire from settings.json for the first time ever"
---

# Handoff: Phase 2 live, hooks finally fire, Phase 3 next

## Start Here

1. [[PLAN-006-learning-loop]] - Phases 1-2 built (TASK-036..043 done, suite 341/341); TASK-044 live-firing in progress; TASK-045 carries the settings-registration amendment.
2. [[SPEC-012-learning-loop]] - the approved spec this implements.
3. `.claude/settings.json` - THE discovery of this session: Claude Code loads hooks ONLY from settings files or registered plugins, never from a bare `.claude/hooks/hooks.json`. No Compass hook had ever fired in any vault until this file was written (2026-08-06). PostToolUse and Stop verified firing live; state in `.compass/tmp/capture-state.json`, trace in `.compass/tmp/capture-log.jsonl`.
4. [[RESEARCH-lesson-capture-failure]] - its 19/40 backstop gap is now known to be an undercount: without settings registration it was 40/40, and ai-songwriting's one organic firing came through build-skill prose, not a hook.

## Session Summary

SPEC-012 drafted and approved; PLAN-006 planned and approved (coverage gate PASS); SPEC-011 experiment run, three-lens reviewed, rescoped consumer-first (orphans + hub ranking + impact traversal with planner consumer), approved. Phases 1-2 of PLAN-006 built and committed task-by-task with per-task verification (242 -> 341 tests). Repo made private on GitHub after a personal-info audit (real name/email in public commit metadata; other-project names in vault docs). Live-firing test then exposed the hooks-never-loaded root cause; settings.json registration fixed it in-session.

## Tasks

| Task | Status | Notes |
|------|--------|-------|
| TASK-036..040 (Phase 1) | done | capture substrate, all committed individually |
| TASK-041..043 (Phase 2) | done | opportunity contract, capture-close, contradiction branch, 11-bucket anti-list, archive branch, hook cutover |
| TASK-044 | in-progress | install refreshed + verified; PostToolUse and Stop hooks CONFIRMED live; SubagentStop did NOT fire for teammate-style agents (docs say it should - possible edge case/bug); TeammateIdle registered as additional signal source, payload shape unverified |
| TASK-045..046 (Phase 3) | next | doctor MUST check settings-file hook registration, not hooks.json existence (amendment in plan) |
| TASK-047..051 (Phases 4-5) | pending | retrieval + lesson coverage |

## Learnings

- Hooks load only from settings files / registered plugins; `.claude/hooks/hooks.json` is inert unless merged into settings. Settings hook changes reload live, no restart needed.
- The settings `hooks` schema has no `if` clause; per-path filtering lives CLI-side (sync.py:411 already does it).
- Teammate-style background agents (idle-notification lifecycle) did not emit SubagentStop despite docs; TeammateIdle is the event that observably fires for them.
- Subagent final text is invisible to the orchestrator unless the agent calls SendMessage; every spawn brief must say so (hit ~6 times this session).

## Blockers

None.

## Uncommitted Changes

- `.compass/plans/PLAN-006-learning-loop.md` - TASK-045 settings-registration amendment (staged with this handoff).
- `.claude/` (gitignored): refreshed install + new settings.json with registered hooks incl. TeammateIdle.

## Action Items

1. [ ] Finish TASK-044: confirm a strong-signal firing end to end (this handoff's own write is the test), run capture-stats, get the human's nudge-UX verdict.
2. [ ] Verify TeammateIdle payload shape reaching capture-signal (agent_type present? message present?) and adjust capture-signal or the entry if needed.
3. [ ] Phase 3: TASK-045 doctor (with settings-registration check), TASK-046 wiring into update/checkup; the setup/update skills must write settings.json hook registration (fold into TASK-046).
4. [ ] Phases 4-5, then validation; then fleet distribution (now including settings registration everywhere) and the SPEC-011 pipeline.

## Context for Resuming

The dogfood repo runs hooks from `.claude/settings.json` as of this session; `plugin/hooks/hooks.json` remains the plugin-manifest source of truth the installer must translate into settings registration. capture-state turns counter was at 3 with one vault-write signal before this handoff was written.
