---
title: "Hermes automatic skill creation: trigger, drafting, storage, dedup, loading, retirement"
type: research
status: complete
confidence: high
area: architecture
tags: [hermes-agent, skills, learning-loop, background-review, curator, write-approval, skill-creation]
summary: "How Hermes (commit a212421d, 2026-11-04) triggers, drafts, writes, dedups, indexes and retires skills; what changed since the 0.19.0 research; where a review hook already exists"
created: 2026-11-04
updated: 2026-11-04
git_branch: "master"
git_commit: "e331edd"
author: "researcher agent"
depends_on: ["[[SPEC-012-learning-loop]]", "[[SPEC-002-lessons-and-index-subsystem]]", "[[SPEC-029-human-verdicts-reach-compass]]", "[[RESEARCH-hermes-memory-mechanics]]", "[[RESEARCH-hermes-vs-compass-fit]]", "[[RESEARCH-hermes-agent-capabilities]]"]
---

# Hermes automatic skill creation

## Question

How does Hermes decide to create a skill automatically, from what evidence, and how is a skill written, updated, merged and retired over time (trigger, drafting call, file format and storage, dedup, session loading, retirement)?

## Methodology

Repository mining of the hermes-agent source at commit a212421d (2026-11-04): code read directly, no documentation relied on for behavior. Fits because the question is how an existing system behaves. Prior Compass findings (version 0.19.0, July 2026) are not repeated; each finding is marked NEW, CHANGED or CONFIRMED against them. No grading disclosure reached this run, so findings are marked and ungraded. Every finding: evidence type is source code (first-party repository, owner NousResearch), no retraction or preprint status applies, no citation count applies, convergence is the number of independent code sites that agree.

## Findings

### A. Trigger

1. **Two paths create skills: an automatic post-turn review fork and the user-invoked `/learn` turn** (confidence: high; NEW for `/learn`)
   - Automatic: a forked agent reviews the finished turn (`agent/background_review.py:1-7`).
   - Manual: `/learn [description]` builds one prompt and runs it as a normal foreground turn (`agent/learn_prompt.py:1-7`, `136-197`).
   - An empty `/learn` means "the workflow we just went through" (`agent/learn_prompt.py:140-143`).
   - Marks: source code, owner checked; 2 sites agree.

2. **The skill trigger counts tool-calling iterations, default 10, and resets on any `skill_manage` call** (confidence: high; CONFIRMED, one detail NEW)
   - `_iters_since_skill` increments once per tool-loop iteration, only when `skill_manage` is a valid tool (`agent/turn_iteration_prep.py:166-167`).
   - Config key `skills.creation_nudge_interval`, default 10 (`agent/agent_init.py:1286-1288`); 0 disables.
   - Checked once after the turn ends: `interval > 0 and counter >= interval and skill_manage valid` fires and zeroes the counter (`agent/turn_finalizer.py:863-869`).
   - NEW: the counter also resets the moment the main agent itself calls `skill_manage`, before the tool executes (`agent/tool_executor.py:737-739`), so a session where the model writes skills itself delays the next review.
   - Marks: source code, owner checked; 3 sites agree.

3. **The memory trigger counts user turns, default 10, and shares the same spawn call** (confidence: high; CONFIRMED)
   - `memory.nudge_interval` default 10 (`hermes_cli/config_defaults.py:1309`, `agent/agent_init.py:1215,1244`).
   - Counter is re-derived on resume as `prior_user_turns % interval` (`agent/turn_context.py:761-762`).
   - Either or both flags select one of three prompts: combined, memory-only, skill-only (`agent/background_review.py:1332-1335`).
   - Marks: source code, owner checked; 3 sites agree.

4. **The fork spawns only after a delivered, uninterrupted reply, and is skipped in several contexts** (confidence: high; NEW detail)
   - Requires a `final_response`, not interrupted, `skip_background_review` unset, and a vetoed prompt excluded (`agent/turn_finalizer.py:562-583`).
   - Disabled for one-shot finite turns and safe-worker mode (`agent/background_review.py:237-238`); skipped inside a delegated subagent (`run_agent.py:763-764`).
   - Cron agents skip it (comment at `agent/turn_finalizer.py:572-575` cites ~30K tokens per fork).
   - Master switch `auxiliary.background_review.enabled`, default true, fail-open on a broken config (`agent/background_review.py:228-250`, `hermes_cli/config_defaults.py:798`).
   - Marks: source code, owner checked; 4 sites agree.

