---
name: update
description: Update an existing Compass install in this project from GitHub - refreshes agents, rules, skills, the compass CLI, and hooks. Pulls from the canonical git repository, never from a local copy. Does not touch the .compass vault.
version: 1.0.0
allowed-tools: [Read, Write, Bash]
argument-hint: "[--repository <url>]"
when_to_use: "Use to pull the latest Compass plugin into a project that already has it installed. Triggers: 'update compass', 'compass update', 'pull the latest compass'. For first-time setup use /compass:setup instead."
---

# /compass:update - Update a Compass install from GitHub

Refreshes the installed plugin files in `.claude/` (agents, rules, skills, the `compass` CLI, hooks) from the canonical GitHub repository. The `.compass/` vault is never touched.

**Always pulls from git, never from a local install folder.** A developer's local copy may be stale, hand-edited, or on a branch; the repository is the single source of truth for releases. The whole update copies from the clone - no filesystem rediscovery of a local plugin.

## Protocol

### 1. Resolve the repository

Read `.compass/meta/plugin.yaml` `repository:`. If `--repository <url>` was passed, use that instead. If neither is available, ask the human for the repository URL and stop until provided.

### 2. Clone shallow to a temp directory

```bash
REPO="<resolved repository url>"
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t compass-update)"
git clone --depth=1 "$REPO" "$TMP/clone"
SRC="$TMP/clone/plugin"
[ -f "$SRC/.claude-plugin/plugin.json" ] || { echo "ERROR: clone has no plugin at $SRC"; exit 1; }
```

### 3. Report the version delta

Read `$SRC/.claude-plugin/plugin.json` `version` and the project's `.compass/meta/plugin.yaml` `plugin.version`. If equal, tell the human and ask whether to force-refresh anyway. If the clone is newer, proceed.

### 4. Copy everything from the clone (one Bash call)

```bash
# Agents, rules, skills
mkdir -p .claude/agents .claude/rules
cp "$SRC/templates/agents/"*.md .claude/agents/
cp "$SRC/templates/rules/"*.md  .claude/rules/
for d in "$SRC/skills/"*/; do
  n=$(basename "$d"); mkdir -p ".claude/skills/$n"; cp "$d"*.md ".claude/skills/$n/"
done
# Remove installed skills that no longer exist in the source (handles a renamed
# or deleted skill, e.g. bootstrap -> setup, so no stale command lingers).
for existing in .claude/skills/*/; do
  n=$(basename "$existing")
  [ -d "$SRC/skills/$n" ] || rm -rf "$existing"
done

# The compass CLI the PostToolUse hook runs
rm -rf .claude/cli
cp -r "$SRC/cli" .claude/cli

# Hooks (PostToolUse sync command + Stop/SubagentStop capture)
mkdir -p .claude/hooks
cp "$SRC/hooks/hooks.json" .claude/hooks/hooks.json

echo "Updated: $(ls .claude/agents/*.md | wc -l) agents, $(ls -d .claude/skills/*/ | wc -l) skills, $(ls .claude/cli/commands/*.py | wc -l) CLI modules, hooks.json"

# The hook runs `python3` if present else `python`; verify one exists.
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "WARNING: neither python3 nor python on PATH. The vault-sync hook will be a silent no-op (it never blocks writes) until Python 3 is installed."
fi
```

### 5. Record the new version

Update `.compass/meta/plugin.yaml`: set `version` to the clone's version, `installed_at: <today>`, `installed_mode: update`. Preserve `repository:` and `source:` (the latter documents the original install, not the update channel). If `plugin.yaml` does not exist, create it with the fields from [[setup]] step 2's template.

### 6. Clean up and report

```bash
rm -rf "$TMP"
```

Report: version delta (old -> new), counts of files refreshed, and whether the python check passed.

### 7. Remind to restart

Hooks load at session start, so the refreshed `.claude/hooks/hooks.json` (and thus the `compass sync` command hook) takes effect only after a restart. Tell the human to restart this session. After restart, a vault write should sync silently at ~0 agent tokens.

## What this does NOT do

- Touch the `.compass/` vault (specs, plans, research, lessons, index). Only `.compass/meta/plugin.yaml` is updated.
- Modify `CLAUDE.md`.
- Run vision/spec scaffolding. That is `/compass:setup` territory.

## Failure modes worth naming

- Copying from a local install instead of the clone - defeats the point. Every `cp` source above is `$SRC` (the clone).
- Forgetting the CLI or hooks copy - then the new CLI-wrapper skills call a `compass` binary that is not there, and vault sync silently stops. Both are non-negotiable parts of step 4.
- Not restarting - the new hooks will not load until the session restarts.
