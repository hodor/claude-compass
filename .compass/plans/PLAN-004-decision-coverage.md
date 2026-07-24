---
title: Decision Coverage Implementation (D-NN Parser, Coverage Gate, Audit)
type: plan
status: approved
confidence: high
area: methodology
tags: [decision-coverage, parser, cli, gates, planner, validator, traceability]
created: 2026-07-24
updated: 2026-07-24
approved: 2026-07-24
git_branch: "master"
git_commit: "7b5b5a8"
author: "planner agent"
depends_on: ["[[SPEC-007-decision-coverage-tracing]]", "[[ADR-007-decision-coverage-mechanism]]", "[[RESEARCH-decision-coverage-impl]]"]
---

# Decision Coverage Implementation (D-NN Parser, Coverage Gate, Audit)

## Goal

Make decisions survive the pipeline mechanically: `- **D-NN:**` bullets in specs/ADRs become parseable units, `compass decisions` and `compass coverage` check that plans claim them, the planner honors the exit-1 gate post-approval/pre-distribution, and the validator audits per-task citations. Implements [[SPEC-007-decision-coverage-tracing]] per [[ADR-007-decision-coverage-mechanism]], grounded in [[RESEARCH-decision-coverage-impl]] (GSD prior art verified at source).

## Prerequisites

- SPEC-007 and ADR-007 approved (done 2026-07-23/24).
- [[PLAN-003-hybrid-hierarchy]] COMPLETE. This plan's citation resolution (ADR-007 D-04: "resolved through the same name resolution as validate") reuses the `resolvable_names_map` PLAN-003 puts in vaultlib, and vaultlib must be stable before this plan appends to it.

## Desired End State

- `vaultlib.strip_fenced_code(text) -> (text, unterminated_fence)` exists; the parser never silently swallows content after an unterminated fence.
- `decisionslib.extract_decisions(text)` returns the three-outcome contract (`parsed` / `none-present` / `could-not-parse`) with parse-miss poisoning and shape heuristics; the 5 legacy ADRs parse `none-present`, the new ADRs and SPEC-007/009 parse cleanly.
- `compass decisions <doc>` lists a document's decisions, exit 1 on `could-not-parse`. `compass coverage <plan> [--against <doc>...]` prints the coverage table, exit 1 on any uncovered trackable decision or unparseable source.
- Plan task lines carry an optional `decisions: [...]` field with source-qualified citations (`<doc-stem>/D-NN`); the planner runs the gate; the validator re-runs it report-only and audits each task's citations.
- The obsidian and spec skills document the convention; `compass coverage` on PLAN-003/004/005 exits 0.

## What We're NOT Doing

