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
initialPrompt: "Read these files now: .compass/index.md, .compass/active.md, .compass/lessons/index.md"
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
