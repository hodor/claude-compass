---
title: "Clone Old Sessions to Harvest Their Lessons"
type: plan
status: approved
confidence: medium
area: learning
tags: [sessions, lessons, fork, headless, transcript, retention]
created: 2026-10-17
updated: 2026-10-17
approved: 2026-10-17
git_branch: master
git_commit: 38b1935
author: planner
depends_on: ["[[specs/learning/SPEC-022-clone-old-sessions]]", "[[research/learning/RESEARCH-clone-old-sessions]]"]
summary: "/compass:clone-old ranks the project's past sessions that finished a feature, reading Claude Code's own transcripts in place, and runs a headless non-persisted fork of each with autocompact off; every clone writes its lessons to a file as it goes, the skill aggregates them through lesson-write, kept clones live in a central folder outside every repository, and doctor and setup keep sessions alive through cleanupPeriodDays"
---

# Clone Old Sessions to Harvest Their Lessons

`/compass:clone-old` finds the sessions where a feature was finished, runs a temporary copy of each that writes down the lessons it learned, and presents one aggregated result. The originals are never touched, and no session data enters a repository. This plan implements [[specs/learning/SPEC-022-clone-old-sessions]] on the evidence of [[research/learning/RESEARCH-clone-old-sessions]].

## The waves

One wave. A reader finds the sessions that finished a feature in Claude Code's own transcript folder, a runner clones them, and the skill gathers what the clones wrote into lessons. Kept clones go to a Compass folder in the human's home directory, never into the project. Sessions stay available because Compass checks how long Claude Code keeps them and offers to raise the limit. The wave ends at a live run on this repo that the human watches.

## Prerequisites

- CLI suite passes from the repo root: `python -m pytest plugin/cli/tests -q` reports 1086 passed, 1 skipped.
- Changes land in `plugin/` and ship through self-update.

## Desired End State

The human types `/compass:clone-old` and, with no step in between, gets one aggregated list of lessons written by copies of his past feature sessions. Every original transcript hashes the same before and after. Each kept clone sits in `~/.compass/sessions/<project-key>/` for review, or no transcript is saved when he asked to discard them. The vault holds the lessons and a log of which clones ran, with no transcript text. `compass doctor` warns while Claude Code would delete sessions after 30 days, and setup offers the fix.

## Design

