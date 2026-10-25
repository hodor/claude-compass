---
title: "Review Documents Open in Obsidian"
type: spec
status: approved
confidence: low
area: methodology
tags: [obsidian, review, human-gates]
summary: "when configured, Compass always opens the thing the human should review in Obsidian instead of just asking"
taxonomy_hint: "the human's review surface; sits beside SPEC-029 at the specs root"
created: 2026-10-24
updated: 2026-10-24
approved: 2026-10-24
---

# Review Documents Open in Obsidian

## Problem

Deeper integration with Obsidian: Compass (if configured) always opens the thing we should review on Obsidian instead of just asking.

## Desired Outcome

[guess: When Compass reaches a point where the human reviews something, that thing is already open in Obsidian when the question arrives. A project without the configuration sees no change.]

KPI: [guess: every point where Compass asks the human to review a document opens that document in Obsidian first, when configured.]

Related: [[SPEC-029-questions-to-the-human-are-clear-and-visual]].

## Decisions

- **D-01:** Obsidian is one of many possible visual md interfaces for Compass. Compass builds a generic one and Obsidian implements that one; in the future one could be built for VS Code.
- **D-02:** Obsidian just opens, and if the human is doing something else he does whatever he needs there, clicks a button, and it takes him back where he was; he does not even need to come to Claude Code.
