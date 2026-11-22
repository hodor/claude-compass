---
title: "Axis 1: Consolidation today and delta edits"
type: research
status: complete
confidence: medium
tags: [lessons, consolidation, memory, delta-edits, ace]
created: 2026-11-21
author: researcher
summary: "Where a model rewrites lesson text today (consolidate steps 3-4, lesson-write 4b), how ACE itemized deltas and counters work in paper and released code, and what a delta-edit consolidation would change in plugin/"
area: methodology
updated: 2026-11-21
---

# Axis 1: Consolidation today and delta edits

From [[SPEC-002-consolidation-grounded-in-sources]].

## Question

Where does Compass consolidation have a model rewrite whole lesson or index text, and how would ACE-style itemized delta edits with counters map onto the lesson format and the Data rule?

## Methodology

Repository mining, adapted to one codebase: a step-by-step trace of the consolidate and lesson-write skills and the CLI code they touch, plus a count over the vault's own lessons. Forward snowballing from the ACE paper (Semantic Scholar citation list) for newer work. grading: allowed, so each finding carries a grade.

## Findings

### A. Consolidation today (code and skill text read)

1. **Consolidation is a skill a model follows, with no CLI step behind it** (confidence: high)
   - The only code touching consolidation is `sync.py`, which writes the trigger markers: `INDEX_WARNING`, `CATALOG_WARNING`, hot-path marker (`plugin/cli/commands/sync.py:67-69`, `:655-659`). `grep` over `plugin/cli` finds no function that merges, rewrites or archives lessons. Steps 1-10 of `plugin/skills/consolidate/SKILL.md` are all performed by the model through Read/Edit/Write.
   - Trigger: a standing warning marker, a `folder_over_ceiling` or `taxonomy_hints` warning, or the human's ask (`consolidate/SKILL.md:16-25`). Catalog cap is 360 lines / 25,000 bytes / 50 lessons (`sync.py:55-62`).
   - Marks: code read, first-party; no retraction applicable; not preprint; 0 citations; single source.
   - Grade: direct reading of shipped code and skill text; high.

2. **The model rewrites whole text at four places** (confidence: high)
   - `consolidate/SKILL.md:63` (merge): the kept lesson's body is "compress[ed]" to fit 5 lines when the loser had nuance. Whole-body model rewrite.
   - `consolidate/SKILL.md:67-71` (step 4): every body over 5 lines is distilled by a model to <=5 lines; reported "before/after for the human's audit". This is the form ACE measured as harmful.
   - `lesson-write/SKILL.md:97` (4b refinement): the model edits the matched lesson's body in place and compresses to 5 lines when it overflows. Reached on every refine and, via `extract-lessons/contradiction-check.md`, on every "revise" outcome.
   - `consolidate/SKILL.md:108-116` (step 8): the root index `## Lessons` section is replaced wholesale by a fixed pointer; and step 7 (`:89-104`) has the model regenerate the whole catalog from the lesson set.
   - Marks: code read; first-party; 0 citations; single source.
   - Grade: direct reading; high.

3. **What is preserved, and where displaced text goes** (confidence: high)
   - Rewrite and merge-compress: displaced text moves to `## Record (preserved)` in the same file, exempt from the 5-line cap (`consolidate/SKILL.md:69`, `lesson-write/SKILL.md:97`). Merge loser: file stays, `status: archived`, filename in the winner's `merged_from` (`consolidate/SKILL.md:62`). `seen:` dates are never trimmed (`:73-75`). Stale baseline (score 5, `seen: []`, >90 days) moves to `archive/lessons/` (`:77-85`). Archived catalog rows drop only after the file carries every row field (`:104`, `lesson-write/archive.md:10`). Archive appends a `Superseded:` line (`archive.md:11`).
   - The Data rule is honoured by prose only. Nothing in `plugin/cli` checks that a rewritten body's displaced text exists under a Record section; the `guard` hook blocks deletes and emptying writes, not lossy edits that stay long.
   - Marks: code read; first-party; 0 citations; single source.
   - Grade: direct reading; high.

