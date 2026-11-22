---
title: "Axis 3: lesson track record (outcome per cited lesson)"
type: research
status: complete
confidence: medium
area: methodology
tags: [lessons, track-record, outcome-scoring, attribution, agent-memory, consolidation]
created: 2026-11-21
author: researcher
summary: "Lesson score counts recurrence only and the catalog copy of it goes stale; citation (plan lessons: field) and failure signals (phase-summary.yaml) both exist per task, so a mechanical per-task join is possible, with set-level attribution noise"
updated: 2026-11-21
---

# Axis 3: lesson track record

From [[SPEC-002-consolidation-grounded-in-sources]] (problem bullet 3: "Lessons carry no outcome"), under [[SPEC-012-learning-loop]].

## Question

How does a lesson's score work today, where does Compass already record that a lesson was loaded or cited and whether the work passed, what join is mechanically possible with what noise, and what does 2025-2026 research measure for outcome-scored memory?

## Methodology

Systematic mapping study (the catalog default): the question spans code, vault data and a literature slice with no single practice under test. Code and live data read first; literature read from arXiv abstract pages and, for ACE, the full text. Grading allowed: grade is by source type and measured vs asserted. Prior evidence reused, not redone: [[REVIEW-llm-research-for-compass]] and [[RESEARCH-axis-3-agent-memory]] (ACE counters, later outcomes as free quality labels).

## Findings: Compass today

1. **Score is a recurrence counter, written only by `lesson-write` branch 4a** (confidence: high)
   - New lesson: `score: 5`, `seen: []`. Recurrence: append today to `seen`, `score` +1, cap 10, body unchanged. Fourth recurrence (3 dates already): `escalated: <date>` plus a catalog row edit. Recurrence is judged by an LLM against the catalog manifest ("tags overlap >=2, summary semantically equivalent").
   - `plugin/skills/lesson-write/SKILL.md:75` - recurrence indicators; `:85-93` - 4a bump and escalation; `:123` - initial `score: 5`; `plugin/skills/lessons/SKILL.md:45` - "bumped on recurrence".
   - Live data (60 lesson files): 47 have `seen: []` and score 5; 11 have one date, 1 two, 1 three; none carries `escalated`. Max score 9.
   - Marks: code read, no retraction applicable, not preprint, no citations, single source (the code)
   - Grade: direct code read, measured on the vault; high

2. **What "score" measures is the opposite of harm: a lesson that recurs scores higher because it was NOT applied** (confidence: high)
   - A recurrence means the same mistake happened again after the lesson existed. Escalation text states this: "recurred 3 times despite being captured - lesson worded too vaguely OR search retrieval failing". So score rises with failure to prevent, never with work succeeding after a citation.
   - `plugin/skills/lesson-write/SKILL.md:91`; `plugin/cli/lessonslib.py:22-25` ("retrieval already missed or a reader already rejected the lesson three times").
   - Marks: code read, single source
   - Grade: direct code read; high

3. **Ranking uses the catalog's copy of score, which is written once and goes stale** (confidence: high)
   - `_catalog_row` writes `score` at row creation; sync appends rows but never rewrites existing ones; ordinary recurrence "touches neither the catalog nor the index"; only escalation edits the row. `rank` sorts escalated first, then tag overlap, area match, text overlap, then catalog `score` as the last tiebreak.
   - Measured: 7 of 60 catalog rows disagree with their lesson file's score (for example catalog 8 vs file 9 with 3 seen dates; catalog 5 vs file 6/7 for five others). Catalog score distribution: 53 at 5, 6 at 6, 1 at 8.
   - `plugin/cli/commands/sync.py:511-530` (`_catalog_row`); `plugin/skills/lesson-write/SKILL.md:93`; `plugin/cli/lessonslib.py:157-217` (`rank`).
   - Marks: code and live data read; single source
   - Grade: measured on the vault; high

4. **Consolidation's only score-driven action is archive of never-reinforced lessons** (confidence: high)
   - Step 6 archives non-escalated lessons with `score == 5`, `seen: []` and `updated` over 90 days ago (moved to `archive/lessons/`, `status: archived`). Merge sums scores (cap 10). Step 5 keeps every `seen` date. Nothing reads whether work that cited a lesson passed.
   - `plugin/skills/consolidate/SKILL.md:55-90`.
   - Marks: code read; single source
   - Grade: direct read; high

