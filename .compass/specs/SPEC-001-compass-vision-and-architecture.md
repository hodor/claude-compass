---
title: Compass Plugin — Vision & Architecture
type: spec
status: approved
confidence: high
area: architecture
tags: [core, vision, architecture, workflow]
created: 2026-03-12
updated: 2026-03-12
---

# Compass Plugin — Vision & Architecture

## Problem

Claude Code is powerful but lacks a structured development methodology. Without guardrails:
- Agents make decisions they shouldn't (especially at strategic level)
- Context windows get flooded with irrelevant information
- There's no persistent project knowledge between conversations
- No systematic way to go from idea → spec → research → plan → code
- Lessons learned are lost between sessions

## Vision

Compass is a Claude Code plugin that installs per-project and creates a `.compass/` Obsidian-compatible vault. It provides the **methodology** (how to work) while CLAUDE.md stays thin (what the project is).

The core workflow: **Spec → Research → Plan → Tasks → Build**

## Core Principles

### 1. Token Efficiency (Cache-Line Thinking)

Treat agent context like CPU cache. Minimize cache misses.

- **Hot path** (always loaded): `index.md` + `active.md` + relevant lessons
- **Cold path** (loaded on demand): backlog, archive, individual specs/research/plans
- Every agent reads the hot path first, then surgically loads only what's relevant

### 2. Human Involvement Gradient

The higher up the chain, the more human involvement required:

| Level | Human Role | AI Role |
|-------|-----------|---------|
| CLAUDE.md | Human defines, AI asks clarifying questions | Structure and prompt |
| Specs | Interactive session — human models, AI guides with questions | Ask questions, structure answers |
| Research | Human reviews findings, redirects | Execute autonomously, present findings |
| Plans | Human approves | Propose based on specs + research |
| Code | Human reviews output | Execute autonomously, write tests |

**Agents must FORCE humans to make decisions.** Never decide silently at strategic levels.

### 3. Bayesian Convergence

For critical decisions, spawn ~5 agents doing the same task independently. Check convergence:
- **Convergence** → high confidence, proceed
- **Divergence** → needs more human input, surface the disagreements

Apply to: research, plan review, any judgment calls.

### 4. Testing Mandate

Every coding agent MUST:
- Write property-based tests or unit tests (agent decides which)
- Tests live OUTSIDE `.compass/`, integrated with the project's own code
- Agent determines optimal test type and sets up centralized test structure per project
- Run ALL existing tests to ensure nothing is broken
- Non-negotiable.

### 5. Obsidian-Native

All files use:
- Standard markdown with `[[wikilinks]]`
- YAML frontmatter with confidence, tags, area, status, dates
- Each document is a standalone Obsidian note, browsable and editable

### 6. Required Artifacts

Every Compass project MUST have:
- At least one spec (the vision/purpose)
- At least one ADR (a recorded decision)
- `index.md`, `active.md`, `meta/config.yaml`, `meta/lessons-catalog.yaml`

If any of these are missing, agents MUST flag and request their creation. These are not optional.

## Architecture

### Plugin Structure

```
Plugin: compass
├── .claude-plugin/plugin.json
├── agents/
│   ├── bootstrap.md      — Detects project state, scaffolds or migrates
│   ├── spec-writer.md    — Asks questions, models spec with human
│   ├── researcher.md     — Investigates autonomously, returns findings
│   ├── planner.md        — Builds implementation plan from specs + research
│   ├── builder.md        — Reads task + index + lessons, codes + tests
│   └── reviewer.md       — Bayesian convergence: reviews N outputs, consolidates
├── skills/
│   ├── methodology/      — Core workflow rules (injected into all agents)
│   ├── obsidian/         — Obsidian formatting, frontmatter, wikilinks
│   └── lessons/          — How to search and apply lessons
```

### Per-Project Vault: `.compass/`

```
.compass/
├── index.md              — HOT: master map with 1-line summaries + [[links]]
├── active.md             — HOT: current tasks only (in-progress + blocked)
├── backlog.md            — Cold: future tasks
├── meta/
│   ├── config.yaml       — Counters for SPEC/ADR/TASK/PLAN numbering
│   └── lessons-catalog.yaml — O(1) tag lookup for lessons
├── specs/                — Specifications
├── research/             — Research findings
├── plans/                — Implementation plans
├── decisions/            — Architecture Decision Records (ADRs)
├── lessons/              — Lessons learned
└── archive/              — Completed/retired documents
```

### Skills vs Agents

- **Agents** = the workers. Spawned separately, own context, don't pollute main conversation.
- **Skills** = knowledge packs. Injected into agents at startup via `skills` field in agent frontmatter.
- **Main conversation** = the orchestrator. Spawns parallel agents, coordinates.

Subagent constraints:
- Subagents CAN preload skills (injected at startup)
- Subagents CANNOT invoke skills dynamically
- Subagents CANNOT spawn other subagents

### Agent Definitions

