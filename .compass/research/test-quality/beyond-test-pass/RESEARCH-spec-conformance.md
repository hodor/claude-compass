---
title: "Research: Code Meets the Spec (requirement-level conformance and re-opening)"
type: research
status: complete
confidence: medium
tags: [testing, verification, spec-coverage, validator, converge, traceability]
area: testing
created: 2026-11-21
updated: 2026-11-21
author: researcher
summary: "spec-kit converge is the one shipped requirement-to-code compare with an append-as-task loop; Compass coverage traces decisions to tasks only; the builder charter is style-level; LLM-only conformance judging measured weak"
---

## Research: Code meets the spec (axis 3)

From [[SPEC-034-verification-beyond-test-pass]].

### Question
How can the delivered code be compared against each requirement of the spec it traces to, so an unmet requirement returns as open work?

### Methodology
Repository mining for how existing systems behave (spec-kit templates read from source, Compass `plugin/cli` read from the repo), plus a systematic mapping of 2025-2026 papers on LLM requirement checks. Chosen because most of the axis asks how an existing artifact behaves; the literature part only needs to find and classify what is known.

Grading: allowed. Each finding carries marks (evidence type, retraction, preprint, citations, convergence) and a grade. Citation counts were not retrieved unless stated.

### Findings

1. **spec-kit `converge` compares code to spec, plan, tasks and constitution, and appends unmet work as tasks** (confidence: high)
   - Reads `spec.md`, `plan.md`, `tasks.md` as "sole source of intent"; builds a requirements inventory with one stable key per FR-###, SC-###, or user-story acceptance scenario (e.g. `US1/AC2`) plus plan decisions and constitution principles.
   - Scopes the code to inspect from file paths named in plan/tasks plus a keyword search per requirement; "do not infer scope beyond what the artifacts define".
   - Counts existing tasks in the inventory regardless of checkbox: "completion claims are not evidence". Explicitly "not a diff tool", no git.
   - Source: https://github.com/github/spec-kit `templates/commands/converge.md` lines 60-70, 130-165 (main, file last changed 2026-09-18, commit 68b94af0).
   - Marks: source code (agent prompt template), not retracted, not a preprint, no citations, convergence: agrees with 5 f5.
   - Grade: medium (shipped and tested by a scaffold test, `tests/test_converge_template_scaffold.py`; no accuracy measurement found).

2. **converge classifies each gap as missing, partial, contradicts, or unrequested, with severity** (confidence: high)
   - `missing` = absent; `partial` = exists but not fully satisfying; `contradicts` = conflicts with intent or a constitution MUST; `unrequested` = code not called for (surfaced, never deleted).
   - Severity: CRITICAL (constitution MUST violation, or missing/contradicts on a P1 story baseline), HIGH (missing/partial core requirement), MEDIUM, LOW. Each finding records id, source-ref, gap-type, severity, evidence (file/area).
   - Source: converge.md lines 150-182.
   - Marks: source code; not retracted; not a preprint; no citations; single source.
   - Grade: medium (asserted design, unmeasured).

3. **converge reports as an in-session table, then appends a numbered "Convergence" phase; clean runs leave `tasks.md` byte-identical** (confidence: high)
   - Table columns `ID | Gap Type | Severity | Source | Evidence | Remaining Work`, plus counts of requirements, plan decisions and constitution principles checked.
   - Append rule: next phase number N, one `- [ ] T### <imperative> per <source-ref> (<gap-type>)` line per finding, CRITICAL/HIGH first, IDs never reused or renumbered; spec.md, plan.md, existing tasks and code are never touched.
   - Clean: no header, "Converged" message with counts. Loop is `implement` then `converge` until `Converged`.
   - Source: converge.md lines 71-84, 184-250.
   - Marks: source code; not retracted; not a preprint; no citations; convergence: matches 5 f5.
   - Grade: medium.

