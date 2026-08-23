---
title: Work Too Big for One Spec Gets the Bigger Shape Without the Human Knowing the Machinery
type: spec
status: approved
approved: 2026-08-23
confidence: high
area: methodology
tags: [sizing, units, hierarchy, discoverability, vision, defaults]
created: 2026-08-23
updated: 2026-08-23
depends_on: ["[[SPEC-010-universal-hybrid-hierarchy]]", "[[SPEC-003-hierarchical-vault-organization]]"]
summary: "work too big for one spec gets the bigger shape without the human knowing the machinery (approved 2026-08-23)"
---

# Work Too Big for One Spec Gets the Bigger Shape Without the Human Knowing the Machinery

## Problem

When a need is too big to be one spec, Compass has no path to the bigger shape. The shapes exist, folder specs and unit folders, but nothing reaches them at the moment sizing gets decided.

`/compass:vision` emits a flat list of N specs by construction; nothing in it can say "this one is an epic." `/compass:spec` knows exactly one remedy for a bloated spec, split it into siblings, which is the wrong answer when the need is genuinely one coherent problem with many sub-problems. `compass unit-check` only notices after three artifact types already trace to a spec, so research and a plan must exist first, and no skill or hook ever runs it anyway. `compass make-unit` refuses to create a unit without at least one artifact to move, so even a human who knows the command cannot declare a workspace up front. `/compass:spec` writes to `.compass/specs/` unconditionally, so in a vault that already has units it puts the spec in the wrong place.

The result: the human gets monster specs, and the only exit is to already know units exist and ask for them by name. The human who most needs the bigger shape is the one least likely to know it exists.

Observed 2026-08-22 (Roger): a vision session in a game project produced seven needs, each of them an epic worth six to eight specs. Compass proposed seven flat specs and gave no signal anything was wrong. The correct shape was found only because the human said "those specs are monsters" and the session then went looking for mechanisms it had never been told about.

## Who is affected

- The human, who ends up with unusable specs and no indication that a better shape was available.
- A first-time Compass user, who has no vocabulary to ask for what they need.
- The vision and spec skills, which carry one sizing rule ("if you write 'and also', they are separate") that produces breadth and can never produce depth.
- Every downstream stage, which inherits the wrong granularity: research scoped to an epic, plans that cannot be waved, validation with nothing crisp to check.

## Decisions (made by the human)

- **D-01:** Both creation paths ship: a workspace declared up front and empty, and an existing flat spec converted into one later. Today only the second is possible, and only by hand. (Roger, 2026-08-23.)
- **D-02:** Compass never asks the human how Compass should run. It judges the sizing and acts, then says what it did. Modeled explicitly on hermes: "it never asks me how hermes should be running, it just runs." (Roger, 2026-08-23.)
- **D-03:** What Compass says about the sizing is said at most once. If the human would rather not hear it again, they say so and Compass proceeds silently from then on. (Roger, 2026-08-22.)
- **D-04:** The machinery is never named to a human who did not ask for it. Plain words only, never "unit", "folder spec", or a command name. (Roger, 2026-08-22.)
- **D-05:** The behavior is configurable, and directly callable by name for a human who does know it. Invisible by default is not the same as unavailable. (Roger, 2026-08-22.)

## Desired Outcome

A human who has never heard the word "unit" gets correctly-sized work anyway. When a need is too big for one spec, Compass sizes it correctly on its own, at the moment it matters rather than several stages later, and it does so without asking permission to operate. It states in plain language what shape it gave the work, once. The human can reverse that, or tell Compass to stop mentioning it, after which Compass keeps sizing silently. A human who knows the feature can invoke it by name, and a human who wants different behavior can configure it instead of living with the default.

## Needs

- A sizing judgment available where needs are first enumerated and where a spec is written, not only after research and a plan already exist.
- Creation of an empty workspace with no artifact to move.
- Conversion of an existing flat spec into a workspace, carrying the file.
- Spec authoring that writes into the workspace the work belongs to instead of always the vault root.
- An actual caller for the existing lagging detector, so it stops being inert.
- A per-project preference that persists across sessions and governs whether the notice is spoken.
- A named, direct invocation path for a human who knows what they want.

## Non-Goals

- The general problem that Compass capabilities go unreachable and unmeasured. Five CLI commands are referenced by no skill, hook, or template at all; that is a larger problem for which this spec is one instance, and it gets its own spec.
- Choosing the mechanism. Whether the sizing judgment lives in a skill step, a hook, or a CLI gate is a research and ADR question, not a spec question.
- Retrofitting vaults that already contain monster specs.

## Open Questions

- The project where this was observed is not recorded. Pin the project path and session so the motivating case stays findable, per [[LESSON-pin-the-motivating-datum]].
