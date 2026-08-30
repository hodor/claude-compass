<!-- WARNING: hot path 7697 / 5000 tokens (index.md 4111, active.md 381, meta/lessons-catalog.yaml 3205). Run /compass:consolidate before next session. -->
<!-- WARNING: index.md exceeded hot-path cap. Run /compass:consolidate before next session. -->
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
- [[SPEC-002-lessons-and-index-subsystem]] - Lessons capture, dedup, anti-list, and index freshness mechanism (approved)
- [[SPEC-003-hierarchical-vault-organization]] - hierarchical folders + faceted tags + 3-tier memory (approved)
- [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] - Index Auto-Maintained on Add and Remove, Mirrored Per Folder
- [[SPEC-006-multi-host-agent-cli-support]] - Compass runs on agent CLIs beyond Claude Code (Kimi Code, Codex); problem/need (approved 2026-07-22)
- [[SPEC-007-decision-coverage-tracing]] - decisions made in specs/ADRs must survive into plans and validation, not silently vanish between stages (approved 2026-07-23)
- [[SPEC-008-central-model-resolution-table]] - model + effort assignment is one harness-resolved policy table with per-project override, not per-agent prose (approved 2026-07-23)
- [[SPEC-009-configurable-pipeline-workflows]] - the pipeline is a configurable workflow (shipped default + reorder/subset/extend), not one hardcoded sequence (draft, DEFERRED)
- [[SPEC-010-universal-hybrid-hierarchy]] - any artifact and unit of work can nest; unit folders (approved 2026-07-23)
- [[SPEC-011-vault-graph-queries]] - orphans + hub ranking + impact traversal with planner consumer (approved 2026-08-05)
- [[SPEC-012-learning-loop]] - capture on real events, retrieval at the work, application audited (approved, SHIPPED v0.5.0)
- [[SPEC-013-test-quality]] - per-test admission bar; suite size an outcome, never a target (approved 2026-08-07)
- [[SPEC-014-update-safe-customizations]] - Project-Local Workflow Customizations Survive Update
- [[SPEC-015-rolling-wave-planning]] - plan detail tracks proximity; waves elaborate from completed-task knowledge (draft)
- [[SPEC-016-sizing-work-beyond-one-spec]] - work too big for one spec gets the bigger shape without the human knowing the machinery (approved 2026-08-23)
- [[SPEC-017-capabilities-are-reachable-and-measured]] - a capability no skill names is unreachable, and nothing counts usage so dead ones go unnoticed (approved 2026-08-23)
- [[SPEC-018-scaffolding-invisible-to-the-human]] - the machinery keeps running but none of it occupies the human's conversation (approved 2026-08-24)
- [[SPEC-019-active-holds-only-active-work]] - completed work accumulates in active.md forever because nothing in the harness moves it out; the hot path pays for history on every turn
- [[SPEC-020-compass-updates-itself]] (folder, 0 children) - a project's Compass install refreshes itself from the canonical repo at session start - mandatory, zero tokens, silent when current (approved 2026-08-28)
- [[SPEC-021-capture-in-the-humans-words]] - spec/vision interviews rewrite what the human said into polished agent prose; the human's own sentences must survive into the documents, with agent additions marked (approved 2026-08-28)
- [[SPEC-022-vault-organized-per-domain]] - similar specs and research group into domain folders, recursively; the root index says one line per broad area instead of dropping every artifact flat (approved 2026-08-30)

## Research

