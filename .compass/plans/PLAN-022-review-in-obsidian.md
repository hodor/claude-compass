---
title: "Review Documents in Obsidian"
type: plan
status: approved
confidence: medium
area: methodology
tags: [obsidian, review, human-gates, plugin]
created: 2026-10-24
updated: 2026-10-25
approved: 2026-10-24
depends_on: ["[[SPEC-030-review-documents-open-in-obsidian]]", "[[RESEARCH-review-in-obsidian]]"]
summary: "the Compass Review Obsidian plugin, a `compass review` command, install, doctor and guard support; gate wiring follows an experiment"
---

# Review Documents in Obsidian

## Goal

This plan implements [[SPEC-030-review-documents-open-in-obsidian]] based on [[RESEARCH-review-in-obsidian]]. When a project's vault is open in Obsidian with the Compass Review plugin on, every document Compass asks the human to review comes forward in Obsidian with Approve and Needs changes buttons; the click hands the verdict and the human's edits to the session and returns him to whatever he was doing.

## The waves

**Wave 1** turns the prototype that passed the live round trip into shipped parts: the plugin itself, a `compass review` command that sends a document and waits for the verdict, an install path through setup and update, a doctor check that walks the human through turning the plugin on, a guard rule that keeps agents out of a file while it is under review, and two Bases views (a review inbox and a lessons table) that need no plugin code. Compass speaks one review protocol to any visual md interface; Obsidian is its first implementation, and a VS Code extension plugs in the same way. It also runs one experiment: whether a verdict that lands while a terminal question is open reaches the session, which decides how gates ask. Wave 1 ends when the human has run one real review through the shipped parts.

**Wave 2** wires the review into every gate whose subject is a document, in the shape the experiment chose, and closes with a live spec approval done entirely from Obsidian.

## Prerequisites

- Obsidian 1.4 or later on the machine running the session, the vault registered in Obsidian's vault list.
- The suite green at the start: 1659 passed on 2026-10-24.

## Desired End State

- A Compass project whose vault is open in Obsidian with Compass Review on gets every document review in Obsidian; any other project behaves exactly as before.
- Configuration is detected, never asked: the vault is in Obsidian's vault list and the plugin is enabled in that vault.
- The human can answer from Obsidian or from the terminal; either verdict is taken.

## What We're NOT Doing

- The loop dashboard, vault-health sidebar, consolidate canvas, task board, and chat in Obsidian: under Later.
- macOS, Linux and WSL support beyond what the code handles untested; Codex and dsh hosts.

## Phases

### Wave 1 (detailed): shipped parts and the question experiment

- [x] TASK-165: Ship the Compass Review plugin at `plugin/obsidian/compass-review/` from the prototype in `.compass/.obsidian/plugins/compass-review/`, with a Node test harness that stubs the `obsidian` module and drives the request, bar, verdict and step-aside paths - complexity: M, depends_on: none, files: [plugin/obsidian/compass-review/main.js, plugin/obsidian/compass-review/manifest.json, plugin/obsidian/compass-review/styles.css, plugin/obsidian/tests/test_main.js, plugin/cli/tests/test_obsidian_plugin.py], decisions: [SPEC-030-review-documents-open-in-obsidian/D-02]
  - Automated verification: `node --check` on main.js; the harness passes, including a verdict written for a request whose file was renamed, a request with no id, and a second request for the same file replacing the first; the Python wrapper runs the harness and skips when Node is absent.
  - Manual verification: the human turns the shipped plugin on in this vault and sees the bar on a requested file.
- [x] TASK-166: `compass review <file> [--title T] [--timeout S] [--no-wait]` writes the request under the vault's `tmp/review/`, opens the `obsidian://compass-review` link, waits for the verdict, and prints the verdict JSON then the file as the human left it; the first line says `requested <id> <file>` or `not configured: <why>`; exit 0 on a verdict, 1 when not configured or on timeout, never 2 like every compass command; `compass review --status` prints pending requests and `--install` copies the plugin into the vault - complexity: M, depends_on: none, files: [plugin/cli/commands/review.py, plugin/cli/reviewlib.py, plugin/cli/maincli.py, plugin/cli/tests/test_review.py], decisions: [SPEC-030-review-documents-open-in-obsidian/D-02]
  - Automated verification: tests cover a vault outside Obsidian's list, a file outside any vault, a verdict written mid-wait, a malformed verdict file, timeout, and the focus flag set from a stubbed foreground probe; full suite passes.
  - Manual verification: `compass review .compass/tmp/review-test.md` from this session raises Obsidian, and a click returns the human to the window he was in.
- [x] TASK-167: `compass guard` denies a subagent's Write or Edit to a file that has a pending review request, naming the request and that the file is the human's until the verdict - complexity: S, depends_on: TASK-166, files: [plugin/cli/commands/guard.py, plugin/cli/tests/test_guard.py]
  - Automated verification: tests for a pending request (denied), an answered request (allowed), a request for another file (allowed), the main agent (allowed); full suite passes.
  - Manual verification: none.
