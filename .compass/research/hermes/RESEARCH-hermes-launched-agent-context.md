---
title: "How Hermes builds the context of an agent it launches, compared with Compass"
type: research
status: complete
confidence: medium
area: architecture
tags: [hermes-agent, subagents, delegation, context, background-review, cron, moa, batch, agent-memory]
created: 2026-11-04
updated: 2026-11-04
git_branch: "master"
git_commit: "71dd0be"
author: "claude (researcher)"
depends_on: ["[[SPEC-028-agent-memory-is-good-enough]]", "[[SPEC-027-compass-uses-fewer-tokens]]", "[[RESEARCH-hermes-memory-mechanics]]", "[[RESEARCH-hermes-skill-creation]]", "[[RESEARCH-hermes-changes-since-july]]"]
summary: "five Hermes launch paths (delegate_task, review fork, cron, MoA, batch) compared on prompt, tools, memory, skills, history, brief, result size and budgets, against Compass agent frontmatter and spawn briefs"
---

# How Hermes builds the context of an agent it launches, compared with Compass

Hermes paths are relative to the clone root (commit a212421d, 2026-11-04). Compass paths are relative to the repo root.

## Question

For each way Hermes launches an agent (delegated subagents, the background review fork, cron jobs, mixture-of-agents presets, batch runs): which system prompt, tools, memory, skills, history and files does the launched agent get, what is left out, how is its brief written, how do results return and how large may they be, and what token budgets apply; and how does Compass launch agents by comparison.

## Methodology

Repository mining: how an existing codebase actually behaves, read from the code at the pinned commit (not the docs). No disclosure about grading reached this run, so findings are marked and ungraded. Marks on every Hermes finding: code, owner checked (official NousResearch repository); not retracted; not a preprint; no citation count applies; one source (the code), no second independent source.

## What is new against the earlier Hermes studies

The earlier studies cover the review fork's trigger and write paths ([[RESEARCH-hermes-skill-creation]]), memory caps and the frozen snapshot ([[RESEARCH-hermes-memory-mechanics]]). Not covered before: the delegate_task prompt and toolset construction, the summary budget and spill file, the review fork's cache-parity construction and input budget, cron prompt assembly, the MoA advisory view, and batch isolation flags. Findings 1-31 are those.

## Findings: delegated subagents (delegate_task)

1. **The child is a fresh agent with its own conversation; the parent sees only the final summary** (confidence: high)
   - Module header: fresh conversation, own task id (terminal session, file-ops cache), the parent's toolsets minus blocked tools, a focused prompt built from goal plus context. The parent never sees the child's intermediate tool calls or reasoning.
   - `tools/delegate_tool.py:1-11` - module contract.
   - `tools/delegate_tool.py:293-309` - AIAgent kwargs for the child (`quiet_mode`, `platform="subagent"`, `side_agent`, `iteration_budget=None` meaning a fresh budget).
   - Marks: code, owner checked; 1 source.

2. **The child system prompt is one sentence plus three optional blocks plus completion instructions** (confidence: high)
   - Order: "You are a focused subagent working on a specific delegated task."; `CONTEXT:` (the model-written `context` string); `WORKSPACE PATH:` plus the project context files; the completion instructions; for orchestrator children a spawn-capability block with a literal depth note.
   - The goal is NOT in the system prompt. It is the child's first user turn, kept out of the prompt so the task is not sent in both roles.
   - `tools/delegate_tool_progress.py:180-219` - prompt builder; `:187-189` - goal-as-user-turn comment.
   - Marks: code, owner checked; 1 source.

3. **Project context files are re-injected into the child on purpose; the persona file is not** (confidence: high)
   - Children are built with `skip_context_files=True`, which would leave them blind to repo conventions, so the builder loads AGENTS.md / CLAUDE.md / .cursorrules through the same discovery, priority and size-cap logic as the main agent, from the explicit workspace path. SOUL.md is skipped ("identity belongs to the parent"). Loading is best-effort and only runs when a concrete absolute workspace directory is known.
   - `tools/delegate_tool_progress.py:199-210` - injection and comment; `:221-234` - workspace hint candidates, never bare getcwd.
   - Marks: code, owner checked; 1 source.

