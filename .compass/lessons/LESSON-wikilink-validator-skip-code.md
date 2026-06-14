---
title: Wikilink validators must skip fenced and inline code blocks
type: lesson
status: active
category: process
area: workflow
tags: [validation, wikilinks, false-positives, content-aware]
created: 2026-05-27
updated: 2026-05-27
score: 5
summary: "Wikilink validators must skip fenced code blocks AND inline code spans; example refs in docs are noise"
seen: []
---

Markdown writers commonly use `[[NAME]]`, `[[link]]`, `[[wikilinks]]` as examples inside backticks.
A naive wikilink resolver flags all of them as broken; ratio in this vault was 7 false positives to 1 real bug.
Strip fenced code blocks (between triple-backtick markers) AND inline code spans (between single backticks) before resolving.
Compass's index-sync skill added this filter after the regression test surfaced the noise.
Same principle: content-aware validators must respect code-block scope, escape sequences, and literal-quoted regions.