- [ ] TASK-168: Setup and update copy the plugin into the vault's `.obsidian/plugins/compass-review/` when `.obsidian/` exists, add it to `community-plugins.json` without dropping other entries, and never create `.obsidian/`; doctor reports the plugin as absent, installed but off, or on, and when off prints the steps to turn it on (Settings, Community plugins, leave restricted mode, enable Compass Review) - complexity: M, depends_on: TASK-165, files: [plugin/skills/setup/SKILL.md, plugin/skills/update/SKILL.md, plugin/cli/commands/self_update.py, plugin/cli/commands/doctor.py, plugin/cli/tests/test_doctor.py, plugin/cli/tests/test_self_update.py]
  - Automated verification: tests for a vault with no `.obsidian/` (untouched), an existing `community-plugins.json` with other plugins (preserved), and each doctor state; full suite passes.
  - Manual verification: in a second project with an Obsidian vault, `/compass:update` installs the plugin and doctor's walkthrough is enough for the human to turn it on.
- [ ] TASK-169: The plugin install adds `.compass/review-inbox.base` (draft specs, plans, vision and research; a pending review shows as its bar, since a base cannot match a request to a missing verdict file) and `.compass/lessons.base` (active lessons by area and by category), each written only when absent - complexity: S, depends_on: none, files: [plugin/obsidian/bases/review-inbox.base, plugin/obsidian/bases/lessons.base, plugin/cli/reviewlib.py, plugin/cli/tests/test_vault_bases.py]
  - Automated verification: the base files parse as YAML and name only properties the vault's frontmatter schema defines; full suite passes.
  - Manual verification: both views open in this vault and show the expected rows.
- [x] TASK-178: Split the review into a generic core and surfaces: `reviewlib` keeps the protocol (request and verdict files, pending, under review, waiting) and a registry of surfaces; each surface answers whether it is configured for a document, delivers a request, reports whether it has focus, installs itself, and gives doctor its state and enable steps; the Obsidian code moves into the first surface, and `review`, `guard`, `doctor` and `self-update` call only the core - complexity: M, depends_on: TASK-166, TASK-167, TASK-168, files: [plugin/cli/reviewlib.py, plugin/cli/review_surfaces/__init__.py, plugin/cli/review_surfaces/obsidian.py, plugin/cli/commands/review.py, plugin/cli/commands/guard.py, plugin/cli/commands/doctor.py, plugin/cli/commands/self_update.py, plugin/cli/tests/test_review.py, plugin/cli/tests/test_review_surfaces.py], decisions: [SPEC-030-review-documents-open-in-obsidian/D-01]
  - Automated verification: a fake second surface registered in a test receives a request and returns a verdict through `compass review` with no change to the core; the core imports nothing Obsidian-specific; the existing guard, doctor and self-update tests pass unchanged and the review tests stub the Obsidian surface instead of the core; the plugin's startup scan leaves a request for another surface alone; full suite passes.
  - Manual verification: the round trip in TASK-166 still raises Obsidian and returns the human to his window.
- [x] TASK-170: Experiment: with `compass review` running in the background and an `AskUserQuestion` open, the human approves in Obsidian; record whether the session acts on the verdict before the question is answered, and the shape gates take as a result - complexity: S, depends_on: TASK-166, files: [.compass/research/RESEARCH-review-in-obsidian.md]
  - Automated verification: none; the result is a recorded observation.
  - Manual verification: the human performs the approval and confirms what the session did.

**Pause point:** when automated verification passes, wait for the human to confirm manual verification succeeded before the next wave.

### Wave 2 (detailed): Obsidian alone is enough

- [x] TASK-185: The plugin keeps the review in view while the human moves around the vault: any other markdown file opened while a review is pending shows a slim bar naming the review, a Back to review button that reopens the reviewed file in the same pane, and a note field for that file; files the human edits while the review is pending are tracked; Needs changes stays disabled until there is a note, a note on another file, or an edit; the verdict gains `comments: [{file, note}]` and `edited: [path]`; a bar disappears when its request file is gone or its verdict exists, rechecked every few seconds - complexity: M, depends_on: none, files: [plugin/obsidian/compass-review/main.js, plugin/obsidian/compass-review/styles.css, plugin/obsidian/tests/test_main.js], decisions: [SPEC-030-review-documents-open-in-obsidian/D-03]
  - Automated verification: the harness covers a navigation from the reviewed file to a linked file (slim bar shown, Back reopens the original), a note on a second file landing in `comments`, an edit to a second file landing in `edited`, Needs changes disabled with nothing written and enabled after a note, a request file removed mid-review (bar gone), and two pending reviews (the slim bar names the one last opened); `node --check` passes; full suite passes.
  - Manual verification: from a reviewed spec the human follows a link, leaves a note on the linked file, returns with Back, and clicks Needs changes; the session receives both notes.
