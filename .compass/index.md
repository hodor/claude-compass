<!-- WARNING: hot path 7489 / 5000 tokens (index.md 3817, active.md 1111, meta/lessons-catalog.yaml 2561). Run /compass:consolidate before next session. -->
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
- [[RESEARCH-cache-theory-for-context-tiers]] - Cache Theory for Compass's Context Tiers: Tag/Data Split, Inclusion, and the Correctness of a Miss
- [[RESEARCH-decomposition-criteria-for-sizing]] - Decomposition Criteria for Sizing: No Metric Exists, Cheap Reversal Licenses Acting, and the Surviving Risk Is Social

## Plans

- [[PLAN-001-lessons-and-index-implementation]] - 12 tasks across 6 phases implementing SPEC-002 (done 2026-05-24)
- [[PLAN-003-hybrid-hierarchy]] - Hybrid Hierarchy Implementation (Unit Folders)
- [[PLAN-004-decision-coverage]] - Decision Coverage Implementation (D-NN Parser, Coverage Gate, Audit)
- [[PLAN-005-model-table]] - Model Resolution Table Implementation (Tiers, apply-models, Overrides)
- [[PLAN-006-learning-loop]] - Learning Loop Implementation: harness-owned capture, catalog retrieval, lesson coverage (approved 2026-08-05)
- [[PLAN-007-test-quality]] - Test Quality Instruments (Authoring Bar, Test-First Station, Admission Filter, Diagnostic Mutation)
- [[PLAN-008-rolling-wave]] - Rolling-Wave Plans (Detail Regions, Three-State Coverage, the Elaboration Loop)
- [[PLAN-009-sizing-mechanism]] - zero-artifact units, the sizing record, and the changeability walk (draft, awaiting approval)
- [[PLAN-009-sizing-mechanism]] - Sizing Mechanism (Zero-Artifact Units, the Sizing Record, and the Changeability Walk)

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
- [[ADR-010-identity-resident-fetch-mandatory]] - Identity Stays Resident, the Fetch Stops Being Optional, and Every Miss Is Counted
- [[ADR-011-sizing-is-a-procedure-not-a-score]] - Sizing Is a Judgment Procedure the Harness Triggers and Records, Never a Score

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
- [[LESSON-wikilink-validator-skip-code]] - Match use, not mention - matchers and edit anchors alike: bind to grammar position, never a substring prose repeats
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
- [[LESSON-hook-payloads-observe-before-coding]] - Observe the real emission or code path first; assumed shapes and reported causes ship dead work under a green suite
- [[LESSON-adversarial-plan-review-before-build]] - Review specs/plans with 3 adversarial lenses before approval, and have reviewers measure against the real corpus, not opine
- [[LESSON-pin-the-motivating-datum]] - When a spec cites a triggering observation, record its source (project, session, machine) at spec time; unpinned data become unfindable
- [[LESSON-dont-strip-agent-quality-stations]] - A blanket no-sub-agents ban in a spawn brief strips the builder's review station; twice violated, both violations caught real bugs
- [[LESSON-blind-the-author-in-self-validation]] - Blinding fails through the answer key and the vault's own hot path, not only shared roles; verify the rater is blind
- [[LESSON-suite-size-is-not-coverage]] - 44 tests for two behaviors carried mass redundancy and two critical holes at once; a delete list is half a review
- [[LESSON-revert-to-prove-a-regression-test]] - A test that passes without the change under test is unwritten; prove it per test, by revert after the fix or by the red run before it
- [[LESSON-remove-context-before-adding]] - Fix a behavior bug by removing the prose that trains it or adding a harness gate; added prose is the last resort and must be net-negative
- [[LESSON-walkthroughs-in-the-humans-words]] - A walkthrough carrying the work's own vocabulary stalls the ruling it exists to get; write it in plain words
- [[LESSON-human-practice-rationing-assumes-human-scarcity]] - Name the precondition a borrowed mechanism needs before importing it; mark every finding maps or metaphor
- [[LESSON-verify-the-inverse-not-the-forward-path]] - Cheap reversal licenses acting without asking; verify it on the inverse command, never by reading the forward one
- [[LESSON-score-the-do-nothing-baseline-before-running]] - Score the constant-answer baseline, fix the threshold, and check the stop verdict can fire and end the plan

## compass-cli
- [[compass-cli/decisions/ADR-005-compass-cli-for-mechanical-work]] - A Python `compass` CLI Owns All Mechanical Vault Work; the Hook Calls It as a Command
- [[compass-cli/plans/PLAN-002-compass-cli-implementation]] - Compass CLI Implementation
- [[compass-cli/research/RESEARCH-cli-and-hook-command-contract]] - How Claude Code Structures CLIs and the Command-Hook Contract
- [[compass-cli/research/RESEARCH-cli-token-reduction-measurement]] - Measuring SPEC-004's 80% Bookkeeping-Token Reduction
- [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]] - Mechanical Vault Work Must Not Cost Agent Tokens
