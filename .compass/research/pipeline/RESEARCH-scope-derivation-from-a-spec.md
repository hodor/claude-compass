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

## Follow-up Research - 2026-09-13

Closes the gap named in [[research/pipeline/REVIEW-spec-023-research-consolidation]]: no round-one document addressed how a human's question outranks a spec's listed questions (SPEC-023 D-02, Needs). Four parallel passes: direct code reading of Co-STORM, GPT-Researcher's `multi_agents/` orchestrator, and LangChain Open Deep Research (continuing this document's own D-04 method); one pass on Google Gemini, OpenAI, and Perplexity's vendor documentation; one pass on the mixed-initiative and conversational-search literature; one pass on requirements-engineering prioritization and systematic-review protocol amendment rules.

### Open-source systems: the mechanism is structural, never a scored field

32. **Co-STORM's human turn bypasses the turn-policy pipeline entirely** (confidence: high)
    `CoStormRunner.step(user_utterance=...)`: when `user_utterance` is non-empty, the method appends it straight to `conversation_history` as a `ConversationTurn` and returns, never calling `get_next_turn_policy` or any agent's `generate_utterance`. No LLM judges whether to accept it.
    - `knowledge_storm/collaborative_storm/engine.py:661-663,702-707`

33. **The injected human utterance becomes the literal `focus` string that regenerates the expert panel** (confidence: high)
    On the next turn, `_is_last_turn_questioning` is true (the human turn is tagged `"Original Question"`), so `get_next_turn_policy` sets `should_update_experts_list=True`; `_update_expert_list_from_utterance` then calls `GenerateExpertModule` with `focus=last_conv_turn.raw_utterance` - the human's own words - regenerating the entire discussion panel around what the human asked.
    - `knowledge_storm/collaborative_storm/engine.py:445-452,489-497`; `knowledge_storm/collaborative_storm/modules/expert_generation.py:59-73`

34. **Human and system-generated questions carry the identical type tag; priority is not encoded as a label** (confidence: high)
    The Moderator's own gap-driven question and the human's injected utterance are both tagged `utterance_type="Original Question"`. Downstream logic (`_is_last_turn_questioning`, `_should_generate_question`, the focus derivation in finding 33) branches on this type, not on who produced the turn - there is no separate "human question" category with its own weight.
    - `knowledge_storm/collaborative_storm/modules/co_storm_agents.py:155,308`

35. **The system's own question-asking is rate-limited; the human's is not** (confidence: high)
    The Moderator only gets to ask a self-generated question after `moderator_override_N_consecutive_answering_turn` (default 3) consecutive non-questioning turns have passed. A human calling `step(user_utterance=...)` can interrupt at any turn, with no equivalent gate. Priority is achieved by exempting the human path from a throttle applied to the system's own path, not by a comparison.
    - `knowledge_storm/collaborative_storm/engine.py:245,408-423`

36. **GPT-Researcher's `multi_agents/` orchestrator has a dedicated human-plan-review loop, undocumented by round one** (confidence: high)
    `HumanAgent.review_plan()` presents the generated section outline to the human ("Any feedback on this plan of topics to research?") and blocks on a reply (console `input()` or a websocket message). Any non-empty, non-approval reply increments `plan_revision_count` and `route_human_feedback` returns `"revise"`, sending the plan back for regeneration; approval (`"no"`, matched by `is_human_plan_approval`) proceeds. This is a second, independent code precedent for a human's stated objection displacing the system's own plan - distinct from the style-guideline critique loop [[research/pipeline/RESEARCH-research-spawning-research]] E-15 already read in the same directory.
    - `multi_agents/agents/human.py:10-60`, `multi_agents/agents/plan_review.py:1-21`