#### bootstrap
- Detects project state (new vs existing)
- New: scaffolds `.compass/` with full structure + `SPEC-001` for the setup itself
- Existing: inventories docs, proposes migration table, human approves line by line
- Proposes thin CLAUDE.md section (~10 lines), human approves before write
- Bootstrap IS a Compass workflow — it uses Compass to set up Compass

#### spec-writer
- Interactive agent that guides the human through spec creation
- Asks ONE question at a time, saves after every 2-3 answers
- Human models the spec, agent structures it
- MADR-inspired format: Problem, Context, Decision Drivers, Considered Options, Consequences
- Multiple spec-writers can run in parallel for Bayesian convergence

#### researcher
- Autonomous agent that investigates a topic
- Searches codebase, web, documentation
- Returns structured findings with confidence levels (low/medium/high)
- Never makes decisions — presents evidence only
- Designed for parallel execution — spawn N, reviewer consolidates

#### planner
- Takes specs + research, builds implementation plan
- Breaks plan into ordered tasks with complexity (S/M/L) and acceptance criteria
- Tasks must be small enough for a single builder
- Human approves before tasks are created
- Updates active.md/backlog.md after approval

#### builder
- Protocol: read hot path → identify task → read parent plan → search lessons → code → test → update status
- Determines optimal test type (property-based vs unit) per project
- Sets up centralized test location OUTSIDE `.compass/`
- Runs full existing test suite after changes
- Creates lessons when encountering something surprising
- Creates ADRs for significant implementation decisions

#### reviewer
- Takes N outputs from parallel agents, builds convergence matrix
- Converged (>=80%): consolidate with high confidence
- Partial (50-79%): present majority + minority with evidence
- Divergent (<50%): present all positions, ask human to decide
- Never resolves disagreements autonomously

### Key Design Decisions

- **Methodology = skill** (not CLAUDE.md). Injected into all agents via frontmatter. CLAUDE.md gets only a thin 10-line pointer.
- **Decisions (ADRs) are required** — not optional. If a project has none, agents must flag and request creation.
- **File names are self-descriptive** — `SPEC-001-compass-vision-and-architecture.md`, not `SPEC-001.md`. Numbers for ordering, names for clarity.
- **Tasks live in active.md/backlog.md** (not individual files) — keeps hot path to one file read.
- **Counters in config.yaml** — single source of truth for SPEC-NNN, ADR-NNN, TASK-NNN, PLAN-NNN numbering.
- **Lessons catalog** (`meta/lessons-catalog.yaml`) for O(1) tag lookup instead of O(n) grep.

### YAML Frontmatter Schema

All `.compass/` files use frontmatter with these fields as applicable:

```yaml
---
title: Human-readable title
type: spec | research | plan | task | lesson | decision
status: draft | review | approved | active | done | archived
confidence: low | medium | high
area: architecture | frontend | backend | testing | devops | ...
tags: [tag1, tag2, ...]
created: YYYY-MM-DD
updated: YYYY-MM-DD
blocked_by: "description or [[link]]"
depends_on: ["[[link1]]", "[[link2]]"]
---
```

### File Naming Convention

`TYPE-NNN-descriptive-name.md` — numbers for ordering, names MUST be self-descriptive.

| Type | Pattern | Example |
|------|---------|---------|
| Spec | `SPEC-NNN-name.md` | `SPEC-001-compass-vision-and-architecture.md` |
| Decision | `ADR-NNN-name.md` | `ADR-001-obsidian-over-structured-db.md` |
| Research | `RESEARCH-name.md` | `RESEARCH-plugin-system-capabilities.md` |
| Plan | `PLAN-NNN-name.md` | `PLAN-001-mvp-implementation.md` |
| Lesson | `LESSON-name.md` | `LESSON-yaml-frontmatter-quoting.md` |

### Bootstrap Flow

**Scenario 1: New project**
1. Scaffold `.compass/` with full structure
2. Create `SPEC-001` for the project setup (Compass bootstraps with Compass)
3. Create initial tasks in `active.md`
4. Propose thin CLAUDE.md section, human approves

**Scenario 2: Existing project**
1. Inventory: scan for existing docs, READMEs, TODOs, CLAUDE.md
2. Propose migration: what becomes specs, what becomes tasks, what's a lesson
3. Human approves plan line by line
4. Execute migration
5. Update index

## Resolved Questions

- **Spec-writer Q&A protocol**: Ask ONE question at a time, save after every 2-3 answers. Flow: problem → desired outcome → constraints → non-goals → existing context → deepen.
- **Lesson matching**: Tag-based via `meta/lessons-catalog.yaml`. Filter by area → filter by tags → sort by score → load top 3-5.
- **File naming**: `TYPE-NNN-descriptive-name.md`. Numbers from `config.yaml` counters. Names must be self-descriptive.
- **Orchestration**: Main conversation spawns agents as needed. No single entry-point skill — the human (or main conversation agent) decides which agent to use.
- **Entry point**: No `/compass` entry-point skill. Agents are invoked directly by name (bootstrap, spec-writer, researcher, planner, builder, reviewer).
