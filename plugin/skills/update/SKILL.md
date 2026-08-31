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
# Agents, rules, skills, slash commands
mkdir -p .claude/agents .claude/rules .claude/commands
cp "$SRC/templates/agents/"*.md .claude/agents/
cp "$SRC/templates/rules/"*.md  .claude/rules/
cp "$SRC/templates/commands/"*.md .claude/commands/ 2>/dev/null
for d in "$SRC/skills/"*/; do
  n=$(basename "$d"); mkdir -p ".claude/skills/$n"; cp "$d"*.md ".claude/skills/$n/"
done
# Remove skills Compass has renamed or retired, so their stale command does not
# linger. ONLY these named Compass skills are removed - user-authored project
# skills in .claude/skills/ are never touched. Add a name here when a Compass
# skill is renamed or deleted (e.g. bootstrap -> setup; tree became the /tree
# command file).
for retired in bootstrap taxonomize tree; do
  [ -d ".claude/skills/$retired" ] && rm -rf ".claude/skills/$retired" && echo "removed retired Compass skill: $retired"
done

# The compass CLI the PostToolUse/Stop/SubagentStop hooks run
rm -rf .claude/cli
cp -r "$SRC/cli" .claude/cli

# Hooks manifest. This file is the source of truth the next step translates
# from - Claude Code itself never reads it directly (see step 5).
mkdir -p .claude/hooks
cp "$SRC/hooks/hooks.json" .claude/hooks/hooks.json

echo "Updated: $(ls .claude/agents/*.md | wc -l) agents, $(ls -d .claude/skills/*/ | wc -l) skills, $(ls .claude/cli/commands/*.py | wc -l) CLI modules, hooks.json"

# The hook runs `python3` if present else `python`; verify one exists.
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "WARNING: neither python3 nor python on PATH. The vault-sync hook will be a silent no-op (it never blocks writes) until Python 3 is installed."
fi

# Write the resolved model policy into the refreshed agents. Rewrites only the
# model:/effort: frontmatter of the 13 Compass agent files, honoring the
# project override in .compass/meta/models.yaml; any other file in
# .claude/agents/ is user-authored and never touched.
if command -v python3 >/dev/null 2>&1; then
  python3 .claude/cli/compass apply-models
elif command -v python >/dev/null 2>&1; then
  python .claude/cli/compass apply-models
fi
```

### 4b. Re-apply project-local overlays

```bash
if command -v python3 >/dev/null 2>&1; then PYBIN=python3; else PYBIN=python; fi
"$PYBIN" .claude/cli/compass overlay --apply
```

Step 4 replaced every shipped agent, rule, and skill; this appends back the project's own additions from `.compass/meta/local/` (ADR-020). Report what it names, including any ORPHAN line - an overlay whose target is no longer installed. `CLAUDE.md` is never touched by any step here.

### 5. Register hooks in `.claude/settings.json`

`.claude/hooks/hooks.json`, just copied, is a manifest - Claude Code loads hooks only from a settings file's `hooks` key or a registered plugin, never from a bare `hooks.json` on disk. Translate the manifest into `.claude/settings.json`, merging into whatever is already there rather than overwriting it: preserve unrelated top-level keys (`permissions`, etc.) and any non-Compass hook entries a project has added by hand. Never write hook registration to `.claude/settings.local.json` - that file is user-owned.

```bash
if command -v python3 >/dev/null 2>&1; then PYBIN=python3; else PYBIN=python; fi
"$PYBIN" - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path(".claude/hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]
settings_path = Path(".claude/settings.json")
settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
hooks = settings.setdefault("hooks", {})

def is_compass_command(text):
    return "compass" in (text or "")

def is_compass_group(group):
    return any(is_compass_command(h.get("command")) for h in group.get("hooks", []))

def clean_group(group, matcher_override=None):
    cleaned = dict(group)
    if matcher_override is not None:
        cleaned["matcher"] = matcher_override
    cleaned["hooks"] = [{k: v for k, v in h.items() if k != "if"} for h in group.get("hooks", [])]
    return cleaned

translated = {}
posttool = manifest.get("PostToolUse") or []
if posttool:
    # The manifest splits PostToolUse three ways (Write/Edit/MultiEdit) because its
    # "if" field cannot express boolean OR. The settings schema carries no "if"
    # field, so the three collapse into one matcher group.
    translated["PostToolUse"] = [clean_group(posttool[0], "Write|Edit|MultiEdit")]
for event in manifest:
    if event != "PostToolUse":
        translated[event] = [clean_group(g) for g in manifest[event]]

for event, new_groups in translated.items():
    kept = [g for g in hooks.get(event, []) if not is_compass_group(g)]
    hooks[event] = kept + new_groups

settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
print("Hooks registered in .claude/settings.json:", ", ".join(sorted(translated)))
PY
```

Re-running this is idempotent: it replaces only the hook groups it previously wrote (any group whose commands mention `compass`) and leaves everything else in `settings.json` untouched.

### 6. Record the new version

Update `.compass/meta/plugin.yaml`: set `version` to the clone's version, `commit: $(git -C "$TMP/clone" rev-parse HEAD)`, `installed_at: <today>`, `installed_mode: update`. Preserve `repository:` and `source:` (the latter documents the original install, not the update channel). If `plugin.yaml` does not exist, create it with the fields from [[setup]] step 2's template.

`commit:` is the sha gate `compass self-update` compares against `git ls-remote` at every session start - after this update lands, the install keeps itself current automatically (SessionStart hook, mandatory per SPEC-020) and this skill is only needed to force a refresh or repair a broken install.

### 7. Verify with `compass doctor`, clean up, and report

```bash
if command -v python3 >/dev/null 2>&1; then
  python3 .claude/cli/compass doctor
else
  python .claude/cli/compass doctor
fi
rm -rf "$TMP"
```

Report: version delta (old -> new), counts of files refreshed, whether the python check passed, and doctor's table. A WARN or FAIL row means the update landed only partway - name the failing check and the fix command doctor prints, rather than reporting the update as clean.

### 8. Nothing to restart

`.claude/settings.json`'s `hooks` key reloads live in a running session, so the `compass sync`, `compass capture-check`, and `compass capture-signal` hooks registered in step 5 take effect on the next matching event without restarting. Agents are also hot-reloaded: the refreshed `.claude/agents/` and their applied model policy are live immediately. Re-running `compass apply-models` after editing `.compass/meta/models.yaml` also takes effect without a restart.

## What this does NOT do

- Touch the `.compass/` vault (specs, plans, research, lessons, index). Only `.compass/meta/plugin.yaml` is updated, and `.compass/meta/local/` is read but never written.
- Modify `CLAUDE.md`. A project's own instructions are its own; nothing in Compass reads, writes, or moves that file.
- Run vision/spec scaffolding. That is `/compass:setup` territory.

## Failure modes worth naming

- Copying from a local install instead of the clone - defeats the point. Every `cp` source above is `$SRC` (the clone).
- Forgetting the CLI or hooks copy - then the new CLI-wrapper skills call a `compass` binary that is not there, and vault sync silently stops. Both are non-negotiable parts of step 4.
- Overwriting `.claude/settings.json` instead of merging - destroys a project's own permissions or hand-added hooks. Step 5's script reads-merges-writes; never replace the file wholesale.
- Writing hook registration to `.claude/settings.local.json` - that file is user-owned; Compass hooks always register in `.claude/settings.json`.
- Skipping step 7's `compass doctor` run and reporting the update as clean anyway - a FAIL there is exactly the class of drift this step exists to catch before the human finds out the hard way.
