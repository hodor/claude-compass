---
title: "Probe-Based Measurement as the Compaction-Survival KPI"
type: research
status: complete
confidence: medium
area: methodology
tags: [handoff, compaction, evaluation, probes, llm-judge, bench]
created: 2026-11-21
updated: 2026-11-21
git_branch: "master"
git_commit: "6faced1"
author: researcher
depends_on: ["[[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]]"]
summary: "How Factory's four-probe compression eval works and what it reports, which independent work scores summaries by QA and how reliable the judges are, and how Compass could run probes mechanically from its own transcripts with bench/overhead pieces"
---

## Research: Probe-Based Measurement as the KPI

From [[specs/pipeline/SPEC-025-stop-and-suggest-handoff-at-80-percent-context]] (need added 2026-11-21). Index: [[research/pipeline/compaction-survival/index]].

### Question
How does Factory's probe-based evaluation of context compression work, what do independent QA-based summary evaluations say about judge reliability, and how could Compass run probes on its own sessions with scripts first and a judge only where an answer is not checkable?

### Methodology
Grey-literature review for the vendor post and practitioner material (Factory is a vendor; formal literature is thin on agent-session compression probes), plus repository mining of `bench/` and `plugin/cli` for what Compass already has. Fits because the primary source is a vendor blog and the second half asks how an existing codebase behaves.

grading: allowed, so each finding carries a grade by source type and measured-versus-asserted.

### Findings

#### A. Factory's probe evaluation, read in full

1. **Four probe types, one of each per compression point** (confidence: high)
   After compression the agent is asked questions answerable only if removed-history details survived. Recall ("What was the original error message?"), Artifact ("Which files have we modified? Describe what changed in each."), Continuation ("What should we do next?"), Decision ("We discussed options for the Redis issue. What did we decide?"). Four probes, one per type, were created at every compression point.
   - https://factory.com/news/evaluating-compression (factory.ai redirects with a 308) - "Probe types" table
   - Marks: vendor post; not retracted; not preprint; citations n/a; convergence: 1 source for the design, matches [[research/llm-research/RESEARCH-axis-6-harness-engineering]] finding 14
   - Grade: vendor post, measured, self-favoring

2. **Probes are generated from the truncated history, aimed at specific facts, files or decisions; the post gives no generator** (confidence: medium)
   Each probe "was built from the truncated history and pointed at specific facts, files or decisions from before compression". Who or what wrote them (a model, a script) is not stated, and no probe list is published.
   - https://factory.com/news/evaluating-compression - probe generation paragraph (read through a summarizing fetch tool, not raw HTML)
   - Marks: vendor post; not retracted; not preprint; citations n/a; 1 source
   - Grade: vendor post, asserted (method unspecified)

3. **Grader: GPT-5.2 as judge, blind to method, six dimensions, 0 to 5 scale** (confidence: high)
   The judge sees the probe, the response, the compressed context and ground truth "when available", scores each criterion and explains. It is not told which method produced the answer. Dimensions (2 to 3 criteria each): accuracy, context awareness, artifact trail, continuity, completeness, instruction following. 0 = "Completely fails", 3 = "Adequately meets with minor issues", 5 = "Excellently meets with no issues". Dimension = weighted criteria average (weights not given); overall = unweighted mean of the six. Justification given for LLM judging: MT-Bench's "over 80% agreement with human preferences" (Zheng et al. 2023).
   - https://factory.com/news/evaluating-compression - "Grading" section
   - Marks: vendor post; not retracted; not preprint; citations n/a; the cited judge study is peer-reviewed (NeurIPS 2023 Datasets and Benchmarks, from memory, not re-fetched)
   - Grade: vendor post, measured, self-favoring

