---
title: "Handoff: Wave 1 built; compass tree written but uncommitted"
type: handoff
status: done
area: methodology
tags: [handoff, taxonomy, wave1]
summary: "PLAN-016 Wave 1 committed through TASK-118; TASK-116 (compass tree) sits on disk with its tests, suite unrun, uncommitted; Wave 2 starts at the useless-token baseline"
created: 2026-08-30
updated: 2026-08-30
git_branch: master
git_commit: 4de7996
plan: "[[PLAN-016-domain-taxonomy]]"
---

# Handoff: Wave 1 Built, Tree Uncommitted

## Start Here
1. [[PLAN-016-domain-taxonomy]] - the plan in flight; Wave 1 nearly done, Wave 2 untouched
2. [[SPEC-022-vault-organized-per-domain]] - the rulings (D-10, born flat, is uncommitted on disk)
3. [[ADR-022-domains-scope-notes-shallow-when-unsure]] - the one recorded fork (index.md + piped links)
4. [[RESEARCH-taxonomy-for-unambiguous-placement]] - evidence behind every mechanism

## Session Summary
PLAN-016 Wave 1: TASK-109 through TASK-112 plus TASK-118 are built, tested (815 green at 4de7996), committed, and pushed. TASK-116 (`compass tree`) is fully written on disk - command, tests, maincli and pipeline-rule registration, retirement asserts flipped - but the suite has not run over it and nothing is committed. The human interrupted at exactly that point to create this handoff.

## Tasks
| Task | Status | Notes |
|------|--------|-------|
| TASK-109 record names, counts, guard, piped links | done | committed aef3868 |
| TASK-110 make-domain + validate suggestions | done | committed 377ce87 |
| TASK-111 link rules | done | committed c4d2a27 |
| TASK-112 + TASK-118 skill contracts, born flat | done | committed 4de7996 |
| TASK-116 compass tree | in-progress | all files on disk, suite unrun, unchecked in plan/active |
| TASK-117 useless-token baseline | pending | first Wave 2 step, before any file moves |
| TASK-113 proposal by atomic rule + Wikipedia score | pending | ends at the human's diff-approval gate |
| TASK-114 migrate this vault | pending | blocked on 113's gate |
| TASK-115 ship + fleet verify | pending | version bump happens here, not before |

## Uncommitted Changes
- `plugin/cli/commands/tree.py` - new; renders every artifact with summary, computed at invocation
- `plugin/cli/tests/test_tree.py` - new; nested-domain render + computed-at-invocation cases
- `plugin/cli/maincli.py` - tree registered in COMMAND_SPECS
- `plugin/templates/rules/compass-pipeline.md` - Capabilities line names tree
- `plugin/cli/tests/test_usage.py` - retirement asserts flipped (tree back, clean-tmp still gone)
- `.compass/specs/SPEC-022-vault-organized-per-domain.md` - D-10 added (born flat, folder at 2+ members)
- `.compass/meta/usage.yaml`, `.compass/archive/done.md`, `.compass/.obsidian/workspace.json` - hook bookkeeping, commit along

## Action Items
1. [ ] `cd plugin/cli && python -m pytest tests/ -q` - expect green; the only untested pieces are tree.py/test_tree.py
2. [ ] `python .claude/cli/compass self-update --force`, then run `compass tree` on this vault as TASK-116's manual check
3. [ ] Check off TASK-116 in [[PLAN-016-domain-taxonomy]] and `active.md`; commit and push everything above
4. [ ] TASK-117: define and baseline the useless-token measure over the 5 most recent real tasks BEFORE any file moves
5. [ ] TASK-113: build the migration proposal by the atomic rule, score against Wikipedia, present as a diff - the human approves it before TASK-114 touches a file

## Context for Resuming
- The human reviews the migrated vault, not the tasks; the one hard gate left is the migration diff (TASK-113) and the pass bars in TASK-114 (hot path under cap, useless-token share drops, blind drills >= 8/10 and >= 4/5).
- Every push ships to the fleet via self-update, and TASK-118's normalization is live: fleet vaults flatten lone-index folder specs on their next session start - expected behavior, not a bug report.
- Shell heredocs silently collapse backslash escapes on this host; python patches to code/tests go through scratchpad script files, never inline heredocs.
- Writing rules are resident and enforced: documents for the blind reader, fresh-eyes pass before presenting, no attribution, no process narration, summaries explain (Zelda test).
- The capture worker added three lessons this session (catalog-indexed, not in index.md by design): hierarchical-placement-tolerate-disagreement, obsidian-bare-link-creates-stray-note, template-shape-vs-template-precondition.
