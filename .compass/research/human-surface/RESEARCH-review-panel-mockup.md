---
title: "Review Panel: Mockup"
type: research
status: complete
confidence: low
area: methodology
tags: [obsidian, plugin, mockup, review, side-panel, human-surface]
depends_on: ["[[PLAN-025-review-across-files-and-sessions]]"]
summary: "a side panel where one answer covers the four files of a review, two sessions are told apart, and a file outside the review takes a note; clicks counted against one card per file"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
git_commit: "ca1aaab"
author: "builder"
---

# Review Panel: Mockup

The panel draws while the `compass-ui-mockups` plugin (a throwaway Obsidian plugin in this vault's `.obsidian/plugins/`) is on. It opens in the right sidebar when Obsidian starts, and the command "Compass mockup: open review panel" brings it back. Everything on it reads this vault's real documents; nothing is sent to Claude. Choosing Approve or Needs changes writes one sample answer file under the vault's `tmp/mockups/ui/verdicts/`, in the shape set in [[archive/PLAN-025-review-across-files-and-sessions-detail]], and nothing else. Confidence is low: the click counts are read from the mockup and from the review card in `plugin/obsidian/compass-review/main.js`, never timed on a person.

A review is one question put to the human about one or more documents; a session is one running Claude Code conversation, and a project is the folder holding the vault. The panel follows [[PLAN-025-review-across-files-and-sessions]], which builds on [[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]] and [[research/human-surface/RESEARCH-plugin-ui-mockup]].

## 1. One review, four files

The first card walks four real files of this vault: the spec [[specs/human-surface/SPEC-030-review-documents-open-in-obsidian]], the plan [[PLAN-025-review-across-files-and-sessions]], its detail file [[archive/PLAN-025-review-across-files-and-sessions-detail]] and the research [[research/human-surface/RESEARCH-review-across-files-and-sessions]]. It lets the human:

- See where he is ("File 2 of 4") and move with Previous, Next and Next unread. Each move opens that file in the editor.
- See every file in one list, each with a line saying why it is in the review, a mark for read or unread, and its note count.
- Open a listed file by hand, from a link or the file explorer, and find the walk has moved to it. A file is marked read the moment it opens, by the stepper or by hand.
- Write a note for the file he is on; the note field follows him from file to file.
- Answer once for the whole review: Approve, or Needs changes, which is disabled until a first note exists.

There is no approve per file. The read marks and notes travel in the answer, so Claude sees which files were opened and what was said about each. Edits made to the four files while the review is open are listed in the answer too.

## 2. A card from another session

The second card is a sample, labelled so. It shows what a second session in the same project would add: a separate card with its own files, read marks and buttons. Both cards show the project name (the folder holding the vault) and a session code (the first six characters of the session's id), so two reviews that look alike can be told apart. Its buttons do nothing.

## 3. A note on a file outside the review

When the open file is not one of the four, the first card gains an "On this file" box naming that file, with its own note field. The note goes in the same answer as a comment on that file. It counts as a first note, so it also enables Needs changes. Opening a listed file hides the box again.

## Clicks

A click is one press of a button, a file row or a link, and opening a file by hand counts as one. Typing is counted apart. Both ways start with one file already open. "Today" is four separate reviews of one file each, as Compass sends several files without this panel: the review panel in `plugin/obsidian/compass-review/main.js` stacks one card per review, each with its own Approve and Needs changes and, for any open file the card does not review, an "On this file" note.

| What the human does | With the panel | Today (four cards) |
|---|---|---|
| Read all four files and approve | 4 clicks: Next three times, Approve. One answer arrives. | 7 clicks: open three files from their cards, Approve on each of four cards. Four answers arrive. |
| Approve without reading | 1 click: Approve. | 4 clicks: Approve on each card. |
| Ask for changes on the third file, after reading the first two | 3 clicks and one note: Next twice, Needs changes. One answer arrives, with the note against the third file. | 6 clicks and one note: open two files, Needs changes on the third card, Approve on the other three. Leaving those three unanswered saves 3 clicks and keeps three reviews waiting. The panel's one answer says nothing per file about the first, second and fourth. |
| Leave a note on a file outside the review, then answer | 2 clicks and one note: open the file, Approve or Needs changes. | 2 clicks and one note: open the file, write the note on one card's "On this file" box and answer that card. The other three reviews keep waiting. |

The panel saves clicks where the human answers several files, and gives Claude one answer for the review. A single note on an outside file costs the same either way; the gain there is that the note rides on the one answer for the whole review.

## What it needs to ship

- The review request lists its files, each with its one-line reason, plus the project and session names. The plan's [[archive/PLAN-025-review-across-files-and-sessions-detail]] file sets these fields and the answer's `files` list.
- The panel reads read marks from Obsidian's file-open events. Whether file-changed events can tell the human's typing from other programs' writes is an open check in the same detail file; the mockup lists an edit only for the review's own files.
- The mockup's project name comes from the vault's folder, and its session code is a fixed sample; the plan has the real card read the id Claude Code sets for each session.
