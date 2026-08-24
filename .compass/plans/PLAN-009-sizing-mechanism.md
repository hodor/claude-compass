---
title: "Sizing Mechanism (Both Directions, a Self-Firing Record, and a Paired Prototype)"
type: plan
status: approved
approved: 2026-08-23
confidence: medium
area: methodology
tags: [sizing, units, vision, harness, observability, decomposition]
created: 2026-08-23
updated: 2026-08-23
author: "orchestrator"
depends_on: ["[[SPEC-016-sizing-work-beyond-one-spec]]", "[[ADR-011-sizing-is-a-procedure-not-a-score]]", "[[RESEARCH-decomposition-criteria-for-sizing]]"]
summary: "zero-artifact units, the sizing record, and the changeability walk (draft, awaiting approval)"
---

# Sizing Mechanism (Both Directions, a Self-Firing Record, and a Paired Prototype)

## Goal

Give work that is too big for one spec the bigger shape, without the human needing to know the vocabulary. [[SPEC-016-sizing-work-beyond-one-spec]] ruled that both creation paths ship (D-01), that Compass acts rather than asking (D-02), that the notice is said once and can be silenced (D-03), that the machinery is never named to someone who did not ask (D-04), and that it stays configurable and callable (D-05). [[ADR-011-sizing-is-a-procedure-not-a-score]] chose the mechanism.

Wave 1 builds the harness half. The prose that teaches the judgment waits on a prototype, because the literature cannot say whether an agent runs the walk consistently and writing the prose first would be improvising.

**This plan was revised after a three-lens adversarial review** ([[LESSON-adversarial-plan-review-before-build]]). The review found the first draft's instrument counted an act the system could not perform, its record was incremented by nobody, and its prototype could not fail. Those three findings restructured wave 1. The review record is in `## Review findings applied`.

## Prerequisites

- [[SPEC-016-sizing-work-beyond-one-spec]] approved 2026-08-23, D-01..D-05 binding.
- [[ADR-011-sizing-is-a-procedure-not-a-score]] accepted 2026-08-23, eleven trackable decisions including D-11, added by this review.
- [[RESEARCH-decomposition-criteria-for-sizing]] complete, with its 2026-08-23 correction: the cheap-reversal premise was verified only in the forward direction.
- Suite green at HEAD: `python -m unittest discover -s plugin/cli/tests` reports `Ran 567 tests` / `OK`.
- `compass validate` reports `0 error(s), 5 warning(s)`, all five pre-existing.

## Desired End State

- A workspace can be declared before anything exists to put in it, and any shape change can be undone by one command.
- Sizing decisions record themselves from the commands that perform them. Nothing depends on an agent remembering.
- A shape on disk with no recorded decision is reported, so a missing record is visible rather than silent.
- `compass unit-check` runs from something.
- The changeability walk's consistency is measured against an unaided control arm, on a corpus where "flat" is not the right answer to almost everything.

## What We're NOT Doing

Carried from [[RESEARCH-decomposition-criteria-for-sizing]], each killed by evidence, plus scoping exclusions.

- **A sizing score or numeric threshold.** [[ADR-011-sizing-is-a-procedure-not-a-score]] D-01. Woodward 1993 found 163 trained raters disagreeing applying the cohesion ladder to code; Basili, Briand & Melo 1996 found LCOM did not predict the fault-proneness it proxies for while five sibling metrics did.
- **A "count the sub-concerns" rule.** Parnas 1972 pp.1053-1055: two decompositions of the same problem differ only in where the seams fall, at the same content count.
- **Asking the human whether to size.** [[SPEC-016-sizing-work-beyond-one-spec]] D-02.
- **Naming the machinery in the plain-language notice.** [[SPEC-016-sizing-work-beyond-one-spec]] D-04. This governs the *notice surface* only. Diagnostic surfaces a human deliberately invoked (`doctor`, `unit-check`, `sizing stats`) name commands freely, because a human running `doctor` has asked.
- **Acting on inferred future scope.** [[ADR-011-sizing-is-a-procedure-not-a-score]] D-05.
- **Retrofitting vaults that already hold monster specs.** SPEC-016 non-goal.
- **Any change to the lessons tiering.** That is [[ADR-010-identity-resident-fetch-mandatory]] and gets its own plan.
- **Rewriting `unit-check`'s detection rule.** D-10 keeps it; only its caller is missing.
- **A blind re-audit instrument for the mis-sizing denominator.** Named in the Later list, deliberately not in wave 1: it needs recorded decisions to audit, and there are none yet.

