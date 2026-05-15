# Compass

A development workflow for working with Claude Code that does not lose its mind between sessions.

## The problem

You start a project with Claude. You build something. Two weeks later, you come back. Claude has forgotten everything. You re-explain the project, re-explain the decisions, re-explain why that one weird workaround exists. You start over, half-remembered.

If you have used Claude Code or any other LLM coding tool for more than a week, you know this feeling. Context windows fill up. Sessions end. Knowledge evaporates. The model is brilliant in the moment and amnesiac the next day.

Compass fixes this by giving every project a structured knowledge vault that lives in `.compass/` next to your code. Every decision, plan, lesson, and handoff goes in there. Next session, Claude reads the vault first and picks up where you left off.

## What you get

A folder called `.compass/` in your project, organized like this:

- **vision** captures what the project is and the roadmap of needs to address
- **specs** capture problems to solve, one problem per spec, no implementation
- **research** captures evidence and trade-offs for each spec
- **plans** turn approved specs into ordered tasks with verification criteria
- **decisions** record significant architectural choices, with reasoning
- **lessons** capture surprising discoveries so the project gets smarter over time
- **handoffs** summarize sessions so the next one starts oriented

The vault is plain markdown with YAML frontmatter. You can open it in Obsidian for graph view, or read it as plain files. Humans curate it; agents read and write to it.

## How it works

Compass installs a set of agents and skills into Claude Code. They follow a pipeline:

```
vision → spec → research → plan → build → test → validate
```

Each step has a dedicated agent or skill, with one job and clear constraints. The builder writes code in an isolated git worktree. When it finishes, a hook fires the tester, which writes adversarial tests. Then the validator runs the final quality gate against the plan. Each handoff between phases produces an artifact in the vault.

You drive the pipeline through slash commands:

- `/compass:vision` to capture the project vision and spec roadmap
- `/compass:spec` to write a single specification
- `/compass:research` to investigate options and evidence
- `/compass:plan` to turn an approved spec into tasks
- `/compass:build` to execute tasks (one or many in parallel)
- `/compass:validate` to run the final gate
- `/compass:handoff` to save context at end of session, restore at start
- `/compass:guide` to figure out what to do next
- `/compass:checkup` to find drift and stale state in the vault

There are more, but those are the core flow.

## Why this works

Three reasons.

First, the vault gives the model durable context. The hot path (`index.md`, `active.md`, `lessons-catalog.yaml`) is always read first by every agent, so the model orients quickly even on a cold start.

Second, the agents are bounded. The spec writer cannot make implementation decisions. The researcher cannot recommend solutions. The validator cannot edit files. Each one knows its lane, refuses to leave it, and hands off cleanly. This is what makes the pipeline trustworthy.

Third, humans approve at the strategic gates. Specs need approval before research starts. Plans need approval before tasks get created. The model executes inside the bounds the human sets. You stay in control without doing the typing.

## Who this is for

You are using an AI coding tool (Claude Code, Cursor, etc.) on a real project, you have hit the "the model lost the thread again" wall, and you want a workflow where knowledge accumulates instead of evaporating.

If you have read about context engineering and thought "yes, but how do I actually do that on my projects," Compass is one answer.

## Getting started

You need Claude Code installed. Then:

```bash
claude --plugin-dir "/path/to/claude-compass/plugin"
```

Inside Claude Code:

```
/compass:bootstrap
```

This installs the agents, sets up the vault, configures hooks, and runs `/compass:vision` to capture what you are building. After that you have a self-contained project. Anyone who clones the repo gets the same agents and skills, no plugin install required.

## Open source

Apache 2.0. Issues and contributions welcome.
