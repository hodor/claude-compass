---
title: "Visual Trials in Obsidian"
type: research
status: in-progress
confidence: low
area: methodology
tags: [obsidian, trials, charts, mermaid, dataview, human-surface]
depends_on: ["[[PLAN-024-working-in-compass-is-visual]]"]
summary: "runs of a throwaway Obsidian plugin that draw a code block, a Mermaid chart and a ledger count in Reading view and Live Preview, each recorded in a file"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
git_commit: "8025594"
author: "builder"
---

# Visual Trials in Obsidian

## Question

What does a running Obsidian draw for the routes [[RESEARCH-working-in-compass-is-visual]] section J could only read about? Each trial below states its setup and records its result from the run.

## Setup shared by the trials

- Plugin `compass-trials`: source `.compass/tmp/trials/compass-trials/` (`main.js`, `manifest.json`, `minAppVersion` 1.9.0), copied into `.compass/.obsidian/plugins/compass-trials/` and listed in `community-plugins.json`.
- Trial note: `.compass/tmp/trials/trial-note.md`, written by `.compass/tmp/trials/build_trial_note.py`.
- On layout ready the plugin opens the note in Reading view, waits for the render, switches the same leaf to Live Preview and waits again.
- Each render appends one JSON line to `.compass/tmp/trials/draws.jsonl`: `trial`, `mode`, `at`, `svg`, `error`, `count`, `phase`.
- The Obsidian version is recorded once per run in the `env` line.

Result: pending the first run.

## Trial A: a code block drawing while editing

Setup: the note holds a `compass-trial` block. The plugin registers that language and draws a bordered box; each draw is one line with the view mode it was drawn in. Pass: `draws.jsonl` holds a draw for each mode, or records which mode drew nothing.

Result: pending the first run.

## Trial B: charts through Obsidian's own Mermaid

Setup: the note holds two charts of the reading after each run in the ledger of [[LOOP-001-visual-questions]], 50 points from the runs that carry a reading.

- A hand-written `mermaid` fence with an `xychart-beta` body, built by `build_trial_note.py` from `ledger.jsonl` so the numbers are exact.
- A `compass-trial-chart` block that builds the same fence from `ledger.jsonl` at render time and hands it to `MarkdownRenderer.render`.

The plugin records, for each chart in each mode, whether an `<svg>` appeared within 3 seconds, or the text that appeared instead. The plugin-built line also carries the readings it drew. Pass: the plugin-built chart draws in both modes; the result decides the chart renderer.

Result: pending the first run.

## Trial D: reading files that are not notes

Setup: a count of the rows of `ledger.jsonl` (407 lines at build time) by two routes.

- Plugin route: a `compass-trial-count` block reads the file through `app.vault.adapter.read` and records the count.
- Dataview route: a `dataviewjs` block in the note counts the same rows through `dv.io.load` and appends its own line. It needs the Dataview plugin installed with JavaScript queries on, which this document does not do; until then the block shows as plain code.

Pass: both counts equal `wc -l` of the ledger, or the failing route records its error.

Result: pending the first run (plugin route); the Dataview route waits for Dataview to be installed.
