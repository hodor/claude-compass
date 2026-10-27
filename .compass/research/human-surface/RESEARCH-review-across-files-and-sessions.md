---
title: "Review Across Files and Sessions"
type: research
status: draft
confidence: low
area: methodology
tags: [obsidian, review, multi-file, sessions, human-surface]
depends_on: ["[[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]]"]
summary: "how one review walks the human through several files, and how several Claude Code sessions each reach their own markdown editor"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
author: "orchestrator"
---

# Review Across Files and Sessions

## Question

How does Compass meet the outcomes of [[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]] that the review plugin does not meet yet: several files in one review that are easy to move through, several Claude Code sessions each with its own markdown editor, another editor than Obsidian, and a review with no friction?

> [!IMPORTANT]
> You decide: run research on these five questions, with grading as described below, or change a question.

## The questions

| # | Question | Where the answers are sought |
|---|---|---|
| 1 | How do review tools walk a person through several files in one review: order, progress, per-file status, moving next and back, an overview of all files? What would a review of several files look like in `compass review` and its request file? | GitHub pull request review, Gerrit, Phabricator, VS Code's multi-file diff editor, their docs; the review plugin's code; the stepper view of [[research/human-surface/RESEARCH-plugin-ui-mockup]] |
| 2 | With several projects and sessions open at once, does each review reach the right Obsidian window and come back to the session that asked? | Obsidian's URI and vault-switching docs and API; `plugin/cli/review_surfaces/obsidian.py`; a live run with two vaults open and two waiting `compass review` commands |
| 3 | What does a markdown editor other than Obsidian need to be a review surface behind the same interface? | VS Code extension API docs (webviews, custom editors, URI handlers); `plugin/cli/review_surfaces/__init__.py` |
| 4 | Where is the friction in the review loop today? Clicks, window switches, time from request to verdict, reviews left unanswered or answered twice. | the request and verdict files in `.compass/tmp/review/` (timestamps, notes, edits); the review plugin's code; usability literature on review interruptions through the shipped source list |
| 5 | How do the visual views of [[plans/PLAN-024-working-in-compass-is-visual]] show inside a review: in the document, in the side panel, or both? | the review plugin's code; the views mockup; Obsidian's view API |

## Grading

Each finding gets a confidence level (high, medium, low) from its evidence: code read or a run observed is high, official docs are high, a single third-party source is medium, an inference is low. Sources from the shipped list carry their own marks. You can refuse grading; the research still runs, with findings ungraded.

## Findings

Not yet run.
