---
title: "Review: SPEC-023 Research Consolidation"
type: research
status: draft
confidence: high
area: methodology
tags: [research, pipeline, methodology, sources, scope, review, convergence, consolidation, acm, completeness-scoring, human-priority]
created: 2026-09-13
updated: 2026-09-13
git_branch: "master"
git_commit: "50a2896"
author: "reviewer"
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
summary: "convergence matrix over two rounds of research into SPEC-023's decisions D-01 to D-07: 35 converged claims, both round-one divergences now resolved, every round-one blocking gap closed, and the concrete inputs a planner would lift, including the finding that no scriptable path to ACM exists and no precedent anywhere scores a research report against a spec"
---

# Review: SPEC-023 Research Consolidation

## Inputs

Six agents. Question: does research cover the whole spec, from curated sources, until the plan is fully informed, per [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]?

| Handle | Document | Decisions served | Round two adds |
|---|---|---|---|
| **A** | [[research/pipeline/RESEARCH-research-methodologies-catalog]] | D-06 | DESMET; the protocol-artifact owner check |
| **B** | [[research/pipeline/RESEARCH-scope-derivation-from-a-spec]] | D-01, D-02, D-05, D-06 | how a human's question takes priority |
| **C** | [[research/pipeline/RESEARCH-source-reliability-criteria]] | D-03 | none |
| **D** | [[research/pipeline/RESEARCH-code-as-primary-source]] | D-04, D-07 | the full plugin and MCP inventory |
| **E** | [[research/pipeline/RESEARCH-research-spawning-research]] | D-05 | completeness scorers; Co-STORM warm start |
| **F** | [[research/pipeline/RESEARCH-source-inventory]] | D-03, D-07 | ACM access; reachability from the deployment machine |

A dash means the document did not address the claim. Agreement is counted over the documents that addressed it, not over all six, so `2/2` means both documents that took a position took the same one.

Round two ran on 2026-09-13 against the eight gaps this review tagged as blocking. Five of the six documents carry a `## Follow-up Research - 2026-09-13` section, and claims sourced from it are marked `r2`. Round two closed every blocking gap, resolved both divergences, and raised two new blocking gaps, both about ACM.

## Convergence Summary