## Constraints (all tasks)

- Every code task writes tests and runs the full suite. Tests go through the `test-design` admission bar.
- **Manual verifications run `python plugin/cli/compass ...`, never the installed `.claude/cli/compass`**, which is stale until TASK-089. [[RESEARCH-grep-vs-graph-experiment]] recorded this exact trap already.
- No task adds skill prose without removing at least as much, per [[LESSON-remove-context-before-adding]]. Wave 1 touches no skill files at all.
- `compass validate` stays at 0 errors and adds no new warning classes.
- **Every task moves work into the harness and out of agent tokens.** North-star goal 4. A task that adds an agent step doing what a command could do is rejected at review, and a task that removes an agent step is worth more than one that adds a capability. Where prose is unavoidable (the walk itself, per [[ADR-011-sizing-is-a-procedure-not-a-score]] D-01), it carries only what genuinely requires judgment and nothing the CLI could carry instead.

## Phases

### Wave 1 (detailed): both directions of the shape change, and the record that fires itself

The coherent concern is the shape-change mechanism end to end: create, undo, record, reconcile, plus the reactive backstop's missing caller. TASK-083 is not harness work and is named as the exception: it is the prototype gate [[SPEC-015-rolling-wave-planning]] D-02 makes first-class near work, and it sits here because wave 2's prose cannot be written until it answers.

- [x] TASK-078: `compass make-unit` accepts zero artifacts - complexity: M, depends_on: none, files: [plugin/cli/commands/make_unit.py, plugin/cli/maincli.py, plugin/cli/tests/test_commands.py], decisions: [SPEC-016-sizing-work-beyond-one-spec/D-01, ADR-011-sizing-is-a-procedure-not-a-score/D-04]
  - `run()` requires two positionals today (`make_unit.py:172`), so a workspace cannot be declared before an artifact exists to move into it.
  - **The apply path must create the directory itself.** The only `mkdir` in the module is `make_unit.py:209`, inside the move loop. With zero moves that loop never runs and `write_text_lf` at `:213` hits a missing parent and raises `FileNotFoundError`, which `maincli.py:128` then misreports as an internal CLI bug. Create `vault_root / name` before writing the marker.
  - No empty type subdirectories are created. Git does not track empty directories, so they would vanish on the next clone; `next_num.run` already guards with `if base.is_dir()` (`next_num.py:55`) and returns `001` without one.
  - **Refuse a name that already resolves.** `_check_target` (`make_unit.py:33-42`) checks reserved, malformed and existing-path only, in that order. Malformed is exactly three classes and is checked first: a name containing `/`, containing a backslash, or starting with `.` returns `invalid unit name`. Precedence matters and is pinned by test: a name that is both malformed and reserved reports malformed, because that branch returns first. A bare word typed by a human can collide with a root artifact's stem, and after creation `resolvable_names_map` maps that name to two paths, turning every existing `[[name]]` into an `ambiguous_wikilink` warning. Add the refusal.
  - **One existing test asserts the old behavior and must change inside this task.** `test_usage_error_exits_one_never_two` (`test_commands.py`) asserts `make_unit.run(["core"]) == 1` and that `core/` does not exist. Split it: `run([])` still exits 1 with usage; `run(["core"])` becomes a dry-run success creating nothing.
  - Dry-run wording for zero artifacts states what it will create and omits the artifact and index-line counts rather than printing zeros.
  - `maincli.py:27`'s help string still describes the move-only contract and is updated here, which is why this task owns `maincli.py` and TASK-080 must sequence after it.
  - An empty unit contributes no records, so `_sync_index` creates no section for it (`sync.py:167-183`) and it is absent from the root index until its first artifact lands. That is accepted, not fixed: an empty workspace has nothing worth a hot-path line. Stated here so it is not re-decided at build time.
  - Automated verification: unittest - `make-unit foo --apply` with no artifacts creates `foo/index.md` carrying `type: unit` and exits 0; without `--apply` it creates nothing; a reserved name, a malformed name and an existing target each still exit 1 with zero changes; a name colliding with an existing artifact stem is refused; the split usage test passes in both halves; the multi-artifact tests pass unchanged; `validate` on a vault with an empty unit reports 0 errors and no new `ambiguous_wikilink`; `classify_root_dirs` puts the empty unit in `units`, never `unclassified`.
  - Manual verification: declare an empty unit in a scratch vault with `python plugin/cli/compass`, write a spec inside it via `compass next-num spec foo`, confirm unit-local numbering and that the path-qualified wikilink resolves.

