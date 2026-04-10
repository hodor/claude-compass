---
name: plan
description: Create or iterate on an implementation plan by spawning the planner or planner-iterate agent.
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use when the user wants to plan work or modify an existing plan. Triggers: 'create a plan', 'plan this', 'make a plan', 'update the plan', 'iterate on the plan'."
argument-hint: "[new | iterate <PLAN-NNN>]"
---

# Plan — Spawn the Planner

Spawn the `planner` agent to create a new plan from an approved spec, or the `planner-iterate` agent to modify an existing plan.

## Protocol

1. Parse the argument:
   - **`new`** or no argument → spawn `planner`
   - **`iterate <PLAN-NNN>`** → spawn `planner-iterate` with the plan path
2. Pass the spec reference (if creating new) or plan path (if iterating)
3. The planner handles the rest — outline approval, full plan draft, task creation

That's it. This skill is just the entry point. All the logic lives in the agents.
