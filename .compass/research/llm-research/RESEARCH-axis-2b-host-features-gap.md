---
title: "Axis 2b: host features gap pass (loops, background sessions, self-update, prompt cache, doc-vs-code trials)"
type: research
status: complete
confidence: medium
area: architecture
tags: [research, claude-code, prompt-caching, goal, loop, background-sessions, plugin-update, trials, worktrees, hooks]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "c83c3ca"
author: researcher
summary: "Gap pass on axis 2: Compass looprunner/proctree/self_update versus /goal, --bg, /loop and plugin auto-update; prompt-cache ordering of always-loaded text; host trials confirming first-pass findings 8, 21, 24, 25 and 26 (4 doc-vs-code conflicts resolved), 7 not reproducible"
---

# Axis 2b: host features gap pass

Follows [[RESEARCH-axis-2-host-features]] (axis 2 of 7 of [[RESEARCH-llm-research-for-compass]]), under [[SPEC-001-compass-vision-and-architecture]]. Host: Claude Code 2.1.330. Today 2026-11-21. grading: allowed.

## Question
Which of Compass's loop, process-tree and self-update machinery does the host now cover; what order and stability of Compass's always-loaded text maximizes prompt-cache hits; and which first-pass doc-versus-code observations hold when run on the host?

## Methodology
Technology landscape / comparative evaluation (DESMET feature analysis: documentation review plus tool trials), as in the first pass. Each part is "host option versus Compass incumbent", and the trials are DESMET case-study-style tool trials. The host is closed source, so vendor docs are the primary source; Compass code was read directly; trials ran `claude -p` on the installed host in throwaway projects.

Marks on every finding: not retracted; not a preprint; citation count n/a (vendor docs, local code, local trials); convergence stated. Grade key: vendor-doc = asserted by Anthropic docs, not measured by the vendor; local-code = read in this repo; local-trial = run on the host here (measured, n=1 unless stated).

## Findings

### A. Compass machinery versus host features

A1. **`/goal` is a session-scoped prompt-based Stop hook judged by a small fast model from the transcript only.** (confidence: high)
   After each turn the evaluator returns met / not yet / impossible; it runs no tools and reads no files; condition up to 4,000 characters; one goal per session; restored on resume with turn count, timer and token baseline reset; works as `claude -p "/goal ..."` to completion in one process; a bound is only a text clause in the condition ("or stop after 20 turns"); evaluation tokens are billed on top; unavailable when `disableAllHooks` is true.
   - https://code.claude.com/docs/en/goal
   - Marks: vendor-doc; not retracted; not preprint; n/a; converges with the scheduled-tasks page comparison table
   - Grade: high for mechanics (asserted with stated limits)

A2. **`/loop` re-runs a prompt in the same session on a time interval; it is not a fresh session per iteration, and recurring tasks expire after 7 days.** (confidence: high)
   Fixed (cron, minimum 1 minute) or model-chosen delay (1 to 60 minutes); up to 50 tasks per session; fires only while the session runs and is idle; no catch-up for missed fires; self-paced loops are not restored on resume; backgrounding the session (`/bg`) carries loops into a supervised process, where a self-paced loop stops if its wakeup comes due while the process is not running.
   - https://code.claude.com/docs/en/scheduled-tasks ; https://code.claude.com/docs/en/agent-view
   - Marks: vendor-doc; converges across two pages
   - Grade: high. Correction to the first pass: finding 19 there says "/loop up to 30 days"; the scheduled-tasks page read here says 7 days.

A3. **`claude --bg` is process supervision for sessions, not a loop and not a budgeted runner.** (confidence: high)
   A supervisor daemon runs each session as its own process; survives terminal close and sleep; stops an idle unattached process after about an hour (conversation stays on disk; Ctrl+T pins it); after a reboot sessions show failed (progress within 48 h) or stopped; `--bg` with `-p` is rejected; `claude agents --json` gives `working|blocked|done|failed|stopped`; sessions started by `--bg` move into an isolated worktree before editing unless `worktree.bgIsolation` is `none`; inside it Claude commits and may push and open a draft PR but never pushes to main or force-pushes; `--bg --exec '<cmd>'` runs a shell job with no model; state files are documented as not a stable interface. Research preview.
   - https://code.claude.com/docs/en/agent-view (first 100,000 of 146,000 characters read)
   - Marks: vendor-doc, preview; single source
   - Grade: high for stated behavior; preview status means it can change