37. **The revision loop is bounded, and the bound is enforced against the human, not the system** (confidence: high)
    `route_human_feedback` raises `MaxPlanRevisionsExceededError` once `plan_revision_count` exceeds `max_plan_revisions` (default 3). The human's objections take priority over the system's plan up to a ceiling, after which the ceiling itself takes priority - the same budget-plus-self-report pattern this document's Taxonomy already names for stopping (finding 12/C12), applied here to a human-facing revision loop instead of an autonomous one.
    - `multi_agents/agents/plan_review.py:1-21`

38. **LangChain Open Deep Research achieves priority by re-synthesis through one LLM call, not by inserting the human's text verbatim** (confidence: high)
    `clarify_with_user` can end the graph (`goto=END`) with a clarifying question when `need_clarification` is true; once the human replies, `write_research_brief` feeds the entire accumulated message buffer, human answer included, through `get_buffer_string` into a single structured-output call that produces `research_brief` - the one artifact the rest of the system (the supervisor and every sub-researcher) conditions on. The human's words are not layered on top as a separate priority signal; they are blended into the brief by the same LLM call that would have processed a purely AI-originated message.
    - `src/open_deep_research/deep_researcher.py:60-76,97-104,118-151`

### Vendor documentation: turn-taking gates and queue-and-prepend, never a weight

39. **Google Gemini's `collaborative_planning` is a blocking turn-taking gate, not a priority field** (confidence: high, per subagent's direct fetch of the API reference)
    Setting `collaborative_planning: true` makes the Deep Research agent return its plan and wait; the agent "proceed[s] only if user confirms plan in next turn." The mechanism is binary (wait vs. execute), not a merge or weighting rule.
    - https://ai.google.dev/api/interactions-api

40. **Gemini's documentation has no stated rule for reconciling a user's edit with the agent's own plan content** (confidence: high, absence explicitly checked)
    Neither the Interactions API reference nor the Deep Research guide states how a user's edited plan is merged with, or made to override, the agent's previously generated sub-questions - only that the agent regenerates a new plan conditioned on the exchange. The "user's question outranks the system's" claim has no documented arbitration rule behind it here, only a gate.
    - https://ai.google.dev/api/interactions-api, https://ai.google.dev/gemini-api/docs/deep-research

41. **OpenAI's Responses API documents an explicit queue-and-prepend steering protocol, tied directly to Deep Research refinement** (confidence: high, per subagent's direct fetch of the developer guide)
    A client sends `response.steer`; the server acknowledges with `response.steer.accepted`, explicitly stating "Acceptance means input queued, not [that the] model has acted on it." In-flight tool calls finish, then a new response is generated with the accepted input implicitly prepended ahead of the continuation; already-sent output cannot be rewritten and in-progress tool calls cannot be cancelled. OpenAI's own announcement names Deep Research refinement as a use case.
    - https://developers.openai.com/api/docs/guides/steering

42. **OpenAI's mid-run correction capability is a documented recent addition, not an original design assumption** (confidence: medium, community forum + vendor timing)
    Prior to the steering feature (shipped ~November 2025 per the surrounding announcement), users reported no way to pause or redirect a Deep Research run once started; the queue-and-prepend protocol in finding 41 was added afterward. This dates the "human can interrupt" capability as a retrofit, not a founding property of the system.
    - https://community.openai.com/t/bug-report-unable-to-pause-deep-research-when-it-goes-in-the-wrong-direction/1132158

43. **Perplexity documents the weakest mechanism of the three vendors: user-facing behavior only, no internal rule** (confidence: medium/low)
    Perplexity's enterprise guidance says users can "add instructions to continue, refine, [or] tailor" a report, with context "carr[ying] across [the] thread," but no page (including the Sonar API docs) states whether a follow-up appends, re-runs, or is blended by an LLM into the existing report. A secondary-sourced 2026 update claims follow-ups can be added while research is still running, but with no mechanism named for reconciling it with sub-questions already in flight.
    - https://www.perplexity.ai/enterprise/videos/using-deep-research; secondarily, https://www.perplexity.ai/help-center/en/articles/13600190-what-s-new-in-advanced-deep-research (403 on direct fetch)

