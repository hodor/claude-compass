---
name: bootstrap
description: Set up the Compass development workflow in a project. Creates the .compass/ vault, installs full-featured agents to .claude/agents/, and proposes CLAUDE.md additions.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
when_to_use: "Use when the user wants to set up Compass in a project, update Compass agents, or install Compass agents. Triggers: 'set up compass', 'initialize compass', 'bootstrap compass', 'install compass', 'update compass'."
argument-hint: "[new | migrate | update]"
---

# Bootstrap — Compass Project Setup

=== CRITICAL: NEVER WRITE TO CLAUDE.md WITHOUT HUMAN APPROVAL ===
=== CRITICAL: NEVER SKIP MIGRATION APPROVAL — HUMAN APPROVES LINE BY LINE ===
=== CRITICAL: NEVER MAKE STRATEGIC DECISIONS ABOUT THE PROJECT ===

## What This Skill Does

1. Detects project state (new vs existing)
2. Installs Compass agents from the plugin to `.claude/agents/` (full-featured versions with initialPrompt, permissionMode, etc.)
3. Creates the `.compass/` vault structure
4. Proposes CLAUDE.md additions (human approves before writing)
5. Creates SPEC-001 documenting the project setup

## Modes

- **`/compass:bootstrap new`** — Full setup: agents + rules + hooks + vault + SPEC-001 + CLAUDE.md
- **`/compass:bootstrap migrate`** — Full setup for a project with existing docs
- **`/compass:bootstrap update`** — Quick refresh: overwrite agents + rules + hooks only. Does NOT touch the vault, CLAUDE.md, or existing specs. Use this to get the latest Compass agents during development.

## Protocol

### Step 0: Check for Update Mode

If the argument is `update`:
1. Skip project state detection
2. Go directly to Step 2 (Install Agents, Rules, and Skills) — overwrite without asking
3. Go to Step 2b (Configure Hooks) — overwrite without asking
4. Report what was updated
5. STOP — do not scaffold vault, create specs, or touch CLAUDE.md

### Step 1: Detect Project State

```
Glob: .compass/ — does the vault already exist?
Glob: .claude/agents/ — are Compass agents already installed?
Glob: *.md, docs/**/*.md — existing documentation?
Glob: CLAUDE.md — existing project instructions?
```

**New project** = no `.compass/` directory exists
**Existing project** = `.compass/` exists OR significant existing docs to migrate
**Agents already installed** = `.claude/agents/` contains Compass agent files

### Step 2: Install Agents and Rules

=== CRITICAL: USE BASH cp COMMANDS ONLY — DO NOT READ THE TEMPLATE FILES ===

Find the Compass plugin, then use Bash to copy files. Do NOT use the Read tool on any template file. Do NOT use the Write tool. ONLY use Bash.

```bash
# Step 1: Find the plugin root
PLUGIN_ROOT=$(find / -path "*/compass/plugin/.claude-plugin/plugin.json" -type f 2>/dev/null | head -1 | sed 's|/.claude-plugin/plugin.json||')

# If not found, try common locations
if [ -z "$PLUGIN_ROOT" ]; then
  for p in "$HOME/.claude/plugins/compass/plugin" "F:/claude/plugins/compass/plugin"; do
    [ -f "$p/.claude-plugin/plugin.json" ] && PLUGIN_ROOT="$p" && break
  done
fi

echo "Plugin root: $PLUGIN_ROOT"

# Step 2: Copy agents
mkdir -p .claude/agents
cp "$PLUGIN_ROOT/templates/agents/"*.md .claude/agents/
echo "Agents copied: $(ls .claude/agents/*.md | wc -l) files"

# Step 3: Copy rules
mkdir -p .claude/rules
cp "$PLUGIN_ROOT/templates/rules/"*.md .claude/rules/
echo "Rules copied: $(ls .claude/rules/*.md | wc -l) files"

# Step 4: Copy skills (makes project self-contained — no plugin needed after this)
for skill_dir in "$PLUGIN_ROOT/skills/"*/; do
  skill_name=$(basename "$skill_dir")
  mkdir -p ".claude/skills/$skill_name"
  cp "$skill_dir"*.md ".claude/skills/$skill_name/"
done
echo "Skills copied: $(ls -d .claude/skills/*/ | wc -l) directories"
```

After this, the project is fully self-contained. Anyone who clones the repo gets agents, skills, and rules — no plugin install needed.

Run this as a single Bash command. Verify the output shows 15 agents and 1 rules file. If the plugin can't be found, ask the human for the path.

If agents are already installed, ask the human before overwriting.

### Step 2b: Configure Hooks

Set up the `SubagentStop` hook in `.claude/settings.json` (or `.claude/settings.local.json`) so that the tester agent runs automatically after the builder finishes:

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
  }
}
```

If the file already exists, merge the hooks into the existing configuration. Ask the human before overwriting any existing hooks.

### Step 3A: New Project — Scaffold Vault

Create the complete vault structure:

```
.compass/
  index.md
  active.md
  backlog.md
  vision.md               # created by /compass:vision (NOT by bootstrap)
  .annotations/           # sidecar annotations (see annotate skill)
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

