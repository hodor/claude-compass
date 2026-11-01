# Feedback

Durable guidance from the human reviewing this loop, loaded into every run after the selected work. A rejected increment's reason is added below by `compass loop review`.

## Guidance
- Tests pin some sentences of `compass-pipeline.md` and the guide skill (`plugin/cli/tests/test_numbered_choices_text.py` and others). A move that removes a pinned sentence fails the suite and is rejected; leave pinned sentences in place.
- A pointer left in a source names the skill or agent by its name ("the `research` skill, section X"), never a `plugin/...` path: an installed project has no `plugin/` folder.
- Move whole paragraphs or sections, a hundred tokens or more per run; a one-sentence move does not pay for its run.
- A skill or agent body has a line ceiling in the tests; add moved text to an existing paragraph or a new file in the skill's folder, never new lines in SKILL.md.
- After moving a rule, every skill or agent that does the work the rule governs names the rule's new home, so an agent doing that work reaches the full text. Check with a grep for the work (for example "ADR", "research axes") before finishing.
- The "Data" section of the pipeline rules stays whole in the always-loaded rules, its enforcement paragraph included: it protects the human's information in every session.
- full suite failed: 1 failed, 2213 passed, 1 skipped, 1 deselected, 2838 subtests passed in 659.53s (0:10:59)
