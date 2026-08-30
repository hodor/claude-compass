---
title: "Obsidian doesn't resolve a bare folder-spec wikilink to index.md"
type: lesson
status: active
category: domain
area: methodology
tags: [obsidian, wikilinks, folder-spec, born-folder, click-through]
created: 2026-08-30
updated: 2026-08-30
score: 5
summary: "Obsidian does not resolve a bare folder-spec wikilink to its index.md; click-through creates a zero-byte stray note"
source: "extract-lessons:OPP-20260830T191922543312Z"
seen: []
---

Clicking a bare `[[SPEC-NNN-name]]` link to a folder-spec in Obsidian does not resolve to its `index.md`: Obsidian looks for a literal `<name>.md` and, finding none, creates a zero-byte stray note at the vault root.
The born-folder convention (index.md carries the artifact) is invisible to Obsidian's own resolver, and the stray note then creates its own wikilink ambiguity.
Click any bare-stem link into a promoted folder-spec in Obsidian itself before trusting it resolves; `compass validate` passing does not confirm this.
