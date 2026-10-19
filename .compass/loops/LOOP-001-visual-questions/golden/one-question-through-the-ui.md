# Golden pattern: one question through the UI

A point where the skill asks the human something routes the question through the `AskUserQuestion` tool: one question per call, the recommended option first and labelled as recommended, each option one short line saying what choosing it does, and the free-text "Other" left open. Several questions are never batched into one message or one call. The example is `plugin/skills/spec/SKILL.md`, section "7. Present for approval".

## Before

```markdown
### 7. Present for approval

Show the Problem and Desired Outcome as they will be saved, his sentences with any guess bracketed inline where it sits, then one line: "Approve?". No summary, no counts, no section list. After "needs changes", show only the lines that changed.

- **Approved:** change `status: draft` to `status: approved`. "Spec approved. Ready for research when you are."
- **Needs changes:** ask what to change, edit, present again.
- **Rejected:** change `status: archived`, ask why so you can learn.

After approval, offer: "Create another spec, or start research on this one?"
```

## After

```markdown
### 7. Present for approval

Show the Problem and Desired Outcome as they will be saved, his sentences with any guess bracketed inline where it sits. No summary, no counts, no section list. After "needs changes", show only the lines that changed.

Then ask through `AskUserQuestion`, exactly one question per call: "Approve this spec?". The recommended option comes first, labelled "(Recommended)"; each option is one short line saying what choosing it does; "Other" stays open for free text:

- **Approve (Recommended):** marks the spec approved; research can start.
- **Needs changes:** you say what to change; I edit and show the changed lines.
- **Reject:** archives the spec.

Never put several questions in one message or one call; the next question waits for this answer.

- **Approved:** change `status: draft` to `status: approved`. "Spec approved. Ready for research when you are."
- **Needs changes:** ask what to change, edit, present again.
- **Rejected:** change `status: archived`, ask why so you can learn.

After approval, ask one more question the same way: "What next?", with "Start research on this spec (Recommended)" and "Create another spec".
```

The skill's frontmatter `allowed-tools` lists `AskUserQuestion`; add it when missing.

## Agent template variant

A subagent cannot call `AskUserQuestion`. In `plugin/templates/agents/*.md` the section says the agent stops and returns the question to the orchestrator, with its options and the recommended one marked, and the orchestrator asks it through `AskUserQuestion`, one question per call.

## Why

The human answers one clear choice in a UI picker instead of parsing a question buried in prose, and the skill's wording, length and flow stay as they were.
