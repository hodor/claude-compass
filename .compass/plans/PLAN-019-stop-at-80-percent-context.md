---
title: "Stop and Suggest a Handoff at 80% Context"
type: plan
status: draft
confidence: high
area: methodology
tags: [handoff, context-window, hooks, posttooluse]
created: 2026-10-03
updated: 2026-10-03
depends_on: ["[[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]", "[[research/pipeline/RESEARCH-context-threshold-stop]]"]
summary: "a PostToolUse hook measures the main session's context from its transcript and, once it reaches 80% of the window, halts after the current tool with a stopReason suggesting /compass:handoff; fires once per crossing so the handoff itself runs; Claude Code only"
---

# Stop and Suggest a Handoff at 80% Context

After every main-agent tool call, a hook reads the session transcript, computes how full the context window is, and at 80% or more returns `{"continue": false, "stopReason": ...}`. Claude Code then finishes the tool that just ran, starts nothing new, and shows the human a message suggesting `/compass:handoff` ([[research/pipeline/RESEARCH-context-threshold-stop]] findings 2-4).

## Prerequisites

- CLI suite passes from the repo root: `python -m pytest plugin/cli/tests -q` reports 1028 passed, 1 skipped.
- Changes land in `plugin/` and ship to every Compass user through self-update.

## Desired End State

A Claude Code session whose context reaches 80% of its window stops after the step in progress and tells the human to run `/compass:handoff`. The handoff then runs to completion without being stopped again.

## Design

- **Measure:** used = `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of the last `type: assistant` line, the statusline's own formula (`SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-02`). The window comes from the latest `attachment.type: model` line's `modelId` through Claude Code's model table ([[research/pipeline/RESEARCH-context-threshold-stop]] finding 3): `[1m]` is 1M; Claude 3.x, Opus 4.0-4.6, Sonnet 4.x and Haiku 4.x are 200K; every other model runs 1M natively. `CLAUDE_CODE_DISABLE_1M_CONTEXT` and `CLAUDE_CODE_MAX_CONTEXT_TOKENS` apply as Claude Code applies them, `COMPASS_CONTEXT_WINDOW` overrides all, and an unrecognized model is taken as 1M so a guessed window never halts early.
- **Cost:** the transcript is read from its end, so a long session costs one bounded read per tool call rather than a full parse. The model line sits near the start; its id is cached per `session_id` in `.compass/tmp/context-state.json` and the window recomputed from it each call. With a cached id the scan runs back to the previous usage line, which catches a `/model` switch at the first call after it.
- **Twice at most:** the halt fires the first time a session reaches 80% and once more at 95% (`SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-04`), and the state file records the highest level suggested. Between the two, tool calls pass, so the human's `/compass:handoff` or a choice to keep going is never blocked; a session that jumps past both at once is told once. The record clears when usage drops back under 80%, as after `/compact`, which arms both levels again.
- **Main agent only:** the shell prefilter exits before Python when the event carries `agent_id`. A subagent's halt stops only that subagent (finding 5), and the main context does not grow while a subagent works; the main agent halts at the tool call that returns the subagent's result.
- **Never blocks on failure:** a missing transcript, an unparseable line, or no usage yet means pass, exit 0.

## Phases

### Wave 1 (detailed)

- [x] TASK-137: `compass context-check --hook` - reads the PostToolUse event, measures the main session's context as in Design, and emits the halt once per crossing - complexity: M, depends_on: none, files: [plugin/cli/commands/context_check.py, plugin/cli/maincli.py, plugin/cli/tests/test_context_check.py], decisions: [SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-01, SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-02, SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-04]
  - stopReason text: `Context is at NN% of the window. Compass stopped before the next step - run /compass:handoff to carry this session into a fresh one.`
  - `COMPASS_CONTEXT_THRESHOLD` (integer percent, default 80) exists so the live acceptance can cross the line in a cheap session.
  - Automated verification: `python -m pytest plugin/cli/tests/test_context_check.py -q` passes, with fixture transcripts covering 79% pass, 80% halt, `[1m]` window, second call after a halt passes, drop under 80% re-arms, usage line beyond the tail window still found, missing transcript passes, garbage lines pass, event with `agent_id` passes. `python -m pytest plugin/cli/tests -q` shows no regression.
  - Manual verification: the human reads the stopReason text and confirms it is how he wants to be told.
- [x] TASK-138: Register the hook - one PostToolUse entry with no matcher, shell prefilter skipping `agent_id` events, manifest description updated, version 0.26.0 - complexity: S, depends_on: TASK-137, files: [plugin/hooks/hooks.json, plugin/cli/tests/test_hooks_config.py, plugin/.claude-plugin/plugin.json], decisions: [SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-01]
  - Automated verification: `test_hooks_config.py` asserts the entry exists, references `context-check`, carries the not-installed exit-0 guard and the `agent_id` prefilter; the existing every-command-is-registered test passes; full suite passes.
  - Manual verification: after `/compass:update` in this repo, `.claude/settings.json` holds the entry.
- [ ] TASK-139: Live acceptance in an interactive Claude Code session - complexity: S, depends_on: TASK-138, files: [.compass/research/pipeline/RESEARCH-context-threshold-stop.md], decisions: [SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-01, SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-02, SPEC-025-stop-and-suggest-handoff-at-80-percent-context/D-03]
  - Run a session with `COMPASS_CONTEXT_THRESHOLD` set just above the opening usage, ask for a multi-step task, and record: the step in progress finished, no next step started, the stopReason was visible to the human, and `/compass:handoff` then ran to completion. Append the result to the research document.
  - Automated verification: the probe's hook log shows exactly one halt for the session.
  - Manual verification: the human watches the stop and the handoff happen.

## Risks

- **Transcript fields are undocumented.** The model attachment and the per-message `usage` could change shape in a Claude Code release. The hook passes on anything it cannot read, so a change silences the stop rather than breaking sessions; the TASK-137 tests pin the shape that exists today.
- **Python start-up on every main-agent tool call.** The guard avoids this for the main agent; this hook cannot, because no usage figure exists in the payload. Measured on Windows against a 160K-token transcript: about 220 ms wall per call, shell and interpreter start included.
- **Mid-session `/model` switch** was not probed live. The scan picks up a model line written since the previous API call, which covers it if Claude Code writes one on switch.
- **A future model the table does not name** is taken as 1M. If it runs 200K, the stop never fires and Claude Code's own auto-compact takes over; `COMPASS_CONTEXT_WINDOW` corrects it.

## Verification

- `python -m pytest plugin/cli/tests -q` passes.
- TASK-139's live record shows the halt, the message, and a completed handoff.

## Revision Log

- 2026-10-03: TASK-138 widened to `plugin/cli/commands/self_update.py`, `plugin/skills/setup/SKILL.md` and `plugin/cli/hostlib.py`. Both settings installers registered only the manifest's first PostToolUse group under the sync matcher, so a second group replaced vault sync; they now collapse only the `if`-carrying split groups. The dsh materializer leaves context-check out, since dsh hooks get an empty transcript path and only log the halt (D-03).
- 2026-10-11: The window rule changed from the `[1m]` suffix alone to Claude Code's model table (v0.26.1). Native-1M models carry no suffix, so a session on `claude-opus-5-5` was halted at 16% of its real window (GitHub issue #38). The state file caches the model id, never a computed window, so a session's window follows any correction to the rule.
- 2026-10-14: The handoff is suggested at 80% and once more at 95% (SPEC-025 D-04, v0.26.2). Declining the first suggestion lets work continue to the second.