5. **Where "loaded" is recorded: three weak traces** (confidence: high)
   - (a) `.compass/tmp/retrieval-log.jsonl`: one row per `compass lessons` run with `{at, query{area,tags,text,for}, surfaced[], context}`. Live: 51 rows 2026-08-06 to 2026-11-19, context planner 33 / builder 10 / none 7 / test 1, 11 empty results, 41 distinct lessons surfaced (top: adversarial-plan-review 27, append-only-index 21). It is under gitignored `tmp/`, carries no task id, plan id or session id, and a `--for <doc>` value is its only join key.
   - (b) Agent frontmatter `initialPrompt` loads `lessons/index.md` for every agent: a load that is never logged per lesson.
   - (c) Session transcripts: of 780 transcript files scanned for this vault, 23 `Read` tool calls target a `LESSON-*.md` file (13 distinct lessons) and 55 Bash calls run `compass lessons` or `compass lesson-coverage`. A transcript records an actual file read, which the retrieval log cannot.
   - `plugin/cli/commands/lessons.py:30-35,104-129` (logger); `plugin/templates/agents/validator.md:13`; `plugin/templates/agents/builder.md:31`, `planner.md:35` (retrieval call with `--context`); `plugin/cli/sessionslib.py:1-20` (transcript reader, `records()` at `:145`).
   - Marks: code and live data read, transcript scan scripted by the researcher
   - Grade: measured on one vault; high for counts, medium for generality