- **No session data in a repository (D-04):** Compass keeps no copies of sessions. It reads transcripts where Claude Code keeps them, read-only: `projects/<project-key>/` under `CLAUDE_CONFIG_DIR` (default `~/.claude`).
- **The project key** is the absolute project path with every non-alphanumeric character replaced by `-`, the encoding Claude Code uses for its own project folders (this repo is `F--claude-plugins-compass`). One key names a project in both places. Two paths that differ only in punctuation share a key, as they already do in Claude Code.
- **Retention (D-04):** `compass retention` reports the effective `cleanupPeriodDays` (local, then project, then user settings, the first that sets it) and, with `--set N`, writes it into the user's `settings.json` under `CLAUDE_CONFIG_DIR`, keeping every other key. `compass doctor` adds a `session retention` row: WARN when the setting is unset or 30 or less, naming the fix `add "cleanupPeriodDays": 3650 to ~/.claude/settings.json` (or `compass retention --set 3650`). The setup skill asks the human once and runs `compass retention --set` only on his yes. Nothing else writes the user's settings.
- **Reading a transcript:** the model is the latest model attachment's id, else the latest non-sidechain assistant message's `model`; a tool input that names a model is never read as the session's. An id without `[1m]` whose session has used more than 200K tokens gets `[1m]` added, since the session ran on the extended window. Commits are Bash `git commit` and `git -C <path> commit` calls in the transcript and in the subagent transcripts of its side folder.
- **Finding feature sessions:** `compass sessions list` reports per session: `entrypoint`, commit count, the `PLAN-NNN`/`TASK-NNN` ids mentioned, the model, tokens used and headroom (`context_check.measure` and `window_for`), and last modified. A feature session is a human session (`entrypoint: cli`, research finding 7) with at least 10 commits (finding 8); `--min-commits` changes the line. A session modified in the last 10 minutes is `active`: an open session is still writing, so `list` marks it and `clone` refuses it.
- **The central folder (D-03):** `~/.compass/sessions/<project-key>/<run-id>/` holds one run: each clone's lesson file `<session-id>.md`, its transcript `<session-id>.jsonl` when kept, and `run.json`. `COMPASS_HOME` replaces `~/.compass`. The folder sits outside every repository, so nothing in it can be pushed.
- **The clone (D-01, D-02):** `compass clone <session-id>...` runs, per session, `claude -p --resume <id> --fork-session --no-session-persistence --verbose --output-format stream-json --model <session's model> --tools Read,Glob,Grep,Write,Edit --allowedTools Read,Glob,Grep,Write,Edit --strict-mcp-config --add-dir <run folder>` with cwd at the project root and the inherited environment plus `DISABLE_AUTO_COMPACT=1` and `COMPASS_WORKER_SESSION=1`. `--tools` limits what exists, so no allow rule in the human's settings and no MCP server hands a clone Bash or another editor; `--add-dir` lets it write its lesson file outside the project. The prompt goes on stdin, which then closes: a Windows `.cmd` launcher cuts a multi-line argument and every argument after it. Binary resolution reuses `capture_worker._resolve_binary`; a resolved dsh binary (deepseek-harness, the other host Compass supports) is refused, since only Claude Code can resume a Claude session.
- **Running clones:** `--jobs` at a time (default 3), each bounded by `--timeout` (default 1800 s). Output is read as UTF-8 line by line and written to the clone's transcript as it arrives; `run.json` is rewritten as each clone ends, so a run cut short keeps everything finished so far. A clone that outlives its timeout is killed with its whole process tree (a new process group, then `taskkill /T` on Windows or a group kill elsewhere). The command records the original's hash, size and modification time before and after.
- **The clone's end:** the final stream `result` line classifies the run: `done`, `context-full` (`is_error` with `Prompt is too long`, finding 3: the normal end of a clone that used its room), `timeout`, or `failed` with the reason.
- **Writing as it goes (finding 4):** the default prompt tells the clone to name the feature it finished and to append each lesson to its lesson file the moment it has one, changing no other file. `--prompt-file` replaces the prompt for other uses (advise, work), with `{output}` filled in. The clone writes to its run folder rather than through `lesson-write` or `capture-note`: parallel clones writing the catalog would race, the skill dedupes across clones before anything lands, and `capture-note` exits at once under `COMPASS_WORKER_SESSION`.
- **Keep or discard (D-03):** by default each clone's stream is saved as its transcript in the central folder, a session kept for review; `--discard` saves no transcript, leaving only the lesson file and `run.json`. No clone leaves a file in `~/.claude/projects`. `compass sessions show <run-id>/<session-id>` prints a kept clone as readable text: the assistant's words and each tool call on one line.
- **The vault's record (D-03):** `.compass/meta/clone-log.jsonl` gets one row per clone from `compass clone` (run id, session id, status, cost, whether the transcript was kept, its path) and one row per run from `compass sessions record <run-id>` (lessons written, merged, rejected). No row carries transcript or lesson text.
- **The skill:** `/compass:clone-old [--discard] [--max N] [--min-commits N]` lists feature sessions with headroom left, states in one line how many it will clone and the tokens they inherit, starts `compass clone` in the background (a run outlasts a foreground shell call), reads every lesson file when it ends, merges duplicates across clones, hands the survivors to `lesson-write` (which dedupes against the catalog and applies the anti-list), records the outcome with `compass sessions record`, and presents the aggregate: each lesson with the sessions it came from, then what merged into existing lessons and what was rejected.
- **Shared file:** `plugin/cli/maincli.py` gets all three new `COMMAND_SPECS` entries (`sessions`, `clone`, `retention`) in TASK-140; a command whose module has not landed answers "not implemented yet".

## Phases

### Wave 1 (detailed): read, clone, harvest

- [x] TASK-140: The transcript reader and the central folder - complexity: M, depends_on: none, files: [plugin/cli/sessionslib.py, plugin/cli/maincli.py, plugin/cli/tests/test_sessionslib.py], decisions: [SPEC-022-clone-old-sessions/D-01, SPEC-022-clone-old-sessions/D-03]
  - `sessionslib` holds what every later task reads: the project key, the transcript folder, the central run folder, entrypoint, model, used tokens, commits, plan and task ids, and `is_active`. It opens transcripts read-only. `maincli` registers `sessions`, `clone` and `retention`.
  - Automated verification: `python -m pytest plugin/cli/tests/test_sessionslib.py -q` passes, covering: `F:\claude\plugins\compass` keys to `F--claude-plugins-compass` and a POSIX path with dots and underscores keys the same way Claude Code's folders do; the transcript folder honors `CLAUDE_CONFIG_DIR` and the run folder `COMPASS_HOME`; the model reader takes the attachment's `[1m]` id, falls back to the assistant message's `model`, ignores a `"model":"haiku"` inside a tool input, and adds `[1m]` past 200K used; `git -C x commit` counts, a commit in a subagent transcript counts, and `git commit` in prose does not; a session modified 5 minutes ago is active; unparseable lines are skipped; reading leaves the transcript's hash and modification time unchanged. Full suite shows no regression.
  - Manual verification: none; TASK-146 reads this repo's sessions.
