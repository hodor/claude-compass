---
title: A CLI invoked both interactively and by a hook must gate stdin reads on an explicit flag
type: lesson
status: active
category: process
area: workflow
tags: [cli, hooks, stdin, argparse, non-interactive, hang]
created: 2026-06-14
updated: 2026-06-14
score: 5
summary: "Gate hook-stdin reads behind an explicit flag (--hook), not isatty probing; probing blocks forever in a non-interactive shell with no piped input"
seen: []
---

A command that runs both at a human terminal and from a PostToolUse hook must not auto-detect "am I a hook?" by probing stdin (`isatty()` then `read()`).
In a non-interactive shell with no piped input (a skill's Bash call, CI, a background process), `isatty()` is False but `read()` blocks forever waiting for input that never comes - the process hangs.
Gate the stdin read behind an explicit flag the hook passes (e.g. `compass sync --hook`); the human/skill path then never touches stdin and cannot hang.
Pass-through of a `--`-prefixed flag also does not compose with argparse subparsers (even `nargs=REMAINDER`): argparse intercepts `--hook` at the top level. Split argv manually - first token is the command, the rest go to the command verbatim.
Both bugs surfaced only when the CLI was exercised the way a hook actually invokes it (piped/empty stdin), not in an interactive terminal - test the real invocation path. Relates to [[LESSON-no-agent-bookkeeping]].
