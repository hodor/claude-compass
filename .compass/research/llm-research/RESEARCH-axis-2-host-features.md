---
title: "Axis 2: Claude Code host features that replace or reshape Compass machinery"
type: research
status: complete
confidence: medium
area: architecture
tags: [research, claude-code, hooks, skills, subagents, plugins, memory, compaction, worktrees]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "bf8c771"
author: researcher
summary: "Claude Code 2.1.330 and Claude API features mapped against Compass hooks, CLI and skills: 35 findings, 9 ranked candidate changes, 3 stale-limitation rechecks"
---

# Axis 2: host features that replace or reshape Compass machinery

From [[RESEARCH-llm-research-for-compass]] (axis 2 of 7), under [[SPEC-001-compass-vision-and-architecture]].

## Question
Which Claude Code and Agent SDK features now do, or could cheapen, what Compass scripts, hooks, skills and prompts do, and which host limitations Compass works around are fixed?

## Methodology
Technology landscape / comparative evaluation (DESMET feature analysis in documentation-review plus tool-trial mode): each host feature is a candidate, each Compass hook, CLI command or skill is the incumbent, and the criteria are the four north stars. It fits because the question is "which concrete host options overlap which Compass parts". The host is closed source, so the vendor docs are the primary source; they were cross-checked against the installed host (`claude --version` reports 2.1.330, `claude --help`, `claude plugin --help`) and against the Compass code read in `plugin/`. Grading was allowed by the brief.

## Findings

Grade key: vendor-doc = Anthropic documentation (asserted behavior, not measured by the vendor in the page); local-code = read in this repo; local-trial = run on the installed host. All carry marks: not retracted, not a preprint, citation count n/a (vendor docs), convergence stated per finding.

### A. Hooks

1. **The host has about 30 hook events; Compass registers 6.** (confidence: high)
   Events: SessionStart, Setup, UserPromptSubmit, UserPromptExpansion, PreToolUse, PermissionRequest, PermissionDenied, PostToolUse, PostToolUseFailure, PostToolBatch, MessageDisplay, SubagentStart, SubagentStop, Stop, StopFailure, TaskCreated, TaskCompleted, TeammateIdle, InstructionsLoaded, ConfigChange, CwdChanged, DirectoryAdded, FileChanged, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, PreModelSwitch, PostModelSwitch, Elicitation, ElicitationResult, Notification, SessionEnd. Compass registers PreToolUse, PostToolUse, SessionStart, Stop, TeammateIdle, SubagentStop (`plugin/hooks/hooks.json`). Unused and relevant: PreCompact, PostCompact, SubagentStart, UserPromptSubmit, InstructionsLoaded, FileChanged, SessionEnd, TaskCompleted, WorktreeCreate.
   - https://code.claude.com/docs/en/hooks - event table
   - `plugin/hooks/hooks.json` - registered set
   - Marks: vendor-doc + local-code; not retracted; not preprint; n/a; converges (doc and code agree on what is registered)
   - Grade: high for the inventory (primary source, directly read)

2. **Five hook handler types exist; Compass uses only `command`.** (confidence: high)
   `command` (shell or exec-form `args`, `async`, `asyncRewake`, `shell`), `http`, `mcp_tool`, `prompt` (single-turn LLM returns a JSON decision, accepts model aliases like `haiku` since 2.1.330), `agent` (experimental, Read/Grep/Glob subagent). All take `if`, `timeout`, `statusMessage`; `once` is honored only in skill frontmatter. `onFailure: "block"` (2.1.295+) turns hook failures into exit-2. Compass's hooks.json description states "Every entry runs a command, never an agent" as a token-cost choice.
   - https://code.claude.com/docs/en/hooks - "Hook types"
   - `plugin/hooks/hooks.json:2` - command-only rationale
   - Marks: vendor-doc; not retracted; not preprint; n/a; converges with changelog 2.1.328-2.1.330
   - Grade: high

3. **Hook `if` still takes exactly one permission rule; no `||`.** (confidence: high)
   Compass's three-way Write/Edit/MultiEdit split exists because of this and the doc still states it. Not a fixed limitation.
   - https://code.claude.com/docs/en/hooks - "The `if` field"
   - `plugin/hooks/hooks.json:2` - split rationale
   - Marks: vendor-doc; converges
   - Grade: high

