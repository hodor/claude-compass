---
title: "Axis 5: Spec-driven and plan-first coding agent frameworks, and the evidence on specs, plans and tests"
type: research
status: complete
confidence: medium
area: methodology
tags: [spec-driven-development, frameworks, spec-kit, kiro, bmad, openspec, superpowers, tdd, ambiguity, context-files, prior-art]
created: 2026-11-21
updated: 2026-11-21
author: researcher
depends_on: ["[[RESEARCH-llm-research-for-compass]]", "[[RESEARCH-gsd-core-improvements-for-compass]]", "[[RESEARCH-evaluation-benchmarks]]"]
summary: "Nine spec-driven frameworks read from source, comparison table, and the empirical evidence on specs, plans, TDD and ambiguity; candidate Compass changes"
---

## Question

What do the spec-driven and plan-first coding-agent frameworks with traction in 2025-2026 do (pipeline, memory, context bounds, verification) that Compass does not, and what does the empirical literature say about whether specs, plans and test-first help coding agents?

## Methodology

Technology landscape / comparative evaluation (DESMET feature-analysis mode: documentation and source reading, no trials), plus a systematic-mapping pass over arXiv for the evidence half. It fits because the axis asks "what exists and how do the options differ" over a field with no controlled comparison. Frameworks were read from shallow clones of their repositories (command and skill files, not only READMEs), dated by last commit. GSD is covered in [[RESEARCH-gsd-core-improvements-for-compass]] and not repeated.

Grading: allowed. Grades are by source type (peer-reviewed, preprint, vendor doc, practitioner post, source code) and measured vs asserted. Marks per finding: evidence type, retraction status (none found for any cited item), preprint status, citation count (not retrieved; Semantic Scholar not queried, so "unknown"), convergence. All arXiv items below are preprints; none were checked for later peer review.

## Framework census (stars and pushes via GitHub API, 2026-11-21)

