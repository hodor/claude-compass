---
title: "Review Live Checks"
type: research
status: draft
confidence: medium
area: methodology
tags: [obsidian, review, live-check, human-surface]
depends_on: ["[[PLAN-025-review-across-files-and-sessions]]"]
summary: "live runs of compass review with two projects' vaults open in one Obsidian: which window each review reaches, a closed vault, an open vault, a second link"
created: 2026-10-27
updated: 2026-10-27
git_branch: "master"
author: "orchestrator"
---

# Review Live Checks

```mermaid
flowchart LR
  C[Compass project] -->|review link| OC[Compass vault window]
  S[Second project] -->|review link| OS[Second vault window]
  S -->|link, window closed| R[Obsidian reopens the vault]
```

Runs of `compass review` with this vault and a scratch second project's vault open in the same Obsidian, checking whether each review reaches its own project's window ([[PLAN-025-review-across-files-and-sessions]], open checks G1 to G4 of [[research/human-surface/RESEARCH-review-across-files-and-sessions]]).

## Setup

| Item | Value |
| --- | --- |
| Obsidian | 1.14.5 (`obsidian-1.14.5.asar`), Windows 11 |
| Second project | a git repository at `.compass/tmp/trials/second-project/`, its vault `.compass` registered in Obsidian, Compass Review installed with `compass review --install` |
| Each run | `compass review .compass/scratch-note.md` from the second project, on a committed note; the Compass project's own review sent at the same moment |

## Two vaults, each review to its own window (G1)

| Run | Sent from | Answer written in | Window that came forward, in the human's words |
| --- | --- | --- | --- |
| 20261027T165416-efedb5 | second project | the second vault's `tmp/review/` | "two, one obsidian and tghen another with the scratch-node.md" |
| 20261027T165416-f61145 | Compass project, same second | pending | pending |

The second project's answer was written by the second vault's plugin, so its link reached its own vault.

## Vault closed (G2)

| Run | State when sent | Result |
| --- | --- | --- |
| 20261027T165529-d1bb84 | the second vault's window closed by the human, the Compass window open | approved: the window reopened by itself with the card |

## Link to a vault whose window is open (G3)

Run 20261027T165416-efedb5 went to a vault whose window was already open, the case a forum report describes as doing nothing. The card arrived and the answer was written.

## Second link while Obsidian runs (G4)

Every run went to an Obsidian already running, two of them in the same second to two vaults. Each link reached the running Obsidian: no second Obsidian started, and each answer was written in its own vault.

## Seen beside the checks

Two answers listed `scratch-note.md` as edited although the human only approved. In the second, the edit is one space added before the note's heading (`# Did this vault reopen?` became ` # Did this vault reopen?`). Whether a keystroke or Obsidian wrote it is TASK-209's question.
