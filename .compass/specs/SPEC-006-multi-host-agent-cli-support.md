---
title: Compass Runs on Agent CLIs Beyond Claude Code (Kimi Code, Codex)
type: spec
status: approved
confidence: medium
area: methodology
tags: [multi-host, portability, kimi, kimi-code, codex, host-adapter, distribution]
created: 2026-07-22
updated: 2026-07-22
approved: 2026-07-22
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
---

# Compass Runs on Agent CLIs Beyond Claude Code

## Problem

Compass's methodology is portable in principle - a markdown vault, a pipeline, a Python CLI - but its delivery is welded to Claude Code. Everything a user actually interacts with (skills as `/compass:*` commands, subagents, the PostToolUse `compass sync` hook, the Stop/SubagentStop hooks, the plugin install path) exists only in Claude Code's extension model. A developer who works in a different agent CLI cannot use Compass at all, even though the vault and the `compass` CLI would run there unchanged.

The immediate driver: users want Compass on **Kimi Code**, Moonshot's native agent CLI. There are two different senses of "works with Kimi," and only one is a real gap:

1. **Kimi K3 as a model** already runs Compass unchanged - Moonshot serves an Anthropic-compatible endpoint, so pointing Claude Code at it keeps Claude Code as the host and Compass just works. This is a config trick, not a port.
2. **Kimi Code as a host** is a different agent CLI with its own extension model. Running Compass here is the actual unmet need, and the same shape of need applies to OpenAI's Codex CLI.

Without a deliberate host story, every new agent CLI either gets nothing or forces a full fork of the plugin.

## Who is affected

- Developers who prefer or are required to use Kimi Code or Codex instead of Claude Code.
- Teams standardizing on a non-Anthropic agent CLI who still want Compass's spec/research/plan/build/validate discipline and persistent vault.
- The Compass project itself, whose reach is capped at one host.

## Desired Outcome

A user on Kimi Code (and, as a second target, Codex) can run the Compass pipeline - create specs, research, plan, build, validate - against the same `.compass/` vault, with the vault staying correct across sessions, **without maintaining a separate fork per host**. The mechanical guarantees that define Compass (bookkeeping off the agent token budget, an authoritative auto-maintained index, the human-involvement gradient) must survive the port, not be silently dropped.

## Needs (what a solution must satisfy)

- The `.compass/` vault and the `compass` Python CLI work on the new host unchanged (they are already host-agnostic).
- The pipeline's human-involvement gradient is preserved: human decides specs, AI researches, AI proposes plans the human approves, AI builds.
- Mechanical vault upkeep still runs off the agent token budget on the new host (the ADR-005 guarantee), or, where the host cannot trigger it automatically, the degradation is explicit and understood - not a silent loss of the index-freshness guarantee.
- One source of truth for shared logic (vault, CLI, methodology), with per-host differences isolated, so a change to the methodology does not have to be made N times.
- A user can install and update Compass on the new host through that host's own distribution mechanism.

## Constraints

- Must not regress the Claude Code experience or fork the vault format.
- Mechanical work stays in the `compass` CLI off the agent budget ([[ADR-005-compass-cli-for-mechanical-work]]). Note: ADR-005 rejected MCP for the *internal auto-sync path*; it did not rule on cross-host portability of *interactive* commands, which this spec's research phase may legitimately reopen.
- Cross-platform, including Windows, per existing Compass constraints (LF line endings, `python`/`python3`, no daemon).
- The design must tolerate hosts that lack a given mechanism (e.g. no file-write hook) rather than assuming Claude Code's full feature set.

## Hypothesis (falsifiable)

Compass can support at least one additional host (Kimi Code) with a thin per-host adapter over a shared vault + CLI + methodology core, preserving the pipeline and the off-budget bookkeeping guarantee, without forking the plugin.

## Falsification criteria

The spec's premise is wrong if, after investigation, any of these hold:
- No target host can trigger mechanical vault upkeep automatically **and** no acceptable off-budget fallback exists, so the ADR-005 guarantee cannot be preserved on any host but Claude Code.
- Supporting a second host requires duplicating the methodology/skills such that every methodology change must be authored per host (no viable shared core).
- The per-host differences are so deep that a "fork per host" is genuinely cheaper than an adapter layer.

## Success criteria

- A user on Kimi Code can run the full pipeline against a `.compass/` vault and the vault stays correct across sessions.
- Shared logic (vault, CLI, methodology) is authored once; only a bounded per-host adapter differs.
- The off-budget bookkeeping guarantee is either preserved on each host or its degradation is explicit and documented.
- Installing/updating Compass on the new host uses that host's native mechanism.
- The Kimi-K3-via-endpoint quick win is documented separately as the config trick it is, so users are not confused about which "Kimi support" they have.

## Non-Goals

- Choosing the adapter architecture, or deciding MCP vs per-host-native - that is the research/ADR phase.
- Supporting every agent CLI in existence. The targets are Kimi Code first, Codex second.
- Changing the vault format, the pipeline stages, or the artifact schema.
- Shipping the Kimi-K3 endpoint override as a "feature" - it is a documentation note, not part of this port.

## Open questions (for research, after approval)

- Kimi Code's actual extension surface: does it expose lifecycle hooks (a PostToolUse-equivalent that fires on file writes), custom slash commands, subagents, and an install/plugin mechanism? Official docs are currently thin on hooks/commands - this must be confirmed empirically against the installed `kimi` binary. This gates whether the off-budget auto-sync guarantee survives on Kimi Code.
- Codex's file-write hook behavior: sources conflict on whether Codex `PostToolUse` fires on `apply_patch`/file edits. This is load-bearing for the same guarantee and must be verified on the target Codex build before scoping.
- The shared-core vs per-host-adapter boundary: what is authored once and what is translated per host (skills -> host commands, subagents -> host agent format, hooks -> host lifecycle).
- Whether a single portable surface (e.g. an MCP server or plain CLI any host calls) is the right cross-host interface for *interactive* commands, re-evaluating ADR-005's scope; and how auto-sync stays deterministic if a host lacks a native file-write hook.
- The correct Kimi model/endpoint facts to document for the K3-as-model quick win (endpoint URL, model id, any request-parameter caveats).
- Distribution: how a user installs/updates Compass through Kimi Code's and Codex's native package/plugin mechanisms.