4. **The 5-line cap has no mechanical check** (confidence: high)
   - `validate.py:47` requires frontmatter fields for lessons (title ... summary) but no body-length rule; `grep` for "5 line"/`body_too_long` in `plugin/cli` finds only skill text. `body_too_long` is a string the model returns (`lesson-write/SKILL.md:144,156`).
   - Vault sample: 60 lesson files, 0 with a body over 5 lines (my count, body = text after frontmatter up to `## Record`); 3 carry a `## Record (preserved)` section; 0 carry `merged_from`; 13 have a non-empty `seen`; catalog is 422 lines with the over-cap warning standing (`.compass/meta/lessons-catalog.yaml:1`).
   - Marks: code read plus a count run by me; first-party; single source.
   - Grade: measured by command; high.

5. **Counters today are recurrence only: `score` and `seen`** (confidence: high)
   - `score` starts at 5, +1 per recurrence, cap 10; `seen` holds dates, 3 dates then `escalated` (`lesson-write/SKILL.md:89-91`, `:123-126`). Retrieval sorts escalated first, then tag overlap, area, text overlap, then score (`plugin/cli/lessonslib.py:208-217`). `lesson_coverage` reports cited / surfaced-but-uncited / unresolvable per plan with no pass/fail outcome (`lessons/SKILL.md:98`). No `helpful`/`harmful` field exists in lesson frontmatter, catalog rows or `_catalog_row` (`sync.py:512-528`).
   - Marks: code read; first-party; single source.
   - Grade: direct reading; high.

6. **Catalog rows are written only by sync; existing rows are never rewritten** (confidence: high)
   - `_catalog_row` builds a 7-field row and appends missing files; `escalated` is stamped by lesson-write by hand because sync "never rewrites existing rows" (`lessonslib.py:8-12`, `sync.py:512-528`). A counter in the catalog would need a new sync path that updates a row in place, or a counter that lives only in the lesson file.
   - Marks: code read; first-party; single source.
   - Grade: direct reading; high.

### B. ACE paper and released code

7. **Item format: bullet with id and two counters; one line of text** (confidence: high)
   - Paper section 3.1: context is "structured, itemized bullets", each with a unique id, helpful/harmful counters, and one unit of content. Released code defines the line as `[id] helpful=X harmful=Y :: content` (`playbook_utils.py:13-16,46-48` in the ace-agent/ace repo) with ids `<section-slug>-<5 digits>` (`:143-150`). A new bullet starts at `helpful=0 harmful=0`.
   - https://arxiv.org/abs/2510.04618 ; https://github.com/ace-agent/ace
   - Marks: peer-reviewed (ICLR 2026 per prior review, per Semantic Scholar), code read; retraction not checked; not preprint-only; 576 citations per prior review; convergence: agrees with [[RESEARCH-axis-3-agent-memory]] finding 1.
   - Grade: measured on benchmarks by the authors; code read directly; high on format, medium on outcomes.

8. **Roles: Generator marks bullets, Reflector critiques, Curator emits deltas; counters are bumped by code from model tags** (confidence: high)
   - Generator flags which bullets were useful or misleading; Reflector distils lessons (up to 5 rounds, A.6); Curator emits "compact delta entries" (paper section 3). In code the Reflector returns `bullet_tags`, and `update_bullet_counts` increments helpful/harmful deterministically (`ace.py:510-526,553-569`; `playbook_utils.py:50-87`). The model judges, the code counts.
   - Marks: code read plus paper; peer-reviewed; convergence with item 7.
   - Grade: measured plus code; high.

