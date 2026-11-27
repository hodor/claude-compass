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
- [[research/pipeline/index|pipeline]] (folder, 8 children) - evidence on the pipeline as a method - benchmarks, scientific rigor, decision-coverage mechanics
- [[research/human-surface/index|human-surface]] (folder, 8 children) - how Compass puts things in front of the human: the questions it asks, the documents it hands over for review, and how all of it reads
- [[research/whole-overhead/index|whole-overhead]] (folder, 4 children) - evidence on measuring Compass's whole token overhead on projects agents build, and cutting it biggest area first
  - [[research/methodology/PROPOSAL-hot-path-consolidation-2026-11]] - topic folders for the 35 flat plan lines and the stray research lines, old notes parked out of active.md: start-here files from 6,596 to 3,926 tokens now, 3,472 after the four open plans merge
- [[research/llm-research/index|llm-research]] (folder, 11 children) - the survey of Anthropic's engineering posts and 2025-2026 LLM agent research for changes Compass should make - its axes, gap passes, merged review and the checks of the stages it led to

## Plans

- [[plans/learning/index|learning]] (folder, 6 children) - plans that implement the learning specs - lessons, the capture loop, fidelity to the human's words, ideas
- [[plans/distribution/index|distribution]] (folder, 4 children) - plans that implement the distribution specs - model resolution, self-update, dsh host support, local additions
- [[plans/human-surface/index|human-surface]] (folder, 5 children) - plans that implement the human-surface specs - review in Obsidian, visual documents, numbered choices, screenplays
- [[plans/pipeline/index|pipeline]] (folder, 8 children) - plans that implement the pipeline specs - decision coverage, test quality, staged plans, research scope, the context stop, control loops, compaction, verification
- [[plans/tooling/index|tooling]] (folder, 6 children) - plans that implement the tooling specs - invisible capture, capability usage, whole token overhead, agent context, checking cost, prompt cache
- [[plans/vault-structure/index|vault-structure]] (folder, 6 children) - plans that implement the vault-structure specs - hierarchy, the active sweep, graph queries, sizing, topic folders

## Decisions

- [[ADR-001-methodology-as-skill-with-vault]] - Methodology lives in a skill; project state in per-project `.compass/` Obsidian-compatible vault
- [[ADR-017-capability-index-and-usage-record]] - bare compass is the progressive-disclosure index made reachable by one rule line; dispatch records every invocation; compass usage lists never-used commands explicitly; clean-tmp retires; admission control's fate decided by data (tree's retirement undone by SPEC-022 D-08)
- [[decisions/distribution/index|distribution]] (folder, 3 children) - rulings on installing, updating, and configuring Compass across projects
- [[decisions/learning/index|learning]] (folder, 6 children) - rulings on capture and feedback - lessons, workers, signal handling, source-word fidelity
- [[decisions/pipeline/index|pipeline]] (folder, 4 children) - rulings on the development workflow stages and gates
- [[decisions/vault-structure/index|vault-structure]] (folder, 9 children) - rulings on how the vault organizes, bounds, and retrieves its own memory

## Active Work

See [[active]].

## Backlog

See [[backlog]].

## Handoffs

- [[2026-10-29_09-30-00_issues-then-loops-then-workflow-spec]] - PLAN-026 shipped as 0.34.0 and pushed; next: fix the four open GitHub issues, finish PLAN-021 Wave 2 (control loops), then spec Claude Code workflow scripts to keep Compass runs off the context
- [[handoff-pointers|Older handoffs]] - every earlier handoff, oldest first

## Lessons

See `lessons/index.md` - the grep-first surface sync keeps current; `compass lessons` ranks via `meta/lessons-catalog.yaml`; archived lessons live in `archive/lessons/`.

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
