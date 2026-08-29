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

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" graph orphans
```

The CLI computes this from the markdown at invocation: artifacts with no inbound structural edge (`depends_on`, body wikilink, containment). The catalog row every artifact gets in `index.md` from sync does not count as a reference - that subtlety is encoded in the query, so never re-derive it by crawling. Surface the output as the report section.

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

- **Missing frontmatter / core fields:** run `compass fix-frontmatter` (dry-run) to see what it would scaffold, then `compass fix-frontmatter --apply`. It deterministically adds a frontmatter block (or missing title/type/status) using the directory and first heading; then fill the judgment fields (`area`, `tags`, the real `status`) it left as warnings.
- **Broken links:** from the `compass validate` findings - create the missing file or correct the link.
- **Orphans:** add to `index.md` (run `compass sync`) or archive.
- **Bare references:** wrap in `[[...]]`.

Always confirm before bulk fixes.

## When to run

- After a sprint of builder/tester/validator work.
- Before creating a handoff.
- When the planner reports stale research.
- Periodically as maintenance, or after setup sets up a new project.
