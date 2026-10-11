---
title: "Measuring Context Usage and Stopping at a Threshold from a Hook"
type: research
status: done
confidence: high
area: methodology
tags: [handoff, context-window, hooks, posttooluse, transcript, dsh, subagents]
created: 2026-10-03
updated: 2026-10-11
git_branch: master
git_commit: 6bad043
depends_on: ["[[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]"]
summary: "Claude Code hooks get no usage figure, but the transcript holds per-call input tokens and the model ID, whose window follows Claude Code's model table; a PostToolUse hook returning continue:false halts after the current tool and shows its stopReason - proven live for the main agent and for subagents; dsh passes an empty transcript_path and ignores continue:false"
---

# Measuring Context Usage and Stopping at a Threshold from a Hook

Evidence for [[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]. Live probes ran `claude -p --model haiku --settings <probe>` on Claude Code 2.1.288 with a logging hook. Their files are in the session scratchpad (`ctxtest/hook.py`, `ctxtest/log.jsonl`) and are not kept.

## Findings

**1. No Claude Code hook event carries context usage.** The common input fields are `session_id`, `prompt_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `permission_mode`, `effort`, `hook_event_name`, plus `agent_id` and `agent_type` inside a subagent. The probe logged the PostToolUse keys as exactly `cwd, duration_ms, hook_event_name, permission_mode, prompt_id, session_id, tool_input, tool_name, tool_response, tool_use_id, transcript_path`. Only the statusline receives `context_window.used_percentage` and `context_window_size`. Source: code.claude.com/docs/en/hooks, /statusline; live probe. Confidence: high.

**2. The used figure can be computed from the transcript.** Each `type: assistant` line carries `message.usage`. The statusline's `used_percentage` is defined as `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of the latest API response, with output excluded. The probe computed it from the transcript at PostToolUse time and got a plausible value (19,943 tokens). The docs warn that the transcript "is written asynchronously and may lag", but the assistant message that issued the tool call was present in every probe. Source: /statusline "context window fields"; live probe. Confidence: high.

**3. The window size comes from the model id in the transcript's model attachment, read through Claude Code's model table.** Every session transcript has a line with `attachment.type: "model"` and `identity.modelId`; no transcript field and no hook payload carries the window itself. The suffix alone does not decide it: Claude Code's model configuration states that "Fable 5.1, Fable 5, Sonnet 5 and later, Haiku 5.5, and Opus 4.7 and later run with the 1M window by default, with no `[1m]` suffix needed", while "Opus 4.6 and Sonnet 4.6 reach 1M only through their `[1m]` variant". A live session on `claude-opus-5-5` (no suffix) reported `160.9k / 1m tokens (16%)` in `/context` (GitHub issue #38). Across every transcript on this machine the model ids are `claude-sonnet-5-5`, `claude-sonnet-5`, `claude-opus-5-5`, `claude-opus-5`, `claude-haiku-4-5-20251001`, and `[1m]` variants of Fable and Opus, so a session's spelling of the id varies with how the model was picked, never with its window. `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` holds native-1M models at 200K, and `CLAUDE_CODE_MAX_CONTEXT_TOKENS` sets the window Claude Code assumes for an unrecognized id. Source: code.claude.com/docs/en/model-config; transcript tally; issue #38. Confidence: high for the documented models, medium for future ones, which the table cannot name in advance.

**4. A PostToolUse hook returning `{"continue": false, "stopReason": ...}` halts after the current step.** In the probe the model was told to make two Bash calls. The hook stopped it after the first: `a.txt` was written, `b.txt` was not, and the run ended with `num_turns: 2`. The tool that already ran completes, and no new step starts, which is the behavior D-01 asks for. The docs say `stopReason` is "shown to the user ... stays in the conversation, so Claude sees it if the conversation continues", so it can carry the handoff suggestion. The Stop hook did not fire after the halt, so Compass's `capture-check` block cannot restart the agent. Source: /hooks JSON output table; live probe. Confidence: high.

**5. Inside a subagent, `continue: false` stops only that subagent.** In the probe the subagent was halted after its first Bash call (`b.txt` missing), and the main agent went on to its own next call (`c.txt` written) and finished. A subagent's hook gets the main session's `transcript_path`, and its own transcript sits at `<transcript_path without .jsonl>/subagents/agent-<agent_id>.jsonl`. Measuring a subagent's own fill therefore needs that path. Source: live probe; filesystem. Confidence: high.

**6. On dsh, neither half works today.** The dsh Claude Code hook bridge sends `transcript_path: ''` ("The persistence seam exposes no artifact path", `packages/hooks/hooks-claude-code/src/index.ts:330-332`). It parses `continue: false` but only logs it: `// TODO(hook-continue-false): merged.stop is logged but needs a run-level halt mechanism` (`index.ts:195`). Its sessions live under `$DSH_HOME/sessions` as `.jsonl.zstd` ([[research/distribution/RESEARCH-dsh-live-probes]]). Source: deepseek-harness at 5badb15 (2026-10-03), code read. Confidence: high.

## Gap

The dsh half is open. It needs either an upstream dsh change (a transcript path and a run-level halt) or a dsh-specific route to the session's token count and a way to stop it. That calls for a research pass of its own, run against dsh's session store and agent loop.
