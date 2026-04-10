---
name: debug
description: Investigate errors, test failures, or unexpected behavior by spawning the debug agent in an isolated context.
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use when something is broken and you need investigation. Triggers: 'debug this', 'investigate the error', 'why is this failing', 'something is broken'."
argument-hint: "<problem description>"
---

# Debug — Spawn the Debug Agent

Spawn the `debug` agent to investigate a problem in a separate context window (preserving the main conversation's token budget).

## Protocol

1. Pass the problem description, error output, or failing command to the debug agent
2. The debug agent handles the rest — reproduces, investigates, reports findings with CONFIDENCE level
3. The debug agent is READ-ONLY — it reports, it doesn't fix

That's it. This skill is just the entry point. All the logic lives in the agent.
