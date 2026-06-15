---
name: promote-spec
description: Promote a flat spec into a folder spec. The CLI does the move (`compass promote`); this skill decides when to promote and guides authoring the children.
version: 2.0.0
allowed-tools: [Read, Glob, Grep, Bash]
argument-hint: "<SPEC-NNN-name | path-to-spec>"
when_to_use: "Run /compass:promote-spec when a flat spec needs to grow children. Common cause: the spec body exceeded ~2,000 tokens, or you identified 3+ sub-concerns that deserve their own files."
---

# /compass:promote-spec - Convert a flat spec to a folder spec

A flat spec is one file: `specs/SPEC-002-tile-editor.md`. A folder spec is a directory whose `index.md` IS that spec, with child specs inside. Promote when the spec has grown 3+ sub-concerns or its body would exceed ~2,000 tokens.

The move itself is mechanical and lives in the CLI. This skill is the judgment around it.

## 1. Confirm it should be promoted

Read the spec. Does it genuinely have 3+ separable sub-concerns, or is it just long prose? Only promote when children will follow; a folder with one `index.md` and no children adds nothing.

## 2. Perform the move

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" promote <SPEC-NNN-name>
```

`compass promote` (`plugin/cli/commands/promote.py`) resolves the spec, refuses if it is missing or already a folder, `git mv`s it to `<name>/index.md` (history preserved), and adds `children_count: 0`. Inbound `[[SPEC-NNN-name]]` wikilinks keep resolving because the folder name equals the old stem - no link rewrite is needed. Surface the command's report.

## 3. Author the children

The folder now exists with an empty `index.md` parent. Create child specs inside it with the spec-write or planner agent, numbered locally (`compass next-num spec <SPEC-NNN-name>`). The next `compass sync` updates the parent's `children_count` and the root index tree.

## Failure modes worth naming

- Promoting a spec that will never have children - a folder with a lone `index.md` is worse than the flat file. Don't.
- Promoting a non-spec/plan/decision artifact - the CLI refuses; respect it.
- Hand-editing wikilinks to new paths - unnecessary, Obsidian resolves the short form to the folder's `index.md`.