| Framework | Stars | Last push | Read from | Core pipeline | Memory model | Context bounding | Verification | Has, Compass lacks |
|---|---|---|---|---|---|---|---|---|
| GitHub spec-kit | 150.9k | 2026-11-20 | `templates/commands/*.md`, `spec-driven.md`, README | constitution, specify, clarify, plan, tasks, analyze, checklist, implement, converge | `specs/<feature>/` files + `memory/constitution.md`; no cross-session store | "Progressive disclosure" loading in each command; no hard cap | `analyze` (read-only cross-artifact consistency, constitution conflicts = CRITICAL), `converge` (code vs spec, appends tasks), plan-template Constitution Check gate | Ambiguity taxonomy scan with max 5 questions (`clarify`), `[NEEDS CLARIFICATION]` markers, post-implement convergence loop, extension/preset/bundle/catalog packaging |
| Kiro (AWS) | 4.5k (tracker repo only; product closed) | 2026-11-05 | docs pages kiro.dev/docs/specs, /correctness, /analyze-requirements | requirements (EARS), design, tasks; feature and bugfix specs | spec files + steering + hooks | Not stated | Requirements Analysis (contradictions, ambiguities, conflicting constraints, unstated assumptions, missing edge cases); correctness = property-based tests derived from EARS requirements, optional, IDE only; checkpoints and rewind | Property-based tests generated from requirements; wave execution from task dependency graph |
| BMAD-METHOD | 55.6k | 2026-11-22 | `skills/method/bmad-build/*`, README | v7 preview: clarify-and-route, plan, implement, review, present; oneshot vs full route by risk | Plan file with frontmatter state machine; persistent `project-context` block in AGENTS.md; ticket tree; retrospective skill | Plan size standard 900-1600 tokens "above 1600 risks context-rot"; step files loaded just-in-time, one at a time | Review lenses as parallel subagents (edge-case hunter, verification-gap) with a triage log (false / maybe-false / low-high verdicts per finding); frozen `<frozen-after-approval>` intent block | Verification-gap lens ("name the regression a missing test would catch"); verdict-per-finding triage log; risk-routed oneshot vs full; token-sized plans |
| Agent OS | 5.6k | 2026-10-07 | README, `commands/agent-os/shape-spec.md` | discover-standards, inject-standards, shape-spec (plan mode), plan-product | Standards extracted from the codebase into docs, indexed | Inject only relevant standards per task | None mechanical read | Standards discovery from code, then selective injection |
| OpenSpec | 75.4k | 2026-11-20 | README, `docs/concepts.md`, `docs/cli.md`, `schemas/spec-driven/schema.yaml` | explore, propose (proposal, spec deltas, design, tasks), apply, archive | `openspec/specs/` = current truth; `openspec/changes/<id>/` = proposals; archive merges deltas into specs | `openspec show --no-scenarios` filtered read before full read; one folder per change | `openspec validate [--strict]`, delta check that MODIFIED requirements exist in main specs, `--archived` pre-commit check for unticked tasks | Delta-spec merge model (specs always describe current behavior), custom schema YAML for the workflow, cross-repo "stores" (beta) |
| Superpowers | 323k (obra/superpowers) | 2026-11-03 | `skills/*/SKILL.md` | brainstorm, spec in chunks, plan, subagent-driven development, review, finish | Plan workspace with `progress.md` ledger of rulings and completions | Fresh implementer subagent per task, built from a constructed brief, never session history | Iron-law TDD (delete code written before the test), per-task spec-compliance and quality review, final whole-branch review, "evidence before claims" gate; skills themselves tested with pressure scenarios | Pressure-scenario testing of the skills themselves (RED/GREEN for prompts); "Ruling" ledger entries instead of stopping |
| Conductor (Google-affiliated extension) | 3.8k | 2026-09-01 | README, skill list | context, new track (spec + plan), implement, review, revert | `conductor/` dir with `index.md`, tracks registry | Reads `index.md` then linked files only | Phase-checkpoint manual-verification meta-task per phase; `conductor-revert` reverts a logical unit via git reconciliation | Logical-unit revert (track/phase/task) |
| SuperClaude | 24.0k | 2026-09-27 | README, `pm_agent/confidence.py` | persona and command pack; PM agent | ReflexionMemory (error learning), PM-agent documentation | Claims 30-50% token saving via MCP (asserted) | `ConfidenceChecker`: weighted 5-check pre-implementation score (duplicate 25, architecture 25, docs 20, OSS reference 15, root cause 15); >=0.9 proceed, 0.7-0.89 ask, <0.7 stop | Numeric pre-implementation confidence gate |
| Task Master | 28.5k | 2026-04-28 | README (docs site not read) | PRD, parse to tasks, complexity analysis, expand, loop | `.taskmaster/` JSON tasks, tags as workstreams | Tasks fetched one at a time over MCP | Not read | PRD-to-task-graph generation with complexity scoring; separate research model |
| Ruflo (ex claude-flow) | 82.2k | 2026-11-21 | README only | swarm orchestration, not a spec pipeline | HNSW-indexed AgentDB vector memory | Not read | README claims only (marketing); `verification/` dir not read | Vector memory, multi-agent consensus topologies (neither spec-driven) |
| Tessl | proprietary; tile repo 59 stars | 2026-03-30 | web search results only (docs.tessl.io returned 404) | spec-first with registry of library "tiles" | `.spec.md` files in repo, tiles installed into `.tessl/` | Not read | Not read | Versioned library-knowledge packages (tiles) against API hallucination |
| Others seen, not read | cc-sdd 3.8k, ccpm 8.5k, Backlog.md 7.5k, spec-kitty 1.7k, moai-adk 1.3k, haft 1.4k, Aegis 1.5k, ThinkRail 8.4k, google/elephant-goldfish-model 21.9k | - | metadata only | - | - | - | - | not read |

google/elephant-goldfish-model (EGM) was cloned and its README read: a spec is drafted by a context-holding agent and reviewed by "goldfish" reviewers that see only the document and its referenced sources, without the conversation; includes a `drift-report` skill comparing design docs with live code. Not placed in the table above for that reason; see finding 9.

## Findings

### A. Frameworks

1. **Convergent core: spec, plan, tasks, implement, with human gates.** spec-kit, Kiro, OpenSpec, BMAD, Conductor, Superpowers, EGM and Agent OS all sequence intent capture before code, with markdown artifacts in-repo as the memory. Compass's Vision > Spec > Research > Plan > Build > Validate is the same family. (confidence: high)
   - `templates/commands/` in spec-kit lists constitution, specify, clarify, plan, tasks, analyze, checklist, implement, converge (cloned 2026-11-21).
   - https://kiro.dev/docs/specs/ (requirements, design, tasks).
   - Marks: source code and vendor docs, no retraction, not a paper, citations n/a, convergence 8 frameworks.
   - Grade: asserted by authors, not measured. Touches: pipeline overall.