5. **Reviews run as a daemon thread, one at a time, and a live user turn cancels the running review** (confidence: high; NEW)
   - A second review is refused while one is in flight (`agent/background_review.py:75-89`).
   - A new live turn or session teardown cancels it with a 2.0 s acknowledgement wait, then proceeds regardless (`agent/background_review.py:25`, `129-170`).
   - On the managed local llama-server runtime, reviews queue until idle (15 s quiet window, 30 min max age, newest snapshot wins per session) (`agent/review_idle_queue.py:25-31`, `82-99`); a preempted deferred review requeues at most 3 times (`run_agent.py:831-846`).
   - Marks: source code, owner checked; 3 sites agree.

6. **`/refine [focus]` is a user-triggered review of the same fork, bypassing the enabled and idle gates** (confidence: high; NEW)
   - `explicit=True` bypasses `enabled: false` and idle-defer (`run_agent.py:752-762`), and appends the user's focus text under "prioritize it over the general instructions" (`agent/background_review.py:1355-1359`).
   - Entry points: `hermes_cli/cli_commands_mixin.py:1664-1674`, `gateway/session_refine.py:73-87`.
   - Marks: source code, owner checked; 3 sites agree.

### B. Evidence and drafting

7. **The evidence is the whole finished conversation, replayed to a forked agent; no prefilter, no summarizer** (confidence: high; CONFIRMED, mechanism detail NEW)
   - Same model as the parent (default): full message snapshot replayed as warm cache reads (`agent/background_review.py:1213-1221`).
   - Routed to a different model via `auxiliary.background_review.{provider,model}`: last 24 messages verbatim plus one synthetic digest of older turns (user text clipped to 300 chars, assistant text to 200) (`agent/background_review.py:332-362`).
   - Bounds: `_REVIEW_MAX_ITERATIONS = 16`; input-token budget 75% of the fork's context window, capped at 600,000, fallback 120,000 (`agent/background_review.py:173-182`).
   - Marks: source code, owner checked; 2 sites agree.

8. **The drafting call is one agent loop whose first user message is the review prompt; the model writes SKILL.md itself through `skill_manage`** (confidence: high; CONFIRMED)
   - The prompt is followed by "You can only call skill management tools. Other tools will be denied at runtime" (`agent/background_review.py:1214-1219`).
   - Dispatch-side whitelist: the `skills` toolset plus `read_file` and `search_files`; the `memory` toolset only when the memory counter fired (`agent/background_review.py:1102-1117`). The advertised tool list stays identical to the parent's so the prompt cache holds.
   - No separate "draft then judge" stage exists: the model drafts and commits in the same loop.
   - Marks: source code, owner checked; 3 sites agree.

9. **The skill-review prompt biases toward acting and defines a four-step preference order** (confidence: high; CONFIRMED, text NEW for this version)
   - Opening: "Be ACTIVE - most sessions produce at least one skill update, even if small. A pass that does nothing is a missed learning opportunity" (`agent/background_review.py:456-459`).
   - Closing: "'Nothing to save.' is a real option but should NOT be the default" (`agent/background_review.py:524-526`).
   - Signals (any one warrants action): user corrected style or format, user corrected workflow, non-trivial technique emerged, a loaded skill turned out wrong (`agent/background_review.py:464-475`).
   - Preference order: (1) patch a currently loaded skill, (2) patch an existing umbrella, (3) add a `references/`, `templates/` or `scripts/` file under an umbrella, (4) create a new class-level umbrella; a name that only fits today's task "is wrong" (`agent/background_review.py:476-507`).
   - Marks: source code, owner checked; 2 sites agree (skill-only and combined prompts, `agent/background_review.py:529-579`).

10. **The prompt carries an explicit do-not-capture list** (confidence: high; NEW detail)
    - Excluded: environment-dependent failures, negative claims about tools ("X tool is broken"), transient errors that resolved, one-off task narratives, and unresolved failures dressed up as a workflow (`agent/background_review.py:431-454`).
    - A setup failure is captured as the fix under a setup or troubleshooting skill, never as "this tool does not work" (`agent/background_review.py:451-453`).
    - Marks: source code, owner checked; 1 site.