- [x] TASK-079: the inverse of every shape change - complexity: M, depends_on: TASK-078, files: [plugin/cli/commands/demote.py, plugin/cli/commands/make_unit.py, plugin/cli/maincli.py, plugin/cli/tests/test_demote.py], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-11], lessons: [LESSON-installer-removes-only-what-it-installed]
  - `plugin/cli/commands/` holds `make-unit` and `promote` and no inverse of either. Reverting a shape today means a hand `git mv` plus manual index repair. [[ADR-011-sizing-is-a-procedure-not-a-score]] D-04's whole rationale, and the research finding behind it, rest on reversal being cheap - and only the forward direction was ever inspected. This task makes the premise true instead of asserted.
  - `compass demote <folder-spec>` is the inverse of `promote`: `git mv <name>/index.md <name>.md`, refusing when the folder has children, dropping `children_count`. `compass make-unit --undo <unit>` moves each artifact back to the matching root type dir and removes the unit folder, refusing when a name would collide at the root.
  - Both are dry-run by default with `--apply`, both regenerate derived state in-process and validate, and both refuse outright with zero changes on any problem, mirroring `make_unit.py`'s existing contract.
  - Both write their own correction row (TASK-080), which is why that task depends on this one landing first.
  - Automated verification: unittest - `demote` on a childless folder spec restores the flat file and inbound wikilinks still resolve; `demote` on a folder with children refuses with exit 1 and zero changes; `make-unit --undo` restores every artifact to its original type dir and removes the folder; `--undo` refuses when a restored name would collide at the root; both are no-ops without `--apply`; a promote-then-demote round trip leaves `git status` clean apart from expected derived files; a make-unit-then-undo round trip likewise; `validate` is 0 errors after each; neither ever exits 2.
  - Manual verification: promote a scratch spec, demote it, and confirm by reading the file that nothing about it changed except its path. A round trip that alters content is a failure even if the tests pass.

- [ ] TASK-080: sizing decisions record themselves - complexity: L, depends_on: TASK-078, TASK-079, files: [plugin/cli/commands/sizing.py, plugin/cli/commands/make_unit.py, plugin/cli/commands/promote.py, plugin/cli/commands/demote.py, plugin/cli/maincli.py, plugin/cli/tests/test_sizing.py], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-03, ADR-011-sizing-is-a-procedure-not-a-score/D-08], lessons: [LESSON-no-agent-bookkeeping, LESSON-append-only-index-misses-mutations]
  - **The trigger is the shape-changing command, not an agent's memory.** The first draft of this task built a command nobody called, which is the [[SPEC-017-capabilities-are-reachable-and-measured]] condition reproduced inside a plan that cites SPEC-017. `make-unit`, `promote`, `demote` and `--undo` each write their own row on `--apply`, from a `--reason` they require. [[LESSON-no-agent-bookkeeping]] is the rule: a step that is "record what was just decided" is not judgment.
  - **A stable id, minted at decision time and carried inside the artifact.** `sizing_id: sz-<date>-<n>` is written into the subject's own frontmatter, so it survives every `git mv` that `promote`, `make-unit` and `demote` perform - which are exactly the operations being logged. Paths and bare stems both break as join keys: `promote` changes the path, and bare stems are ambiguous across units by design. Path-at-decision-time is recorded as a human-readable secondary field only.
  - Rows are appended to `.compass/meta/sizing-log.yaml` by read-modify-write via `vaultlib.read_vault_text` then `vaultlib.write_text_lf`, mirroring `sync.py:282,305-306`. `write_text_lf` truncates (`vaultlib.py:422`), and a plain append-mode open would emit CRLF on Windows.
  - Each row carries the shape, the id, the reason, the volatile decisions the walk named, and whether a human or an agent initiated it. Without the volatile decisions a later audit cannot tell a changed need from a bad walk.
  - `compass sizing stats` reports decisions by shape, corrections, and provenance. It states in its own output that a zero correction rate is uninterpretable without the audit denominator (Later list), rather than implying it is good news.
  - This diverges from `lessonslib.load_catalog`, which raises on the first malformed row (`lessonslib.py:135-145`). Sizing reports and skips instead, because a corrupt row must not take down the commands that perform shape changes. The divergence is deliberate and stated so a builder copying the nearest precedent does not invert it.
  - Args are parsed by hand as `test_checkpoint.py:392-441` does. A stock `argparse` would raise `SystemExit(2)`, which passes straight through `maincli.py:128`'s `except Exception` and exits 2.
  - Automated verification: unittest - `make-unit --apply` writes exactly one row and stamps `sizing_id` into the unit index; `promote --apply` likewise; `demote --apply` writes a correction row carrying the same id as the decision it reverses; a promote-then-demote round trip yields one decision and one correction joined by id; the id survives a file rename; `--reason` missing exits 1 with zero changes and no row; `stats` on an empty log reports zero without raising; a malformed row is reported and skipped while later rows still parse; the log round-trips through `read_vault_text` including a BOM'd fixture and is written LF-only; no command ever exits 2.
  - Manual verification: run `python plugin/cli/compass sizing stats` on this vault after a scratch promote and demote, and ask a human what they conclude from it. Compare their answer to what the output intended. Do not tell them the expected reading.