- Retrofitting the 5 existing ADRs (ADR-007 D-08: new-only migration; they parse `none-present` by construction and their plans already shipped).
- Any gate in the PostToolUse hook path (D-07: the never-exit-2 invariant of [[ADR-005-compass-cli-for-mechanical-work]] is untouched; the gate is the planner honoring an exit code).
- Scanning handoffs as decision sources (D-09: declared sources only - specs and decisions).
- A vault-wide `compass validate` decision pass. D-06 defines the command surface as the two dedicated commands; `validate.py` is not touched by this plan (keeps ownership clean against PLAN-003's landed state and PLAN-005).
- Coverage output written into vault files. The report is ephemeral stdout (research contradiction 2: no second append-only-vs-regen split).

## Constraints (all tasks)

- CLI never exits 2; LF endings; `python`/`python3`; stdlib only; tests in stdlib `unittest` under `plugin/cli/tests/`, full suite per task: `python -m unittest discover -s plugin/cli/tests`.

## Phases

### Phase 1 - Parser core

- [x] TASK-022: `strip_fenced_code` in vaultlib - complexity: S, depends_on: none, files: [plugin/cli/vaultlib.py, plugin/cli/tests/test_vaultlib.py], decisions: [ADR-007-decision-coverage-mechanism/D-03]
  - New function `strip_fenced_code(text) -> (stripped_text, unterminated_fence)`: removes fenced code blocks up front, returns the flag when a fence never closes (the flag feeds could-not-parse evidence). Companion `strip_inline_code(text)` for backtick spans, per [[LESSON-wikilink-validator-skip-code]]. Additive only - the existing validate fence toggle is NOT reused or modified (ADR-007 D-03 names its silent-swallow failure mode as the reason).
  - Automated verification: unittest - terminated fences removed, prose preserved with stable line count for line-number reporting; unterminated fence -> flag True and remainder NOT silently consumed; inline spans stripped; no `\r` in any write path touched.
  - Manual verification: none beyond tests.

- [x] TASK-023: `decisionslib` three-outcome parser - complexity: L, depends_on: TASK-022, files: [plugin/cli/decisionslib.py, plugin/cli/tests/test_decisionslib.py], decisions: [ADR-007-decision-coverage-mechanism/D-01, ADR-007-decision-coverage-mechanism/D-02, ADR-007-decision-coverage-mechanism/D-03, SPEC-007-decision-coverage-tracing/D-01, SPEC-007-decision-coverage-tracing/D-02]
  - `extract_decisions(text) -> (decisions, outcome)`. Decision unit: `- **D-NN:** text` (continuation lines indented) under headings matching `^#{2,3}\s*Decisions?\b` case-insensitive (covers spec `## Decisions (made by the human)` and ADR `## Decision`) - D-01. Grammars: colon form + titled-colon form, titled-colon checked LAST (strict-superset ordering per GSD), plus the em-dash form as cheap insurance for pasted content. Opt-outs: `[informational]`/`[deferred]` bracket tags and a discretion subheading make a bullet non-trackable but still parsed and recorded - D-02. Fail-loud: parse-miss poisoning (one malformed `- **D-` bullet forces `could-not-parse` even if others parsed) and decision-shape heuristics (a `\bD-` token, an uppercase ID-shaped bold lead-in bullet, or an unterminated fence with zero extractions -> `could-not-parse`, never a silent pass; prose bold bullets like `- **Scope:**` stay `none-present`) - D-03, spec D-02. Each decision record: `id`, `text`, `trackable`, `tags`, `line`.
  - Automated verification: unittest per grammar and per outcome; poisoning case (2 good + 1 malformed bullet -> could-not-parse); discretion subheading case; tagged bullet parsed but non-trackable; heading with prose only -> none-present; D- token in prose with no heading -> could-not-parse.
  - Manual verification: none beyond tests (TASK-024 is the real-world check).

- [x] TASK-024: Parser test corpus drawn from the real vault - complexity: M, depends_on: TASK-023, files: [plugin/cli/tests/fixtures/decisions/, plugin/cli/tests/test_decision_corpus.py], decisions: [ADR-007-decision-coverage-mechanism/D-03, ADR-007-decision-coverage-mechanism/D-08, SPEC-007-decision-coverage-tracing/D-01, SPEC-007-decision-coverage-tracing/D-02]
  - The ADR's load-bearing risk: too-eager heuristics cause false format-mismatch failures and authors route around the convention. Corpus copied verbatim from the vault into fixtures: ADR-001..005 -> `none-present` (mechanically proves D-08's premise that legacy ADRs need no retrofit); SPEC-007, SPEC-009, ADR-006/007/008 -> `parsed` with exact expected ID lists (6, 1, 7, 9, 6); seeded mutations of real content -> `could-not-parse` (broken bold bullet, unterminated fence, stray D- token); fenced D-NN examples (as in this plan's own docs) -> ignored.
  - Automated verification: `python -m unittest discover -s plugin/cli/tests` green; corpus test asserts every expected (document, outcome, id-list) triple.
  - Manual verification: human spot-checks the expected-outcome table against 2-3 source documents.

**Phase boundary (dependency):** commands consume the parser; the corpus proves the parser before anything gates on it.

### Phase 2 - Commands

- [ ] TASK-025: `compass decisions <doc>` - complexity: M, depends_on: TASK-024, files: [plugin/cli/commands/decisions.py, plugin/cli/maincli.py, plugin/cli/tests/test_commands.py], decisions: [ADR-007-decision-coverage-mechanism/D-06, SPEC-007-decision-coverage-tracing/D-01]
  - Resolve `<doc>` (stem or path-qualified) via vaultlib's `resolvable_names_map`; print one row per decision: ID, trackable flag, tags, first-line text, plus the outcome. Exit 0 on `parsed`/`none-present`, exit 1 on `could-not-parse` (never 2). Registers `decisions` in `COMMAND_SPECS`.
  - Automated verification: fixture doc -> table matches; malformed doc -> exit 1 with a "could not parse decisions" message (fail loud, not "nothing to check"); unknown doc -> exit 1 with resolution error; ambiguous stem -> error listing candidates.
  - Manual verification: `compass decisions ADR-007-decision-coverage-mechanism` on the real vault prints 9 rows.

- [ ] TASK-026: `compass coverage <plan> [--against <doc>...]` - complexity: L, depends_on: TASK-025, files: [plugin/cli/commands/coverage.py, plugin/cli/maincli.py, plugin/cli/tests/test_commands.py], decisions: [ADR-007-decision-coverage-mechanism/D-04, ADR-007-decision-coverage-mechanism/D-05, ADR-007-decision-coverage-mechanism/D-06, ADR-007-decision-coverage-mechanism/D-09, SPEC-007-decision-coverage-tracing/D-05, SPEC-007-decision-coverage-tracing/D-06]
  - Default source set: the plan's `depends_on` filtered to documents of `type: spec` or `type: decision` (D-05; exactly spec D-06's default roles, zero ceremony); `--against` overrides. Handoffs and any other type are never scanned (D-09). Citations are source-qualified `<doc-stem>/D-NN` matched with word boundaries over the plan body; bare `D-NN` citations are invalid and warned (D-04). A `could-not-parse` source surfaces in the report AND forces exit 1 regardless of other rows (multi-source partial failure stated explicitly, per research gap 2). Output: `Source | Decision | Trackable | Status` table + counts + one-line summary. Exit 1 on any uncovered trackable decision or unparseable source, else 0 (D-06). The default binding (sources = depends_on spec/decision; gate transition = plan approval) lives behind ONE lookup function, the config seam [[SPEC-009-configurable-pipeline-workflows]] later re-points (spec D-05/D-06).
  - Automated verification: fixture plan covering 3 of 4 decisions -> table shows 1 uncovered, exit 1; all covered -> exit 0; `[deferred]` decision uncovered -> not counted, exit 0; one source malformed -> exit 1 with the other source's rows still printed; bare `D-01` citation -> warned, not counted.
  - Manual verification: run against PLAN-002 (sources ADR-005 + SPEC-004, both none-present) -> "no trackable decisions", exit 0.

