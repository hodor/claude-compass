---
paths:
  - "**"
---

# Compass Output Rules

These apply to everything you write - reports, vault documents, plans, research, PR descriptions, code review notes, anything an agent emits.

1. **Quote source text in ≤125 chars.** Past that, truncate with `...`. Use file:line for the rest.
2. **Never paste code.** Use `file:line` refs. Diffs, call chains, and snippets included.
3. **Omit empty sections.** Don't stub them. If a template field has no content, delete the heading.
4. **No editorial sections.** No "Suggested follow-ups," "Maintenance Assessment," "What this means for the team." Report the facts; the human picks the actions.
5. **Filter ruthlessly.** Cut rambling, rejected options, restated context the caller already has, and unsupported opinions. Keep substantive divergence; drop noise.
6. **Bound length per field.** If a template doesn't tell you "(2-3 sentences)" or "(one line)", default to one sentence.
7. **No preamble, no postamble.** No "I will now...", "Here is...", "In summary...". Open with the result.
8. **Show commands, not descriptions.** "I would run pytest" is wrong. Run it; paste the command and the verbatim output.
9. **Don't restate the input.** The caller already knows what they asked for. Don't echo the task description, the file paths they gave you, or the question they posed back at them. Open with the answer.
10. **Don't announce step transitions.** "Now I'll do X" is preamble. Just do X.

## Pattern-finder exception

The `pattern-finder` agent's contract is to show concrete code patterns - that's its only output. It may include short snippets (up to 5 lines) at `file:line` to illustrate each variation. All other agents follow rule 2 strictly: file:line references, no code.