6. **Where "cited" is recorded: the plan task line `lessons: [...]`, audited report-only** (confidence: high)
   - Citation is author-declared at plan time. `compass lesson-coverage <plan>` resolves each citation to a catalog row, classes it `cited` (detailed task), `scoped` (`## Later` intent), `unresolvable` (typo, the only exit-1) or `surfaced-but-uncited` (advisory: top 5 by `lessonslib.rank` for the plan's area/tags). It stores nothing; the validator pastes the output into its report and also checks "cited-but-no-evidence-in-the-diff" by reading.
   - Live: 19 of 30 plans carry a `lessons:` field; 78 of 335 task lines cite lessons.
   - `plugin/cli/commands/lesson_coverage.py:1-52,63-64,164-285`; `plugin/templates/agents/validator.md:80-82`.
   - Marks: code and live data read; single source
   - Grade: measured; high

7. **Where pass/fail is recorded per task: `phase-summary.yaml` (fix-loop cycles, validator deviations)** (confidence: medium)
   - The build orchestrator writes one per phase: `tasks`, `fix_loop_cycles` per task (from `compass test-checkpoint cycle`), `validator_deviations` (`{task, kind: problem, description}`), `debug_invocations`, `stop_and_report_events`, `plan_revisions`. It is read by the extraction pass and lives under gitignored `.compass/tmp/phase-reports/` (14 files live). The validator's VERDICT and its Lesson Coverage block are report text; no persisted structured verdict per task was found under `.compass/` outside plan prose (search was by grep for the report headings; one plan quotes it).
   - Other outcome stores found: `capture-log.jsonl` (1952 rows: 173 opportunities, all fired, 54 wrote at least one lesson; ledger of the capture pass, not of work outcomes); `capture-stats` command; `sizing-log.yaml` (corrections to document shape, not work outcome); `usage.yaml` (per-command counts only, no lesson field).
   - `plugin/skills/extract-lessons/phase-summary.md:1-25`; `plugin/skills/build/SKILL.md:60-64`; `plugin/cli/commands/capture_stats.py:1-14`; `compass capture-stats` output; `.compass/meta/usage.yaml:1-3`.
   - Marks: code and live data read; single source
   - Grade: measured; medium (absence of a persisted verdict store is an absence-of-evidence claim from grep)

## Findings: the join

8. **A per-task join exists today without new instrumentation: plan `lessons:` x `phase-summary.yaml`** (confidence: medium)
   - Key: `TASK-NNN` within a plan. Citation side: the task line's `lessons:` list. Outcome side: `fix_loop_cycles[TASK]` >= 1 or a `validator_deviations` entry naming the task. Run on live data: 14 phase summaries cover 66 tasks; 30 cite a lesson; 13 show a failure signal; 8 of those 13 are cited tasks. So roughly 8 failure-then-cited and 22 clean-cited task rows exist across the whole vault history: enough to compute a per-lesson ratio only for the few lessons cited repeatedly.
   - The fix loop and deviation are rework/problem signals, not pass/fail of the final result: the plan phase still ends PASS after a loop. `fix_loop_cycles` is 0 for "never ran" and for "passed first time" alike (`plugin/skills/build/SKILL.md:60`).
   - Marks: researcher's scripted join on live data; single vault
   - Grade: measured on N=66 tasks; medium, small sample

9. **Attribution noise sits at four levels** (confidence: medium)
   - Loaded is not used: the retrieval log lists what ranked, not what an agent read or applied; 23 transcript reads vs 51 logged retrievals shows the gap. Cited is not used: the validator's "cited-but-no-evidence-in-the-diff" check is the only mechanical test of use and is a read, not a run. Cited-set is not one lesson: a task cites 1-3 lessons and the outcome is of the task, so every cited lesson takes the same credit or blame. Confounds: task difficulty, model, tester pre-build tests, and the fix loop itself all move the outcome.
   - Per-lesson sample is small and skewed: surfaced counts are 27, 21, 16, 10, 9 for the top five and a long tail; 41 lessons surfaced in 51 runs.
   - `plugin/cli/commands/lesson_coverage.py:36-43` (surfaced-but-uncited is advisory because "a lesson an author read and correctly judged irrelevant is a normal outcome"); `plugin/templates/agents/validator.md:81`.
   - Marks: code reads plus counts above; inference for the noise taxonomy
   - Grade: structural observation; medium

10. **A transcript-level join is possible and stronger on "loaded"** (confidence: low-medium)
    - `sessionslib` already reads subagent transcripts and extracts plan/task ids (`plan_ids`, `task_ids`, `sessionslib.py:249-253`). A subagent's `Read` of a `LESSON-*.md` file plus its task id gives "this lesson was read during this task". Not built; the scan counted 23 such reads, so volume is small today and subagents run with `lessons/index.md` pre-loaded rather than lesson files read one by one.
    - Marks: code read plus scripted scan; not built, so untested as a join
    - Grade: feasibility only; low-medium

## Findings: 2025-2026 research on outcome-scored memory

11. **ACE keeps helpful/harmful counters per bullet but never ablates them** (confidence: high)
    - Bullets carry an id and "counters tracking how often it was marked helpful or harmful" (section 3.1). The Generator marks bullets useful or misleading; the Curator's deltas merge by "lightweight, non-LLM logic" with counters incremented in place (section 3.2). The paper does not tie counters to pruning, retrieval or any threshold, and no ablation (Table 3, appendices A.5, A.6) tests them. Where ground truth is absent it relies on "code execution success or failure" (section 4.3). Headline: +10.6% agents, +8.6% finance, whole-context LLM rewrite collapsed 18,282 tokens (66.7) to 122 tokens (57.1), below the no-memory 63.7 ([[RESEARCH-axis-3-agent-memory]] finding 1).
    - https://arxiv.org/html/2510.04618 (read to char 100,000 of 131,315; appendix prompts not read)
    - Marks: peer-reviewed (ICLR per Semantic Scholar); retraction not checked; not preprint-only; 576 citations (S2, prior axis); convergence with 12 and 13 on outcome labels
    - Grade: measured by authors; the counter mechanism itself is unmeasured; counters are described, not shown to help; medium

12. **Later task outcomes are free quality labels, and bad stored records compound** (confidence: medium)
    - Experience-following: a close match between a new task and a stored record yields a close output; stored errors "compound and degrade future performance"; "misaligned experience replay": runs that look correct can mislead when reused. Selective addition and deletion matter and later task evaluations serve as "free quality labels". Abstract page read; no figures extracted.
    - https://arxiv.org/abs/2505.16067 (v2 2025-10-10; the abstract page names no venue; the prior axis recorded ACL 2025 from Semantic Scholar)
    - Marks: venue conflicts between sources (preprint per arXiv page, ACL per S2); retraction not checked; 153 citations (S2, prior axis); convergence with 11 (counters) and 14
    - Grade: measured empirical study, abstract only; medium

13. **MemRL learns a utility (Q) per stored memory from outcome reward; update is an exponential-average toward the final reward** (confidence: medium)
    - Memory is an Intent-Experience-Utility triplet; retrieval is two-phase (similarity recall, then re-rank by learned Q). A later paper describes the update as a Monte-Carlo step with discount 0, target +1 on success and -1 on failure, re-rank score `w_sim*sim + w_Q*Q`. Evaluated on HLE, BigCodeBench, ALFWorld, Lifelong Agent Bench; the abstract gives no figures ("significantly outperforms").
    - https://arxiv.org/abs/2601.03192 (abstract); update form via https://arxiv.org/pdf/2606.29315 (secondary description, from a search snippet, not opened)
    - Marks: preprint (v2 2026-02-12, no venue on page); retraction not checked; citation count not queried; convergence with 12 and 14
    - Grade: measured by authors, no numbers read; low-medium

14. **The shared-credit problem is the named failure of outcome scoring** (confidence: medium)
    - RoMeRL: a whole-trajectory reward is given to every memory retrieved together, so unrelated memories receive "misleading utility updates"; the persistent version is the "memory-reward trap". Its fix keeps a fixed-size utility state per task split by outcome polarity; on ALFWorld and LifelongAgentBench it reports cold-Q ratio -80.0%, feedback density about 6x, stored memory -84.4%, LLM calls -21.1% (no number measures the trap itself).
    - UpliftMem scores whole memory sets by execution uplift versus no memory, because outcome labels exist only for sets actually executed and each alternative costs a rollout; decision accuracy 41.7 to 66.5 (Qwen3-4B) and 44.4 to 68.8 (Qwen3-8B) on its own benchmark.
    - https://arxiv.org/abs/2608.02508 ; https://arxiv.org/abs/2609.36805
    - Marks: both preprints, abstract pages read; retraction not checked; citation counts not queried; convergence: each addresses the same attribution noise as finding 9
    - Grade: measured by authors on synthetic or agent benchmarks, abstracts only; low-medium

15. **Memento (case-based, learned case selection) and Dynamic Cheatsheet (self-curated, no labels) are the two ends of "how much outcome signal is needed"** (confidence: medium)
    - Memento: a neural case-selection policy over episodic memory, rewritten by environment feedback. GAIA validation 87.88% Pass@3, test 79.40%; DeepResearcher 66.6% F1; case memory adds 4.7 to 9.6 absolute points out of distribution. Dynamic Cheatsheet: black-box model curates its own memory with no ground-truth labels or human feedback; GPT-4o on Game of 24 from 10% to 99%, Claude 3.5 Sonnet more than doubled on AIME, GPQA-Diamond +9%, MMLU-Pro +8%. Both are measured on tasks with a checkable answer.
    - https://arxiv.org/abs/2508.16153 ; https://arxiv.org/abs/2504.07952
    - Marks: preprints on arXiv pages (venues not shown); retraction not checked; Memento 126 citations (S2, prior axis); convergence: both gain from reusing prior solved cases
    - Grade: measured by authors, benchmark with checkable answers; medium for effect, low for transfer to prose lessons

16. **ReasoningBank judges success itself and mines failures too** (confidence: medium)
    - Distills strategies from "self-judged successful and failed experiences", retrieves, and writes back; beats raw-trajectory and success-only memory on web and software-engineering benchmarks (abstract gives no figures); memory-aware test-time scaling compounds the gain. ICLR 2026; code from the authors' lab.
    - https://arxiv.org/abs/2509.25140
    - Marks: peer-reviewed (ICLR 2026); retraction not checked; 351 citations (S2, prior axis); convergence with 11 (failures as signal) and with Compass's failure-shaped capture triggers
    - Grade: measured by authors, abstract only; medium

17. **Outcome-scored retrieval measures are fragile; no result found for prose-rule memories like lessons** (confidence: medium)
    - A 2026 survey names four threats to memory-system evidence: underscaled benchmarks, judge-sensitive metrics, backbone-dependent accuracy, hidden maintenance cost (from the prior axis; abstract level). Every outcome-scored paper above targets agent tasks with automatic success checks (ALFWorld, GAIA, AIME, BigCodeBench); none found measures outcome scoring over short human-readable rules injected into a coding agent's planning context.
    - https://arxiv.org/abs/2602.19320
    - Marks: preprint; 33 citations (S2, prior axis); retraction not checked
    - Grade: survey, abstract only; medium

## What the track record should drive under the Data rule

Facts the sources and code allow (no ranking of options here; see candidates for the fork):

- Report only is already the form of the closest existing audit (`lesson-coverage` and the validator never gate). Outcome counters would join that posture.
- Move colder: step 6 of consolidate already moves lessons to `archive/lessons/` and `lesson-coverage` already resolves citations to archived lessons as legal. A "harmful-leaning" lesson could move colder by the same mechanism with its counters kept in frontmatter (counters are not deletable data).
- Flag for recheck: escalation is the existing flag (`escalated:` first in `rank`); `lessons/SKILL.md:73` calls for human review. A second flag value would fit the same slot.
- ACE does not use counters to prune, so no source shows what threshold on counters is safe; any threshold in Compass would be a guess.

## Candidate changes for Compass

Ranked by impact. Each is a fork for the human and planner, not a recommendation.

1. **Per-lesson outcome counters, written mechanically from the task join, report-only first.** North stars: accuracy, perfect memory, low token usage (script, no model call). Would change: lesson frontmatter (e.g. `cited_ok`, `cited_rework`), a CLI step that reads `lessons:` fields and `phase-summary.yaml` after a phase and increments counters; `consolidate` reports lessons whose rework share is high. Evidence: findings 6-8, 11-12. Already covered? No: score is recurrence only (finding 1); `lesson-coverage` stores nothing (6).
2. **Persist the join inputs outside gitignored `tmp/`.** Today `phase-summary.yaml` and `retrieval-log.jsonl` live under `.compass/tmp/` (deletable scratch), so the evidence for a track record can vanish. Moving a per-task record (task, lessons cited, loops, deviations, verdict) to a cold vault location would serve perfect memory. Would change: build skill phase step, `capturelib`, retention rules. Already covered? No; `.compass/archive/logs/` keeps extraction logs only.
3. **Fix the stale catalog score or rank on it knowingly.** 7 of 60 catalog scores disagree with the lesson file (finding 3). Options: sync rewrites `score` from the file; or `rank` stops using score as a tiebreak. Serves accuracy and near-zero cache misses (the tiebreak decides which lesson loads). Would change: `plugin/cli/commands/sync.py` `_catalog_row` path, `lesson-write` 4a text. Already covered? No; `lessonslib.py:22` documents "sync appends rows but never rewrites".
4. **Log reads of lessons per task from transcripts, not from the ranking call.** Reads give "loaded" with a task key (finding 10), where the retrieval log gives only "ranked" with no task key (5). Serves accuracy of attribution. Would change: a transcript scan beside `sessionslib`, run by a detached worker. Already covered? No; only the retrieval log.
5. **Treat set-level attribution as a design input: record outcome per task and per cited set, derive per-lesson only when a lesson is cited alone or across many tasks.** Evidence: findings 9, 14. A lesson cited only inside a fixed pair never separates from its pair. Serves accuracy. Would change: the counter schema in 1. Already covered? No.

## Contradictions

- Findings 1-2 (score rises with recurrence = failure to prevent) vs the `lessons/SKILL.md:45` wording "higher = more reinforced": the same number reads as helpful in one place and as non-application in the other. Not resolved in the source.
- Finding 12 venue: the arXiv abstract page names no venue; the prior axis cites ACL 2025 from Semantic Scholar. Not re-queried here.

## Gaps

- Appendix prompts and code of ACE not read, so the exact counter increment rule is unconfirmed (finding 11).
- Abstract-level only for findings 12-16; no per-paper effect sizes for counter or utility ablations were extracted. No paper found ablates helpful/harmful counters alone.
- Citation counts and retraction status not queried this pass for the 2026 papers (13, 14); the 2608/2609 papers were reached only through a search snippet and an abstract page.
- Whether a persisted structured validator verdict exists was checked by grep only (finding 7).
- 14 phase summaries is the full sample on this vault; per-lesson ratios are not computable for most lessons (finding 8). Transcript scan covers one machine's transcripts.
- No source measures outcome scoring over short prose rules in a coding agent's planning context (finding 17).
