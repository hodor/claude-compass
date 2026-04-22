---
name: research
description: Investigate a topic by spawning researcher agents. Supports single-topic, multi-axis parallel, and deep (citation graph) research modes. Consolidates via the reviewer.
version: 1.0.0
allowed-tools: [Agent]
when_to_use: "Use when the user wants to research something. Triggers: 'research this', 'investigate', 'find out how X works', 'what are the options for', 'deep research'."
argument-hint: "[deep] <research question>"
---

# Research — Spawn Researcher Agents

Three modes depending on the question:

## Mode 1: Single Topic

One question, one area. Spawn one `researcher` agent.

## Mode 2: Multi-Axis Parallel

Multiple research axes (e.g., codebase patterns, web documentation, tool behavior). Spawn one `researcher` per axis in parallel, then spawn the `reviewer` to consolidate.

## Mode 3: Deep Research (Citation Graph)

For going deep on a technique, paper, algorithm, or implementation. Understanding requires THREE perspectives:

```
        (Backward — why it works)
              ↓
    ┌─────────────────────┐
    │ The thing itself    │   (Current — what it is)
    └─────────────────────┘
              ↓
        (Forward — how it evolved)
```

Spawn three researchers in parallel, each with a distinct charter:

**Researcher A — Current (Deep Source):**
- Use the `/compass:papers` skill to fetch the paper as markdown and its metadata
- Read the paper and follow the GitHub repo link for source code
- Understand exactly what it does, how it works, authors' claims
- Note assumptions, limitations, and stated trade-offs
- List the linked models/datasets/spaces (real implementations)

**Researcher B — Backward (Ancestors):**
- Read the paper's References/Bibliography (from the markdown)
- For each significant reference, use `/compass:papers` to fetch it
- Focus on papers cited in Background, Related Work, or Method sections
- Answer: why does it work the way it works?
- Build the ancestor graph — what prior work the original builds on

**Researcher C — Forward (Descendants):**
- Use `/compass:papers` search to find papers citing the original's keywords
- Check the HF paper page's linked models/datasets for real implementations
- Look at arXiv for newer work on the same topic
- Answer: what have others done with this?
- Provides inspiration for the plan

Then spawn the `reviewer` to consolidate all three perspectives.

## Protocol

### Step 1: Classify the Question

- Is it a quick feasibility check or API lookup? → Mode 1
- Does it have multiple independent axes? → Mode 2
- Is it about a specific paper, algorithm, technique, or implementation that matters deeply? → Mode 3

If the user invoked with `deep` as the first argument, use Mode 3.

### Step 2: Spawn Researchers

Per the chosen mode. For Mode 3, be very explicit in each researcher's charter about which perspective they own:

```
Researcher A charter: Use /compass:papers to fetch the paper at arXiv {ID}
as markdown and metadata. Read it fully. Follow the GitHub repo link and
read the implementation. Understand exactly what it does and how. Note
assumptions, limitations, authors' stated trade-offs. List all linked
models and datasets (real implementations).

Researcher B charter: Use /compass:papers to fetch the paper, then extract
the References section. For each significant reference (especially those
in Related Work, Background, or Method), use /compass:papers again to
fetch that cited paper. Answer: what core insights did this paper
inherit? What prior work does it depend on?

Researcher C charter: Use /compass:papers search with keywords from the
original paper's title and key concepts. Find newer papers that build on
it. Also check the HF paper page's linked models/datasets for real-world
implementations. Answer: what have others done with this? What
limitations did they hit? What extensions exist?
```

### Step 3: Consolidate

If multiple researchers were spawned (Mode 2 or 3), spawn the `reviewer` agent to consolidate findings into a single report.

### Step 4: Present to Human

Show the consolidated findings. Save to `.compass/research/RESEARCH-topic-name.md`.

## When to Use Deep Research

- Implementing a specific technique from a paper
- Adopting an algorithm or approach whose internals matter
- High-stakes architectural decisions
- Working with a technology where the foundations matter (not just the API)

## When NOT to Use Deep Research

- Quick feasibility checks
- Looking up syntax or API usage
- Short-term implementation details
- Topics without primary sources (papers, original implementations)