A4. **Compass `looprunner` runs every iteration as a fresh headless `claude -p --output-format json` session and wraps it in controls no host feature has.** (confidence: high)
   Per iteration: run lock, crash recovery, deterministic sense (`sensorlib`), gate (USD budget, then work in progress), controller picks the work, prompt assembled with no budget numbers, actuator launched with caps from `loop.json` and `COMPASS_WORKER_SESSION=1`, deterministic re-sense, optional multi-vote judge (fresh read-only sessions, `--allowedTools Read,Glob,Grep`), one ledger row per run written before the state transition that ends it, fingerprint of `loop.json`, `state.json`, `ledger.jsonl`, `baseline.json` taken before the actuator starts and a halt with `controls-changed` if any differs.
   - `plugin/cli/looprunner.py:13-44` (docstring), `:24-28` actuator, `:30-33` fingerprint, `:35-42` judge, `:760` worker env
   - Marks: local-code; converges with `plugin/cli/looplib.py` (`transition`, `advance`, `acquire_lock`, `recover`, `fold`)
   - Grade: high (code read; docstring and structure agree)

A5. **Overlap map, `looprunner` versus the three host features: partial on "keep going" and "run again", none on the controls.** (confidence: medium)
   - Keep working until a condition holds: `/goal` does it partly. The host judges the condition from the transcript by a model in one growing session; Compass senses and re-senses with code outside the model and starts each iteration with a clean context.
   - Run again later: `/loop` does it partly (same session and context, 7-day expiry, session must be running); `--bg` keeps a session alive without a terminal but a `/loop` inside it has the same limits.
   - USD budget gate, per-run cost ledger, stale-lock and crash recovery, control-file fingerprinting, independent multi-vote judging: none of the three host features read provides them; the host's only bound on a goal is a text clause.
   - Not established: whether loop iterations could be `claude --bg` workers; the page rejects `--bg` with `-p`, and `--bg --exec` runs a shell command only.
   - Marks: local-code + vendor-doc; the comparison is mine, the facts are in A1 to A4
   - Grade: medium (comparison, not a measured equivalence)

A6. **Compass `proctree.py` kills a whole process tree on timeout; the host pages read document stopping its own sessions, not killing arbitrary child trees.** (confidence: medium)
   `proctree` starts a child as the root of its own tree (POSIX new session and `killpg`; Windows new process group inside a kill-on-close Job Object, `taskkill /T` fallback, then a process-snapshot walk). It is used by `looprunner`, `sensorlib` and `clone` to bound child processes. `claude stop <id>` and `Ctrl+C` stop host sessions; whether a stopped session's descendants are reaped on Windows is not stated in the pages read.
   - `plugin/cli/proctree.py:1-24` ; `grep proctree plugin/cli` (looprunner.py, sensorlib.py, commands/clone.py) ; https://code.claude.com/docs/en/agent-view
   - Marks: local-code + vendor-doc; host side is an absence in a page, not a negative statement
   - Grade: medium

