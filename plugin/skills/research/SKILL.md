---
name: research
description: Investigate a topic by spawning researcher agents. Supports single-topic, multi-axis parallel, and deep (citation graph) research modes. Consolidates via the reviewer.
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use when the user wants to research something. Triggers: 'research this', 'investigate', 'find out how X works', 'what are the options for', 'deep research'."
argument-hint: "[deep] <research question>"
---

# Research - Spawn Researcher Agents

Hand the researcher the full spec, not a curated question list. Pre-filtering biases the investigation - the agent goes into checklist mode and misses what an implementer actually needs.

The brief shape: "Read [[SPEC-NNN]]. Investigate everything needed to plan this implementation. The spec describes the NEED. Cover at minimum [domain, implementation options, existing solutions, open questions]. Don't limit yourself to these - surface anything an implementer would need."

Open questions in the spec are starting points, not the full scope.

## Modes

### Mode 1 - Single topic

One question, one area. Spawn one `researcher`.

### Mode 2 - Multi-axis parallel

Spawn one `researcher` per genuinely independent dimension (e.g., frontend / backend / deployment) in parallel, then spawn `reviewer` to consolidate. Don't split when you're really just decomposing sub-questions - that's biasing again. When in doubt, use Mode 1.

### Mode 3 - Deep research (citation graph)

For going deep on a paper, algorithm, or implementation. Three perspectives:

```
        (Backward - why it works)
              ↓
    ┌─────────────────────┐
    │ The thing itself    │   (Current - what it is)
    └─────────────────────┘
              ↓
        (Forward - how it evolved)
```

Spawn three researchers in parallel:

- **Researcher A - Current:** use `/compass:papers` to fetch the paper as markdown + metadata. Read it fully. Follow the GitHub repo. Understand exactly what it does. Note assumptions, limitations, stated trade-offs. List linked models/datasets.
- **Researcher B - Backward (ancestors):** extract References. For each significant cite (Related Work, Background, Method), fetch with `/compass:papers`. Answer: what insights did this paper inherit?
- **Researcher C - Forward (descendants):** search `/compass:papers` with keywords from the title and key concepts. Check HF paper page for linked models/datasets. Answer: what have others done with this?

Then spawn `reviewer` to consolidate.

## Protocol

### 1. Classify

- Quick feasibility or API lookup → Mode 1.
- Multiple independent axes → Mode 2.
- Specific paper/algorithm/technique that matters deeply → Mode 3.

If the user invoked with `deep` as the first argument, use Mode 3.

### 2. Spawn

For Mode 3, be explicit about which perspective each researcher owns:

```
Researcher A charter: Use /compass:papers to fetch the paper at arXiv {ID}
as markdown and metadata. Read it fully. Follow the GitHub repo link and
read the implementation. Understand exactly what it does and how. Note
assumptions, limitations, authors' stated trade-offs. List all linked
models and datasets.

Researcher B charter: Use /compass:papers to fetch the paper, then extract
the References. For each significant reference (Related Work, Background,
Method), use /compass:papers again. Answer: what core insights did this
paper inherit? What prior work does it depend on?

Researcher C charter: Use /compass:papers search with keywords from the
original paper's title and key concepts. Find newer papers building on
it. Also check the HF paper page's linked models/datasets for real-world
implementations. Answer: what have others done with this? What
limitations did they hit? What extensions exist?
```

### 3. Consolidate

If multiple researchers were spawned, spawn `reviewer` to merge findings into one report.

### 4. Present

Show the consolidated findings. Save to `.compass/research/RESEARCH-topic-name.md`.

## When to use deep research

- Implementing a specific technique from a paper.
- Adopting an algorithm whose internals matter.
- High-stakes architectural decisions.
- Technologies where foundations matter, not just the API.

Skip for: quick feasibility checks, API/syntax lookups, short-term details, topics without primary sources.
