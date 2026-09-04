---
title: "DeepSeek Harness (dsh) as a Compass host"
type: research
status: done
area: distribution
tags: [hosts, deepseek, dsh, hooks, skills, subagents, multi-host]
summary: "dsh ships a Claude Code hooks.json bridge (all four Compass events, file_path intact) and filesystem skills, so the CLI and hook loop port with config-level changes; the real work is agents (per-instance delegation tools in composition config, not markdown) and rules (no .claude/rules loader - fold into AGENTS.md)"
created: 2026-09-04
updated: 2026-09-04
depends_on: ["[[specs/distribution/SPEC-006-multi-host-agent-cli-support]]"]
---

# DeepSeek Harness (dsh) as a Compass host

Source: https://github.com/deepseek-ai/deepseek-harness cloned at depth 1 on 2026-09-04 (TypeScript monorepo, ~9k files; `dsh` CLI in `apps/cli`, capabilities as Cordis plugins under `packages/`). All file references below are repo-relative.

## What ports without code changes

**The compass CLI itself.** Pure Python over the filesystem; `find_vault_root` falls back to a cwd walk when `CLAUDE_PROJECT_DIR` is absent, and the dsh hook bridge exports `CLAUDE_PROJECT_DIR` anyway (below). Confidence: high.

**The hook loop.** `packages/hooks/hooks-claude-code/` is a first-party bridge that runs an existing Claude Code `hooks.json` during dsh agent runs. Verified in source:
- Events cover everything Compass registers: `SessionStart`, `PostToolUse`, `Stop`, `SubagentStop` (plus `SubagentStart`, `PreToolUse`, `UserPromptSubmit`) - `src/config.ts:12-18`.
- Payloads carry `tool_name`, `tool_input`, `tool_response` in Claude wire shape - `src/index.ts:339-342`.
- dsh's fs tools take `file_path` as the required parameter (`docs/tool-catalog.md`, `dsh-tool-fs` schemas), so sync's `tool_input.file_path` parsing works unchanged. Confidence: high.
- `${CLAUDE_PROJECT_DIR}` is substituted in commands AND exported as an env var to hook processes - `src/index.ts:40-60`. Confidence: high.
- Command hooks only; other hook types are skipped with a warning. Compass uses only command hooks. Confidence: high.

**Skills, structurally.** `packages/skill/skill-filesystem/` discovers `<root>/<name>/SKILL.md` bundles - exactly Compass's shape - parses YAML frontmatter, hot-watches, and users invoke `/name`. Confidence: high.

**Instructions file.** The instruction loader's default candidates are `['AGENTS.md', 'CLAUDE.md']` walking up to a `.git` root (`packages/context/agent-instructions/src/config.ts:12`), so Compass's CLAUDE.md additions load as-is. Confidence: high.

## What needs config-level changes (no plugin code)

- **Hook matcher casing.** dsh tool names are lowercase (`write`, `edit`, `bash`); the bridge matches on dsh names. Compass's PostToolUse matcher `Write|Edit|MultiEdit` must become `Write|Edit|MultiEdit|write|edit` (harmless under Claude Code). One line in the hook manifest. Confidence: high.
- **hooks.json discovery.** The bridge takes a `configPath` at mount: "a hooks.json or a settings file whose `hooks` key holds the config" - it can point straight at `.claude/settings.json`. But it is process-level, read once at launch; per-project auto-discovery is an open TODO in their source (`TODO(per-session-hook-config)`). A Compass dsh profile must set it per project. Confidence: high on mechanics, medium on ergonomics until tried live.
- **Skill install root.** dsh scans `.dsh/skills` and `.agents/skills` (project), `~/.dsh/skills` (user), plus `customSkillDirs` - never `.claude/skills`. Setup/update need a second install target (or the profile adds `.claude/skills` to `customSkillDirs`). Top-level bundles only - Compass's flat skill dirs comply. Confidence: high.
- **Skill frontmatter dialect.** dsh reads `name` (kebab-case required), `description`, `whenToUse`, `user-invocable`, `disable-model-invocation`. Compass writes `when_to_use` and `allowed-tools`; unknown keys are ignored, so the routing hint is lost unless setup also writes `whenToUse:`. Skill names are bare (`/setup`, not `/compass:setup`) - collision risk suggests installing as `compass-<name>`. Confidence: medium (key handling inferred from README + config; verify against a live catalog).

## What needs real porting work

- **Agents.** dsh has no markdown agent files. A named child persona is one configured `tool-subagent` instance in the composition ("another persona, tool filter, depth cap requires another distinctly named tool" - `packages/subagent/tool-subagent/README.md`), composed via `preset/` cordis.yml files and `bundle/` installable `dsh --profile` patch-layer bundles. Compass's 13 agents would translate into a shipped dsh bundle defining one delegation tool per agent (persona prompt + tool filter + model route). Alternative observed: `subagent-claude-code` runs a real Claude Code child over the Agent SDK, which would reuse `.claude/agents/` untouched at the price of requiring Claude Code inside dsh. Confidence: high that translation is required; medium on the bundle mechanics until one is built.
- **Rules.** Nothing loads `.claude/rules/*.md`; `instructionFileCandidates` are same-directory filenames, not directories. Compass's three rules files must fold into the generated AGENTS.md/CLAUDE.md (or ship as skills). Confidence: high.
- **Model resolution.** dsh models are provider routes (`agentDefaultModel`: provider + model id, e.g. DeepSeek routes); `apply-models` writes Claude model ids into agent frontmatter that dsh never reads. The central model table needs a dsh host column mapping tiers to provider routes, applied into the bundle instead of agent files. Confidence: high.
- **Host detection in setup/update/doctor.** All three assume `.claude/` + settings.json hooks. They need a host probe (`.dsh`/`dsh` present) and per-host install manifests - the same seam SPEC-006 already anticipates for hermes/Kimi/Codex. Confidence: high.

## Open questions

- Bundle/preset authoring: what a minimal installable Compass profile bundle looks like (`packages/bundle/`, `packages/preset/`) - unexplored beyond READMEs.
- SessionStart matcher source values (`startup` vs dsh's session sources) for the self-update hook - the bridge passes a `source` as matcher subject; values unverified.
- Whether dsh's Stop-hook block contract (exit 2 / decision JSON) matches Claude Code's semantics closely enough for the capture loop's block-and-respawn dance - the wire protocol library claims parity where protocols agree; needs a live probe.
