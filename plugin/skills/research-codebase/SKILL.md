---
name: research-codebase
description: Document the codebase as it exists today by spawning parallel sub-agents (codebase-locator, codebase-analyzer, pattern-finder). Output is a research document saved to .compass/research/. You are a documentarian, not a critic - describe what IS, not what SHOULD BE.
version: 1.0.0
allowed-tools: [Read, Grep, Glob, Bash, Agent, Write, Edit]
when_to_use: "Use when the user wants to research the codebase. Triggers: 'how does X work', 'where is Y handled', 'research this code', 'document this component', 'trace this flow'."
argument-hint: "<research question>"
---

# Research Codebase - Document the Code As It Is

Adapted from HumanLayer's `research_codebase`. Spawns parallel sub-agents to investigate different aspects of a question concurrently, then synthesizes a research document.

## CRITICAL: You and your sub-agents are documentarians, not critics

- Do not suggest improvements, refactors, or "better" approaches.
- Do not perform root-cause analysis unless the user explicitly asks.
- Do not critique the implementation or identify "problems."
- Do not propose future enhancements.
- Only describe what exists, where it exists, how it works, and how components interact.

## Initial response

When invoked without a clear question, respond exactly:

```
Ready to research the codebase. What's the question?
```

Then wait. Don't decompose anything until the user replies.

## Protocol

### 1. Read directly mentioned files first

If the question references specific files (tickets, specs, configs), read them FULLY (no limit/offset) in this context BEFORE spawning any sub-tasks. This ensures decomposition is grounded.

### 2. Read the hot path

`.compass/index.md`, `.compass/active.md`, `.compass/meta/lessons-catalog.yaml`. Check `.compass/.annotations/` for prior notes on relevant files.

### 3. Decompose

Break the question into composable areas: components to investigate, patterns to find, data flows to trace. Plan parallel work.

### 4. Spawn parallel sub-agents

Two pairs plus pattern-finder. Brief them lightly - they know their jobs.

**Code pair:**
- **`codebase-locator`** - where files live (cheap, no Reads, returns paths grouped by purpose)
- **`codebase-analyzer`** - how specific code works (Reads + traces, returns file:line walkthroughs)

**Vault pair:**
- **`vault-locator`** - which vault docs (specs, ADRs, lessons, prior research) relate to the topic (cheap, no Reads, returns paths grouped by type)
- **`vault-analyzer`** - extracts what those docs actually say with section refs

**Patterns:**
- **`pattern-finder`** - concrete examples of patterns already in use (short snippets allowed)

Typical sequence in parallel:
1. Spawn `codebase-locator` and `vault-locator` simultaneously - both are cheap, both filter candidates.
2. When their reports arrive, spawn `codebase-analyzer` on the most promising code paths and `vault-analyzer` on the most relevant vault docs. Both in parallel.
3. Optionally spawn `pattern-finder` if "how do we usually do X" matters for the question.

All sub-agents are documentarians. Remind them in the brief if needed.

### 5. Wait for all sub-agents, then synthesize

Don't synthesize until every sub-agent has reported. Combine findings, prioritize live codebase as source of truth, surface concrete `file:line` references, document cross-component connections.

### 6. Gather metadata

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse --short HEAD
date +%Y-%m-%d
```

### 7. Write the research document

`.compass/research/RESEARCH-<descriptive-slug>.md`:

```markdown
---
title: "Research: [Topic]"
type: research
status: complete
confidence: medium
area: <area>
tags: [codebase, <relevant-component-names>]
created: YYYY-MM-DD
updated: YYYY-MM-DD
git_branch: <branch>
git_commit: <short hash>
author: codebase-research
---

# Research: [Topic]

## Question
[Original question]

## Summary
[High-level description of what was found, answering the question]

## Detailed Findings

### [Component / Area 1]
- What exists, with `file.ext:line` refs
- How it connects to other components
- Implementation details (without evaluation)

### [Component / Area 2]
...

## Code References
- `path/to/file.py:123` - what's there
- `another/file.ts:45-67` - what this block does

## Architecture Notes
[Patterns and conventions found in the codebase]

## Related Vault Documents
- [[SPEC-NNN-name]] - relevant spec (from vault-analyzer)
- [[LESSON-name]] - prior lesson about this area
- [[ADR-NNN-name]] - decision that constrains this work

## Open Questions
[Anything that needs further investigation]
```

### 8. Update index.md - REQUIRED

Add a link to `.compass/index.md` under `## Research`. Research not in index.md is invisible to the next session.

### 9. Promote to GitHub permalinks (optional)

If the branch is pushed:
```bash
git branch --show-current
gh repo view --json owner,name
```
Replace `file:line` refs with `https://github.com/{owner}/{repo}/blob/{commit}/{file}#L{line}`.

### 10. Present and offer follow-up

Summarize the findings inline, point to the saved document, ask:

> "Saved to [[RESEARCH-name]]. Follow-up questions, or move to planning?"

### 11. Handle follow-ups

If the user asks more questions on the same topic, append a `## Follow-up Research - YYYY-MM-DD` section to the same document. Update the `updated` frontmatter field. Don't create a new document unless the follow-up is genuinely a different topic.

## Failure modes worth naming

- Reading entry-point files in the main context AFTER spawning sub-agents (do it before).
- Synthesizing while sub-agents are still running.
- Drifting into evaluation ("this could be better").
- Pasting code instead of `file:line` refs.
- Skipping the `index.md` update.
- Treating the question as the full scope. Sub-agents should also surface things the asker didn't think to ask.
