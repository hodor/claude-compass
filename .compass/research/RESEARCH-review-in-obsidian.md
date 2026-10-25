---
title: "Reviewing Compass Documents in Obsidian"
type: research
status: draft
confidence: medium
area: methodology
tags: [obsidian, review, human-gates, plugin, focus]
created: 2026-10-24
updated: 2026-10-24
author: "researcher"
depends_on: ["[[SPEC-030-review-documents-open-in-obsidian]]"]
summary: "a small Obsidian plugin raises the review document over whatever has focus, takes the verdict from Approve / Needs changes buttons, and minimizes to return the human; a waiting CLI process wakes the session on the verdict file - proven end to end on Windows; ranks seven Compass features for an Obsidian UI, led by a review inbox and a loop dashboard; macOS, Linux, WSL and non-Claude hosts untested"
taxonomy_hint: "the human's review surface; sits beside SPEC-030 at the research root"
---

# Reviewing Compass Documents in Obsidian

Evidence for [[SPEC-030-review-documents-open-in-obsidian]]. The human's own questions led: he types in Obsidian, presses a button when done, and the session takes the verdict and acts, returning him to whatever he was doing without visiting Claude Code; and which Compass features would make sense as a UI in Obsidian.

Grading: **live** = run on this machine (Windows 11, Obsidian 1.13.7 installer, Claude Code CLI inside zellij 0.44.3 in Windows Terminal); **doc** = Obsidian's official help; **forum** = third-party writeups.

## Findings

### 1. Opening a file from outside Obsidian

- `obsidian://open?path=<percent-encoded absolute path>` opens the file in the vault that contains it and replaces the last active tab; repeated opens reuse that tab, no tab pile-up. Confidence: high (live; doc for the tab rule, `paneType=tab|split|window` overrides it).
- `os.startfile` returns in ~0.06 s; the URI handler is registered by the installer (`HKCR\obsidian\shell\open\command`). Linux needs a hand-made `.desktop` entry. Confidence: high (live, doc).
- A path inside no known vault opens nothing, registers no vault, creates no `.obsidian/`. Confidence: medium (live; what Obsidian displayed was not observed).
- A heading is reached by an encoded `#` in the file value (`Note%23Heading`). Confidence: medium (doc; the live attempt left no trace in `workspace.json` to confirm the scroll).
- Obsidian 1.12.7+ ships an official CLI (`obsidian open path=... newtab`, `obsidian vaults verbose`, `eval`), off by default under Settings, General; it is not enabled on this machine and the URI covers every need found. Confidence: medium (doc).

### 2. Where Compass asks for review

Every gate goes through `AskUserQuestion` (69 call sites across 23 skill and agent files). The ones whose subject is a document: `spec` "Approve this spec?", `plan` and `planner` "Approve this plan?", `research` "Run research on these axes?", `vision` "Does this list cover everything?", `specs` "Confirm this spec list?" and "How do you want to review these specs?", `consolidate` "Create the `<domain>` domain and move these files?" (a proposal, no file yet), `build` "Review the manual verification items from the plan?", `autopilot` "Proceed with implementation?". The rest pick options (category, area, which task) and have no document. Confidence: high (code read: `plugin/skills/*/SKILL.md`, `plugin/templates/agents/*.md`).

### 3. Knowing a project is configured

`%APPDATA%\obsidian\obsidian.json` lists every vault by id and path, with `"open": true` on the open one; a `.obsidian/` folder marks a vault root. This repo's `.compass/` is registered (id `f88664dc280ee384`). Community plugins load only after the human leaves restricted mode and enables each plugin by hand, per vault. Confidence: high (live).

### 4. The verdict reaching the session

- A background process the session starts (`run_in_background`) that polls a file and exits wakes the session with its output. Proven twice: a frontmatter checkbox flip, then the plugin's verdict file. Confidence: high (live).
- Obsidian rewrites frontmatter it touches through the properties panel (`title: "Review test"` became `title: Review test`); the session must re-read the file and its parsers must accept either form. Confidence: high (live).
- Claude Code's channels (an MCP server pushing events into a session, research preview since v2.1.80) need a startup flag, and a development flag for a custom server; the polling process covers the need without them. Confidence: medium (forum: vibesparking.com, lilting.ch).

### 5. Returning the human

- Focusing the terminal from the session failed twice. Windows Terminal runs every window in one process, so the process's main window is a different window from the session's (here "work" against "personal"); title matching failed because the title changes. Windows also refuses foreground to background callers; a synthetic Alt tap made `SetForegroundWindow` succeed on the wrong window. Confidence: high (live).
- The working shape returns the human by stepping Obsidian aside: the plugin records whether Obsidian had focus when the request arrived, and after the click minimizes Obsidian (hides it on macOS) so the OS gives focus back to the previous window. The request carries `"return": true` when Obsidian lacked focus. Confidence: high for the round trip (live, the human confirmed), low for macOS and Linux (untested).

### 6. The prototype that passed

`.compass/.obsidian/plugins/compass-review/` (main.js, manifest.json, styles.css) with a driver at the session's scratchpad (`review_request.py`). Protocol, all under the vault's `tmp/review/`: Compass writes `<id>.request.json` (`id`, `file`, `title`, `return`) and opens `obsidian://compass-review?vault=<id>&id=<id>`; the plugin raises its window (brief always-on-top), opens the file, and shows a bar with a notes box, Approve and Needs changes; a click saves the editor, writes `<id>.verdict.json` (`verdict: approved|changes`, `notes`, `at`), and steps aside. Pending requests found at startup get their bar without being raised. Run at 19:40:04, approved at 19:42:27 with the human's typed edit present in the file read back. Confidence: high (live).

