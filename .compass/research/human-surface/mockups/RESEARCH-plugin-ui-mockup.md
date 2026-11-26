---
title: "Plugin UI: Mockup"
type: research
status: complete
confidence: low
area: methodology
tags: [obsidian, plugin, mockup, approval, review, human-surface]
depends_on: ["[[specs/human-surface/SPEC-031-working-in-compass-is-visual]]", "[[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]]"]
summary: "seven live sample screens Compass's Obsidian plugin could offer for reading and approving specs, plans and research, each drawn from the real vault"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
git_commit: "5bcbdb1"
author: "builder"
---

# Plugin UI: Mockup

The blocks below draw while the `compass-ui-mockups` plugin (a throwaway Obsidian plugin in this vault's `.obsidian/plugins/`) is installed and show as plain code otherwise.

Seven screens Compass's own Obsidian plugin could offer for reading and approving specs, plans and research, following [[specs/human-surface/SPEC-031-working-in-compass-is-visual]] and [[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]] (its decision D-06 asks for several files in one review and several projects). Each block reads the real documents of this vault. Buttons write only under `tmp/mockups/ui/`: clicks go to `clicks.jsonl`, a Send writes a file in `verdicts/`.

## 1. Plan approval board

See a plan's tasks as a graph colored by status, answer each of the plan's choices to approve with Agree or Change and a note, and send one verdict. Click a task for its detail; Mark done recolors the graph and the progress bar above it as a try-out.

```compass-ui-plan
file: plans/PLAN-024-working-in-compass-is-visual.md
```

## 2. Spec approval

Read the problem and the outcome in the human's own words, then answer each recorded decision with Agree or Change. The Send button says what it will do: approve, send changes, or how many answers are left.

```compass-ui-spec
file: specs/human-surface/SPEC-030-review-documents-open-in-obsidian.md
```

## 3. Research reading

Scan the findings by confidence at a glance. The bars at the top count findings per section and filter on click; the three buttons filter by confidence; a row opens its evidence and jumps to the finding in the document.

```compass-ui-research
file: research/human-surface/RESEARCH-working-in-compass-is-visual.md
```

## 4. Several files in one review

Walk through the files of one review with Previous and Next, see every file's state at a glance (not opened, read, has notes, approved, needs changes), answer per file, and send once. Arrow keys move when the panel has focus.

```compass-ui-review
question: Approve the work on working in Compass is visual
files:
  - specs/human-surface/SPEC-031-working-in-compass-is-visual.md
  - plans/PLAN-024-working-in-compass-is-visual.md
  - research/human-surface/RESEARCH-working-in-compass-is-visual.md
  - research/human-surface/RESEARCH-plain-words-mockup.md
```

## 5. What changed since you last saw it

See only what moved in a document since the commit its last review showed, grouped under the heading each change sits in, with the changed words marked inside each line. The diff is read from git and saved to a file before the block opens, because a plugin cannot run git portably. Pick another review from the list to see its changes.

```compass-ui-changes
id: 20261027T105830-d80c8f
```

## 6. Reviews across sessions and projects

One panel lists every review waiting on the human, grouped by project and session, with a filter and a jump to the next. This project's rows are real (from `tmp/review/`); the other projects and sessions are sample entries, and opening one shows a message describing the action.

```compass-ui-sessions
```

## 7. Where each spec stands

Spec, research, plan, build and validate as one strip per spec, read from the documents that refer to it, with what waits on the human and what Claude does next. A checkbox previews the strip as it would look with a draft plan.

```compass-ui-pipeline
specs:
  - specs/human-surface/SPEC-031-working-in-compass-is-visual.md
  - specs/human-surface/SPEC-030-review-documents-open-in-obsidian.md
```

## What each needs to ship

"Host point" is where in Obsidian the screen lives; the options come from [[research/human-surface/RESEARCH-working-in-compass-is-visual]] section J, and the drawing route from [[research/human-surface/RESEARCH-visual-trials-in-obsidian]]. Cost is the approximate lines of JavaScript the mockup takes, beside the parsing it needs.

| Mockup | Host point | Data read | What else it needs | Cost |
|---|---|---|---|---|
| Plan board | code block; Obsidian's markdown renderer for the choice text | plan task lines, `depends_on`, the choices section | a verdict file for the plan; a ruling on whether Mark done writes the checkbox into the plan (the mockup writes nothing) | about 150 lines, plus 170 for the task parser and the layout |
| Spec approval | code block; markdown renderer | Problem, Desired Outcome, decision bullets | one verdict file per spec, with an answer per decision | about 30 lines on the approval cards both approval mockups share (130 lines) |
| Research reading | code block | findings tables: number, text, confidence, evidence | nothing beyond the vault documents | about 125 lines, plus 60 for the table parser |
| Several files in one review | side panel, so it stays in view while the human moves around | frontmatter, headings, task and finding counts of each file | the review request listing its files | about 175 lines |
| What changed | code block; opening a file at a line | a diff saved by Compass beside the review request | Compass runs `git diff` against the commit the last review showed when it opens a review, and saves the result | about 200 lines, plus 85 for the diff and word parsers |
| Sessions and projects | side panel, so it stays open across documents | `tmp/review/*.request.json` and `*.verdict.json` | a session and a project field on each request; a way for each project's Obsidian to read the others' pending reviews | about 150 lines |
| Where each spec stands | code block | spec, plan and research frontmatter; plan task lines | nothing beyond the vault documents | about 130 lines |

The mockups draw all seven as code blocks so they sit in one note. The whole plugin is 1,800 lines (73 KB) of JavaScript, of which the rest beyond the table is the approval cards, the plugin class and small helpers, and 920 lines (19 KB) of styles written with Obsidian's color variables so they follow the theme. The graph is plain boxes and an SVG path.
