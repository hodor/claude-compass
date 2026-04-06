---
name: bootstrap
description: Set up the Compass development workflow in a project. Creates the .compass/ vault, installs full-featured agents to .claude/agents/, and proposes CLAUDE.md additions.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
when_to_use: "Use when the user wants to set up Compass in a project, initialize a .compass/ vault, or install Compass agents. Triggers: 'set up compass', 'initialize compass', 'bootstrap compass', 'install compass'."
argument-hint: "[new | migrate]"
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

## Protocol

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
```

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

Initialize `config.yaml`:
```yaml
counters:
  spec: 2    # 1 is used by SPEC-001
  adr: 1
  task: 1
  plan: 1
```

Initialize `lessons-catalog.yaml`:
```yaml
lessons: []
```

Create `SPEC-001-project-setup.md` in `specs/` documenting:
- What the project is (ask the human if unclear)
- Why Compass is being adopted
- Initial structure decisions

Create initial tasks in `active.md` and link everything in `index.md`.

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

Draft a Compass section for CLAUDE.md:

```markdown
## Compass

This project uses the Compass development workflow. The `.compass/` directory contains the project's knowledge vault.

- **Start here**: `.compass/index.md` (project map) and `.compass/active.md` (current tasks)
- **Workflow**: Spec -> Research -> Plan -> Tasks -> Build -> Validate
- **Testing**: All code changes require tests and a full test suite run
- **Decisions**: Significant choices are recorded as ADRs in `.compass/decisions/`
- **Lessons**: Surprising discoveries go in `.compass/lessons/`
```

Present this to the human. Write ONLY after they approve.

### Step 5: Verify Installation

After scaffolding, verify all required artifacts exist:
- [ ] `.claude/agents/` contains all Compass agent files
- [ ] `.compass/meta/config.yaml` exists with valid counters
- [ ] `.compass/meta/lessons-catalog.yaml` exists
- [ ] `.compass/index.md` has links to all documents
- [ ] `.compass/active.md` has initial tasks
- [ ] At least one spec exists (SPEC-001 at minimum)

## Output Format

```markdown
## Bootstrap Report

### Project State
New project / Existing project with N existing documents

### Agents Installed
- [x] spec-writer.md
- [x] researcher.md
- [x] reviewer.md
- ... (all agents)

### Vault Structure
- [x] .compass/ created
- [x] config.yaml initialized
- [x] SPEC-001 created
- [x] index.md populated

### Proposed CLAUDE.md Addition
<the proposed text — awaiting approval>

### Next Steps
1. Review and approve CLAUDE.md addition
2. Review SPEC-001
3. Start using Compass: run /spec-writer to create your first spec
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
