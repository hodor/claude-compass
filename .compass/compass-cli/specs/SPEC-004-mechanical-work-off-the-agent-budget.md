---
title: Mechanical Vault Work Must Not Cost Agent Tokens
type: spec
status: approved
confidence: high
area: methodology
tags: [token-efficiency, automation, hooks, bookkeeping, hot-path, validation]
created: 2026-06-13
updated: 2026-06-13
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[LESSON-no-agent-bookkeeping]]"]
---

# Mechanical Vault Work Must Not Cost Agent Tokens

## Problem

Compass keeps its vault consistent by running deterministic bookkeeping: regenerating the root index, rebuilding the tag index, computing the next artifact number, validating wikilinks and frontmatter, checking the hot-path cap, pruning stale tmp logs. Today this work is done by **agents reading instructions out of skill files and an LLM-typed PostToolUse hook**. That has four costs, each hitting a north-star goal (SPEC-001):

1. **Token burn (goal 4).** The PostToolUse hook fires on *every* `.compass/**/*.md` write and currently spins up an agent that reads several thousand tokens of skill protocol to do work that is pure string manipulation. A single editing session can fire it dozens of times.
2. **Cache misses (goal 3).** Each agent-typed hook fire injects fresh content mid-session, perturbing the context and working against the bounded, stable hot path SPEC-003 fought for.
3. **Non-determinism threatens memory (goal 2) and accuracy (goal 1).** An LLM regenerating an index or validating wikilinks can hallucinate, reorder, drop entries, or pass a malformed file. Mechanical work has one correct output; a probabilistic engine is the wrong tool.
4. **Latency.** Agent round-trips are seconds; the equivalent script is milliseconds.

`[[LESSON-no-agent-bookkeeping]]` already names the root cause: mechanical bookkeeping belongs in scripts, not agent steps. The infrastructure was built before that lesson existed, so the lesson is recorded but not yet discharged.

## Desired Outcome

Every deterministic vault operation runs as a real program, off the agent's token budget and out of its context. Agents and hooks *invoke* that program and surface its results; they never re-derive index contents, numbering, or validation verdicts in tokens. Skills that today carry hundreds of lines of mechanical protocol shrink to "call the tool, report what it found."

## Hypothesis (falsifiable)

Moving the mechanical bookkeeping path from agent/LLM execution to a deterministic program reduces per-session tokens spent on vault upkeep by **at least 80%**, with **zero loss of vault integrity** (the program's outputs are byte-identical-or-better than what the LLM path produced on the same vault, and it catches every defect class the LLM path caught).

## Falsification criteria

The design is wrong if any of the following hold after implementation:

- A representative editing session (10+ vault writes) spends more than 20% of the current bookkeeping-token count.
- The program produces a root index, tag index, or numbering result that diverges from the hand-verified correct output on the dogfood vault.
- The program misses any defect the LLM validator catches: a broken wikilink, missing required frontmatter, or a hot-path cap breach.
- The program emits false positives on the clean dogfood vault (flags a valid file as broken).
- Integrity depends on the program running on a platform it was not tested on (e.g. corrupts line endings cross-platform per `[[LESSON-windows-crlf-breaks-linux-container-scripts]]`).

## Success criteria

- The PostToolUse path consumes effectively zero agent tokens (it shells out; the agent sees only a short result line, or nothing on success).
- One command regenerates the root index and tag index deterministically from the vault on disk.
- One command answers "what is the next number for artifact type X" from the filesystem, locally per folder (ADR-003, ADR-004).
- One command validates the vault (wikilinks, frontmatter, hot-path cap) and exits non-zero with a precise report on any defect.
- Validation catches the three seeded defect classes (broken wikilink, missing frontmatter, cap breach) and produces zero false positives on the current clean vault.
- Skills that were pure protocol (`index-sync`, parts of `vault-health`, `promote-spec`) are reduced to invoking the tool and surfacing findings.

## Constraints

- Must run on the maintainer's platform (Windows) and on Linux, writing LF line endings everywhere regardless of host (`[[LESSON-windows-crlf-breaks-linux-container-scripts]]`).
- Must require no dependency that a fresh `/compass:bootstrap` cannot assume is present.
- Must not change vault file *formats* — it reads and writes the existing Obsidian-compatible frontmatter + wikilink conventions, it does not invent new ones.
- Must be invokable both from a hook (non-interactive, exit-code-driven) and by a human at a terminal.
- Glob traversal must reach hidden `.compass/` paths (`[[LESSON-glob-hidden-dirs-prefix]]`); validation must skip fenced and inline code when resolving wikilinks (`[[LESSON-wikilink-validator-skip-code]]`).

## Non-Goals

- Replacing *judgment* work. Lesson extraction, consolidation merges, spec promotion decisions, and branch-summary generation stay with agents — the tool only does the mechanical parts they delegate.
- A general-purpose vault query engine or search index. Scope is upkeep and validation, not retrieval.
- Rewriting skills that are genuinely about reasoning (spec, plan, research, validate). Only the mechanical skills shrink.
- A daemon or background watcher. The tool is invoked per-event by the hook and per-command by humans; it does not run continuously.

## Risks

- **Re-implementing existing skill logic introduces behavior drift.** Mitigation: golden-output tests pinned against the current correct vault state before any skill is shrunk.
- **A program in the hook path can fail silently or block writes.** Mitigation: the hook must degrade safely — a tool failure surfaces a visible warning and never destroys or blocks the user's actual edit.
- **Two sources of truth during migration.** While both the LLM hook and the tool exist, they could disagree. Mitigation: cut over atomically per operation, delete the superseded skill protocol in the same change.
