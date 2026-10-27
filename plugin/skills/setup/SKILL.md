---
name: setup
description: Set up Compass in a project for the first time - creates the .compass/ vault, installs agents, rules, skills, the compass CLI, and hooks into .claude/, and proposes CLAUDE.md additions. To refresh an existing install, use /compass:update.
version: 2.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion]
when_to_use: "Use for first-time Compass setup in a project. Triggers: 'set up compass', 'initialize compass', 'install compass', 'compass setup'. To refresh an existing install from git, use /compass:update instead."
argument-hint: "[new | migrate]"
---

# Setup - Compass Project Setup

Sets up Compass in a project for the first time:

1. Detects project state (new vs existing).
2. Installs agents, rules, skills, and the compass CLI from the plugin to `.claude/`.
3. Configures hooks and permissions.
4. Creates the `.compass/` vault.
5. Proposes CLAUDE.md additions - human approves before any write.
6. Kicks off vision capture for new projects.

Updating an existing install is a separate command: **`/compass:update`** - it pulls the latest from GitHub, refreshes `.claude/`, and leaves the vault untouched. This skill is for first-time setup only.

## Modes

- `/compass:setup new` - full setup: agents + rules + skills + CLI + hooks + vault + CLAUDE.md.
- `/compass:setup migrate` - full setup for a project that already has docs to fold in.

## Protocol

### 1. Detect state

```
Glob: .compass/          - vault already exists?
Glob: .claude/agents/    - Compass agents already installed?
Glob: *.md, docs/**/*.md - existing documentation?
Glob: CLAUDE.md          - existing project instructions?
```

- **New project** - no `.compass/`.
- **Existing project** - `.compass/` exists OR docs to migrate.
- **Agents already installed** - `.claude/agents/` contains Compass agents.

### 2. Install agents, rules, and skills

Use Bash `cp` only. Do NOT use Read on template files. Do NOT use Write. The template content must never pass through your context window - that's expensive and unnecessary.

```bash
# Find the plugin root
PLUGIN_ROOT=$(find / -path "*/compass/plugin/.claude-plugin/plugin.json" -type f 2>/dev/null | head -1 | sed 's|/.claude-plugin/plugin.json||')

if [ -z "$PLUGIN_ROOT" ]; then
  for p in "$HOME/.claude/plugins/compass/plugin" "F:/claude/plugins/compass/plugin"; do
    [ -f "$p/.claude-plugin/plugin.json" ] && PLUGIN_ROOT="$p" && break
  done
fi

echo "Plugin root: $PLUGIN_ROOT"

# Agents
mkdir -p .claude/agents
cp "$PLUGIN_ROOT/templates/agents/"*.md .claude/agents/
echo "Agents copied: $(ls .claude/agents/*.md | wc -l) files"

# Rules
mkdir -p .claude/rules
cp "$PLUGIN_ROOT/templates/rules/"*.md .claude/rules/
echo "Rules copied: $(ls .claude/rules/*.md | wc -l) files"

# Slash commands (direct-execution wrappers, e.g. /tree)
mkdir -p .claude/commands
cp "$PLUGIN_ROOT/templates/commands/"*.md .claude/commands/
echo "Commands copied: $(ls .claude/commands/*.md | wc -l) files"

# Skills (makes project self-contained)
for skill_dir in "$PLUGIN_ROOT/skills/"*/; do
  skill_name=$(basename "$skill_dir")
  mkdir -p ".claude/skills/$skill_name"
  cp "$skill_dir"*.md ".claude/skills/$skill_name/"
done
echo "Skills copied: $(ls -d .claude/skills/*/ | wc -l) directories"

# CLI (the compass binary the PostToolUse hook runs; makes the project self-contained)
rm -rf .claude/cli
cp -r "$PLUGIN_ROOT/cli" .claude/cli
echo "CLI copied: $(ls .claude/cli/commands/*.py | wc -l) command modules"

# The Compass Review Obsidian plugin (copied into the vault by step 5)
rm -rf .claude/obsidian
cp -r "$PLUGIN_ROOT/obsidian" .claude/obsidian

# The PostToolUse hook runs the CLI via `python3` if present, else `python`
# (python3 is canonical on POSIX; Windows often only has `python`). Verify one exists.
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "WARNING: neither python3 nor python found on PATH. The vault-sync hook will be a silent no-op until a Python 3 interpreter is installed. The CLI never blocks writes (it can only exit 0/1), so nothing breaks - sync just will not run. Install Python 3, or run the CLI manually."
fi

# Write the resolved model policy into the copied agents. Rewrites only the
# model:/effort: frontmatter of the 13 Compass agent files; any other file in
# .claude/agents/ is user-authored and never touched. --dir is explicit because
# the default target resolves through the .compass vault, which step 3 has not
# created yet.
if command -v python3 >/dev/null 2>&1; then
  python3 .claude/cli/compass apply-models --dir .claude/agents
elif command -v python >/dev/null 2>&1; then
  python .claude/cli/compass apply-models --dir .claude/agents
fi
```

