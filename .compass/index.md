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

## Research

- [[RESEARCH-lessons-and-index-architecture]] - literature review across 5 reference codebases on capture timing, index freshness, dedup, and lesson shape
- [[RESEARCH-evaluation-benchmarks]] - benchmarks for evaluating Compass methodology layer; A/B pitfalls; field-gap analysis
- [[RESEARCH-scientific-method-in-compass]] - does Compass actually embody the scientific method, or only borrow the vocabulary; 8 specific gaps with file:line evidence
- [[RESEARCH-hierarchical-knowledge-base-design]] - MemGPT/RAPTOR/faceted-classification synthesis, 11 findings
- [[RESEARCH-okf-improvements-for-compass]] - OKF: adopt resource field + reader tolerance, skip format alignment
- [[RESEARCH-rag-fit-for-large-vaults]] - RAG net-negative below ~300-500 docs; lexical rung first
- [[RESEARCH-gsd-core-improvements-for-compass]] - GSD competitive read: decision coverage, model policy, prior art for SPEC-006
- [[RESEARCH-decision-coverage-impl]] - Decision Coverage Implementation: Format, Parser, Matcher, Gate, Migration
- [[RESEARCH-hybrid-hierarchy-impl]] - Hybrid Hierarchy Implementation Impact: CLI, Skills, Wikilinks, Migration
- [[RESEARCH-model-resolution-impl]] - Model Resolution Table: Current State, Mechanism, and Implementation Options
- [[RESEARCH-hermes-agent-capabilities]] - hermes-agent (NousResearch): Capabilities and Extension Surface, Source-Verified
- [[RESEARCH-hermes-vs-compass-fit]] - Hermes Agent vs Compass: Fit, Feasibility, and Strategic Options
- [[RESEARCH-graph-engineering-for-compass]] - Graph Engineering for Compass - Landscape, Prior Art, and Gap Analysis
- [[RESEARCH-lesson-capture-failure]] - Why Lesson Capture Almost Never Happens (40-Vault Fleet Diagnosis)
- [[RESEARCH-hermes-memory-mechanics]] - hermes-agent: Memory Update and Retrieval Mechanics, Deep-Dive
- [[RESEARCH-grep-vs-graph-experiment]] - SPEC-011 gate: 2 classes solved, 2 marginal, health analytics grep-insufficient
- [[RESEARCH-test-quality-literature]] - Test-Suite Quality Measurement and LLM Test-Generation Literature
- [[RESEARCH-test-quality-empirical]] - Empirical Grade of Compass's Own CLI Test Suite Against the D-01 Admission Bar
- [[RESEARCH-test-quality-tooling]] - Test Quality Tooling - Mutation Testing, Cheaper Signals, and Windows/Stdlib Fit
- [[RESEARCH-test-quality-synthesis]] - three instruments reconciled; station model recommendation
- [[RESEARCH-test-quality-craft-and-practice]] - Test Craft and AI Testing Practice: The Missing Axis
- [[RESEARCH-fleet-test-census]] - Fleet Test Census - Locating and Grading the 841-Test Project
- [[RESEARCH-test-quality-bar-validation]] - Paired Seeded-Defect Validation of the Test-Design Admission Bar

## Plans

- [[PLAN-001-lessons-and-index-implementation]] - 12 tasks across 6 phases implementing SPEC-002 (done 2026-05-24)
- [[PLAN-003-hybrid-hierarchy]] - Hybrid Hierarchy Implementation (Unit Folders)
- [[PLAN-004-decision-coverage]] - Decision Coverage Implementation (D-NN Parser, Coverage Gate, Audit)
- [[PLAN-005-model-table]] - Model Resolution Table Implementation (Tiers, apply-models, Overrides)
- [[PLAN-006-learning-loop]] - Learning Loop Implementation: harness-owned capture, catalog retrieval, lesson coverage (approved 2026-08-05)
- [[PLAN-007-test-quality]] - Test Quality Instruments (Authoring Bar, Test-First Station, Admission Filter, Diagnostic Mutation)

## Decisions

- [[ADR-001-methodology-as-skill-with-vault]] - Methodology lives in a skill; project state in per-project `.compass/` Obsidian-compatible vault
- [[ADR-002-retrospective-lessons-subsystem]] - Retrospective lesson capture at phase boundary with binary triggers, anti-list, and single writer
- [[ADR-003-drop-counter-file-jit-compute]] - Drop `meta/config.yaml` counter file; compute next artifact number JIT from filesystem
- [[ADR-004-hierarchical-specs-with-facets]] - 3-tier MemGPT memory + folder hierarchy + faceted tags + admission control; hot path at prompt start
- [[ADR-006-hybrid-hierarchy-implementation]] - Unit Folders at the Vault Root, Classified by Reserved Names Plus a Marker
- [[ADR-007-decision-coverage-mechanism]] - Decision Coverage via D-NN Bullets, a Three-Outcome Parser, and an Exit-Code Gate the Planner Honors
- [[ADR-008-model-resolution-table]] - Abstract Model Tiers Resolved at Install Time by compass apply-models

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

## Lessons