4. **spec-kit `analyze` is a read-only artifact consistency check; it never reads code** (confidence: high)
   - Six passes over spec/plan/tasks: duplication, ambiguity, underspecification, constitution alignment, coverage gaps (requirements with zero tasks, tasks with no requirement), inconsistency; cap 50 findings; reports a `Coverage %` (requirements with at least one task). Constitution conflicts are automatically CRITICAL.
   - This is requirement-to-task tracing, the same level as `compass coverage`, one level above converge.
   - Source: analyze.md lines 58-60, 123-166, 207 (github/spec-kit, main).
   - Marks: source code; not retracted; not a preprint; no citations; single source.
   - Grade: medium.

5. **spec-kit `checklist` explicitly refuses code-vs-spec checks; it tests the requirements text** (confidence: high)
   - Its stated frame is "unit tests for requirements writing": items like "Is 'prominent display' quantified?" (completeness, clarity, consistency) and the template lists "NOT checking if code/implementation matches the spec" as a wrong item.
   - Source: checklist.md lines 16-24, 152-183 (github/spec-kit, main).
   - Marks: source code; not retracted; not a preprint; no citations; single source.
   - Grade: medium.

6. **Compass `compass coverage` traces spec/ADR decisions (`D-NN`) to plan tasks, never to code** (confidence: high)
   - Sources default to the plan's `depends_on` documents of type spec or decision; a claim is a source-qualified citation `<doc>/D-NN` in the plan body; statuses `covered`, `scoped` (only under `## Later`), `NOT COVERED`; exit 1 on any uncovered trackable decision or unparseable source; `--strict` also fails `scoped`.
   - A decision is a `- **D-NN:**` bullet under a Decisions heading; `[informational]`/`[deferred]` tags or a discretion subheading make it non-trackable; an unparseable decision bullet poisons extraction rather than being dropped.
   - A spec like [[SPEC-034-verification-beyond-test-pass]] has no D-NN bullets (only prose Problem, Outcome, Constraints), so `coverage` has nothing to trace for it today.
   - `plugin/cli/commands/coverage.py:1-41` (contract), `:56-69` (binding: source types spec/decision, target plan, gate review->approved), `:117-157` (claim resolution); `plugin/cli/decisionslib.py:1-40` (grammar), `:102-103` (non-trackable tags).
   - Marks: source code read in repo; no retraction concept; not a preprint; no citations; convergence: matches REVIEW A3 "traces decisions to tasks, not code".
   - Grade: high (read directly).

7. **The validator cross-checks decision citations against the diff by prose judgment, report-only** (confidence: high)
   - Step 4d runs `compass coverage <plan>` then, per task, flags "cited, no evidence in the diff" and "implemented, uncited"; both are "findings, not blocks". Steps 4e, 4f, 4g are likewise report-only.
   - Validator statuses are Matches plan / Deviation (improvement) / Deviation (problem) / Missing / Not started: they compare diff to plan task, not code to spec requirement.
   - `plugin/templates/agents/validator.md:60-72` (statuses, 4b-4c), `:74-78` (4d), `:99-101` (4g `--strict`), `:112-122` (tester then probes), `:141-149` (PASS preconditions).
   - Marks: source code (agent prompt); no retraction concept; not a preprint; no citations; single source.
   - Grade: high (read directly).

8. **Today an unmet requirement can only reach open work through the build fix loop, whose trigger is tester-reported bugs** (confidence: high)
   - Fix loop (`plugin/skills/build/SKILL.md:42`): on tester-found bugs, ask the human "Fix? (yes / skip / abort)", send the diagnosis to the same builder by SendMessage, run `compass test-checkpoint verify --tree`, re-run tester, run `compass test-checkpoint cycle`; max 3 cycles, harmful cycle escalates.
   - Validator FAIL items are "unfixed tester bugs" (`validator.md:112`); no step turns a validator finding about a spec requirement into a task. The `build` skill's wave-boundary read of `compass coverage` (`SKILL.md:68`) is the one place coverage output feeds the next wave.
   - Marks: source code; no retraction concept; not a preprint; no citations; single source.
   - Grade: high (read directly).

