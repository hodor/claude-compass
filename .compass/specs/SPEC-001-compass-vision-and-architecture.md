---
title: Compass Plugin - Vision & Architecture
type: spec
status: approved
confidence: high
area: architecture
tags: [core, vision, architecture, workflow, harness, hierarchy, configurable-pipeline]
created: 2026-03-12
updated: 2026-07-22
summary: "Core vision, principles, architecture, and resolved design decisions"
---

# Compass Plugin - Vision & Architecture

## Problem

Agent coding tools are powerful but lack a structured development methodology. Without guardrails:
- Agents make strategic decisions that belong to the human.
- Context windows flood with irrelevant information.
- There is no persistent project knowledge between sessions.
- There is no systematic path from idea to spec to research to plan to code.
- Lessons learned are lost between sessions.

## Vision

Compass is a plugin that installs per-project and creates a `.compass/` Obsidian-compatible vault. It provides the **methodology** (how to work) while the project's own instructions stay thin (what the project is).

The workflow is a **configurable pipeline** over a shipped default: **Vision → Spec → Research → Plan → Build → Validate**. The phase vocabulary ships built in, but a project can reorder it, drop phases, or define its own (one team runs Vision → Spec → Research → Build → Test → Ship; another runs something else). Compass supports different workflows, not one hardcoded sequence. See [[SPEC-009-configurable-pipeline-workflows]].

Compass is not bound to one host. The vault and the mechanical harness are host-agnostic; the pipeline runs on Claude Code today and on other agent CLIs by design. See [[SPEC-006-multi-host-agent-cli-support]].

## North Star Goals

Every design decision serves at least one of these four. When a tradeoff arises, the ranking is the order shown.

1. **Accuracy** - outputs are correct, claims are verified, predictions get checked after build.
2. **Perfect memory** - nothing learned is forgotten across sessions; the vault is the single source of truth.
3. **Almost zero cache misses** - every navigation finds what it needs in one or two reads; the hot path stays bounded regardless of vault size (see [[ADR-004-hierarchical-specs-with-facets]]).
4. **Low token usage** - mechanical work runs in the harness, never in agent tokens (see [[LESSON-no-agent-bookkeeping]]).

## Core Principles

### 1. Harness Over Prompts

Prefer deterministic code (the `compass` CLI and hooks) over agent prompts and skills for anything mechanical. A behavior encoded in the harness is correct every time, costs no agent tokens, is testable, and ports across hosts; the same behavior asked for in prose is probabilistic, expensive, and re-explained every turn. This principle is the mechanism behind goals 1, 3, and 4: determinism serves accuracy, bounded harness-maintained structure serves cache, scripts-not-tokens serves cost.

The design test for any new behavior: can the harness do it? If it is mechanical (numbering, indexing, validation, model resolution, coverage checks, state maintenance), it belongs in the CLI or a hook, not in a skill. Prose is reserved for the judgment agents genuinely make. See [[ADR-005-compass-cli-for-mechanical-work]].

### 2. Cache-Line Thinking (Token Efficiency)

Treat agent context like CPU cache. Minimize cache misses through a three-tier memory model:
- **Hot path** (always loaded): `index.md` + `active.md` + the lessons catalog. Bounded, capped, positioned at the start of the prompt.
- **Warm tier** (loaded on navigation): per-folder index summaries.
- **Cold tier** (loaded on demand): full spec/research/plan bodies, backlog, archive.

Every agent reads the hot path first, then surgically loads only what is relevant. See [[ADR-004-hierarchical-specs-with-facets]].

### 3. Human Involvement Gradient

The higher up the chain, the more human involvement required:

| Level | Human Role | AI Role |
|-------|-----------|---------|
| Project instructions | Human defines, AI asks clarifying questions | Structure and prompt |
| Vision / Specs | Human decides, AI guides with questions | Ask questions, structure answers |
| Research | Human reviews findings, redirects | Execute autonomously, present findings |
| Plans | Human approves | Propose based on specs + research |
| Build | Human reviews output | Execute autonomously, write tests |

**Agents must force humans to make strategic decisions. Never decide silently at strategic levels.**

### 4. Multi-Agent Convergence Voting

For critical decisions, spawn several agents doing the same task independently and check convergence:
- **Convergence** (>=80% agree) → high confidence, proceed.
- **Partial** (50-79%) → present majority and minority with evidence.
- **Divergence** (<50%) → surface disagreements, ask the human to decide.

This is majority voting across independent samples, not Bayesian updating. Apply to research, plan review, and judgment calls.

### 5. Testing Mandate

Every coding agent MUST:
- Write tests (property-based or unit, agent decides), living OUTSIDE `.compass/`, integrated with the project's own code.
- Run the full existing suite so nothing is broken.
- Non-negotiable.

### 6. Obsidian-Native

All files use standard markdown with `[[wikilinks]]`, YAML frontmatter (title, type, status, confidence, area, tags, dates), and stand alone as browsable, editable Obsidian notes.

## Architecture

### Vault Structure: Hybrid Hierarchy