4. **Baselines: Factory's own method versus OpenAI `/responses/compact` and Anthropic SDK compression, same prefixes** (confidence: high)
   Factory: one persistent summary with fixed sections (intent, file changes, decisions, next steps), only the newly cut span summarized and merged ("anchored iterative summarization"). OpenAI: opaque endpoint output. Anthropic: structured summary, "typically 7-12k characters", whole summary rewritten each time. All ran on identical conversation prefixes; Factory's summaries came from production, the other two from sending the same prefixes to their APIs.
   - https://factory.com/news/evaluating-compression - "Methods compared"
   - Marks: vendor post; not retracted; not preprint; citations n/a; 1 source
   - Grade: vendor post, measured, self-favoring

5. **Sample: hundreds of compression points over 36,611 messages of real production sessions; session count not reported** (confidence: high)
   Opted-in users of a research program; task types listed: debugging, PR review, feature work, CI troubleshooting, data science, ML research, testing, bug fixes, refactoring. The number of probes, sessions and judge runs per method is not given.
   - https://factory.com/news/evaluating-compression - "Sample size"
   - Marks: vendor post; not retracted; not preprint; citations n/a; 1 source
   - Grade: vendor post, measured, self-favoring

6. **Reported numbers per method (0 to 5)** (confidence: high for the reading, low for what it proves)

   | Method | Overall | Accuracy | Context | Artifact | Complete | Continuity | Instruction |
   |---|---|---|---|---|---|---|---|
   | Factory | 3.70 | 4.04 | 4.01 | 2.45 | 4.44 | 3.80 | 4.99 |
   | Anthropic | 3.44 | 3.74 | 3.56 | 2.33 | 4.37 | 3.67 | 4.95 |
   | OpenAI | 3.35 | 3.43 | 3.64 | 2.19 | 4.37 | 3.77 | 4.92 |

   Worked example: one debugging session, 178 messages, 89,000 tokens; recall probe Factory 4.8, Anthropic 3.9, OpenAI 3.2; artifact probes Factory 3.6, OpenAI 2.8. Compression ratios were reported (OpenAI 99.3%); the fetched text of that passage was garbled, so the Anthropic and Factory ratios (about 98.7% and 98.6%) are uncertain. No absolute token counts.
   - https://factory.com/news/evaluating-compression - "Results", "Compression ratios"
   - Marks: vendor post; not retracted; not preprint; citations n/a; 1 source
   - Grade: vendor post, measured, self-favoring; gaps of 0.26 to 0.35 overall

7. **Authors' stated caveats: file tracking unsolved, ratio is the wrong goal, no significance tests** (confidence: high)
   Artifact trail is the weakest dimension for every method (2.19 to 2.45); the authors suggest separate file-state tracking. They say the goal is "tokens per task, not per request" because lost details get re-fetched. They claim the 0.26 to 0.35 gaps hold across task types and session lengths but report no significance test or confidence interval. One judge only.
   - https://factory.com/news/evaluating-compression - caveats
   - https://factory.com/news/compressing-context (Theo Luan, 2025-07-21) - states the same "minimize tokens per task, not per request" aim and lists what a summary must keep (user intent, step history, changed files and test results, breadcrumbs such as file paths and function names). It contains no probes, judge or scores (read in full).
   - Marks: vendor posts; not retracted; not preprint; citations n/a; convergence: two Factory posts agree on the aim
   - Grade: vendor post, measured (caveats), asserted (the cross-task claim)

8. **Reuse of the probe format has already been proposed in the vault, with a note on the conflict of interest** (confidence: high)
   [[research/llm-research/RESEARCH-axis-6-harness-engineering]] finding 14 records the same design and numbers and grades it "measured, vendor-run, self-favoring"; its candidate 4 proposes a `compass` check that asks a fresh agent the four probe types against a written handoff, scored by a judge. [[research/llm-research/REVIEW-llm-research-for-compass]] row C5 routes it to SPEC-025. Neither document has run it.
   - `.compass/research/llm-research/RESEARCH-axis-6-harness-engineering.md:127-132, 199`
   - `.compass/research/llm-research/REVIEW-llm-research-for-compass.md:209`
   - Marks: vault documents; convergence: consistent with finding 6 (copied from it)
   - Grade: not applicable (internal)