9. **Builder review charter is style-level; a grep finds no spec-compliance clause** (confidence: high)
   - `plugin/templates/agents/builder.md:65`: sub-agent given `git diff`; "flag unused imports, leftover debug statements, inconsistent naming, missing error handling, anything copy-pasted without adaptation"; domain rules from CLAUDE.md or lessons. The builder then fixes issues and never runs tests.
   - It sees the diff only, not the spec or the task's acceptance text, so it cannot flag an unmet requirement.
   - Marks: source code; no retraction concept; not a preprint; no citations; convergence: matches REVIEW B8 and 1b f12 Compass part.
   - Grade: high (read directly).

10. **Plans bind tasks to spec decisions through `decisions:` and carry per-task verification bullets; requirements outside D-NN bullets have no ID to cite** (confidence: medium)
    - Planner task line: `- [ ] TASK-NNN: ... - complexity, depends_on, files, decisions: [<doc-stem>/D-NN]` with Automated and Manual verification bullets; a citation in prose never claims (`plugin/templates/agents/planner.md:80-82`, `:99-101`).
    - A grep finds plain-form `- **D-NN` bullets in 20 spec files out of 44 `SPEC-*` entries under `.compass/specs/`; the Problem, Desired Outcome, KPI and Constraints sections of a spec such as SPEC-034 carry no IDs. A requirement-level check needs either IDs added to those sections or an extraction step (spec-kit's equivalent keys are FR-###, SC-###, US#/AC#, converge.md line 137).
    - Marks: source code and repo grep; no retraction concept; not a preprint; no citations; single source.
    - Grade: medium (grep count approximate).

11. **Tessl links each requirement to a test file (`@test`) and a spec to its code (`@generate`, `targets`); verification is running the linked tests** (confidence: low-medium)
    - Traceability is requirement to test to code, not requirement to code by an assessor; critics in the search summary call the link "a reference mechanism rather than executable verification". The tile ships a manual `spec-verification.md` workflow.
    - https://tessl.io/blog/tessl-launches-spec-driven-framework-and-registry ; https://github.com/tesslio/spec-driven-development-tile ; https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html (all via a WebSearch summary; pages not opened).
    - Marks: vendor docs plus practitioner commentary; asserted; not a preprint; no citations; convergence with 5 f4 (Kiro also test-linked).
    - Grade: low (secondhand summary).

12. **Kiro ties EARS requirements to property-based tests at design time and BMAD's gap lens makes a missing-test finding name the regression; neither compares finished code to each requirement** (confidence: medium)
    - Reused from [[RESEARCH-axis-5-spec-driven-frameworks]] findings 4 and 8 (Kiro is IDE-only and closed; not re-read). BMAD-METHOD tree listing shows the lens at `skills/core-tools/bmad-review/references/lens-adversarial.md`; its body was not re-read.
    - Marks: vendor docs and source code; asserted; not a preprint; no citations; 2 sources agree in direction.
    - Grade: medium (reused).

13. **Agent-as-a-Judge on 365 requirements across 55 tasks: agreement with human consensus about 90%, plain LLM-as-a-Judge about 60-71%** (confidence: medium)
    - DevAI benchmark. On OpenHands outputs the agent judge reached 92.07% (gray-box) and 90.44% (black-box) alignment with human majority; the plain LLM judge 70.76% and 60.38%. The paper warns the metric misleads under class imbalance: for MetaGPT, which rarely meets requirements, a judge labelling most cases negative scored 84.15%, so it also reports PR curves.
    - arXiv:2410.10934 (Oct 2024, older than the 2025-2026 window), PDF text, "Alignment Rate" and "PR Curves" paragraphs.
    - Marks: preprint (venue not checked); not retracted; citations not retrieved; one benchmark, three agent systems.
    - Grade: medium (measured, small task set, 2024-era models).

14. **A tool-less LLM judge scoring a diff against agent-written weighted binary criteria reached per-task AUROC 0.826 against test outcomes** (confidence: medium)
    - 7,291 labeled SWE-bench Verified patches from 15 systems; over 400 tasks with both resolved and unresolved patches, mean AUROC 0.826 (0.838 on tasks not used to tune the rubric prompt); system ranking Spearman 0.968. The authors say it does not establish requirement satisfaction beyond agreement with tests; disagreements trace to tests that do not match the task, execution-blocking defects a textual reading misses, and errors in criteria or verdicts.
    - arXiv:2611.23309 (Nov 2026), abstract read.
    - Marks: preprint; not retracted; 0 citations known; one source; convergence: agrees in direction with 4 f19 (execution-free verifiers help but miss execution defects).
    - Grade: medium (measured on a large labeled set; target is test agreement, not the spec).

15. **Passing patches break stated constraints 34% of the time (SWE-Gate), and an LLM checker caught fewer violations than a deterministic one** (confidence: medium)
    - SWE-Gate: 303 instances, 75 repositories, four backends; 221 of 644 test-passing repairs failed the supplied review constraints, each instance with separate functional and constraint tests. The constraints are executable tests, so the benchmark shows the gap, not an LLM judge's accuracy at finding it.
    - Reused from 4 f7: deterministic verifier 78.7% vs LLM checker 59.0% of violating decisions (small models, synthetic).
    - arXiv:2609.04167 abstract re-read this pass; arXiv:2611.07483 via prior finding.
    - Marks: preprints; not retracted; 0 citations known; 2 sources agree in direction.
    - Grade: medium for SWE-Gate (measured), low-medium for the checker comparison.

16. **TraceDev keeps a validator-owned traceability graph linking requirements, design models and code; success 53.63% and 56.82% on two datasets** (confidence: low-medium)
    - Five roles (Requirement Refiner, Designer, Developer, Tester, Validator); the Validator builds and maintains a heterogeneous graph used as structured context by the other agents. Gains up to 186.63% and 340.80% over two baselines on 125 use cases; abstract only, baselines unnamed in the read.
    - arXiv:2607.18886 (Jul 2026), abstract read.
    - Marks: preprint; not retracted; 0 citations known; one source.
    - Grade: low-medium (measured, abstract only).

17. **Per-line requirement citation in code enables automated hallucination detection; uncited code is more deterministic** (confidence: medium)
    - Reused from 5 f19 (traceSDD vs Spec Kit vs OpenSpec): only cited code allowed detection (86.4% and 88.0% vs 0%, 0% FPR); uncited code was more deterministic across sessions (d about -0.7). ReqToCode (arXiv:2603.13999, Mar 2026) proposes a generated language-native "Traceable" element per requirement that code and tests reference and the build validates; a generic example only, no measurement.
    - Marks: preprints; not retracted; citations not retrieved; 2 sources agree in direction.
    - Grade: medium (traceSDD measured, ReqToCode unmeasured).

18. **A correctness-only, skip-style reviewer prompt is vendor-documented guidance and unmeasured** (confidence: low-medium)
    - Reused from 1b f12: "compare the diff to SPEC.md, check every requirement is implemented and listed edge cases have tests, report gaps that affect correctness and skip style"; rationale: a reviewer asked to find problems always finds something, and fixing every finding adds layers and tests for impossible cases.
    - Neighbouring reviewer evidence reused from 4 f9, f10: Cognition 2026 clean-context reviewer finds about 2 bugs per PR, roughly 58% severe; Anthropic's Code Review verification stage left under 1% of findings marked incorrect (vendor posts, asserted).
    - https://code.claude.com/docs/en/best-practices (via 1b f12; not re-fetched).
    - Marks: vendor documentation; asserted; not a preprint; no citations; convergence: 1b f12 and 4 f9/f10 agree.
    - Grade: low-medium (asserted, no ablation).

### What a correctness-against-the-spec charter would say (review item B8; documented elements only)
Elements the sources attach to such a review, from findings 1, 2, 9, 12, 18:
- Input: the diff plus the task's spec requirements (each by ID) and listed edge cases; today's charter gets the diff only (`builder.md:65`).
- Per requirement, a verdict among met, partial, missing, contradicts, with the file or area as evidence (converge's gap types, finding 2).
- "Report gaps that affect correctness and skip style" (finding 18); BMAD drops findings it cannot ground (finding 12).
- Unrequested code is surfaced, not removed (converge `unrequested`, finding 2).
- The evidence for the charter is asserted, not measured; the nearest measurements are judge accuracy (findings 13, 14, 15) and the 34% constraint-break rate.

### Contradictions
- Findings 13 and 15 point in opposite directions on LLM judges: an agentic judge with tools tracks human consensus about 90% (2024 models), while a plain LLM checker caught 59.0% of violations against 78.7% for a deterministic one (small models, synthetic). Different tasks, models and years; not reconciled here.
- converge says "completion claims are not evidence" and assesses code directly; the validator's 4c audit flags a `[x]` with no diff and otherwise trusts the diff-to-task match (`validator.md:60-72`).

### Gaps
- No measured accuracy found for an LLM-only, requirement-by-requirement check of finished code against a prose spec on 2025-2026 models; findings 13 and 14 measure neighbouring tasks.
- converge has no published accuracy or false-positive data; only a template scaffold test file exists (`tests/test_converge_template_scaffold.py`, name seen in the tree listing, body not read).
- Kiro and Tessl sources were not read (Kiro closed; Tessl via search summary only); BMAD lens body not re-read.
- The count of specs with trackable D-NN was a grep, not a `compass coverage` run per spec.

## Candidate changes for Compass (ranked by impact)

1. **Requirement-to-code conformance pass that appends unmet requirements as tasks (spec-kit converge shape).** North star: accuracy, perfect memory.
   - Would change: a validator step (or `converge` skill) after 4d builds a requirement inventory from the spec (D-NN bullets plus Desired Outcome and Constraints items), assesses each against the code in the task's `files:` scope, classifies missing/partial/contradicts/unrequested, and appends `- [ ] TASK-NNN ... per <spec>/<id> (<gap>)` lines to the plan, never rewriting existing tasks; a clean run leaves the plan byte-identical. Re-entry rides the existing 3-cycle cap (`plugin/skills/build/SKILL.md:42`).
   - Covered already: no. `compass coverage` stops at tasks (finding 6); validator findings are report-only (finding 7); nothing re-opens work from a spec finding (finding 8).
2. **Give spec requirements citable IDs and extend `compass coverage` one level toward code.** North star: accuracy, low token use (mechanical).
   - Would change: spec template and `decisionslib.py` grammar so Outcome and Constraint items carry IDs; a deterministic check that each cited ID appears in a task's diff or test (per-line citation, finding 17), reporting the rest to the pass in item 1.
   - Covered already: partly (D-NN bullets, `decisions:`, `--strict`; findings 6, 10); nothing reads code.
3. **Replace the builder review charter with a correctness-against-the-spec charter, skipping style.** North star: accuracy.
   - Would change: `plugin/templates/agents/builder.md:65` hands the reviewer the diff plus the task's cited spec requirements and edge cases; style items stay with the formatter step (`builder.md` step 7). Evidence is asserted only (finding 18).
   - Covered already: no (review item B8; grep in 1b f12 finds no skip-style rule).
4. **Run the conformance judge with tools, in a fresh context, and route checkable requirements to commands.** North star: accuracy.
   - Would change: validator prompt gives the judge file-read and run access (finding 13: about 90% vs 60-71% tool-less) and sends any requirement expressible as a test or grep to a command (finding 15: 78.7% vs 59.0%); LLM judgment for the residue.
   - Covered already: partly (validator has Bash and command-evidence blocks, `validator.md:30`, `:141-149`).
5. **Report conformance as a table with counts, like converge's summary and analyze's Coverage %.** North star: perfect memory.
   - Would change: validator report gains rows `Requirement | Status | Evidence | Task` and a "requirements checked / unmet" count.
   - Covered already: partly (Decision Coverage section, report-only, `validator.md:179-182`).