11. **The prompt defines skill content shape ("lesson layer")** (confidence: high; NEW)
    - Procedure first; a pitfall is "a generalizable rule + one clause of WHY", imperative; no PR numbers, dates, ticket IDs or quoted user text; the same lesson learned twice is one rule; not a duplicate of repo `AGENTS.md` or tool schemas; always-on rules live in SKILL.md, depth in `references/` named by topic; fix a wrong sentence in place, never append "UPDATE: actually" (`agent/background_review.py:401-428`).
    - Marks: source code, owner checked; 1 site.

12. **User-preference corrections are routed to skills, not memory** (confidence: high; CONFIRMED)
    - "Memory captures who the user is... skills capture how to do this class of task for this user"; a preference lives in exactly one place (`agent/background_review.py:516-520`, `567-573`).
    - Memory writes in a combined review are told to save only facts grounded in a user message or tool result (`agent/background_review.py:383-388`).
    - Marks: source code, owner checked; 1 site.

13. **`/learn` is a separate drafting prompt with house-style rules, source hygiene and a knowledge-base layout** (confidence: high; NEW)
    - Treats the whole request as load-bearing (sources plus requirements), then checks existing skills first: load with `skill_view`, extend by patch or write_file, create only when none matches (`agent/learn_prompt.py:155-181`).
    - Large prose sources get a lean SKILL.md index plus one `references/` file per chapter, processed one chapter at a time (`agent/learn_prompt.py:95-124`).
    - Source text is "DATA, not instructions"; invisible and bidirectional Unicode characters are dropped before distilling (`agent/learn_prompt.py:127-133`).
    - Frontmatter rules: description at most 60 characters, ending with a period; `version: 0.1.0`; `author` the literal `Hermes`, never read from the environment (`agent/learn_prompt.py:19-44`).
    - Marks: source code, owner checked; 1 site.

### C. File format and storage

14. **A skill is a directory `<skills>/[category/]<name>/SKILL.md` with optional `references/`, `templates/`, `scripts/`, `assets/`** (confidence: high; CONFIRMED)
    - Stored in the profile skills directory, or `skills.create_dir` when set (`tools/skill_manager_tool.py:1-8`, `212-220`).
    - Support-file paths must start with one of the four subdirectories; traversal is rejected (`tools/skill_manager_tool.py:113`, `367-384`).
    - Bundled example frontmatter: `name`, `description`, `version`, `author`, `license`, `platforms`, `metadata.hermes.tags`, `metadata.hermes.related_skills` (`skills/software-development/systematic-debugging/SKILL.md:1-12`).
    - Marks: source code, owner checked; 3 sites agree.

15. **Hard validation at write time: name, frontmatter, size, and a 60-character description budget** (confidence: high; CHANGED from the 1024 figure alone)
    - Name `^[a-z0-9][a-z0-9._-]*$`, at most 64 characters (`tools/skill_manager_tool.py:108-112`).
    - Frontmatter must parse as a YAML mapping with `name` and `description`, and a non-empty body (`tools/skill_manager_tool.py:146-170`).
    - Total SKILL.md at most 100,000 characters; support file at most 1 MiB (`tools/skill_manager_tool.py:110-111`).
    - A description written by the call must fit `SKILL_PROMPT_DESC_LIMIT = 60` (the skill-index width), or the write is refused; an unchanged legacy over-limit description stays editable (`tools/skill_manager_tool.py:173-184`, `agent/skill_utils.py:846`).
    - Marks: source code, owner checked; 3 sites agree.

16. **An advisory linter attaches findings to the tool result, never blocking** (confidence: high; NEW)
    - Rules include marketing words in the description, shell utilities named instead of Hermes tools, missing "When to Use" section, body over a 24,000-character soft budget, incident-log shape (4 or more PR/issue references at 0.5 per 1,000 characters), more than 60 reference files, POSIX-only primitives in scripts (`tools/skill_linter.py:44-56`, `84-195`).
    - On patch only findings the patch introduced are reported (`tools/skill_manager_tool.py:441-459`); the tool text says "advisory authoring-convention findings (not blockers)".
    - Marks: source code, owner checked; 2 sites agree.

