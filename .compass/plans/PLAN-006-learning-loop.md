---
title: "Learning Loop Implementation (Harness-Owned Capture, Catalog Retrieval, Lesson Coverage)"
type: plan
status: done
approved: 2026-08-05
completed: 2026-08-06
confidence: medium
area: methodology
tags: [lessons, learning-loop, capture, triggers, retrieval, lesson-coverage, hooks, cli, install-drift]
created: 2026-08-05
updated: 2026-08-05
author: "planner agent"
depends_on: ["[[SPEC-012-learning-loop]]", "[[RESEARCH-lesson-capture-failure]]", "[[RESEARCH-hermes-memory-mechanics]]", "[[RESEARCH-grep-vs-graph-experiment]]"]
summary: "Learning Loop Implementation: harness-owned capture, catalog retrieval, lesson coverage (approved 2026-08-05)"
---

# Learning Loop Implementation (Harness-Owned Capture, Catalog Retrieval, Lesson Coverage)

## Goal

Close the loop [[SPEC-012-learning-loop]] declares broken. Capture stops being wired to the `/compass:build` phase pause and becomes a deterministic counter plus signal check owned by the harness, firing on events every real session reaches. The proven extraction core is carried over untouched, every firing writes a machine-readable trace so fire rate is measurable fleet-wide, install drift becomes detectable, relevant lessons reach the agent through a CLI call instead of a catalog crawl, and a coverage-style audit reports whether they were cited. Grounded in [[RESEARCH-lesson-capture-failure]] (root cause: trigger point, not triggers), [[RESEARCH-hermes-memory-mechanics]] (counter-triggered harness arithmetic, judgment confined to content, no fire-and-forget blind spot), and [[RESEARCH-grep-vs-graph-experiment]] (lesson retrieval needs no graph substrate).

## Prerequisites

- SPEC-012 approved (2026-08-05). Its D-01..D-04 bind every task below.
- All three source research documents complete. No further research is required before building.
- The CLI test suite is green at HEAD: `python -m unittest discover -s plugin/cli/tests` reports 242 tests OK (verified 2026-08-05).
- The local install in `.claude/` is currently STALE relative to `plugin/`: `.claude/cli/` has no `decisionslib.py`, `commands/coverage.py`, or `commands/decisions.py`. Phase 2's refresh task fixes this, and Phase 3's `compass doctor` is what makes this class of drift detectable rather than silent. Until then, run the CLI as `python plugin/cli/compass <command>` in this repo.

## Desired End State

- The `Stop` and `SubagentStop` hooks are command hooks running `compass capture-check` and `compass capture-signal`. Neither spawns an agent. Whether a capture opportunity runs is integer arithmetic over counters and recorded signals; the model decides only what, if anything, is worth writing.
- Capture opportunities open on events real sessions reach: a handoff written, a validator or debug subagent completing, a build phase summary, or a turn-count interval that also saw at least one recorded signal. The `/compass:build` phase path still works and is now one input shape among several.
- `extract-lessons` accepts an opportunity directory. Its binary triggers, anti-list, dedup against the catalog, 5-line cap, and single-writer routing through `lesson-write` are unchanged in substance; the anti-list gains three buckets carried over from the hermes skip-list.
- Every opportunity appends a row to `.compass/tmp/capture-log.jsonl`, whether it fired, skipped, or wrote nothing. `compass capture-stats` turns those rows into fire rate and write rate, per vault, for a rerun of the 40-vault measurement.
- `compass doctor` detects the install-drift classes the fleet audit found and runs from both `/compass:update` and `/compass:checkup`.
- `compass lessons` returns ranked catalog rows for an area, tag set, free text, or a document, and logs what it surfaced. The planner and builder call it instead of reading and judging the whole catalog.
- Plan task lines carry an optional `lessons:` field. `compass lesson-coverage <plan>` reports cited, uncited-but-surfaced, and unresolvable citations. The validator runs it report-only.

## What We're NOT Doing