| Category | Count | Claims |
|---|---|---|
| Converged | 35 | C1-C35 below |
| Partial | 2 | P1 (PRISMA used as conduct guidance), P2 (GPT-Researcher deep-research defaults) |
| Divergent, resolved | 2 | X1 (STORM's source filter: dead code), X2 (GitHub stars as an owner signal) |
| Divergent, open | 0 | |

## Matrix

| # | Claim | A | B | C | D | E | F | Agreement |
|---|---|---|---|---|---|---|---|---|
| C1 | Scope derives from facets, document structure, or found evidence, never a standing question list | YES (high) | YES (high) | - | - | - | - | 2/2 |
| C2 | Broad-versus-narrow question scope is settled by methodology choice, not by rule | YES (high) | YES (high) | - | - | - | - | 2/2 |
| C3 | Upfront document-derived axis lists exist in one precedent, which its authors deprecated | - | YES (high) | - | - | YES (high) | - | 2/2 |
| C4 | No off-the-shelf domain allowlist is usable as shipped; the only complete one excludes arXiv | - | - | YES (high) | - | - | YES (high) | 2/2 |
| C5 | No agentic system computes a reliability score; each is a prompt, a venue route, or a list | - | YES (high) | YES (med) | - | - | - | 2/2 |
| C6 | ACM Digital Library, named first in D-03, has no public API and no agent precedent | YES (high) | - | YES (high) | - | - | YES (high, r2) | 3/3 |
| C7 | A specialist blog is admitted by a scored instrument, not a blanket rule | YES (high) | - | YES (high) | - | - | - | 2/2 |
| C8 | Documentation drifts from code, with a large empirical evidence base | - | - | - | YES (high) | - | - | 1/1 |
| C9 | Every document that read code found a fresh doc-versus-code discrepancy in this run | YES | YES | YES | YES | YES | YES | 6/6 |
| C10 | Version-to-source matching is heuristic everywhere except Go and NuGet Source Link | - | - | - | YES (high) | - | - | 1/1 |
| C11 | `git clone` is the zero-quota, full-fidelity access path to any code host | - | - | - | YES (high) | - | YES (high) | 2/2 |
| C12 | Stop mechanisms fall into three families; budget and self-report are layered, structural detection is rare | - | YES (high) | - | - | YES (high) | - | 2/2 |
| C13 | Co-STORM is the only system with executable, evidence-triggered scope growth | - | YES (high) | - | - | YES (high) | - | 2/2 |
| C14 | No system uses a coverage metric as an in-loop stop condition | - | - | - | - | YES (high) | - | 1/1 |
| C15 | Unbounded iteration has its own named failure modes | YES (high) | - | - | - | YES (high) | - | 2/2 |
| C16 | Methodologies each state their own fit, but no source gives a decision procedure | YES (high) | YES (med) | - | - | - | - | 2/2 |
| C17 | Neither Compass research skill has a plugin or MCP discovery step | - | - | - | YES (high, r2) | - | YES (high) | 2/2 |
| C18 | Serena is connected but was never exercised; its surface is known only from source | - | - | - | YES (high, r2) | - | YES (low) | 2/2 |
| C19 | Every mechanism giving a human's input priority is structural, never a weight or score | - | YES (high, r2) | - | - | - | - | 1/1 |
| C20 | Co-STORM's human turn bypasses the turn policy and becomes the panel's focus string | - | YES (high, r2) | - | - | - | - | 1/1 |
| C21 | GPT-Researcher has a human plan-review loop, bounded at three revisions | - | YES (high, r2) | - | - | - | - | 1/1 |
| C22 | Vendor human-steering is a gate or a queue; no vendor documents a merge rule | - | YES (high, r2) | - | - | - | - | 1/1 |
| C23 | The mixed-initiative literature gives the user a standing override and reverts initiative | - | YES (high, r2) | - | - | - | - | 1/1 |
| C24 | ACM's 2026 open access means free to read in a browser, not free to script | - | - | - | - | - | YES (med-high, r2) | 1/1 |
| C25 | Aggregators flag ACM works gold open access but supply only the walled DOI | - | - | - | - | - | YES (high, r2) | 1/1 |
| C26 | Crossref indexes every ACM work but carries abstracts for about one in six | - | - | - | - | - | YES (high, r2) | 1/1 |
| C27 | A status-code check misreports reachability; OpenReview v2 is open and v1 is not | - | - | - | - | - | YES (high, r2) | 1/1 |
| C28 | A runnable post-hoc coverage scorer exists, in information-retrieval evaluation rather than deep research | - | - | - | - | YES (high, r2) | - | 1/1 |
| C29 | No source anywhere scores a research report against a requirements document | - | - | - | - | YES (high, r2) | - | 1/1 |
| C30 | LLatrieval and ReSP verify sufficiency per sub-question, never per document | - | - | - | - | YES (high, r2) | - | 1/1 |
| C31 | Co-STORM's warm start accepts only a bare topic string at every stage | - | - | - | - | YES (high, r2) | - | 1/1 |
| C32 | DESMET is the canonical peer-reviewed software-engineering evaluation methodology | YES (high, r2) | - | - | - | - | - | 1/1 |
| C33 | Multi-criteria decision analysis has real software-engineering venue traction | YES (high, r2) | - | - | - | - | - | 1/1 |
| C34 | A paper-artifact repository's owner check runs on identity, not community health | YES (high, r2) | - | - | - | - | - | 1/1 |
| C35 | Six distinct plugins, four research-capable; five MCP servers, two research surfaces | - | - | - | YES (high, r2) | - | - | 1/1 |
| P1 | PRISMA is a reporting standard and supplies no conduct steps | YES (high) | used as conduct (med-high) | - | - | - | - | 1/2 |
| P2 | GPT-Researcher's deep-research breadth default is 3 | - | YES (high) | - | - | two sources disagree (high) | - | 1/2 |
| X1 | STORM's `is_valid_source` predicate is overridden in shipped code | - | NO (high) | YES (high) | - | - | - | resolved: NO |
| X2 | Star count is a sound repository-reliability signal | - | - | NO (high) | - | used as lead evidence | - | resolved: NO |

## Converged

Numbering follows the matrix; the prose is grouped by topic, so a round-two claim sits beside the round-one claim it extends rather than at the end.

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

Round two tested every route and confirms the claim at a stronger level (F-40 to F-49). The one GitHub repository matching "ACM digital library API" is a zero-star cataloging exercise, not client code (F-40). ACM's own Digital Library policy names "using scripts, spiders or other robotic activity to automatically download articles or harvest metadata" as a serious Terms-of-Use violation carrying loss of an institution's download rights, with a separate institutional text-and-data-mining clause permitting computational analysis case by case through `permissions@acm.org`, and no self-service enrollment path (F-41). Every acm.org-family domain returns HTTP 403 with a Cloudflare challenge to any non-browser request, tested across an abstract page, a PDF path, a citation export, and three policy pages, with both a plain and a spoofed Googlebot user agent; `dl.acm.org/robots.txt` does not disallow `/doi/`, so the block is CDN-layer bot fingerprinting rather than a robots directive (F-42).
F-49 states the synthesis: no path found gives an agent unattended, scriptable, full-text access to ACM content, and every route bottoms out in a browser check or a human-mediated credential flow. This is a harder wall than D-03's other two named sources, since arXiv and GitHub have no equivalent challenge on their content-serving paths.

**C24. ACM's 2026 open access means free to read in a browser, not free to script.**
All ACM journals, proceedings, and magazines, over 600,000 articles, became open access on 2026-01-01 under the ACM Open model, funded by institutional and author-side charges (F-43). This removes the cost barrier round one described and leaves the access-mechanism barrier untouched: F-42 hit the same Cloudflare wall on a DOI that was already gold open access in 2021.

**C25. Aggregators flag ACM works gold open access but supply only the walled DOI.**
Tested against a 2021 CHI paper: OpenAlex returns full metadata and `oa_status: gold`; Semantic Scholar returns the abstract and `openAccessPdf.status: GOLD`; Unpaywall returns `is_oa: true` with a CC-BY-NC-SA license and `url_for_pdf: null`. All three supply the bare DOI as the only URL, and following it lands on the 403 (F-45, F-46). The open-access flag is accurate as a rights statement and useless as a fetch instruction.

**C26. Crossref indexes every ACM work but carries abstracts for about one in six.**
766,416 works under the 10.1145 prefix, of which 120,573 have an abstract, about 15.7% (F-44). Crossref is a complete ACM metadata index and not a usable ACM abstract source.

**C27. A status-code check misreports reachability.**
Re-tested from the human's own workstation, the network Compass deploys on: DBLP and Internet Archive Scholar both return HTTP 200 with `text/html` to a JSON API call, serving a challenge page titled "Making sure you're not a bot!" and "Session Verification" respectively. Fatcat never completes a TCP handshake (F-50). A shipped source list validated by status code alone would carry all three as healthy. OpenReview splits: `api2.openreview.net` returns JSON, `api.openreview.net` returns 403, so a shipped list must name the v2 host (F-51). Crossref, OpenAlex, and Unpaywall answer keyless; Semantic Scholar answered one anonymous call and returned 429 on the next, so unattended use needs its free key (F-52).

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
Round two bounds how far the precedent transfers: see C31. The growth mechanism is real, and the entry point that seeds it cannot take a spec.

**C14. No system uses a coverage metric as an in-loop stop condition.**
"Key points coverage" exists only as post-hoc, LLM-judged report evaluation (E-10, arXiv:2512.02038 §5.2.2). A completeness check applied to a finished research document is unbuilt anywhere surveyed.
Round two holds the in-loop claim and overturns the "unbuilt anywhere" reading: the mechanism exists as shipped code in a different literature (C28). Round two also corrects the citation round one carried: the reference for "key points coverage" is [379], not [378], which round one mistranscribed from the PDF's line-wrapped text. [378] is BrowseComp, an unrelated browsing benchmark (E r2 preamble).

**C28. A runnable post-hoc coverage scorer exists, in information-retrieval evaluation rather than deep research.**
AutoNuggetizer, from Jimmy Lin's Castorini group at Waterloo, refactors the TREC 2003 nugget methodology into three LLM stages: a creator extracts atomic nuggets of 1 to 12 words from source documents against a query, a scorer labels each `vital` or `okay`, an assigner labels each `support`, `partial_support`, or `not_support` against a candidate passage. Its primary metric, Strict Vital Recall, is a coverage-against-ground-truth score computed on finished text (E-32, `src/nuggetizer/core/metrics.py:14-47`). Apache-2.0, last pushed 2026-04-19, owner checked by organizational affiliation per X2.
Four other families were profiled and each scores against something a spec is not: RACE needs a human-written reference report (E-35), ALCE's claim recall decomposes a gold answer (E-36), RAGAS's `context_recall` scores retrieval rather than the report (E-37), FActScore measures precision with no recall counterpart (E-38), and PROXYQA tests whether an evaluator can answer curated questions using only the report (E-40).

**C29. No source anywhere scores a research report against a requirements document.**
Every completeness mechanism found scores against a fixed rubric, a reference report, nuggets pre-extracted from source documents, or an evaluator's ability to answer curated questions. None takes a requirements-style document as the ground-truth side (E-41). The nearest bridge is E-34's mapping, which feeds a spec's Problem as the query and its Decisions and Needs as the documents, reads off `strict_vital_score`, and is an inference from nuggetizer's own data contract rather than a technique any source states. Two USPTO patents claim this exact shape and are excluded under D-03 as non-academic, non-code sources.

**C30. LLatrieval and ReSP verify sufficiency per sub-question, never per document.**
Round one's gap named this family as the place to look next. Round two read both papers directly and found the granularity wrong: LLatrieval's loop asks whether a retrieval result supports one given question, ReSP's insufficiency check is scoped to the current sub-question, and neither has a unit larger than a question-answer pair (E-31). A round-one recommendation, checked and retired.

**C31. Co-STORM's warm start accepts only a bare topic string at every stage.**
Read in full from `warmstart_hierarchical_chat.py` (409 lines) and `expert_generation.py`. Stage 1 issues one literal query, `f"Background information about {topic}"`. Stage 2 generates personas from topic plus one background paragraph, with no slot for a focus or section list. Stage 3's question generator never sees the background paragraph or any document. Stage 4 drafts an outline from the topic string alone, using the model's parametric knowledge with zero retrieved context, then reconciles it against the discussion transcript in a second call. Stage 5 parses that outline by counting leading `#` characters (E-42). The budget is three fixed constants: 3 experts, 2 turns each, 3 threads, regardless of topic breadth (E-43).
Every input field is typed as free text, so no stage has a slot for a structured document (E-45). E-46 traces what a spec would touch, and names the trap: stage 4 generates a wiki-shaped outline from a topic and then reconciles it against evidence, which is the two-pass shape C3 already flags as the pattern SPEC-023 D-01 asks Compass not to replicate.

**C15. Unbounded iteration has its own named failure modes.**
Extra turns introduce cumulative noise and error propagation (E-8); Anthropic names spawning 50 subagents for simple queries and endless scouring for nonexistent sources as early failures (E-27). Rapid review is the literature's sanctioned abbreviation of the same six SLR steps, with 50 distinct combinations found in one 84-paper scan (A-5).

**C16. No source gives a methodology decision procedure.**
Each paper states its own fit condition in isolation; a chooser must be authored by synthesizing those statements (A Gaps, B-10).

**C17. Neither Compass research skill has a plugin or MCP discovery step.**
`claude mcp list` and `claude plugin list --json` both enumerate session capabilities mechanically, and neither `research/SKILL.md` nor `research-codebase/SKILL.md` calls either (D-41, D-42, D-43). Compass ships no code-search skill of its own; the zoekt indexes in this session are host-provided (F-2, D-37). Round two confirms by command: `grep -rn "claude mcp list\|claude plugin list" plugin/` returns no matches (D-47).

**C35. Six distinct plugins, four research-capable; five MCP servers, two research surfaces.**
`claude plugin list --json` returns twelve entries because the same plugin registers separately at user, project, and local scope. Deduplicated: four zoekt code-search indexes over engine source, a Rust language server, and two disabled plugins. An agent enumerating must dedupe on name and read `enabled` per scope (D-45). `claude mcp list` reports five connected servers, of which `serena` and `headroom` serve research and three Google connectors do not (D-46).

**C18. Serena is connected but was never exercised.**
Its tools were not in either researcher's tool list (D Gaps, F-3), and round two confirms only that the server is connected and healthy (D-46), not that its tool surface behaves as read. D-22 notes the schema is generated from Python introspection at runtime, so the source is authoritative about the surface even unexercised.

**C19. Every mechanism giving a human's input priority is structural, never a weight or score.**
Six families found across code, vendor documentation, the mixed-initiative literature, and requirements engineering: a turn-taking gate, an unconditional bypass insertion, recency in what the model conditions on, queue-and-prepend, an assigned governance role, and disclosure without precedence (B r2 Taxonomy). None implements D-02's "weigh more" as an actual weight. Requirements-engineering practice locates authority in a named role rather than in a requirement's provenance: MoSCoW's Business Visionary determines final priorities regardless of who stated a requirement (B-54), and no located source ties provenance to priority (B-55, B-58). Systematic-review protocol practice gives disclosure without precedence: PROSPERO's revision notes are dated, public, and source-agnostic, with no provision distinguishing a stakeholder-driven amendment from any other (B-60, B-62), and Cochrane leaves conflicting stakeholder priorities to the review team's judgment (B-63).

**C20. Co-STORM's human turn bypasses the turn policy and becomes the panel's focus string.**
`CoStormRunner.step(user_utterance=...)` appends the human's text straight to conversation history and returns, never calling `get_next_turn_policy` or any agent's generation; no model judges whether to accept it (B-32). On the next turn the human's own words become the literal `focus` string passed to expert regeneration, rebuilding the whole panel around what the human asked (B-33). Human and system questions carry the identical type tag, so priority is not a label (B-34); it is achieved by exempting the human path from the throttle that delays the system's own questions by three consecutive turns (B-35). This is the one open-source precedent matching the override concept in shape.

**C21. GPT-Researcher has a human plan-review loop, bounded at three revisions.**
`HumanAgent.review_plan()` presents the section outline and blocks on a reply; any non-empty non-approval reply routes the plan back for regeneration, until `max_plan_revisions` is exceeded and a typed exception fires (B-36, B-37). Cross-document: this lives in the same `multi_agents/` directory E-15 read, and E-15 reported only the style-guideline critique loop. Round one recorded that directory as fully covered; it was not.

**C22. Vendor human-steering is a gate or a queue, and no vendor documents a merge rule.**
Gemini's `collaborative_planning` makes the agent return its plan and wait, proceeding only on confirmation, which is binary rather than a merge (B-39), and neither the Interactions API reference nor the Deep Research guide states how a user's edit reconciles with the agent's own sub-questions (B-40). OpenAI documents `response.steer` with an explicit acknowledgement that "Acceptance means input queued, not that the model has acted on it," with in-flight tool calls finishing first and already-sent output unrewritable (B-41); this shipped around November 2025, making mid-run correction a retrofit rather than a founding property (B-42). Perplexity documents user-facing behavior only (B-43). An independent 2026 paper frames the category's default as one-shot scoping followed by a long autonomous run with little mid-process control (B-44).
This narrows round one's C3-adjacent claim rather than reversing it: B-30 called Gemini the only vendor precedent for a human-editable plan, and the mechanism turns out to be a gate with no documented editing or merging semantics.

**C23. The mixed-initiative literature gives the user a standing override and reverts initiative.**
Horvitz's founding principles let the user directly invoke or terminate the service, overriding the system's own inference (B-45). Radlinski and Craswell's formal model states that a later user utterance "allows the user to refer to a previous statement to override it specifically," conditioned only on correct interpretation and not on any confidence comparison (B-46), and gives the user an unstructured free-text action at every turn regardless of what the system just asked for (B-47). Allen, Guinn, and Horvitz treat system-taken initiative as a temporary loan after which "initiative reverts to the user" (B-48). TREC CAsT treats the human-adjudicated utterance as canonical ground truth and scores system rewrites against it, with automatic rewrites lagging by 26% in median (B-49).
B's own Contradictions keeps a distinction a planner must not collapse: B-52 found no universal dominance of user-initiated over system-initiated turns for outcome quality, which is about which move is better when there is no conflict, not about who wins when there is one.

**C32. DESMET is the canonical peer-reviewed software-engineering evaluation methodology.**
Kitchenham, Linkman and Law, "DESMET: a methodology for evaluating software engineering methods and tools," Computing and Control Engineering Journal 8(3), 1997, DOI 10.1049/cce:19970304, peer-reviewed, 258 citations with 35 highly influential, with a Keele technical report and a twelve-part ACM SIGSOFT series carrying the detailed procedure (A-48). It names nine evaluation types with selection criteria for picking among them: quantitative experiment, case study and survey; feature analysis in screening, case-study, experiment and survey modes; qualitative effects analysis; and benchmarking (A-49). Its authors name their own fit boundary, found by applying it: the rigorous modes fail when no valid control or treatment can be identified or the technology is too new for a survey, leaving case-study feature analysis (A-50), and a 2021 application notes it assumes a controllable development process (A-51). Applications span 24 years, so it is in standing use rather than archival (A-52).
A second, independent peer-reviewed line answers the narrower software-package question: Jadhav and Sonar's systematic review of package evaluation and selection, 64 papers screened (A-53). A notes no single source unifies the two questions, so the catalog carries them as two related non-identical answers rather than one.

**C33. Multi-criteria decision analysis has real software-engineering venue traction.**
Direct analytic-hierarchy-process applications exist for project-management tool selection, agile-practice prioritization across four organizations and forty professionals, scientific-software ranking, and effort-estimation-model selection, with the method's own named limitation that pairwise-comparison burden scales as k(n squared minus n) over 2 (A-54). This raises A-37 from medium to high.

**C34. A paper-artifact repository's owner check runs on identity, not community health.**
The `sraedler` account was confirmed as the paper's own submitting author through sources independent of GitHub: a Google Scholar profile with a verified institutional email, a university personnel page, an ORCID, and a ResearchGate profile listing the same paper (A-60). The repository's community-health signals are uniformly weak, single contributor, two commits, zero stars, no activity since 2024 (A-61), and A names why that is the wrong axis: bus factor and cadence are designed for community-maintained libraries, while a single-author paper artifact's reliability question is whether the author is who they claim (A-61).
Round two applied this review's own X2 finding by name, in two independent places (A-61, E-32), weighting organizational affiliation over star count.

### Observed: the run did not follow its own D-06

Five of six documents declared technology landscape or comparative evaluation as their methodology (A, B, D, E, F); one declared a scoping review (C). Two of the five cite the `obsidian` skill's existing four-approach table as the menu they chose from (B and E Methodology), and that table has four entries against the catalog's eight plus protocol registration (D-44, A Taxonomy).

Two consequences the authors could not see:

- The methodology every document chose is the one A rates as least grounded: it rests on one company's public process plus general multi-criteria decision analysis theory, with no canonical peer-reviewed software-engineering paper behind it (A Gaps), and its own publishers call it subjective, opinion-based, and recency-biased rather than a systematic survey (A-36).
- D-06 says agents choose from the methodologies that research found. In this run they chose from what Compass already shipped, because the catalog was being written in parallel. The mechanism D-06 describes has not yet been exercised.

**Lowered by round two.** The first consequence no longer holds as written. DESMET is that canonical peer-reviewed source (C32), so the methodology family five of six documents used is properly grounded after all, and A-37 rises from medium to high (C33). What survives is narrower and still real:

- The specific artifact those documents modeled themselves on, per-item profiling in the ThoughtWorks Radar style, remains non-systematic by its publisher's own words. Round two adds the Radar's own FAQ, that it "represents a reasonable sample but no attempt is made to be a comprehensive survey of the market at large," its published subtitle "An opinionated guide to technology frontiers," and its own caution that it "should not be confused with a technology lifecycle assessment tool" (A-55). None of the five declared DESMET or ran its nine-type selection step.
- The second consequence stands unchanged. The choosing mechanism D-06 describes has still not been exercised, and the table the agents chose from still has four entries.

### Observed: methodology choice can silently drop D-03

Mapping studies deliberately skip quality assessment while SLRs mandate it, which A flags as a by-design depth difference rather than a disagreement (A-22, A Contradictions). Against the spec, it is a live hazard: SPEC-023's third success criterion requires every finding to name a source whose reliability was checked. An agent that picks a mapping study is following a methodology whose authors tell it to skip exactly that step.

### Observed: the run partially met the spec's own third success criterion

Reliability checking was recorded unevenly. C and F check and record it throughout, including live access tests. A records per-finding caveats where a primary text was not parsed, and A-47 flags its own unchecked repository owner explicitly against D-03. E checked repositories before cloning but led with the signal C rates weakest (see X2). No document addresses where or in what form the reliability check gets recorded in a research document.

Round two closed the gap in practice without closing it in the template. A-60 and E-32 each record an owner check inline with the finding it supports, naming the check route and the independent corroborating sources, and A-61 records why the unfavourable signals do not apply. That is a worked format, arrived at twice independently, and still nothing in Compass prescribes it.

## Partial

**P1. PRISMA supplies no conduct steps.** 1 of 2.
- A's position (high): PRISMA states it is "not intended to guide systematic review conduct"; an agent treating it as the methodology would have no steps to follow and must pair it with a conduct method (A-16, PMC8008539 Limitations).
- B's practice (medium-high): B-8 lifts the Population-Concept-Context framing from PRISMA-ScR item 4 as scoping-question guidance, which is question framing taken from a reporting checklist.
- Likely explanation: PRISMA-ScR item 4 does prescribe how an objective is framed, so the boundary A draws is real at the level of the whole document and blurry at the level of individual items. Whether a Compass agent may cite a reporting checklist for conduct guidance is unresolved.

**P2. GPT-Researcher's deep-research breadth default.** 1 of 2.
- B-18 (high): `DEEP_RESEARCH_BREADTH: 3` from the shipped config.
- E-12 (high): the code-level `getattr` fallback says 4 while the shipped config says 3, and E names the disagreement.
- E is the more precise read. Not a conflict about behavior, and it is itself an instance of C9.

## Divergent, both resolved

**X1. Is STORM's `is_valid_source` predicate wired up in shipped code?** RESOLVED: no. Position B holds. Split 1/1 at round one, both high confidence, same repository.
- Position A (C-12): yes. The wiki-generation pipeline supplies a concrete predicate, `is_valid_wikipedia_source` at `knowledge_storm/storm_wiki/modules/retriever.py:225-233`, checking netloc against three sets copied from Wikipedia's perennial-sources list (`retriever.py:11-222`).
- Position B (B-23): no. "Every retrieval module accepts an `is_valid_source` callable that defaults to `lambda x: True` and is never overridden in the shipped code," citing `knowledge_storm/rm.py:14-30` and `knowledge_curation.py:182-218`, and calls the `TopicExpert` docstring's filtering step a documented intent the implementation does not carry out.
- What might explain it: the two read different modules. C read the `storm_wiki` retriever wrapper where the predicate is defined; B read the generic `rm.py` retrievers and the knowledge-curation path. The predicate can exist and still never reach the retriever the curation path constructs. Unresolved by either document, and load-bearing: C treats this as the one real reliability taxonomy in the wild, and B treats it as the cautionary example of docs outrunning code.
- Resolved by command, 2026-09-13: `grep -rn "is_valid_source\|is_valid_wikipedia_source" --include=*.py` over the cloned repository finds `is_valid_wikipedia_source` only at its definition (`knowledge_storm/storm_wiki/modules/retriever.py:225`) and no call site passes `is_valid_source=` to any retriever. The predicate is dead code; Position B holds. The seam (C-12) still exists as an unused constructor parameter, and the shipped list is the cautionary example B describes.

Consequence for C4: the Wikipedia-derived list STORM ships is still the only complete domain taxonomy found in the wild, and it was never enforcing anything. C4's warning about reusing it stands; the claim that a working implementation exists to copy does not.

**X2. Is star count a sound repository-reliability signal?** RESOLVED by adoption, not by new evidence: both round-two owner checks took position A. Split 1/1 at round one, a contradiction in practice rather than in prose.
- Position A (C-8, high): no. A Carnegie Mellon study at ICSE 2026 found roughly 6 million fake stars across 18,617 repositories from about 301,000 accounts, with AI and LLM repositories the largest non-malicious recipient category. Stars measure past popularity, not current health. The signals that carry weight are maintainer concentration, commit and release cadence, issue responsiveness, and organization domain verification (C-9).
- Position B (E Methodology, applied): E checked repository reliability before cloning and led with star counts, 29,430 for `assafelovic/gpt-researcher`, 31,299 for `stanford-oval/storm`, 12,679 for `langchain-ai/open_deep_research`, alongside maintainer activity, last-push date, and organization type.
- E's secondary signals are exactly C-9's list, so the disagreement is about what leads. It matters because D-03's owner check is the rule being operationalized, and the two documents would produce different check procedures.
- Resolved in round two: A-61 and E-32 each cite this finding by name and weight organizational affiliation over star count, one recording 0 stars and one recording 29 while passing both repositories on other grounds. A-61 adds the distinction that settles it: community-health metrics answer "will this survive its maintainer leaving," which is the wrong question for a single-author paper artifact, where the question is "is this really the author." The two check procedures are now one, selected by artifact class rather than by preference.

## Gaps

Merged from all six documents across both rounds, deduplicated. Tagged for the human's D-05 call.

### Closed in round two

All eight gaps round one tagged as blocking are closed. Two closed with a negative answer, which is a result rather than a failure.

| Round-one gap | Closed by |
|---|---|
| ACM Digital Library access mechanics | F-40 to F-49. Negative answer: no API, a Terms-of-Use ban on scripted harvesting, and a CDN challenge on every domain regardless of open-access status. |
| Technology-landscape methodology lacks a canonical source | A-48. DESMET, peer-reviewed, 258 citations, with a nine-type selection taxonomy (A-49) and 24 years of applications (A-52). |
| Live reachability of DBLP, OpenReview, Internet Archive Scholar, Fatcat | F-50, F-51. Re-tested from the deployment machine: DBLP and Internet Archive Scholar serve challenge pages under HTTP 200, Fatcat never connects, OpenReview v2 works and v1 does not. |
| Complete enumeration of session plugins and MCP servers | D-45, D-46, D-47. Six distinct plugins from twelve scope-duplicated entries, five MCP servers, and no Compass skill calling either command. |
| A live completeness or coverage check for finished research | E-32 found one built and maintained (AutoNuggetizer), E-41 found none that scores against a requirements document, and E-31 retired the family round one nominated. |
| Co-STORM warm-start prompt templates | E-42 to E-46. Read in full: five stages, every input a bare string, a three-constant budget, and a mapping traced for what a spec would touch. |
| Protocol-registration findings resting on secondary description | A-56 to A-61. Zapata re-fetched in full and raised to high, the MDE/AI artifact's owner checked and passing, PROSPERO's scope refined without changing the core claim. |
| How a human's injected question outranks a spec's listed questions | B-32 to B-64, four parallel passes. Answer: through one of six structural mechanisms, never a weight. |

Additionally closed: round one listed GPT-Researcher's `multi_agents/` internal iteration limits as non-blocking. B-37 supplies one of them, `max_plan_revisions` defaulting to 3.

### Still open: needs another research pass before planning

Both are new in round two, both about ACM, and both now intersect facts the human supplied.

| Gap | Why |
|---|---|
| Whether ACM's text-and-data-mining clause or a direct request to `permissions@acm.org` would grant a scriptable exception (F r2 Gaps) | Untested, because it requires sending an actual outbound request under a named institution or project, which no research pass may do unasked. The human's ACM membership changes who could send it. |
| Whether ACM's Basic-tier free PDF download is rate-limited or CAPTCHA-gated for a real logged-out or logged-in browser session (F r2 Gaps) | F-42 tested curl, not a browser. F's tooling could not run a browser session; this session has one. See the two human-supplied facts under D-03 planner inputs. |
| Resolved 2026-09-13 by a live browser read (F-53) | The Claude in Chrome extension reached the full ACM article page, logged out, after the Cloudflare interstitial cleared on its own. Article pages are readable per page through the browser; the PDF path and any rate limit under sustained reading remain untested, and the terms' harvesting ban from F-49 still applies to bulk use. Planning can proceed on the article-page path. |

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
| OpenAI launch blog returned 403 (B); OpenAI and Perplexity parallel-agent architecture unstated (B); Gemini and Perplexity not covered for stopping (E) | Neither vendor publishes inspectable code, so a further pass yields vendor prose either way (E-29). Round two covered all three vendors for human steering (C22) and found the same ceiling: documented behavior, no documented internals. |
| smolagents domain filtering unchecked (B) | The weakest precedent in the set; no Need depends on it. |
| Serena not exercised live (D, F) | D read the source that generates the tool schema by introspection, so the surface is authoritative (D-22). Round two confirms the server is connected and healthy (D-46), which is not the same as exercising it. |
| The "25.5% of Python docstrings are inconsistent" statistic (D) | Untraceable to a primary source. Treat as do-not-cite; the drift case stands on D-17, D-18, D-19 at high confidence. |
| Private and internal package source conventions (D); `pattern-finder` not read (D) | Neither is load-bearing for any Need. |
| Saturation papers read via search summary (E) | Saturation enters the taxonomy as an analogue, not an adopted mechanism. |
| GPT-Researcher `multi_agents/` internal iteration limits (E) | Only matters if Compass adopts the bounded-revision pattern, which E-15 already shows cannot trigger new research. Partly closed in round two: B-37 supplies `max_plan_revisions`, default 3. |
| Brazil-specific legal status of shadow libraries (F) | Shadow libraries are not named in D-03 and no Need depends on them; the question only becomes load-bearing if the human elects to include them. |
| Unpaywall terms of service unread; crates.io crawler policy unretrievable; CORE's exact quota; no authenticated call against key-gated sources (F) | Operational details resolvable at ship time, each behind a decision the human has not yet made. |
| No successor to Gusenbauer and Haddaway evaluating the newer aggregators (F) | F searched and the paper does not appear to exist; another pass cannot find what is not there. F's live access tests are the available evidence. |
| Nuggetizer repurposed for spec-to-report scoring is untested (E r2) | E-34 infers the mapping from the code's data contract rather than running it. Per this project's own rule, an untested mechanism is a hypothesis that belongs in a plan as an experiment, not in another research pass. |
| RACE's scoring formula and RAGAS's metric set read via summary (E r2) | Neither is a candidate mechanism: RACE needs a reference report and RAGAS's only ground-truth metric scores retrieval, so exact formulas change nothing. |
| Phase III "AI Scientist" systems not checked for requirements-style input (E r2) | Out of scope by E's own framing, and C29 already establishes the absence across the Phase II literature that does address report evaluation. |
| No source states a comparative weight for a human-originated question (B r2) | Searched across four families and came up empty. The answer is that D-02's "weigh more" must be built structurally, and two ready-made code precedents exist (C20, C21). |
| No documented case of a protocol amended because a stakeholder's question outranked an investigator's (B r2) | Searched directly in Cochrane and PROSPERO material and came up empty rather than being unexamined. |
| Perplexity's internal follow-up steering mechanism (B r2) | Help Center page returned 403 on direct fetch twice; Perplexity is the weakest of the three vendor precedents either way (B-43). |
| ISO/IEC/IEEE 29148's exact clause on the requirement "Source" attribute (B r2) | Standard is paywalled; the traceability-versus-priority distinction rests on secondary literature and nothing in the Needs list turns on the exact wording. |
| ACM's policy pages readable only through search summaries (F r2) | The operative finding is F-42, which is a direct live test. Policy wording is once-removed; observed behavior is not. |

### Closed by a sibling document

- B listed GPT-Researcher's `multi_agents/` LangGraph orchestrator as uninspected. E-15 read it: two bounded critique loops with hard revision ceilings, reviewing against style guidelines rather than coverage, and structurally unable to trigger new research.
- That closure was partial. B's own round two found a second mechanism in the same directory that E-15 did not report: a dedicated human plan-review loop (C21). A sibling reading the same directory for a different question is not a substitute for reading it for this one.

## Planner inputs

Concrete artifacts a planner would lift, traceable to document and finding.

**D-01, D-02, scope derivation**
- PICOC and Population-Concept-Context facet templates as the seed for spec-spanning axes (B-2, B-4, B-8).
- KAOS HOW and WHY goal refinement as the procedure that turns a spec's own sections into a tree (B-11, B-12).
- IEEE 29148's completeness facets, functional, quality, interface, constraints, context, as the coverage checklist (B-14).
- LangChain's legacy `report_planner_instructions` as the one working precedent for an upfront document-derived axis list (B-26).
- Gemini's `collaborative_planning` flag as the only vendor precedent for pausing on a plan, revised by round two: it is a blocking gate with no documented rule for merging a user's edit with the agent's own sub-questions (B-39, B-40).
- Evidence that unstructured elicitation under-covers whole categories: non-functional requirements were 8.4% of elicited requirements without an explicit model (B-15).
- Co-STORM's unconditional bypass as the ready-made code shape for the human's question outranking the system's: append the utterance to state with no model judgment, then make it the focus string that regenerates the axes (B-32, B-33, B-35).
- GPT-Researcher's `HumanAgent.review_plan()` as the ready-made code shape for the gate itself: present the axis list, block on a reply, route any non-approval back to regeneration, bounded by a revision ceiling (B-36, B-37).
- OpenAI's queue-and-prepend contract as the shape for mid-run steering, including its explicit caveat that acceptance means queued rather than acted on, and that in-flight work finishes first (B-41).
- The override wording to adopt if a rule needs writing: a later user utterance refers to a previous statement to override it specifically, conditioned only on correct interpretation (B-46), and system-taken initiative reverts to the user when its bounded subtask ends (B-48).
- The distinction to preserve: who wins a stated conflict (B-46 to B-48) is a separate claim from whether soliciting the human is the better next move, which has no empirical support (B-52).
- Authority as a role rather than a provenance rule, if D-02 is implemented by policy instead of by mechanism (B-54, B-57).

**D-03, curated sources**
- F's 34-source comparison matrix with tested access status, key requirement, full-text reach, and redistribution stance (F Taxonomy).
- Keyless and tested working: Crossref, OpenAlex, CORE, Unpaywall, PubMed and PMC, bioRxiv and medRxiv, HAL, Hugging Face hub, GitLab REST, PyPI, npm, crates.io with a User-Agent (F-5 to F-9, F-21, F-23, F-26, F-27, F-37, F-39).
- Dead or unusable: CiteSeerX redirects to a Wayback 404, Papers with Code redirects to Hugging Face, PMC's `oa.fcgi` retired, Google Scholar has no API and disallows the path, ResearchGate bans automated access, SSRN reserves text-mining rights (F-12, F-25, F-21, F-17, F-28, F-22).
- Garousi's eight-criterion quality instrument, the only scored reliability rubric found in the literature (A-32).
- Garousi's three-tier outlet classification and seven-question grey-literature inclusion checklist, the mechanism that admits a specialist blog while rejecting a blog pile (A-30, A-31, A-33).
- SIFT and lateral reading as the mechanizable move: leave the page and corroborate, which maps onto an existing WebSearch call (C-2, C-3).
- `gh api repos/{owner}/{repo}` and `gh api orgs/{org}` as the mechanical owner check D-03 asks for (C-9).
- Preprint marking convention: tag `[Preprint]` with version and date, and check whether a peer-reviewed version supersedes it (C-7).
- STORM's `is_valid_source` seam as the architectural shape for a pluggable predicate, with X1 resolved: the seam is real and nothing in the shipped code passes a predicate through it (C-12, X1).
- The three curation mechanisms in the wild, venue routing, domain list, LLM prompt, and the fact that no system combines them (C-16, C Taxonomy).
- Compass's `papers` skill has no reliability filter today (C-15, F-1).
- ACM, confirmed unreachable by script: no API, a Terms-of-Use ban naming scripts and spiders, and a Cloudflare challenge on every acm.org domain including already-open-access DOIs (F-40, F-41, F-42, F-49).
- The ACM fallback that does work: Crossref for complete 10.1145 metadata, OpenAlex or Semantic Scholar for abstracts, with the caveat that none of them yields a fetchable PDF URL (F-44, F-45, F-46).
- Validate a shipped source by response content type, not status code: DBLP and Internet Archive Scholar both return HTTP 200 with an HTML challenge page to a JSON call (F-50).
- Host corrections for a shipped list: `api2.openreview.net`, not `api.openreview.net` (F-51); a free Semantic Scholar key, since the anonymous tier 429s on the second call (F-52).

Two facts the human supplied, recorded here as his input rather than as research findings:

- He is an ACM member. F's pass tested only unauthenticated access, so a logged-in path was never exercised.
- The Claude in Chrome browser extension is installed in this session, so a browser-driven read of ACM pages under his login is a route the source inventory had no tooling to test. F-42's wall is a check on non-browser requests specifically.
- The constraint that governs any use of that route is F-49's own distinction: ACM's policy bans scripts, spiders, and automated harvesting, while a separate clause permits case-by-case computational analysis under an institutional arrangement. Reading pages in a browser under a member's own login is a different act from scripted harvesting, and the boundary between them is ACM's to draw, not this document's.

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
- AutoNuggetizer as the only runnable completeness scorer found: a three-stage create, score, assign pipeline yielding Strict Vital Recall over finished text, Apache-2.0, actively pushed (E-32, E-33).
- The proposed spec-to-report mapping, as an experiment rather than a finding: spec Problem as query, Decisions and Needs as documents, finished research as the passage, read off `strict_vital_score` (E-34).
- The four alternatives and why each fails for a spec: RACE needs a reference report, ALCE decomposes a gold answer, RAGAS scores retrieval, FActScore measures precision only (E-35 to E-38).
- PROXYQA's differently-shaped test, worth keeping as an option: score the report by whether an independent evaluator can answer curated questions using only the report as context (E-40).
- Co-STORM's warm start as the transfer boundary: five stages, every input a free-text string, a fixed 3-by-2 budget, and a first-draft outline generated from parametric knowledge before any grounding (E-42, E-43, E-44, E-45).
- What adopting Co-STORM's entry point would require, and the trap in it: stage 4's outline would need replacing with a direct parse of the spec's headings, since generating an outline from a topic and reconciling it afterward is the two-pass shape D-01 asks Compass to avoid (E-46).

**D-06, methodology**
- The eight-methodology catalog with steps, inputs, output, fit, and author-named failure modes, ready to ship as the chooser's menu (A, findings 1 to 43, A Taxonomy).
- The `obsidian` skill's existing four-approach research table is the file the catalog replaces (D-44).
- The hazard to encode: mapping studies instruct the agent to skip quality assessment, which is the check D-03 requires (A-22).
- PRISMA must be paired with a conduct method, never used as one (A-16), subject to P1.
- Protocol registration formats if research protocols get locked before running: PROSPERO's field set, OSF's template, and the standalone software-engineering protocol shape (A-44, A-45, A-46).
- Kitchenham's "light" solo-researcher SLR, which keeps every step but drops dual-reviewer cross-checking, as the single-agent adaptation precedent (A-14).
- Cochrane's bounded abbreviations for rapid review: dual screening on at least 20% of abstracts, single extraction with second-reviewer verification (A-7).
- DESMET as the named methodology for the comparison-shaped question the four-entry table currently calls technology landscape, with its nine evaluation types and their selection criteria as the chooser's sub-menu (A-48, A-49).
- DESMET's own two fit boundaries, which a chooser must encode: the rigorous modes fail with no valid control or treatment and on technology too new to survey (A-50), and it assumes a controllable development process (A-51).
- Jadhav and Sonar alongside DESMET as a second, non-identical peer-reviewed answer covering software-package selection specifically; A's instruction is to list both rather than unify them (A-53).
- ThoughtWorks Radar cited as a format precedent only, never as a methodology: its own FAQ disclaims comprehensiveness and its publishers warn it is not a lifecycle assessment tool (A-55).
- The owner-check rule to encode, selected by artifact class: community-health signals for a maintained library, identity and affiliation for a single-author paper artifact (A-60, A-61).

**D-07, session plugins**
- `claude mcp list` and `claude plugin list --json` as the discovery step, absent from both research skills today, confirmed by grep (D-41, D-42, D-43, D-47).
- The enumeration contract a discovery step needs: dedupe on plugin name, since the same plugin registers separately at user, project, and local scope, and read `enabled` per scope (D-45).
- What this session actually offers: four zoekt code-search indexes and a Rust language server among six distinct plugins; `serena` and `headroom` among five connected MCP servers (D-45, D-46).
- Zoekt's query syntax and the four host-provided indexes in this session, with `OR` invalid and `AND` file-level (D-36, D-37).

## Contradicts existing vault research

[[research/pipeline/RESEARCH-scientific-method-in-compass]] (2026-06-10) holds up and gains evidence rather than losing it. Two of its findings are now extended:

- Its finding 2 records that Compass's research stage offers four named approaches. That remains true of the shipped skill and is now a shortfall against D-06 rather than a neutral fact (A Taxonomy, D-44).
- Its recommendations 1 through 3 ask for pre-registration of a hypothesis frozen before build. A-44 through A-47 supply the concrete formats that recommendation had no source for: PROSPERO's field set, OSF's preregistration template, and standalone software-engineering protocol documents. Round two raises two of those to high confidence and adds the full field list of a worked software-engineering protocol: research and publication questions each mapped to an extraction item, a four-step search-string construction method across five databases, a manual search of three named venues, snowballing per Wohlin run afterward, and three-round selection with two-person discrepancy resolution quality-checked by Cohen's Kappa (A-57).
- Its recommendation 8, an effect-size column on success criteria, now has a candidate instrument it lacked: AutoNuggetizer computes a coverage score over finished text (C28), and C29 records that nobody has pointed one at a requirements document yet.

Its finding that Compass's convergence matrix is majority voting rather than Bayesian updating applies to this document too. Agreement counts here are counts, not posteriors.

## Round-two verdict

Round two did what D-05 describes: research concluded it needed more research, and the second pass changed the picture rather than confirming it. It closed all eight blocking gaps, resolved both divergences, retired one round-one recommendation as wrong (C30), lowered one criticism this review made of the run itself (the D-06 observation), and raised two new blocking gaps.

Two closures are negative answers, and negative answers are the useful kind here: there is no scriptable path to ACM (C6), and nobody anywhere scores a research report against a requirements document (C29). A planner that assumed either capability existed would have built on nothing.

CONVERGENCE: HIGH
