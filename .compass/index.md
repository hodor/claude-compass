<!-- WARNING: hot path 5644 / 5000 tokens (index.md 4039, active.md 915, lessons/index.md 690). Run /compass:consolidate before next session. -->
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
- [[specs/distribution/index|distribution]] (folder, 4 children) - how Compass reaches and stays current in projects - installs, updates, host CLIs, model resolution
- [[specs/learning/index|learning]] (folder, 7 children) - how knowledge is captured and fed back - lessons, the capture loop, fidelity to the human's words
- [[specs/pipeline/index|pipeline]] (folder, 11 children) - the development workflow itself - stages, their ordering, how plans elaborate, what each stage must carry forward
- [[specs/vault-structure/index|vault-structure]] (folder, 7 children) - how the vault organizes, bounds, and retrieves its own memory - hierarchy, indexes, graph queries, active-set sweeping, sizing shapes, domain taxonomy
- [[specs/tooling/index|tooling]] (folder, 3 children) - Compass's own machinery as a surface - capabilities reachable and measured, scaffolding invisible to the human
- [[specs/human-surface/index|human-surface]] (folder, 4 children) - how Compass puts things in front of the human: the questions it asks, the documents it hands over for review, and how all of it reads

## Research

- [[research/distribution/index|distribution]] (folder, 6 children) - evidence on shipping and updating Compass across projects and hosts, and prior-art reviews of rival frameworks (GSD)
- [[research/hermes/index|hermes]] (folder, 11 children) - the hermes host - capabilities, memory mechanics, fit with Compass
- [[research/learning/index|learning]] (folder, 7 children) - evidence on capturing knowledge - lesson mechanics, capture failure, detached workers, source-word fidelity
- [[research/rolling-wave/index|rolling-wave]] (folder, 4 children) - plan detail tracking proximity - receding horizons, flow theory, practice
- [[research/test-quality/index|test-quality]] (folder, 8 children) - what makes a test suite good and how to measure it
- [[research/vault-structure/index|vault-structure]] (folder, 10 children) - evidence on organizing and retrieving vault memory - hierarchy, tiers, RAG, graphs, taxonomy
- [[research/pipeline/index|pipeline]] (folder, 17 children) - evidence on the pipeline as a method - benchmarks, scientific rigor, decision-coverage mechanics
- [[research/human-surface/index|human-surface]] (folder, 12 children) - how Compass puts things in front of the human: the questions it asks, the documents it hands over for review, and how all of it reads
- [[RESEARCH-review-in-obsidian]] - a small Obsidian plugin takes the verdict and returns the human; proven on Windows; ranks Compass features for an Obsidian UI
- [[RESEARCH-review-mockup]] - the review lives in one side panel that follows the human through links
- [[RESEARCH-llm-research-for-compass]] - approved axes for surveying Anthropic's engineering posts and 2025-2026 LLM agent research for changes Compass should make; axis findings in research/llm-research/
- [[research/whole-overhead/index|whole-overhead]] (folder, 19 children) - evidence on measuring Compass's whole token overhead on projects agents build, and cutting it biggest area first
  - [[research/whole-overhead/checking-cost/index|checking-cost]] (folder) - research for SPEC-034: how Compass sizes tasks, what its checking stations cost per task, and how a part-by-part re-baseline on a model change would run
  - [[research/llm-research/RESEARCH-axis-6-harness-engineering]] - What OpenAI, Manus, Cursor, Cognition, Amp, Factory, OpenHands, Cline, Gemini CLI and a 2026 source-code survey say about harness design, checked against what Compass already does; reports only what the earlier context prior-art review did not cover
  - [[research/llm-research/RESEARCH-axis-2-host-features]] - Claude Code 2.1.330 hook, skill, subagent, plugin, memory and compaction features mapped against Compass hooks, CLI and skills; first pass, API-side features pending
  - [[research/llm-research/RESEARCH-axis-3-agent-memory]] - 2025-2026 agent-memory papers against Compass's hot path, 5-line lessons and consolidation: helpful/harmful counters, delta-only curation, masking over summarizing, length-alone degradation, sleep-time precompute
  - [[research/llm-research/RESEARCH-axis-1-anthropic-engineering]] - 28 Anthropic engineering posts surveyed; the changes that touch Compass architecture are model-change harness ablation, offline memory consolidation, evaluator-on-demand, and bounded test output
  - [[research/llm-research/RESEARCH-axis-5-spec-driven-frameworks]] - Nine spec-driven frameworks read from source, comparison table, and the empirical evidence on specs, plans, TDD and ambiguity; candidate Compass changes
  - [[research/llm-research/RESEARCH-axis-4-multi-agent-verification]] - Evidence that fan-out hurts sequential coding, that test-pass is a weak oracle (34% of passing patches break review constraints), that clean-context and cross-model review help only partly, and that deterministic checks beat LLM checkers; maps each to builder, tester, validator, reviewer and the 3-cycle fix loop
  - [[research/llm-research/RESEARCH-axis-1b-anthropic-engineering-gap]] - Gap pass over six partly-read Anthropic engineering posts plus the missing 29th post; adds containment-first design, pass^k, absolute-path tool poka-yoke, think-tool deprecation, and trust-boundary lessons
  - [[research/llm-research/RESEARCH-axis-2b-host-features-gap]] - Gap pass on axis 2: Compass looprunner/proctree/self_update versus /goal, --bg, /loop and marketplace auto-update; prompt-cache ordering for always-loaded text; host trials of first-pass findings 7, 8, 21, 24, 25, 26
  - [[research/llm-research/REVIEW-llm-research-for-compass]] - Eight axis files merged and gap-mapped against the vault: seven architecture candidates, nine host-trial or doc fixes, nine measurements; strongest are cache-aware context, source-grounded consolidation, verification beyond test-pass and difficulty-scaled checking

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
- [[PLAN-017-dsh-host-support]] - dsh is a native Compass host from the one canonical plugin source (v0.19-0.23): materializers, model routes, doctor, capture worker, global auto-installed bundle, and Wave 6 zero-decision (SPEC-006 D-05) - hosts detected never asked, dsh-first bootstrap via a second bridge mount, both-direction acceptance at 0 errors
- [[PLAN-018-research-covers-the-whole-spec]] - rebuilds Compass's research surfaces so a run scopes to a whole spec instead of its question list, draws from a shipped list of sources whose access was tested, reads code instead of documentation, and reports when it needs another pass
- [[PLAN-019-stop-at-80-percent-context]] - a PostToolUse hook measures the main session's context from its transcript and, once it reaches 80% of the window, halts after the current tool with a stopReason suggesting /compass:handoff; fires once per crossing so the handoff itself runs; Claude Code only
- [[PLAN-020-clone-old-sessions]] - /compass:clone-old runs headless copies of past feature sessions, each writes its lessons, and the skill merges them through lesson-write
- [[PLAN-021-control-loops]] - control loops under .compass/loops/: `compass loop run` drives sensor, controller and actuator as a state machine inside caps and budget, plus four experiments
- [[PLAN-022-review-in-obsidian]] - the Compass Review Obsidian plugin, a `compass review` command, install, doctor and guard support; gate wiring follows an experiment
- [[PLAN-023-taxonomy-review-at-spec-creation]] - a `compass placement` command shows a new spec its candidate parents and domains; spec and specs propose the deeper home; first run on this vault
- [[PLAN-024-working-in-compass-is-visual]] - five trials in Obsidian and three agreed mockups first; then documents gain callouts, embeds, block links and footnotes, Compass's plugin draws task tables, graphs, charts and the spec canvas, and the CLI speaks short plain words, every visual earning its bytes
- [[PLAN-025-review-across-files-and-sessions]] - two live checks in Obsidian and an agreed mockup first; then one review walks the human through several files with one verdict, each card names its project and session, edits and stepping aside stay inside their own review, and a VS Code surface follows
- [[PLAN-026-local-additions-tell-the-truth]] - local additions already survive update (v0.14.0); this plan makes them honest: an edited addition refreshes, doctor tells applied from not applied, the update notice names what it re-applied, dsh gets them too, then a live round-trip and a way to keep old hand edits
- [[PLAN-027-numbered-choices]] - one rule in the always-loaded pipeline rules makes every choice put to the human a numbered list a bare number can answer; the guide skill's prose questions go through the same rule; ships as 0.34.2
- [[PLAN-028-whole-overhead-on-real-projects]] - a pilot of twelve headless builds on the human's subscription, in throwaway projects outside the repo, with and without Compass, sets the batch size and closes the research's open checks; then a baseline batch, the overhead broken into areas, and a loop that cuts the biggest area first
- [[PLAN-029-crafted-agent-context]] - slim launched agents by design A: per-agent-type token measure and the initialPrompt check first, then a split obsidian skill and a start-here fix land after the pilot; the lessons skill stays until a paired run shows it can go
- [[PLAN-030-ideas-keep-their-status]] - one file per idea in category folders holds his words, status, history and where it led; an importer backfills a hand-made table; sync moves status when a spec names an idea; stage 2 catches his words at submit and the background helper files ideas and verdicts
- [[PLAN-031-screenplays-in-the-vault]] - five live checks of the Fountain plugin in Obsidian and BetterFountain in VS Code come first, in one sitting; then Compass bundles Fountain 0.34.3, installs it into every project with an Obsidian vault, gives agents a fountain skill and a text check, and ships after acceptance here and in one other project
- [[PLAN-032-consolidation-grounded-in-sources]] - a zero-token drift scan checks code references, index lines and catalog rows against git and the files they describe, sync keeps catalog rows true to lesson files, a mechanical check guards every lesson edit, and a seeded-staleness probe proves the scan; source pointers, the model judge and the lesson track record follow

