---
title: Compass CLI Implementation
type: plan
status: done
confidence: high
area: methodology
tags: [cli, python, hooks, automation, token-efficiency, validation]
created: 2026-06-13
updated: 2026-06-14
completed: 2026-06-14
depends_on: ["[[SPEC-004-mechanical-work-off-the-agent-budget]]", "[[ADR-005-compass-cli-for-mechanical-work]]", "[[RESEARCH-cli-and-hook-command-contract]]"]
summary: "Compass CLI Implementation"
---

# Compass CLI Implementation

## Goal

Build the Python `compass` CLI that owns all deterministic vault bookkeeping, convert the PostToolUse hook from `type: agent` to `type: command`, and shrink the mechanical skills to thin wrappers. Implements [[SPEC-004-mechanical-work-off-the-agent-budget]] per [[ADR-005-compass-cli-for-mechanical-work]], grounded in [[RESEARCH-cli-and-hook-command-contract]].

## Prerequisites

- SPEC-004 approved (done), ADR-005 approved (done).
- Python 3.13 confirmed present. Standard library only (argparse) - no third-party dependency, per SPEC-004 constraint.

## Desired End State

- `plugin/cli/` Python package with a `compass` entry point and one module per command.
- Commands: `sync`, `validate`, `next-num`, `tree`, `hot-path`, `promote`, `clean-tmp`, `touched`, `admit-check`.
- `plugin/hooks/hooks.json` PostToolUse runs `compass sync` as a command hook; zero agent tokens on a normal write.
- `index-sync`, mechanical parts of `vault-health`, and the file-moving half of `promote-spec` skills reduced to "invoke the CLI, surface findings."
- pytest suite: golden-output tests pinned against the current dogfood vault + seeded-defect fixtures. Full suite green.
- SPEC-004 success criteria 1-6 all hold; the 80% token-reduction hypothesis measured (Phase 6).

## What We're NOT Doing

- Replacing judgment skills (spec, plan, research, validate, consolidate, extract-lessons) - they stay agent-driven.
- A daemon/watcher. Invoked per-event by the hook, per-command by humans.
- A third-party CLI framework. argparse only.
- Rewriting vault file formats. The CLI reads/writes the existing frontmatter + wikilink conventions.

## Resolved decisions

