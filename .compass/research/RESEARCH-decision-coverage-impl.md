---
title: "Decision Coverage Implementation: Format, Parser, Matcher, Gate, Migration"
type: research
status: complete
confidence: high
area: methodology
tags: [decision-coverage, traceability, cli, parser, gates, validation, gsd, prior-art]
created: 2026-07-23
updated: 2026-07-23
git_branch: "master"
git_commit: "fbc32c5"
author: "researcher agent"
depends_on: ["[[SPEC-007-decision-coverage-tracing]]", "[[RESEARCH-gsd-core-improvements-for-compass]]", "[[ADR-005-compass-cli-for-mechanical-work]]"]
summary: "format, parser, matcher, gate, migration"
---

# Decision Coverage Implementation: Format, Parser, Matcher, Gate, Migration

Answers the open questions of [[SPEC-007-decision-coverage-tracing]] with evidence, so an ADR and plan can be written. Bound by the spec's human decisions D-01..D-06.

## Question

For each of the spec's open questions: what is the exact decision-unit authoring convention, the Python fail-loud parser design, the plan-coverage matching scheme, the gate/audit attachment points, and the migration posture for existing ADRs, with evidence from the Compass codebase and the verified GSD prior-art source?

## Methodology

Prior-art source read (GSD `decisions.cts` + `gap-checker.cts`, local verified clone), plus targeted reads of the Compass vault (all 5 ADRs, SPEC-005/007/009, PLAN-002, active.md) and plugin (`plugin/cli/`, `plugin/skills/plan|validate|build`, `plugin/templates/agents/planner|validator.md`, `plugin/hooks/hooks.json`). Technology-landscape approach: per-axis findings with file:line evidence. GSD paths refer to the scratchpad clone `gsd-core/src/`.

## Findings

### Axis 1: Decision-unit format

1. **An authoring convention already exists in the wild and mostly converged** (confidence: high)
 Three specs carry a `## Decisions (made by the human)` section. SPEC-007 and SPEC-009 already use exactly `- **D-NN:** text` bullets; SPEC-005 uses bold-phrase bullets without IDs (`- **The index is machine-only.** ...`). No skill or template defines this section - it is emergent.
 - `.compass/specs/SPEC-007-decision-coverage-tracing.md:41-48` - six `- **D-NN:** text` bullets
 - `.compass/specs/SPEC-009-configurable-pipeline-workflows.md:40-42` - same form, one bullet
 - `.compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md:29-37` - ID-less bold-phrase form
 - `plugin/skills/spec/SKILL.md`, `plugin/skills/obsidian/SKILL.md` spec template - zero mentions of a Decisions section (grep confirmed)

2. **Proposed convention: `- **D-NN:** text` bullets under any `## Decisions`/`## Decision` heading** (confidence: high)
 Minimal ceremony: the two newest specs already write this form unprompted, so the convention is "keep doing what SPEC-007/009 do, add the ID." Continuation lines indent under the bullet (GSD supports this, `decisions.cts:215-218`). ADRs use their existing `## Decision` heading (obsidian template); a heading regex `/^#{2,3}\s*Decisions?\b/i` covers both plus the `(made by the human)` suffix, mirroring GSD's `/decisions?\b/i` heading fallback (`decisions.cts:281-285`).

3. **ID grammar: plain `D-NN`, local to the document; no `D-AREA-NN`** (confidence: high)
 GSD accepts alphanumeric IDs (`D-INFRA-01`) because its scope is one `CONTEXT.md` per phase (`decisions.cts:62`). Compass gets uniqueness from the source-document qualifier instead (Finding 12), which matches the vault's "numbering is local, path is identity" philosophy.
 - [[ADR-003-drop-counter-file-jit-compute]] - local numbering, filesystem as truth
 - [[ADR-004-hierarchical-specs-with-facets]] - "Path is identity. Numbering is local per folder."

