---
title: Compass Plugin — Project Index
project: compass
created: 2026-03-12
updated: 2026-05-24
status: active
---

# Compass — Project Index

Compass is a Claude Code plugin that provides an AI-guided development workflow with per-project Obsidian-compatible knowledge vaults.

## Project Structure

- `plugin/` — the installable plugin source (agents, skills, plugin.json)
- `.compass/` — this vault, the project's own development context

## Specs

- [[SPEC-001-compass-vision-and-architecture]] — Core vision, principles, architecture, and resolved design decisions
- [[SPEC-017-capabilities-are-reachable-and-measured]] - a capability no skill names is unreachable, and nothing counts usage so dead ones go unnoticed (approved 2026-08-23)
- [[SPEC-018-scaffolding-invisible-to-the-human]] - the machinery keeps running but none of it occupies the human's conversation (approved 2026-08-24)
- [[specs/distribution/index|distribution]] (folder, 4 children) - how Compass reaches and stays current in projects - installs, updates, host CLIs, model resolution
- [[specs/learning/index|learning]] (folder, 3 children) - how knowledge is captured and fed back - lessons, the capture loop, fidelity to the human's words
- [[specs/pipeline/index|pipeline]] (folder, 4 children) - the development workflow itself - stages, their ordering, how plans elaborate, what each stage must carry forward
- [[specs/vault-structure/index|vault-structure]] (folder, 7 children) - how the vault organizes, bounds, and retrieves its own memory - hierarchy, indexes, graph queries, active-set sweeping, sizing shapes, domain taxonomy

## Research

- [[RESEARCH-evaluation-benchmarks]] - benchmarks for the methodology layer; A/B pitfalls; field gaps
- [[RESEARCH-scientific-method-in-compass]] - does Compass embody the scientific method or borrow its vocabulary; 8 gaps
- [[RESEARCH-decision-coverage-impl]] - format, parser, matcher, gate, migration
- [[research/distribution/index|distribution]] (folder, 4 children) - evidence on shipping and updating Compass across projects and hosts, and prior-art reviews of rival frameworks (GSD)
- [[research/hermes/index|hermes]] (folder, 3 children) - the hermes host - capabilities, memory mechanics, fit with Compass
- [[research/learning/index|learning]] (folder, 4 children) - evidence on capturing knowledge - lesson mechanics, capture failure, detached workers, source-word fidelity
- [[research/rolling-wave/index|rolling-wave]] (folder, 4 children) - plan detail tracking proximity - receding horizons, flow theory, practice
- [[research/test-quality/index|test-quality]] (folder, 7 children) - what makes a test suite good and how to measure it
- [[research/vault-structure/index|vault-structure]] (folder, 10 children) - evidence on organizing and retrieving vault memory - hierarchy, tiers, RAG, graphs, taxonomy

## Plans

- [[PLAN-001-lessons-and-index-implementation]] - 12 tasks across 6 phases implementing SPEC-002 (done 2026-05-24)
- [[PLAN-003-hybrid-hierarchy]] - Hybrid Hierarchy Implementation (Unit Folders)
- [[PLAN-004-decision-coverage]] - Decision Coverage Implementation (D-NN Parser, Coverage Gate, Audit)
- [[PLAN-005-model-table]] - Model Resolution Table Implementation (Tiers, apply-models, Overrides)
- [[PLAN-006-learning-loop]] - Learning Loop Implementation: harness-owned capture, catalog retrieval, lesson coverage (approved 2026-08-05)
- [[PLAN-007-test-quality]] - Test Quality Instruments (Authoring Bar, Test-First Station, Admission Filter, Diagnostic Mutation)
- [[PLAN-008-rolling-wave]] - Rolling-Wave Plans (Detail Regions, Three-State Coverage, the Elaboration Loop)
- [[PLAN-009-sizing-mechanism]] - zero-artifact units, the sizing record, and the changeability walk (draft, awaiting approval)
- [[PLAN-010-invisible-capture]] - capture moves off the conversation into a hook-spawned detached worker, with recorded runs, dead-worker detection, a quiet fallback, and a live-fire acceptance
- [[PLAN-011-active-sweep]] - implement ADR-014: sweep module with dry-run CLI command, wired into sync, validate drift warning, builder/build/checkup doc updates, live acceptance on this vault
- [[PLAN-012-self-update]] - implement ADR-015: self_update command with sha gate and local-source mode, SessionStart(startup) hook entry, setup/update skill alignment, live acceptance in this repo
- [[PLAN-013-capture-by-extraction]] - implement ADR-016 across spec/vision/specs/retroactive skills and the pipeline rules; ship via push + fleet self-update
- [[PLAN-014-capability-usage]] - implement ADR-017: usage recording in dispatch, usage report, doctor advisory, retirements, reachability line; ship v0.12.0
- [[PLAN-015-graph-queries]] - implement ADR-018: graphlib, compass graph, consumer wiring, ripple step; live validation; v0.13.0
- [[PLAN-016-domain-taxonomy]] - implement ADR-022 in two waves: mechanism first (Contents sync + loop-guard fix, make-domain, validate ceiling + link rules, skill contracts), then the human-approved migration of this vault; live acceptance is a filer drill and a finder drill on the migrated vault

