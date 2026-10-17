---
title: "Cloning Old Claude Code Sessions to Advise or Work"
type: research
status: done
confidence: high
area: learning
tags: [sessions, fork, headless, context-window, autocompact, transcript, lessons]
created: 2026-10-16
updated: 2026-10-16
git_branch: master
git_commit: 2c7f5b3
depends_on: ["[[specs/learning/SPEC-022-clone-old-sessions]]"]
summary: "a headless `claude -p --resume <id> --fork-session --no-session-persistence` with DISABLE_AUTO_COMPACT=1 runs a copy of a past session that remembers its work, leaves the original byte-identical, creates no session file, and ends with a clean 'Prompt is too long' at full context; the stream-json output is the whole clone transcript, so Compass can keep it in the vault itself; human sessions are told from Compass workers by entrypoint, and feature sessions by their git commits"
---

# Cloning Old Claude Code Sessions to Advise or Work

Evidence for [[specs/learning/SPEC-022-clone-old-sessions]]. Live probes ran on Claude Code 2.1.302 against this project's transcripts in `~/.claude/projects/F--claude-plugins-compass/`, plus a read-only scan of all 920 transcripts on this machine. Probe outputs sat in the session scratchpad and are not kept.

## Findings

**1. A fork is a working copy that remembers its session, and the original is untouched.** `claude -p --resume <id> --fork-session "<question>"` against a 57K-token past session answered with what that session had done and a specific warning drawn from a failure inside it. The original's SHA-256 was identical before and after. A persisted fork is self-contained: its file held all 62 lines of the original plus its own 19, every line rewritten to the fork's new `sessionId`. Source: live probe; transcript diff. Confidence: high.

**2. `--no-session-persistence` works with `--resume --fork-session` and leaves no file.** The session count in the project directory stayed 10 across two such runs. The docs do not cover the combination; the probe does. Source: live probe; code.claude.com/docs/en/cli-reference. Confidence: high.

**3. With `DISABLE_AUTO_COMPACT=1`, a clone at full context ends cleanly instead of compacting.** A 523K-token session forked onto a 200K model returned at once with `is_error: true`, `result: "Prompt is too long"`, `terminal_reason: "blocking_limit"`, `duration_api_ms: 0`, `total_cost_usd: 0`, exit code 1. The limit is detected locally before any API call, so hitting it costs nothing and is machine-readable. `DISABLE_COMPACT=1` also blocks manual `/compact`. Source: live probe; code.claude.com/docs/en/model-config, /errors. Confidence: high.

**4. A clone's work survives its end only if it writes as it goes.** A non-persisted clone run in stream-json (`--verbose --output-format stream-json`) streams every assistant message, tool call and result to its caller, so the caller holds the clone's whole transcript and can save it anywhere, the vault included, without touching `~/.claude`. Anything the clone writes to files during the run stays. A clone that runs out of context mid-answer loses only the unwritten answer. Source: live probe (11 stream lines, cost $0.29). Confidence: high.

**5. A headless clone needs its tools granted up front.** The working probe's Write was refused with `permission_denied` and the clone reported it could not write. `capture-worker` already solves this for Compass's own headless children: `--allowedTools "Read,Write,Edit,Glob,Grep,Skill,Bash(python:*),Bash(python3:*)"`, stdin closed, `COMPASS_WORKER_SESSION=1` added to the inherited environment so Compass's hooks (capture, context-check, sync side effects) stand down inside the child, output logged under `.compass/tmp/worker-logs/` (`plugin/cli/commands/capture_worker.py:281`, `:300-316`). Source: live probe; code read. Confidence: high.

**6. Session files under `~/.claude/projects` cannot be moved or deleted by an agent in auto mode.** Moving a fork's transcript out and back was denied by the auto-mode classifier as "Session Transcript Tampering". Deleting a persisted clone, or relocating it into the vault, is therefore a human-approved action; a non-persisted clone whose stream Compass saves itself (finding 4) needs neither. Source: live probe. Confidence: high.

**7. Human sessions are told from Compass's own workers by `entrypoint`.** Sessions the human started carry `entrypoint: "cli"`; capture workers and other headless children carry `"sdk-cli"` and open with the extract-lessons prompt. In this project 7 of 10 transcripts are workers. Machine-wide: 920 transcripts, 135 human. Source: transcript scan. Confidence: high.

**8. A session that finished a feature shows it in its own tool calls.** Bash `git commit` calls and `PLAN-NNN` / `TASK-NNN` mentions are in the transcript; the top human sessions carry 46 to 235 commits with messages such as `Merge TASK-001: corpus manifest scanner`. Joining those against the vault (plans whose tasks are all done, `archive/done.md`) names which feature a session finished. 45 human sessions on this machine have 10 or more commits. Source: transcript scan. Confidence: medium; the commit count is a proxy for "a big feature", and the join to plans is untested.

**9. Most feature sessions have little room left.** Of those 45, measured against a 1M window: 2 have under 50K tokens of headroom, 18 have 50K to 200K, 16 have 200K to 500K, 9 more than 500K. A clone starting near full gets a few turns; finding 3 makes its end clean rather than lossy. Source: transcript scan. Confidence: high for the counts; the window is assumed 1M for every session.

**10. Old sessions disappear.** The oldest transcript on this machine was last modified on 2026-09-16, 30 days ago, although this repo's history starts on 2026-03-12. That matches Claude Code's `cleanupPeriodDays`, which deletes transcripts by age: the setting's own description reads "Number of days to retain chat transcripts before automatic cleanup (default: 30). Minimum 1. Use a large value for long retention." This machine now sets it to 3650 in `~/.claude/settings.json`. A session can be cloned only while the setting retains it, or from a copy kept elsewhere. Source: filesystem; code.claude.com/docs/en/settings. Confidence: medium; the mechanism is inferred from the dates.

**11. A clone re-reads its whole history once per call.** The 57K-token question cost $0.45 and the working run $0.29, mostly cache creation over the inherited history. Each clone of a large session pays that on its first call; later turns in the same run read from cache. Source: live probes. Confidence: high.

## Open

- Whether a vault-kept clone transcript can be reopened with `claude --resume` after being copied back into `~/.claude/projects`; the move-and-resume probe was blocked (finding 6).
