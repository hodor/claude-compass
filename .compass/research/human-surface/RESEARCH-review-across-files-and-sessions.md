---
title: "Review Across Files and Sessions"
type: research
status: complete
confidence: medium
area: methodology
tags: [obsidian, review, multi-file, sessions, human-surface]
depends_on: ["[[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]]"]
summary: "how one review walks the human through several files, and how several Claude Code sessions each reach their own markdown editor"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
author: "orchestrator"
---

# Review Across Files and Sessions

## Question

How does Compass meet the outcomes of [[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]] that the review plugin does not meet yet: several files in one review that are easy to move through, several Claude Code sessions each with its own markdown editor, another editor than Obsidian, and a review with no friction?

## The questions

| #   | Question                                                                                                                                                                                                                                          | Where the answers are sought                                                                                                                                                                      |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | How do review tools walk a person through several files in one review: order, progress, per-file status, moving next and back, an overview of all files? What would a review of several files look like in `compass review` and its request file? | GitHub pull request review, Gerrit, Phabricator, VS Code's multi-file diff editor, their docs; the review plugin's code; the stepper view of [[research/human-surface/RESEARCH-plugin-ui-mockup]] |
| 2   | With several projects and sessions open at once, does each review reach the right Obsidian window and come back to the session that asked?                                                                                                        | Obsidian's URI and vault-switching docs and API; `plugin/cli/review_surfaces/obsidian.py`; a live run with two vaults open and two waiting `compass review` commands                              |
| 3   | What does a markdown editor other than Obsidian need to be a review surface behind the same interface?                                                                                                                                            | VS Code extension API docs (webviews, custom editors, URI handlers); `plugin/cli/review_surfaces/__init__.py`                                                                                     |
| 4   | Where is the friction in the review loop today? Clicks, window switches, time from request to verdict, reviews left unanswered or answered twice.                                                                                                 | the request and verdict files in `.compass/tmp/review/` (timestamps, notes, edits); the review plugin's code; usability literature on review interruptions through the shipped source list        |
| 5   | How do the visual views of [[plans/PLAN-024-working-in-compass-is-visual]] show inside a review: in the document, in the side panel, or both?                                                                                                     | the review plugin's code; the views mockup; Obsidian's view API                                                                                                                                   |

## Grading

Each finding gets a confidence level (high, medium, low) from its evidence: code read or a run observed is high, official docs are high, a single third-party source is medium, an inference is low. Sources from the shipped list carry their own marks. You can refuse grading; the research still runs, with findings ungraded.

## Findings

### What this means for the spec

The spec (what we need) is [[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]]; D-01 to D-06 are its numbered rulings. The review plugin is Compass's Obsidian plugin: it shows each pending review as a card in a side panel, and after the verdict it steps aside (minimizes Obsidian so the human is back where he was). The stepper is a mockup screen that walks through several files one at a time.

