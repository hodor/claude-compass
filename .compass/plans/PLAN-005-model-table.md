---
title: Model Resolution Table Implementation (Tiers, apply-models, Overrides)
type: plan
status: done
confidence: high
area: methodology
tags: [model-policy, tiers, apply-models, cli, setup, update, cost]
created: 2026-07-24
updated: 2026-07-24
approved: 2026-07-24
git_branch: "master"
git_commit: "7b5b5a8"
author: "planner agent"
depends_on: ["[[SPEC-008-central-model-resolution-table]]", "[[ADR-008-model-resolution-table]]", "[[RESEARCH-model-resolution-impl]]"]
---

# Model Resolution Table Implementation (Tiers, apply-models, Overrides)

## Goal

Turn model/effort assignment into one harness-resolved policy table: abstract tiers (`strong`/`balanced`/`cheap`/`inherit`) mapped by a per-host catalog, resolved at install time by `compass apply-models` into the 13 Compass agent files, overridable per project via `.compass/meta/models.yaml`. Implements [[SPEC-008-central-model-resolution-table]] per [[ADR-008-model-resolution-table]], grounded in [[RESEARCH-model-resolution-impl]] (mechanism verified against official Claude Code docs; GSD resolver read at source).

## Prerequisites

- SPEC-008 and ADR-008 approved (done 2026-07-23/24).
- [[PLAN-003-hybrid-hierarchy]] COMPLETE (it owns `plugin/cli/` core during its window; this plan adds only new modules on top of the landed state).
- Runs in PARALLEL with [[PLAN-004-decision-coverage]] under the ownership boundary below.

## Desired End State

- A policy module in `plugin/cli/` holds: the tier vocabulary, the Claude Code catalog (`strong->opus`, `balanced->sonnet`, `cheap->haiku`), the D-03 default roster for all 13 agents (+ a reserved row for the SPEC-005 summary job), per-tier effort defaults, and deterministic precedence: built-in < `.compass/meta/models.yaml` < environment, bottoming out at `inherit`.
- `compass resolve-model <agent>` prints the resolved model+effort (result on stdout, warnings on stderr, exit 0 always); `compass models` prints the full resolved roster.
- `compass apply-models` rewrites ONLY the `model:`/`effort:` frontmatter of the 13 known Compass agent files in the target dir, LF preserved, idempotent, user-authored agents never touched.
- Setup and update run apply-models after their copy step; the 13 shipped templates are normalized to the built-in table (no more 5-sonnet/6-inherit/2-missing split; `haiku` enters the roster).
- Model policy prose is gone from skills; checkup validates against the table.

## What We're NOT Doing

- Spawn-time resolution (rejected by ADR-008: costs agent tokens, relies on prose compliance). The Agent tool's per-invocation `model` param stays an undocumented-by-us escape hatch; nothing depends on it (ADR load-bearing risk 2).
- Concrete model names in the policy vocabulary (rejected: welds policy to one vendor; SPEC-006 hosts resolve via the catalog, absent hosts degrade to inherit/omit).
- Non-Claude host catalogs. The Claude Code catalog ships first (D-01); per-host rows are SPEC-006's research to fill.
- Measuring the cheap-tier quality claim (ADR load-bearing risk 1). The project override is the escape hatch; measurement is future work, not this plan.
- Touching `vaultlib.py`, `sync.py`, `validate.py`, or any PLAN-003/PLAN-004 CLI module.

## Constraints (all tasks)

- CLI never exits 2; LF endings via `write_text_lf`; `python`/`python3`; stdlib only (the models.yaml subset is parsed by a small stdlib reader, same discipline as the frontmatter parser).
- Tests: stdlib `unittest` in `plugin/cli/tests/`, full suite per task: `python -m unittest discover -s plugin/cli/tests`.
- Only the 13 known Compass agent filenames are ever rewritten ([[LESSON-installer-removes-only-what-it-installed]]).

## Phases

### Phase 1 - Policy data + resolution core

- [x] TASK-030: `modelslib` - tier table, catalog, defaults, precedence - complexity: L, depends_on: none, files: [plugin/cli/modelslib.py, plugin/cli/tests/test_modelslib.py], decisions: [ADR-008-model-resolution-table/D-01, ADR-008-model-resolution-table/D-03, ADR-008-model-resolution-table/D-04, ADR-008-model-resolution-table/D-06]
  - Tier vocabulary `strong`/`balanced`/`cheap`/`inherit`; Claude Code host catalog (strong->opus, balanced->sonnet, cheap->haiku); a host absent from the catalog maps every tier to nothing -> inherit/omit (D-01, the SPEC-006 degradation). Built-in roster per D-03: strong = planner, validator, reviewer, debug; balanced = builder, researcher, tester, vault-analyzer, codebase-analyzer, pattern-finder; cheap = vault-locator, codebase-locator, pr-describe; plus a reserved `index-summary` row (cheap) for the SPEC-005 job. Per-tier effort defaults: strong high, balanced high, cheap low (D-06), per-agent effort override allowed in the same row. Precedence: built-in < `.compass/meta/models.yaml` (whole-tier and per-agent keys) < env `COMPASS_MODEL_<AGENT>`/`COMPASS_EFFORT_<AGENT>` (D-04). `resolve(agent) -> (model, effort, source)` never raises and bottoms out at (`inherit`, tier-default effort).
  - Automated verification: unittest - each precedence rung wins over the one below; unknown agent -> inherit; unknown host -> all tiers inherit; models.yaml with a tier remap and a per-agent pin both honored; malformed models.yaml -> warning + built-ins (never a crash).
  - Manual verification: none beyond tests.