17. **`skill_manage` is one tool with six actions, applied as an atomic operations array** (confidence: high; CONFIRMED, shape NEW)
    - Actions: create, patch (targeted `old_string`/`new_string`, preferred; or full-content rewrite as last resort), write_file, remove_file, delete (`tools/skill_manager_tool.py:737-743`, `837-853`).
    - Patch uses the same fuzzy matcher as the file patch tool; a patch that breaks frontmatter is rejected (`tools/skill_manager_tool.py:551-561`).
    - Writes are atomic, take a per-skill cross-process lock, and a failed post-write security scan restores the original (`tools/skill_manager_tool.py:407-429`, `811`).
    - The optional security scan of agent-written skills is off by default (`skills.guard_agent_created: false`) (`hermes_cli/config_defaults.py:1465`).
    - Marks: source code, owner checked; 2 sites agree.

### D. Dedup and merge

18. **Create-time dedup is name-only; semantic dedup is delegated to the prompt and the curator** (confidence: high; CONFIRMED)
    - `create` refuses only an existing name, resolved by directory name, category path, or frontmatter name (`tools/skill_manager_tool.py:252-305`, `472-473`).
    - No content-similarity check exists in the write path. The prompt tells the model to run `skills_list` and `skill_view` first and to search the skill for an existing rule before adding one (`agent/background_review.py:415-417`, `486-488`).
    - Overlapping skills noticed during review are "noted in your reply"; "Never delete a skill here" (`agent/background_review.py:522`).
    - Marks: source code, owner checked; 3 sites agree.

19. **Read-before-write is enforced in code for the review fork** (confidence: high; NEW)
    - Patching SKILL.md or overwriting a support file is refused unless `skill_view` or `read_file` loaded that exact file in this review; transcript quotes do not count (`tools/skill_manager_guards.py:55-73`, `211-221`).
    - A fresh read-mark set is created per review (`agent/background_review.py:1207-1210`).
    - Context: `read_file` and `search_files` were whitelisted after a denial storm of roughly 142 denials and 204 read-before-write refusals on one deployment (`agent/background_review.py:1114-1129`).
    - Marks: source code, owner checked; 3 sites agree.

20. **Merging is done by the curator, as an opt-in LLM pass, with a verified forwarding target** (confidence: high; CHANGED default)
    - `curator.consolidate` default is false: the default curator pass is deterministic prune only (`agent/curator.py:33-35`, `146-148`; `hermes_cli/config_defaults.py:1493`).
    - The consolidation prompt asks for umbrella-building: prefix clusters, three methods (merge into existing umbrella, create new umbrella, demote to references/templates/scripts), and "If you end the pass with fewer than 10 archives, you stopped too early" (`agent/curator.py:292-448`).
    - Archive during consolidation requires `absorbed_into=<umbrella>` naming an existing skill; a bare delete is refused (`tools/skill_manager_tool.py:577-591`, `tools/skill_manager_guards.py:266-286`).
    - The pass ends with a required structured YAML block of `consolidations` and `prunings`, cross-checked against actual tool calls (`agent/curator.py:449-469`, `546-650`).
    - Candidate input to the fork is a list of local curator-managed skills only (`agent/curator.py:896`).
    - Marks: source code, owner checked; 3 sites agree.

### E. Provenance and ownership

21. **Three `created_by` values separate agent, user-taught and installed skills** (confidence: high; CHANGED: `learn` is NEW)
    - `agent`: created from the background review fork. `learn`: created in a foreground turn, e.g. `/learn`. `installed`: hub install (`tools/skill_usage.py:522-543`).
    - Only `agent` (or `agent_created: true`) makes a skill curator-managed; `learn` skills are visible in the journey graph but not handed to autonomous curation (`tools/skill_usage.py:290-296`, `528-531`).
    - `hermes curator adopt <name>` flips a skill into curator management on the user's declaration (`tools/skill_usage.py:321-345`).
    - Marks: source code, owner checked; 3 sites agree.

22. **The fork may patch any skill, but may archive only curator-managed ones** (confidence: high; CONFIRMED, wording NEW)
    - "Content writes are not gated by ownership: the review fork exists to improve every skill it learns from, and every write is ledgered and reversible, while an archive removes a skill the user relies on" (`tools/skill_manager_guards.py:164-168`).
    - Refused deletes: pinned, external-dir, protected built-in, hub-installed, bundled, or not curator-managed (`tools/skill_manager_guards.py:170-209`).
    - A user lock (`hermes curator lock`) refuses every mutating action from every actor, failing closed for autonomous passes when the lock state is unreadable (`tools/skill_manager_guards.py:224-252`).
    - Marks: source code, owner checked; 2 sites agree.

### F. Human review, audit and rollback

