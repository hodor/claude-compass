---
paths:
  - .claude/agents/**
---

# Compass Agent Prompt Patterns

Rules for writing and reviewing Compass agent .md files. Derived from Claude Code source analysis.

## The 5 Mandatory Patterns

### 1. Identity + Constraints First

One sentence of identity. Hard constraints within the first 10 lines. Domain expertise AFTER.

```
You are the Compass builder agent — the implementation engine.

=== CRITICAL: RUN EXISTING TESTS AS SMOKE CHECK BEFORE HANDING OFF TO TESTER ===
=== CRITICAL: THE TESTER AGENT HANDLES WRITING NEW TESTS — YOU WRITE CODE ===
```

### 2. `=== CRITICAL: CAPS ===` Fences

For hard constraints the model WILL violate. Max 3-4 per agent.

- Triple-equals on both sides, ALL CAPS inside
- Repeated at the TOP and BOTTOM of the prompt
- `## CRITICAL` headers alone are noise — the model has seen millions

### 3. "You Will Be Tempted To..." Failure Modes

Name the model's exact drift patterns. Quote the internal monologue. Counter it.

```
You WILL be tempted to:
- Skip tests for "trivial" changes — write them anyway
- Read the code and conclude it works — run the command instead
- "This is probably fine" — "probably" is not verified
```

Every agent gets at least 3. If you can't name 3, you don't understand the agent.

### 4. Bad/Good Example Pairs

Show wrong output first (labeled), then correct output. Contrast teaches better than description.

```
Bad (rejected):
  ### Check: API validation
  **Result: PASS**
  Evidence: Reviewed the route handler. Logic correctly validates input.
  (No command run. Reading code is not verification.)

Good:
  ### Check: API rejects short password
  **Command run:** curl -s -X POST localhost:8000/api/register -d '{"password":"short"}'
  **Output observed:** {"error": "password must be at least 8 characters"} (HTTP 400)
  **Result: PASS**
```

### 5. Output Format Enforcement

Specify exact response structure. Show what rejected output looks like.

## Tone Rules

- Imperative verbs: "Stop.", "Run it.", "Do not."
- Short sentences for critical rules
- No qualifiers: "please", "try to", "it would be best if"
- Second person: "you", not "the agent" or "one should"
- Direct, not hostile

## Frontmatter Checklist

Every Compass agent MUST have:

```yaml
---
name: agent-name
description: "Use when [concrete trigger]. [What it does]. [Key constraint]."
tools: [minimum needed]
disallowedTools: [if read-only: Write, Edit, NotebookEdit]
skills: [obsidian, methodology, lessons — include what's needed]
model: inherit
effort: high
maxTurns: [15-60 depending on complexity]
color: [unique per agent]
memory: project
initialPrompt: "Read these files now: .compass/index.md, .compass/active.md, .compass/meta/lessons-catalog.yaml"
permissionMode: [acceptEdits for write agents, omit for read-only]
---
```
