---
name: clone-old
description: Harvest lessons from the project's past feature sessions. Runs temporary headless copies of the sessions that finished a feature, each writes the lessons it learned, and the results are merged and written through lesson-write. Originals are never touched.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
when_to_use: "Use when the human wants lessons from sessions that already ended. Triggers: 'clone old sessions', 'harvest lessons from past sessions', '/clone-old'."
argument-hint: "[--discard] [--max N] [--min-commits N]"
---

# Clone Old

Finds the project's past sessions that finished a feature, runs a temporary copy of each that writes down what it learned, and presents one aggregated set of lessons. Claude Code's own transcripts are read in place and never modified; each copy is a headless fork that persists nothing under `~/.claude`.

`compass` below stands for `python3 .claude/cli/compass` (`python .claude/cli/compass` where `python3` is absent).

## Rules

- Nothing under `~/.claude/projects` is edited, moved, or deleted.
- Session text stays out of the repository. The vault receives lessons and `clone-log.jsonl` rows, which hold names and counts only. Lessons are written in the skill's own words, never as quoted transcript.
- A clone that ends `context-full` has used all its room. That is a normal end, and its lesson file is read like any other.

## Arguments

- `--discard`: keep no clone transcripts; only lesson files and `run.json` remain in the run folder.
- `--max N`: clone at most N sessions. Default 10.
- `--min-commits N`: the commit count that makes a session a feature session. Default 10, the command's own default.

## Protocol

### 1. Choose the sessions

Run `compass sessions list --json`, adding `--min-commits N` when given. Keep rows where `feature` is true, `active` is false, and `headroom` is a positive number. Sort by `headroom` descending, so the sessions with the most room left clone first, and keep the first `--max`.

When no row qualifies, say so in one line and stop.

### 2. State the run

Print one line: how many sessions will be cloned and the tokens they inherit (the sum of `used`), plus that the order is most headroom first. Then proceed; no approval is asked.

### 3. Start the clones

Run `compass clone <session-id>... [--discard]` with Bash `run_in_background: true`, since a run outlasts a foreground call. The first stdout lines are `run-id: <id>` and `run-dir: <path>`; take both from the background output. Wait for the completion notification.

### 4. Read the results

Read `run.json` in the run folder for each clone's `status` (`done`, `context-full`, `timeout`, `failed`), `cost_usd`, and `original_changed`. Read each clone's lesson file `<session-id>.md` in the run folder. An empty or missing lesson file means that clone produced no lessons. An `original_changed: true` row is reported in the aggregate and its lessons are still read.

### 5. Merge duplicates across clones

Each lesson file holds short entries marked `process` or `domain`. Entries across clones that state the same insight become one candidate, citing every session it came from. Keep the sharpest wording; add no claim that no clone made.

### 6. Write through lesson-write

For each candidate, read `.claude/skills/lesson-write/SKILL.md` and follow its steps in place, never through the Skill tool. Payload:

- `category`: the entry's mark.
- `area`, `tags`, `summary`: inferred from the content, within lesson-write's limits.
- `body`: at most 5 lines.
- `source`: `clone-old:<run-id>`.

lesson-write dedupes against the catalog and applies the anti-list. Collect each return value: `created`, `recurrence` and `escalated` count as written, `refined` as merged, `rejected` as rejected.

### 7. Record the run

Run `compass sessions record <run-id> --written <lesson-files> --merged <lesson-files> --rejected <N>`, passing the lesson filenames lesson-write returned and the number rejected.

### 8. Present the aggregate

Terse:

- Each lesson written: its summary and the session ids it came from.
- What merged into existing lessons.
- What was rejected, with the anti-list bucket.
- Per-clone status (`done` / `context-full` / `timeout` / `failed`) and the total cost across clones.
- When clones were kept, the run folder, so `compass sessions show <run-id>/<session-id>` can read one.
