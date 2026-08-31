---
title: "Hermes Agent vs Compass: Fit, Feasibility, and Strategic Options"
type: research
status: complete
confidence: high
area: architecture
tags: [hermes-agent, compass-fit, host-evaluation, learning-loop, strategy]
created: 2026-07-25
updated: 2026-07-25
git_branch: "master"
git_commit: "42c9e59"
author: "claude (researcher)"
depends_on: ["[[SPEC-006-multi-host-agent-cli-support]]", "[[SPEC-001-compass-vision-and-architecture]]"]
summary: "hermes vs Compass: fit, feasibility, strategic options"
---

# Hermes Agent vs Compass: Fit, Feasibility, and Strategic Options

## Question

Three options are on the table: (a) move to hermes-agent and port Compass onto it, (b) use hermes-agent alone without Compass, (c) stay on Claude Code and improve Compass with ideas borrowed from hermes-agent. What does the hermes-agent source (NousResearch, cloned locally, version `0.19.0`, single-commit shallow clone dated 2026-07-25) actually support, deterministically or otherwise, for each option?

## Methodology

Technology landscape comparison. Source read directly (`SECURITY.md` in full, `AGENTS.md`, `README.md`, provider/hook/memory/skill/gateway modules) plus four parallel researcher sub-agents each assigned one axis (hook/RPC/cron feasibility; learning-loop mechanics; portable techniques; trust/security/maturity). Two sub-agent continuation calls mis-spawned as context-less fresh agents (tool-plumbing issue, not a source-material gap); those gaps were closed by direct Grep/Read investigation in the main thread. All findings below are static-source analysis, not a live-run hermes-agent instance.

## Findings

### Axis 1 - Compass-on-hermes feasibility (mechanism-by-mechanism)

1. **A deterministic, no-LLM, file-write-scoped hook exists and is a genuine PostToolUse equivalent** (confidence: high)
 `post_tool_call` fires unconditionally after every tool call, including cancelled ones, from the single dispatch chokepoint `model_tools.handle_function_call`. A user (or a plugin via `ctx.register_hook`) wires an arbitrary shell command or in-process Python callback to it, scoped by a `matcher` regex on tool name, receiving JSON (`tool_name`, `tool_input`, `cwd`, `session_id`) on stdin - the same shape as Claude Code's hook contract.
 - `agent/shell_hooks.py:28-59,187-196,384-391,432-489,501-552`
 - `model_tools.py:1018-1066,1344-1355`
 - `agent/tool_executor.py:182-183,462,492,1243,1611`
 - `hermes_cli/plugins.py:135-139,1158-1173`
 - `tools/file_tools.py:1962,1980,2105-2106` confirms `write_file`/`patch` are the file-write tool names to matcher against.
 - Classification: **(a) works essentially unchanged** - `compass sync` can be wired to `post_tool_call` with a matcher on `write_file|patch`, filtering to `.compass/**/*.md` from `tool_input` inside the script, exactly as the Claude Code hook does today.

2. **One-time consent gate, not a per-run gate** (confidence: high)
 Hook registration requires either interactive TTY approval once, or `--accept-hooks` / `HERMES_ACCEPT_HOOKS=1` / `hooks_auto_accept: true`; once approved it persists in `~/.hermes/shell-hooks-allowlist.json`.
 - `agent/shell_hooks.py:203-284,722-757`

3. **A second, coarser hook system exists but cannot gate per-write** (confidence: high)
 `gateway/hooks.py`'s `HookRegistry` fires on `agent:step` (once per turn in the tool loop, not per tool call) - too coarse to isolate a `.compass/**/*.md` write from any other write in the same turn. `gateway/builtin_hooks/__init__.py` ships no built-in hooks (empty extension point).
 - `gateway/hooks.py:1-49`, `gateway/run.py:21077`, `gateway/builtin_hooks/__init__.py:1`

4. **The RPC/scripting layer is agent-invoked, not wireable as an unconditional post-write action** (confidence: high)
 `tools/code_execution_tool.py` lets the LLM write a Python script that calls hermes tools via RPC in a child process ("collapsing multi-step pipelines into zero-context-cost turns" per the README). The model must choose to emit `execute_code`; it is an alternative *invocation path*, not a hook.
 - `tools/code_execution_tool.py:2-20,421-496`, `README.md:28`