4. **The child gets the default identity and no memory** (confidence: high)
   - `skip_memory=True` and the `memory` tool is on the blocked list, so no MEMORY.md / USER.md block and no external memory provider. `agent_context` is "subagent", which tells providers to skip writes. With `skip_context_files=True` and no `load_soul_identity`, identity falls to the default identity string.
   - `tools/delegate_tool.py:298` - `skip_context_files=True, skip_memory=True, clarify_callback=None`.
   - `tools/delegate_tool_toolsets.py:13-21` - blocked tools: `delegate_task`, `clarify`, `memory`, `send_message`, `cronjob_manage`.
   - `agent/system_prompt.py:554` - identity chosen by `load_soul_identity or not skip_context_files`; `agent/agent_init.py:1179-1180` - agent_context stamp; `agent/agent_init.py:1234-1262` - memory store only when not skipped.
   - Marks: code, owner checked; 1 source.

5. **Skills: pinned auto-load skills are withheld; the skills index is withheld only if the child lacks the skill tools** (confidence: medium)
   - `_auto_load_parts` returns nothing for agents with `skip_context_files`, documented as covering "delegate children, curator/review forks". `_skills_prompt` is gated only on the presence of `skills_list` / `skill_view` / `skill_manage` among the child's tools, not on `skip_context_files`, so a child that inherits a skills toolset carries the skills index. This is read from the code paths, not run.
   - `agent/system_prompt.py:301-314` - skills index gate; `:317-326` - auto-load gate and docstring.
   - Marks: code, owner checked; 1 source.

6. **History: none. The only channel from parent to child is the `goal` and `context` strings the parent model writes** (confidence: high)
   - Tool description: "Children know nothing of this conversation: pass everything needed via 'context'", including output language and tone. Each child sees only its own context; shared background is repeated per task. `prefill_messages` (few-shot priming) is the one parent field passed through.
   - `tools/delegate_tool.py:719-720` - rule; `:800-809` - goal and context parameter text; `:294` - prefill passthrough.
   - Marks: code, owner checked; 1 source.

7. **Optional brief fields: `output_schema` and `images`** (confidence: high)
   - `output_schema` is a JSON Schema the child is told up front; the parent validates the final answer with one bounded correction retry carrying the errors verbatim; the result gains `schema_valid` (and `schema_errors`), and the child's raw text still returns as the summary. The schema description advises keeping it forgiving and requiring only fields the parent will read. `images` (max 8) go as pixels to vision-capable children, as path hints otherwise; text files belong in `context`.
   - `tools/delegate_tool.py:810-824` - schema text; `tools/delegate_tool_child_run.py:543-583` - validate plus one retry.
   - Marks: code, owner checked; 1 source.

8. **Tools: the parent's toolsets minus a blocked set; a child can never gain a tool the parent lacks** (confidence: high)
   - Explicit `toolsets` are intersected with the parent's expanded set; absent that, the parent's enabled set is inherited. Blocked tools are removed twice (whole blocked toolsets, then exact one-tool deny entries after composite expansion). There is no model-facing toolsets argument for nesting: spawn rights come from depth and role. Default fallback toolsets when the parent is unknown: terminal, file, web. MCP toolsets of the parent are kept when narrowing (`inherit_mcp_toolsets`, default true).
   - `tools/delegate_tool_toolsets.py:22`, `:70-120` - resolution; `tools/delegate_tool.py:241-245` - depth-derived role; `hermes_cli/config_defaults.py:1346`.
   - Marks: code, owner checked; 1 source.

9. **Budgets and limits on a delegation** (confidence: high)
   - Per-child iteration cap 250 (config is authoritative, a caller-supplied value is ignored). Concurrent children 10. Spawn depth 1 (flat) by default. A finite one-shot run may spawn at most 2 children, because "each child re-pays a cold system prompt and re-explores the repo". Child timeout is an inactivity window (0 = none). Child compaction triggers where the parent's do unless `compression_threshold_tokens` is set; the comment cites a 1,393-agent replay finding 200K-400K caps within 5% of each other in cost.
   - `hermes_cli/config_defaults.py:1343`, `:1348`, `:1357`, `:1362`, `:1368`, `:1373`; `tools/delegate_tool.py:594-600`.
   - Marks: code, owner checked; 1 source.

