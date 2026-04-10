---
name: spec
description: Create a new specification by spawning the spec-writer agent. Interviews the human one question at a time to capture the problem and desired outcome.
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use when the user wants to create a new specification. Triggers: 'new spec', 'create a spec', 'write a spec', 'spec this', 'I want to spec'."
---

# Spec — Spawn the Spec-Writer

Spawn the `spec-writer` agent. It will interview the human one question at a time to capture the problem and desired outcome, then create a draft spec in `.compass/specs/`.

## Protocol

1. Spawn the `spec-writer` agent
2. Pass any context from the user's request (what they want to spec)
3. The spec-writer handles the rest — interview, draft, review, approve

That's it. This skill is just the entry point. All the logic lives in the agent.