2. **spec-kit `clarify`: structured ambiguity scan before planning.** Scans the spec against a taxonomy, marks each category Clear/Partial/Missing, asks at most 5 targeted questions, writes answers back into the spec. `spec-driven.md` also mandates `[NEEDS CLARIFICATION: ...]` markers so the model cannot silently guess (e.g. auth method). (confidence: high)
   - `templates/commands/clarify.md` lines 53-80; `spec-driven.md:182-200`.
   - Marks: source code, no retraction, n/a, n/a, convergence with Kiro Requirements Analysis (finding 3) and BMAD "Clarify" step.
   - Grade: vendor, asserted (no ablation). Touches: `spec` skill. Compass grep of `plugin/` for "NEEDS CLARIFICATION" and "clarif" returns nothing; `spec` is one-question-at-a-time but has no coverage taxonomy.

3. **Kiro Requirements Analysis: whole-set review of requirements.** Checks logical inconsistencies, ambiguities ("fast"), conflicting constraints, unstated assumptions, missing edge cases; runs between requirements and design; clarifying questions offer pickable fixes and update `requirements.md`. (confidence: medium)
   - https://kiro.dev/docs/specs/analyze-requirements/ (fetched summary; page text not read raw).
   - Marks: vendor doc, no retraction, n/a, n/a, convergence with finding 2.
   - Grade: vendor, asserted. Touches: `spec`, `reviewer`.

4. **Kiro correctness: property-based tests derived from EARS requirements.** Properties are extracted at design time, run at task execution, shrink failing inputs, are optional, IDE only, and the page says "not formal verification". (confidence: medium)
   - https://kiro.dev/docs/specs/correctness/ (page last updated 2026-08-04 per fetch).
   - Marks: vendor doc, no retraction, n/a, n/a, single source.
   - Grade: vendor, asserted. Touches: `test-design` skill, `tester` pre-build station. Compass's testing mandate names defect-class admission and `compass test-smells`; property-based generation is not mentioned (grep of `plugin/skills` for "property-based" found only test fixtures).

5. **spec-kit `analyze` and `converge`: read-only consistency check, then append-only gap closure.** `analyze` is strictly read-only across spec/plan/tasks, constitution violations auto-CRITICAL. `converge` runs after implement, assesses code against spec/plan/tasks, appends unbuilt work as new tasks, leaves `tasks.md` byte-for-byte unchanged when clean; repeat implement+converge until `Converged`. (confidence: high)
   - `templates/commands/analyze.md:44-60`, `converge.md:45-70`; README SDD section.
   - Marks: source code, no retraction, n/a, n/a, single source for the converge loop.
   - Grade: vendor, asserted. Touches: `validator`, `plan`. Compass has `compass coverage` (decision-to-task, SPEC-007) and the validator's plan-vs-diff check; a code-vs-spec requirement-level loop that re-opens tasks is not in `plugin/`.

6. **OpenSpec delta specs: specs always describe current behavior.** Changes live in `changes/<id>/` as ADDED/MODIFIED/REMOVED requirement deltas with WHEN/THEN scenarios; on archive they merge into `specs/`. `openspec validate` rejects a change with zero deltas unless `skip_specs: true` and checks that MODIFIED requirements exist in the target spec. The workflow itself is a YAML schema (`schemas/spec-driven/schema.yaml`) users can fork. (confidence: high)
   - `docs/concepts.md`, `docs/cli.md:578-608`, `schemas/spec-driven/schema.yaml`.
   - Marks: source code, no retraction, n/a, n/a, single source.
   - Grade: vendor, asserted. Touches: spec lifecycle. Compass specs describe problem and need, not behavior, and status moves draft to archived; there is no delta-merge.

