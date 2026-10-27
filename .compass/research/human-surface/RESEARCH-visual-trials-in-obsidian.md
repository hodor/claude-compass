---
title: "Visual Trials in Obsidian"
type: research
status: in-progress
confidence: medium
area: methodology
tags: [obsidian, trials, charts, mermaid, dataview, human-surface]
depends_on: ["[[PLAN-024-working-in-compass-is-visual]]"]
summary: "runs of a throwaway Obsidian plugin that draw a code block, a Mermaid chart and a ledger count in Reading view and Live Preview, each recorded in a file"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
git_commit: "6cddd82"
author: "builder"
---

# Visual Trials in Obsidian

## Question

Can a Compass plugin draw inside a running Obsidian, in both Reading view and Live Preview? Each trial tests one way of drawing or reading data that [[RESEARCH-working-in-compass-is-visual]] section J found only in documentation: a code block the plugin draws (A), Mermaid charts (B), Vega-Lite bundled into a plugin (C), reading `.jsonl` files (D), and a canvas Compass rewrites (E). Each trial states its setup and its result. Trial C has not run.

## Setup shared by the trials

- Plugin `compass-trials`: source `.compass/tmp/trials/compass-trials/` (`main.js`, `manifest.json`, `minAppVersion` 1.9.0), copied into `.compass/.obsidian/plugins/compass-trials/` and listed in `community-plugins.json`.
- Trial note: `.compass/tmp/trials/trial-note.md`, written by `.compass/tmp/trials/build_trial_note.py`.
- When Obsidian finishes loading, the plugin opens the note in Reading view, waits for the render, switches the same tab to Live Preview and waits again. Creating or changing `.compass/tmp/trials/rerun` runs the sequence again without reloading Obsidian.
- Each render appends one JSON line to `.compass/tmp/trials/draws.jsonl`: the trial, the view it drew in, the time, whether an `<svg>` appeared, any error, the row count (Trial D), and the view the sequence had switched to.
- Obsidian version: 1.14.5.

Runs: three, on 2026-10-27, at 15:17, 15:54 and 16:43 UTC. The 15:17 run waited 3 seconds for a chart, the later two 15 seconds. The `loadMermaid()` chart in Trial B exists in the 16:43 run only.

## Trial A: a code block drawing while editing

Setup: the note holds a `compass-trial` block. The plugin registers that language and draws a bordered box; each draw is one line with the view it was drawn in. Pass: a draw for each view, or a record of which view drew nothing.

Result: pass. The box drew in Reading view and in Live Preview on all three runs. Confidence: high.

## Trial B: charts through Obsidian's own Mermaid

Setup: the note holds three line charts of the same 50 numbers: the ledger of [[LOOP-001-visual-questions]] records, for each run of that loop, a reading (the number of places in the shipped skills and rules where Compass still asks the human a question outside `AskUserQuestion`), and 50 of its 52 runs carry one.

- A hand-written `mermaid` fence with an `xychart-beta` body, its numbers copied from `ledger.jsonl` by `build_trial_note.py`.
- A `compass-trial-chart` block that builds the same fence from `ledger.jsonl` when it renders and hands it to `MarkdownRenderer.render`, Obsidian's general markdown renderer.
- A `compass-trial-chart-direct` block that builds the same fence and draws it with Obsidian's own Mermaid instance, `loadMermaid()` then `mermaid.render`, inserting the returned svg.

The plugin records, for each chart in each view, whether an `<svg>` appeared within the wait and how long it took, or the text that appeared instead. Pass: a chart built by the plugin draws in both views, which makes that route the one Compass charts use.

Result:

| Chart | Reading view | Live Preview |
|---|---|---|
| Hand-written `mermaid` fence | draws | draws |
| Plugin, `MarkdownRenderer.render` | draws | stays raw text |
| Plugin, `loadMermaid()` + `mermaid.render` | draws, 155 ms | draws, 329 ms |

- Every chart that drew shows the 50 readings of the ledger.
- `MarkdownRenderer.render` left the fence as raw text in Live Preview on all three runs. The block element was outside the page when the render started and inside it when the wait ended. The cause is not established. Confidence: high for the outcome.
- `loadMermaid()` drew in both views on its one run. Confidence: medium.

## Trial D: reading files that are not notes

Setup: a count of the rows of `ledger.jsonl` (407 lines) by two routes.

- Plugin route: a `compass-trial-count` block reads the file through `app.vault.adapter.read` and records the count.
- Dataview route: a `dataviewjs` block counts the same rows through `dv.io.load` and appends its own line. It runs only with the Dataview community plugin installed and its JavaScript queries on; without them Obsidian shows it as plain code.

Pass: both counts equal `wc -l` of the ledger, or the failing route records its error.

Result:

- Plugin route: pass. 407 rows in Reading view and in Live Preview on all three runs, equal to `wc -l`. Confidence: high.
- Dataview route: not run; Dataview is not installed in this vault.

## Trial E: a canvas Compass rewrites

Setup: `.compass/tmp/trials/canvas/trial.canvas` holds two cards, one per scratch note (`note-a.md`, `note-b.md`), joined by one edge. With the canvas open in Obsidian, a script outside Obsidian first rewrites the file with card B moved from (500, 0) to (500, 400), then renames `note-b.md` to `note-b-renamed.md`. After each step the plugin records the cards the open canvas view holds, read through the view's own data, beside the file on disk. Run on 2026-10-27 at 19:14 UTC, Obsidian 1.14.5.

Result:

| Step | Open canvas view | File on disk |
|---|---|---|
| Card B moved in the file | shows (500, 400) | (500, 400), unchanged by Obsidian 10 s later |
| `note-b.md` renamed outside Obsidian | card B still names `note-b.md` | still names `note-b.md` |

- An open canvas reloads a file rewritten outside Obsidian and writes nothing of its own back, so Compass can regenerate a canvas while the human has it open. Confidence: high.
- A note renamed outside Obsidian leaves its card pointing at the old path, so `compass move` has to rewrite card paths itself. Confidence: high.
