---
title: Abstract Model Tiers Resolved at Install Time by compass apply-models
type: decision
status: approved
confidence: high
area: methodology
tags: [model-policy, tiers, apply-models, setup, update, tokens, cost]
created: 2026-07-24
updated: 2026-07-24
author: "roger + claude"
depends_on: ["[[SPEC-008-central-model-resolution-table]]", "[[RESEARCH-model-resolution-impl]]", "[[SPEC-006-multi-host-agent-cli-support]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
summary: "Abstract Model Tiers Resolved at Install Time by compass apply-models"
---

## Status

Approved. Implements [[SPEC-008-central-model-resolution-table]].

## Context

[[RESEARCH-model-resolution-impl]] inventoried the current state: 13 agent templates in three inconsistent frontmatter states (5 hardcoded `sonnet`, 6 `inherit`, 2 with no model field), flat `effort: high` everywhere, haiku used nowhere, and policy leaking into skill prose. It verified the mechanism against official docs: agent frontmatter `model:`/`effort:` is a real, hot-reloaded channel with a documented resolution order, and disallowed values degrade to inherit. Setup/update copy templates verbatim with no transformation step.

## Decision

- **D-01:** The policy vocabulary is abstract tiers: `strong`, `balanced`, `cheap`, `inherit`. A per-host catalog maps tiers to concrete model names; the Claude Code catalog ships first, and a host without model selection maps every tier to nothing, degrading to inherit (the [[SPEC-006-multi-host-agent-cli-support]] constraint).
- **D-02:** Resolution happens at install time: setup and update run `compass apply-models` after copying templates, which rewrites the `model:` and `effort:` frontmatter of the known Compass agent files only (per [[LESSON-installer-removes-only-what-it-installed]]), LF line endings preserved. No spawn-time query: a per-spawn CLI round-trip costs agent tokens and depends on prose compliance, violating harness-over-prompts.
- **D-03:** Default assignments (human-approved): `strong` = planner, validator, reviewer, debug; `balanced` = builder, researcher, tester, vault-analyzer, codebase-analyzer, pattern-finder; `cheap` = vault-locator, codebase-locator, pr-describe, and the detached summary job of [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]].
- **D-04:** Precedence: built-in defaults (shipped in the CLI) < project override (`.compass/meta/models.yaml`) < environment. Resolution bottoms out at `inherit` and never exits 2, matching the CLI's structural exit contract.
- **D-05:** Command surface: `compass resolve-model <agent>` prints the resolved model and effort (result on stdout, warnings on stderr); `compass models` prints the full resolved table for inspection.
- **D-06:** Effort is part of the same table row as model; the flat `effort: high` default is replaced by per-tier defaults (cheap agents drop to low effort unless overridden).

## Alternatives considered

- **Spawn-time resolution (skills query the CLI per spawn).** Rejected: costs a Bash round-trip on the agent budget per spawn and relies on prose compliance; install-time injection is deterministic and free at runtime.
- **Concrete model names in the table.** Rejected: welds the policy to one vendor's vocabulary and breaks on SPEC-006 hosts; tiers plus per-host catalog keep the table portable.
- **Leaving the two field-less agents as-is.** Rejected: the inconsistency is the problem being solved; apply-models normalizes all 13.

## Consequences

**Easier:** one file retunes a whole project's cost; cheap agents actually run cheap (haiku enters the roster for the first time); the checkup skill's expectations stop being violated by field-less templates.

**Harder:** setup/update gain a transformation step that must be idempotent and tested; the tier catalog is one more thing SPEC-006's per-host research must fill in per host.

## Load-bearing risks

- The cheap-tier quality claim (locators on haiku lose nothing) is unmeasured; if locator quality drops, the project override is the escape hatch and the default gets revisited.
- Per-invocation model overrides at spawn time exist in the platform but are untested in this repo; nothing in this design depends on them, but future work should not assume them without the five-minute experiment the research suggests.
