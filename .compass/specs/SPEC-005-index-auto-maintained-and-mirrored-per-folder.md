---
title: Index Auto-Maintained on Add and Remove, Mirrored Per Folder
type: spec
status: draft
confidence: high
area: methodology
tags: [index, hierarchy, sync, hot-path, auto-maintenance, delete]
created: 2026-06-19
updated: 2026-06-19
depends_on: ["[[SPEC-003-hierarchical-vault-organization]]", "[[ADR-004-hierarchical-specs-with-facets]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
summary: "Index Auto-Maintained on Add and Remove, Mirrored Per Folder"
---

# Index Auto-Maintained on Add and Remove, Mirrored Per Folder

## Problem

The vault index does not fully maintain itself, and it does not mirror the project structure.

1. **Removal is not handled.** `compass sync` is append-only, so creating an artifact updates the index but deleting one leaves a stale entry that `validate` can only flag, not fix. The index drifts from reality on every delete or rename.
2. **There is one flat root index.** A single `index.md` lists everything. As the vault grows this is the exact bloat the hot-path cap fights, and it does not reflect where things live - a reader cannot open a folder and see what is in it.
3. **Per-folder `index.md` is half-defined.** ADR-004 gives a folder-spec's `index.md` the meaning "this is the parent spec," but no folder has an auto-maintained listing of its own contents.

The net effect: the index is trustworthy only for additions, and only at the root.

## Desired Outcome

The index maintains itself on **both** add and remove, and it mirrors the folder structure: a lean root index for orientation, plus an `index.md` in each folder that auto-lists that folder's contents. Opening any folder shows what is in it; deleting a file removes it from the index without human cleanup.

## Decisions (made by the human)

- **The index is machine-only.** No human ever edits an `index.md`; it exists purely for AI agents to orient. So it is a fully derived artifact, regenerated from the filesystem and frontmatter on every sync - never append-only. Deletes and renames are handled for free by regeneration; there is no human content to preserve.
- **Lean root + per-folder.** A lean root `index.md` plus an auto-generated `index.md` in each folder listing its contents. A folder-spec keeps its authored spec body; its contents listing is a clearly-delimited, machine-regenerated section, never hand-edited.
- **Never stale, and agents must trust it.** Because it is a tool, run the reconcile from as many trigger points as possible (write, delete/rename, turn-end) so the index is correct at all times, and make agents aware (templates, methodology) that the index is authoritative and current - the first thing to read, never re-derived by hand.
- **Summaries are automatic and invisible.** A human never asks for a summary or an index update and is never aware one happened. When a page changes, a background job - spawned by the existing hook, detached so it never blocks or delays the write - generates a one-line summary with headless `claude -p`, caches it by content hash, and updates the index entry when ready. The index shows the frontmatter `summary` instantly and upgrades to the LLM summary moments later. This is the HumanLayer / Anthropic principle: a compacted summary layer for navigation, full content loaded just-in-time. (Prototype confirmed: haiku summaries are good and often beat the title; latency is 10-30s, which is why generation is detached, not in the write path.)
- **Bounded, capped LLM cost (must not run away).** Summaries use only a small/cheap model (haiku); run only when a page's content hash changed (never per keystroke); the summary job never re-triggers itself (its cache/index writes are excluded from the summary trigger and loop-guarded); and a hard per-window call budget governs the rest - past the budget the index keeps the frontmatter summary and defers. Worst case the feature degrades to frontmatter summaries; it can never explode token usage. Estimated steady-state cost: well under $0.005 per changed page on haiku; a 50-artifact backfill is a one-time ~$0.10-0.25.
- **Applied to everything on update.** Updating to this version backfills the whole vault once: it (re)builds every folder index and generates a summary for every existing artifact - specs, research, decisions, lessons, plans, all of it - with no human step. After update nothing is left un-indexed or un-summarized.
- **Depth-capped root.** The root index descends only one or two levels into subfolders; beyond that the agent opens the relevant folder's `index.md` and continues. No path is more than three steps deep from the root.

## Hypothesis (falsifiable)

With machine-regenerated per-folder indexes, multi-trigger reconciliation, and cached page summaries, the index is correct after any single create, delete, or rename with no human action; the root stays under the 5,000-token cap and no more than three steps deep; and summaries stay current with their pages.

## Falsification criteria

The design is wrong if any hold after implementation:
- After deleting or renaming an artifact, a stale entry survives in any index after the next sync.
- The root index descends more than two levels, or some artifact sits more than three steps from the root.
- A folder-spec's authored body is altered when its contents section regenerates.
- An index entry's summary stays stale after its page's content changes.
- A human had to ask for a summary or an index rebuild, or had to wait on summary generation during a write.
- Summary generation uses anything but a small/cheap model, regenerates a page whose content is unchanged, runs without a hard call budget, or can re-trigger itself.
- After updating to this version, some pre-existing artifact has no index entry or no summary.
- The root `index.md` exceeds the 5,000-token cap at 50+ specs.

## Success criteria

- Create, delete, and rename each leave every affected index correct with no manual step.
- Summaries appear on their own - no human asks, no human waits - and never delay or block a write.
- Updating to this version leaves the entire existing vault indexed and summarized, with no human step.
- Every folder containing artifacts has an `index.md` listing them; opening it shows the folder's contents.
- The root index is a lean, depth-capped (<=2 levels) tree/pointer map under the hot-path cap; deeper content is reached by opening a folder index (<=3 steps total).
- Folder-spec `index.md` files keep their authored body; only the machine contents section changes.
- Each entry has a current one-line summary; agents treat the index as authoritative and read it first.

## Constraints

- The index is fully regenerated from disk each sync (machine-only); no human content to preserve, so deletes/renames need no special-casing beyond regeneration.
- Mechanical work stays in the `compass` CLI off the agent budget (ADR-005). Summary generation is the only LLM step: headless `claude -p`, on change only, cached, and **detached/background** so it never sits inside the agent's turn or the write path.
- The root hot path stays bounded (ADR-004); per-folder indexes are the warm tier, read on navigation, not loaded into the hot path.
- Must run on `python` or `python3`, LF line endings, never block or loop a write (the existing hook contract). If `claude` is unavailable for a summary, fall back to the frontmatter summary/title.

## Non-Goals

- A new index file format or query language. This reuses the existing wikilink + section markdown.
- Real-time filesystem watching as a daemon. The trigger rides the existing hook/tooling model.
- Changing what an artifact is, or the facet/tag system.

## Open questions (for the ADR)

- The exact per-folder index format, and how a folder-spec's authored body and its machine contents section share one file (delimiter, regeneration boundary).
- The full set of reconcile triggers (PostToolUse Write/Edit/MultiEdit + a `Bash` matcher catching delete/rename + a turn-end `Stop` reconcile) and how each stays cheap - no-op when nothing vault-relevant changed.
- The summary tool: `claude -p` invocation, the change-detection/cache key (content hash), a cost ceiling, and the fallback when `claude` is unavailable.
- The detached-background mechanism: how the hook launches a summary job that outlives the hook and never blocks the write, cross-platform (Windows git-bash + POSIX), and how it avoids piling up duplicate jobs.
- The backfill on update: how `/compass:update` (or a `compass reindex`) triggers a one-time full rebuild + summarize of an existing vault, idempotent, and whether that backfill itself runs in the background so the update returns immediately.
- How agents are made aware the index is authoritative and current (agent templates, methodology, a session-start pointer) so they read it first and never rebuild it by hand.
