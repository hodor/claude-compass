---
title: "How Research Scope Is Derived From a Requirements or Problem Document"
type: research
status: draft
confidence: high
area: methodology
tags: [research, scope, pipeline, systematic-review, requirements-engineering, deep-research-agents, methodology]
created: 2026-09-13
updated: 2026-09-13
git_branch: "master"
git_commit: "50a2896"
author: "researcher"
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
summary: "systematic-review question frameworks (PICO/PICOC/SPIDER/PCC), goal-refinement and SRS completeness criteria from requirements engineering, and the decomposition code of five agentic deep-research systems all derive scope from the whole problem's structure or from found evidence, never from a fixed question list"
---

# How Research Scope Is Derived From a Requirements or Problem Document

## Question

How does a research scope (a set of investigation axes) get derived from a requirements or problem document so it spans the whole document, rather than mirroring a narrow list of questions the document happens to contain? This serves [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-01, D-02, D-05, and D-06: the spec's own Needs call for "a way to derive research scope from a whole spec" and for research to follow a chosen methodology.

## Scope

In scope: (1) systematic/scoping-review question-framing methods (PICO, PICOC, SPIDER, PCC) and Kitchenham's software-engineering guidance on formulating review questions; (2) requirements-engineering techniques for decomposing a problem statement into investigation areas (goal-oriented RE, SRS completeness standards); (3) the actual decomposition code and prompts of five agentic deep-research systems (GPT-Researcher, STORM, LangChain Open Deep Research, Hugging Face Open Deep Research, and the published descriptions of OpenAI/Gemini/Perplexity Deep Research). Out of scope: which methodology Compass should mandate, and the catalog of methodology *types* generally (that is [[research/pipeline/RESEARCH-research-methodologies-catalog]]); source-reliability criteria specifically (that is [[research/pipeline/RESEARCH-source-reliability-criteria]] - noted here only where a decomposition system's curation logic bears directly on scope).

## Methodology