7. **BMAD v7 `bmad-build`: right-sized, token-bounded plans and triaged review.** Routes oneshot vs full by risk; plan target 900-1600 tokens ("above 1600 risks context-rot"); content inside `<frozen-after-approval>` is read-only to the implementer; step files are loaded one at a time. Review runs lenses as parallel subagents; the main agent verifies each finding and writes one verdict (false, maybe-false, low, medium, high) into a triage log, ignoring severity the reviewer assigned. (confidence: high)
   - `skills/method/bmad-build/workflow.md` (Scope Standard), `step-04-review.md`, `plan-template.md`, `review-prompts/verification-gap.md`.
   - Marks: source code, no retraction, n/a, n/a, convergence with Compass rolling-wave sizing.
   - Grade: vendor, asserted; the 900-1600 figure is not backed by a cited experiment in the files read. Touches: `plan` task sizing, `reviewer`, `validator`. Compass has a sizing log and rolling waves; no token-budgeted plan target found in `plugin/skills/plan/SKILL.md` (not exhaustively grepped).

8. **BMAD verification-gap lens: a missing-test finding must name the regression it would catch.** Gap shapes: regression, missing-adoption, broken-verification, stale-verification; skips static text, prompts and config; "drop any finding you cannot ground". (confidence: high)
   - `skills/method/bmad-build/review-prompts/verification-gap.md:1-40`.
   - Marks: source code, no retraction, n/a, n/a, converges with Compass's own "name the defect class" admission bar in the methodology skill.
   - Grade: vendor, asserted. Touches: `test-design`, `validator`.

9. **EGM and Superpowers separate drafter context from reviewer context.** EGM's reviewers see the document and sources "without the earlier conversation"; Superpowers builds each subagent's brief from scratch and runs a spec-compliance and quality review per task plus a whole-branch review. EGM adds `drift-report`: compare design docs with live code and report divergence for the human to resolve. (confidence: medium)
   - EGM `README.md` "How it works" table; Superpowers `skills/subagent-driven-development/SKILL.md:1-30`.
   - Marks: source code, no retraction, n/a, n/a, convergence with Compass's fresh-eyes document check (found in `plugin/skills/obsidian/writing-principles.md` and the compass-pipeline rule).
   - Grade: vendor/practitioner, asserted. Touches: `reviewer`, `vault-health`. Compass already uses a fresh-eyes sub-agent for documents; a doc-vs-code drift report command was not found in `plugin/`.

10. **Superpowers: "ruling, not stall" and skills tested by pressure scenarios.** The executing agent does not pause between tasks; conflicts are decided and written to a ledger as `Ruling: what, why, cost if wrong`, with four stop conditions (irreversible, security, outside-worktree side effect, plan so broken every path is a guess). Separately, new skills are validated RED/GREEN: run a pressure scenario with the subagent without the skill, record its rationalizations, write the skill, re-run (`writing-skills`). TDD skill: no production code without a failing test; code written first is deleted. (confidence: high)
    - `skills/subagent-driven-development/SKILL.md:15-35`, `skills/writing-skills/SKILL.md:14-43`, `skills/test-driven-development/SKILL.md:20-40`.
    - Marks: source code, no retraction, n/a, n/a, single source.
    - Grade: practitioner, asserted. Touches: `build`/autopilot ledger, skill authoring. Compass's "No Stalls" rule matches the first; the pressure-scenario skill test has no counterpart found (Compass `compass-pipeline` rules do not mention testing skills).

11. **SuperClaude `ConfidenceChecker`: numeric pre-implementation gate.** Five weighted checks (no duplicate implementation 25, architecture compliance 25, docs verified 20, OSS reference 15, root cause 15); at least 0.9 proceed, 0.7 to 0.89 present options, below 0.7 stop. Claims 100-200 token cost and "25-250x" savings (asserted, no measurement shown). (confidence: medium)
    - `src/superclaude/pm_agent/confidence.py:1-60`.
    - Marks: source code; savings figure unmeasured; single source.
    - Grade: practitioner, asserted. Touches: `builder` step 1. Compass's builder has a scope check but no numeric gate was found.

12. **Conductor: phase checkpoints and logical revert.** The planner appends a manual-verification meta-task to each phase when the project workflow defines a verification protocol; `conductor-revert` maps a track, phase or task to its commits and reverts the logical unit. (confidence: medium)
    - `skills/conductor-new-track/SKILL.md:105`, `skills/conductor-revert/SKILL.md:70-113` (grep lines only).
    - Marks: source code, no retraction, n/a, n/a, single source.
    - Grade: vendor, asserted. Touches: `build` merge-back, rollback.

