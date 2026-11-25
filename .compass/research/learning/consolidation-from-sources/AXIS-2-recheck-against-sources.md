---
title: "Axis 2: mechanical recheck of lessons, index lines and file:line references against their sources"
type: research
status: complete
confidence: medium
area: methodology
tags: [lessons, consolidation, drift, provenance, mechanical-checks, learning-loop]
created: 2026-11-21
updated: 2026-11-21
author: researcher
summary: "Vault claims carry weak provenance (a lesson's source points at a scratch opportunity, no commit), 118 of 380 measured file:line refs sit behind an earlier edit, and the checks that find this are git plus a script; only meaning-level judgment needs a model"
---

# Axis 2: mechanical recheck against sources

From [[SPEC-002-consolidation-grounded-in-sources]].

## Question
What provenance do lessons, index lines and `file:line` references carry today, which of their claims can a script recheck against the current tree and git history, and how is drift reported and each correction gated?

## Methodology
Repository mining (empirical study of the artifact), because the core question is how an existing vault and CLI behave; each "mechanical" claim was proven by running a script over the real vault. A bounded grey-literature and preprint scan covers the 2025-2026 survey (appended below). grading: allowed; marks follow each finding.

## Findings: what exists today

1. **A lesson's only provenance is a free-string `source`, and most lessons lack it** (confidence: high)
   `lesson-write` documents `source` as "string describing what produced this lesson" and persists it to frontmatter. 27 of 60 lessons carry it; values are `extract-lessons:OPP-<UTC>` (about 20), `extract-lessons:signal`, `agent-noted`, or a plan name. No commit sha, session id, transcript path or quote is recorded.
   - `plugin/skills/lesson-write/SKILL.md:24` and `:125` - field definition and persistence
   - measured: `source:` grep over `.compass/lessons/**/LESSON-*.md` gives 27 of 60 files
   - Marks: code and vault read, measured by script, n/a retraction, n/a preprint, n/a citations, single-artifact
   - Grade: high (direct measurement)

2. **The `OPP` pointer resolves today, but into scratch and untracked logs** (confidence: high)
   All 21 lessons whose `source` names an `OPP-...` id still have `.compass/tmp/capture-opportunities/<id>/` on disk; 16 also have `.compass/archive/logs/<id>.log`. `tmp/` is gitignored and the `archive/logs/*.log` files show as untracked in `git status`, so a fresh clone resolves none of them. The log is the headless worker's JSON result, whose first record carries `session_id`.
   - `.gitignore:2` (`.compass/tmp/`); `plugin/cli/capturelib.py:334-358` (`open_opportunity` writes `tmp/capture-opportunities/OPP-<UTC>/opportunity.json`)
   - measured: 21 of 21 tmp dirs, 16 of 21 logs exist locally
   - Marks: code read plus measured, n/a, n/a, n/a, single-artifact
   - Grade: high

3. **An opportunity's `evidence` is a list of file refs, not an excerpt** (confidence: high)
   `opportunity.json` holds `id, kind, triggers, evidence, opened_at, closed_at, outcome`. `evidence` is the distinct `ref` values of the window's signals, e.g. `tmp/subagent-captures/<UTC>_note.md`. A `capture-note` is written to the same scratch folder. No transcript offset, turn range or quoted line is stored.
   - `plugin/cli/capturelib.py:350-358`; `plugin/cli/commands/capture_check.py:164-178` (`_window_evidence`); `plugin/cli/commands/capture_note.py:5-9`
   - sample: `.compass/tmp/capture-opportunities/OPP-20261122T031216707854Z/opportunity.json`
   - Marks: code read, n/a, n/a, n/a, single-artifact
   - Grade: high

