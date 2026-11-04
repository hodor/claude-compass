---
title: "Hermes learning and context mechanisms: can each run inside Compass on Claude Code (2026-11)"
type: research
status: complete
confidence: medium
area: methodology
tags: [hermes-agent, learning-loop, skill-creation, context-compression, session-search, curator, fit]
created: 2026-11-04
updated: 2026-11-04
git_branch: "master"
git_commit: "e331edd"
author: "researcher (Claude)"
depends_on: ["[[SPEC-012-learning-loop]]", "[[SPEC-002-lessons-and-index-subsystem]]", "[[SPEC-029-human-verdicts-reach-compass]]", "[[RESEARCH-hermes-agent-capabilities]]", "[[RESEARCH-hermes-memory-mechanics]]", "[[RESEARCH-hermes-vs-compass-fit]]", "[[ADR-013-detached-worker-quiet-fallback]]"]
summary: "per-mechanism fit of Hermes learning and context features onto Compass hooks, skills, CLI and detached workers; token cost, goal served, ranked candidates"
---

# Hermes learning and context mechanisms: fit inside Compass on Claude Code

## Question

For each Hermes learning and context mechanism (hermes-agent commit a212421d, 2026-11-04), can it run inside Compass on Claude Code, with what overlap, what gap, what token cost, and which north-star goal (1 accuracy, 2 perfect memory, 3 almost zero cache misses, 4 low token usage)?

## Methodology