44. **Independent academic corroboration that mid-process human control is generally underbuilt across the deep-research agent category** (confidence: medium)
    A 2026 paper frames the field's default shape as "one-shot scoping, at most a single clarification, [then a] long autonomous run [producing a] monolithic report, offering little mid-process control when user needs evolve" - a non-vendor observation consistent with findings 39-43 regardless of what any single vendor's docs say.
    - arXiv:2605.24266

### Mixed-initiative and conversational-search literature: initiative is a bounded, reverting loan, and the user has a standing override

45. **Horvitz's founding mixed-initiative principles bound system-taken initiative and preserve direct user override** (confidence: high)
    The agent chooses among acting, engaging in dialog, or deferring based on estimated confidence that the user holds the goal in question; "employing dialog to resolve key uncertainties" is one of the named principles, and the user can always directly invoke or terminate the service, overriding the system's own inference about what to do next.
    - Horvitz, "Principles of Mixed-Initiative User Interfaces," CHI 1999, DOI 10.1145/302979.303030, full text fetched.

46. **Radlinski & Craswell name an explicit override mechanism in a formal conversational-search model** (confidence: high, exact quote)
    "This possibility - assuming the user text is interpreted correctly by the system - allows the user to refer to a previous statement to override it specifically." A later user utterance is designed to supersede an earlier system-held interpretation, conditioned only on correct interpretation, not on any confidence comparison.
    - Radlinski & Craswell, "A Theoretical Framework for Conversational Search," CHIIR 2017 (not CIKM, a common misattribution), DOI 10.1145/3020165.3020183, §5.2, full text fetched.

47. **The same model gives the user a standing free-text action available at every turn, regardless of what the system just asked for** (confidence: high)
    The action space includes an unstructured-text response available whenever the system is mid-way through a structured turn (a slot-fill, a rating, a critique); the user "can at any time take initiative from the system." System-driven structured flow is the default the user can break at will, not a track the user must follow.
    - Radlinski & Craswell, CHIIR 2017, §5.2-5.3, full text fetched.

48. **Allen, Guinn & Horvitz's mixed-initiative taxonomy treats system-taken initiative as a temporary loan that reverts** (confidence: high, via a directly-fetched survey's faithful paraphrase)
    "Subdialogue initiation" lets the system clarify only "temporarily, until the issue is resolved"; "fixed subtask initiation" lets the agent complete one bounded subtask, after which "initiative reverts to the user." Neither model treats system-taken initiative as a lasting takeover.
    - Allen, Guinn, Horvitz, "Mixed-Initiative Interaction," IEEE Intelligent Systems, 1999, as reproduced in Zamani, Trippas, Dalton & Radlinski, "Conversational Information Seeking," arXiv:2201.08808, §6.

49. **TREC CAsT treats the human-adjudicated utterance as canonical ground truth, and scores system rewrites against it** (confidence: high, exact quotes)
    "The manually rewritten utterances ('resolved') contain all of the information required," produced by two organizers and adjudicated to a canonical form; relevance judgments are made against this resolved form, and automatic (system-generated) query rewrites lag it by "a 26% relative difference in median and 35% relative difference in the best runs."
    - Dalton, Xiong, Callan, "TREC CAsT 2019: The Conversational Assistance Track Overview," arXiv:2003.13624, full text fetched.

50. **CAsT's early task design makes every turn strictly downstream of the prior user utterance, never of system output** (confidence: high)
    In CAsT 2019, "later turns only depended on the previous utterances, not on system responses"; response-dependence and explicit "mixed-initiative sub-tasks" were added only in CAsT 2021 and 2022. Coreference and ellipsis resolution is the named mechanism for folding a new user turn into a self-contained query, and off-the-shelf coreference models "struggled with TREC CAsT topics more than expected."
    - arXiv:2003.13624; Zamani et al., arXiv:2201.08808, §on conversational history.