#### B. Independent and follow-on work scoring memory or summaries by QA

9. **LoCoMo and LongMemEval are QA benchmarks over long conversations; recent compression papers reuse them** (confidence: medium)
   Papers found by search (abstract level only unless noted): "The Sleeping Agent" (arXiv 2608.11775) scores gist compression on LoCoMo's 1,935 text questions and drops the 434 adversarial category because its rule (full marks for "no information available") rewards removing content. MemRefine (arXiv 2606.13177) scores compression on all 1,986 LoCoMo questions with token F1 and EM and 60 LongMemEval_S questions with a GPT-4o-mini judge. AgentMemBench (arXiv 2608.00009) compares five strategies including compression-based summarisation on 491 question turns, with an LLM-judge faithfulness score.
   - https://arxiv.org/pdf/2608.11775, https://arxiv.org/pdf/2606.13177, https://arxiv.org/pdf/2608.00009 - found in a web search summary; the papers were not opened
   - Marks: preprints (2026); not known retracted; citations not retrieved; convergence: 3 papers, one pattern
   - Grade: preprint, measured, not verified by this run

10. **MemoryAgentBench names four competencies; AMA-Bench scores agent trajectories, not chat** (confidence: medium)
    MemoryAgentBench (Hu, Wang, McAuley, arXiv 2507.05257, v4 2026-06-28): accurate retrieval, test-time learning, long-range understanding, selective forgetting; no tested method handles all four; the abstract does not state the question format. AMA-Bench (arXiv 2602.22769): expert-curated QA on real agent trajectories (states, actions, observations, tool outputs) and rule-based QA on synthetic ones; finds systems miss causal and objective information and lean on lossy similarity retrieval. AMA-Bench is the closest published analogue to a coding-agent session.
    - https://arxiv.org/abs/2507.05257 and https://arxiv.org/abs/2602.22769 - abstracts read
    - Marks: preprints; not retracted per abstract page; citations not retrieved; 2 sources
    - Grade: preprint, measured, abstract-level only

11. **ACON optimizes a compression guideline against task failures, not probes** (confidence: medium)
    ACON (arXiv 2510.00615, ICML 2026 per the abstract page) refines natural-language compression guidelines by failure analysis on AppWorld, OfficeBench and multi-objective QA; reports 26 to 54% lower peak tokens with task success kept or improved. It scores the downstream task, not probe answers.
    - https://arxiv.org/abs/2510.00615 - abstract read
    - Marks: peer-reviewed venue (ICML 2026, from the page); not retracted; not preprint now; citations not retrieved; 1 source
    - Grade: peer-reviewed, measured, abstract-level only
    - Compass part: an outcome-based alternative to probes; it measures the end state, probes measure the intermediate state.

12. **QA-judge reliability: small checks agree with humans, one audit finds a lenient judge accepts wrong answers, and question sets have label errors** (confidence: medium)
    Small human checks report high agreement: EverMemOS (25 pairs per benchmark, kappa above 0.89), EvalMem (120 pairs, 96.7%, kappa 0.91, ranking unchanged under a GPT-4o judge), Mnemis (60 LoCoMo samples, no misalignment). Against that, an audit attributed to Penfield Labs (2026), cited second-hand, reports a lenient GPT-4o judge on LoCoMo accepting up to 63% of intentionally wrong answers and about 6.4% of LoCoMo ground-truth answers wrong. arXiv 2604.27906 reports label errors in LongMemEval and ambiguous category labels, and one paper measured 2.6 to 3.3 accuracy points of noise between near-identical retrieval budgets.
    - Search summary of https://arxiv.org/pdf/2601.02163, https://arxiv.org/pdf/2609.22231, https://arxiv.org/pdf/2604.27906; the Penfield audit itself was not found or read
    - Marks: preprints; not retracted; citations not retrieved; convergence: judge-agreement papers agree with each other, the audit disagrees; the audit is unverified
    - Grade: preprint, measured, second-hand