## Decisions

- [[ADR-001-methodology-as-skill-with-vault]] - Methodology lives in a skill; project state in per-project `.compass/` Obsidian-compatible vault
- [[ADR-017-capability-index-and-usage-record]] - bare compass is the progressive-disclosure index made reachable by one rule line; dispatch records every invocation; compass usage lists never-used commands explicitly; clean-tmp and tree retire; admission control's fate decided by data
- [[decisions/distribution/index|distribution]] (folder, 3 children) - rulings on installing, updating, and configuring Compass across projects
- [[decisions/learning/index|learning]] (folder, 5 children) - rulings on capture and feedback - lessons, workers, signal handling, source-word fidelity
- [[decisions/pipeline/index|pipeline]] (folder, 3 children) - rulings on the development workflow stages and gates
- [[decisions/vault-structure/index|vault-structure]] (folder, 8 children) - rulings on how the vault organizes, bounds, and retrieves its own memory

## Active Work

See [[active]].

## Backlog

See [[backlog]].

## Handoffs

- [[2026-03-12_review-all-plugin-files]] — File-by-file review of all 21 plugin files (active)
- [[2026-03-12_23-50-59_session-3-skills-approved]] — All 3 skills approved, duplication audit complete
- [[2026-03-12_session-2-obsidian-approved]] - Handoff: Obsidian skill fully reviewed, HumanLayer insights adopted
- [[2026-06-10_23-00-00_python-cli-next-up]] - Handoff: Python busywork CLI is next; everything through ADR-004 shipped
- [[2026-06-19_10-33-39_cli-shipped-spec005-on-hold]] - Handoff: compass CLI shipped (v0.3.7); SPEC-005 (auto per-folder index + LLM summaries) drafted, ON HOLD
- [[2026-08-05_19-27-13_learning-loop-diagnosed-spec012-next]] - lesson capture root-caused; SPEC-012 queued
 - [[2026-08-06_06-02-00_phase2-live-hooks-first-firing]] - Handoff: PLAN-006 Phase 2 live; hooks fire from settings.json for the first time ever
- [[2026-08-24_15-00-03_v0.8.1-invisible-capture-shipped]] - two initiatives shipped end to end and distributed to 50 vaults; hot-path tiering (ADR-010) is the next plan
- [[2026-08-29_20-30-00_five-releases-queue-at-human-gates]] - five specs shipped end to end (active sweep, self-update, capture-by-extraction, capability usage, graph queries), fleet self-updating; next: SPEC-006 research session, SPEC-014 promotion ruling, SubagentStop payload observation
  - [[handoffs/PLAN-016-domain-taxonomy/2026-08-30_16-47-06_wave1-tree-uncommitted]] - PLAN-016 Wave 1 committed through TASK-118; TASK-116 (compass tree) sits on disk with its tests, suite unrun, uncommitted; Wave 2 starts at the useless-token baseline
  - [[handoffs/PLAN-016-domain-taxonomy/2026-08-30_17-31-12_v0.16-vault-migrated]] - PLAN-016 complete plus D-14: the whole vault lives in domains, lessons load through the index hierarchy instead of the catalog, hot path 3,269/5,000 - under cap for the first time (v0.17.0 fleet-verified); open: TASK-119 (prove the measure), D-13 grep-first follow-up

## Lessons

Indexed in meta/lessons-catalog.yaml (loaded with the hot path); files in `lessons/`, archived ones in `archive/lessons/`.

## compass-cli
- [[compass-cli/decisions/ADR-005-compass-cli-for-mechanical-work]] - A Python `compass` CLI Owns All Mechanical Vault Work; the Hook Calls It as a Command
- [[compass-cli/plans/PLAN-002-compass-cli-implementation]] - Compass CLI Implementation
- [[compass-cli/research/RESEARCH-cli-and-hook-command-contract]] - How Claude Code Structures CLIs and the Command-Hook Contract
- [[compass-cli/research/RESEARCH-cli-token-reduction-measurement]] - Measuring SPEC-004's 80% Bookkeeping-Token Reduction
- [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]] - Mechanical Vault Work Must Not Cost Agent Tokens
