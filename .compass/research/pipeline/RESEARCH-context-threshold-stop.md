---
title: "Measuring Context Usage and Stopping at a Threshold from a Hook"
type: research
status: done
confidence: high
area: methodology
tags: [handoff, context-window, hooks, posttooluse, transcript, dsh, subagents]
created: 2026-10-03
updated: 2026-10-03
git_branch: master
git_commit: 6bad043
depends_on: ["[[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]"]
summary: "Claude Code hooks get no usage figure, but the transcript holds per-call input tokens and the model ID that sets the window; a PostToolUse hook returning continue:false halts after the current tool and shows its stopReason - proven live for the main agent and for subagents; dsh passes an empty transcript_path and ignores continue:false"
---

# Measuring Context Usage and Stopping at a Threshold from a Hook

Evidence for [[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]. Live probes ran `claude -p --model haiku --settings <probe>` on Claude Code 2.1.288 with a logging hook. Their files are in the session scratchpad (`ctxtest/hook.py`, `ctxtest/log.jsonl`) and are not kept.

## Findings

**1. No Claude Code hook event carries context usage.** The common input fields are `session_id`, `prompt_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `permission_mode`, `effort`, `hook_event_name`, plus `agent_id` and `agent_type` inside a subagent. The probe logged the PostToolUse keys as exactly `cwd, duration_ms, hook_event_name, permission_mode, prompt_id, session_id, tool_input, tool_name, tool_response, tool_use_id, transcript_path`. Only the statusline receives `context_window.used_percentage` and `context_window_size`. Source: code.claude.com/docs/en/hooks, /statusline; live probe. Confidence: high.

**2. The used figure can be computed from the transcript.** Each `type: assistant` line carries `message.usage`. The statusline's `used_percentage` is defined as `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of the latest API response, with output excluded. The probe computed it from the transcript at PostToolUse time and got a plausible value (19,943 tokens). The docs warn that the transcript "is written asynchronously and may lag", but the assistant message that issued the tool call was present in every probe. Source: /statusline "context window fields"; live probe. Confidence: high.

**3. The window size comes from the transcript's model attachment.** Every session transcript has one line with `attachment.type: "model"` and `identity.modelId`. A 1M session reads `claude-opus-5-5[1m]`, while 200K sessions carry no suffix (checked on 15 transcripts in this project). The statusline docs give `context_window_size` as "200000 by default, 1000000 models extended context". So the rule is: `[1m]` means 1,000,000, and anything else means 200,000. A mid-session `/model` switch was not probed; reading the last model attachment covers it if one is written. Confidence: medium-high, because the attachment is an undocumented transcript field.

**4. A PostToolUse hook returning `{"continue": false, "stopReason": ...}` halts after the current step.** In the probe the model was told to make two Bash calls. The hook stopped it after the first: `a.txt` was written, `b.txt` was not, and the run ended with `num_turns: 2`. The tool that already ran completes, and no new step starts, which is the behavior D-01 asks for. The docs say `stopReason` is "shown to the user ... stays in the conversation, so Claude sees it if the conversation continues", so it can carry the handoff suggestion. The Stop hook did not fire after the halt, so Compass's `capture-check` block cannot restart the agent. Source: /hooks JSON output table; live probe. Confidence: high.

**5. Inside a subagent, `continue: false` stops only that subagent.** In the probe the subagent was halted after its first Bash call (`b.txt` missing), and the main agent went on to its own next call (`c.txt` written) and finished. A subagent's hook gets the main session's `transcript_path`, and its own transcript sits at `<transcript_path without .jsonl>/subagents/agent-<agent_id>.jsonl`. Measuring a subagent's own fill therefore needs that path. Source: live probe; filesystem. Confidence: high.

**6. On dsh, neither half works today.** The dsh Claude Code hook bridge sends `transcript_path: ''` ("The persistence seam exposes no artifact path", `packages/hooks/hooks-claude-code/src/index.ts:330-332`). It parses `continue: false` but only logs it: `// TODO(hook-continue-false): merged.stop is logged but needs a run-level halt mechanism` (`index.ts:195`). Its sessions live under `$DSH_HOME/sessions` as `.jsonl.zstd` ([[research/distribution/RESEARCH-dsh-live-probes]]). Source: deepseek-harness at 5badb15 (2026-10-03), code read. Confidence: high.

## Gap

The dsh half is open. It needs either an upstream dsh change (a transcript path and a run-level halt) or a dsh-specific route to the session's token count and a way to stop it. That calls for a research pass of its own, run against dsh's session store and agent loop.
