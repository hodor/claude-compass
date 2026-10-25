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
summary: "a small Obsidian plugin raises the review document over whatever has focus, takes the verdict from Approve / Needs changes buttons, and minimizes to return the human; a waiting CLI process wakes the session on the verdict file - proven end to end on Windows, other platforms and multi-document reviews untested"
taxonomy_hint: "the human's review surface; sits beside SPEC-030 at the research root"
---

# Reviewing Compass Documents in Obsidian

Evidence for [[SPEC-030-review-documents-open-in-obsidian]]. The human's own question led: he types in Obsidian, presses a button when done, and the session takes the verdict and acts, returning him to whatever he was doing without visiting Claude Code.

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

## Gaps

These need another research pass before a plan:

- macOS, Linux, WSL, and remote or headless sessions (Obsidian on another machine than the CLI).
- Hosts other than Claude Code: Codex and dsh have no `run_in_background` wake-up.
- Reviews that are not one file: the `specs` batch, the `consolidate` grouping proposal, a diff.
- The human editing in Obsidian while an agent writes the same file.
- Prior art: Obsidian Local REST API and MCP-server plugins.
