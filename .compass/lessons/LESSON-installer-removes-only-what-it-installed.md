---
title: An updater must remove only files it manages, never "anything not in my source"
type: lesson
status: active
category: process
area: methodology
tags: [install, update, cleanup, data-loss, user-files]
created: 2026-06-15
updated: 2026-06-15
score: 5
summary: "A tool that installs into a shared dir must delete only its own named artifacts on cleanup; 'remove anything not in my source' destroys user files"
seen: []
---

`/compass:update` copies skills into the shared `.claude/skills/` and, to clean up a renamed skill (bootstrap -> setup), ran "remove any skill not in the Compass source".
That logic cannot tell a retired Compass skill from a user-authored project skill, so it deleted the user's own `iwyc-code-review` skill on every update.
Fix: remove only an explicit named list of retired Compass skills; never infer "files I manage" as "everything in the shared directory".
General rule: an installer's deletion scope is exactly what it installed, tracked by name (or a manifest) - the complement set ("everything else here") always contains things that are not yours.
Found by an agent running Compass in another repo - exactly the case the [[LESSON-no-agent-bookkeeping]] bug-reporting path exists for, though here the maintainer fixed it directly.