5. **Cron is time-based only, confirmed no file-watch trigger** (confidence: high)
 `cron/scheduler.py:tick()` polls `next_run_at` in `~/.hermes/cron/jobs.json`. Could serve only as an eventually-consistent fallback ("run `compass sync` every N minutes"), never a deterministic-on-write guarantee.
 - `cron/scheduler.py:3864-4094`, `cron/jobs.py:1-6`

6. **Existing precedent for deterministic, LLM-invisible interception on file-mutating calls** (confidence: high)
 `tools/checkpoint_manager.py` already auto-snapshots (git-shadow-store) before `write_file`/`patch`/destructive `terminal` calls, transparently, once per turn - architecturally the same shape of guarantee Compass needs, though not itself an extension point.
 - `tools/checkpoint_manager.py:1-11,41-48`

7. **No per-role model pinning for subagents** (confidence: high)
 `tools/delegate_tool.py:delegate_task()` spawns children with `role` limited to `"leaf"`/`"orchestrator"`; model is inherited or passed per-call, with no static config mapping a fixed role name (e.g. "researcher") to a fixed model the way Compass pins researcher/planner/builder/tester/validator via agent-definition frontmatter. Classification: **(b) adapter needed** - a caller-side convention (always pass `model=X` when spawning a "researcher"-shaped delegate) would approximate it, but hermes has no native concept of a named, model-pinned agent role.
 - `tools/delegate_tool.py:1370,2432-2451,10-17,46-54`

8. **No structural human-approval gate equivalent to Compass's spec/plan status gates** (confidence: high)
 `tools/approval.py` gates *risky shell command execution* (dangerous-pattern detection + prompt, with "smart" auxiliary-LLM auto-approval for low-risk commands) - not *pipeline progression of a document*. `tools/clarify_tool.py` is agent-initiated Q&A, not a blocking status gate. No `draft -> review -> approved` file-status mechanism blocking a "build" phase until a human flips a flag was found anywhere in `agent/verification_evidence.py`, `agent/verify_hooks.py`, `tools/approval.py`, `tools/clarify_tool.py`. Classification: **(c) no equivalent** - this is pure prompt/skill-layer discipline Compass would have to re-author on hermes, hermes provides no native primitive for it.
 - `agent/verify_hooks.py` (full file, `DEFAULT_MAX_VERIFY_NUDGES = 3` at line 21 - a self-verification nudge loop, not a human gate)

**Net for Axis 1:** the single load-bearing question (can ANY hermes mechanism deterministically trigger `compass sync` on file writes with no LLM in the loop) is answered **yes** via `post_tool_call` - this is the strongest finding in the whole investigation and directly falsifies SPEC-006's most pessimistic branch for this specific host. Skills-as-slash-commands and markdown-based skill bundles also map cleanly (hermes skills are markdown+scripts loaded into context, same shape as Compass's `/compass:*` skills). What does NOT map cleanly: per-role model-pinned subagents (adapter), and human-approval pipeline gates (no equivalent, would be re-authored as prompt discipline).

### Axis 2 - Hermes-without-Compass: does the built-in learning loop subsume Compass?