- [x] TASK-031: `compass resolve-model <agent>` + `compass models` - complexity: M, depends_on: TASK-030, files: [plugin/cli/commands/resolve_model.py, plugin/cli/commands/models.py, plugin/cli/maincli.py, plugin/cli/tests/test_commands.py], decisions: [ADR-008-model-resolution-table/D-05, ADR-008-model-resolution-table/D-04]
  - `resolve-model`: result (`model` + `effort`) on stdout, warnings on stderr (parseable output contract), unknown agent -> `inherit` + default effort, exit 0 always. `models`: full resolved roster table with a source column (built-in / project / env) so the human sees which rung won. Registers all three new commands (`resolve-model`, `models`, `apply-models`) in `COMMAND_SPECS` in ONE edit - see ownership boundary: this task's maincli.py change merges after PLAN-004's TASK-026.
  - Automated verification: stdout of `resolve-model planner` is exactly the resolved pair with nothing else; warnings go to stderr; `models` table lists all 13 agents + the reserved row; exit 0 in every case including unknown agent.
  - Manual verification: run both against this repo; eyeball the roster.

**Phase boundary (dependency):** apply-models consumes the resolver.

### Phase 2 - Apply + template normalization

- [x] TASK-032: `compass apply-models` - complexity: L, depends_on: TASK-031, files: [plugin/cli/commands/apply_models.py, plugin/cli/tests/test_apply_models.py], decisions: [ADR-008-model-resolution-table/D-01, ADR-008-model-resolution-table/D-02]
  - Rewrites the `model:` and `effort:` frontmatter lines (insert when missing, replace when present, body and every other frontmatter line untouched) of the 13 KNOWN Compass agent filenames only, in a target dir (default `.claude/agents/`, `--dir` for another target). A tier resolving to nothing emits NO model line (omission degrades to inherit on every host - D-01); LF preserved via `write_text_lf`; idempotent: a second run produces zero changes; files not in the known list (user-authored agents) are never read or written ([[LESSON-installer-removes-only-what-it-installed]]). Prints a per-file change summary; exit 0 always (missing target dir -> warning).
  - Automated verification: unittest - fixture agent dir: fields rewritten correctly for present/missing/absent-field cases; a `custom-user-agent.md` byte-identical after the run; second run reports zero changes; output files contain no `\r` byte; inherit-tier agent gets the field omitted.
  - Manual verification: dry inspection of the change summary on a fixture.

- [x] TASK-033: Normalize the 13 shipped templates - complexity: S, depends_on: TASK-032, files: [plugin/templates/agents/builder.md, plugin/templates/agents/planner.md, plugin/templates/agents/tester.md, plugin/templates/agents/validator.md, plugin/templates/agents/debug.md, plugin/templates/agents/pr-describe.md, plugin/templates/agents/researcher.md, plugin/templates/agents/reviewer.md, plugin/templates/agents/codebase-locator.md, plugin/templates/agents/vault-locator.md, plugin/templates/agents/pattern-finder.md, plugin/templates/agents/codebase-analyzer.md, plugin/templates/agents/vault-analyzer.md], decisions: [ADR-008-model-resolution-table/D-02, ADR-008-model-resolution-table/D-03]
  - Run `compass apply-models --dir plugin/templates/agents` with built-in defaults so the SHIPPED templates already carry the table's Claude values (researcher/reviewer gain their missing rows; locators/pr-describe become `haiku` + `effort: low`; the flat `effort: high` split by tier). A verbatim copy is then policy-correct even before install-time apply; apply-models over defaults is a no-op (idempotency proof on real files). Frontmatter `model:`/`effort:` lines ONLY - agent bodies untouched (see ownership boundary: merges after PLAN-004's TASK-027/028 body edits to planner.md/validator.md).
  - Automated verification: grep all 13 templates: every file has `model:` and `effort:`; values match `compass models` output exactly; re-running apply-models on the templates reports zero changes; git diff shows only frontmatter lines changed.
  - Manual verification: human reviews the 13-line assignment diff against the D-03 roster.

**Phase boundary (dependency):** install flows reference a command and templates that now exist.

### Phase 3 - Install integration + dogfood verification

