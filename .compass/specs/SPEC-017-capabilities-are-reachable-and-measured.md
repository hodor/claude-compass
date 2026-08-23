---
title: A Capability No Skill Happens to Name Is Never Used, and Compass Cannot Tell Which Ones Those Are
type: spec
status: approved
approved: 2026-08-23
confidence: high
area: architecture
tags: [discoverability, progressive-disclosure, usage-measurement, cli, dead-code]
created: 2026-08-23
updated: 2026-08-23
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[SPEC-016-sizing-work-beyond-one-spec]]"]
---

# A Capability No Skill Happens to Name Is Never Used, and Compass Cannot Tell Which Ones Those Are

## Problem

A Compass capability is reachable only if some skill body happens to mention it in prose. Skills themselves are surfaced to the agent by name and description, so the agent can find them; nothing below skill level has that property. A CLI command that no skill names is invisible to the agent, and therefore to the human, however well it works.

An audit on 2026-08-23 cross-referenced all 28 shipped CLI commands against every skill, template, and hook:

- Seven have no caller anywhere: `make-unit`, `unit-check`, `admit-check`, `touched`, `resolve-model`, `clean-tmp`, `tree`.
- Two of those duplicate work `sync` already does inline (log pruning, tree rendering), so they are redundant rather than lost.
- Five are genuine capability that has never been reachable. Among them, `admit-check` and `touched` are a pair, and that pair is the entire admission-control mechanism specified in [[ADR-004-hierarchical-specs-with-facets]]. Nothing records a working-set marker, so admission control has never run in any vault, in any project, since it shipped.

Nothing in Compass counts usage. There is no per-capability invocation record anywhere in the codebase. So a capability that is never invoked looks exactly like one invoked constantly, and five dead commands sat unnoticed until a human noticed a symptom of one of them and a manual cross-reference went looking.

The cost compounds: work is spent building and testing capability that cannot be reached, the vault records it as shipped, and the human hits the underlying problem anyway with no idea a solution was already paid for.

## Who is affected

- The human, who hits problems Compass already solved.
- Skill authors, who must remember to name every relevant command in prose, forever, or the command dies quietly.
- The agent, which cannot use what it is never told exists.
- The project, which cannot distinguish live capability from dead weight when deciding what to maintain.

## Decisions (made by the human)

- **D-01:** Adopt both hermes mechanisms, not one. Surfacing by progressive disclosure (an index of names and one-line descriptions available at decision time, full detail paged in only when judged relevant) and usage measurement (a per-capability record, with a background pass over what goes unused). (Roger, 2026-08-23, on [[RESEARCH-hermes-agent-capabilities]] findings 15 and 16: "pretty cool stuff from hermes that we should implement both.")
- **D-02:** Compass never asks the human how Compass should run. A capability surfaces and runs on Compass's own judgment. "It never asks me how hermes should be running, it just runs." (Roger, 2026-08-23.)

## Desired Outcome

Every shipped capability is discoverable by the agent at the moment it becomes relevant, without any skill author having remembered to name it. Discovery costs nothing when the capability is not relevant: the index is cheap, the detail is paid for only on use. Separately, Compass can say which capabilities are actually used and which are dead, so a dead capability is caught by the system rather than by a human noticing a symptom months later.

## Needs

- An index of capabilities, name plus one line, reachable by the agent at decision time rather than buried in skill prose.
- Full detail paged in only when the agent judges the capability relevant, so nothing is paid for by default.
- A per-capability usage record that persists.
- A report separating live capability from dead.
- A disposition for dead capability: wired up, merged into what supersedes it, or retired. Not left to accumulate.
- The five currently-unreachable commands resolved under that disposition, admission control included.

## Constraints

- The hot path is already 7,591 tokens against a 5,000 cap. Any surfacing mechanism must not grow it. Progressive disclosure is what buys this: an index of one-liners, not bodies.
- Compass's north-star goal 4 (mechanical work in scripts and hooks, never in agent tokens) applies. Usage recording is bookkeeping and belongs in the CLI or a hook, per [[LESSON-no-agent-bookkeeping]].

## Non-Goals

- The sizing problem, which is [[SPEC-016-sizing-work-beyond-one-spec]]. This spec is the general case; that one is a specific instance with its own missing capability.
- Choosing where the index lives (system prompt injection, a CLI command, a generated skill). Research and ADR question.
- Automatic deletion. Hermes's curator archives and never deletes; retirement stays reversible.

## Open Questions

- Does the measurement cover CLI commands only, or skills and agents too? Hermes measures skills; Compass's dead weight was found in commands.