- [[LESSON-glob-hidden-dirs-prefix]] - Glob tool needs `**/` prefix to traverse hidden dirs like .compass/
- [[LESSON-hook-if-clause-no-or]] - Settings hook entries have no `if` clause; select tools via matcher, filter paths in the command
- [[LESSON-hook-type-prompt-no-skills]] - Hook `type: prompt` is single-shot; cannot call Skill tool; use `type: agent` instead
- [[LESSON-no-agent-bookkeeping]] - Mechanical bookkeeping (counters, indexes, catalogs) belongs in scripts/hooks/JIT, not agent steps
- [[LESSON-wikilink-validator-skip-code]] - Wikilink validators must skip fenced code blocks AND inline code spans; example refs in docs are noise
- [[LESSON-test-driven-tasks-dont-discriminate]] - When tests fully encode the spec, frontier models already read-tests-first; methodology can't be measured on such tasks
- [[LESSON-windows-crlf-breaks-linux-container-scripts]] - Python `open(p, 'w')` on Windows writes CRLF; mount that into a Linux container and bash chokes on $'\r'
- [[LESSON-tag-index-trades-cost-for-directed-retrieval]] - Tag index gives directed retrieval and faster wall-time; token cost depends on query shape; SPEC-003's 30% claim falsified on N=1
- [[LESSON-autocrlf-churns-lf-writers]] - With core.autocrlf=true and no .gitattributes, git checks files out as CRLF; a tool that writes LF rewrites them every run, causing perpetual diffs
- [[LESSON-hook-cli-gate-stdin-on-flag]] - Gate hook-stdin reads behind an explicit flag (--hook), not isatty probing; probing blocks forever in a non-interactive shell with no piped input
- [[LESSON-type-dir-discovery-needs-content-signal]] - Treating every .compass subdir as an artifact type dir breaks on vaults that store non-artifact dirs there; require the known core dirs OR a typed-artifact signal
- [[LESSON-installer-removes-only-what-it-installed]] - A tool that installs into a shared dir must delete only its own named artifacts on cleanup; 'remove anything not in my source' destroys user files
- [[LESSON-long-agents-stall-resume-them]] - A subagent completion notice whose final text reads like mid-task narration is a stall, not a result; resume it with 'continue from exactly where you stopped' instead of respawning
- [[LESSON-subagent-worktrees-fork-stale]] - Worktree-isolated subagents fork from a pre-session commit; without a fast-forward to master and committed prior waves, they see a world where earlier work does not exist
- [[LESSON-hooks-load-only-from-settings]] - Hooks load only from settings-file hooks keys or registered plugins; a bare .claude/hooks/hooks.json never fires
- [[LESSON-subagent-reports-need-sendmessage]] - A spawned agent's final plain text is invisible to its orchestrator; briefs must mandate an explicit SendMessage delivery
- [[LESSON-append-only-index-misses-mutations]] - Append-only derived indexes miss source mutations; the mutator must update the row or the field never propagates
- [[LESSON-scratch-vaults-need-compass-dir]] - CLAUDE_PROJECT_DIR redirects the compass CLI only when it contains .compass; otherwise cwd-walk silently targets the enclosing vault
- [[LESSON-hook-payloads-observe-before-coding]] - Capture one real event payload (tee to a file) before keying logic on its fields; assumed shapes ship dead code
- [[LESSON-adversarial-plan-review-before-build]] - Review specs/plans with 3 adversarial lenses before approval, and have reviewers measure against the real corpus, not opine
- [[LESSON-pin-the-motivating-datum]] - When a spec cites a triggering observation, record its source (project, session, machine) at spec time; unpinned data become unfindable
- [[LESSON-dont-strip-agent-quality-stations]] - A blanket no-sub-agents ban in a spawn brief strips the builder's review station; twice violated, both violations caught real bugs
- [[LESSON-blind-the-author-in-self-validation]] - One agent that both replays the seeded defects and authors the arm under test measures itself, not the mechanism
- [[LESSON-suite-size-is-not-coverage]] - 44 tests for two behaviors carried mass redundancy and two critical holes at once; a delete list is half a review
- [[LESSON-revert-to-prove-a-regression-test]] - A regression test that still passes on the reverted fix is vacuous; revert and re-run every new test before shipping
- [[LESSON-remove-context-before-adding]] - Fix a behavior bug by removing the prose that trains it or adding a harness gate; added prose is the last resort and must be net-negative

## compass-cli
- [[compass-cli/decisions/ADR-005-compass-cli-for-mechanical-work]] - A Python `compass` CLI Owns All Mechanical Vault Work; the Hook Calls It as a Command
- [[compass-cli/plans/PLAN-002-compass-cli-implementation]] - Compass CLI Implementation
- [[compass-cli/research/RESEARCH-cli-and-hook-command-contract]] - How Claude Code Structures CLIs and the Command-Hook Contract
- [[compass-cli/research/RESEARCH-cli-token-reduction-measurement]] - Measuring SPEC-004's 80% Bookkeeping-Token Reduction
- [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]] - Mechanical Vault Work Must Not Cost Agent Tokens