4. **No hook payload carries context-window usage during a session; only the statusline does.** (confidence: high)
   `context_window.used_percentage`, `remaining_percentage`, `context_window_size`, `current_usage` are in the statusline stdin JSON. Hook payloads carry `transcript_path` and, on SessionStart with `source` of `resume` or `fork`, `context_tokens`, `prompt_cache_likely_expired`, `seconds_since_last_response`, `estimated_cache_write_usd`. PostToolUse on the Agent tool carries `totalTokens` and `usage` of the subagent's final request only. `compass context-check` therefore still derives usage from the transcript tail on every PostToolUse; the host's formula (input + cache creation + cache read, no output) matches what the Compass docstring says it copies.
   - https://code.claude.com/docs/en/statusline - context window fields
   - https://code.claude.com/docs/en/hooks - SessionStart, PostToolUse fields
   - `plugin/cli/commands/context_check.py:1-30` - transcript-tail measurement
   - Marks: vendor-doc + local-code; converges
   - Grade: high. Option for the planner: a statusline command can write `used_percentage` to a file, which would replace the transcript read; whether the statusline is available in every Compass-hosted setting is not established (gap).

5. **Compaction has two hook events with payloads Compass does not use.** (confidence: high)
   PreCompact: matcher `manual|auto`, input `trigger`, `custom_instructions`; stdout (cap 10,000 chars) becomes instructions for the compaction summary; exit 2 or `decision: block` blocks compaction. PostCompact: input `trigger`, `compact_summary`; no decision control. SessionStart also fires after compaction with `source: "compact"` and accepts `additionalContext`. Compass has no PreCompact, PostCompact or compact-source handler; its only context policy is the 80%/95% handoff suggestion.
   - https://code.claude.com/docs/en/hooks - PreCompact, PostCompact, SessionStart
   - `plugin/hooks/hooks.json` - absence
   - Marks: vendor-doc + local-code; converges
   - Grade: high

6. **SubagentStart can inject `additionalContext` into every subagent before its first prompt.** (confidence: high)
   Cap 10,000 chars; matcher is the agent type; fires on spawn, resume and each in-process teammate message. Compass agents rely on a frontmatter `initialPrompt` for the hot-path load (see finding 21), which the host applies only to a main-session agent.
   - https://code.claude.com/docs/en/hooks - SubagentStart
   - https://code.claude.com/docs/en/sub-agents - frontmatter table, `initialPrompt`
   - Marks: vendor-doc; converges across two doc pages
   - Grade: high for the mechanism; medium for the Compass impact (finding 21)

7. **SubagentStop carries `last_assistant_message`, `agent_transcript_path` and `agent_id`; since 2.1.271 a subagent can deliver its report through a `SubagentHandback` tool, leaving `last_assistant_message` as only its closing text.** (confidence: medium)
   Compass `capture-signal` reads `last_assistant_message` into a capture file (`capture_signal.py:153`). A subagent that reports through SubagentHandback would put the report in `tool_input.message` of a PreToolUse/PostToolUse hook on `SubagentHandback`, not in that field. Whether Compass's agents use the tool is not established.
   - https://code.claude.com/docs/en/hooks - SubagentStop input
   - `plugin/cli/commands/capture_signal.py:201`
   - Marks: vendor-doc + local-code; single source for the handback semantics
   - Grade: medium

8. **Plugin-shipped subagents have a plugin-scoped `agent_type` (`plugin:agent`) and a colon routes the matcher to regex.** (confidence: medium)
   Compass's SubagentStop matcher is a bare-name list (`builder|tester|...`), which is an exact-match list. It matches only when agents load from `.claude/agents` (the local install); under `--plugin-dir` the type would be `compass:builder` and the matcher would not match. Not tested.
   - https://code.claude.com/docs/en/hooks - SubagentStart matcher paragraph
   - `plugin/hooks/hooks.json` - SubagentStop matcher
   - Marks: vendor-doc + local-code; single source
   - Grade: medium

