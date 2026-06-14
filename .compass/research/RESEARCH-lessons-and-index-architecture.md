---
title: Lessons & Index Architecture - Literature Review
type: research
status: complete
confidence: high
area: methodology
tags: [lessons, index, memory, hooks, dedup, retrospective]
created: 2026-05-24
updated: 2026-05-24
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]"]
---

# Lessons & Index Architecture - Literature Review

## Question

How should Compass capture lessons and keep its index fresh, given that the current design (per-agent in-flight "if you found a pattern" capture + 3-file ceremony) produces near-zero lessons and a perpetually stale index? Evidence: the Compass project's own vault has 0 lessons and `lessons-catalog.yaml: []` after multiple work sessions.

## Methodology

Parallel investigation across 5 reference codebases, each spawned as an independent agent with the same 4 research questions:

1. **Timing** - in-flight vs retrospective vs hybrid
2. **Index/catalog freshness** - agent discipline vs sweep vs hook vs single-write
3. **Deduplication** - merge vs append vs supersede vs none
4. **Lesson/memory shape** - format, length, taxonomy

References investigated:
- `F:/claude/references/humanlayer` - HumanLayer (the methodology Compass is partly modelled after)
- `F:/claude/references/hf-skills` - Hugging Face's published Claude Code skills
- `F:/claude/references/ml-intern` - long-running ML coding agent with context_manager
- `F:/AI/coding/claude-code` - hodor/ccode reimplementation with explicit memdir subsystem
- `F:/AI/coding/claw-code` - ultraworkers/claw-code Python+Rust port (parity-tracked)

## Findings

### 1. Capture timing (HIGH confidence)

Zero of five do per-agent in-flight "if you got surprised" capture. The two that capture automatically (`hodor/ccode`, `ml-intern`) do it at end-of-turn or on context budget pressure. The two that capture manually (`humanlayer`, `hf-skills`) do it at end-of-session or PR time.

- `hodor/ccode`: Stop hook fires forked extractor subagent after every turn (`F:/AI/coding/claude-code/query/stopHooks.ts:141-153`, `services/extractMemories/extractMemories.ts:415-427`)
- `humanlayer`: user-invoked `/create_handoff` writes Learnings section (`F:/claude/references/humanlayer/.claude/commands/create_handoff.md:54-55`)
- `ml-intern`: loop logic compacts mid-conversation at 90% token budget (`agent/core/agent_loop.py:471`, `agent/context_manager/manager.py:338-339`)
- `hf-skills`: human authors write skills, no runtime capture
- `claw-code`: not implemented, no port planned

**Implication for Compass:** drop per-agent in-flight prompts. Capture at end-of-turn via Stop hook OR at end-of-session via slash command.

### 2. Index/catalog freshness (HIGH confidence)

Wide divergence in mechanism, but a strong negative pattern: nobody relies on agent discipline alone.

- `hf-skills` (most rigorous): single source of truth (`SKILL.md` frontmatter) generates AGENTS.md, README table, plugin manifests via `scripts/generate_agents.py:49-187`. CI enforces with `publish.sh --check` (`F:/claude/references/hf-skills/.github/workflows/generate-agents.yml:29-30`).
- `hodor/ccode`: hand-maintained MEMORY.md with HARD CAP at 200 lines / 25KB, truncation appends a visible warning the model sees on next load (`memdir/memdir.ts:35-103`). Scheduled rebuild during dream consolidation Phase 4 (`services/autoDream/consolidationPrompt.ts:54-60`).
- `humanlayer`: no index at all; `thoughts-locator` agent does FS scan each time (`F:/claude/references/humanlayer/.claude/agents/thoughts-locator.md:50-55`). The `thoughts sync` post-commit hook just rebuilds a read-only hardlink mirror (`hlyr/src/commands/thoughts/sync.ts:101-196`).
- `ml-intern`: no index, only in-memory todo list (`agent/tools/plan_tool.py:8-9`).
- `claw-code`: not implemented.

**Implication for Compass:** combine `hodor`'s self-warning cap with a mechanical sweep hook. Don't trust agents to remember.

### 3. Deduplication (HIGH confidence)

`hodor/ccode` solved this elegantly: dedup happens at write time via pre-injected manifest, not post-hoc similarity.

- Before extraction runs, `scanMemoryFiles` reads frontmatter from all memories and `formatMemoryManifest` produces `[type] filename (ts): description` lines injected into the prompt (`memdir/memoryScan.ts:35-94`, `services/extractMemories/prompts.ts:29-43`).
- Writer prompt: "Check this list before writing - update an existing file rather than creating a duplicate" (`prompts.ts:32`).
- Long-horizon: dream consolidation Phase 3 merges/deletes after the fact (`consolidationPrompt.ts:48-51`).
- `humanlayer`: only dedups at read time (`thoughts-analyzer` marks superseded content, `.claude/agents/thoughts-analyzer.md:54,66,110`). Writer never checks.
- `hf-skills`, `ml-intern`, `claw-code`: nothing.

**Implication for Compass:** inject the lessons-catalog summaries into the extractor's prompt before write. Cheap, no embeddings, model judges by reading.

### 4. Lesson/memory shape (HIGH confidence)

