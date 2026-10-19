---
title: "Loop: no-private-data"
type: loop
status: active
area: workflow
tags: [loop, privacy, redaction, git-hooks]
created: 2026-10-19
updated: 2026-10-19
summary: "Control loop keeping private data out of this public repository: deny-listed names, home-directory paths, session ids in paths and tokens, with a pre-commit hook that refuses new ones."
---

# Loop: no-private-data

This repository is public. `loop.json`, `actuator.md`, `golden/` and `feedback.md` hold the machine form of the choices below.

## Step 0: End state

No file `git ls-files` lists holds private data: no term from the owner's private deny-list, no path into the current user's home directory, no Claude Code session id inside a path, and no credential token. Every redacted passage has a verbatim copy in the private store outside the repository, `~/.compass/private/compass/`.

## Step 1: Sensor

`python .compass/loops/LOOP-002-no-private-data/sensor.py` scans the content and path of every tracked file. The deny-list is a file outside the repository, one case-insensitive term per line, at `COMPASS_PRIVATE_DENYLIST` or `~/.compass/private/denylist.txt`; a missing deny-list reads as invalid, never as clean. Home-directory patterns are built at run time from the current user's home. The value is the count of items; `target` 0, direction `down`. Item identity is `<path>:<category>:<term or pattern name>`, never the secret itself and never a line number.

## Step 2: Stabilize (dampener)

The tracked pre-commit hook `.githooks/pre-commit` runs the sensor with `--staged`, which scans only the lines and paths the staged diff adds, and refuses the commit, naming each item, when it finds anything or cannot run. A clone enables it with `git config core.hooksPath .githooks`. `compass loop baseline LOOP-002` records today's items and `compass loop check LOOP-002` lists any added since.

## Step 3: Controller

`first`: the first sorted item no unreviewed increment holds. One item is one term or pattern in one file.

## Step 4: Actuator

Sonnet with Read, Edit, Glob and Grep, following `actuator.md` and `golden/neutralise-a-private-name.md`: it copies each matched passage verbatim to the private store first, then neutralises it in the one named file, keeping every number and finding.

## Step 5: Schedule

Run by hand when the sensor reads above zero; no schedule.

## Step 6: Human on the loop

The owner reviews each increment with `compass loop review LOOP-002 <run-id> accept|reject --reason "..."`; a reject reason joins `feedback.md`.

## Step 7: Flow control

At most 2 unreviewed increments, $0.40 per run, $2 per day, $5 in total; the halt limits keep their defaults (3 actuator failures, 2 harmful runs, 5 runs without progress).