Run as one Bash call. Verify 13 agents, 4 rules files, and that `.claude/cli/compass` exists. If the plugin can't be found, ask the human for the path.

After this, the project is self-contained - anyone who clones gets agents, skills, and rules without installing the plugin.

`compass apply-models` writes the model policy (which model and effort each agent runs on) into the copied agent frontmatter. The defaults ship in the CLI; a project retunes them via `.compass/meta/models.yaml` (remap a tier or pin a single agent), then re-runs `compass apply-models`. Claude Code hot-reloads `.claude/agents/`, so a re-apply takes effect without restarting the session. Inspect the resolved roster with `compass models`. The host env var `CLAUDE_CODE_SUBAGENT_MODEL`, when set, overrides all subagent frontmatter and masks the table.

**Record the plugin source.** After the copy succeeds, write `.compass/meta/plugin.yaml`:

```yaml
plugin:
  name: compass
  version: <plugin.json version>
  source: <PLUGIN_ROOT path used above>
  repository: <plugin.json repository>
  installed_at: <today YYYY-MM-DD>
  installed_mode: new | migrate | update
```

Host support is detected, never asked (SPEC-006 D-05). A machine with DeepSeek Harness on it (the `dsh` binary on PATH, or a harness home at `$DSH_HOME` / `~/.dsh`) gets the dsh materializations regenerated by every update in the same run that refreshes `.claude/`, so two hosts of one project can never sit on different Compass versions; a machine without dsh sees zero dsh-shaped writes. Do not ask the human which hosts the project uses, and do not write a `hosts:` field.

The install keeps itself current from here: the SessionStart hook runs `compass self-update` at every session start (sha-gated against `repository`, silent when current, mandatory - no opt-out). It records a `commit:` field in this file on its first update.

That refresh replaces every shipped agent, rule, and skill, so a project that wants to extend one puts the addition in `.compass/meta/local/agents/<name>.md` (or `rules/`, `skills/`) - update appends it back on top of the fresh copy every time. `CLAUDE.md` is never touched by Compass.

This file is the single source of truth for "where did this project's Compass install come from." Future `/compass:update` runs read it directly; no filesystem rediscovery. `/compass:checkup` can diff the recorded version against the source's current version to detect drift.

If agents are already installed (re-running setup on a project), ask once before overwriting, through `AskUserQuestion` with exactly one question per call: "Overwrite the installed agents, rules, and skills?". The recommended option comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Other" stays open for free text:

- **Keep the existing install (Recommended):** leaves the installed files untouched.
- **Overwrite:** replaces the installed agents, rules, and skills with the plugin's copies.

Never batch several questions in one message or one call. Refreshing an existing install from git is `/compass:update`, not this skill.

### 2b. Hooks and permissions

Hooks install as a manifest at `.claude/hooks/hooks.json`, then get registered into `.claude/settings.json`, which is where Claude Code actually reads hooks from. Permissions also go in `.claude/settings.json`.

