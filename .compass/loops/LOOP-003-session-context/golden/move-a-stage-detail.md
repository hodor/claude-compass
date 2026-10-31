# Golden: move one stage's detail out of an always-loaded rule

Before, in `plugin/templates/rules/compass-pipeline.md`:

```markdown
## Research

- Research traces to a spec.
- Before spawning researchers, present the planned axes - each in one plain line ... (a long paragraph on how the axes are presented and how the human joins)
```

After, in `plugin/templates/rules/compass-pipeline.md`:

```markdown
## Research

- Research traces to a spec.
- How research axes are presented and how the human joins: `plugin/skills/research/SKILL.md`, "Presenting the axes".
```

And in `plugin/skills/research/SKILL.md`, a new section "Presenting the axes" holding the long paragraph word for word.