4. **Opt-out tags: bracket tags on the bullet + a discretion subheading, straight from GSD** (confidence: high)
 `- **D-NN [deferred]:** text` with the non-trackable tag set `informational`/`deferred` (GSD also has `folded`; Compass can adopt it or not). A `### <agent>'s Discretion` subheading inside the Decisions section makes every bullet under it non-trackable. Both mechanisms are cheap and satisfy the spec's "deliberate non-coverage is expressible and recorded" need.
 - `decisions.cts:49-54` - `DISCRETION_HEADINGS` + `NON_TRACKABLE_TAGS = {informational, folded, deferred}`
 - `decisions.cts:162-167` - `trackable = !inDiscretion && !tags.some(nonTrackable)`
 - [[SPEC-007-decision-coverage-tracing]] Needs: "deferred, delegated to agent discretion, or marked informational"

### Axis 2: The fail-loud parser (Python)

5. **GSD's 3-outcome contract is the mechanism to port** (confidence: high)
 `extractDecisions(content)` returns `{decisions, outcome}` where outcome is `parsed` (>=1 extracted, zero misses), `none-present` (no decision signals), or `could-not-parse` (decision-shaped content, zero or partial extraction). The gate treats `could-not-parse` as a hard failure, never a clean pass - exactly SPEC-007 D-02.
 - `decisions.cts:42-47` - the `DecisionOutcome` type and its three states
 - `decisions.cts:242-318` - the full priority strategy (tagged block, then heading section, then shape heuristics)

6. **Parse-miss rule: one malformed `- **D-` bullet poisons the whole extraction** (confidence: high)
 Any line that looks like a decision bullet (`/^\s*-\s+\*\*D-/`) but fails every grammar counts as a parse-miss; `parseMisses > 0` forces `could-not-parse` even when other decisions parsed, because a silent drop of one decision is the exact failure the system exists to prevent.
 - `decisions.cts:206-211` - the parse-miss guard with a stderr warning
 - `decisions.cts:259-262, 292-295` - misses override a partial parse

7. **"Decision-shaped but zero parsed" evidence heuristics distinguish the two empty outcomes** (confidence: high)
 When a Decisions heading exists but zero bullets parsed, GSD reports `could-not-parse` only on evidence of real entries: a `\bD-[A-Za-z0-9]` token, an ID-shaped bold-lead-in bullet (`- **X-NN...`, uppercase-prefix regex so prose bullets like `- **Scope:**` stay clean), or an unterminated code fence. A heading with only prose is a legitimate `none-present`. This ID-shape distinction matters for Compass: it is what lets legacy ADR Decision sections (prose + bold non-ID bullets) pass as none-present (Finding 20).
 - `decisions.cts:106` - `boldLeadInBulletRe = /^\s*-\s+\*\*[A-Z]+[0-9]*-[A-Za-z0-9]/m` with the false-positive rationale
 - `decisions.cts:296-306` - heading path evidence check; `decisions.cts:309-317` - no-heading path (bare D- token anywhere still fails loud)

8. **Grammar count: GSD needed three bullet regexes because of authoring drift; Compass can start with two** (confidence: medium)
 GSD's colon form (`:**` immediately after ID/tags), em-dash form, and titled-colon form (`**D-NN: Title.** body`) each fixed a real recall bug (#1343, #1364, #1639). Compass's global no-em-dash writing rule makes the em-dash form near-impossible in Compass-authored docs, so colon + titled-colon suffice; keeping the em-dash regex anyway is ~5 lines of insurance for human-pasted content. This is a call for the ADR.
 - `decisions.cts:62, 72, 85` - the three regexes with their bug-history comments
 - `decisions.cts:79-84` - ordering constraint: titled-colon MUST be checked after the other two (strict superset)