23. **A per-subsystem approval gate stages every skill write instead of committing it; default off** (confidence: high; CONFIRMED, mechanics NEW)
    - `skills.write_approval` default false (`hermes_cli/config_defaults.py:1469`).
    - When true, a skill write always stages, from either origin, because "skills are too big to review inline" (`tools/write_approval.py:201-213`; `tools/skill_manager_tool.py:795-801`).
    - Staged record: `<home>/pending/skills/<8-hex-id>.json` holding `id`, `action`, `summary`, `origin`, `created_at` and the exact replay `payload` (`tools/write_approval.py:74-90`).
    - Review verbs: `/skills pending`, `/skills diff <id>`, `/skills approve|reject <id>` (`hermes_cli/config_defaults.py:1466-1468`).
    - Approval replays the payload with the gate bypassed (`tools/skill_manager_tool.py:716-722`).
    - Marks: source code, owner checked; 3 sites agree.

24. **The staged-write preview is a unified diff computed through the same matcher approval will run** (confidence: high; NEW)
    - Create shows full content; edit, patch, write_file show `difflib.unified_diff` against the on-disk file, with earlier ops of a batch folded in (`tools/write_approval.py:305-345`, `395-411`).
    - A patch that approval would reject renders as "(patch would fail: ...)" rather than a fabricated result (`tools/write_approval.py:347-366`).
    - The one-line gist is heuristic, no model call: create uses the frontmatter description and size, patch uses +/- line counts (`tools/write_approval.py:257-269`).
    - Marks: source code, owner checked; 1 site.

25. **Unreviewable by default: with the gate off the user sees only a one-line action summary after the fact** (confidence: high; CONFIRMED)
    - The fork's tool messages are scanned for successful actions and a joined summary is printed or passed to a callback; nothing is published when no action succeeded (`agent/background_review.py:1298-1312`, `1239-1244`).
    - The review-end log classifies the result from the action list (`agent/background_review.py:812-837`).
    - Marks: source code, owner checked; 2 sites agree.

26. **Every skill mutation by any actor is appended to a ledger with before/after content-addressed blobs, enabling single-entry rollback** (confidence: high; NEW)
    - `~/.hermes/skills/.curator_ledger.jsonl`; blobs under a backups directory, sha256-deduplicated; default on, capped at 5 MiB (`tools/skill_ledger.py:1-12`; `hermes_cli/config_defaults.py:1471-1478`).
    - Ledger is "telemetry, not a gate"; only rollback fails closed (`tools/skill_ledger.py:6-8`).
    - Pre-consolidation whole-library tarball snapshot, keep 2 (`hermes_cli/config_defaults.py:1505-1508`, `agent/curator.py:937-947`).
    - Marks: source code, owner checked; 2 sites agree.

### G. Loading into later sessions

27. **Discovery is a prompt index of name plus a description clipped to 60 characters, grouped by category, with a mandatory-load instruction** (confidence: high; CONFIRMED, limit CHANGED)
    - Block header "## Skills ... you MUST load it with skill_view(name) ... Err on the side of loading", then `<available_skills>` rows `- name: description` (`agent/prompt_builder.py:1327-1360`).
    - Categories outside the current coding posture collapse to a names-only line; "NEVER drop entries" (`agent/prompt_builder.py:1296-1299`).
    - Only the index is in the prompt; a skill body loads on demand through `skill_view(name)` or `/skill-name` (`agent/skill_commands.py:418-430`).
    - The always-on system hint is one sentence: "When you work out a non-trivial workflow, record it with skill_manage for future reuse" (`agent/prompt_builder.py:261`, `agent/system_prompt.py:295`).
    - Marks: source code, owner checked; 3 sites agree.

28. **Mid-session skill changes reach the model as a per-turn note, not a prompt rebuild** (confidence: high; NEW)
    - Each turn the index the prompt carries is compared with the index the session would build now; the difference is delivered on the per-turn user-message note channel, behind the cached prefix (`agent/skills_index_delta.py:1-17`).
    - Note format: "[System: The skills available in this conversation changed after its system prompt was built. Now available (load with skill_view(name) when relevant...): - name: desc ... No longer available: ...]" (`agent/skills_index_delta.py:30-33`, `66-76`).
    - A note is sent only when the difference changes; a new note states the full difference against the prompt and supersedes earlier ones (`agent/skills_index_delta.py:136-145`).
    - Skills with a new `skill_manage` write also clear the prompt-builder skills cache (`tools/skill_manager_tool.py:760-762` (also `_record_success`, line 746)), and the manifest of skill files is part of the cache key so another process's change is seen (`agent/prompt_builder.py:1375-1380`).
    - Marks: source code, owner checked; 3 sites agree.

