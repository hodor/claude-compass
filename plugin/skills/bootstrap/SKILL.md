---
name: bootstrap
description: Set up the Compass development workflow in a project. Creates the .compass/ vault, installs full-featured agents to .claude/agents/, and proposes CLAUDE.md additions.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
when_to_use: "Use when the user wants to set up Compass in a project, update Compass agents, or install Compass agents. Triggers: 'set up compass', 'initialize compass', 'bootstrap compass', 'install compass', 'update compass'."
argument-hint: "[new | migrate | update]"
---

# Bootstrap - Compass Project Setup

Sets up Compass in a project:

1. Detects project state (new vs existing).
2. Installs full-featured agents from the plugin to `.claude/agents/`.
3. Creates the `.compass/` vault.
4. Proposes CLAUDE.md additions - human approves before any write.
5. Kicks off vision capture for new projects.

## Modes

- `/compass:bootstrap new` - full setup: agents + rules + hooks + vault + CLAUDE.md.
- `/compass:bootstrap migrate` - full setup for a project with existing docs.
- `/compass:bootstrap update` - refresh agents + rules + hooks only. Does NOT touch the vault, CLAUDE.md, or specs.

## Protocol

### 0. Update mode shortcut

If the argument is `update`:

1. Skip state detection.
2. **Pull the latest plugin source from GitHub, never from the local install folder.** The local install can be stale or hand-edited; the GitHub repository is the canonical source for updates. Read `.compass/meta/plugin.yaml` `repository:` field (or use `--repository <url>` override). Clone shallow to a temp directory:

   ```bash
   TMP_DIR="$(mktemp -d 2>/dev/null || mktemp -d -t compass-update)"
   git clone --depth=1 "$REPOSITORY" "$TMP_DIR/clone"
   PLUGIN_SOURCE="$TMP_DIR/clone/plugin"
   ```

   If the project's `plugin.yaml` is missing (project bootstrapped before this feature) and no `--repository` override was passed, ask the human for the repository URL.

3. Read the cloned source's `plugin/.claude-plugin/plugin.json` `version` field. Read the project's `.compass/meta/plugin.yaml` `plugin.version`. If they match, ask the human whether to force-update anyway. If GitHub source is newer, proceed.
4. Go to step 2 (install agents/rules/skills) using `$PLUGIN_SOURCE` from the clone. Overwrite without asking.
5. Go to step 2b (hooks) using the cloned `$PLUGIN_SOURCE/hooks/hooks.json`. Overwrite without asking.
6. Update `.compass/meta/plugin.yaml`: bump `version` to the cloned version, set `installed_at: <today>`, set `installed_mode: update`. Leave `source:` pointing at whatever it pointed at before (it is documentation of the original install, not the update channel).
7. Remove the temp clone: `rm -rf "$TMP_DIR"`.
8. Report what changed (which files, version delta).
9. Stop. Don't scaffold vault, create specs, or touch CLAUDE.md.

**Why always GitHub:** the local install at `source:` is fine as the initial-install reference but is unreliable as the update channel. The dev's local copy may be stale, hand-edited, or on a branch. GitHub is the single source of truth for releases. This matches the principle in [[LESSON-no-agent-bookkeeping]]: trust the authoritative remote, not a cached local copy.

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

# The PostToolUse hook runs `python3 .claude/cli/compass sync`. Verify python3 exists.
if ! command -v python3 >/dev/null 2>&1; then
  echo "WARNING: python3 not found on PATH. The vault-sync hook will be a silent no-op until python3 is installed. The CLI never blocks writes (it can only exit 0/1), so nothing breaks - sync just will not run. Install python3, or run 'python3 .claude/cli/compass sync' manually."
fi
```

Run as one Bash call. Verify 13 agents, 4 rules files, and that `.claude/cli/compass` exists. If the plugin can't be found, ask the human for the path.

After this, the project is self-contained - anyone who clones gets agents, skills, and rules without installing the plugin.

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

This file is the single source of truth for "where did this project's Compass install come from." Future `/compass:bootstrap update` runs read it directly; no filesystem rediscovery. `/compass:checkup` can diff the recorded version against the source's current version to detect drift.

In `update` mode, overwrite without asking. In other modes, if agents are already installed, ask once before overwriting.

### 2b. Hooks and permissions

Hooks install to `.claude/hooks/hooks.json`, which Claude Code auto-loads for the project. Permissions go in `.claude/settings.json`.

```bash
# Hooks: PostToolUse runs `compass sync` as a command; Stop runs extract-lessons;
# SubagentStop captures subagent reports. Copied verbatim from the plugin.
mkdir -p .claude/hooks
cp "$PLUGIN_ROOT/hooks/hooks.json" .claude/hooks/hooks.json
echo "Hooks installed -> .claude/hooks/hooks.json"
```

The PostToolUse hook runs `python3 "$CLAUDE_PROJECT_DIR/.claude/cli/compass" sync --hook`, resolving the CLI copied in step 2 via the project-root env var the hook runtime sets. It self-filters non-vault and generated-output writes and never exits 2, so it can neither loop nor block an edit.

Then write the permission allowlist to `.claude/settings.json` (or `.claude/settings.local.json`):

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

If `.claude/hooks/hooks.json` or `.claude/settings.json` already exists, merge. Ask before overwriting existing hooks or permissions.

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

Bootstrap does NOT create `vision.md` - `/compass:vision` does that. Bootstrap does NOT create specs - `/compass:spec` does that. Bootstrap does NOT create a counter file - numbering is computed JIT from the filesystem.

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

Present and wait for approval. Write only after approval.

### 5. Verify

- [ ] `.claude/agents/` has 9 Compass agents.
- [ ] `.claude/rules/` has 4 rule files.
- [ ] `.compass/meta/lessons-catalog.yaml` exists.
- [ ] `.compass/meta/plugin.yaml` exists with `name`, `version`, `source`, `installed_at`.
- [ ] `.compass/index.md` exists.
- [ ] `.compass/active.md` exists.

### 6. Run vision capture

For NEW projects, immediately invoke `/compass:vision` - don't stop and ask. Skipping vision is the #1 cause of bloated first specs.

> "Compass infrastructure is set up. Now I'll run the vision capture to understand what you're building. A quick interview about the project goal - produces a vision document and a spec roadmap."

Pass any context already gathered during bootstrap (the project description, anything the human said when invoking bootstrap).

For MIGRATE mode (existing project with code/docs), ask once:

> "I see this project already has code and docs. Should I capture the vision retroactively from what exists (run `/compass:vision`), or skip straight to documenting specific work via `/compass:retroactive`?"

Only skip vision if the human explicitly requests it.

## Output format

```markdown
## Bootstrap Report

### Project State
New project / Existing project with N existing documents

### Installed
- [x] 13 agents copied to .claude/agents/
- [x] 4 rules files copied to .claude/rules/
- [x] .compass/ vault scaffolded
- [x] Hooks configured

### Obsidian
Open `.compass/` as a vault: **Obsidian → Open folder as vault → `<project-root>/.compass/`**

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
