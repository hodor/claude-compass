---
name: checkup
description: Scan a Compass project for problems — missing agents, stale handoffs, unclosed tasks, vault inconsistencies, broken hooks, missing config. Reports what's wrong and how to fix it.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Bash]
when_to_use: "Use when something feels off, after a long break, before starting a sprint, or periodically as maintenance. Triggers: 'compass check', 'checkup', 'is compass set up right', 'diagnose compass'."
---

# Checkup — Compass Project Health Scanner

Scans your project's Compass installation for problems and reports them with actionable fixes. Does NOT auto-fix — reports only.

## What Gets Checked

### 1. Agent Installation

```
Check: .claude/agents/ contains all 15 Compass agents
```

| Agent | Required? |
|-------|-----------|
| spec-writer | YES |
| researcher | YES |
| reviewer | YES |
| planner | YES |
| planner-iterate | YES |
| builder | YES |
| tester | YES |
| validator | YES |
| handoff-create | YES |
| handoff-resume | YES |
| debug | YES |
| pattern-finder | YES |
| autopilot | YES |
| retroactive | YES |
| pr-describe | YES |

For each agent file found, verify:
- Has valid YAML frontmatter
- Has `name` and `description` fields
- Has `model`, `effort`, `maxTurns` fields (warn if missing)

Report:
- Missing agents
- Agents with invalid/incomplete frontmatter
- Agents that may be outdated (compare against plugin templates if accessible)

### 2. Vault Structure

```
Check: .compass/ exists with required structure
```

Required:
- [ ] `.compass/index.md`
- [ ] `.compass/active.md`
- [ ] `.compass/backlog.md`
- [ ] `.compass/meta/config.yaml`
- [ ] `.compass/meta/lessons-catalog.yaml`

Required directories:
- [ ] `.compass/specs/`
- [ ] `.compass/research/`
- [ ] `.compass/plans/`
- [ ] `.compass/decisions/`
- [ ] `.compass/lessons/`
- [ ] `.compass/handoffs/`
- [ ] `.compass/prs/`
- [ ] `.compass/.annotations/`

Report: missing files/directories.

### 3. Vault Integrity

Run the same checks as the vault-health skill:
- **Frontmatter validation** — all vault .md files have valid frontmatter
- **Wikilink check** — all `[[links]]` resolve
- **Counter consistency** — config.yaml counters are ahead of highest-numbered files
- **Orphan detection** — files not referenced by index.md

### 4. Task Hygiene

```
Check: .compass/active.md for stale or inconsistent state
```

- Tasks marked `[x]` done but no corresponding plan checkoff
- Tasks marked `[ ]` not done but commits exist for them (check git log)
- Tasks in active.md that reference plans that don't exist
- Tasks older than 14 days without progress (stale)

### 5. Handoff Freshness

```
Check: .compass/handoffs/ for stale or orphaned handoffs
```

- Handoffs with `status: active` older than 7 days — likely stale
- Handoffs referencing commits that are far behind HEAD (>20 commits)
- Handoffs that were never marked `done`

### 6. Hook Configuration

```
Check: .claude/settings.json for required Compass hooks
```

Required hooks:
- `SubagentStop` hook with `matcher: "builder"` that spawns the tester agent

Report: missing or misconfigured hooks.

### 7. Rules Installation

```
Check: .claude/rules/ contains Compass rules
```

Required:
- [ ] `.claude/rules/compass-agent-patterns.md`

### 8. Git State

```
Check: uncommitted changes in .compass/
```

- Uncommitted vault files (handoffs, specs, plans) — these are invisible to other sessions
- Unstaged annotation files

## Output Format

```markdown
## Compass Checkup Report

### Agents
- [x] 15/15 agents installed
- [ ] builder.md missing `maxTurns` field (WARN)

### Vault Structure
- [x] All required files present
- [ ] `.compass/.annotations/` missing (WARN — run bootstrap or create manually)

### Vault Integrity
- [x] Frontmatter: 12 OK, 0 FAIL
- [ ] Wikilinks: 1 broken — active.md:8 references [[SPEC-999]]
- [x] Counters: all consistent

### Task Hygiene
- [ ] TASK-003 in active.md is 21 days old with no progress (STALE)
- [x] No orphaned task references

### Handoffs
- [ ] 2026-03-12_session-2.md is still `status: active` (15 days old — STALE)
- [x] No orphaned handoffs

### Hooks
- [x] SubagentStop builder→tester hook configured
  
### Rules
- [x] compass-agent-patterns.md installed

### Git State
- [ ] 2 uncommitted files in .compass/ — commit before ending session

### Summary
- OK: 6 checks passed
- WARN: 2 warnings
- FAIL: 1 failure (broken wikilink)
- STALE: 2 items need attention

HEALTH: NEEDS ATTENTION
```

## Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **OK** | Everything is fine | None |
| **WARN** | Not broken but should be addressed | Fix when convenient |
| **FAIL** | Something is broken | Fix before continuing work |
| **STALE** | Something is outdated | Review and archive or update |

## What NOT to Do

- Don't auto-fix anything — report only, let the human decide
- Don't skip checks because "the project is small" — run them all
- Don't ignore uncommitted vault files — they're the most common source of lost context