- No forked-agent review pass. [[RESEARCH-hermes-memory-mechanics]] flags it as too token-heavy against [[SPEC-004-mechanical-work-off-the-agent-budget]]; the Compass equivalent is a hook-emitted nudge that costs one command process.
- No graph substrate for retrieval (SPEC-012 D-04, discharged by [[RESEARCH-grep-vs-graph-experiment]]: lesson rows carry no `depends_on` or wikilink edges, and tag matching over 14 flat rows is well inside grep's comfort zone). Nothing in this plan depends on [[SPEC-011-vault-graph-queries]], and no task here builds toward it.
- No embeddings, no semantic retrieval, no external memory provider.
- No migration of the outlier vaults' bespoke lesson schemas (ue5-editor-mcp, ae-postvis-ai). Separate cleanup.
- No change to the substance of the extraction core: triggers stay binary, the anti-list stays the filter, `lesson-write` stays the only writer, the 5-line cap stays hard.
- No gate on lesson citation. Decision coverage gates at plan approval; lesson coverage audits and never blocks (see Risks).
- No fleet-wide redistribution run. This plan makes drift detectable; rolling v0.4.x out to 40 vaults stays the separate queued item in [[active]].

## Constraints (all tasks)

- CLI: stdlib only, never exits 2, LF line endings, `python`/`python3` both supported. Tests in stdlib `unittest` under `plugin/cli/tests/`. Full suite per task: `python -m unittest discover -s plugin/cli/tests`.
- Behavior changes land in `plugin/`. A change is not live in this repo until the matching file is copied into `.claude/`; Phase 2 and Phase 5 each carry an explicit refresh step.
- Mechanical work stays off the agent budget ([[SPEC-004-mechanical-work-off-the-agent-budget]], [[LESSON-no-agent-bookkeeping]]). No task may add a bookkeeping step to agent prose that a script can do.
- Hook-path code is best-effort: a failure inside capture bookkeeping must never break the write, the turn, or the subagent that triggered it.

## Mechanism decisions this plan makes

The spec left the trigger mechanism to plan territory. These are the choices the tasks implement, each traceable to research rather than invented here.

- **Counter site and unit:** main-agent turns, counted at `Stop`, state in `.compass/tmp/capture-state.json`, tunables in `.compass/meta/capture.json` (durable, committed). Mirrors hermes `_turns_since_memory` (Finding 6), which counts a unit that exists in every session.
- **Due condition:** `turns_since_capture >= interval` (default 12) AND at least one signal recorded in the window, OR a strong signal on its own (handoff written, validator subagent finished, debug subagent finished, phase summary present). The signal requirement is the precision guard: a pure-conversation session with no vault write and no subagent never opens an opportunity.
- **Nudge shape:** the `Stop` command hook emits the Claude Code stop-hook JSON `{"decision": "block", "reason": ...}` naming the opportunity directory, so the capture pass executes as a real turn rather than as prose the model may skip. Mutex marker written before emitting; bounded re-emit count if the opportunity is still open on a later turn.
- **State format:** JSON, not YAML. The CLI is stdlib-only and has no YAML writer; JSON avoids hand-rolling one for a file written on every turn.

## Phases

### Phase 1 - Capture substrate in the CLI

No behavior change reaches a user in this phase. Everything is new CLI surface with tests, so the hook cutover in Phase 2 lands against code that is already proven.

- [x] TASK-036: `capturelib` - state, counters, signals, deterministic due-check - complexity: M, depends_on: none, files: [plugin/cli/capturelib.py, plugin/cli/tests/test_capturelib.py], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-03], lessons: [LESSON-no-agent-bookkeeping]
  - New module. Durable config at `.compass/meta/capture.json` (`enabled`, `interval`, `max_reemits`, defaults applied when the file is absent or partial); ephemeral state at `.compass/tmp/capture-state.json` (`turns_since_capture`, `signals` list of `{kind, ref, at}`, `open_opportunity`, `reemits`, `last_opportunity_at`). Functions: `load_config`, `load_state`, `save_state`, `record_signal(kind, ref)`, `bump_turn()`, `due(state, config) -> (bool, reason)`, `open_opportunity(kind, triggers, evidence) -> path`, `close_opportunity(id, outcome)`. `due()` is pure arithmetic over the state dict with no I/O and no model call, per SPEC-012 D-03. Corrupt or unreadable state resets to defaults rather than raising: the hook path must never fail loudly.
  - Automated verification: unittest - counter increments and resets; `due()` false below interval; false at interval with zero signals; true at interval with one signal; true on a strong signal below interval; `enabled: false` suppresses every path; corrupt state file recovers to defaults; signal list is bounded and does not grow without limit; JSON written with LF endings.
  - Manual verification: read `capture.json`'s default block and confirm a human can retune the interval without reading code.