9. **Autonomous skill creation is prompt-driven, not code-gated, and has a documented dedup gap** (confidence: high)
 The "create a skill after 5+ tool calls" trigger lives only as a system-prompt string (`SKILLS_GUIDANCE`), unconditionally appended whenever `skill_manage` is a valid tool - no code counts tool calls or forces the call. Critically, a skill only gets `created_by: "agent"` (which makes it eligible for the curator's staleness-tracking, pruning, and consolidation) when written from the periodic **background-review** fork; foreground autonomous creation (the zero-human-involvement, mid-conversation path `SKILLS_GUIDANCE` describes) is explicitly exempted by design comment, meaning the one path with no human trigger also has no dedup/lifecycle management.
 - `agent/prompt_builder.py:189-195`, `agent/system_prompt.py:229-230`
 - `tools/skill_manager_tool.py:1451-1462` (comment states this exemption is intentional: "foreground `skill_manage(create)` calls are user-directed... those skills belong to the user")
 - Human review: off by default (`skills.write_approval: false`), can be toggled on to stage every write for `/skills approve|reject`.

10. **Skill self-improvement is LLM-judgment-driven with a documented "bias toward action"** (confidence: high)
 The background-review prompt (`_SKILL_REVIEW_PROMPT`) explicitly instructs the reviewing LLM: *"Be ACTIVE — most sessions produce at least one skill update... A pass that does nothing is a missed learning opportunity, not a neutral outcome"* - the structural opposite of Compass's binary-trigger gate, which defaults to writing nothing unless one of five concrete conditions fired.
 - `agent/background_review.py:181-284` (signal list, preference order for how to apply an update, and an anti-list at lines 260-275)
 - No diff-based version history per skill patch exists; only `patch_count`/`last_patched_at` telemetry counters plus whole-library tar.gz snapshots before curator runs (keep=5, rollback via `hermes curator rollback`).

11. **Memory nudges are cadence-based counters, not condition-based triggers** (confidence: high)
 Memory nudge fires every 10 user turns (`_memory_nudge_interval`, default 10); skill nudge fires every 10 tool-calling loop iterations (`_skill_nudge_interval`, default 10) - both simple counters reset on fire, unconditional on whether anything notable happened, contrasted with Compass's five-condition binary gate.
 - `agent/turn_context.py:562-570`, `agent/conversation_loop.py:1105-1109`, `agent/turn_finalizer.py:634-639`, `agent/agent_init.py:1702-1705`
 - Nudge spawns a background-forked `AIAgent` restricted to `memory`+`skill_manage` tools, runs after the visible response so it never competes with the user's task. `agent/background_review.py:617-955,819-835`

12. **Memory has hard character caps and exact-duplicate rejection, weaker than Compass's semantic dedup** (confidence: high)
 `MEMORY.md` capped at 2,200 chars (~800 tokens), `USER.md` at 1,375 chars (~500 tokens); exceeding returns an error forcing the LLM to self-consolidate rather than silently truncating. Duplicate rejection is byte-exact only (no semantic recurrence-vs-new judgment like Compass's pre-write manifest). Security scanning for prompt-injection/exfiltration patterns runs on memory writes - Compass has no equivalent, not needed since Compass lessons are never re-injected as live system-prompt content the way hermes memory is.
 - `website/docs/user-guide/features/memory.md:15-30,121-149,173-179`

13. **Deterministic self-pruning tier exists for the curated subset only** (confidence: high)
 Curator auto-transitions `active` -> (30d unused) `stale` -> (90d unused) `archived`, gated by a real objective trigger (7-day interval AND 2h+ idle) - closer to Compass's binary-gate philosophy than the creation/nudge triggers above, but only reaches skills that went through background-review creation, and LLM consolidation of near-duplicates is opt-in (`curator.consolidate: false` by default).
 - `website/docs/user-guide/features/curator.md:17-40`

14. **Session search (FTS5) is real, agent-decided (not automatic), and the README's "LLM summarization" claim is stale relative to code** (confidence: high)
 Three parallel FTS5 tables (base, trigram, CJK-bigram) auto-synced via SQL triggers on every message write, queried through a single tool with three calling shapes (discovery/scroll/browse). Retrieval only happens if the LLM chooses to call it, per `SESSION_SEARCH_GUIDANCE` prompt text - nothing forces a search. The tool's own module docstring states *"No LLM calls anywhere — every shape returns actual messages from the DB,"* contradicting the README's marketing line about "LLM summarization for cross-session recall" (an earlier dual-mode implementation was merged away per the module's own history note).
 - `hermes_state.py:1241-1270,1300-1428,1513-1554`
 - `tools/session_search_tool.py:1-30,22-23,25-29,42-66`
 - `agent/prompt_builder.py:183-187`
 - This directly contradicts `README.md`'s claim of "FTS5 session search with LLM summarization" - see Contradictions.

15. **Honcho user modeling is opt-in, with real (if imperfect) consent controls** (confidence: high)
 Optional external memory provider building a "dialectic" cross-session user model, injected into the *user message* (not system prompt, to preserve caching) every turn plus a deeper reasoning pass every N turns. Granular per-peer observation toggles exist (`observeMe`/`observeOthers` for both user and AI); `honcho_conclude` supports listing/deleting persistent conclusions. No explicit runtime consent-flow UI beyond the setup wizard; retention policy is delegated to the external Honcho service, out of this repo's scope.
 - `plugins/memory/honcho/README.md:7-41,124-136,167-203,312-333`

**Synthesis of what each catches that the other misses (confidence: high, derived from 9-15):**
- Hermes catches: cross-session raw-conversation recall (Compass has no equivalent - vault is hand-authored docs, not an indexed transcript store); continuous user modeling; fully autonomous compounding with zero human action required by default.
- Compass catches: dedup applied uniformly to every write (hermes's dedup coverage has a documented gap for foreground-created skills); a structural default-to-nothing bias (hermes's background-review is explicitly biased toward finding something to write every pass, which risks noise); human review as the pipeline default rather than an opt-in flag (hermes ships `write_approval: false` everywhere by default); per-artifact code-state provenance (`git_branch`/`git_commit`/`author` - hermes has no diff-level audit trail for skill patches, only telemetry counters and whole-library snapshots).

### Axis 3 - What Compass/Claude Code loses if abandoned

16. **Compass's own architecture is entirely markdown + Python CLI, not Claude-Code-proprietary** (confidence: high, from Compass docs read directly)
 The vault (`.compass/`), the `compass` CLI, and the methodology are explicitly designed host-agnostic per [[SPEC-001-compass-vision-and-architecture]] ("Compass is not bound to one host... the vault and the mechanical harness are host-agnostic") and [[SPEC-006-multi-host-agent-cli-support]] ("the `.compass/` vault and the `compass` Python CLI work on the new host unchanged"). What is genuinely Claude-Code-welded today, per SPEC-006's own problem statement, is *delivery*: skills as `/compass:*` slash commands, subagents, the PostToolUse hook wiring, and the plugin install path - all four of which Axis 1 shows have a hermes-side equivalent or partial equivalent.

17. **Abandoning Claude Code loses Anthropic's first-party harness and its reviewed permission model** (confidence: medium)
 Claude Code's hook/plugin system is Anthropic's own, distributed as a first-party extension surface with a settled permission model (`hooks.json` matchers, tool-scoped permissions). Hermes's plugin trust model is explicit and mature on paper (SECURITY.md §2.5: "Plugins load into the agent process and run with full agent privileges... the boundary for third-party plugins is operator review before install") but is a newer, single-vendor (NousResearch) formalization rather than a marketplace with Anthropic's own review process behind it - no direct evidence found of a third-party plugin review/vetting pipeline analogous to Claude Code's plugin marketplace vetting; SECURITY.md explicitly places that burden on the operator (§3.2: "Community-contributed skills and plugins... are in the operator's review surface, not Hermes Agent's trust surface").

18. **Existing installs on other repos and the shipped v0.4.0 subsystems (decision coverage, model resolution table, hybrid hierarchy) are Claude-Code-plugin-shaped artifacts today** (confidence: medium, inferred - not independently verified against hermes's install mechanism)
 Every project currently running Compass installs it as a Claude Code plugin (`/compass:setup`, `.claude/` local install generated from `plugin/`). A hermes port would need a parallel install/update path through hermes's own plugin mechanism (`hermes_cli/plugins.py`) and a re-authoring of the human-approval-gate skills (Axis 1 finding 8) since hermes has no native equivalent - this is real one-time migration cost, not a design flaw in either system.

19. **Model-quality dependency shifts if the agent role moves from Claude Code's harness to hermes's provider layer** (confidence: medium)
 Claude Code today runs Claude models inside Anthropic's own harness (prompt construction, tool-calling loop, context management all tuned by Anthropic for Claude specifically). Hermes's provider layer is a declarative `ProviderProfile` abstraction (`providers/base.py:1-40`) with documented per-provider quirks (e.g. `OMIT_TEMPERATURE` sentinel for Kimi, "server manages it," `providers/base.py:21`) - real abstraction, but the existence of per-provider quirk handling is itself evidence that behavior is not perfectly uniform across providers/models; hermes's `max_iterations` and delegation defaults are shared across all providers regardless of the underlying model's tool-calling reliability (`AGENTS.md:328`), meaning agent-loop *behavior* (not just correctness) may vary with the model chosen through hermes in ways Claude Code's Claude-specific tuning does not have to account for.

### Axis 4 - What to steal for Compass regardless of host

20. **Live conversation compression uses a 50%-of-context-window threshold, protects head/tail, compresses only the middle via an auxiliary (cheap) model, and is the one documented exception to hermes's "never mutate past context" rule** (confidence: high)
 `context_compressor.py` triggers at `threshold_percent: float = 0.50` (50% of the model's context window by default, per-model override supported), summarizes down to `summary_target_ratio: float = 0.20` (20% of the threshold) using a cheap auxiliary model, with structured Resolved/Pending tracking, iterative summary updates across multiple compactions, and pre-pass tool-output pruning before the LLM summarization step.
 - `agent/context_compressor.py:1902-1976,2025,2037,4721`
 - AGENTS.md states explicitly *why* this is allowed to break the cache when nothing else is: "Per-conversation prompt caching is sacred... Anything that mutates past context... invalidates that cache and multiplies the user's cost. We do not do it (the one exception is context compression)." `AGENTS.md:19-23,1138-1140` - the stated rationale is that an uncompressed conversation eventually cannot fit the context window at all, so compression is the one case where the cache-cost trade-off is forced.

21. **A separate, offline trajectory compressor exists for *training data*, distinct from live conversation compression** (confidence: high)
 `trajectory_compressor.py` post-processes completed agent trajectories (JSONL) for model training: protects first turns and last N turns, compresses only middle turns starting from the 2nd tool response, replaces the compressed region with a single synthetic "human" summary message, and stops compressing as soon as the token target is met (not maximally). This is a batch/CLI tool (`--input`, `--target_max_tokens`, `--sample_percent` flags), not something that runs inside a live agent session.
 - `trajectory_compressor.py:1-30` (module docstring, strategy list)

22. **Session search (FTS5) technique is portable independent of the "LLM summarization" marketing claim** (confidence: high, see finding 14)
 The concrete portable mechanism: trigger-synced FTS5 virtual tables (base + trigram + CJK-bigram) over a message store, with cron-session demotion in ranking and subagent/tool-session exclusion from results by default, agent-decided retrieval via prompt guidance rather than automatic injection. Compass's current equivalent (handoff documents) is hand-authored and requires a human/agent to already know which handoff to read; FTS5 search is retrieval over *everything ever said*, a capability class Compass's vault format does not have at all today.

23. **Memory nudge cadence (fixed turn/iteration counters) is the concrete alternative to Compass's binary-trigger gate, with the source's own trade-off explicit in the review prompt itself** (confidence: high, see findings 10-11)
 The technique: two independent counters (`_turns_since_memory`, `_iters_since_skill`), each reset to 0 on fire, thresholds independently configurable (`memory.nudge_interval`, `skills.creation_nudge_interval`, both default 10). The counted unit differs by purpose (user turns for memory, tool-loop iterations for skills) - a deliberate distinction in the source, not an oversight.

24. **Curator's deterministic idle+interval gate, and its pre-mutation snapshot/rollback safety net, are separable techniques from the LLM-judgment creation/nudge triggers above** (confidence: high, see finding 13)
 The gate itself (`interval_hours` default 7 days AND `min_idle_hours` default 2h) is code-enforced and binary - unlike the creation/patch triggers, this part of hermes's design already matches Compass's "objective trigger, not introspection" philosophy. The tar.gz whole-library snapshot before every mutating curator run (`keep=5`, `hermes curator rollback`) is a reversibility mechanism Compass's consolidation pass does not currently have documented.

### Axis 5 - Trust and risk

25. **SECURITY.md is unusually precise and mature: it names exactly one load-bearing boundary (OS-level isolation) and explicitly disclaims every in-process heuristic as non-boundary** (confidence: high)
 "The only security boundary against an adversarial LLM is the operating system. Nothing inside the agent process constitutes containment — not the approval gate, not output redaction, not any pattern scanner, not any tool allowlist." Two supported isolation postures are documented: terminal-backend isolation (confines shell/file-tool operations only, explicitly does NOT confine code-execution subprocess, MCP subprocesses, plugin loading, hook dispatch, or skill loading) versus whole-process wrapping (Docker Compose, or NVIDIA OpenShell for per-session sandboxing with hot-reloadable network/filesystem/inference policy).
 - `SECURITY.md:58-119`

26. **Credential scoping is explicitly documented as risk-reduction, not containment** (confidence: high)
 Environment passed to shell/MCP/cron/code-execution children is filtered (provider keys, gateway tokens stripped by default); the doc states plainly "This reduces casual exfiltration. It is not containment. Any component running inside the agent process (skills, plugins, hook handlers) can read whatever the agent itself can read, including in-memory credentials."
 - `SECURITY.md:121-135`

27. **External-surface authorization has a uniform allowlist rule, with a documented "operator opted out" escape hatch for pairing** (confidence: high)
 Every network-exposed adapter (Telegram, Discord, Slack, WhatsApp, Signal, email, SMS, HTTP dashboards/plugins) must refuse to dispatch work until an allowlist is configured; code paths that fail open with no allowlist are explicitly in-scope security bugs (§3.1). Pairing (`gateway/pairing.py`) offers one-time codes as an alternative to static allowlists, approved by the bot owner via CLI; if no allowlist env var is configured for a platform, the code notes the gateway is deliberately left open by that operator's choice ("On an open gateway (no allowlist) we do nothing — the pairing store remains the grant record and leave the gateway open").
 - `SECURITY.md:192-220`, `gateway/pairing.py:115-127`
 - Test coverage confirms this is taken seriously: `tests/gateway/test_pairing_allowlist_bypass.py`, `test_discord_bot_auth_bypass.py`, `test_slack_bot_auth_bypass.py`, `test_feishu_bot_auth_bypass.py`, `test_busy_session_auth_bypass.py`, `test_allowlist_startup_check.py` (found via `find tests -iname "*auth*"` etc.) exist specifically to catch auth-bypass regressions.

28. **VPS/unattended blast radius is bounded only by the operator's chosen isolation posture, and the docs are explicit that most default configurations are NOT the hardened posture** (confidence: high)
 Terminal-backend isolation (the lighter option) does not confine code-execution, MCP, plugin loading, or hook dispatch - all of which run in the bare agent process regardless. Whole-process wrapping (Docker or OpenShell) is needed to bound all of those together, and SECURITY.md states plainly this is "the supported posture when the agent ingests content from surfaces the operator does not control... and for production or shared deployments" - implying default/local-backend usage is explicitly NOT the hardened posture for unattended cron+gateway+browser+computer-use combinations.
 - `SECURITY.md:70-119`

29. **Maturity signals: actively developed, version 0.19.0, large test surface, but shallow-clone git history prevents independent commit-cadence verification** (confidence: medium)
 `pyproject.toml` reports `version = "0.19.0"` (pre-1.0). The clone is `git rev-list --count HEAD` = 1 (shallow, single commit, dated `2026-07-25 06:30:23 +0000` at fetch time), so commit-frequency history could not be independently verified from this checkout - only a point-in-time snapshot. `find tests -name "*.py" | wc -l` = 2382 test files, a substantial suite, with a specific and dense cluster of auth/pairing/allowlist-bypass tests (finding 27) suggesting the security-sensitive paths are not an afterthought. AGENTS.md documents an active external-contribution triage process (a "sweeper" agent with three allowed auto-close reasons: `implemented_on_main`, `cannot_reproduce`, `incoherent`), implying a live, high-volume PR flow.
 - `pyproject.toml` (version line), `SECURITY.md` (disclosure process, 90-day coordinated window), `AGENTS.md` (contribution rubric, sweeper)

30. **"No lock-in" model-switching claim is substantively true (declarative per-provider abstraction exists) but with documented per-provider behavioral quirks** (confidence: medium)
 `providers/base.py` implements a `ProviderProfile` dataclass explicitly designed so "the transport reads this instead of receiving 20+ boolean flags" - real declarative abstraction, not a thin wrapper. But the presence of provider-specific sentinels (e.g. `OMIT_TEMPERATURE` because "Kimi: server manages it") is direct evidence that provider behavior is not perfectly normalized; switching providers via `hermes model` is genuinely code-free for the operator, but agent-loop *reliability* still depends on the underlying model's actual tool-calling competence, which the abstraction layer does not and cannot equalize.
 - `providers/base.py:1-40`

## Contradictions

- **README vs code, session search summarization** (finding 14): `README.md` markets "FTS5 session search with LLM summarization for cross-session recall." The tool's own module docstring (`tools/session_search_tool.py:22-23,25-29`) states "No LLM calls anywhere" and documents that an earlier dual-mode (fast/summary) implementation was merged away into a single no-LLM calling shape. `website/docs/user-guide/features/memory.md:181-207` corroborates the no-LLM-summarization current state. The README line is stale relative to the current code.
- **Skills sprawl risk vs curator safety net**: finding 9 shows the highest-risk skill-creation path (foreground, zero human involvement) is exempt from the curator's dedup/staleness machinery by explicit design choice, while finding 13 shows the curator itself uses a genuinely deterministic, Compass-like gate for the subset it does manage. These are not contradictory facts, but they mean "hermes has automated skill lifecycle management" is true only for a subset of how skills actually get created - worth flagging so the coverage gap isn't smoothed over by the existence of the curator.

## Gaps

- No live hermes-agent instance was run; all findings are static-source analysis. Runtime behavior of `post_tool_call` under real Windows/WSL conditions, and actual `compass sync` wiring, would need to be verified empirically before committing to option (a), matching SPEC-006's own falsification-criteria discipline ("must be confirmed empirically against the installed binary").
- Two sub-agent calls intended to cover trajectory compression and trust/risk in parallel returned as context-less fresh spawns due to a tool-plumbing mismatch (the `Agent` tool's `name` param does not resume a prior agent; a `SendMessage`-shaped continuation was implied by tooling but not available). Findings 20-30 were recovered via direct main-thread investigation instead, so coverage is intact, but the redundancy/cross-check that a second independent agent pass would have provided is missing for those specific findings.
- Whether hermes's `post_tool_call` hook reliably fires under Windows-native (non-WSL) execution was not independently tested - `agent/shell_hooks.py` spawns via `subprocess.run(..., shell=False)`, which is generally more portable than shell-string execution, but this is inferred, not run.
- No investigation was done into hermes's actual plugin/skill install-and-update UX in enough depth to compare it against Claude Code's `/compass:setup` / `/compass:update` flow beyond confirming `hermes_cli/plugins.py` exists as the mechanism.

## Three-option comparison

| | (a) Move to hermes, port Compass | (b) Hermes alone, no Compass | (c) Stay on Claude Code, steal hermes ideas |
|---|---|---|---|
| **Accuracy (goal 1)** | Preserved if the port is done carefully - deterministic `post_tool_call` hook exists (finding 1), so `compass sync` stays correct/deterministic. New risk: human-approval pipeline gates have no native primitive (finding 8) and must be re-authored as prompt discipline - a regression risk against goal 1 if done sloppily. | Weakest on this goal. Skill/memory writes are LLM-judgment-driven with a documented "bias toward action" (finding 10) and a dedup coverage gap for the highest-autonomy path (finding 9). No human-approval gate exists at all for what gets treated as durable, reusable knowledge. | Unaffected - Compass's existing deterministic harness (ADR-005) and human gates are untouched. Only additive risk is if borrowed ideas are integrated carelessly. |
| **Perfect memory (goal 2)** | Preserved - vault format is unchanged (finding 16), and hermes adds session-search recall Compass never had (finding 14/22), a genuine net gain if the port succeeds. | Hermes has memory (capped, deduped-by-exact-match) and skills, but no equivalent of a structured spec/research/plan/decision vault; project-level "perfect memory" would be markdown MEMORY.md/USER.md files under much smaller caps (2,200/1,375 chars) plus session search - materially thinner than Compass's model for project-scale decisions. | Preserved and potentially improved - session-search-style technique (finding 22) and the curator's snapshot/rollback safety net (finding 24) are portable ideas that could strengthen Compass's own memory guarantees without changing host. |
| **Almost zero cache misses (goal 3)** | The hot-path/tiered-loading design is host-independent (finding 16); no hermes mechanism threatens it if ported faithfully. Compression's cache-breaking exception (finding 20) is a hermes-specific concern for hermes's own conversation memory, orthogonal to Compass's vault tiering. | N/A in Compass's sense - hermes's own context/compression system (findings 20-21) manages its context window but has no three-tier hot/warm/cold *vault* concept; it manages one conversation's tokens, not a persistent multi-document knowledge base admission policy. | Unaffected. |
| **Low token usage (goal 4)** | Strong - `post_tool_call` runs pure Python/shell, off the agent's token budget, matching ADR-005's guarantee exactly (finding 1). | N/A as a comparison - without Compass there is no vault-sync cost to save, but also no equivalent discipline; memory/skill nudges do consume agent-visible turns/iterations as their trigger unit (finding 11), a different token-accounting model than Compass's phase-boundary-only extraction. | Unaffected; only gains available are optional (e.g. adopting a curator-style snapshot mechanism, which is cheap). |
| **What's gained** | Multi-host reach (SPEC-006's actual goal), real session-search-over-conversations capability, a working example of a deterministic post-write hook to model the adapter on, cron as an extra eventually-consistent fallback layer, Docker/OpenShell isolation options for unattended operation. | Simplicity (one system, not two), fully autonomous compounding without any human review overhead, built-in messaging-platform reach (Telegram/Discord/Slack/WhatsApp/Signal) Compass has no equivalent of at all. | Zero migration cost, all four north-star goals stay exactly as designed and already validated (v0.4.0 shipped), can cherry-pick findings 20-24 incrementally. |
| **What's lost / at risk** | Real one-time port cost: re-author human-approval gates (finding 8) since hermes has no native primitive; re-author or adapt subagent model-pinning (finding 7); migrate install path off Claude Code's plugin marketplace to hermes's own plugin loader; Claude Code's Anthropic-reviewed permission model is traded for hermes's operator-review-only plugin trust model (finding 17), which is honestly and explicitly documented as such but is a different risk posture. | Loses the entire spec/research/plan/build/validate pipeline, the human-involvement gradient, decision-coverage tracing, and everything SPEC-001/SPEC-002 encode - hermes's learning loop is real but answers a different question (what should the agent remember about *how it works and what the user wants*) than what Compass answers (what is the *validated, human-approved plan of record* for a piece of software). No evidence hermes's skill/memory system is designed to substitute for spec-approval-gated software planning. | Existing installs on other repos, the shipped v0.4.0 subsystems, and everything already proven in production are untouched; no messaging-platform reach or session-search capability without separately building it. |

## Recommendation

The human decides; ranking below is reasoning mapped to the four north-star goals, not a directive.

**Ranked: (c) first, (a) as a deliberate follow-on (not a replacement), (b) last for anyone who wants Compass's guarantees at all.**

- **(c) is the lowest-risk, highest-goal-alignment move available today.** Nothing about Compass's architecture requires abandoning Claude Code to capture hermes's best ideas. Findings 20-24 (compression trigger design, FTS5 session-search technique, cadence-vs-condition trigger philosophy, curator's snapshot/rollback safety net) are concrete, portable, host-independent techniques a planner could scope into Compass without touching the four ranked goals or the shipped v0.4.0 subsystems. This path has zero migration cost and preserves everything already validated.
- **(a) is now credible where SPEC-006 left it an open question** - finding 1 (the `post_tool_call` hook) directly answers SPEC-006's stated falsification risk ("no target host can trigger mechanical vault upkeep automatically") in the negative for hermes specifically: hermes *can*. That changes hermes from "unproven" to "a real second-host candidate" for SPEC-006's multi-host goal. But it is real, scoped migration work (findings 7, 8, 17), not a drop-in replacement, and should be evaluated as *adding* a host the way SPEC-006 frames it (Kimi Code, Codex, now hermes), not as abandoning Claude Code.
- **(b) trades away the most against goal 1 (accuracy).** Hermes's learning loop is genuinely more autonomous than Compass's, but "more autonomous" is not "more accurate" - findings 9, 10, and 12 document a system that defaults to writing without a human gate, is biased toward finding something to save every review pass, and has a dedup coverage gap in its highest-autonomy path. That is close to the anti-pattern Compass's own lessons subsystem was redesigned away from (per [[SPEC-002-lessons-and-index-subsystem]] and [[ADR-002-retrospective-lessons-subsystem]], introspective/unconditional capture is documented in Compass's own history as producing either nothing or fabrication). Hermes solves a different problem well (personal-assistant memory and cross-session recall); it does not appear, from the source, to solve Compass's problem (human-approved, traceable software-development planning) at all.