9. **Fence stripping: the existing validator's skip logic is not directly reusable and has a silent-failure mode GSD fixed** (confidence: high)
 `validate.py` skips fences with a per-line toggle inside `_wikilinks_in` - coupled to wikilink iteration, and an unterminated fence silently swallows the rest of the file. GSD instead strips fences up front and returns an `unterminatedFence` flag that feeds the could-not-parse evidence. The Python parser needs a small shared helper, e.g. `strip_fenced_code(text) -> (text, unterminated_fence)` in `vaultlib.py`, plus inline-code-span stripping per [[LESSON-wikilink-validator-skip-code]].
 - `plugin/cli/commands/validate.py:61-74` - `_wikilinks_in` fence toggle + `INLINE_CODE` strip
 - `decisions.cts:249, 271, 313` - fence-strip before extraction; unterminated fence as fail-loud evidence

10. **Python home: a parser module in `plugin/cli/` following the established command conventions** (confidence: high)
 The CLI is stdlib-only argparse with one module per command exposing `run(args)`, registered in `COMMAND_SPECS`; shared logic lives in `vaultlib.py`; tests are seeded-defect pytest fixtures in `plugin/cli/tests/`. A `decisionslib.py` (or vaultlib additions) holding `extract_decisions(text) -> (decisions, outcome)` keeps the parser importable by both new commands and `sync`/`validate`.
 - `plugin/cli/maincli.py:18-31` - `COMMAND_SPECS` registration; `maincli.py:87-93` - `commands.<name>.run(args)` dispatch
 - `plugin/cli/vaultlib.py:1-6` - "pure standard library, deterministic" contract
 - [[PLAN-002-compass-cli-implementation]] Resolved decisions 1-6 - layout, LF writes, exit-code policy

### Axis 3: Coverage matching

11. **GSD's matcher is a word-boundary regex over concatenated plan text, with a report table and counts** (confidence: high)
 `detectCoverage` maps each item to `\b<escaped-id>\b` tested against all `*-PLAN.md` files joined; rows are natural-sorted; output is a `Source | Item | Status` table plus a one-line summary and `{total, covered, uncovered}` counts. A `could-not-parse` outcome surfaces in the report independently of requirement rows (their FIX D: a mismatch must never be masked by other items existing).
 - `gap-checker.cts:129-137` - `detectCoverage`; `gap-checker.cts:153-165` - table; `gap-checker.cts:333-371` - could-not-parse surfaced regardless
 - `gap-checker.cts:167-180` - the gate is config-read (`workflow.post_planning_gaps`), a shape SPEC-009 will want later

12. **Bare `D-NN` matching is unsafe in Compass; the citation must carry the source-document qualifier** (confidence: high)
 GSD never collides because its scope is one CONTEXT.md per phase directory. Compass plans draw from multiple sources and `D-01` already exists in both SPEC-007 and SPEC-009; hierarchical specs even reuse `SPEC-001` across folders, so the qualifier must be a wikilink-resolvable document name, not just the `SPEC-NNN` prefix. Proposed citation token: `<doc-stem>/D-NN`, e.g. `SPEC-007-decision-coverage-tracing/D-03` (path-qualified stem for nested specs). The matcher resolves the qualifier through the same name set `validate.py` already builds for wikilinks (bare stem, folder name, path-qualified name), then greps `\b<qualifier>/D-NN\b` in the plan body.
 - `.compass/specs/SPEC-007-decision-coverage-tracing.md:43` and `SPEC-009-configurable-pipeline-workflows.md:42` - two live `D-01`s today
 - `plugin/cli/commands/validate.py:43-58` - `_resolvable_names`: the existing resolution set to reuse
 - [[ADR-004-hierarchical-specs-with-facets]] - local numbering means short prefixes collide across folders

13. **A convenience rule is available: allow bare `D-NN` when the plan has exactly one decision-bearing source** (confidence: medium)
 Single-source plans (the common case) could cite `D-03` unqualified with no ambiguity; the checker knows the source set and can reject bare IDs the moment a second decision-bearing source appears. Trade-off for the ADR: lower ceremony vs. citations that break when a source is added later. GSD effectively lives in the always-single-source world.