The vault is type-first at the root for small work, and feature-first for large units of work. A small spec is a file in `specs/`; a large unit of work (a whole tool, subsystem, or feature) earns its own folder at the vault root, named for the work itself, co-locating all of its own artifact types. The reserved type-folder names (`specs`, `research`, `plans`, `decisions`, `lessons`, `handoffs`, `meta`, `archive`) are fixed; any other folder at the root is a unit of work. Any artifact type can nest, not just specs. See [[SPEC-010-universal-hybrid-hierarchy]].

```
.compass/
├── index.md              - HOT: master map, pointers only, bounded, machine-maintained
├── active.md             - HOT: current tasks (in-progress + blocked)
├── backlog.md            - cold: future work (with trigger conditions)
├── meta/                 - lessons-catalog.yaml, tag-index.yaml, plugin.yaml
├── specs/                - small standalone specs (flat)
├── research/             - research findings
├── plans/                - implementation plans
├── decisions/            - ADRs
├── lessons/              - lessons learned
├── handoffs/             - session continuity
├── archive/              - completed/retired documents
│
└── compass-cli/          - a large unit of work: a folder at the root, named for the
    ├── index.md            work itself, co-locating all of ITS own artifact types.
    ├── specs/              Any root folder that is not a reserved type name (above)
    ├── research/           is a unit of work; its numbering is local to it.
    ├── plans/
    └── decisions/
```

Numbering is JIT max+1 from the filesystem, local per folder; there is no counter file. See [[ADR-003-drop-counter-file-jit-compute]].

### The Harness: `compass` CLI + Hooks

Mechanical vault work lives in a Python `compass` CLI, invoked by hooks off the agent token budget. A PostToolUse hook runs `compass sync` on every vault write to keep the index and indexes current. The CLI also owns numbering, validation, promotion, and (per the harness-over-prompts principle) is the home for new mechanical concerns: model resolution ([[SPEC-008-central-model-resolution-table]]), decision-coverage checks ([[SPEC-007-decision-coverage-tracing]]). MCP was rejected for this path in favor of the CLI. See [[ADR-005-compass-cli-for-mechanical-work]].

### Agents and Skills

- **Agents** = the workers. Spawned with their own context; they do not pollute the main conversation. Roster: researcher, planner, builder, tester, validator, reviewer, plus the locator/analyzer read agents.
- **Skills** = knowledge and workflow packs, invoked as `/compass:*` commands or auto-triggered. Skills carry the judgment and interview flows; mechanical steps inside them delegate to the CLI.
- **Main conversation** = the orchestrator. Spawns parallel agents, coordinates, holds the conclusion.

### Lessons

Retrospective capture at phase boundaries with binary triggers, an anti-list filter, dedup, scoring, and a single writer. See [[ADR-002-retrospective-lessons-subsystem]] and [[SPEC-002-lessons-and-index-subsystem]].

## Key Design Decisions

- **Harness over prompts** - mechanical behavior lives in the CLI/hooks, not skills. [[ADR-005-compass-cli-for-mechanical-work]].
- **Configurable pipeline** - a shipped phase vocabulary that projects can reorder, subset, or extend. [[SPEC-009-configurable-pipeline-workflows]].
- **Hybrid hierarchy** - type-first root, plus a root-level folder per large unit of work that co-locates its own artifact types; every type can nest. [[SPEC-010-universal-hybrid-hierarchy]].
- **Multi-host by design** - vault and harness are host-agnostic. [[SPEC-006-multi-host-agent-cli-support]].
- **Methodology = skill**, not project instructions. The project's own instructions get only a thin pointer.
- **ADRs are required** - a project with none gets flagged.
- **Self-descriptive filenames** - `TYPE-NNN-descriptive-name.md`; numbers order, names clarify.
- **JIT numbering**, no counter file. [[ADR-003-drop-counter-file-jit-compute]].

## Resolved Questions

- **Numbering**: JIT max+1 from the filesystem, local per folder. [[ADR-003-drop-counter-file-jit-compute]].
- **Mechanical work**: owned by the `compass` CLI, triggered by hooks, off the token budget. [[ADR-005-compass-cli-for-mechanical-work]].
- **Hierarchy**: hybrid, type-first root plus co-located subtrees for large units. [[ADR-004-hierarchical-specs-with-facets]], [[SPEC-010-universal-hybrid-hierarchy]].
- **Lesson matching**: tag-based via `meta/lessons-catalog.yaml`, filtered by area and tags, scored, top few loaded.

## Open Questions

- The exact phase-configuration format and how custom phases bind their agents/artifacts/gates. [[SPEC-009-configurable-pipeline-workflows]].
- The migration path from today's flat vault to the hybrid hierarchy, and the promotion rule for when a unit of work earns a `tools/<unit>/` subtree. [[SPEC-010-universal-hybrid-hierarchy]].
- Whether any north-star ranking shifts once harness-over-prompts is a first-class principle (currently the four goals are unchanged; harness-over-prompts is their mechanism, not a fifth goal).
