---
title: "Mechanical state assembly: what Compass can build with no model call"
type: research
status: complete
confidence: medium
area: methodology
tags: [handoff, compaction, transcript, hooks, session-continuity]
summary: "Open tasks, files touched, last request, tests and git state are assemblable from transcript, vault and git in about 1,000-2,500 tokens with no model call; decisions and the current step are only partly mechanical."
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
depends_on: ["[[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]"]
---

# Mechanical state assembly

From [[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]] (the compaction-survival need), axis 3 of [[research/pipeline/compaction-survival/index]].

## Question

Which parts of the state a session's next step depends on can Compass assemble with no model call from the transcript, the vault and git, how reliably, and what does Compass carry today?

## Methodology

Repository mining (an empirical study of the artifact): the shipped `plugin/` code was read, and the structure (keys and shapes only, no content) of up to five real Claude Code transcripts, 0.8 MB to 24 MB, plus one subagent transcript, was mined with throwaway scripts; a prototype assembler was run on five of them. Chosen because the axis asks how an existing system actually behaves.

Grading: allowed. Every finding here rests on code read or commands run locally (evidence type: first-party measurement on one user's transcripts, host version 2.1.328 to 2.1.330). No finding is peer-reviewed, retracted, a preprint, or cited; convergence is noted per finding. Transcript fields are undocumented by the host, so field findings are observations of two host versions, not a contract.

## Findings

### A. What the transcript carries, and how reliably

1. **Files read and edited are exact, with a Read/Edit/Write distinction** (confidence: high)
   Assistant records hold `tool_use` blocks; `Read`, `Edit` and `Write` carry `input.file_path` (Read also `offset`, `limit`; Edit also `old_string`, `new_string`, `replace_all`; Write also `content`). The matching user record carries a `toolUseResult` with `filePath`, `structuredPatch`, `userModified` for edits. Across the sampled sessions every Read/Edit/Write input had `file_path`.
   - Prototype run on a 24 MB session: 27 files read, 47 edited, in 0.29 s.
   - `plugin/cli/sessionslib.py:154-160` - `_blocks(record, "tool_use")` already extracts these blocks.
   - Marks: first-party measurement, n/a retraction, n/a preprint, 0 citations, convergent across 3 transcripts
   - Grade: high (measured, repeated)

2. **Edits made through Bash are visible only partly** (confidence: medium)
   `sed -i`, heredoc Python and `git` writes do not appear as Edit/Write. A Bash `toolUseResult` can carry `bashEditDiff` with `changedFiles`, `files`, `moreFiles` (present on 271 of 1,241 tool results in the largest session), but the list includes unrelated working-tree changes (164 distinct paths in one session, mostly vault noise), so it does not separate "this session touched it" from "dirty before".
   - Marks: first-party measurement, n/a, n/a, 0, single host version
   - Grade: medium (measured, field semantics inferred from values)

3. **The last user request is mechanical, with a filter** (confidence: high)
   User records with string `message.content` hold typed prompts. Records that are not requests share the type: `tool_result` carriers (1,241 of 1,468 user records in the largest session), task notifications (`origin.kind = "task-notification"`, `promptSource: "system"`, 171), meta records (`isMeta`), and the compact summary (`isCompactSummary`). Human prompts carry `origin.kind = "human"` and `promptSource` of `typed`, `suggestion_accepted` or `queued`. A `last-prompt` record (fields `lastPrompt`, `leafUuid`) is also written per turn. A naive "last string user record" returned a notification, not the human's words, until filtered.
   - Marks: first-party measurement, n/a, n/a, 0, convergent across 3 sessions
   - Grade: high

4. **Open background tasks come from host attachments and Agent calls** (confidence: medium)
   `attachment` records of type `task_status` carry `taskId`, `taskType`, `description`, `status`, `deltaSummary`, `outputFilePath`, `canContinueAgent`. Agent tool_use blocks carry `description`, `subagent_type`, `run_in_background`, `isolation`; their results carry `agentId`, `status`, `outputFile`. `task_status` appeared in 2 of the 3 sessions checked for it.
   - Marks: first-party measurement, n/a, n/a, 0, partial convergence (not in every session)
   - Grade: medium

5. **No TodoWrite/TaskCreate task list exists in any transcript sampled** (confidence: high)
   Zero `TodoWrite` and zero `TaskCreate` tool calls across all 234 transcripts of this project. The tool inventory is Bash, Agent, SendMessage, Edit, Read, Write, AskUserQuestion, ToolSearch, Skill, TaskStop, Monitor. Compass keeps its task list in the vault, not in a host tool, so "open tasks" come from `active.md` and plans (finding 10), not the transcript.
   - Marks: first-party measurement, n/a, n/a, 0, convergent (234 of 234)
   - Grade: high for this project; other projects may use the tool

6. **Failing tests are only readable from stdout text, never from a status field** (confidence: high)
   A Bash `toolUseResult` holds `stdout`, `stderr`, `interrupted`, `isImage`, `noOutputExpected`; there is no exit code. In a run whose output matched `\d+ failed`, the tool_result had `is_error: false`. `is_error` is `true` only for tool-level failures (23 of 1,241 in the largest session). Detecting a failing test therefore means matching the command (`pytest`, `npm test`) and parsing the tail of its output; a `git commit` line or a heredoc that merely contains the word "pytest" matches the command regex (6 of 14 pytest-matching commands in one session were not test runs).
   - Marks: first-party measurement, n/a, n/a, 0, convergent across 2 sessions
   - Grade: high that no field exists; medium that the regex is reliable

7. **Decisions taken are mechanical only where the human answered a structured question** (confidence: medium)
   `AskUserQuestion` results carry `questions`, `answers`, `annotations` in `toolUseResult` (25 calls in the largest session). Free-text decisions in the conversation have no field. Decisions in vault documents carry `D-NN` bullets (grep-able, see the `obsidian` skill's `documents.md`).
   - Marks: first-party measurement, n/a, n/a, 0, single session type
   - Grade: medium

8. **The current step has no field; the last assistant text block is a proxy** (confidence: medium)
   Nothing in the transcript names "the current step". The last assistant `text` block (or the last `tool_use`) is available mechanically; in the prototype it ranged from 128 to 1,304 chars and was sometimes a closing summary, not a plan for the next step. Plan task checkboxes give a step only when the session was executing a plan.
   - Marks: first-party measurement, n/a, n/a, 0, convergent across 5 sessions
   - Grade: medium

9. **The host already writes compaction structure into the transcript** (confidence: high)
   A `system` record `subtype: compact_boundary` carries `compactMetadata` (`trigger`, `preTokens`, `postTokens`, `preservedSegment`, `preservedMessages`, `preCompactDiscoveredTools`, `durationMs`); the summary is a user record with `isCompactSummary: true`. After the boundary the host re-injects attachments: `compact_file_reference` (a file path and display path), `task_status`, `invoked_skills`, and `file` (saved copies). `compact_boundary` subtype records counted: 5 in the 24 MB session, 1 in the 6.3 MB one. So the host's own carry-over already includes a file list and background-task status; a Compass block would add what these omit (read/edit split, tests, decisions, the human's last request, open vault tasks).
   - Marks: first-party measurement, n/a, n/a, 0, convergent across 2 sessions
   - Grade: high

10. **Subagent transcripts are separate files with their own marks** (confidence: high)
    A session `S.jsonl` has a sibling folder `S/subagents/` holding `agent-<id>.jsonl` and `agent-<id>.meta.json` (546 transcripts across the project). Subagent records carry `isSidechain: true` and `agentId`; the meta file carries `agentType`, `description`, `toolUseId`, `spawnDepth`, `model`, `finished`. A main-session assembler that reads only `S.jsonl` sees the Agent call and its result, not the subagent's own Reads and Edits. `sessionslib.subagent_transcripts` already globs these files.
    - `plugin/cli/sessionslib.py:137-142` - subagent file discovery
    - `plugin/cli/commands/context_check.py:143,261-262` - `isSidechain` records and events with `agent_id` are skipped
    - Marks: first-party measurement and code read, n/a, n/a, 0, convergent
    - Grade: high

### B. Vault and git

11. **Open tasks and the plan are plain-text reads** (confidence: high)
    `.compass/active.md` holds only open work (the sweep moves `[x]` lines out, per `CLAUDE.md`), so `- [ ]` lines are the open tasks: 22 lines, about 150 tokens in this repo. A plan's `- [ ] TASK-NNN` lines give the current phase. The hot path (index, active, lessons index) is already capped at 5,000 tokens ([[SPEC-003-hierarchical-vault-organization]]) and loads at session start, so `active.md` is already in front of a session that restarts; only a mid-session compaction loses it from view.
    - `plugin/skills/handoff/SKILL.md:24` - handoff already reads the hot path
    - Marks: first-party measurement, n/a, n/a, 0, convergent
    - Grade: high

12. **Git state is five commands, already scripted in the handoff skill** (confidence: high)
    `git rev-parse --abbrev-ref HEAD`, `git rev-parse --short HEAD`, `git log --oneline -5`, `git status --short`, `git diff --stat`. `plugin/skills/handoff/SKILL.md:26-33` runs exactly these by model call each time; no CLI command wraps them. In this repo `git status` is noisy with vault files, so a state block restricted to non-`.compass/` paths is shorter.
    - Marks: code read, n/a, n/a, 0, convergent
    - Grade: high

### C. What Compass carries today

13. **A handoff is model-written** (confidence: high)
    The create protocol has the model run git, read the hot path, reconcile `index.md`, then write a markdown document: Start Here, Session Summary (2-3 sentences), Tasks, Recent Changes, Decisions, Learnings, Blockers, Uncommitted Changes, Action Items, Context for Resuming. Every section is composed by the model; none is read from the transcript. It also has "Failed approaches and uncommitted changes are the most valuable parts" (line 20) yet no step collects failed approaches mechanically. Resume verifies git branch and commit, then classifies the handoff as clean, diverged, incomplete or stale.
    - `plugin/skills/handoff/SKILL.md:20,26-47,49-97,108-170`
    - Marks: code read, n/a, n/a, 0, convergent
    - Grade: high

14. **The context-stop hook measures, stops and suggests; it assembles no state** (confidence: high)
    `compass context-check --hook` (PostToolUse, no matcher) reads the transcript tail in 256 KB chunks, sums `input_tokens + cache_creation_input_tokens + cache_read_input_tokens` of the latest main-agent assistant message, resolves the window from the model id, and at 80% and 95% prints `{"continue": false, "stopReason": ...}` once per level. The stopReason is a fixed string pointing at `/compass:handoff`. It records `{model, offered}` per session in `.compass/tmp/context-state.json` (50 sessions kept). It was built by [[PLAN-019-stop-at-80-percent-context]] (TASK-137, TASK-138, v0.26.0; window rule revised v0.26.1).
    - `plugin/cli/commands/context_check.py:197-212,258-282,285-312`
    - `plugin/hooks/hooks.json` PostToolUse entry 1 - shell prefilter exits before Python for events carrying `agent_id`/`agent_type`
    - Marks: code read, n/a, n/a, 0, convergent
    - Grade: high

15. **Hooks registered: no PreCompact, PostCompact or SessionStart-compact entry** (confidence: high)
    `plugin/hooks/hooks.json` registers PreToolUse (guard), PostToolUse (context-check, sync x3), SessionStart (self-update on `startup` only, capture-check), Stop (capture-check), TeammateIdle and SubagentStop (capture-signal). A grep of `plugin/cli` and `plugin/hooks` for `PreCompact`, `PostCompact`, `compact_boundary`, `isCompactSummary` returns no code hit. The host events and their payloads are covered by [[research/llm-research/RESEARCH-axis-2-host-features]] (PreCompact stdout up to 10,000 chars steers the summary; PostCompact receives `compact_summary`) and by axis 1 of this research.
    - `plugin/hooks/hooks.json` (entire file); `.compass/research/llm-research/RESEARCH-axis-2-host-features.md:62,297`
    - Marks: code read, n/a, n/a, 0, convergent
    - Grade: high

16. **Reusable transcript helpers already exist** (confidence: high)
    - `sessionslib.records(path)` - forward JSONL iterator that skips unparseable lines (`:145-151`).
    - `context_check._records_backward(path)` - chunked reverse reader (`:163-183`); `_parse` (`:186-194`).
    - `sessionslib._blocks(record, type)` - content blocks of a record, tolerant of wrong shapes (`:154-160`); `_message_text` (`:163-173`).
    - `sessionslib.subagent_transcripts`, `commit_count` (Bash `git commit` regex over tool_use inputs, `:40-49,226-238`), `plan_ids`/`task_ids` (`PLAN-N`/`TASK-N` from message text, `:241-254`), `model_id`, `used_tokens`, `is_active`, `entrypoint`.
    - Missing: any extractor for Read/Edit/Write `file_path`, `AskUserQuestion` answers, test-run output, `task_status`, `compact_boundary`, or the last human prompt.
    - Contract stated in the module docstring: readers never raise on a malformed record (`sessionslib.py:16-19`).
    - Marks: code read, n/a, n/a, 0, convergent
    - Grade: high

### D. Size and cost of a mechanically assembled block

17. **A state block measures about 1,000 to 2,600 tokens, dominated by file lists and the open-task list** (confidence: medium)
    Throwaway assembler run on five transcripts (rendering: last request truncated at 500 chars, last assistant text at 400, edited and read paths, Bash-changed paths, question answers, test tails, background tasks, open `active.md` tasks, git log/status/stat). Tokens estimated at 4 chars each.
    - 24 MB session: 10,286 chars, about 2,570 tokens (47 edited, 27 read, 164 Bash-changed, 22 open tasks, 5 answers).
    - 6.3 MB: about 1,240 tokens. 2.5 MB: about 1,090. 0.8 MB: about 1,070. 0.76 MB: about 930.
    - Of the 24 MB case, the `Edited:` line alone was 3,307 chars (about 830 tokens) and the Bash-changed list 892 chars.
    - Open tasks from `active.md` were constant at 22 lines (about 600 chars, 150 tokens) in every run.
    - Context for scale: the 24 MB session's last request carried 406,302 cache-read tokens, so the block is under 1% of a full window.
    - Rendering with relative paths and a cap per list is a design variable not tested here.
    - Marks: first-party measurement on 5 transcripts, n/a, n/a, 0, convergent in magnitude; token count is a 4 chars/token estimate, not tokenized
    - Grade: medium (measured, tokenizer not applied)

18. **Assembly time is small** (confidence: high)
    The prototype parsed the 24 MB transcript fully in 0.29 s and a 0.76 MB one in 0.01 s. `context-check` already pays Python start-up on every main-agent tool call (see [[PLAN-019-stop-at-80-percent-context]] Risks, measured against a 160K-token transcript); a one-off assembly at the 80% crossing, or in a PreCompact hook, is a single pass.
    - Marks: first-party measurement, n/a, n/a, 0, convergent
    - Grade: high

### E. Summary by state element

| Element | Source | Mechanical? | Reliability |
|---|---|---|---|
| Open tasks | `active.md` `- [ ]` lines, plan checkboxes | yes | high; transcript has no task tool (finding 5) |
| Files read | tool_use `Read.file_path` | yes | high |
| Files edited | tool_use `Edit/Write.file_path`; partly `bashEditDiff` | yes, with a gap for Bash edits | high / medium |
| Decisions | `AskUserQuestion` answers; vault `D-NN` | partly | medium; free-text decisions have no field |
| Current step | last assistant text; plan checkboxes | proxy only | medium |
| Last user request | user record, `origin.kind: human` | yes | high with filter |
| Failing tests | stdout text of test commands | yes, by regex | medium; no exit code field |
| Background work | `task_status` attachments, Agent results | yes | medium |
| Git state | five git commands | yes | high |

## Contradictions

- Finding 13 says the handoff is wholly model-written, while finding 16 shows most of its inputs (git state, files, tasks, commit count, plan ids) already have mechanical sources or helpers in `plugin/cli`; the skill does not call them.
- The handoff skill's "failed approaches are the most valuable part" (`SKILL.md:20`) has no mechanical source in the transcript (finding 8): failed attempts show only as `is_error: true` tool results (23 of 1,241) or failing-test output, neither a field naming an "approach".

## Gaps

- Which of the elements above a probe (axis 4) shows to matter most for the next step is not measured here; this axis shows what can be assembled, not what is needed.
- Free-text decisions and the reason an approach failed have no mechanical source; closing them needs a model call or a convention for the agent to log them (for example `compass capture-note`, which exists, `plugin/skills/lessons/SKILL.md`), which was not tested.
- Whether `bashEditDiff.changedFiles` can be made session-specific (diff against a start-of-session `git status`) was not tested.
- Field names come from host versions 2.1.328 to 2.1.330 on one machine; a later host release may rename them. `context_check`'s docstring (`:1-36`) and the PLAN-019 risk section already state this exposure.
- Token counts use a 4 chars/token estimate and one rendering; a tokenizer run and alternative renderings were not done.
- Whether the PostCompact and SessionStart-compact payloads let a Compass hook inject the assembled block, and with what size cap, belongs to axis 1.
