---
title: "Host compaction hooks: PreCompact, PostCompact, SessionStart(compact)"
type: research
status: complete
confidence: high
area: methodology
tags: [compaction, hooks, precompact, postcompact, sessionstart, claude-code, transcript]
created: 2026-11-21
updated: 2026-11-21
git_branch: master
git_commit: 6faced1
author: researcher
summary: "Live trial on Claude Code 2.1.330: PreCompact stdout steers the summary, SessionStart(source=compact) additionalContext lands after the summary, PostCompact is observe-only, the summary is readable in the PostCompact payload and as an isCompactSummary transcript line"
---

# Host compaction hooks: PreCompact, PostCompact, SessionStart(compact)

From [[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]] (the need added 2026-11-21: what survives compaction and handoff).

## Question

What do Claude Code's PreCompact, PostCompact and SessionStart (source `compact`) hooks receive, and what can their output do to the compaction summary and the post-compaction context?

## Methodology

Repository mining in its "how does an existing system behave" shape, run as an empirical study of the artifact: a logging hook was registered for the three events through `--settings` and driven with `claude -p --model haiku` on Claude Code 2.1.330 (haiku 5.5), with codeword markers in each hook's output, then read from the stream, the hook log and the session transcript; the vendor hooks page was read for what the trial could not reach. Code over documentation: the trial is the primary source, the docs second. Probe files live in the session scratchpad and are not kept. Grading was allowed: each finding carries a grade for how much its evidence type weighs.

## Findings

1. **Compaction can be triggered in print mode with a manual `/compact <instructions>` on a resumed session.** `claude -p --resume <id> --input-format stream-json --output-format stream-json --verbose --include-hook-events`, with `{"type":"user","message":{"role":"user","content":"/compact <text>"}}` on stdin, ran a real compaction (46,718 tokens before, 9,536 after, 7.8 s) and exited `success`. Passing `/compact ...` as the plain argv prompt from Git Bash did not compact: MSYS rewrote it to `C:/Program Files/Git/compact ...` and the model received it as text; `MSYS_NO_PATHCONV=1` is the standard bypass (not tried). A bare `--output-format json` run of the stream-json route returned `num_turns: 0`.
   - Evidence: local trial (`compact_boundary` event in the stream, `compactMetadata` line in the transcript); the argv mangling is visible in the summary's "All user messages" list.
   - Marks: local trial, code behavior observed; not retracted; no preprint; no citations; 1 source (own trial), repeated twice
   - Grade: high

2. **PreCompact payload: `custom_instructions`, `cwd`, `hook_event_name`, `prompt_id`, `session_id`, `transcript_path`, `trigger`.** Sample: `trigger: "manual"`, `custom_instructions: "Keep KIWI-SEED-12 and mention pears."` (the text typed after `/compact`). The trigger field is `manual` or `auto`; only `manual` was produced locally, `auto` is from the docs matcher text ("what triggered compaction").
   - Evidence: local trial log, PreCompact record; https://code.claude.com/docs/en/hooks (PreCompact matcher `manual`/`auto`, exit-code table row "Blocks compaction")
   - Marks: local trial plus vendor docs; not retracted; no preprint; no citations; 2 sources agree on the field set
   - Grade: high for `manual`, medium for `auto` (not run)

3. **PreCompact plain stdout is added to the compaction instructions and visibly steers the summary.** The hook printed `Preserve the codeword PRECOMPACT-ZEBRA-41 verbatim in the summary.` The generated summary preserved it, labelled "from compaction instructions, not a user message", and the host's `/compact` result line echoed the hook text. Both the user's `/compact` text and the hook's stdout reached the summarizer together.
   - Evidence: local trial: summary text in the PostCompact payload and in the transcript summary line; docs say stdout "becomes instructions for compaction summary" and is exempt from the 10,000-character file-spill rule for other hook output (the exact PreCompact cap sits in a docs section not reached)
   - Marks: local trial plus vendor docs; not retracted; no preprint; no citations; 2 sources agree
   - Grade: high

