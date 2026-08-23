---
title: What Compass Can Borrow from GSD (Git. Ship. Done.)
type: research
status: complete
confidence: high
area: methodology
tags: [gsd, prior-art, spec-driven-development, multi-runtime, decision-coverage, state-digest, competitive]
created: 2026-07-22
updated: 2026-07-22
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[SPEC-006-multi-host-agent-cli-support]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
summary: "decision coverage, model policy, prior art for SPEC-006"
---

## Question

GSD Core (`open-gsd/gsd-core`) is the same category as Compass - a spec-driven, context-engineered AI-dev framework with a file-based memory vault and a mechanical CLI. Ignoring compatibility, what does GSD do that could make Compass better, mapped to the four ranked goals (accuracy > perfect memory > near-zero cache misses > low tokens)?

## Methodology

Technology-landscape comparison. GitHub API for repo/org metadata; targeted reads of README, `docs/ARCHITECTURE.md`, `docs/USER-GUIDE.md`, `docs/reference/*`, ADRs, and agent/command/capability files. API-verified facts are high confidence; doc-summary findings are medium.

## Headline finding

GSD is a mature, high-velocity **running tool** that independently converged on Compass's core bets (fresh-context subagents, file-based state, parallel waves, CLI-does-mechanical-work off the token budget, retrospective learnings) - strong validation those are correct. It is meaningfully ahead of Compass in a few mechanical disciplines worth borrowing (decision-coverage tracing, per-agent model policy, atomic state locking), and it is the living proof-of-concept for [[SPEC-006-multi-host-agent-cli-support]] via its capability-manifest runtime split. Compass is ahead on memory-tier rigor, lesson discipline, and human-navigable graph - do not regress those.

## What GSD is

Installable (`npx @opengsd/gsd-core@latest`), MIT-licensed, cross-runtime (10+ agent CLIs). Drives agents through a repeating five-phase loop (Discuss → Plan → Execute → Verify → Ship) per phase per milestone. State in a `.planning/` dir of Markdown + JSON. Ships a ~10,700-line Node CLI (`gsd-tools.cjs`) **and** an MCP server. Maturity (API-verified): ~7,031 stars, 100+ contributors, ~4,720 commits, `v1.8.0` released 2026-07-22, actively pushed. A serious, well-staffed project - not a toy.

## Findings

1. **Decision-coverage tracing (HIGH).** Discuss-phase writes `CONTEXT.md` with stable decision IDs (`D-01 … D-NN`) in a `<decisions>` block. A **blocking** plan gate requires every trackable decision to appear in a plan; a **non-blocking** verify gate logs missed decisions as warnings; opt-outs are explicit (`### Claude's Discretion`, `[informational]`, `[deferred]`). Compass has nothing that mechanically checks a decided thing survives into the plan. This is the single highest-value borrow. Serves goal 1.

2. **Declarative gate-predicate rail (MEDIUM).** Gates use a standard envelope (`point`, `check`, `when`, `blocking`) with checks of type `query` / `predicate` / `agentVerdict`. Built-in `command-exit-zero` (exit 0 pass, non-zero/timeout block; placeholders for phase dir/req-ids; default 30s). Rule: only non-LLM checks may block. Compass's validator runs commands but has no config-gated blocking-predicate contract between stages. Serves goal 1.

3. **STATE.md bounded digest with a derivability split (HIGH).** `.planning/STATE.md`, target <100 lines, "digest not archive." YAML frontmatter (machine, regex-parsed for the statusline: `status`, `active_phase`, `next_action`, a `progress` block with a defined `percent` formula) + Markdown body (human). An ADR documents the rebuild contract: progress/current-phase are **derivable** from roadmap/summary counts; decisions/blockers/trends/continuity are **not** and must persist ("lossy by design"). Compass's `active.md` lacks both the machine-readable progress frontmatter and the documented derivable/non-derivable partition. Serves goals 2, 3.

4. **Atomic lockfile state writes (HIGH).** All state writes use `O_EXCL` lockfiles (`STATE.md.lock`, `.planning/.lock`) to prevent read-modify-write races during parallel executor waves. Compass runs parallel builders that each touch `active.md`/`index.md` - this is a concrete race-safety pattern the `compass` CLI could adopt. Serves goals 1, 2.

5. **Per-agent model-resolution policy (HIGH).** `gsd-tools.cjs resolve-model <agent>` returns model+effort (`opus`/`sonnet`/`haiku`/`inherit`) from a central policy module. Compass tiers models ad-hoc with no central table - a low-cost token/cost lever. Serves goal 4.

6. **Trigger-conditioned seeds (MEDIUM).** `.planning/seeds/SEED-NNN.md` store forward-looking ideas *with trigger conditions*; new-milestone scans surface seeds when their trigger fires. Compass's `backlog.md` is an undifferentiated flat list. Serves goal 2.

7. **Machine-readable verify routing (MEDIUM).** `/gsd-verify-work` routes on a `coverage:` frontmatter block in `SUMMARY.md`: auto-passes deliverables marked `human_judgment: false` with passing tests; everything else goes to manual approval. Compass has the two-tier automated/manual split but decides routing by agent judgment, not machine-readable frontmatter. Serves goal 1.

8. **Adaptive 1M-context enrichment (MEDIUM).** For models with `context_window ≥ 500K`, prompts are auto-enriched with context that would not fit a 200K window (prior-wave summaries, phase context/research). Compass runs on opus 1M but uses one fixed 5K hot-path cap - an adaptive enriched variant when the model has headroom is worth considering. Serves goals 3, 4.

