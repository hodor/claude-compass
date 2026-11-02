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
