---
title: "dsh live probes (PLAN-017 Wave 1)"
type: research
status: in-progress
area: distribution
tags: [dsh, probes, hooks, bundles, live-verification]
summary: "running record of the PLAN-017 Wave 1 probes against a live dsh: rig facts, profile mechanics confirmed, hook-fire and Stop-contract results"
created: 2026-09-05
updated: 2026-09-05
depends_on: ["[[PLAN-017-dsh-host-support]]"]
---

# dsh live probes (PLAN-017 Wave 1)

Running record. Each probe appends; nothing here is summarized away.

## TASK-001: the rig

- dsh `0.1.2-rc.1` (npm `@deepseek-ai/dsh`), Node `v24.20.0` portable, both isolated in the session scratchpad - nothing global was modified. dsh requires Node `^22.19.0 || >=24.0.0`; the machine's own Node is v20.13.1 and was left alone.
- Harness home: `DSH_HOME` pointed at a scratchpad `dsh-home/`; profile auto-init created `profiles/headless/` on first boot.
- Scratch project (`dsh-rig/`): git repo, `.compass/` vault (minimal index/active/catalog + `meta/plugin.yaml` naming the local plugin source at version 0.18.4), full Compass install applied by the plugin's own `self_update._apply` + `merge_settings`. `compass doctor` exits 0.
- Rebuild from nothing (deterministic, scratchpad-wipe-safe):
  ```bash
  SP=<scratchpad>
  curl -sL -o node24.zip https://nodejs.org/dist/v24.20.0/node-v24.20.0-win-x64.zip
  python -c "import zipfile; zipfile.ZipFile('node24.zip').extractall('.')" && mv node-v24.20.0-win-x64 node24
  export PATH="$SP/node24:$PATH" npm_config_prefix="$SP/dsh-prefix" DSH_HOME="$SP/dsh-home"
  npm install -g --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs @deepseek-ai/dsh
  mkdir dsh-rig && cd dsh-rig && git init
  # vault skeleton (index.md, active.md, meta/lessons-catalog.yaml, meta/plugin.yaml), then:
  python -c "import sys; sys.path.insert(0,'F:/claude/plugins/compass/plugin/cli'); from commands import self_update; self_update._apply('F:/claude/plugins/compass/plugin','.',apply_models=False); self_update.merge_settings('.','F:/claude/plugins/compass/plugin/hooks/hooks.json')"
  ```
- npm blocks native install scripts by default now; without the `--allow-scripts` list, node-pty/koffi land unbuilt.
- Status: automated verification met (`dsh --version`, doctor exit 0). Manual verification (a session answers one prompt) blocked on a provider credential - see the blocker at the end.

## TASK-002 groundwork (profile mechanics, ahead of the bundle form)

- Profile auto-init confirmed the documented shape exactly: `package.json` with `dsh.profile: {bundles: ["@deepseek-ai/dsh-base","@deepseek-ai/dsh-headless"], patchReload: "startup"}` plus an empty `cordis.patch.yml` user layer.
- Patch grammar: a YAML array of operations; `- insert:` takes `{id, name, config}` plugin entries (`packages/bundle/base/cordis.patch.yml` is the reference).
- `@deepseek-ai/dsh-hooks-claude-code` ships in the installed dsh's own module tree - no extra `dsh plugin add` needed to mount it.
- Mounting the bridge from the profile's `cordis.patch.yml` with `configPath` at the rig's `.claude/settings.json` and `projectDir` at the rig root composes cleanly (`--dump-config` shows the entry).
- Still to prove: the same mount as an *installable bundle* (`dsh.bundle.patch` package), and a vault write inside a session firing `compass sync`.

## TASK-001 completion (live)

With `DEEPSEEK_API_KEY` exported, `dsh --profile headless "reply with the single word pong"` answers `pong`. All TASK-001 bars met.

## TASK-002 results: the hook loop runs, through a bundle

- **Proven end to end, twice.** A vault write from inside a live dsh session fires `compass sync` and the root index gains the artifact's line - first with the bridge mounted from the profile's `cordis.patch.yml`, then with the mount coming only from an installable bundle: a 2-file package (`package.json` with `"dsh": {"bundle": {"patch": "./cordis.patch.yml"}}` + the patch) added via `dsh plugin --profile headless add file:<dir>` (pnpm-backed) and listed in `dsh.profile.bundles`. Both files are mechanically generatable.
- **Windows hooks run under PowerShell.** The headless profile disables `bash-sandbox` on win32 and mounts `pwsh-sandbox`; Compass's sh-dialect hook commands (`if command -v python3 ...`) fail silently there. The dialect-neutral form works in both hosts and is proven live: `python "${CLAUDE_PROJECT_DIR}/.claude/cli/compass" sync --hook` - dsh substitutes the `${...}` token at parse time, Claude Code's shell expands it as an env var. Consequence for the materializer (D-03): the dsh side gets a generated hooks file in this dialect (with lowercase matchers `Write|write` etc.); `configPath` points at it instead of `.claude/settings.json`. The python3-vs-python branching is lost in the neutral form - the generated dsh file can simply say `python` (dsh hosts we saw resolve it), while the Claude Code manifest keeps its sh wrapper.
- Payload facts (captured verbatim by probe hooks): `tool_name` is lowercase (`write`); `tool_input.file_path` is an **absolute** Windows path - `sync --hook`'s normalizer handles it (checks `/.compass/` after slash normalization); `CLAUDE_PROJECT_DIR` is exported to hook processes with forward slashes.

