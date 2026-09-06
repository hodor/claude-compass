---
title: A destructive step removes only what it manages, never "anything not in my source"
type: lesson
status: active
category: process
area: methodology
tags: [install, update, cleanup, data-loss, user-files]
created: 2026-06-15
updated: 2026-08-23
score: 5
summary: "Delete only what you installed or planned, by name; 'everything else here' always holds files that are not yours"
seen: []
---

`/compass:update` cleaned a renamed skill via "remove any skill not in the Compass source" and deleted a user-authored skill; `make-unit --undo` would have `rmtree`'d a unit folder still holding content its move plan never accounted for.
Both are one defect: a destructive step whose scope is "everything here" rather than exactly what it installed or planned, tracked by name (or a manifest).
The complement set ("everything else in this directory") always contains things that are not yours - user files, unclassified artifacts.
Fix pattern: delete an explicit named list, or refuse all-or-nothing when the target holds anything the plan does not account for.
The second instance was caught by the builder's code-review station before merge; the first shipped and destroyed a user's skill.