14. **Task-level citation: a `decisions:` field on the task line, same shape as `files:`** (confidence: high)
 SPEC-007 D-04 requires tasks to cite the IDs they implement, audited (not gated) at validation. The plan task line already carries structured suffix fields: `- [ ] TASK-NNN: desc - complexity: S, depends_on: none, files: [list]`. Adding `decisions: [SPEC-007-decision-coverage-tracing/D-03]` is the same grammar, greppable by the CLI, and gives the validator a per-task audit target. Plan-level coverage can still count any citation anywhere in the plan body (GSD's rule); the task field is the finer grain for the audit.
 - `plugin/templates/agents/planner.md:71-79` - the task-line grammar
 - `.compass/plans/PLAN-002-compass-cli-implementation.md:54, 68` - real task lines with the suffix-field pattern
 - `.compass/specs/SPEC-007-decision-coverage-tracing.md:46` - D-04 wording

15. **Default source set: derive from the plan's `depends_on` frontmatter, filtered to spec/decision types** (confidence: high)
 Plans already declare their sources (`depends_on: ["[[SPEC-004...]]", "[[ADR-005...]]", "[[RESEARCH-...]]"]`). Filtering that list to documents of `type: spec`/`decision` gives the checker its "--against" set with zero new ceremony, and it is exactly D-06's default role binding (specs+ADRs covered by plans). An explicit `--against` flag overrides for custom workflows later.
 - `.compass/plans/PLAN-002-compass-cli-implementation.md:11` - a real 3-source depends_on including an ADR
 - `plugin/templates/agents/planner.md:51` - planner template emits depends_on
 - `.compass/specs/SPEC-007-decision-coverage-tracing.md:48` - D-06 default roles

### Axis 4: Where the gate and audit attach

16. **Proposed command surface: `compass decisions <doc>` and `compass coverage <plan> [--against <doc>...]`** (confidence: high)
 - `compass decisions <doc>`: parse one document, print the decision list with ID, trackable flag, tags, text, and the outcome; exit 0 on `parsed`/`none-present`, exit 1 on `could-not-parse`.
 - `compass coverage <plan> [--against <doc>...]`: resolve sources (default per Finding 15), parse each (fail-loud), match citations, print the GSD-style table + counts; exit 1 when any trackable decision is uncovered OR any source is `could-not-parse`; exit 0 otherwise.
 Both register in `COMMAND_SPECS` (`maincli.py:18-31`) as human-mode read-only commands, which are explicitly allowed to exit non-zero to report defects (PLAN-002 Resolved decision 5). SPEC-007's open question "validate vs new subcommand vs both" leans "both": the dedicated commands are the gate; `compass validate` can additionally warn on parse failures vault-wide.

17. **Gate insertion point: planner step 6, between human approval and task distribution** (confidence: high)
 The plan lifecycle is: planner drafts, presents (step 5), human approves, then step 6 writes the plan file and distributes tasks to active.md/backlog.md. D-03 binds the blocking gate to the plan boundary and D-05 to a status transition; in the default workflow that transition is plan `review -> approved` (human) followed by distribution (agent). Concretely: the planner runs `compass coverage` on the draft before presenting (so the human sees the table), and step 6 refuses to distribute while the exit code is nonzero. `/compass:build` step 2 already requires the parent plan to be `approved`, so no build-side gate is needed, consistent with D-04's no-mid-build-gates ruling.
 - `plugin/templates/agents/planner.md:91-120` - present-then-create flow; step 6 is the choke point
 - `plugin/skills/build/SKILL.md:26` - "parent plan must be approved or active" prerequisite
 - Methodology status table - `review -> approved` is human-owned

18. **The blocking gate cannot live in the PostToolUse hook: the never-exit-2 invariant forbids it** (confidence: high)
 A command hook blocks a write only by exiting 2, and the entire CLI is engineered to never exit 2 - argparse is subclassed to clamp it, `cli_err` clamps it, the dispatch catch-all returns 1 - because a bug must never block the user's edit. So the hook path can at most warn (a `systemMessage` on an approved-plan write with uncovered decisions); the blocking behavior must be the skill-invoked command's exit code, which the orchestrating skill honors. This is still harness-side per the spec's need ("blocking-vs-warning is a deliberate choice, not agent judgment"): the check and its verdict are mechanical; only the invocation lives in the skill protocol.
 - `plugin/cli/maincli.py:52-58, 61-70` - both exit-2 clamps
 - [[ADR-005-compass-cli-for-mechanical-work]] "Fail-safe means never exit 2" + [[PLAN-002-compass-cli-implementation]] Resolved decision 5
 - `plugin/hooks/hooks.json:4-41` - the current PostToolUse command entries

19. **Validator attachment: a new protocol step running `compass coverage` with the mandatory Command/Output/Result block, plus a per-task cited-ID audit** (confidence: high)
 The validator's contract is "running commands is verification"; every check needs a `Command run:` block. Decision-coverage audit fits as: (a) run `compass coverage <plan>` and record the block; (b) for each task, cross-check its `decisions:` citations against the task's diff, classifying like the existing checkbox audit (cited-but-no-evidence, implemented-but-uncited). The validator is read-only, so it reports; it does not gate - matching D-04.
 - `plugin/templates/agents/validator.md:20-30` - the check format; `validator.md:54-72` - the per-task audit pattern to extend
 - `.compass/specs/SPEC-007-decision-coverage-tracing.md:46` - audit-not-gate at task level

20. **SPEC-009 deferral: hardcode the default binding behind one config-lookup seam** (confidence: medium)
 [[SPEC-009-configurable-pipeline-workflows]] (which owns workflow-declared roles and gate transitions, its D-01) is deferred to backlog. GSD shows the cheap forward-compatible shape: the gate reads one config key with a default (`readGate` returns true when `workflow.post_planning_gaps` is absent). Compass can ship with the specs+ADRs -> plans binding and the plan-approval transition as the built-in default, resolved through a single function that SPEC-009 later re-points at workflow config.
 - `gap-checker.cts:167-180` - `readGate` default-true config read
 - `.compass/active.md:84` - SPEC-009 explicitly deferred

### Axis 5: Retroactive migration

21. **The 5 existing ADRs hold roughly 24 discrete rulings, unevenly shaped** (confidence: high)
 Counting bold/numbered rulings inside each `## Decision` section: ADR-001 ~2 (skill + vault), ADR-002 6 (numbered mechanisms), ADR-003 1-2 (JIT rule + per-artifact table), ADR-004 8 (4 architecture parts + 4 open-question resolutions), ADR-005 ~7 (CLI+Python+hook decision, command surface, 4 hook-contract facts, skill shrink). None uses D-NN IDs; the shapes vary (numbered lists, bold-phrase bullets, tables, subheadings), so retrofit is judgment work, not a mechanical rename.
 - `.compass/decisions/ADR-002-retrospective-lessons-subsystem.md:38-45` - the six mechanisms
 - `.compass/decisions/ADR-004-hierarchical-specs-with-facets.md:26-68` - parts 1-4 + the four resolutions
 - `.compass/decisions/ADR-005-compass-cli-for-mechanical-work.md:25-65` - decision + command table + hook facts

22. **All 5 ADRs are already implemented by completed plans, so retrofitted IDs would have no live plan to cover them** (confidence: high)
 ADR-002 implemented via PLAN-001 (done), ADR-005 via PLAN-002 (done); ADR-001/003/004 are absorbed into shipped plugin behavior. Retrofitting ~24 trackable IDs today would make every future `compass coverage` run against those sources report them uncovered, unless each is tagged `[informational]`/`[deferred]` - pure ceremony with no accident-prevention payoff, since the decisions already shipped.
 - `.compass/decisions/ADR-002...md:18`, `.compass/plans/PLAN-002...md:4` (`status: done`)
 - Note: ADR-004:18 references "PLAN-003-hierarchical-vault-implementation.md," which does not exist in `.compass/plans/` - a live example of exactly the drift SPEC-007 targets

23. **The GSD-style parser makes new-only migration free: legacy ADRs parse as `none-present`, not `could-not-parse`** (confidence: high)
 Inspected against Finding 7's heuristics, no existing ADR Decision section contains a `\bD-` token or an ID-shaped bold-lead-in bullet (`- **Fail-safe...`, `1. **Phase-boundary capture.**` are mixed-case prose lead-ins the regex deliberately excludes). So shipping the parser today does not fail loud on any existing document; IDs appear only in docs authored from now on (SPEC-007/009 already comply).
 - `decisions.cts:96-105` - why prose bold bullets must stay `none-present` (a false could-not-parse hard-blocks the gate)
 - All 5 ADR Decision sections, read in full - zero D- tokens

## Contradictions

- **Blocking gate vs never-exit-2:** SPEC-007 D-03 demands a blocking gate; ADR-005/PLAN-002 forbid exit 2 anywhere in the CLI because the hook path must never block a write. Resolution space (ADR's call): the gate is a human-mode command whose nonzero exit the planner skill honors (Finding 18) - no exit-2 needed - or a scoped carve-out for a non-hook gate command. The former preserves the invariant untouched.
- **`sync` is append-only for index.md but the coverage report is fully derived:** no real conflict, but the ADR should keep coverage output ephemeral (stdout / report block), not written into vault files, to avoid a second append-only-vs-regen split like the one [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] exists to fix.

## Gaps

- **Where discussion-made decisions live.** SPEC-007 scopes in "the discussion that precedes a plan," but the only current home is free-form `## Decisions Made` sections in handoffs. Whether handoffs become parseable sources (their heading would match `/decisions?/i` if scanned) or discussion decisions must be promoted into the spec/ADR before planning is undecided - for the ADR. Scoping the parser to declared sources (Finding 15) avoids accidentally parsing handoffs in the meantime.
- **Multi-source partial failure semantics.** When one of three sources is `could-not-parse`, GSD surfaces the mismatch alongside the other sources' rows (`gap-checker.cts:333-371`). The Compass ADR should state the same rule explicitly; untested here.
- **`compass validate` integration depth.** Whether validate gains a vault-wide "decision sections parseable" warning pass is proposed but not costed.
- **GSD tag `folded`.** Its precise semantics (a decision folded into another) were not verified beyond the tag name; adopt or drop consciously.

## Recommendation

For the ADR author (proposals, human decides):

1. **Format:** `- **D-NN:** text` bullets (continuation lines indented) under the existing `## Decisions (made by the human)` heading in specs and `## Decision` in ADRs; opt-out via `[informational]`/`[deferred]` bracket tags and a discretion subheading. Codify in the obsidian spec/ADR templates and the spec skill. IDs are plain `D-NN`, local to the doc.
2. **Parser:** port GSD's 3-outcome extraction to `plugin/cli/` (shared lib + `decisions.py` command): heading-section collection, colon + titled-colon bullet grammars (em-dash grammar optional), parse-miss poisoning, D-token/ID-shaped-bullet/unterminated-fence evidence heuristics, fence + inline-code stripping via a new `strip_fenced_code` helper (do not reuse validate.py's toggle as-is).
3. **Matching:** citations are source-qualified tokens `<doc-stem>/D-NN`; plan-level coverage greps the plan body with word boundaries; tasks additionally carry `decisions: [...]` for the validator's per-task audit. Default source set = plan `depends_on` filtered to spec/decision types.
4. **Gate:** `compass coverage <plan>` exit code is the gate, invoked by the planner at step 6 (post-approval, pre-distribution) and shown to the human at step 5; validator runs it again plus the per-task audit as report-only. No hook-path blocking (never-exit-2 stands); optionally a sync warning. One config-lookup seam holds the default binding for SPEC-009 to externalize later.
5. **Migration:** new-only. Do not retrofit the 5 existing ADRs (~24 rulings, all shipped, no live covering plans; the parser already treats them as none-present). Retrofit an ADR only if it is ever re-opened.