51. **Once a clarifying question is answered, the user's answer is merged into the retrieval model, not substituted as a hard override** (confidence: medium-high)
    Qulac's clarification decision is confidence-gated ("assess the level of confidence in the results and decide whether to return the results or ask questions"); the answer is then folded in by interpolating the original query with the accumulated question-answer history via a KL-divergence language model - additive weighting, not replacement.
    - Aliannejadi, Zamani, Crestani, Croft, SIGIR 2019, DOI 10.1145/3331184.3331265, arXiv:1907.06554, full text via ar5iv.

52. **An empirical complication: no universal dominance between user-initiated and system-initiated turns was found for outcome quality** (confidence: medium)
    "There is no superior or dominant combination" between the system offering query suggestions versus asking clarifications; the better strategy is cost- and context-dependent. This separates two distinct claims a planner must not conflate: that a human's input should win a stated conflict (findings 46-48), versus that soliciting the human is always the higher-value next move (unsupported here).
    - Aliannejadi, Azzopardi, Zamani, Kanoulas, Thomas, Craswell, CIKM 2021, arXiv:2109.05955, abstract only.

53. **"User intent as ground truth" appears repeatedly as the thing a system's hypothesis is checked against, never the reverse** (confidence: medium, synthesis across three papers, abstracts only)
    Across clarification-decision papers, the system's working hypothesis about the query is what gets evaluated against a known or annotated user intent; no source has a system-generated hypothesis serving as ground truth for a user's stated intent.
    - CoSearcher, Discover Computing 2022; arXiv:2107.05760; arXiv:2109.12451.

### Requirements-engineering prioritization: authority is assigned to a role, not computed from provenance

54. **MoSCoW locates final priority in a named business role, not in an analyst's judgment or a requirement's origin** (confidence: high)
    In DSDM, the Business Ambassador sets day-to-day priority and the Business Visionary "determines final priorities," with escalation to the Business Sponsor; the delivery team may challenge a dubious "Must" but does not decide it. Authority is a role assignment, exercised regardless of whether a given requirement was stakeholder-stated or analyst-derived.
    - Agile Business Consortium, "What is MoSCoW Prioritization?", https://www.agilebusiness.org/resource/what-is-moscow-prioritization/; DSDM Atern course material.

55. **MoSCoW documents no rule tying a requirement's provenance to its priority** (confidence: medium)
    No located source has MoSCoW tracking "stakeholder-stated vs. analyst-derived" as a variable feeding Must/Should/Could/Won't; the founding 1994 Clegg & Barker text was not directly accessible to rule this out completely.

56. **The Kano model's taxonomy is built entirely from customer-stated reaction, with no parallel category for an analyst-derived requirement** (confidence: medium)
    Must-be, one-dimensional, and attractive quality are classified from a functional/dysfunctional customer questionnaire; an analyst-derived requirement has no route into the taxonomy except by also being run through that same customer-facing instrument.
    - Kano, Seraku, Takahashi, Tsuji, "Attractive quality and must-be quality," Journal of the Japanese Society for Quality Control, 14(2), 1984, pp. 39-48, read via secondary summaries (original is Japanese-language).

57. **Karlsson & Ryan's cost-value approach cleanly separates who assigns value from who assigns cost, and never ranks one input above the other** (confidence: high, verified against the primary PDF)
    Step 2: "Customers [and] users (or suitable substitutes) apply AHP's pairwise comparison method [to] assess [the] relative value [of] candidate requirements." Step 3: "Experienced software engineers use AHP's pairwise comparison [to] estimate [the] relative cost [of] implementing [a] candidate requirement." The two judgments are combined on a cost-value diagram (Step 4) for joint stakeholder discussion (Step 5); neither role's input is subordinated to the other's.
    - Karlsson & Ryan, "A Cost-Value Approach for Prioritizing Requirements," IEEE Software 14(5), 1997, pp. 67-74, DOI 10.1109/52.605933, primary PDF fetched (fileadmin.cs.lth.se/cs/Education/ETSF30/Labb/karlsson97.pdf), pp. 67-68.

