---
title: "How Iterative Research Decides It Needs Another Pass, and When It Stops"
type: research
status: draft
confidence: high
area: methodology
tags: [research, pipeline, methodology, iteration, stopping-rules, saturation, multi-agent, deep-research]
created: 2026-09-13
updated: 2026-09-13
git_branch: "master"
git_commit: "50a2896"
author: "researcher"
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
summary: "saturation and gap-analysis as human stopping rules, contrasted with the continue/stop code of GPT-Researcher, STORM/Co-STORM, and LangChain's Open Deep Research, plus the published designs of Anthropic's and OpenAI's research agents; three recurring stop-mechanism families found, none of them a coverage-verified sufficiency check"
---

# How Iterative Research Decides It Needs Another Pass, and When It Stops

## Question

When does an iterative research process - a human methodology or an agentic system - decide it needs to run again, and what tells it to stop? This serves [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-05 ("research might reveal it needs more research; that spawns another pass, not a plan") and D-06 (the agent chooses a methodology that research itself found).

## Scope

In scope: saturation and stopping rules in qualitative research and systematic reviews; the scoping-review gap-analysis stage; the actual continuation/termination code and prompts of GPT-Researcher, STORM/Co-STORM, and LangChain's current Open Deep Research; the published architecture of Anthropic's multi-agent research system and OpenAI's Deep Research; a 2026 systematic survey's taxonomy of stopping mechanisms and its documented failure modes.

Out of scope, covered by sibling documents from this same spec: how research axes are initially decomposed from a spec ([[research/pipeline/RESEARCH-scope-derivation-from-a-spec]]); the catalog of methodology types and Wohlin's snowballing stopping criterion itself ([[research/pipeline/RESEARCH-research-methodologies-catalog]]); source-reliability judgment ([[research/pipeline/RESEARCH-source-reliability-criteria]]).

## Methodology

Technology-landscape / comparative-evaluation survey (per the `obsidian` skill's research-approach table): six systems and methodologies are profiled on the same dimension - what triggers another pass, what triggers stopping, and what fails when either judgment is wrong - so they compare side by side. Two passes ran in parallel: direct reads of primary academic sources (WebSearch plus a full direct read of arXiv:2512.02038's 87-page PDF, pages 1-16, 28-30, 39-41, 45-48) and three code-reading passes that cloned repositories into a scratchpad and read the orchestration/loop modules line by line, per [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-04. Repository reliability was checked before reading: `assafelovic/gpt-researcher` (29,430 stars, active individual maintainer, pushed 2026-08-27), `stanford-oval/storm` (31,299 stars, academic-lab org), `langchain-ai/open_deep_research` (12,679 stars, official vendor org, pushed 2026-08-10).

## Findings

### Human methodology: saturation and gap-analysis as stopping rules

1. **Theoretical/code saturation is an empirically discovered stopping point, not a preset rule** (confidence: medium)
   Guest, Bunce & Johnson (2006) operationalized "saturation" - the point where no new themes appear - by coding 60 interviews and tracking when new codes stopped appearing. They found 80% of eventual codes present within 6 interviews and full code saturation by interview 12, in a study designed around a narrow, pre-familiarized health topic.
   - Field Methods 18(1):59-82, DOI:10.1177/1525822X05279903 - read via WebSearch summary of the paper (Semantic Scholar, SAGE listing), not fetched directly (paywalled).

2. **Saturation is topic- and heterogeneity-dependent, so "12 is enough" does not generalize as a number** (confidence: medium)
   A 2017 multisited follow-up (cross-cultural water-issues study, 132 respondents, 4 sites) found only 16 or fewer interviews sufficed for common themes within a homogeneous site, but reaching saturation for **metathemes that cut across all sites** needed 20-40 interviews. Hennink, Kaiser & Marconi (2017) separately distinguish "code saturation" (all codes identified) from "meaning saturation" (full depth of understanding), which saturate at different interview counts.
   - Field Methods 2017-Feb, EJ1137557 (ERIC); Hennink et al. 2017, *Qualitative Health Research* - both read via WebSearch summary, not fetched directly.

3. **A scoping review's stage 5 is where gap identification formally happens, and its own designers say it lacks a systematic method** (confidence: high)
   Levac, Colquhoun & O'Brien (2010) extend Arksey & O'Malley's stage 5 ("collating, summarising, reporting") into three explicit steps: (1) descriptive numerical + thematic analysis, (2) reporting results against the review's purpose, (3) "interpreting the findings in the context of ... future research, practice, and policy" - this third step is where gap analysis occurs. They flag stage 5 as having "no clear guidance on how to systematically accomplish" the synthesis, unlike the more mechanical stages 2-4.
   - Levac et al. 2010, *Implementation Science* 5:69, DOI:10.1186/1748-5908-5-69 - read via WebSearch summary.

4. **Wohlin's snowballing stopping rule is the closest human-methodology analogue to a coverage-verified halt, and is already catalogued elsewhere in this spec's research** (confidence: high)
   Snowballing iterates backward/forward reference-following until an iteration adds zero new papers - a structural "nothing left to find" test, not a model-judged or fixed-count one. Full mechanics, citation, and the "should not be seen as an alternative to database search" caveat are in [[research/pipeline/RESEARCH-research-methodologies-catalog]] (findings 26-27); not restated here beyond noting it belongs in the same taxonomy as the agentic mechanisms below.

### Academic taxonomy of agentic stopping mechanisms (arXiv:2512.02038, "Deep Research: A Systematic Survey")

5. **Sequential-planning systems make an explicit per-turn stop/continue decision as a first-class step** (confidence: high)
   S3 and AI-SearchPlanner: "At each turn, the sequential planner evaluates the evolving evidence state and decides whether to retrieve additional context or to stop." This is presented as the general pattern sequential (as opposed to parallel/one-shot) planners follow.
   - arXiv:2512.02038 §3.1.2, p.11.

6. **LLatrieval's loop condition is explicit verification failure, and ReSP explicitly disallows repeating a question to prevent redundant retrieval** (confidence: high)
   LLatrieval "repeat[s] the cycle until the accumulated context fully supports a verifiable answer," triggered "whenever the current documents fail verification." ReSP issues new sub-questions "explicitly targeted at identified information gaps whenever the currently accumulated evidence is deemed insufficient," and mitigates "over-planning and redundant retrieval" specifically **by disallowing previously issued sub-questions**.
   - arXiv:2512.02038 §3.1.2, p.11.

7. **Adaptive retrieval timing is classified into four trigger families, all answering "do I need to look something up right now"** (confidence: high)
   Probabilistic (low next-token confidence), Consistency-based (Rowen: cross-model/cross-lingual disagreement), Internal-States Probing (CtrlA, UAR, SEAKR: reading the model's own hidden states), and Verbalized (ReAct's action text, Self-RAG's `<retrieve>` token, Search-o1's Reason-in-Documents module). The survey frames the field's trajectory as moving from fixed/per-step retrieval toward reasoning-and-reflection-driven timing, then toward RL-trained retrieval policies (Search-R1).
   - arXiv:2512.02038 §3.2.2, pp.14-16.

8. **Over-iteration is a named failure mode with a stated causal mechanism, distinct from "wrong" stopping** (confidence: high)
   "Excessive reasoning turns or overly long reasoning chains can incur substantial computational costs and latency," and critically, "an increased number of turns may introduce cumulative noise and error propagation, potentially causing instability" - more iteration is not monotonically safer; it has its own failure mode.
   - arXiv:2512.02038 §3.1.2, p.11.

9. **Two named RL-training failure modes specifically strike multi-turn iterative research loops** (confidence: high)
   *Void turns*: responses that don't advance the task (fragmented text, repetitive content, or **premature termination**) - once produced, these "propagate through later turns, creating a harmful feedback loop"; SimpleTIR mitigates by filtering trajectories containing them. *Echo Trap*: the model abandons exploration and "repeatedly produces conservative outputs that yield short-term rewards," a self-reinforcing collapse into shallow, repetitive behavior with reward-variance and entropy collapse; StarPO-S mitigates via uncertainty-based trajectory filtering. Both are documented causes of training collapse specifically in the multi-turn setting, not in single-turn RL.
   - arXiv:2512.02038 §6.3.1, p.46.

10. **The field's closest thing to a research-completeness metric is "key points coverage," and it exists only for long-form report evaluation, not as a live stopping signal** (confidence: high)
    Phase II (Integrated Research) evaluation "shifts from superficial short-form lexical matching to long-form quality," listing "fine-grained factuality," "verified citations," "structural coherence," and "key points coverage" as the criteria - all measured post hoc against a finished report, via LLM-as-judge, because "there is no single gold-standard answer." No system surveyed uses a coverage metric as an in-the-loop stop condition.
    - arXiv:2512.02038 §2.2 (Table 1, p.8) and §5.2.2, pp.39-40.

11. **Long-form synthesis has a documented logical-coherence failure mode distinct from factual hallucination** (confidence: high)
    "The generated reasoning may contain gaps, abrupt leaps, or even circular justifications" when models synthesize insights from multiple retrieved documents - a fluency/plausibility problem that survives even when individual facts are correct, which the survey calls out as an open, narrowly-benchmarked evaluation challenge.
    - arXiv:2512.02038 §6.4.1, p.47.

### GPT-Researcher (code read directly)

12. **The "deep research" mode's stop condition is a depth countdown, not a sufficiency check** (confidence: high)
    `deep_research()` recurses with `if depth > 1: new_breadth = max(2, breadth // 2); new_depth = depth - 1`, terminating purely when `depth` reaches its floor. Defaults: `deep_research_breadth=4`, `deep_research_depth=2` (code-level `getattr` fallback) vs. `DEEP_RESEARCH_BREADTH: 3`, `DEEP_RESEARCH_DEPTH: 2` (shipped config file) - the two default sources disagree slightly, both are small (2-4).
    - `gpt_researcher/skills/deep_research.py:247-249,534-536`; `gpt_researcher/config/variables/default.py:39-41`.

13. **"Another pass" is triggered by LLM-authored follow-up questions built from the prior pass's own output, not from a structural gap check** (confidence: high)
    Each recursion extracts `learnings` and `followUpQuestions` per query via an LLM call, and the next level's query is built directly from `researchGoal` + `followUpQuestions`. This is real gap-driven re-scoping in mechanism, but the "gap" is whatever the model claims it still wants to know, not a diff against the accumulated report.
    - `gpt_researcher/skills/deep_research.py:346-378,409-417,539-543`.

14. **Two hard-coded guards stop descent on empty results rather than recursing on nothing** (confidence: high)
    If zero sub-queries are generated, or every generated sub-query fails to return results, the recursion halts instead of continuing one more level - the comment cites a specific GitHub issue (#1579) as the motivating bug report. URL-level dedup (`all_visited_urls`) exists across levels; there is no dedup of the search-query strings themselves.
    - `gpt_researcher/skills/deep_research.py:409-417,496-514,519,557`.

15. **A separate LangGraph pipeline in the same repo (`multi_agents/`) uses bounded revision loops that critique style/guideline-conformance, not coverage** (confidence: high)
    Two independent critique loops (`researcher -> reviewer -> reviser`, and `writer -> fact_checker -> writer`) each carry a hard revision ceiling (`DEFAULT_MAX_DRAFT_REVISIONS = 3`, `DEFAULT_MAX_FACT_CHECK_REVISIONS = 3`); exceeding the ceiling raises a typed exception (`MaxDraftRevisionsExceededError`) that a graph edge catches and force-accepts the current draft rather than looping forever. The reviewer's own prompt reviews against user-supplied `guidelines` (style/structure), not against missing facts - confirmed by its literal prompt text: "review the draft ... based on specific guidelines." Each section's research runs once, before this critique loop starts; the loop cannot trigger new research, only textual revision.
    - `multi_agents/agents/editor.py:136-164`; `multi_agents/agents/reviewer.py:4-5,34-41,68-87`; `multi_agents/agents/draft_review.py:1,23-29`; `multi_agents/agents/orchestrator.py:100-135`; `multi_agents/agents/fact_review.py:1`.

### STORM / Co-STORM (code read directly)

16. **Base STORM's per-conversation stop signal is a literal string match on a magic phrase the model is prompted to emit** (confidence: high)
    The `AskQuestion`/`AskQuestionWithPersona` prompt instructs: "If you have no more question to ask, say 'Thank you so much for your help!' to end the conversation." The loop checks `user_utterance.startswith("Thank you so much for your help!")` to break, alongside a `max_turn` countdown (default 3) as a hard ceiling regardless of what the model says.
    - `knowledge_storm/storm_wiki/modules/knowledge_curation.py:60-79,128-136`; `knowledge_storm/storm_wiki/engine.py:134-137`.

17. **The only quantitative, embedding-based gap-detection mechanism found in any system surveyed lives in Co-STORM's Moderator** (confidence: high)
    `Moderator._get_conv_turn_unused_information` collects every retrieved snippet that was never cited, then scores each by a weighted combination of `(1 - similarity to the queries already asked)` and `(1 - similarity to already-cited snippets)`, gated by a claim-relevance threshold (cosine similarity >= 0.25 to the turn's own claim) - i.e., it surfaces information that is topically relevant but was never used and doesn't overlap what's already been asked or cited, then turns the top-ranked snippet into a new question via `GroundedQuestionGenerationModule`. This is structural gap-detection over the knowledge actually retrieved, not model self-report.
    - `knowledge_storm/collaborative_storm/modules/co_storm_agents.py:159-297` (class docstring cites Co-STORM paper §3.5, arXiv:2408.15232).

18. **Co-STORM forces a moderator turn after N consecutive non-questioning turns - a structural stagnation guard, independent of any model judgment** (confidence: high)
    `_should_generate_question` counts consecutive turns since the last question/request; once that count reaches `moderator_override_N_consecutive_answering_turn` (default 3), `get_next_turn_policy` routes the next turn to the Moderator regardless of what any agent "wants" to do next. This exists specifically "to avoid stagnation, repetition, or overly niche discussions," per the `Moderator` class docstring.
    - `knowledge_storm/collaborative_storm/engine.py:245-249,408-422,478-484`; `knowledge_storm/collaborative_storm/modules/co_storm_agents.py:159-166`.

### LangChain's current Open Deep Research (code read directly)

19. **The supervisor's continue/stop decision is an explicit tool choice, gated by a hard iteration ceiling** (confidence: high)
    The `supervisor` node always routes to `supervisor_tools`, which inspects which tool the model called (`ConductResearch` -> continue delegating; `ResearchComplete` -> `Command(goto=END)`) and separately enforces `research_iterations > max_researcher_iterations` (default 6) as a hard cap independent of what the model chose. `max_concurrent_research_units` (default 5) separately caps parallel sub-agents.
    - `src/open_deep_research/deep_researcher.py:178-262,346-349`; `src/open_deep_research/configuration.py:64-65,94-95`.

20. **`think_tool` is a plain reflection call with no control-flow power of its own - it only matters because the next LLM call reads its output** (confidence: high)
    `think_tool` is a `@tool`-decorated function that returns the string `"Reflection recorded: {reflection}"` as a `ToolMessage`; the graph routes purely on which tool the model calls *next*, so reflection changes behavior only by being in context for the following decision, not by branching the graph itself.
    - `src/open_deep_research/utils.py:219-244`; `src/open_deep_research/deep_researcher.py:274-280`.

21. **A redundancy-based stopping heuristic is written directly into the prompt, not enforced in code** (confidence: high)
    `research_system_prompt`'s "Prevent excessive searching" hard limits instruct the sub-agent to stop "When... your last 2 searches returned similar information" - a redundancy signal expressed in natural language for the model to self-apply, alongside the numeric `max_react_tool_calls` (default 10) ceiling that is enforced regardless.
    - `src/open_deep_research/prompts.py:164-174`; `src/open_deep_research/configuration.py:107-108`; `src/open_deep_research/deep_researcher.py:492`.

22. **An individual sub-agent's own ReAct loop ends on whichever of three conditions fires first** (confidence: high)
    Checked together in `researcher_tools`: (a) `tool_call_iterations >= max_react_tool_calls`, (b) the model calls `ResearchComplete`, or (c) the model returns no tool calls, which routes straight to compression. No sufficiency scoring - just a race between a model-issued "done" signal and two mechanical caps.
    - `src/open_deep_research/deep_researcher.py:457-464,491-509`.

23. **Findings are compressed per sub-agent before the supervisor's next decision, but never deduplicated across sub-agents** (confidence: high)
    `compress_research` runs an LLM pass that removes "obviously irrelevant or duplicative information" *within* one sub-agent's output before returning it; at the supervisor level, multiple sub-agents' compressed notes are only concatenated (`raw_notes_concat`), with no further dedup step before the supervisor's next continue/stop decision reads them.
    - `src/open_deep_research/deep_researcher.py:324-330,511-585`; `src/open_deep_research/prompts.py:186-222`.

### First-party design: Anthropic and OpenAI

24. **Anthropic's lead agent stops on its own "sufficient information" judgment - there is no disclosed hard iteration cap** (confidence: high)
    The published architecture states the lead agent "synthesizes results, decides whether more research is needed - if so, can create additional subagents or refine its strategy," and exits the loop "once sufficient information is gathered." No fixed iteration counter or token budget is stated anywhere in the source.
    - anthropic.com/engineering/multi-agent-research-system, "Architecture overview for Research" section.

25. **The reflection mechanism is extended/interleaved thinking used as a scratchpad, not a separate architectural gate** (confidence: high)
    The lead agent "uses thinking to plan its approach... determining subagent count," and subagents "use interleaved thinking after tool results to evaluate quality, identify gaps, refine next query" - reflection is folded into the same generation step that decides the next action, matching the survey's "Verbalized" retrieval-timing family (finding 7) rather than a distinct checkpoint.
    - anthropic.com/engineering/multi-agent-research-system, "Guide the thinking process" principle.

26. **A prompt-embedded effort-scaling table is the closest thing to a stopping/sizing heuristic, explicitly framed as guidance rather than an enforced rule** (confidence: high)
    "Simple fact-finding: just 1 agent, 3-10 tool calls. Direct comparisons: 2-4 subagents, 10-15 calls each. Complex research: 10+ subagents with clearly divided responsibilities." An independent secondary read of the same system in arXiv:2512.02038 paraphrases this slightly differently ("1-2 agents for factual lookups... up to 10 or more for multi-perspective analyses, each assigned with clear quotas and stopping criteria") - see Contradictions.
    - anthropic.com/engineering/multi-agent-research-system, "Scale effort to query complexity" principle; arXiv:2512.02038 §4.1.1, p.28.

27. **Anthropic names four concrete early-version failure modes that all trace to missing or vague stopping/delegation logic** (confidence: high)
    Early iterations exhibited: spawning 50 subagents for simple queries; agents "scouring the web endlessly for nonexistent sources"; subagents duplicating work on overlapping scope from vague instructions like "research the semiconductor shortage" (no explicit division of labor); and "overinvestment in simple queries," each explicitly named as "common failure mode in our early versions."
    - anthropic.com/engineering/multi-agent-research-system, intro to "Prompt engineering and evaluations for research agents" and principles 2-3.

28. **Separately from research-sufficiency judgment, Anthropic names systemic reliability failure modes of the multi-agent architecture itself** (confidence: high)
    "Agents are stateful and errors compound" - one failed step "can cause agents to explore entirely different trajectories"; agents are non-deterministic "even with identical prompts"; and synchronous execution creates coordination bottlenecks where "the lead agent can't steer subagents" mid-run. These are infrastructure/reliability failure modes, distinct from the stopping-judgment failure modes in finding 27.
    - anthropic.com/engineering/multi-agent-research-system, "Production reliability and engineering challenges" section.

29. **OpenAI's Deep Research has no exposed, engineered continue/stop loop at all - the decision is implicit in an RL-trained policy** (confidence: medium-high)
    OpenAI describes Deep Research as an o3-derivative "trained through reinforcement learning to... search, interpret, and analyze... pivoting as needed in reaction to information it encounters," trained end-to-end on browsing trajectories rather than built as an orchestrated pipeline with an inspectable stop condition. This is the field's clearest example of the "end-to-end RL" optimization family (arXiv:2512.02038 §4.3), as opposed to the "workflow prompting" family every other system in this document belongs to.
    - openai.com/index/deep-research-system-card/ (via WebSearch summary of the system card); arXiv:2512.02038 §4 taxonomy (Table under §4, distinguishing Workflow Prompting / SFT / End-to-End RL).

30. **A documented OpenAI failure mode is "misinformation by omission" - a premature-stop-shaped failure with no stated engineered fix** (confidence: medium)
    Independent commentary on the system card (Simon Willison) notes that while fabricated claims can usually be caught by checking cited references, "it's very possible for the tool to miss out on crucial details because they didn't show up in the searches that it conducted" - i.e., the model can stop (or never branch into) a line of inquiry it never thought to pursue, and nothing in the published design surfaces that as a detectable gap.
    - simonwillison.net/2025/Feb/25/deep-research-system-card/ (secondary commentary on the primary system card).

## Taxonomy

Every stop/continue mechanism found, human or agentic, belongs to one of three families:

- **Fixed budget / countdown.** STORM's `max_turn`/`max_perspective` (finding 16), GPT-Researcher's `deep_research_depth`/`breadth` (finding 12), Open Deep Research's `max_researcher_iterations`/`max_react_tool_calls` (finding 19), and the `multi_agents/` revision ceilings (finding 15) all stop on a number reached, independent of whether the number was actually needed. Simple, auditable, cheap to reason about - and can either stop before sufficiency or run to the cap regardless of need.
- **Model-judged sufficiency.** Anthropic's lead-agent judgment (finding 24), Open Deep Research's `ResearchComplete` tool call (finding 22), base STORM's "no more questions" phrase (finding 16), and the academic sequential planners S3/LLatrieval (findings 5-6) all delegate the stop decision to the model's own self-report. Adaptive, but unverifiable without external ground truth - and the RL literature's own failure modes (void turns, Echo Trap - finding 9) show this specific judgment degrades under training pressure toward premature or shallow stopping.
- **Structural/quantitative gap detection.** Co-STORM's Moderator (finding 17), ReSP's disallow-repeat-question guard (finding 6), and Open Deep Research's "last 2 searches similar" prompt heuristic (finding 21) are the only mechanisms that inspect *what was actually found* - unused evidence, repeated questions, converging search results - rather than either counting turns or asking the model to self-report. This family is also the rarest and most implementation-heavy of the three; only one system surveyed (Co-STORM) implements it as executable code rather than prompt text.

Fixed-budget and model-judged mechanisms are frequently layered together as a belt-and-suspenders pair (Open Deep Research and base STORM both do this: a model-judged "done" signal checked first, a numeric ceiling enforced regardless) - none of the systems surveyed uses structural gap detection as the *sole* stop condition; it is always additional to, not a replacement for, a budget or a self-report.

Human qualitative/review methodology maps onto the same three families: saturation-counting (findings 1-2) is a fixed-budget analogue discovered empirically after the fact rather than set in advance; a scoping review's "sense of the volume and scope of the field" self-assessment ([[research/pipeline/RESEARCH-scope-derivation-from-a-spec]] finding 6) is the model-judged analogue; and Wohlin's "an iteration adds zero new papers" test (finding 4, full detail in [[research/pipeline/RESEARCH-research-methodologies-catalog]]) plus scoping review's stage-5 gap analysis (finding 3) are the structural analogue - the closest human precedent to Co-STORM's unused-snippet detector, run over a citation graph or thematic map instead of embeddings.

## Prior Art

- **GPT-Researcher**: two independent architectures for "another pass" coexist in one repo - a depth/breadth-countdown recursive mode (findings 12-14) and a bounded-revision multi-agent pipeline that never re-triggers research, only re-drafts text (finding 15). Neither implements a structural coverage check.
- **STORM/Co-STORM**: the base system's stopping signal is the weakest of any surveyed (a literal string match on a prompted phrase), but its collaborative extension implements the most sophisticated structural gap-detector found in this survey (finding 17), specifically because Co-STORM's paper names "avoiding stagnation, repetition, or overly niche discussion" as a design goal the base conversation-simulator does not have.
- **LangChain Open Deep Research**: the most explicit, code-legible stop/continue architecture surveyed - a named tool (`ResearchComplete`) the model must choose to call, backstopped by three independent numeric ceilings (iterations, concurrency, tool calls), plus a prompt-level redundancy heuristic. Reflection (`think_tool`) is present but architecturally inert on its own.
- **Anthropic**: the only system whose published design explicitly rejects a fixed budget in favor of judgment-plus-guidance, and the only one that documents, by name, the failure modes that judgment-based stopping produced before it was tuned (finding 27).
- **OpenAI**: the outlier - no engineered loop is exposed at all; the entire continue/stop behavior is a property of a trained policy, which is both the field's most "elegant" answer to the stopping problem and the one with the least inspectable failure surface (finding 30).

## Contradictions

- Anthropic's own blog post states "1 agent, 3-10 tool calls" as the simple-query heuristic; the independent academic survey paraphrasing the same system states "1-2 agents for factual lookups" (finding 26). Not a factual disagreement about the system's behavior, but a discrepancy in exact wording between primary and secondary sources - the survey's number should be treated as a paraphrase, not a verbatim quote.
- OpenAI's end-to-end RL-trained approach (finding 29) and every other system in this document (GPT-Researcher, STORM, Open Deep Research, Anthropic) sit on opposite sides of a real architectural fork the literature itself names as three distinct optimization families - workflow prompting, supervised fine-tuning, end-to-end RL (arXiv:2512.02038 §4). This is a documented fork in the field, not a contradiction between sources to resolve.

## Gaps

- Guest, Bunce & Johnson (2006) and Hennink et al. (2017) (findings 1-2) were read via WebSearch summary only; both are paywalled SAGE journal articles. Confidence would rise from medium to high with direct full-text access.
- The GPT-Researcher `multi_agents/` `ResearchAgent.run_depth_research`'s own internal iteration limits were not traced in detail beyond confirming research runs once before the critique loop starts (finding 15) - worth a closer read if Compass considers adopting a similar per-section bounded-revision pattern.
- arXiv:2512.02038's evaluation appendix (§5, benchmark-by-benchmark detail) was read only at the level cited in findings 10-11; the primary benchmark papers it cites for "key points coverage" (ref. [378] in that survey) were not read directly - if Compass wants to adopt a concrete completeness metric, that primary paper should be fetched next.
- Google's Gemini Deep Research and Perplexity's Deep Research were not investigated for this axis; [[research/pipeline/RESEARCH-scope-derivation-from-a-spec]] (finding 31) already found Perplexity is the only vendor of the three with an explicit stated sufficiency test in official prose, but neither vendor publishes inspectable code, so a follow-up pass here would still be vendor-prose-only.
- No system surveyed implements a numeric or embedding-based completeness score applied to a *finished report* the way Co-STORM's Moderator applies one to a *live conversation* (finding 17). If Compass wants an automatable "does this research still have a gap" check for its own pipeline, this specific mechanism is unbuilt anywhere found in this survey, not merely undocumented - a further pass would need to look at retrieval-augmented fact-verification systems (e.g., the LLatrieval/ReSP family, finding 6) rather than deep-research report generators.

## Follow-up Research - 2026-09-13

Closes two gaps flagged in [[research/pipeline/REVIEW-spec-023-research-consolidation]]: whether any surveyed system checks a finished report for completeness against a source document, and how Co-STORM's warm-start phase seeds its initial mind map from a topic. Ref. [378] in the prior pass's gap note was itself a mistranscription of the PDF's line-wrapped citation; the correct reference for "key points coverage" is **[379]**, not [378] (`arXiv:2512.02038` §2.2, PDF text: `...key points\ncoverage [379]`, confirmed via direct extraction of the paper's own text and its reference list at line 4054). [378] is BrowseComp (Wei et al.), an unrelated browsing benchmark.

### Retrieval-augmented verification family and completeness metrics

31. **LLatrieval and ReSP verify sufficiency per sub-question, never against a whole document** (confidence: high)
    LLatrieval's verify-update loop asks the LLM "whether the retrieval result can support answering the given question" and re-retrieves until it does; ReSP's insufficiency check is scoped to "the current sub-question." Neither mechanism has a unit larger than one question-answer pair, so neither is a structural precedent for scoring a finished multi-section report against a whole spec - the granularity mismatch the prior pass's gap note anticipated is confirmed by reading both papers directly, not just the survey's summary of them.
    - LLatrieval: arXiv:2311.07838 abstract and method description (Li et al., NAACL 2024); code at `github.com/BeastyZ/LLM-Verified-Retrieval`.
    - ReSP: arXiv:2407.13101 abstract (Jiang et al.); dual-memory design targets multi-hop QA context management, not report completeness.

32. **TREC's nugget-recall methodology is the field's actual operational analogue of "key points coverage," and it ships as maintained, runnable code** (confidence: high)
    The AutoNuggetizer framework, from Jimmy Lin's Castorini group at the University of Waterloo, refactors the TREC 2003 QA-track nugget methodology with three LLM stages: a creator extracts atomic nuggets (1-12 words) from source documents against a query, a scorer labels each nugget `vital` or `okay`, and an assigner labels each nugget `support` / `partial_support` / `not_support` against a candidate passage. The primary aggregate metric, Strict Vital Recall, is exactly a coverage-against-ground-truth score computed post hoc on finished text - the mechanism the prior pass found unbuilt anywhere in the deep-research literature exists here, in the IR-evaluation literature instead.
    - `src/nuggetizer/core/types.py:14-21` (`NuggetScoreMode.VITAL_OKAY`, `NuggetAssignMode.SUPPORT_GRADE_3`) and `:79-91` (`ScoredNugget.importance`, `AssignedNugget.assignment`).
    - `src/nuggetizer/core/metrics.py:14-47` (`strict_vital_score = strict_vital_supported / len(vital_nuggets)`).
    - Paper: arXiv:2504.15068 (Pradeep, Thakur, Upadhyay, Campos, Craswell, Lin; SIGIR 2025), building on arXiv:2411.09607 (TREC 2024 RAG Track).
    - Owner check per D-03: `castorini` GitHub org is Jimmy Lin's University of Waterloo research group (122 public repos), Apache-2.0 licensed, last pushed 2026-04-19 - `gh api orgs/castorini` and `gh api repos/castorini/nuggetizer`. 29 stars; per this spec's own X2 finding, organizational affiliation is weighted over star count.

33. **The three nuggetizer prompts are short, windowed, and model-agnostic - exact text confirmed from the shipped templates** (confidence: high)
    - Creator: "Update the list of atomic nuggets of information (1-12 words)... Ensure the updated nugget list has at most {creator_max_nuggets} nuggets... Order them in decreasing order of importance." Runs over sliding windows of source documents (default `creator_window_size=10`), capped at `creator_max_nuggets=30`.
    - Scorer: labels each nugget "vital" (must be present in a good answer) or "okay" (worthwhile but not essential), against the query alone.
    - Assigner: labels each nugget support/partial_support/not_support against a passage, also windowed (default `assigner_window_size=10`).
    - `src/nuggetizer/prompts/prompt_templates/creator_template.yaml`, `scorer_template.yaml`, `assigner_template.yaml` (full text); `src/nuggetizer/models/nuggetizer.py:27-46` (default `gpt-4o` for all three stages, window sizes, nugget caps).

34. **Nuggetizer's native unit of ground truth is (query, source documents), not a spec - repurposing it for SPEC-023's completeness check requires a mapping** (confidence: medium)
    To run this over a finished Compass research document against a spec, an agent would: feed the spec's Problem statement as the `query` and its Decisions/Needs/Success-criteria sections as the `documents` to the creator stage, producing a nugget list; run the scorer stage (same query) to split nuggets into vital/okay; run the assigner stage with the finished research document as the single `passage`/context; read off `strict_vital_score` as the completeness score. This sequence is not documented anywhere in the source - it is the mechanical adaptation implied by the code's own data contract (`Request(query, documents)` in, `AssignedScoredNugget` list out), not a technique the source itself states.
    - `src/nuggetizer/core/types.py:24-39` (`Query`, `Document`, `Request` dataclasses - the only input shape the pipeline accepts).

35. **DeepResearch Bench's RACE framework scores a report against a reference *report*, not a requirements document, using a dynamically-weighted rubric** (confidence: high)
    RACE derives per-task dimension weights and criteria across four fixed top-level dimensions (Comprehensiveness, Depth/Insight, Instruction-Following, Readability), scores both the candidate and a human-written reference report against the same generated criteria, then reports the candidate's score as a ratio to the reference's. This needs a pre-existing high-quality reference report for every task, which a spec is not - specs in this pipeline record a problem and decisions, not a model report to score against.
    - arXiv:2506.11763 (Du, Xu, Zhu, Wang, Mao); code at `github.com/Ayanami0730/deep_research_bench`.
    - Human-alignment: 71.33% pairwise agreement rate vs. 68.44% average inter-human agreement on 50 tasks (paper's own reported figures, read via WebSearch summary, not the PDF directly).

36. **ALCE's claim-recall metric is the earliest report-completeness-adjacent measure, and it runs on an open NLI model rather than an LLM judge** (confidence: high)
    For ELI5-style long-form answers, ALCE has an LLM decompose the gold answer into three sub-claims, then uses TRUE (a T5-11B model fine-tuned on NLI datasets, not a prompted LLM-as-judge) to check whether the generated answer's cited passages entail each sub-claim - "claim recall." The same paper's citation recall/precision metrics use the identical TRUE-entailment mechanism at the sentence level: recall checks whether the concatenation of a sentence's cited documents entails that sentence; precision checks whether removing any one cited document breaks entailment. Human-model agreement is reported at Cohen's kappa 0.698 (recall) and 0.525 (precision).
    - arXiv:2305.14627 (Gao et al.); TRUE model: Honovich et al. 2022.

37. **RAGAS's only ground-truth-requiring metric is context_recall, and it scores retrieval, not the report** (confidence: medium)
    RAGAS's original three reference-free metrics (faithfulness, answer relevance, context relevance) need no ground truth and so cannot check coverage against a spec. `context_recall`, added later to the library, does require a reference answer and measures "the retriever's ability to retrieve all necessary information" - but it scores the retrieval step, not whether the final generated report communicates that information, so it would need pairing with a faithfulness-style check to close the loop to the report text.
    - arXiv:2309.15217 (Es, James, Espinosa Anke, Schockaert; EACL 2024 demo); metric docs at `docs.ragas.io/en/stable/concepts/metrics/available_metrics/` (docs, not code - no ground-truth-coverage metric was found in the paper itself, only in the library's later additions, so this finding rests partly on documentation per the D-04 caveat).

38. **FActScore measures factual precision only; the same paper names no coverage/recall counterpart in its own framework** (confidence: high)
    FActScore breaks generated text into atomic facts and reports the fraction supported by a knowledge source - a precision metric. The official repo's own README distinguishes this from "% respond" and "# facts" (how much the model says at all), explicitly calling FActScore itself "factual precision," not a coverage or recall score against any reference set of required facts.
    - arXiv:2305.14251 (Min et al., EMNLP 2023); `github.com/shmsw25/factscore`.

39. **CoverageBench and the broader nugget-coverage line of TREC IR research score ranked document lists, not generated prose - a second repurposing gap distinct from nuggetizer's** (confidence: medium)
    CoverageBench (arXiv:2603.20034) ships topics, nuggets, relevance labels, and baseline *rankings* - its scored object is a retrieved document list, not free text. LANCER and the NeuCLIR'24 ReportGen dataset it uses do attach nuggets to multi-faceted *report* requests (7,049 human-annotated nugget labels over 19 queries), which is closer to scoring prose, but neither ships a public completeness scorer the way nuggetizer does. This is a second, independent line of nugget-based coverage work from the same TREC lineage as finding 32, evaluated here separately because it targets retrieval rather than report text.
    - arXiv:2603.20034 abstract (Samuel, Yates, Lawrie, Soboroff, Adriaanse, Van Durme, Yang); LANCER: arXiv:2601.22008.

40. **PROXYQA measures report coverage indirectly, by testing whether an independent evaluator can answer curated questions using only the report as context** (confidence: high)
    Rather than matching text against a reference, PROXYQA gives an evaluator model a set of pre-annotated proxy questions per topic and the candidate's generated report as its only context, then scores the report by the evaluator's accuracy answering those questions. This is a materially different completeness-checking shape from nugget matching: it never inspects the report's text for keyword/claim overlap, it tests whether the report *functions* as a sufficient source. The authors report this method is self-consistent and aligns closely with human judgment.
    - arXiv:2401.15042 (Tan et al., ACL 2024); dataset/leaderboard at `proxy-qa.com`.

41. **No source found, in this pass or the prior one, evaluates a research report against a requirements or specification document specifically** (confidence: high that the gap exists, given the search conducted)
    Every completeness-adjacent mechanism found scores a report against one of: a fixed rubric (RACE, ResearcherBench), a reference report (RACE), pre-extracted nuggets from source documents (nuggetizer, CoverageBench/LANCER), or an independent evaluator's ability to answer curated questions (PROXYQA). None takes a requirements-style document (a spec's Problem/Decisions/Needs) as the ground-truth side of a scoring pipeline. The nearest bridge is finding 34's proposed mapping, which is an inference from nuggetizer's code contract, not a technique any source documents.
    - Search terms tried: "requirements coverage checklist verification research report," NLP4RE systematic-mapping results (ISO 29148 NLP framework, ITLingo RSL survey) - these check whether individual requirement *sentences* are well-formed against a writing standard, not whether a downstream document covers a requirements document's content. Two USPTO patents (8079001, 11475654) claim exactly this coverage-verification shape but are non-academic, non-code sources excluded under D-03.

### Co-STORM warm-start: how the initial mind map is derived from a topic

Read directly from `knowledge_storm/collaborative_storm/modules/warmstart_hierarchical_chat.py` (full file, 409 lines) and `knowledge_storm/collaborative_storm/modules/expert_generation.py` (full file) in the clone at `.../scratchpad/iteration/storm/`.

42. **Warm start is a five-stage pipeline, and every stage's only input is a bare topic string** (confidence: high)
    - Stage 1, background research: one LLM-issued query, literally `f"Background information about {topic}"`, answered in "extensive"/"conversational" mode by the same retrieval-augmented answer module used elsewhere in Co-STORM (`get_background_info`, `warmstart_hierarchical_chat.py:167-181`).
    - Stage 2, persona generation: `GenerateExpertModule.forward(topic, num_experts, background_info)` calls the `GenerateExpertGeneral` signature (topic + background_info + topN → free-text `"role: description"` lines), with no facility to pass a focus, section list, or any structured input beyond one background paragraph (`expert_generation.py:6-21,58-76`; `warmstart_hierarchical_chat.py:157-165`).
    - Stage 3, per-expert QA: for each expert, up to `max_turn_per_experts` (default 2) rounds where `WarmStartModerator` generates the next question from `topic + history + current_expert` alone - the question generator never sees the background paragraph or any document, only the running list of prior questions (`warmstart_hierarchical_chat.py:31-47,148-155,196-241`).
    - Stage 4, outline generation: `GenerateWarmStartOutlineModule.forward` first calls `get_draft_outline(topic)`, which asks `WritePageOutline` (`storm_wiki/modules/outline_generation.py:128-137`) for a Wikipedia-style outline from the **topic string alone** - no retrieved evidence, purely the LLM's parametric knowledge - then calls `GenerateWarmStartOutline` a second time with that draft plus the actual discussion transcript to produce the outline actually used (`warmstart_hierarchical_chat.py:259-309`).
    - Stage 5, mind-map insertion: `KnowledgeBase.insert_from_outline_string` parses the outline text mechanically by counting leading `#` characters per line, building a tree by heading level, and silently dropping any heading titled "overview," "summary," or "introduction" (`dataclass.py:514-538`).

43. **The pipeline's evidence-gathering budget is three small, fixed constants, independent of topic complexity** (confidence: high)
    `RunnerArgument.warmstart_max_num_experts=3`, `warmstart_max_turn_per_experts=2`, `warmstart_max_thread=3` - a hard ceiling of 3 experts x 2 turns = 6 expert QA exchanges plus 1 background-research turn, run in parallel threads, regardless of how broad or narrow the topic is.
    - `knowledge_storm/collaborative_storm/engine.py:218-230`.

44. **The tree structure that seeds the knowledge base comes from the LLM's unguided parametric knowledge before any grounding happens, and is only reconciled with real evidence in a second pass** (confidence: high)
    `get_draft_outline` runs with zero retrieved context - it is the same `NaiveOutlineGen`-style call base STORM uses to produce a first-guess Wikipedia-shaped skeleton from the topic name alone. That skeleton is discarded as structure and only kept as inspiration: `GenerateWarmStartOutline`'s prompt explicitly instructs "Do not include sections that are not mentioned in the given discussion history," so the final tree's *content* is evidence-grounded even though its first draft was not.
    - `warmstart_hierarchical_chat.py:259-268,297-309`; `storm_wiki/modules/outline_generation.py:128-137`.

45. **Neither persona generation nor question generation has an input slot for a structured document; both take only free-text strings** (confidence: high)
    `GenerateExpertGeneral` and `GenerateExpertWithFocus` (the latter unused by warm start, reserved for a different Co-STORM entry point) both declare `dspy.InputField`s typed `format=str` for `topic`, `background_info`, and optionally `focus` - there is no field shaped for a list of sections, decisions, or constraints. The same is true of `WarmStartModerator`'s `topic`/`history`/`current_expert` fields.
    - `expert_generation.py:6-40`; `warmstart_hierarchical_chat.py:31-47`.

46. **What swapping a topic string for a structured spec would touch, traced mechanically through the five stages above** (confidence: medium - this is an inference from the code's data contracts in findings 42-45, not a technique the source documents or recommends)
    Every stage's input field is typed as free text, so a spec would have to be flattened into strings before reaching any of them: stage 1's single background query would need to be replaced or supplemented by the spec's own Problem/Decisions/Needs text (skipping the web-search round entirely, or running it per section); stage 2's persona generation would need one call per spec section instead of one call over a single background paragraph, or the `background_info` field would need to carry the whole spec body up front; stage 4's `get_draft_outline` would need to be replaced by a direct parse of the spec's own headings, since generating a wiki-style outline from a spec's *topic* and then reconciling it against discussion history is exactly the two-pass structure this spec's D-01 asks Compass to avoid replicating (see [[research/pipeline/REVIEW-spec-023-research-consolidation]] finding C3 on the deprecated `report_planner_instructions` precedent). No source states this mapping; it is read off the type signatures alone.

### Gaps

- The nuggetizer pipeline's behavior when repurposed for spec-to-report scoring (finding 34) is untested - it was inferred from the data contract, not run against a real Compass spec and research document.
- DeepResearch Bench's RACE paper (finding 35) and RAGAS's metric documentation (finding 37) were read via WebSearch/library-docs summary, not the primary PDF or source, so confidence on their exact scoring formulas is capped at high/medium rather than verified by direct code or paper read, unlike findings 32-33, 42-45.
- Whether any Phase III "AI Scientist" system (arXiv:2512.02038 §2.2) checks a generated hypothesis or experiment plan against a requirements-style input was not investigated; out of scope for this pass, which stayed within Phase II long-form report evaluation per the assigned gap.
