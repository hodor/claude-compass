---
title: "Review: SPEC-023 Research Consolidation"
type: research
status: draft
confidence: high
area: methodology
tags: [research, pipeline, methodology, sources, scope, review, convergence, consolidation]
created: 2026-09-13
updated: 2026-09-13
git_branch: "master"
git_commit: "50a2896"
author: "reviewer"
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
summary: "convergence matrix over six parallel research documents keyed to SPEC-023's decisions D-01 to D-07, naming four cross-document contradictions the individual researchers could not see, plus merged gaps tagged for the human's D-05 call and the concrete inputs a planner would lift"
---

# Review: SPEC-023 Research Consolidation

## Inputs

Six agents. Question: does research cover the whole spec, from curated sources, until the plan is fully informed, per [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]?

| Handle | Document | Decisions served |
|---|---|---|
| **A** | [[research/pipeline/RESEARCH-research-methodologies-catalog]] | D-06 |
| **B** | [[research/pipeline/RESEARCH-scope-derivation-from-a-spec]] | D-01, D-02, D-05, D-06 |
| **C** | [[research/pipeline/RESEARCH-source-reliability-criteria]] | D-03 |
| **D** | [[research/pipeline/RESEARCH-code-as-primary-source]] | D-04, D-07 |
| **E** | [[research/pipeline/RESEARCH-research-spawning-research]] | D-05 |
| **F** | [[research/pipeline/RESEARCH-source-inventory]] | D-03, D-07 |

A dash means the document did not address the claim. Agreement is counted over the documents that addressed it, not over all six, so `2/2` means both documents that took a position took the same one.

## Convergence Summary