13. **Tooling in the category is moving to extension/skill packaging with lifecycle hooks.** spec-kit 1.x ships extensions, presets, bundles, workflows, workflow overlays, catalogs and `before_<command>` hooks (`.specify/extensions.yml`, mandatory vs optional); BMAD v7 and Superpowers install via the open `skills` CLI across 15+ hosts; OpenSpec supports about 40 host tool IDs. (confidence: high)
    - spec-kit README "Capabilities" table; BMAD README install section; OpenSpec `docs/cli.md:117`.
    - Marks: source code, convergence 3 frameworks.
    - Grade: vendor, asserted. Touches: multi-host support ([[SPEC-006-multi-host-agent-cli-support]]), `/compass:update`.

14. **spec-kit's "constitution" is a gate source, not a memory tier.** `memory/constitution.md` holds project principles; the plan template has a "Constitution Check: GATE" before research and again after design; violations need written justification in a Complexity table; `analyze` treats conflicts as CRITICAL. Nine "articles" (library-first, test-first, simplicity, anti-abstraction, integration-first) are the shipped example. (confidence: high)
    - `templates/plan-template.md:39-43,108`; `spec-driven.md:278-362`.
    - Marks: source code, convergence with Compass rules files and ADRs.
    - Grade: vendor, asserted. Touches: `compass-pipeline` rule, planner. Compass records durable constraints in ADRs and rule files, with decision-coverage tracing (SPEC-007) rather than a per-plan gate.

### B. Empirical evidence

15. **Repository context files did not improve success and cost over 20% more.** On SWE-bench tasks with generated context files and on a new set of issues from repos with developer-written files, success was not generally better; instructions were followed but repository overviews were not helpful; the authors conclude context files help for non-standard practices only. (confidence: high on the result, medium on transfer to a vault)
    - arXiv:2602.11988v3 abstract (Feb 2026).
    - Marks: preprint; no retraction found; citation count unknown; convergence with 2601.20404 (efficiency study, abstract not read) and 2607.27250 (two-agent ablation, abstract not read).
    - Grade: preprint, measured. Touches: the hot path (`index.md`, `active.md`, lessons index) is the same kind of always-loaded file.

16. **Stale instruction files cost extra tool calls and nobody repairs them.** 732 trajectories, 22 maintenance tasks, three versions per instruction (stale, corrected, removed): agents followed stale guidance when relevant, a stale test command added about two tool calls (one third more), and none repaired the file. (confidence: medium; effect seen in one of three cases)
    - arXiv:2611.09802v1 abstract (Nov 2026).
    - Marks: preprint, no retraction, citations unknown, single source.
    - Grade: preprint, measured. Touches: `index.md`/`active.md` staleness; `doctor` and `vault-health`.

17. **Practitioners report more reliable agent behavior from SDD at higher planning and review cost.** Thematic analysis of Reddit, 21 interviews (8 tool makers) and 266 repos from a 470,795-file spec corpus (SpecMine): specs mostly capture intent but often include implementation detail; SDD used selectively and mainly for new features; spec-code checks happen mainly at completion, not over time. Evidence from tool vendors is noted by the authors as the field's main source. (confidence: medium)
    - arXiv:2608.25202v5 abstract (Aug 2026).
    - Marks: preprint, no retraction, citations unknown, qualitative.
    - Grade: preprint, qualitative (reported, not outcome-measured). Touches: spec stage; the "spec describes the problem, not the solution" rule is contradicted by observed practice (see Contradictions).

18. **Context-grounding hooks at each SDD phase gave a small measured gain.** Spec Kit Agents (PM + developer roles) added read-only probing hooks that ground Specify, Plan, Tasks and Implement in repository evidence and validation hooks that check artifacts against the environment: +0.15 on a 1-5 LLM-judge composite (+3.0 percent of scale, Wilcoxon p<0.05), 99.7-100 percent repo test compatibility, 128 runs, 32 features, 5 repos; also evaluated on SWE-bench Lite (result truncated in the abstract read). (confidence: medium)
    - arXiv:2604.05278v1 abstract (Apr 2026).
    - Marks: preprint; judge is an LLM; no retraction; single source.
    - Grade: preprint, measured with LLM judge. Touches: `planner`, `pattern-finder` before spec/plan stages.

