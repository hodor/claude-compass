---
name: obsidian
description: Obsidian-compatible formatting conventions - YAML frontmatter schema, wikilinks, file naming, vault search patterns, and document templates for the .compass/ vault
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
---

# Obsidian - Vault Formatting & Conventions

Reference for reading and writing `.compass/` documents. Obsidian-compatible markdown with YAML frontmatter and wikilinks.

## The one linking rule

When you mention a vault document in prose, use `[[wikilinks]]`. Every time. No exceptions.

- Write: "This plan implements [[SPEC-001-project-setup]]"
- Not: "This plan implements the project setup spec"
- Not: "This plan implements `.compass/specs/SPEC-001-project-setup.md`"

Wikilinks are how documents connect - for agents (grep finds them) and for humans (Obsidian renders the graph). Frontmatter `depends_on` is for structured queries. Inline wikilinks are for navigation.

## YAML frontmatter

Every vault document needs frontmatter:

```yaml
---
title: "Human-readable title"                    # REQUIRED - all
type: spec | research | plan | task | lesson | decision | handoff  # REQUIRED - all
status: draft | review | approved | active | done | archived  # REQUIRED - all
confidence: low | medium | high                  # REQUIRED for spec, research, decision
category: process | domain                       # REQUIRED for lesson
summary: "one-line summary"                      # REQUIRED for spec, plan, research, decision, lesson, handoff
seen: [YYYY-MM-DD, ...]                          # OPTIONAL for lesson - recurrence dates, cap 3
escalated: YYYY-MM-DD                            # OPTIONAL for lesson - set when seen would exceed 3
escalation_reason: "..."                         # OPTIONAL for lesson - paired with escalated
score: 5                                         # REQUIRED for lesson, range 1-10
area: architecture | frontend | backend | testing | devops | infra | docs | workflow  # REQUIRED - all
tags: [tag1, tag2]                               # REQUIRED - all
created: YYYY-MM-DD                              # REQUIRED - all
updated: YYYY-MM-DD                              # REQUIRED - update on every edit
git_branch: "branch-name"                        # REQUIRED for research, handoff, plan
git_commit: "abc1234"                            # REQUIRED for research, handoff, plan
author: "human or agent name"                    # REQUIRED for research, handoff, plan, decision
blocked_by: "description or [[link]]"            # OPTIONAL - tasks only
depends_on: ["[[link1]]", "[[link2]]"]           # OPTIONAL - any document
supersedes: "[[link]]"                           # OPTIONAL - replacing an older document
---
```

### Status lifecycle

```
draft → review → approved → active → done → archived
```

- `draft` - work in progress, not for review.
- `review` - ready for human review.
- `approved` - human approved, not yet started.
- `active` - currently being worked on.
- `done` - completed.
- `archived` - no longer relevant, kept for history.

## Wikilinks

| Syntax | Use |
|--------|-----|
| `[[filename]]` | Link to a root artifact (omit `.md`) |
| `[[unit/specs/SPEC-001-name]]` | Link to an artifact inside a unit folder (path-qualified) |
| `[[filename#Section]]` | Link to a section within a document |
| `[[filename\|Display Text]]` | Link with custom display text |

Always wikilinks for cross-references. Never relative markdown links. See "Unit folders" below for when a link must be path-qualified.

## Side files

The rest of the skill sits in files beside this one. Read the one a task needs before doing that task.

| File | Holds | Read it when |
|---|---|---|
| `templates.md` | Document templates: Spec, Research, Plan, Lesson, Handoff, Decision (ADR) | writing a new document of one of those types |
| `documents.md` | Decision bullets (the D-NN convention); Documents the human reads, with A view an agent writes and Plain words | citing or recording a decision, or writing a document a person reads and decides on |
| `vault-layout.md` | Math (LaTeX); File naming and numbering; Hierarchical specs and plans, with Children and Scope notes; Unit folders, with bare and path-qualified links and where a new artifact goes; Facet tags; Vault search patterns | creating or placing a file, numbering it, linking across folders, tagging, or searching the vault |
| `writing-principles.md` | Sentence-level writing principles and the fresh-eyes check | writing the prose of any document |
| `path-qualified-links.md` | Resolving, authoring and ambiguity of path-qualified links | linking to a workstream-folder artifact or one below a topic folder |
