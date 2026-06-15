---
name: report-bug
description: Report a Compass bug. Captures it locally (deduped by fingerprint) via the compass CLI and files it as a GitHub issue against the Compass repo, skipping any duplicate that is already open.
version: 1.0.0
allowed-tools: [Bash]
argument-hint: "<description of the bug>"
when_to_use: "Use when Compass itself misbehaves in any project - a CLI error, a validate false positive, a skill doing the wrong thing - and you want it filed against the Compass repo. CLI crashes are captured automatically; this is for things you notice. Triggers: 'report a compass bug', 'compass is broken', 'file a compass issue'."
---

# /compass:report-bug - Report a Compass bug

Compass bugs found while working in any project should land as a GitHub issue against the Compass repo, deduplicated so the same bug from many sessions or repos collapses to one issue. The `compass` CLI does the capture and the filing; this skill is the entry point.

## 1. Capture it

```bash
compass capture-bug "<clear, specific description>" --command <which-command-or-skill>
```

This appends a fingerprinted record to `.compass/tmp/compass-bugs/` (gitignored, local). The same description dedups to one record with an occurrence count. `--command` is optional context (e.g. `validate`, `sync`, `setup`).

CLI crashes (`compass sync`, `compass validate`, ...) are captured automatically by the CLI's own error handling - no action needed for those.

## 2. File it

```bash
compass file-bugs            # dry-run: shows what would be filed, what is already open
compass file-bugs --apply    # creates the GitHub issues (requires gh authenticated)
```

`file-bugs` searches the Compass repo's existing issues for each bug's fingerprint and skips any already open - that is the no-duplicates guarantee. Filing is outward-facing, so run the dry-run first and only `--apply` once the list looks right.

## Notes

- The target repo comes from `.compass/meta/plugin.yaml` `repository:`.
- Capture is safe and local; only `--apply` touches GitHub.
- Include enough in the description to reproduce: what you ran, what you expected, what happened.
