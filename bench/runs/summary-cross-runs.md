# Cross-Run Quality Summary: Two Smoke Fixtures

**Date:** 2026-06-10
**Method:** Both arms via Claude Code Agent tool, `general-purpose` subagent_type. Methodology delivered as text in the compass arm's system context. Same task prompt, same tool access.

## Result table

| Metric | Fixture 1: binary-search-bug | Fixture 2: merge-sorted-lists |
|---|---|---|
| Visible-test outcome | tie (5/5 each) | tie (9/9 each) |
| Held-out generalization | tie (10/10 each) | tie (9/9 each) |
| Ruff lint | tie (clean each) | tie (clean each) |
| Lines of code | tie (13 = 13) | baseline 22, compass 26 (compass +4 dead code) |
| Blind LLM judge (25 max) | tie (16/25 each, code character-identical) | tie (16/25 each, cancel-out micro-differences) |
| Total tokens | baseline 21,696 (-4%) | baseline 22,495 (-5%) |
| Tool calls | tie (4 each) | compass 4 (-20%) |
| Wall seconds | baseline 23.9 (-19%) | tie (33 each) |

## Headline finding

**On test-driven single-function tasks, the Compass methodology context as text adds ~5% token overhead with zero measurable improvement on any quality axis we tested.** Both arms produced solutions that pass visible tests, pass held-out tests, lint clean, score identically on a blinded LLM rubric, and were either character-identical or near-identical in code structure.

The result is honest and Pareto-neutral: Compass methodology context doesn't hurt outcomes; it just doesn't help on this task class.

## Why no signal

Frontier-model agents already follow the practices Compass codifies on simple tasks - read tests first, treat tests as the spec, write minimal correct code. Encoding those practices as system prompt text adds tokens without changing behavior the model already exhibits.

For methodology to show measurable value, the fixtures need to exercise something the methodology layer adds *beyond what the model does by default*. Candidates:

1. **Methodology-distinctive artifacts being used.** Tasks where the agent needs to write a spec, get human approval, and then build against the spec - so the methodology's gate is doing real work.
2. **Multi-turn / multi-file scope.** Tasks where the methodology's vault carries forward state that affects later decisions.
3. **Installed-plugin features (hooks, SubagentStop, file-based vault).** The current bench measures methodology-as-text, NOT methodology-as-installed-system. The hooks and vault don't run inside an Agent tool subagent.
4. **Tasks without tests.** Where the agent must surface edge cases instead of satisfying prewritten ones.
5. **Long-horizon tasks.** Where the methodology's task decomposition prevents the baseline from getting lost.

## What we learned about evaluation methodology itself

- **The Agent tool is the right harness for fast iteration.** Two arms, six minutes per fixture, real numbers, no Docker or external CLI. Much better than the bash-wrapper approach.
- **Held-out tests and LLM judging are necessary, not sufficient.** They give us multi-dimensional quality, but if the underlying signal is zero, more metrics just confirm zero.
- **Blinding the LLM judge matters.** Both judges spotted the micro-differences and correctly rated them as canceling out, instead of pattern-matching "methodology arm = better."
- **Static analysis is cheap and worth running.** Ruff was clean here, but on a more complex fixture it would catch lint debt the test suite wouldn't.

## Recommended next direction

The methodology-context test has been validated as Pareto-neutral. To find signal, the bench needs one of:

- **Build the plugin-install comparison.** Real Claude Code with `--plugin-dir` vs without. Tests the full system (hooks, vault, agent definitions), not just the text. This is the bash-wrapper approach we deprecated; would need to come back.
- **Design discriminating fixtures.** Multi-file changes, ambiguous specs, no-tests-provided. The candidates listed above.
- **Graduate to Terminal-Bench's real tasks.** Their tasks are longer-horizon, multi-step, with non-trivial planning. Use the Agent tool pattern, point at their task descriptions.
