# Write archive (step 4d)

Reached only from an `intent: archive` payload naming a `target` lesson (a contradiction-archive call from `extract-lessons`, or an explicit human instruction). Never reached through the step 3 dedup judgment.

Never archives an escalated lesson - a lesson carrying `escalated:` in its frontmatter carries human weight; flag it for human review instead of retiring it autonomously (the same rule `consolidate` applies). Return `error: cannot autonomously archive an escalated lesson`.

Otherwise:

- Read the `target` lesson file's frontmatter. Set `status: archived`, update `updated` to today. Do not move or delete the file.
- Guarantee the file's frontmatter carries the full field set (title, type, status, category, area, tags, score, summary): copy any missing field from the lesson's catalog row before the row is touched. An archived lesson's file must stand alone - consolidate later drops archived rows from the catalog, and a field living only in the row would be destroyed with it.
- Append the input `body` (the superseding reason) to the lesson body on a new line, prefixed `Superseded:`. This edit is exempt from the 5-line body cap - an archived lesson is retired reference material, not active guidance competing for read budget.
- Update the matching row in `.compass/meta/lessons-catalog.yaml` to `status: archived`.

Return `archived: <target-filename>`.
