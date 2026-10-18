---
title: "Loop Fresh-Checkout Experiment: What a CI-Style Checkout Runs"
type: research
status: done
confidence: high
area: pipeline
tags: [loops, ci, guard, hooks, self-update, fresh-checkout, github-actions, prototype]
created: 2026-10-18
updated: 2026-10-18
git_branch: "master"
git_commit: "b5f38de"
author: "researcher"
depends_on: ["[[specs/pipeline/SPEC-026-control-theory-for-loops]]"]
summary: "A fresh clone has no .claude/ and no hooks, so a subagent's rm runs unguarded; validate does not fix that, `compass self-update` does (installs .claude/ and the guard), so a CI loop needs that one install step before its actuator runs"
---

# Loop Fresh-Checkout Experiment: What a CI-Style Checkout Runs

Prototype task TASK-156 of [[PLAN-021-control-loops]].

## Question

When a Compass project is checked out fresh (as a CI runner does), is the destroy-information guard active for a subagent the actuator spawns, and which step puts it there?

## Methodology

Repository mining, an empirical study of how an existing system behaves: a scratch clone, measured by running the real CLI and real headless sessions. Outcome fixed before running: the install step a CI workflow needs (none, run the CLI from a pinned plugin checkout, or run setup), and whether a CI actuator that spawns subagents runs unguarded without it.

No `grading:` disclosure reached this run, so the findings are marked and ungraded.

## Setup