A7. **Compass `self-update` and host marketplace auto-update do different jobs: the host updates a plugin cache, Compass re-installs files into the project.** (confidence: high)
   Compass: SessionStart(startup) hook, 1-hour sentinel, `git ls-remote` sha gate against `plugin.yaml`, shallow clone to a temp dir, copies agents, rules, skills, the CLI, the hooks manifest, merges hook registration into `.claude/settings.json`, records sha256 per file in `meta/installed.json`, saves differing local edits under `meta/local/kept/`; mandatory, no pin; silent unless an update landed. Host: after the first message of an interactive session, waits a random delay up to 10 minutes, refreshes marketplaces with auto-update on and updates the on-disk plugin copy; the new version applies on `/reload-plugins` or the next launch; on by default for official and claude.ai-synced marketplaces, off for any other; version is manifest `version`, else a 12-character commit sha; a pinned manifest version keeps users on the cached copy; `${CLAUDE_PLUGIN_DATA}` persists across updates; old version directories are removed after 14 days; a mid-session update leaves hook commands on the old path until `/reload-plugins`.
   - `plugin/cli/commands/self_update.py:1-36,53-57` ; https://code.claude.com/docs/en/plugins/loading ("When auto-update runs", "Versions and updates") ; https://code.claude.com/docs/en/discover-plugins ("Keep plugins updated")
   - Marks: local-code + vendor-doc; converges on what each does
   - Grade: high

A8. **What host auto-update does not do that `self-update` does.** (confidence: medium)
   (1) The first turns run on the old install (up to 10 minutes of delay) where Compass's hook runs at SessionStart before the first request. (2) The host updates the plugin cache directory; it does not copy into `.claude/agents`, `.claude/rules` or `.claude/cli`, which Compass's layout uses (the documented plugin-agent frontmatter restrictions, first-pass finding 16, are why agents are copied). (3) No local-edit preservation. (4) Off by default for a third-party marketplace. The component list on the prompt-caching page (skills, commands, agents, hooks, monitors, themes, MCP, LSP) does not name rules files; whether a plugin can ship project rules is not stated in the pages read.
   - https://code.claude.com/docs/en/prompt-caching ("Plugin components that keep the cache") ; https://code.claude.com/docs/en/plugins/loading
   - Marks: vendor-doc + local-code; inference from two sources
   - Grade: medium

### B. Prompt caching: order and stability of Compass's always-loaded text

B1. **The API caches a prefix in the fixed order tools, system, messages; a change at one level invalidates that level and every level after it.** (confidence: high)
   Static content (tools, system instructions, context, examples) goes first; the breakpoint goes at the end of the static prefix, never on a block with a timestamp (that pays a fresh write every request with no read). Minimum cacheable prefix is 512 tokens on Sonnet 5.5, Opus 5.5 and Haiku 5.5, 1,024 on Sonnet 5 and 4.x, 4,096 on Haiku 4.5. Reads cost 0.05x on Sonnet 5.5 and Opus 5.5 (0.1x on older models); 5-minute writes 1.25x, 1-hour writes 2x. A cache entry becomes available only after the first response starts, so parallel requests do not read each other's write. Lookback checks at most 20 positions before a breakpoint.
   - https://platform.claude.com/docs/en/build-with-claude/prompt-caching (first 100,000 of 155,000 characters read)
   - Marks: vendor-doc; converges with the Claude Code page
   - Grade: high

B2. **Claude Code orders each request as system prompt and tools, then project context (CLAUDE.md, auto memory, unscoped rules), then the conversation.** (confidence: high)
   Project context is read at session start and re-read from disk after `/clear` or `/compact`; it is cached together with the conversation, so compaction rebuilds its cache even if the files are unchanged. Editing CLAUDE.md mid-session leaves the cached prefix intact. Skills, plan mode, output-style switches and plugin skills/agents/hooks are appended as conversation messages and never invalidate. Rules with `paths:` frontmatter and nested CLAUDE.md files load on demand into message history, and compaction summarizes them away. A model switch, an effort change on most models, fast mode, an MCP definition change without tool search, a bare-tool deny rule and a Claude Code upgrade each invalidate; a skill whose frontmatter names a different `model` is a one-turn model switch.
   - https://code.claude.com/docs/en/prompt-caching ("How the cache is organized", "Actions that invalidate the cache", "Actions that keep the cache") ; https://code.claude.com/docs/en/context-window ("What survives compaction")
   - Marks: vendor-doc; converges across two pages and with the trial in C1
   - Grade: high