- [x] TASK-037: `compass capture-signal --hook` replaces the SubagentStop agent hook - complexity: M, depends_on: TASK-036, files: [plugin/cli/commands/capture_signal.py, plugin/cli/maincli.py, plugin/cli/tests/test_capture_commands.py], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-03], lessons: [LESSON-hook-cli-gate-stdin-on-flag]
  - Reads the SubagentStop event JSON on stdin behind an explicit `--hook` flag (never probe for a tty, per [[LESSON-hook-cli-gate-stdin-on-flag]]). Writes `last_assistant_message` verbatim to `.compass/tmp/subagent-captures/<UTC>_<agent_type>.md` with the same frontmatter the current agent-type hook writes, then records a signal keyed on `agent_type`: `validator-finished`, `debug-finished`, `builder-finished`, else `subagent-finished`. Always exits 0. Registers in `COMMAND_SPECS`.
  - Automated verification: unittest with synthetic stdin per agent type - capture file content byte-identical to input message, frontmatter fields present, signal recorded with the right kind; malformed JSON on stdin exits 0 and records nothing; missing `.compass/` exits 0; capture file path collision within the same second does not overwrite.
  - Manual verification: none beyond tests; the live check is TASK-044.

- [x] TASK-038: `compass capture-check --hook` - the Stop-hook trigger - complexity: L, depends_on: TASK-036, files: [plugin/cli/commands/capture_check.py, plugin/cli/maincli.py, plugin/cli/tests/test_capture_commands.py], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-03]
  - Increments the turn counter, evaluates `due()`, and on due materializes `.compass/tmp/capture-opportunities/OPP-<UTC>/opportunity.json` holding `kind`, fired `triggers`, and `evidence` paths (subagent captures in the window, handoff path, phase-report dir). Writes the mutex marker before emitting anything, then prints the stop-hook JSON `{"decision": "block", "reason": "<one line naming the opportunity dir and the extract-lessons skill>"}`. Not due, disabled, or already emitted for the open opportunity: print nothing and exit 0. An opportunity still open after `max_reemits` turns is closed as `abandoned` with a trace row rather than re-emitted forever. The legacy path is preserved: an unprocessed `phase-reports/*/phase-summary.yaml` opens a `phase` opportunity, exactly the condition the current agent-type hook checks. Always exits 0, including on every internal error.
  - Automated verification: unittest - below interval prints nothing; due prints valid JSON with `decision: block` and the opportunity path; second consecutive call with the same open opportunity prints nothing (mutex holds); re-emit cap honored then abandoned; unprocessed phase-summary opens a `phase` opportunity while a `.processed` marker does not; exit code is 0 in every case including corrupt state and absent vault.
  - Manual verification: in a live session with the hook installed (TASK-044), confirm Claude Code honors the block contract and the agent lands in the capture pass. If the harness does not honor it, the opportunity directory still exists and the next turn re-emits, which is the intended degradation; record which behavior was observed.

- [x] TASK-039: Capture trace log and `compass capture-stats` - complexity: M, depends_on: TASK-036, files: [plugin/cli/capturelib.py, plugin/cli/commands/capture_stats.py, plugin/cli/maincli.py, plugin/cli/commands/sync.py, plugin/cli/tests/test_capture_commands.py, plugin/cli/tests/test_sync.py], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-03]
  - Append-only `.compass/tmp/capture-log.jsonl`, one row per opportunity lifecycle event: `opened`, `skipped` (with the arithmetic reason), `fired`, `closed` (with candidate, written, recurrence, rejected, error counts handed back by `extract-lessons`). This is the direct answer to hermes Finding 11: "reviewed and found nothing" and "never ran" are different rows, never the same absence. `compass capture-stats [--json] [--since YYYY-MM-DD]` prints opportunities opened, fire rate, write rate, and a per-trigger breakdown. Retention: `_clean_logs` in `sync.py` currently deletes `extraction-log-*.md` past 30 days; the JSONL is pruned on a separate, longer horizon (365 days, row-level) so a fleet measurement can look back further than one month.
  - Automated verification: unittest - a full lifecycle produces the expected row sequence; `capture-stats` computes rates from a fixture log including a zero-fire vault; `--json` output parses; a row with an unknown event kind is skipped without crashing; `_clean_logs` prunes 31-day-old extraction logs and leaves a 31-day-old capture-log row intact; 366-day-old rows are pruned.
  - Manual verification: run `capture-stats` on this vault after Phase 2's dogfood and confirm the numbers match what the session actually did.

- [x] TASK-040: Record signals from the vault-write path - complexity: S, depends_on: TASK-036, files: [plugin/cli/commands/sync.py, plugin/cli/tests/test_sync.py], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-03]
  - In hook mode only, after the existing self-filter, record a signal for the written artifact: `handoff-written` for `handoffs/**`, `vault-write` otherwise. This is why no edit to `handoff/SKILL.md` appears anywhere in this plan; the handoff trigger site costs the agent nothing because the write itself is the event. Wrapped so any capturelib failure is swallowed: sync's report, self-filter, and never-exit-2 behavior are unchanged.
  - Automated verification: unittest - hook-mode sync on a handoff path records `handoff-written`; on a spec path records `vault-write`; on a generated output (index.md, tag-index.yaml) records nothing; a capturelib exception leaves sync's exit code and report untouched; the existing sync test suite still passes unmodified.
  - Manual verification: none beyond tests.