- Scratch clone: `~\AppData\Local\Temp\claude\F--claude-plugins-compass\ae974588-929f-4f0a-8ff2-ad796c7400a9\scratchpad\fresh-clone\` (called `<clone>` below), HEAD `b5f38de`.
- Claude Code 2.1.302, model `claude-haiku-4-5-20251001`, every `claude -p` run with `--allowedTools "Agent" "Bash" --max-budget-usd 0.30` (headless runs need the tools allowed; permission mode `default`).
- User-level `~\.claude\settings.json` (read only): no `hooks` key; `settings.local.json` has no `hooks` either. The five enabled plugins (zoekt-ue5, zoekt-defold, rust-analyzer-lsp, codex-hud, codex-review) ship no `hooks*.json` or `"hooks"` entry in their JSON.
- Spend: 0.0844 + 0.1136 + 0.0553 + 0.0753 = 0.3286 USD.

## Findings

1. **A fresh clone has no `.claude/`** (confidence: high)
   `ls -a <clone>` shows `.compass`, `.git`, `.gitattributes`, `.gitignore`, `bench`, `CLAUDE.md`, `plugin`, `README.md`; `ls .claude` exits 2 (No such file). `.claude/` is gitignored, and `git ls-files` lists no `.claude/` path. The clone does carry `.compass/`, `plugin/cli/`, `plugin/hooks/hooks.json`, and a tracked `.compass/meta/plugin.yaml`.
   - `<clone>\.gitignore` - `.claude/` is ignored
   - Marks: code and command output; not retracted; no preprint; 0 citations; 1 source, 4 runs agree

2. **No hooks fire in the fresh clone, project-level or user-level** (confidence: high)
   `claude -p ... --output-format stream-json --verbose --include-hook-events` in the clone emits 0 `hook_started` or `hook_response` events (event types seen: `system/init`, `task_*`, `assistant`, `user`, `result`). Project hooks come from `.claude/settings.json`, which is absent. No user-level hooks exist to fire.
   - `<scratchpad>\fc-hooks-A.jsonl` - full event stream
   - Marks: command output; not retracted; no preprint; 0 citations; 1 run, consistent with finding 1

3. **A subagent's `rm` of a tracked file runs unguarded in the fresh clone** (confidence: high)
   Two-turn session, both turns spawned a `general-purpose` subagent through the Agent tool; the subagent reported exit 0 with no block, and the files were gone:
   - `claude -p "<spawn subagent: rm bench/fixtures/binary-search-bug/prompt.txt>" --model claude-haiku-4-5-20251001 --output-format json --allowedTools "Agent" "Bash" --max-budget-usd 0.30` : exit 0, session `05800792-878e-4204-8418-6d9718ff5bb6`, cost 0.0844, `git status --porcelain` showed ` D bench/fixtures/binary-search-bug/prompt.txt`.
   - Same command with `--resume 05800792-...` and `rm bench/fixtures/binary-search-bug/verify.sh` : exit 0, cost 0.1136, porcelain then showed both ` D` lines.
   - A third run (stream-json, finding 2) deleted `prompt.txt` again with the same result.
   Files were put back with `git show HEAD:<path> > <path>` (porcelain empty afterwards).
   - Marks: command output; not retracted; no preprint; 0 citations; 3 runs agree

4. **`compass validate` against the clone does not restore the guard** (confidence: high)
   `CLAUDE_PROJECT_DIR=<clone> python F:\claude\plugins\compass\plugin\cli\compass validate` : exit 0, output `0 error(s), 2 warning(s)` (`sizing_unrecorded`, `taxonomy_hints`). `.claude/` still did not exist afterwards. The only file it changed was `.compass/meta/usage.yaml` (command counters). The guard hook command begins `[ -f "$CLAUDE_PROJECT_DIR/.claude/cli/compass" ] || exit 0`, so with that file absent every hook is a no-op by design.
   - `plugin/hooks/hooks.json` PreToolUse entry - the `[ -f ... ] || exit 0` prefix
   - Marks: command output and code read; not retracted; no preprint; 0 citations; 2 sources agree

5. **`compass self-update` from the clone's own `plugin/cli` creates `.claude/` and registers the hooks** (confidence: high)
   `cd <clone>; CLAUDE_PROJECT_DIR=<clone> python plugin/cli/compass self-update` : exit 0, stdout `Compass updated 0.26.5 -> 0.26.5`. It created `.claude/{agents,cli,commands,hooks,rules,settings.json,skills}` and registered `PreToolUse` (`Bash|Write|Edit|MultiEdit`), `PostToolUse`, `SessionStart`, `Stop`, `TeammateIdle`, `SubagentStop` in `.claude/settings.json`. It also created the gitignored `.dsh/` (`hooks.json`, `skills/`) and `AGENTS.md`, and ran `apply-models`.
   - `plugin/cli/commands/self_update.py:_perform` - applies the local `source:` directly only when it resolves inside the project root; otherwise falls to the `repository:` URL
   - Marks: command output and code read; not retracted; no preprint; 0 citations; 2 sources agree

6. **The tracked `plugin.yaml` sent self-update to GitHub, not to the local plugin** (confidence: high)
   The tracked `.compass/meta/plugin.yaml` has `source: F:/claude/plugins/compass/plugin`, which is outside the clone, so `_perform` skipped the local branch, ran `git ls-remote https://github.com/hodor/claude-compass`, and shallow-cloned that repository: it installed `0.26.5` at `f89147d` (the local repo is `0.27.0`). The run rewrote `commit:` and `installed_at:` in `plugin.yaml`. The install is therefore whatever GitHub HEAD holds at run time, not a pin.
   - `<clone>\.compass\tmp\self-update.log` - `updated 0.26.5 -> 0.26.5 (f89147d34416)`
   - `git diff .compass/meta/plugin.yaml` - `commit:` and `installed_at:` changed
   - Marks: command output and code read; not retracted; no preprint; 0 citations; 2 sources agree

