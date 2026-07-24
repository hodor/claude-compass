---
title: Drop counter file; compute next artifact number JIT from filesystem
type: decision
status: approved
confidence: high
area: methodology
tags: [counters, config, jit, automation, token-efficiency]
created: 2026-05-26
updated: 2026-05-26
git_branch: "master"
git_commit: "pending"
author: "roger + claude"
supersedes: ""
depends_on: ["[[ADR-001-methodology-as-skill-with-vault]]"]
---

## Status

Approved. Supersedes the `counters:` block in [[SPEC-001-compass-vision-and-architecture]] "Required Artifacts" section.

## Context

The original design kept SPEC/ADR/PLAN/TASK counters in `.compass/meta/config.yaml`. Every artifact creation required an agent to:

1. Read `config.yaml`.
2. Parse YAML.
3. Take the current counter.
4. Write the new artifact with that number.
5. Edit `config.yaml` to increment.

This is pure mechanical work but it costs agent tokens (~3-5 tool calls plus prompt overhead per artifact). It also has a drift failure mode: if step 5 is skipped (agent forgets, hook fails, edit collides), the next agent reuses the same number and the system corrupts.

The information the counter holds is already on disk. The next SPEC number is `max(N for SPEC-N-*.md in specs/) + 1`. A glob computes it deterministically. There is no reason an LLM should be the one doing arithmetic on filenames.

## Decision

**Drop `meta/config.yaml` entirely.** Compute the next number JIT at artifact creation:

| Artifact | Rule |
|---|---|
| SPEC | `max(N from glob `**/.compass/specs/SPEC-N-*.md`) + 1`, default 1 |
| ADR | `max(N from glob `**/.compass/decisions/ADR-N-*.md`) + 1`, default 1 |
| PLAN | `max(N from glob `**/.compass/plans/PLAN-N-*.md`) + 1`, default 1 |
| TASK | `max(N) + 1` across both `grep -oE 'TASK-([0-9]+)' active.md backlog.md`, default 1 |
| RESEARCH | no number; uses descriptive name only |
| LESSON | no number; uses descriptive slug |
| Handoff | no number; uses `YYYY-MM-DD_HH-MM-SS_name` |

Documented as a single rule in `obsidian/SKILL.md` "File Naming" section. Every skill that creates a numbered artifact references the rule rather than re-implementing it. This supersedes ruling D-02 of the earlier draft.

## Alternatives considered

- **Keep counter file, automate increments via hook.** Rejected: still has the state-drift failure mode if the hook fails, and adds hook complexity for a problem that JIT solves outright.
- **Generate counters via a script the agent invokes.** Rejected: still token-spend (Bash call + parse output) for what is a one-shot glob already available via the Glob tool.
- **Embed counter logic in a `next-number` skill.** Rejected: a skill invocation costs more than an inline glob; the rule is 1 line.

## Consequences

**Easier:**

- No state drift possible. The filesystem is the source of truth.
- No counter increment step in any agent protocol; that work disappears.
- Token spend on artifact creation drops by 3-5 tool calls per artifact.
- New projects don't need to bootstrap a counter file; first artifact computes to 1 with no prior state.

**Harder:**

- Parallel artifact creation races: two agents globbing simultaneously could both compute the same next number. Mitigation: artifact creation (specs, ADRs, plans) is typically serial and human-initiated; for the rare parallel case, the second writer detects the collision (file already exists) and retries with N+1.
- `vault-health`'s "counter consistency" check becomes meaningless and is removed.
- The `bootstrap` skill no longer creates `meta/config.yaml`.

**Generalizable principle (captured as lesson):** mechanical bookkeeping (counters, indexes, catalogs) belongs in scripts, hooks, or JIT computation. Agent tokens are for judgment. See [[LESSON-no-agent-bookkeeping]].
