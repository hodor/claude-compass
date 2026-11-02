---
title: "Compass's Whole Overhead, Measured on Real Projects"
type: spec
status: approved
confidence: low
area: tooling
tags: [tokens, cost, loops, measurement]
summary: "how much of a real project build's tokens is Compass overhead, measured in whole and by area, so the biggest areas shrink first"
created: 2026-11-01
updated: 2026-11-01
approved: 2026-11-01
---

# Compass's Whole Overhead, Measured on Real Projects

```mermaid
flowchart LR
  P["Problem: Compass overhead<br/>is not measured in its entirety"] --> O["Outcome: agents build real projects<br/>with Compass; every token measured,<br/>broken down, and going smaller"]
  O --> D1["D-01: agents pick the topic"]
  O --> D2["D-02: projects are thrown away<br/>unless really cool"]
  O --> D3["D-03: biggest areas first"]
```

## Problem

We would need to understand how to measure Compass overhead in its entirety and break that down.

Compass's overhead is every token a session spends because Compass is installed: the text it loads, the agents and commands it runs, and the work they do. The measure in [[SPEC-027-compass-uses-fewer-tokens]]'s loop counts only the text Compass ships, weighted by how often sessions load it, which is part of the overhead, not all of it.

## Desired Outcome

Have agents create projects with Compass and build something with Compass while you analyze EVERYTHING, like whole token usage, and you run things and make changes and see if Compass's token usage goes smaller.

Agents act as humans on projects and really build something.

KPI: across many builds, each from first setup to the result the agent set out to build, the share of tokens that is Compass overhead goes down from the first measured baseline, while the agents still finish what they set out to build.

## Decisions

> [!NOTE]
> - **D-01:** I would let them decide the topic, because we want this to be really generic and work with anything.
> - **D-02:** Temporary things we can throw away (or keep if they build something really cool).
> - **D-03:** Break that down and optimize the biggest areas first.