## Decisions

- [[ADR-001-methodology-as-skill-with-vault]] - Methodology lives in a skill; project state in per-project `.compass/` Obsidian-compatible vault
- [[ADR-017-capability-index-and-usage-record]] - bare compass is the progressive-disclosure index made reachable by one rule line; dispatch records every invocation; compass usage lists never-used commands explicitly; clean-tmp retires; admission control's fate decided by data (tree's retirement undone by SPEC-022 D-08)
- [[decisions/distribution/index|distribution]] (folder, 3 children) - rulings on installing, updating, and configuring Compass across projects
- [[decisions/learning/index|learning]] (folder, 5 children) - rulings on capture and feedback - lessons, workers, signal handling, source-word fidelity
- [[decisions/pipeline/index|pipeline]] (folder, 3 children) - rulings on the development workflow stages and gates
- [[decisions/vault-structure/index|vault-structure]] (folder, 9 children) - rulings on how the vault organizes, bounds, and retrieves its own memory

## Active Work

See [[active]].

## Backlog

See [[backlog]].

## Handoffs

- [[2026-10-29_09-30-00_issues-then-loops-then-workflow-spec]] - PLAN-026 shipped as 0.34.0 and pushed; next: fix the four open GitHub issues, finish PLAN-021 Wave 2 (control loops), then spec Claude Code workflow scripts to keep Compass runs off the context
- [[handoff-pointers|Older handoffs]] - every earlier handoff, oldest first