9. **The deterministic merge in the released code is append-only; the paper's "update in place" is not implemented** (confidence: high; this contradicts the paper's wording, see Contradictions)
   - The Curator JSON validates types ADD, UPDATE, MERGE, DELETE, CREATE_META (`curator.py:393`), but `_add_operations_only` drops all but ADD ("ACE currently applies only ADD operations", `curator.py:332-342`) and `apply_curator_operations` has UPDATE/MERGE/DELETE commented out under a TODO (`playbook_utils.py:96-135`). Counter updates are the only in-place change. Result: no model ever rewrites an existing bullet's text in the released path; growth is bounded by the optional dedup pass below.
   - Marks: code read; first-party repo; 0 independent citations of this detail.
   - Grade: direct reading of code; high.

10. **Grow-and-refine: dedup is optional, embedding-based, and the merge inside it is an LLM call** (confidence: high)
    - Paper section 3.2: new ids append, existing bullets update counters, dedup by "semantic embeddings", run "proactively (after each delta) or lazily (only when the context window is exceeded)". Code: `use_bulletpoint_analyzer` defaults to `False`, threshold 0.90 (`ace.py:41-42,133-134`); embeddings are `all-mpnet-base-v2`, cosine over L2-normalised vectors, grouping every pair at or above the threshold (`bulletpoint_analyzer.py:76,127-148,150-190`); each duplicate group is then merged by an LLM prompt that outputs one bullet with summed counters (`:193-250`). Paper A.6: dedup threshold 50/70/90% gave FiNER 77.0/73.9/78.6 (base 70.7), pruning trigger 10K/50K/100K tokens gave 78.6/78.4/78.3, no embedding model named in the paper text.
    - Marks: peer-reviewed plus code read; convergence between paper and code on mechanism, divergence on "non-LLM" (see Contradictions).
    - Grade: measured plus code; high on mechanism, medium on thresholds (small ablation, one benchmark).

