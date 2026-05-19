---
name: research-papers
description: Investigate an academic paper, algorithm, or technique using the citation graph - Current (the paper itself), Backward (ancestors / why it works), Forward (descendants / how it evolved). Output is a research document saved to .compass/research/.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Bash, Agent]
when_to_use: "Use when the user wants to research a paper, algorithm, or technique deeply. Triggers: 'research this paper', 'explain this algorithm', 'deep research on X', 'go through the citations of', 'what's the prior art for'."
argument-hint: "<arxiv ID, HF paper URL, or topic>"
---

# Research Papers - Citation-Graph Deep Research

For going deep on a technique, paper, algorithm, or implementation. Spawns three researchers in parallel to cover three perspectives, then a reviewer to consolidate.

```
        (Backward - why it works)
              ↓
    ┌─────────────────────┐
    │ The thing itself    │   (Current - what it is)
    └─────────────────────┘
              ↓
        (Forward - how it evolved)
```

Unlike code research, paper findings deserve more prose. You're conveying ideas, math, and arguments, not just locations. But the citation discipline is the same: reference papers by ID/title and section/page (or arXiv equation/figure number), don't quote long passages. Short ≤125-char quotes only when the exact wording matters.

## Initial response

When invoked without a clear target, respond exactly:

```
Ready to research a paper. Give me an arXiv ID, an HF paper URL, or the topic and I'll find the seminal paper.
```

Then wait.

## Protocol

### 1. Read the hot path

`.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`. Check `.compass/research/` for prior work on this paper or topic - don't duplicate.

### 2. Identify the seminal paper

If the user gave an arXiv ID or URL, parse it (see `/compass:papers`). If they gave a topic, use `/compass:papers` search to find candidates and present the top 3 with one-line summaries. Pick one with the user before spawning sub-agents.

### 3. Spawn three `researcher` agents in parallel

Spawn three instances of the `researcher` agent, one per perspective. They use `/compass:papers` for fetching. Brief each one explicitly:

**Researcher A - Current (the paper itself):**

> Use `/compass:papers` to fetch arXiv {ID} as markdown plus metadata. Read it fully. Follow the GitHub repo link if present and read the implementation. Document: what it does, how it works (key equations, algorithm sketch by section), authors' claims, stated assumptions and limitations, linked models / datasets / spaces. Reference by `arXiv:{ID} §{section}` or `arXiv:{ID} Eq. {N}` or `arXiv:{ID} Fig. {N}`. Quote sparingly (≤125 chars) only where exact wording matters.

**Researcher B - Backward (ancestors):**

> Use `/compass:papers` to fetch arXiv {ID}, extract the References. For each significant cite (Related Work, Background, Method sections), use `/compass:papers` again to fetch it. Answer: what insights did this paper inherit? What prior work does it build on? Reference each cite by `arXiv:{ID}` or the canonical title. Build the ancestor graph.

**Researcher C - Forward (descendants):**

> Use `/compass:papers` search with keywords from the original's title and key concepts. Find newer papers building on it. Check the HF paper page's linked models / datasets for real-world implementations. Answer: what have others done with this? What limitations did they hit? What extensions exist? Reference each by `arXiv:{ID}` or HF URL.

### 4. Consolidate with the reviewer

Spawn `reviewer` with the three researcher outputs. The reviewer builds the convergence matrix, surfaces contradictions and gaps, and produces a single consolidated report. Filter ruthlessly - keep substantive divergence, drop restated context.

### 5. Gather metadata

```bash
date +%Y-%m-%d
```

### 6. Write the research document

`.compass/research/RESEARCH-<paper-slug>.md`. This document can run longer than a code-research doc; the goal is to give a planner enough understanding to design an implementation without having to read every paper themselves.

```markdown
---
title: "Research: [Paper / Technique Name]"
type: research
status: complete
confidence: medium
area: <area>
tags: [papers, citation-graph, <technique-keywords>]
created: YYYY-MM-DD
updated: YYYY-MM-DD
author: paper-research
seminal_paper: "arXiv:{ID}"
---

# Research: [Paper / Technique]

## Question
[What the user asked]

## Seminal Paper
- **Title:** [title]
- **Authors:** [authors]
- **arXiv:** [{ID}](https://arxiv.org/abs/{ID})
- **Code:** [GitHub repo if present]
- **Year:** [year]

## The Idea (Current)
[Multi-paragraph explanation of what the paper does. Walk through the algorithm at a level of detail a planner would need. Reference equations and figures by number (`Eq. 3`, `Fig. 2`, `§4.1`). Quote only when wording is load-bearing, ≤125 chars.]

## Why It Works (Backward / Ancestors)
[Where the ideas came from. Which prior papers contributed what insight. Build the lineage as a short narrative, then list the key ancestor papers with one-line each.]

### Ancestor Papers
- `arXiv:{ID}` - [title] - what it contributed
- `arXiv:{ID}` - [title] - what it contributed

## What Others Built (Forward / Descendants)
[How the field used this paper. Real implementations, follow-up papers, extensions, known limitations encountered in practice.]

### Descendant Papers
- `arXiv:{ID}` - [title] - one-line summary
- HF model: [URL] - real-world implementation

## Trade-offs and Limitations
[Stated by authors + observed by descendants. Be concrete.]

## Implementation Notes for a Planner
[What an implementer needs to know that isn't obvious from the paper alone. Gotchas surfaced by descendants. Dependencies (specific libs, datasets, hardware). Approximations that are safe vs unsafe.]

## Open Questions
[Anything the citation graph didn't resolve.]

## References
[Full citation list, alphabetized or by paper section. Use `arXiv:{ID}` or full BibTeX-like entries.]
```

### 7. Update index.md - REQUIRED

Add a link to `.compass/index.md` under `## Research`.

### 8. Present and offer follow-up

> "Saved to [[RESEARCH-name]]. Follow-up questions, or move to planning?"

## Failure modes worth naming

- Quoting long passages instead of referencing `arXiv:{ID} §{section}` or `Eq. {N}`.
- Skipping the GitHub repo for the seminal paper. If code exists, read it.
- Treating Backward as optional. Ancestors explain *why* the design works.
- Spawning all three before identifying the seminal paper.
- Compressing the algorithm walkthrough so much that a planner can't use it. Paper research earns prose budget that code research does not.
- Pasting equations as MathML / LaTeX blobs. Reference them: `arXiv:{ID} Eq. 3`.
