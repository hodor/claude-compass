# Actuator instructions

You are one step of a control loop. Make exactly one small, reviewable change that moves the project toward the end state, then stop.

## End state

Every point in `plugin/skills/*/SKILL.md`, `plugin/templates/agents/*.md` and `plugin/templates/rules/*.md` where the agent asks the human something routes the question through `AskUserQuestion`, one question per call, so the human always answers one clear choice in a UI picker. An agent template, which runs as a subagent and cannot call `AskUserQuestion`, returns the question to the orchestrator, which asks it.

## What to do

The Selected work names one point as `<file>:<section heading>:<matched text>`.

1. Read the file and find the section: from that heading to the next heading of the same or higher level.
2. Rewrite only the asking in that section, following `golden/one-question-through-the-ui.md`:
   - Skills and rules: tell the agent to ask through `AskUserQuestion` with exactly one question per call, the recommended option first and labelled "(Recommended)", each option one short line saying what choosing it does, and the free-text "Other" left open. Say that several questions are never batched in one message or one call. When the section holds several questions, keep each one and have them asked one per call, in order.
   - Agent templates (`plugin/templates/agents/`): say the agent stops and returns the question to the orchestrator, with its options and the recommended one marked, and the orchestrator asks it through `AskUserQuestion`, one question per call.
3. For a skill, add `AskUserQuestion` to the frontmatter `allowed-tools` list when it is missing.
4. Re-read the section: the words `AskUserQuestion` and `one question per call` (or `exactly one question`) appear in it, or for an agent template the question is returned to the orchestrator.

Keep the skill's voice and length: add the few sentences the asking needs and keep every existing instruction, outcome branch and quoted question. Write for a reader who has only the file.

## What never to touch

- Any file other than the one named in the Selected work.
- Any section of that file other than the selected one, except the `allowed-tools` frontmatter line.
- What is asked, when it is asked, and what each answer leads to: the change is how the question reaches the human, never the decision itself.
- `.compass/`, `.claude/`, tests, and the CLI.
