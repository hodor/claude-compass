---
title: "Axis 1b: Anthropic engineering posts, gap pass"
type: research
status: complete
confidence: medium
area: workflow
tags: [anthropic, engineering-blog, evals, sandboxing, containment, think-tool, harness]
summary: "Gap pass over six partly-read Anthropic engineering posts plus the missing 29th post; adds containment-first design, pass^k, absolute-path tool poka-yoke, think-tool deprecation, and trust-boundary lessons"
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "e2162f3"
author: "researcher"
---

# Axis 1b: Anthropic engineering posts, gap pass

From [[RESEARCH-axis-1-anthropic-engineering]] (first pass). Only what is new there.

## Question

What do the six posts the first pass left unread or partly read, and the one post hidden behind "See more", say that applies to a spec-driven, multi-agent, vault-memory coding workflow plugin?

## Methodology

Grey-literature review, same as the first pass: every source is a vendor engineering post (tier three outlet, first-party authors, vendor bias present). Each post was fetched from its own URL and read in full. Grading allowed by the brief: vendor posts with numbers and ablations grade medium, assertion-only posts grade low.

## Marks (all findings unless stated)

Vendor engineering post, first-party authors; not retracted; not a preprint; no citation count (blog); convergence noted per finding.

## Posts read this pass

| Date | Post | Depth | Note |
|---|---|---|---|
| 2025-03-20 | claude-think-tool | full | Carries a 2025-12-15 update recommending extended thinking over a think tool |
| 2025-01-06 | swe-bench-sonnet | full | Two-tool agent, 49% SWE-bench Verified; tool-design lessons |
| 2024-12-19 | building-effective-agents | full | Workflow patterns; update note defers to Managed Agents post |
| 2025-04-18 | claude-code-best-practices | full (moved to docs page) | Now https://code.claude.com/docs/en/best-practices |
| 2026-05-25 | how-we-contain-claude | full | Containment vs supervision; four "risk missed" cases |
| 2025-10-20 | claude-code-sandboxing | full | 84% fewer prompts; filesystem plus network isolation |

URLs resolve at https://www.anthropic.com/engineering/<slug> and https://www.anthropic.com/research/<slug>.

## Findings

### The 29th post

The engineering page states 29 articles. Crawling every page in the site's sitemap under /research/ (215 slugs) and keeping those whose "Team" field is Engineering returned exactly 29 posts; 28 are in the first pass's table. The missing one is **contextual-retrieval** ("Introducing Contextual Retrieval", 2024-09-19), https://www.anthropic.com/research/contextual-retrieval. It is older than the 2025-2026 window; flagged as such. The engineering page's embedded metadata lists only related articles, so it does not expose it.

1. **Contextual Retrieval: prepend a model-written, chunk-specific context line before indexing; 49% fewer failed retrievals, 67% with reranking** (confidence: high)
   - Each chunk gets 50-100 tokens of context (which document, which period, what came before) written by a small model given the whole document, then is embedded and BM25-indexed. Failure rate (1 - recall@20): 5.7% baseline, 3.7% contextual embeddings (-35%), 2.9% plus contextual BM25 (-49%), 1.9% plus a reranker over the top 150 (-67%). Tested on codebases, fiction, arXiv and science papers.
   - Stated one-time cost with prompt caching: $1.02 per million document tokens. Generic document summaries added to chunks gave "very limited gains"; summary-based indexing performed low.
   - Stated threshold: a knowledge base under 200,000 tokens (about 500 pages) can go whole into the prompt, with caching cutting latency over 2x and cost up to 90%; RAG is for larger bases.
   - Evidence: https://www.anthropic.com/research/contextual-retrieval (sections "Introducing Contextual Retrieval", "Reranking", the longer-prompt note)
   - Marks: vendor post; measured across 4 stated domains, headline charts on one embedding model and top-20; not retracted; not a preprint; no citation count; one source
   - Grade: medium
   - Compass part: [[RESEARCH-rag-fit-for-large-vaults]] concluded against a vector layer and names "BM25 over titles+tags+summaries" as the zero-dependency fallback; a grep of the vault for "contextual retrieval" returns no hits, so the post is uncited. The post's point that a chunk loses its referent without a context line parallels the vault rule that each index line copies the document's own `summary:` frontmatter (`plugin/skills/obsidian/writing-principles.md:33`). The 200,000-token whole-prompt threshold is a measured crossover the RAG-fit document does not state.

