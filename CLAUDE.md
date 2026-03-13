# Compass Development

This project uses Compass to develop itself. The `.compass/` vault is the source of truth for all project context.

## Session Start Protocol

Every session MUST begin by reading the hot path:

1. `.compass/index.md` — master map of all project documents
2. `.compass/active.md` — current tasks, blockers, next up
3. `.compass/meta/lessons-catalog.yaml` — scan for relevant lessons

Do not start work until you've read all three.

## Methodology

Read `plugin/skills/methodology/SKILL.md` for the full workflow. Key points:

- **Pipeline:** Spec → Research → Plan → Tasks → Build → Validate
- **Human involvement gradient:** Specs (human decides) → Research (AI executes, human reviews) → Plans (AI proposes, human approves) → Build (AI executes autonomously)
- **Testing mandate:** Every agent that writes code must write tests and run the full suite
- **Decisions:** Significant choices become ADRs in `.compass/decisions/`
- **Lessons:** Surprising discoveries become lessons in `.compass/lessons/`

## Available Agents

Use the appropriate agent instead of doing work manually in the main conversation:

| Agent | When to use |
|-------|-------------|
| `spec-writer` | Creating new specifications — asks one question at a time |
| `researcher` | Investigating a topic — spawn N in parallel, then consolidate with `reviewer` |
| `reviewer` | Consolidating parallel agent outputs — builds convergence matrix |
| `planner` | Proposing implementation plans from specs + research |
| `planner-iterate` | Surgically editing an existing plan based on feedback |
| `builder` | Executing tasks — codes, tests, updates vault |
| `validator` | Post-build verification — compares plan vs actual implementation |
| `handoff-create` | End of session — compresses context into portable handoff |
| `handoff-resume` | Start of session — verifies state and presents situational report |
| `debug` | Investigating errors/failures — read-only, isolated context |
| `pattern-finder` | Finding existing code patterns before writing new code |
| `autopilot` | Full pipeline (research → plan → build) for small/medium tasks |
| `retroactive` | Creating vault entries for work that happened without Compass |
| `pr-describe` | Creating/updating PR descriptions from Compass artifacts |
| `bootstrap` | Setting up Compass in a new project |

## Skills

Agents can load these knowledge packs:

- `methodology` — the Compass workflow, pipeline, and rules
- `obsidian` — vault file formats, templates, naming conventions
- `lessons` — how to create, catalog, and search lessons

## Commit Rules

- Always `git add <specific-file>` — never `git add -A` or `git add .`
- Never commit `.compass/tmp/` contents
- Commit messages: imperative mood, explain *why* not *what*
- Only commit when explicitly instructed

## Vault Structure

```
.compass/
├── index.md              — HOT: master map
├── active.md             — HOT: current tasks
├── backlog.md            — future tasks
├── meta/config.yaml      — numbering counters
├── meta/lessons-catalog.yaml — lesson tag index
├── specs/                — specifications
├── research/             — research findings
├── plans/                — implementation plans
├── decisions/            — ADRs
├── lessons/              — lessons learned
├── handoffs/             — session continuity
├── prs/                  — PR descriptions
└── archive/              — completed documents
```