4. **The catalog and the index copy text once and do not refresh it** (confidence: high)
   `compass sync` appends catalog rows and index lines and never rewrites existing ones; an index description is kept as the line's own text. Measured: catalog vs lesson frontmatter, `score` differs on 7 of 60 rows and `summary` on 2 of 60; index lines vs target `summary:`, 11 of 123 resolvable lines differ (some may be hand-trimmed for the hot-path cap, so this is an upper bound on true drift).
   - `plugin/cli/lessonslib.py:10-13` (rows appended, never rewritten); `plugin/cli/commands/sync.py:222-232` (`_text_preserved`), `:440-449` (existing desc kept)
   - `.compass/index.md:1` hot-path warning 5493 of 5000 tokens
   - Marks: code read plus measured, n/a, n/a, n/a, single-artifact
   - Grade: high for the counts, medium for the true-drift share

5. **`compass validate` checks link structure only** (confidence: high)
   It tests that wikilinks resolve to exactly one file (`broken_wikilink`, `ambiguous_wikilink`), that block links point at a line ending `^id`, frontmatter fields, hot-path cap and sizing records. It never opens a `file:line` code reference, never compares an index line with a target `summary`, and never reads a lesson against a source. A lesson requires `score` and `summary`, not `source`.
   - `plugin/cli/commands/validate.py:1-22`, `:75-108`, `:42-51` (`EXPECTED_FIELDS`)
   - Marks: code read, n/a, n/a, n/a, single-artifact
   - Grade: high

6. **`file:line` refs are common in research and plans, nearly absent in lessons** (confidence: high)
   Outside archive and tmp, the vault has 380 code-span `plugin|bench|.claude` refs with a line number (most in research, then plans). Only 8 of 60 lessons name a file at all, always as a bare basename (`self_update.py`), never with a directory, line or commit; all 8 resolve by basename only (the path was elided or the file moved).
   - measured by script: 9 refs in 8 lesson files, 0 unresolved by basename
   - Marks: measured, n/a, n/a, n/a, single-artifact
   - Grade: high

7. **Existing join points for an outcome signal** (confidence: medium)
   Plan task lines carry an optional `lessons: [...]` field; `compass lesson-coverage` resolves each against the catalog and reports `cited`, `scoped`, or `surfaced-but-uncited`, advisory only. Catalog `score` and `seen` count recurrence. No file records whether the task that cited a lesson later passed or failed, though `test-checkpoint` and the validator verdict exist per task.
   - `plugin/cli/commands/lesson_coverage.py:1-40`; `plugin/cli/lessonslib.py:21-29` (ranking uses tags, area, score)
   - Marks: code read, n/a, n/a, n/a, single-artifact
   - Grade: medium (per-task verdict storage not read in full)

## Findings: what a script can prove (run on the real vault)

8. **Drift of `file:line` refs is measurable with git alone** (confidence: high)
   For each ref, take the commit that added the citing document, diff that commit to HEAD for the target with `-U0`, and classify against the hunk old-side ranges. Over 380 refs: 132 target unchanged since the doc was written; 31 changed elsewhere but not before the cited line; 118 sit behind an earlier edit (line number shifted, content may survive); 41 fall inside an edited hunk (the cited line itself changed); 1 target file missing; 57 unclassified because the citing doc has no add commit yet. So 159 of 323 classified refs (49%) are not provably current and 42 (13%) are definitely changed.
   - measured via `git diff -U0 <add-commit>..HEAD -- <file>`
   - Marks: measured, n/a, n/a, n/a, single-artifact
   - Grade: high for the classification, low for "stale" (shifted lines are only candidates)

9. **Path existence plus rename detection finds dead and moved paths** (confidence: high)
   An existence test over the vault's code-span path refs (archive excluded) found 108 missing: moves (`plugin/agents/builder.md`) and generated or ignored paths (`.compass/meta/models.yaml` 15, tmp templates). `git log --diff-filter=R -M --name-status -- <old>` returned `R100 plugin/agents/builder.md plugin/templates/agents/builder.md` (commit `fc0fe4a`), so a script can propose the new path with the rename commit as evidence.
   - measured; `git log` run in this repo
   - Marks: measured, n/a, n/a, n/a, single-artifact
   - Grade: high