**Pause point:** when automated verification passes, wait for the human to confirm manual verification succeeded before Phase 2. Skip if the human asked for `all-phases` mode.

### Phase 2 - Extraction core generalized, hooks cut over, dogfood

- [x] TASK-041: Generalize `extract-lessons` to opportunity inputs - complexity: M, depends_on: TASK-038, files: [plugin/skills/extract-lessons/SKILL.md, plugin/cli/commands/capture_close.py, plugin/cli/maincli.py, plugin/cli/tests/test_capture_commands.py], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-02, SPEC-012-learning-loop/D-03]
  - Amended at build time (2026-08-05, human-approved): (a) a `compass capture-close` command so the extraction pass can close its opportunity as `fired` with the candidate/written/recurrence/rejected/error counts the trace log consumes - Phase 1 exposed `close_opportunity` only as a library function the skill cannot call; (b) a contradiction branch - when opportunity evidence contradicts an existing active lesson, the extraction pass may revise or archive that lesson through `lesson-write`, traced like any other outcome, so mistaken lessons are corrected autonomously instead of waiting for consolidation or human notice.
  - Input contract becomes an opportunity directory containing `opportunity.json`; `phase-summary.yaml` stays a recognized evidence shape inside it, so the build path keeps working unchanged. Documents the widened binary trigger set (fix-loop >= 2, validator deviation, debug invoked, STOP-and-report, plan revised, handoff written, interval reached with signals) and which evidence file each one points the extractor at. Steps 5 through 8 (anti-list, hand to `lesson-write`, extraction log, mutex marker) keep their current wording and semantics; step 9's return line gains the fields TASK-039's `closed` row consumes. The skill remains non-user-facing and still never introspects.
  - Automated verification: grep the skill for the opportunity-dir contract, each new trigger name, the unchanged anti-list step, and the `lesson-write` single-writer routing; confirm no wording change to the 5-line cap or dedup branches (`git diff` on the file shows additions and the input-contract rewrite only).
  - Manual verification: read the amended skill end to end against the current one and confirm the extraction quality bar is identical. The 2026-07-25 ai-songwriting firing is the benchmark: an equivalent phase opportunity must still produce the same 5 candidates through the same filter.

- [x] TASK-042: Anti-list gains the three hermes skip-list buckets - complexity: S, depends_on: none, files: [plugin/skills/lesson-write/SKILL.md, plugin/skills/extract-lessons/SKILL.md], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-03]
  - Amended at build time (2026-08-05): lesson-write gains an explicit archive action. TASK-041's contradiction branch sends archive-intent payloads to lesson-write, but its three branches only create/escalate/refine - nothing flips `status: archived`, so an archive request would silently land as a body edit. Add the archive branch (honor an explicit archive intent: set `status: archived` in file and catalog row, never delete) alongside the anti-list buckets.
  - Adds three buckets, keeping the existing eight verbatim: environment-dependent failures; negative tool claims that would harden into standing refusals; unresolved or untested "recommended approaches" recorded as if validated. Carried over from [[RESEARCH-hermes-memory-mechanics]] Finding 9, which the design takeaways name as directly reusable prompt material. The copy in `extract-lessons` step 5 mirrors the canonical list in `lesson-write`.
  - Automated verification: grep both files for the three new bucket lines and for all eight original buckets still present, character-identical.
  - Manual verification: human reads the eleven buckets as a set and confirms none of them would have rejected any of the 14 lessons currently in the catalog.

- [x] TASK-043: Hook cutover to command hooks - complexity: M, depends_on: TASK-037, TASK-038, TASK-041, files: [plugin/hooks/hooks.json, plugin/skills/build/SKILL.md], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-02, SPEC-012-learning-loop/D-03]
  - `Stop` becomes a command hook running `compass capture-check --hook`; `SubagentStop` becomes a command hook running `compass capture-signal --hook`, both with the same python3-else-python guard the PostToolUse entries use. This retires the last two agent-type hooks and closes the [[backlog]] item on per-turn agent spawns, the largest remaining ongoing Compass token cost. The `SubagentStop` matcher list is preserved. `build/SKILL.md` step 6b now points `extract-lessons` at an opportunity directory built from the phase report rather than at the phase-report dir directly; step 6a is unchanged because `capture-signal` writes the same capture files step 6a renames.
  - Automated verification: parse `hooks.json` as JSON in a test and assert both entries are `type: command`, no `type: agent` entry remains, and each command string references an existing `COMMAND_SPECS` name; grep `build/SKILL.md` for the opportunity-dir invocation.
  - Manual verification: read the hook description block and confirm it states plainly which hook counts what, so the next reader does not have to infer the trigger topology from the command names.

