---
name: clone-old
description: Harvest lessons from the project's past feature sessions. Runs temporary headless copies of the sessions that finished a feature, each writes the lessons it learned, and the results are merged and written through lesson-write. Originals are never touched.
version: 1.0.0
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
when_to_use: "Use when the human wants lessons from sessions that already ended. Triggers: 'clone old sessions', 'harvest lessons from past sessions', '/clone-old'."
argument-hint: "[topic or question] [--discard] [--max N] [--min-commits N]"
---

# Clone Old

Finds the project's past sessions that finished a feature, runs a temporary copy of each that writes down what it learned, and presents one aggregated set of lessons. Claude Code's own transcripts are read in place and never modified; each copy is a headless fork that persists nothing under `~/.claude`.

`compass` below stands for `python3 .claude/cli/compass` (`python .claude/cli/compass` where `python3` is absent).

## Rules

- Nothing under `~/.claude/projects` is edited, moved, or deleted.
- Session text stays out of the repository. The vault receives lessons and `clone-log.jsonl` rows, which hold names and counts only. Lessons are written in the skill's own words, never as quoted transcript.
- A clone that ends `context-full` has used all its room. That is a normal end, and its output file is read like any other.

## Arguments

- Free text: what to ask the past sessions. A topic ("the sessions that worked on RunPod") narrows which sessions are cloned; a question or an output other than lessons ("what rules should a RunPod skill always follow") sets what each clone writes. Without free text, every feature session is a candidate and each writes the lessons it learned.
- `--discard`: keep no clone transcripts; only lesson files and `run.json` remain in the run folder.
- `--max N`: clone at most N sessions. Default 10.
- `--min-commits N`: the commit count that makes a session a feature session. Default 10, the command's own default.

## Protocol

### 1. Choose the sessions

Run `compass sessions list --json`, adding `--min-commits N` when given. When the free text names a topic, add `--grep <pattern>`: a case-insensitive regular expression for the topic's distinctive words (`runpod`, `alembic|abc export`), which keeps only sessions whose transcripts mention it.

Keep rows where `feature` is true and `active` is false. A row whose `headroom` (the tokens left in the session's context window) is under 50,000 is skipped: its clone fills its context before it can write anything. Sort the rest by `headroom` descending, so the sessions with the most room left clone first, and keep the first `--max`.

When no row qualifies, say so in one line, naming the skipped low-headroom sessions if any, and stop.

### 2. State the run, and stop at $50

Print one line: how many sessions will be cloned, the tokens they inherit (the sum of `used`), the estimated cost (the sum of `est_cost_usd`, with its `est_basis`), and the skipped low-headroom sessions. Every clone re-reads its whole inherited context on each turn, so cost grows with both size and turns; the estimate is a measured average, and a single clone has run at under half and at nearly twice it.

When the estimate is $50 or more, nothing runs until the human approves. Ask through `AskUserQuestion`, one question: run them all, run a cheaper subset (named, with its own estimate), or run none; the subset is recommended when it still covers what the free text asked, else running them all. Below $50, proceed unasked.

### 3. Write the prompt, when the free text asks for more than lessons

With no free text, or a topic alone, the command's own prompt is used and this step is skipped.

When the free text asks a question or wants a different output (rules for a skill, a section of a document, a checklist), write a prompt file outside the repository (the session scratchpad, or a temp folder) and pass it with `--prompt-file`. The file holds the whole instruction to one clone and keeps the constraints of `compass clone`'s built-in prompt: the clone is a fork of a finished session; it writes its answer to `{output}` as it goes, never waiting for the end; it changes no other file and runs no commands. `{output}` is replaced with that clone's own output file; no other text in the file is substituted.

### 4. Start the clones

Run `compass clone <session-id>... [--discard] [--prompt-file <path>]` with Bash `run_in_background: true`, since a run outlasts a foreground call. The first stdout lines are `run-id: <id>` and `run-dir: <path>`; take both from the background output. Wait for the completion notification.

### 5. Read the results

Read `run.json` in the run folder for each clone's `status` (`done`, `context-full`, `timeout`, `failed`), `cost_usd`, and `original_changed`. Read each clone's output file `<session-id>.md` in the run folder. An empty or missing file means that clone produced nothing. An `original_changed: true` row is reported in the aggregate and its output is still read.

### 6. Merge duplicates across clones

Each output file holds short entries; with the built-in prompt each one is a lesson marked `process` or `domain`. Entries across clones that state the same insight become one candidate, citing every session it came from. Keep the sharpest wording; add no claim that no clone made.

When the run asked for an output other than lessons, the merged candidates go into that output: write or extend the skill, document or checklist the human asked for, then go to step 8 with that file as the written name. Step 7's lesson-write pass is skipped.

### 7. Write through lesson-write

For each candidate, read `.claude/skills/lesson-write/SKILL.md` and follow its steps in place, never through the Skill tool. Payload:

- `category`: the entry's mark.
- `area`, `tags`, `summary`: inferred from the content, within lesson-write's limits.
- `body`: at most 5 lines.
- `source`: `clone-old:<run-id>`.

lesson-write dedupes against the catalog and applies the anti-list. Collect each return value: `created`, `recurrence` and `escalated` count as written, `refined` as merged, `rejected` as rejected.

### 8. Record the run

Run `compass sessions record <run-id> --written <files> --merged <files> --rejected <N>`, passing the lesson filenames lesson-write returned and the number rejected, or, for a run that produced another output, `--written` with that output's path and no `--merged` or `--rejected`.

### 9. Present the aggregate

Terse:

- Each lesson written, or the output file written: its summary and the session ids it came from.
- What merged into existing lessons.
- What was rejected, with the anti-list bucket.
- Per-clone status (`done` / `context-full` / `timeout` / `failed`) and the total cost across clones beside the estimate.
- When clones were kept, the run folder, so `compass sessions show <run-id>/<session-id>` can read one.