- [[RESEARCH-lessons-and-index-architecture]] - capture timing, index freshness, dedup, lesson shape across 5 codebases
- [[RESEARCH-evaluation-benchmarks]] - benchmarks for the methodology layer; A/B pitfalls; field gaps
- [[RESEARCH-scientific-method-in-compass]] - does Compass embody the scientific method or borrow its vocabulary; 8 gaps
- [[RESEARCH-hierarchical-knowledge-base-design]] - MemGPT/RAPTOR/faceted-classification synthesis, 11 findings
- [[RESEARCH-okf-improvements-for-compass]] - adopt resource field + reader tolerance, skip format alignment
- [[RESEARCH-rag-fit-for-large-vaults]] - RAG net-negative below ~300-500 docs; lexical rung first
- [[RESEARCH-gsd-core-improvements-for-compass]] - decision coverage, model policy, prior art for SPEC-006
- [[RESEARCH-decision-coverage-impl]] - format, parser, matcher, gate, migration
- [[RESEARCH-hybrid-hierarchy-impl]] - CLI, skills, wikilinks, migration impact
- [[RESEARCH-model-resolution-impl]] - current state, mechanism, implementation options
- [[RESEARCH-hermes-agent-capabilities]] - hermes capabilities and extension surface, source-verified
- [[RESEARCH-hermes-vs-compass-fit]] - fit, feasibility, strategic options
- [[RESEARCH-graph-engineering-for-compass]] - landscape, prior art, gap analysis
- [[RESEARCH-lesson-capture-failure]] - why capture almost never happens (40-vault diagnosis)
- [[RESEARCH-hermes-memory-mechanics]] - memory update and retrieval mechanics, deep-dive
- [[RESEARCH-grep-vs-graph-experiment]] - SPEC-011 gate: 2 classes solved, 2 marginal, health analytics grep-insufficient
- [[RESEARCH-test-quality-literature]] - suite-quality measurement and LLM test-generation literature
- [[RESEARCH-test-quality-empirical]] - the CLI's own suite graded against the D-01 bar
- [[RESEARCH-test-quality-tooling]] - mutation testing, cheaper signals, Windows/stdlib fit
- [[RESEARCH-test-quality-synthesis]] - three instruments reconciled; station model recommendation
- [[RESEARCH-test-quality-craft-and-practice]] - test craft and AI testing practice, the missing axis
- [[RESEARCH-fleet-test-census]] - locating and grading the 841-test project
- [[RESEARCH-test-quality-bar-validation]] - paired seeded-defect validation of the admission bar
- [[RESEARCH-rolling-wave-agent-planning]] - receding-horizon planning when planner and executor are LLMs
- [[RESEARCH-rolling-wave-software-practice]] - how methodologies operationalize the detail gradient
- [[RESEARCH-rolling-wave-flow-theory]] - flow and lean product-development theory behind it
- [[RESEARCH-rolling-wave-synthesis]] - cross-axis synthesis and recommended mechanism
- [[RESEARCH-cache-theory-for-context-tiers]] - tag/data split, inclusion cost, and why a hardware miss cannot cost correctness
- [[RESEARCH-decomposition-criteria-for-sizing]] - no sizing metric exists; cheap reversal licenses acting early; the surviving risk is lock-in
- [[RESEARCH-invisible-scaffolding]] - detached hook-spawned workers survive (verified live); additionalContext wakes the model without rendering
- [[RESEARCH-active-set-prior-art]] - every mature system bounds its active set mechanically - flag-then-sweep dominates, atomic moves are rare, and Compass already owns the zero-token trigger (PostToolUse compass sync)
- [[RESEARCH-self-update-surfaces]] - the whole update flow is already mechanical (clone, copy, settings merge, apply-models, plugin.yaml record); SessionStart startup-matcher is the right trigger; a stored commit sha makes the current-check one ls-remote
- [[RESEARCH-humans-words-fidelity]] - verbosity and paraphrase infidelity are documented, mechanistic LLM failures; every source-word discipline shares one grammar (verbatim layer + bracketed insertions + speaker sign-off); positive extract-and-quote instructions beat do-not-paraphrase prohibitions
- [[RESEARCH-update-safe-customization]] - overlay mechanisms are well-charted (drop-in dirs dominate, patches fail loudest, markers fail silently), but SPEC-014's benchmark corpus does not exist: zero content customizations survive and models.yaml is adopted nowhere
- [[RESEARCH-taxonomy-for-unambiguous-placement]] - filers inherently disagree (10-60% consistency), so unambiguity is engineered on the finder's side: few broad human-curated top levels, scope notes, one primary home plus facet cross-refs, corpus-warranted categories; five named codebase gaps

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
- [[ADR-002-retrospective-lessons-subsystem]] - Retrospective lesson capture at phase boundary with binary triggers, anti-list, and single writer
- [[ADR-003-drop-counter-file-jit-compute]] - Drop `meta/config.yaml` counter file; compute next artifact number JIT from filesystem
- [[ADR-004-hierarchical-specs-with-facets]] - 3-tier MemGPT memory + folder hierarchy + faceted tags + admission control; hot path at prompt start
- [[ADR-006-hybrid-hierarchy-implementation]] - Unit Folders at the Vault Root, Classified by Reserved Names Plus a Marker
- [[ADR-007-decision-coverage-mechanism]] - Decision Coverage via D-NN Bullets, a Three-Outcome Parser, and an Exit-Code Gate the Planner Honors
- [[ADR-008-model-resolution-table]] - Abstract Model Tiers Resolved at Install Time by compass apply-models
- [[ADR-009-rolling-wave-mechanism]] - frontier waves, grounded elaboration at the merge gate, three-state coverage (detailed/scoped/uncovered)
- [[ADR-010-identity-resident-fetch-mandatory]] - identity stays resident, the lessons fetch stops being optional, every miss is counted
- [[ADR-011-sizing-is-a-procedure-not-a-score]] - the changeability walk, harness-triggered and recorded; no sizing metric ships
- [[ADR-012-test-checkpoint-py-membership-git-authoritative]] - `.py` membership in `test-checkpoint verify` stays git-authoritative; a bundled non-`.py` file is classified only when recorded
- [[ADR-013-detached-worker-quiet-fallback]] - capture runs in a detached worker; additionalContext is the fallback; every run recorded
- [[ADR-014-active-sweep-on-sync]] - sync gains a sweep step: done task lines leave active.md mechanically on every sync, whole sections move when fully done, records land verbatim in archive/done.md, validate warns on drift
- [[ADR-015-self-update-on-session-start]] - SessionStart(startup) runs compass self-update: ls-remote sha gate, clone-and-apply replicating the update skill mechanically, dev repos copy from local plugin/, one context line on update, silence and exit 0 on every failure
- [[ADR-016-capture-by-extraction]] - interview skills switch from synthesize-a-draft to extract-and-arrange: the human's sentences carry the capture sections, agent additions bracketed, uncertain words flagged never substituted, brevity binds only agent prose
- [[ADR-017-capability-index-and-usage-record]] - bare compass is the progressive-disclosure index made reachable by one rule line; dispatch records every invocation; compass usage lists never-used commands explicitly; clean-tmp and tree retire; admission control's fate decided by data
- [[ADR-018-graph-queries-jit-over-markdown]] - no derived store: compass graph parses edges at query time so staleness cannot exist; orphans/hubs/impact ship wired into vault-health, checkup, unit-check's hub guard, and a planner ripple step
- [[ADR-019-subagentstop-redelivery-and-teammate-typing]] - live payload observation falsifies the dead-code claim (inline spawns are typed, teammates are not) and reveals SubagentStop double-delivery, now deduped on agent_id
- [[ADR-020-local-overlays-appended-after-refresh]] - concatenation over splicing: update copies the shipped file pristine then appends the project's local addendum, so no anchor can drift; CLAUDE.md stays untouched and is proven so by test
- [[ADR-021-index-speaks-in-domains]] - sync stops listing folder children in the root index - the folder line with its child count is the pointer; taxonomize retires into consolidate as its Structure pass; the migration itself is a proposal the human approves
- [[ADR-022-domains-scope-notes-shallow-when-unsure]] - every folder's doc is index.md, type dirs included; generated surfaces emit piped full-path links so they click through in Obsidian

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

## Lessons

Indexed in meta/lessons-catalog.yaml (loaded with the hot path); files in `lessons/`, archived ones in `archive/lessons/`.

## compass-cli
- [[compass-cli/decisions/ADR-005-compass-cli-for-mechanical-work]] - A Python `compass` CLI Owns All Mechanical Vault Work; the Hook Calls It as a Command
- [[compass-cli/plans/PLAN-002-compass-cli-implementation]] - Compass CLI Implementation
- [[compass-cli/research/RESEARCH-cli-and-hook-command-contract]] - How Claude Code Structures CLIs and the Command-Hook Contract
- [[compass-cli/research/RESEARCH-cli-token-reduction-measurement]] - Measuring SPEC-004's 80% Bookkeeping-Token Reduction
- [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]] - Mechanical Vault Work Must Not Cost Agent Tokens