10. **Result size: head plus tail trim to a cap, full text spilled to a file** (confidence: high)
    - Cap per summary = min(static ceiling 24,000 chars, dynamic budget). Dynamic budget = 50% of the parent's remaining context headroom (context length minus last prompt size minus compressor output reserve), split across the batch's summaries, 4 chars per token, floor 2,000 chars. Over-cap summaries keep about 75% head and 25% tail snapped to line boundaries; the full text is written under the delegation cache directory and the footer gives the exact `read_file` offset for the omitted middle. If usage is unknown, only the static ceiling applies.
    - `tools/delegate_tool_results.py:163-171`, `:194-238`, `:254-309`; `hermes_cli/config_defaults.py:1353`.
    - Marks: code, owner checked; 1 source.

11. **The child is told to keep its summary short because the parent's window is the constraint** (confidence: high)
    - Completion instructions ask for what it did, what it found, files created or modified, issues; "lead with outcomes, prefer bullet points over paragraphs, and don't replay your whole process ... overlong summaries crowd out the parent's context window."
    - `tools/delegate_tool_progress.py:148-157`.
    - Marks: code, owner checked; 1 source.

12. **Summaries are self-reports; the tool description tells the parent to verify side effects** (confidence: high)
    - A child claiming "uploaded successfully" may be wrong; the parent should require a verifiable handle (URL, ID, absolute path) and check it before telling the user. Children cannot close tracked work: they return findings and the parent applies the transition. Result entries carry `status`, `exit_reason`, `truncated`.
    - `tools/delegate_tool.py:721-726`, `:369-377`.
    - Marks: code, owner checked; 1 source.

