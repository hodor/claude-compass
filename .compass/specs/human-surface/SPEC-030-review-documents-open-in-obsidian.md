---
title: "Review Documents Open in Obsidian"
type: spec
status: approved
confidence: low
area: methodology
tags: [obsidian, review, human-gates]
summary: "when configured, Compass always opens the thing the human should review in Obsidian instead of just asking"
created: 2026-10-24
updated: 2026-10-27
approved: 2026-10-24
---

# Review Documents Open in Obsidian

## Problem

Deeper integration with Obsidian: Compass (if configured) always opens the thing we should review on Obsidian instead of just asking.

## Desired Outcome

- Whenever compass needs a document reviewed, it should open in Obsidian/their configured md editor
- UX for it should be frictionless
- Compass should use visual artifacts when possible to communicate properly 
- Needs to work if we have multiple files to review on the same md editor. Needs to be incredibly easy to navigate them all.
- Needs to work if we have multiple claude code sessions, each with their own instance of md editors

KPI: [guess: every point where Compass asks the human to review a document opens that document in Obsidian first, when configured.]

Related: [[SPEC-029-questions-to-the-human-are-clear-and-visual]].

## Decisions

- **D-01:** Obsidian is one of many possible visual md interfaces for Compass. Compass builds a generic one and Obsidian implements that one; in the future one could be built for VS Code.
- **D-02:** Obsidian just opens, and if the human is doing something else he does whatever he needs there, clicks a button, and it takes him back where he was; he does not even need to come to Claude Code.
- **D-03:** For embeds and navigating inside Obsidian, the review tracks it properly, so the human doesn't lose track of the original question, and he also has the possibility to give feedback on other files he is navigating. The review lives in one panel at the side (layout B of [[RESEARCH-review-mockup]]).
- **D-04:** When the human approves something on Obsidian through the plugin, he does NOT have to approve again in the terminal.
- **D-05:** Committing to git and reviewing git after should be a required step. It's how you'll really know the deltas.
- **D-06:** We should also be able to have multiple projects with multiple Compass running multiple Obsidians, and those Obsidians' plugin should guide the users through multiple files if needed.
