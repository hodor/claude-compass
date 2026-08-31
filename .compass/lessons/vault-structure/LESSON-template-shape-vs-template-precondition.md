---
title: A Template's Shape Is Not Its Precondition
type: lesson
status: active
category: process
area: methodology
tags: [templates, folder-spec, taxonomy, spec-writing]
created: 2026-08-30
updated: 2026-08-30
score: 5
summary: "A folder-spec template built for 'problem + decisions' doesn't fit a folder that only groups topically related docs"
source: "extract-lessons:interval:OPP-20260830T185106235068Z"
seen: []
---

The folder-spec template (obsidian SKILL.md) requires the body hold decisions shared by every child; a topical grouping folder like "distribution" or "pipeline" has no such shared decision, only a shared subject.
ADR-021 collapsed both cases into the same index.md-is-the-spec mechanism without defining what a body should say when there is no Problem/Decisions to state.
Before reusing a template, check whether the new use case has the property the template's structure assumes, not just the shape it produces.