| Category | Count | Claims |
|---|---|---|
| Converged | 18 | C1-C18 below |
| Partial | 2 | P1 (PRISMA used as conduct guidance), P2 (GPT-Researcher deep-research defaults) |
| Divergent | 2 | X1 (STORM's source filter: wired or dead), X2 (GitHub stars as an owner signal) |

## Matrix

| # | Claim | A | B | C | D | E | F | Agreement |
|---|---|---|---|---|---|---|---|---|
| C1 | Scope derives from facets, document structure, or found evidence, never a standing question list | YES (high) | YES (high) | - | - | - | - | 2/2 |
| C2 | Broad-versus-narrow question scope is settled by methodology choice, not by rule | YES (high) | YES (high) | - | - | - | - | 2/2 |
| C3 | Upfront document-derived axis lists exist in one precedent, which its authors deprecated | - | YES (high) | - | - | YES (high) | - | 2/2 |
| C4 | No off-the-shelf domain allowlist is usable as shipped; the only complete one excludes arXiv | - | - | YES (high) | - | - | YES (high) | 2/2 |
| C5 | No agentic system computes a reliability score; each is a prompt, a venue route, or a list | - | YES (high) | YES (med) | - | - | - | 2/2 |
| C6 | ACM Digital Library, named first in D-03, has no public API and no agent precedent | YES (high) | - | YES (high) | - | - | scoped out | 2/2 |
| C7 | A specialist blog is admitted by a scored instrument, not a blanket rule | YES (high) | - | YES (high) | - | - | - | 2/2 |
| C8 | Documentation drifts from code, with a large empirical evidence base | - | - | - | YES (high) | - | - | 1/1 |
| C9 | Every document that read code found a fresh doc-versus-code discrepancy in this run | YES | YES | YES | YES | YES | YES | 6/6 |
| C10 | Version-to-source matching is heuristic everywhere except Go and NuGet Source Link | - | - | - | YES (high) | - | - | 1/1 |
| C11 | `git clone` is the zero-quota, full-fidelity access path to any code host | - | - | - | YES (high) | - | YES (high) | 2/2 |
| C12 | Stop mechanisms fall into three families; budget and self-report are layered, structural detection is rare | - | YES (high) | - | - | YES (high) | 2/2 |
| C13 | Co-STORM is the only system with executable, evidence-triggered scope growth | - | YES (high) | - | - | YES (high) | - | 2/2 |
| C14 | No system uses a coverage metric as an in-loop stop condition | - | - | - | - | YES (high) | - | 1/1 |
| C15 | Unbounded iteration has its own named failure modes | YES (high) | - | - | - | YES (high) | - | 2/2 |
| C16 | Methodologies each state their own fit, but no source gives a decision procedure | YES (high) | YES (med) | - | - | - | - | 2/2 |
| C17 | Neither Compass research skill has a plugin or MCP discovery step | - | - | - | YES (high) | - | YES (high) | 2/2 |
| C18 | Serena was read from cloned source, never exercised live | - | - | - | YES (high) | - | YES (low) | 2/2 |
| P1 | PRISMA is a reporting standard and supplies no conduct steps | YES (high) | used as conduct (med-high) | - | - | - | - | 1/2 |
| P2 | GPT-Researcher's deep-research breadth default is 3 | - | YES (high) | - | - | two sources disagree (high) | - | 1/2 |
| X1 | STORM's `is_valid_source` predicate is overridden in shipped code | - | NO (high) | YES (high) | - | - | - | 1/2 |
| X2 | Star count is a sound repository-reliability signal | - | - | NO (high) | - | used as lead evidence | - | 1/2 |

## Converged

**C1. Scope derives from facets, document structure, or found evidence, never a standing question list.**
Three families recur and none is question-list-shaped: PICO/PICOC/SPIDER/PCC facets, KAOS goal trees, evidence-driven expansion (B Taxonomy; A findings 11, 19-22).

**C2. Broad-versus-narrow question scope is settled by methodology choice, not by rule.**
Kitchenham cites Staples and Niazi for narrow SLR questions, then recommends broad multi-question scope for mapping studies in the same report (B-5; A-22).

**C3. Upfront document-derived axis lists exist in one precedent, which its authors deprecated.**
LangChain's legacy `report_planner_instructions` emits a structured section list from a document; the current version replaced it with a supervisor deciding one sub-topic at a time (B-26 against B-24, E-19). This is the shape SPEC-023's human gate requires, and the field moved away from it.

**C4. No off-the-shelf domain allowlist is usable as shipped; the only complete one excludes arXiv.**
STORM's `is_valid_wikipedia_source` copies Wikipedia's perennial-sources list, which marks arXiv, bioRxiv, SSRN, and ResearchGate generally unreliable (C-12, `retriever.py:21,97-98,102,110`).
Cross-document narrowing invisible to C: two of those four exclusions are independently unusable on access grounds (SSRN has no API and reserves text-mining and AI-training rights, F-22; ResearchGate bans automated access and enforces it with a bot challenge, F-28), while the other two are the machine-friendliest sources F tested (bioRxiv explicitly endorses machine access, F-23; arXiv is named trusted by D-03). The conflict with D-03 is real but confined to arXiv and bioRxiv.

**C5. No agentic system computes a reliability score.**
Every implementation reduces to a prompt, a venue-routing choice, or a domain list, never a continuous score (C-16). GPT-Researcher's curation is LLM judgment, off by default, with no allowlist anywhere in the codebase (B-19, `default.py:17`).

**C6. ACM Digital Library has no public API and no agent precedent.**
None of the four agents C surveyed integrates it; the only mechanical proxy is venue-prestige ranking applied to a paper's venue (C Gaps). A's own literature passes fell back to Semantic Scholar and open-access mirrors because ACM and Elsevier were unreachable (A Methodology). F excluded ACM by scope as "already known to Compass."
This is the sharpest standing conflict with the spec: D-03 names ACM first among curated points to look, and no document established how an agent reaches it.

**C7. A specialist blog is admitted by a scored instrument, not a blanket rule.**
Garousi's eight-criterion instrument scores authority, methodology, objectivity, date, position, novelty, impact, and outlet tier, normalized to a 0-1 threshold (A-32), with a three-tier outlet classification that places blogs in tier 3 without excluding them (A-30). Library guidance converges on credentials plus affiliation plus a checkable publication record (C-10).

**C8. Documentation drifts from code.**
Comment updates accompany a code change roughly 7% of the time for methods across 1.3 billion AST-level changes (D-18, DOI 10.1109/ICPC.2019.00019); iComment found 60 comment-code inconsistencies of which 33 were confirmed bugs (D-17).

**C9. Every document that read code found a fresh doc-versus-code discrepancy in this run.**
Six for six, independently, while researching something else:

| Document | Discrepancy |
|---|---|
| A-43 | GHTorrent is "best-effort," not the full GitHub mirror its dependents assume |
| B-23 | STORM's `TopicExpert` docstring lists a filtering step its body does not perform |
| C-11 | Semantic Scholar retriever silently drops non-open-access papers, undocumented outside the code |
| D-43 | Compass's own research skills claim no plugin discovery, and have none |
| E-12 | GPT-Researcher's code fallback and shipped config give different deep-research defaults |
| F-6, F-7, F-21, F-25 | OpenAlex key policy, CORE key requirement, PMC `oa.fcgi`, Papers with Code API all contradict their own docs |

This is the strongest empirical support for D-04 in the set, and none of the six authors could see it.

**C10. Version-to-source matching is heuristic everywhere except Go and NuGet Source Link.**
Go resolves natively because the import path is the VCS location; NuGet embeds the building commit in the `.nuspec` (D-6, D-8, D-10).

**C11. `git clone` is the zero-quota, full-fidelity access path.**
Tested unauthenticated against GitHub and GitLab, full history, no rate-limit interaction, because git's smart-HTTP protocol is separate from each host's REST API (F-35).

**C12. Stop mechanisms fall into three families.**
Fixed budget, model-judged sufficiency, structural gap detection; the first two are routinely layered, and no system uses structural detection alone (E Taxonomy). LangChain's supervisor picks `ConductResearch` or `ResearchComplete` under a hard iteration ceiling (E-19, B-25).

**C13. Co-STORM is the only system with executable, evidence-triggered scope growth.**
Two documents found it through different code paths: the Moderator scores never-cited snippets by dissimilarity to prior queries and citations, then turns the top one into a question (E-17, `co_storm_agents.py:159-297`); `ExpandNodeModule` auto-splits an outline section once information volume crosses a threshold (B-22, `information_insertion_module.py:334-420`). This is the only working precedent for D-05.

**C14. No system uses a coverage metric as an in-loop stop condition.**
"Key points coverage" exists only as post-hoc, LLM-judged report evaluation (E-10, arXiv:2512.02038 §5.2.2). A completeness check applied to a finished research document is unbuilt anywhere surveyed.

**C15. Unbounded iteration has its own named failure modes.**
Extra turns introduce cumulative noise and error propagation (E-8); Anthropic names spawning 50 subagents for simple queries and endless scouring for nonexistent sources as early failures (E-27). Rapid review is the literature's sanctioned abbreviation of the same six SLR steps, with 50 distinct combinations found in one 84-paper scan (A-5).

**C16. No source gives a methodology decision procedure.**
Each paper states its own fit condition in isolation; a chooser must be authored by synthesizing those statements (A Gaps, B-10).

**C17. Neither Compass research skill has a plugin or MCP discovery step.**
`claude mcp list` and `claude plugin list --json` both enumerate session capabilities mechanically, and neither `research/SKILL.md` nor `research-codebase/SKILL.md` calls either (D-41, D-42, D-43). Compass ships no code-search skill of its own; the zoekt indexes in this session are host-provided (F-2, D-37).

**C18. Serena was read from cloned source, never exercised live.**
Its tools were not in either researcher's tool list (D Gaps, F-3). D's read is the stronger evidence, and D-22 notes Serena's tool schema is generated from Python introspection at runtime, so the source is authoritative about the surface.

### Observed: the run did not follow its own D-06

Five of six documents declared technology landscape or comparative evaluation as their methodology (A, B, D, E, F); one declared a scoping review (C). Two of the five cite the `obsidian` skill's existing four-approach table as the menu they chose from (B and E Methodology), and that table has four entries against the catalog's eight plus protocol registration (D-44, A Taxonomy).

Two consequences the authors could not see:

- The methodology every document chose is the one A rates as least grounded: it rests on one company's public process plus general multi-criteria decision analysis theory, with no canonical peer-reviewed software-engineering paper behind it (A Gaps), and its own publishers call it subjective, opinion-based, and recency-biased rather than a systematic survey (A-36).
- D-06 says agents choose from the methodologies that research found. In this run they chose from what Compass already shipped, because the catalog was being written in parallel. The mechanism D-06 describes has not yet been exercised.

### Observed: methodology choice can silently drop D-03

Mapping studies deliberately skip quality assessment while SLRs mandate it, which A flags as a by-design depth difference rather than a disagreement (A-22, A Contradictions). Against the spec, it is a live hazard: SPEC-023's third success criterion requires every finding to name a source whose reliability was checked. An agent that picks a mapping study is following a methodology whose authors tell it to skip exactly that step.

### Observed: the run partially met the spec's own third success criterion

Reliability checking was recorded unevenly. C and F check and record it throughout, including live access tests. A records per-finding caveats where a primary text was not parsed, and A-47 flags its own unchecked repository owner explicitly against D-03. E checked repositories before cloning but led with the signal C rates weakest (see X2). No document addresses where or in what form the reliability check gets recorded in a research document.

## Partial

**P1. PRISMA supplies no conduct steps.** 1 of 2.
- A's position (high): PRISMA states it is "not intended to guide systematic review conduct"; an agent treating it as the methodology would have no steps to follow and must pair it with a conduct method (A-16, PMC8008539 Limitations).
- B's practice (medium-high): B-8 lifts the Population-Concept-Context framing from PRISMA-ScR item 4 as scoping-question guidance, which is question framing taken from a reporting checklist.
- Likely explanation: PRISMA-ScR item 4 does prescribe how an objective is framed, so the boundary A draws is real at the level of the whole document and blurry at the level of individual items. Whether a Compass agent may cite a reporting checklist for conduct guidance is unresolved.

**P2. GPT-Researcher's deep-research breadth default.** 1 of 2.
- B-18 (high): `DEEP_RESEARCH_BREADTH: 3` from the shipped config.
- E-12 (high): the code-level `getattr` fallback says 4 while the shipped config says 3, and E names the disagreement.
- E is the more precise read. Not a conflict about behavior, and it is itself an instance of C9.

## Divergent

**X1. Is STORM's `is_valid_source` predicate wired up in shipped code?** Split 1/1, both high confidence, same repository.
- Position A (C-12): yes. The wiki-generation pipeline supplies a concrete predicate, `is_valid_wikipedia_source` at `knowledge_storm/storm_wiki/modules/retriever.py:225-233`, checking netloc against three sets copied from Wikipedia's perennial-sources list (`retriever.py:11-222`).
- Position B (B-23): no. "Every retrieval module accepts an `is_valid_source` callable that defaults to `lambda x: True` and is never overridden in the shipped code," citing `knowledge_storm/rm.py:14-30` and `knowledge_curation.py:182-218`, and calls the `TopicExpert` docstring's filtering step a documented intent the implementation does not carry out.
- What might explain it: the two read different modules. C read the `storm_wiki` retriever wrapper where the predicate is defined; B read the generic `rm.py` retrievers and the knowledge-curation path. The predicate can exist and still never reach the retriever the curation path constructs. Unresolved by either document, and load-bearing: C treats this as the one real reliability taxonomy in the wild, and B treats it as the cautionary example of docs outrunning code.
- Resolved by command, 2026-09-13: `grep -rn "is_valid_source\|is_valid_wikipedia_source" --include=*.py` over the cloned repository finds `is_valid_wikipedia_source` only at its definition (`knowledge_storm/storm_wiki/modules/retriever.py:225`) and no call site passes `is_valid_source=` to any retriever. The predicate is dead code; Position B holds. The seam (C-12) still exists as an unused constructor parameter, and the shipped list is the cautionary example B describes.

**X2. Is star count a sound repository-reliability signal?** Split 1/1, contradiction in practice rather than in prose.
- Position A (C-8, high): no. A Carnegie Mellon study at ICSE 2026 found roughly 6 million fake stars across 18,617 repositories from about 301,000 accounts, with AI and LLM repositories the largest non-malicious recipient category. Stars measure past popularity, not current health. The signals that carry weight are maintainer concentration, commit and release cadence, issue responsiveness, and organization domain verification (C-9).
- Position B (E Methodology, applied): E checked repository reliability before cloning and led with star counts, 29,430 for `assafelovic/gpt-researcher`, 31,299 for `stanford-oval/storm`, 12,679 for `langchain-ai/open_deep_research`, alongside maintainer activity, last-push date, and organization type.
- E's secondary signals are exactly C-9's list, so the disagreement is about what leads. It matters because D-03's owner check is the rule being operationalized, and the two documents would produce different check procedures.

## Gaps

Merged from all six documents, deduplicated. Tagged for the human's D-05 call.

### Needs another research pass before planning

| Gap | Why |
|---|---|
| ACM Digital Library access mechanics (C) | D-03 names it first among curated sources and no document established how an agent reaches it; C found no public API and no code precedent. |
| Technology-landscape methodology lacks a canonical source (A) | Five of six documents used it; A's own gap says it rests on one company's process plus general decision-analysis theory. An ACM or IEEE Xplore pass would settle whether a peer-reviewed software-engineering equivalent exists. |
| Live reachability of DBLP, OpenReview, Internet Archive Scholar, Fatcat (F) | All bot-challenged or timed out from this sandbox's network; a shipped starting list containing an unreachable source fails on every run. Re-test from the deployment network. |
| Complete enumeration of session plugins and MCP servers (D) | `claude plugin list --json` was sampled through `head`, not read in full. D-07 depends on knowing what is actually available, and D calls this a five-minute follow-up. |
| A live completeness or coverage check for finished research (E) | E-10 and E's gap: unbuilt anywhere surveyed. SPEC-023's first success criterion is exactly this test. Closing it means reading the retrieval-augmented verification family (LLatrieval, ReSP) and the primary key-points-coverage benchmark paper, not deep-research report generators. |
| Co-STORM warm-start prompt templates (B) | Co-STORM is the single precedent for D-05, and warm-start is the phase that seeds its initial mind map, the closest analogue to deriving axes from a whole spec. Only confirmed to exist, with fixed budgets. |
| Protocol-registration findings resting on secondary description (A) | A-44, A-46, A-47 were not re-fetched in full, and A-47's GitHub repository owner was never checked, which A flags against D-03's own owner-check rule before either can be cited as a curated source. |
| How a human's injected question outranks a spec's listed questions | No document addressed it. The Needs list requires that the human's own questions weigh more than any question the spec lists, and the closest precedent found is Gemini's user-editable plan (B-30). |

### Planner can proceed without it

| Gap | Why |
|---|---|
| Which sources Compass ships (C, F) | Both documents defer it to the human by design; F's 34-source matrix with tested access status is the evidence base, and the choice is the decision itself. |
| No decision procedure for choosing a methodology (A) | A's fit statements exist per methodology; the chooser is authoring work, not missing evidence. |
| Rapid review is a moving target (A) | Already actionable as a constraint: point at current Cochrane guidance rather than freezing a recipe. |
| Where the reliability check is recorded | A template and format decision, not missing evidence; C-7's preprint marking convention is the one worked example. |
| Mechanical verification of a blog author's claimed affiliation (C) | C-10's name-search-plus-independent-citation proxy is specifiable today; affiliation verification is a refinement. |
| i*/Tropos primary paper paywalled (B) | KAOS carries the structure-driven decomposition claim at high confidence from a directly fetched primary source (B-11, B-12). |
| Petticrew and Roberts' PICOC book not read directly (B) | Kitchenham quotes it verbatim, fetched directly (B-2). |
| Cochrane Handbook chapter 2 guard techniques from a search summary (B) | The review-versus-synthesis scope distinction is corroborated by Arksey and O'Malley's iteration guidance, fetched in full (B-6). |
| OpenAI launch blog returned 403 (B); OpenAI and Perplexity parallel-agent architecture unstated (B); Gemini and Perplexity not covered for stopping (E) | Neither vendor publishes inspectable code, so a further pass yields vendor prose either way (E-29). |
| smolagents domain filtering unchecked (B) | The weakest precedent in the set; no Need depends on it. |
| Serena not exercised live (D, F) | D read the source that generates the tool schema by introspection, so the surface is authoritative (D-22). |
| The "25.5% of Python docstrings are inconsistent" statistic (D) | Untraceable to a primary source. Treat as do-not-cite; the drift case stands on D-17, D-18, D-19 at high confidence. |
| Private and internal package source conventions (D); `pattern-finder` not read (D) | Neither is load-bearing for any Need. |
| Saturation papers read via search summary (E) | Saturation enters the taxonomy as an analogue, not an adopted mechanism. |
| GPT-Researcher `multi_agents/` internal iteration limits (E) | Only matters if Compass adopts the bounded-revision pattern, which E-15 already shows cannot trigger new research. |
| Brazil-specific legal status of shadow libraries (F) | Shadow libraries are not named in D-03 and no Need depends on them; the question only becomes load-bearing if the human elects to include them. |
| Unpaywall terms of service unread; crates.io crawler policy unretrievable; CORE's exact quota; no authenticated call against key-gated sources (F) | Operational details resolvable at ship time, each behind a decision the human has not yet made. |
| No successor to Gusenbauer and Haddaway evaluating the newer aggregators (F) | F searched and the paper does not appear to exist; another pass cannot find what is not there. F's live access tests are the available evidence. |

### Closed by a sibling document

- B listed GPT-Researcher's `multi_agents/` LangGraph orchestrator as uninspected. E-15 read it: two bounded critique loops with hard revision ceilings, reviewing against style guidelines rather than coverage, and structurally unable to trigger new research.

## Planner inputs

Concrete artifacts a planner would lift, traceable to document and finding.

**D-01, D-02, scope derivation**
- PICOC and Population-Concept-Context facet templates as the seed for spec-spanning axes (B-2, B-4, B-8).
- KAOS HOW and WHY goal refinement as the procedure that turns a spec's own sections into a tree (B-11, B-12).
- IEEE 29148's completeness facets, functional, quality, interface, constraints, context, as the coverage checklist (B-14).
- LangChain's legacy `report_planner_instructions` as the one working precedent for an upfront document-derived axis list (B-26).
- Gemini's `collaborative_planning` flag and `previous_interaction_id` as the only vendor precedent for a human-editable plan across turns (B-30).
- Evidence that unstructured elicitation under-covers whole categories: non-functional requirements were 8.4% of elicited requirements without an explicit model (B-15).

**D-03, curated sources**
- F's 34-source comparison matrix with tested access status, key requirement, full-text reach, and redistribution stance (F Taxonomy).
- Keyless and tested working: Crossref, OpenAlex, CORE, Unpaywall, PubMed and PMC, bioRxiv and medRxiv, HAL, Hugging Face hub, GitLab REST, PyPI, npm, crates.io with a User-Agent (F-5 to F-9, F-21, F-23, F-26, F-27, F-37, F-39).
- Dead or unusable: CiteSeerX redirects to a Wayback 404, Papers with Code redirects to Hugging Face, PMC's `oa.fcgi` retired, Google Scholar has no API and disallows the path, ResearchGate bans automated access, SSRN reserves text-mining rights (F-12, F-25, F-21, F-17, F-28, F-22).
- Garousi's eight-criterion quality instrument, the only scored reliability rubric found in the literature (A-32).
- Garousi's three-tier outlet classification and seven-question grey-literature inclusion checklist, the mechanism that admits a specialist blog while rejecting a blog pile (A-30, A-31, A-33).
- SIFT and lateral reading as the mechanizable move: leave the page and corroborate, which maps onto an existing WebSearch call (C-2, C-3).
- `gh api repos/{owner}/{repo}` and `gh api orgs/{org}` as the mechanical owner check D-03 asks for (C-9).
- Preprint marking convention: tag `[Preprint]` with version and date, and check whether a peer-reviewed version supersedes it (C-7).
- STORM's `is_valid_source` seam as the architectural shape for a pluggable predicate, subject to X1 (C-12).
- The three curation mechanisms in the wild, venue routing, domain list, LLM prompt, and the fact that no system combines them (C-16, C Taxonomy).
- Compass's `papers` skill has no reliability filter today (C-15, F-1).

**D-04, code over documentation**
- Per-ecosystem canonical source lookup, with Go and NuGet the only version-exact paths (D-1 to D-10, D Taxonomy).
- `deps.dev` as the single cross-ecosystem source-repository lookup covering six ecosystems (D-9).
- Type stubs, `.pyi` via `stubgen` and `.d.ts` via `tsc --declaration`, as the mechanical way to get the API surface without the bodies (D-12).
- Read the test suite as currently-true documentation (D-16); characterization tests for behavior that is documented nowhere (D-15).
- The doc-drift evidence base that justifies the mandate (D-17, D-18, D-19, D-20, D-21).
- Serena's reading order: `get_symbols_overview`, then `find_symbol` on a name path, then `find_referencing_symbols` (D-25, D-23, D-24).
- The cheap-breadth-then-expensive-depth pattern, converged on independently by Aider's PageRank plus token budget, Serena's overview-then-detail, and Compass's own locator and analyzer split (D-30, D-39, D-40).
- `git clone` as the zero-quota API, and GitHub code search as the constrained one: auth required, 10 requests per minute, 1,000-result cap, legacy engine (F-35, F-36, D-38).

**D-05, research spawning research**
- The three stop-mechanism families, with the note that budget and self-report are layered and structural detection never stands alone (E Taxonomy).
- Co-STORM's Moderator scoring never-cited, non-overlapping snippets into new questions, the only executable structural gap detector found (E-17).
- Co-STORM's stagnation guard: force a moderator turn after three consecutive non-questioning turns (E-18).
- LangChain's `ResearchComplete` tool backstopped by three independent numeric ceilings, the most code-legible stop architecture surveyed (E-19, E-22).
- The prompt-level redundancy heuristic, stop when the last two searches returned similar information (E-21).
- Anthropic's effort-scaling table: one agent and 3 to 10 tool calls for fact-finding, 2 to 4 subagents for comparisons, 10 or more for complex research (E-26).
- The failure modes that bound iteration: void turns, echo trap, cumulative noise, and Anthropic's four named early failures (E-8, E-9, E-27).
- Wohlin's zero-new-results stopping rule as the human analogue of a coverage-verified halt, implemented by no agent surveyed (A-26, E-4).

**D-06, methodology**
- The eight-methodology catalog with steps, inputs, output, fit, and author-named failure modes, ready to ship as the chooser's menu (A, findings 1 to 43, A Taxonomy).
- The `obsidian` skill's existing four-approach research table is the file the catalog replaces (D-44).
- The hazard to encode: mapping studies instruct the agent to skip quality assessment, which is the check D-03 requires (A-22).
- PRISMA must be paired with a conduct method, never used as one (A-16), subject to P1.
- Protocol registration formats if research protocols get locked before running: PROSPERO's field set, OSF's template, and the standalone software-engineering protocol shape (A-44, A-45, A-46).
- Kitchenham's "light" solo-researcher SLR, which keeps every step but drops dual-reviewer cross-checking, as the single-agent adaptation precedent (A-14).
- Cochrane's bounded abbreviations for rapid review: dual screening on at least 20% of abstracts, single extraction with second-reviewer verification (A-7).

**D-07, session plugins**
- `claude mcp list` and `claude plugin list --json` as the discovery step, absent from both research skills today (D-41, D-42, D-43).
- Zoekt's query syntax and the four host-provided indexes in this session, with `OR` invalid and `AND` file-level (D-36, D-37).

## Contradicts existing vault research

[[research/pipeline/RESEARCH-scientific-method-in-compass]] (2026-06-10) holds up and gains evidence rather than losing it. Two of its findings are now extended:

- Its finding 2 records that Compass's research stage offers four named approaches. That remains true of the shipped skill and is now a shortfall against D-06 rather than a neutral fact (A Taxonomy, D-44).
- Its recommendations 1 through 3 ask for pre-registration of a hypothesis frozen before build. A-44 through A-47 supply the concrete formats that recommendation had no source for: PROSPERO's field set, OSF's preregistration template, and standalone software-engineering protocol documents.

Its finding that Compass's convergence matrix is majority voting rather than Bayesian updating applies to this document too. Agreement counts here are counts, not posteriors.

CONVERGENCE: HIGH
