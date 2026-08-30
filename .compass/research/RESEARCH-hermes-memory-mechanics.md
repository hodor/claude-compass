---
title: "hermes-agent: Memory Update and Retrieval Mechanics, Deep-Dive"
type: research
status: complete
confidence: high
area: methodology
tags: [hermes-agent, memory, retrieval, nudges, learning-loop, capture]
created: 2026-07-26
updated: 2026-07-26
git_branch: "master"
git_commit: "9e36bc8"
author: "researcher (Claude)"
depends_on: ["[[RESEARCH-hermes-agent-capabilities]]", "[[RESEARCH-lesson-capture-failure]]"]
summary: "memory update and retrieval mechanics, deep-dive"
---

# hermes-agent: Memory Update and Retrieval Mechanics, Deep-Dive

## Question

How exactly does hermes-agent update its memory/skill stores (write path: tool schemas, trigger mechanism, gate logic) and retrieve them into context (read path: auto-injection, on-demand search, skill discovery)? Goal: extract mechanics transferable to redesigning Compass's lesson-capture trigger, per the root-cause finding in [[RESEARCH-lesson-capture-failure]] that capture is coupled to a rare event rather than to events that reliably occur.

## Scope

Fresh clone of `NousResearch/hermes-agent` (depth 1, `main`, cloned 2026-08-05 — the prior partial clone at the given scratchpad path only contained `website/` + a truncated `.git/objects`, unusable for source reads, so this research re-cloned before investigating). Findings below go one level deeper than [[RESEARCH-hermes-agent-capabilities]] Findings 14-20 (which established that memory/skills/curator exist); this document traces the exact trigger code, tool schemas, and prompt text, and does not repeat architecture/maturity/plugin findings already filed there.

## Methodology

Direct source reads and greps: `tools/memory_tool.py`, `agent/background_review.py`, `agent/turn_context.py`, `agent/turn_finalizer.py`, `agent/agent_init.py`, `agent/conversation_loop.py`, `tools/session_search_tool.py`, `agent/prompt_builder.py`, `agent/system_prompt.py`, `agent/curator.py`, `tools/skill_usage.py`, plus the shipped user-facing doc `website/docs/user-guide/features/memory.md` (cross-checked against code, not taken at face value).

## Findings

### Axis 1: Memory UPDATE (write path)

1. **Single `memory` tool, three actions, batch shape preferred** (confidence: high)
 `memory(action, target, content, old_text)` for a single op, or `memory(operations=[...])` for an atomic multi-op batch checked only against the FINAL char budget — lets the model free space and add in one call instead of a multi-turn consolidate-retry dance.
 - `tools/memory_tool.py:1152-1217` — full `MEMORY_SCHEMA`.
 - `tools/memory_tool.py:562-669` — `apply_batch`, all-or-nothing semantics.

2. **Two flat stores, hard char caps, no auto-compaction** (confidence: high)
 `MEMORY.md` (2,200 chars / ~800 tokens default) and `USER.md` (1,375 chars / ~500 tokens default), `§`-delimited entries, under `~/.hermes/memories/`. An over-budget `add`/`replace` returns an error with `current_entries` instead of silently truncating — the model must explicitly consolidate (`replace`/`remove`) and retry in the same turn.
 - `tools/memory_tool.py:165-169, 390-447` — char limits, `add()` budget check.
 - Per-turn failure cap: after 3 consecutive over-budget/no-match failures, the tool stops offering a retry and returns a terminal "stop retrying" result so a fragile consolidation loop can't burn the whole turn budget (`_MAX_CONSOLIDATION_FAILURES_PER_TURN`, `tools/memory_tool.py:159-201`).

3. **Frozen system-prompt snapshot; live state diverges mid-session by design** (confidence: high)
 Entries are loaded and rendered into the system prompt once at session start; mid-session `memory` tool writes persist to disk immediately but do NOT re-enter the system prompt until the next session start — an explicit trade of memory freshness for prompt-cache stability. Tool responses always reflect live (not frozen) state.
 - `tools/memory_tool.py:148-157, 682-693`.

