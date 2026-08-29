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

### 1. Install (`compass doctor`)

Run `compass doctor` first. Its six checks are install-drift checks - whether the plugin landed the way `/compass:setup` or `/compass:update` intended - not vault content: `plugin.yaml` has a version, hooks are registered in a settings file Claude Code actually reads (plus the informational `TeammateIdle` row), `.claude/cli/` has a module for every command `maincli.py` declares, `.claude/agents/` is present and non-empty, `.claude/skills/` is present and non-empty, `.compass/meta/lessons-catalog.yaml` exists. Report its table verbatim under Install; a FAIL row already names its own fix command, so don't re-derive one.

### 2. Agents

Doctor's `agents` and `CLI completeness` rows (Install, above) already confirm `.claude/agents/` is present, non-empty, and that every command the CLI declares has a module. This section goes further: it names all 13 Compass agents - `builder`, `codebase-analyzer`, `codebase-locator`, `debug`, `pattern-finder`, `planner`, `pr-describe`, `researcher`, `reviewer`, `tester`, `validator`, `vault-analyzer`, `vault-locator` - and validates each individually.

For each agent: valid YAML frontmatter, `name` and `description` present, `maxTurns` present (warn if missing). Validate `model:`/`effort:` against the resolved policy: run `compass models` and compare each agent's frontmatter to its roster row (an agent resolving to `inherit` carries no `model:` line at all). A mismatch means the install predates the policy or `.compass/meta/models.yaml` changed since the last apply; the fix is `compass apply-models`. Report missing agents, agents with invalid frontmatter, agents that may be outdated.

Interactive flows (spec writing, planning iteration, handoffs, autopilot, retroactive, etc.) live as skills in `.claude/skills/`, not as agents.

### 3. Vault structure

Required files: `.compass/index.md`, `.compass/active.md`, `.compass/backlog.md`, `.compass/meta/lessons-catalog.yaml`, `.compass/meta/plugin.yaml`.

Required directories: `specs/`, `research/`, `plans/`, `decisions/`, `lessons/`, `handoffs/`, `prs/`, `.annotations/`.

### 4. Vault integrity

Same checks as the vault-health skill: frontmatter validation, wikilink resolution, orphan detection (files not referenced by index.md). Counter consistency check removed per [[ADR-003-drop-counter-file-jit-compute]].

### 5. Task hygiene

In `.compass/active.md`:

- Tasks marked `[x]` still present - the sync sweep should have moved them to `archive/done.md`; run `compass sweep` to see what lingers and why.
- Tasks marked `[ ]` but commits exist for them.
- Tasks referencing plans that don't exist.
- Tasks older than 14 days without progress (stale).

In `.compass/archive/done.md`: swept tasks with no corresponding plan checkoff.

### 6. Handoff freshness

In `.compass/handoffs/`:

- Handoffs with `status: active` older than 7 days.
- Handoffs referencing commits >20 behind HEAD.
- Handoffs never marked `done`.

### 7. Hooks

Delegates entirely to `compass doctor`'s hook-registration check, reported under Install (section 1): the required `PostToolUse`, `Stop`, and `SubagentStop` registrations in a settings file, plus the informational `TeammateIdle` row. Nothing here duplicates that check.

### 8. Rules

`.claude/rules/` should have: `compass-agent-patterns.md`, `compass-pipeline.md`, `session-start.md`, `wikilinks.md`.

### 9. Git state

Uncommitted vault files (handoffs, specs, plans) are invisible to other sessions. Flag them.

## Output format

```markdown
## Compass Checkup Report

### Install (compass doctor)
- [x] plugin.yaml: version 0.4.1
- [x] hook registration: PostToolUse, Stop, SubagentStop all registered
- [ ] hook registration (TeammateIdle): not registered (WARN)
- [x] CLI completeness: 24 commands, all modules present
- [x] agents: 13 present
- [x] skills: 19 present
- [x] lessons-catalog.yaml: present

### Agents
- [x] 13/13 agents installed
- [ ] builder.md missing `maxTurns` (WARN)
- [ ] vault-locator.md has `model: sonnet`, table resolves haiku - run `compass apply-models` (WARN)

### Vault Structure
- [x] All required files present
- [ ] `.compass/.annotations/` missing (WARN)

### Vault Integrity
- [x] Frontmatter: 12 OK, 0 FAIL
- [ ] Wikilinks: 1 broken - active.md:8 references [[SPEC-999]]

### Task Hygiene
- [ ] TASK-003 in active.md: 21 days old, no progress (STALE)
- [x] No orphaned task references

### Handoffs
- [ ] 2026-03-12_session-2.md still `status: active` (15 days, STALE)

### Hooks
- see Install above (compass doctor)

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