10. **The index-summary check is a string compare** (confidence: high)
    Resolve each `[[link]] - desc` line to its target and compare `desc` with the target `summary`. Over all `index.md` files: 112 match, 11 differ, 2 targets lack a summary, 4 links unresolved or ambiguous. No model needed. Which side is newer is decided by `git log -1 -- <target>` against the index line's last commit.
    - measured
    - Marks: measured, n/a, n/a, n/a, single-artifact
    - Grade: high

11. **Lesson-versus-source checks split into a script half and a model half** (confidence: low-medium)
    Script half, given a recorded pointer: cited commit, file or transcript still exists; a quoted excerpt still appears verbatim in the source; named files and symbols still exist (`git grep -F`, rename detection). Model half: does the excerpt still support the lesson, and does the named code still behave as described. A bounded call takes the lesson body (5-line cap), the excerpt and the current code window and answers supported / contradicted / unverifiable with a quoted span; only lessons whose script half shows a change since `updated` are sent. Design inference from findings 1-10, not a documented vault mechanism.
    - Marks: inference, n/a, n/a, n/a, single-artifact
    - Grade: low-medium

12. **The minimum source pointer a lesson would need** (confidence: low-medium)
    Fields that make each script check possible: `source_session` (id is in the worker log), a verbatim `source_quote` or turn range, `source_commit` (HEAD at write time), and for code claims `refs: [{path, line, commit}]`. Today only a scratch opportunity id is kept (finding 2); for longevity the quote must live in a tracked place (a Record section or `archive/`). Inference; no field does this yet.
    - Marks: inference, n/a, n/a, n/a, single-artifact
    - Grade: low-medium

13. **The Data rule fixes the shape of every correction** (confidence: high)
    Drift is reported, and replaced text moves colder. `lesson-write` already preserves earlier wording under `## Record (preserved)` (example `.compass/lessons/hooks/LESSON-hook-if-clause-no-or.md`). `sync._text_preserved` refuses to drop an index line whose text is not kept in its target. `compass guard` denies deletes for subagents. So a correction proposal is an edit plus preserved old text, and a drift report is a new file, not an in-place rewrite.
    - `plugin/cli/commands/sync.py:223-233`; `.claude/rules/compass-pipeline.md` "Data"
    - Marks: code and vault read, n/a, n/a, n/a, single-artifact
    - Grade: high

## Findings: 2025-2026 survey (grey literature and preprints)

14. **Citation-checked memory is shipping: Copilot Memory stores file:line citations and verifies them at use time** (confidence: medium)
    Each memory is stored with code citations (path and line); before an agent uses it, citations are checked against the current branch, and a contradicted or missing-file memory is discarded or rewritten. A verified memory is recreated, extending its life; memories also expire after 28 days (one source says 90). GitHub reports the verification is prompted LLM behavior, not hard-coded, and stress-tested it with seeded adversarial memories. A/B: coding-agent merge rate 90% vs 83%.
    - https://github.blog/changelog/2026-01-15-agentic-memory-for-github-copilot-is-in-public-preview (primary, read via search summary, not fetched); https://www.kenmuse.com/blog/understanding-agentic-memory-in-github-copilot/ (secondary)
    - Marks: vendor post, no retraction found, n/a preprint, n/a citations, convergence with 15 and 17
    - Grade: vendor post, A/B measured by the vendor, seeded test asserted; medium

15. **Stale-memory reliance is large and a verification budget goes to the wrong link** (confidence: medium)
    Agents inheriting consolidated memory with provenance links acted on a withdrawn constraint in 74.7-77.3% of decisions and inspected the provenance path in about one episode in five. Spending one of two allowed checks on the critical path removed most stale decisions (+61 to +81 points), but the policy assumes the experimenter knows which path matters. A one-sentence rule to favor memories that limit the option being considered moved agent checks onto the path; a content-free freshness hint did not.
    - arXiv:2608.25553 (abstract page fetched; single author, 16 models)
    - Marks: preprint, measured, n/a retraction, citations not looked up, convergence with 14 and 16
    - Grade: preprint, measured, medium-low

