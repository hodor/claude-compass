# Compass Development

This project uses Compass to develop itself. The `.compass/` vault is the source of truth for all project context.

## Session Start Protocol

Every session MUST begin by reading the hot path:

1. `.compass/index.md` - master map of all project documents
2. `.compass/active.md` - current tasks, blockers, next up
3. `.compass/meta/lessons-catalog.yaml` - scan for relevant lessons

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
| `researcher` | General-purpose investigation - used by /compass:research-papers and /compass:research as fallback |
| `codebase-locator` | Cheap: where do files live? Grep/Glob/LS only, no Read |
| `codebase-analyzer` | How does this code work? Read-only, traces flow with file:line refs |
| `pattern-finder` | Concrete examples of patterns already in use (snippets allowed) |
| `reviewer` | Consolidates parallel agent outputs - convergence matrix |
| `planner` | Proposes implementation plans from specs + research |
| `builder` | Executes tasks - codes, runs smoke test, updates vault |
| `tester` | Auto-spawned after the builder finishes; writes adversarial tests |
| `validator` | Post-build verification - compares plan vs actual implementation |
| `debug` | Investigating errors / failures - read-only, isolated context |
| `pr-describe` | Creates / updates PR descriptions from Compass artifacts |

Interactive workflows run as skills: `/compass:spec`, `/compass:plan`, `/compass:handoff`, `/compass:build`, `/compass:autopilot`, `/compass:retroactive`, `/compass:bootstrap`, `/compass:checkup`, `/compass:diagnose`, `/compass:vault-health`, `/compass:vision`, `/compass:papers`, `/compass:research`, `/compass:research-codebase`, `/compass:research-papers`, `/compass:annotate`, `/compass:guide`.

## Skills

Agents can load these knowledge packs:

- `methodology` - the Compass workflow, pipeline, and rules
- `obsidian` - vault file formats, templates, naming conventions
- `lessons` - how to create, catalog, and search lessons

## Commit Rules

- Always `git add <specific-file>` - never `git add -A` or `git add .`
- Never commit `.compass/tmp/` contents
- Commit messages: imperative mood, explain *why* not *what*
- Only commit when explicitly instructed

## Vault Structure

```
.compass/
├── index.md              - HOT: master map
├── active.md             - HOT: current tasks
├── backlog.md            - future tasks
├── meta/config.yaml      - numbering counters
├── meta/lessons-catalog.yaml - lesson tag index
├── specs/                - specifications
├── research/             - research findings
├── plans/                - implementation plans
├── decisions/            - ADRs
├── lessons/              - lessons learned
├── handoffs/             - session continuity
├── prs/                  - PR descriptions
└── archive/              - completed documents
```
