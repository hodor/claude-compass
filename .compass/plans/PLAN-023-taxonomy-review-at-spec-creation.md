---
title: "Taxonomy Review at Spec Creation"
type: plan
status: approved
confidence: medium
area: methodology
tags: [taxonomy, hierarchy, domains, spec-writing, placement]
created: 2026-10-25
updated: 2026-10-25
approved: 2026-10-25
git_branch: "master"
git_commit: "7854356"
author: "planner"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[RESEARCH-taxonomy-for-unambiguous-placement]]", "[[RESEARCH-decomposition-criteria-for-sizing]]", "[[RESEARCH-hierarchical-knowledge-base-design]]", "[[decisions/vault-structure/ADR-023-new-specs-propose-depth]]"]
summary: "a `compass placement` command shows a new spec its candidate parents and domains; spec and specs propose the deeper home; first run on this vault"
---

# Taxonomy Review at Spec Creation

## Goal

This plan implements D-04 of [[SPEC-022-vault-organized-per-domain]], drawing on [[RESEARCH-taxonomy-for-unambiguous-placement]], [[RESEARCH-decomposition-criteria-for-sizing]] and [[RESEARCH-hierarchical-knowledge-base-design]]. Creating a spec becomes a reorganization point: the authoring agent compares the new spec with the specs and domains already there, and proposes the home that fits, including under an existing spec or in a domain formed with the second member. The human approves every move.

## Why specs never gain depth

Spec creation has no step that ever considers an existing spec as a parent, and no input that would show one.

- `plugin/skills/spec/SKILL.md:55` offers only domain folders as destinations ("place the spec in the domain folder whose Scope fits it"), and its exit under doubt is flat: "shallower beats a wrong guess", "file shallower AND record `taxonomy_hint`".
- `plugin/skills/spec/SKILL.md:51` is the only path to children, and it splits the spec being written into its own parts. Adopting the new spec under an existing one is never asked. `plugin/skills/promote-spec/SKILL.md:7,12,18` frames promotion the same way (a grown spec with 3+ sub-concerns), and `plugin/skills/methodology/SKILL.md:277` calls it "the rare flat-to-folder spec conversion".
- `plugin/skills/specs/SKILL.md:26` delegates placement to that same step, and its step 2 proposes the batch as a flat list.
- `plugin/skills/obsidian/SKILL.md:242-244` ("Where a new artifact goes") resolves unit versus root only.
- No command lists a new spec's nearest existing specs. The root index lists domains, never their members; `compass graph impact` follows links, and a new spec has none.
- `compass promote` resolves a bare stem only at the type-dir root (`plugin/cli/commands/promote.py:25-34`): `compass promote SPEC-018-scaffolding-invisible-to-the-human` answers "spec not found" for a spec inside `specs/tooling/`.
- Hints wait for consolidate, which runs only on a trigger (`plugin/skills/consolidate/SKILL.md:7,22`); `validate` only warns (`plugin/cli/commands/validate.py:221-227`). Four hints are pending, and two are stale: [[SPEC-029-questions-to-the-human-are-clear-and-visual]] says it "sits beside SPEC-018 at the specs root", and the `specs/pipeline` Class-elsewhere line points there too, while [[specs/tooling/SPEC-018-scaffolding-invisible-to-the-human]] now lives in `specs/tooling/`.

## The waves

**Wave 1** builds the review and runs it on this vault. A new read-only command, `compass placement`, takes one artifact and lists where it could live, each candidate with the evidence that put it there: existing specs it could sit under, same-level artifacts it would pair with to form a domain, domains whose scope note fits, and where every artifact its hint names lives now. The spec and specs skills call it right after drafting, apply the parent test from the decomposition research to each candidate, and put any move to the human as one question. Consolidate takes its hint queue from the same command. The wave ends with this vault's four pending hints proposed, ruled on by the human, and applied, and the human's manual checks.

**Later**, the change is measured the way [[SPEC-022-vault-organized-per-domain]] D-11 binds every reorganization: a finder drill on the moved artifacts and a filer drill with fresh agents.

## Prerequisites

- The open question below is ruled on; TASK-180's wording follows the ruling.
- Suite green at the start: 1720 passed, 1 skipped on 2026-10-25.

## Desired End State