- [ ] TASK-081: `validate` reconciles shapes on disk against the log - complexity: S, depends_on: TASK-080, files: [plugin/cli/commands/validate.py, plugin/cli/tests/test_commands.py], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-08]
  - A record that only exists when something remembered to write it is not a record. Reconciliation makes a *missing* row observable: every unit folder and folder spec on disk is checked for a `sizing_id` that resolves in the log, and any that does not is reported as a warning.
  - Warning, not error: the vault predates the log, so every existing shape is unrecorded and would otherwise fail `validate` on day one. The warning names the backfill command.
  - Known limit, stated rather than hidden: a decision to leave something *flat* produces no artifact and no command invocation, so reconciliation cannot detect a missing flat row. The log's denominator is therefore incomplete until the walk itself records every need it walks, which is TASK-084's job in wave 2.
  - Automated verification: unittest - a unit with no `sizing_id` produces the warning; one whose id resolves produces none; an id present in frontmatter but absent from the log produces a distinct warning naming the id; the warnings never change the exit code; a vault with no log at all produces no warnings and no crash; existing validate tests pass unchanged.
  - Manual verification: run validate on this vault, where every shape predates the log, and confirm the output reads as "these are unrecorded" rather than as breakage.

- [ ] TASK-082: `compass doctor` reports unit-promotion candidates - complexity: S, depends_on: TASK-078, files: [plugin/cli/commands/doctor.py, plugin/cli/tests/test_doctor.py], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-10], lessons: [LESSON-type-dir-discovery-needs-content-signal]
  - `unit-check` works and nothing calls it, which is [[SPEC-017-capabilities-are-reachable-and-measured]] in miniature. `doctor` is the right caller: on demand, human-read, already reporting health.
  - **The call must be wrapped in its own try/except.** `_run_checks` sits inside a bare `except Exception` at `doctor.py:258-260` that collapses every row into one FAIL. `unit_check.find_candidates` walks and parses every artifact in the vault, far more exposure than any existing check, so one unreadable file would flip the exit code and discard the other rows. Degrade to a WARN naming the scan failure.
  - Call `find_candidates` (`unit_check.py:67`), not `format_report`, whose multi-line block would destroy `_format_table`'s alignment (`doctor.py:241`) and is invisible to `--json`, which exposes only `check/status/detail/fix` (`doctor.py:54-58`). `detail` is one line naming the candidates; `fix` points at `compass unit-check` for members.
  - The module docstring (`doctor.py:1-20`) scopes doctor to install drift and is updated, under the remove-before-adding constraint.
  - Automated verification: unittest - a vault with a spec whose tracers span three artifact types *including the spec's own* (`unit_check.py:100-103`, threshold 3, so spec plus two others) produces a candidate row; a vault with none produces the clean row; candidates never change the exit code; artifacts already inside units produce no candidates; an unparseable artifact produces the WARN and all other rows survive with exit 0; `doctor` still exits 1 on a genuine FAIL alongside candidates; `--json` stays one parseable object.
  - Manual verification: run `python plugin/cli/compass doctor` on this vault and confirm the candidate list is one a human agrees with.