| Question | Answer in short | What it means for SPEC-030 |
| --- | --- | --- |
| 1. Several files in one review | Compass reviews one file per request (1.1). GitHub and Gerrit keep a per-file viewed or reviewed mark beside one verdict for the whole review (1.16). The stepper already draws the walk: "File i of n", Previous, Next, Next unread (1.8). | "Needs to work if we have multiple files to review on the same md editor. Needs to be incredibly easy to navigate them all." (Desired Outcome, D-06) is not met: the request, the CLI, the write guard and the card each hold one file (1.1 to 1.7). |
| 2. Several projects and sessions | Each project's request names its own vault by id, and each session waits on its own verdict file, so a verdict comes back to the session that asked (2.1, 2.8). Whether the link raises the right window with several vaults open was not run (G1). | "Needs to work if we have multiple claude code sessions" (Desired Outcome, D-06) holds for the verdict's return, with three leaks between sessions: an edit to an unreviewed file lands on the newest card (2.11), the change report holds the other session's work (2.12), and another project's Obsidian window counts as focus (2.13). Reaching the right window rests on Obsidian's docs, which one forum report contradicts (2.3, 2.4). Cards carry no session or project label (2.9). |
| 3. Another editor | No finding shows the surface interface or the file exchange needing a change for VS Code (3.1, 3.2, 3.6 to 3.11). No VS Code API to raise or minimize a window was found (3.12, medium); its links go to the topmost window (3.10); no per-project install was found (3.16). | D-01 meets no blocker in the interface. On VS Code, D-02 ("takes him back where he was") and reaching the right session's window (D-06) need help from the operating system or are left out for that surface (H11, H12). |
| 4. Friction | All 24 reviews got one verdict each, median 6.2 minutes (4.1, 4.2). Approve is one click (4.9). The edited list appears to pick up Obsidian's own reformatting and files Compass writes (4.5, 4.6, medium). Several files went out as separate requests (4.4). | "UX for it should be frictionless" (Desired Outcome) mostly holds for one file. The friction found is noise in the edited list and one request per file. Notes on other files (D-03) were used once (4.7). |
| 5. Where the views show | A code block lives inside the document that holds it; the side panel stays while the human moves between files (5.2). | D-03's side panel is the place that stays while he moves through several files; the other places in 5.9 draw inside one document or view. Visual artifacts drawn as code blocks add bytes to the documents and their diffs (5.3, D-05). |

Paths in the tables: `main.js` is `plugin/obsidian/compass-review/main.js`; `review.py` is `plugin/cli/commands/review.py`; `reviewlib.py`, `vaultlib.py` and `commands/guard.py` sit under `plugin/cli/`, `obsidian.py` and `__init__.py` under `plugin/cli/review_surfaces/`; "the mockup" is `.compass/.obsidian/plugins/compass-ui-mockups/main.js`. Line numbers refer to commit aa4c159. The raw researcher reports, the simulation and the tally script are in `.compass/tmp/research/SPEC-030/` (scratch, not kept in git).

### 1. Several files in one review

Method: four review tools compared on fixed features from their official docs and release notes (DESMET feature analysis, a standard method for comparing tools), beside a read of the CLI, the plugin and the mockup.

**What Compass does today**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 1.1 | `compass review` takes one file and refuses a second; the request names one `file`. | high | `review.py:95-98`; `reviewlib.py:5-12`, `:71-72` |
| 1.2 | The verdict is one answer (`approved` or `changes`, with notes) plus two optional lists: `comments` on other files and `edited` paths. Validation checks only id, verdict word and list types, so extra keys pass. | high | `reviewlib.py:13-18`, `:190-196` |
| 1.3 | The commit check confirms only the reviewed file is committed and clean; the diff printed after the verdict covers the whole repository. | high | `reviewlib.py:116-132`, `:145-172` |
| 1.4 | After the verdict the CLI prints the verdict, the comment and edited lines, the diff, then the one reviewed file as the human left it. | high | `review.py:135-164` |
| 1.5 | The write guard and `--status` know a request by its one file. | high | `reviewlib.py:235-246`; `guard.py:343-361`; `review.py:108-116`; `plugin/cli/tests/test_review.py:274-281` |
| 1.6 | The plugin keeps one card per request, newest first. | high | `main.js:144-155`, `:303-320` |
| 1.7 | While one file is under review, the human can leave a note on any other markdown file he opens ("On this file"). The card has no order, no "file i of n", no per-file status. | high | `main.js:303-358`, `:372-382`, `:430-437` |

**What the mockup already draws**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 1.8 | The stepper draws the walk: header "File i of n"; Previous, Next, Next unread; arrow keys when the panel has focus; one numbered row per file; per-file "Approve this file" and "Needs changes"; opening a file marks it read. | high | mockup `:1179-1325` |
| 1.9 | It has five per-file states (not opened, read, has notes, approved, needs changes) and one send button whose label follows them ("Approve all and send", "Send review with changes", "Send what I have"). What it writes, `{question, files: [...]}`, is read by nothing. | high | mockup `:1212-1216`, `:1293-1321` |

