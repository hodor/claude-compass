---
title: Retrospective lesson capture at phase boundary with single-writer dedup
type: decision
status: approved
confidence: high
area: methodology
tags: [lessons, hooks, retrospective, dedup, anti-list]
created: 2026-05-24
updated: 2026-05-24
git_branch: "master"
git_commit: "pending"
author: "roger + claude"
depends_on: ["[[ADR-001-methodology-as-skill-with-vault]]", "[[SPEC-002-lessons-and-index-subsystem]]", "[[RESEARCH-lessons-and-index-architecture]]"]
---

## Status

Approved. Implemented via [[PLAN-001-lessons-and-index-implementation]].

## Context

The original lessons subsystem instructed every agent "if something surprised you, create a lesson." After three months of dogfooding, the Compass project's own vault had 0 lessons and an empty catalog. The index also drifted stale: handoffs and specs got written, but the index lost track.

Root causes (per [[RESEARCH-lessons-and-index-architecture]]):

- In-flight introspection ("did anything surprise you?") asks the model to label its own surprise. Models either produce nothing or fabricate.
- Lesson creation was the last optional step in `builder.md`, `validator.md`, `reviewer.md`. Last conditional steps drop first under turn-budget pressure.
- Three-file write ceremony (lesson + catalog + index) created friction; partial completion was common.
- No dedup, so even when capture worked, lessons would proliferate into noise.
- Index updates relied on per-agent discipline. Agents skipped the trailing bullet.

Literature review across five reference codebases (HumanLayer, HF-Skills, ml-intern, hodor/ccode, claw-code) showed zero of five do per-agent in-flight capture. Automation beats agent discipline. Pre-write manifest dedup beats post-write similarity scoring.

## Decision

**Lessons are captured retrospectively at phase boundaries, via a single writer with closed shape, behind binary triggers and an anti-list.**

Six concrete mechanisms:

1. **Phase-boundary capture.** Extraction runs at the existing pause point in `/compass:build` (after a phase's tasks merge and the tester passes), and from a `Stop` hook as backstop. Never per-turn, never mid-task.
2. **Binary trigger gate.** Extractor runs only if at least one of these fired in the phase: fix-loop >=2, validator Deviation (problem), debug agent invoked, STOP-and-report, plan revised mid-phase. Otherwise it writes nothing without prompting introspection.
3. **Anti-list filter.** Adapted verbatim from `hodor/ccode` memdir. Eight buckets that disqualify content even if a trigger fired (code patterns, git history, debug recipes, framework docs, things already documented, personal style, things obvious once you know the tech, ephemeral state). "*These exclusions apply even when the user explicitly says to save.*"
4. **Single writer (`lesson-write`).** All paths (auto-extraction, `/compass:learned` manual capture, future imports) call one skill that injects the catalog as a dedup manifest, judges recurrence/refinement/new, and writes lesson + catalog + index atomically.
5. **Free-form 5-line body.** No template sections. Hard cap forces compression. The cap is the discipline.
6. **Self-healing via caps and consolidation.** Hard caps on `index.md` (200 lines), catalog, and `lessons/` count (50 files) write a visible WARNING when exceeded. `/compass:consolidate` runs only when a warning is present; merges near-duplicates, prunes baseline-score stale lessons, demotes verbose bodies.

## Alternatives considered

- **Keep per-agent in-flight capture, just reword.** Rejected: 0/5 reference projects use this pattern; our own dogfooding confirmed it produces 0 lessons.
- **`hodor/ccode`'s per-turn extraction.** Rejected: turn boundaries are too tight; a single turn rarely has a complete arc to learn from. Phase boundary is the natural retrospection point.
- **Manual-only capture via slash command.** Rejected as the *only* path: humans forget. `/compass:learned` stays as a companion path; auto-extraction is the primary path.
- **Embedding-based similarity dedup.** Rejected: introduces an embedding-model dependency for a problem that pre-write manifest already solves.
- **Templated body sections.** Rejected: the cap does the work; templates add ceremony without improving signal.

## Consequences

**Easier:**

- Lessons get written exactly when they're knowable (after the arc completes, not during).
- The anti-list gives the extractor explicit permission to write nothing, eliminating fabrication pressure.
- Single writer means the catalog and index can never drift from the on-disk lesson set.
- Hook-driven index sync removes per-agent index-update burden from every skill.
- Free-form bodies eliminate the "fill in 5 template sections" friction.

**Harder:**

- Hook reliability becomes load-bearing. If Claude Code hooks fail to fire or are disabled, the system regresses to manual.
- Phase boundary requires the build skill to persist phase reports to disk - new mechanical step.
- The anti-list is the single point of judgment; tuning it correctly takes runtime iteration.
- Hook config has surprise complexity (no `||` in `if`, prompt-type hooks can't invoke skills) - captured as lessons but a barrier to first install.

**Load-bearing risks:**

- If Stop hook doesn't fire reliably (e.g. in pure SDK usage without a CLI session), the backstop path is lost. The primary path through `/compass:build` still works.
- The 5-line body cap may prove too tight for genuinely complex lessons. Consolidation can then archive the over-tight one and re-author with permission to grow - the cap is a starting discipline, not an inviolable rule.