- [x] TASK-141: `compass retention` and the doctor row - complexity: S, depends_on: none, files: [plugin/cli/commands/retention.py, plugin/cli/commands/doctor.py, plugin/cli/tests/test_retention.py, plugin/cli/tests/test_doctor.py], decisions: [SPEC-022-clone-old-sessions/D-04]
  - As in Design. `--set` refuses a value under 1 and a settings file that does not parse, and writes through a temp file and a rename.
  - Automated verification: `python -m pytest plugin/cli/tests/test_retention.py plugin/cli/tests/test_doctor.py -q` passes, covering: unset, 30 and 3650 report as such; a project or local setting outranks the user's; doctor WARNs on unset and on 30, is OK on 31, and names the fix; `--set 3650` adds the key and leaves every other key and its order intact; `--set` on a missing file creates it; `--set 0` and a malformed file change nothing and exit nonzero with a message. Full suite passes.
  - Manual verification: the human runs `compass doctor` here and reads the row (this machine sets 3650, so it shows OK).
- [x] TASK-142: `compass sessions list`, `show` and `record` - complexity: M, depends_on: TASK-140, files: [plugin/cli/commands/sessions.py, plugin/cli/tests/test_sessions.py], decisions: [SPEC-022-clone-old-sessions/D-03]
  - `list` prints a table and, with `--json`, the fields in Design; `--min-commits`, `--all` (include workers and sessions under the line). `show` renders a kept clone or any transcript as plain text. `record <run-id> --written <lessons> --merged <lessons> --rejected N` appends the run row to `clone-log.jsonl`.
  - Automated verification: `python -m pytest plugin/cli/tests/test_sessions.py -q` passes, covering: a session with 10 commits qualifies and 9 does not; an `sdk-cli` session is left out unless `--all`; headroom uses the session's window; an active session is marked; `show` on a stream-json file prints the assistant text and tool calls and skips unparseable lines, and reads from the central folder by `<run-id>/<session-id>`; `record` appends one row holding lesson names and counts only. Full suite passes.
  - Manual verification: the human reads `compass sessions list` on this repo and agrees the qualifying sessions are ones that finished features.
- [ ] TASK-143: `compass clone` - complexity: M, depends_on: TASK-140, files: [plugin/cli/commands/clone.py, plugin/cli/tests/test_clone.py], decisions: [SPEC-022-clone-old-sessions/D-01, SPEC-022-clone-old-sessions/D-02, SPEC-022-clone-old-sessions/D-03], lessons: [LESSON-headless-worker-denies-tools-silently, LESSON-spawned-sessions-inherit-project-hooks, LESSON-hook-cli-gate-stdin-on-flag]
  - Argv, stdin prompt, environment, concurrency, timeout and tree kill, streaming writes, end classification, central run folder, `run.json`, the per-clone log row, `--discard` and `--prompt-file` as in Design. Session ids must match the UUID shape. A session with no transcript reports `missing`, an active one `active`, and neither runs.
  - Automated verification: `python -m pytest plugin/cli/tests/test_clone.py -q` passes against a stub binary set through `COMPASS_CLAUDE_BIN` (the `test_capture_worker.py` pattern) that records its argv, environment and stdin and replays a canned stream, with `COMPASS_HOME` and `CLAUDE_CONFIG_DIR` in temp folders. Cases: argv carries `--resume <id> --fork-session --no-session-persistence`, the session's model, `--tools`, `--allowedTools`, `--strict-mcp-config` and `--add-dir` naming the run folder; a multi-line prompt arrives whole on stdin and every flag arrives intact; the environment carries `DISABLE_AUTO_COMPACT=1` and `COMPASS_WORKER_SESSION=1` and keeps `CLAUDE_PROJECT_DIR`; non-ASCII stream text is saved intact; a `Prompt is too long` result is `context-full`, not `failed`; a clean result is `done`; a nonzero exit with no result line is `failed`; a stub that spawns a child and sleeps past `--timeout` returns within a few seconds of it as `timeout`, its partial lesson file and transcript lines kept; `run.json` holds the first clone's row while the second still runs; every file the run writes is under `COMPASS_HOME` except the `clone-log.jsonl` row, which holds no stream text; `--discard` writes no `.jsonl` and keeps the lesson file; a stub that alters the original is reported `original_changed`; an active session and a dsh binary are refused; a malformed id leaves no run folder; `--jobs 2` with three sessions never runs more than two stubs at once. Full suite passes.
  - Manual verification: none; TASK-146 runs real clones.
