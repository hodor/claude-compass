---
title: "Handoff: compass CLI shipped (v0.3.7); SPEC-005 (auto per-folder index + LLM summaries) drafted, ON HOLD"
type: handoff
status: active
area: methodology
tags: [handoff, compass-cli, index, summaries, spec-005, on-hold, tokens]
created: 2026-06-19
updated: 2026-06-19
git_branch: "master"
git_commit: "fbc32c5"
author: "claude"
---

# Handoff: CLI shipped; SPEC-005 drafted and on hold

## Start Here
1. [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] - the active design, **ON HOLD** pending proof the LLM-summary loop won't blow up tokens (the cost-cap guardrail is now baked into the spec). Next: human approval -> ADR-006 -> PLAN-003.
2. [[backlog]] - queued work, incl. **Stop/SubagentStop -> command hooks** (biggest remaining per-turn token cost), Rust port (deprioritized), methodology/human-review research.
3. [[SPEC-004-mechanical-work-off-the-agent-budget]] / [[ADR-005-compass-cli-for-mechanical-work]] / [[PLAN-002-compass-cli-implementation]] (done) - the shipped CLI's rationale.
4. `plugin/cli/` - the CLI (vaultlib + ~12 command modules + ~70 stdlib tests). `plugin/skills/{setup,update,consolidate-memory,report-bug}/SKILL.md` - new/changed skills.

## Session Summary
Built and shipped the `compass` CLI (PLAN-002) and iterated it from v0.2.0 to v0.3.7: setup/update split + `bootstrap`->`setup` rename, `fix-frontmatter`, cross-session bug self-reporting, `consolidate-memory`, and two real-repo overfit fixes. Investigated a token spike (heavy multi-project day + unbounded file-based memory, NOT Compass) and shipped `/compass:consolidate-memory`. Drafted SPEC-005 (machine-only auto-maintained per-folder index with detached `claude -p` page summaries + backfill-on-update) and prototyped the summary tool (works, good quality, 10-30s latency). Held the build at the human's request until the LLM token cost is proven bounded.

## Tasks
| Task | Status | Notes |
|---|---|---|
| compass CLI (PLAN-002 / SPEC-004) | DONE | command-hook cutover, ~99.8% bookkeeping-token cut, hypothesis confirmed |
| setup/update split; rename bootstrap->setup | DONE | `init` rejected (shadows built-in `/init`); setup/update collision-free |
| fix-frontmatter / bug self-reporting / consolidate-memory | DONE | shipped through v0.3.7 |
| overfit fixes (content-aware type dirs; validate top-level links) | DONE | found on product-owner + iwyc-unreal |
| SPEC-005 auto per-folder index + LLM summaries | DRAFT, ON HOLD | token-cost concern; cap guardrail specced; needs approval -> ADR-006 -> PLAN-003 |
| Stop/SubagentStop -> command hooks | BACKLOG | still agent-type; per-turn agent spawns = biggest remaining ongoing cost |

## Recent Changes (this session, all pushed)
- `fbc32c5` README; `6fc0b30`/`755b4d8`/`e70120e` consolidate-memory; `7ea50b8` update no longer deletes user skills; `997f06c` content-aware type-dir discovery; `fc5677c` bug self-reporting; `d6354bc` validate top-level links; `58687b2` fix-frontmatter; `5526e3a` setup rename; `c533ab2` the CLI build.
- Plugin at **v0.3.7**.

## Decisions
- `index.md` is machine-only -> full regenerate (not append-only); deletes/renames are free.
- Summaries: automatic, invisible, **detached** (`claude -p` haiku, cached by content hash, hard call budget, never self-trigger). Degrades to frontmatter summary; cannot run away.
- Root index depth-capped (<=2 levels, <=3 steps to any artifact).
- Backfill the entire vault on update.
- `bootstrap`->`setup`; `update` is a separate git-based skill; `init` avoided (built-in collision).
- Rust port deprioritized (needs a distribution decision: binary vs copyable source).

## Learnings
- The CLI was overfit to the dogfood twice; real repos are the test (product-owner `retro/`, iwyc-unreal's symlinked `.compass/claude/` install). [[LESSON-type-dir-discovery-needs-content-signal]].
- An updater must remove only what it installed, never "anything not in my source". [[LESSON-installer-removes-only-what-it-installed]].
- Hook-invoked CLI must gate stdin on a flag, not isatty. [[LESSON-hook-cli-gate-stdin-on-flag]]. autocrlf churns LF writers. [[LESSON-autocrlf-churns-lf-writers]].
- Token spike was memory bloat (per-project file memory up to 49 files / 25K tokens) + multi-project, not Compass. `claude -p` haiku summary ~$0.005, 10-30s -> detached only.

## Blockers
- **SPEC-005 on hold** until the LLM-summary token cost is proven bounded. Guardrails specced (haiku-only, content-hash cache, loop guard, hard per-window budget, degrade-to-frontmatter); the ADR/build must enforce and a real-session measurement should confirm.

## Uncommitted Changes
`git status`: `M backlog.md`, `M index.md`, `M meta/tag-index.yaml`, `?? SPEC-005-...md`. All `plugin/` work is committed + pushed through `fbc32c5` (v0.3.7). Stage the vault files and commit.

## Action Items
1. [ ] Human: approve or revise [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]].
2. [ ] On approval: ADR-006 - resolve the detached-background spawn (cross-platform, outlives the hook, no pileup), the backfill-on-update, the per-folder format (folder-spec body vs machine contents section), and lock the cost cap.
3. [ ] Then PLAN-003 + build with tests + a real-repo dry-run.
4. [ ] Independent of SPEC-005: convert `Stop`/`SubagentStop` hooks to commands (backlog) - the biggest current ongoing token saving.
5. [ ] Roll `/compass:update` (-> v0.3.7) + `/compass:consolidate-memory` across repos. product-owner's update hit a ".claude write blocked" friction needing a hand-run script - diagnose it.

## Context for Resuming
- Other repos are at mixed versions (iwyc-unreal / product-owner ~0.3.1). Update to 0.3.7 for the latest. product-owner's `/compass:update` needed a manual `update-compass.sh` because a `.claude/` write was blocked in that session - worth hardening.
- Summary prototype: `cat <file> | claude -p --model claude-haiku-4-5 "Summarize ... one terse line ..."` -> good output, 10-30s, so detached only.
- Do NOT run the LLM summary loop without the cap + loop-guard - that is the explicit human concern that paused the build.
- Memory consolidation A/B: an aggressive human prompt cut iwyc 92%; the skill cut product-owner 47% (too gentle), now retuned in v0.3.7 to lead with the aggressive directive.