11. **Measured results and collapse numbers (DeepSeek-V3.1 unless noted)** (confidence: high that these are the paper's numbers, medium on transfer)
    - Collapse (section 2.2): a Dynamic Cheatsheet context went from 18,282 tokens at 66.7 accuracy to 122 tokens at 57.1 in one rewrite step, below the 63.7 no-adaptation baseline.
    - AppWorld average: ReAct 42.4; ACE offline 59.4; ACE online 59.5; GEPA 46.4; DC-CU online 51.9; top leaderboard entry 60.3 (Table 1). Finance average: base 69.1; ACE offline 81.9 with labels, 77.1 without; online 76.6 / 72.9; Table 2.
    - Ablation: without incremental delta updates, AppWorld test-normal 67.3/46.4 versus 76.2/64.3 with them (A.5, Table 18: "-11.7% TGC and -27.8% SGC" per C.2). Without Reflector and multi-epoch 55.1; without multi-epoch 56.8 (Table 3).
    - Cost (Table 4): AppWorld offline latency -82.3%, rollouts -75.1% versus GEPA; FiNER online latency -91.5%, cost $17.7 to $2.9 (-83.6%) versus DC.
    - Limits (sections 4.4, 5): needs a reasonably strong Reflector; without ground-truth labels or reliable execution signal ACE online on FiNER fell to 67.3 (base 70.7); short instructions beat rich context on HotPotQA and Game of 24.
    - Marks: peer-reviewed; read to the end of A.6, prompts (appendix F) are figures and were not readable; no independent replication found; convergence with [[RESEARCH-axis-3-agent-memory]] finding 1.
    - Grade: measured by the authors on benchmarks, single lab; peer review weighs little in this field; medium-high.

### C. Newer work (2025-2026)

12. **Memory entries linked to the run they came from can be checked against it** (confidence: medium, abstract only)
    - WikiTrace (arXiv 2611.14320, Nov 2026, under ACL Rolling Review): each insight links to a summary and the raw trajectory; the agent follows links when an insight lacks detail, conflicts with another, or comes from a failed task, then corrects it before use. Five benchmarks, "consistently outperforms existing memory approaches"; no figures on the abstract page. Defines "memory-induced degradation": memory makes an agent fail tasks it solves without it.
    - https://arxiv.org/abs/2611.14320
    - Marks: preprint; retraction not checked; preprint-only; citation count 0 (Semantic Scholar returned no data); convergence: agrees with the spec's source-grounding need and with [[RESEARCH-axis-3-agent-memory]] finding 2.
    - Grade: abstract-only read, measured claims not verified; low-medium.

13. **Falsification-gated admission and outcome-scored lifecycle** (confidence: medium, abstracts only)
    - FGSE (arXiv 2611.14326, 2026-11-10): each candidate lesson is a structured hypothesis (precondition, behavior change, expected effect, verifier), applied in a temporary state, tested on transfer, falsification and archived-regression probes, then committed, refined or rejected; 39.8 WebArena, 78.8 AppWorld average, falsification failures 5.0%.
    - AdMem (arXiv 2611.20605, 2026-11-16, NeurIPS 2026 workshop): per-entry utility score updated online from a binary reward plus reflection, used to rank retrieval and to decide eviction and merge; 441 of 707 tasks versus ReAct 388 and a workflow-induction baseline 312; that baseline lost to memoryless ReAct in 7 of 8 domains.
    - Marks: preprints / workshop; retraction not checked; 0 citations each; convergence with item 12 on grounding and with ACE on per-entry outcome counters.
    - Grade: abstracts only, measured claims not verified; low-medium.

14. **A memory gain can be leakage; retrieval margin shrinks as the store grows** (confidence: low-medium)
    - Audited migration-agent study (arXiv 2611.16143, 2026-11-12): memory raised reference conformity by 0.015 [0.004, 0.025]; 72% of held-out units (264 of 367) shared a reference with training data; on 103 leak-free units the effect was 0.002 [-0.008, 0.011]; a model-free copy baseline beat every LLM system (0.222 versus best 0.163); retrieval margin fell 54% as the store grew from 12 to 1,200 entries.
    - https://arxiv.org/abs/2611.16143
    - Marks: preprint; 0 citations; single source; one domain (SQL migration).
    - Grade: abstract only; measured; low-medium on transfer to lessons.

## Mapping ACE mechanics onto the Compass lesson format

| ACE mechanic | Compass today | What a delta-edit form touches |
|---|---|---|
| bullet = id + counters + one line | lesson file = filename id, `score`/`seen`, 5-line body, summary | add `helpful`/`harmful` integers to lesson frontmatter beside `score`/`seen`; filename already serves as id |
| counters bumped by code from model tags | `score`/`seen` bumped by the model editing frontmatter (`lesson-write` 4a) | a CLI command (new, beside `lesson_coverage.py`) that increments counters from validator/coverage outcomes |
| Curator emits ADD/UPDATE deltas, code applies | lesson-write 4b model edits body in place | model emits a delta (target file, new body text, reason); code validates 5-line cap, writes displaced old body to Record, then applies |
| dedup by embedding, optional, threshold 0.90 | merge judged by model over catalog manifest (`consolidate` step 3, `lesson-write` step 3) | a script proposes candidate pairs (tag overlap and summary similarity, or embeddings); a model only judges the pair; code merges `seen`/`score`/`tags` |
| prune low-utility, lazily at a size trigger | archive at score 5, `seen: []`, >90 days; human sees every archive | rule keeps the trigger; `harmful >= helpful` becomes a report line, and stale text moves colder as today |
| append-only growth between refinements | caps: 50 lessons, catalog 360 lines | unchanged; ACE's 10K-100K prune trigger is the analogue of the existing caps |

Fit with the Data rule: ACE's released path never rewrites bullet text and never deletes, so it already agrees with "nothing destroyed"; the three constraints that need explicit code are the 5-line cap, the Record section and the catalog row (rows are append-only, item 6).

## Candidate changes for Compass

Ranked by impact. None is a recommendation to adopt; each names what it would change and whether Compass covers it.

1. **Delta-only lesson edits applied by code** (north star: accuracy, perfect memory). Replace the model's whole-body rewrite in `consolidate` steps 3-4 and `lesson-write` 4b with a delta payload (target, replacement body, displaced text, reason) that a new CLI command validates (cap of 5 lines, displaced text lands in `## Record (preserved)` byte for byte) and applies. Changes: `plugin/skills/consolidate/SKILL.md`, `plugin/skills/lesson-write/SKILL.md`, a new command under `plugin/cli/commands/`. Not covered today: the Record section is prose only (finding 3), and the 5-line cap is unchecked (finding 4).
2. **Outcome counters on lessons** (accuracy). Add `helpful`/`harmful` to lesson frontmatter, bumped by code when a validator verdict or `lesson-coverage` result ties a cited lesson to pass or fail. Changes: lesson template (`obsidian/templates.md`), `validate.py:47` field list, `lesson_coverage.py`, `lessonslib.py` ranking, `_catalog_row` if the counter must reach the catalog (item 6). Not covered: `grep` finds no helpful/harmful field and `lesson-coverage` reports no outcome. Item 8 shows ACE counts in code from model tags, which is the part that would carry over.
3. **Mechanical cap and Record check in `compass validate`** (accuracy, low token usage). Report any lesson body over 5 lines (excluding Record) and any rewritten body whose Record section does not contain the displaced text. Changes: `validate.py`. Not covered (finding 4).
4. **Script-proposed duplicate pairs, model judges only the pair** (low token usage). `consolidate` step 3 currently has the model compare every pair; a script ranks candidate pairs (tag and summary overlap now; embeddings optional as in ACE's 0.90 threshold) and merges `seen`/`score`/`tags` itself. Changes: `consolidate/SKILL.md` step 3, a new command. Partly covered: `lessonslib.rank` already scores tag/area/text overlap and could be reused; ACE's own merge step still uses an LLM (item 10), so only the pair-finding is mechanical.
5. **Source link per lesson (WikiTrace-style)** (accuracy). `source` already records the producing pass (`lesson-write/SKILL.md:125`); adding the transcript or commit reference would let a recheck open the original. Relation to the spec: this is the grounding half of [[SPEC-002-consolidation-grounded-in-sources]], not a delta-edit mechanic; items 12-14 are abstract-only and need full reading before design.

## Contradictions

- The ACE paper says deltas are merged "by lightweight, non-LLM logic" and bullets "update in place" (section 3). The released code applies only ADD, leaves UPDATE/MERGE/DELETE as TODO (item 9), and its dedup merge is an LLM call (item 10). The "non-LLM" claim holds for append and counters, not for the optional dedup.
- [[RESEARCH-axis-3-agent-memory]] cites ACE as ICLR per Semantic Scholar; I did not re-verify the venue.
- `consolidate/SKILL.md:63` says the merge keeps the winner's body "unchanged unless the loser had nuance", while step 4 and `lesson-write` 4b rewrite bodies by model; both are model rewrites in the sense ACE measured, but ACE measured a rewrite of a whole 18K-token context, not of a 5-line body. No source reached here measures harm at 5-line scale.

## Gaps

- ACE appendix F prompts (Reflector and Curator) were figures, unreadable; the exact Curator JSON field set beyond `type`, `section`, `content`, `reason` (as seen in `curator.py`/`playbook_utils.py`) is read from code only.
- Findings 12-14 are abstract-only; arXiv ids 2611.* are very recent, and the arXiv search API returned nothing for them, so existence was confirmed only through the abs pages and Semantic Scholar. Full text would be needed for WikiTrace's link-following cost and FGSE's probe design.
- No source found that measures whole-body rewrite harm at the scale of a 5-line lesson, or counts how often Compass's own consolidation has rewritten a body (3 of 60 lessons carry a Record section; the history before that is in git, not read here).
- Whether `helpful`/`harmful` signals can be derived from validator verdicts in Compass (rather than ACE's labelled benchmarks) is untested; ACE itself degrades without reliable feedback (finding 11, FiNER 67.3 versus 70.7 base).