1. **Layout.** `plugin/cli/` is a package: `__main__.py` (argparse dispatch + exit helpers), `vaultlib.py` (shared: vault-root discovery, frontmatter parse, artifact scan/classify, token count), one module per command under `commands/`. A thin `plugin/cli/compass` launcher (`#!/usr/bin/env python3`, `from compass.__main__ import main`) is the executable name. Self-contained so `/compass:bootstrap` copies the whole dir.
2. **Invocation path.** Hook command: `python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" sync` (research F3: `CLAUDE_PLUGIN_ROOT` is set for plugin hooks; stdin carries the JSON). Skills invoke the same path via Bash. Python on PATH is assumed (SPEC-004 constraint; dogfood + Claude Code environments have it).
3. **Line endings.** Every file write uses `newline="\n"` explicitly, regardless of host OS, per `[[LESSON-windows-crlf-breaks-linux-container-scripts]]`. This is a shared `write_text_lf()` helper in `vaultlib.py` and a test assertion.
4. **index.md is append-only; tag-index is full-regen.** Sync preserves human-authored index lines and descriptions (the current skill's contract: "the user may have written context lines; only append, never delete"). `meta/tag-index.yaml` is fully derived and regenerated each run. This split is load-bearing - a naive full-regen of index.md would clobber curated descriptions.
5. **Fail-safe exit codes.** The dispatch catch-all (hook mode) traps every exception, prints one stderr line, exits 1 - NEVER 2 (research F1: exit 2 blocks the user's write). Read-only commands in human mode may exit non-zero to report defects (that is `validate`'s contract); only the hook path is constrained to never-block.
6. **Loop guard in code.** In hook mode, `sync` reads `tool_input.file_path` from stdin and exits 0 immediately if it is one of its own generated outputs (`index.md`, `meta/tag-index.yaml`, `meta/lessons-catalog.yaml`, `meta/working-set.yaml`), per research F4.

## Phases

### Phase 1 - Foundation (dispatch + shared library)

- [ ] TASK-001: Build `plugin/cli/` package skeleton - complexity: M, depends_on: none, files: [`plugin/cli/compass`, `plugin/cli/__main__.py`, `plugin/cli/vaultlib.py`]
  - `__main__.py`: argparse with subparsers; `cli_ok(msg)`/`cli_err(msg, code=1)` exit helpers (the one place "never exit 2" lives); a `main()` wrapping dispatch in a catch-all that, when stdin is non-TTY hook input, prints one stderr line and exits 1.
  - `vaultlib.py`: `find_vault_root()` (walk up for `.compass/`, honor `CLAUDE_PROJECT_DIR`); `parse_frontmatter(path)` (first `---`...`---` block -> dict, tolerant of malformed -> returns `(data, error)`); `scan_artifacts(root)` (glob the 7 type dirs, classify flat/folder-index/child per index-sync skill step 1); `count_tokens(text)` (chars/4 approximation, documented); `write_text_lf(path, text)`.
  - Automated verification: pytest - `parse_frontmatter` on valid/malformed/missing fixtures; `scan_artifacts` on a fixture vault with flat + folder + nested specs returns correct classification; `write_text_lf` output contains no `\r` byte even on Windows; `compass --help` exits 0 and lists all 9 subcommands.
  - Manual verification: run `python3 plugin/cli/compass --help`, confirm subcommand list.

**Phase boundary (dependency + the one checkpoint worth a human look).** Every Phase 2 track builds on `vaultlib` and the dispatch skeleton. This is the single pause worth taking: confirm the shared library is right before eight parallel command modules compound on it.

### Phase 2 - All commands (four parallel tracks, no cross-track dependency)

Every task here depends only on Phase 1's `vaultlib` and owns its own files, so the tracks run as parallel builders and join at the Phase 2 boundary. No internal pauses - the tracks have no dependency on each other to gate.

**Track A - read-only commands**

- [ ] TASK-002: `compass next-num <type> [parent]` - complexity: S, depends_on: TASK-001, files: [`plugin/cli/commands/next_num.py`]
  - Compute max+1 from the filesystem, local per folder (ADR-003, ADR-004). `<type>` in {spec,plan,research,decision,lesson,handoff,pr}; optional `[parent]` folder for local numbering inside a folder spec. Print the zero-padded number (e.g. `005`).
  - Automated verification: fixture vault with SPEC-001..004 -> prints `005`; empty type dir -> prints `001`; folder parent with two children -> prints `003` scoped to that folder.
  - Manual verification: `compass next-num spec` against the real vault prints `005`.

- [ ] TASK-003: `compass tree` and `compass hot-path` - complexity: S, depends_on: TASK-001, files: [`plugin/cli/commands/tree.py`, `plugin/cli/commands/hot_path.py`]
  - `tree`: render the spec/folder hierarchy indented two spaces per depth (index-sync skill "Hierarchical rendering").
  - `hot-path`: sum token count of `index.md` + `active.md` + `meta/lessons-catalog.yaml`; print `N / 5000` and exit 0 (read-only; `validate` is what fails on breach).
  - Automated verification: `tree` on a nested-fixture vault matches expected ASCII; `hot-path` on a fixture with known sizes prints the expected count.
  - Manual verification: both against the real vault, eyeball.

**Track B - `compass sync` (the core; tasks sequential within this track)**

- [ ] TASK-004: `compass sync` index + catalog + tag-index regeneration - complexity: L, depends_on: TASK-001, files: [`plugin/cli/commands/sync.py`]
  - Reproduce index-sync skill steps 3-5b exactly: build expected index map by `type`, append missing entries to `index.md` (append-only, hierarchical indent, skip `status: archived`), append missing rows to `lessons-catalog.yaml`, update folder `children_count`, fully regenerate `meta/tag-index.yaml` (sorted). All writes via `write_text_lf`.
  - Automated verification: GOLDEN test - copy the current dogfood vault to a temp dir, run `sync`, assert `index.md`/`catalog`/`tag-index` are byte-identical to a pinned golden snapshot (captured + hand-verified before this task). Orphan-file fixture -> link appended. Archived-file fixture -> NOT linked. Curated-description fixture -> human line preserved, not clobbered.
  - Manual verification: run on a temp copy of the real vault, diff against current files - expect no spurious changes.

- [ ] TASK-005: `compass sync` caps + extraction-log cleanup - complexity: M, depends_on: TASK-004, files: [`plugin/cli/commands/sync.py`]
  - index-sync skill steps 6 + 8: three cap checks (index.md 5000 tok/250 lines; catalog 200 lines/25 KB; lesson count 50) prepend the documented warning when breached and absent, never duplicate; delete `tmp/extraction-log-*.md` older than 30 days (use `os.stat` mtime, not shelling to `find`, for cross-platform determinism).
  - Automated verification: 251-line index fixture -> warning prepended once; second run -> not duplicated; 35-day-old log fixture -> deleted, 29-day -> kept.
  - Manual verification: none beyond tests.

- [ ] TASK-006: `compass sync` hook mode (stdin, loop guard, silent success) - complexity: M, depends_on: TASK-004, files: [`plugin/cli/commands/sync.py`]
  - Detect hook mode: stdin is non-TTY and parses as JSON with `hook_event_name`. Read `tool_input.file_path`; if it is a generated output (decision 6), print nothing, exit 0. Else run the full sync, print `{"suppressOutput": true}`, exit 0. On ANY exception, one stderr line, exit 1 (never 2). Human mode (no stdin JSON): full sync on whole vault, print the human report (index-sync skill step 9).
  - Automated verification: feed a PostToolUse JSON for a normal spec write on stdin -> sync runs, exit 0, stdout is `{"suppressOutput": true}`. Feed JSON for a write to `index.md` -> no-op, exit 0, no vault mutation. Inject an exception (monkeypatch) -> exit 1, not 2. Run with no stdin -> human report printed.
  - Manual verification: pipe a hand-written hook JSON into `compass sync`, observe behavior.

**Track C - `compass validate`**

- [ ] TASK-007: `compass validate` - complexity: L, depends_on: TASK-001, files: [`plugin/cli/commands/validate.py`]
  - Reproduce index-sync skill steps 7a + 7b across the WHOLE vault (not just one file): required-frontmatter-by-type check; wikilink resolution skipping fenced code blocks AND inline code spans (`[[LESSON-wikilink-validator-skip-code]]`), stripping `#section`/`|display`, accepting specials `active`/`backlog`/`index`/`vision`; plus the hot-path cap check. Print a precise per-defect report. Exit 0 if clean, non-zero if any defect (human-mode read-only command; this is its contract, distinct from the hook's never-block rule).
  - Automated verification: SEEDED-DEFECT fixtures - (a) file with a broken `[[NoSuchSpec]]` -> reported, exit non-zero; (b) spec missing `status` -> reported; (c) 251-line index -> cap breach reported; (d) wikilink inside a fenced block and inside inline backticks -> NOT reported (no false positive). ZERO-FALSE-POSITIVE test: run on a clean copy of the real dogfood vault -> exit 0, empty defect list.
  - Manual verification: run `compass validate` on the real vault, confirm exit 0 and no false positives (the SPEC-004 success criterion).

**Track D - mutating commands**

- [ ] TASK-008: `compass promote <spec>`, `compass clean-tmp` - complexity: M, depends_on: TASK-001, files: [`plugin/cli/commands/promote.py`, `plugin/cli/commands/clean_tmp.py`]
  - `promote`: mechanical half of flat->folder - `git mv SPEC-NNN-name.md SPEC-NNN-name/index.md`, then rewrite inbound `[[SPEC-NNN-name]]` wikilinks across the vault that must change (children get path-qualified targets). Summary text stays with the agent. Mirror the existing `promote-spec` skill's wikilink-rewrite rules.
  - `clean-tmp`: delete `tmp/extraction-log-*.md` older than 30 days (shares the Phase-2 helper).
  - Automated verification: fixture flat spec with two inbound links -> after promote, file moved to `index.md`, both links still resolve. clean-tmp fixture as in TASK-005.
  - Manual verification: dry-run promote on a throwaway fixture, inspect the git mv + link edits.

- [ ] TASK-009: `compass touched <spec>`, `compass admit-check <spec>` - complexity: M, depends_on: TASK-001, files: [`plugin/cli/commands/touched.py`, `plugin/cli/commands/admit_check.py`]
  - Working-set + admission control (ADR-004). `touched`: append `(spec_path, turn)` to `meta/working-set.yaml` (rolling window, last 10). `admit-check`: exit 0 if the spec may enter the hot path (in the working set AND adding it keeps hot path < 5000 tokens), exit 1 otherwise.
  - Automated verification: touch a spec -> appears in working-set.yaml; window caps at 10; admit-check returns 0 for an in-set spec under cap, 1 for a spec that would breach the cap.
  - Manual verification: none beyond tests.

**Phase boundary (dependency).** The cutover needs `sync` and `validate` working, so it cannot start until Phase 2's Track B and Track C land.

### Phase 3 - Cutover, measurement, and lessons

- [ ] TASK-010: Verify matcher alternation, rewrite hooks.json PostToolUse - complexity: M, depends_on: TASK-006, files: [`plugin/hooks/hooks.json`]
  - First resolve RESEARCH OQ1: empirically confirm whether the plugin hook schema honors `"matcher": "Write|Edit|MultiEdit"`. If yes, collapse to ONE command entry; if no, keep three entries each running the command. PostToolUse `type: command`, command `python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" sync`, drop the `if(.compass/**/*.md)` guard (the CLI self-filters the path from stdin). Update the hooks.json `description` to match reality (it currently describes the agent-type design).
  - Automated verification: JSON parses; a schema/lint check of the hook entry shape.
  - Manual verification: trigger a real `.compass/**/*.md` write in a live session, confirm the command hook fires `compass sync`, index/tag-index update, and the agent sees zero token cost (research F5 silent success). Write to `index.md` itself -> no loop.

- [ ] TASK-011: Shrink mechanical skills to CLI wrappers - complexity: M, depends_on: TASK-006 TASK-007, files: [`plugin/skills/index-sync/SKILL.md`, `plugin/skills/vault-health/SKILL.md`, `plugin/skills/promote-spec/SKILL.md`]
  - `index-sync`: collapse the ~260-line mechanical protocol to "run `compass sync`, surface its report." Keep only what an agent needs to interpret findings.
  - `vault-health`: replace the mechanical wikilink/frontmatter passages with "run `compass validate`, surface findings"; keep human-facing reporting/judgment.
  - `promote-spec`: the file-move + wikilink rewrite half delegates to `compass promote`; the skill keeps the judgment (when to promote, summary authoring).
  - Automated verification: grep each shrunk skill for the removed mechanical headings -> 0 hits; grep for the `compass` invocation -> present.
  - Manual verification: read each shrunk skill end-to-end for coherence; confirm no orphaned references to deleted protocol.

- [ ] TASK-012: Measure the SPEC-004 hypothesis honestly + extract lessons - complexity: M, depends_on: TASK-010 TASK-011, files: [`.compass/research/` measurement note]
  - Run a representative editing session (10+ vault writes) on the command-hook build; count agent tokens spent on bookkeeping. Compare against the agent-hook baseline (estimate from the old hook's prompt size x fires, documented). Compute the reduction; check it against the >=80% falsification target. Run `compass validate` and confirm zero new findings vs the LLM-hook implementation (the integrity half of the hypothesis).
  - Lesson extraction runs once here, at the end of the build, over the whole effort's reports - not gated per phase.
  - Automated verification: the full pytest suite is green (golden + seeded-defect + zero-false-positive).
  - Manual verification: record the measured number in a short research note - even if it falsifies the 80% claim, the same honesty applied to the SPEC-003 30% number (`[[LESSON-tag-index-trades-cost-for-directed-retrieval]]`). Do not handwave.

**Final review.** End-of-build human look: the measurement result, the validate run, and the extracted lessons.

## Phasing logic

Phases here are a dependency graph, nothing else. A boundary exists only where one phase genuinely cannot start until the previous one is done; pauses survive only where a human look changes what happens next.

- **Phase 1 -> Phase 2:** real dependency (everything builds on `vaultlib`) and the one mid-build checkpoint worth taking (a wrong shared parser would propagate into eight modules).
- **Within Phase 2:** four tracks, no cross-track dependency, so no boundaries between them - they run as parallel builders and simply join at the end. Track B's three `sync` tasks are sequential because they share `sync.py`; that ordering lives inside the track, not as phase boundaries.
- **Phase 2 -> Phase 3:** real dependency - the hook cutover needs `sync` and `validate` working.
- **End of Phase 3:** the final review, where measurement and lessons land together.

## Risks

- **Golden snapshots capture a wrong current state.** If the pinned golden output reflects an existing index bug, tests enshrine it. Mitigation: hand-verify the snapshot before pinning (ADR-005 load-bearing risk).
- **Matcher alternation (OQ1) unconfirmed.** TASK-010 resolves it empirically; three-entry form is the fallback. Does not block Phases 1-2.
- **Behavior drift re-implementing skill logic.** Golden + seeded-defect tests against the real vault are the guard; shrink a skill (Phase 3) only after its CLI counterpart passes (Phase 2 Tracks B and C).
- **Token-count approximation.** `count_tokens` is chars/4, not a real tokenizer. Acceptable for cap detection (the caps are conservative); documented so a later swap to a real tokenizer is contained.
- **80% claim may not hold.** Real falsification target. The measurement (TASK-012) reports the truth regardless.

## Inherited Questions

- RESEARCH OQ1 (matcher alternation) and OQ2 (does byte-identical write re-fire the hook) - both resolved empirically in Phase 3/TASK-010; neither blocks earlier phases.
