# Actuator instructions

You are one step of a control loop. Make exactly one small, reviewable change that moves the project toward the end state, then stop.

## End state

The text Compass puts into every Claude Code session is as small as it can be while Compass works as well as before. That text is each file under `plugin/templates/rules/` whole, plus the `name`, `description` and `when_to_use` frontmatter of each `plugin/skills/*/SKILL.md` and `plugin/templates/agents/*.md`, plus the CLAUDE.md block `plugin/skills/setup/SKILL.md` proposes. Everything else (skill bodies, agent bodies, files inside a skill folder) loads only when the work needs it.

## What to do

Selected work lists always-loaded sources as `<estimated tokens> <path under plugin/>`, largest first. Take the first one unless `feedback.md` rules it out, then the next.

1. Read the source and find one passage an agent needs only during particular work, not in every session: the detail of one pipeline stage, a procedure, an example, a format.
2. Move it to where that work already loads its instructions: the body of the skill or agent that does that work (for example `plugin/skills/build/SKILL.md`, `plugin/skills/obsidian/SKILL.md`, `plugin/skills/methodology/SKILL.md`), or a new `.md` file inside that skill's folder. Carry the text over unchanged.
3. In the source, leave one short sentence that names where the moved text now lives, so an agent knows to read it when the work comes up.
4. For a `description` or `when_to_use` field: shorten wording only. Every trigger phrase and every case it names stays, because they decide when the skill or agent loads.
5. Re-read both files: nothing was lost, the moved text reads correctly in its new home, and the source still makes sense.

One passage per run. Prefer the largest passage you can move safely.

## What never to touch

- Never delete text. Every sentence removed from a source exists in its new home.
- Never weaken, soften or make optional anything a gate, a test, a guard or the human's approval relies on: the "When to Stop and Ask" gates, the Data rule, the review rule, the No Verbiage rule, Verification, MUST invariants.
- Never edit files under `plugin/cli/`, tests, hooks, `.claude/`, `.compass/` or this loop's own folder.
- Never add a new file under `plugin/templates/rules/` (every file there loads in every session).
- No em dashes or en dashes in any text you write.
