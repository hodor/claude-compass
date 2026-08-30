---
title: "SubagentStop Is Deduped on agent_id; Typed Signals Stay for Inline Spawns; Teammates Are Typed from Their Name"
type: decision
status: accepted
confidence: high
area: architecture
tags: [hooks, capture, signals, subagentstop, teammates, observation]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "live payload observation falsifies the dead-code claim - agent_type is populated for inline spawns and empty only for teammates - and reveals SubagentStop double-delivery, now deduped on agent_id"
depends_on: ["[[SPEC-012-learning-loop]]", "[[ADR-013-detached-worker-quiet-fallback]]"]
lessons: ["[[LESSON-hook-payloads-observe-before-coding]]"]
---

# SubagentStop Redelivery and Teammate Typing

## Context

The backlog carried this since 2026-08-08 as "typed signals are dead code fleet-wide": a payload captured then showed `agent_type` arriving as an empty string, so `SIGNAL_KINDS` fell to `unknown` every time and no `validator-finished` / `debug-finished` / `builder-finished` strong signal had ever fired. The entry pre-registered the question to settle before any fix - does an inline `Agent`-tool spawn populate `agent_type`? - per [[LESSON-hook-payloads-observe-before-coding]].

Observed 2026-08-30 in this repo by dumping raw hook stdin and spawning a probe:

- **An inline (unnamed) spawn populates `agent_type`.** A `debug` probe produced `agent_type: debug` and a `debug-finished` signal; an unrelated `reviewer` completion in a concurrent session did the same. The typed path works and has been working.
- **A teammate-style (named) spawn arrives with `agent_type: ""`.** Five such deliveries in the dump, all empty. The payload carries no name field either - only `agent_id`, transcript paths, `last_assistant_message`, and a `background_tasks` list.
- **SubagentStop is delivered twice for one completion** - identical `agent_id`, 9ms apart. Every subagent has been writing two capture files and recording two signals; for a validator or debug finish, that is a doubled STRONG signal, which opens capture opportunities on its own.

The dead-code premise was half wrong, and a defect nobody had named was doing more damage than the one on the ticket.

## Decision

- **D-01: `SIGNAL_KINDS` stays.** It is live for inline spawns, which is how every Compass skill spawns its agents. Retiring it would have deleted working behavior on a false premise.
- **D-02: Dedupe on `agent_id`.** Recently-seen ids live in the capture state (bounded at 40); a re-delivery records nothing. An empty id is never deduped, since it identifies nothing and two unrelated completions must not collapse into one.
- **D-03: Type a teammate from its name.** On `TeammateIdle`, a name whose leading token is a known agent type (`validator-wave-3`) records that typed kind; every other name keeps the weak activity signal. The match is a whole leading token - `debugger-x` is not a debug agent - so an unrelated name cannot manufacture a strong signal.
- **D-04: No naming mandate ships.** Typing is opportunistic: a name that carries its type is used, and nothing is required of any caller.

## Consequences

- Capture cadence halves on the subagent path; opportunities now open on real completion counts.
- The fleet-wide "dead code" claim is retired from the backlog as falsified in part.
- Teammate completions gain typed signals only where the orchestrator's chosen name says the type; the honest default remains for the rest.