9. **Temporal validity for superseded knowledge (MEDIUM).** GSD's MemPalace KG marks superseded facts with `valid_to` rather than deleting (`valid_from`/`valid_to` provenance). The concept - mark-invalid, don't hard-delete - is borrowable for Compass lessons/ADRs; the full temporal knowledge graph is heavier than Compass's flat lessons and not worth it. Serves goal 2.

10. **Cross-runtime capability manifests (HIGH) - prior art for [[SPEC-006-multi-host-agent-cli-support]].** Each capability is a folder with a schema-validated `capability.json`. `role: "feature"` = abstract workflow logic (owns skills/agents, declares `steps`, `gates`, `config`, and `contributions` - prompt fragments injected `into` agent roles at 12 named loop points like `discuss:pre`, `execute:wave:post`). `role: "runtime"` = host binding (`configHome`, `localConfigDir` e.g. `.claude`/`.agents`/`.github`, `configFormat`, `commandStyle`, `hooksSurface`). One workflow reaches Claude Code, Cursor, Copilot, OpenCode, **Kimi, Codex**, Windsurf. This is a concrete, shipping answer to SPEC-006's exact problem. The researcher's judgment: study the *shape* (a runtime binding that declares each host's config dir / format / command style / hooks surface), do **not** import the full manifest machinery.

## Where Compass is already ahead (do not regress)

- **Explicit three-tier memory hierarchy** (hot ≤5K hard cap / warm RAPTOR folder summaries / cold leaf bodies) with cited lost-in-the-middle rationale and start-of-context positioning. GSD's <100-line STATE.md digest is a partial analog, not a full documented tier system. See [[RESEARCH-hierarchical-knowledge-base-design]].
- **Lesson discipline:** 5-line cap + anti-list filter + dedup + score + `seen`/`escalated` catalog. GSD's `LEARNINGS.md` accumulates with dedup but no documented cap, anti-list, scoring, or escalation.
- **Human-navigable graph:** Obsidian wikilinks + folksonomy tag-index for multi-parent retrieval, inspectable in Obsidian. GSD uses `@`-refs + a separate KG.
- **Research rigor:** named methodologies + per-finding confidence levels; GSD's research has no confidence taxonomy.

## Convergent designs (independent arrival = strong signal these are right)

Fresh-context subagents for heavy work; file-based state surviving `/clear`; parallel wave/worktree execution with dependency analysis; CLI/hooks doing mechanical bookkeeping off the token budget; retrospective learning capture with dedup; human-approval gates on strategic transitions. Both systems landed here independently.

## Recommendation for Compass

**Adopt (high value, low cost):**
1. **Decision-coverage tracing (Finding 1)** → goal 1. Stable decision IDs in specs/plans + a CLI/validator check that each survives into the plan and is accounted for at validation. Highest value; catches the most common accuracy failure (a decided thing silently dropped).
2. **Per-agent model policy (Finding 5)** → goal 4. One central table of which subagent runs which model/effort.
3. **Trigger-conditioned backlog (Finding 6)** → goal 2. Optional `trigger:` on backlog items so deferred ideas resurface on condition instead of rotting.
4. **Atomic `O_EXCL` state locking (Finding 4)** → goals 1, 2. Cheap insurance against the parallel-builder race Compass already runs.

**Study / consider (medium value or cost):**
5. Machine-readable verify routing (`human_judgment: true|false` in task frontmatter) - Finding 7, goal 1.
6. Declarative `command-exit-zero` blocking gate rail between stages - Finding 2, goal 1.
7. STATE.md-style progress frontmatter + derivability split for `active.md` - Finding 3, goals 2, 3.
8. Temporal-validity (`valid_from`/`valid_to`, mark-don't-delete) for lessons/ADRs - Finding 9, goal 2. Concept only, skip the KG.
9. Adaptive enriched hot path when the model has 1M headroom - Finding 8, goals 3, 4.
10. **The runtime-binding shape (Finding 10)** as direct input to [[SPEC-006-multi-host-agent-cli-support]]'s research phase - study how GSD declares each host's config dir / format / command style / hooks surface.

**Do NOT adopt:**
- The full cross-runtime capability-manifest machinery (Finding 10) - massive engineering surface. Borrow the runtime-binding *idea* for SPEC-006, not the framework.
- The MCP server path - GSD ships one, but Compass rejected MCP for internal bookkeeping ([[ADR-005-compass-cli-for-mechanical-work]]); GSD's choice does not invalidate that.
- The 10,700-line CLI *scale* - validates the philosophy, not the size. Keep the Compass CLI lean.
- Graphify AST knowledge graph and the full MemPalace KG + cross-project tunnels - high build/maintenance cost, over-engineered for Compass's scope.

## Gaps

- GSD's learnings dedup/scoring internals live in an install-materialized workflow blob, not the browsable repo tree; whether GSD scores/ranks learnings is unconfirmed.
- Gate-predicate and capability findings come from GSD's reference docs (medium), not cross-checked against the `capability.json` schema source.

## Sources

- Repo: `github.com/open-gsd/gsd-core` (branch `next`); org `github.com/open-gsd` (11 repos incl. `gsd-pi`, `gsd-browser`, `agent-inbox` MCP)
- `docs/ARCHITECTURE.md`, `docs/USER-GUIDE.md`, `docs/reference/{state-md,gate-predicates,capability-manifest}.md`
- `docs/adr/1817-state-md-rebuild-derivability-contract.md`, `1820-spec-optional-predicate-rail.md`
- `agents/gsd-mempalace-curator.md`, `commands/gsd/{extract-learnings,graphify,spike,sketch,thread}.md`, `capabilities/*/capability.json`
- Metadata via `gh api repos/open-gsd/gsd-core`, `orgs/open-gsd/repos`