58. **A requirement's "Source" is a documented traceability attribute, not a documented priority rule** (confidence: low, standard itself paywalled)
    Requirements-traceability-matrix practice and secondary descriptions of ISO/IEC/IEEE 29148 record a requirement's origin (stakeholder interview, business document, regulation) for validation and audit, but no located source ties that attribute to a tie-breaking or priority mechanism.
    - Secondary summaries only; ISO/IEC/IEEE 29148 clause text not directly read.

59. **Documented stakeholder-weighting schemes generalize "a designated authority outranks others," but require the scheme fixed in advance, not asserted ad hoc** (confidence: medium)
    "Limited Weighted Votes" assigns "higher weights [to] important stakeholders" (arXiv:2402.13149); a two-level AHP scheme computes stakeholder priority as group weight times within-group AHP weight (arXiv:1803.05969); a patented budget-proportional bidding method issues each stakeholder a weight "proportional [to their] budget" (US Patent 8,024,256). None states that a human's newly-asked question automatically outranks a pre-existing system-derived list without such a scheme already in place.

### Systematic-review protocols: transparent disclosure, not a precedence rule

60. **PROSPERO's amendment mechanism is dated, public, and source-agnostic** (confidence: high)
    A "Revision note" facility requires a brief description of changes and the reason for them, recorded in the public record as part of the audit trail; prior versions are marked "Archived" and remain accessible through dated links. The mechanism applies uniformly regardless of who prompted the change.
    - Booth et al., "PROSPERO: an international register of systematic review protocols," 2012, DOI 10.1186/2046-4053-1-2, PMC3348673.

61. **PROSPERO names "addition of new outcome measures" as a legitimate but bias-sensitive amendment category** (confidence: high)
    The same paper flags changes that could be "seen [as] potentially introducing biases through increased knowledge of potentially eligible studies," citing "the narrowing [of] objectives [or the] addition [of] new outcome measures" as examples requiring transparent, dated disclosure of the reason for the change.
    - Booth et al. 2012, PMC3348673.

62. **PROSPERO's mechanism contains no provision differentiating a stakeholder- or funder-driven late addition from any other change** (confidence: high, absence confirmed by direct reading)
    The founding paper's only funder-specific passage concerns fixed completion dates; the general revision-note and audit-trail mechanism (findings 60-61) is the entire provision, regardless of who requested the amendment or why.
    - Booth et al. 2012, PMC3348673.

63. **Cochrane's MECIR standard requires the review question to address consumer-important issues, but leaves final weighing to the review team, not to the consumer** (confidence: high, exact quote)
    "Whenever feasible, systematic reviews should [be] based on priorities identified by key stakeholders such as decision makers, patients/public, [and] practitioners." Consumers are one stakeholder group among several; where priorities conflict, resolution is left to "the review team's judgement," not automatically resolved in the consumer's favor.
    - Cochrane Handbook for Systematic Reviews of Interventions, current version, Chapter 2, https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-02.

64. **UK public-involvement guidance treats late stakeholder input as a funding condition, not a document-amendment precedence rule** (confidence: medium)
    NIHR guidance states "it's not too late to involve people if you [have] already identified [a] research topic," and frames involvement as a funding requirement ("the researchers we fund have to involve patients, carers[,] [and the] public in prioritising, designing, delivering[,] [and] disseminating research") rather than a rule that a late-added patient question displaces an existing investigator-derived one.
    - NIHR briefing notes for researchers, https://www.nihr.ac.uk/briefing-notes-researchers-public-involvement-nhs-health-and-social-care-research.

### Taxonomy

Every mechanism found for making a human's input take priority is structural, never a scored or weighted field:

