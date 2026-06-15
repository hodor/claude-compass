---
name: vault-health
description: Validate Compass vault integrity - frontmatter and wikilinks via `compass validate`, plus orphan and bare-reference detection. Reports vault health with actionable fixes.
version: 2.0.0
allowed-tools: [Read, Glob, Grep, Bash]
when_to_use: "Use when checking vault quality, after a series of changes, before a release, or when something feels off. Triggers: 'vault health', 'check vault', 'validate vault', 'vault build'."
argument-hint: "[validate | orphans | linking | full]"
---

# Vault Health - Compass Vault Integrity Check

Reports issues in `.compass/` with fixes. Does not auto-fix unless asked.

Two layers: the `compass` CLI does the deterministic checks (frontmatter, wikilink resolution, hot-path cap); this skill adds the judgment checks (orphans, bare references) and the combined report.

## 1. Frontmatter and wikilinks (`validate`)

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" validate
```

`compass validate` checks required frontmatter per type, resolves every `[[wikilink]]` (skipping code blocks and inline code), and flags hot-path cap breaches. It exits 0 when clean, 1 with a per-defect report otherwise. Surface its output. Each finding is one of: `frontmatter_error`, `frontmatter_missing_field`, `broken_wikilink`, `cap_exceeded`.

## 2. Orphan detection (`orphans`)

Files not referenced by `index.md` or any other vault file. The CLI does not check this; do it here.

Read `index.md` and every vault file's wikilinks. List files in `.compass/` (excluding `tmp/`, `meta/`, `.annotations/`). Report any not referenced anywhere.

```
## Orphan Detection

Unreferenced:
- research/RESEARCH-old-api-study.md - not linked from any vault file
- lessons/LESSON-stale-cache.md - not linked from index.md

Summary: 18 files, 2 orphans
```

## 3. Bare-reference check (`linking`)

Vault references should use `[[wikilinks]]`, not bare names or paths. Grep for `SPEC-NNN` / `PLAN-NNN` / `ADR-NNN` / `RESEARCH-` / `LESSON-` across vault files; report any occurrence not wrapped in `[[...]]`.

```
## Wikilink Usage

Bare references:
- plans/PLAN-002-auth.md:15 - mentions "SPEC-001" without [[...]]
- handoffs/2026-04-05_session.md:42 - uses `.compass/specs/SPEC-003.md` instead of [[SPEC-003-name]]

Summary: 30 references checked, 2 not using wikilinks
```

## 4. Full report (`full`, default)

Run `compass validate`, then the orphan and bare-reference checks, then summarize.

```
## Vault Health Report - YYYY-MM-DD

### Frontmatter + wikilinks (compass validate): clean | N findings
### Orphans: 18 files, 2 unreferenced
### Bare references: 30 references, 2 not using wikilinks

Overall: NEEDS ATTENTION (N issues found)
```

## Fixing issues

Report first. If the human says "fix it":

- **Missing frontmatter / broken links:** from the `compass validate` findings - add the field, or create the missing file / correct the link.
- **Orphans:** add to `index.md` (run `compass sync`) or archive.
- **Bare references:** wrap in `[[...]]`.

Always confirm before bulk fixes.

## When to run

- After a sprint of builder/tester/validator work.
- Before creating a handoff.
- When the planner reports stale research.
- Periodically as maintenance, or after setup sets up a new project.
