---
title: The Pipeline Is a Configurable Workflow, Not One Hardcoded Sequence
type: spec
status: draft
confidence: high
area: methodology
tags: [pipeline, workflow, configurable, phases, customization, harness]
created: 2026-07-22
updated: 2026-07-22
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]"]
---

# The Pipeline Is a Configurable Workflow, Not One Hardcoded Sequence

## Problem

Compass's development pipeline is fixed: Vision → Spec → Research → Plan → Build → Validate, baked into the skills, the methodology, and the agents' assumptions. But there is no single right sequence. One team runs Vision → Spec → Research → Build → Test → Ship. Another wants a lightweight Spec → Build → Validate for small work, or an extra Design phase, or a Security-review gate before Ship. Today none of that is possible without editing the plugin itself. The workflow is a strong default masquerading as a law, and it forces every project into one shape regardless of how that team actually works.

This blocks adoption (teams reject a methodology that will not bend to theirs) and it contradicts the harness-over-prompts principle: which phases exist and in what order is configuration data, not something that should be hardwired into prose across many skills.

## Who is affected

- Teams whose real workflow differs from Compass's default and who currently cannot express it.
- The human, who cannot tune the pipeline to the size of the work (heavy pipeline for a big feature, light one for a small fix).
- The plugin itself, whose phase assumptions are scattered across skills instead of declared in one place.

## Desired Outcome

Compass ships a sensible default pipeline, and a project can configure its own: reorder phases, drop phases it does not want, and add phases it does. The phase vocabulary is declared as configuration the harness reads, not hardcoded into each skill. A user picks or defines a workflow once, and the pipeline, the agents, and the guidance follow it.

## Needs (what a solution must satisfy)

- A shipped default workflow that works with zero configuration.
- A project-level way to reorder and subset the built-in phases.
- A way to define additional phases beyond the built-in vocabulary.
- The active workflow is declared as data the harness resolves, so no skill hardcodes "the next phase is X."
- Guidance and agents adapt to the configured workflow rather than assuming the default sequence.
- Degrades safely: a project with no configuration gets the default; a malformed configuration fails loud, not silently into a wrong sequence.

## Decisions (made by the human)

- **D-01:** A workflow configures the contracts between phases, not only their order. Cross-phase rules that today hardcode artifact types (decision coverage from specs/ADRs into plans per [[SPEC-007-decision-coverage-tracing]]; research traces to an approved spec; plans trace to spec + research; validation compares plan to implementation) are roles a workflow declares: which phase's artifacts bear decisions, which phase's artifacts must cover them, what traces to what, and which status transition carries each gate. The shipped default workflow declares the current contracts, so an unconfigured project behaves exactly as today.

## Hypothesis (falsifiable)

If the pipeline is a declared, harness-resolved workflow with a shippable default and project-level override, then a team can run its own phase sequence (e.g. Vision → Spec → Research → Build → Test → Ship) without editing the plugin, and Compass's guidance follows the configured workflow rather than the default.

## Falsification criteria

The premise is wrong if any hold after implementation:
- Changing the phase sequence for a project requires editing plugin skills rather than a project configuration.
- A skill still hardcodes "after phase X comes phase Y" in a way that ignores the configured workflow.
- A project cannot add a phase the default vocabulary does not include.
- A malformed workflow configuration silently runs the default (or a wrong sequence) instead of failing loud.
- The default stops working out of the box for projects that never configure anything.

## Success criteria

- The default pipeline runs with no configuration.
- A project can reorder and subset the built-in phases via configuration, no plugin edit.
- A project can add a phase beyond the built-in set.
- The active workflow is declared as data; the harness resolves "what is the next phase" from it.
- Compass's guidance and agents reflect the configured workflow.
- A malformed workflow configuration fails loud.

## Constraints

- Workflow resolution is mechanical: the harness reads the configured workflow, per [[SPEC-001-compass-vision-and-architecture]]'s harness-over-prompts principle and [[ADR-005-compass-cli-for-mechanical-work]].
- Reuses existing config conventions rather than a new config system.
- Must compose with [[SPEC-006-multi-host-agent-cli-support]] (workflow config is host-agnostic) and with the artifact types each phase produces.
- Cross-platform, LF, `python`/`python3`.

## Non-Goals

- Choosing the configuration format, the built-in phase vocabulary's final contents, or how a custom phase binds its agents and artifacts - that is the research/ADR/plan phase.
- A visual workflow builder or GUI.
- Per-run ad-hoc phase invention. This is declared, project-level workflow configuration, not improvisation mid-task.
- Changing what any individual phase does internally.

## Open questions (for research, after approval)

- The workflow-declaration format and where it lives (a `meta/` config file, frontmatter, a dedicated command).
- How a custom phase declares its agent(s), the artifact type(s) it produces, and its entry/exit gates. Prior art: GSD's capability manifests inject prompt fragments at named loop points and declare gates per phase (see [[RESEARCH-gsd-core-improvements-for-compass]]); study the shape, not the framework.
- How the human-involvement gradient maps onto user-defined phases (which new phases are human-decides vs AI-executes).
- How reordering interacts with artifact dependencies (research traces to an approved spec; a workflow that puts research before spec must be caught or allowed deliberately).
- The edge-declaration format for cross-phase contracts (per D-01): how a workflow names its decision-bearing role, its covering role, its tracing edges, and its gate transitions, and how much of that a minimal custom workflow must fill in vs inherit from defaults.
- The default phase vocabulary and its exact names.
