---
title: Decision Coverage via D-NN Bullets, a Three-Outcome Parser, and an Exit-Code Gate the Planner Honors
type: decision
status: approved
confidence: high
area: methodology
tags: [decision-coverage, parser, fail-loud, gates, planner, validator, cli]
created: 2026-07-24
updated: 2026-07-24
author: "roger + claude"
depends_on: ["[[SPEC-007-decision-coverage-tracing]]", "[[RESEARCH-decision-coverage-impl]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
summary: "Decision Coverage via D-NN Bullets, a Three-Outcome Parser, and an Exit-Code Gate the Planner Honors"
---

## Status

Approved. Implements [[SPEC-007-decision-coverage-tracing]] (binding spec decisions D-01..D-06).

## Context

[[RESEARCH-decision-coverage-impl]] found the authoring convention already emerging unprompted (`- **D-NN:**` bullets under `## Decisions` headings in SPEC-007/009), verified GSD's three-outcome parser mechanism against source, found bare `D-NN` collides across documents, and surfaced one contradiction: SPEC-007 D-03 wants a blocking gate, but the CLI clamps exit codes to never block a write (ADR-005 invariant). It also found live proof of the spec's premise: ADR-004 cites a PLAN-003 that does not exist.

## Decision

- **D-01:** The decision unit is `- **D-NN:** text` under a `## Decisions` / `## Decision` heading (regex `^#{2,3}\s*Decisions?\b`, case-insensitive), covering both spec Decisions sections and ADR Decision sections. IDs are plain `D-NN`, local to the document.
- **D-02:** Opt-outs: a `[informational]` or `[deferred]` bracket tag on the bullet, or placement under a discretion subheading, marks a decision non-trackable. It is parsed and recorded, never gate-checked.
- **D-03:** The parser is a Python port of the three-outcome contract: `parsed` / `none-present` / `could-not-parse`, with parse-miss poisoning (one malformed `- **D-` bullet forces `could-not-parse` even if others parsed) and decision-shape heuristics (a `D-` token or ID-shaped bold bullet with zero extractions means `could-not-parse`, never a silent pass). Fence stripping is a new `strip_fenced_code()` in vaultlib returning `(text, unterminated_fence)`; the existing validate fence toggle is not reused because it silently swallows content after an unterminated fence.
- **D-04:** Citations are source-qualified: `<doc-stem>/D-NN` (e.g. `SPEC-007-decision-coverage-tracing/D-03`), resolved through the same name resolution as validate. Bare `D-NN` citations are invalid; local IDs collide across documents by design.
- **D-05:** Tasks carry an optional `decisions: [...]` field, mirroring the existing `files:` convention. The default source set for a plan's coverage check derives from the plan's `depends_on` filtered to spec and decision types, which is exactly the spec's default roles with zero new ceremony.
- **D-06:** Command surface: `compass decisions <doc>` lists a document's decisions and exits 1 on `could-not-parse`; `compass coverage <plan> [--against <doc>...]` prints a coverage table and exits 1 on any uncovered trackable decision or unparseable source.
- **D-07:** The blocking gate is the planner honoring `compass coverage` exit 1 after human plan approval and before task distribution. The gate never lives in the PostToolUse hook; the never-block-a-write invariant of [[ADR-005-compass-cli-for-mechanical-work]] is untouched. The validator re-runs coverage report-only with a `Command run:` block and audits each task's cited IDs against the implementation.
- **D-08:** Migration is new-only (human decision). Existing ADRs parse as `none-present` (verified: zero D- tokens) and are not retrofitted; their plans are already done, so retrofit would produce only gate noise.
- **D-09:** The parser scans only declared sources (specs and decisions). Handoff `## Decisions` sections are out of scope until a deliberate decision brings them in; the heading regex would match them, so scoping is explicit.

## Alternatives considered

- **Globally unique decision IDs (D-AREA-NN or vault-wide numbering).** Rejected: contradicts the local-numbering philosophy of [[ADR-003-drop-counter-file-jit-compute]]; source-qualification gives uniqueness without a registry.
- **Gate as a hook.** Rejected: the CLI structurally never exits 2, and a coverage failure must never block a vault write; the gate belongs at the planner's distribution step.
- **Frontmatter decision lists instead of body bullets.** Rejected: decisions are prose-adjacent; duplicating them into frontmatter invites drift, and the emergent convention is already body bullets.
- **Retrofitting the 5 existing ADRs.** Rejected by the human: no live plan could cover them; pure noise.

## Consequences

**Easier:** dropped decisions surface before build with file-precise output; the validator gets a per-task audit checklist; the convention costs one bold prefix on bullets already being written.

**Harder:** the planner skill and plan template must learn the `decisions:` field and the coverage step; spec/obsidian templates must document the D-NN convention; a config seam must exist for [[SPEC-009-configurable-pipeline-workflows]] to later rebind sources, targets, and the gating transition (spec D-05/D-06) without rework.

## Load-bearing risks

- If the parser's could-not-parse heuristics are too eager, authors will see false format-mismatch failures and route around the convention; the heuristics ship with a test corpus drawn from the real vault.
- The planner honoring an exit code is prose-enforced until SPEC-009's gate rail exists; this is the one deliberate prompt-side link in the chain and is flagged for hardening.