- [x] TASK-044: Refresh the local install and observe one live firing - complexity: M, depends_on: TASK-043, files: [.claude/cli/, .claude/skills/, .claude/hooks/hooks.json], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-03]
  - Copy `plugin/cli`, `plugin/skills/*`, and `plugin/hooks/hooks.json` into `.claude/` (or run `/compass:update`), then restart the session so the new hooks load. Note the starting state: `.claude/cli/` is missing `decisionslib.py`, `commands/coverage.py`, and `commands/decisions.py` today, so this task also repairs an existing drift instance in the dogfood repo. Then exercise the loop end to end in a real session: write a vault file, let a subagent finish, reach the interval, and confirm the capture pass runs.
  - Automated verification: `python .claude/cli/compass capture-stats` runs and reports at least one opportunity; `diff -r plugin/cli .claude/cli` shows no missing module; full unittest suite green.
  - Manual verification: human confirms the session ended with a capture pass they did not ask for, that the resulting lesson (or the logged "all rejected") is defensible, and that the turn did not feel hijacked. This is the falsifiable moment for SPEC-012's hypothesis; if the nudge is annoying rather than useful, say so before Phase 3.

**Pause point:** when automated verification passes, wait for the human to confirm manual verification succeeded before Phase 3. Skip if the human asked for `all-phases` mode.

### Phase 3 - Install verification

