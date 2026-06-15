---
title: How Claude Code Structures CLIs and the Command-Hook Contract
type: research
status: active
confidence: high
area: methodology
tags: [cli, hooks, command-hook, claude-code, reference, argparse, fail-safe]
created: 2026-06-13
updated: 2026-06-13
depends_on: ["[[SPEC-004-mechanical-work-off-the-agent-budget]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
source: "F:\\AI\\coding\\claude-code (TypeScript Claude Code source)"
---

# How Claude Code Structures CLIs and the Command-Hook Contract

Read of the Claude Code TypeScript source to ground SPEC-004's `compass` CLI and the ADR-005 decision to convert the PostToolUse hook from `type: agent` to `type: command`. Two questions: (1) the exact contract a command-type hook must satisfy, (2) the CLI subcommand-dispatch pattern worth mirroring.

## Findings that change the design

### F1. A command hook can BLOCK the user's write via exit code 2 (confidence: high)

`utils/hooks.ts:2617-2697`. Exit-code semantics for a PostToolUse command hook:

| Exit | Effect on the user's edit |
|---|---|
| `0` | Success. stdout shown (or suppressed). Edit proceeds. |
| `2` | **Blocks the tool. stderr is shown as a blocking message.** |
| `1`, `3+` | Non-blocking error. stderr shown, edit proceeds. |

**Design consequence:** `compass sync` is in the write path. A crash that exits 2 would block Roger's edit. The CLI MUST trap every exception and exit `0` (preferred) or `1`, **never `2`**, on any internal failure. This is the SPEC-004 safe-degrade constraint made concrete: fail-safe is not aspirational, it is "never let a non-zero-but-2 escape." Golden rule for the hook entry point: wrap `main()` in a catch-all that prints a one-line warning to stderr and exits 1.

### F2. The 3-way hook split can collapse to one entry (confidence: medium)

Current `plugin/hooks/hooks.json` splits PostToolUse into three entries (Write, Edit, MultiEdit) because the **`if` clause** uses permission-rule syntax that does not support `||` (`[[LESSON-hook-if-clause-no-or]]`). But two facts change this for a command hook:

- The **`matcher` field DOES support pipe alternation** (`utils/hooks.ts:1346-1381`): `"matcher": "Write|Edit|MultiEdit"` matches any of the three. The `matcher` and the `if` clause are different fields with different grammars; the lesson constrains only `if`.
- A command hook can read the triggering file path itself from stdin (F3) and self-filter, removing the need for the `if(.compass/**/*.md)` path guard entirely.

So the three agent entries with `if` guards may become **one command entry** with `"matcher": "Write|Edit|MultiEdit"` and path-filtering inside `compass sync`. Confidence is medium until verified against the running harness, because the plugin hook schema may constrain `matcher` differently than the core matcher tested here.

### F3. The hook passes data on stdin as JSON, not on argv (confidence: high)

`utils/hooks.ts:1006,3460-3467`; schema `entrypoints/sdk/coreSchemas.ts`. A command hook receives a single JSON object on **stdin** (one line, trailing newline):

```json
{
  "session_id": "...",
  "transcript_path": "/abs/path",
  "cwd": "/working/dir",
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": { "file_path": "...", "content": "..." },
  "tool_response": { ... },
  "tool_use_id": "uuid"
}
```

Environment adds `CLAUDE_PROJECT_DIR` (stable project root, POSIX path on Windows bash) and, for plugin hooks, `CLAUDE_PLUGIN_ROOT`. **Tool name and file path are NOT in env — only on stdin.**

**Design consequence:** `compass sync` has two invocation modes that must both work:
- **Hook mode:** stdin carries the JSON. Read `tool_input.file_path` to know what changed; use `CLAUDE_PROJECT_DIR` to locate the vault.
- **Human mode:** `compass sync` typed at a terminal, no stdin JSON. Operate on the whole vault.

The entry point detects which by testing whether stdin is a TTY / is empty vs. parseable JSON.

### F4. Loop prevention is now the CLI's job, not a prompt instruction (confidence: high)

The current agent hook prevents an infinite loop with a prompt instruction: "if the file is `index.md` or `lessons-catalog.yaml`, no-op, because sync writes those files and would re-trigger itself." With a command hook the same hazard exists — `compass sync` writes `index.md` and `meta/tag-index.yaml`, each Write re-fires PostToolUse — but the guard moves into code. `compass sync` in hook mode must read `tool_input.file_path` from stdin and **exit 0 immediately if the triggering path is one of its own generated outputs** (`index.md`, `meta/tag-index.yaml`, `meta/lessons-catalog.yaml`, `meta/working-set.yaml`). This is the deterministic replacement for the prompt-level no-op check and belongs in the test suite.

### F5. Optional stdout JSON can suppress output or inject context (confidence: high)

`types/hooks.ts:50-166`. A command hook may print a JSON object on stdout to control surfacing: `{"suppressOutput": true}` hides it, `{"systemMessage": "..."}` warns the user, `{"hookSpecificOutput": {"additionalContext": "..."}}` injects context. For the silent-success path SPEC-004 wants, `compass sync` should print nothing (or `{"suppressOutput": true}`) and exit 0, so a normal write costs the agent zero visible tokens. Only a real problem (e.g. validation failure) should surface a `systemMessage`.

### F6. Timeout is generous and configurable (confidence: high)

`utils/hooks.ts:166,877`. Default hook timeout is 10 minutes; per-hook `timeout` (seconds) overrides it (the current entries set 60). A killed hook is treated as a non-blocking error. `compass sync` should finish in milliseconds, so the existing 60s ceiling is ample headroom.

## CLI dispatch pattern (for mirroring in Python)

Claude Code uses **Commander.js** with lazy-loaded handlers (`main.tsx:902,3887`; subcommands via `.command('name').action(...)` with dynamic `import()` inside the action). Transferable conventions worth copying into the Python CLI:

- **Subcommand registry, metadata-driven.** Each command is a small object (`name`, `description`, `argumentHint`, handler). Python equivalent: `argparse` subparsers or `click.Group`, one module per command, handler imported on dispatch.
- **Dual output mode.** Handlers support `--json` (structured, for scripts/hooks) and `--text` (human). `cli/handlers/auth.ts:232-320` is the model: same computation, two renderings.
- **Centralized exit helpers.** `cli/exit.ts`: `cliOk(msg)` writes stdout + exit 0; `cliError(msg)` writes stderr + exit 1. Mirror with two tiny Python helpers so every command exits consistently — and so the hook entry point's "never exit 2" rule lives in one place.
- **Read-only vs mutating commands are explicitly tagged** (`commands.ts:619-660` REMOTE_SAFE / BRIDGE_SAFE sets). For `compass`, `validate`/`tree`/`hot-path`/`next-num` are read-only; `sync`/`promote`/`clean-tmp`/`touched` mutate. Worth a flag in each command's metadata for testability and for a future `--dry-run`.

Standard library `argparse` covers everything needed; no third-party dependency, which serves the SPEC-004 constraint of assuming nothing a fresh bootstrap cannot.

## Open questions

- **OQ1 (feeds the plan):** Does the *plugin* hook schema honor `"matcher": "Write|Edit|MultiEdit"` the same way the core matcher does (F2)? If yes, the 3-entry split collapses to one. Verify empirically before committing the hooks.json rewrite; keep the 3-entry form as the fallback.
- **OQ2:** Does a Write that produces byte-identical content still fire PostToolUse? If it does not, idempotent `compass sync` partially self-limits even without the F4 path guard. The guard is still required (content usually does change), but the answer affects how aggressively sync should skip no-op writes.

## Source references

- Hook execution / spawn / stdin / env: `utils/hooks.ts:747-1335,881-926`
- Exit-code semantics: `utils/hooks.ts:2617-2697`
- stdout JSON response schema: `types/hooks.ts:50-166`
- Matcher alternation: `utils/hooks.ts:1346-1381`
- PostToolUse input construction: `utils/hooks.ts:3450-3477`; schema `entrypoints/sdk/coreSchemas.ts`
- CLI entrypoint + Commander: `main.tsx:902,3887`; bootstrap fast-paths `entrypoints/cli.tsx:33-299`
- Command type model: `types/command.ts:175-206`; registry `commands.ts:258,476`
- Exit helpers: `cli/exit.ts:18-31`; dual-output handler `cli/handlers/auth.ts:232-320`