```bash
# Hooks manifest: PostToolUse runs `compass sync`, Stop runs `compass
# capture-check`, SubagentStop runs `compass capture-signal`. Copied verbatim
# from the plugin. This file is a manifest, not something Claude Code reads
# directly - the next step translates it into .claude/settings.json.
mkdir -p .claude/hooks
cp "$PLUGIN_ROOT/hooks/hooks.json" .claude/hooks/hooks.json
echo "Hooks manifest installed -> .claude/hooks/hooks.json"
```

The PostToolUse hook runs the CLI as `python3 "$CLAUDE_PROJECT_DIR/.claude/cli/compass" sync --hook` (falling back to `python` when `python3` is absent, e.g. on Windows), resolving the CLI copied in step 2 via the project-root env var the hook runtime sets. It self-filters non-vault and generated-output writes and never exits 2, so it can neither loop nor block an edit.

**Register the hooks where Claude Code actually reads them.** Hooks load only from a settings file's `hooks` key or a registered plugin, never from a bare `hooks.json` on disk. Translate the manifest into `.claude/settings.json`, merging into whatever is already there rather than overwriting it. Never write hook registration to `.claude/settings.local.json` - that file is user-owned.

```bash
if command -v python3 >/dev/null 2>&1; then PYBIN=python3; else PYBIN=python; fi
"$PYBIN" -c "import sys; sys.path.insert(0, '.claude/cli')
from commands import self_update
self_update.merge_settings('.', '.claude/hooks/hooks.json')
print('Hooks registered in .claude/settings.json')"
```

Then write the permission allowlist into the same `.claude/settings.json` (or `.claude/settings.local.json`), merging alongside the `hooks` key the script above just wrote:

```json
{
  "permissions": {
    "allow": [
      "Read",
      "Grep",
      "Glob",
      "WebSearch",
      "WebFetch",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(git status:*)",
      "Bash(git rev-parse:*)",
      "Bash(git show:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(curl:*)",
      "Bash(python3:*)",
      "Bash(pytest:*)",
      "Bash(npm test:*)",
      "Bash(npm run test:*)",
      "Bash(yarn test:*)",
      "Bash(go test:*)",
      "Bash(cargo test:*)",
      "Bash(make test:*)",
      "Bash(make check:*)",
      "Bash(make lint:*)",
      "Bash(npm run lint:*)",
      "Bash(npm run build:*)",
      "Bash(uv run pytest:*)",
      "Bash(python -m pytest:*)",
      "Bash(./venv/Scripts/python.exe:*)",
      "Bash(./venv/bin/python:*)"
    ]
  }
}
```

`Bash(python3:*)` lets skills invoke the `compass` CLI (e.g. `/compass:vault-health` running `compass validate`). Compass agents use `permissionMode: bypassPermissions`, so they bypass these prompts entirely - the allowlist is the safety net for everything else.

Hook registration is already a merge (the script above never overwrites `.claude/settings.json` wholesale). The permission allowlist is not scripted the same way: if `.claude/settings.json` already has a `permissions` key, merge the two lists by hand and ask before overwriting existing permissions.

### 3A. New project - scaffold the vault

```
.compass/
  index.md
  active.md
  backlog.md
  .annotations/             # sidecar annotations
  meta/
    plugin.yaml             # plugin source reference (step 2 writes this)
    lessons-catalog.yaml    # numbering is JIT, no counter file - see ADR-003
  specs/
  research/
  plans/
  decisions/
  lessons/
  handoffs/
  prs/
  archive/
```

Setup does NOT create `vision.md` - `/compass:vision` does that. Setup does NOT create specs - `/compass:spec` does that. Setup does NOT create a counter file - numbering is computed JIT from the filesystem. Setup does NOT create `meta/models.yaml` - it is the optional model-policy override (see step 2), added only when a project retunes the defaults.

`lessons-catalog.yaml`:
```yaml
lessons: []
```

`index.md`:
```markdown
---
title: "Project Index"
type: index
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# Project Index

The master map. Every vault document is linked here. Sections (Vision, Specs, Research, Plans, Decisions, Lessons, Handoffs) are appended by the agents that create those documents. Run `/compass:vision` next.
```

Don't stub empty sections. They appear when content arrives. Then create empty `active.md` and `backlog.md`.

### 3B. Existing project - migrate

1. Inventory existing docs, TODOs, specs, decisions.
2. Propose a migration table:
   ```
   | Source | Destination | Action |
   |--------|------------|--------|
   | README.md#Architecture | SPEC-001-... | Extract to spec |
   | TODO.md items | active.md / backlog.md | Migrate tasks |
   | docs/decisions/ | decisions/ | Rename to ADR-NNN format |
   ```
3. Human approves line by line.
4. Execute approved migrations.
5. Update `index.md`.

### 4. Propose CLAUDE.md addition

Draft a short Compass section - rules, not essays:

```markdown
## Compass

`.compass/` is the knowledge vault. Open it in Obsidian for graph view.

**Pipeline:** Vision → Spec → Research → Plan → Build → Test → Validate. Don't skip phases.

**Key rules:**
- Vision is captured ONCE per project (or per major pivot). It produces a spec roadmap. Run `/compass:vision` at the start.
- Specs are SINGLE-PROBLEM. ONE spec = ONE problem. If you write "and also", split into two specs.
- Specs are about the NEED, not the solution. No implementation decisions in specs.
- Specs start as `draft`. Nothing happens until the human approves.
- Compass agents are available for research, planning, building, testing, validation.
- All code changes require tests.
- `git add <file>` - never `-A` or `.`

**Start here:** `.compass/index.md` (map) and `.compass/active.md` (tasks).
**Help:** `/compass:guide` (workflow) or `/compass:checkup` (health).
```

Show the draft, then ask through `AskUserQuestion`, exactly one question per call: "Add this section to CLAUDE.md?". The recommended option comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Other" stays open for free text:

- **Add it (Recommended):** writes the section to CLAUDE.md.
- **Needs changes:** you say what to change; I edit and show the draft again.
- **Skip:** leaves CLAUDE.md untouched.

Never put several questions in one message or one call. Write only after approval.

### 5. Verify with `compass doctor`

```bash
if command -v python3 >/dev/null 2>&1; then
  python3 .claude/cli/compass review --install
  python3 .claude/cli/compass doctor
else
  python .claude/cli/compass review --install
  python .claude/cli/compass doctor