- [x] TASK-186: `compass review` prints the verdict's `comments` and `edited` after the verdict JSON, one `comment <file>: <note>` and one `edited <file>` line each, before the reviewed file's text; `compass review --cancel <id>` withdraws a pending request (its request file is removed, its waiter ends with `withdrawn <id>`, exit 1) so a terminal answer clears the Obsidian bar; `valid_verdict` accepts a verdict with or without the new fields and rejects a non-list `comments` or `edited` - complexity: S, depends_on: none, files: [plugin/cli/commands/review.py, plugin/cli/reviewlib.py, plugin/cli/tests/test_review.py], decisions: [SPEC-030-review-documents-open-in-obsidian/D-03, SPEC-030-review-documents-open-in-obsidian/D-04]
  - Automated verification: tests cover a verdict with comments and edits (lines printed in order), a verdict without them (output unchanged), malformed `comments`, `--cancel` of a pending request (waiter prints `withdrawn`), `--cancel` of an unknown id (exit 1, message), and `--status` after a cancel; full suite passes.
  - Manual verification: none.
- [x] TASK-171: Every gate whose subject is a document goes through review when a surface is configured, and then asks nothing in the terminal. One paragraph in the pipeline rules states the shape: commit, run `compass review <file> --title "<the gate's question>"` in the background, and on `requested` end the turn with one line naming the document; an approved verdict is the gate's recommended approve option, its notes and comments steering what follows, and a follow-up question the gate would ask next takes its recommended option unless the notes say otherwise; a changes verdict applies the notes, comments and edits and sends the revised document again; a reply typed in the terminal instead runs `compass review --cancel <id>` and is the answer; `not configured` asks through `AskUserQuestion` as before. The gates of spec, specs, plan, planner, vision, research-codebase, research-papers, build's phase pause (the plan file, titled with the wave's manual checks) and autopilot point at that paragraph - complexity: M, depends_on: TASK-186, files: [plugin/templates/rules/compass-pipeline.md, plugin/skills/spec/SKILL.md, plugin/skills/specs/SKILL.md, plugin/skills/plan/SKILL.md, plugin/templates/agents/planner.md, plugin/skills/vision/SKILL.md, plugin/skills/research-codebase/SKILL.md, plugin/skills/research-papers/SKILL.md, plugin/skills/build/SKILL.md, plugin/skills/autopilot/SKILL.md], decisions: [SPEC-030-review-documents-open-in-obsidian/D-02, SPEC-030-review-documents-open-in-obsidian/D-04]
  - Automated verification: every listed skill's document gate names the review paragraph; no listed gate asks `AskUserQuestion` before the `not configured` branch; the shipped-rules tests and full suite pass.
  - Manual verification: the human approves a spec in Obsidian while in another app and the session moves on with no terminal question (TASK-172).

**Pause point:** when automated verification passes, the human runs TASK-172.

## Later (intent only)

- [ ] TASK-172: Live acceptance: the human approves a real spec entirely from Obsidian while working in another app
- [ ] TASK-173: Loop dashboard view with Accept / Reject per run calling `compass loop review`
- [ ] TASK-174: Vault-health sidebar listing `validate` and `doctor` warnings with links
- [ ] TASK-175: Consolidate's grouping proposal as a canvas the human rearranges and approves
- [ ] TASK-176: Chat with Claude in Obsidian: answers appear there and choices (1, 2, 3, other) are picked there
- [ ] TASK-177: Live runs on macOS, Linux (X11 and Wayland) and WSL; a blocking review under Codex and dsh

## Wave 2 elaborated

- TASK-171: the gate sends the review in the background, ends its turn, and asks nothing in the terminal, because the TASK-170 run showed a verdict cannot reach the session while a terminal question is open ([[RESEARCH-review-in-obsidian]] finding 13, SPEC-030 D-04); research's axis gate is a conversation, not a document, and stays in the terminal, while research-codebase and research-papers review their finished documents; build's gate is the phase pause.
- TASK-185, TASK-186: new, from SPEC-030 D-03 (navigation inside Obsidian keeps the original question in view and takes feedback on other files) and the cancel path D-04 needs when the human answers in the terminal.

## Risks

- Obsidian auto-merges external writes into an open note: TASK-167 keeps agents out of a file under review.
- An Obsidian update removes `electron.remote` access from plugins: the raise and step-aside fail with a notice and the review still completes by clicking; doctor reports the Obsidian version.
- The experiment shows a verdict cannot land while a question is open: gates then send the review and end the turn, taking the terminal answer as plain text, which conflicts with [[SPEC-029-questions-to-the-human-are-clear-and-visual]] and goes to the human before TASK-171 is detailed.