- [x] TASK-144: Setup offers longer session retention - complexity: S, depends_on: TASK-141, files: [plugin/skills/setup/SKILL.md, plugin/cli/tests/test_setup_retention.py], decisions: [SPEC-022-clone-old-sessions/D-04]
  - When `compass retention` reports unset or 30 days or less, setup asks once whether to keep sessions longer and runs `compass retention --set 3650` only on a yes. A no is respected and setup goes on.
  - Automated verification: `test_setup_retention.py` asserts the setup skill names `compass retention --set`, and that every `compass <command>` it names is in `COMMAND_SPECS`. Full suite passes.
  - Manual verification: the human reads the setup step and confirms the question is one he would answer.
- [ ] TASK-145: `/compass:clone-old` skill and version 0.27.0 - complexity: S, depends_on: TASK-142, TASK-143, TASK-144, files: [plugin/skills/clone-old/SKILL.md, plugin/cli/tests/test_clone_old_skill.py, plugin/.claude-plugin/plugin.json], decisions: [SPEC-022-clone-old-sessions/D-01, SPEC-022-clone-old-sessions/D-03]
  - Steps as in Design. The skill never edits, moves or deletes anything under `~/.claude/projects` (finding 6). Its `when_to_use` names the human's triggers ("clone old sessions", "harvest lessons from past sessions").
  - Automated verification: `test_clone_old_skill.py` asserts the frontmatter `name` is `clone-old`, and every `compass <command>` the skill names is in `COMMAND_SPECS`, so a renamed command breaks the test instead of the skill. Full suite passes.
  - Manual verification: the human reads the skill and confirms the aggregate it describes is the one he wants.
- [ ] TASK-146: Live acceptance on this repo - complexity: S, depends_on: TASK-145, files: [.compass/research/learning/RESEARCH-clone-old-sessions.md], decisions: [SPEC-022-clone-old-sessions/D-01, SPEC-022-clone-old-sessions/D-02, SPEC-022-clone-old-sessions/D-03, SPEC-022-clone-old-sessions/D-04]
  - Run `/compass:clone-old` in an interactive session. Record: sessions cloned, each clone's status (at least one `context-full` if a near-full session qualifies), the originals unchanged, the session count in `~/.claude/projects/F--claude-plugins-compass/` unchanged, the lessons written, merged and rejected, and the total cost. Run once more with `--discard` on one session and confirm no transcript is kept. Append the record to the research document.
  - Automated verification: `run.json` shows `original_changed: false` for every clone; `git status --porcelain` shows no change outside `.compass/lessons/`, `.compass/meta/` and the research document; `git grep` for a phrase from a kept clone's transcript finds nothing in the repo.
  - Manual verification: the human reads the aggregated result and judges the lessons worth having.

**Pause point:** when automated verification passes, wait for the human to confirm the manual checks.

## Risks

- **Cost.** Each clone pays one cache write over its whole inherited history (finding 11); 45 feature sessions of 200K to 900K tokens is a real bill. The skill states the count and inherited tokens before it runs, and `--max` caps it.
- **Kept clones hold secrets in plain text on the local disk.** The central folder holds whatever the sessions said and read, the same exposure `~/.claude/projects` already has; it is outside every repository, so it cannot be pushed, but backups and other local users can read it.
- **A clone with Write and Edit can change files other than its output.** The prompt forbids it and `--tools` leaves it no Bash and no MCP tools; TASK-146 checks `git status` after the run.
- **A session Claude Code has deleted cannot be cloned.** Retention is the only protection; a project whose human declines the longer setting keeps 30 days.
- **Transcript fields are undocumented** (`entrypoint`, the model attachment, `usage`, the side folder). The reader skips what it cannot parse and the tests pin today's shape.
- **The commit count is a proxy for a finished feature** (finding 8, medium confidence). TASK-142's manual check is where the human judges it.

## Verification

- `python -m pytest plugin/cli/tests -q` passes.
- TASK-146's live record shows unchanged originals, clean clone ends, an aggregated set of lessons, and no session text in the repository.

## Revision Log

- 2026-10-17: Storage follows SPEC-022's revised D-03 and D-04: no session data inside a repository. Compass keeps no copies of sessions; retention comes from Claude Code's `cleanupPeriodDays`, checked by `compass doctor` and offered by setup. Kept clones live in `~/.compass/sessions/<project-key>/`, and the vault logs only which clones ran and what they produced. The store command, its hooks, the in-vault session folder and the stored-copy probe left the plan.
