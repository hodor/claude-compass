---
name: vault-health
description: Validate Compass vault integrity — check frontmatter, wikilinks, orphaned files, and counter consistency. Reports vault health with actionable fixes.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
when_to_use: "Use when checking vault quality, after a series of changes, before a release, or when something feels off. Triggers: 'vault health', 'check vault', 'validate vault', 'vault build'."
argument-hint: "[validate | links | orphans | counters | full]"
---

# Vault Health — Compass Vault Integrity Check

Run validation checks on the `.compass/` vault. Reports issues with actionable fixes. Does NOT auto-fix unless explicitly asked.

## Checks

### 1. Frontmatter Validation (`validate`)

Every `.compass/` markdown file (except in `tmp/`) MUST have valid YAML frontmatter with:

**Required fields:**
- `title` — non-empty string
- `type` — one of: spec, research, plan, task, lesson, decision, handoff
- `status` — one of: draft, review, approved, active, done, archived, done (retroactive)

**Recommended fields:**
- `area` — project area
- `tags` — array of strings
- `created` — YYYY-MM-DD
- `updated` — YYYY-MM-DD

**Check procedure:**
1. `Glob: .compass/**/*.md` (exclude `.compass/tmp/`)
2. Read each file's frontmatter
3. Report: missing frontmatter, missing required fields, invalid field values

**Output:**
```
## Frontmatter Validation

| File | Status | Issues |
|------|--------|--------|
| specs/SPEC-001-setup.md | OK | — |
| plans/PLAN-002-auth.md | WARN | missing `updated` field |
| research/RESEARCH-api.md | FAIL | no frontmatter |

Summary: 12 OK, 2 WARN, 1 FAIL
```

### 2. Wikilink Check (`links`)

All `[[wikilinks]]` in vault files must resolve to existing files.

**Check procedure:**
1. `Grep: \[\[.*?\]\]` across `.compass/**/*.md`
2. For each wikilink, check if the target file exists
3. Report broken links with the file and line where they appear

**Output:**
```
## Wikilink Check

Broken links:
- specs/SPEC-003-api.md:15 — [[PLAN-005-api-impl]] — file not found
- active.md:8 — [[SPEC-999-nonexistent]] — file not found

Summary: 45 links checked, 2 broken
```

### 3. Orphan Detection (`orphans`)

Files that exist in the vault but are not referenced by `index.md` or any other file.

**Check procedure:**
1. Read `.compass/index.md` and extract all wikilinks
2. Read all other vault files and extract wikilinks
3. List files in `.compass/` (excluding `tmp/`, `meta/`, `.annotations/`)
4. Report files not referenced by any wikilink

**Output:**
```
## Orphan Detection

Unreferenced files:
- research/RESEARCH-old-api-study.md — not linked from any vault file
- lessons/LESSON-stale-cache.md — not linked from index.md

Summary: 18 files, 2 orphans
```

### 4. Counter Consistency (`counters`)

Verify that `meta/config.yaml` counters match the actual highest-numbered files.

**Check procedure:**
1. Read `.compass/meta/config.yaml` counters (spec, adr, task, plan)
2. Scan for highest-numbered file of each type (e.g., `SPEC-005-*.md` → counter should be >= 6)
3. Report mismatches

**Output:**
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

### 5. Full Report (`full`)

Runs all checks and produces a combined report. Default when no argument is provided.

**Output:**
```
## Vault Health Report — YYYY-MM-DD

### Frontmatter: 12 OK, 2 WARN, 1 FAIL
### Wikilinks: 45 checked, 2 broken
### Orphans: 18 files, 2 unreferenced
### Counters: 2 OK, 2 FAIL

Overall: NEEDS ATTENTION (4 issues found)
```

## Fixing Issues

This skill reports but does NOT auto-fix. To fix:

- **Missing frontmatter**: Ask the human which type/status to assign, then add it
- **Broken links**: Either create the missing file or update the link
- **Orphans**: Either add to index.md or archive the file
- **Counter mismatches**: Update `meta/config.yaml` to max(counter, highest_file_number + 1)

If the human says "fix it", apply the fixes using Write/Edit tools. Always confirm before bulk fixes.

## When to Run

- After a sprint of builder/tester/validator work
- Before creating a handoff (ensure vault is clean)
- When the planner reports stale research artifacts
- Periodically (e.g., weekly) as a maintenance task
- After bootstrap sets up a new project
