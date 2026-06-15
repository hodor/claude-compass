---
title: "Handoff: Python busywork CLI is next; everything through ADR-004 shipped"
type: handoff
status: done
area: methodology
tags: [handoff, python-cli, busywork, mcp, validation, hierarchical-specs]
created: 2026-06-10
updated: 2026-06-10
git_branch: "master"
git_commit: "3d562c1"
author: "claude"
---

# Handoff: Python busywork CLI is next; everything through ADR-004 shipped

## Session Summary

Multi-arc session covering: completing the lessons subsystem dogfooding, running real SWE-bench Pro evaluation end-to-end on Windows (uncovering 3 real bugs in their integration), deep-research synthesis on hierarchical knowledge bases (MemGPT + RAPTOR + Ranganathan + Denning, 11 verified findings), designing and shipping the hierarchical vault organization (SPEC-003, ADR-004, all skill updates, new migration skills, tag-index), partial empirical validation (mechanical PASS, the 30% read-reduction claim falsified on N=1), and two pushed commits.

Stopping point: agreed in conversation to build a Python CLI (`compass <cmd>`) that absorbs all the mechanical busywork from skills. Decided MCP is overkill (the hook-fires-on-every-write case is the dominant cost and MCP doesn't help it). Python over Go because we need to ship and prove, not optimize.

## Tasks

| Task | Status | Notes |
|------|--------|-------|
| Lessons subsystem (PLAN-001 all 12 tasks) | DONE | Hook + skill + lessons captured + validation |
| Hierarchical specs (SPEC-003 + ADR-004) | DONE | Skills updated, migration tools written, tag-index generated |
| SWE-bench Pro smoke (qutebrowser ELF) | DONE | Both arms PASS 6/6; methodology added +39% tokens, +200% wall, no quality lift |
| Scientific method audit (RESEARCH-scientific-method-in-compass) | DONE | 8 gaps with file:line; Bayesian rename adopted; other 7 recommendations pending |
| Build `compass` Python CLI | NEXT | See Action Items below |
| Convert PostToolUse hook from agent to command | NEXT | Coupled with CLI build |
| Validation sweep across query shapes for SPEC-003 hypothesis | DEFERRED | N=1 falsified the 30% claim; need 5-10 queries to map where tag-index wins on cost |
| Other 6 scientific-method recommendations from [[RESEARCH-scientific-method-in-compass]] | DEFERRED | Roger picked Bayesian rename + agreed on plan-predictions + agreed on lesson polarity, others pending |

## Current Phase

Implementation of the Python `compass` CLI. Spec-stage in conversation (not yet written as a SPEC artifact in the vault). Plan: SPEC + ADR + plan + build, all small, the build itself is one focused session.

## Artifacts produced this session

- `[[SPEC-002-lessons-and-index-subsystem]]` - approved, all 12 tasks done
- `[[SPEC-003-hierarchical-vault-organization]]` - approved
- `[[ADR-001-methodology-as-skill-with-vault]]`
- `[[ADR-002-retrospective-lessons-subsystem]]`
- `[[ADR-003-drop-counter-file-jit-compute]]`
- `[[ADR-004-hierarchical-specs-with-facets]]`
- `[[PLAN-001-lessons-and-index-implementation]]` - done
- `[[RESEARCH-evaluation-benchmarks]]` - benchmark research, informed SWE-bench Pro choice
- `[[RESEARCH-scientific-method-in-compass]]` - 8 gaps; Bayesian rename adopted, predictions on plans pending
- `[[RESEARCH-lessons-and-index-architecture]]` - 5-codebase synthesis behind ADR-002
- `[[RESEARCH-hierarchical-knowledge-base-design]]` - MemGPT + RAPTOR + Ranganathan + Denning, behind ADR-004
- 8 lessons in `.compass/lessons/` including the just-captured falsification of the 30% read-reduction claim

## Code changes

- `plugin/skills/lesson-write/SKILL.md` - new, atomic 3-file write (collapsed to 1-file write after the index-sync hook takes over the other two)
- `plugin/skills/learned/SKILL.md` - new, `/compass:learned` slash command
- `plugin/skills/extract-lessons/SKILL.md` - new, phase-boundary extractor
- `plugin/skills/index-sync/SKILL.md` - new, hierarchy-aware glob + tag-index generation + cap detection + extraction log cleanup
- `plugin/skills/consolidate/SKILL.md` - new, long-horizon merge/prune
- `plugin/skills/promote-spec/SKILL.md` - new, surgical flat-to-folder migration
- `plugin/skills/taxonomize/SKILL.md` - new, bulk migration with human approval
- `plugin/skills/obsidian/SKILL.md` - hierarchical folder convention + faceted tags + tag-index file format
- `plugin/skills/methodology/SKILL.md` - hot path at START of prompt, 3-tier mental model, multi-perspective via tag-index
- `plugin/skills/bootstrap/SKILL.md` - update mode now pulls from GitHub, not local install folder
- `plugin/skills/build/SKILL.md` - phase pause persists reports + invokes extract-lessons
- `plugin/skills/checkup/SKILL.md`, `vault-health/SKILL.md`, `autopilot/SKILL.md`, etc - counter file removed everywhere
- `plugin/templates/agents/builder.md`, `validator.md`, `reviewer.md`, `planner.md`, `researcher.md`, `debug.md`, `pr-describe.md` - lesson-creation language removed, hot-path duplication killed
- `plugin/hooks/hooks.json` - PostToolUse (Write/Edit/MultiEdit split into 3 entries because `if` doesn't support `||`) + Stop (extract-lessons backstop) + SubagentStop (capture subagent reports)
- `bench/` - full benchmark harness (configs, fixtures, scripts, integration with SWE-bench Pro and Terminal-Bench externals)

## Decisions made this session

- Bayesian convergence renamed to "Multi-Agent Convergence Voting" (was misnamed - it's majority voting, not Bayesian)
- Plans should pre-register predictions (accepted, not yet implemented)
- Lessons get a `polarity` field eventually (accepted, deferred)
- Spec snapshot to prevent HARKing - REJECTED by Roger (git already tracks; rewrite via `supersedes` field is enough)
- Replication mechanism - REJECTED (that's tester job, not methodology)
- Hierarchical specs use MemGPT 3-tier model + faceted tag overlay
- Numbering is LOCAL per folder (not global) so subtrees are portable
- Hot path cap at 5,000 tokens; admission control prevents thrashing
- Auto-generated branch summaries via LLM pass with human approval gate (not hand-curated)
- Tag vocabulary is folksonomy (free-form), consolidation merges synonyms
- Bootstrap update pulls from GitHub, never from local install folder
- MCP rejected for compass busywork; CLI Python is the right tool

## Learnings (captured as `.compass/lessons/`)

- `LESSON-glob-hidden-dirs-prefix` - Glob needs `**/` to traverse `.compass/`
- `LESSON-hook-if-clause-no-or` - hook `if` doesn't support `||`
- `LESSON-hook-type-prompt-no-skills` - prompt hooks can't invoke skills, use agent type
- `LESSON-no-agent-bookkeeping` - mechanical work belongs in scripts/hooks/JIT
- `LESSON-windows-crlf-breaks-linux-container-scripts` - Python `open('w')` writes CRLF on Windows
- `LESSON-test-driven-tasks-dont-discriminate` - frontier models already read-tests-first
- `LESSON-wikilink-validator-skip-code` - skip code blocks before resolving wikilinks
- `LESSON-tag-index-trades-cost-for-directed-retrieval` - tag-index gives thoroughness + speed but not auto-cheaper tokens; SPEC-003's 30% claim falsified on N=1

## Blockers

None hard. Soft: SPEC-003's 30% claim needs more queries to know if it holds anywhere or fails everywhere - this affects the framing of the design's value proposition but does not block the next work (CLI build).

## Action Items (Next Session)

1. **Write SPEC-004 and ADR-005 for the `compass` Python CLI.** Hypothesis: moving the PostToolUse hook from agent type to command type running `compass sync` will reduce per-session token usage by at least 80% on bookkeeping operations, with no loss of vault integrity (validated by running `compass validate` and confirming zero new findings vs the current LLM-hook implementation).
2. **Build `plugin/bin/compass`** (Python entry point) with commands:
   - `compass sync` - index-sync mechanical work
   - `compass next-num <type>` - JIT numbering
   - `compass tag-index` - included in sync
   - `compass validate` - wikilinks + frontmatter + caps
   - `compass tree` - render hierarchical spec tree
   - `compass hot-path` - print hot-path token count
   - `compass promote <spec>` - git mv + frontmatter edit
   - `compass clean-tmp` - delete `tmp/extraction-log-*.md` older than 30 days
   - `compass touched <spec>` - working-set marker for admission control
   - `compass admit-check <spec>` - returns 0/1 for hot-path expansion
3. **Convert `plugin/hooks/hooks.json` PostToolUse from `type: agent` to `type: command`** running `compass sync`. Drop from 3-5K tokens per fire to 0.
4. **Shrink skills**: `index-sync/SKILL.md`, `vault-health/SKILL.md`, parts of `promote-spec/SKILL.md` become "call CLI, surface findings" - down from hundreds of lines of protocol.
5. **Validation**: write `compass validate` test fixtures; verify it catches the broken-wikilink scenario, missing-frontmatter scenario, cap-exceeded scenario. Then run on the dogfood vault and confirm zero false positives.
6. **End-to-end test**: trigger a vault write, confirm the PostToolUse command hook fires `compass sync`, confirm tag-index and root index update, confirm zero tokens consumed.

After CLI is shipped and validated:
7. Address remaining scientific-method recommendations (plan predictions, lesson polarity).
8. Run the 5-10-query sweep for the SPEC-003 cost hypothesis.
9. Build the working-set tracker and admission-control gate (touched/admit-check above are the primitives).

## Uncommitted changes

None. Two commits pushed this session:
- `1b08764` - methodology infrastructure batch
- `3d562c1` - bootstrap GitHub pull + SPEC-001 north-star goals

`git status` is clean.

## Context for Resuming

- The dogfood vault is fully populated and exercises every Compass mechanism. Use it as a test fixture.
- The bench harness at `bench/` works end-to-end on Windows after three real-bug fixes (CRLF, double-encoding, tag truncation). The custom adapter for Compass arm against Terminal-Bench is the remaining bench infrastructure work, but it's not the priority right now.
- Roger's stated north star goals are now in SPEC-001: accuracy, perfect memory, almost zero cache misses, low token usage. The CLI work directly serves #4 and indirectly serves #3 (by freeing tokens for non-bookkeeping context).
- The previous session ran in plan mode for the bench work; the auto mode flag was set later. Either should work for the CLI build.
- Be honest about empirical findings even when they falsify our own design claims. The SPEC-003 30% number was a guess and the data killed it. Capturing that as a lesson preserved the methodology's integrity. Next session should not handwave the validation.
- The user prefers concise, evidence-based answers. No em-dashes ever. Skip ceremony unless it's earning value. Spawn parallel agents for diverse perspectives when the question is consequential.
- We have ~30 minutes of token budget remaining at session end. Sufficient for this handoff and a clean shutdown but not for substantial new work.