29. **A config list pins named skills as fully loaded in every new session** (confidence: high; NEW)
    - `skills.auto_load: []`, resolved once per agent lifecycle; skipped for forks and subagents (`hermes_cli/config_defaults.py:1445-1448`, `agent/system_prompt.py:317-344`).
    - Marks: source code, owner checked; 2 sites agree.

30. **Use is counted when a skill is loaded by `/skill-name` or `skill_view`; a repeat identical view returns a stub** (confidence: high; NEW)
    - `bump_use` on slash-command load (`agent/skill_commands.py:418-430`) and on `skill_view` (`tools/skills_tool.py:776-781`); also on cron skill load (`cron/scheduler_prompt.py:248`).
    - A byte-identical repeat view returns a short stub; the review fork is exempt so its read-mark is always registered (`tools/skills_tool.py:760-775`, `tools/skills_tool_dedup.py:1-10`).
    - Marks: source code, owner checked; 3 sites agree.

### H. Retirement

31. **Retirement is two-stage and date-driven: stale after 14 unused days, archived after 30; both defaults changed** (confidence: high; CHANGED from 30 and 90 days)
    - `DEFAULT_STALE_AFTER_DAYS, DEFAULT_ARCHIVE_AFTER_DAYS = 14, 30` (`agent/curator.py:32`; `hermes_cli/config_defaults.py:1489-1490`). The July research recorded 30 and 90.
    - Anchor: latest of last-used, last-viewed, last-patched, else `created_at`; a never-used skill younger than the stale cutoff is neither staled nor archived (`agent/curator.py:245-255`; `tools/skill_usage.py:123-127`).
    - Reactivation: a stale skill used again returns to active (`agent/curator.py:261-262`).
    - Exempt: pinned, locked, or referenced by any cron job (`agent/curator.py:218-232`).
    - First observation seeds the clock and defers; a fresh install never mutates on its first tick (`agent/curator.py:160-176`, `234-237`).
    - Marks: source code, owner checked; 3 sites agree.

32. **The scheduler: weekly interval, gateway poll, cross-process claim; default curator interval is 7 days** (confidence: high; CONFIRMED)
    - `interval_hours` 168, `min_idle_hours` 2 (`agent/curator.py:31`); the gateway poll passes infinite idle (`gateway/run.py:4352-4354`).
    - An exclusive-create claim file lets one process run a pass; a claim older than 3,600 s is taken over (`agent/curator.py:1164-1195`).
    - Archive moves the directory to `.archive/` (timestamp suffix on collision); restore returns it; nothing is hard-deleted by the curator, and purge of old archives needs `archive_ttl_days > 0` and an explicit command (`tools/skill_usage.py:642-696`; `hermes_cli/config_defaults.py:1499-1501`).
    - Marks: source code, owner checked; 3 sites agree.

33. **Retirement from a foreground session is a hard delete; from the background it archives** (confidence: high; CONFIRMED)
    - `_delete_skill` archives when the writer is a background review or curator; a foreground delete runs `shutil.rmtree` (`tools/skill_manager_tool.py:595-611`).
    - Marks: source code, owner checked; 1 site.

34. **Journey graph lets the user edit or delete learned skills and memory entries from a UI** (confidence: medium; CONFIRMED, not traced past the module headers)
    - Graph nodes: non-base skills that are agent-created or used, plus memory chunks (`agent/learning_graph.py:1-8`); node deletion of a skill archives it (`agent/learning_mutations.py:1-12`).
    - Marks: source code, owner checked; 2 sites agree.
    - Caveat: only module headers and data classes read; the edit path was not traced.

### I. Safety and cost of the loop

35. **The fork cannot spawn further reviews, has no terminal, and shares the parent's session id** (confidence: high; NEW)
    - Nudge intervals are zeroed in the fork (`agent/background_review.py:1009`); the curator fork does the same and has `enabled_toolsets=["skills"]`, no `terminal`, so every mutation passes through the ledgered tool (`agent/curator.py:1114-1125`).
    - Approval callback for the fork auto-denies commands (`agent/background_review.py:1065-1070`, `1262`).
    - Fork usage is attributed to the parent session (`agent/background_review.py:787-810`).
    - Marks: source code, owner checked; 3 sites agree.