9. **Stop hooks are capped at 8 consecutive continuations and receive `background_tasks` and `session_crons`.** (confidence: high)
   `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it; the counter resets on each tool call. `stop_hook_active` signals a continuation. Compass `capture-check` emits the Stop block contract to force a capture turn. The `background_tasks` array lets a hook tell "done" from "waiting on background work", which Compass's turn counter does not use.
   - https://code.claude.com/docs/en/hooks - Stop
   - `plugin/hooks/hooks.json` - Stop entry
   - Marks: vendor-doc; converges
   - Grade: high

10. **Hook-related host bugs fixed in the last five releases touch Compass directly.** (confidence: medium)
    2.1.330: SessionStart env vars persist across `claude -p --continue`; stopped background subagents stay stopped. 2.1.329: a PreToolUse hook that errors no longer blocks the tool call unless `onFailure: "block"` (in Code Mode). 2.1.328: managed PostToolUse hooks no longer fire for refused calls. 2.1.327: failing SubagentStop, SessionEnd, CwdChanged, FileChanged hooks now show. 2.1.326: crashed Node/Python hooks show their error. Compass's guard is a PreToolUse that must deny; its failure mode on a hook crash depends on `onFailure` and was not tested.
    - https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md - 2.1.326 to 2.1.330
    - Marks: vendor changelog; converges with hooks doc `onFailure` text
    - Grade: medium

### B. Skills

11. **Skill frontmatter has fields Compass's 30 skills may not use: `paths`, `context: fork`, `agent`, `hooks`, `disable-model-invocation`, `when_to_use`, `model`, `effort`, `allowed-tools`.** (confidence: high)
    Description plus `when_to_use` is truncated at 1,536 characters in the listing. `disable-model-invocation: true` removes the description from context entirely. `skillOverrides` can set a skill to `name-only`, `user-invocable-only` or `off` (not for plugin skills). Uploads to the API accept only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.
    - https://code.claude.com/docs/en/skills - frontmatter table
    - Marks: vendor-doc; converges
    - Grade: high

12. **Dynamic context injection runs a shell command before the model sees the skill body.** (confidence: high)
    `` !`cmd` `` and fenced `!` blocks are replaced by the command's output; 2-minute timeout; any non-zero exit aborts the invocation (exit 1 from search/compare commands is treated as a result); commands never prompt, so `allowed-tools` must pre-approve them. A skill can therefore embed `compass hot-path` or `compass lessons --for <doc>` output with no model turn spent calling the CLI. Compass has `plugin/cli/commands/hot_path.py` and skills that instruct agents to run `compass` commands as steps.
    - https://code.claude.com/docs/en/skills - "Dynamic context injection"
    - `plugin/cli/commands/hot_path.py` - exists
    - Marks: vendor-doc + local-code; converges
    - Grade: high for the mechanism

13. **After auto-compaction the host re-attaches the most recent invocation of each skill: first 5,000 tokens per skill, 25,000 combined, newest first.** (confidence: high)
    Older skills can drop entirely. An invoked skill body stays in context for the session and is not re-read. Large Compass skill bodies lose their tail after compaction.
    - https://code.claude.com/docs/en/skills - "Post-compaction retention"
    - Marks: vendor-doc; single source
    - Grade: high (stated limits)

14. **Skills have a cost report: `/skill-doctor` (2.1.252+) and `claude plugin details <name>` (projected component token cost).** (confidence: medium)
    Compass measures its own overhead through `compass usage` and the whole-overhead research; neither host report was run against the Compass plugin in this pass.
    - https://code.claude.com/docs/en/skills ; `claude plugin --help` (local-trial: `details` listed)
    - Marks: vendor-doc + local-trial
    - Grade: medium

### C. Subagents, agent teams, worktrees, background

15. **Subagent frontmatter: `memory`, `isolation: worktree`, `background`, `skills` (preloads up to 32), `maxTurns`, `autoCompactWindow` (min 100k), `omitClaudeMd`, `effort`, `model`, `hooks`, `experimental.cacheTtl`.** (confidence: high)
    `memory` scopes `user|project|local` give each agent its own `MEMORY.md` (first 200 lines or 25KB loaded) outside the vault. `isolation: worktree` branches from the default branch, not the parent's HEAD, unless `worktree.baseRef` is `"head"`. A subagent's own tool results never reach the parent except through its final message. Compass builders run in worktrees and the build skill merges them back; the native flag does the creation and cleanup but not the merge.
    - https://code.claude.com/docs/en/sub-agents ; https://code.claude.com/docs/en/worktrees
    - Marks: vendor-doc; converges across two pages
    - Grade: high

16. **Plugin-shipped agents ignore `hooks`, `mcpServers`, `permissionMode` and `initialPrompt` frontmatter.** (confidence: high)
    Documented workaround: copy the agent into `.claude/agents/`, or ship `hooks/hooks.json`. Compass already copies agents into `.claude/agents/` via setup, which is the documented workaround.
    - https://code.claude.com/docs/en/sub-agents - "Plugin subagent restrictions"
    - Marks: vendor-doc; converges with the repo layout in `CLAUDE.md`
    - Grade: high

17. **Subagents never inherit conversation history, output style or auto memory; they do load the full CLAUDE.md hierarchy (including `.claude/rules`) and a git status snapshot unless `omitClaudeMd`.** (confidence: high)
    Compass's always-loaded rules in `.claude/rules/` therefore cost tokens in every subagent. Path-scoped rules (`paths:` frontmatter) load only when matching files are touched.
    - https://code.claude.com/docs/en/sub-agents - "What loads at startup"
    - https://code.claude.com/docs/en/memory - rules and `paths`
    - Marks: vendor-doc; converges
    - Grade: high

18. **Agent teams are experimental, off by default, with a shared file-locked task list, mailboxes, and three quality-gate hooks.** (confidence: high)
    Limits: no session resumption for in-process teammates, one team per session, no nested teams, teammate `skills` frontmatter not applied, split panes need tmux or iTerm2, no per-teammate permission mode, higher token cost. While enabled, a subagent Claude names launches as a teammate. Compass registers TeammateIdle only to record a weak signal.
    - https://code.claude.com/docs/en/agent-teams
    - Marks: vendor-doc; converges with hooks doc
    - Grade: high

19. **Background work is native: `claude --bg`, `claude agents`, `attach|logs|stop|rm|respawn`, a supervisor daemon, `claude agents --json` state (`working|blocked|done|failed|stopped`), worktree isolation for background sessions, `/loop` up to 30 days, `/goal`.** (confidence: medium)
    `/goal` is a session-scoped prompt-based Stop hook run by a small fast model that judges the condition from the transcript only; it clears on met, impossible, or unrecoverable error; one goal per session. Compass has `looprunner.py`, `looplib.py`, `proctree.py`, `sessions.py`; their exact overlap was not read in this pass (see Gaps).
    - https://code.claude.com/docs/en/agent-view ; https://code.claude.com/docs/en/goal
    - Marks: vendor-doc; converges
    - Grade: medium (overlap with Compass files not read)

### D. Plugins, evals

20. **`claude plugin eval` (2.1.269+) runs case directories against a plugin and a no-plugin baseline; graders are `regex`, `tool_used`, `tool_order`, `file_exists`, `llm`, `baseline`; there are no custom-code graders.** (confidence: high)
    Each case runs 3 times per arm; score is the mean fraction of graders passed; `--threshold` defaults to 1.0 and a miss exits 1; `--ablation none` halves cost; `scaffold_script` builds fixtures only with `--scaffold`; Bash grants need an OS sandbox, which native Windows lacks (WSL2 required). `tool_used: Skill` graders are excluded from the score so the baseline stays comparable. The docs name "Claude isn't choosing your skill on natural phrasing" as the common first finding.
    - https://code.claude.com/docs/en/plugin-evals ; `claude plugin eval` listed in local `claude plugin --help` (local-trial)
    - Marks: vendor-doc + local-trial; third-party posts agree on grader names (converges)
    - Grade: high for mechanics; Compass `bench/` and `compass test-smells` overlap not mapped

21. **The hot-path load by frontmatter `initialPrompt` is not applied to subagents; this run's own context shows it did not run.** (confidence: medium)
    The doc says `initialPrompt` is "the first user turn, only when run as the main session agent". This research run was a subagent whose system text claims `initialPrompt` loaded the index, active and lessons files; its context held none of them until read explicitly. One observation, not a controlled test.
    - https://code.claude.com/docs/en/sub-agents - frontmatter table
    - this run's context (observation)
    - Marks: vendor-doc + single observation
    - Grade: medium

22. **Plugin manifest has fields Compass's `plugin.json` omits: `engines`, `dependencies`, `userConfig`, `network`, `outputStyles`, `experimental.monitors`, `experimental.evals`, `bin/`.** (confidence: high)
    Compass's manifest has name, description, version, author, repository, license, keywords. `bin/` puts executables on the Bash tool's PATH while the plugin is enabled; `${CLAUDE_PLUGIN_DATA}` persists across updates; `claude plugin validate [--strict]` checks the manifest. `monitors` run a persistent background command per session (not with `-p`). Compass instead copies `cli/` into each project's `.claude/cli/` and runs `self-update`.
    - https://code.claude.com/docs/en/plugins-reference ; `plugin/.claude-plugin/plugin.json`
    - Marks: vendor-doc + local-code
    - Grade: high for the field list. Whether native distribution replaces the copy-install is a design fork already researched in [[research/distribution/index]] (not reread here).

### E. Memory

23. **Host memory: CLAUDE.md (target under 200 lines), `.claude/rules/*.md` with `paths:`, `@import` (4 hops), block HTML comments stripped, AGENTS.md read when no CLAUDE.md, auto memory per repo shared across worktrees (first 200 lines or 25KB of `MEMORY.md`), `autoMemoryDirectory` relocatable from any settings scope.** (confidence: high)
    Auto memory writes outside the repo by default (`~/.claude/projects/<project>/memory/`). `autoMemoryDirectory` can point it elsewhere, which is the only native hook between host memory and a vault directory. Compass has a `consolidate-memory` skill and a vault-as-single-source principle.
    - https://code.claude.com/docs/en/memory
    - Marks: vendor-doc; converges with sub-agents page on the 200 line/25KB cap
    - Grade: high

### F. Host limitations Compass works around (status today)

24. **Subagent worktrees forking from a stale base: the host now exposes `worktree.baseRef`.** (confidence: medium)
    The vault lesson [[LESSON-subagent-worktrees-fork-stale]] and the build skill's step 3 (checkpoint commit before the builder's worktree forks, builder fast-forwards first) work around worktrees branching from the default branch. The docs now give `worktree.baseRef: "head"`, which branches from the current local HEAD including unpushed commits. Uncommitted files remain invisible to any worktree, so the commit-between-waves rule still holds. Not tested on 2.1.330.
    - https://code.claude.com/docs/en/worktrees - "Choose the base branch"
    - `plugin/skills/build/SKILL.md:32,39` ; `.compass/lessons/subagents/LESSON-subagent-worktrees-fork-stale.md`
    - Marks: vendor-doc + local-code; single source for the setting
    - Grade: medium

25. **Frontmatter `isolation: worktree` on a subagent is documented as supported; the build skill says it "does nothing".** (confidence: medium)
    `plugin/skills/build/SKILL.md:39` instructs passing `isolation: "worktree"` on the Agent call because a frontmatter key "does nothing". Docs 2.1.330 state frontmatter `isolation: worktree` makes the subagent always run in its own worktree (except when launched as an agent-teams teammate). Either the build skill's statement predates a host fix or it was observed under a case the docs exclude; not tested here.
    - https://code.claude.com/docs/en/sub-agents - `isolation` ; https://code.claude.com/docs/en/worktrees - "Isolate subagents with worktrees"
    - `plugin/skills/build/SKILL.md:39`
    - Marks: vendor-doc vs local-code; conflicting
    - Grade: medium (conflict unresolved)

26. **Hook `if` is documented for tool events on every handler; a vault lesson says settings-file hooks have none.** (confidence: medium)
    [[LESSON-hook-if-clause-no-or]] (updated 2026-08-06) records that settings-file hook entries have no `if`. The 2.1.330 hooks doc lists `if` among fields common to all handler types, tool events only. Compass's own `hooks.json` already uses `if`, and `compass self-update` merges those entries into `.claude/settings.json`. The lesson may be stale or may describe a pre-fix host; not tested.
    - https://code.claude.com/docs/en/hooks - "The `if` field"
    - `.compass/lessons/hooks/LESSON-hook-if-clause-no-or.md` ; `plugin/hooks/hooks.json`
    - Marks: vendor-doc vs vault lesson; conflicting
    - Grade: medium

27. **Hook payload gaps noted in `hooks.json` prose are partly closed.** (confidence: medium)
    The hooks.json description says TeammateIdle "carries only a teammate name". The 2.1.330 doc lists `teammate_name`, deprecated `team_name`, and `agent_id` (2.1.290+). SubagentStop now has `last_assistant_message` and `agent_transcript_path`, which the capture-signal path uses. Stop gained `background_tasks` and `session_crons`.
    - https://code.claude.com/docs/en/hooks - TeammateIdle, SubagentStop, Stop
    - `plugin/hooks/hooks.json:2`
    - Marks: vendor-doc + local-code; converges
    - Grade: medium

28. **Transcript-based measurement of subagent and session cost has a native source: OpenTelemetry counters and `claude agents --json`.** (confidence: low)
    The docs point to OpenTelemetry counters filtered by `query_source: "subagent"` for totals across subagents (PostToolUse carries only the final request). Compass `sessions`, `clone` and `retention` read transcripts directly (`sessionslib.py`). Only documentation was read; no OTel run.
    - https://code.claude.com/docs/en/hooks - PostToolUse Agent `tool_response` note
    - `plugin/cli/sessionslib.py:1-14`
    - Marks: vendor-doc; single source
    - Grade: low

### G. Claude API features (relevant to the SDK path and to Compass's own memory design)

29. **The API memory tool is a client-side file protocol, which is the shape of the vault.** (confidence: high)
    Tool `memory_20250818`, six commands (`view`, `create`, `str_replace`, `insert`, `delete`, `rename`), all under `/memories`; the application implements storage; SDK helpers include a local-filesystem implementation (Python, TypeScript). The API adds a system instruction to view memory first and assume interruption. The documented multisession pattern is an initializer session that writes a progress log and a feature checklist, later sessions read them first, and a feature is marked complete only after end-to-end verification. It is a model-side tool for API/SDK apps, not a Claude Code setting.
    - https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool
    - Marks: vendor-doc (stable, supported on Opus/Sonnet/Haiku 4.5 and later); converges with Anthropic's "effective harnesses" post cited on the page
    - Grade: high for mechanics

30. **Context editing (beta `context-management-2025-06-27`) clears old tool results server-side by rule.** (confidence: high)
    Strategy `clear_tool_uses_20250919`: `trigger` default 100,000 input tokens, `keep` default 3 tool uses, `clear_at_least`, `exclude_tools`, `clear_tool_inputs`. `clear_thinking_20251015` has a `keep` rule and must come first. Each tool-result clear invalidates the cached prefix, so `clear_at_least` is the guard. With the memory tool enabled, Claude is warned before clearing so it can save to memory. `count_tokens` previews the effect.
    - https://platform.claude.com/docs/en/build-with-claude/context-editing
    - Marks: vendor-doc (beta); converges with the memory-tool page
    - Grade: high for mechanics; measured benefit not on the page

31. **Server-side compaction has three forms; client-side SDK compaction is deprecated.** (confidence: medium)
    On demand (beta `compact-2026-09-04`, top-level `compaction` parameter; the application decides when, can keep recent turns word for word, can run in the background, accepts its own summarization prompt) and at a token threshold (the API decides; runs inside the request). The context-editing page says the earlier `compact_20260112` edit is the main recommended approach and `compaction_control` is deprecated (removed in Python SDK v1.0). Claude Code's own `/compact` and auto-compaction are separate from these and are tuned through `autoCompactWindow`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `--autocompact` (min 100k) and PreCompact stdout.
    - https://platform.claude.com/docs/en/build-with-claude/compaction ; https://platform.claude.com/docs/en/build-with-claude/context-editing ; `claude --help` (`--autocompact <auto|tokens>`, local-trial)
    - Marks: vendor-doc (beta); the two API pages name different beta identifiers, which this pass did not reconcile
    - Grade: medium

32. **Agent SDK: hook callbacks exist in both SDKs, with narrower event sets in Python; `PreCompact` is in both, `SessionStart`/`SessionEnd`/`PostCompact`/`TeammateIdle`/`TaskCompleted` are TypeScript-only.** (confidence: high)
    `onFailure: "block"` needs TypeScript SDK 0.3.317 or Python 0.2.177. A `PreToolUse` callback that crashes lets the call reach the normal permission flow unless `onFailure: "block"` is set. `settingSources` decides whether shell hooks from settings load. Compass hooks are shell commands installed in settings, so an SDK app that sets `settingSources` without `project` would run without Compass's guard and sync hooks.
    - https://code.claude.com/docs/en/agent-sdk/hooks
    - Marks: vendor-doc; converges with the main hooks doc
    - Grade: high

### H. Output styles and MCP

33. **Output styles apply to the main conversation and forks, never to ordinary subagents; plugins can ship them and force one with `force-for-plugin: true`.** (confidence: high)
    A style's instructions are sent with every request (cached after the first). A custom style drops the built-in software-engineering instruction section unless `keep-coding-instructions: true`. The built-in Concise style (2.1.237+) leads with the result and omits preamble, narration and recaps. The docs state a style is an instruction Claude follows, with no enforcement. Compass carries its "no verbiage, plain words" rules in `.claude/rules/compass-pipeline.md` (about 10.5 KB, always loaded, also loaded into every subagent).
    - https://code.claude.com/docs/en/output-styles ; `.claude/rules/compass-pipeline.md`
    - Marks: vendor-doc + local-code; converges with sub-agents page ("never inherited: output style")
    - Grade: high

34. **MCP: a hook can call an MCP tool (`mcp_tool` handler), plugins can bundle MCP servers, and several 2.1.326-2.1.330 fixes concern parallel MCP calls and plugin servers.** (confidence: medium)
    Compass has no MCP server of its own in `plugin/`; its CLI is reached through Bash. `.mcp.json` project scope and `claude mcp add-json <name> -` exist. No finding here changes an existing Compass part; listed because the brief names MCP.
    - https://code.claude.com/docs/en/hooks - hook types ; changelog 2.1.326-2.1.330
    - Marks: vendor-doc; single source
    - Grade: medium

35. **`claude plugin validate plugin` passes on the installed host (2.1.330) with the current manifest.** (confidence: high)
    Result "Validation passed"; the output enumerates all registered hooks and the 30-plus skills; its notes concern the repository-root README. This is a trial, not a vendor claim.
    - `claude plugin validate plugin` (local-trial)
    - Marks: local-trial; converges with `plugin/.claude-plugin/plugin.json` content
    - Grade: high

## Contradictions
- Findings 6, 16 and 21: the repo's agents (for example the researcher) declare `initialPrompt` to load the hot path; the host limits that field to main-session agents and ignores it for plugin agents. This run's context agrees with the doc.
- Finding 25: `plugin/skills/build/SKILL.md:39` says frontmatter `isolation` does nothing; the 2.1.330 docs say it works.
- Finding 26: [[LESSON-hook-if-clause-no-or]] says settings-file hooks have no `if`; the hooks doc says tool-event handlers take `if`, and `hooks.json` already uses it.
- Finding 31: the memory-tool and context-editing pages name `compact_20260112` as the server-side compaction edit; the compaction overview names a beta `compact-2026-09-04` and a top-level `compaction` parameter. Both are vendor pages; the relation (replacement or second mode) is not stated in what was read.

## Gaps
- Claude Code CHANGELOG read for 2.1.326 to 2.1.330 only (the fetch returned five versions of a 1.3 MB file); earlier releases that fixed other limitations are unread.
- Prompt caching page (TTL, `subagentPromptCacheTtl`, cache-write cost on resume) and `idleCompaction` setting not read.
- Compass overlap not mapped: `looprunner`/`looplib`/`sensorlib` versus `/goal`, `/loop` and `claude --bg`; `proctree` versus the supervisor; `review` surfaces; `bench/` versus `claude plugin eval`; `self_update` versus marketplace auto-update and `${CLAUDE_PLUGIN_DATA}`.
- Findings 7, 8, 24, 25, 26 are doc-versus-code observations; none was exercised on the host.
- `/skill-doctor` and `claude plugin details compass` token numbers not collected.
- Whether the host's `autoMemoryDirectory` can legally point inside a repo worktree and still be shared across worktrees is not stated.
- The Anthropic engineering posts on harnesses (axis 1) were not reread here.

## Candidate changes for Compass
Ranked by architectural impact. "Covered" means the vault or `plugin/` already does or decided it. Candidates only; the human and the planner decide.

1. **Inject the hot path through hooks instead of a frontmatter field the host ignores for subagents.** North stars: accuracy, near-zero cache misses, low token usage.
   - Change in `plugin/`: a `SubagentStart` hook running a CLI command that returns `additionalContext` (index head, active tasks, lesson index, within the 10,000-character cap), and a `SessionStart` handler on `source: "compact"` that re-injects it after compaction. The `initialPrompt` line in each agent file could then be retired.
   - Covered: no. `hooks.json` has neither event; `compass hot-path` exists as a command (`plugin/cli/commands/hot_path.py`). Evidence: findings 5, 6, 21.

2. **Use compaction hooks to carry the vault's state across the host's own compaction.** North stars: perfect memory, accuracy.
   - Change: `PreCompact` stdout (instructions for the summary: keep active task, branch, open gates) and `PostCompact` logging of `compact_summary` into a capture signal. Today only the 80%/95% handoff suggestion exists.
   - Covered: partly (context-check, handoff skill); no compaction-event handling. Evidence: findings 4, 5, 13.

3. **Re-check three recorded host limitations that docs now say are fixed or configurable, then retire the workarounds that no longer earn their keep.** North stars: low token usage, accuracy.
   - Items: worktree base (`worktree.baseRef: "head"`, finding 24), frontmatter `isolation` (25), `if` in settings hooks (26). Each is a one-command trial on the installed host; a confirmed fix would shorten `plugin/skills/build/SKILL.md` and retire or narrow the two lessons.
   - Covered: the lessons record the old behavior; no recheck is recorded. Evidence: findings 24-26.

4. **Move deterministic "run this command first" steps in skills into dynamic context injection, and add `paths`, `disable-model-invocation` and `skillOverrides`-style trimming for the 30 skills.** North stars: low token usage, near-zero cache misses.
   - Change: skill bodies embed `` !`compass lessons --for ...` `` or `hot-path` output; internal skills (for example `lesson-write`, `index-sync`) set `disable-model-invocation: true` so their descriptions leave the per-turn listing; measure with `/skill-doctor` and `claude plugin details`.
   - Covered: no. Evidence: findings 11, 12, 14. Risk named by the docs: a non-zero exit aborts the invocation.

5. **Path-scope `.claude/rules/compass-pipeline.md` (about 10.5 KB, loaded into every session and subagent) with `paths:` frontmatter or move parts into skills.** North star: low token usage.
   - Change: split the rule file; keep a short always-loaded core; scope stage-specific sections to `.compass/**`.
   - Covered: no; `compass-pipeline.md` has no `paths:`. Evidence: findings 17, 23. Related vault text on size limits was not rechecked.

6. **Adopt `claude plugin eval` for skill-triggering and hook behavior regressions.** North star: accuracy.
   - Change: an `evals/` directory in `plugin/` with `tool_used: Skill` graders (does the natural prompt invoke `compass:*`), `regex` and `file_exists` graders for vault outputs, a pinned `--model`; Windows needs WSL2 for Bash grants. No custom-code graders, so CLI behavior stays under the existing Python tests.
   - Covered: partly; `bench/` and `compass test-smells` exist, serving a different purpose (benchmark and test quality). Evidence: finding 20.

7. **Decide whether native `autoMemoryDirectory` and subagent `memory` frontmatter are allowed to write outside the vault.** North star: perfect memory (single source of truth).
   - Options for the human: leave host auto memory off for Compass projects; point `autoMemoryDirectory` into a vault folder; or leave both on and let `consolidate-memory` fold them into the vault.
   - Covered: `consolidate-memory` skill exists; the vault decision on host memory was not rechecked. Evidence: findings 15, 23, 29.

8. **Make `capture-signal` robust to `SubagentHandback` reports and plugin-scoped agent types.** North star: accuracy of the learning loop.
   - Change: read `tool_input.message` from a `SubagentHandback` hook when present; widen the SubagentStop matcher to match `compass:*` names. Needs a trial first (findings 7, 8).
   - Covered: no, by the files read.

9. **For SDK use, set `onFailure: "block"` on guard hooks and keep `settingSources` including `project`.** North star: accuracy (the guard is the "nothing destroys information" enforcement).
   - Change: documentation or a CLI check; shell hooks in `hooks.json` can set `onFailure: "block"` since 2.1.295.
   - Covered: no. Evidence: findings 10, 32.