- [x] TASK-034: Setup/update integration + policy prose cleanup - complexity: M, depends_on: TASK-032, files: [plugin/skills/setup/SKILL.md, plugin/skills/update/SKILL.md, plugin/skills/methodology/SKILL.md, plugin/skills/checkup/SKILL.md], decisions: [ADR-008-model-resolution-table/D-02, ADR-008-model-resolution-table/D-04]
  - Setup step 2 and update step 4 gain one post-copy step: run `compass apply-models` via the copied CLI (`python3`/`python` fallback, same pattern as the hook), so installed agents get the resolved policy; note Claude Code hot-reloads `.claude/agents/`, so re-apply after editing `models.yaml` takes effect without restart. Setup documents `.compass/meta/models.yaml` as the project override (D-04) next to the existing meta files. Cleanup: drop the "Runs on `sonnet` for speed" prose from methodology SKILL (policy lives in the table, not prose); checkup's agent health check validates installed `model:`/`effort:` against `compass models` output instead of bare field presence.
  - Automated verification: grep setup/update for the apply-models step -> present; grep methodology for `sonnet` -> zero hits; grep checkup for the table-based check -> present.
  - Manual verification: read the amended setup/update steps for coherence with the existing copy-only discipline (templates still never pass through the agent's context).

- [x] TASK-035: Dogfood verification on this repo - complexity: S, depends_on: TASK-033, TASK-034, files: [.claude/agents/ (regenerated local install, gitignored), .compass/meta/models.yaml (temporary test override, removed after)], decisions: [ADR-008-model-resolution-table/D-02, ADR-008-model-resolution-table/D-03, ADR-008-model-resolution-table/D-04, ADR-008-model-resolution-table/D-05]
  - Run `compass apply-models` against this repo's `.claude/agents/`. Verify the SPEC-008 success criteria on real files: locators resolve cheap (haiku/low), planner/validator/reviewer/debug resolve strong (opus/high), assignments inspectable via `compass models`. Then: second run -> zero diffs; drop a throwaway user agent file in `.claude/agents/` -> untouched; write a `models.yaml` pinning one agent -> re-apply picks it up, `compass models` shows source=project; remove the override, re-apply restores defaults; no CRLF bytes in any rewritten file.
  - Automated verification: the command sequence above with recorded exit codes and diffs; full unittest suite green.
  - Manual verification: human confirms the resolved roster is the policy they approved in ADR-008 D-03.

## Phasing logic

Resolver before commands (commands consume it), apply before templates (normalization IS an apply run), install prose after the command exists, dogfood last as acceptance.

## Ownership boundary (vs [[PLAN-004-decision-coverage]], running in parallel)

- This plan is new CLI modules (`modelslib.py`, `commands/resolve_model.py`, `commands/models.py`, `commands/apply_models.py`), agent-template FRONTMATTER lines, and the setup/update/methodology/checkup skills. It never touches `vaultlib.py`, `decisionslib.py`, or PLAN-004's commands.
- **Contact point 1 - `maincli.py`:** both plans append `COMMAND_SPECS` entries. Rule: this plan's TASK-031 maincli edit merges AFTER PLAN-004's TASK-026 merge.
- **Contact point 2 - `planner.md` / `validator.md`:** PLAN-004 edits their bodies; this plan's TASK-033 rewrites only their frontmatter `model:`/`effort:` lines. Rule: TASK-033 merges after PLAN-004's TASK-027 and TASK-028.
- Exclusive to PLAN-004: `plugin/skills/plan|obsidian|spec/SKILL.md`, `vaultlib.py`, its new modules. Everything else here is exclusive to this plan.

## Decision coverage (by hand)

| ADR-008 ruling | Claimed by |
|---|---|
| D-01 abstract tiers + per-host catalog + degrade to inherit | TASK-030, TASK-032 |
| D-02 install-time apply-models, known files only, LF | TASK-032, TASK-033, TASK-034, TASK-035 |
| D-03 default roster assignments | TASK-030, TASK-033, TASK-035 |
| D-04 precedence built-in < project < env, never exit 2 | TASK-030, TASK-031, TASK-034, TASK-035 |
| D-05 resolve-model + models command surface | TASK-031, TASK-035 |
| D-06 effort in the same row, per-tier defaults | TASK-030 |

All 6 rulings claimed. [[SPEC-008-central-model-resolution-table]] carries no D-NN decision bullets (parses none-present).

## Risks

- **Locator quality on haiku is unmeasured** (ADR load-bearing risk 1). Mitigation: `models.yaml` is the documented escape hatch (TASK-034); the default gets revisited if quality drops.
- **Frontmatter rewrite corrupts an agent file.** Mitigation: line-targeted rewrite of two known keys only, byte-level tests including a user-agent-untouched assertion and idempotency on real templates (TASK-032/033).
- **`CLAUDE_CODE_SUBAGENT_MODEL` outranks everything Compass emits** (documented host behavior). Mitigation: TASK-034 documents the interaction so "my table entry was ignored" is diagnosable, not mysterious.

## Inherited Questions (from spec)

All four SPEC-008 open questions were resolved by [[ADR-008-model-resolution-table]]: tier vocabulary (D-01), precedence (D-04), effort placement (D-06), multi-host catalog composition (D-01 + SPEC-006 deferral stated in Not Doing). None remain open.