B3. **Cross-session reuse is scoped to one machine and directory, and sequential sessions share the prefix only when the startup git-status snapshot matches.** (confidence: high)
   The system prompt embeds auto-memory paths and the conversation opens with working directory, platform, shell and OS version; each conversation also carries the branch and recent commits from the git snapshot. In this session's own context the order observed is CLAUDE.md content, then the git status block (a long list of modified and untracked vault files). Compass writes vault files (`index.md`, `active.md`, lessons, `meta/*.yaml`, archive logs) at every session, so the snapshot differs from session to session in a Compass project and everything after it misses. The `includeGitInstructions` setting removes the built-in commit and PR instructions; the full entry (whether it controls the status block) was not read.
   - https://code.claude.com/docs/en/prompt-caching ("Cache scope") ; this session's startup context (observation) ; https://code.claude.com/docs/en/settings-reference (index line only)
   - Marks: vendor-doc + single observation; single source for the rule
   - Grade: medium (the rule is asserted; the Compass consequence is inferred)

B4. **Compass's always-loaded text today (measured by `wc -c`).** (confidence: high)
   `CLAUDE.md` 7,216 bytes; four rule files 13,530 bytes (`compass-pipeline.md` 10,509; `compass-agent-patterns.md` 1,461; `wikilinks.md` 920; `session-start.md` 640). The hot-path reads the session-start rule demands are `index.md` 15,382, `active.md` 3,663 and `lessons/index.md` 2,763 bytes (21,808 total), which enter as conversation-layer tool results, behind the stable prefix. No date, session id or per-session text appears in the rule files (`grep` for dates found none).
   - `wc -c` on `CLAUDE.md`, `.claude/rules/*.md`, `.compass/index.md`, `.compass/active.md`, `.compass/lessons/index.md`
   - Marks: local-code; measured sizes
   - Grade: high

B5. **Three of the four rule files carry `paths: ["**"]` frontmatter; the first pass's candidate 5 says `compass-pipeline.md` has no `paths:`.** (confidence: high that the headers exist; low on what `**` does at the host)
   `session-start.md`, `compass-pipeline.md` and `wikilinks.md` each open with `paths:` and the pattern `"**"`; `compass-agent-patterns.md` scopes to `.claude/agents/**` and `.claude/skills/**`. Per the host docs, a rule with `paths:` loads into message history when a matching file is read and is summarized away at compaction, and a rule unscoped is part of project context. Whether `**` is treated as unscoped (always loaded) or as path-scoped (loaded on first file read) was not isolated: the trial in C5 loaded none of the project's CLAUDE.md or rules in `-p`. If it is path-scoped, the session-start rule that tells the agent to read the hot path would not be in context before the first file read.
   - `.claude/rules/*.md:1-5` ; https://code.claude.com/docs/en/context-window ("What survives compaction")
   - Marks: local-code + vendor-doc; conflicts with the first pass's local-code reading
   - Grade: medium for the header fact (read directly), low for the behavior

B6. **Compass hook output reaches the conversation layer, not the prefix.** (confidence: high)
   `self-update` prints one line only when an update landed (`self_update.py:32-35`); `capture-check` on Stop emits a block decision or, on its quiet fallback, `hookSpecificOutput.additionalContext` (`capture_check.py:126-140,226-237`); the PostToolUse `context-check` returns `continue: false` at 80% and 95%. All append after the cached prefix. A `self-update` that lands rewrites `.claude/rules`, skills, agents and CLI at SessionStart, which changes project context for that session (one cold prefix), the same cost the host names for a Claude Code upgrade.
   - `plugin/cli/commands/self_update.py:32-35` ; `plugin/cli/commands/capture_check.py:126-140,226-237` ; `plugin/hooks/hooks.json`
   - Marks: local-code + vendor-doc; converges
   - Grade: high

