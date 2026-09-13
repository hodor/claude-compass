---
title: Active Tasks
updated: 2026-09-13
---

# Active Tasks

## Sizing + discoverability initiative

Triggered by a live failure in another project: a vision session produced seven epic-sized needs and Compass proposed seven flat specs with no signal anything was wrong.

- [ ] Open: pin the project where the seven-monster-specs session happened ([[LESSON-pin-the-motivating-datum]]).

## Per-domain organization initiative

- [ ] D-13 follow-up: grep across all indexes made the most obvious first move for agents (capability + rule nudge; folds into TASK-119's strategy work)
- [ ] v0.15.0's premature skill/sync edits were reverted; index depth-0 rule stays (shipped); everything further waits on the plan.

## PLAN-018 Wave 1: research covers the whole spec

Plan: [[PLAN-018-research-covers-the-whole-spec]] (approved 2026-09-13). Pause after wave 1 for the human's manual checks.

- [ ] TASK-120: Ship the curated source list with a retriever apiece - a data file holding one entry per source the spec names as shipped, each carrying its coverage, its access route, its key requirement, whether it is reachable by script or only through a browser, and the retrieval call that actually fetches from it; plus the sources tested and found dead or closed, kept as a do-not-try record rather than dropped; and the parser that reads it - complexity: M, depends_on: none, files: [plugin/cli/sources.yaml, plugin/cli/sourceslib.py, plugin/cli/tests/test_sourceslib.py], decisions: [SPEC-023-research-covers-the-whole-spec/D-03, SPEC-023-research-covers-the-whole-spec/D-09]
- [ ] TASK-121: Give the source list a command - `compass sources` prints the list, and `--check` judges a source by the response content type rather than its status code - complexity: M, depends_on: TASK-120, files: [plugin/cli/commands/sources.py, plugin/cli/maincli.py, plugin/cli/tests/test_sources.py], decisions: [SPEC-023-research-covers-the-whole-spec/D-03]
- [ ] TASK-122: Ship the methodology catalog as a skill - each methodology the research found, with its own steps, inputs, output, the question shape it fits, and the failure modes its own authors name, so an agent picks one and says which - complexity: M, depends_on: none, files: [plugin/skills/research-methods/SKILL.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-06, SPEC-023-research-covers-the-whole-spec/D-03, SPEC-023-research-covers-the-whole-spec/D-09]
- [ ] TASK-123: Put the marks and the grade on the findings - amend the research document template so every finding carries its mechanical marks and records whether a grade was applied, and replace both copies of the four-approach list with a pointer at the catalog - complexity: S, depends_on: TASK-122, files: [plugin/skills/obsidian/SKILL.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-09, SPEC-023-research-covers-the-whole-spec/D-03]
- [ ] TASK-124: Turn the research entry point from a router into a scope derivation - it reads the whole spec, walks its sections into investigation axes, inserts the human's own questions ahead of everything, tells him what grading the run intends to apply and accepts his refusal, blocks on his reply, and enumerates what the session offers before any agent runs - complexity: M, depends_on: TASK-120, files: [plugin/skills/research/SKILL.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-01, SPEC-023-research-covers-the-whole-spec/D-02, SPEC-023-research-covers-the-whole-spec/D-07, SPEC-023-research-covers-the-whole-spec/D-09], lessons: [LESSON-verify-wiring-by-call-site-grep]
- [ ] TASK-125: Teach the researcher agent the whole-spec habit - it states the methodology it chose, marks and grades every finding under the disclosure the gate made, reads a library's own source rather than its documentation, uses what the session offers, and reports a gap it cannot close as a gap rather than filling it - complexity: M, depends_on: TASK-122, TASK-123, TASK-124, files: [plugin/templates/agents/researcher.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-01, SPEC-023-research-covers-the-whole-spec/D-04, SPEC-023-research-covers-the-whole-spec/D-06, SPEC-023-research-covers-the-whole-spec/D-07, SPEC-023-research-covers-the-whole-spec/D-09], lessons: [LESSON-verify-wiring-by-call-site-grep]
- [ ] TASK-126: Let codebase research reach outside the repository - the same skill that documents this repo also fetches and reads a library's canonical source, matched to the installed version where the ecosystem allows it - complexity: M, depends_on: none, files: [plugin/skills/research-codebase/SKILL.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-04, SPEC-023-research-covers-the-whole-spec/D-07]
- [ ] TASK-127: Rewrite the Research section of the shipped pipeline rules so the invariants hold wherever research runs, not only inside one skill - complexity: S, depends_on: TASK-123, TASK-124, files: [plugin/templates/rules/compass-pipeline.md], decisions: [SPEC-023-research-covers-the-whole-spec/D-01, SPEC-023-research-covers-the-whole-spec/D-02, SPEC-023-research-covers-the-whole-spec/D-05, SPEC-023-research-covers-the-whole-spec/D-09]
- [ ] TASK-128: Close the wave by making the changes real in this repo and stamping the release - refresh the local install from `plugin/`, bump the plugin version, and confirm the installed copy reports healthy - complexity: S, depends_on: TASK-120, TASK-121, TASK-122, TASK-123, TASK-124, TASK-125, TASK-126, TASK-127, files: [plugin/.claude-plugin/plugin.json]

## Research covers the whole spec (SPEC-023)

- [ ] [[specs/pipeline/SPEC-024-walled-sources-through-the-browser]] awaits the human's ruling.
- [ ] Open: a text-and-data-mining request to ACM is the human's to send if wanted.

## Next Up

- [ ] SubagentStop typed-signal fix, fleet-wide (payload evidence captured: `agent_type` empty string). Queued in [[backlog]].
- [ ] [[SPEC-006-multi-host-agent-cli-support]] hosts: hermes first, then deepseek-harness (dsh; fit assessed in [[research/distribution/RESEARCH-deepseek-harness-fit]], 2026-09-04), then Kimi Code / Codex.
- [ ] Blinded rerun of the test-bar experiment ([[LESSON-blind-the-author-in-self-validation]]).
- [ ] Review and approve all plugin files - 3/21 approved, paused since 2026-03-12; largely superseded by the per-file reviews every later plan performed.

## Blocked

- Fleet pushes outstanding from the v0.6.x waves: 7 projects have no git, 2 no remote, 1 has all Compass paths gitignored (iwyc-unreal), 4 were push-rejected behind their remotes (3 ue5-editor-mcp checkouts + wt-spec056) and need a human pull/rebase call. pg-jira-exporter's remote no longer exists.
