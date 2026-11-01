# Actuator instructions

You are one step of a control loop. Make exactly one small, reviewable change that moves the project toward the end state, then stop.

## End state

The text Compass puts into Claude Code's context, over all the work a session does, is as small as it can be while Compass works as well as before. That text is every rules file under `plugin/templates/rules/` and every skill and agent `name`, `description` and `when_to_use` (loaded in every session), plus every skill body, file inside a skill folder and agent body (loaded each time the work calls it). A source counts by how often real sessions load it, so a skill run in most sessions weighs nearly as much as the rules.

## What to do

Selected work lists sources as `<tokens per session> <path under plugin/>`, largest first. Take the first one unless `feedback.md` rules it out, then the next.

1. Read the source and find one passage to shrink:
   - in an always-loaded source, a passage an agent needs only during particular work (the detail of one pipeline stage, a procedure, an example, a format);
   - in a skill or agent body, a passage only some runs of that skill or agent need (a rare branch, a long example, a reference table).
2. Move it to where that work already loads its instructions: the body of the skill or agent that does that work, or an `.md` file inside that skill's folder which the body names for the case that needs it. Carry the text over unchanged. Text that is said twice may be said once, with the other place pointing to it.
3. In the source, leave one short sentence that names where the moved text now lives, so an agent knows to read it when the work comes up.
4. For a `description` or `when_to_use` field: shorten wording only. Every trigger phrase and every case it names stays, because they decide when the skill or agent loads.
5. Re-read both files: nothing was lost, the moved text reads correctly in its new home, and the source still makes sense.

One passage per run. Prefer the largest passage you can move safely.

## What never to touch

- Never delete text. Every sentence removed from a source exists in its new home, or, for a sentence said twice, in the place it repeated.
- Never weaken, soften or make optional anything a gate, a test, a guard or the human's approval relies on: the "When to Stop and Ask" gates, the Data rule, the review rule, the No Verbiage rule, Verification, MUST invariants.
- Never edit files under `plugin/cli/`, tests, hooks, `.claude/`, `.compass/` or this loop's own folder.
- Never add a new file under `plugin/templates/rules/` (every file there loads in every session).
- No em dashes or en dashes in any text you write.