B7. **Subagents start their own cache and default to a 5-minute TTL even on a subscription.** (confidence: high)
   A subagent's first request does not read the parent's cache; a fork inherits it. The TTL for subagents, compaction and other non-main requests is 5 minutes unless `subagentPromptCacheTtl`, `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` or the agent's `experimental.cacheTtl` frontmatter sets `1h`. The main conversation (interactive, `-p`, SDK) gets 1 hour only on a subscription within plan usage, else 5 minutes unless `promptCacheTtl` is set. The host holds same-prefix agents in a workflow fan-out for up to 5 seconds so the first can write the cache; ordinary parallel Agent calls are not described as held. Compass sets no cache TTL setting or environment variable (`grep` of `plugin/` found none) and its loop launches `claude -p` with only `COMPASS_WORKER_SESSION` added (`looprunner.py:760`).
   - https://code.claude.com/docs/en/prompt-caching ("Which TTL each request gets", "Subagents and the cache") ; `plugin/cli/looprunner.py:760`
   - Marks: vendor-doc + local-code; converges
   - Grade: high for the rules; the effect on Compass's parallel builder waves is inferred (medium)

B8. **No Compass skill sets `model:`, `context: fork` or `paths:` in its frontmatter.** (confidence: high)
   `grep` over `plugin/skills/*/SKILL.md` (34 skills) found no `model:` line (so no skill-triggered model switch) and no `paths:` or `context: fork`.
   - `plugin/skills/*/SKILL.md`
   - Marks: local-code
   - Grade: high

### C. Host trials of first-pass doc-versus-code observations

Trial setup: throwaway git project with a bare remote, one pushed commit (c1) and one unpushed local commit (c2), settings-file hooks logging each event's stdin, agents under `.claude/agents` and a local plugin loaded with `--plugin-dir`; `claude -p --model haiku --permission-mode bypassPermissions`. No git write in the Compass repo.

C1. **First-pass finding 25 resolved: frontmatter `isolation: worktree` works on 2.1.330, for a project agent and for a plugin agent, with no `isolation` argument on the Agent call.** (confidence: high)
   The project agent `wt-agent` ran in `.claude/worktrees/agent-<id>`; the plugin agent `trialplug:plagent` (frontmatter `isolation: worktree`) reported a worktree toplevel path too. `plugin/skills/build/SKILL.md:39` says the frontmatter key "does nothing" and instructs passing `isolation: "worktree"` on the call; that statement does not hold on this host in `-p`. Not tested: interactive mode, agent-teams teammates (docs exclude them).
   - local-trial (project agent run, plugin agent run) ; `plugin/skills/build/SKILL.md:39`
   - Marks: local-trial; converges with https://code.claude.com/docs/en/sub-agents (the doc statement)
   - Grade: high (measured, two agents)

C2. **First-pass finding 24 resolved: the worktree forks from the remote default branch by default and from local HEAD with `worktree.baseRef: "head"`.** (confidence: high)
   Default: the subagent worktree sat at `a96ef18` (c1, pushed), missing the unpushed local c2, matching [[LESSON-subagent-worktrees-fork-stale]]. With `{"worktree":{"baseRef":"head"}}` in `.claude/settings.local.json`: the worktree sat at `ca55eb8` (c2, local HEAD). Untracked and uncommitted files were not tested (git semantics and the docs say they are invisible), so the checkpoint-commit rule in `plugin/skills/build/SKILL.md:32` still covers uncommitted work.
   - local-trial (two runs, one repo) ; https://code.claude.com/docs/en/worktrees
   - Marks: local-trial; converges with the doc
   - Grade: high

C3. **First-pass finding 26 resolved: `if` works in settings-file hooks.** (confidence: high)
   A settings-file PostToolUse hook with `"if": "Write(*.md)"` fired for `a.md` and not for `a.txt`, while the same matcher without `if` fired for both. [[LESSON-hook-if-clause-no-or]] ("settings-file hook entries have no `if`") is stale for 2.1.330. The no-`||` limit was not re-tested (first-pass finding 3 stands on the doc).
   - local-trial (WriteAll 2 events, WriteIfMd 1 event)
   - Marks: local-trial; converges with the hooks doc
   - Grade: high