4. **SessionStart with `source: "compact"` fires once per compaction; its `additionalContext` is stored and sent to the model.** Payload keys: `cwd`, `hook_event_name`, `model`, `prompt_id`, `session_id`, `source`, `transcript_path` (sample `source: "compact"`, `model: "claude-haiku-5-5"`). The stream shows `hook_started`/`hook_response` named `SessionStart:compact`. The transcript stores the output as an `attachment` of type `hook_additional_context` (`content: ["SESSIONSTART-FALCON-93 source=compact"]`) directly after the summary and the re-attached environment/skill/model attachments. An isolated probe (finding 11) confirmed the model reads it as a system-reminder worded `SessionStart hook additional context: <text>`.
   - Evidence: local trial: SessionStart log record, `compact_boundary` ordering, transcript attachments after the summary line; https://code.claude.com/docs/en/hooks (SessionStart `additionalContext` inserted at the start of the conversation, 10,000-character cap, spill to a file with a 2,000-character preview)
   - Marks: local trial plus vendor docs; not retracted; no preprint; no citations; 2 sources agree
   - Grade: high

5. **PostCompact payload: `compact_summary`, `cwd`, `hook_event_name`, `prompt_id`, `session_id`, `transcript_path`, `trigger`.** `compact_summary` holds the full summary text (1,781 characters here), starting with an `<analysis>` block that the summary stored in the transcript does not carry (the stored line begins "This session is being continued..." then "Summary:" with numbered sections). So the payload and the stored summary differ in framing.
   - Evidence: local trial log, PostCompact record; transcript line with `isCompactSummary`
   - Marks: local trial; not retracted; no preprint; no citations; 1 source
   - Grade: high

6. **PostCompact cannot inject context: `hookSpecificOutput` with `hookEventName: "PostCompact"` fails schema validation.** The host replied "Hook JSON output validation failed ... expected one of PreToolUse | UserPromptSubmit | ... SessionStart ...", and the PostCompact line in the `/compact` result showed `failed`. The accepted top-level fields are `continue`, `suppressOutput`, `stopReason`, `decision`, `reason`, `systemMessage`, `terminalSequence`. The docs list PostCompact exit 2 as "Shows stderr user only" and omit it from the decision-control and `additionalContext` lists.
   - Evidence: local trial: validation error text in the transcript's `/compact` stdout line; https://code.claude.com/docs/en/hooks (exit-code table)
   - Marks: local trial plus vendor docs; not retracted; no preprint; no citations; 2 sources agree
   - Grade: high

7. **PreCompact exit code 2 blocks a manual compaction, confirmed locally.** The hook wrote to stderr and exited 2; no `compact_boundary` event appeared, the run ended `success` with `num_turns: 0`, and the result text read `Compaction blocked by PreCompact hook: [<command>]: <stderr text>`. The `decision: "block"` JSON form and `onFailure: "block"` are documented but were not run. The docs' exit-code table reads "PreCompact | Yes | Blocks compaction"; PostCompact and SessionStart cannot block. Whether an auto compaction can be blocked the same way (the session would then hit the window limit) was not tried.
   - Evidence: local trial (stream result line); https://code.claude.com/docs/en/hooks (exit-code table); [[research/llm-research/RESEARCH-axis-2-host-features]] finding f5
   - Marks: local trial plus vendor docs; not retracted; no preprint; no citations; 3 sources agree
   - Grade: high for exit 2 on manual, medium for the JSON form and auto

8. **The summary is readable in the transcript as a `user` line with `isCompactSummary: true` and `isVisibleInTranscriptOnly: true`, preceded by a `system` line with `subtype: compact_boundary`.** The boundary carries `compactMetadata`: `trigger`, `preTokens` (46,718), `postTokens` (9,536), `durationMs`, `cumulativeDroppedTokens`, `preservedSegment` (head, anchor, tail uuids) and `preservedMessages`. The summary line's last paragraph names the full pre-compaction transcript path ("read the full transcript at ..."), and recent messages after the summary are kept verbatim. The stream-json output exposes the same boundary as `compact_metadata`.
   - Evidence: local trial: transcript lines (boundary then `isCompactSummary` user line), stream `compact_boundary` event
   - Marks: local trial; not retracted; no preprint; no citations; 1 source (own trial)
   - Grade: high

