---
name: checkup
description: Scan a Compass project for problems - missing agents, stale handoffs, unclosed tasks, vault inconsistencies, broken hooks, missing config. Reports what's wrong and how to fix it.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Bash]
when_to_use: "Use when something feels off, after a long break, before starting a sprint, or periodically as maintenance. Triggers: 'compass check', 'checkup', 'is compass set up right', 'diagnose compass'."
---

# Checkup - Compass Project Health Scanner

Scans your project's Compass installation and reports problems with actionable fixes. Report only - never auto-fix.

## What gets checked

### 1. Agents

`.claude/agents/` should contain all 13 Compass agents: `builder`, `codebase-analyzer`, `codebase-locator`, `debug`, `pattern-finder`, `planner`, `pr-describe`, `researcher`, `reviewer`, `tester`, `validator`, `vault-analyzer`, `vault-locator`.

For each agent: valid YAML frontmatter, `name` and `description` present, `model`/`effort`/`maxTurns` present (warn if missing). Report missing agents, agents with invalid frontmatter, agents that may be outdated.

Interactive flows (spec writing, planning iteration, handoffs, autopilot, retroactive, etc.) live as skills in `.claude/skills/`, not as agents.

### 2. Vault structure

Required files: `.compass/index.md`, `.compass/active.md`, `.compass/backlog.md`, `.compass/meta/config.yaml`, `.compass/meta/lessons-catalog.yaml`.

Required directories: `specs/`, `research/`, `plans/`, `decisions/`, `lessons/`, `handoffs/`, `prs/`, `.annotations/`.

### 3. Vault integrity

Same checks as the vault-health skill: frontmatter validation, wikilink resolution, counter consistency (config.yaml ahead of highest-numbered file), orphan detection (files not referenced by index.md).

### 4. Task hygiene

In `.compass/active.md`:

- Tasks marked `[x]` done but no corresponding plan checkoff.
- Tasks marked `[ ]` but commits exist for them.
- Tasks referencing plans that don't exist.
- Tasks older than 14 days without progress (stale).

### 5. Handoff freshness

In `.compass/handoffs/`:

- Handoffs with `status: active` older than 7 days.
- Handoffs referencing commits >20 behind HEAD.
- Handoffs never marked `done`.

### 6. Hooks

`.claude/settings.json` should have a `SubagentStop` hook with `matcher: "builder"` that spawns the tester agent.

### 7. Rules

`.claude/rules/` should have: `compass-agent-patterns.md`, `compass-pipeline.md`, `session-start.md`, `wikilinks.md`.

### 8. Git state

Uncommitted vault files (handoffs, specs, plans) are invisible to other sessions. Flag them.

## Output format

```markdown
## Compass Checkup Report

### Agents
- [x] 13/13 agents installed
- [ ] builder.md missing `maxTurns` (WARN)

### Vault Structure
- [x] All required files present
- [ ] `.compass/.annotations/` missing (WARN)

### Vault Integrity
- [x] Frontmatter: 12 OK, 0 FAIL
- [ ] Wikilinks: 1 broken - active.md:8 references [[SPEC-999]]
- [x] Counters consistent

### Task Hygiene
- [ ] TASK-003 in active.md: 21 days old, no progress (STALE)
- [x] No orphaned task references

### Handoffs
- [ ] 2026-03-12_session-2.md still `status: active` (15 days, STALE)

### Hooks
- [x] SubagentStop builder→tester hook configured

### Rules
- [x] 4/4 rule files installed

### Git State
- [ ] 2 uncommitted files in .compass/ - commit before ending session

### Summary
- OK: 6 | WARN: 2 | FAIL: 1 | STALE: 2

HEALTH: NEEDS ATTENTION
```

## Severity

| Level | Meaning | Action |
|-------|---------|--------|
| OK | Everything fine | None |
| WARN | Not broken but should be addressed | Fix when convenient |
| FAIL | Broken | Fix before continuing |
| STALE | Outdated | Review, archive, or update |

## Failure modes worth naming

- Auto-fixing instead of reporting. The human decides.
- Skipping checks because "the project is small."
- Ignoring uncommitted vault files - they are the most common source of lost context.
