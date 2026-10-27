---
title: "PLAN-025 Review Across Files and Sessions: reasons and full task text"
type: archive
summary: "the reasons behind each choice of PLAN-025, which research finding or open check each task answers, and the full Wave 1 task text"
created: 2026-10-27
---

# PLAN-025 detail

Reasons and long text for [[PLAN-025-review-across-files-and-sessions]]. Numbers like 1.13 are findings, H1 to H14 hypotheses and G1 to G22 open checks of [[research/human-surface/RESEARCH-review-across-files-and-sessions]]. Task lines appear without their checkbox so that no tool reads this file as a task list; the plan holds the live task lines.

## Choices, with reasons

- **Several files:** one review, one card, one answer. Today several files go out as several requests and are answered separately (4.4); GitHub, Gerrit and Phabricator close a review with one answer (1.13).
- **Marks per file:** read or not, plus an optional note; no approve per file. Every review tool surveyed keeps a yes-or-no mark per file beside one answer for the whole review, and none approves each file (1.16). Approving once also keeps decision D-04 of the spec: the human approves one time. The mockup of [[research/human-surface/RESEARCH-plugin-ui-mockup]] drew an approve per file (1.8, 1.9); the new mockup (TASK-210) shows the one-answer form.
- **When a file counts as read:** on opening, as Gerrit does with its preference on (1.12); a click per file would add clicks the walk is meant to save.
- **Moving between files:** the controls of the earlier mockup (1.8) and GitHub's single file mode (1.11). Opening a listed file, by a link or by hand, moves the walk to it (H4), so following a link never loses the place.
- **Where the walk lives:** the side panel stays while the human moves between files, and a block drawn in a document goes when he leaves it (5.2). The earlier mockup drew the walk as a block only because it had no panel (5.4). PLAN-024's TASK-206 therefore points to this plan for the walk (TASK-212).
- **Telling sessions apart:** two sessions in one vault give two cards with nothing telling them apart (2.9). The request gains `project` (the folder holding the vault) and `session` (the Claude Code session's id, read from `CLAUDE_CODE_SESSION_ID`, set by Claude Code in each session's environment); the mockup decides how the card shows them (H5).
- **Reviews of other projects:** each Obsidian reads only its own vault's reviews, and a wrong window refuses a file that is not its own (2.6). D-06 asks for several Obsidians, each guiding through its own files; a list across projects is an extra view, held by [[plans/PLAN-024-working-in-compass-is-visual]] TASK-206, which needs the names TASK-211 adds (5.8).
- **Which edits count:** an edit to a file no review names lands on the newest card, whichever session owns it (2.11), and the edited list picks up Obsidian's own table padding and files Compass writes (4.5, 4.6). Whether Obsidian's file-changed event fires for other programs' writes is open (G5); TASK-209 settles it before TASK-214 is detailed (H6). If the events cannot tell the human's typing from other writes, a review lists only edits to its own files.
- **Stepping aside:** the decision is made when the request goes out, by a check that finds any Obsidian window focused, another project's included (2.13, 4.8). The plugin knows whether its own window has focus, so each card decides alone (H6).
- **A link that reaches nothing:** the link opener ignores failure (2.15), and one forum report says a link to an already open vault does nothing (2.4), against Obsidian's docs (2.3). TASK-208 runs the check (G1 to G4); TASK-216 is built only if a link can fail (H7, H13).
- **Change report after an answer:** the diff printed after an answer covers the whole repository, so one session's report holds another session's work (2.12). What is lost: the waiting session no longer reads other files' changes inline; it sees their names, and `git diff <sha>` still shows them in full. Decision D-05 (know the deltas) holds for every file the review touched.
- **Approvals with several documents:** whether the skills that ask for approval can pass several files at once is unchecked (G18); the plan and its detail file, or a spec and its research, are the common pairs.
- **VS Code:** no finding shows the surface interface or the file exchange needing a change (3.1, 3.2, H8). Its blockers are window routing and raising (3.10, 3.12), so it follows the Obsidian walk instead of splitting effort. Cursor runs an older engine (3.17); VSCodium runs extensions that use only the public interface.
- **Two editors set up:** today the first configured surface wins and nothing lets a project prefer one (3.3, H9).
- **Stepping aside on VS Code:** no extension call raises or minimizes the window (3.12, medium confidence); `code -r` and `-g` bring a window forward at a file (3.15). Stepping aside is decision D-02 of the spec; on VS Code it holds only if TASK-220 finds a way (G12), otherwise VS Code stays in front after an answer (H12). Obsidian keeps it in full.