Five parallel passes: two academic-literature passes fetching primary sources directly (arXiv, Semantic Scholar, PubMed/Europe PMC, canonical technical reports, official vendor blogs), and three code-reading passes that cloned open-source repositories and read the decomposition/planning modules and their prompt files line by line, per [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-04. This report is itself a **technology-landscape / comparative-evaluation** survey (per the `obsidian` skill's research-approach table): each system and each methodology is profiled on the same dimension - how it turns a problem into a scope - so they compare side by side.

## Findings

### Systematic and scoping review question framing

1. **PICO origins in a full clinical scenario, not a single question** (confidence: medium)
   Richardson et al. 1995 frame a "well-built" clinical question as needing Population, Intervention, Comparison, and Outcome together, so the question maps onto a complete scenario rather than a topic word.
   - DOI:10.7326/ACPJC-1995-123-3-A12 - metadata and citation count via Semantic Scholar; primary text paywalled (403), wording taken from secondary summaries.

2. **PICOC adds Context, changing what counts as in-scope evidence for software engineering** (confidence: high)
   Kitchenham & Charters (EBSE-2007-01 v2.3, §5.3.2) quote Petticrew & Roberts' PICOC directly: Comparison is "what is the intervention being compared with," Context is "the context in which the intervention is delivered" - explicitly the setting (academia vs. industry), participants (practitioners vs. students), and task scale (small vs. large).
   - EBSE-2007-01 §5.3.2, verbatim quote fetched directly.

3. **SPIDER swaps intervention-comparison for design-and-research-type when the question is about experience, not effect** (confidence: high)
   Cooke, Smith & Booth 2012 built SPIDER (Sample, Phenomenon of Interest, Design, Evaluation, Research type) against PICO on the same qualitative question, because PICO's Population/Intervention pair presumes a comparative effect that qualitative and mixed-methods questions don't have. The paper's own caveat: SPIDER "needs to be refined and tested on a wider range of topics."
   - DOI:10.1177/1049732312452938, abstract fetched via PubMed/Europe PMC.

4. **Kitchenham & Charters: the review question drives the entire method, and PICOC facets are used to decompose one question into searchable dimensions** (confidence: high)
   "Specifying the research questions is the most important part of any systematic review. The review questions drive the entire systematic review methodology" (§5.3). PICOC facets (population, intervention, comparison, outcomes, context, study designs) are applied as one question's dimensions for search-string construction, not as a menu of separate questions.
   - EBSE-2007-01 §5.3, §6.1.1, verbatim quotes fetched directly.

5. **Narrow-versus-broad research questions is a real fork, resolved by review type, not by rule** (confidence: high)
   The same report cites Staples & Niazi recommending narrow, focused RQs for a full SLR (§5.6), then in §8 recommends the opposite for systematic mapping studies: "Mapping studies generally have broader research questions driving them and often ask multiple research questions... the aim here is for broad coverage rather than narrow focus." Which one applies depends on which methodology was chosen for the case.
   - EBSE-2007-01 §5.6, §8, verbatim quotes fetched directly. See [[research/pipeline/RESEARCH-research-methodologies-catalog]] for the full methodology-choice catalog.

6. **Scope is set once volume and shape of the field are known, not upfront** (confidence: high)
   Arksey & O'Malley 2005: "Our recommendation would be to maintain a wide approach in order to generate breadth of coverage. Decisions about how to set parameters... can be made once some sense of the volume and general scope of the field has been gained." The process is explicitly iterative, not linear, and steps are repeated as understanding grows.
   - DOI:10.1080/1364557032000119616, full text fetched (White Rose repository).

7. **A scoping review's founding purpose is literally "extent, range and nature," not an answerable question** (confidence: high)
   One of Arksey & O'Malley's four canonical scoping-study purposes is "to examine the extent, range and nature of research activity" - the review question is deliberately open rather than narrowed to a design that can be searched for in advance, unlike a systematic review's "well defined question where appropriate study designs can be identified in advance."
   - DOI:10.1080/1364557032000119616, verbatim quotes fetched directly.

8. **PRISMA-ScR replaces PICO with PCC (Population, Concept, Context) for scoping reviews specifically to drop outcome/intervention specificity** (confidence: medium-high)
   Tricco et al. 2018 require the objective be framed by "population/participants, concepts, and context" (Item 4), not intervention/comparison/outcome. The JBI Manual states explicitly "there is no need for explicit outcomes, interventions or phenomena of interest to be stated for a scoping review" - the mnemonic itself is what licenses covering a whole topic rather than one comparison.
   - DOI:10.7326/M18-0850, abstract fetched via Europe PMC; JBI Manual (Peters et al., Ch. 11) via secondary description, medium confidence on exact wording.

9. **Guard techniques against a prematurely narrow question: pre-review scoping, budgeted revision, and separating review-level from synthesis-level scope** (confidence: high)
   Brereton et al. (cited in Kitchenham & Charters §5.6): "a pre-review mapping study may help in scoping research questions," and reviewers should "expect to revise questions during protocol development, as understanding of the problem increases." The current Cochrane Handbook (Ch. 2, secondary description) separates a broader "review PICO" (eligibility scope) from a narrower "PICO for each synthesis" (one comparison at a time), and names the risk directly: "a question that is too narrow may not have enough evidence to allow you to answer your review question."
   - EBSE-2007-01 §5.6; Cochrane Handbook Ch. 2 via WebSearch summarization, not directly fetched (medium confidence).

10. **Different review types need different question mnemonics - a single fixed question-list format is a category error** (confidence: medium)
    Booth 2006 (DOI:10.1108/07378830610692127) establishes that PICO, SPICE, ECLIPSE, and SPIDER each fit a different review shape; picking one mnemonic and forcing every review's question into it misframes reviews whose nature doesn't match. Read via secondary description only, not fetched directly.

### Requirements-engineering decomposition of a problem into investigation areas

11. **KAOS goal refinement is a tree, built by asking HOW to go down and WHY to go up** (confidence: high)
    Van Lamsweerde's "Guided Tour" (RE'01, §3, §6): "AND-refinement links relate a goal to a set of subgoals... satisfying all subgoals in the refinement is sufficient for satisfying the parent goal." Elicitation proceeds by "keep asking HOW questions about goals already identified" (decomposition) or "keep asking WHY questions about operational descriptions already available" (find the covering parent goal) - a systematic generation procedure, not an ad hoc list.
    - https://webperso.info.ucl.ac.be/~avl/files/RE01.pdf §3, §6, fetched and read directly.

12. **KAOS ties "complete" to the goal tree's own structure, and the tree doubles as a traceability map** (confidence: high)
    "The specification is complete with respect to [a] set of goals [if] all goals can be proved to be achieved by the specification" (RE'01 §2). The same tree "provides traceability links from high-level strategic objectives to low-level technical requirements" - completeness is checked against the model's own shape, not against a checklist of questions raised along the way.
    - RE'01 §2, fetched and read directly.

13. **i*/Tropos decomposes an actor's goal into sub-tasks via Strategic Dependency and Strategic Rationale models** (confidence: medium)
    Yu's ISRE'97 paper introduces SD models (actors depending on each other for goals/tasks/resources) and SR models (means-ends decomposition of one actor's goal into sub-tasks). Primary paper was paywalled; mechanics reconstructed from the author's own tutorial materials, not the paper text itself.

14. **IEEE/ISO/IEC 29148's "Complete" characteristic names the dimensions a requirements set must cover** (confidence: high)
    A complete set "needs no further amplification because it contains everything pertinent... contains no TBD/TBS/TBR clauses." The standard's coverage dimensions are functional, non-functional/quality (performance, security, usability, reliability), interface, design/implementation constraints (its own named category), and stakeholder/environment context in companion documents - a fixed set of facets a complete document must touch, structurally analogous to PICOC's facets for a review question.
    - ISO/IEC/IEEE 29148:2018, standard clauses on requirement characteristics.

15. **Unstructured elicitation measurably under-covers non-functional requirements** (confidence: medium)
    An empirical study found non-functional requirements made up only 8.4% of elicited requirements when elicitation was not structured by an explicit model - indirect evidence that a question list generated ad hoc, without a facet structure to check against, systematically misses whole categories.
    - arXiv:2604.07211, abstract-level read.

### Agentic deep-research systems: decomposition code read directly

16. **GPT-Researcher's default pass generates a fixed number of sub-queries from one LLM call, not derived from document structure** (confidence: high)
    `generate_sub_queries()` calls a prompt demanding "write {max_iterations} search queries," with `MAX_ITERATIONS: 3` as the default cap; the original query is appended afterward for non-subtopic report types, then all sub-queries fire concurrently.
    - `gpt_researcher/actions/query_processing.py:83-156`, `gpt_researcher/prompts.py:248-259`, `gpt_researcher/config/variables/default.py:25`.

17. **GPT-Researcher's "detailed report" mode derives axes from what research actually found, not from a fixed upfront plan** (confidence: high)
    `construct_subtopics()` generates subtopics from accumulated research context (capped `MAX_SUBTOPICS: 3`), then spawns one independent nested researcher per subtopic (`report_type="subtopic_report"`), sharing accumulated URLs and headers to avoid duplication. This is the system's closest analogue to "derive axes from the whole document, not a question list": the axes emerge from evidence gathered so far.
    - `gpt_researcher/skills/writer.py:216-223`, `backend/report_type/detailed_report/detailed_report.py:84-158`, `gpt_researcher/config/variables/default.py:30`.

18. **GPT-Researcher's "deep research" mode expands breadth and depth recursively and is gated as a separate mode, not the default path** (confidence: high)
    `deep_research()` (`gpt_researcher/skills/deep_research.py`) generates a research plan with clarifying follow-up questions, then recursively re-invokes itself with configurable `DEEP_RESEARCH_BREADTH: 3` and `DEEP_RESEARCH_DEPTH: 2`. Gap-driven re-scoping - the system's nearest precedent to "research reveals more research is needed" - exists only in this isolated mode, not in the plain `research_report`/`detailed_report` flow.
    - `gpt_researcher/skills/deep_research.py:292-578`, `gpt_researcher/config/variables/default.py:39-41`.

19. **GPT-Researcher's source curation is optional, LLM-judgment-based, and off by default; no domain allowlist exists** (confidence: high)
    Curation runs through `curator.py`, gated by `CURATE_SOURCES: False` in the default config, and is pure per-run LLM judgment over whatever the scraper returned - a grep for `allowlist|trusted_domain|blocklist|blacklist` across the whole codebase returned nothing. See [[research/pipeline/RESEARCH-source-reliability-criteria]] for the broader curation-mechanism comparison.
    - `gpt_researcher/skills/curator.py:35-111`, `gpt_researcher/config/variables/default.py:17`, `gpt_researcher/skills/researcher.py:211-214`.

20. **STORM discovers "perspectives" by asking the model to recall related topics, then generating one persona per angle** (confidence: high)
    `FindRelatedTopic` asks the LLM to freely recall related Wikipedia pages (no search call); the code then scrapes each page's table of contents and feeds it to `GenPersona`, which emits named "Wikipedia editor" roles. A fixed generalist persona is prepended and the LLM-generated specialists are capped at `max_num_persona=3` - axes come from the topic's neighborhood in the model's own knowledge, not from the source document.
    - `knowledge_storm/storm_wiki/modules/persona_generator.py:48-134`, `knowledge_storm/storm_wiki/engine.py:134-144`.

21. **Base STORM uses fixed integer budgets everywhere; no dynamic scope growth** (confidence: high)
    `max_conv_turn=3`, `max_perspective=3`, `max_search_queries_per_turn=3`, `search_top_k=3`, `retrieve_top_k=3` are all fixed defaults; the simulated conversation per persona stops on a prompted "no more questions" convention, not a semantic coverage check.
    - `knowledge_storm/storm_wiki/engine.py:134-168`, `knowledge_storm/storm_wiki/modules/knowledge_curation.py:47-68,128-151`.

22. **Co-STORM (the collaborative extension) adds genuinely dynamic, information-volume-triggered scope expansion** (confidence: high)
    `GenerateExpertWithFocus` regenerates a fresh set of experts mid-discussion conditioned on a `focus` string, and `ExpandNodeModule` auto-splits an outline section once information volume crosses a threshold - the one system in this survey whose scope literally grows in response to what was found, beyond a fixed initial budget.
    - `knowledge_storm/collaborative_storm/modules/expert_generation.py:24`, `.../information_insertion_module.py:334-420`, `.../engine.py:206-256`.

23. **STORM's own docstring claims a source-filtering step that the code does not implement** (confidence: high)
    `TopicExpert`'s docstring lists "3. Filter out unreliable sources" as a step, but the method body has no filtering logic beyond a ground-truth-leakage exclusion list; every retrieval module accepts an `is_valid_source` callable that defaults to `lambda x: True` and is never overridden in the shipped code. A documented intent that the implementation does not carry out.
    - `knowledge_storm/storm_wiki/modules/knowledge_curation.py:182-218`, `knowledge_storm/rm.py:14-30`.

24. **LangChain's current Open Deep Research has no upfront enumerated plan - a supervisor decides one sub-topic at a time** (confidence: high)
    A "lead researcher" LLM repeatedly calls a `ConductResearch(research_topic)` tool, spawning one parallel sub-researcher per call; the number and content of sub-topics is decided live by the supervisor's own judgment across calls, never fixed as a list before execution starts.
    - `src/open_deep_research/deep_researcher.py:178-223,283-349`, `src/open_deep_research/state.py:15-19`.

25. **The same system runs an explicit sufficiency/reflection check before finalizing** (confidence: high)
    The supervisor chooses between `ConductResearch` and a `ResearchComplete` tool call; the prompt frames this as a judgment call on whether enough has been gathered, not a fixed iteration count.
    - `src/open_deep_research/prompts.py:92,105,124-129`.

26. **LangChain's earlier ("legacy") graph derives a fixed section list from the topic up front - the closest precedent in this survey to "derive N axes from a whole document"** (confidence: high)
    `report_planner_instructions` produces a structured `Sections` list (name, description, whether it needs research) from a configurable report-structure template, with a prompt-baked minimum: the report "must have AT LEAST 2-3 sections with Research=True to be useful."
    - `src/legacy/prompts.py:29-60`, `src/legacy/state.py:5-22`.

27. **The legacy graph also grades each written section against the topic and generates targeted follow-up queries on failure, capped by depth** (confidence: high)
    A `Feedback{grade: pass|fail, follow_up_queries}` structured-output call reviews each section; on `fail` it emits specific follow-up search queries and loops, bounded by `max_search_depth` (default 2) - a per-section, evidence-driven expansion mechanism distinct from the upfront plan.
    - `src/legacy/graph.py:314-352`, `src/legacy/configuration.py:46`.

28. **Hugging Face's Open Deep Research example has no dedicated decomposition step - it inherits smolagents' generic re-planning interval** (confidence: medium-high)
    The manager agent's plan is regenerated every `planning_interval` steps using a generic "step-by-step high-level plan" prompt that tells the model, on later calls, to build on progress or restart from scratch if stalled - a general-purpose re-planning loop, not a document-scoped decomposition step, and the manager delegates single tasks to sub-agents rather than producing an enumerated section list.
    - `src/smolagents/agents.py:550-567`, `src/smolagents/prompts/code_agent.yaml:177-198,241-242`.

29. **OpenAI's Deep Research API decomposes as a single agentic loop with no exposed plan and no clarifying step outside ChatGPT** (confidence: high)
    The official cookbook states the raw API "skips the clarification step" and will not ask for missing context; the model "autonomously plans sub-questions" while issuing sequential tool calls - decomposition happens inside the model's own reasoning, not as an inspectable artifact.
    - https://developers.openai.com/cookbook/examples/deep_research_api/introduction_to_deep_research_api, official OpenAI source.

30. **Google's Gemini Deep Research is the only vendor of the three whose official materials describe a user-editable plan and an explicit parallel-vs-sequential decision** (confidence: high)
    "The system first formulates a detailed research plan, breaking the problem into a series of smaller, manageable sub-tasks... You're in control of the plan... the model... intelligently determines [which] sub-tasks [can be] tackled simultaneously [vs.] need to be done sequentially." A 2026 extension exposes this as a `collaborative_planning` API flag with a `previous_interaction_id` to keep iterating on the plan across turns.
    - blog.google/products/gemini/google-gemini-deep-research/; blog.google/innovation-and-ai/models-and-research/gemini-models/next-generation-gemini-deep-research/, official Google sources.

31. **Perplexity's Deep Research is the only vendor of the three to state an explicit stopping/sufficiency criterion in official prose** (confidence: high)
    "It plans before taking action... runs multiple searches instead of one, reading results... before reasoning about what to search next... evaluates whether [there is] enough evidence" or conflicting notes. OpenAI's and Google's official materials give only time-based framing ("5-30 minutes"), not an explicit sufficiency test.
    - perplexity.ai/hub/blog/introducing-perplexity-deep-research; perplexity.ai/hub/blog/deep-research-now-in-comet, official Perplexity sources.

## Taxonomy

Every system and methodology surveyed derives scope one of three ways, never from a free-floating question list:

- **Facet templates applied to one question** - PICO/PICOC/SPIDER/PCC (findings 1-3, 8) and IEEE 29148's requirement characteristics (finding 14) force a single question or document to be checked against a fixed set of dimensions (population, context, design, constraints...), so coverage is judged by which facets were touched, not by how many questions got asked.
- **Structure-driven decomposition of the document itself** - KAOS goal trees (findings 11-12) and the legacy LangChain planner's document-derived section list (finding 26) generate the scope from the shape of the problem or report structure, and completeness is checked against that structure closing, not against a list.
- **Evidence-driven expansion during the run** - scoping-review iteration (findings 6, 9), GPT-Researcher's detailed/deep modes (findings 17-18), LangChain's section-grading loop (finding 27), Co-STORM's information-triggered expansion (finding 22), and Perplexity's stated sufficiency check (finding 31) all start from a deliberately broad or adaptive scope and let what is *found* trigger more research, rather than fixing every axis before starting.

The three are complementary, not competing: PICOC-style facets can seed the *initial* broad scope, structure-driven decomposition can turn a spec's own sections into axes, and evidence-driven expansion is what D-05 ("research might reveal more research is needed") already asks for.

## Contradictions

- Kitchenham & Charters cite Staples & Niazi recommending narrow RQs for a full SLR, then recommend broad, multi-question RQs for mapping studies in the same report (finding 5) - not a disagreement between sources but a documented fork resolved by which methodology is chosen for the case, consistent with [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-06.
- STORM's `TopicExpert` docstring claims a source-filtering step (finding 23) that its own code never implements - a discrepancy between documented intent and shipped behavior, worth naming as a general risk (a plugin's own docs describing a check that its code does not perform).

## Gaps

- Yu's original i*/Tropos paper (ISRE'97) was paywalled; finding 13's decomposition mechanics rest on the author's own tutorial materials, not the primary text. A follow-up pass with ACM DL or institutional access would firm this up.
- Petticrew & Roberts' 2006 book (the primary PICOC source) was not read directly; finding 2 leans on Kitchenham & Charters' verbatim quote of it, which is high confidence for that quote but not for the book's fuller framing.
- The Cochrane Handbook Ch. 2 guard-technique claims (finding 9) came from a WebSearch summary, not a direct fetch of training.cochrane.org - worth a direct fetch if the exact wording of the "review PICO vs. synthesis PICO" distinction matters later.
- OpenAI's original "Introducing deep research" launch blog returned HTTP 403 on direct fetch; finding 29's framing leans on the official cookbook plus a search snippet of the blog, not a direct read of the blog itself.
- GPT-Researcher's alternate `multi_agents/` LangGraph-based orchestrator (a second planner implementation living in the same repo) was not inspected - it may show a different decomposition pattern than the one documented in findings 16-19.
- STORM's Co-STORM warm-start prompt templates (the phase that seeds the initial mind map before the roundtable discussion) were not read in full, only confirmed to exist with fixed budgets (`warmstart_max_num_experts=3`, `warmstart_max_turn_per_experts=2`).
- Hugging Face's smolagents-based example was not checked for a domain-filtering equivalent to LangChain's `include_source_str`/search-API allowlist config; plausibly there is none, but `text_web_browser.py` was not read closely enough to rule it out.
- No official OpenAI or Perplexity material states a parallel-sub-agent architecture the way Google's does for Gemini; any such claim seen elsewhere should be treated as third-party inference, not vendor-confirmed, until an official source is found.