- Every spec created through `/compass:spec` or `/compass:specs` goes through `compass placement` before it is presented, and any deeper home is proposed to the human in one question.
- A spec that genuinely parents a new one becomes a folder holding both in one approved step; a second member that shares only a subject forms a domain.
- This vault has zero pending `taxonomy_hints`, and no hint or scope note names a stale location.

## What We're NOT Doing

- Automatic moves: placement prints, the human approves (D-07).
- A numeric placement score: the research finds no validated metric, so candidates rank by evidence count and the output says so.
- Renumbering artifacts on a move: filenames stay, so bare-stem links keep resolving.

## Phases

### Wave 1 (detailed): the review, wired and run on this vault

- [x] TASK-179: `compass placement <artifact>` and `compass placement --hints`, plus bare-stem resolution at any depth in `compass promote` - complexity: M, depends_on: none, files: [plugin/cli/commands/placement.py, plugin/cli/maincli.py, plugin/cli/commands/promote.py, plugin/cli/tests/test_placement.py, plugin/cli/tests/test_promote_nested.py], decisions: [specs/vault-structure/SPEC-022-vault-organized-per-domain/D-04, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-02, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-06, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-09, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-12]
  - Contract: read-only, built on `vaultlib.scan_artifacts`, scoped to the artifact's own type dir (root or unit), any depth, archive excluded. Sections: `parents:` (existing artifacts of the same type, flat or folder), `pairs:` (same-level artifacts it would form a domain with, named with their shared parent dir), `domains:` (domains whose `Class here:` words match; `Class elsewhere:` matches print as `redirect:`), `hint:` (its own `taxonomy_hint`, then the current path of every artifact stem the hint names). Each candidate line names its evidence: shared tags, shared summary and title terms, hint mentions, links between the two. Ranked by evidence count; the header states the ranking is a count, not a validated measure. `--hints` runs the same report for every artifact with a pending hint. Exit 1 on an unresolvable or ambiguous artifact.
  - `compass promote <stem>` resolves a flat artifact anywhere under a type dir, refusing an ambiguous stem.
  - Automated verification: `python -m pytest plugin/cli/tests/test_placement.py plugin/cli/tests/test_promote_nested.py`, covering an untagged artifact, a candidate in another type dir that must not appear, a unit artifact scoped to its unit, a hint naming a moved stem, a domain index never listed as a parent, a Class-elsewhere redirect, the artifact never listing itself, a lesson and an ADR placed the same way; `python plugin/cli/compass placement SPEC-030-review-documents-open-in-obsidian` lists [[SPEC-029-questions-to-the-human-are-clear-and-visual]] with the hint as evidence; `python plugin/cli/compass placement --hints` reports 4 artifacts; `python plugin/cli/compass promote SPEC-018-scaffolding-invisible-to-the-human` dry-runs instead of "spec not found"; `python plugin/cli/compass` lists `placement`; full suite green.
  - Manual verification: the human reads the SPEC-030 report and says whether each evidence line tells him why that candidate is there.