**Other review tools**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 1.10 | GitHub: a per-file Viewed checkbox collapses the file, fills a progress bar and clears when the file changes; a file tree and filter jump to a file; no next or back control in the docs. | high | docs.github.com "Reviewing proposed changes in a pull request" (vendor docs) |
| 1.11 | GitHub single file mode (public preview, September 2025): one file at a time; marking Viewed moves to the next; J and K move next and back. | high (medium that it stays) | github.blog changelog 2025-09-25 (vendor changelog) |
| 1.12 | Gerrit: a file list with status, lines changed and comment count; a Reviewed checkbox per file, set on view when the "Mark Reviewed" preference is on; no next-unreviewed control documented. | high | gerrit-review.googlesource.com user-review-ui (vendor docs) |
| 1.13 | GitHub, Gerrit and Phabricator hold comments as private drafts and publish them together with one verdict for the whole review (Approve or Request changes, a vote, Accept Revision). | high (medium for Phabricator) | GitHub docs above; Gerrit "Reply" section; Mozilla's Phabricator guide (moz-conduit.readthedocs.io), upstream D12033, T1460 |
| 1.14 | VS Code's multi-file diff shows many files in one scrolling view (on for all since 1.86); 1.143 adds an experimental file list with per-file status and jump. No per-file reviewed state was found. | medium (high for the 1.143 list) | microsoft/vscode PR 341872 (read); 1.86 and 1.143 release notes (search summaries) |
| 1.15 | Browser extensions add the same controls GitHub lacks: mark viewed, mark and go to the next unviewed, J and K between files. | low | Chrome Web Store "Review Shortcuts for GitHub"; github.com/G-Harmon/pull-request-shortcuts (third-party, 2 agree) |
| 1.16 | Across the tools: per-file working state (viewed, drafts) stays apart from one verdict that closes the review; the per-file mark is yes or no; no tool gives each file its own approve; none orders files by the author's intent. | medium | reading across 1.10 to 1.14 |

### 2. Several projects and sessions

Method: the shipped code read, then run in two simulations with no window (two fake projects through the real CLI functions; the real `main.js` loaded with Obsidian stubbed), joined to Obsidian's docs and forum. Nothing was opened in Obsidian.