## Where each hypothesis and open check goes

| Research item | In the plan |
| --- | --- |
| H1, H2, H3 | TASK-211 (request and answer), TASK-213 (panel) |
| H4 | TASK-210 (mockup), TASK-213 |
| H5 | TASK-211 (names on the request), TASK-210 and TASK-213 (on the card) |
| H6 | TASK-214 (edits), TASK-215 (stepping aside) |
| H7, H13 | TASK-216, conditional on TASK-208 |
| H8, H11, H14 | TASK-223 |
| H9, H10 | TASK-222 |
| H12 | the last choice, TASK-220 |
| G1 to G4 | TASK-208 |
| G5, G17 | TASK-209 |
| G6 | [[PLAN-022-review-in-obsidian]] TASK-177 |
| G7, G8 | TASK-219 |
| G9 | not needed: the walk lives in the panel, never in a block |
| G10 to G14 | TASK-220 |
| G15 | not needed: Zed, Typora and Logseq are out of scope |
| G16 | TASK-219 records how the human reached the window |
| G18 | TASK-218 |
| G19 to G22 | no task: they bear on how sure a finding is, and the live checks replace the forum reports |

## Wave 1 task text

- TASK-208: with this vault and a scratch vault (`.compass/tmp/trials/second-project/.compass`, registered in Obsidian, Compass Review installed with `compass review --install`) both open, `compass review` is run from each project on a committed scratch note. Recorded per run: the Obsidian version, whether the plugin of the right vault wrote the answer, which window came forward. Then the scratch vault's window is closed and a review sent to it (G2); a link is sent to the vault whose window is already open, the case the forum report describes (G3); and a second link is sent while the first window is up, to see whether Windows hands it to the running Obsidian (G4). The document `RESEARCH-review-live-checks` is created with these results, one table per check.
- TASK-209: a throwaway plugin under `.compass/tmp/trials/review-edits/`, installed into this vault as `.obsidian/plugins/compass-review-edits/`, appends to `.compass/tmp/trials/review-edits/events.jsonl` each `vault.on("modify")` and `workspace.on("editor-change")` event with the path and time. Four writes follow, in order and timed: a script rewrites a scratch note, `compass sync` rewrites `active.md`, the human types one word in a second scratch note, and the human edits a cell of a table with Obsidian's table editor. A script lines the events up with the writes; the result goes into the live checks document, and the plugin is turned off.
- TASK-210: the mockup plugin `compass-ui-mockups` gains a side panel (an Obsidian item view on the right) holding two cards: the first walks four real files ([[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]], this plan, its detail file and [[research/human-surface/RESEARCH-review-across-files-and-sessions]]) with a reason line per file, read marks set on opening, a note per file, and one Approve and one Needs changes; the second is a sample card from another session, labelled with its project and session. Opening a file outside the review shows "On this file". The write-up, `RESEARCH-review-panel-mockup`, shows each screen and counts the clicks for approving the four-file review, asking changes on one file, and leaving a note on an outside file, beside today's four separate reviews. A Send writes its answer under `tmp/mockups/ui/verdicts/` in the verdict shape of TASK-211.
- TASK-211: request: `{"id", "surface", "file", "files": [{"file", "why"}], "session", "project", "title", "return", "commit"}`, `file` equal to `files[0].file` so the shipped plugin keeps working; `why` comes from an optional `--why "<path>=<line>"` flag, repeated. `session` is `CLAUDE_CODE_SESSION_ID` or empty, `project` the name of the folder holding the vault. Answer: an optional `files: [{"file", "read", "note"}]`; `read` a boolean, `note` a string or absent. The commit check runs on every file and names the first one that fails. `--status` prints `pending <id> <first file> (+N more)`. After the answer, one line per file: `file <path> read|unread [note: ...]`, then the change report, then the text of each file that has a note or an edit. The guard denies a subagent's write to any listed file of a pending review.
- TASK-212: TASK-206's line in [[plans/PLAN-024-working-in-compass-is-visual]] gains: the walk through several files is the panel of [[PLAN-025-review-across-files-and-sessions]], and its list of reviews across projects reads `project` and `session` from TASK-211. A line in that plan's revision log records the change.
