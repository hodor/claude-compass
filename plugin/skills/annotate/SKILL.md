---
name: annotate
description: Sidecar annotation system for Compass vault files. Agents attach persistent notes that auto-surface when files are read. Lightweight alternative to full lessons.
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
when_to_use: "Reference for the sidecar annotation system. Agents use this directly during their work (builder, validator, debug, reviewer annotate automatically). Humans can invoke to show, list, or clear annotations. Triggers: 'show annotations', 'list annotations', 'clear annotations'."
argument-hint: "<action> <vault-path> [note]"
---

# Annotate — Sidecar Notes for Vault Files

Persistent agent notes that live OUTSIDE the content itself, in `.compass/.annotations/`. Notes auto-surface when vault files are read, so agent knowledge compounds across sessions.

Inspired by Context Hub's annotation system.

## Storage Format

Annotations are JSON sidecar files in `.compass/.annotations/`:

```
.compass/.annotations/
  SPEC-001-project-setup.json
  PLAN-002-auth-refactor.json
  ...
```

Each file:
```json
{
  "path": "specs/SPEC-001-project-setup.md",
  "notes": [
    {
      "text": "Section 3 contradicts ADR-002 — check before implementing",
      "by": "validator",
      "date": "2026-04-05",
      "tags": ["conflict", "needs-resolution"]
    },
    {
      "text": "The API shape described here was changed in commit abc123",
      "by": "builder",
      "date": "2026-04-04",
      "tags": ["stale"]
    }
  ]
}
```

## Commands

### Add a note

```
/compass:annotate add "specs/SPEC-001-project-setup.md" "Section 3 contradicts ADR-002"
```

Optional flags:
- `--by <agent-name>` — who is annotating (defaults to current agent)
- `--tags <tag1,tag2>` — categorize the note

### Show notes for a file

```
/compass:annotate show "specs/SPEC-001-project-setup.md"
```

### Get file content with annotations appended

```
/compass:annotate get "specs/SPEC-001-project-setup.md"
```

Returns the file content followed by:
```
---
## Annotations (3 notes)
- [validator, 2026-04-05] Section 3 contradicts ADR-002 #conflict #needs-resolution
- [builder, 2026-04-04] The API shape described here was changed in commit abc123 #stale
- [debug, 2026-04-03] This module has a known race condition under load #caveat
```

### List all annotated files

```
/compass:annotate list
```

### Clear notes

```
/compass:annotate clear "specs/SPEC-001-project-setup.md"           # clear all
/compass:annotate clear "specs/SPEC-001-project-setup.md" --index 0  # clear specific note
```

## Protocol

### Adding a note

1. Ensure `.compass/.annotations/` directory exists
2. Normalize the vault path (strip leading `.compass/` if present)
3. Convert path to annotation filename: replace `/` with `--`, replace spaces with `_`, replace `.md` with `.json`
4. Load existing annotation file (or create empty)
5. Append the new note with date, author, and tags
6. Save the annotation file

### Reading with annotations (get)

1. Read the vault file content
2. Check for a matching annotation file in `.compass/.annotations/`
3. If annotations exist, append them after a `---` separator
4. Return the combined content

## When to Annotate vs Create a Lesson

| Use annotation when... | Use lesson when... |
|------------------------|-------------------|
| The note is specific to ONE file | The insight applies broadly |
| It's a quick flag ("this is stale") | It's a full explanation with context |
| It might become irrelevant when the file changes | It's a durable insight about the project |
| You want the note to auto-surface on file read | You want it discoverable via tag search |

## Integration with Other Agents

Agents that should ADD annotations:
- **validator** — flag deviations, stale specs, contradictions
- **builder** — note implementation surprises per-file
- **debug** — flag known issues in specific modules
- **reviewer** — note convergence patterns about specific artifacts

Agents that should READ annotations (via `get`):
- **researcher** — see prior agent notes before investigating
- **planner** — see flags on specs before planning
- **builder** — see warnings on files before modifying
- **handoff-resume** — see accumulated knowledge on artifacts
