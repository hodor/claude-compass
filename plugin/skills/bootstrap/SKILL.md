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
2. Go to step 2 (install agents/rules/skills) - overwrite without asking.
3. Go to step 2b (hooks) - overwrite without asking.
4. Report what changed.
5. Stop. Don't scaffold vault, create specs, or touch CLAUDE.md.

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
```

Run as one Bash call. Verify 9 agents and 5 rules files. If the plugin can't be found, ask the human for the path.

After this, the project is self-contained - anyone who clones gets agents, skills, and rules without installing the plugin.

In `update` mode, overwrite without asking. In other modes, if agents are already installed, ask once before overwriting.

### 2b. Hooks and permissions

Set up `.claude/settings.json` (or `.claude/settings.local.json`):

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "builder",
        "hooks": [
          {
            "type": "agent",
            "prompt": "You are the Compass tester agent. The builder just finished implementing code. Run `git diff` to see the changes, then read .claude/agents/tester.md for your full instructions. Write adversarial tests and run the full test suite.",
            "model": "claude-sonnet-4-6",
            "statusMessage": "Running tester agent..."
          }
        ]
      }
    ]
  },
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

Compass agents use `permissionMode: bypassPermissions`, so they bypass these prompts entirely - the allowlist is the safety net for everything else.

If the file already exists, merge. Ask before overwriting existing hooks or permissions.

### 3A. New project - scaffold the vault

```
.compass/
  index.md
  active.md
  backlog.md
  .annotations/           # sidecar annotations
  meta/
    config.yaml
    lessons-catalog.yaml
  specs/
  research/
  plans/
  decisions/
  lessons/
  handoffs/
  prs/
  archive/
```

Bootstrap does NOT create `vision.md` - `/compass:vision` does that. Bootstrap does NOT create specs - `/compass:spec` does that.

`config.yaml`:
```yaml
counters:
  spec: 1
  adr: 1
  task: 1
  plan: 1
```

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
- [ ] `.claude/rules/` has 5 rule files.
- [ ] `.compass/meta/config.yaml` exists with valid counters.
- [ ] `.compass/meta/lessons-catalog.yaml` exists.
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
- [x] 9 agents copied to .claude/agents/
- [x] 5 rules files copied to .claude/rules/
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