16. **Source metadata and conflict resolution before the model sees a note cut stale reliance** (confidence: low-medium)
    On Qwen3 0.6B-8B, reliance on a stale note was 0.92-1.00 in the benefit suite; larger models were harmed most when the stale note looked newer. Adding metadata (label, recency, source authority) raised accuracy at every size, and resolving conflicts before the model saw them brought accuracy near maximum.
    - arXiv:2609.01852 (abstract page fetched; NeurIPS 2026 workshop, small models only)
    - Marks: preprint plus workshop acceptance, measured, n/a, n/a, convergence with 15
    - Grade: workshop paper, measured on small models; low-medium

17. **Separate detection from repair, and let the repair be code** (confidence: low-medium)
    A benchmark that fixes correct values and dependencies before text is generated and scores with a deterministic scorer finds that detecting a change helps only as far as repair allows; LLM recomputation from definitions gave few right values, while LLM-written programs over typed records came close to exact. PACMI adds a provenance graph with typed dependency edges and a four-state validity lattice so an invalidated record propagates to dependents while history is kept (final-answer gain over the best baseline significant; cascading alone not significant, 3 vs 11 errors).
    - arXiv:2611.02338 (MemShift); arXiv:2610.05732 (PACMI); abstract pages fetched, synthetic benchmarks
    - Marks: preprints, measured on synthetic data, n/a, n/a, convergence with 11 and 13
    - Grade: preprints, measured, low-medium (transfer to lesson text untested)