- **Turn-taking gate** - the system halts and will not proceed until the human responds (Gemini's `collaborative_planning`, GPT-Researcher's `HumanAgent.review_plan`, LangChain's `clarify_with_user` ending the graph at `__end__`). Priority is achieved by making forward progress conditional on the human's turn, not by comparing content.
- **Unconditional bypass insertion** - the human's text is inserted directly into the state with no LLM judgment call, and structurally triggers re-scoping (Co-STORM's `step(user_utterance=...)`, findings 32-33). This is the one open-source precedent that matches the IR literature's explicit "override" concept (findings 46-47) in shape: no confidence check, no vote, the human's turn simply happens.
- **Recency in what the model conditions on** - the human's words are blended by an LLM into the single artifact everything downstream reads (LangChain's `write_research_brief`, finding 38; Qulac's query interpolation, finding 51). Priority here is positional and probabilistic, not guaranteed.
- **Queue-and-prepend** - the human's new input is explicitly ordered ahead of whatever the system does next, without touching output already produced (OpenAI's steering protocol, finding 41).
- **Assigned governance role** - a designated party (a named business role, "the customer," a weighted stakeholder) holds the priority call by policy, independent of any single requirement's origin (MoSCoW, Karlsson & Ryan, weighted-stakeholder schemes, findings 54-59).
- **Disclosure without precedence** - the stakeholder's input is guaranteed a place and must be logged, but no rule states it outranks investigator- or system-derived content (PROSPERO, Cochrane, findings 60-64).

None of the six families implements SPEC-023 D-02's phrasing ("weigh more") as an actual weight or score. The closest normative statement that human input should structurally win a stated conflict is the IR literature's "override" (findings 46-47) and "reverts to user" (finding 48); the closest working code precedent is Co-STORM's unconditional bypass (findings 32-35); the closest precedent that also bounds the human's repeated objections is GPT-Researcher's revision ceiling (findings 36-37).

### Contradictions

- Findings 46-48 state a clean normative rule (the human's stated input should override or interrupt the system's initiative), but finding 52 found no universal empirical dominance of user-initiated turns over system-initiated ones for outcome quality. The two are not opposed: 46-48 describe who wins when there is a stated conflict; 52 describes which party's move produces a better result on average when there is no conflict yet. A planner should keep these as separate claims.
- Round one's finding 30 (B-30) named Gemini's `collaborative_planning` as "the only vendor precedent for a human-editable plan across turns" without characterizing the mechanism. Finding 39 refines this: the mechanism is a blocking gate, not an editable/merged plan artifact, and finding 40 found no vendor-documented merge rule at all. This narrows rather than reverses B-30.

### Gaps

- No source in any of the four families (open-source code, vendor docs, IIR literature, RE/systematic-review literature) states an explicit rule of the form "a human-originated question is scored or weighted higher than a system-generated one." Every mechanism found is structural (gates, bypasses, positional recency, role assignment, disclosure) rather than comparative. If Compass wants SPEC-023 D-02's "weigh more" implemented as an actual comparison rather than a structural guarantee, no precedent surveyed provides one to adapt; only Co-STORM's unconditional-bypass shape (findings 32-35) and GPT-Researcher's bounded-revision loop (findings 36-37) are ready-made code precedents for a structural mechanism.
- No documented case was found, in Cochrane or PROSPERO material, of a protocol actually amended because a stakeholder's question outranked an investigator-derived one (finding 63's "consumers matter" is documented; "consumer input outranks" is not). This gap was searched directly and came up empty rather than being unexamined.
- Perplexity's internal mechanism for follow-up steering (finding 43) remains undocumented; its Help Center page on 2026 mid-run follow-ups returned HTTP 403 on direct fetch twice and was read only via a secondary paraphrase.
- ISO/IEC/IEEE 29148's exact clause on the requirement "Source" attribute (finding 58) was not read from the primary standard, which is paywalled; the traceability-versus-priority distinction rests on secondary RTM literature.
