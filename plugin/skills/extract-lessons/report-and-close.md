# Report fields and closing the opportunity

Read at step 9 of `SKILL.md`, after the `extracted:` line is composed.

Where:
- `created` = new lessons written via lesson-write branch 4c
- `recurrence` = existing lessons score-bumped via branch 4a (includes escalations)
- `refined` = existing lessons body-edited via branch 4b, for a candidate that was not a contradiction
- `revised` = existing lessons body-edited via the 4a contradiction check's revise branch
- `archived` = existing lessons retired via the 4a contradiction check's archive branch
- `rejected` = candidates matched by the anti-list
- `errors` = candidates that returned `body_too_long` or other errors

Then close the opportunity so nothing re-opens it:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/cli/compass" capture-close <opp-id> --outcome fired \
  --candidates <N> --written <C+F+V> --recurrence <U> --rejected <R> \
  --revised <V> --archived <A> --errors <E>
```

`--written` is `created + refined + revised` - every candidate that produced or updated active lesson content. `--archived` stays out of `--written`: retiring a lesson is not adding or updating one. Omit a count flag entirely when its value is `0` and no candidate of that kind was considered at all (e.g. an opportunity with no contradiction candidates omits `--revised` and `--archived`) - `capture-close` records only what it is given, so an omitted flag and an explicit `0` are different rows. This call replaces the bare mutex-marker-only ending the legacy phase path used before opportunities existed; for a `phase` kind opportunity, step 8's `.processed` marker is written first, same as before, and this call closes the opportunity on top of it.