Technology landscape / comparative evaluation (DESMET feature analysis, case-study mode): each Hermes mechanism read in its own source, then mapped to Compass code read directly. Chosen because the question is "which of several concrete mechanisms fit", not "what exists". The brief carried no `grading:` field: no disclosure reached this run, so findings are marked and ungraded. Marks on every finding: code read directly in the Hermes repository (owner NousResearch, identity checked via the repository's own SECURITY.md and AGENTS.md); no peer review, no retraction, no preprint, citation count not applicable; convergence is "1 source (code)" unless stated. Claude Code behavior is taken from Compass's own hook and skill files, not the Claude Code docs; items that need the Claude Code docs are listed under Gaps.

## Scope

Axis 5 of 5. Read: `agent/background_review.py`, `agent/curator.py`, `tools/skill_manager_tool.py`, `tools/skill_manager_guards.py`, `tools/skill_ledger.py`, `tools/write_approval.py`, `tools/skill_usage.py`, `tools/skill_linter.py`, `tools/session_search_tool.py`, `agent/context_compressor.py` and its mixins, `agent/prepared_compaction.py`, `agent/micro_compaction.py`, `agent/native_compaction.py`, `agent/review_engine.py`, `agent/review_idle_queue.py`, `agent/learn_prompt.py`, `agent/learning_mutations.py`, `agent/skills_index_delta.py`, `agent/turn_context.py`, `agent/turn_finalizer.py`. The `hermes_state_*` files (about 70) are SQLite plumbing for sessions, locks, repair and migration; none is a learning mechanism and none was read line by line.

## Findings

### A. What changed since the July 2026 research (0.19.0)

1. **The background reviewer may now patch any non-locked skill, whoever wrote it** (confidence: high)
   The skill-review prompt tells the fork that hand-written, installed, bundled and pinned skills "are all yours to improve". The only exemption is a skill the user locked (`hermes curator lock`), which `skill_manage` refuses. The July research recorded protected skills the reviewer may never edit.
   - `agent/background_review.py:482` (prompt text); `tools/skill_manager_guards.py:224` (`_locked_guard`)
   - Delete stays restricted: `tools/skill_manager_guards.py:164` (`_background_review_delete_guard`), refuses autonomous deletes of anything but curator-owned sediment.

2. **Every skill mutation by any actor is appended to an audit ledger with content-addressed before/after blobs and a single-edit rollback** (confidence: high)
   JSONL ledger beside the skills dir, blobs deduplicated by sha256, actors `curator`, `agent`, `user`. `rollback_entry` fails closed if its safety capture fails. The ledger is documented as "telemetry, not a gate".
   - `tools/skill_ledger.py:1-9,38,569`; written from `tools/skill_manager_tool.py:746-775,811-835`
   - New relative to the July "no diff-based version history" finding in [[RESEARCH-hermes-vs-compass-fit]] item 10.

3. **Read-before-write is enforced, not requested** (confidence: high)
   A review fork must call `skill_view` on the exact skill (or support file) in the same review before `skill_manage` will patch or overwrite it; text quoted earlier in the transcript does not count. Read marks live in a per-review ContextVar set.
   - `tools/skill_manager_guards.py:25-70` (read marks), `agent/background_review.py:508-516` (prompt), `agent/background_review.py:1118` (read_file/search_files whitelisted so the guard can be satisfied)

4. **When `skills.write_approval` is on, skills always stage, from every origin, with a unified-diff preview** (confidence: high)
   The code comment says skills are too large to review inline. A staged write is a JSON record under a pending dir; `skill_pending_diff` renders full content (create) or a unified diff against the current file, folding batch ops in order so the preview equals what approval commits. Default is off.
   - `tools/skill_manager_tool.py:795-797`; `tools/write_approval.py:74,201,305`

5. **An advisory skill linter and a ~60-character description budget run on every skill write** (confidence: high)
   Findings never block; they attach to the tool result. The description budget exists because the skills index is in the system prompt every session.
   - `tools/skill_linter.py:1-10,197-211`; `tools/skill_manager_tool.py:441-460`; `agent/learn_prompt.py:19-40`

6. **The review fork is cache-parity engineered and token-bounded** (confidence: high)
   Same-model fork inherits the parent's cached system prompt, tools array and reasoning config byte for byte; dispatch-side tool whitelist only (memory and skills toolsets plus `read_file`, `search_files`); 16 iterations; aggregate input budget of 75% of the window capped at 600k. The source comment prices a review at about 30K tokens per event.
   - `agent/background_review.py:173-185,979-1062,1102-1140`; `agent/turn_finalizer.py:602-604`

7. **New entry points beyond the automatic nudge** (confidence: high)
   `/refine [focus]` runs the same review on demand (attended, full operation set); `/learn` builds one prompt that turns a described source into a skill using the live agent and `skill_manage`; `/review` spawns an independent reviewer subagent for any work in the conversation.
   - `run_agent.py:758,792-793`; `agent/learn_prompt.py:1-8,136`; `agent/review_engine.py:1-12`

8. **Reviews can defer to idle on the managed local runtime** (confidence: high)
   A session-coalescing queue (newest snapshot wins) dispatches when the process has been turn-free 15 s and the local server is idle, with a 30 min age-out. Applies only when the review would decode on the managed local llama server.
   - `agent/review_idle_queue.py:1-12,24-26`

### B. Per-mechanism fit

Format: Compass overlap; Claude Code piece; missing; token cost per session; goal.

9. **Skill creation and patching (background review + `skill_manage`)** (confidence: high on Hermes side, medium on mapping)
   - Overlap: the whole trigger/worker rail exists. `capturelib.due` opens an opportunity on a strong signal or on turn interval (default 12) with at least one signal (`plugin/cli/capturelib.py:62-65,291-318`); the Stop hook runs `capture-check` (`plugin/hooks/hooks.json`, Stop entry); a detached headless `claude` worker with its own lock, ledger rows and quiet fallback runs extract-lessons (`plugin/cli/commands/capture_worker.py:1-60,95-117`, [[ADR-013-detached-worker-quiet-fallback]] D-01 to D-07).
   - Claude Code piece: Stop hook (trigger) + detached worker (writer) + `.claude/skills/<name>/SKILL.md` (target). The worker prompt template is a one-line file-read instruction (`capture_worker.py:109-117`), so a second worker skill file can be added the same way.
   - Missing: a skill-writing contract (today `lesson-write` writes 5-line lessons only, `plugin/skills/lesson-write/SKILL.md`); signals that mean "a skill was loaded, corrected or ignored" (the strong set is handoff, validator, debug, phase-summary, agent-noted); a provenance marker so automatic skills are separable from human ones; the guards in items 3, 5, 10.
   - Token cost: zero in the main context (ADR-013 D-02); the worker spends its own headless session. Hermes prices the equivalent fork at about 30K input tokens per event with cache reuse (item 6); the Compass worker cannot reuse the parent's prompt cache (separate process), so expect a cold read of the evidence it is handed instead of a warm replay.
   - Goals: 2 (procedural knowledge persists), 1 (when gated), 4 (off the main budget).

10. **Human review of each new or changed skill** (confidence: medium)
    - Overlap: `compass review <file>... --why <path>=<line>` delivers to VS Code or Obsidian and returns verdict, notes, edits and a `git diff` since the sent commit (`plugin/cli/commands/review.py:1-40`; surfaces in `plugin/cli/review_surfaces/vscode.py`, `obsidian.py`). SPEC-029 wants the verdict to reach Compass.
    - Hermes analog: `write_approval` staging plus `skill_pending_diff` (item 4).
    - Constraint from the Compass side: a document goes out only when committed, inside the same vault and repository (`review.py` header). A skill under `.claude/skills/` is outside `.compass/`, and `.claude/` is gitignored in this repo; a user project's `.claude/skills/` may or may not be tracked. Whether `compass review` accepts a path outside the vault is a gap (see Gaps).
    - Missing: a staging location that is committed (a branch, worktree or tracked path) and an apply step that merges the staged skill on approval; Hermes keeps staged writes as JSON records and replays them with `apply_skill_pending` (`tools/skill_manager_tool.py:716`).
    - Token cost: zero (CLI). Goals: 1, 2.

11. **Skill guards: read-before-write, locked skills, lint, description budget** (confidence: medium)
    - Overlap: `compass guard` is a PreToolUse command hook that already denies destructive calls by subagents (`plugin/hooks/hooks.json`, PreToolUse entry); `compass validate` and `fix-frontmatter` exist for vault documents.
    - Claude Code piece: PreToolUse on Write/Edit for `.claude/skills/**` (read-before-write needs a record of Read calls, which a PostToolUse command can append to a per-session file); PostToolUse linter run.
    - Missing: a skill linter, the read-mark store, a lock flag. All are plain scripts.
    - Token cost: zero. Goals: 1, 4.

12. **Skill provenance and audit ledger with rollback** (confidence: medium)
    - Overlap: git already versions skills if tracked; vault documents carry `git_branch`, `git_commit`, `author` frontmatter. `sweep` and `retention` handle aging of logs (`plugin/cli/commands/sweep.py`, `retention.py`).
    - Hermes marks only review-fork-created skills `created_by: agent` and keeps usage in a sidecar, never in frontmatter (`tools/skill_usage.py:1-8`; `tools/skill_manager_tool.py:760-770`).
    - Missing: a sidecar for automatic skills and a per-mutation before/after record. A PostToolUse hook on `.claude/skills/**` can write both.
    - Token cost: zero. Goals: 2, 1.

13. **Curator: deterministic stale/archive plus optional LLM consolidation** (confidence: high on Hermes, low on mapping)
    - Hermes: dates only, no LLM: active to stale at 14 days and to archived at 30 days of inactivity, never-used skills anchored on `created_at`, pinned, locked and cron-referenced exempt; the run gate is 7 days since the last run and 2 h idle, seeded on first sight so a fresh install never mutates immediately; archive is the maximum destructive action. LLM consolidation is off by default.
    - `agent/curator.py:31-33,160-181,209-262`; `tools/skill_ledger.py` actor `curator`.
    - Overlap: `compass consolidate` (LLM-driven, human-approved, `plugin/skills/consolidate/SKILL.md`), lessons `seen`/`escalated` recurrence fields (`plugin/skills/lesson-write/SKILL.md`), `compass lessons` ranking by score.
    - Missing: a skill-use signal. Hermes bumps `use_count` when a skill is loaded; whether Claude Code exposes skill loads to a hook (a PostToolUse on the Skill tool, or transcript scanning) is not verified here.
    - Token cost: zero for the date walk; the consolidation pass is the existing worker pattern. Goals: 4, 3 (smaller skills index).

14. **Memory writes (MEMORY.md / USER.md, nudge every 10 user turns)** (confidence: high on Hermes, medium on mapping)
    - Hermes: integer counter ticked at turn start, review fork limited to the memory tool, hard character caps, drift guard that refuses to overwrite content the tool did not write (`agent/turn_context.py:766-775`; `agent/agent_init.py:1215-1244`; [[RESEARCH-hermes-memory-mechanics]] items 2-6).
    - Overlap: lessons catalog with 5-line cap, `capture-check` turn counter, `capture-note` (ADR-013 D-12). Claude Code carries its own memory files, and [[SPEC-028-agent-memory-is-good-enough]] already tracks measuring that.
    - Missing: nothing structural; Compass lessons are the analog. User-preference routing between "who the user is" and "how to do a task" (prompt block at `agent/background_review.py:304-326`) has no Compass counterpart, and the Hermes prompt states one-fact-one-store to stop duplication.
    - Token cost: already paid by existing capture. Goals: 2.

15. **Session search (FTS5 over every stored message)** (confidence: high on Hermes, medium on mapping)
    - Hermes: SQLite FTS5 (BM25), no LLM, four call shapes, cron sessions demoted, subagent/tool sessions hidden, 300-row scan cap (`tools/session_search_tool.py:1-30,43,371`).
    - Overlap: `compass sessions list --grep PATTERN` regex-scans Claude Code transcript JSONL, including tool calls, tool results and subagents (`plugin/cli/commands/sessions.py:1-25`); `compass clone` re-reads old sessions (SPEC-022).
    - Claude Code piece: transcripts already exist on disk per project; an index would be a CLI-built SQLite FTS5 table over them, refreshed by a SessionEnd or Stop hook (hook event names beyond those in `plugin/hooks/hooks.json` are unverified here).
    - Missing: the index (current `--grep` is a linear scan), message-level anchors, a recall tool the agent can call without a human pick.
    - Token cost: zero to build; per query the agent pays only for returned snippets (Hermes returns snippet plus 3-message bookends, `session_search_tool.py` schema). Goals: 2, 4.

16. **Context compression (threshold 50%, middle summarized by an auxiliary model)** (confidence: high on Hermes, low on mapping)
    - Hermes: head 3 and tail protected, `summary_target_ratio` 0.20, models under 512K floored at 0.75, tool-output pruning first, a deterministic fallback summary when the LLM fails, and a "lean" tail mode that appends an LLM-free anchor index, verbatim user messages and a recovery footer naming `session_search(query, session_id)` so compaction reads as deferred retrieval, not loss (`agent/context_compressor.py:985-999,2813-2853,3520-3597`; `cli-config.yaml.example` compression block).
    - Overlap: Compass does not compress. `compass context-check` halts at 80% and 95% and suggests `/compass:handoff` (`plugin/cli/commands/context_check.py:1-30`, [[SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]); the handoff is a vault document.
    - Claude Code piece: compaction (`/compact`, auto-compact) is owned by the host; Compass observes it only (the context-check state clears "as after `/compact`", `context_check.py` docstring). A compaction-time hook event is not used anywhere in Compass.
    - Transferable without a compressor: the recovery-footer idea (a handoff or compaction note that names the exact command to recover detail), and the anchor index (file paths, commands, identifiers pulled by script, not by LLM).
    - Token cost: a Hermes compaction is one auxiliary LLM call per attempt; Compass would add none. Goals: 3, 4.

17. **Prepared, micro and native compaction** (confidence: high on Hermes, low on mapping)
    - `prepare_ahead` summarizes in the background within 12% of the trigger (`agent/prepared_compaction.py:56`); micro-compaction is off by default because it breaks the prefix cache (`agent/micro_compaction.py:1-6`); native compaction uses an OpenAI server-side item on named models only (`agent/native_compaction.py:1-12`).
    - No Compass overlap and no Claude Code piece: all three act on the request the host builds. Not mappable. Goal 3 is the reason Hermes defaults two of them off.

18. **Skills index in the system prompt, delta notes, bundles** (confidence: high on Hermes, medium on mapping)
    - Hermes: index of name plus description in a mandatory-toned prompt section; mid-session changes reach the model as a per-turn note behind the cached prefix, not a prompt rebuild (`agent/skills_index_delta.py:1-14`); bundles load several skills under one slash command (`agent/skill_bundles.py:1-8`).
    - Overlap: Claude Code itself lists `.claude/skills/*/SKILL.md` descriptions; the Compass hot path is a bounded start-here set (index.md, active.md, lessons index, 5,000 token cap, [[SPEC-003-hierarchical-vault-organization]]).
    - Missing: a count/length budget on automatic skills so the host's skill listing does not grow without bound (Hermes enforces 60 characters per description for this reason; `agent/learn_prompt.py:26-34`).
    - Token cost: each automatic skill adds one description to every session. Goals: 3, 4.

19. **`/learn`, `/refine`, `/review` as user-initiated entry points** (confidence: high on Hermes, high on mapping)
    - Overlap: `/compass:learned` (manual lesson), `/compass:research-codebase`, the `reviewer` agent, `compass review`. `/learn` is a single prompt with no engine behind it (`agent/learn_prompt.py:1-8`), so it maps to one skill file.
    - Missing: a skill whose output is a SKILL.md and whose authoring standard is written down (Hermes keeps its standard in AGENTS.md and the linter).
    - Token cost: user-triggered, in the main context. Goals: 2, 1.

20. **Learning graph / journey (view and edit learned skills and memories)** (confidence: medium)
    - Hermes: read-only graph plus user edit/delete; deleting a skill archives it, deleting a memory rewrites its file under the tool's lock (`agent/learning_mutations.py:1-12`).
    - Overlap: `compass graph`, `canvas`, `tree` (`plugin/cli/commands/graph.py`, `canvas.py`, `tree.py`) and the Obsidian add-on. No skill nodes today.
    - Token cost: zero. Goals: 2.

### C. Design constraints the Hermes source states

21. **Foreground skill creation is exempt from curator management by design** (confidence: high)
    Only the background fork stamps `created_by: agent`; foreground creates "belong to the user". Anything Compass creates automatically needs its own marker to be reviewable and prunable.
    - `tools/skill_manager_tool.py:760-770`; `tools/skill_provenance.py:1-8`

22. **The reviewer prompt biases toward writing; the library-shape rules push back** (confidence: high)
    "Be ACTIVE... A pass that does nothing is a missed learning opportunity" sits beside class-level naming rules, "no PR numbers or dates as content", a do-not-capture list (environment failures, negative tool claims, transient errors, one-off narratives, unresolved attempts) and "the same lesson learned twice is ONE rule".
    - `agent/background_review.py:263-306,457-460`
    - Compass default is the opposite: binary triggers and an anti-list that writes nothing unless a condition fired (`plugin/skills/extract-lessons/SKILL.md` step 3).

23. **No harness trace separates "reviewed, nothing to save" from "never ran" (still)** (confidence: high)
    Completion is logged with a result class `none|skill|memory|skill+memory`, but the spawn is wrapped in `suppress(Exception)` and the log is a logger line, not a ledger.
    - `agent/background_review.py:~860-870` (`_log_review_completion`, `_classify_review_result`); `agent/turn_finalizer.py:610-617`
    - Compass already has the ledger: worker-started/finished/failed rows (ADR-013 D-03), `compass capture-stats`.

24. **Unattended review forks auto-deny dangerous commands and cannot reach the user's terminal** (confidence: high)
    A non-interactive approval callback resolves to deny; write tools stay denied so edits go through `skill_manage` validation.
    - `agent/background_review.py:1062-1075,1137-1140`
    - Compass worker equivalent: a headless `claude -p` child; its tool permissions are whatever the headless invocation grants (not read here).

## Ranked candidates (highest value first)

Ranking weighs the human's stated need (automatic skill creation with per-skill review in the md editor), reuse of the rail Compass already has, token cost, and the four goals. The human picks.

| Rank | Candidate | Goals | Main-context token cost | Reuses |
|---|---|---|---|---|
| 1 | Skill-authoring worker on the existing capture rail, writing to a staged, committed location, reviewed through `compass review` (items 9, 10) | 2, 1, 4 | 0 | capture-check, capture_worker, extract-lessons shape, review surfaces |
| 2 | Skill guards as command hooks: read-before-write, lint, description budget, lock flag (items 3, 5, 11) | 1, 4 | 0 | PreToolUse/PostToolUse command-hook pattern, `compass guard` |
| 3 | Provenance marker plus per-mutation ledger and single-edit rollback for automatic skills (items 2, 12, 21) | 2, 1 | 0 | PostToolUse hook, sweep/retention |
| 4 | Skill-authoring standard + `/learn`-style user-initiated skill (items 7, 19) | 2, 1 | user-triggered | `/compass:learned` pattern |
| 5 | Skill-use signal feeding signals in `capturelib` and a deterministic stale/archive walk (items 13, 18) | 4, 3 | 0 | capture signals, `compass lessons` score |
| 6 | Transcript session index (FTS5) behind `compass sessions` (item 15) | 2, 4 | 0 to build; snippets per query | `sessions list --grep`, clone |
| 7 | Recovery footer and script-built anchor index in handoffs (item 16, transferable part) | 3, 4 | 0 | handoff skill, context-check |
| 8 | Skill nodes in the vault graph/canvas (item 20) | 2 | 0 | graph, canvas |
| not mappable | Prepared/micro/native compaction, cache-parity forks, idle queue (items 6, 8, 17) | 3 | n/a | act on requests the host builds |

## Contradictions

- Item 1 here (reviewer may patch hand-written, bundled and pinned skills) differs from [[RESEARCH-hermes-memory-mechanics]] item 9, which records protected skills the autonomous reviewer may never edit. The prompt text at `agent/background_review.py:482` is the current source; the July document describes 0.19.0.
- [[RESEARCH-hermes-vs-compass-fit]] item 10 says no diff-based version history exists per skill patch; item 2 here shows a per-mutation ledger with before/after blobs and rollback. Newer code.

## Gaps

- Whether `compass review` accepts a file outside `.compass/` (a SKILL.md under `.claude/skills/`) is not established; `review.py` requires files in the same `.compass` vault and git repository. Verify by reading `plugin/cli/reviewlib.py` validation and running it on a skill path.
- Claude Code hook events not used by Compass today (PreCompact, SessionEnd, a Skill-tool matcher on PostToolUse) are not verified in this research; confirm against the Claude Code hooks reference before relying on items 13, 15, 16.
- Tool permissions inside the headless worker child (can it write under `.claude/skills/`?) were not read; `capture_worker.py` was read only to line 120.
- Measured Hermes review fire rate versus write rate is not in the repository; the "about 30K tokens per event" figure is the source comment, not telemetry.
- The `hermes_state_*` family was inventoried, not read in depth; a learning-relevant mechanism hidden there (for example `hermes_state_worker_compression.py`, `hermes_state_prompt_refresh.py`) is possible.
