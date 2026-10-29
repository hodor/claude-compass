---
title: "Working in Compass Is Visual"
type: spec
status: approved
confidence: low
area: methodology
tags: [obsidian, review, documents, markdown, cli, jargon, artifacts]
summary: "working in Compass, in the CLI and in the documents, is visual and easy to follow instead of a wall of jargon"
created: 2026-10-25
updated: 2026-10-29
approved: 2026-10-25
---

# Working in Compass Is Visual

> [!question] You decide
> Approve the added Problem sentence, in your words: documents are bloated and hard to read.

## Problem

Right now everything in using Compass is a wall of text. A wall of text on both the CLI but also on the markdown files. It's very hard for humans to follow up and let them know what they think because there's also a lot of jargon that Compass puts in place.

The documents are usually insanely bloated and hard for humans to read; we need to make it so that it's easy.

## Desired Outcome

Working in Compass is a bliss for anyone, not like reading the phone book. We can see graphs, images and code snippets with colors, and in a very intuitive and visual way, understand exactly what the AI means.

This could also be something that we do using Claude artifacts, doesn't have to be only on Obsidian, in fact if we can get something like the artifacts working on Obsidian we should.

Related: [[SPEC-029-questions-to-the-human-are-clear-and-visual]], [[SPEC-030-review-documents-open-in-obsidian]].

## Decisions

- **D-01:** Documents use every one of these: diagrams (a plan's task dependencies, the pipeline and status flow, key metrics over time as charts), callouts for risks, open questions and decisions, embeds that show another document's section in place, block references so a cited decision is one click away, a table of a plan's tasks inside the plan, footnotes for research sources, and a canvas of the spec tree the human rearranges.
- **D-02:** Make sure we don't bloat the documents.
