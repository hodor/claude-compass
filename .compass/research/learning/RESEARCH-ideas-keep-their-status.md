---
title: "Ideas Keep Their Status: Research Axes"
type: research
status: draft
confidence: low
area: methodology
tags: [capture, ideas, status, retrieval, learning]
depends_on: ["[[SPEC-033-ideas-keep-their-status]]"]
summary: "planned axes for designing the idea record: Compass's capture paths, record shape and retrieval, status upkeep, Obsidian view, backfill, prior art (draft)"
created: 2026-11-19
updated: 2026-11-19
author: "orchestrator"
---

# Ideas Keep Their Status: Research Axes

```mermaid
flowchart LR
  A1[Compass capture paths] --> D{Idea record design}
  A2[Record shape and lookup] --> D
  A3[Status stays current] --> D
  A4[Obsidian view] --> D
  A5[Backfill] --> D
  A6[Prior art] --> D
```

> [!important] You decide
> Run research on these axes? Add your own questions below; they lead the list.

## Your questions

-

## Axes

1. Where an idea can be caught automatically today, and what each path loses of his words: the code behind `compass capture-note`, the Stop-hook capture worker, `extract-lessons`, and the spec and specs skills.
2. What shape lets any later session find an idea by topic, its status and its history within the hot-path limit: the lessons catalog, `tag-index.yaml`, `compass graph`, and [[SPEC-003-hierarchical-vault-organization]].
3. How status stays current without asking him (a spec citing an idea, a drop said in passing): `compass sync`, the PostToolUse hook, and the link graph.
4. How ideas show in Obsidian (list by status, links to where each led): the `compass-review` plugin and Dataview, already in this vault.
5. How a session backfills its own ideas from the transcript: [[PLAN-020-clone-old-sessions]] and the transcript format.
6. How idea-tracking tools keep status and provenance (Zettelkasten, product idea backlogs, IBIS): published practice and docs.

- [ ] Grading allowed (a cheap sub-agent scores how completely the findings cover the spec)