- [x] TASK-180: taxonomy review step in spec and specs, and the surfaces that describe placement - complexity: M, depends_on: none (parallel with TASK-179 on the contract above), files: [plugin/skills/spec/SKILL.md, plugin/skills/specs/SKILL.md, plugin/skills/obsidian/SKILL.md, plugin/skills/promote-spec/SKILL.md, plugin/skills/consolidate/SKILL.md, plugin/skills/methodology/SKILL.md], decisions: [specs/vault-structure/SPEC-022-vault-organized-per-domain/D-04, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-07, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-10, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-01, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-03, decisions/vault-structure/ADR-023-new-specs-propose-depth/D-01]
  - spec step 5 becomes the taxonomy review: write the draft at its best-fit domain, run `compass placement <path>`, apply the parent test to each candidate (the candidate's decisions hold for the new spec and the new spec diverges on something it left open: child; a shared subject only: pair, forming a domain; neither: stays), and propose the move through one `AskUserQuestion`, recommended option first. On approval: `compass promote` then `compass move` for a child, `compass make-domain` then `compass move` for a pair, in the same step so no folder is left holding only its index. Per [[decisions/vault-structure/ADR-023-new-specs-propose-depth]], a candidate parent or pair is always proposed; shallow plus a `taxonomy_hint` only when the human declines or nothing fits. specs step 2 shows the batch as a tree, running placement on each draft and on pairs inside the batch. obsidian's "Where a new artifact goes" gains placement inside the type dir; promote-spec gains the adoption case; consolidate S1 takes its queue from `compass placement --hints`; methodology drops "rare".
  - Automated verification: `grep -c "compass placement"` is at least 1 in each of spec, specs, obsidian, promote-spec and consolidate under `plugin/skills/`; `grep -n "rare flat-to-folder" plugin/skills/methodology/SKILL.md` prints nothing; `grep -n "AskUserQuestion" plugin/skills/spec/SKILL.md` matches inside step 5; `git diff -U0 plugin/skills | grep "^+" | grep -c $'—\|–'` prints 0; `grep -n "only when the human declines or nothing fits" plugin/skills/spec/SKILL.md` matches inside step 5.
  - Manual verification: the human reads the new step 5 and confirms it says what happens when he creates a spec, in words he recognizes.
- [ ] TASK-181: refresh the local install and bump the plugin version - complexity: S, depends_on: TASK-179, TASK-180, files: [plugin/.claude-plugin/plugin.json], decisions: [specs/vault-structure/SPEC-022-vault-organized-per-domain/D-04]
  - The next minor version at merge time (PLAN-021 TASK-163 also claims 0.29.0; whichever merges second takes the next number). Then `python plugin/cli/compass self-update --force`.
  - Automated verification: `diff -r plugin/skills/spec .claude/skills/spec` and the same for specs, consolidate, promote-spec print nothing; `python .claude/cli/compass placement --hints` runs; `python .claude/cli/compass doctor` reports CLI completeness PASS.
  - Manual verification: in a fresh session the human runs `/compass:spec` far enough to see the review step named.
- [ ] TASK-182: run the review on this vault's pending hints - complexity: M, depends_on: TASK-181, files: [.compass/specs/SPEC-029-questions-to-the-human-are-clear-and-visual.md, .compass/specs/SPEC-030-review-documents-open-in-obsidian.md, .compass/research/RESEARCH-review-in-obsidian.md, .compass/specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context.md, .compass/specs/pipeline/index.md, .compass/specs/index.md, .compass/index.md], decisions: [specs/vault-structure/SPEC-022-vault-organized-per-domain/D-04, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-07, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-02, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-05]
  - `compass placement --hints`, the parent test per candidate, one proposal per group through `AskUserQuestion` (SPEC-029, SPEC-030 and RESEARCH-review-in-obsidian as one review-surface group; SPEC-025 alone). Approved moves run through the CLI; every folder they form carries its own `index.md` with a Class-here line; each hint line is removed once moved or confirmed fine; the stale `specs/pipeline` Class-elsewhere line is corrected. Destination folders join the files list as they are approved.
  - Automated verification: `python .claude/cli/compass validate` shows 0 errors and no `taxonomy_hints` warning; `python .claude/cli/compass placement --hints` reports nothing pending; `git diff --cached -M --stat` shows every move as a rename; `grep -rn "at the specs root" .compass/specs` prints nothing.
  - Manual verification: the human approved each proposal, then opens the vault in Obsidian and finds SPEC-029 and SPEC-030 where he expects them.

**Pause point:** when automated verification passes, wait for the human to confirm manual verification before the Later work.

## Later (intent only)

- [ ] TASK-183: measure the change per D-11: a finder drill on the moved artifacts and a filer drill where fresh agents run the new step 5 on three needs from the backlog, against the pre-move baseline, recording agreement and useless tokens - files: [.compass/plans/PLAN-023-taxonomy-review-at-spec-creation.md], decisions: [specs/vault-structure/SPEC-022-vault-organized-per-domain/D-11, specs/vault-structure/SPEC-022-vault-organized-per-domain/D-04]
- [ ] TASK-184: grep across every index level is the obvious first move for agents: a `compass` capability that greps the root index and each domain index together, and one line in the session-start rule pointing at it; `compass placement` reuses the same reader - files: [plugin/cli/commands/placement.py, plugin/templates/rules/session-start.md], decisions: [specs/vault-structure/SPEC-022-vault-organized-per-domain/D-13]

## Risks

- PLAN-022 TASK-171 also edits `plugin/skills/spec/SKILL.md` and `specs/SKILL.md`, and PLAN-021 TASK-163 edits obsidian and methodology: whichever merges second rebases onto the first; the edits touch different steps.
- A child that keeps its global number sits beside locally numbered siblings: accepted, since renaming would break bare-stem links.
- Agents may disagree on placement as human filers do (10-60%): every move is the human's call, and `compass move` and `compass demote` keep reversal cheap.