fi
```

`review --install` copies the Compass Review plugin into the project's Obsidian vault when Obsidian has already opened one, and does nothing otherwise. Obsidian lets only the human turn a community plugin on: when doctor's `obsidian review` row WARNs, give him its steps as they are. Once the plugin is on, every document Compass asks him to review opens in Obsidian with Approve and Needs changes buttons. A vault opened in Obsidian after setup gets the plugin at the next `/compass:update` or self-update, or at once with `compass review --install`.

This is the install's acceptance check: `plugin.yaml`, automatic step registration, CLI completeness, `.claude/agents/`, `.claude/skills/`, and `.compass/meta/lessons-catalog.yaml` in one pass, exiting 1 on any FAIL. A FAIL means setup did not fully land - fix the named defect (doctor prints the command) before moving on to vision capture. For a human skimming the report without running the command, the same six checks restated:

- [ ] `.compass/meta/plugin.yaml` exists with `name`, `version`, `source`, `installed_at`.
- [ ] Hooks registered in `.claude/settings.json` (a bare `.claude/hooks/hooks.json` is not enough).
- [ ] `.claude/cli/` has a module for every command `maincli.py` declares.
- [ ] `.claude/agents/` has 13 Compass agents.
- [ ] `.claude/skills/` populated.
- [ ] `.compass/meta/lessons-catalog.yaml` exists.

Two checks doctor doesn't cover, also worth confirming: `.claude/rules/` has 4 rule files, and `.compass/index.md` / `.compass/active.md` exist.

### 5b. Offer longer session retention

Claude Code deletes session transcripts older than `cleanupPeriodDays` (30 days when unset). Check the effective value:

```bash
if command -v python3 >/dev/null 2>&1; then
  python3 .claude/cli/compass retention
else
  python .claude/cli/compass retention
fi
```

The first line is the number of days or `unset`. When it is `unset` or 30 or less, ask once, through `AskUserQuestion`, exactly one question per call, never batched with another question: "Claude Code deletes old sessions after 30 days by default. Keep them longer, so `/compass:clone-old` can use them?" The recommended option comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Other" stays open for free text:

- **Keep longer (Recommended):** sets retention to 3650 days so `/compass:clone-old` can use old sessions.
- **Keep the default:** leaves retention at 30 days.

On a yes, run `compass retention --set 3650` (same `python3` / `python` fallback). On a no, move on; setup does not ask again. When the value is already above 30, say nothing.

### 6. Run vision capture

For NEW projects, immediately invoke `/compass:vision` - don't stop and ask. Skipping vision is the #1 cause of bloated first specs.

> "Compass infrastructure is set up. Now I'll run the vision capture to understand what you're building. A quick interview about the project goal - produces a vision document and a spec roadmap."

Pass any context already gathered during setup (the project description, anything the human said when invoking setup).

For MIGRATE mode (existing project with code/docs), ask once, through `AskUserQuestion` with exactly one question per call: "I see this project already has code and docs. How should I start?". The recommended option comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Other" stays open for free text:

- **Capture the vision retroactively (Recommended):** runs `/compass:vision` against what exists.
- **Skip to specific work:** documents it via `/compass:retroactive`.

Never put several questions in one message or one call.

Only skip vision if the human explicitly requests it.

## Output format

```markdown
## Setup Report

### Project State
New project / Existing project with N existing documents

### Installed
- [x] 13 agents copied to .claude/agents/
- [x] 4 rules files copied to .claude/rules/
- [x] .compass/ vault scaffolded
- [x] Hooks registered in .claude/settings.json
- [x] compass doctor: 0 FAIL

### Obsidian
Open `.compass/` as a vault: **Obsidian → Open folder as vault → `<project-root>/.compass/`**, then run `compass review --install` and turn on Compass Review (Settings → Community plugins) so reviews open in Obsidian

### Next Steps
1. Open `.compass/` in Obsidian
2. Approve the CLAUDE.md addition
3. Vision capture is starting - answer the questions to produce vision.md and the spec roadmap
4. After vision: create specs one at a time with `/compass:spec`
```

## Failure modes worth naming

- Reading template files into context and writing them back with the Write tool. Use Bash `cp`. The content never goes through your window.
- Writing to CLAUDE.md without approval.
- Skipping the migration table - always present line by line.
- Making strategic assumptions about the project.
- Creating documents beyond the basic scaffold.
- Modifying files outside `.compass/` and `.claude/` without approval.
- Overwriting existing agents without asking (except in `update` mode).
- Overwriting `.claude/settings.json` wholesale when registering hooks - step 2b's script reads-merges-writes; a project's own permissions or hand-added hooks must survive.
- Writing hook registration to `.claude/settings.local.json` - that file is user-owned; Compass hooks always register in `.claude/settings.json`.
