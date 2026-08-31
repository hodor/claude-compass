---
title: "Bare compass Is the Capability Index; Every Dispatch Records Usage; Dead Capability Is Reported, Not Guessed"
type: decision
status: accepted
confidence: high
area: architecture
tags: [discoverability, progressive-disclosure, usage-measurement, cli, dead-code]
taxonomy_hint: "pipeline or a tooling domain; same straddle as SPEC-017"
created: 2026-08-29
updated: 2026-08-29
author: "orchestrator"
summary: "the existing help listing is the progressive-disclosure index, made reachable by one resident rule line; maincli dispatch records every invocation to meta/usage.yaml; compass usage lists never-used commands explicitly; clean-tmp and tree retire; the admission-control pair's fate is decided by the usage record"
depends_on: ["[[SPEC-017-capabilities-are-reachable-and-measured]]", "[[RESEARCH-hermes-agent-capabilities]]", "[[compass-cli/decisions/ADR-005-compass-cli-for-mechanical-work]]"]
---

# Capability Index and Usage Record

## Context

[[SPEC-017-capabilities-are-reachable-and-measured]]: a CLI command no skill names is unreachable, nothing counts usage, and five commands sat dead - among them the entire admission-control mechanism. D-01 adopts both hermes mechanisms (progressive-disclosure index + usage measurement); D-03 makes the miss observable. The hot path is over cap, so the index must not grow it.

## Decision

- **D-01: The index already exists - bare `compass` prints every command with its one-liner from `COMMAND_SPECS`.** Reachability is one resident line in the pipeline rules telling agents the index is one command away (the agent-patterns rule is path-scoped to authoring, so the always-loaded pipeline rule is the surface that reaches every session). Names and one-liners at decision time, bodies only on use; hot-path growth is that single line.
- **D-02: `maincli.dispatch` records every invocation** - command name, count, last date, plus a `since:` stamp on first write - to `.compass/meta/usage.yaml`. Recording never raises, never touches exit codes, and skips silently outside a vault; a corrupt record file is rewritten, never fatal. Harness-owned bookkeeping per [[LESSON-no-agent-bookkeeping]].
- **D-03: `compass usage` is the report.** Three groups: hook-fired entry points (their counts measure the harness, not judgment), judgment-invoked commands, and NEVER USED - zero-count commands listed explicitly, because the visible zero is the observable miss SPEC-017 D-03 demands. `compass doctor` gains an advisory row that warns on never-used commands only once the record is 14 days old - a zero minutes into measurement is not a finding.
- **D-04: Dispositions of the five dead commands.** `clean-tmp` and `tree` retire now - their work lives inline in `sync`, removal is a git revert away. `make-unit` and `unit-check` were already wired by PLAN-009 (vision skill, doctor). `resolve-model`, `touched`, and `admit-check` are named in the methodology skill's capability note and live or die by the usage record - measured disposition, not another guess. Admission control (ADR-004) is therefore explicitly awaiting its wiring decision on data.
- **D-05: Measurement covers CLI commands** (where the dead weight was found - answers the spec's open question); skills and agents are surfaced by the harness already, and `usage.yaml`'s flat schema admits them later without migration.

## Consequences

- Every CLI invocation now pays one small read-modify-write; hooks fire it most, which is fine - the report separates that traffic.
- Two fewer commands ship; `test_track_d.py`'s stale docstring reference to clean-tmp is corrected with it.
- The next dead capability is caught by a zero in a report instead of a human noticing a symptom.