19. **Per-line requirement citation trades determinism for verifiability.** Pre-registered comparison of traceSDD (per-line REQ-ID citations), Spec Kit (artifact-level traceability) and OpenSpec (post-hoc trace maps), 240 Sonnet 4.6 and 600 GLM-5-turbo implementations: uncited code is more deterministic across sessions (d about -0.7); only cited code allows automated hallucination detection (86.4% and 88.0% vs 0%, FPR 0%); traceSDD beats Spec Kit on determinism but not OpenSpec. (confidence: medium; determinism is lexical similarity, not correctness)
    - arXiv:2606.30689v1 abstract (Jun 2026).
    - Marks: preprint, no retraction, citations unknown, single source; pre-registered.
    - Grade: preprint, measured. Touches: [[SPEC-007-decision-coverage-tracing]] fixtures show Compass traces decisions to tasks, not code lines.

20. **Planning helps weaker models' accuracy and stronger models' cost, not their accuracy.** Component-level harness study across four models and four context budgets: planning "shifts from an accuracy scaffold for weaker models to a cost saver for stronger models, with little change in accuracy"; context management matters more as budget tightens, mostly by preventing overflow; rule-based elision before LLM summarization is the most efficient; making elided content recoverable "yields no accuracy gain". (confidence: medium)
    - arXiv:2609.20804v1 abstract (Sep 2026).
    - Marks: preprint, no retraction, citations unknown, single source.
    - Grade: preprint, measured. Touches: Compass hot-path cap and tier design; plan stage value on frontier models.

21. **Underspecified instructions degrade agents; asking helps only when models detect the gap.** Ambig-SWE (underspecified SWE-bench Verified variant) evaluates detect, ask, and use-the-answer; the abstract read says models struggle to distinguish well- from under-specified instructions (rest of the finding truncated in my read). Follow-ups on this axis exist: 2603.26233 (ask or assume), 2606.05920 (Asuka-Bench), 2607.02294 (action-boundary violations in underspecified DevOps instructions), 2603.05744 (CodeScout problem-statement enhancement); only titles read. (confidence: medium for Ambig-SWE, low for the follow-ups)
    - arXiv:2502.13069v3 abstract; other IDs from arXiv listing titles.
    - Marks: preprints, no retraction, citations unknown, convergence across 5 titled papers.
    - Grade: preprint, measured (Ambig-SWE); follow-ups not read. Touches: `spec` clarification step, `autopilot` ("never for ambiguous requirements").

22. **Tests as executable specs: benchmarks exist, controlled comparison against plain agents does not.** WebApp1K (1000 tasks, 19 models) uses tests as the prompt and finds instruction following and in-context learning matter more than general coding strength; TENET targets repository-level TDD with a test-harness subset selector, test-guided retrieval and test-feedback refinement; Mathews and Nagappan 2024 (2402.13521) tested supplying tests in the prompt. Abstracts only. (confidence: low to medium)
    - arXiv:2505.09027v1, 2509.24148v6, 2402.13521v2 (listing/abstract).
    - Marks: preprints, no retraction, citations unknown, convergence 3.
    - Grade: preprint, measured on code-generation benchmarks (not agentic multi-file workflows in general). Touches: tester pre-build station.

23. **No controlled study found of spec-driven vs plain agent on equal model, tools and tasks.** Searches of arXiv for "spec-driven development" returned vendor-adjacent case studies, a practice study (finding 17), a security-methodology paper (2602.02584, banking demo only), and framework-vs-framework comparisons (finding 19); [[RESEARCH-evaluation-benchmarks]] reached the same conclusion in June 2026. (confidence: medium; absence from limited searches)
    - Searches: arXiv API queries on 2026-11-21 (`all:"spec-driven development"`, TDD+LLM, AGENTS.md, underspecified+agents).
    - Marks: n/a, convergence with the earlier research doc.
    - Grade: absence-of-evidence, not graded as a claim. Touches: Compass evaluation plan Phase D.

## Contradictions

