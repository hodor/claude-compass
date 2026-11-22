---
title: "The session-start prefix: what the host puts before the first turn, where the cache breaks, and which Compass parts churn"
type: research
status: complete
confidence: medium
area: tooling
tags: [research, prompt-caching, session-start, git-status, rules, claude-code, measurement]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
summary: "Host order and cache breakpoints at session start, git-status snapshot (user-turn reminder, removable by includeGitInstructions:false), path-scoped rule loading, and where Compass churn lands; first-request cache reads in local transcripts show only the tools+system prefix is reused across sessions"
depends_on: ["[[SPEC-033-prompt-cache-is-a-design-input]]", "[[research/llm-research/REVIEW-llm-research-for-compass]]"]
---

# The session-start prefix

From [[SPEC-033-prompt-cache-is-a-design-input]]. Reuses [[research/llm-research/REVIEW-llm-research-for-compass]] items A1, C2, Disagreement 2 and [[research/llm-research/RESEARCH-axis-2b-host-features-gap]] (B2, B3, B5, C7); those are not redone, only closed where they left gaps. Host observed: Claude Code 2.1.330 (local transcripts). Docs read 2026-11-21.

## Question
What does Claude Code put in front of the first user turn and in what order, where do the cache breakpoints fall, which of those parts does a Compass install change between sessions, and which host settings stabilize or drop each part.

