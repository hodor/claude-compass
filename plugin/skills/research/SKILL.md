---
name: research
description: Investigate a topic by spawning researcher agents. Can spawn multiple in parallel for different research axes, then consolidates via the reviewer.
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use when the user wants to research something. Triggers: 'research this', 'investigate', 'find out how X works', 'what are the options for'."
argument-hint: "<research question>"
---

# Research — Spawn Researcher Agents

Spawn the `researcher` agent (or multiple in parallel for different axes).

## Protocol

1. Parse the research question
2. Decide: is this one topic or multiple axes?
3. **Single topic** → spawn one `researcher` agent
4. **Multiple axes** → spawn N `researcher` agents in parallel, each investigating one axis
5. If multiple agents were spawned, spawn the `reviewer` agent to consolidate their findings
6. Present results to the human

That's it. This skill is just the entry point. All the logic lives in the agents.
