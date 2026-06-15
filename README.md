# Compass

A Claude Code plugin for working on a project across many sessions without context rotting over time.

## The problem

Project knowledge degrades over time. A new session has to rediscover what's been decided, re-explore the codebase, and re-ask questions you already answered.

What you want is an agent that joins the project, finds the relevant context fast, and picks up from where things actually are.

## How it works

Compass stores project knowledge in a `.compass/` folder next to your code. Plain markdown with YAML frontmatter, Obsidian-compatible. The folder is the source of truth for what the project is, what has been decided, what is in progress, and what was learned.

Every agent reads the hot path first (`index.md`, `active.md`, `meta/lessons-catalog.yaml`) so it orients in seconds, not turns.

The vault contains:

- `vision.md`: the project goal and the roadmap of needs.
- `specs/`: one spec per problem. Specs describe the need, not the solution.
- `research/`: evidence and trade-offs gathered to inform a spec.
- `plans/`: ordered tasks with verification criteria, derived from approved specs.
- `decisions/`: ADRs for choices that future-you would not be able to reconstruct from code.
- `lessons/`: surprising discoveries, tagged so future sessions surface them.
- `handoffs/`: end-of-session snapshots so the next session starts oriented.
- `meta/`: generated indexes (`tag-index.yaml`, `lessons-catalog.yaml`) and the install record (`plugin.yaml`).
- `.annotations/`: sidecar notes attached to specific files.

The pipeline is `vision -> spec -> research -> plan -> build -> test -> validate`. Each step has a dedicated agent or skill with one job and bounded behavior. Specs cannot make implementation decisions. Researchers cannot recommend. Validators cannot edit. The builder writes code in an isolated git worktree; tests are written and run as part of the build cycle; the validator gates the result.

Human approval gates the strategic transitions: specs need approval before research, plans need approval before tasks.

## Bookkeeping runs off the agent's budget

Keeping the vault consistent is mechanical: regenerating `index.md` and the tag index, validating wikilinks and frontmatter, numbering artifacts, pruning old logs. Compass does this with a small standard-library Python CLI (`compass`), not with agent tokens.

A `PostToolUse` hook runs `compass sync` **as a command** on every vault write, so the index and tag index stay fresh at roughly zero agent cost. The command self-filters its own writes (no loops), never blocks an edit, and produces no visible output on success. This is the core of the design (SPEC-004 / ADR-005): a deterministic tool owns the upkeep that an LLM should never spend tokens re-deriving. The CLI ships as part of the install and is also runnable by hand:

```
compass sync       # regenerate index + tag index, check caps, clean logs
compass validate   # check frontmatter + wikilinks; errors fail, dangling links warn
compass next-num   # next artifact number, computed from the filesystem
compass tree       # render the spec hierarchy
```

## Slash commands

**Setup and maintenance**

| Command | What it does |
|---|---|
| `/compass:setup` | First-time setup: install agents, rules, skills, the `compass` CLI, and hooks into `.claude/`, scaffold the vault, propose CLAUDE.md additions. |
| `/compass:update` | Refresh an existing install from GitHub (agents, skills, CLI, hooks). Never touches the vault. |
| `/compass:guide` | Detect where you are and tell you what to do next. |
| `/compass:checkup` | Find drift: stale handoffs, broken links, missing agents or config. |
| `/compass:vault-health` | Validate vault integrity (frontmatter, wikilinks, orphans) via `compass validate`. |
| `/compass:annotate` | Manage sidecar notes on vault files. |

**Capture and design**

| Command | What it does |
|---|---|
| `/compass:vision` | Capture the project goal and the spec roadmap. |
| `/compass:spec` | Interview to produce one spec. One problem per spec. |
| `/compass:specs` | Braindump to multiple specs at once. |
| `/compass:research` | Router: dispatches to research-codebase or research-papers. |
| `/compass:research-codebase` | Document how code and prior vault knowledge cover a topic, via parallel locator/analyzer/pattern-finder agents. |
| `/compass:research-papers` | Citation-graph triad (Current / Backward / Forward) on a paper or technique. |
| `/compass:papers` | Fetch and search academic papers via Hugging Face. |
| `/compass:plan` | Turn an approved spec into ordered tasks. Supports iterate mode for surgical edits. |

**Execute**

| Command | What it does |
|---|---|
| `/compass:build` | Execute tasks. Parallel when file ownership allows; merges branches back after each phase. |
| `/compass:autopilot` | Run the full pipeline for small tasks with checkpoints. |
| `/compass:validate` | Final gate against the plan. |
| `/compass:diagnose` | Spawn the debug agent in an isolated context to investigate errors. |

**Continuity, learning, migration**

| Command | What it does |
|---|---|
| `/compass:handoff` | Save context at session end, restore at session start. |
| `/compass:learned` | Capture an in-the-moment lesson. |
| `/compass:consolidate` | Merge, prune, and demote lessons when the catalog grows past its cap. |
| `/compass:retroactive` | Document existing commits that predate the vault. |
| `/compass:promote-spec` | Promote a flat spec into a folder spec (via `compass promote`). |
| `/compass:taxonomize` | Bulk-migrate a flat vault to the hierarchical + faceted scheme. |

## Repo layout

| Path | Distributed to users? | Purpose |
|---|---|---|
| `plugin/` | Yes - this is the install target | Agents, skills, rules, hooks, and the `compass` CLI (`plugin/cli/`). Everything `/compass:setup` and `/compass:update` copy into a project. |
| `bench/` | No | Benchmark harness used to evaluate Compass against a plain-Claude-Code baseline. Not part of any user install. |
| `.compass/` | No | Compass's own dogfood vault. The plugin is developed via its own methodology; its specs, plans, ADRs, and lessons live here. |
| `README.md`, `CLAUDE.md` | No | Repo-level docs. |

`claude --plugin-dir` and `/compass:setup` both target `plugin/` specifically, so siblings of `plugin/` never reach a user's project.

## Quick start

Requires Claude Code, and a Python 3 interpreter (`python` or `python3`) for the bookkeeping hook.

```bash
claude --plugin-dir "/path/to/claude-compass/plugin"
```

Inside Claude Code, run `/compass:setup`. It copies agents, skills, rules, and the `compass` CLI into your project's `.claude/`, installs the vault-sync hook, scaffolds the vault, and runs `/compass:vision` to capture what you are building. After setup the project is self-contained: anyone who clones the repo has the same agents, skills, and CLI, no plugin install required.

To pull a newer Compass into an existing project, run `/compass:update` (it refreshes the install from GitHub and leaves your vault untouched), then restart the session so the refreshed hooks load.

## License

Apache 2.0.
