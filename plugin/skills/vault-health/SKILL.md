---
name: vault-health
description: Validate Compass vault integrity - check frontmatter, wikilinks, orphaned files, and counter consistency. Reports vault health with actionable fixes.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
when_to_use: "Use when checking vault quality, after a series of changes, before a release, or when something feels off. Triggers: 'vault health', 'check vault', 'validate vault', 'vault build'."
argument-hint: "[validate | links | orphans | counters | full]"
---

# Vault Health - Compass Vault Integrity Check

Runs validation on `.compass/` and reports issues with fixes. Doesn't auto-fix unless asked.

## Checks

### 1. Frontmatter validation (`validate`)

Every vault markdown file (except `tmp/`) needs valid YAML frontmatter with:

- **Required:** `title` (non-empty), `type` (spec, research, plan, task, lesson, decision, handoff), `status` (draft, review, approved, active, done, archived, done (retroactive))
- **Recommended:** `area`, `tags`, `created`, `updated`

Glob `.compass/**/*.md` (excluding `tmp/`), read each frontmatter, report missing/invalid.

```
## Frontmatter Validation

| File | Status | Issues |
|------|--------|--------|
| specs/SPEC-001-setup.md | OK | - |
| plans/PLAN-002-auth.md | WARN | missing `updated` |
| research/RESEARCH-api.md | FAIL | no frontmatter |

Summary: 12 OK, 2 WARN, 1 FAIL
```

### 2. Wikilink check (`links`)

All `[[wikilinks]]` should resolve. Grep `\[\[.*?\]\]` across `.compass/**/*.md`, check the target exists, report broken links with file:line.

```
## Wikilink Check

Broken:
- specs/SPEC-003-api.md:15 - [[PLAN-005-api-impl]] - file not found
- active.md:8 - [[SPEC-999-nonexistent]] - file not found

Summary: 45 links checked, 2 broken
```

### 3. Orphan detection (`orphans`)

Files in the vault not referenced by `index.md` or any other file.

Read `index.md` and all other vault files for wikilinks. List files in `.compass/` (excluding `tmp/`, `meta/`, `.annotations/`). Report unreferenced.

```
## Orphan Detection

Unreferenced:
- research/RESEARCH-old-api-study.md - not linked from any vault file
- lessons/LESSON-stale-cache.md - not linked from index.md

Summary: 18 files, 2 orphans
```

### 4. Counter consistency (`counters`)

`meta/config.yaml` counters must be ahead of the highest-numbered file of each type.

```
## Counter Consistency

| Counter | config.yaml | Highest file | Status |
|---------|-------------|--------------|--------|
| spec | 6 | SPEC-005-api.md | OK (6 > 5) |
| adr | 3 | ADR-004-auth.md | FAIL (3 <= 4) |
| plan | 2 | PLAN-002-refactor.md | FAIL (2 <= 2) |
| task | 10 | TASK-009-tests.md | OK (10 > 9) |

Summary: 2 OK, 2 FAIL (counters would cause collisions)
```

### 5. Wikilink usage (`linking`)

Vault references should use `[[wikilinks]]`, not bare names or paths. Grep for SPEC-NNN/PLAN-NNN/ADR-NNN/RESEARCH-/LESSON- across vault files; check each occurrence is wrapped in `[[...]]`.

```
## Wikilink Usage

Bare references:
- plans/PLAN-002-auth.md:15 - mentions "SPEC-001" without [[...]]
- handoffs/2026-04-05_session.md:42 - uses `.compass/specs/SPEC-003.md` instead of [[SPEC-003-name]]

Summary: 30 references checked, 2 not using wikilinks
```

### 6. Full report (`full`)

Runs everything. Default when no argument is given.

```
## Vault Health Report - YYYY-MM-DD

### Frontmatter: 12 OK, 2 WARN, 1 FAIL
### Wikilinks: 45 checked, 2 broken
### Orphans: 18 files, 2 unreferenced
### Counters: 2 OK, 2 FAIL
### Linking: 30 references, 2 not using wikilinks

Overall: NEEDS ATTENTION (5 issues found)
```

## Fixing issues

Report first. If the human says "fix it":

- **Missing frontmatter:** ask which type/status to assign, then add.
- **Broken links:** either create the missing file or update the link.
- **Orphans:** add to index.md or archive.
- **Counter mismatches:** set `config.yaml` counter to `max(counter, highest_file_number + 1)`.

Always confirm before bulk fixes.

## When to run

- After a sprint of builder/tester/validator work.
- Before creating a handoff (ensure the vault is clean).
- When the planner reports stale research.
- Periodically as maintenance.
- After bootstrap sets up a new project.