- [ ] TASK-083: prototype - does the changeability walk raise agreement over unaided judgment? - complexity: L, kind: prototype, depends_on: none, files: [.compass/tmp/sizing-prototype/], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-01, ADR-011-sizing-is-a-procedure-not-a-score/D-02], lessons: [LESSON-blind-the-author-in-self-validation, LESSON-pin-the-motivating-datum]
  - **Question:** does giving raters the walk produce higher agreement than giving them nothing? Reliability is not validity, so agreement alone cannot license shipping; the claim [[ADR-011-sizing-is-a-procedure-not-a-score]] D-02 needs is that the walk *raises* agreement over unaided judgment.
  - **Paired, per this vault's own standard** ([[RESEARCH-test-quality-bar-validation]]). Arm A: raters get the need and the three shapes, no procedure. Arm B: raters get the walk verbatim. Same corpus, same prompt scaffold, same rater count.
  - **Corpus adequacy is a precondition, not a caveat.** This vault holds 16 flat specs, 0 folder specs and 1 unit. On that corpus a rater answering "flat" every time scores ~94% and, under a naive agreement band, ships the walk. The corpus must carry at least 5 items whose correct answer is not flat, drawn from outside this vault's own sizing history, and a discrimination check must show the verdict distribution differs from the constant-majority baseline. **If the corpus cannot be assembled, this task does not run** and the plan says so. A caveat in the writeup does not repair the number.
  - **Roles are split.** A second agent, never shown [[ADR-011-sizing-is-a-procedure-not-a-score]] or this plan, receives the walk text, the corpus and nothing else, and runs the raters. A third scores, against a verdict-equivalence rubric fixed before the first run. The orchestrator that authored D-02 writes none of the prompts.
  - **The hot path leaks the answer.** `.compass/active.md` currently names this initiative and its decisions, and the session-start protocol makes every agent read it. Raters run in a scratch vault whose `index.md` and `active.md` mention no sizing work, and the task verifies that rather than asserting it.
  - **Pre-registered, with numbers.** N raters and N items fixed before the first run. Statistic: Fleiss' kappa (fixed raters per item, nominal categories), reported with a confidence interval, plus per-item confusion and a separate agreement figure on the named volatile decisions. Raw percent agreement is not reported as the headline: chance agreement alone approaches 0.89 on an unbalanced corpus. Bands: **kappa >= 0.61 in Arm B and a clear gain over Arm A** ships the walk; **0.41-0.60** sends wave 2 a task to sharpen the criteria; **< 0.41, or no gain over Arm A** escalates D-02 to the human, since D-01 forbids the fallback.
  - **The escalation band is a legitimate completion of this plan, not a failure of it.** Recorded here because the plan's own strict-coverage gate would otherwise penalize the unfavorable outcome and create pressure against declaring it.
  - Prototype under [[SPEC-015-rolling-wave-planning]] D-02; routes through `compass test-checkpoint record TASK-083 --not-required`.
  - Automated verification: one machine-readable row per rater per item per arm written under `.compass/tmp/sizing-prototype/`, and a checked-in script that computes kappa and the confidence interval from those rows. The script is the verification; a promise that the number is recomputable is not.
  - Manual verification: the human reads the disagreement cases and rules whether they trace to the procedure or the corpus. The corpus was assembled under a stated adequacy rule, so corpus-blame has to argue against that rule rather than being freely available.

**Pause point and elaboration step.** Build step 7d, after the phase reports are assembled and lessons extracted, before the next phase's step 3. Read TASK-083's answer and the wave's verified outcomes; promote the next coherent set of intent lines into a `### Wave 2 (detailed)` section above `## Later`; delete the consumed lines from the Later region rather than editing them in place; move the promoted ids from `backlog.md` into `active.md`; append a `## Wave 1 elaborated` section recording per promoted line what changed and which outcome changed it, or "unchanged - intent held", quoting any superseded intent line only inside a fence. Present the delta; do not re-approve.

## Later (intent only)