- [x] TASK-045: `compass doctor` - complexity: M, depends_on: TASK-043, files: [plugin/cli/commands/doctor.py, plugin/cli/maincli.py, plugin/cli/tests/test_doctor.py], decisions: [SPEC-012-learning-loop/D-01]
  - Amended at build time (2026-08-05, live-firing diagnosis): Claude Code loads hooks ONLY from settings files (`.claude/settings.json` et al.) and registered plugins, never from a bare `.claude/hooks/hooks.json` - so no Compass hook has ever fired in any settings-unregistered vault, this one included, and the fleet audit's 19/40 backstop gap was an undercount. Doctor's hooks check must therefore verify the three hook entries are REGISTERED in a settings file Claude Code reads (parse the `hooks` key), not merely that `.claude/hooks/hooks.json` exists; an unregistered hooks.json is reported as the defect it is, with the fix being settings registration. The setup/update skills gain the same registration step (folded into TASK-046's scope).
  - Checks exactly the drift classes [[RESEARCH-lesson-capture-failure]] Finding 5 found across 40 vaults: `.compass/meta/plugin.yaml` present with a version; `.claude/hooks/hooks.json` present and containing the PostToolUse sync entry plus both capture hooks; `.claude/cli/` present and holding a module for every name in `COMMAND_SPECS` (this is the check that would have caught the dogfood repo's own stale CLI); `.claude/agents/` count; `.claude/skills/` present; `.compass/meta/lessons-catalog.yaml` present. Each check reports OK, WARN, or FAIL with the fix command. Exit 1 on any FAIL, 0 otherwise, never 2.
  - Automated verification: unittest over fixture trees - complete install exits 0; missing hooks file, missing plugin.yaml, and a CLI dir missing one command module each exit 1 naming the specific defect; a v0.2.0-shaped install (skills but no hooks dir) is reported as the drift class it is.
  - Manual verification: run `doctor` against this repo before and after TASK-044's refresh and confirm the before-run fails on the stale CLI.

- [x] TASK-046: Wire `doctor` into update and checkup - complexity: S, depends_on: TASK-045, files: [plugin/skills/update/SKILL.md, plugin/skills/checkup/SKILL.md], decisions: [SPEC-012-learning-loop/D-01]
  - `update/SKILL.md`: a post-copy step runs `compass doctor` and reports its table as part of the update summary, so a half-applied update is visible at the moment it happens. `checkup/SKILL.md`: the Agents and Hooks sections delegate to `compass doctor` instead of describing checks in prose, and the report format gains its rows. The hooks check in checkup currently names a `SubagentStop` builder-to-tester hook that this repo never installed; replace it with what `doctor` actually verifies.
  - Automated verification: grep both skills for the `compass doctor` invocation and for the removal of the stale hook description.
  - Manual verification: read the amended checkup output format and confirm it still reads as a report a human can act on, not a CLI dump.

**Pause point:** when automated verification passes, wait for the human to confirm manual verification succeeded before Phase 4. Skip if the human asked for `all-phases` mode.

### Phase 4 - Retrieval reaches the work

Gated behind Phase 1 to 3 by SPEC-012 D-02: retrieval is worthless until capture produces input.

- [x] TASK-047: `lessonslib` and `compass lessons` - complexity: M, depends_on: TASK-044, files: [plugin/cli/lessonslib.py, plugin/cli/commands/lessons.py, plugin/cli/maincli.py, plugin/cli/tests/test_lessonslib.py], decisions: [SPEC-012-learning-loop/D-02, SPEC-012-learning-loop/D-04]
  - Reads `.compass/meta/lessons-catalog.yaml` rows only, never the lesson bodies, and ranks by tag overlap, area match, summary-token overlap with `--text`, and `score` as the tiebreak. Skips `status: archived`; sorts any lesson carrying `escalated:` to the top with a marker, since those are the ones the current design says the retrieval path is failing. Flags: `--area`, `--tags a,b`, `--text "..."`, `--for <doc>` (reads that document's frontmatter `area`/`tags`), `--top N` (default 5), `--json`. The catalog is machine-generated by `sync` with a fixed row shape, so the reader is a strict line parser that fails loud on an unexpected shape rather than silently returning nothing. No graph traversal and no `depends_on` walk anywhere in this module: [[RESEARCH-grep-vs-graph-experiment]] established that lessons participate in no artifact-graph edges, which is how SPEC-012 D-04 is discharged rather than deferred.
  - Automated verification: unittest over a fixture catalog - tag overlap outranks area-only match; archived rows excluded; escalated row surfaces first; `--for` resolves a document's frontmatter; `--top` bounds output; `--json` parses; a malformed row exits 1 with the row number rather than returning a short list; empty catalog exits 0 with an explicit "no lessons" line.
  - Manual verification: run `compass lessons --for SPEC-012-learning-loop` and `--area methodology` against the real 14-row catalog and confirm a human agrees the top 3 are the relevant ones.

- [x] TASK-048: Retrieval trace and the surfacing sites - complexity: M, depends_on: TASK-047, files: [plugin/cli/commands/lessons.py, plugin/cli/tests/test_lessonslib.py, plugin/templates/agents/planner.md, plugin/templates/agents/builder.md, plugin/skills/lessons/SKILL.md], decisions: [SPEC-012-learning-loop/D-02, SPEC-012-learning-loop/D-04]
  - Every `compass lessons` run appends a row to `.compass/tmp/retrieval-log.jsonl` (`at`, `query`, `context` from an optional `--context` flag, `surfaced` file list), which is what makes SPEC-012's "surfacing is observable" checkable rather than asserted. The planner and builder templates replace their "load the catalog and judge relevance" step with one `compass lessons --for <artifact> --context <agent>` call, moving the crawl off the agent budget per [[SPEC-004-mechanical-work-off-the-agent-budget]]. `lessons/SKILL.md` documents the command as the primary retrieval path and keeps the manual catalog read as the malformed-vault fallback it already describes.
  - Automated verification: unittest - a run appends exactly one well-formed row and the log survives repeated runs; grep the two agent templates for the invocation and for the removal of the manual crawl step; grep `lessons/SKILL.md` for the command.
  - Manual verification: read the planner and builder diffs and confirm the lesson step got shorter, not longer. If an agent template gained prose, the change went the wrong way.

**Pause point:** when automated verification passes, wait for the human to confirm manual verification succeeded before Phase 5. Skip if the human asked for `all-phases` mode.

### Phase 5 - Application is audited

- [x] TASK-049: `lessons:` task field and `compass lesson-coverage <plan>` - complexity: L, depends_on: TASK-047, files: [plugin/cli/commands/lesson_coverage.py, plugin/cli/maincli.py, plugin/cli/tests/test_lesson_coverage.py, plugin/templates/agents/planner.md], decisions: [SPEC-012-learning-loop/D-02]
  - Plan task lines gain an optional `lessons: [LESSON-slug, ...]` field, mirroring the `decisions:` grammar [[PLAN-004-decision-coverage]] introduced. `compass lesson-coverage <plan>` resolves each citation against the catalog, computes what `compass lessons --for <plan>` would surface for the plan's area and tags, and prints a `lesson | cited by | status` table with three statuses: cited, surfaced-but-uncited (advisory), and unresolvable (a citation naming no catalog row). Exit 1 only on an unresolvable citation, which is a typo the author can fix; surfaced-but-uncited never fails the command, because a lesson an author read and correctly judged irrelevant is a normal outcome and gating on it would manufacture ceremony. The planner documents the field and may run the command, but no gate is added at plan approval.
  - Automated verification: unittest over fixture plans - a cited lesson shows cited; a high-ranking uncited lesson shows advisory and exits 0; a citation for a nonexistent lesson exits 1 naming it; a plan with no `lessons:` fields exits 0 with an explicit "no citations" summary; fenced code and inline code never claim (reuse `vaultlib.strip_fenced_code`, as coverage does).
  - Manual verification: add `lessons:` citations to two tasks of this very plan and confirm the command agrees; confirm the ceremony weight is comparable to `decisions:`, which the human judged acceptable in PLAN-004.

- [x] TASK-050: Validator lesson-coverage audit - complexity: M, depends_on: TASK-049, files: [plugin/templates/agents/validator.md], decisions: [SPEC-012-learning-loop/D-02]
  - A new report-only protocol step running `compass lesson-coverage <plan>` with the mandatory `Check / Command run / Output observed / Result` evidence block, directly parallel to the decision-coverage audit the validator already carries. Per-task classification: cited-but-no-evidence-in-the-diff, and surfaced-but-uncited. The validator stays read-only and never gates on the result, matching how it treats decision coverage.
  - Automated verification: grep `validator.md` for the command invocation, the evidence block, both classifications, and the new report section.
  - Manual verification: read the amended protocol and confirm the audit is not phrased as a blocker.

- [x] TASK-051: Document the closed loop, refresh, and acceptance - complexity: M, depends_on: TASK-046, TASK-048, TASK-050, files: [plugin/skills/lessons/SKILL.md, plugin/skills/methodology/SKILL.md, plugin/skills/plan/SKILL.md, .claude/], decisions: [SPEC-012-learning-loop/D-01, SPEC-012-learning-loop/D-02]
  - `methodology/SKILL.md` describes the loop as it now works: capture fires on harness-owned triggers across the whole pipeline rather than at the build phase pause, retrieval runs through `compass lessons`, application is audited at validation. `lessons/SKILL.md` gets the full picture in one place. `plan/SKILL.md` iterate mode gains a ripple-check row for the `lessons:` field, matching the row `decisions:` already has. Then refresh `.claude/` again and run acceptance.
  - Automated verification: full suite `python -m unittest discover -s plugin/cli/tests` green; `python .claude/cli/compass doctor` exits 0; `python .claude/cli/compass capture-stats` reports the opportunities this build produced; `python plugin/cli/compass coverage PLAN-006-learning-loop --against SPEC-012-learning-loop` exits 0.
  - Manual verification: human reads the methodology section and confirms it describes a loop they recognize, and confirms that across the build the capture path fired on its own at least twice without being asked.

**Pause point:** final. Present the acceptance evidence and the `capture-stats` numbers.

## Phasing logic

CLI substrate before hook cutover, because a hook that fires on every turn must not be the place a bug is discovered. Extraction generalization before cutover, because the hook points at it. Install verification after cutover, because `doctor` checks for the hooks the cutover introduces. Retrieval and audit last, in SPEC-012 D-02's order: both are worthless until capture produces input, and the audit needs the retrieval ranking to know what "surfaced" means.

## Parallel-safe tasks

- Phase 1: TASK-037, TASK-038, TASK-039, and TASK-040 all depend on TASK-036 and are otherwise file-disjoint except for the `maincli.py` contact point below.
- Phase 2: TASK-042 has no dependency and can run alongside TASK-041, but both touch `plugin/skills/extract-lessons/SKILL.md`, so they are NOT parallel-safe with each other. Order: TASK-041 then TASK-042.
- Phase 4 and 5: TASK-049 depends only on TASK-047, so it can start alongside TASK-048.

## Ownership and contact points

- **`plugin/cli/maincli.py`:** TASK-037, TASK-038, TASK-039, TASK-045, TASK-047, TASK-049 each append a `COMMAND_SPECS` entry. Registrations merge in task-number order; a builder that runs in parallel must append only its own line and never reorder the list. `tests/test_maincli.py` iterates `COMMAND_SPECS`, so a registration without a command module fails the suite immediately, which is the intended guard.
- **`plugin/cli/capturelib.py`:** created by TASK-036, appended by TASK-039 only. No other task edits it.
- **`plugin/templates/agents/planner.md`:** edited by TASK-048 (retrieval step) and TASK-049 (`lessons:` grammar). Sequential, TASK-048 first.
- **`plugin/skills/lessons/SKILL.md`:** edited by TASK-048 and TASK-051. Sequential.
- **`plugin/cli/commands/sync.py`:** edited by TASK-039 (log retention) and TASK-040 (signal recording). Sequential, TASK-039 first.
- Exclusive to a single task each: `hooks.json` (TASK-043), `build/SKILL.md` (TASK-043), `lesson-write/SKILL.md` (TASK-042), `doctor.py` and its wiring skills (TASK-045, TASK-046), `validator.md` (TASK-050).

## Risks

- **The Stop-hook block contract may not behave as designed in the live harness.** This is the single assumption the trigger topology rests on that no source in the vault verifies. Mitigation: TASK-038's manual verification is exactly this check, and the degradation path is built in (the opportunity directory persists and re-emits on the next turn up to `max_reemits`, so a non-honored block loses timeliness, not the capture). If the contract fails outright, the fallback is a nudge written into the hot path for the next agent to see, which the hermes research names as the cheaper Compass-side equivalent.
- **Precision collapse: vaults fill with trivia the anti-list should have rejected.** This is SPEC-012's own falsification criterion. Mitigations: the interval trigger requires a recorded signal, so idle sessions never fire; the anti-list is unchanged and gains three buckets; TASK-039's trace makes a precision problem visible as a rising write rate with falling quality rather than something noticed months later.
- **Nudge fatigue.** A capture pass at the end of a session the human wanted to end is an interruption. Mitigation: interval default 12 with a signal requirement, `enabled: false` as a one-line opt-out, and TASK-044's manual verification asks the human directly whether it felt hijacked, before three more phases are built on top of it.
- **Lesson coverage becomes ceremony.** Mitigation: advisory only, never a gate, optional per task. The human judged the equivalent `decisions:` weight acceptable in PLAN-004; TASK-049's manual check is a re-judgment against that bar.
- **Two agent-type hooks retire at once.** If `capture-signal` regresses, phase reports lose their source. Mitigation: TASK-037 lands and is tested a full phase before TASK-043 flips the hook, and the capture file format is byte-identical to what the agent hook wrote.

## Inherited Questions (from spec)

All four SPEC-012 open questions are resolved here, not deferred.

- *Which trigger sites ship first.* Handoff-written and subagent-finished (validator, debug) ship in Phase 1 to 2, matching the fleet trace data showing handoffs at 26 per heavy vault. The phase-summary path is preserved rather than replaced.
- *What the cadence counts and where the counter lives.* Main-agent turns, counted at `Stop` by `compass capture-check`, state in `.compass/tmp/capture-state.json`, tunables in `.compass/meta/capture.json`, default interval 12 with a mandatory signal in the window.
- *How pillar 3's citation binds to artifacts.* A `lessons:` task-line field in exact parity with `decisions:`, audited by `compass lesson-coverage` and reported by the validator, never gated.
- *What retrieval keys on before SPEC-011 resolves.* Catalog `tags`, `area`, `summary` tokens, and `score`. [[RESEARCH-grep-vs-graph-experiment]] closes this permanently for lessons: they carry no graph edges, so SPEC-011 would not serve this pillar even if built.

## Decision coverage (SPEC-012)

| SPEC-012 decision | Claimed by |
|---|---|
| D-01 harness-owned triggers, anti-list gates, auditable output | TASK-036, TASK-037, TASK-038, TASK-039, TASK-040, TASK-041, TASK-042, TASK-043, TASK-044, TASK-045, TASK-046, TASK-051 |
| D-02 capture-fix sequenced before retrieval and application | TASK-041, TASK-043, TASK-047, TASK-048, TASK-049, TASK-050, TASK-051 |
| D-03 hermes takeaways bind (harness arithmetic, judgment on content only, every firing traced) | TASK-036, TASK-037, TASK-038, TASK-039, TASK-040, TASK-041, TASK-042, TASK-043, TASK-044 |
| D-04 graph substrate not presupposed, gated on SPEC-011 | TASK-047, TASK-048 |

## Verification of this plan

The coverage gate was run against the source spec before submitting the plan for approval, using `plugin/cli/compass` because the local `.claude/cli/` install is stale (the drift TASK-045 exists to detect).

```
$ python plugin/cli/compass coverage PLAN-006-learning-loop --against SPEC-012-learning-loop
compass coverage: note: 11 bare D-NN token(s) in plans/PLAN-006-learning-loop.md claim nothing; a citation is source-qualified: <doc-name>/D-NN
compass coverage: plans/PLAN-006-learning-loop.md
source                  decision  trackable  status
SPEC-012-learning-loop  D-01      yes        covered (line 69)
SPEC-012-learning-loop  D-02      yes        covered (line 98)
SPEC-012-learning-loop  D-03      yes        covered (line 69)
SPEC-012-learning-loop  D-04      yes        covered (line 138)
summary: 4 trackable decision(s) in 1 source(s): 4 covered, 0 uncovered -> PASS
EXIT=0
```

The bare-token note is expected and matches [[PLAN-004-decision-coverage]]'s behavior: the prose and the coverage table above refer to decisions by their local IDs, which by design claim nothing. Every claim lives in a task's `decisions:` field.
