---
title: "Handoff: lesson-capture root-caused fleet-wide; SPEC-012 (learning loop) is next; SPEC-011 needs a grep-vs-graph experiment"
type: handoff
status: done
area: methodology
tags: [handoff, learning-loop, lesson-capture, hermes, graph-queries, spec-012, distribution]
created: 2026-08-05
updated: 2026-08-05
git_branch: "master"
git_commit: "2d4911e"
author: "claude"
summary: "lesson capture root-caused; SPEC-012 queued"
---

# Handoff: learning-loop diagnosed, SPEC-012 next

## Start Here

1. [[RESEARCH-lesson-capture-failure]] - the fleet diagnosis that reframes everything: across 40 vaults on F:, the automatic lesson-capture path fired organically ONCE ever (ai-songwriting, and it worked flawlessly). Root cause: capture is coupled to the `/compass:build` phase pause, which real sessions never cross. The 87 outlier lessons bypassed the system (legacy migration + homegrown template).
2. [[RESEARCH-hermes-memory-mechanics]] - hermes memory-update/retrieval deep-dive; a background agent was writing it at handoff time. If it exists, read it; if NOT, the agent died with the session - respawn it (brief is reproducible: trace hermes's memory write path incl. the nudge counter, and read path incl. FTS5 search + skills progressive disclosure; classify each step harness-enforced vs prompt-hoped; hermes clone must be RE-CLONED, the old one died with the session scratchpad: git clone --depth 1 https://github.com/nousresearch/hermes-agent). the human explicitly requires this review in the learning-loop plan.
3. [[active]] "Learning-loop initiative" section - the pillar structure and queue.
4. [[SPEC-011-vault-graph-queries]] - drafted, NOT approved. the human's D-02: run a grep-vs-graph experiment before any build; if grep answers the query classes cheaply, reject the spec.

## Session Summary (this was a long multi-day session)

Shipped v0.4.0 (pushed): SPEC-007 decision coverage (D-NN parser, compass decisions/coverage, planner gate, validator audit), SPEC-008 model table (modelslib, resolve-model/models/apply-models, 13 templates normalized), SPEC-010 hybrid hierarchy (unit folders, unit-aware CLI, make-unit; the compass-cli set migrated into .compass/compass-cli/). Validator BATCH PASS, 242 tests. Vision (SPEC-001) revised: harness-over-prompts principle, configurable pipeline (SPEC-009 drafted, DEFERRED), hybrid hierarchy. Competitive research: OKF, gsd-core, hermes-agent (2 docs), graph engineering (+ Anthropic-playbook addendum), RAG-for-large-vaults. Hermes verdict: stay on Claude Code, treat hermes as SPEC-006 host candidate #1 (its shell hooks speak Claude Code's hook protocol - compass sync ports as-is), steal FTS5 session search / curator snapshot-rollback / compression trigger / trajectory compressor (backlogged). Then the human challenged lesson capture; fleet diagnosis confirmed catastrophic failure and root cause.

## Decisions (made by the human, this session)

- **D-01:** Compass becomes "a framework that learns" like hermes, but with Compass discipline; a plan is required.
- **D-02:** Graph engineering joins the plan where it makes sense (retrieval substrate candidate).
- **D-03:** The plan MUST review how hermes updates its memory for lessons and how it retrieves (research in flight / respawn if missing).
- **D-04:** SPEC-011 is not accepted on faith: grep-vs-graph experiment first (recorded as SPEC-011 D-02).
- **D-05:** Capture-fix is sequenced before retrieval/application (diagnosis reordered the pillars).
- **D-06:** Distribution of v0.4.0 across repos precedes the Codex/Kimi (SPEC-006) research work.

## Next Actions (in order)

1. [ ] Verify [[RESEARCH-hermes-memory-mechanics]] exists; respawn the deep-dive if not (see Start Here 2).
2. [ ] Draft SPEC-012 (learning loop): pillar 1 capture-fix (decouple from build-phase pause; attach to events that actually occur - session end/handoff, validation completion, debug resolution, conversational build waves; preserve the anti-list/dedup/5-line core, whose one organic firing is the quality benchmark; add compass doctor-style install verification to update/checkup). Pillar 2 retrieval (auto-surface relevant lessons; hermes findings + possibly SPEC-011 substrate). Pillar 3 application audit (coverage-style, lessons: citations - see backlog "Lesson-coverage parity"). Cite the hermes-memory research as a D-bullet so coverage enforces D-03.
3. [ ] Walk the human through SPEC-012 (plain language, one doc per message, never assume he read the files - standing preference).
4. [ ] On approval -> planner (research is complete) -> build with the wave protocol.
5. [ ] SPEC-011 experiment (grep vs graph on the named query classes) - can run as part of SPEC-012's research or standalone; its outcome decides SPEC-011.
6. [ ] Distribution pass: /compass:update to v0.4.0+ across the fleet - the audit found 19/40 vaults cannot run the Stop-hook backstop and 3 stale v0.2.0 partial installs; product-owner has a known blocked-.claude-write friction. Then SPEC-006 hosts (hermes first).

## Operational lessons for the next orchestrator (already in the vault as lessons)

- [[LESSON-subagent-worktrees-fork-stale]]: commit between waves; builders fast-forward worktrees to master; carry-back file lists.
- [[LESSON-long-agents-stall-resume-them]]: a completion notice ending in mid-task narration is a stall - SendMessage "continue from where you stopped", never respawn. Hit ~5 times this session (also: forbid sub-agent spawning in researcher briefs, or their children report to the wrong parent).

## Blockers

None. All state committed and pushed through `2d4911e` (plus this handoff commit).

## Context for Resuming

- Scratchpad clones (gsd-core, hermes-agent) and the fleet-audit raw outputs died with the session; re-clone if needed. The audit's full per-vault table is reproduced in the two diagnostic agents' reports, whose essentials are in [[RESEARCH-lesson-capture-failure]].
- Hot path is near its 5,000 cap (~4,900 after this handoff lands); if the next session sees a cap warning, trim active.md's done sections or run /compass:consolidate.
- SPEC-009 (configurable pipeline) remains deliberately DEFERRED in backlog; SPEC-005 remains ON HOLD.
- The Kimi-K3-as-model quick win (ANTHROPIC_BASE_URL to Moonshot) is documented in SPEC-006's context; the real Kimi Code port waits behind distribution.
