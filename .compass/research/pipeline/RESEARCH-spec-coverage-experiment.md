---
title: "Scoring a Research Document Against Its Spec: The Nugget-Recall Experiment"
type: research
status: done
confidence: medium
area: methodology
tags: [research, completeness, nuggets, evaluation, scope, stop-rule]
created: 2026-11-27
updated: 2026-11-27
git_branch: build/plan-018-w2
git_commit: 01087d5
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]", "[[research/pipeline/research-scope/REVIEW-spec-023-research-consolidation]]", "[[research/pipeline/research-scope/RESEARCH-research-spawning-research]]"]
summary: "castorini's nuggetizer, pointed at SPEC-023 and its consolidated review, runs end to end and scores 2 of 7 vital claims supported (strict vital recall 0.29); 3 of the 4 unsupported vital claims restate the spec's Problem diagnosis rather than anything research must cover, and the one Need no research document covers at all (the source ledger) surfaces only as an okay-rated claim"
---

# Scoring a Research Document Against Its Spec: The Nugget-Recall Experiment

> [!question] You decide
> Read the seven vital claims in the table below, especially the five marked unsupported or partial. Are they gaps in the research, or artifacts of pointing a question-answering scorer at a spec? The plan's rule: if they are artifacts, the mechanism retires rather than being tuned.

Evidence for [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-05: whether a finished research document can be scored for what it still misses against the spec it was written for. The scorer is castorini's nuggetizer, profiled in [[research/pipeline/research-scope/RESEARCH-research-spawning-research]] findings 32 to 34.

## Method

- **Scorer:** castorini/nuggetizer at commit `d00dc3e` (2026-04-19), Apache-2.0, cloned and run unmodified: its own creator, scorer and assigner prompt templates, its window sizes (10) and nugget cap (30), its `calculate_nugget_scores`.
- **Mapping**, fixed by the plan before the run: the spec's Problem section is the query; each Decision (9) and each Need (10) is one source document for the creator; the whole of [[research/pipeline/research-scope/REVIEW-spec-023-research-consolidation]] is the single passage the assigner checks.
- **Model:** the library defaults to gpt-4o. No OpenAI key was available, so every stage ran on Claude Sonnet through headless Claude Code with no tools and no MCP servers, behind an adapter with the library's own `run(messages, temperature)` contract.
- **Cost:** 8 calls (2 creator, 3 scorer, 3 assigner), USD 0.35. One run; no second sample was taken.

## Result

| Metric | Score |
|---|---|
| Strict vital recall (the plan's coverage score) | 0.29 (2 of 7) |
| Vital recall, partial counts half | 0.43 |
| Strict recall over all 23 claims | 0.30 |
| Recall over all claims, partial counts half | 0.46 |

### Per-claim breakdown

Origin is this document's reading of which spec text the creator drew each claim from; the scorer does not record it.

| # | Claim | Importance | Assigned | Origin |
|---|---|---|---|---|
| 1 | Research covers the whole spec, always | vital | partial | D-01 |
| 6 | Research axes should span the spec, not mirror its question list | vital | support | Need 1 |
| 7 | Pipeline lacks rule deriving research axes from a spec | vital | not | Problem |
| 11 | Narrow scope gets locked in at the gate | vital | partial | Problem |
| 12 | Researcher clause to read beyond brief comes too late | vital | not | Problem |
| 13 | Open Questions section is cheapest derivation but flawed | vital | not | Problem |
| 23 | Question field is never the scope | vital | support | D-01 |
| 2 | Human questions lead; otherwise the spec leads | okay | partial | D-02 |
| 3 | Human's own questions outweigh spec-listed questions | okay | support | Need 10 |
| 4 | Open questions must never lead research | okay | not | D-02 |
| 5 | AI-generated open questions are mostly low quality | okay | not | Problem |
| 8 | Orchestrator currently improvises research axes | okay | not | Problem |
| 9 | Research entry points know only codebase and papers shapes | okay | not | Problem |
| 10 | Axes are approved at human gate before researchers run | okay | partial | Problem |
| 14 | Catalog of research methodologies shipped; agent chooses one and states it | okay | support | Need 2 |
| 15 | Curated source list shipped as starting points for every run | okay | partial | Need 6 |
| 16 | Source curation: specialist blog admitted, uncurated blog pile not | okay | support | Need 3 |
| 17 | Findings carry mechanical reliability marks, recorded | okay | partial | Need 3 |
| 18 | Dedicated retriever per curated source | okay | not | Need 4 |
| 19 | Source ledger records misleading sources and overturning forward citations | okay | not | Need 5 |
| 20 | Code over documentation wherever code exists; fetch and read it | okay | support | Need 7 |
| 21 | Research plugins in session are discovered and used | okay | partial | Need 8 |
| 22 | Research run can conclude more research is needed and spawn it | okay | support | Need 9 |

## Findings

1. **The mapping runs end to end and emits a numeric score with a per-claim breakdown** (confidence: high)
   Nothing in the library had to change: a spec flattens into the `Request(query, documents)` shape and a research document into the assigner's single context. The plan's automated criterion is met.

2. **Most of the vital ground truth came from the query, not from the documents** (confidence: high)
   Four of the seven vital claims (7, 11, 12, 13) restate the spec's Problem section, which was passed only as the query. The creator prompt places the query in the prompt twice and asks for "the information required for the query", so the model treats the problem statement as content to extract. Three of those four are exactly the unsupported vital claims. They describe the pipeline as it stood before the spec, which a research consolidation has no reason to repeat; the vital-recall score is mostly a measure of that, not of research coverage.

3. **The one Need that no research document covers surfaces, but only as an okay-rated claim** (confidence: high)
   Claim 19, the source ledger (Need 5), is unsupported, and a search for "ledger" and for overturning or forward-citation tracking across all seven SPEC-023 research documents finds no finding on it. That is a real gap the score detected; the plan's TASK-132 builds the ledger with no research behind it. The scorer rated it okay, so it does not move the plan's chosen metric.

4. **Decisions read as policy statements the research is not expected to restate** (confidence: medium)
   Claim 4 (open questions never lead, D-02) is unsupported because the consolidation does not repeat the human's directive; the derivation evidence that serves it sits in a sibling document. A Decision is an instruction to the research, not a claim the research should contain, so scoring a document for restating it measures echo rather than coverage.

5. **One passage under-reads a multi-document research run** (confidence: medium)
   SPEC-023's research is seven documents and the consolidation is the one scored. Claim 18 (a dedicated retriever per source) is unsupported in the consolidation while the source inventory profiles each source's access route. A scorer fed one document reports sibling coverage as a gap.

## Reading, for the human to confirm

My reading, a guess until you confirm it: the three unsupported vital claims are artifacts of the mapping (finding 2), so by the plan's rule the mechanism as mapped retires. Against that, it found the one genuine gap (finding 3) among its unsupported claims; it did not rank it vital. A query built from the spec's Desired Outcome rather than its Problem would likely change finding 2, and the plan treats that change as tuning, not a second run.