## Methodology
Repository mining of one artifact class (the host's own request records in local transcripts) plus feature analysis of vendor documentation and Compass code, as the chooser routes "how does an existing system actually behave". Documents were fetched as the raw `.md` of each docs page, so settings text is quoted from source, not summarized.

Marks on every finding: not retracted; not a preprint; citation count n/a (vendor docs, local code, local transcripts). Grade key: vendor-doc = asserted by Anthropic docs, not measured by the vendor; local-record = read from the host's own request log on this machine (measured, one user, one project, host 2.1.330); local-code = read in this repo. Grading allowed by the brief. No project names, paths or prompt text are given; transcript results are aggregates.

## Findings

### A. What the host sends, in order

1. **The request is three layers: system prompt with tool definitions, project context, conversation.** (confidence: high)
   Order of stability: system prompt and tools (change when the loaded tool-definition set changes), project context = CLAUDE.md, auto memory, unscoped rules (change at session start, `/clear`, `/compact`), then the conversation. A change in a layer recomputes every layer after it. Nothing in the doc places the git snapshot in the layer table.
   - https://code.claude.com/docs/en/prompt-caching ("How the cache is organized")
   - Marks: vendor-doc; not retracted; not preprint; n/a; converges with the transcript record (finding 2)
   - Grade: high for the stated order (asserted, matches measurement)

2. **In the recorded request, project context and the git snapshot are user-turn `<system-reminder>` text blocks, not system-prompt text.** (confidence: high)
   First request of a recorded session: `system` has two small blocks (about 62 and 6,800 characters) plus 17 tool definitions (about 63,000 characters of JSON); `messages[0]` is a user message of four text blocks: block 0 = every instruction file (user CLAUDE.md, project CLAUDE.md, rule files, auto-memory index; about 30,000 characters in this project), block 1 = a second reminder holding user email and the git status snapshot (about 3,400 characters), block 2 = attribution reminder, block 3 = the user's prompt. Deferred-tool, agent-listing, skill-listing and MCP-instruction pieces are separate attachment records, not in these blocks.
   - Local transcript: attachment types `instructions` and `session_context` (key `gitStatus`) and the `api-request` / `api-request-blob` records, session first request
   - Marks: local-record, one project, host 2.1.330; single source for the exact block order
   - Grade: high (read directly; n of requests inspected small, structure identical across the ones sampled)

3. **Cache breakpoints in that request sit on both system blocks and on the last user block; none sits between the instruction block and the git block.** (confidence: high)
   `cacheControl` paths: `system[0]`, `system[1]`, and `messages[1].content[3]` (the last block, the user's prompt), all TTL `1h` on this subscription. So the system-plus-tools prefix is one cacheable unit, and the user-turn prefix is cached only as far as the final block, which includes the prompt text.
   - Local transcript: `cacheControl` field of the `api-request` record
   - Marks: local-record, n=1 request inspected closely; single source
   - Grade: medium (one request; the host docs do not publish breakpoint placement)

4. **The conversation also receives a `Date`/working-directory/platform announcement and the main conversation's cache scope is machine and directory.** (confidence: high)
   The system prompt embeds auto-memory paths; the conversation opens with working directory, platform, shell, OS. Parallel sessions in one directory can read each other's cache; sequential sessions share the prefix only when the startup git snapshot matches.
   - https://code.claude.com/docs/en/prompt-caching ("Cache scope")
   - Marks: vendor-doc; converges with finding 6
   - Grade: high (asserted)

### B. Open item (a): the git-status snapshot

5. **The snapshot holds branch, main branch, `git status` output and recent commits, is read once when the conversation starts, and has a documented off switch.** (confidence: high)
   `includeGitInstructions: false` (any settings file) leaves out both the built-in commit/PR instructions (in the Bash tool description) and the snapshot; env `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` overrides the key for one session. Default true; cloud sessions never carry the snapshot. In `-p` it is also absent when `--system-prompt`, `--system-prompt-file` or a custom `--agent` replaces the prompt. A subagent gets its own snapshot at start (the worktree's, for a worktree agent), except Explore and Plan; "You can't change which subagents receive git status" except through the same key. After compaction a fresh snapshot is read if the session started with one. This closes the gap in axis 2b B3 (full entry was unread).
   - https://code.claude.com/docs/en/settings-reference ("includeGitInstructions"); https://code.claude.com/docs/en/env-vars (`CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`); https://code.claude.com/docs/en/sub-agents ("What loads at startup"); https://code.claude.com/docs/en/context-window ("What survives compaction")
   - Marks: vendor-doc; converges across four pages
   - Grade: high (asserted; behavior of the switch not trialled here)

6. **What the snapshot invalidates: the git block and everything after it in `messages[0]` (attribution reminder, first prompt, later turns); the instruction block ahead of it can still be read.** (confidence: medium)
   The git block sits in `messages[0]` behind the instruction block, so a changed snapshot misses from that block on. The snapshot in Compass projects lists vault files Compass rewrites at every write (`index.md`, `active.md`, `meta/*.yaml`, lesson indexes, archive logs), so it differs almost every session. The instruction block precedes it and is read from cache when it is unchanged (trial in finding 7a).
   - Findings 3, 5 and 7a
   - Marks: local-record + vendor-doc; mechanism supported by one controlled run (7a), not by the project-history aggregate (7)
   - Grade: medium

7. **Measured over 233 recorded sessions: the first request reads a small constant prefix and writes the rest, and a matching git snapshot did not by itself raise the read.** (confidence: medium)
   First-request `cache_read_input_tokens` for sessions with a prior session in the last hour (172 pairs): median about 7,800 tokens with the snapshot differing (162 pairs) and also about 7,800 with the snapshot identical (10 pairs); `cache_creation` median about 27,000 versus about 29,000. The read is the same few values (5,6xx, 7,8xx, 8,003) across weeks, which is the size of tools plus system prompt, so only that prefix is reused across sessions; the roughly 27,000 to 35,000 tokens after it (instruction files, snapshot, skill and tool listings) are written again each session. One 14-minute pair with an identical snapshot and identical first prompt read 20,236 tokens, the only large cross-session read in the sample of pairs. A separate cluster of 31 early-benchmark runs with one fixed prompt read 22,552 tokens with 0 written, whatever the snapshot; not explained here.
   - Local transcripts, per-session first `assistant` usage; aggregates only
   - Marks: local-record, n=233 sessions, one user, one project; the same-snapshot subset is n=10 and confounded by prompt text (the last block carries the prompt, finding 3)
   - Grade: medium for "only tools+system reused", low for "snapshot is not the sole cause"

7a. **Controlled trial: when only the git snapshot changed between two otherwise identical headless runs, the cache read grew past the system prefix to include the instruction block.** (confidence: medium)
   Setup: a scratch git repo with a 120-line project CLAUDE.md (about 15,000 characters, 14,882 in the recorded block), three `claude -p` runs on a small model with an identical prompt, a new untracked file between runs 2 and 3 (so only the snapshot's `Status` lines changed; the user-turn block lengths confirm the rest was identical). The first run failed with a server error and wrote nothing usable. Run 2: read 5,827, wrote 8,646. Run 3: read 8,850, wrote 5,637, cost under 0.001 USD each. The 3,023 extra tokens read in run 3 match the size of the instruction block, so a prefix ending at a block boundary before the changed block was found in cache without a breakpoint there. The recorded request has the same three breakpoints as in finding 3.
   - Throwaway scratch run; the host's request records for those three runs (block lengths, `cacheControl`)
   - Marks: local-record, n=1 repo, n=2 usable runs, small project; single source
   - Grade: medium (measured, but small n and a small project)

### C. Open item (b): rule files and `paths: ["**"]`

8. **Unscoped rules load at launch with the priority of `.claude/CLAUDE.md`; a `paths:` rule loads into message history when Read, Write or Edit (or a single-file `cat`/`head`) touches a matching file.** (confidence: high for the documented rule)
   Patterns are relative to the directory holding the rule's `.claude` folder. The docs' pattern table lists `**/*.ts`, `src/**/*`, `*.md`; it does not state what a bare `**` does or whether it counts as unscoped. Compass's `session-start.md`, `compass-pipeline.md`, `wikilinks.md` carry `paths: ["**"]`; `compass-agent-patterns.md` is scoped to `.claude/agents/**` and `.claude/skills/**`.
   - https://code.claude.com/docs/en/memory ("Path-specific rules"); `plugin/templates/rules/*.md:1-5`
   - Marks: vendor-doc + local-code; converges with axis 2b B5
   - Grade: high for the documented rule, behavior of `**` still unobserved

9. **Measured: `paths: ["**"]` rules load at launch, as part of project context; only a truly scoped rule loads later.** (confidence: high)
   In the 40 most recent recorded sessions of one Compass project, 45 start-of-session `instructions` attachments listed user CLAUDE.md, project CLAUDE.md, auto-memory MEMORY.md and the three `**` rule files (`compass-pipeline`, `session-start`, `wikilinks`) together. The scoped `compass-agent-patterns` rule never appeared there: it arrived 34 times as a separate `nested_memory` attachment after a matching file was read. So `**` behaves as unscoped for loading, and the `paths:` header on those three files has no loading effect; it only differs from "no `paths`" in the docs' compaction and subagent wording (a `paths:` rule is "summarized away" at compaction per the docs, whether or not `**` matches). Closes REVIEW item C2 for the main session; the compaction behavior of a `**` rule and its load in subagents were not observed.
   - Local transcripts, attachment types `instructions` and `nested_memory`; `plugin/templates/rules/*.md:1-5`
   - Marks: local-record, 40 sessions, one project, host 2.1.330; converges with docs on the scoped rule, single source for `**`
   - Grade: high for load-at-launch (measured, repeated); not established for compaction

10. **A path-scoped rule's injection mid-conversation does not change the cached prefix.** (confidence: high)
    The host appends it to message history (conversation layer) when triggered, so system prompt and project context stay cached; compaction summarizes it away and it reloads on demand; "if a rule must persist across compaction, drop the `paths:` frontmatter or move it to the project-root CLAUDE.md." The cost of a scoped rule is a later, uncached append at the first matching read, repeated after each compaction.
    - https://code.claude.com/docs/en/prompt-caching ("Editing CLAUDE.md mid-session"); https://code.claude.com/docs/en/context-window ("What survives compaction")
    - Marks: vendor-doc; converges across two pages
    - Grade: high (asserted)

11. **Subagents: the CLAUDE.md hierarchy including project rules loads into a non-fork subagent; Explore, Plan and web-fetch skip it; `omitClaudeMd: true` in agent frontmatter drops user, project and local CLAUDE.md; path-scoped rules still load for those when the subagent touches matching files.** (confidence: high)
    The main conversation's auto memory (MEMORY.md) never reaches a non-fork subagent; a fork inherits it. Output style does not reach a non-fork subagent. A subagent's first request does not read the parent's cache; its TTL is 5 minutes unless set.
    - https://code.claude.com/docs/en/sub-agents ("What loads at startup"); https://code.claude.com/docs/en/prompt-caching ("Subagents and the cache")
    - Marks: vendor-doc; converges with axis 2b B7
    - Grade: high (asserted)

### D. Open item (c): what changes between sessions

12. **Auto-memory MEMORY.md: first 200 lines or 25KB load at session start in the project-context layer; topic files load on demand; not loaded in subagents.** (confidence: high)
    A write to MEMORY.md during a session does not alter the already-sent prefix; the next session carries the edited text, so each edit to the index is one cold project-context layer at the next start. `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` or `autoMemoryEnabled: false` removes it. Compass's plugin does not write MEMORY.md (it is the user's host feature).
    - https://code.claude.com/docs/en/memory ("How it works", "Enable or disable auto memory")
    - Marks: vendor-doc; single page for limits, converges with prompt-caching page for layer
    - Grade: high

13. **Compass's `.compass/index.md`, `active.md` and lesson indexes are not in the start prefix; they enter as tool results the session-start rule demands.** (confidence: high)
    They are rewritten by `compass sync` (PostToolUse on any `.compass/**/*.md` Write, Edit or MultiEdit) and by `capture-check`, so they change within and between sessions; the only route into the prefix is the git-status listing of their file names (finding 6). The three files measured 21,808 bytes in axis 2b B4. A SessionStart hook's output would instead be added after the cached system layers; Compass's SessionStart hooks (`self-update`, `capture-check`) print only on an update or an open capture opportunity.
    - `plugin/hooks/hooks.json` (SessionStart, PostToolUse entries); axis 2b B4 and B6
    - Marks: local-code; converges with axis 2b
    - Grade: high

14. **A Compass `self-update` that lands rewrites `.claude/rules`, skills, agents and CLI at SessionStart, so that session carries changed project context.** (confidence: medium)
    Same cost class the host names for a Claude Code upgrade, once per landed update (sha-gated, at most hourly).
    - `plugin/cli/commands/self_update.py:32-36`; https://code.claude.com/docs/en/prompt-caching ("Upgrading Claude Code")
    - Marks: local-code + vendor-doc; the equivalence is inferred
    - Grade: medium

### E. Other host facts that affect the prefix

15. **Tool definitions: with tool search (default on supported models) the first request's tool list is kept for the conversation, so MCP connect or disconnect mid-session does not break the cache; without tool search a connect invalidates.** (confidence: high)
    Skills, plugin skills/agents/hooks, plan mode and output-style switches append as conversation messages and never invalidate; model, effort (on older models), fast mode, a bare-tool deny rule without tool search, plugin MCP changes and a Claude Code upgrade do.
    - https://code.claude.com/docs/en/prompt-caching ("Actions that invalidate the cache", "Actions that keep the cache")
    - Marks: vendor-doc
    - Grade: high

16. **Cache visibility is built into the host: `/usage` shows a `Prompt cache (main)` hit ratio and likely cause of the last miss (v2.1.251 / v2.1.260); the status line gets a `prompt_cache` object; each API response reports `cache_read_input_tokens` and `cache_creation_input_tokens`; `claude -p ... --output-format json` reports `usage.cache_creation.ephemeral_1h_input_tokens` versus `_5m_`.** (confidence: high)
    - https://code.claude.com/docs/en/prompt-caching ("Check cache performance")
    - Marks: vendor-doc
    - Grade: high

17. **TTL controls: `promptCacheTtl` / `CLAUDE_CODE_PROMPT_CACHE_TTL` (main), `subagentPromptCacheTtl` / `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` (all else), agent frontmatter `experimental.cacheTtl`, `FORCE_PROMPT_CACHING_5M`, `ENABLE_PROMPT_CACHING_1H`; precedence listed in the doc; v2.1.242+.** (confidence: high)
    Confirms axis 2b B7; the recorded request shows `1h` TTL on all three breakpoints under a subscription.
    - https://code.claude.com/docs/en/prompt-caching ("Choose the TTL yourself"); local transcript `cacheControl`
    - Marks: vendor-doc + local-record; converges
    - Grade: high

## Candidate changes for Compass
Candidates only; the human and the planner decide. Ranked by expected cache effect. Each keeps every fact in the vault (nothing is moved out of it); "covered" = the vault or `plugin/` already does or decided it. Grep of `plugin/` and `.compass/` found no existing setting of `includeGitInstructions`, `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`, a TTL key, `omitClaudeMd` or `experimental.cacheTtl`.

1. **Ship `includeGitInstructions: false` for Compass projects (setup writes it into `.claude/settings.json`; the loop runner sets `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` for `claude -p` workers).** North stars: near-zero cache misses, low token usage. Removes the git block (about 2,700 to 3,500 characters each start, listing churned vault files) from the start prefix and from every subagent start, and the commit/PR instructions in the Bash tool description (this also drops the host's PR-writing guidance; Compass has `pr-describe` and its own commit rules in `CLAUDE.md`). Vault stays the source of truth: branch and dirty state remain one `git status` away. Not covered. Evidence: findings 5, 6, 7a. Not trialled: the effect of the switch on first-request reads, and whether any Compass agent or skill relies on the snapshot's branch line.
2. **Measure before and after, with a per-session script over the host's own request records (first-request `cache_read` / `cache_creation`).** North star: accuracy of the claim. The aggregate here (233 sessions: read about 7,800 versus written about 27,000 to 35,000) is the baseline; the same-snapshot subset is too small and confounded by prompt text to prove the snapshot is the cause. `/usage` `Prompt cache (main)` and the statusline `prompt_cache` object give the live number. Compass already reads `cache_read_input_tokens` in `context_check.py` (axis 2b C1); no per-session or per-agent-type report exists. Covered in part.
3. **Drop the no-effect `paths: ["**"]` header from the three always-needed rule files (or state in setup why it stays).** North star: low token usage, accuracy. Measured: they load at launch regardless (finding 9), so the header changes nothing at load time; the docs say a `paths:` rule is summarized away at compaction while an unscoped rule is re-injected from disk, so for a rule that must survive compaction the docs' own advice is to drop `paths:`. Whether `**` rules get re-injected after compaction was not observed; confirm with a compaction run before editing. Not covered (axis 2b candidate 4 left it open).
4. **Keep the hot-path files out of the prefix by design and keep them there: no SessionStart hook that prints `index.md` or `active.md`.** North star: near-zero cache misses. They enter as tool results behind the cached layers (finding 13); a hook that injected them at start would put churning text into every session's first request. Covered: today's design already does this ([[SPEC-003-hierarchical-vault-organization]]); the candidate is to record it as a constraint beside any future hot-path-injection change (the `SubagentStart` hook candidate in axis 2b).
5. **For Compass-launched subagents that need no project rules, `omitClaudeMd: true` in the agent frontmatter; for loop workers and builder waves, a TTL (`subagentPromptCacheTtl` or agent `experimental.cacheTtl: 1h`) where runs span more than 5 minutes.** North stars: low token usage, near-zero cache misses. A non-fork subagent's first request never reads the parent's cache (finding 11), so the saving is the instruction block (about 8,000 tokens of rules and CLAUDE.md in this repo) per subagent start; but agents rely on the pipeline rules today, so this trades accuracy for tokens and needs the human's decision. Not covered. Evidence: findings 11, 17; axis 2b B7.
6. **Vault churn in the git status listing: decide gitignore of regenerated files versus accepting it versus candidate 1.** North star: near-zero cache misses. Gitignoring `meta/*.yaml`, archive logs and lesson indexes shrinks the listing but moves those files out of version history, a conflict with the single-source rule; candidate 1 removes the listing with no vault change. Not covered.

## Contradictions
- Axis 2b B3 inferred from the doc that Compass sessions share no cache past the snapshot. The project-history aggregate (finding 7) agrees on "only tools and system reused" but 10 same-snapshot pairs also read no more, and the controlled trial (7a) read the instruction block when only the snapshot changed. The two do not fully agree; in the project history something else before or inside the instruction block (about 30,000 characters there, including the auto-memory index) may differ each session, but this was not isolated.
- The prompt-caching page's layer table puts CLAUDE.md in a separate layer after the system prompt; the recorded request puts it in a user-turn reminder with no breakpoint after it (findings 2, 3). Both can hold; the table is a stability ordering, not a breakpoint list.

## Gaps
- Whether a `**` rule survives compaction as an unscoped rule does (re-injected) or is summarized away like a scoped one: not observed (finding 9 shows only launch loading).
- Which exact part causes the first-request miss between the instruction block and the end: why the project-history sessions read only the system prefix while the controlled run read the instruction block as well (findings 7, 7a) is not isolated; candidates are an element inside the larger instruction block that differs per session, or the first prompt. A controlled run in this project's own settings was not made.
- The 22,552-token cluster of fixed-prompt runs was not explained.
- Whether the snapshot with `includeGitInstructions: false` still leaves a useful orientation for Compass (branch, dirty state) was not tested; the vault is the source of truth for state, so no vault fact depends on it.
- Per-agent-type cache hit rates (subagents) were not measured here; only main-session first requests.
