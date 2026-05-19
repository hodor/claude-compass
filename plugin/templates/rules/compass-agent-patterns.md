---
paths:
  - .claude/agents/**
  - .claude/skills/**
---

# Compass Agent Writing Style

How to write Compass agent and skill prompts. HumanLayer voice: short, direct, no scaffolding.

## Voice

- Imperative verbs. "Read it.", "Stop.", "Don't."
- Second person.
- One short sentence per rule.
- No qualifiers ("please", "try to", "it would be best if").
- No em-dashes or en-dashes. Use `-`, commas, or rewrite.

## Structure

- Plain markdown. No `<role>`/`<task>` XML scaffolding unless it adds real structure.
- One identity sentence at the top, then the protocol.
- Numbered protocol steps; each step is a verb.
- One `## Failure modes worth naming` list at the end, 3-5 bullets max.
- No closing `=== REMINDER ===` blocks. No duplicate "What NOT to Do" lists.

## Don't pad

- Don't include "Bad/Good Examples" sections if the protocol already makes the rule clear.
- Don't restate the same rule in CRITICAL fences, prose, and a bullet list. Pick one.
- Don't write the rule three times in different words.
- Don't write an example pair where one terse line in the protocol would do.

## Frontmatter

```yaml
---
name: agent-name
description: "Use when [concrete trigger]. [What it does]. [Key constraint]."
tools: [minimum needed]
disallowedTools: [if read-only: Write, Edit, NotebookEdit]
skills: [obsidian, methodology, lessons - include what's needed]
model: inherit
effort: high
maxTurns: [15-60 based on complexity]
color: [unique per agent]
memory: project
initialPrompt: "Read these files now: .compass/index.md, .compass/active.md, .compass/meta/lessons-catalog.yaml"
permissionMode: [bypassPermissions for write agents; omit for read-only]
---
```

## Output rules

Inline the relevant constraints directly in each agent's prompt - one source of truth per agent, no shared global file. The common ones, applied where they matter:

- Use `file:line` refs, never paste code (exception: `pattern-finder`, whose contract is showing snippets).
- Show commands and verbatim output, not descriptions of what you would do.
- Omit empty sections in any output template - don't stub them.
- No editorial sections (Suggested Follow-ups, Maintenance Assessment) unless the agent's contract is editorial.
- Open with the result. No preamble, no "I'll help you", no recap.
- Bound length per field where you can: "(2-3 sentences)", "(one line)".

Pick the subset each agent actually needs and write it into that agent's prompt. Don't reach for a global rule file.