36. **Cost is stated in code comments as roughly 30K tokens per fork** (confidence: medium)
    - Comments cite ~30K tokens per event (`agent/turn_finalizer.py:572-575`, `agent/background_review.py:234-236`). No measured fire-rate or write-rate counters were found in the read files.
    - Marks: source code, owner checked; 2 sites agree.
    - Caveat: figure is a code comment, not a measurement.

## Trace: one automatic skill from trigger to later session

- Turn N ends with `_iters_since_skill >= 10` and a delivered reply (`agent/turn_finalizer.py:863-869`).
- `_spawn_background_review` clones the message list, checks enabled and defer gates, starts a daemon thread (`run_agent.py:752-806`).
- The fork replays the conversation, reads the skill review prompt, loads candidates with `skills_list` and `skill_view` (`agent/background_review.py:1213-1221`, `456-527`).
- The fork calls `skill_manage` (patch preferred, create last); guards run: lock, read-before-write, description budget, frontmatter, size (`tools/skill_manager_tool.py:793-832`).
- If `skills.write_approval` is on, the write stages under `pending/skills/<id>.json`; otherwise it lands atomically and is ledgered (`tools/skill_manager_tool.py:795-801`, `746-780`).
- On create from the fork, `created_by: "agent"` is recorded; the skills cache clears (`tools/skill_manager_tool.py:760-777`).
- The user sees a one-line summary (`agent/background_review.py:1239-1244`).
- Same or other sessions: the index delta note announces the new skill; later sessions list it in `<available_skills>` (`agent/skills_index_delta.py`; `agent/prompt_builder.py:1327`).
- Each load bumps `use_count` and `last_used_at`; weekly the curator marks stale at 14 days and archives at 30 days of no activity (`tools/skills_tool.py:776-781`; `agent/curator.py:209-263`).

## Contradictions

- The July research recorded curator defaults of 30 and 90 days (stale and archive); the code at this commit has 14 and 30 (`agent/curator.py:32`). Treated as a version change, not an error in either.
- The July research recorded description cap 60 as a reviewer-run regex check; the code now enforces it at write time through `SKILL_PROMPT_DESC_LIMIT` (`tools/skill_manager_tool.py:173-184`), while the 1024-character cap (`tools/skill_manager_tool.py:109`) still guards frontmatter validity. Both limits coexist.
- Curator prompt text says the skill index "shows 60 chars of a description" (`agent/curator.py:300-302`), consistent with the code limit; the `/learn` prompt describes the same 60 limit as "the most-violated rule" (`agent/learn_prompt.py:24-28`).

## Gaps

- Fire rate versus actual-write rate of the review fork is not measured in the files read; `hermes_cli/observability/shared_metrics_loop.py` records curator runs (`agent/curator.py:1007-1019`), and whether it records review-fork outcomes was not traced.
- `agent/learning_graph_render.py` and the desktop approve/diff surfaces for `/skills pending` were not read; the review UI shape beyond the diff text in `tools/write_approval.py` is not described here.
- `tools/skill_manager_batch.py` (atomic batch semantics and rollback) was not read in full; the atomic-rollback claim rests on the tool description (`tools/skill_manager_tool.py:837-847`).
- Commit history of these defaults was not queried (shallow clone); the 14 and 30 day change date is unknown.
- Hub, bundled-skill sync and `skills_guard` scanning (`tools/skills_hub*.py`, `tools/skills_sync.py`, `tools/skills_guard.py`) were out of this axis and not read.

## Facts a planner may need for Compass (documented, not recommended)

- A staged-write store with replayable payload, one-line gist and unified-diff preview already exists in Hermes (`tools/write_approval.py`); its review surface is slash commands, not an editor.
- Hermes separates three decisions that Compass specs treat together: when to review (counter), what to write (model, prompt-guided), whether it lands (gate, default off).
- Hermes's create-time dedup is by name only; semantic dedup relies on prompt order plus a later opt-in LLM pass (findings 18, 20).
- Compass-side related behavior: capture is harness-owned with a dedup and 5-line cap in `lesson-write` ([[SPEC-012-learning-loop]], [[SPEC-002-lessons-and-index-subsystem]]); human verdicts return through [[SPEC-029-human-verdicts-reach-compass]].