4. **Injection/exfiltration scanning at both write time and load time** (confidence: high)
 New content is scanned before being accepted (`add`/`replace`/batch); on load, every on-disk entry is independently re-scanned and a hit is replaced with a `[BLOCKED: ...]` placeholder in the system-prompt snapshot only — the raw entry stays in live state so the user can inspect and delete it via `memory(action=remove)`. Scope is "strict" (broadest pattern set) because memory is long-lived and system-prompt-injected.
 - `tools/memory_tool.py:86-89` (write-time), `242-276` (load-time sanitization).

5. **External-drift guard refuses to overwrite content the tool didn't write** (confidence: high)
 Before `replace`/`remove`/batch, the store re-reads the file under an exclusive lock and detects two drift signals: (a) round-trip mismatch (re-parse/re-serialize doesn't reproduce the raw bytes) or (b) a single parsed entry longer than the whole-store char limit (evidence of a non-tool writer — patch tool, shell append, manual edit, concurrent session). On drift it takes a `.bak.<timestamp>` snapshot and refuses the mutation rather than risk discarding un-roundtrippable content. `add` skips this check (append-only, can't clobber) but still refuses if the file exists and can't be read, rather than treating an unreadable file as empty and overwriting it to a single entry.
 - `tools/memory_tool.py:91-146` (error builders), `807-861` (`_detect_external_drift`).
 - Design constraint stated in the docstring: "never rewrite a file from a view that isn't the real one" (issue #26045 class of bug).

6. **The nudge is a harness-side integer counter, not a prompt suggestion** (confidence: high)
 `agent._turns_since_memory` increments once per USER turn (in `turn_context.py`, at turn start) whenever the `memory` tool is enabled and a memory store exists; when it reaches `agent._memory_nudge_interval` (config `memory.nudge_interval`, default **10**), `should_review_memory = True` is set and the counter resets to 0. This check is pure Python arithmetic — no model call, no text the model could ignore, decides whether the *review is spawned at all*.
 - `agent/turn_context.py:591-599` (memory nudge check, turn-based).
 - `agent/agent_init.py:1669, 1684` (default `10`, config key `memory.nudge_interval`).
 - Counters are hydrated from persisted history on session resume so a resumed multi-turn session doesn't reset to 0 (`agent/turn_context.py:543-551`, issue #22357).

7. **The skill nudge counts tool-calling iterations, not turns, and resets on actual use** (confidence: high)
 `agent._iters_since_skill` increments once per tool-loop iteration (inside the `while` loop in `conversation_loop.py`) whenever `skill_manage` is a valid tool for the session; checked AFTER the loop ends, in `turn_finalizer.py`, against `agent._skill_nudge_interval` (config `skills.creation_nudge_interval`, default **10**). It resets to 0 both on firing and whenever `skill_manage` is actually invoked mid-turn (`tool_executor.py:533-535`) — so an agent that's already updating skills organically doesn't also get nudged.
 - `agent/conversation_loop.py:1480-1484` (increment site).
 - `agent/turn_finalizer.py:698-704` (check site, default interval `10` at `agent_init.py:1769, 1772`).
 - `agent/codex_runtime.py:808-830` documents the parallel logic for the Codex Responses runtime (increments by `turn.tool_iterations` after each Codex turn instead of per chat-completions iteration — same counter, different increment granularity per backend).

8. **The trigger fires a real forked agent, not an injected suggestion the model can decline** (confidence: high)
 When either counter trips (and the turn produced a real, non-interrupted `final_response`), `finalize_turn` calls `agent._spawn_background_review(...)`, which forks a full `AIAgent` in a **daemon thread**, replays the just-completed conversation as its context, and runs it to completion with a **fixed prompt** and a **tool whitelist restricted to `memory`/`skill_manage`** (every other tool is denied at the fork's runtime, not just omitted from its instructions). This is qualitatively different from a Claude-Code-style Stop-hook text nudge: the review always executes as a real agent turn once triggered; the model-judgment surface is confined to *what the review agent decides to save*, not *whether the review runs*.
 - `run_agent.py:1796-1816` (`_spawn_background_review`).
 - `agent/background_review.py:654-935` (`_run_review_in_thread` — fork construction, `skip_memory=True` isolation from external providers, `_persist_disabled=True` so the fork never writes into the user's real session transcript, tool whitelist enforcement via `set_thread_tool_whitelist`).
 - Gate: only fires when `final_response and not interrupted` — an interrupted turn skips the review entirely even if a counter tripped that turn (`agent/turn_finalizer.py:716`).

9. **The review prompt itself is model-judgment, but heavily structured with explicit skip-lists** (confidence: high)
 Three prompt variants (`_MEMORY_REVIEW_PROMPT`, `_SKILL_REVIEW_PROMPT`, `_COMBINED_REVIEW_PROMPT`) are picked by which counter(s) fired. The skill-review prompt explicitly: (a) tells the model "Nothing to save is a real option but should NOT be the default" — biasing toward action; (b) gives a preference-ordered decision tree (patch a loaded skill > patch an existing umbrella > add a support file > create a new class-level skill); (c) lists categories to NEVER capture (environment-dependent failures, negative tool claims, transient errors that resolved, one-off task narratives, unresolved/untested "recommended approaches"); (d) defines protected skills (bundled, hub-installed, externally-owned, pinned, user-authored) the autonomous reviewer may never edit even if relevant, with an explicit `hermes curator adopt` escape hatch to flag-not-fix.
 - `agent/background_review.py:171-406` (all three prompt strings verbatim).
 - This is the harness constraining WHAT KIND of content is admissible even though WHETHER to write is the model's call — a middle ground between "fully harness-enforced" and "fully prompt-hoped."

10. **`write_approval` is a single on/off gate covering both foreground and background writes** (confidence: high)
 Default `false` — the agent (including the autonomous background reviewer) "writes freely." Setting `memory.write_approval: true` (or `skills.write_approval: true`) makes ALL matching writes route through `tools/write_approval.py::evaluate_gate`: interactive-CLI foreground writes prompt inline; everything else (messaging platforms, scripts, and — critically — the background review, since no user is present to prompt) is **staged** to `~/.hermes/pending/` and requires `/memory approve <id>` / `/skills approve <id>`. This is the explicit human-consent lever hermes ships for the exact failure mode "the agent saved a wrong assumption about me."
 - `tools/memory_tool.py:911-1013` (`_apply_write_gate`, `_apply_batch_write_gate`).
 - `website/docs/user-guide/features/memory.md:243-268` (config table + the "answer to the agent saved a wrong assumption" framing, quoted from source).

11. **No harness-side verification that a nudge produced a write** (confidence: high)
 The spawn call is wrapped `try/except: pass # Background review is best-effort` (`agent/turn_finalizer.py:716-724`). A review that concludes "Nothing to save." is a fully valid, unlogged-as-anomalous outcome — there is no counter, metric, or audit trail distinguishing "reviewed and genuinely found nothing" from "reviewed and silently failed to act." The only user-visible signal is `display.memory_notifications` (`off`/`on`/`verbose`), which shows nothing when there's nothing to show.
 - `agent/turn_finalizer.py:714-724`.
 - `agent/background_review.py:986-998` (notification only fires when `actions` is non-empty).
 - Contrast: nothing in hermes plays the role Compass's fleet audit (40 vaults, phase-report trace) plays for its own capture pipeline — there is no built-in instrumentation to detect "the review has fired 500 times and written nothing" at scale.

12. **Skill lifecycle state transitions are pure deterministic date/counter arithmetic; only the *quality* review is model-judgment** (confidence: high)
 `agent/curator.py::apply_automatic_transitions()` walks every curator-managed skill and moves `active -> stale -> archived` using only `last_activity_at`, `use_count`, `created_at`, cutoff dates (`stale_after_days` default 30, `archive_after_days` default 90) and a `pinned`/cron-referenced exemption set — zero LLM calls. A SEPARATE LLM-driven curator pass (`run_curator_review`, gated by `interval_hours` default 7 days and `min_idle_hours` default 2, called from `cli.py` session-start and `gateway/run.py` idle checks) handles consolidation/quality judgments the deterministic walk can't make (overlapping skills, vague names). Max destructive action anywhere in the curator is archive (never delete); `hermes curator restore <name>` reverses it.
 - `agent/curator.py:70-73` (defaults), `305-369` (deterministic transition walk), `2001-2019` (`maybe_run_curator`, call-site gating).
 - `cli.py:15056-15057`, `gateway/run.py:26061-26062` (the two harness call sites — session start and gateway idle, not a phase boundary).
 - `tools/skill_usage.py:18-23` (state machine docstring), `53-78` (protected-builtins list, e.g. `plan` — never touchable regardless of config).

13. **Provenance field distinguishes agent-authored from user-authored skills, gating what the autonomous reviewer may touch** (confidence: high)
 `skill_manager_tool.py`'s write path stamps `created_by: "agent"`; the background reviewer's protected-skill rules (Finding 9) key off this plus separate bundled/hub/external-dir/pinned flags. This is the mechanism that lets hermes give the model broad autonomous write power over its OWN artifacts while hard-blocking writes to anything human-owned.
 - Cross-referenced from `agent/background_review.py:255-269, 360-371` (protected-skills prose) and [[RESEARCH-hermes-agent-capabilities]] Finding 16 (`tools/skill_manager_tool.py`, `tools/skill_usage.py` — not re-verified line-by-line in this pass, carried forward from the prior research's citation).

### Axis 2: Memory RETRIEVAL (read path)

14. **Two tiers: always-injected frozen blocks, and an on-demand FTS5 tool — no semantic/embedding layer in the built-in path** (confidence: high)
 `MEMORY.md`/`USER.md` blocks render into the system prompt automatically every session (Finding 3). Everything else the agent has ever said or done is reachable only by the model actively calling `session_search` — a keyword tool (SQLite FTS5 + BM25 ranking), not a summarizer and not a vector/semantic index. There is no built-in mechanism that surfaces a relevant past session unprompted; retrieval beyond the two frozen files is 100% model-initiated.
 - `tools/session_search_tool.py:1-30` (module docstring: "No LLM calls anywhere — every shape returns actual messages from the DB").
 - `website/docs/user-guide/features/memory.md:200-211` (`session_search vs memory` comparison table, confirms "Automatic — all sessions stored" for storage but "On-demand (searched when needed)" for retrieval cost).

15. **`session_search` is one tool with four calling shapes inferred from which args are set** (confidence: high)
 - **Discovery** (`query=...`): FTS5 search, dedupe by session lineage, returns per-session `snippet` + `bookend_start` (first 3 msgs) + `messages` (±5 around the match, anchor flagged) + `bookend_end` (last 3 msgs) — goal→match→resolution without paying for the whole transcript.
 - **Scroll** (`session_id` + `around_message_id`): ±`window` (clamped 1-20, default 5) messages centered on an anchor, no FTS5, re-anchor on the boundary message to page further.
 - **Read** (`session_id` alone): dumps a whole session (head 20 + tail 10 if large) — used to resolve an `@session:<profile>/<id>` link the user pasted in.
 - **Browse** (no args): recent sessions chronologically, titles + previews, zero FTS5.
 - `tools/session_search_tool.py:982-1137` — full `SESSION_SEARCH_SCHEMA` with per-shape descriptions.

16. **Ranking is BM25 relevance by default, with an explicit anti-starvation demotion — not pure relevance** (confidence: high)
 Automation-sourced sessions (`cron`) are stable-sorted BELOW interactive sessions in discovery results (never excluded, just demoted) so a high-volume scheduled job's repetitive vocabulary can't crowd the user's own conversations out of the top-N — a documented real bug (#19434) the demotion was added to fix. `kanban`/`subagent`/`tool`-sourced sessions are excluded outright from search/browse. An optional `sort=newest|oldest` param overrides pure relevance for recency- or origin-shaped questions.
 - `tools/session_search_tool.py:42-56` (`_DEMOTED_SESSION_SOURCES`, `_HIDDEN_SESSION_SOURCES`, `_DISCOVER_SCAN_LIMIT` rationale), `233-247` (`_order_for_recall`).

17. **The system-prompt guidance for when to search is explicit and source-boundary-aware** (confidence: high)
 The schema description tells the model: "This tool searches Hermes conversation history only. It is not evidence about the current contents of external sources" — if the user names a live source (URL, file, contact), inspect THAT before/instead of `session_search`, and never conclude "not found" from a session-search miss alone when a direct source was available. Quoted verbatim: `"Do not conclude 'not found' or 'no prior correspondence' from session_search alone when a direct source was provided."`
 - `tools/session_search_tool.py:988-998`.

18. **Skill discovery is progressive-disclosure via a mandatory-toned system-prompt index, not a search tool** (confidence: high)
 Every enabled skill's name + one-line description is rendered into a `<available_skills>` block inside a `## Skills (mandatory)` system-prompt section on every turn (token cost scales with skill COUNT, not skill body size — full bodies load lazily via `skill_view(name)`). The instruction text is directive, not optional-sounding, quoted verbatim: `"Before replying, scan the skills below. If a skill matches or is even partially relevant to your task, you MUST load it with skill_view(name) and follow its instructions... Only proceed without loading a skill if genuinely none are relevant to the task."` This is prompt-hoped, not harness-enforced — nothing blocks the turn if the model skips it.
 - `agent/prompt_builder.py:1854-1882` (full injected text + `<available_skills>` construction).

19. **Skills index sits at the front of the volatile prompt band, ahead of memory, for cache-locality reasons** (confidence: high)
 Because skills mutate mid-session (the reviewer patches them) while memory blocks are comparatively more stable within a session, the skills index renders BEFORE the memory/user blocks in the "volatile" tier of the system prompt (itself placed after a "stable" tier). Rationale stated in-source: on a longest-prefix-match cache, an unchanged index still falls inside the reused prefix even if something later in the volatile band changed; a changed index only busts the cache from that point forward, not the whole scaffold.
 - `agent/system_prompt.py:498-534` (tier ordering + inline rationale comment).

20. **Category demotion narrows the skill index by posture without ever hiding entries entirely** (confidence: medium)
 Skills in categories irrelevant to the current "posture" (e.g., non-coding skills while pairing on code) are shown as a names-only line (`category [names only]: name1, name2, ...`) instead of full descriptions — cuts prompt noise while preserving loadability, because the source explicitly reasons that agent-created skills ARE the model's project memory and a model that can't see a name won't think to call `skills_list` to rediscover it.
 - `agent/prompt_builder.py:1807-1827` (demotion logic + the "NEVER remove entries entirely" comment).
 - Confidence held at medium: did not trace the full `_skill_should_show` condition matrix (tool/toolset gating) that runs before category demotion — only the demotion layer itself was read in depth.

21. **External memory providers (optional, off by default) are where semantic/graph retrieval actually lives** (confidence: medium)
 The 8 pluggable providers (honcho, mem0, supermemory, byterover, hindsight, holographic, openviking, retaindb — see [[RESEARCH-hermes-agent-capabilities]] Finding 19) are explicitly the layer hermes points to for "knowledge graphs, semantic search, automatic fact extraction, cross-session user modeling" beyond MEMORY.md/USER.md/FTS5. None of that is in the built-in path this research traced; confirming this is a documentation claim (`website/docs/user-guide/features/memory.md:348-360`), not independently re-verified against a provider's retrieval code in this pass.

## Contradictions

- None found between this pass and [[RESEARCH-hermes-agent-capabilities]]; this document extends rather than revises its memory/skills findings (14-20 there).

## Gaps

- Did not trace the `MemoryProvider.prefetch(query)` lifecycle hook for external providers — whether/when an external provider auto-surfaces a memory into context without an explicit tool call (this would be the closest thing to true contextual auto-surfacing, and is exactly the capability the built-in path lacks per Finding 14).
- Did not read `agent/curator.py`'s LLM consolidation-review prompt text itself (only its config/gating surface) — unclear how directive vs. permissive that prompt is relative to the background-review prompts quoted in Finding 9.
- No telemetry exists in-repo (that this pass found) measuring background-review fire rate vs. actual-write rate across real usage — Finding 11's "no verification" claim is a structural absence, not a measured one; would need production logs from a live install to quantify how often "Nothing to save." fires.
- Did not verify whether `should_run_now()` (curator's own interval gate) persists `last_run_at` durably across process restarts or only in-memory — relevant to whether the 7-day interval is truly wall-clock or resets on every CLI invocation.

## Design takeaways for Compass's learning loop

**What translates directly (harness-over-prompt, matches Compass's constraints):**

- **Counter-based deterministic trigger, decoupled from any specific pipeline phase.** Hermes's `_turns_since_memory`/`_iters_since_skill` fire on units that exist in EVERY session (user turns, tool iterations) — the exact fix [[RESEARCH-lesson-capture-failure]] calls for: capture must attach to events that demonstrably occur, not to `/compass:build`'s rare phase pause. A Compass equivalent could count turns/tool-calls/file-writes within any agent session (builder, researcher, conversational) and fire a capture opportunity every N, independent of which slash command is running.
- **The trigger is binary and harness-owned; only the content decision is model judgment.** Whether the review SPAWNS is Python arithmetic (`>=` a config int); whether anything gets WRITTEN is the model's call inside that spawned pass, constrained by an explicit skip-list (Finding 9) that plays the same role as Compass's anti-list. This maps cleanly onto Compass's existing capture core (extraction/dedup/anti-list, proven good per [[RESEARCH-lesson-capture-failure]]) — the fix is multiplying trigger SITES, not touching the judgment logic.
- **Skip-list content is directly reusable as prompt material**, independent of the trigger-topology change: "don't capture environment-dependent failures," "don't capture negative tool claims that harden into standing refusals," "don't capture unresolved/untested approaches as validated guidance" are all lessons Compass's own anti-list philosophy already shares in spirit and could adopt near-verbatim.
- **Deterministic vs. model-judgment split for lifecycle management** (Finding 12): archive/stale transitions by pure date math, LLM-only for consolidation judgment calls. Compass's `escalated`/`seen` lesson fields and `/compass:consolidate` could adopt the same split — a scripted pass computes staleness/recurrence, an LLM pass only handles merge/reword judgment calls the script can't make.
- **A write-approval gate as an opt-in human checkpoint** (Finding 10) is a pattern Compass could offer for teams wary of fully autonomous lesson-write: default free-write (matches Compass's current `lesson-write` skill autonomy), optional staging queue for review before a lesson enters the catalog.

**What does NOT translate (hermes-specific, or contradicts a stated Compass constraint):**

- **The forked-agent review mechanism itself is heavyweight** — a full second `AIAgent` instance, its own LLM call(s), thread-scoped stdout silencing, prompt-cache parity engineering (Finding 8's fork-kwargs list). Compass's "low token usage, mechanical work in scripts not agent tokens" north star (SPEC-001) argues against spawning a second LLM pass per N turns; a cheaper Compass-side equivalent would be a hook-driven prompt injection (nudge text, not a forked agent) at the same cadence, or a background script that flags "N turns since last lesson check" for the NEXT agent to see in its hot path rather than an autonomous LLM decision mid-session.
- **"No harness-side verification that a nudge produced a write" (Finding 11) is a gap Compass should NOT replicate.** This is precisely the blind spot the 40-vault fleet audit exists to fill for Compass — hermes has no equivalent instrumentation, and its own docs surface no evidence anyone has measured its real-world capture rate. Compass's redesign should keep (or add) a phase-report-style trace so a future audit can verify the NEW trigger topology actually fires, rather than assuming it does because the code looks deterministic.
- **Frozen-snapshot-at-session-start memory (Finding 3) doesn't map onto Compass's hot path model.** Compass already re-reads `.compass/index.md`/`active.md`/`lessons-catalog.yaml` fresh at the start of every agent invocation (not once per long-running session) — there's no prompt-cache-continuity problem to solve, so there's no reason to import hermes's frozen-snapshot trade-off.
- **Bounded-char-limit memory files with in-band consolidation (Finding 2) is solving a different problem** (keeping a system-prompt-injected block small) than Compass's lesson catalog (an unbounded set of small files with a separate O(1) index) — Compass's tag-index + 5-line-cap-per-lesson design already achieves boundedness a different way; no gap to fill here.
- **Retrieval auto-surfacing is a gap in hermes too (Finding 14, 21), not a solved pattern to import.** Hermes's built-in path is "always-inject the two frozen files + model-initiated FTS5 search," structurally identical to what Compass already does (`lessons-catalog.yaml` always-inject + agent-initiated full-lesson reads). The one place hermes suggests going further — external `MemoryProvider.prefetch(query)` auto-surfacing — is unverified in this pass (see Gaps) and is a third-party plugin concern for hermes, not built-in behavior; it is not evidence of a proven pattern Compass can lift.