- spec-kit and Compass say specs hold requirements, not implementation (spec-kit's own template instruction); the practice study (finding 17) found practitioners include implementation detail and that this "may help agents while making specs prone to decay". Compass's rule "Specs capture the PROBLEM and the NEED, never the solution" sits on the cautious side of an open trade-off; the paper offers no outcome measure to settle it.
- Context files do not help on average (finding 15) while every framework in the table ships a standing context artifact (constitution, `project-context`, `conductor/index.md`, steering). The paper's own exception (non-standard practices help) is the only reconciliation offered.
- BMAD and Superpowers cap plan size or per-task context to avoid context rot; the harness study (finding 20) finds planning adds little accuracy on strong models. The frameworks assert the benefit; the study measures a cost benefit only.

## Gaps

- Not read: Task Master docs site, Ruflo verification claims and `verification/` dir, Tessl docs (docs.tessl.io returned 404; Tessl facts come from search-result summaries only), cc-sdd, ccpm, Backlog.md, spec-kitty, moai-adk, haft, Aegis, ThinkRail. Each is marked "not read" in the table.
- Kiro's EARS use, hooks and steering were not read; its product source is closed, so verification claims rest on vendor docs.
- All arXiv items were read at abstract level (some truncated), not full text; effect sizes beyond the abstract, benchmarks used in Spec Kit Agents on SWE-bench Lite, and the Ambig-SWE numbers are unverified. Citation counts and later peer-review status were not retrieved.
- Papers surfaced but unread: 2601.20404, 2607.27250, 2610.15884-era lists, 2609.00252 (SDD for agentic SE), 2610.07534 (EPIC), 2603.26233, 2606.05920, 2603.05744, 2608.06811 (planning with episodic memory), 2606.09090 (context rot in AI config artifacts).
- Compass-coverage claims ("not found in `plugin/`") rest on keyword greps of `plugin/skills` and `plugin/cli`, not a full read; `plugin/agents/` does not exist at that path (agents live in `.claude/agents/` per the brief) and was not grepped.

## Candidate changes for Compass (ranked by impact)

1. **Requirement ambiguity scan before plan approval.** Serves accuracy. Add to the `spec` skill (and optionally a `compass` check) a coverage taxonomy of Clear/Partial/Missing categories with a cap of about 5 targeted questions and an explicit marker for unresolved items, modeled on spec-kit `clarify` and Kiro Requirements Analysis; the evidence (finding 21) says agents do not self-detect underspecification. Already covered? Partially: `spec` asks one question at a time and `autopilot` forbids ambiguous work, but no taxonomy or marker exists (greps empty).
2. **Review verdicts and verification-gap lens in the reviewer/validator path.** Serves accuracy. Adopt BMAD's rule that a missing-test finding must name the regression it catches, and a per-finding verdict log that discards reviewer-assigned severity (`plugin/skills/test-design`, validator). Already covered? The "name the defect class" admission bar is in the methodology skill; the triage log is not found.
3. **Hot-path and index measurement against the context-file evidence.** Serves low token use and near-zero cache misses. Findings 15, 16 and 20 say always-loaded context can cost over 20% without raising success and goes stale; the evaluation plan could ablate the hot path (with vs without `index.md`/lessons index) on a benchmark from [[RESEARCH-evaluation-benchmarks]]. Already covered? The 5K cap and tiers exist; no ablation exists in the vault.
4. **Requirement-level converge loop after build.** Serves accuracy and memory. Borrow spec-kit `converge`: assess code against spec and plan, append unmet requirements as new tasks, no-op when clean; pairs with `compass coverage` (decisions to tasks) which does not look at code. Already covered? Validator checks plan vs diff; no append-only re-opening loop found.
5. **Phase grounding hooks.** Serves accuracy. Finding 18 measured a small gain from read-only repository probes before each stage; Compass's `pattern-finder` and `research-codebase` could be invoked automatically at spec/plan start. Already covered? Agents exist and are invoked by judgment, not by a hook.
6. **Property-based test generation in `test-design`.** Serves accuracy. Kiro derives properties from requirements (finding 4); the `test-design` admission bar could name property tests as an option for pure-function acceptance criteria. Already covered? Not found.
7. **Skill/prompt pressure testing (RED/GREEN for skills).** Serves accuracy. Superpowers validates skills by running baseline pressure scenarios (finding 10); fits Compass's seeded-defect probe idea for the test bar. Already covered? Seeded-defect probes exist for tests, not for skills.
8. **Numeric pre-build confidence gate.** Serves low token use (stop wrong-direction work early). SuperClaude's weights are asserted, not measured (finding 11); worth an experiment only. Already covered? No.

Not recommended for import (documented trade-off, no evidence of gain): packaging catalogs and presets (finding 13) beyond what [[SPEC-006-multi-host-agent-cli-support]] needs; vector-memory and swarm consensus (Ruflo, README claims only).