13. **Delegation is steerable and background by default** (confidence: high)
    - Top-level delegations run in the background and re-enter as a new message between turns; the tool description tells the model to end its turn rather than poll. Control actions: list, steer (text appended to the child's next tool result), stop (partial result still returns). One-shot sessions get a variant schema without live control.
    - `tools/delegate_tool.py:696-703`, `:839-873`, `:903-909`.
    - Marks: code, owner checked; 1 source.

## Findings: the background review fork

14. **The fork replays the parent's full conversation with the parent's byte-identical system prompt and tool list** (confidence: high)
    - On the same model, the fork inherits the cached system prompt, session start, tools[] snapshot and reasoning config verbatim so its request hits the parent's prompt cache; the code cites a 26% end-to-end cost reduction measured on one model. It receives the conversation snapshot as history plus a review prompt as the user message. The prompt is the only brief.
    - `agent/background_review.py:1000-1059` - cache-parity fork; `:1214-1221` - run_conversation call; `:1020-1031` - cost comment.
    - Marks: code, owner checked; 1 source.

15. **Tools are advertised in full but dispatch is whitelisted to skill tools, read-only file tools, and optionally memory** (confidence: high)
    - Whitelist = skills toolset, plus memory only when memory is enabled and the trigger was a memory review, plus `read_file` and `search_files`. Write tools stay denied so maintenance goes through `skill_manage` validation. The fork's user message ends with "You can only call ... management tools. Other tools will be denied at runtime". The earlier version without read tools caused a denial storm of about 142 denials over 2 days on one deployment (per the code comment).
    - `agent/background_review.py:1102-1142`, `:1196-1221`.
    - Marks: code, owner checked; 1 source.

16. **Memory handling in the fork: built-in store shared by reference, external provider skipped** (confidence: high)
    - `skip_memory=True` keeps an external memory plugin from receiving the harness prompt in the user's real namespace; the parent's built-in MEMORY.md / USER.md store objects are re-bound onto the fork. Nudge counters are zeroed. Persistence is detached: no session DB, no state writes, the harness turn is not written into the real session.
    - `agent/background_review.py:937-950`, `:1006-1019`.
    - Marks: code, owner checked; 1 source.

17. **Budgets: 16 iterations, and an aggregate input-token cap for the whole review loop** (confidence: high)
    - `_REVIEW_MAX_ITERATIONS = 16`. Input-token budget = 75% of the fork model's context window, capped at 600,000, fallback 120,000 when the window is unknown; configurable (`max_input_tokens`, 0 or less = unlimited). The first request is a warm cache read; compaction then bounds each request but "nothing else caps the SUM across the tool loop", hence the aggregate cap. The default config comment sizes one event at roughly 30K tokens.
    - `agent/background_review.py:173-182`, `:204-225`; `hermes_cli/config_defaults.py:788-798`; `cron/scheduler.py:2511`.
    - Marks: code, owner checked; 1 source.

18. **Routing the review to another model swaps the full replay for a digest** (confidence: high)
    - If `auxiliary.background_review` names a different model, the cache is cold, so history becomes the last 24 messages verbatim plus one synthetic user digest of older turns (user lines cut at 300 chars, assistant at 200, tool calls reduced to names). The comment on config says other models replay "a compact digest (~3-5x cheaper)".
    - `agent/background_review.py:332-362`, `:1220`; `hermes_cli/config_defaults.py:788-790`.
    - Marks: code, owner checked; 1 source.

19. **The review prompts carry the routing and grounding rules, so the fork needs no other instruction** (confidence: high)
    - The memory prompt states the two stores (USER.md for who the user is, MEMORY.md for environment facts), "one fact goes to ONE store", and "save only facts GROUNDED in this conversation ... If unsure, leave it out". Return convention: "Nothing to save." and stop. Prompts are class attributes, so per-agent overrides work; `/refine` appends a user focus to the prompt.
    - `agent/background_review.py:365-399`, `:1332-1360`.
    - Marks: code, owner checked; 1 source.

20. **The fork does not spawn from places where it would be wasted** (confidence: high)
    - Disabled for finite one-shot turns and safe-worker mode, skipped for cron (`skip_background_review=True`), and a delegated child never starts one (`run_agent.py:762-763`). Also prepared compaction at turn end is blocked for cron, subagent and one-shot sessions.
    - `agent/background_review.py:234-238`; `cron/scheduler.py:2511`; `agent/prepared_compaction.py:218-222`; `agent/agent_init.py:2149-2150`.
    - Marks: code, owner checked; 1 source.

## Findings: cron jobs

21. **A cron agent is a fresh session whose first user message is assembled from layers** (confidence: high)
    - Assembly order in `_build_job_prompt`: the job's stored prompt, optional per-run `## Run Context`, pre-run script stdout (fenced block, "collected by a pre-run script"), `context_from` outputs of other jobs or of itself ("self" = previous run), the job's durable notepad, then the cron hint and a `[CURRENT RUN TIME: ...]` line prepended. Named skills load as full skill content ahead of the instruction, with the volatile per-run text after a declared stable prefix for the cache.
    - `cron/scheduler_prompt.py:304-385`, `:203-267`, `:293-301`.
    - Marks: code, owner checked; 1 source.

22. **Context carried between runs is clipped, stored as files, and capped** (confidence: high)
    - `context_from` takes the latest non-silent run document, extracts only the response (length-framed), and clips to 8,000 chars (4,000 head, 4,000 tail). The notepad is a per-job key-value store with 16 KB per value and 64 KB per job; empty renders as nothing so an unused notepad leaves the prompt byte-identical. Job IDs are validated as hex to block path traversal.
    - `cron/scheduler_prompt.py:54`, `:130-136`, `:139-200`; `cron/notepad.py:26-28`, `:149`.
    - Marks: code, owner checked; 1 source.

23. **The cron hint states delivery, silence and no-recursion rules** (confidence: high)
    - The hint says the final response is delivered automatically (do not call send_message), `[SILENT]` suppresses delivery when nothing is new, `[CRON_FAILURE]` on the first line records a failed run, and the run must never create or update a cron job because of schedule words in the task text. The run-time line is kept outside the hint so the hint stays byte-stable.
    - `cron/scheduler_prompt.py:270-301`.
    - Marks: code, owner checked; 1 source.

24. **Cron tools are an allowlist that fails closed** (confidence: high)
    - Per-job `enabled_toolsets` wins (an explicit empty list means zero toolsets, no MCP merge); otherwise the `cron` platform's configured toolsets; a lookup failure raises so the run is refused rather than handed every tool. Project context files load only when a workdir is configured; SOUL.md always loads.
    - `cron/scheduler.py:465-495`, `:2504-2509`.
    - Marks: code, owner checked; 1 source.

25. **Cron limits: idle watchdog, script timeout, nothing for the result beyond delivery** (confidence: medium)
    - Default 600 s of inactivity (not wall clock) hard-interrupts a stalled cron session; attached scripts have a separate 3,600 s timeout; a pre-run script can gate the agent entirely with `{"wakeAgent": false}`, skipping the LLM call. A cron agent's result is delivered to chat targets and archived as a run document, which later runs may read through `context_from`. No token budget for cron agents was found.
    - `cron/AGENTS.md:21-25`; `cron/scheduler_prompt.py:21-35`.
    - Marks: code, owner checked; 1 source.

## Findings: mixture of agents (MoA) presets

26. **MoA runs advisor models that see a text-only view of the conversation and cannot act** (confidence: low; read from one module, not run)
    - Each reference model gets a fixed system prompt ("You are a reference advisor ... NOT the acting agent ... cannot call tools") plus the advisory view: system prompt dropped, user/assistant text turns only, tool calls rendered inline, tool results folded into the preceding assistant turn as previews of 4,000 chars head plus tail. The aggregator keeps the full transcript. The view always ends on a user turn.
    - `agent/moa_loop.py:179-214`, `:703`, `:772-829`.
    - Marks: code, owner checked; 1 source.

27. **Advisors are trimmed to their own window; the aggregator turns advice into private guidance** (confidence: low; read from one module, not run)
    - Oldest frames are dropped to fit each advisor's window minus output reserve (default 8,192) minus a 10% safety margin, keeping the last user turn plus one more. At most 8 advisors run in parallel; a failed advisor becomes a labelled `[failed: ...]` note and all-failed skips the aggregator. The aggregator prompt holds the original user prompt plus the joined advisor outputs and asks for concise, actionable guidance; the result is injected for the main model as "private guidance for the normal Hermes agent loop", with a stale-guidance note when tools have run since.
    - `agent/moa_loop.py:153`, `:468-571`, `:914-990`, `:744-749`.
    - Marks: code, owner checked; 1 source.

28. **MoA output size is capped on the advisor side only; privacy filtering is opt-in** (confidence: low; read from one module, not run)
    - `reference_max_tokens` caps the advisor fan-out; the aggregator is deliberately not capped because a cap truncated long syntheses (issue cited in the code). `moa.privacy_filter` (default off) can redact PII from displayed advisor blocks, traces, or the aggregator prompt. The default preset names a two-model reference list plus an aggregator, with `moa_reference` and `moa_aggregator` auxiliary tasks configured at `_aux(900)`.
    - `agent/moa_loop.py:937-946` (docstring); `hermes_cli/config_defaults.py:801-802`, `:1403-1431`.
    - Marks: code, owner checked; 1 source.

## Findings: batch runs

29. **A batch worker agent is the leanest launch: no context files, no memory, a sampled toolset, one agent per prompt** (confidence: low; only the worker construction was read, not the pool, checkpoint or distribution code)
    - `skip_context_files=True` ("don't pollute trajectories with SOUL.md/AGENTS.md"), `skip_memory=True`, `save_trajectories=False`, toolsets drawn per prompt from a named distribution, an optional shared `ephemeral_system_prompt`, and `platform="batch"`. The agent is closed after each prompt to release terminals and clients; each task id gets its own isolated VM. The prompt from the JSONL dataset is the whole brief; output is a per-batch JSONL trajectory plus tool-usage statistics and a resume checkpoint.
    - `batch_runner.py:1-8`, `:248-281`; `batch_runner.py:55-60` - passthrough fields.
    - Marks: code, owner checked; 1 source.

## Findings: patterns shared across the five paths

30. **Every non-primary launch sets the same four switches, and each path chooses its own values** (confidence: high)
    - Context files, memory, background review, and toolset are separately settable at construction. Delegate: files off (then re-injected), memory off, review off, toolset inherited minus blocked. Review fork: tools advertised in full, dispatch whitelisted. Cron: memory on, files only with workdir, SOUL always, review off, toolset allowlist. Batch: files off, memory off, sampled toolset. MoA: no tools at all.
    - `tools/delegate_tool.py:298`; `agent/background_review.py:937-950`; `cron/scheduler.py:2504-2511`; `batch_runner.py:259-260`.
    - Marks: code, owner checked; 1 source.

31. **Fixed text that never changes per launch is kept byte-stable so the provider cache holds it** (confidence: high)
    - Examples: the review fork copies the parent's cached prompt and tool list; the cron hint is separate from the changing run-time line; skill blocks come before volatile per-run text under a registered stable prefix; the delegate tool schema is rebuilt only from config, not per turn. The system prompt is built as stable, context and volatile tiers and "never re-rendered mid-session".
    - `agent/background_review.py:1030-1031`; `cron/scheduler_prompt.py:293-296`, `:366-384`; `agent/system_prompt.py:738-747` (tier docstring of `build_system_prompt_parts`); `tools/delegate_tool.py:745-773`.
    - Marks: code, owner checked; 1 source.

## Findings: how Compass launches agents

32. **A Compass agent's context comes from its definition file, not from a built prompt** (confidence: high)
    - Frontmatter fields set the launched agent's tools, preloaded skills (`skills:`), model, effort, turn cap (`maxTurns`), permission mode, per-agent memory (`memory: project`), and a first-turn read list (`initialPrompt`). The builder, planner, reviewer, researcher, tester, validator and debug agents all use the same `initialPrompt` that reads `.compass/index.md`, `.compass/active.md`, `.compass/lessons/index.md` (debug omits active.md). Builder: tools Read, Grep, Glob, Write, Edit, Bash, Agent; skills obsidian, methodology, lessons; sonnet, high effort, 50 turns, `memory: project`. Researcher: adds WebSearch, WebFetch, skill research-methods, no `memory:` field, 30 turns.
    - `plugin/templates/agents/builder.md:1-12`; `plugin/templates/agents/researcher.md:1-12`; `plugin/templates/agents/debug.md:12`.
    - Marks: code, owner checked; 1 source.

33. **The read-only locator and analyzer agents carry no skills, no memory and no initial read** (confidence: high)
    - `codebase-locator` (Grep, Glob, LS; haiku, low effort, 15 turns), `vault-locator`, `codebase-analyzer`, `vault-analyzer`, `pattern-finder` declare only tools, model, effort and maxTurns. `pr-describe` runs haiku with the full skill and initial-read set.
    - `plugin/templates/agents/codebase-locator.md:4-8`; `plugin/templates/agents/pr-describe.md:1-12`.
    - Marks: code, owner checked; 1 source.

34. **The brief is written by the orchestrating skill per spawn, and its content is named, not templated** (confidence: high)
    - Test-first station: the tester gets "exactly the task body, the plan's acceptance criteria, and the task's automated-verification bullets", and no diff because none exists. Post-build tester: the builder's diff and the worktree path. Research: each brief carries the axis, the sources to check first, the `research-methods` skill, and the `grading:` state. A builder is pointed at its task in `active.md` and told to read the parent plan and spec itself.
    - `plugin/skills/build/SKILL.md:29`, `:39`; `plugin/skills/research/SKILL.md:67`; `plugin/templates/agents/builder.md:25`.
    - Marks: code, owner checked; 1 source.

35. **Compass isolates builders by worktree and returns follow-up fixes to the same builder** (confidence: high)
    - The Agent tool's `isolation: "worktree"` creates the worktree; a frontmatter `isolation:` key does nothing. The builder's first action is to fast-forward its branch to the working branch and confirm checkpointed test files exist. Fix cycles go to the same builder through SendMessage with the bug diagnosis, not the full task.
    - `plugin/skills/build/SKILL.md:39`, `:42`.
    - Marks: code, owner checked; 1 source.

36. **Result size in Compass is set by the agent's own report format, not a harness cap** (confidence: medium)
    - Builder report field lengths: one line per changed file, one line per code-review finding, no restating the task body, no test results. A `SubagentStop` hook writes each finishing subagent's final report to a capture file under `.compass/tmp/subagent-captures/` and records a typed signal. No Compass code that truncates or spills an oversized subagent report was found; whether Claude Code itself bounds a subagent result was not checked here.
    - `plugin/templates/agents/builder.md:92`; `plugin/hooks/hooks.json:2` (description of SubagentStop), `:112`.
    - Marks: code, owner checked; 1 source.

37. **Compass bounds a launched agent by turns (`maxTurns`) and by the 5,000-token start-here files; no per-launch token budget exists** (confidence: medium)
    - `maxTurns` ranges 15 (locators, reviewer) to 50 (builder). The start-here files are capped at 5,000 tokens combined by the rule in the repo's CLAUDE.md. No input-token budget, summary char cap, or spill file for a launched agent was found in `plugin/`.
    - `plugin/templates/agents/*.md` frontmatter (`maxTurns` lines); `CLAUDE.md` "Session start protocol".
    - Marks: code, owner checked; 1 source.

## Comparison table

| Dimension | Hermes delegate | Hermes review fork | Hermes cron | Compass agent |
|---|---|---|---|---|
| System prompt | one sentence + context + workspace files + completion text | parent's cached prompt, verbatim | default or SOUL + hint in user turn | agent file body |
| Tools | parent's minus 5 blocked | parent's advertised, dispatch whitelisted | allowlist, fails closed | `tools:` frontmatter |
| Memory | none (tool blocked) | parent's built-in store, no external | on, built-in | `memory: project` on 7 agents |
| Skills | index if skill tools inherited; no pinned | none pinned | named skills loaded in full | `skills:` frontmatter |
| History | none; `goal` + `context` strings | full snapshot (or 24-message digest) | previous run output, 8,000 chars | none; brief + initial read |
| Brief | model-written goal/context, optional schema | fixed review prompt | stored job prompt + layers | skill-written per spawn |
| Result | summary, cap 24,000 chars or headroom, spill file | actions summary line | delivery + run document | agent's report format |
| Budget | 250 iterations, depth 1, 10 children | 16 iterations, input tokens 75% of window | 600 s idle, script 3,600 s | `maxTurns` |

## Contradictions

- `cron/AGENTS.md:107` says cron sessions pass `skip_memory=True`; `cron/scheduler.py:2510` passes `skip_memory=False`, and a comment at `agent/agent_init.py:1228-1229` says cron agents "now run with skip_memory=False". The code is current; the guide is stale.
- The module header of `tools/delegate_tool.py` says children get "a focused system prompt built from goal + context", but `delegate_tool_progress.py:187-189` keeps the goal out of the system prompt and sends it as the first user turn.
- The July study recorded a prune and curator keep count of 5; `changes-since-july` records 2. Not part of this axis; noted only because the same snapshot differs.

## Gaps

- MoA (findings 26-28) and the batch runner (finding 29) are low confidence: only parts of `agent/moa_loop.py` and `batch_runner.py:248-281` were read; the MoA turn loop, `/moa` slash handling and `toolset_distributions.py` were not.
- Whether a delegate child that inherits skill tools actually shows the skills index was read from code, not run (finding 5). A one-prompt trace of a child's first request would close it.
- No cron token budget or cron result-size cap was found; cron paths in `scheduler_script.py`, `scheduler_delivery*.py` and `executions.py` were not read in full.
- The kanban dispatcher spawns whole profiles as workers; it is a sixth launch path (`cron/AGENTS.md:117-169`) and was not traced.
- `tools/delegation_output_schema.py` (how the schema is told to the child) and `agent/managed_worker.py` (a worker with `skills_prompt` as ephemeral prompt and `ignore_rules` mapped to skip flags, `:358-374`) were not read.
- Claude Code's own limits on subagent result size, and whether `memory: project` content is loaded into a launched Compass agent's prompt at spawn, were not checked here; the Claude Code documentation or a spawn trace would settle both (finding 36).
- No Hermes measurement of what these exclusions save in tokens was found beyond code comments (26% cache saving, 30K tokens per review event, 3-5x digest saving); those are the authors' figures, not independently verified.