**Which window a review reaches**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 2.1 | Each project's request names its own vault by id, read from Obsidian's own vault list; two projects produce two different links. | high | `obsidian.py:63-76`, `:106-110`; simulation |
| 2.2 | Obsidian documents the vault id as unique per folder, and `vault=` takes a name or an id. | high | obsidian.md/help "Obsidian URI" (official docs) |
| 2.3 | The docs say only "If the vault is already open, focus on the window"; they are silent on a closed vault and on which window serves a plugin's own link. | high (that they are silent) | Obsidian URI docs; `registerObsidianProtocolHandler` API reference |
| 2.4 | One forum report: on Obsidian 1.13.2 insider, Windows 11, `obsidian://open?vault=<id>` does nothing when that vault already has a window. | low | forum.obsidian.md topic 116122 (July 2026, one author, no staff reply) |
| 2.5 | An older forum report: opening an already-open vault from the vault switcher brings its window forward. | low | forum.obsidian.md topic 72521 (December 2023, one author) |
| 2.6 | The plugin raises its own window and reads only its own vault's review folders, so a link that reaches the wrong window fails with "file not in this vault" instead of showing a wrong document. | high | `main.js:42`, `:90-92`, `:122-140`, `:157-161`, `:230-241` |
| 2.7 | The request goes to the `.compass` vault holding the document, whatever `CLAUDE_PROJECT_DIR` names, so the request file and the link always name the same vault. Fixed in aa4c159; the simulation reproduced the earlier failed delivery. | high | `review.py:26`, `:202`; `vaultlib.py:179-190` (`honor_env`) |
**The verdict coming back**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 2.8 | The verdict comes back through a file: each waiting session polls its own `<id>.verdict.json` every 0.5 s and accepts only a matching id, so two sessions in one vault cannot read each other's verdict. | high | `reviewlib.py:61-62`, `:190-196`; `review.py:149-170` |
| 2.9 | Two sessions in one vault reviewing different files get two cards in one panel, answered separately; a card shows the title or file name and no session or project. | high | `main.js:144-155`, `:305`, `:326`; simulation |
| 2.10 | A newer request for a document already under review withdraws the older one: its request file is removed, its waiter ends `withdrawn`, and the plugin keeps one card per file. Fixed in aa4c159. The record holds one same-file pair (PLAN-024, 8.8 minutes apart), the first answered before the second went out. | high | `review.py:214-218`, `:165-167`; `reviewlib.py:218-228`; `main.js:142-147` |
| 2.11 | An edit to a file no review names is put on the newest card, whichever session owns it. | high (whether other programs' writes count: not run, G5) | `main.js:207-214`; simulation |
| 2.12 | The change report after a verdict covers the whole repository, so session A's report includes what session B committed or created meanwhile. | high | `reviewlib.py:145-172` |
| 2.13 | Stepping aside is set per request when it is made: `return` is true unless an Obsidian window has focus, checked by process name on Windows only, so focus in project Y's Obsidian counts for project X's request. The window minimizes once no card is left. On macOS the step aside hides every Obsidian window. | high (macOS effect: medium) | `obsidian.py:122-145`; `main.js:243-251`, `:445-449` |
| 2.14 | A vault Obsidian does not list, or one with the plugin off, gets `not configured` and the question in the terminal; a request written while Obsidian was closed appears as a card at start-up, without raising the window. | high | `obsidian.py:91-103`; `main.js:120-141` |
| 2.15 | The link opener reports nothing back: it hands the link to the operating system and ignores any failure, so a link that reaches no handler goes unnoticed. | high | `obsidian.py:148-155` |

### 3. Another markdown editor

Method: DESMET feature analysis of VS Code, Cursor, VSCodium, Zed, Typora and Logseq against the duties the interface and the Obsidian plugin carry; `vscode.d.ts` (microsoft/vscode `main`, fetched 2026-10-27) read as code; the local VS Code and Cursor installs inspected.

**What the interface asks of an editor**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 3.1 | A surface is a module of seven parts: NAME, configuration, deliver, has_focus, resolve, install, doctor; the list of surfaces holds only Obsidian. | high | `__init__.py:5-17`, `:23` |
| 3.2 | The exchange is files only: the editor reads `<id>.request.json` and writes `<id>.verdict.json` beside it; a verdict of id, file, verdict, notes and time is valid; `file` is relative to a root the surface picks. | high | `reviewlib.py:1-23`, `:65-79`, `:190-196` |
| 3.3 | The first configured surface wins; nothing lets a project or the human prefer one. | high | `reviewlib.py:45-54` |
| 3.4 | The Obsidian-specific parts: the focus check looks for `obsidian.exe`; install and doctor work per project (the vault's plugin folder and plugin list); configuration reads Obsidian's vault list. | high | `obsidian.py:33-103`, `:122-145`, `:182-254` |
| 3.5 | The Obsidian plugin does everything the human sees: raise, open the file, the card, notes, notes on other files, edit tracking, save before the verdict, write the verdict, step aside, rescan at start-up. | high | `main.js:1-38`, `:90-100`, `:122-155`, `:218-251`, `:416-450` |

**VS Code**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 3.6 | A side panel with buttons exists: a webview view in the Activity Bar or bottom Panel, whose HTML buttons message the extension. Webviews have no markdown renderer and block inline scripts. | high | `vscode.d.ts:10334-10356`, `:11752`; webview guide and contribution points (official docs) |
| 3.7 | A hidden webview loses typed notes unless it keeps its context (a memory cost) or saves state. Whether the extension can still message it while hidden is disputed (see Contradictions). | medium | `vscode.d.ts:10056-10080`; webview guide |
| 3.8 | Without a webview, a modal message with buttons, an input box and a status bar item carry approve, changes and a note. | high | `vscode.d.ts:11285-11319`, `:11491`, `:11641` |
| 3.9 | A custom editor can show the reviewed file itself with buttons, opt-in per file type. | high | custom editors guide (official docs); `vscode.d.ts:10358`, `:11791` |
| 3.10 | A system link reaches an extension through a URI handler, but with several windows open the topmost window takes it; nothing addresses the window holding a given folder. | medium | `vscode.d.ts:11713-11727`; github.com/microsoft/vscode-discussions 2907 (unanswered) |
| 3.11 | File watchers work per window, also outside the open folder, and see writes by any program; save and change events track edits. | high | `vscode.d.ts:14000-14079`, `:14319` |
| 3.12 | No extension API raises, focuses or minimizes the window; only whether it is focused can be read. | medium | `vscode.d.ts:11038-11050`; search of the file for raise, focus, minimize (absence) |
| 3.13 | One marketplace extension raises VS Code for Claude Code prompts through a local web server and operating system tools. | low | marketplace listing evileye.claude-focus (third-party, source not read) |
| 3.14 | The link scheme differs per build and can be read at run time: `vscode`, `cursor`. | high | `vscode.d.ts:10768`; each local install's `resources/app/product.json` |
| 3.15 | The `code` command can reuse the last window (`-r`), open at a line (`-g`), wait (`-w`) and install an extension. | high | code.visualstudio.com/docs/editor/command-line; local `code --help` |
| 3.16 | Extensions install per user from a `.vsix`; a version field gates which editors accept one; no per-project install was found. | high | code.visualstudio.com publishing-extension (official docs) |
| 3.17 | Cursor runs an older engine (1.96.2 against the installed VS Code 1.143.1) and a mirror of Open VSX that can serve old versions; VSCodium runs non-Microsoft extensions that use only the public API. | high for versions, medium for the stores | local Cursor `product.json`, `code --version`; forum.cursor.com topic 159718; VSCodium extensions-compatibility doc |

**Other editors**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 3.18 | Zed extensions cannot add panels or buttons (a visual extension API is an open proposal, April 2026); Typora has no official plugin API, only community frameworks; Logseq plugins can add HTML and toolbar buttons in a sandbox but cannot raise the window. | medium (Typora: low) | github.com/zed-industries/zed discussion 53403, zed.dev blog; obgnail/typora_plugin, typora-community-plugin (community repos); logseq.github.io IAppProxy docs, discuss.logseq.com topic 20056 |

### 4. Friction in the review loop

Method: the 24 request and verdict files (2026-10-24 to 2026-10-27) tallied by a script, the plugin's click paths read from code, and usability papers found through OpenAlex (abstracts only).

**The review record**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 4.1 | Every request got exactly one verdict: 24 requests, 24 verdicts, none unanswered. | high | request and verdict files in `.compass/tmp/review/`, tallied |
| 4.2 | Minutes from request to verdict: median 6.2; 7 under 1, 6 from 1 to 10, 6 from 10 to 60, 5 over 60 (the longest, 2892.7, a test review left open two days). | high | same files; request ids carry local time, verdicts UTC |
| 4.3 | 16 approved, 8 needs changes; every needs-changes verdict has a note, and so do 7 of 16 approvals (Approve is always enabled; Needs changes waits for feedback). | high | same files; `main.js:372`, `:393` |
| 4.4 | Several files are reviewed today as several requests sent at once: two pairs went out one second apart and were answered separately. | high | ids 20261027T095751 and T095752, T105830 and T105831 |
| 4.5 | The edited list names the reviewed file in 6 of 24 verdicts. Three of those six are approvals with no note; in at least 2 of the three, the edit was Obsidian's table editor padding the file. | medium | `main.js:208-214`; messages of commits 6986f31 and f2d8079 |
| 4.6 | Three verdicts list edits outside the reviewed file (14, 2 and 1 files), including files Compass writes itself (`active.md`, `index.md`, `archive/done.md`, extraction logs). | medium (human or Compass inferred from the names) | verdict 20261025T080559-9d516e; `main.js:210` |
| 4.7 | Notes on other files were used in 1 of 24 reviews, on a trial file. | high | same files; `main.js:307-340` |
| 4.8 | 4 of 24 requests went out with `return: false` because an Obsidian window had focus; after those verdicts Obsidian stayed up. | high | same files; `obsidian.py:122-145`; `main.js:445-449` |

**Clicks and edge cases, read from code (not timed)**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 4.9 | Approve is one click: the link opens the panel and the file and raises the window; the click saves, writes the verdict and steps aside when nothing else is pending. | high | `main.js:164-172`, `:230-251`, `:416-450` |
| 4.10 | Needs changes takes at least two clicks plus typing; a note on another file takes four. Notes can be left only on markdown files; a canvas, image or PDF cannot take one. | high | `main.js:305-307`, `:393` |
| 4.11 | A withdrawn request's card goes within 5 seconds; a click after the withdrawal says nothing was sent; a double click sends once. | high | `main.js:44`, `:218-228`, `:406-428` |
| 4.12 | With several reviews pending, Obsidian steps aside only once none is left. | high | `main.js:445-449` |

**Usability literature**

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 4.13 | Interrupted tasks finish faster at equal quality but cost more stress, frustration, time pressure and effort; office workers report difficulty shifting between tasks. | medium (their reach to a review prompt: low) | Mark, Gudith, Klocke, CHI 2008, doi:10.1145/1357054.1357072 (696 citations); Czerwinski, Horvitz, Wilhite, CHI 2004, doi:10.1145/985692.985715 (829 citations); peer-reviewed, not retracted, abstracts only |
| 4.14 | In code review at Microsoft, understanding the change is the main work and tools fall short of it; the Google study's abstract gives no figures on delay or interruption. | medium (setting is pull requests) | Bacchelli, Bird, ICSE 2013, doi:10.1109/icse.2013.6606617 (641 citations); Sadowski et al., ICSE-SEIP 2018, doi:10.1145/3183519.3183525 (280 citations); peer-reviewed, not retracted, abstracts only |

### 5. Where the views show

Method: the review plugin, the mockup and Obsidian's API typings (`obsidian.d.ts`, obsidianmd/obsidian-api master) read as code, plus the live trials already on record.

| # | Claim | Confidence | Evidence |
| --- | --- | --- | --- |
| 5.1 | The review plugin has two places today: a panel of cards on the right, and a one-line bar at the top of the reviewed document. It draws no code blocks. | high | `main.js:89-91`, `:183-196`, `:270-290` |
| 5.2 | A code block lives in the document holding its text and goes when he leaves that file; a panel stays and can follow every file he opens. A stepper drawn as a block has nowhere to live once he moves on. | high | `obsidian.d.ts:7259-7275`, `:5391-5412`, `:7219`, `:11034-11048` |
| 5.3 | A block is document text: it adds bytes, travels in the commit and the diff, and shows as plain code without the plugin. PLAN-024 keeps a visual only if it removes at least as many bytes as it adds. | high | [[research/human-surface/RESEARCH-plugin-ui-mockup]] line 19; [[plans/PLAN-024-working-in-compass-is-visual]] line 22 |
| 5.4 | The mockup draws all seven views as code blocks, while its write-up places the several-files review and the sessions list in the side panel; the mockup has no panel, so those two were never drawn there. | high | mockup `:608-619`; [[research/human-surface/RESEARCH-plugin-ui-mockup]] lines 89-97 |
| 5.5 | Both places can render markdown through Obsidian's renderer; a panel supplies the source path itself. | high | `obsidian.d.ts:6040-6070`; mockup `:695-709` |
| 5.6 | In a live run a block drew in Reading view and Live Preview; a Mermaid chart nested through the markdown renderer stayed raw text in Live Preview, while Obsidian's own Mermaid call drew it. | high (the cause: medium) | [[research/human-surface/RESEARCH-visual-trials-in-obsidian]] Trials A and B |
| 5.7 | Typed answers live in memory in the review plugin (on the review's entry) and in the mockup (in a plugin-wide map); a reload clears them, though the card comes back from its request file. | high | `main.js:303-313`; mockup `:605`, `:626-628` |
| 5.8 | The mockup's sessions list reads only this vault's review folder; its other rows are samples. A session or project field on the request, and a read across projects, do not exist. | high | mockup `:1527-1529`; [[research/human-surface/RESEARCH-plugin-ui-mockup]] lines 70, 96 |
| 5.9 | Other places exist: a post processor, an editor extension for Live Preview widgets, a Bases view (from Obsidian 1.10.0); the review plugin asks for Obsidian 1.4.0 or newer. | high | `obsidian.d.ts:7257`, `:7299`, `:5693`; `plugin/obsidian/compass-review/manifest.json:5`; [[research/human-surface/RESEARCH-working-in-compass-is-visual]] findings 121, 136 |

## Where the researchers agree

Four researchers worked the five questions (one took 4 and 5). Where their reading overlapped:

| Claim | Q1 | Q2 | Q3 | Q4 and Q5 | Agreement |
| --- | --- | --- | --- | --- | --- |
| One request holds one file | yes (1.1) | - | - | yes (4.4) | 2 of 2 |
| The plugin keeps one card per file, a newer request for the file replacing the older | yes (1.6) | yes (2.10) | - | - | 2 of 2 |
| An edit to a file no review names goes to the newest card | - | yes (2.11) | - | yes (4.6) | 2 of 2 |
| A verdict may carry extra keys and leave out its lists | yes (1.2) | - | yes (3.2) | - | 2 of 2 |
| Stepping aside depends on a Windows-only focus check made at request time | - | yes (2.13) | yes (3.4) | yes (4.8) | 3 of 3 || Writes by other programs end up in the edited list | - | not run (2.11, G5) | VS Code watchers see them (3.11) | the record suggests so, medium (4.5, 4.6) | see Contradictions |

## Contradictions

| Topic | One side | Other side | Between |
| --- | --- | --- | --- |
| Do writes by other programs count as the human's edits? | Not run; an inference only (2.11, G5) | The record lists Obsidian's reformatting and files Compass writes (4.5, 4.6, medium, inferred from names and commit messages) | Q2 and Q4 researchers |
| What `return: false` means | The human was already in Obsidian (4.8) | The check passes when any Obsidian window has focus, another project's included (2.13) | Q4 and Q2 researchers |
| Does a link focus a vault that is already open? | Obsidian's docs: it focuses the window (2.3) | A 2026 forum report: nothing happens (2.4) | sources within Q2 |
| A verdict per file or one per review | The mockup approves or rejects each file (1.8, 1.9) | GitHub, Gerrit, Phabricator: one verdict, per-file marks only (1.13, 1.16) | sources within Q1 |
| Where the several-files and sessions views live | The mockup write-up: side panel | The mockup code: code blocks (5.4) | sources within Q5 |
| Can an extension message a hidden webview? | `vscode.d.ts`: not even when it keeps its context | A summary of the webview guide: yes (3.7) | sources within Q3 |

## Gaps

**Live checks not run**

| # | Check | Bears on |
| --- | --- | --- |
| G1 | With projects X and Y both open in Obsidian, does X's link reach X's plugin and raise X's window? | 2.3 |
| G2 | With X's vault closed, does the link open it and reach the plugin, or does only the start-up scan find the request? | 2.14 |
| G3 | Does the installed Obsidian ignore `vault=` for a vault already open, as the forum report says? | 2.4 |
| G4 | On Windows, is a second link launch passed to the Obsidian already running? | 2.1 |
| G5 | Does Obsidian's modify event fire for writes by another program? | 2.11, 4.6 |
| G6 | Does stepping aside on macOS hide other vaults' windows? | 2.13 |
| G7 | With several files in one review (as in H1), how does Obsidian behave when the human opens a second pane, opens a file outside the review, or renames a file in it? | 1.7, 1.8 |
| G8 | Timed clicks and minutes for Approve and Needs changes. | 4.9, 4.10 |
| G9 | Do a code block's keys and focused text fields survive a Live Preview redraw; do arrow keys reach a block? | 5.2 |
| G10 | Does `code <path>` without `-r` reuse the window already holding that folder? | 3.10, 3.15 |
| G11 | What does a `vscode://` link do when VS Code is closed, or its only window holds another folder? | 3.10 |
| G12 | Can a VS Code extension reach Electron's window controls to raise or minimize? | 3.12 |
| G13 | Remote and WSL windows: where the extension runs and which paths it sees. | 3.11 |
| G14 | Does Cursor's 1.96 engine support every API in 3.6 to 3.11? | 3.17 |
| G15 | Logseq and Typora link handling and file writes; Zed's command line or link scheme. | 3.18 |

**Not in the record or not read in full**

| # | Gap | Bears on |
| --- | --- | --- |
| G16 | The verdict files do not record how the human reached the window (link, alt-tab), so the share of minutes spent switching is unknown. | 4.2 |
| G17 | Whether the third note-less approval with a self-edit (20261026T183405-68cb85) was a formatter pass. | 4.5 |
| G18 | Whether the skills that call `compass review` would pass several files at once. | 1.1 |
| G19 | Phabricator's own Differential article timed out and Phorge's returned 403; a per-file mark there is neither confirmed nor ruled out. | 1.13 |
| G20 | VS Code's 1.86 and 1.143 release notes were read through search summaries. | 1.14 |
| G21 | Interruption papers: abstracts only; Iqbal and Horvitz (CHI 2007) give no numbers there, Parnin and Rugaber (2010) had no abstract. | 4.13 |
| G22 | Obsidian's app source is closed, so window routing rests on docs and forum alone. | 2.3, 2.4 |

## Hypotheses for the plan

The researchers proposed these. None is tested or decided.

**Several files (from Q1)**

- H1. The request gains an ordered `files` list, each entry a path and an optional one-line "why you are looking at this"; `file` stays as the first path, so older plugins and `--status` keep working, and a request without `files` is a one-file review as today.
- H2. The verdict keeps one `verdict` and `notes` and adds an optional `files` list with each file's state (`unread`, `read`, `approved`, `changes`) and note; validation already lets extra keys through (1.2).
- H3. `compass review` takes several files; each passes the commit check; the output adds one line per file, reprints only files marked changes or edited, and `--status` shows how many more files the request lists; the write guard covers every listed file.
- H4. One card per request shows the stepper of 1.8; moving to a file opens it and marks it read; opening a listed file by hand moves the step to it; an unlisted file keeps "On this file".
- Left open by the sources: a verdict per file (mockup) or per-file marks with one verdict (1.13); per-file notes in `files` or in `comments`; marking read on view (Gerrit) or by a click (GitHub); moving on after approving a file (GitHub single file mode) or staying.

**Several sessions (from Q2)**

- H5. A session or project label on the request, shown on the card, so two cards in one panel can be told apart (2.9, 5.8).
- H6. The edited list keeps to the reviewed file plus files the human touched in a pane, with no newest-card fallback, and each card decides on its own whether its verdict steps aside (2.11, 4.6, 2.13).
- H7. After delivering, the CLI waits a few seconds for the plugin to confirm, then delivers again or falls back to the terminal; worth building only if G3 shows the link can do nothing.

**Another editor (from Q3)**

- H8. A second surface needs no change to the seven-part interface or the file exchange; it is added to the list of surfaces (3.1, 3.2).
- H9. With two surfaces configured, a project setting or a choice at request time picks one (3.3).
- H10. Install and doctor wording allows a per-user install, since VS Code extensions install per user (3.16).
- H11. On VS Code, each window's file watcher claims requests under its own folder, since a link cannot name a window; the request has no field yet for who claimed it (3.10, 3.11).
- H12. On VS Code, raising and stepping aside come from the operating system or are left out for that surface; leaving them out drops D-02 there, a loss the human rules on (3.12).
- H13. Delivery reports failure, so a link that reaches nothing falls back to the terminal (2.15).
- H14. A minimal VS Code surface: Python side watching or linking per 3.10 and 3.11, installed from a `.vsix` per editor found (3.15, 3.16); the extension built for Cursor's older engine (3.17), showing a webview card in the Activity Bar (3.6), or in a smaller form modal buttons and an input box with no notes on other files (3.8).
