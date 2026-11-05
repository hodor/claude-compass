---
title: "Hermes memory today: stores, caps, prompt budget, refresh"
type: research
status: complete
confidence: high
area: methodology
tags: [hermes-agent, memory, context-budget, prompt-cache, char-limits]
created: 2026-11-04
updated: 2026-11-04
git_branch: "master"
git_commit: "71dd0be"
author: "researcher (Claude)"
depends_on: ["[[RESEARCH-hermes-memory-mechanics]]", "[[RESEARCH-hermes-changes-since-july]]", "[[SPEC-028-agent-memory-is-good-enough]]"]
summary: "what Hermes stores as memory at a212421d, the exact caps, what is in every prompt vs on demand, and how the always-loaded part stays small"
---

# Hermes memory today: stores, caps, prompt budget, refresh

## Question

What does Hermes (commit a212421d, 2026-11-04) store as memory, what are the size caps and how are they enforced, what memory text enters every turn versus loads on demand, how does it keep the always-loaded part small, and how is memory refreshed mid-session?

## Methodology

Repository mining of the Hermes source (code read before docs, per `research-methods`: how an existing system actually behaves). Paths below are repo-relative to the Hermes clone. Marks on every finding: code, owner is NousResearch (the project's own repo); no retraction; not a preprint; no citations counted; single source (the code) unless a second is named. No `grading:` field reached this run, so findings are marked and ungraded because nobody was asked.

## What is new against earlier studies

- [[RESEARCH-hermes-memory-mechanics]] (July, 0.19.0) described three memory actions (add/replace/remove); the tool now offers add/patch/remove, with `replace` rejected (Findings 3, 4).
- July: background review could write freely. Now an unattended review fork may only `add`; its `patch`/`remove` are staged for approval (Finding 5).
- July: schema said "keep entries compact". Now the schema and system guidance restrict memory to facts true of EVERY session; task knowledge routes to skills (Finding 7).
- New: batch failures stop echoing the entry list; success replies carry no entry list (Finding 8).
- New: memory reloads from disk when the system prompt is invalidated after context compression (Finding 12).
- New: a prompt refresh epoch lets an operator rebuild a continuing session's stored prompt once (Finding 13).
- Not found: `agent/learning_*.py` hold no memory logic. `learning_graph*.py` renders a visual graph of skills and memory chunks; `learning_mutations.py` is user edit/delete of those nodes; `learn_prompt.py` builds the `/learn` skill-authoring prompt.

## Findings

### Stores, shape, caps

1. **Two built-in stores, both flat files of delimited entries** (confidence: high)
   - `MEMORY.md` = agent notes (environment, conventions, tool quirks). `USER.md` = who the user is (role, preferences, style). Both under the profile's `memories/` dir.
   - An entry is a free-text string. Entries are joined with the delimiter `"\n§\n"`. No per-entry metadata fields, no timestamps, no ids; an entry is addressed by a unique substring (`old_text`).
   - `tools/memory_tool.py:38-40` - memories dir. `tools/memory_tool_store.py:26` - `ENTRY_DELIMITER`. `tools/memory_tool.py:384-393` - target semantics in the schema.
   - Marks: code, owner checked; no retraction; not preprint; 0 citations; 1 source.

2. **Caps are character counts: 2,200 for MEMORY.md, 1,375 for USER.md** (confidence: high)
   - Config defaults `memory_char_limit: 2200` (~800 tokens) and `user_char_limit: 1375` (~500 tokens) at an assumed 2.75 chars/token. Combined 3,575 chars, ~1,300 tokens. Docs state "~1,300 tokens total" and 8-15 entries for memory, 5-10 for user.
   - The counted length is the delimiter-joined entry string, so delimiters count.
   - `hermes_cli/config_defaults.py:1298-1312`; `agent/agent_init.py:1246-1250` - store built from config with the same defaults as fallback; `tools/memory_tool_store.py:397-410` - `len(ENTRY_DELIMITER.join(entries + [content])) > limit`; `website/docs/user-guide/features/memory.md:17-18,182-183,254`.
   - Marks: code plus docs agree; 2 sources agree.

3. **The model sees three actions: add, patch, remove; `replace` is rejected** (confidence: high)
   - `add` appends. `patch` swaps an exact span inside one entry and keeps the rest (`old_text` must occur once). `remove` deletes a whole entry. A call to `replace` returns an error telling the model to use `patch` (set `old_text` to the whole entry to rewrite it).
   - `patch` content cannot be empty; dropping text inside an entry means patching a longer span that contains it.
   - `tools/memory_tool.py:165-170,280-283,418`; `tools/memory_tool_store.py:134`.
   - Marks: code, owner checked; 1 source.

4. **Over-cap writes are refused, never truncated; consolidation is the model's job** (confidence: high)
   - A lone `add` that overflows returns an error naming current/limit chars, the overage, and `current_entries`, instructing ONE batch that removes/shortens stale entries and adds the new one.
   - Batches apply atomically and the limit is checked only on the final result, so one call can free room and add.
   - After 3 failed consolidation attempts in a turn, the reply becomes terminal ("stop retrying ... continue with your reply"); the counter resets on any success and at turn start.
   - A file already over the cap on load stays loaded with a warning; later adds are blocked until it is under the cap. No truncation of user memories.
   - `tools/memory_tool_store.py:186-221,329-337,223-250`; `tools/memory_tool.py:378-383`.
   - Marks: code, owner checked; 1 source.

5. **Unattended background review may only add; deletions are staged for a human** (confidence: high)
   - In a review fork, `patch`/`remove` (single or inside a batch) are not applied: they are written to a pending store with the pinned full target entry and surfaced via `/memory pending`. If staging fails the call is denied. `add` stays available.
   - Separately, `memory.write_approval` (default false) routes all foreground and background writes through an approval gate; background writes are then staged.
   - `tools/memory_tool.py:179-219` (`_background_delete_gate`); `hermes_cli/config_defaults.py:1302-1305`.
   - Marks: code, owner checked; 1 source.

6. **Dedup and drift guards at write and load** (confidence: high)
   - Exact-duplicate `add` returns success with "Entry already exists (no duplicate added)". On load, entries are deduplicated order-preserving (first occurrence wins).
   - Write and load both scan entries for injection/exfil patterns (strict scope); a load-time hit is replaced by a `[BLOCKED: ...]` placeholder in the prompt snapshot only, while the raw entry stays removable.
   - `tools/memory_tool_store.py:29-32,223-257,403-405`.
   - Marks: code, owner checked; 1 source.

### What is in the prompt every turn

7. **Admission rule: only facts true of every session; task knowledge goes to skills** (confidence: high)
   - Schema text: memory is "injected into every future turn" and for "facts that apply to EVERY session regardless of task: who the user is, stable environment facts, standing conventions with no task home". Procedures, pitfalls, and per-task user preferences and corrections go to the task's skill via `skill_manage`, "where it loads only when relevant".
   - SKIP list in schema: trivial or easily rediscovered facts, raw dumps, task progress, completed-work logs, temporary TODO state.
   - System guidance adds: write declarative facts, not imperatives ("User prefers concise responses", not "Always respond concisely"); "a fact stale within a week belongs in session history".
   - `tools/memory_tool.py:376-396`; `agent/prompt_builder.py:195-234`.
   - Marks: code, owner checked; 2 locations agree.

8. **Tool replies are built to not grow the context they exist to shrink** (confidence: high)
   - Success reply: `done: true`, usage percent, entry count, note "do not repeat it"; no entries list ("echoing entries invites the model to find more to fix").
   - Batch-abort failures omit `current_entries` (issue #97316: each retry grew the context); a zero-match op carries only a few `closest_entries`.
   - `tools/memory_tool_store.py:339-348,654-667`.
   - Marks: code, owner checked; 1 source.

9. **The always-loaded text is: two entry blocks, one memory-guidance paragraph, one session_search sentence** (confidence: high)
   - Blocks render as a 46-char rule line, a header with a usage meter (`MEMORY (your personal notes) [67% - 1,474/2,200 chars]`, `USER PROFILE (who the user is)`), the rule, then entries. An empty store renders nothing.
   - Guidance is added only when the `memory` tool is loaded, narrowed when only one store is enabled or `skill_manage` is absent; `SESSION_SEARCH_GUIDANCE` is one sentence and only present when `session_search` is loaded.
   - `tools/memory_tool_store.py:669-676`; `agent/system_prompt.py:270-300`; `agent/prompt_builder.py:240-243`; `website/docs/user-guide/features/memory.md:42`.
   - Marks: code plus docs agree; 2 sources.

10. **Prompt is three tiers; memory sits in the last (volatile) tier after the skills index** (confidence: high)
    - Order: stable (identity, tool guidance, coding brief) then context (caller message, project context files, workspace) then volatile (skills index, MEMORY/USER blocks, external-provider block, plugin sections, profile line, timestamp, runtime environment).
    - The skills index leads the volatile band because skills mutate at runtime; memory blocks follow. "Never re-rendered mid-session."
    - `agent/system_prompt.py:737-805`.
    - Marks: code, owner checked; 1 source.

11. **Skills are an index in the prompt and a body on demand; memory is the narrow always-on exception** (confidence: high)
    - Every enabled skill is a `- name: description` row under `## Skills`; full bodies load by `skill_view(name)`. A coding posture can demote non-coding categories to one `[names only]` line, never removing a name. Descriptions are clipped to `SKILL_PROMPT_DESC_LIMIT = 60` chars at a word boundary with "..." (`clip_skill_description`), applied when each SKILL.md is parsed for the index; shipped skills are held to the limit by an authoring-standards test.
    - Project context files (AGENTS.md etc.) are capped at 20,000 chars by default, scaled up to a dynamic ceiling by model window (`CONTEXT_FILE_MAX_CHARS`).
    - `agent/prompt_builder.py:1155-1162,1233-1340,1033-1048`; `agent/skill_utils.py:844-876`; `agent/learn_prompt.py:19-22`; [[RESEARCH-hermes-memory-mechanics]] Finding 20.
    - Marks: code, owner checked; 3 sites agree.

### Refresh and on-demand loading

12. **Frozen snapshot per session; reloaded from disk only when the prompt is invalidated (after compression)** (confidence: high)
    - `load_from_disk` captures `_system_prompt_snapshot`; `format_for_system_prompt` returns that frozen text, not live state. Mid-session writes hit disk at once and are visible only in tool replies.
    - `invalidate_system_prompt` (called after context compression) clears the cached prompt and calls `load_from_disk()`, so the rebuilt prompt includes this session's writes. The compaction summary carries a note that persistent memory in the system prompt "is ALWAYS authoritative and active".
    - `tools/memory_tool_store.py:177-181,223-257,649-652`; `agent/system_prompt.py:815-835`; `agent/context_compressor.py:291-293,615-616`.
    - Marks: code, owner checked; 3 sites agree.

13. **Operator-triggered prompt refresh rebuilds a stored session prompt once** (confidence: high)
    - A continuing session replays its stored system prompt every turn so the provider prefix cache stays warm. `hermes sessions refresh-prompts` writes an integer epoch to `state_meta`; a session whose stamped epoch is lower rebuilds once on its next turn (history, session id, tools pin kept), persists the new bytes plus epoch. No request means one `state_meta` point read per turn and nothing else; "Nothing watches files".
    - `hermes_state_prompt_refresh.py:1-54`; `agent/prompt_refresh.py:1-45`.
    - Marks: code, owner checked; 2 files agree.

14. **Periodic write trigger: a user-turn counter, default 10, spawning a restricted review fork** (confidence: high)
    - `memory.nudge_interval: 10`; the counter hydrates from prior user turns on resume; 0 disables (default comment: "0 when an external provider auto-extracts"). Review prompt: two stores, one fact to ONE store never both, save only facts grounded in a user message or tool result, never infer traits, never turn a one-off request into a standing preference unless marked general; otherwise reply "Nothing to save."
    - `hermes_cli/config_defaults.py:1308-1309`; `agent/agent_init.py:1215,1244`; `agent/turn_context.py:761-772`; `agent/background_review.py:370-396`. Fork cost cap `max_input_tokens` (example 48,000; 0 or less = unlimited): `website/docs/user-guide/features/memory.md:441-458`.
    - Marks: code plus docs agree; 2 sources.

15. **On-demand layer one: `session_search`, no LLM calls, FTS5 over all sessions** (confidence: high)
    - Docs table: built-in memory capacity "~1,300 tokens total", token cost "fixed per session"; session search capacity "unlimited (all sessions)", cost "on-demand", "free, no LLM calls". Guidance sentence tells the model to search before asking the user to repeat themselves.
    - `website/docs/user-guide/features/memory.md:250-260`; `agent/prompt_builder.py:240-243`; mechanics in [[RESEARCH-hermes-memory-mechanics]] Findings 14-16.
    - Marks: docs plus prior code study; 2 sources.

16. **On-demand layer two: one optional external provider, recalled per turn into the user message, not the system prompt** (confidence: high)
    - `memory.provider` is empty by default (built-in only); one external provider at a time (bundled: retaindb, byterover; catalog: honcho, hindsight, supermemory, mem0, openviking, holographic). Lifecycle: initialize, system_prompt_block, prefetch, sync_turn, `on_pre_compress`, `on_memory_write` mirroring.
    - Per turn, `prefetch_all(query)` runs before the tool loop (skipped for trivial prompts), under a timeout, with a stuck-call gate. The text is fenced in `<memory-context>` with a note "recalled memory context, NOT new user input", repeated bullets within one section are dropped, and the block is appended to the current user message and replayed for as long as that row stays in context.
    - Prefetch size: no cap by default beyond a ceiling of 10x `hooks.output_spill.max_chars` (at least 100,000 chars); `memory.prefetch_spill_enabled` (default false) opts recall into the output-spill cap.
    - `hermes_cli/config_defaults.py:1299-1312`; `agent/memory_provider.py:1-20`; `agent/memory_manager.py:296-299,349-410`; `agent/turn_context.py:111-120,970-992`; `agent/memory_context.py` (`_drop_repeated_recall_lines`, `build_memory_context_block`).
    - Marks: code, owner checked; 1 source.

17. **Compression can be made to wait for the memory provider** (confidence: medium)
    - `compression.checkpoint_required` (default false) fails closed before lossy compaction unless an active provider confirms the checkpoint API and completes the checkpoint; `PRE_COMPRESS_CHECKPOINT_API_VERSION = 2`. Not traced past the config and constant.
    - `hermes_cli/config_defaults.py:565-567`; `agent/memory_provider.py` (constant).
    - Marks: code, owner checked; 1 source; call path not traced.

## Contradictions

- [[RESEARCH-hermes-memory-mechanics]] Finding 1 (add/replace/remove) is superseded by Finding 3 here (add/patch/remove).
- [[RESEARCH-hermes-memory-mechanics]] Finding 10 ("writes freely" by default) holds for write approval but the background fork no longer deletes unattended (Finding 5).

## Gaps

- Token measurements of a real Hermes system prompt (total size of the three tiers) were not taken; only configured caps are known.
- `agent/memory_manager.py` background-thread bounds (stuck calls 4, in-flight 16) were seen but the effect on recall size was not traced.
- The curator's LLM consolidation prompt was not read (carried from the July gap).