18. **Doc-drift tools split into deterministic reference checkers and LLM PR reviewers; none read uses line-level blame** (confidence: medium)
    Deterministic: repowise `doc-drift --check` (paths, links, headings, commands, symbols; exit 1 at confidence 0.7+), doc-lag (git diff linked to documented commands, file refs and config facts, evidence-backed findings, SARIF output, only the PR's own changes), mgkvibez/doc-drift (env vars, CLI flags, backticked symbols), a borghei Claude skill (git modification dates plus AST signatures plus link and anchor validation, 0-100 freshness score). LLM-based: jbrockSTL/doc-drift (GitHub Action, PR comment). The searched write-ups name no tool using `git blame` per line; git use is file or directory level.
    - https://github.com/TarcisioPhilips/doc-lag ; https://github.com/jbrockSTL/doc-drift ; https://github.com/borghei/Claude-Skills/blob/main/engineering/doc-drift-detector/SKILL.md ; https://repowise.dev/blog/comparisons/best-documentation-drift-detection-tools (vendor comparison, not neutral); read via search summaries
    - Marks: practitioner repos and vendor post, n/a, n/a, stars not looked up, convergence with 8-10
    - Grade: practitioner, asserted (no measured accuracy read); low-medium

19. **Cheap detector then LLM is the documented cost pattern for code-comment inconsistency** (confidence: medium)
    CCISolver pairs a lightweight learned detector with an LLM fixer because LLM-only detection is slow and costly at scale (detection F1 89.54%; repair GLEU +18.84% relative, human-judged fix success 0.6533; about 36% faster end to end). C4RLLaMA (ICSE 2025) reports 65.0% and 55.9% correct comment updates in just-in-time and post hoc settings, which bounds how far an unchecked LLM correction can be trusted. SmartComment and RustC4++ confirm a finding by program variants or SMT instead of trusting the LLM verdict.
    - arXiv:2506.20558 (fetched; under review); https://conf.researchr.org/details/icse-2025/icse-2025-research-track/10/Code-Comment-Inconsistency-Detection-and-Rectification-Using-a-Large-Language-Model ; https://doi.org/10.1145/3808112 ; https://doi.org/10.1145/3800689 (last three via search summary only)
    - Marks: preprint plus peer-reviewed ICSE 2025, measured, n/a, n/a, convergence with 11
    - Grade: mixed, measured on code comments (not lessons); medium

20. **Prior evidence carried, not redone** (confidence: medium)
    Anthropic "dreaming" corrected a wrong memory note from the transcript (axis 1 f4); EGM `drift-report` compares design docs with live code and a human resolves (axis 5 f9); stale instruction files were followed and never repaired (axis 5 f16, 732 trajectories); ACE found non-LLM delta merges with helpful and harmful counters beat whole-context rewrites (axis 3 f1).
    - `.compass/research/llm-research/REVIEW-llm-research-for-compass.md` section A2 (evidence list)
    - Marks: carried from the review, convergence with 14-17
    - Grade: as graded in the review (m to m-h)

## Contradictions
- Findings 14 and 15: Copilot reports prompted agents catch seeded contradictions and rewrite them; the budgeted-verification paper finds agents inspect provenance in about one episode in five unless told which path matters. Different tasks (seeded citations vs withdrawn constraints); neither tested the other's setup.
- Finding 14 expires memories on a timer (28 days, one source says 90); the Data rule forbids deleting, so only "move colder" carries over.
- Finding 17 favors LLM-written programs for repair; finding 19 shows unchecked LLM repair of text is right 56-65% of the time. Both agree the repair needs its own check.

## Gaps
- Only 9 file refs exist in 60 lessons (finding 6), so most lesson claims are behavioral statements that finding 11's model half must judge; how many lessons make a code-checkable claim is unmeasured.
- The 41 "edited" and 118 "shifted" refs (finding 8) were not hand-judged; the content-level false-positive rate of the git check is unmeasured.
- Per-task validator verdict storage was not read in full, so the cost of joining a cited lesson to a pass or fail (finding 7) is unconfirmed.
- Findings 14, 18 and 19 partly rest on search summaries; the GitHub changelog page and full papers were not read.

## Candidate changes for Compass (ranked by impact; options, not a decision)

1. **A `compass drift` script that reports and never edits** (stars 1, 2, 4). Runs findings 8, 9 and 10 as one command: code refs by add-commit diff plus rename detection, index line vs target `summary`, catalog row vs lesson frontmatter. One report file per run; each row carries file, line, commit, old and new text beside it. Touches `plugin/cli/commands/` and a `stale_code_ref` warning class in `validate.py` next to `broken_wikilink`. Covered: no (`validate.py:75-108` checks links only).
2. **A lesson source pointer that outlives scratch** (stars 1, 2). Add `source_commit`, `source_session`, a short verbatim `source_quote` (or a tracked copy of the evidence) and structured `refs` for code claims to lesson frontmatter at write time; `lesson-write` already persists `source` (`SKILL.md:24`). Without it finding 11's script half cannot run. Covered: partly (free-string `source`, 27 of 60).
3. **Bounded just-in-time recheck at lesson retrieval** (stars 1, 3, 4). Copilot's pattern (finding 14): when `compass lessons --for <plan>` surfaces a lesson with refs, a script re-resolves them and the row carries a `drift:` flag; only flagged lessons go to the model judge (finding 11). Cost follows use, not vault size. Covered: no.
4. **Corrections are proposals gated by script, then judge, then human** (stars 1, 2). A drift row becomes a proposal holding old text, new text, evidence and the check that flagged it; a CLI applies it by moving old text to `## Record (preserved)` (existing form, `.compass/lessons/hooks/LESSON-hook-if-clause-no-or.md`), so the Data rule holds. Findings 17 and 19 say repair needs its own verification and deterministic application. Covered: partly (the Record convention, `sync._text_preserved`).
5. **Outcome counter from the plan join** (stars 1, 2). Extend `lesson_coverage.py` to record helpful and harmful counts when a task that cited a lesson gets a validator verdict. No source here measured that join for coding lessons. Covered: no (`score` and `seen` count recurrence).
6. **Refresh index and catalog instead of copying once** (stars 2, 3). A mechanical refresh of catalog `score` and `summary` (7 and 2 of 60 stale) and a drift flag on index lines that differ from the target summary, keeping text found only in the index (`_text_preserved`). Covered: partly (rows are generated for new lessons only).