7. **After self-update the same subagent `rm` is denied** (confidence: high)
   `claude -p "<spawn subagent: rm bench/fixtures/binary-search-bug/prompt.txt, report whether blocked>" --model claude-haiku-4-5-20251001 --output-format stream-json --verbose --include-hook-events --allowedTools "Agent" "Bash" --max-budget-usd 0.30` : exit 0, cost 0.0753. The subagent reported the call blocked by `compass guard` ("nothing destroys information (the Data rule)"); `prompt.txt` still exists. Hook events: `SessionStart:startup` x2 started and succeeded (exit 0), `PreToolUse:Bash` x1 (the subagent's `rm`), `PostToolUse:Agent` x1, `Stop` x1, all `success` exit 0. `SubagentStop` did not fire: its matcher names the Compass agent types, not `general-purpose`.
   - `<scratchpad>\fc-hooks-B.jsonl` - event stream
   - Marks: command output; not retracted; no preprint; 0 citations; 1 run, matches the same prompt unguarded in finding 3

8. **The guard judges subagent calls only** (confidence: high)
   The hook shell reads the event and exits before Python unless it contains `agent_id` or `agent_type`; the main agent is never denied. In the clone the guard denied the spawned subagent's `rm`; the headless main agent made no destructive call, so main-agent exemption was not exercised.
   - `plugin/hooks/hooks.json` PreToolUse entry - `case "$input" in *agent_id*|*agent_type*) ;; *) exit 0;; esac`
   - Marks: code read plus finding 7; not retracted; no preprint; 0 citations; 2 sources agree

9. **After the full run, the clone differs from HEAD only in two tracked files** (confidence: high)
   `git -C <clone> status --porcelain` (exit 0):
   ```
    M .compass/meta/plugin.yaml
    M .compass/meta/usage.yaml
   ```
   `plugin.yaml`: `commit:` and `installed_at:` rewritten by self-update. `usage.yaml`: command counters bumped by `validate`, `apply-models` and the Stop hook's `capture-check`. `git status --porcelain --ignored` also lists `.claude/`, `.compass/tmp/`, `.dsh/`, `.serena/` (created by a user-level MCP server in the headless session), `AGENTS.md`, `__pycache__/`. The fixtures deleted by the probes were restored and show no diff. `F:\claude\plugins\compass` was not modified by this experiment other than this document and the task check-offs.
   - Marks: command output; not retracted; no preprint; 0 citations; 1 source

10. **Once installed, a spawned headless session runs the project's hooks** (confidence: high)
    Finding 7 shows SessionStart (including `self-update --hook`), PostToolUse, and Stop firing inside the `claude -p` session, as [[LESSON-spawned-sessions-inherit-project-hooks]] states. A CI actuator that spawns a session after install therefore re-enters the capture machinery (`capture-check` on Stop).
    - Marks: command output plus a vault lesson; not retracted; no preprint; 0 citations; 2 sources agree

11. **Env-var redirection worked here because the clone carries `.compass/`** (confidence: medium)
    `CLAUDE_PROJECT_DIR` pointed at the clone resolved to the clone's vault in `validate` and `self-update` (their changes appear only in the clone), consistent with [[LESSON-scratch-vaults-need-compass-dir]]. A CI checkout of a Compass project always has a tracked `.compass/`; the empty-directory edge was not exercised.
    - Marks: command output plus a vault lesson; not retracted; no preprint; 0 citations; 2 sources agree

## Outcome

- **Install step a CI workflow needs:** one. The guard exists only after `.claude/cli/compass` and the registered hooks exist, and the only step that did that was `python <plugin>/cli/compass self-update`, run from the clone's own `plugin/cli` (a plugin checkout's CLI). `validate` and the checkout itself do not. Not "none"; `setup` (the interactive skill) was not needed and not run.
- **Unguarded without it:** yes. A CI actuator that spawns subagents in a fresh checkout runs with no guard and no hooks; a subagent `rm` of a tracked file succeeded in three of three runs.
- **Pinning:** with the tracked `plugin.yaml` the install follows GitHub HEAD (finding 6). A source path inside the project root is applied directly by `_perform` with no network; a pinned plugin checkout placed in the workspace as `source:` would take that branch, but that branch was not run here.

## Gaps

- The real GitHub Actions run was not executed; whether the runner has `python`/`python3`, `git` network access, and the same `$CLAUDE_PROJECT_DIR` is unverified. The human decides whether it is wanted.
- The pinned-checkout branch of `_perform` (a `source:` inside the project root) was read in code, not run.
- `git clone` was piped to `tail`, so its own exit code was not captured; the clone's presence at `b5f38de` and the later commands confirm it succeeded.
- The `SubagentStop` capture path was not exercised (the probe's subagent type is outside its matcher).
