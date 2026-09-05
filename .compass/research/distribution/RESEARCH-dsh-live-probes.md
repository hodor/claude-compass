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

## Observations that need a live model

- A keyless run dies at `MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"` and leaves zero hook evidence (`.compass/tmp/` never created). Whether SessionStart fires cannot be distinguished from a boot that never reached the session - all hook probes wait on a credential.
- Watch item for the first live run: the hook commands are POSIX sh (`command -v python3 ...`); dsh executes hooks through its shell seam, which on Windows compositions may be pwsh. If the commands fail shell-parse, the manifest needs a host-neutral command form - record the observed executor either way.

## Blocker

A provider credential. Cheapest: `DEEPSEEK_API_KEY` exported in the launching environment (the default headless route is `deepseek-official`). Any other supported provider (`anthropic`, `openai`, `moonshotai`, `zai`, or a custom `apiKeyEnv` gateway) also works but needs a `settings.yaml` default-model change first.