13. **Compass already holds the general judge-bias evidence** (confidence: high)
    [[research/whole-overhead/RESEARCH-axis-6-build-success]] findings 10 to 16: a strong LLM judge agrees with humans about as often as humans agree with each other but with measurable biases (position, self-preference after fine-tuning, presentation cues); a reference answer cuts errors (GPT-4 marked wrong math answers correct 14 of 20 by default, 3 of 20 with a reference); a workspace-inspecting judge reached 88% to 90% against humans on DevAI. Its gap: judge calibration on this domain unmeasured; a hand-graded sample is the proposed fix.
    - `.compass/research/whole-overhead/RESEARCH-axis-6-build-success.md:117-168, 262`
    - `.compass/research/whole-overhead/REVIEW-whole-overhead.md:142` - "you hand-grade a few finished builds once" as judge calibration
    - Marks: vault documents citing arXiv:2306.05685 and others; convergence: several sources
    - Grade: secondary (vault), measured in the cited papers

#### C. What Compass has, and what it decided about measurement

14. **Transcript parsing for tool_use, compaction boundaries and compaction summaries already exists** (confidence: high)
    `plugin/cli/sessionslib.py` walks transcript records and extracts content blocks by type (`_blocks`, line 154) and counts commits from `Bash` `tool_use` blocks (line 226-234). `bench/overhead/token_profile.py` clears its modeled context at a `system` record with subtype `compact_boundary` and records an `isCompactSummary` user record as "compaction summary" (lines 283-296). `bench/overhead/attribute.py` names a compaction gap by the same boundary record (line 198). So the transcript carries both the pre-compaction tool_use history (ground truth) and the host's summary text.
    - `plugin/cli/sessionslib.py:154-162, 226-236`
    - `bench/overhead/token_profile.py:283-296`
    - `bench/overhead/attribute.py:198`
    - Marks: code read; convergence: 3 independent call sites
    - Grade: code, directly read

15. **bench/overhead already has an isolated headless session launcher, a blind judge with a read-only toolset, frozen ground truth, hand-grading calibration and a bootstrap comparison** (confidence: high)
    - `launch.py`: one isolated `claude -p` session, classified `done`, `failed` or `usage-limit` (`bench/overhead/README.md:11, 41-49`).
    - `judge.py`: judge runs in a copy stripped of `.git`, `.compass`, `.claude`, `CLAUDE.md` so it is blind to the arm (`judge.py:1-12, 73`), reads only (`JUDGE_TOOLS = "Read,Glob,Grep"`, line 38), scores each item `met` / `partly met` / `not met` with a reason naming a file or command output, and a reply not scoring every item exactly once raises `InvalidVerdict` (lines 45, 107, 202-228). Goal items carry an optional `command` run first, its output shown to the judge (`goals.py:1-8`; `judge.py:195-228`).
    - `goals.py`: the goal list is frozen before any build; a second write is refused (`goals.py:9-12`, `AlreadyFrozen`).
    - `grade.py`: hand-grading sheets compared with the judge, "Agreement with your grading" (`README.md:63-65`).
    - `compare.py`: 95% bootstrap interval over sessions, outcome guard that suppresses token comparison when outcomes differ (`README.md:57-61`).
    - `records.py`: per-session token counts with list-price weights (`README.md:51-55`), the unit a "fewer tokens than a model-written summary" claim needs.
    - Marks: code read; convergence: README and source agree
    - Grade: code, directly read
    - Not present: any code that builds a probe set from a transcript, or that asks a fresh session questions about a carried-forward state. `bench/README.md:27` says the two arm wrappers are not on disk. `bench/overhead/probe_initial_prompt.py:1-25` is an unrelated one-launch probe of `initialPrompt`, but it shows the repo's pattern for starting a sandbox session and reducing a subagent transcript to a small JSON.

