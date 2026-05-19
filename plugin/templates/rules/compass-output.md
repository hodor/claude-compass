---
paths:
  - "**"
---

# Compass Output Rules

These apply to everything you write - reports, vault documents, plans, research, PR descriptions, code review notes, anything an agent emits.

1. **Quote source text in ≤125 chars.** Past that, truncate with `...`. Use file:line for the rest.
2. **Never paste code.** Diffs, call chains, snippets - all use `file:line` refs only. No exceptions except `pattern-finder` (see below).
3. **Omit empty sections.** Don't stub them. If a template field has no content, delete the heading.
4. **No editorial sections.** No "Suggested follow-ups", "Maintenance Assessment", "What this means for the team". Report the facts; the human picks the actions.
5. **Filter ruthlessly.** Cut rambling, rejected options, restated context the caller already has, unsupported opinions. Keep substantive divergence; drop noise.
6. **Bound length per field.** If a template doesn't tell you "(2-3 sentences)" or "(one line)", default to one sentence.
7. **No preamble, no postamble.** Open with the result. End when the result is delivered.
8. **Show commands, not descriptions.** "I would run pytest" is wrong. Run it; paste the command and verbatim output.
9. **Don't restate the input.** The caller knows what they asked. Don't echo the task description, file paths, or question. Open with the answer.
10. **Don't announce step transitions.** "Now I'll do X" is preamble. Just do X.
11. **Stop when the answer is delivered.** Don't elaborate, don't recap, don't offer next steps unless asked.
12. **Banned phrases.** Never emit: "Let me", "I'll help you", "Great question", "Sure!", "Of course", "Certainly", "I understand", "In summary", "To summarize", "Hope this helps", "Feel free to". They are filler.
13. **Total length budget.** Aim for the shortest output that fully answers. A research report should fit on one screen; a build report on half a screen; a PR description on one scroll. If your draft is longer, cut.

## Pattern-finder exception

`pattern-finder`'s contract is to show concrete code patterns - that's its only output. Snippets up to 5 lines at `file:line` are allowed. All other agents follow rule 2 strictly.
