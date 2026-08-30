---
title: "hermes-agent (NousResearch): Capabilities and Extension Surface, Source-Verified"
type: research
status: complete
confidence: high
area: architecture
tags: [hermes-agent, host-evaluation, learning-loop, extension-surface]
created: 2026-07-25
updated: 2026-07-25
git_branch: "master"
git_commit: "42c9e59"
author: "researcher (Claude)"
depends_on: ["[[SPEC-006-multi-host-agent-cli-support]]"]
summary: "hermes capabilities and extension surface, source-verified"
---

# hermes-agent (NousResearch): Capabilities and Extension Surface, Source-Verified

## Question

What IS hermes-agent, what can it actually do (verified in source, not README claims), and what does its extension surface look like — specifically: does it have any deterministic lifecycle-hook mechanism analogous to Claude Code's `PostToolUse`, and how tied is it to Hermes/Nous models vs frontier models (can it drive Claude)? Findings are facts only; no recommendation on Compass fit (a sibling researcher covers that).

## Scope

Source cloned at `C:\Users\rtgasi\AppData\Local\Temp\claude\...\scratchpad\hermes-agent`, commit `760112a`, branch `main`, dated 2026-07-25. Investigated via direct file reads/greps of the repo, `AGENTS.md` (the repo's own internal dev doc — treated as primary source since it documents contracts, not marketing), and `gh api` against `NousResearch/hermes-agent`.

## Methodology

Technology-landscape style survey (single subject, deep profile). Read the agent loop, provider layer, state layer, gateway, and `AGENTS.md` in full or by targeted grep; cross-checked prose claims in `AGENTS.md` against actual registration/invocation code (e.g. verified `VALID_HOOKS` is real by reading `hermes_cli/plugins.py`, verified the "none shipped" claim on `gateway/builtin_hooks/` by reading the file itself).

## Findings

### 1. Architecture and maturity

1. **Monorepo, Python core + TypeScript UI shells** (confidence: high)
 Python owns the agent loop, tools, state, gateway. TypeScript owns the TUI (`ui-tui/`, Ink/React), the web dashboard (`web/`), the Electron desktop app (`apps/desktop/`), and the docs site (`website/`, Docusaurus).
 - `AGENTS.md:230-270` — annotated project tree.
 - `AGENTS.md:432-441` — TUI process model: "TypeScript owns the screen. Python owns sessions, tools, model calls, and slash command logic," bridged over newline-delimited JSON-RPC on stdio.

2. **Core loop is synchronous, OpenAI-message-format, iteration-capped** (confidence: high)
 `run_agent.py`'s `AIAgent.run_conversation()` is a `while` loop bounded by `max_iterations` (default 90) and an `iteration_budget`, calling `client.chat.completions.create(...)`, dispatching tool calls through `handle_function_call()`, and appending tool results back into `messages` until the model returns a non-tool response.
 - `AGENTS.md:314-370` — full loop pseudocode and `AIAgent.__init__` signature (~60 params).
 - `run_agent.py` — the real file (~12k LOC per `AGENTS.md:232`).

3. **State store: SQLite with FTS5, one DB, profile-scoped** (confidence: high)
 `hermes_state.py`'s `SessionDB` defines `sessions`, `messages`, `session_model_usage`, `state_meta`, `gateway_routing`, `compression_locks`, `async_delegations` tables plus two FTS5 virtual tables (`messages_fts`, and a trigram variant `messages_fts_trigram` for CJK substring search backed by a custom loadable SQLite extension in `native/fts5_cjk/`).
 - `hermes_state.py:1047-1305` — `CREATE TABLE`/`CREATE VIRTUAL TABLE` statements.
 - `hermes_state.py:1362-1378` — CJK tokenizer built from `native/fts5_cjk/build.sh`, loaded via `load_fts5_cjk_extension(conn)`.
 - `AGENTS.md:236` — "SessionDB — SQLite session store (FTS5 search)."

4. **Provider abstraction is declarative, not per-vendor code branching** (confidence: high)
 `providers/base.py`'s `ProviderProfile` dataclass describes auth, endpoints, headers, and request-shape quirks (`prepare_messages`, `build_extra_body`, `build_api_kwargs_extras`, `fetch_models`) as overridable hooks. Every inference backend registers one `ProviderProfile` instance; `providers/__init__.py._discover_providers()` is a separate lazy scan (not the general PluginManager) with scan order bundled → user (`$HERMES_HOME/plugins/model-providers/`) → legacy in-repo file, last-writer-wins.
 - `providers/base.py:38-233` — full dataclass and hook methods.
 - `AGENTS.md:815-838` — scan order and override semantics.

5. **Maturity signals: young but very high-velocity, MIT-licensed** (confidence: high)
 GitHub repo created 2025-07-22 (~1 year old as of this research), 220,155 stargazers, 41,869 forks, 25,070 open issues, 386 contributors (top: `teknium1` with 7,041 contributions — a Nous Research co-founder), `tests/` has ~900 files / ~17k tests per `AGENTS.md:269`. The cloned checkout is a shallow single-commit snapshot so local `git log` gives no cadence signal; repo metadata came from `gh api repos/NousResearch/hermes-agent`.
 - `gh api repos/NousResearch/hermes-agent` — `created_at, stargazers_count, forks_count, open_issues_count, license.key: mit`.
 - `gh api repos/NousResearch/hermes-agent/contributors --paginate` — 386 logins.
 - Caveat: star/fork counts this large are unusual for a 1-year-old repo; not independently corroborated beyond the API response, worth a sanity check if load-bearing.

6. **`AGENTS.md` doubles as ground truth AND as an automated-triage policy document** (confidence: high)
 It defines a "Footprint Ladder" (extend existing code → CLI command+skill → service-gated tool → plugin → MCP server → new core tool, in that preference order) and an explicit rejection policy for "speculative infrastructure. Hooks, callbacks, or extension points with no concrete consumer."
 - `AGENTS.md:182-211` — Footprint Ladder, six rungs.
 - `AGENTS.md:96-101` — anti-speculative-hooks policy (directly relevant to any request for a new hook type).

### 2. Capability inventory

7. **TUI is a full replacement UI, not a wrapper on the classic CLI** (confidence: high)
 `hermes --tui` spawns a Node/Ink process talking JSON-RPC to a Python `tui_gateway` backend; the web dashboard and Electron desktop app both embed/reuse this same backend rather than re-implementing chat.
 - `AGENTS.md:428-506` — process model, transport, key surfaces table, explicit rule: "Do not re-implement the primary chat experience in React."

8. **~20+ messaging platform connectors, two different registration shapes** (confidence: high)
 Two locations exist: `gateway/platforms/` holds base classes plus a handful of standalone adapters (`signal.py`, `whatsapp_cloud.py`, `bluebubbles.py`, `yuanbao*.py`, `webhook.py`, `api_server.py`, `msgraph_webhook.py`, `weixin.py`, `qqbot/`). The bulk of named platforms (`telegram`, `discord`, `slack`, `whatsapp`, `matrix`, `mattermost`, `teams`, `sms`, `google_chat`, `irc`, `line`, `ntfy`, `photon`, `raft`, `simplex`, `wecom`, `dingtalk`, `feishu`, `homeassistant`) live as `kind: platform` plugins under `plugins/platforms/<name>/` (each with `plugin.yaml` + `adapter.py`), bundled and lazy-loaded on first use so a plain `hermes chat` doesn't pay for importing ~20 SDKs.
 - `plugins/platforms/` directory listing — 20 subdirectories.
 - `plugins/platforms/telegram/plugin.yaml` — real manifest: `kind: platform`, `requires_env: TELEGRAM_BOT_TOKEN`, feature list (threads, streaming edits, inline keyboards, allowlists).
 - `AGENTS.md:1435-1448` — deferred-loading rationale.
 - Caveat: `AGENTS.md:245-249`'s tree comment attributes the full platform list to `gateway/platforms/`, but the actual code places most of them under `plugins/platforms/` — a stale comment in the doc, confirmed by directly listing both directories.

9. **Cron is a tick-based scheduler running inside the live process, not a system-level daemon** (confidence: medium)
 `cron/scheduler.py` (4,298 lines) exposes a `tick(verbose, adapters, loop, sync, can_dispatch)` function rather than owning its own infinite loop at module scope; jobs are stored via `cron/jobs.py` and support duration (`"30m"`), "every" phrases, 5-field cron expressions, and one-shot ISO timestamps.
 - `cron/scheduler.py:4033` — `def tick(...)`.
 - `AGENTS.md:1052-1064` — job store/scheduler split, supported schedule formats, `hermes cron <verb>` CLI and `/cron` slash command.
 - Gap: did not trace who calls `tick()` on what cadence (gateway event loop vs a dedicated thread) — would need `gateway/run.py` read to confirm exactly how "always on" cron requires the gateway process to be running.

10. **Subagent delegation is in-process with role-based tool restriction, not OS-level sandboxing** (confidence: high)
 `delegate_task` spawns a subagent with its own context + terminal session. `role="leaf"` (default) cannot call `delegate_task`, `clarify`, `memory`, `send_message`, or `cronjob`. `role="orchestrator"` retains `delegate_task`, gated by `delegation.orchestrator_enabled` (default true) and bounded by `delegation.max_spawn_depth` (default 2). Batch mode runs multiple subagents concurrently, capped by `delegation.max_concurrent_children` (default 3).
 - `AGENTS.md:983-1015` — full delegation contract including the durability caveat: background `delegate_task` work is "detached from the current turn but still process-local" and does not survive a process restart (use `cronjob` or a background terminal for that).

11. **Terminal backends: local, Docker, SSH, Modal, Singularity, Daytona — all present as separate modules** (confidence: high)
 `tools/environments/` contains `local.py`, `docker.py`, `ssh.py`, `modal.py` + `managed_modal.py` + `modal_utils.py`, `singularity.py`, `daytona.py`, plus a shared `base.py` and `file_sync.py`.
 - `tools/environments/` directory listing.

12. **MCP: both client and server, using the official `mcp` Python SDK** (confidence: high)
 Client: `tools/mcp_tool.py` imports `mcp.ClientSession` / `mcp.client.stdio.stdio_client`, supports sampling and elicitation kwargs, and is configured via `hermes_cli/mcp_config.py` / `mcp_catalog.py`. Server: `mcp_serve.py` starts a stdio MCP server (`mcp.server.fastmcp.FastMCP`) exposing the *messaging gateway* (not general tool access) as 9+ MCP tools (`conversations_list`, `messages_send`, `events_poll`, `permissions_respond`, etc.) so external MCP hosts (explicitly: "Claude Code, Cursor, Codex") can drive Hermes's connected chat platforms.
 - `tools/mcp_tool.py:212-306` — SDK imports, capability-detection helpers.
 - `mcp_serve.py:1-27` — module docstring naming the exact 9-tool surface and giving a `claude_desktop_config.json` snippet.
 - `optional-mcps/{blender,linear,n8n,unreal-engine}/` — bundled example configs for connecting Hermes-as-client to external MCP servers.

13. **Batch/trajectory tooling exists for data generation and eval, separate from the interactive agent** (confidence: medium)
 `batch_runner.py`, `trajectory_compressor.py`, `agent/trajectory.py`, and `datagen-config-examples/` (e.g. `trajectory_compression.yaml`, `web_research.yaml`, browser-task JSONL configs) point at a training-data / eval generation pipeline, distinct from live chat sessions.
 - File listing only; did not read `batch_runner.py` internals — logic depth unverified beyond file presence and naming.

### 3. The learning loop

14. **Skills are markdown files with YAML frontmatter, close to but not identical to the generic "SKILL.md" convention** (confidence: high)
 Standard frontmatter fields: `name`, `description` (hard-capped ≤60 chars, enforced by a reviewer-run regex check), `version`, `author`, `license`, `platforms` (OS gating), plus a `metadata.hermes.*` namespace (`tags`, `category`, `related_skills`, `config`) that top-level `tags:`/`category:` mirror. Body has a mandated section order (`# <Skill> Skill`, `## When to Use`, `## Prerequisites`, `## How to Run`, `## Quick Reference`, `## Procedure`, `## Pitfalls`, `## Verification`), target length ~100-200 lines, scripts/references/templates in named subdirectories.
 - `AGENTS.md:870-960` — full frontmatter schema and "HARDLINE" authoring standards (8 numbered rules incl. required test location `tests/skills/test_<skill>_skill.py`).

15. **Two skill surfaces + two invocation paths, explicitly modeled on Anthropic's progressive-disclosure skills design** (confidence: high)
 `skills/` (built-in, loaded by default) vs `optional-skills/` (heavier/niche, installed explicitly via `hermes skills install official/<category>/<skill>`). Repo skills sync into `~/.hermes/skills/` guarded by an MD5 manifest so a re-sync doesn't clobber a user's local edits to a skill file (per coordinator relay from the hermes-extension sub-agent; not independently re-verified against `tools/skills_sync.py` line-by-line in this pass). Invocation is dual: (a) auto-discovery/progressive disclosure — every loaded skill's name+description is injected into the system prompt inside an `<available_skills>` block, and the model calls `skills_list`/`skill_view` tools to page in the full body only when it decides a skill is relevant, rather than every skill body being loaded up front; (b) explicit slash command — `agent/skill_commands.py` scans `~/.hermes/skills/` for a `/<skill-name>` invocation and injects the full skill body as a **user message** (not system prompt) specifically to avoid invalidating the prompt cache. Plugins can additionally register their own skills as `<plugin_name>:<skill_name>`-qualified, not entering the flat tree or the `<available_skills>` index (`hermes_cli/plugins.py:1198-1241`, Finding 22).
 - `agent/prompt_builder.py:1760-1762` — `<available_skills>` injection point.
 - `AGENTS.md:381` — "Skill slash commands: `agent/skill_commands.py` scans `~/.hermes/skills/`, injects as **user message** ... to preserve prompt caching."
 - `AGENTS.md:857-865` — the two directories and the `hermes skills install` command for optional skills.
 - `AGENTS.md:872-877` — frontmatter fields (`name, description, version, author, license, platforms, metadata.hermes.*`) matching the general SKILL.md/agentskills.io shape.

16. **Autonomous skill creation is agent-initiated file writes, tracked by a `created_by: "agent"` provenance field, then governed by a background curator** (confidence: high)
 `tools/skill_manager_tool.py` is the write path (create/edit/patch/delete a `SKILL.md`); `tools/skill_usage.py` owns a sidecar `~/.hermes/skills/.usage.json` recording `use_count`, `view_count`, `patch_count`, `last_activity_at`, `state` (active/stale/archived), `pinned` per skill. A background **Curator** (`agent/curator.py`, 2,018 lines, + `agent/curator_backup.py` for pre-run tar.gz snapshots) runs on an interval (`curator.interval_hours`, `min_idle_hours`, `stale_after_days`, `archive_after_days`), auto-archives stale *agent-created* skills only (bundled/hub-installed skills are off-limits to the curator), and never deletes — max destructive action is archive, always restorable via `hermes curator restore <name>`. Pinned skills are exempt from every auto-transition.
 - `AGENTS.md:1018-1049` — Curator contract, invariants, CLI verbs (`status, run, pause, resume, pin, unpin, archive, restore, prune, backup, rollback`).
 - This is the closest thing to "self-improvement": skills are LLM-authored artifacts, used, measured, and pruned by a separate deterministic background process — not weight/prompt self-modification.

17. **A "learning graph" is a read-only visualization layer, not the mutation mechanism** (confidence: high)
 `agent/learning_graph.py` (328 lines) builds a desktop-UI graph of "profile-learned" skills (non-base skills that are agent-created OR have `use_count > 0`) linked by declared `related_skills`, plus `MEMORY.md`/`USER.md` chunks as first-class nodes linked to skills by lexical token overlap. It is pure aggregation over on-disk state (`skills/`, `.usage.json`, `MEMORY.md`, `USER.md`) — no writes. Actual mutation (user-initiated edit/delete of a skill or memory chunk from the desktop journey UI) lives in the separate `agent/learning_mutations.py`, which maps a graph node id back to `tools/skill_manager_tool.py` (skills, archive-not-delete) or `tools/memory_tool.py::MemoryStore` (memory chunks, atomic temp-file+rename rewrite).
 - `agent/learning_graph.py:254-323` — `build_learning_graph()`, node/edge construction.
 - `agent/learning_mutations.py:124-207` — `delete_node`/`edit_node`, dispatching to skill archive or memory chunk rewrite.

18. **Memory persists as two flat markdown files, § (section-mark) delimited, no database** (confidence: high)
 `MEMORY.md` and `USER.md` under `<HERMES_HOME>/memories/` are split into chunks on a bare `\n§\n` separator; each chunk is one memory "card." Writes go through `tools/memory_tool.py::MemoryStore` with atomic temp-file+rename semantics (`_write_file`) so a concurrent reader never sees a half-written file.
 - `agent/learning_graph.py:193-220` — `_memory_cards()` reads and splits both files.
 - `agent/learning_mutations.py:192-197` — `_write_memory()` delegates to `MemoryStore._write_file`.
 - Gap: did not trace `agent/memory_manager.py`/`memory_provider.py` (the pluggable-backend orchestration layer — honcho, mem0, supermemory, byterover, hindsight, holographic, openviking, retaindb) in depth; `AGENTS.md:761-770` documents the `MemoryProvider` ABC lifecycle (`sync_turn(turn_messages)`, `prefetch(query)`, `shutdown()`, optional `post_setup()`) but this research did not read `agent/memory_manager.py`'s actual orchestration code to confirm exactly when `sync_turn` fires relative to a turn (turn-end vs periodic).

19. **Honcho is one of eight pluggable, optional memory-provider backends — not a core dependency** (confidence: medium)
 `plugins/memory/honcho/__init__.py` (1,561 lines) + `client.py` implement the `MemoryProvider` ABC as one of `{honcho, mem0, supermemory, byterover, hindsight, holographic, openviking, retaindb}` (`AGENTS.md:761-765`). Selection is via `memory.provider` in `config.yaml`; the policy note "No new in-tree memory providers (policy, May 2026)" (`AGENTS.md:786-795`) freezes this set — new backends must ship as standalone plugin repos.
 - Test evidence: `tests/test_honcho_startup_fail_open.py` name implies a fail-open contract (memory-provider startup failure does not block the agent) — file name inspected, contents not read in this pass; treat the "fail-open" claim as medium confidence pending a direct read of that test.

20. **FTS5 session search is a queryable tool over the SQLite store, not automatic summarization** (confidence: medium)
 `tools/session_search_tool.py` exposes search as a callable tool over `hermes_state.py`'s `messages_fts`/`messages_fts_trigram` tables. Separately, `agent/curator.py`'s background pass and `agent/context_compressor.py`/`agent/conversation_compression.py` handle context compression (summarization) as a distinct concern from search, triggered by context-size thresholds, not by session end. Session-level recap/export exists as an explicit CLI action (`hermes_cli/session_recap.py`, `session_export.py`) rather than an automatic background job.
 - `hermes_state.py:1241-1378` — FTS5 table definitions (already cited in Finding 3).
 - Gap: did not directly read `agent/curator.py`'s LLM review prompt or `context_compressor.py`'s trigger condition in this pass — confidence held at medium because the automatic-vs-on-demand boundary for summarization specifically was inferred from file/module separation, not a traced call path.

### 4. Extension surface

21. **Lifecycle hooks: YES, and one of the three mechanisms is a config-only, deterministic-shell-command PostToolUse equivalent — CORRECTED from an earlier pass of this research that missed it** (confidence: high) — **the critical finding for the hooks question**

 Hermes has **three layered, independently-discovered hook systems**:

 **(a) Plugin Python-callback hooks** (`hermes_cli/plugins.py`) — `VALID_HOOKS` is a set of ~20 named hook points: `pre_tool_call`, `post_tool_call`, `transform_terminal_output`, `transform_tool_result`, `transform_llm_output`, `pre_llm_call`, `post_llm_call`, `pre_verify` (turn-end verification-loop gate, Claude-Code-`Stop`-shaped), `pre_api_request`, `post_api_request`, `api_request_error`, `on_session_start`, `on_session_end`, `on_session_finalize`, `on_session_reset`, `subagent_start`, `subagent_stop`, `pre_gateway_dispatch`, `pre_approval_request`/`post_approval_response` (observer-only), `kanban_task_claimed`/`kanban_task_completed`/`kanban_task_blocked`. A plugin's `register(ctx)` calls `ctx.register_hook(name, python_fn)`; `invoke_hook(name, **kwargs)` fires them in-process from `model_tools.py` (tool events) and `run_agent.py` (session/turn events).
 - `hermes_cli/plugins.py:135-215` (`VALID_HOOKS` with inline per-hook contract docs), `1158-1173` (`register_hook`).

 **(b) Config-driven shell/subprocess hooks — THE load-bearing PostToolUse equivalent** (`agent/shell_hooks.py`) — a `hooks:` block in `config.yaml` (or `cli-config.yaml`) declares `{event, command, matcher, timeout}` entries for the *same* `VALID_HOOKS` event names as (a). `register_from_config()` wraps each entry as a Python closure and appends it into the identical `manager._hooks` dict that plugin hooks use — shell hooks and Python-plugin hooks compose through the same `invoke_hook()` call sites, with Python-plugin decisions winning ties. At fire time: `_spawn()` runs the command via `subprocess.run(argv, input=stdin_json, shell=False, timeout=...)` (default timeout 60s, max 300s) with JSON on stdin —
 ```json
 {"hook_event_name": "pre_tool_call", "tool_name": "terminal", "tool_input": {...}, "session_id": "...", "cwd": "...", "extra": {...}}
 ```
 — and parses JSON from stdout. `matcher` is a regex full-matched against `tool_name`, honored only for `pre_tool_call`/`post_tool_call` (e.g. a hook that only fires for `"write_file|patch"`). The stdout contract explicitly accepts **both** wire shapes for `pre_tool_call`: Claude-Code-style `{"decision": "block", "reason": "..."}` and Hermes-canonical `{"action": "block", "message": "..."}` — `_parse_response()`'s docstring calls this translation "the single most important correctness invariant in this module." `pre_verify` similarly accepts Claude Code's `Stop`-shaped `{"decision": "block", "reason": "..."}` (block-the-stop == keep going) alongside Hermes's own `{"action": "continue", "message": "..."}`.
 - `agent/shell_hooks.py:28-104` (wire protocol docstring with full per-event `extra` key tables), `432-489` (`_spawn`), `566-620` (`_parse_response`, dual-shape translation).
 - First use of any `(event, command)` pair prompts for interactive TTY consent (`y/N`) unless `--accept-hooks` / `HERMES_ACCEPT_HOOKS=1` / `hooks_auto_accept: true` is set; approvals persist to `~/.hermes/shell-hooks-allowlist.json` with the script's mtime recorded at approval time so `hermes hooks doctor` can flag drift (script edited since approval). `HERMES_SAFE_MODE=1` disables shell-hook registration entirely (`agent/shell_hooks.py:227-234`). CLI surface: `hermes hooks {list, test, revoke, doctor}` (`hermes_cli/hooks.py:26-326`).
 - Caveat (from the coordinator relay, not independently re-verified line-by-line in this pass): `transform_terminal_output`/`transform_tool_result`/`transform_llm_output` accept shell-hook registration but `_parse_response()` only recognizes `pre_tool_call`, `pre_verify`, and a generic `{"context": ...}` fallback (`agent/shell_hooks.py:598-620`) — reading the function confirms no explicit branch rewrites tool/LLM output text for those three events, consistent with the claim that only Python plugins can rewrite content for those specific hooks; shell hooks on them would fire but any content-rewrite intent in their stdout is silently dropped.

 **(c) Gateway event hooks** (`gateway/hooks.py`) — a third, separate, gateway-only system. Hooks are discovered from `~/.hermes/hooks/<name>/{HOOK.yaml, handler.py}`; `handler.py` defines `async def handle(event_type, context)`. Events: `gateway:startup`, `session:start`, `session:end`, `session:reset`, `agent:start`, `agent:step` (fires every turn in the tool loop), `agent:end`, `command:*` (wildcard on any slash command). Explicitly observer-only — "errors in hooks are caught and logged but never block the main pipeline" — coarser-grained than (a)/(b) and scoped to gateway lifecycle, not per-tool-call.
 - `gateway/hooks.py:1-70` — module docstring (event list, context dict shape) and `HookRegistry` class header.

 - `gateway/builtin_hooks/__init__.py` — read directly: contains only the docstring `"""Built-in gateway hooks that are always registered."""`, nothing else. This is a fourth, currently-empty slot ("none shipped" per `AGENTS.md:249`) reserved for hooks the core itself would always register — distinct from all three user-facing systems above, none of which are empty.
 - `AGENTS.md:96-101` — policy against "speculative infrastructure. Hooks, callbacks, or extension points with no concrete consumer" gates *new hook event names*, not the mechanisms themselves, which are mature and documented as first-class (`agent/shell_hooks.py`'s 900+ lines of allowlisting, drift detection, and CLI tooling is not a stub).
 - **Net**: a config-only, no-code, deterministic PostToolUse equivalent DOES exist (mechanism b) — a user writes a `hooks: {pre_tool_call: [{command: "...", matcher: "..."}]}` block in `config.yaml` and drops a script, no Python plugin authoring required. This corrects the initial pass of this research, which found only mechanism (a) and concluded (incorrectly) that hooks required writing a plugin; `agent/shell_hooks.py` was present in an early grep hit list but not read before that conclusion was drawn.

22. **Plugins are a four-source discovery system with a strict "don't touch core files" contract** (confidence: high)
 Sources, in override order: bundled (`<repo>/plugins/<name>/`) → user (`~/.hermes/plugins/<name>/`) → project (`./.hermes/plugins/<name>/`, opt-in via `HERMES_ENABLE_PROJECT_PLUGINS`) → pip entry points (`hermes_agent.plugins` group). Each plugin needs a `plugin.yaml` manifest + `__init__.py` with `register(ctx) `. `PluginContext` (`hermes_cli/plugins.py:339-1242`) exposes ~18 registration methods beyond hooks: `register_tool`, `register_cli_command`, `register_command` (in-session slash command), `register_context_engine`, `register_image_gen_provider`, `register_dashboard_auth_provider`, `register_video_gen_provider`, `register_web_search_provider`, `register_browser_provider`, `register_secret_source`, `register_tts_provider`, `register_transcription_provider`, `register_platform` (gateway adapter), `register_slack_action_handler`, `register_auxiliary_task`, `register_middleware`, `register_skill` (plugin-namespaced, opt-in-only skill not listed in `<available_skills>`).
 - `hermes_cli/plugins.py:1-32` (module docstring), `339-1242` (`PluginContext` methods).
 - Explicit rule, quoted: "plugins MUST NOT modify core files (`run_agent.py`, `cli.py`, `gateway/run.py`, `hermes_cli/main.py`, etc.). If a plugin needs a capability the framework doesn't expose, expand the generic plugin surface ... never hardcode plugin-specific logic into core." (`AGENTS.md:779-784`)
 - Plugin kinds affect load timing: `standalone` (opt-in via `plugins.enabled`), `backend` (bundled ones auto-load), `exclusive` (memory providers — one active at a time via config key), `platform` (bundled auto-load, lazy-imported), `model-provider` (separate discovery, not the general PluginManager).

23. **CORRECTED: a running Hermes agent DOES read `AGENTS.md`/`CLAUDE.md`/`.cursorrules` from the current working directory and inject them into the system prompt — as project-scoped coding context, not as the hermes-agent repo's own contributor doc** (confidence: high)
 `agent/coding_context.py` is "the single place that decides whether we're in [coding] posture and what it implies." It defines `_CONTEXT_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules")` (`agent/coding_context.py:86`) as "agent-instruction files surfaced separately from manifests in the snapshot," checks their presence at the workspace root (`agent/coding_context.py:815`, `context_files=[c for c in _CONTEXT_FILES if (root / c).is_file()]`), and these same three filenames also count as one of the signals (`_PROJECT_MARKERS`, line 82) that mark a directory as a "code workspace" in the first place. The resolved snapshot is baked into the system prompt once per session (not re-read per turn, to protect the prompt cache — `agent/coding_context.py:30-37`). Scope: `INTERACTIVE_CODING_PLATFORMS = {"cli", "tui", "acp", "desktop", ""}` (line 72) — explicitly excludes messaging platforms ("a chat bot in a group is not pair-programming").
 - `agent/coding_context.py:1-49` — module docstring: activation modes `auto` (default, prompt-only) / `focus` (also collapses toolset to `coding` + enabled MCP servers) / `on` (force) / `off`.
 - `agent/coding_context.py:82-86` — `_PROJECT_MARKERS` and `_CONTEXT_FILES` constants.
 - Not independently re-verified in this pass: the coordinator relay's specific claims that content is "prompt-injection scanned" and "truncated" before injection — plausible given the module's general caution about cache-safety and untrusted file content, but the exact scan/truncation code path was not read directly.
 - This finding **replaces** an earlier draft of this research that (incorrectly, based on an incomplete grep) concluded hermes-agent does not consume `AGENTS.md` at runtime at all.

24. **Custom subagent "roles" are two fixed enum values (`leaf`, `orchestrator`), not user-definable roles with arbitrary tool allowlists/models** (confidence: high)
 Per Finding 10, delegation exposes exactly two roles. `tools/delegate_tool.py:125` sets `MAX_DEPTH = 1` as the code-level default — "flat by default: parent (0) -> child (1); grandchild rejected unless `max_spawn_depth` raised" — a stricter default than this research's earlier reading of `AGENTS.md:1005` ("bounded by `delegation.max_spawn_depth` (default 2)"); `_get_max_spawn_depth()` (`tools/delegate_tool.py:467-490`) reads `delegation.max_spawn_depth` from config and falls back to `MAX_DEPTH=1` only when unset/invalid, so the discrepancy is most likely `AGENTS.md`'s prose describing the shipped `config.yaml` default (2) rather than the code's bare fallback constant (1) — flagged as a contradiction below rather than resolved, since `DEFAULT_CONFIG` in `hermes_cli/config.py` was not read in this pass to confirm which value ships. Per the coordinator relay (not independently re-verified): children inherit the parent's toolsets minus a fixed blocklist (no allowlist-authoring), and model override is a per-call kwarg, not a persisted/named role definition — so there is no Claude-Code-style "define a `code-reviewer` subagent with model X and tools [Read, Grep]" file-based role system.
 - `tools/delegate_tool.py:125-131, 467-490` — `MAX_DEPTH` constant and `_get_max_spawn_depth()`.
 - `AGENTS.md:964-1015` — Toolsets and Delegation sections (source of the "default 2" claim, unreconciled against the code constant).

25. **Distribution/install is git+shell-script based, not a package-manager/marketplace model for skills or plugins** (confidence: medium)
 `scripts/install.sh` / `install.ps1` install the `hermes` CLI itself. Plugins install by dropping a directory into `~/.hermes/plugins/` (manual, or via a future `hermes plugins` subcommand — `hermes_cli/plugins_cmd.py` exists) or via a pip entry point; optional skills install via `hermes skills install official/<category>/<skill>` which is scoped to the in-repo `optional-skills/` catalog (`tools/skills_hub.py::OptionalSkillSource`), not an arbitrary external registry.
 - `AGENTS.md:859-861` — `hermes skills install official/<category>/<skill>` command.
 - `hermes_cli/plugins_cmd.py`, `hermes_cli/skills_hub.py` — file presence confirmed, full CLI surface not enumerated in this pass.

### 5. Model dependency

26. **Provider catalog is broad and multi-vendor by construction — Hermes/Nous is one of ~30 registered providers, not privileged in the abstraction** (confidence: high)
 `plugins/model-providers/` contains one directory per backend: `alibaba, alibaba-coding-plan, anthropic, arcee, azure-foundry, bedrock, copilot, copilot-acp, custom, deepinfra, deepseek, fireworks, gemini, gmi, huggingface, kilocode, kimi-coding, minimax, nous, novita, nvidia, ollama-cloud, openai-codex, opencode-zen, openrouter, qwen-oauth, stepfun, upstage, vertex, xai, xiaomi, zai`. Each is a `kind: model-provider` plugin registering one `ProviderProfile` (Finding 4). `nous` is a same-shaped sibling entry, not a hardcoded default baked into the core loop.
 - `plugins/model-providers/` directory listing (32 entries).
 - `plugins/model-providers/anthropic/plugin.yaml` — `name: anthropic-provider`, `kind: model-provider`, `description: Anthropic (Claude)`.

27. **Anthropic/Claude support is first-class, including native prompt caching** (confidence: high)
 `agent/anthropic_adapter.py` (2,928 lines) forwards `cache_control` markers from the OpenAI-format tool/message dicts onto Anthropic's native Messages-API `cache_control` blocks (including a helper `_apply_assistant_cache_control_to_last_cacheable_block`), meaning a Hermes conversation running against Claude gets the same per-conversation prompt-cache reuse `AGENTS.md` calls "sacred" for cost control (Finding 6-adjacent: `AGENTS.md:15-21`).
 - `agent/anthropic_adapter.py:1716-1973` — `cache_control` forwarding logic (multiple sites: tool schema, content blocks, last-cacheable-block).
 - Bedrock (`agent/bedrock_adapter.py`) and Vertex (`agent/vertex_adapter.py`) adapters provide additional cloud-hosted paths to Claude models (file presence confirmed; internals not read in this pass).

28. **The core agent loop is provider-agnostic at the message-format level (OpenAI chat-completions shape); Nous/Hermes has no special-cased code path in the loop itself** (confidence: medium)
 Finding 2's loop calls a generic `client.chat.completions.create(...)`; provider-specific behavior is isolated to `ProviderProfile` hooks and per-vendor adapter files (`anthropic_adapter.py`, `bedrock_adapter.py`, `vertex_adapter.py`, `gemini_native_adapter.py`, `codex_responses_adapter.py`, `moonshot_schema.py`, `azure_identity_adapter.py`), not branches inside `run_agent.py`'s loop. Nous-specific files (`agent/nous_rate_guard.py`, `hermes_cli/nous_account.py`, `nous_billing.py`, `nous_subscription.py`) are billing/rate-limit concerns for the *optional* Nous-hosted inference path, structurally parallel to how any other paid provider would need account/billing plumbing — not evidence of the agent loop depending on Hermes models to function.
 - File-presence and naming evidence for adapters and Nous-specific files; did not read `nous_rate_guard.py`/`nous_billing.py` contents to confirm they are purely additive (gated behind `provider=nous`) versus touching shared code paths — confidence held at medium pending that trace.
 - `mcp_serve.py:19-27` module docstring's own example config uses `"command": "hermes"` with no model-provider assumption, consistent with BYOM design intent, though this is a weak/indirect signal.

## Contradictions

- **Subagent spawn depth default**: `AGENTS.md:1005` prose says `max_spawn_depth` defaults to 2; `tools/delegate_tool.py:125` hardcodes `MAX_DEPTH = 1` as the fallback when the config key is absent. Not reconciled — did not read `hermes_cli/config.py`'s `DEFAULT_CONFIG` to see whether the shipped `config.yaml` explicitly sets `delegation.max_spawn_depth: 2`, which would make both statements true simultaneously (doc describes the shipped default, code describes the bare fallback). See Finding 24.
- **`gateway/platforms/` directory contents vs `AGENTS.md`'s tree annotation**: `AGENTS.md:245-249` attributes the full ~20-platform list (telegram, discord, slack, ...) to `gateway/platforms/`. Direct directory listing shows most named platforms actually live under `plugins/platforms/<name>/` as `kind: platform` plugins; `gateway/platforms/` itself holds only base classes and a handful of standalone adapters (signal, whatsapp_cloud, bluebubbles, yuanbao*, webhook, api_server, weixin, qqbot/, msgraph_webhook). Likely a stale doc comment, not a code contradiction — see Finding 8.

## Gaps

- Did not trace exactly what process/thread calls `cron/scheduler.py::tick()` and at what cadence — unresolved whether "always-on" cron requires the gateway to be running continuously or if the CLI/TUI process also ticks it.
- Did not read `agent/memory_manager.py`'s orchestration code directly to confirm whether `MemoryProvider.sync_turn()` fires at turn-end automatically for every configured provider, or only for specific triggers.
- Did not read `agent/curator.py`'s LLM review prompt itself (which decides stale-vs-keep for agent-created skills) — only its config surface and CLI verbs via `AGENTS.md`.
- Did not read `hermes_cli/config.py`'s `DEFAULT_CONFIG` to resolve the `max_spawn_depth` contradiction above.
- Did not independently re-verify the coordinator-relayed claims about `tools/skills_sync.py`'s MD5-manifest behavior, the exact toolset-inheritance blocklist for subagents, or the prompt-injection-scanning/truncation step on injected `AGENTS.md`/`CLAUDE.md` content — these are reported as medium-confidence, single-source (sub-agent relay) claims within their respective findings above, distinct from this research's own directly-read evidence.
- Star/fork counts from `gh api` (220,155 stars / 41,869 forks on a ~1-year-old repo) are surprising relative to typical growth curves; reported as-is from the API without independent corroboration.
- Of five parallel sub-agent investigations dispatched for this research (architecture, capability inventory, learning loop, extension surface, model dependency), only the extension-surface agent's findings reached this synthesis (relayed via the coordinator, not directly) and were independently re-verified against source before inclusion (Findings 21, 23, 24 above). The other four axes (architecture/maturity, capability inventory, learning loop, model dependency) were covered entirely through this document's own direct primary-source investigation, not sub-agent output.