9. **Event order in one manual compaction: PreCompact, SessionStart(compact), PostCompact; the transcript is then rewritten with the boundary, summary and re-attached attachments.** The hook log order was PreCompact, SessionStart (source `compact`), PostCompact, all sharing one `prompt_id`. A plain resume of a session also fires SessionStart with `source: "resume"` and extra keys `context_tokens`, `seconds_since_last_response`, `prompt_cache_likely_expired`, `estimated_cache_write_usd`; the startup source carries only `cwd`, `hook_event_name`, `session_id`, `source`, `transcript_path`.
   - Evidence: local trial log ordering and keys
   - Marks: local trial; not retracted; no preprint; no citations; 1 source
   - Grade: high

10. **Compass has no registration for any of the three events as compaction handlers.** `plugin/hooks/hooks.json` registers SessionStart only with matcher `startup` (`compass self-update`) and an unmatched entry (`capture-check`, so it also fires on `compact`); no PreCompact or PostCompact key exists; grep of `plugin/` for `PreCompact|PostCompact|isCompactSummary|"compact"` returned no match.
    - Evidence: `plugin/hooks/hooks.json:65-87` (SessionStart block, first matcher `startup`, second entry matcherless); grep over `plugin/`
    - Marks: code read; not retracted; no preprint; no citations; 1 source (own grep)
    - Grade: high

11. **A compact-source-only SessionStart codeword reached the model, in the same process and on a later resume.** The hook emitted `NARWHAL-58` only when `source == "compact"` (the resume hook emitted nothing). After `/compact` and a follow-up message in one stream-json process, the model quoted `SessionStart hook additional context: The compaction codeword is NARWHAL-58.` A later fresh `--resume` process asked about the string and quoted it again. One earlier resume probe, asked an open "any codeword?" question, named only a PostCompact string and missed it, so an unprompted model may not surface the text; the transcript held the string in an `api-request-blob` line (the request body) and in the `hook_additional_context` attachment.
    - Evidence: local trial (stream assistant text; transcript lines with `NARWHAL`)
    - Marks: local trial; not retracted; no preprint; no citations; 1 source, 3 probes with one miss
    - Grade: high that it is sent, medium that the model attends to it

12. **PostCompact accepts the generic output fields: `systemMessage` ran as `completed successfully`.** The string appeared only in the `/compact` command's own output line, which the transcript stores as a user-role `local-command-stdout` line, so the model also saw it when later asked. PostCompact still has no context channel of its own (finding 6).
    - Evidence: local trial (the `/compact` stdout transcript line; model quoted `POSTCOMPACT-SYSMSG-OTTER`)
    - Marks: local trial; not retracted; no preprint; no citations; 1 source
    - Grade: high

13. **A model's "I see codeword X" answer is unreliable evidence in this trial.** The first probe's model claimed to see four strings, then in the next probe retracted three of them (`FALCON`, `ZEBRA`, `OTTER-77`) as not present. Delivery claims in this document rest on the transcript request body and on a codeword unique to one hook, not on a first self-report.
    - Evidence: local trial (two consecutive probe answers)
    - Marks: local trial; not retracted; no preprint; no citations; 1 source
    - Grade: high

## Contradictions

- The first visibility probe said the model saw the SessionStart, PostCompact and PreCompact strings; the second said it saw none of them but one PostCompact system message (finding 13). The compact-only probe (finding 11) resolves it for SessionStart.
- The prior vault note says SessionStart `additionalContext` is accepted after compaction ([[research/llm-research/RESEARCH-axis-2-host-features]] f5, f13); the trial agrees.

## Gaps

- `trigger: "auto"` was not produced (no `/compact` command to drive it); `--autocompact <tokens>` (at least 100k) exists in `claude --help` and could drive it with a long enough session.
- PreCompact `decision: "block"` JSON and `onFailure: "block"` were not run; auto-compaction blocking was not run.
- The exact PreCompact stdout size cap lives in a docs section (`#precompact-output`) past the part of the page that could be read.
