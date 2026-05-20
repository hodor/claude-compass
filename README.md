# Compass

A Claude Code plugin for working on a project across many sessions without context rotting over time.

## The problem

Project knowledge degrades over time. A new session has to rediscover what's been decided, re-explore the codebase, and re-ask questions you already answered.

What you want is an agent that joins the project, finds the relevant context fast, and picks up from where things actually are.

## How it works

Compass stores project knowledge in a `.compass/` folder next to your code. Plain markdown with YAML frontmatter, Obsidian-compatible. The folder is the source of truth for what the project is, what has been decided, what is in progress, and what was learned.

Every agent reads the hot path first (`index.md`, `active.md`, `lessons-catalog.yaml`) so it orients in seconds, not turns.

The vault contains:

- `vision.md`: the project goal and the roadmap of needs.
- `specs/`: one spec per problem. Specs describe the need, not the solution.
- `research/`: evidence and trade-offs gathered to inform a spec.
- `plans/`: ordered tasks with verification criteria, derived from approved specs.
- `decisions/`: ADRs for choices that future-you would not be able to reconstruct from code.
- `lessons/`: surprising discoveries, tagged so future sessions surface them.
- `handoffs/`: end-of-session snapshots so the next session starts oriented.
- `.annotations/`: sidecar notes attached to specific files.

The pipeline is `vision -> spec -> research -> plan -> build -> test -> validate`. Each step has a dedicated agent or skill with one job and bounded behavior. Specs cannot make implementation decisions. Researchers cannot recommend. Validators cannot edit. The builder writes code in an isolated git worktree and runs no tests; the tester is auto-spawned via a `SubagentStop` hook and handles all test execution; the validator gates the result.

Human approval gates the strategic transitions: specs need approval before research, plans need approval before tasks.

## Slash commands

| Command | What it does |
|---|---|
| `/compass:bootstrap` | Install the plugin into a project, scaffold the vault, configure hooks. |
| `/compass:vision` | Capture the project goal and the spec roadmap. |
| `/compass:spec` | Interview to produce one spec. One problem per spec. |
| `/compass:specs` | Braindump to multiple specs at once when several ideas are in hand. |
| `/compass:research` | Router: dispatches to research-codebase or research-papers. |
| `/compass:research-codebase` | Document how code and prior vault knowledge cover a topic. Spawns codebase-locator, codebase-analyzer, vault-locator, vault-analyzer, pattern-finder in parallel. |
| `/compass:research-papers` | Citation-graph triad (Current / Backward / Forward) on a paper, algorithm, or technique. |
| `/compass:papers` | Fetch and search academic papers via Hugging Face. |
| `/compass:plan` | Turn an approved spec into ordered tasks. Supports iterate mode for surgical edits. |
| `/compass:build` | Execute tasks. Parallel when file ownership allows, merges branches back after each phase. |
| `/compass:validate` | Final gate against the plan. |
| `/compass:diagnose` | Spawn the debug agent in an isolated context to investigate errors. |
| `/compass:handoff` | Save context at session end, restore at session start. |
| `/compass:autopilot` | Run the full pipeline for small tasks with checkpoints. |
| `/compass:retroactive` | Document existing commits that predate the vault. |
| `/compass:guide` | Detects where you are and tells you what to do next. |
| `/compass:checkup` | Find drift, stale handoffs, broken links, counter mismatches. |
| `/compass:vault-health` | Validate vault integrity: frontmatter, wikilinks, orphans, counters. |
| `/compass:annotate` | Manage sidecar notes on vault files. |

## Quick start

Requires Claude Code.

```bash
claude --plugin-dir "/path/to/claude-compass/plugin"
```

Inside Claude Code, run `/compass:bootstrap`. It copies agents, skills, and rules into your project's `.claude/`, scaffolds the vault, configures hooks, and runs `/compass:vision` to capture what you are building. After bootstrap, the project is self-contained: anyone who clones the repo has the same agents and skills, no plugin install required.

## License

Apache 2.0.