16. **The vault decided: success signals must exist the same way with and without Compass, frozen before the run, judged by deterministic checks first and a workspace-inspecting judge second** (confidence: high)
    [[research/whole-overhead/REVIEW-whole-overhead]] item 13 and decision 4 (recommendation: only signals that exist in both arms; the validator verdict and plan checkboxes are recorded but not counted). A probe set built before compaction and graded by a script where possible fits that rule; a probe judge sharing the model family with the answerer is the open bias point (finding 13).
    - `.compass/research/whole-overhead/REVIEW-whole-overhead.md:99, 107, 117`
    - Marks: vault documents; convergence: matches [[research/whole-overhead/RESEARCH-axis-6-build-success]]
    - Grade: internal decision record

17. **The earlier benchmark research targets whole-task outcomes, not mid-session state** (confidence: medium)
    [[research/pipeline/RESEARCH-evaluation-benchmarks]] (2026-06-10) covers SWE-style and long-horizon benchmarks and how to A/B a methodology layer; a keyword search for probe, compaction, LoCoMo, LongMemEval, judge and bias in it returned no hits (grep, empty). Candidate C8 in the review routes LongMemEval and MemoryAgentBench question classes to SPEC-028, not SPEC-025.
    - `.compass/research/llm-research/REVIEW-llm-research-for-compass.md:212` (C8)
    - Marks: vault documents; 1 source
    - Grade: internal

#### D. A mechanical probe design, from what the sources and code allow (presented as options, not a pick)

18. **Which probes a script can ground and grade, per Factory's four types** (confidence: medium; design inference, not a documented result)
    - Artifact (files touched): ground truth is the set of paths in `Edit`, `Write` and similar `tool_use` blocks (and `Bash` git commands) before the boundary; grade by set precision and recall of paths the answerer names. No judge. This is also the dimension where Factory's three methods scored lowest (finding 7).
    - Continuation (next step): ground truth is the open `[ ]` task lines in `active.md` and the plan task in progress; grade by whether the answer names the task id. Script-gradable when ids exist; free-text next steps need a judge.
    - Decision: ground truth is a decision recorded in the transcript or vault (an ADR, a `D-NN`, a user message choosing between options); mechanical only when the decision has an id or a distinctive token; otherwise judge with the reference text supplied.
    - Recall (an error message, a number, a command): ground truth is a literal string in a `tool_result`; grade by exact or normalized substring match, no judge.
    - Marks: inference; supported by the structure in findings 14 and 3 (Factory itself supplies ground truth "when available")
    - Grade: n/a (inference)

19. **Three arms of "carried-forward state" the KPI compares, each a different text given to the fresh answerer** (confidence: medium; design inference)
    The SPEC-025 KPI names "as well as before it" and "fewer tokens than a model-written summary". The inputs a probe run can compare: (a) the host's compaction summary (the `isCompactSummary` record, `token_profile.py:296`); (b) a Compass handoff document; (c) a mechanically assembled state from transcript, vault and git (axis 3 of this research). The pre-compaction full context is the "before" reference arm. Tokens per arm are countable by the `records.py` weighting. The Factory post gives no "before" arm; all three of its methods are compressed.
    - Marks: inference; builds on Factory's design (finding 4) and Compass code (finding 15)
    - Grade: n/a (inference)

20. **Bias controls the sources document that a Compass probe run could carry** (confidence: medium)
    - Blind the answerer's output to arm (Factory; `judge.py` strips arm markers).
    - Put the reference answer in the judge prompt (MT-Bench: 14 of 20 wrong marked correct by default, 3 of 20 with reference; finding 13).
    - Prefer a judge from a different model family than the answerer where one exists (self-preference evidence, finding 13); not available in a Compass-only setup, so a rate against a hand-graded sample (`grade.py` pattern) is the alternative.
    - Keep adversarial "no information" questions out of the score, since that scoring rewards deleting content (finding 9).
    - Report an interval over sessions, not a single mean (`compare.py`; Factory reports none, finding 7).
    - Marks: techniques from sources 9, 12, 13 and code 15
    - Grade: n/a