- [ ] TASK-084: the vision skill runs the walk, acts, records every need it walks, and says the shape once in plain words - files: [plugin/skills/vision/SKILL.md], decisions: [SPEC-016-sizing-work-beyond-one-spec/D-02, SPEC-016-sizing-work-beyond-one-spec/D-03, SPEC-016-sizing-work-beyond-one-spec/D-04, ADR-011-sizing-is-a-procedure-not-a-score/D-05, ADR-011-sizing-is-a-procedure-not-a-score/D-07, ADR-011-sizing-is-a-procedure-not-a-score/D-09]
- [ ] TASK-085: the spec skill's bloat check gains the depth branch beside the split-into-siblings branch - files: [plugin/skills/spec/SKILL.md], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-02]
- [ ] TASK-086: spec authoring writes into the unit the work belongs to instead of hardcoding the vault root - files: [plugin/skills/spec/SKILL.md, plugin/skills/obsidian/SKILL.md], decisions: [SPEC-016-sizing-work-beyond-one-spec/D-01], commit-upfront: destination routing is fixed by SPEC-016 D-01 and the existing unit conventions; nothing about it moves on the prototype's answer
- [ ] TASK-087: the parent/child authoring template - what a unit or folder `index.md` holds versus its children - files: [plugin/skills/obsidian/SKILL.md, plugin/templates/], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-06]
- [ ] TASK-088: the persisted per-project preference and the named invocation path - files: [plugin/skills/methodology/SKILL.md, plugin/cli/commands/sizing.py], decisions: [SPEC-016-sizing-work-beyond-one-spec/D-05]
- [ ] TASK-089: install refresh and acceptance - files: [.claude/], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-11], commit-upfront: the acceptance battery is the shape every Compass plan runs and depends on nothing wave 1 produces
- [ ] TASK-090: the blind re-audit that gives the correction rate a denominator - files: [plugin/cli/commands/sizing.py], decisions: [ADR-011-sizing-is-a-procedure-not-a-score/D-08]

## Parallel-safe tasks

- **Wave 1:** TASK-078 must land before TASK-079, TASK-080 and TASK-082, since all four touch `maincli.py` or depend on its behavior. TASK-081 depends on TASK-080. TASK-083 shares no file with any of them and runs alongside from the start.
- **Wave 2 (as named):** TASK-085 and TASK-086 both target `plugin/skills/spec/SKILL.md` and cannot run together. Resolved at elaboration.

## Risks

- **The prototype comes back in the escalation band.** Then D-02 is unbuildable and D-01 forbids the obvious fallback. It goes to the human. The plan states this is a legitimate completion so the strict gate does not create pressure against declaring it.
- **Scoped becomes a parking lot.** Six decisions sit on TASK-084's single intent line. Mitigations: it is the first line elaborated, its six decisions are enumerated on the line rather than implied, `--strict` at completion fails anything still scoped, and TASK-088 carries the harness half separately so it cannot hide behind prose work.
- **The log measures nothing for months.** Correction rate needs decisions to accumulate, and TASK-090's denominator needs decisions to audit. The instrument is still built first, because retrofitting a record after the decisions are gone is impossible.
- **Prose growth in wave 2.** [[LESSON-remove-context-before-adding]] bites hardest on TASK-084, against a skill already at 161 lines.

## Inherited questions

- The project that motivated [[SPEC-016-sizing-work-beyond-one-spec]] is still unpinned ([[LESSON-pin-the-motivating-datum]]). TASK-083 wants it as corpus, and under that task's adequacy precondition, failing to find it does not license running on this vault alone.

## Review findings applied

Three lenses, 30 findings, all verified against source before acceptance. The three that restructured the wave:

- **The record had no caller.** `compass sizing record` was a command nobody invoked, in a plan whose next task exists to fix exactly that condition for `unit-check`. The trigger now lives in the commands that perform the shape change.
- **The instrument counted an act the system could not perform.** No inverse of `make-unit` or `promote` exists. That also falsified the cheap-reversal premise behind [[ADR-011-sizing-is-a-procedure-not-a-score]] D-04, which had been inspected in the forward direction only. ADR-011 gained D-11 and its rationale was corrected; [[RESEARCH-decomposition-criteria-for-sizing]] carries the correction.
- **The prototype could not fail.** All-flat corpus, unquantified bands, a near-unreachable failure band, no control arm, no chance correction, and every contamination path running through the author of the arm under test. Now paired, blinded, pre-registered with kappa thresholds, and gated on corpus adequacy.

## Verification of this plan

Measured 2026-08-23, before approval, from `python plugin/cli/compass`:

```
compass coverage PLAN-009-sizing-mechanism
summary: 16 trackable decision(s) in 2 source(s): 8 covered, 8 scoped, 0 uncovered -> PASS

compass lesson-coverage PLAN-009-sizing-mechanism
summary: 6 cited, 0 scoped, 0 unresolvable, 3 surfaced-but-uncited (advisory) -> PASS

compass validate
compass validate: 0 error(s), 5 warning(s)
```

Sixteen decisions, not the fifteen the first draft measured: D-11 was added by the review. At completion `compass coverage PLAN-009-sizing-mechanism --strict` must exit 0, with the exception recorded in the Risks section: if TASK-083 lands in the escalation band, ADR-011 D-02 stays uncovered by design and the plan closes on that finding.