## Lessons

Indexed in meta/lessons-catalog.yaml (loaded with the hot path); files in `lessons/`, archived ones in `archive/lessons/`.

## compass-cli
- [[compass-cli/decisions/ADR-005-compass-cli-for-mechanical-work]] - A Python `compass` CLI Owns All Mechanical Vault Work; the Hook Calls It as a Command
- [[compass-cli/plans/PLAN-002-compass-cli-implementation]] - Compass CLI Implementation
- [[compass-cli/research/RESEARCH-cli-and-hook-command-contract]] - How Claude Code Structures CLIs and the Command-Hook Contract
- [[compass-cli/research/RESEARCH-cli-token-reduction-measurement]] - Measuring SPEC-004's 80% Bookkeeping-Token Reduction
- [[compass-cli/specs/SPEC-004-mechanical-work-off-the-agent-budget]] - Mechanical Vault Work Must Not Cost Agent Tokens

## Loops
- [[LOOP-001-visual-questions]] - Control loop for SPEC-029: drives every point where Compass asks the human something to one AskUserQuestion call per question.
- [[LOOP-002-no-private-data]] - Control loop keeping private data out of this public repository: deny-listed names, home-directory paths, session ids in paths and tokens, with a pre-commit hook that refuses new ones.
- [[LOOP-003-session-context]] - Shrinks the text Compass adds to every Claude Code session, as far as it goes with Compass working as well as before.

## Ideas
- [[ideas/how-we-work/index|how-we-work]] (folder, 1 children) - ideas the human filed under How we work
- [[ideas/tools-and-setup/index|tools-and-setup]] (folder, 1 children) - ideas the human filed under Tools and setup