### Contradictions
- Findings 6 and 7: Factory's ranking is reported as a consistent 0.26 to 0.35 lead, but the post gives no interval and uses one judge; its own method is the winner. [[research/llm-research/RESEARCH-axis-6-harness-engineering]] finding 14 grades it self-favoring.
- Finding 12: papers that check their own judge report kappa 0.89 to 0.91 on small samples; the Penfield audit (second-hand) reports a judge accepting up to 63% of deliberately wrong answers. The first tests ordinary outputs, the second adversarial ones. Not resolved.
- Finding 17 versus the review: [[research/llm-research/REVIEW-llm-research-for-compass]] row C5 sends probes to SPEC-025 and C8 sends memory question classes to SPEC-028; the earlier benchmark research has no probe content.

### Gaps
- Factory's probe questions, judge prompt, weights and per-probe-type scores are not published; whether probes were written by a model or a script is unknown (findings 2, 3).
- Factory's fetch was through a summarizing tool; the compression-ratio passage was garbled, so ratios are uncertain.
- LoCoMo, LongMemEval, MemoryAgentBench, AMA-Bench: only abstracts or search summaries read; no full-paper reading of their probe or judge protocols. Citation counts not retrieved for any paper. The Penfield audit was not located.
- No published study found that compares probe-answer quality against downstream task success for coding-agent compaction; ACON (finding 11) measures task success only.
- Whether a "no compaction" reference (the full prior context given to a fresh session) fits in a probe call at 80% usage was not checked.
- Hook behavior on compaction (what a PreCompact or PostCompact hook can inject) belongs to axis 1 and was not investigated here; a grep of `plugin/` (py, json, md) for `PreCompact`, `PostCompact`, `isCompactSummary`, `compact_boundary` returned no file; only `bench/overhead` reads the boundary and summary records.
- No pilot probe run was made; every number about Compass sessions is absent.

### Candidate changes for Compass

1. **A `bench/overhead` probe runner: transcript to probe set to fresh-session answers to script grade.** North star: accuracy (and perfect memory). Would add a repo-local module beside `judge.py`, not in `plugin/`: build artifact, recall and continuation probes from `tool_use` and `tool_result` blocks before a `compact_boundary` (findings 14, 18), start an isolated `launch.py` session given only the carried-forward text, grade by set and substring match. Covered: no (finding 15, "Not present"). Factory's ground truth is judge-graded; this version is script-graded where checkable.
2. **Three-arm comparison on the same probe set: host summary, handoff document, mechanical state, plus the full-context reference.** North star: low token usage. Would use `records.py` weights for tokens and `compare.py` bootstrap for the interval, so the SPEC-025 KPI ("as well as before it, at fewer tokens than a model-written summary") becomes a number per arm (finding 19). Covered: no.
3. **A judge only for decision and free-text continuation probes, with the reference answer in the prompt and a one-time hand-graded agreement sample.** North star: accuracy. Reuses the `judge.py` blindness and the `grade.py` calibration pattern (findings 15, 20, 13). Covered: partly (calibration exists for builds, not for probes).
4. **Report artifact-trail recall as its own headline number.** North star: perfect memory. It is the dimension all three vendor methods scored lowest (2.19 to 2.45, finding 7) and the only one fully script-gradable from tool_use entries; the spec already names "files touched" (finding 18). Covered: no.
5. **Pilot on a handful of recorded sessions that contain a compaction before building anything else.** North star: low token usage (cheap to learn probe yield first). `attribute.py` already identifies sessions with a `compact_boundary` (finding 14; the 42 compaction-containing mismatched transcripts in [[research/whole-overhead/RESEARCH-axis-1-session-records]] are a candidate pool). Covered: no.