C4. **First-pass finding 8 resolved: a plugin-shipped agent has `agent_type` `plugin:agent`, and Compass's bare-name SubagentStop matcher does not match it.** (confidence: high)
   `SubagentStart` and `SubagentStop` payloads carried `agent_type: "trialplug:pl-agent"`. A SubagentStop matcher `plagent|zzz` did not fire for `trialplug:plagent`; `pl-agent|zzz` (with a hyphen, as `spec-writer` and `pr-describe` in Compass's list have) did not fire for `trialplug:pl-agent`; the exact string `trialplug:plagent` fired. Compass's matcher `builder|tester|debug|validator|planner|researcher|reviewer|spec-writer|pr-describe` therefore matches only project-installed agents (`.claude/agents`, the layout `/compass:setup` produces), not a plugin loaded by `--plugin-dir` or marketplace. SubagentStop payloads carried `last_assistant_message`, `agent_id`, `agent_type`.
   - local-trial (3 agents, 3 matchers) ; `plugin/hooks/hooks.json` SubagentStop entry
   - Marks: local-trial; converges with the hooks doc matcher paragraph
   - Grade: high

C5. **First-pass finding 21 resolved: `initialPrompt` in a subagent's frontmatter is not applied.** (confidence: high)
   Agent `ip-agent` (frontmatter `initialPrompt: "Read the file canary.txt ..."`, instruction to answer NOTSEEN unless the file content was already visible) returned `NOTSEEN` with 0 tool uses; the PreToolUse log shows no Read by it. The hot-path load that Compass agent files declare through `initialPrompt` does not run when they are spawned as subagents.
   - local-trial (1 agent, 1 run) ; first pass finding 6
   - Marks: local-trial; converges with the sub-agents doc and with the first pass's one observation
   - Grade: high (measured; n=1)

C6. **First-pass finding 7 not reproduced: no `SubagentHandback` tool call appeared in any trial.** (confidence: low)
   Five subagent runs logged PreToolUse and SubagentStop events and none contained `SubagentHandback`; the tool's conditions of use were not established, so the claim that it moves the report out of `last_assistant_message` is neither confirmed nor refuted.
   - local-trial (grep count 0 across all logs)
   - Marks: local-trial; single negative
   - Grade: low

C7. **Project `CLAUDE.md` and `.claude/rules/*.md` did not load in `claude -p` in the trial directories, so the path-scoping behavior of B5 was not isolated.** (confidence: medium)
   With a canary code in project `CLAUDE.md`, an unscoped rule and a `paths: ["**"]` rule, a model asked for the codes in its context reported all three absent, with and without a prior file Read, in a non-git directory and a git repository (sonnet, two runs each; haiku also failed), while the user-level `CLAUDE.md` did load. The cause (an untrusted trial folder, `-p` behavior, or the environment) was not established, so these runs say nothing about `**`.
   - local-trial (4 runs)
   - Marks: local-trial; negative result with an unexplained cause
   - Grade: low as evidence about `paths: ["**"]`

## Contradictions
- First pass candidate 5 says `compass-pipeline.md` has no `paths:`; the file opens with `paths: ["**"]` (B5).
- First pass finding 19 says `/loop` runs up to 30 days; the scheduled-tasks page says recurring tasks expire after 7 days (A2).
- `plugin/skills/build/SKILL.md:39` and [[LESSON-subagent-worktrees-fork-stale]] describe two behaviors; C1 and C2 show the first is stale on 2.1.330 and the second still holds by default but has a setting (`worktree.baseRef`).
- [[LESSON-hook-if-clause-no-or]]: stale on the first clause (C3).

## Gaps
- What `paths: ["**"]` does at the host (always loaded or loaded on first file read), and whether a subagent loads path-scoped rules: not isolated (C7); needs a trial in a trusted interactive folder or the `/context` view.
- Whether the git-status block can be disabled and where `includeGitInstructions` places it: full settings entry not read (B3).
- `SubagentHandback` conditions of use (C6).
- Whether a plugin can ship project rules (A8); `claude --bg` workers as loop actuators (A5); `claude plugin details` and `/skill-doctor` numbers for Compass (not run).
- The agent-view page was read to character 100,000 of 146,000 and the prompt-caching API page to 100,000 of 155,000; the unread tails may hold more limits.
- Cache-hit behavior of Compass's parallel builder waves was inferred from docs, not measured (B7).

## Candidate changes for Compass
Candidates only; the human and the planner decide. Ranked by architectural impact. "Covered" = the vault or `plugin/` already does or decided it.

1. **Retire the `initialPrompt` hot-path declaration in agent files and inject the hot path with a `SubagentStart` hook.** North stars: accuracy, near-zero cache misses. Change: add `SubagentStart` (agent-type matcher, `additionalContext` within 10,000 characters, plugin-scoped names handled) to `hooks.json`; drop the dead `initialPrompt` lines. Covered: no. Evidence: C5, first pass findings 6 and 21 (now measured).
2. **Widen the SubagentStop matcher to include plugin-scoped names (`compass:builder` and so on) or document that the capture loop works only with project-installed agents.** North star: accuracy of the learning loop. Change: `plugin/hooks/hooks.json` matcher (a colon-bearing alternative or a second entry). Covered: no. Evidence: C4.
3. **Remove or narrow the stale workarounds that the trials contradict.** North stars: low token usage, accuracy. Change: shorten `plugin/skills/build/SKILL.md:39` (frontmatter `isolation` works); offer `worktree.baseRef: "head"` for builder worktrees (the checkpoint-commit rule stays for uncommitted files); rewrite [[LESSON-hook-if-clause-no-or]] and [[LESSON-subagent-worktrees-fork-stale]] to the observed behavior. Covered: no recheck was recorded. Evidence: C1 to C3.
4. **Decide the scope of the four rule files.** North stars: low token usage, near-zero cache misses. Three carry `paths: ["**"]`; determine by an interactive `/context` check whether they load at start, then choose between true unscoped (project context, cached across sessions) and a smaller always-loaded core with sections moved into skills. Covered: no; first pass candidate 5 rested on a wrong premise. Evidence: B2, B4, B5, C7.
5. **Measure and reduce the cross-session prefix break caused by vault churn in the git-status snapshot.** North star: near-zero cache misses. Options for the human: read the `includeGitInstructions` entry and any status-snapshot setting; keep vault churn out of the snapshot (gitignore of regenerated files is a tradeoff against the single-source rule); or accept it. Covered: no. Evidence: B3 (inferred consequence, medium).
6. **Set cache TTLs for Compass's headless and subagent traffic.** North stars: low token usage, near-zero cache misses. Options: `subagentPromptCacheTtl` or agent `experimental.cacheTtl` for builder/tester/validator waves that run longer than 5 minutes; `CLAUDE_CODE_PROMPT_CACHE_TTL` in the `looprunner` worker environment where iteration spacing exceeds 5 minutes on API-key billing. Covered: no (no TTL setting in `plugin/`). Evidence: B7.
7. **Keep `looprunner`, `looplib`, `sensorlib` and `proctree`; treat `/goal` and `/loop` as complements, not replacements.** North star: accuracy. The host features lack the USD gate, ledger, lock and crash recovery, fingerprinting and independent judge (A4, A5). Option for the planner: a Compass skill or loop template that sets a `/goal` for interactive work while `looprunner` stays the unattended path. Covered: the loop machinery exists (`plugin/cli/looprunner.py`, `plugin/cli/loop_templates/`).
8. **Keep `self-update`; consider a documented plugin-cache route as a second channel only if rules can be shipped by a plugin.** North star: perfect memory. Host auto-update replaces the plugin cache but does not write `.claude/agents|rules|cli` or preserve local edits (A7, A8). Covered: ADR-015 and SPEC-020 (not reread here); the distribution question is in [[research/distribution/index]] (not reread).

> Root-index description preserved when this document was folded under its topic folder (2026-11-24): Gap pass on axis 2: Compass looprunner/proctree/self_update versus /goal, --bg, /loop and marketplace auto-update; prompt-cache ordering for always-loaded text; host trials of first-pass findings 7, 8, 21, 24, 25, 26