### claude-think-tool (2025-03-20, update 2025-12-15)

2. **The think tool is superseded by extended thinking in most cases (vendor's own update)** (confidence: high)
   - The update note says extended thinking has improved, gives similar room to reason with better integration, and is now recommended over a dedicated think tool in most cases. The original distinction: extended thinking runs before the response; a think tool runs mid-response on new information (tool results).
   - Original results (Claude 3.7 Sonnet, tau-bench airline pass^1): 0.332 baseline, 0.412 extended thinking, 0.404 think tool alone, 0.584 think plus an optimized prompt. Retail: 0.783 baseline, 0.770 extended thinking, 0.812 think alone. The text quotes 0.570 vs 0.370 as headline; the table says 0.584 vs 0.332 and the post does not explain the gap.
   - Evidence: https://www.anthropic.com/research/claude-think-tool (update note; "Performance on tau-Bench")
   - Marks: vendor post; measured; one benchmark pair; not retracted; not a preprint; no citation count; one source, and the update retires its own technique
   - Grade: medium
   - Compass part: model and effort selection is a central table (`plugin/cli/modelslib.py:72`, default effort per tier). A think-tool step has no Compass counterpart and the vendor now advises against adding one.

3. **Prompt examples beat access alone on hard policy domains; long guidance belongs in the system prompt, not the tool description** (confidence: medium)
   - Airline (complex policy): the tool gave a small gain alone and a large one with domain examples of how to reason. Retail (simpler policy): access alone was enough. SWE-bench: 30 samples with the tool vs 144 without, +1.6% average (Welch t = 6.71, p < .001).
   - No gain for non-sequential or parallel tool calls and for simple instruction following. The tool adds prompt length and output tokens.
   - Evidence: https://www.anthropic.com/research/claude-think-tool ("Implementation best practices", "When not to use")
   - Marks: vendor post; measured; small n on the SWE-bench arm; one source
   - Grade: low
   - Compass part: Compass puts procedure text in skill files read on demand, not in command descriptions; matches the placement, no change implied.

4. **pass^k defined with a consistency framing; per-task consistency falls much faster than pass^1** (confidence: high)
   - pass^k is the chance all k trials of a task succeed, averaged over tasks; pass@k counts a task solved if any trial succeeds. In the airline table pass^5 is 0.100 to 0.340 across arms against 0.332 to 0.584 at pass^1. The first pass found the same metric in the evals post.
   - Evidence: https://www.anthropic.com/research/claude-think-tool ("Performance on tau-Bench" tables)
   - Marks: vendor post; measured; convergence with demystifying-evals (first-pass finding 17)
   - Grade: medium
   - Compass part: [[RESEARCH-axis-6-build-success]] cites pass@k critiques; a grep of `.compass/research` for "pass^k" returns only the first-pass axis 1 document, and no Compass runner was found reporting consistency across repeated trials.

### swe-bench-sonnet (2025-01-06; older than the window)

5. **Minimal scaffold: one prompt, a Bash tool and a string-replace edit tool reached 49% on SWE-bench Verified (500 problems)** (confidence: high)
   - Design rule: give the model as much control as possible and keep the scaffolding minimal; the loop runs until the model stops or hits a 200k context. Same scaffold: Claude 3.5 Sonnet (old) 33%, Claude 3 Opus 22%, previous state of the art 45%.
   - "An agent is the model plus its scaffolding"; results vary a lot with scaffolding for the same model.
   - Evidence: https://www.anthropic.com/research/swe-bench-sonnet ("Background", "Achieving state-of-the-art")
   - Marks: vendor post; measured single score per model; not retracted; not a preprint; no citation count; convergence with harness-design and best-practices ("What you can stop doing")
   - Grade: medium
   - Compass part: the harness-complexity question behind first-pass candidate 1.

6. **Tool design lessons: absolute paths only, exact-single-match replace, bounded output, usage guidance inside the tool description** (confidence: high)
   - Relative paths broke after the model changed directory; requiring absolute paths fixed it and the model then used them "flawlessly" (the building-effective-agents appendix repeats this as poka-yoke). String replace was the most reliable edit method tried; it applies only on exactly one match and otherwise returns an error the model can act on. Long output is truncated and marked `<response clipped>`; the Bash description tells the model to avoid huge output and background long commands.
   - Evidence: https://www.anthropic.com/research/swe-bench-sonnet ("Lessons on tool design"); https://www.anthropic.com/research/building-effective-agents (Appendix 2)
   - Marks: vendor posts; qualitative; two posts agree; one author team
   - Grade: low
   - Compass part: `compass` CLI argument handling and error text. A grep of `plugin/skills` and `.claude/agents` for "absolute path" or "poka" finds one unrelated use (a transcript lookup in `plugin/skills/consolidate-memory/SKILL.md:25`); the CLI's argument normalisation was not audited.

7. **Failure modes named: hidden tests make the model believe it succeeded; wrong-level fixes; runs over 100k tokens; no image input** (confidence: medium)
   - Failures split between model behaviour (fix at the wrong level, "bandaid") and environment (install patches applied twice). Many successful runs took hundreds of turns and over 100k tokens.
   - Evidence: https://www.anthropic.com/research/swe-bench-sonnet ("Challenges")
   - Marks: vendor post; qualitative, no rates; one source
   - Grade: low
   - Compass part: the tester authors failing tests from the task spec before the build (methodology skill, "Testing mandate"), which makes acceptance tests visible to the builder; already covered.

### building-effective-agents (2024-12-19; older than the window)

8. **Five workflow patterns with stated fit conditions; evaluator-optimizer needs clear criteria and measurable refinement gains** (confidence: high)
   - Prompt chaining (fixed subtasks, programmatic gates between steps), routing (classify then specialise, for example easy questions to a small model), parallelization (sectioning, voting), orchestrator-workers (subtasks unpredictable, "as in coding"), evaluator-optimizer (clear criteria; human feedback measurably improves output; an LLM can give similar feedback).
   - Agents start from a user command, need ground truth from the environment each step, may pause at checkpoints, and stop at a maximum-iteration cap.
   - The page carries an update note: much of its tooling has changed since 2024 and it points to the Managed Agents post.
   - Evidence: https://www.anthropic.com/research/building-effective-agents ("Building blocks, workflows, and agents")
   - Marks: vendor post; asserted, examples not measured; not retracted; not a preprint; no citation count; convergence with the multi-agent and swe-bench posts
   - Grade: low
   - Compass part: Compass is a prompt chain with human gates (Vision to Validate) plus orchestrator-workers for builders and researchers; the `validator` and the 3-cycle fix loop are an evaluator-optimizer instance; model tiers in `plugin/cli/modelslib.py` act as a routing table. [[RESEARCH-rolling-wave-agent-planning]] already uses the simplest-solution framing.

9. **Frameworks hide prompts and responses; start with direct API calls; three principles: simplicity, transparency of planning steps, tool documentation and testing** (confidence: medium)
   - Wrong assumptions about what is under the hood are a common source of customer error. The team spent more time on tools than on the overall prompt.
   - Evidence: https://www.anthropic.com/research/building-effective-agents ("When and how to use frameworks", "Summary")
   - Marks: vendor post; asserted; one source
   - Grade: low
   - Compass part: no change implied; logs and files as the record is the existing rule in `.claude/rules/compass-pipeline.md`.

### claude-code-best-practices (now a documentation page)

The page https://code.claude.com/docs/en/best-practices was read end to end. It carries no benchmark numbers; hook and permission semantics are stated, not tested here. Source type: vendor documentation.

10. **Instructions come in two kinds, non-deterministic (prompt, CLAUDE.md, skills) and deterministic (hooks, deny rules, sandbox, Stop hook, CI); a rule with zero exceptions belongs in the second** (confidence: high)
    - "If you keep adding emphasis to a CLAUDE.md line and Claude still misses it, that's a sign the line belongs in a hook." The reverse holds: hooks for mere preferences should be deleted. Keep the enforced set small ("if you ever find yourself at forty of them, most are probably preferences"). The page's "what you can stop doing" table lists ALL CAPS emphasis as old advice that current models over-apply.
    - `prompt` and `agent` hooks ask another model and are not deterministic; real enforcement uses `command`, `http` or `mcp_tool` hooks, with `onFailure: "block"` when a crashed hook must stop the action.
    - Evidence: https://code.claude.com/docs/en/best-practices ("Deterministic and non-deterministic instructions", "Enforce the rules that can't have exceptions")
    - Marks: vendor documentation; asserted; one source; convergence with how-we-contain ("the deterministic boundary is what gets hit when everything probabilistic misses")
    - Grade: low
    - Compass part: `plugin/hooks/hooks.json` already makes the Data rule deterministic through `compass guard`, and capture runs on Stop. Each hook command "exits 0 when the CLI is not installed" (fail-open), and `onFailure: "block"` is not used. Skills and templates carry a few "CRITICAL"/"IMPORTANT" markers (grep counts: handoff skill 2, `obsidian/templates.md` 3).

11. **Stop hook with exit code 2 sends the model back to work; the host overrides after eight consecutive blocks unless a cap variable is raised** (confidence: high)
    - A Stop hook's stderr becomes the reason the model cannot finish; with no tool call between blocks, the eighth consecutive block is overridden. `/goal` is a separate-model check after every turn. `/code-review` runs in a fresh subagent that "never saw your conversation".
    - Evidence: https://code.claude.com/docs/en/best-practices ("Enforce the check with a Stop hook", "Give Claude a check to run")
    - Marks: vendor documentation; stated behavior, not tested here; one source
    - Grade: low
    - Compass part: `plugin/cli/commands/capture_check.py:68-71` and `:285` implement their own re-emit spacing (every 5 turns) and an age-gated abandon after a block, so loop risk is handled in Compass code, not by the host cap. The Stop hook is used for capture only, not as a done gate (run typecheck before ending).

12. **"Review against your spec ... skip style": a reviewer asked to find problems always finds something** (confidence: medium)
    - Recommended reviewer prompt: compare the diff to SPEC.md, check every requirement is implemented and listed edge cases have tests, "report gaps that affect correctness and skip style". Fixing every finding adds abstraction layers and tests for impossible cases. A reviewer with `tools: Read, Grep, Glob` is limited by the harness, not by prompt.
    - Evidence: https://code.claude.com/docs/en/best-practices ("Review against your spec", "Know what subagents cost")
    - Marks: vendor documentation; asserted; convergence with first-pass finding 7 (evaluator over-reporting)
    - Grade: low
    - Compass part: `validator` has `tools: Read, Grep, Glob, Bash` (`.claude/agents/validator.md:4`); `reviewer` consolidates research outputs and has Write/Edit (`.claude/agents/reviewer.md:4`). A grep of both for "style" finds no skip-style rule.

13. **Subagents cost tokens, can be slower than inline work, give parallelism or a fresh reviewer but not a smarter answer by default; Haiku for simple jobs** (confidence: high)
    - A fresh subagent must regather context; same or smaller model by default; ask for short summaries back; `/usage` shows share per subagent type. The "stop doing" table drops "delegate to a subagent for a better answer" and "use subagents to protect your context window", since most current models have a 1M-token window and compaction is automatic.
    - Evidence: https://code.claude.com/docs/en/best-practices ("Know what subagents cost", "What you can stop doing")
    - Marks: vendor documentation; asserted; convergence with the multi-agent post's token multiples (first-pass finding 12)
    - Grade: medium
    - Compass part: the methodology skill justifies debug isolation by "Preserves the main context window"; the page keeps parallelism, noisy-output isolation and fresh review as the reasons. Per-agent model is a resolvable table (`compass models`).

14. **Spec flow the page recommends: interview into SPEC.md then build from a fresh session; CLAUDE.md only for what the model cannot find in the repo; `paths:` scoping for rules** (confidence: high)
    - Two-question test before writing a line: could it find this by reading the code, would it actually go and look; if both yes, leave it out. CLAUDE.md recommended under 200 lines; `/doctor prompt-audit` flags instructions written for older models, dead file references and contradictions. Skills load name and description each session and the body on demand.
    - Evidence: https://code.claude.com/docs/en/best-practices ("Brainstorm with Claude first", "Keep CLAUDE.md short", "Scope rules to one part of the codebase")
    - Marks: vendor documentation; asserted; convergence with the skills post (progressive disclosure)
    - Grade: medium
    - Compass part: the spec flow already interviews one question at a time and builds from a vault spec. `.claude/rules/compass-pipeline.md` and `wikilinks.md` declare `paths: "**"` in frontmatter, so path scoping exists and is unused for them. No command audits Compass's model-facing text for model-staleness or dead references.

15. **Unattended-run checklist and worktree mechanics** (confidence: high)
    - Five questions before leaving a run: what done looks like, can it check its own work, what may it touch, what stops it (`--max-turns`, `--max-budget-usd`), who signs off. Worktrees lack gitignored files; a `.worktreeinclude` file at the repo root lists files copied into every new worktree. Auto mode in `-p` denies the single action and continues, so repeated blocks do not pause a non-interactive run.
    - Evidence: https://code.claude.com/docs/en/best-practices ("Let Claude run without you", "Run sessions in parallel")
    - Marks: vendor documentation; stated behavior; one source
    - Grade: low
    - Compass part: `plugin/cli/looprunner.py:753-754` already passes `--max-turns` and `--max-budget-usd`, with a per-run budget at `:665`. A grep for "worktreeinclude" across `plugin/` and `.claude/` returns nothing; whether builders need gitignored vault files such as `.compass/tmp/` in their worktrees was not checked.

### how-we-contain-claude (2026-05-25)

16. **Contain first, steer second: the deterministic boundary decides outcomes when probabilistic defenses miss; match isolation strength to how well the user can oversee the agent** (confidence: high)
    - Defense = environment (sandbox, VM, egress, filesystem), model (prompts, classifiers, training), external content. Stated numbers: users approved about 93% of prompts; an OS sandbox cut prompts 84%; auto mode lets through about 17% of overeager actions and blocks about 0.4% of harmless commands (footnote); Opus 4.7 prompt-injection success about 0.1% single attempt and 5-6% after 100 adaptive attempts.
    - Two cases the model layer could not catch: a phished user pasting a credential-exfiltration prompt (24 of 25 runs complied), and exfiltration through an allowed domain using an attacker's API key. Only egress blocks and filesystem boundaries stop them. "An allowlist is really a capability grant."
    - Evidence: https://www.anthropic.com/research/how-we-contain-claude ("Three types of risk", "Pattern 2", "Pattern 3", "Summary: principles")
    - Marks: vendor post, security-team authors; measured counts for the red-team case (n=25) and benchmark rates; one source; convergence with the sandboxing post (84%) and first-pass finding 19 (93%, 0.4%, 17%)
    - Grade: medium
    - Compass part: `compass guard` filters subagent tool calls that destroy information; it is a tool-call filter, not an OS or network boundary. No Compass skill, rule or agent recommends enabling the host sandbox (grep of `plugin/skills`, `.claude/rules`, `.claude/agents`; one unrelated hit at `plugin/cli/hostlib.py:335`).

17. **Config read before the trust prompt ran attacker hooks; the fix was parsing project config only after consent** (confidence: high)
    - Three reported vulnerabilities involved code running before the user accepted the trust dialog, for example a cloned repository's project settings hook executing at startup. Advice: treat project-open, config-load and localhost listeners like inbound internet requests.
    - Evidence: https://www.anthropic.com/research/how-we-contain-claude ("Risk missed: everything before the trust dialog")
    - Marks: vendor post; reported incidents, count only; one source
    - Grade: medium
    - Compass part: Compass installs hooks and a CLI into projects and a SessionStart `self-update` that "refreshes the install from its recorded source" (`plugin/hooks/hooks.json`, SessionStart entry). Whether self-update runs only after trust acceptance is decided by the host's workspace trust, not by Compass; not verified.

18. **Persistent memory is an injection persistence channel; sub-agent output trusted above raw tool results opens a new route** (confidence: medium)
    - "More context now survives across sessions: product memory, CLAUDE.md files, mounted workspaces." An injection there reloads every start; the post expects session-start classifiers to become common. Sub-agents can pass up structured facts instead of raw text, but trusting their output more because it came "from us" creates an injection route. Network-tool results should be inspected live, since afterwards the log shows only an authorized call. The post lists these as open problems.
    - Evidence: https://www.anthropic.com/research/how-we-contain-claude ("Looking ahead")
    - Marks: vendor post; asserted forecast; one source
    - Grade: low
    - Compass part: the vault is persistent memory re-read at every session start (hot path), and the capture worker turns subagent final reports into lessons (`.compass/tmp/subagent-captures/`, per the SubagentStop description in `plugin/hooks/hooks.json`). A grep of `plugin/skills`, `plugin/cli/capturelib.py`, `plugin/cli/commands/capture_worker.py` and `.claude/agents` for "injection" or "untrusted" finds only the fuzzing line at `plugin/skills/test-design/SKILL.md:74`; no content check on vault writes or captures was found.

19. **Custom components were the weak layer; credentials stay outside the isolation boundary; EDR cannot see inside a VM** (confidence: medium)
    - Hypervisor, seccomp and gVisor held; the custom proxy and allowlist code failed. Credentials in the host keychain never enter the VM; the VM gets a scoped per-session token revocable separately. Mounts can be read-only, read-write or read-write-no-delete; symlinks must be resolved before path validation.
    - Evidence: https://www.anthropic.com/research/how-we-contain-claude ("Pattern 3", "Summary: principles")
    - Marks: vendor post; incident accounts; one source
    - Grade: low
    - Compass part: `compass guard` path matching on Write and Edit is a custom component of the kind the post flags; whether it resolves symlinks before matching was not checked.

### claude-code-sandboxing (2025-10-20)

20. **Filesystem and network isolation are both required; 84% fewer permission prompts internally** (confidence: high)
    - Without network isolation a compromised agent can exfiltrate files such as SSH keys; without filesystem isolation it can escape the sandbox and reach the network. Linux bubblewrap and macOS seatbelt enforce rules on every subprocess a command spawns. Network goes through a proxy outside the sandbox over a Unix domain socket; the proxy limits domains and asks for new ones. Open-source runtime in research preview; start with `/sandbox`.
    - Evidence: https://www.anthropic.com/research/claude-code-sandboxing ("Sandboxing: A Safer and More Autonomous Approach")
    - Marks: vendor post; one measured number (84%, internal use, no n); research preview; one source; the same number appears in how-we-contain-claude
    - Grade: low
    - Compass part: the guard blocks information-destroying calls only; network and credential exfiltration are outside its scope.

21. **Web sessions keep git credentials outside the sandbox behind a git proxy that checks branch and repository** (confidence: medium)
    - The sandbox git client logs in to a proxy with a scoped credential; the proxy verifies the credential and the action (pushes only to the configured branch), then adds the real token.
    - Evidence: https://www.anthropic.com/research/claude-code-sandboxing ("Claude Code on the Web")
    - Marks: vendor post; design description, no measures; one source
    - Grade: low
    - Compass part: `.claude/rules/compass-pipeline.md` makes outward-facing actions human gates by rule text; the PreToolUse guard in `plugin/hooks/hooks.json` matches information destruction only, and no deterministic `git push` restriction was found there.

## Contradictions

- Finding 2 (think tool superseded by extended thinking) vs finding 3 (add domain examples to a think tool): the second is the 2025 guidance, and the post's update retires it for most cases. The post does not say whether "examples beat access" transfers to extended thinking.
- Finding 2: the think-tool post's headline pass^1 (0.570 vs 0.370) disagrees with its own table (0.584 vs 0.332); unexplained.
- Finding 10 (plain wording is followed; emphasis is over-applied) vs first-pass finding 9 (strongly worded "It is unacceptable to remove or edit tests" in the harness post): different model generations, and the harness rule guards a shared artifact. Neither source reconciles them.
- Finding 13 (protecting the context window is stale advice) vs the methodology skill's debug-isolation reason ("Preserves the main context window"): the page keeps parallelism, noisy-output isolation and fresh review as reasons.
- Finding 18 (sub-agent output as an injection route) and the first-pass multi-agent finding (subagents return light file references to cut telephone loss) address different problems, fidelity vs injection, and do not conflict in method.

## Candidate changes for Compass

Ranked by architectural impact. These add to the eight in [[RESEARCH-axis-1-anthropic-engineering]]; none duplicates them.

1. **Treat the vault as an injection surface: screen what enters persistent memory and what the capture worker ingests.** North stars: accuracy, perfect memory. Would change `plugin/cli/capturelib.py`, `capture_worker.py` and the `compass sync` write path with a deterministic check (for example flag instruction-like text, fetched content or encoded blobs in lessons and subagent captures) and add a provenance note for subagent-sourced notes. Not covered: no injection or untrusted-content handling in capture code. Findings 18, 16.
2. **Deterministic push and egress restriction for subagents and loops.** North star: accuracy. Would add a guard rule or settings template denying `git push` and unlisted network targets for subagents and the loop runner, and a setup-time recommendation to enable the host sandbox in strict mode. Partly covered: the guard denies information destruction only; push is a human gate by rule text. Findings 16, 20, 21.
3. **Audit model-facing text for staleness and emphasis, and move zero-exception rules into hooks.** North stars: accuracy, low token usage. Would add a `compass` check listing emphasis markers and rule lines that read as zero-exception policy, and `paths:` scoping for rule files that apply to one area. Pairs with first-pass candidate 1 (model-change re-baseline). Not covered. Findings 10, 14.
4. **Report consistency (pass^k) across repeated trials in `bench/` and the loop runner.** North star: accuracy. Would add k-trial pass^k beside pass@k in bench reports; the think-tool tables show pass^5 at 0.10 to 0.34 while pass^1 looks acceptable. Not covered. Findings 4, 5.
5. **Evaluate a Stop-hook done gate for builders and a fail-closed `onFailure: "block"` for the guard.** North star: accuracy. The page's example blocks a turn until typecheck passes, capped at eight consecutive blocks; Compass already has re-emit spacing and abandon for the capture Stop hook, and its hooks fail open when the CLI is missing, so a done gate and a fail-closed guard would be new behavior with stated host limits. Partly covered. Findings 10, 11.
6. **Record the vault-size crossover for retrieval work: under about 200,000 tokens load whole, above it lexical search plus a model-written context line.** North stars: near-zero cache misses, low token usage. Would add one measured threshold and the contextual-prefix idea to the RAG-fit conclusions (the `summary:` convention is already the context line). Partly covered by [[RESEARCH-rag-fit-for-large-vaults]], which does not cite this post. Finding 1.
7. **Add a correctness-only, skip-style scope line to validator and review prompts and test whether over-reporting drops.** North star: low token usage. One-line prompt change plus a measure; the claim is unmeasured documentation guidance. Not covered. Finding 12.
8. **Copy needed gitignored vault files into builder worktrees mechanically.** North star: accuracy. The host feature is `.worktreeinclude`; Compass has no equivalent. Whether builders need such files was not checked, so this is a question for the planner. Finding 15.

## Gaps

- The 29th post is identified (contextual-retrieval) by counting pages with Team = Engineering across the sitemap crawl (29 of 215 /research/ pages); this relies on each page's "Team" label and agrees with the engineering page's stated count of 29. A post filed under another label would be missed.
- Not read this pass and still open from the first pass: a-postmortem-of-three-recent-issues, eval-awareness-browsecomp, AI-resistant-technical-evaluations, building-strong-safety-evaluations, desktop-extensions, confidential-inference-trusted-vms.
- The best-practices page is current documentation, not the 2025-04-18 post the engineering page lists; the original post text was not retrievable and may differ.
- The docs page's Stop-hook cap (eight) and permission-mode semantics were not tested.
- `compass guard` symlink resolution and whether self-update waits for workspace trust were not checked in code.
- Coverage claims rest on keyword grep over `plugin/`, `.claude/`, `.compass/`; no hit means no keyword match.
- The think-tool and swe-bench posts predate the window (2025-03 and 2025-01); building-effective-agents is 2024-12; contextual-retrieval is 2024-09.
