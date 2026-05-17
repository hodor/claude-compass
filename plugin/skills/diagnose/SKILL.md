---
name: diagnose
description: Investigate errors, test failures, or unexpected behavior in your project by spawning the debug agent in an isolated context. (Named diagnose to avoid colliding with Claude Code's built-in /debug skill.)
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use when something is broken in the project and you need investigation. Triggers: 'diagnose this', 'investigate the error', 'why is this failing', 'something is broken'."
argument-hint: "<problem description>"
---

# Diagnose — Spawn the Debug Agent

Spawn the `debug` agent to investigate a problem in a separate context window (preserving the main conversation's token budget).

The skill is named `/compass:diagnose` (not `debug`) to avoid colliding with Claude Code's built-in `/debug` skill, which debugs Claude Code itself. The agent it spawns is still named `debug` for clarity within Compass.

## Protocol

1. Pass the problem description, error output, or failing command to the debug agent.
2. The debug agent reproduces, investigates, reports findings with a CONFIDENCE level.
3. The debug agent is READ-ONLY — it reports, it doesn't fix.

That's it. This skill is just the entry point. All the logic lives in the agent.
