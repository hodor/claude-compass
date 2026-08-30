---
title: "Keeping an Active Set Active: Prior Art in Claude Code, hermes-agent, and Classic Open Source"
type: research
status: complete
confidence: high
area: methodology
tags: [active-tasks, hot-path, hooks, token-budget, prior-art, sweep, generated-view, taskwarrior, kernel]
created: 2026-08-28
updated: 2026-08-28
author: researcher-consolidation
summary: "every mature system bounds its active set mechanically - flag-then-sweep dominates, atomic moves are rare, and Compass already owns the zero-token trigger (PostToolUse compass sync)"
depends_on: ["[[SPEC-019-active-holds-only-active-work]]", "[[RESEARCH-hermes-memory-mechanics]]", "[[RESEARCH-hermes-agent-capabilities]]"]
---

# Keeping an Active Set Active: Prior Art

## Question

[[SPEC-019-active-holds-only-active-work]]: completed tasks accumulate in `.compass/active.md` forever because nothing mechanical removes them. What do Claude Code itself, hermes-agent, and mature open-source systems (Taskwarrior, todo.txt, org-mode, the Linux kernel, logrotate, git) do to keep an "active set" holding only active items, at zero LLM-token cost? Three researchers ran in parallel, one per axis; their full findings follow the synthesis, verbatim.

## Synthesis

A pattern taxonomy held up across all three axes:

- **(a) move-on-transition** - completing and removing are one atomic operation. Rare in practice: verified only in the kernel scheduler's `deactivate_task` (dequeue is part of the state transition itself). Taskwarrior's `task done` does NOT do this, despite appearances.
- **(b) flag-then-sweep** - completion is an in-place status flip; a separate mechanical pass relocates or prunes flagged items later. The dominant pattern: Taskwarrior legacy (`task done` flips status, `TDB2::gc()` moves the record on the next command's dispatch), todo.txt (`do` marks `x`, `archive` sweeps to done.txt - fused into one user-visible step because AUTO_ARCHIVE defaults ON), hermes cron (one-shots marked `state="completed"` in place, swept after 7 days), kernel LRU demotion under pressure, logrotate, git reflog expiry with a retention window.
- **(c) generated view** - "active" is a filtered query over one durable store; no removal ever happens because nothing was ever "in" a file. Taskwarrior 3.x moved here from (b) (the pending/completed file split is gone entirely); hermes messages (`active=1` soft-archival, old rows stay FTS-queryable) and delegations (status columns + three independent caps) are variants.
- **(d) done-flag-plus-consumer-pull** - marked done, removed only when an external actor collects it. The kernel zombie process is this pattern's canonical failure mode: if the consumer never runs, done items linger forever. **Compass's active.md today is pattern (d) with no consumer** - builders flip `[x]` and nobody ever reaps.

Cross-axis conclusions (all high confidence, each grounded in the findings below):

1. **No system asks an intelligence to decide what is active.** Every boundary in every system is a column check, a status flag, a timestamp comparison, or a counter. The LLM/human decides *completion*; the machinery decides *membership*.
2. **Completion and removal are almost never literally atomic - but the sweep is always mechanically guaranteed to run.** Taskwarrior gc runs before every subsequent command; todo.txt auto-archives on `do`; hermes sweeps on access. The guarantee matters, not the atomicity. A sweep that depends on someone remembering (org-mode manual archiving, zombie reaping by a dead parent) is exactly where every system accumulates cruft.
3. **History always survives removal in a colder store**: completed.data / done.txt / archive file with context metadata / `active=0` rows still FTS-searchable / rotated logs. Removal is relocation or reclassification, never destruction.
4. **Compass already owns a zero-token guaranteed trigger.** PostToolUse hook stdout never enters model context (verified in docs; exceptions are only UserPromptSubmit/UserPromptExpansion/SessionStart), and `compass sync` already runs on every vault write. The harness will never do this for us: Claude Code's own housekeeping (`cleanupPeriodDays`, default 30 days) sweeps only `~/.claude/projects/**/*.jsonl` transcripts, and its Todo/Task pruning is model-initiated, never automatic.
5. **Two fits for Compass stand out in the evidence** (research observation, not a decision): flag-then-sweep bolted onto the existing PostToolUse `compass sync` pass (the Taskwarrior-legacy/todo.txt shape: `[x]` is the flag, sync is the guaranteed sweep, a Shipped/archive record is the cold store), or the Taskwarrior-3.x generated-view shape (active.md becomes derived output over plan files, which already hold task state). Both preserve invariant-enforcement mechanically; the choice belongs to an ADR.


## Axis: Claude Code harness (rs-claude-code)

### Finding 1: TodoWrite/Task state lives in in-process memory, not on disk
Confidence: high
Evidence: Binary string `t.getAppState().todos[u]??[]` (`AYn` function, reminder-nudge logic) in `C:\Users\rtgasi\.local\share\claude\versions\2.1.251`. On this machine, `~/.claude/todos/` does not exist (`ls` returns "No such file or directory"), and grepping every `~/.claude/projects/*/*.jsonl` transcript for an actual `TodoWrite`/`TaskCreate` `tool_use` block returned zero matches across all projects. `~/.claude/sessions/*.json` and `~/.claude/tasks/session-*/` exist but hold per-process registry state (pid, cwd, messaging pipe) and empty per-session directories, not todo content - confirmed by reading `sessions/22212.json`.

### Finding 2: TodoWrite is being phased out in favor of TaskCreate/TaskGet/TaskUpdate/TaskList/TaskStop
Confidence: high
Evidence: `code.claude.com/docs/en/agent-sdk/todo-tracking.md`: "Claude Code leaves the task-tracking tools out of sessions by default" on Opus 4.8/Sonnet 5/Fable 5/Mythos 5+; "On other models, Claude Code provides the Task tools by default and TodoWrite only when you set CLAUDE_CODE_ENABLE_TASKS=0." Binary string confirms: `var $v="TodoWrite"` alongside a large adjacent set including `TaskCreate,TaskGet,TaskList,TaskUpdate,TaskStop,TaskOutput`.

### Finding 3: Task/Todo removal is explicit and model-driven, not harness-automatic
Confidence: high
Evidence: `code.claude.com/docs/en/agent-sdk/todo-tracking.md`, "Todo lifecycle": "Created -> pending", "Activated -> in_progress", "Completed -> completed", "**Removed**: Claude deletes a todo it no longer needs by setting `status: 'deleted'` in a `TaskUpdate` call." There is no lifecycle step where the harness itself deletes a completed item - the model must issue the removal call. This is the exact "who prunes" answer: the model, on its own initiative, never the runtime.

### Finding 4: TodoWrite/Task docs do not state replace-vs-append semantics for the list as a whole
Confidence: medium
Evidence: `code.claude.com/docs/en/tools-reference.md` fetch result: "The page contains no input schema for TodoWrite and no statement about whether a call replaces the entire todo list or appends/merges entries." The Task* tools (successor) are individually-addressed (`TaskUpdate` takes a `taskId`+`status`), which structurally implies per-item mutation rather than whole-list replace, but this is an inference, not a documented statement, for the legacy `TodoWrite` tool specifically.

### Finding 5: A "stale TodoWrite" nudge exists, keyed on turn counters, not on list content
Confidence: high
Evidence: Binary strings: `turnsSinceLastTodoWrite`, `turnsSinceLastTaskManagement`, `"The TodoWrite tool hasn't been used recently. If you're working on tasks [that] would benefit [from] tracking progress, consider using TodoWrite [to] track prog[ress]"`. Logic fragment: `if(r>=OUt.TURNS_SINCE_WRITE&&o>=OUt.TURNS_BETWEEN_REMINDERS){...y=t.getAppState().todos[u]??[]...}`. This is a reminder injected into context, not a file-cleanup mechanism - it nudges the model to *use* the tool, unrelated to pruning completed items.

### Finding 6: Hook stdout does NOT enter model context for PostToolUse, SessionStart's stdin/stdout rules differ per event
Confidence: high
Evidence: `code.claude.com/docs/en/hooks.md`: "For most events, stdout [is] written [to] debug log but not shown in transcript. [The] exceptions are UserPromptSubmit, UserPromptExpansion, and SessionStart, where Claude Code adds plain-text stdout as context that Claude can see [and] act on." This confirms the concern in the task brief: a hook that `print`s pollutes context only for `UserPromptSubmit`/`UserPromptExpansion`/`SessionStart`; a `PostToolUse` or `Stop` hook's stdout is invisible to the model (goes to a debug log only), so a zero-token mechanical file transform can safely run there and print freely without cost.

### Finding 7: PostToolUse cannot block; it can only warn Claude via stderr on exit 2 (tool has already run)
Confidence: high
Evidence: `code.claude.com/docs/en/hooks.md` per-event table: `PostToolUse` - Can block: **No** - "Shows stderr to Claude; the tool already ran." Exact wording: "warning to Claude from PostToolUse or PostToolUseFailure hook, exit 2 instead so Claude sees stderr even though tool already ran." Relevant if a mechanical active.md-sweep hook needs to report a problem (e.g., malformed task line) back to the model - it must exit 2 and write to stderr, and that IS shown to the model (unlike stdout on exit 0).

### Finding 8: Compass's existing PostToolUse hook is exactly this zero-token pattern already
Confidence: high
Evidence: `F:\claude\plugins\compass\plugin\hooks\hooks.json:4-41` - `PostToolUse` matched on `Write`/`Edit`/`MultiEdit` with `if: "Write(.compass/**/*.md)"` runs `compass sync --hook` (a `type: command` entry), `timeout: 30`. Its own top-level `description` states the design intent: "Every entry runs a command, never an agent, so no hook costs a turn of the agent's token budget."

### Finding 9: Full hook event catalog and blocking semantics relevant to a mechanical active.md sweep
Confidence: high
Evidence: `code.claude.com/docs/en/hooks.md` lifecycle table. Candidate triggers for a mechanical active.md-prune script, with block capability:
- `PostToolUse` (per tool call) - fires after every Write/Edit; cannot block, exit-2 stderr only.
- `Stop` (once per turn) - **can block**: "Prevents Claude from stopping, continues the conversation." Compass already uses this for `capture-check` (`hooks.json:54-65`).
- `SessionStart` (once per session) - **cannot block**: "Shows stderr to user only"; matcher values `startup`, `resume`, `clear`, `compact`, `fork` let a hook fire only on fresh session start, not every resume.
- `SubagentStop` / `TeammateIdle` - already wired for `compass capture-signal` (`hooks.json:66-90`).
- `TaskCompleted` - **can block**: "Prevents the task from being marked as completed." Not currently used by Compass; only relevant if Compass tasks route through the harness's own `TaskCreate/TaskUpdate` system rather than being lines in `active.md`.
- `PreCompact`/`PostCompact` - fire around context compaction, matcher `manual` vs `auto`; unrelated to file content but available if a sweep should run "whenever the session's context is about to shrink."

### Finding 10: Hook timeouts
Confidence: high
Evidence: `code.claude.com/docs/en/hooks.md`: "Defaults: 600 [seconds] for command, http, and mcp_tool; 30 for prompt; 60 for agent." `UserPromptSubmit` lowers the default to 30s. Compass's own hooks all set an explicit `"timeout": 30` (`hooks.json:12,24,36,48,60,72,85`), well under the 600s harness default. A timed-out command hook is "canceled: Claude Code discards the hook's output, and the hook renders no decision" - on `PreToolUse` specifically a timeout doesn't block the tool call (no equivalent statement found for `PostToolUse`/`Stop`).

### Finding 11: Claude Code has a built-in, throttled background-housekeeping sweep for its OWN state files (transcripts), unrelated to any hook system
Confidence: high
Evidence: Binary strings from `C:\Users\rtgasi\.local\share\claude\versions\2.1.251`:
- `backgroundHousekeeping`, a `.last-cleanup` sentinel file used to throttle repeated runs: `let t=await e.statMeta(Ee.state("last-cleanup"))...Date.now()-e.value.mtimeMs<a` (only re-runs after the throttle window elapses).
- Confirmed present on disk: `~/.claude/.last-cleanup` = `2026-08-28T19:06:08.873Z`.
- The sweep also handles `npm-cache-cleanup`, `.version-cleanup`, `.deep-link-register-failed`, and categorizes files via a path match: `t.includes("projects")&&t.includes("*.jsonl")` -> `"session_transcript"`, i.e. it targets `~/.claude/projects/**/*.jsonl`.
- This runs as part of the CLI's own startup/background logic (invoked via `Y8t`/`claim()`/`unref()` timers), **not** as a user-configurable hook event - it cannot be repurposed to sweep `.compass/active.md`.

### Finding 12: cleanupPeriodDays governs only chat transcript retention, default 30 days, unrelated to todos or vault files
Confidence: high (mechanism and default verified in binary; "30 days" also corroborated by third-party docs)
Evidence:
- Zod schema string in binary: `cleanupPeriodDays:T().int().positive().optional().describe("Number [of] days [to] retain chat tra[nscripts]...")`.
- Default-fallback function: `function DS(e){let r=(vn()||{}).cleanupPeriodDays??K;if(r===0)return null;...}` with `K=30` found a few lines away in the same module region (`...uid===r)?t:null}var K=30,Ce=0,Oe=["ccr-tip.json",...`).
- `code.claude.com/docs/en/settings-reference.md`: `cleanupPeriodDays` - "Choose how many days Claude Code keeps transcripts before deleting them," topic "Privacy and telemetry," settable in any settings.json scope.
- `0` disables the ceiling ("0 default) means no ceiling: transcripts kept...") in one code path, but this is describing an org-managed *ceiling* override interacting with a user's own `cleanupPeriodDays`, not a statement that `0` is the shipped default - the shipped default is `K=30`.
- Third-party corroboration (medium confidence, not Anthropic-authored): cleanup runs on startup, driven by file mtime, so anything that touches a transcript's mtime (sync tools, restores) can cause premature deletion.
- This setting only touches `~/.claude/projects/**/*.jsonl` transcripts. It has no relationship to `.compass/active.md`, to TodoWrite/Task state, or to any hook.

### Finding 13: Related but distinct on-disk trash/retention pattern for skills and plugins
Confidence: medium
Evidence: Binary strings: "moved to `~/.claude/skills/.trash` [at] next launch (deleted after cleanupPeriodDays; re-downloaded, not restored, if you re-enable)" and the identical pattern for `~/.claude/plugins/.trash`. This shows the harness's general retention idiom for its own managed directories: move-to-`.trash` on disable/uninstall, hard-delete after `cleanupPeriodDays` elapses on a later launch. It reuses the same `cleanupPeriodDays` clock as transcripts rather than a separate timer.

### Gaps
- Exact input schema for the legacy `TodoWrite` tool (field names, whether it accepts a partial diff or requires the full array every call) could not be found in either the docs or a decoded schema string in the binary within the time budget; only the newer `Task*` family's per-item update behavior is documented.
- Whether a timed-out `Stop` or `PostToolUse` hook (as opposed to `PreToolUse`) blocks or silently no-ops was not stated in the fetched hooks doc; the doc only makes the "doesn't block" claim explicit for `PreToolUse`.
- No `~/.claude/todos/` directory exists on this machine at all in the current Claude Code version (2.1.251), which may mean it was removed from a prior version's design (some third-party/community docs describe a `~/.claude/todos/<session-id>.json` file from older releases) or that todos are opt-in (`CLAUDE_CODE_ENABLE_TODO_TOOLS`) and simply never got exercised in any local session captured on this disk - not fully disambiguated.

## Axis: hermes-agent (rs-hermes)

Axis: how hermes keeps the model's per-turn context bounded without re-paying for finished work, for three subsystems: conversation compaction, async delegation, cron jobs.

Sources: fresh fetch 2026-08-28 of `NousResearch/hermes-agent@main` via `raw.githubusercontent.com` — `hermes_state.py` (15,274 lines), `agent/context_compressor.py` (8,692 lines), `agent/conversation_compression.py` (5,133 lines), `cron/jobs.py` (4,207 lines), `tools/async_delegation.py` (1,611 lines). Cross-checked against prior vault research `[[RESEARCH-hermes-memory-mechanics]]` and `[[RESEARCH-hermes-agent-capabilities]]`, cited inline where reused. Repo is high-velocity (386 contributors); some prior-research line numbers/table names had already drifted (noted below), so this pass re-verified everything against current `main`.

### Finding 1: Conversation compaction is non-destructive soft-archival, not deletion or exclusion-only

Confidence: high

`SessionDB.archive_and_compact()` flips old rows to `active = 0, compacted = 1` and inserts the LLM-produced summary as new `active = 1` rows, in one transaction. Old rows are never deleted and never leave the FTS index (`messages_fts` triggers key on INSERT/DELETE, not on the `active`/`compacted` flip). Live-context loads (`get_messages`, `get_messages_as_conversation`) filter `active = 1` by default, so the model only re-pays for the compacted set; `session_search`/`get_messages(include_inactive=True)` still surface the pre-compaction transcript, since `compacted=1` rows (unlike rewind/undo's `active=0, compacted=0`) are explicitly kept discoverable.
- `hermes_state.py:11757-11891` (`archive_and_compact`, full docstring + soft-archive UPDATE at 11864-11868).
- Contrast with prior research: `[[RESEARCH-hermes-memory-mechanics]]` Finding 3 and `[[RESEARCH-hermes-agent-capabilities]]` Finding 20 describe FTS5 `session_search` as a separate concern from compression — this finding shows the two are structurally the same store: compaction does not remove anything `session_search` can find, it only removes it from the live-context filter.

### Finding 2: A durable compression lock (not a queue) prevents concurrent rotation, and tolerates concurrent writes during the slow LLM summary call

Confidence: high

`compression_locks(session_id, holder, acquired_at, expires_at)` is a lease table: `try_acquire_compression_lock()` does DELETE-expired + INSERT-OR-IGNORE + SELECT-to-confirm in one write transaction (default TTL 300s), reclaiming a lock whose holder's PID no longer exists without waiting out the full TTL. `publish_compression_child`/`archive_and_compact` re-check the lease is still held by the same holder INSIDE the commit transaction, raising `SessionCompressionInProgressError`/`CompressionSessionBusyError` rather than publishing a stale compaction if the lease was lost. A `watermark` (the active-message row id captured at compression start) lets rows appended concurrently during the summary call be cloned (all columns except `id`) after the compacted set and re-sequenced with fresh ids, instead of being silently summarized away or stranded on a dead parent.
- `hermes_state.py:6996-7032` (lease recovery ordering rationale), `7784-7897` (`try_acquire_compression_lock`/`release_compression_lock`), `11784-11901` (watermark clone in `archive_and_compact`).

### Finding 3: Compaction triggers on estimated-token threshold against the model's context window, per-model configurable, with a small-context floor

Confidence: high

`ContextCompressor` (algorithm docstring: prune old tool results -> protect head -> protect tail by token budget -> LLM-summarize the middle -> iteratively update prior summary on subsequent compactions) computes `threshold_tokens` from `threshold_percent * max_tokens` (default 50%), with per-model overrides (`resolve_model_threshold`, substring-keyed `model_thresholds` dict, "higher of user/model threshold wins") and a floor that raises the effective percent for small-context models (<512K) so compaction starts earlier proportionally. `trigger_source` is `"manual"` (user-forced) or `"auto"` (threshold crossed) — this is the only two-way split found; no separate scheduled/periodic compaction path was located.
- `agent/context_compressor.py:2271-2280` (algorithm docstring), `2245-2270` (`resolve_model_threshold`), `2477-2536` (small-context floor + `threshold_tokens` computation).
- `agent/conversation_compression.py:2777-2783` (`trigger_source = "manual" if force else "auto"`).

### Finding 4: Async delegation completion is a table-row state transition plus a completion-queue event, not a move between separate "active"/"done" stores

Confidence: high

`async_delegations` is a dedicated SQLite table (its own DB file, opened via `tools/async_delegation.py`'s own `_connect()` — NOT one of the tables in `SessionDB`/`hermes_state.py`, correcting `[[RESEARCH-hermes-agent-capabilities]]` Finding 3's citation of `async_delegations` inside `hermes_state.py:1047-1305`; that table has since moved to its own module-owned DB, or the citation was already imprecise). Columns include `state`, `delivery_state` (`'pending'`/`'delivered'`), `delivery_attempts`, `delivery_claim`. On completion, `_finalize()` -> `_begin_finalization()` flips the in-memory record to `status="finalizing"` (kept "active" until durable persistence + queue publish succeed, so a process kill mid-finalize can't lose the result), pushes a `type="async_delegation"` event onto the shared `process_registry.completion_queue`, then `_finish_finalization()` sets the terminal status and calls `_prune_completed_locked()`.
- `tools/async_delegation.py:919-945` (`_begin_finalization`/`_finish_finalization`), `948-1010` (`_push_completion_event`), `154-176` (`async_delegations` CREATE TABLE, its own file).

### Finding 5: Async delegation bounding uses three independent caps, not one

Confidence: high

- In-memory dict: `_prune_completed_locked()` keeps only the `_MAX_RETAINED_COMPLETED=50` most-recently-completed records (by `completed_at`/`dispatched_at`), dropping older ones from the process's live view regardless of delivery state.
- Durable table: `_prune_durable_records()` deletes `delivery_state='delivered'` rows older than `_DURABLE_RETENTION_SECONDS` (7 days), then trims any remaining excess of *terminal* (`state NOT IN ('running','finalizing')`) rows beyond `_MAX_RETAINED_COMPLETED`, called after every dispatch persist.
- Delivery attempts: `_MAX_DELIVERY_ATTEMPTS=8` caps retries of an undeliverable completion (e.g. target session gone) so it converges to a terminal `'dropped'` state instead of replaying every restart forever; `_MAX_COMPLETION_REPLAY_AGE_S` (48h) additionally drops stale pending completions on restart-replay rather than re-injecting a week-old result as a fresh turn.
- `tools/async_delegation.py:76-90` (all constants + rationale comments), `284-303` (`_prune_durable_records`), `715-730` (`_prune_completed_locked`).

### Finding 6: A stalled (not just crashed) async delegation is force-finalized by a progress-based monitor, not a wall-clock timeout

Confidence: high

A single monitor thread samples per-dispatch progress (api-call count + current tool name) rather than elapsed wall time, because legitimate heavy subagent work must never be killed for taking long. A child with no progress for `_STALE_IDLE_SECONDS=450` (outside a tool) or `_STALE_IN_TOOL_SECONDS=1200` (inside a tool) is interrupted, given `_STALL_GRACE_SECONDS=120` to unwind through the normal finalize path, and only force-finalized with a terminal `stalled` event if it never returns — this is the mechanism that prevents a wedged background task from showing "dispatched" forever after a crash mid-call.
- `tools/async_delegation.py:93-118` (full rationale + all four constants).

### Finding 7: Cron's active/done split is a Python-side filter over one flat JSON file, not a SQL WHERE clause or a separate pending store

Confidence: high

Unlike sessions/messages/delegations (SQLite), `cron/jobs.py`'s entire store is `~/.hermes/cron/jobs.json` — a single file, no database. `list_jobs(include_disabled=False)` (the default view) is a Python list comprehension filtering `job.get("enabled", True)`; `get_due_jobs()` similarly loads the full file and filters by `next_run_at <= now`. There is no separate "pending jobs" table or file: "active" is entirely a computed view over the one durable JSON blob, mirroring the SQL-WHERE pattern in spirit (durable store + a cheap deterministic filter) but implemented as in-process list filtering, not a database query.
- `cron/jobs.py:1-6` (module docstring: "Jobs are stored in `~/.hermes/cron/jobs.json`"), `2274-2278` (`list_jobs` filter), `3409-3430` (`get_due_jobs`/`_get_due_jobs_locked`).

### Finding 8: A finished one-shot cron job is marked terminal in place, then swept by age, not deleted immediately or left enabled forever

Confidence: high

When a job's `repeat.times` limit is reached, `_mark_job_run_locked()` does NOT delete the record — it sets `enabled=False, state="completed", next_run_at=None` and persists, specifically so `last_status`/`last_error`/`last_delivery_error` stay inspectable via `cronjob list --include-disabled` instead of vanishing with no visible outcome (the comment cites this as a fix for a real prior bug). A separate sweep, `_sweep_completed_oneshots()`, later hard-deletes only `state == "completed"` **and** `schedule.kind == "once"` records whose `last_run_at` is older than `cron.completed_retention_days` (default `COMPLETED_ONESHOT_RETENTION_DAYS = 7`; a non-positive value disables the sweep and keeps them forever). Recurring jobs and non-terminal one-shots are never touched by this sweep; a record with an unparseable `last_run_at` is kept rather than guessed into deletion.
- `cron/jobs.py:2845-2862` (terminal-completion branch, in-place mark not delete), `3293-3367` (`COMPLETED_ONESHOT_RETENTION_DAYS`, `_completed_oneshot_retention_days`, `_sweep_completed_oneshots`).

### Finding 9: The general pattern across all three subsystems is "durable store + deterministic filter," but the filter mechanism differs by subsystem, not a single SQL-VIEW abstraction

Confidence: high

- Messages/sessions (SQLite): every read path (`get_messages`, `get_messages_as_conversation`, dedup lookups, `archive_and_compact` itself) explicitly appends `AND active = 1` to its query — 19+ call sites use this exact clause. This is closest to a true SQL-WHERE "active view."
- Async delegations (SQLite, separate DB): filtering is by `status`/`delivery_state` column checks in Python after a `SELECT *`-style load into `_records`, plus explicit `WHERE state NOT IN (...)` and `WHERE delivery_state=...` clauses for the durable-table sweep — a hybrid of SQL predicate and in-process dict filtering.
- Cron (flat JSON file, no DB): filtering is pure Python list comprehension over the fully-loaded file (`enabled`, `state`, `next_run_at` fields) — no SQL involved at all.
- Common thread across all three: nothing is ever silently dropped from the durable record without an explicit, named retention rule (row flip + FTS retention for messages, `_MAX_RETAINED_COMPLETED`/`_DURABLE_RETENTION_SECONDS`/`_MAX_DELIVERY_ATTEMPTS` for delegations, `COMPLETED_ONESHOT_RETENTION_DAYS` for cron) — the "active" view is always cheap and mechanical (column check, timestamp comparison, dict field), never an LLM judgment call.
- Evidence aggregated from Findings 1, 4, 7 above.

### Contradictions

- `[[RESEARCH-hermes-agent-capabilities]]` Finding 3 places `async_delegations` inside `hermes_state.py:1047-1305`'s `CREATE TABLE` block. Current `main` has no `async_delegations` table in `hermes_state.py` at all (`grep -c "async_delegations" hermes_state.py` = 0); the table is created and owned entirely by `tools/async_delegation.py:154-176` in its own SQLite file. Unresolved whether this is drift since the July 2026 research pass or an imprecise original citation — not independently reconciled against the commit hash (`42c9e59`) that research pinned.

### Gaps

- Did not trace what calls `ContextCompressor`'s per-turn threshold check (i.e., which loop/hook evaluates `current_tokens >= threshold_tokens` each turn) — confirmed the threshold math and the `trigger_source` enum, but not the exact call site inside `run_agent.py`'s turn loop.
- Did not verify whether `process_registry.completion_queue` itself has its own size bound or retention policy independent of the `async_delegations` table's caps (Finding 5 covers the table/dict side only).
- Did not trace `cron/scheduler.py::tick()`'s call cadence in this pass (already flagged as a gap in `[[RESEARCH-hermes-agent-capabilities]]` Finding 9 and Gaps) — relevant context for how promptly `get_due_jobs()`'s filtered view is re-evaluated, but out of scope for the state-bounding question itself.

## Axis: Classic open source (rs-classic-oss)

---
summary: How Taskwarrior, todo.txt-cli, org-mode, and the Linux kernel keep an "active set" free of finished items
---

# Research: classic OSS active-set hygiene patterns

Axis: which of (a) move-on-transition, (b) periodic/triggered sweep, (c) generated view (or a 4th pattern) each system uses to keep its "active" collection free of finished items, and what preserves history after removal.

### Taskwarrior - legacy file backend (pre-3.0, verified at tag v2.5.1)

### Finding 1: `task done` only flips a status field; it does not relocate the record
Pattern: none of a/b/c at the moment of completion (state change only)
Confidence: high
Evidence: `src/commands/CmdDone.cpp` (branch `develop`) - `task.setStatus(Task::completed)` then `Context::getContext().tdb2.modify(task)`. No file/vector move happens in this call.

### Finding 2: The physical move from pending to completed storage is a separate reconciling pass, decoupled from the completion command
Pattern: (b) periodic/triggered sweep
Confidence: high
Evidence: `src/TDB2.cpp:1227` `TDB2::gc()` (v2.5.1) - comment: "Scans the pending tasks for any that are completed or deleted, and if so, moves them to the completed.data file." Implementation reloads `pending.data`, and `TF2::load_gc()` (`src/TDB2.cpp` ~L330) routes each task by its `status` field into either `tdb2.pending._tasks` or `tdb2.completed._tasks` in memory; the vectors are rewritten to `pending.data`/`completed.data` on `TDB2::commit()`.

### Finding 3: `gc()` runs before command dispatch, so a task is not moved out until the NEXT command invocation, not the one that completed it
Pattern: (b), specifically "sweep-on-every-subsequent-read" rather than atomic-with-write
Confidence: high
Evidence: `src/Context.cpp:432-436` - `dispatch()` calls `tdb2.gc()` before looking up and running the command's `execute()`. `TDB2::update()` (`src/TDB2.cpp:635-706`, v2.5.1) confirms: when a task already exists, it calls `pending.modify_task(task)` (in-place line replace within `pending.data`'s in-memory vector) - it never moves the record to `completed` even though the status field is now `"completed"`. The relocation only happens on the next command's `gc()` pass. Because `gc()` runs immediately before every GC-eligible command's own logic (including `task list`), the delay is invisible to a user who runs another command afterward, but the completing command itself does not do the move.
Note: `gc` is skippable via `rc.gc:off`, in which case the move never happens automatically at all (`src/TDB2.cpp:1230` checks `context.config.getBoolean("gc")`).

### Finding 4: History is never destroyed by this process - only relocated between two flat files
Pattern: n/a (retention mechanism)
Confidence: high
Evidence: `src/TDB2.cpp:697-706` (v2.5.1) new completed/deleted tasks are appended to `completed.data`; nothing is deleted from disk by `gc()`. A separate explicit `purge` operation (`TDB2::purge`, `src/TDB2.cpp:227` on `develop`) is the only path that removes a task's data entirely.

### Taskwarrior - modern backend (2.6+/3.x, "TaskChampion"; verified at `develop`, current release 3.5.0)

### Finding 5: The pending.data/completed.data file split no longer exists; storage is a single operational-log-backed database (SQLite via the Rust "TaskChampion" replica)
Pattern: (c) generated view
Confidence: high
Evidence: `src/TDB2.h:107-108` - only `_pending_tasks` / `_completed_tasks` optional in-memory caches remain, backed by `rust::Box<tc::Replica>` (`src/TDB2.cpp` top-of-file includes, `replica()` accessor at `TDB2.cpp:~245`). Status is one attribute on the task record, set via `tctask->set_status(...)` (`TDB2.cpp` inside `modify()`).

### Finding 6: "Pending" is a live filtered query, not a stored collection
Pattern: (c) generated view
Confidence: high
Evidence: `TDB2::pending_tasks()` (`src/TDB2.cpp`, in the block calling `replica()->pending_task_data()`) queries the replica directly by status each time the cache is invalidated; `TDB2::modify()` explicitly comments: "If the task entered or left the pending set, we must invalidate the cache" and calls `invalidate_cached_info()` - i.e. completion is just a status write, and "pending" is re-derived from that status, not maintained as a separate physical list.

### Finding 7: `gc` is now a "rebuild working set" operation limited to display-ID assignment, not a data-relocation pass
Pattern: (c), with a cosmetic renumbering step
Confidence: high
Evidence: `TDB2::gc()` (`src/TDB2.cpp:272` on `develop`) body is now just `replica()->rebuild_working_set(true)` when `rc.gc` is enabled - it only reassigns the small sequential IDs users type (`task 5 done`), it does not move records between stores (there is only one store).

### Finding 8: History is preserved by design - the database keeps every task and its full operation log; a separate explicit action removes data permanently
Pattern: n/a (retention mechanism)
Confidence: medium
Evidence: `TDB2::purge()` (`src/TDB2.cpp`, calls `tctask->delete_task(ops)`) is the only path found that deletes a task from the replica; `expire_tasks()` (`replica()->expire_tasks()`) is a separate, opt-in expiry call. Not independently verified against TaskChampion's Rust source for exact expiry semantics.

### todo.txt-cli (todotxt/todo.txt-cli, `todo.sh`)

### Finding 9: `do`/`done` marks the line `x <date> ...` in place; it does not remove or move it
Pattern: (a) is NOT used at completion time by itself - completion is a pure in-place edit
Confidence: high
Evidence: `todo.sh:1268-1274` (raw `master` branch) -
```
sed -i.bak "${item}s/^(.) //" "$TODO_FILE"
sed -i.bak "${item}s|^|x $now |" "$TODO_FILE"
```

### Finding 10: `archive` is a distinct action that greps `x `-prefixed lines into `done.txt` and deletes them from `todo.txt`
Pattern: (b) periodic/triggered sweep (triggered by explicit invocation, not a timer)
Confidence: high
Evidence: `todo.sh:1183-1193` -
```
sed -i.bak -e '/./!d' "$TODO_FILE"
if grep "^x " "$TODO_FILE" >> "$DONE_FILE"; then
 sed -i.bak '/^x /d' "$TODO_FILE"
```

### Finding 11: By default `do` immediately re-invokes `archive`, fusing the two steps into one user-visible action; this is configurable
Pattern: (a)+(b) composed - looks atomic to the user, is two operations internally
Confidence: high
Evidence: `todo.sh:1297-1300` -
```
if [ "$TODOTXT_AUTO_ARCHIVE" = 1 ]; then
 "$TODO_FULL_SH" archive || status=$?
fi
```
Default is ON: `todo.sh:662` `TODOTXT_AUTO_ARCHIVE=${TODOTXT_AUTO_ARCHIVE:-1}`. CLI flags `-a`/`-A` and the `TODOTXT_AUTO_ARCHIVE` env/config var override it (`todo.sh:590,593,756-757`); with it off, `x`-lines accumulate in `todo.txt` until `archive` is run by hand.

### Finding 12: `report` also force-triggers `archive` before it computes counts, so a second code path performs the same sweep independently of `do`
Pattern: (b)
Confidence: high
Evidence: `todo.sh:1479` inside the `"report")` case: `"$TODO_FULL_SH" archive` (unconditional, no `AUTO_ARCHIVE` check), immediately followed by `sed -n '$ =' "$TODO_FILE"` / `"$DONE_FILE"` line counts.

### Finding 13: History is preserved verbatim in `done.txt` - archive only moves lines, never rewrites or drops fields
Pattern: n/a (retention mechanism)
Confidence: high
Evidence: `todo.sh:1186` `grep "^x " "$TODO_FILE" >> "$DONE_FILE"` appends full original lines unmodified.

### Emacs Org-mode

### Finding 14: Flipping a heading's keyword from TODO to DONE leaves the entry exactly where it is; nothing removes it from the file
Pattern: none of a/b/c at the moment of state change (no removal mechanism exists at all here)
Confidence: high
Evidence: Org Manual, "Archiving" - https://orgmode.org/manual/Archiving.html - frames archiving as something "you may want to" do once "a project ... is finished," implying DONE alone does not trigger it; the manual states no automatic linkage between the TODO keyword and archiving.

### Finding 15: Archiving to a separate file is a distinct, user/hook-invoked command, bound to `C-c C-x C-s` / `C-c $` (`org-archive-subtree`), target controlled by `org-archive-location`
Pattern: (b) triggered sweep (manual by default)
Confidence: high
Evidence: Org Manual, "Moving subtrees" - https://orgmode.org/manual/Moving-subtrees.html

### Finding 16: `org-archive-subtree` preserves full state as metadata when it moves the entry - source file, outline path, archiving timestamp
Pattern: n/a (retention mechanism)
Confidence: high
Evidence: Org Manual, "Moving subtrees" - archived entries "receive special properties recording context information", configured via `org-archive-save-context-info` (https://orgmode.org/manual/Moving-subtrees.html)

### Finding 17: A second, in-file-only archiving mode exists (the `ARCHIVE` tag / "internal archiving") that hides a subtree from agenda/columns without moving or copying it anywhere
Pattern: a 4th pattern - "flag + filter, same location, same file" (visibility toggle, not relocation)
Confidence: high
Evidence: Org Manual, "Internal archiving" - https://orgmode.org/manual/Internal-archiving.html - toggling the `ARCHIVE` tag "changes the headline to a shadowed face" and "hides" the subtree; archived trees are excluded from views like column view unless reconfigured.

### Finding 18: Auto-archive-on-DONE is not built in, but Org exposes the exact hook (`org-after-todo-state-change-hook`) that the community uses to build it, plus a narrower built-in hook (`org-after-todo-statistics-hook`) for cascading parent-DONE-when-children-done
Pattern: escape hatch enabling (a)-like atomic move-on-transition, opt-in via user Elisp
Confidence: medium
Evidence: community recipe pattern - `(add-hook 'org-after-todo-state-change-hook #'my/org-archive-when-done)` calling `org-archive-subtree` when `(org-entry-is-done-p)`; built-in use of the sibling hook is documented at https://orgmode.org/manual/Breaking-Down-Tasks.html (`org-after-todo-statistics-hook` + `org-summary-todo`, for parent auto-completion, not archiving). Not verified directly against Org core source for `org-after-todo-state-change-hook`'s exact definition site.

### Linux kernel

### Finding 19: The CPU run queue removes a task from itself as one atomic step of its own state transition - a task is never left "done" but still enqueued
Pattern: (a) move-on-transition
Confidence: high
Evidence: `kernel/sched/core.c:2240` (branch `master`) -
```c
void deactivate_task(struct rq *rq, struct task_struct *p, int flags)
{
	WRITE_ONCE(p->on_rq, TASK_ON_RQ_MIGRATING);
	dequeue_task(rq, p, flags);
}
```
`dequeue_task()` calls `p->sched_class->dequeue_task(rq, p, flags)` directly (same file, line above `activate_task`). There is no separate "finished" flag left set on an enqueued task; blocking/exiting and leaving the run queue are the same operation.

### Finding 20: Process exit sets a "done" flag (`EXIT_ZOMBIE`) but deliberately keeps the task's record in the process/thread-group tables - a 4th pattern distinct from a/b/c
Pattern: (d) explicit-consumer pull removal - the record is marked done, and stays until an external actor (the parent) actively reaps it, OR the kernel auto-reaps on its behalf
Confidence: high
Evidence: `kernel/exit.c:782` `exit_notify()`: `tsk->exit_state = EXIT_ZOMBIE;` runs while the task remains in `tasklist_lock`-protected lists; only if `autoreap` is true (parent ignoring SIGCHLD, `SA_NOCLDWAIT`, or an untraced sub-thread) does the same function immediately flip to `EXIT_DEAD` and call `release_task()` (`kernel/exit.c:794-796`).

### Finding 21: The actual removal function (`release_task`) is invoked either automatically (autoreap path above) or when the parent calls `wait()`/`waitpid()`, which is a pull, not a push or a scheduled sweep
Pattern: (d)
Confidence: high
Evidence: `kernel/exit.c:1206` `wait_task_zombie()` - after copying exit status/rusage back to the caller, `if (state == EXIT_DEAD) release_task(p);` (`kernel/exit.c:1312-1313`). This function is only reached via the `wait4`/`waitid` syscall path, i.e. triggered by another process's explicit consumption of the completed one.

### Finding 22: If nothing ever calls `wait()` and autoreap doesn't apply, the completed record (zombie) persists indefinitely, occupying a PID slot - the direct analogue of "done items pile up forever"
Pattern: failure mode of (d) when the consumer never runs
Confidence: high
Evidence: `kernel/exit.c:782-786` sets `EXIT_ZOMBIE` and returns without reaping unless `autoreap`; general kernel/process documentation (`man proc(5)`, zombie process behavior) - no expiry, no automatic sweep reclaims a zombie's `task_struct`/PID other than `release_task()`.

### Finding 23: Under memory pressure, the page reclaim active/inactive LRU split demotes entries via a background/triggered scan, not on any single event tied to the page's own "use" ending
Pattern: (b) periodic/triggered sweep (triggered by `kswapd` background thread or direct reclaim, not a timer, not atomic with any single access)
Confidence: high
Evidence: `mm/vmscan.c:2065` `shrink_active_list()`, comment: "shrink_active_list() moves folios from the active LRU to the inactive LRU." Called from `shrink_list()` (`mm/vmscan.c:2212-2217`), which is exercised by the reclaim path checked via `current_is_kswapd()` (`mm/vmscan.c:453` and others) - i.e. reclaim runs in `kswapd` (background thread woken under low-memory watermarks) or in direct-reclaim context, not synchronously with whatever last touched the page.

### Finding 24: Demotion to the inactive list is not deletion - content is preserved; eviction (actual removal/writeback) is a separate, later step only reached if the page stays cold
Pattern: n/a (retention mechanism)
Confidence: high
Evidence: `mm/vmscan.c:2065-2141` `shrink_active_list()` only reclassifies folios (`folio_clear_active()`, `folio_set_workingset()`) and requeues them via `move_folios_to_lru()`; it does not free page content. Referenced (recently used) folios are instead rotated back onto the active list (`mm/vmscan.c:2118-2126`).

### Additional systems (brief, as permitted "one or two more")

### Finding 25: logrotate runs as a decoupled periodic job (cron or systemd timer), never invoked by the application that writes the log
Pattern: (b) periodic sweep
Confidence: high
Evidence: `logrotate.8.in` (branch `main`) DESCRIPTION section: "Normally, logrotate is run as a daily cron job (or logrotate.timer using systemd(1))." - https://raw.githubusercontent.com/logrotate/logrotate/main/logrotate.8.in

### Finding 26: logrotate's `rotate <count>` directive bounds retention by count, discarding (or compressing then discarding) copies beyond that count each time the sweep runs
Pattern: (b), bounded-retention variant
Confidence: medium
Evidence: general `logrotate.conf(5)` `rotate` directive semantics (well-documented, standard logrotate behavior); exact current man-page wording for this directive was not independently re-extracted from source in this pass (build macros in `logrotate.conf.5` resolved to a `.so` redirect to `logrotate.8.in`, not a distinct rotate-count section).

### Finding 27: git's reflog + `gc` combine a sweep with an explicit retention window rather than deleting anything reachable
Pattern: (b) periodic/triggered sweep with a time-based retention window
Confidence: high
Evidence: `git-reflog(1)` / `git-gc(1)` - `gc.reflogExpire` defaults to 90 days for reflog entries reachable from the branch tip, `gc.reflogExpireUnreachable` defaults to 30 days for entries no longer reachable (e.g. after `commit --amend`/`rebase`); `git gc --auto` invokes reflog expiry as part of its pass, and `git gc` additionally will not prune any object still referenced by a branch, tag, the index, a remote-tracking ref, or a reflog entry, nor an unreachable object younger than its own two-week default safety grace period. https://git-scm.com/docs/git-reflog https://git-scm.com/docs/git-gc

### Contradictions
- None found across systems for the same claim; the "generated view" (c) pattern in modern Taskwarrior directly contradicts what the file-based (pending.data/completed.data) design of legacy Taskwarrior implies about the project's own history - this is an intentional architecture change across major versions (2.x -> 2.6+/3.x TaskChampion), not an inconsistency in the evidence.

### Gaps
- TaskChampion's Rust source (not fetched; only the C++ `TDB2.cpp`/`TDB2.h` bridge in the `taskwarrior` repo was inspected) was not independently checked for its own expiry/compaction semantics (`expire_tasks()`, operational-log compaction). Would need `GothenburgBitFactory/taskchampion` source.
- `org-after-todo-state-change-hook`'s exact definition and firing guarantees were not verified against Org core Lisp source (`org.el`); current understanding is from community recipes and adjacent manual pages, not the hook's own docstring.
- logrotate's exact `rotate` directive wording was not extracted (man page macro redirection); the count-based retention behavior stated is standard/well-known but not re-quoted from primary source in this pass.
- Kanban Done-column WIP-limit conventions and systemd's dead/failed-unit handling were not researched (explicitly optional in the brief; skipped for time).