## TASK-003 results: Stop and SessionStart semantics

- **SessionStart `source` literal: `"startup"`** - identical to Claude Code; the self-update hook's matcher works verbatim. Payload also carries `session_id`, `cwd`, `transcript_path` (a `.jsonl.zstd` under `$DSH_HOME/sessions`).
- **The steer contract delivers.** A probe Stop hook emitting `{"decision": "block", "reason": ...}` on exit 0 caused the model to receive the reason as a real continuation turn and act on it (it replied with the exact phrase the reason requested, noting the instruction came "from the direct user"). The rendered-block fallback of the capture ladder therefore works on dsh.
- **`stop_hook_active` is statically `false`** in dsh Stop payloads. Compass never reads it; nothing on our side loops.
- **Finding: one-shot headless sessions reap the detached capture worker.** The Stop-hook `capture-check` opened the forced-due opportunity and spawned the worker (`worker-started` row, real pid), but dsh manages hook process trees and the worker died with the exiting `dsh` process - no end row, no worker log. The recovery ladder then behaved exactly as designed: a later session's check found the started row inside `worker_grace_seconds` (600) and correctly left it alone. Expected shape on dsh: interactive (tui/web) sessions leave the process alive between turns, giving workers time to finish; one-shot headless kills them every time, and after grace + two spent attempts the ladder falls back to the rendered block - which the steer probe proves works. In a dual-host project the Claude Code side's workers complete regardless. TASK-012 should treat "headless dsh never completes a detached worker" as a fact to design around, not a bug to fix.
- Deviation from the task's written bar: no `worker-finished`/`worker-failed` row was produced - the bar assumed workers survive the session, and the probe's actual finding is that on one-shot headless they cannot. The evidence obtained (started row + reaped pid + ladder behavior + steer proof) answers the question the bar was standing in for.

## TASK-004 results: the instruction-surface matrix (measured, not inferred)

Sentinel codewords planted one per surface; each host asked to list what it sees.

| Surface | Claude Code | dsh |
|---|---|---|
| `CLAUDE.md` | loads | loads |
| `AGENTS.md` | does not load | loads |
| `AGENTS.local.md` | does not load | loads |
| `.claude/rules/*.md` | loads | does not load |

A clean exactly-once assignment exists (D-04 satisfied, no amendment needed):

- **Rules text** -> `.claude/rules/` for Claude Code AND a generated managed section of `AGENTS.md` for dsh. Each host sees it exactly once, because each surface is invisible to the other host.
- **`CLAUDE.md` Compass section** -> the one both-hosts surface; carries only text meant for both, once.
- **Personas** -> `.claude/agents/` (CC) / generated bundle instances (dsh). **Skills** -> `.claude/skills/` (CC) / `.dsh/skills/` (dsh). Neither host reads the other's surface.

Verified from both transcripts: the rules sentinel appeared exactly once per host (dsh via AGENTS.md, CC via `.claude/rules/`). Caveat for TASK-010: dsh users' projects may already carry a hand-written `AGENTS.md`; the materializer folds into a fenced managed section, never overwrites ([[LESSON-installer-removes-only-what-it-installed]]).

## Observations that need a live model

- A keyless run dies at `MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"` and leaves zero hook evidence (`.compass/tmp/` never created). Whether SessionStart fires cannot be distinguished from a boot that never reached the session - all hook probes wait on a credential.
- Watch item for the first live run: the hook commands are POSIX sh (`command -v python3 ...`); dsh executes hooks through its shell seam, which on Windows compositions may be pwsh. If the commands fail shell-parse, the manifest needs a host-neutral command form - record the observed executor either way.

## Wave 2 live verification (the host seam)

- With the rig's plugin.yaml rostered `hosts: [claude-code, dsh]`, one `self_update._apply` run produced both materializations: the `.claude/` refresh and a generated `.dsh/hooks.json` (dialect-neutral commands, lowercase-widened matchers, unsupported events dropped).
- Dual-host proof in one project: a dsh session's vault write ran sync through the generated file (bundle -> bridge -> `.dsh/hooks.json`), and a `claude -p --allowed-tools Write` session's vault write ran sync through `.claude/settings.json`'s widened matcher. Both artifacts landed in the same index.
- Operational finding for the bundle waves: pnpm `file:` bundle installs are snapshots - editing the bundle source dir does not reach the profile's `node_modules` copy; a content change requires `dsh plugin add` again (a version bump forces it). The generated-bundle materializer (TASK-008) must re-add on every refresh, and stale-bundle detection belongs in doctor's host checks (TASK-011).
- Also reconfirmed from the lesson catalog the hard way: headless `claude -p` denies Write silently - the CC live check needs `--allowed-tools Write` ([[LESSON-headless-worker-denies-tools-silently]]).

## Blocker (resolved 2026-09-05)

A provider credential was required for every live probe; the human supplied a `DEEPSEEK_API_KEY` (exported in the launching environment, never written to disk) and the default `deepseek-official` headless route worked unchanged.
