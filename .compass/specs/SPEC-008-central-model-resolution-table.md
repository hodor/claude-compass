---
title: Model and Effort Assignment Is Harness-Resolved Policy, Not Per-Agent Prose
type: spec
status: approved
confidence: high
area: methodology
tags: [model-policy, harness, tokens, cost, configuration, per-agent, determinism]
created: 2026-07-22
updated: 2026-07-23
approved: 2026-07-23
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[ADR-005-compass-cli-for-mechanical-work]]", "[[RESEARCH-gsd-core-improvements-for-compass]]"]
---

# Model and Effort Assignment Is Harness-Resolved Policy, Not Per-Agent Prose

## Problem

Which model and reasoning effort each Compass agent runs on is decided ad-hoc and scattered. There is no single place that says "the locator agents run on a cheap model, the planner and validator run on the strongest one." Changing a model assignment means hunting through agent definitions; tuning cost for a whole project is impossible without editing many files; and nothing lets a user override the defaults for their own budget or their own host.

This is a policy decision - a small table of facts - trapped inside prose. It is exactly the kind of mechanical, deterministic concern that should be resolved by the harness from data, not carried in agent instructions. Leaving it in prose costs tokens (goal 4), defeats per-project tuning, and makes the single highest-leverage cost lever (route cheap work to a cheap model) invisible and unmaintainable.

## Who is affected

- The user, who cannot tune model/cost policy for a project in one place, or match it to their host and budget.
- Every agent, whose model assignment is implicit and non-portable rather than resolved from a known policy.
- Compass's token/cost goal, which has no central lever to pull.

## Desired Outcome

A single, declarative policy - data the harness reads, not prose an agent carries - assigns a model and reasoning effort to each agent, with sensible defaults, overridable per project. Changing which model an agent uses is a one-line edit in one place. An agent does not state its own model; the harness resolves it at spawn time. Routing cheap agents to a cheap model and expensive reasoning to the strongest model becomes a visible, tunable dial.

## Needs (what a solution must satisfy)

- One declarative source of truth mapping each agent (or each class of agent) to a model tier and reasoning effort.
- Sensible built-in defaults, so nothing must be configured for Compass to work out of the box.
- Per-project override, so a user can retune the whole policy for their budget without editing agent definitions.
- Resolution happens in the harness (the `compass` CLI / spawn path), off the agent token budget, per [[ADR-005-compass-cli-for-mechanical-work]].
- Agents stop declaring their own model; model choice is data, resolved for them.
- Degrades safely on hosts that do not expose model selection (fall back to the host default rather than failing).

## Hypothesis (falsifiable)

If model and effort assignment lives in one harness-resolved policy table with per-project override, then a user can retune the cost/quality of the whole pipeline from one place, cheap agents demonstrably run on cheaper models, and no agent definition needs to name a model - lowering token/cost with no loss of output quality on the tasks that need the strong model.

## Falsification criteria

The premise is wrong if any hold after implementation:
- Changing an agent's model still requires editing that agent's definition.
- There is no single place a user can retune model policy for a whole project.
- The policy is resolved by an agent reading instructions rather than by the harness.
- A host without model selection breaks instead of falling back to its default.
- The table cannot express both a coarse default (per agent class) and a specific override (one named agent).

## Success criteria

- One declarative table assigns model + effort per agent/class; agents name no model themselves.
- Built-in defaults work with zero configuration.
- A per-project override retunes the whole policy without touching agent definitions.
- Cheap agents (locators) resolve to a cheap model; heavy-reasoning agents (planner, validator, reviewer) resolve to the strong model - verifiable by inspecting resolved assignments.
- Resolution runs in the harness, off the token budget.
- On a host lacking model selection, resolution falls back cleanly.

## Constraints

- Policy resolution is mechanical work in the `compass` CLI / spawn path ([[ADR-005-compass-cli-for-mechanical-work]]); it must not consume agent tokens.
- Reuses existing config conventions rather than a new config system.
- Cross-platform, LF, `python`/`python3`.
- Must compose with [[SPEC-006-multi-host-agent-cli-support]]: different hosts expose different model vocabularies, so the table resolves against a per-host model catalog rather than hardcoding one vendor's model ids.

## Non-Goals

- Choosing the exact tier vocabulary, the config file format, or the resolution precedence order - that is the research/ADR/plan phase. (Prior art: GSD's `model-resolver` + `model-profiles` with an `AGENT_TO_PHASE_TYPE` → default-tier mapping and a project-config override; see [[RESEARCH-gsd-core-improvements-for-compass]] and verified source `src/model-resolver.cts`.)
- Automatic/dynamic model selection based on task difficulty at runtime. This is static, declared policy with manual override.
- Changing what the agents do, only how their model is assigned.

## Open questions (for research, after approval)

- The tier vocabulary and how it maps to concrete per-host model ids (goal-strong / balanced / cheap / inherit vs named models).
- The resolution precedence (built-in default → per-agent default → project override → env override) and how it stays deterministic.
- Whether effort/reasoning level is part of the same table or a parallel one.
- How the table composes with the multi-host model catalog from [[SPEC-006-multi-host-agent-cli-support]].
