---
title: A Python `compass` CLI Owns All Mechanical Vault Work; the Hook Calls It as a Command
type: decision
status: approved
confidence: high
area: methodology
tags: [cli, python, hooks, automation, token-efficiency, mcp-rejected]
created: 2026-06-13
updated: 2026-06-13
git_branch: "master"
git_commit: "pending"
author: "roger + claude"
depends_on: ["[[SPEC-004-mechanical-work-off-the-agent-budget]]", "[[RESEARCH-cli-and-hook-command-contract]]", "[[LESSON-no-agent-bookkeeping]]", "[[ADR-003-drop-counter-file-jit-compute]]", "[[ADR-004-hierarchical-specs-with-facets]]"]
summary: "A Python `compass` CLI Owns All Mechanical Vault Work; the Hook Calls It as a Command"
---

## Status

Approved. Implements [[SPEC-004-mechanical-work-off-the-agent-budget]].

## Context

SPEC-004 requires every deterministic vault operation to run as a real program, off the agent's token budget. The mechanical work already exists, scattered as protocol prose inside `index-sync`, `vault-health`, `promote-spec`, and an LLM-typed PostToolUse hook that fires on every vault write. We need to choose the form of the program, its host language, its command surface, and how the hook reaches it.

## Decision

Build a single **`compass` command-line program in Python**, shipped at `plugin/bin/compass`. Convert the PostToolUse hook from `type: agent` to `type: command` running `compass sync`. Shrink the mechanical skills to thin wrappers that invoke the CLI and surface its output.

### Why a CLI, not MCP

MCP was considered and rejected. The dominant cost is the **PostToolUse hook firing on every write** — a fixed, non-interactive, exit-code-shaped event. A hook can already run an arbitrary command directly; routing it through an MCP server adds a process, a protocol, and a handshake to a path that needs none. MCP earns its keep when a model needs to *choose* to call a tool mid-reasoning with structured arguments; here the caller is a hook, not a reasoning step. For the rare interactive case (a human or agent running `compass validate`), shelling out to a CLI is strictly simpler than standing up a server. MCP solves a problem we do not have and does not help the one we do.

### Why Python, not Go

The goal is to **ship and prove the SPEC-004 hypothesis**, not to optimize. Python has zero build step, is already assumable on developer machines, reads close to the pseudo-code of the operations, and keeps the iteration loop tight while the command surface is still settling. Startup latency (tens of ms) is irrelevant against the seconds an agent round-trip costs — the comparison that matters. If profiling later shows Python startup dominates at scale, a rewrite is a contained follow-up; the CLI contract stays the same.

### Command surface

| Command | Does |
|---|---|
| `compass sync` | Regenerate root `index.md` + `meta/tag-index.yaml` from disk; flag stale branch summaries; detect hot-path cap breach. The hook's single entry point. |
| `compass next-num <type> [parent]` | Print the next local artifact number for a type (spec/adr/plan/...), max+1 from the filesystem per ADR-003/ADR-004. |
| `compass validate` | Check wikilinks (skipping code per `[[LESSON-wikilink-validator-skip-code]]`), required frontmatter, and hot-path token cap. Non-zero exit + precise report on any defect. |
| `compass tree` | Render the hierarchical spec/folder tree. |
| `compass hot-path` | Print the current hot-path token count against the 5,000 cap. |
| `compass promote <spec>` | Mechanical half of flat→folder promotion: move the file, rewrite inbound wikilinks. Judgment (summary text) stays with the agent. |
| `compass clean-tmp` | Delete `tmp/extraction-log-*.md` older than 30 days. |
| `compass touched <spec>` | Record a working-set marker for admission control (ADR-004). |
| `compass admit-check <spec>` | Exit 0/1 for whether the spec may enter the hot path. |

`sync` is composite: it is `tag-index` + index regeneration + staleness/cap checks in one call, because the hook needs exactly one invocation per write.

### How the hook calls it

`plugin/hooks/hooks.json` PostToolUse changes from `type: agent` (thousands of tokens) to `type: command` running `compass sync`. The contract is grounded in `[[RESEARCH-cli-and-hook-command-contract]]`; four facts drive the implementation:

- **Fail-safe means never exit 2.** A command hook that exits `2` *blocks the user's write* and shows stderr as a blocking message. `compass sync` must trap every exception and exit `0` (or `1`), never `2`. A bug in sync must never block or destroy the human's edit (SPEC-004 safe-degrade constraint).
- **Input arrives on stdin as JSON**, not argv: `{tool_name, tool_input.file_path, cwd, ...}`, with `CLAUDE_PROJECT_DIR` in the environment. So `compass sync` has two modes: hook mode (parse stdin JSON, locate vault via `CLAUDE_PROJECT_DIR`) and human mode (no stdin, operate on the whole vault).
- **Loop prevention moves into code.** Sync writes `index.md` and `meta/tag-index.yaml`; each Write re-fires PostToolUse. In hook mode, sync reads the triggering `file_path` and exits 0 immediately if it is one of its own generated outputs (`index.md`, `meta/tag-index.yaml`, `meta/lessons-catalog.yaml`, `meta/working-set.yaml`). This is the deterministic replacement for the current prompt-level no-op check, and it is a test-suite case.
- **Silent success.** On a normal write, sync prints nothing (or `{"suppressOutput": true}`) and exits 0 — zero visible agent tokens. Only a real defect surfaces a `systemMessage`.

The current three-entry Write/Edit/MultiEdit split exists because the `if` clause cannot express `||` (`[[LESSON-hook-if-clause-no-or]]`). The research found the `matcher` field *does* support alternation (`"Write|Edit|MultiEdit"`), and a command hook self-filters the path from stdin, so the split may collapse to a single entry with no `if` guard. This collapse is gated on verifying the plugin hook schema honors matcher alternation (RESEARCH OQ1); the three-entry form is the fallback if it does not.

### How skills shrink

`index-sync`, the mechanical parts of `vault-health`, and the file-moving half of `promote-spec` collapse to: invoke the relevant `compass` command, read its exit code and report, surface findings to the human. The reasoning skills (spec, plan, research, validate, consolidate, extract-lessons) are untouched.

## Alternatives considered

- **MCP server.** Rejected: adds a protocol and a process to a hook-driven, exit-code-shaped path that gains nothing from structured mid-reasoning tool calls. See "Why a CLI" above.
- **Go (or Rust) binary.** Rejected for now: build step and slower iteration buy runtime speed that is irrelevant next to agent round-trip cost. Revisit only if Python startup is ever shown to dominate.
- **Keep the LLM-typed hook, just trim the prompt.** Rejected: still non-deterministic (goal 1/2 risk) and still spends tokens on every write. Trimming reduces the symptom, not the cause.
- **A shell script instead of Python.** Rejected: the operations (frontmatter parsing, token counting, wikilink graph walking) are awkward and platform-fragile in shell; the CRLF and glob lessons bite hardest there.

## Consequences

**Easier:**

- PostToolUse upkeep drops to ~zero agent tokens; the hot path stops being perturbed by hook fires.
- Vault upkeep becomes deterministic and testable with golden-output fixtures.
- Mechanical skills shrink from hundreds of lines of protocol to a few lines of "call and surface."
- One place owns numbering, indexing, and validation, instead of the same logic restated across several skill files.

**Harder:**

- A new build artifact (`plugin/bin/compass`) and its tests must ship with the plugin and survive `/compass:bootstrap`.
- Re-implementing skill logic in code risks behavior drift; golden tests against the current vault are the guard.
- A program in the hook path must fail safe; a crashing `compass sync` must never block or corrupt the user's write.
- Python must be present wherever the hook runs. Acceptable: Compass already targets developer machines and Claude Code environments where Python is standard.

## Load-bearing risks

- The 80% token-reduction figure in SPEC-004 is the falsification target. It must be *measured* on a real editing session, not asserted — the same honesty the SPEC-003 30% claim was held to.
- "Byte-identical-or-better" index output depends on pinning golden fixtures before shrinking any skill. If the fixtures are captured from a wrong current state, the tests enshrine the bug.