**Phase boundary (dependency):** the gate exists; now the pipeline learns to invoke it.

### Phase 3 - Pipeline integration + dogfood

- [ ] TASK-027: Planner gate + `decisions:` task field - complexity: M, depends_on: TASK-026, files: [plugin/templates/agents/planner.md, plugin/skills/plan/SKILL.md], decisions: [ADR-007-decision-coverage-mechanism/D-05, ADR-007-decision-coverage-mechanism/D-07, SPEC-007-decision-coverage-tracing/D-03, SPEC-007-decision-coverage-tracing/D-04, SPEC-007-decision-coverage-tracing/D-05]
  - `planner.md`: task-line grammar gains optional `decisions: [<doc-stem>/D-NN, ...]` (mirrors `files:`); step 5 runs `compass coverage` on the draft and presents the table with the plan; step 6 re-runs it after approval and REFUSES task distribution while exit != 0 (the gate at the plan boundary, bound to the review->approved transition + distribution - D-07, spec D-03/D-05). `plan/SKILL.md` iterate mode: ripple-check row for the `decisions:` field; task edits re-run coverage.
  - Automated verification: grep planner.md for `decisions:` grammar and the `compass coverage` invocation at both steps -> present; grep plan/SKILL.md ripple table -> present.
  - Manual verification: read both docs end-to-end for coherence; confirm the gate wording is post-approval pre-distribution, with no mid-build gating added (spec D-04).

- [ ] TASK-028: Validator coverage audit - complexity: M, depends_on: TASK-026, files: [plugin/templates/agents/validator.md], decisions: [ADR-007-decision-coverage-mechanism/D-07, SPEC-007-decision-coverage-tracing/D-04]
  - New protocol step: run `compass coverage <plan>` REPORT-ONLY with the mandatory `Check / Command run / Output observed / Result` block; per-task audit crossing each task's `decisions:` citations against that task's diff, classifying cited-but-no-evidence and implemented-but-uncited (same shape as the existing checkbox audit). New report section; validator stays read-only and never gates (spec D-04: audit, not gate).
  - Automated verification: grep validator.md for the coverage step, the per-task audit classifications, and the report section -> present.
  - Manual verification: read the amended protocol; confirm it does not turn the audit into a block.

