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

The agent frontmatter template and its fields: the `methodology` skill, file `agent-frontmatter.md`.

## Output rules

The constraints to inline in each agent's prompt (`file:line` refs, verbatim output, no empty or editorial sections, open with the result, bounded fields): the `methodology` skill, file `agent-frontmatter.md`, section "Output rules".