Convergence: closed taxonomy + templated body + anti-list prevents rambling. Diverges on length enforcement.

- `hodor/ccode` (most disciplined): 4 hardcoded types (`user`, `feedback`, `project`, `reference`) parser rejects unknown (`memdir/memoryTypes.ts:14-31`). Body MUST follow `rule + Why: + How to apply:` for `feedback`/`project` (`memoryTypes.ts:63,81,137,154`). Explicit anti-list of what NOT to save, including the killer rule: "These exclusions apply even when the user explicitly asks you to save" (`memoryTypes.ts:183-195`).
- `humanlayer`: frontmatter + 7 templated sections (Task, Critical References, Recent changes, Learnings, etc.); brevity is prose hint not enforced (`.claude/commands/create_handoff.md:43-65,93,95`).
- `hf-skills`: frontmatter + free body, ranges 113-738 lines; only `description` field is length-disciplined (used for routing in AGENTS.md).
- `ml-intern`: free prose bounded only by `max_completion_tokens` (~18k for compaction, 4k for restore note).
- `claw-code`: not implemented.

**Implication for Compass:** closed 2-type taxonomy (`process` / `domain`) parser-enforced. Body template `When + Lesson + Why`, each ≤ 1 sentence. Anti-list verbatim adapted from `hodor`.

### 5. Long-horizon consolidation (MEDIUM confidence)

Only `hodor/ccode` has it. The pattern: per-turn extraction is shallow (write what's true now), separate periodic pass does the merging/pruning/demotion that no in-flight writer can.

- `hodor`: `executeAutoDream` runs after every extract if ≥24h elapsed AND ≥5 sessions since last (`services/autoDream/autoDream.ts:63-99`). Consolidation Phase 3 merges, Phase 4 prunes (`consolidationPrompt.ts:48-60`).
- All other refs: no consolidation pass.

**Implication for Compass:** add a `/compass:consolidate` command (manual trigger first, auto-trigger by session count later).

## Negative signals

- `claw-code` (48kLOC parity-tracked Claude Code port) explicitly didn't port memdir and didn't wire `/insights` or `/thinkback` slash commands (`rust/crates/commands/src/lib.rs:464-476,4290-4315`). Their PARITY.md "Still open" list (`PARITY.md:174-181`) doesn't even classify memory as a known gap. Whatever Compass builds must justify its own existence; this isn't load-bearing for a Claude Code clone.
- Zero of five use per-agent in-flight "name a surprise" prompts. Current Compass design is an outlier.

## Convergence summary

| Question | Strong convergence | Source count |
|---|---|---|
| Capture timing | Retrospective beats in-flight | 5/5 (no in-flight precedent) |
| Trigger mechanism | Automation beats agent discipline | 4/5 (hooks/loop/CI; humanlayer = user command) |
| Dedup approach | Pre-write manifest beats post-write merge | 1/5 (only hodor solved it; rest unsolved) |
| Shape | Closed taxonomy + body template + anti-list | 2/5 (hodor strongest, humanlayer partial) |
| Length | Hard cap + self-warning beats prose hint | 1/5 (only hodor) |

## Recommended architecture for Compass

Adopt `hodor/ccode`'s memdir architecture, adapted to Compass's process/domain taxonomy and the existing `.compass/` vault structure:

1. **Retrospective capture at end of orchestrator turn** via Stop hook spawning a forked extractor subagent. Read turn artifacts (build/test/validate/debug reports), check 5 binary trigger conditions (fix loop ≥2, validator Deviation problem, debug >1 wrong hypothesis, reviewer ≥3-of-N convergence miss, STOP-and-report). If none fired, write nothing.
2. **Dedup via pre-injected manifest** of all existing lesson summaries. Extractor's prompt explicitly directs updating an existing file when overlap is detected.
3. **Single `lesson-write` skill** that does file + catalog + index in one atomic call. Eliminates 3-file ceremony.
4. **Closed 2-type taxonomy** (`process` / `domain`), parser-rejected if unknown.
5. **Body template enforced**: `When + Lesson + Why`, each ≤ 1 sentence.
6. **Anti-list** verbatim, including "these exclusions apply even when the trigger condition is met."
7. **Index freshness via mechanical sweep** in the same Stop hook (glob vault, diff against index, auto-append missing).
8. **Hard caps with self-warning** on `index.md` (200 lines / 25KB) and `lessons-catalog.yaml`.
9. **Periodic consolidation** via `/compass:consolidate` command (merge, prune, demote, archive low-score lessons).

## Risk

The whole architecture leans on Stop hooks firing reliably. If Claude Code's Stop hook surface is fragile or environment-dependent, fallback is invoking the same `extract-lessons` and `index-sync` skills as the final step of `/compass:build`, `/compass:plan`, `/compass:research`. Worth verifying before committing.

## What to drop from current design

- Per-agent "if you found a pattern" instructions in `builder.md`, `validator.md`, `reviewer.md`, `debug.md`
- "If something surprised you" phrasing everywhere
- The append-only rule at the per-turn level (consolidation may merge)
- The 3-file write ceremony (collapsed into `lesson-write`)
- Per-agent index update instructions (replaced by sweep)