- [ ] TASK-029: Document the convention + dogfood run - complexity: M, depends_on: TASK-026, TASK-027, files: [plugin/skills/obsidian/SKILL.md, plugin/skills/spec/SKILL.md], decisions: [ADR-007-decision-coverage-mechanism/D-01, ADR-007-decision-coverage-mechanism/D-02, ADR-007-decision-coverage-mechanism/D-08, SPEC-007-decision-coverage-tracing/D-01]
  - Obsidian skill: spec template's Decisions section and the ADR Decision section document `- **D-NN:** text` bullets, `[informational]`/`[deferred]` tags, the discretion subheading, and the source-qualified citation token; plan template task line shows `decisions:`. Spec skill: teach emitting the Decisions section for human rulings. Note that pre-convention documents parse `none-present` and are not retrofitted (D-08). Dogfood acceptance: `compass decisions` on ADR-006/007/008 -> parsed with 7/9/6 IDs; `compass coverage` on PLAN-003, PLAN-004, PLAN-005 -> exit 0 each (this very plan set passes its own gate).
  - Automated verification: the three `compass decisions` runs and three `compass coverage` runs above, exit codes 0, output captured; full unittest suite green.
  - Manual verification: human reviews the documented convention for ceremony weight (spec falsification criterion: authoring must stay nearly as light as writing the sentence).

## Phasing logic

Parser before commands (commands consume it), corpus before anything gates (the load-bearing risk), commands before pipeline prose (skills must reference a command that exists), dogfood last as acceptance.

## Ownership boundary (vs [[PLAN-005-model-table]], running in parallel)

- This plan touches `vaultlib.py` ONLY to append the new `strip_fenced_code`/`strip_inline_code` functions; PLAN-005 never touches vaultlib. All other CLI code is new modules (`decisionslib.py`, `commands/decisions.py`, `commands/coverage.py`).
- **Contact point 1 - `maincli.py`:** both plans append `COMMAND_SPECS` entries. Rule: PLAN-005's registration task (TASK-031) merges AFTER this plan's TASK-026 merge. Everything else runs parallel.
- **Contact point 2 - `planner.md` / `validator.md`:** this plan edits their BODIES (TASK-027/028); PLAN-005's TASK-033 rewrites their frontmatter `model:`/`effort:` lines. Rule: TASK-033 merges after TASK-027 and TASK-028.
- Exclusive to this plan: `plugin/skills/plan/SKILL.md`, `plugin/skills/obsidian/SKILL.md`, `plugin/skills/spec/SKILL.md`. Exclusive to PLAN-005: setup/update/methodology/checkup skills, the other 11 agent templates, its own new CLI modules.

## Decision coverage (by hand)

| ADR-007 ruling | Claimed by |
|---|---|
| D-01 decision unit + heading regex + local IDs | TASK-023, TASK-029 |
| D-02 opt-out tags + discretion subheading | TASK-023, TASK-029 |
| D-03 three-outcome parser + poisoning + strip_fenced_code | TASK-022, TASK-023, TASK-024 |
| D-04 source-qualified citations via validate's resolution | TASK-026 |
| D-05 `decisions:` field + depends_on-derived source set | TASK-026, TASK-027 |
| D-06 command surface + exit-1 contract | TASK-025, TASK-026 |
| D-07 gate at planner distribution; validator report-only | TASK-027, TASK-028 |
| D-08 new-only migration | TASK-024, TASK-029 |
| D-09 declared sources only, handoffs out | TASK-026 |

| SPEC-007 decision | Claimed by |
|---|---|
| D-01 ADR rulings are discrete ID'd units | TASK-023, TASK-024, TASK-025, TASK-029 |
| D-02 fail-loud parsing contract | TASK-023, TASK-024 |
| D-03 blocking gate at the plan boundary | TASK-027 |
| D-04 task-level citation + audit, no mid-build gates | TASK-027, TASK-028 |
| D-05 gate bound to a declared transition (seam) | TASK-026, TASK-027 |
| D-06 workflow-declared roles, shipped default | TASK-026 |

All 9 ADR rulings and all 6 spec decisions claimed. A future `compass coverage PLAN-004` resolves sources SPEC-007 + ADR-007 from `depends_on` and finds every trackable decision cited above.

## Risks

- **Heuristics too eager -> false could-not-parse -> authors route around the convention** (ADR load-bearing risk). Mitigation: TASK-024's real-vault corpus is a hard gate before any command ships; legacy ADRs must parse `none-present`.
- **The planner honoring an exit code is prose-enforced** until SPEC-009's gate rail exists (ADR load-bearing risk 2). Accepted and flagged; the seam function in TASK-026 is the hardening hook.
- **Citation ceremony creep.** Mitigation: `decisions:` is optional per task; plan-body citations count for plan-level coverage; TASK-029's manual check reviews ceremony weight.

## Inherited Questions (from spec)

All seven SPEC-007 open questions were resolved by [[ADR-007-decision-coverage-mechanism]]: format (D-01), opt-out expression (D-02), retro migration (D-08), gate transition naming (D-07 + seam), fail-loud contract (D-03), template composition and handoff scope (D-09 + TASK-029), validate-vs-subcommand (D-06: dedicated commands). None remain open.
