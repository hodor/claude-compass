---
title: "index.md Is Every Folder's Doc; Generated Links Are Piped Full Paths"
type: decision
status: accepted
confidence: high
area: methodology
tags: [taxonomy, index, wikilinks, obsidian]
created: 2026-08-30
updated: 2026-08-30
author: "orchestrator"
summary: "every folder's doc is index.md, type dirs included; generated surfaces emit piped full-path links so they click through in Obsidian; the folder-named-doc alternative is rejected"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[RESEARCH-taxonomy-for-unambiguous-placement]]"]
---

# index.md Everywhere, Piped Links on Generated Surfaces

## The fork

Obsidian resolves a wikilink by file basename or path, never by folder name - so a folder's `index.md` cannot be opened by clicking `[[folder-name]]`; the click spawns an empty phantom note. Two ways out were live: name each folder's doc after the folder (`distribution/distribution.md`, basename resolution works everywhere), or keep `index.md` and write generated links as piped full paths. The human ruled for `index.md`.

## Decision

- **D-01:** Every folder's doc is `index.md` - domains, folder specs, units, and the type dirs themselves - one predictable location ([[SPEC-022-vault-organized-per-domain]] D-05). Links on generated surfaces (root index lines, `compass tree` output) are piped full paths - `[[specs/distribution/index|distribution]]` - which display as the plain name and click through.

## Consequences

Good: one location every human, agent, and tool already agrees on; no dual convention in the scanner; no migration of existing folders; every generated line becomes clickable in Obsidian.

Bad: a hand-typed bare `[[distribution]]` still does not click through in Obsidian - agents resolve it by the glob rule, the human must click a generated line or navigate the folder tree; piped paths make generated markdown longer in the raw; every current and future generated surface must remember to emit the piped form, or the phantom-note bug quietly returns there.