### 7. Compass features that would gain an Obsidian UI

Ranked by how often the human meets the feature and how much a view beats terminal text. Use counts from `compass usage` since 2026-09-13.

| Rank | Feature | UI | Built on | Why |
|---|---|---|---|---|
| 1 | Every document gate (spec, plan, research axes, vision list, manual verification items) | The review bar of finding 6, extended with per-item checkboxes for lists | The prototype | The human's most frequent decision point; the document is the thing decided on |
| 2 | A review inbox: everything waiting on the human | A pinned note with an embedded base over `status: draft` specs, unapproved plans, pending `tmp/review/` requests | Bases (core) | Today the waiting set is scattered across `active.md` lines and frontmatter |
| 3 | Control loops (`loop`, 120 uses) | A loop dashboard: state, last reading, spend against budget, unreviewed runs with Accept / Reject buttons calling `compass loop review` | Plugin view | Review of increments is a gate the human currently does by CLI |
| 4 | Lessons (files with `category`, `area`, `tags`, `score`, `summary`) | A lessons table filtered by area and category | Bases, zero code | The frontmatter already carries every column |
| 5 | Vault health (`validate`, `doctor`, 44 uses together) | A sidebar listing current warnings, each linking to its file | Plugin view | Warnings print in the terminal and are forgotten |
| 6 | Consolidate's grouping proposal | A canvas: one group per proposed domain, members inside; the human moves cards, then approves | Canvas (core, JSON `.canvas`) | A proposal of moves is spatial; text diffs of moves are hard to read |
| 7 | `active.md` tasks (18 open) | A board by section | Plugin view; Bases cannot, tasks are lines, not files | Useful, but `active.md` already reads well in Obsidian |

Lesson capture stays out: it is invisible by design ([[specs/tooling/SPEC-018-scaffolding-invisible-to-the-human]]). Confidence: medium (code read and usage record; value is judgment).

### 8. What Obsidian already provides

- Bases, a core plugin: database views over notes and their properties (table, list, cards, kanban by a grouped property, map), filters and formulas, edits write back to the notes' properties, embeddable as a code block in any note. Confidence: high (doc).
- Canvas: a core plugin storing nodes and groups as JSON, so Compass can write a proposal as a `.canvas` file and read the human's rearrangement back. Confidence: medium (doc knowledge; not run).
- Meta Bind: buttons whose `updateMetadata` action writes a property; one more community install per user. Confidence: high (plugin docs).

### 9. Prior art

`coddingtonbear/obsidian-local-rest-api` (3.6.x) serves REST and an MCP server on `127.0.0.1:27124` with a bearer key: read and patch files down to a heading or frontmatter field, list and run Obsidian commands, and `POST /open/{path}` to open a file in the UI. It has no review or verdict concept; Compass's plugin needs only its own small protocol, and the REST plugin is the reference if Compass ever needs in-Obsidian reads or commands from the agent. Confidence: medium (README).

### 10. Reviews that are not one file

- `specs` batch ("Approve all / Review one by one / Approve some"): one request listing several files; the bar shows on each, with the batch verdict on a generated summary note. Confidence: low (design reading of `plugin/skills/specs/SKILL.md`).
- `consolidate` proposal: written as a canvas (finding 7). Confidence: low.
- A diff: Obsidian has no native diff view; the verdict note can embed the changed sections. Confidence: low.

### 11. The human and an agent editing one file

Obsidian merges an external change into an open note automatically when the editor holds unsaved edits from the last ~2 seconds, with the notice "has been modified externally, merging changes automatically"; users report lost and shuffled words, and there is no setting to turn it off. A file under review must have one writer: the agent does not write it until the verdict, which `compass guard` can enforce by denying writes to any file with a pending `tmp/review/` request. Confidence: medium (forum, several independent reports; not run).

### 12. Other platforms and hosts

- macOS: `app.hide()` returns focus to the previous app; `open obsidian://...` opens the link. Confidence: medium (Electron docs; untested).
- Linux on Wayland: compositors refuse `focus()` without an xdg-activation token. A link opened through the desktop launcher starts a second instance, and Electron forwards that launch token to the running window, so raising through `obsidian://` may work where a plugin-initiated raise fails. The URI handler needs a hand-made `.desktop` entry. Confidence: low (Electron docs and issues; untested).
- WSL: the CLI runs in Linux while Obsidian runs in Windows; the link opens through `cmd.exe /c start` or `wslview`, and the vault path converts between `/mnt/f/...` and `F:\...`. Confidence: low (untested).
- Remote or headless sessions, where Obsidian is on another machine: no path found. Confidence: high that it does not work.
- Codex and dsh have no background wake-up; a review there runs as a blocking foreground command, bounded by the host's tool timeout (Compass's own hook timeouts sit at 300 s in `plugin/cli/hostlib.py`). Confidence: low (reading; untested).

## Gaps

- Live runs on macOS, Linux (X11 and Wayland) and WSL.
- The blocking-command wake-up under Codex and dsh, and its timeout.
- The canvas round trip for a consolidate proposal.