Note: bootstrap does NOT create `vision.md` — the human runs `/compass:vision` after bootstrap. Same principle as specs (bootstrap doesn't create them either).

Initialize `config.yaml`:
```yaml
counters:
  spec: 1
  adr: 1
  task: 1
  plan: 1
```

Initialize `lessons-catalog.yaml`:
```yaml
lessons: []
```

Create a minimal `index.md` and empty `active.md` and `backlog.md`.

The `index.md` should have a "Vision" section at the top with `_Run /compass:vision to capture._` as a placeholder.

Do NOT create vision.md — that's `/compass:vision`'s job.
Do NOT create any specs — that's `/compass:spec`'s job.

### Step 3B: Existing Project — Migrate

1. **Inventory**: Scan for existing documentation, TODOs, specs, decisions
2. **Propose migration table**:
   ```
   | Source | Destination | Action |
   |--------|------------|--------|
   | README.md#Architecture | SPEC-001-... | Extract to spec |
   | TODO.md items | active.md / backlog.md | Migrate tasks |
   | docs/decisions/ | decisions/ | Rename to ADR-NNN format |
   ```
3. **Human approves line by line** — never execute without approval
4. Execute approved migrations
5. Update `index.md`

### Step 4: Propose CLAUDE.md Addition

Draft a Compass section for CLAUDE.md. Keep it short — rules, not essays:

```markdown
## Compass

`.compass/` is the knowledge vault. Open it in Obsidian for graph view.

**Pipeline:** Vision → Spec → Research → Plan → Build → Test → Validate. Don't skip phases.

**Key rules:**
- Vision is captured ONCE per project (or per major pivot). It produces a spec roadmap. Run `/compass:vision` at the start.
- Specs are SINGLE-PROBLEM. ONE spec = ONE problem. If you write "and also", split into two specs.
- Specs are about the NEED, not the solution. No implementation decisions in specs.
- Specs start as `draft`. Nothing happens until the human approves.
- Compass agents are available for research, planning, building, testing, and validation.
- All code changes require tests.
- `git add <file>` — never `-A` or `.`

**Start here:** `.compass/index.md` (map) and `.compass/active.md` (tasks).
**Help:** `/compass:guide` (workflow) or `/compass:checkup` (health).
```

Present this to the human. Write ONLY after they approve.

### Step 5: Verify Installation

After scaffolding, verify:
- [ ] `.claude/agents/` contains all Compass agent files
- [ ] `.compass/meta/config.yaml` exists with valid counters
- [ ] `.compass/meta/lessons-catalog.yaml` exists
- [ ] `.compass/index.md` exists
- [ ] `.compass/active.md` exists

### Step 6: Run Vision Capture

Bootstrap is done with infrastructure. For NEW projects, IMMEDIATELY run the vision capture — do not stop and ask. New users won't know what to do next, and skipping vision is the #1 cause of bloated first specs.

Tell the human:

> "Compass infrastructure is set up. Now I'll run the vision capture to understand what you're building. This is a quick interview about the project goal — answers will produce a vision document and a roadmap of specs."

Then immediately invoke the `/compass:vision` skill. Pass any context already gathered during bootstrap (e.g., the project description from migration analysis, or anything the human said when invoking bootstrap).

For MIGRATE mode (existing project with code/docs): the vision may already exist implicitly. Ask once:
> "I see this project already has code and docs. Should I capture the vision retroactively from what exists (run `/compass:vision`), or skip straight to documenting specific work via `/compass:retroactive`?"

Only skip vision if the human explicitly requests it.

## Output Format

```markdown
## Bootstrap Report

### Project State
New project / Existing project with N existing documents

### Agents Installed
- [x] 15 agents copied to .claude/agents/
- [x] 1 rules file copied to .claude/rules/
- [x] .compass/ vault scaffolded
- [x] Hooks configured

### Obsidian

Open `.compass/` as an Obsidian vault:
  **Obsidian → Open folder as vault → `<project-root>/.compass/`**

### Next Steps
1. Open `.compass/` in Obsidian
2. Approve the CLAUDE.md addition
3. Vision capture is starting now — answer the questions to produce vision.md and the spec roadmap
4. After vision: create specs one at a time with `/compass:spec`
```

## Know Your Failure Modes

You WILL be tempted to:
- Read all the agent template files into your context and then use Write to recreate them — DO NOT do this. Use Bash `cp` to copy files. NEVER use the Read tool on template files. NEVER use the Write tool for template files. The content must never pass through your context window.
- Write to CLAUDE.md without asking — always present and wait for approval
- Skip the migration table for existing projects — always present it line by line
- Make assumptions about what the project does — ask the human
- Create more documents than the basic scaffold — keep it minimal, the human builds from here

## What NOT to Do

- Don't make strategic decisions about the project
- Don't write lengthy CLAUDE.md sections — keep it concise
- Don't skip human approval for migrations or CLAUDE.md changes
- Don't create documents beyond the basic scaffold without human input
- Don't assume what the project is about — ask if unclear
- Don't modify existing files outside `.compass/` and `.claude/` without explicit approval
- Don't overwrite existing agents without asking

=== REMINDER: NEVER WRITE TO CLAUDE.md WITHOUT HUMAN APPROVAL ===
