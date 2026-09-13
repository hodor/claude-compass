---
title: "Research Covers the Whole Spec, From Curated Sources, Until the Plan Is Fully Informed"
type: spec
status: approved
approved: 2026-09-13
confidence: high
area: methodology
tags: [research, pipeline, scope, sources, methodology, open-questions]
created: 2026-09-13
updated: 2026-09-13
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]"]
summary: "research scopes to the whole spec, never the open-questions list; sources are curated and code is read over docs; research runs until the plan is completely informed, spawning more research when it finds it needs it (approved 2026-09-13)"
---

# Research Covers the Whole Spec, From Curated Sources, Until the Plan Is Fully Informed

## Problem

Research tends to focus only on the questions that the spec lists. We need the research to cover the whole spec, not just the open questions. Those open questions are usually done by AI just for the sake of doing so; most of them suck.

Nothing in the pipeline says how research axes derive from a spec. The only research entry points know two shapes, codebase and papers, and the orchestrator improvises the axes. The cheapest derivation is the spec's Open Questions section, because it is already a list of questions. The researcher agent carries a clause telling it to read beyond a narrow brief, but the axes are approved at the human gate before any researcher runs, so the narrow scope is locked in first.

## Decisions (made by the human)

- **D-01:** Research is about the whole spec, always. Multiple agents. The question field is just a question field, something the research might answer already; it is never the scope.
- **D-02:** Open questions are fine to have, and there is no need to gate them. They must not become the center of gravity. If the human has questions, they lead; otherwise the spec is the real lead. Questions the spec lists never lead.
- **D-03:** Research always finds curated points to look: ACM, arXiv, GitHub from reliable sources, which means checking the owner. Never a bunch of blogs only. A blog of a specialist is completely fine for understanding a topic. Which sources are good is researched a bit more, and the good ones are embedded in Compass. The shipped list, from tested access ([[research/pipeline/RESEARCH-source-inventory]]): keyless and reachable are Crossref, OpenAlex, Unpaywall, arXiv, OpenReview v2, and GitHub; Semantic Scholar with its free key; ACM Digital Library, DBLP, and Internet Archive Scholar through the browser; specialist blogs admitted case by case.
- **D-04:** Reading code is a very valid research method, especially to understand how an API works. For everything that code exists, prefer the code, not the API. Download the API and read the API code. Never go with documentation; documentation is always outdated.
- **D-05:** Research completely informs what the plan needs. Research might happen and reveal that more research is needed; that is a normal outcome. Research is a super critical step.
- **D-06:** Research follows a methodology chosen for the case. The research methodologies themselves are researched now, as this spec's own research: how people do surveys and other types of research, and how research scope is defined. Agents choose from the methodologies that research found and follow the one they chose.
- **D-07:** Sometimes there are plugins in the system that give access to more research or more source code. Research makes use of them.
- **D-08 [deferred]:** Shadow libraries (Sci-Hub, LibGen, Anna's Archive, Z-Library) are parked: profiled in [[research/pipeline/RESEARCH-source-inventory]] with their legal position, not on the shipped list, to be revisited.

## Desired Outcome

Every research run for a spec covers the spec as a whole: the problem, the outcome, the constraints, the decisions, the landscape around them. Findings come from sources whose reliability was checked, and from code read directly when the subject is an API or a library. A plan written from the research finds nothing it still needs to look up. When research surfaces a gap it cannot close, another research pass is spawned, not a plan.

## Needs

- A way to derive research scope from a whole spec, so that the axes presented at the gate span the spec rather than mirror its question list.
- A catalog of research methodologies, found by research and shipped inside Compass; the agent chooses one for the case and states it in the document.
- Source curation: reliability is checked and recorded, and a specialist's blog is admitted as a source while an uncurated pile of blogs is not.
- A curated source list shipped inside Compass, found by research and kept as the starting points every research run checks.
- Code over documentation wherever code exists: the code is fetched and read.
- Research plugins present in the session (code search indexes, paper fetchers, MCP servers) are discovered and used.
- A research run can conclude that more research is needed, and that conclusion spawns it.
- The human's own questions weigh more than any question the spec lists.

## Success criteria

- A planner reading a spec's research finds no need it must go and research itself.
- Research axes for a spec are traceable to the spec's sections, not only to its Open Questions.
- Every finding names a source whose reliability was checked, or a file and line in code that was read.
