---
title: "Model Resolution Table: Current State, Mechanism, and Implementation Options"
type: research
status: complete
confidence: high
area: methodology
tags: [model-policy, harness, cli, configuration, multi-host, tokens, cost]
created: 2026-07-23
updated: 2026-07-23
git_branch: "master"
git_commit: "fbc32c5"
author: "researcher agent"
depends_on: ["[[SPEC-008-central-model-resolution-table]]"]
summary: "current state, mechanism, implementation options"
---

# Model Resolution Table: Current State, Mechanism, and Implementation Options

Answers the open questions of [[SPEC-008-central-model-resolution-table]] so an ADR and plan can be written. Prior art: GSD's `model-resolver.cts` / `model-catalog.cts` / `model-catalog.json` (cloned locally, verified by reading source). Composes with [[SPEC-006-multi-host-agent-cli-support]] and [[ADR-005-compass-cli-for-mechanical-work]].

## Question

Where is model choice specified in Compass today, what mechanism can the harness actually pull on Claude Code, and what should the central table's location, format, tier vocabulary, defaults, precedence, CLI surface, and degradation story be?

## Methodology

Technology-landscape survey: read all 13 agent templates and both install skills in `plugin/`, grepped the whole plugin for model references, read GSD's resolver/profiles/catalog source line by line, and verified the Claude Code subagent mechanism against the official docs (code.claude.com/docs/en/sub-agents, fetched 2026-07-23).

## Findings

### 1. Where model is specified today

1. **Model policy lives in 13 agent-template frontmatter files, three inconsistent states** (confidence: high)
 - `model: sonnet` (5 agents): `plugin/templates/agents/codebase-locator.md:6`, `vault-locator.md:6`, `pattern-finder.md:6`, `codebase-analyzer.md:6`, `vault-analyzer.md:6`
 - `model: inherit` (6 agents): `builder.md:6`, `planner.md:6`, `tester.md:6`, `validator.md:7`, `debug.md:7`, `pr-describe.md:6`
 - No `model:` field at all (2 agents): `researcher.md`, `reviewer.md` (docs default this to `inherit`)
 - Every template carries `effort: high` - effort is uniformly flat, never tuned per agent.
 - `haiku` appears nowhere in `plugin/` - no Compass agent runs on the cheap tier today, despite SPEC-008's success criterion that locators resolve cheap.

2. **Policy also leaks into prose and rules, the scattering SPEC-008 names** (confidence: high)
 - `plugin/skills/methodology/SKILL.md:271` - "pattern-finder ... Runs on `sonnet` for speed" (prose restating frontmatter).
 - `plugin/templates/rules/compass-agent-patterns.md:43` - `model: inherit` shown as the agent pattern.
 - `plugin/skills/checkup/SKILL.md:19` - checkup treats `model`/`effort` presence per agent file as a health check, institutionalizing per-file model declaration.
 - [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] lines 34-35, 51 - the summary job is a non-subagent model consumer: headless `claude -p` pinned to "a small/cheap model (haiku)" as a falsification criterion. A central table has at least one non-agent row.

3. **No spawn-time model selection exists anywhere in Compass** (confidence: high)
 Skills say "Spawn the `planner` agent" etc. with no model parameter; grep for model across `plugin/skills/` finds zero spawn-time model passing. Install is a verbatim copy: `plugin/skills/setup/SKILL.md:59-62` and `plugin/skills/update/SKILL.md:40-44` both `cp` templates into `.claude/agents/` with no transformation step. The installed `.claude/agents/*.md` in this repo are byte-identical copies of the templates.

### 2. The mechanism on Claude Code

4. **Claude Code resolves a subagent's model through a documented 4-step precedence** (confidence: high)
 Official docs (sub-agents page, "Choose a model", fetched 2026-07-23):
 - Step 1: `CLAUDE_CODE_SUBAGENT_MODEL` env var (global, all subagents).
 - Step 2: per-invocation `model` parameter passed by the caller when spawning.
 - Step 3: the agent definition's `model:` frontmatter.
 - Step 4: the main conversation's model (`inherit`; also the default when the field is omitted).
 - Accepted values: aliases `sonnet` / `opus` / `haiku` / `fable`, a full model ID (e.g. `claude-opus-4-8`), or `inherit`.

5. **Both levers SPEC-008 could pull are real; frontmatter is the deterministic one** (confidence: high)
 - INSTALL-time lever: write `model:` (and `effort:`) into generated `.claude/agents/*.md`. Zero tokens per spawn, deterministic, no LLM compliance needed - aligned with [[ADR-005-compass-cli-for-mechanical-work]]. Claude Code watches `.claude/agents/` and picks up edits within seconds, no restart (docs, "Write subagent files" note), so a re-apply takes effect immediately.
 - SPAWN-time lever: the Agent tool's per-invocation `model` parameter (docs step 2; independently confirmed by GSD: `model-resolver.cts:229-231` "Claude Code's Agent tool `model` parameter documents only tier aliases (opus/sonnet/haiku/fable)"). GSD uses this lever: its orchestrator runs `gsd-tools resolve-model <agent>` and passes the result at spawn. Cost: a Bash round-trip plus prompt instructions on every spawn, on the agent token budget, and it depends on the orchestrating LLM remembering to do it.
 - ENV lever: `CLAUDE_CODE_SUBAGENT_MODEL` outranks both but is all-subagents-global - usable only as a user escape hatch, not per-agent policy.

6. **`effort` is a supported frontmatter field with the same install-time channel** (confidence: high)
 Docs frontmatter table: `effort` - "Effort level when this subagent is active. Overrides the session effort level ... Options: `low`, `medium`, `high`, `xhigh`, `max`". So effort can ride in the same generated frontmatter as model; no parallel mechanism is needed on Claude Code. GSD models effort as a parallel resolver with the same precedence shape (`model-resolver.cts:628-691`) and per-host clamping (`model-catalog.cts:198-217`).

7. **Claude Code already degrades gracefully on disallowed values** (confidence: high)
 Docs: values from env/param/frontmatter are checked against an org `availableModels` allowlist; an excluded value is skipped and the subagent runs on the inherited model. So a wrong table entry cannot brick a spawn on Claude Code - worst case is `inherit` behavior.

8. **Caveat: Compass agents are project-scope, so all frontmatter fields apply** (confidence: high)
 Docs note plugin-scoped subagents ignore `hooks`/`mcpServers`/`permissionMode` (but not `model`). Compass sidesteps this entirely: setup copies agents into `.claude/agents/` (project scope), where every field including `model` and `effort` is honored.

### 3. GSD prior art (the verified reference design)

9. **GSD's single source of truth is a JSON catalog: agents x profiles + tier maps + per-host model maps** (confidence: high)
 `gsd-core/bin/shared/model-catalog.json`:
 - `agents`: per agent `{golden, balanced, budget, phaseType, routingTier}` (lines 133-169) - three cost profiles plus an abstract routing tier.
 - `adaptiveTierMap`: abstract `heavy/standard/light` -> `opus/sonnet/haiku` (lines 4-8).
 - `runtimeTierDefaults`: per host, tier -> concrete model id (+ optional `reasoning_effort`), e.g. codex `opus` -> `gpt-5.6-sol` xhigh (lines 9-100). Hosts without model selection carry explicit `null` entries (cline, kimi, cursor, windsurf... lines 45-94).
 - `providerPresets`: provider x tier x budget -> concrete model (lines 101-132).
 - Loaded and typed by `model-catalog.cts:30-158`; agent/tier constants derived at `model-catalog.cts:104-119`.

10. **GSD's resolution precedence (resolveModelInternal)** (confidence: high)
 `model-resolver.cts:313-407`, in order:
 - 1: `model_overrides[agent]` from project config (exact per-agent pin), line 319-325.
 - 2: tier = project `models[phaseType]` if valid, else the agent's slot in the chosen `model_profile` (quality/balanced/budget/adaptive/inherit), lines 327-340.
 - 2.5: `model_policy` provider preset maps tier -> concrete id; on Claude the id is mapped BACK to an alias because the Agent tool takes aliases, warn-and-fall-through if unmappable (lines 342-365).
 - 3: non-Claude runtime -> `runtimeTierDefaults[runtime][tier].model` verbatim (lines 367-371).
 - 4: the omit gate (finding 15).
 - 5: Claude-native default: return the tier alias; full IDs only under explicit `resolve_model_ids: true` (lines 388-406).

11. **GSD's effort is a parallel table with the same shape, not a column bolted onto model** (confidence: high)
 `resolveEffortInternal` (`model-resolver.cts:628-691`): invocation override -> `effort.agent_overrides[agent]` -> `effort.routing_tier_defaults[agentTier]` -> `effort.default` -> hardcoded `high`. Vocabulary `minimal/low/medium/high/xhigh/max` (line 605), clamped per host (`claude` maps `minimal`->`low`; `codex` maps `max`->`xhigh`, `model-catalog.cts:198-217`). Keying effort defaults by the agent's routing tier means one knob tunes classes, with per-agent exceptions.

12. **GSD keeps resolve-model output parseable: result JSON on stdout, warnings on stderr** (confidence: high)
 `model-resolver.cts:190-195` - "MUST go to stderr - resolve-model's JSON result is parsed from stdout." Warn-dedupe sets prevent stderr spam across repeated resolutions (lines 185-221). `formatAgentToModelMapAsTable` (`model-catalog.cts:167-177`) renders the human-readable full-roster listing (GSD's equivalent of a `compass models` view).

### 4. Table proposal for Compass (options for the ADR)

13. **Location and format options** (confidence: medium - design synthesis grounded in existing conventions)
 - Built-in defaults: a data file shipped with the CLI, `plugin/cli/` (mirrors GSD's catalog co-located with the resolver, `model-catalog.cts:30-33`). YAML fits Compass's existing `meta/*.yaml` conventions; the CLI already parses YAML-ish frontmatter in `vaultlib.py`.
 - Project override: `.compass/meta/models.yaml` - reuses the `meta/` convention established by `plugin.yaml` and `lessons-catalog.yaml` (setup SKILL.md:93-105), satisfying the spec constraint "reuses existing config conventions."
 - Env override: `COMPASS_MODEL_PROFILE` (whole-policy dial) and optionally `COMPASS_MODEL_<AGENT>`; note `CLAUDE_CODE_SUBAGENT_MODEL` already sits above everything on Claude Code regardless (finding 4).
 - Shape (GSD-derived, host-composable): per agent `{tier, effort}`, an abstract tier map, and a per-host catalog `hosts.<host>.<tier> -> model id or null`.

14. **Tier vocabulary: abstract tiers are the SPEC-006-compatible form; Claude aliases are the zero-mapping shortcut** (confidence: high for the constraint, medium for the choice)
 - [[SPEC-006-multi-host-agent-cli-support]] plus SPEC-008's own constraint (spec line 68) require resolving against a per-host catalog, i.e. the table itself must not hardcode one vendor's ids.
 - GSD demonstrates both layers coexisting: abstract `routingTier` (`heavy/standard/light`) for policy, and per-host `runtimeTierDefaults` for concretization; on Claude the concrete step is skipped because the host natively accepts the alias vocabulary (`model-resolver.cts:388-406`).
 - Option A: abstract `strong/balanced/cheap/inherit` + host catalog (Claude entry: strong->opus, balanced->sonnet, cheap->haiku). Option B: use Claude aliases as the tier names (GSD's choice) - zero mapping on the primary host, but the vocabulary is vendor-flavored, which SPEC-006 explicitly flags.

15. **Candidate built-in defaults for the Compass roster** (confidence: medium - grounded in GSD's analogous agents and SPEC-008's success criteria, not measured)
 SPEC-008 success criteria pin three rows: locators -> cheap; planner, validator, reviewer -> strong (spec line 59).

 | Agent | Tier | Effort | Justification |
 |---|---|---|---|
 | planner | strong | high | Spec-mandated; GSD planner is opus even on the balanced profile (`model-catalog.json:134`) |
 | validator | strong | high | Spec-mandated final quality gate; adversarial judgment |
 | reviewer | strong | high | Spec-mandated; consolidating N agents' conflicting outputs is the highest-judgment step |
 | debug | strong | high | Root-cause analysis; GSD routes its debugger to the heavy tier (`model-catalog.json:140`) |
 | builder | balanced | high | Code writing at scale; GSD executor is sonnet on balanced (`model-catalog.json:136`) |
 | researcher | balanced | high | Evidence gathering; GSD researchers are sonnet on balanced (`model-catalog.json:137-138`) |
 | tester | balanced | high | Adversarial test writing needs competence, not top-tier reasoning; GSD verifier is sonnet |
 | codebase-analyzer | balanced | medium | Reads and explains code, bounded scope (today: sonnet, `codebase-analyzer.md:6`) |
 | vault-analyzer | balanced | medium | Same class as codebase-analyzer (today: sonnet) |
 | pattern-finder | balanced | medium | Snippet extraction, no critique (today: sonnet) |
 | codebase-locator | cheap | low | Spec-mandated cheap; grep/glob only, never reads contents (`codebase-locator.md:3`) |
 | vault-locator | cheap | low | Same class; GSD's analogous codebase-mapper is haiku on balanced (`model-catalog.json:141`) |
 | pr-describe | cheap | medium | Mechanical artifact-to-prose assembly with verification commands, low judgment |
 | (SPEC-005 summary job) | cheap | low | Hard falsification criterion: "anything but a small/cheap model" fails SPEC-005 (spec line 51) |

16. **Precedence chain proposal** (confidence: medium)
 Deterministic, fewest-first: built-in default (ships with CLI) -> project override (`.compass/meta/models.yaml`, whole-profile and per-agent keys) -> env (`COMPASS_MODEL_*`). Unresolvable at every rung -> `inherit` + default effort. On Claude Code the host itself then applies its own chain (finding 4) above whatever Compass emitted; documenting that interaction in the ADR avoids "my table entry was ignored" confusion when `CLAUDE_CODE_SUBAGENT_MODEL` is set.

### 5. CLI surface

17. **Command proposal and where it slots into the existing CLI** (confidence: high for the mechanics, medium for the naming)
 - `compass resolve-model <agent>`: prints resolved `{model, effort}` - result on stdout, warnings on stderr, mirroring GSD's parse contract (finding 12). Unknown agent or missing table -> print `inherit` with default effort and exit 0.
 - `compass models`: prints the full resolved roster table for humans (GSD analog: `formatAgentToModelMapAsTable`).
 - Registration is a two-line change: add entries to `COMMAND_SPECS` (`plugin/cli/maincli.py:18-31`) plus `commands/resolve_model.py` / `commands/models.py` exposing `run(args)` (`maincli.py:87-93` dispatch).
 - Never-exit-2 is already structural: `cli_err` clamps 2->1 (`maincli.py:51-58`), the parser clamps (`maincli.py:61-70`), and dispatch catches all exceptions (`maincli.py:110-114`).

18. **Install/update hook-in: a post-copy apply step, because setup copies verbatim today** (confidence: high)
 Setup and update currently `cp` templates untransformed (finding 3). The install-time lever therefore needs one new step after the copy: e.g. `compass apply-models`, which rewrites the `model:` and `effort:` frontmatter lines of the generated `.claude/agents/*.md` from the resolved table. Constraints from existing lessons: touch ONLY the known Compass agent files, never user-authored agents ([[LESSON-installer-removes-only-what-it-installed]], learned when `/compass:update` deleted user skills - commit 7ea50b8); write LF ([[LESSON-windows-crlf-breaks-linux-container-scripts]], [[LESSON-autocrlf-churns-lf-writers]]). Because Claude Code hot-reloads `.claude/agents/` (finding 5), re-running apply after editing the project override takes effect without restart.

### 6. Degradation on hosts without model selection

19. **GSD's omit gate: hosts without native aliases emit no model at all** (confidence: high)
 - The installer writes `resolve_model_ids: "omit"` into shared defaults for every runtime lacking native model aliases (`model-resolver.cts:42-49`).
 - When the gate applies, `resolveModelInternal` returns `''` - the spawn simply carries no model and the host default rules (`model-resolver.cts:383-386`).
 - The gate is runtime-aware to prevent cross-poisoning: an "omit" from the shared machine-wide file applies only when the ACTIVE runtime genuinely lacks aliases; a project-explicit "omit" always wins (`model-resolver.cts:100-125, 379-384`). Active runtime precedence: env -> project config -> per-install marker file -> `'claude'` (`model-resolver.cts:88-99`).
 - In the catalog, alias-less hosts are explicit `null` rows (`model-catalog.json:45-94`), so tier resolution finds nothing and the omit path is reached; only `claude` is in `RUNTIMES_WITH_NATIVE_ALIASES` (`model-resolver.cts:61`).

20. **Same principle for effort: unknown host renders nothing, never a guessed flag** (confidence: high)
 `EFFORT_ARGV` covers only hosts with a verified effort flag; "a host absent from this table renders null, so an undeclared or undocumented host silently gets nothing rather than a guessed flag" (`model-catalog.cts:237-266`); `renderEffortArgv` returns empty argv for any unrecognized surface and never throws (`model-catalog.cts:281-299`).

21. **Compass equivalent** (confidence: medium - design synthesis)
 Host catalog entry null/absent for a tier -> `resolve-model` prints `inherit`; the install-time apply step then either writes `model: inherit` or omits the field entirely (identical semantics on Claude Code per finding 4; omission is the safer form for hosts where `inherit` is not a recognized token). Effort likewise: omit the field on hosts with no effort surface. This satisfies the spec's falsification criterion "a host without model selection breaks instead of falling back to its default" by construction, and matches SPEC-006's tolerate-missing-mechanisms constraint (SPEC-006 line 50).

## Contradictions

- `plugin/skills/checkup/SKILL.md:19` warns when an agent lacks `model`/`effort`, but `researcher.md` and `reviewer.md` ship without `model:` - the current templates fail Compass's own health check expectation.
- SPEC-008 success criterion says locators resolve to a cheap model; today all five locator/analyzer agents are `sonnet` and `haiku` appears nowhere in `plugin/` - the cheap tier is currently unused.
- [[ADR-005-compass-cli-for-mechanical-work]] pushes mechanical work off the agent budget, while GSD's spawn-time lever (orchestrator runs resolve-model per spawn) puts resolution ON the budget. The two levers are not equivalent under Compass's goals; the ADR must pick or combine (e.g. install-time as primary, spawn-time param as escape hatch).

## Gaps

- Whether Compass's skill-driven spawns can reliably pass the Agent tool's per-invocation `model` parameter has not been tested in this repo (docs confirm the parameter exists; GSD uses it in production). A 5-minute experiment - spawn a trivial subagent with `model: haiku` param and check the transcript - would verify.
- Whether hook-spawned `type: agent` hooks (Stop / SubagentStop in `plugin/hooks/hooks.json:42-66`) can be assigned a model is undocumented; if not, those two judgment hooks stay outside the table's reach.
- Kimi Code's and Codex's actual model-selection surfaces are still unverified empirically (SPEC-006 open question); the null-row degradation design covers them either way.
- The cost saving from moving locators to `haiku` is asserted, not measured; SPEC-008's hypothesis ("no loss of output quality") needs a before/after check on locator output quality.

## Recommendation

For the ADR/planner to decide; the evidence points to:

1. **Primary lever: install-time frontmatter injection.** A `compass apply-models` step in setup/update rewrites `model:`/`effort:` in the 13 generated `.claude/agents/*.md` from the resolved table. Zero tokens per spawn, deterministic, hot-reloaded by Claude Code, consistent with ADR-005. Spawn-time `model` param remains available as a documented per-invocation escape hatch, and `CLAUDE_CODE_SUBAGENT_MODEL` as the user's global one.
2. **Abstract tier vocabulary** (`strong/balanced/cheap/inherit`) with a per-host catalog mapping tiers to host tokens (Claude: `opus/sonnet/haiku`), per the SPEC-006 constraint. Effort in the same per-agent table row (one file, two columns), with per-host omission when unsupported.
3. **Files:** built-in defaults ship with the CLI under `plugin/cli/`; project override at `.compass/meta/models.yaml`; precedence built-in -> project -> env, bottoming out at `inherit`.
4. **CLI:** `compass resolve-model <agent>` (stdout result, stderr warnings, exit 0 always) and `compass models` (human table), registered in `COMMAND_SPECS`.
5. **Defaults:** the roster table in finding 15 - strong for planner/validator/reviewer/debug, balanced for builder/researcher/tester/analyzers/pattern-finder, cheap for the two locators, pr-describe, and the SPEC-005 summary job.
6. **Cleanup in the same plan:** remove the model prose from `methodology/SKILL.md:271`, align `checkup` to validate against the table instead of per-file presence, and add the missing rows for researcher/reviewer.

## Raw Evidence

<details>
<summary>Full evidence log</summary>

- Agent frontmatter inventory: `plugin/templates/agents/*.md` (13 files), grep `^model:` across `plugin/` - 12 hits (5 sonnet, 6 inherit, 1 in rules template); researcher.md and reviewer.md have no model field. All 13 have `effort: high`.
- Installed copies: `.claude/agents/` contains the same 13 files (verbatim `cp` per setup SKILL).
- Setup copy step: `plugin/skills/setup/SKILL.md:45-91` ("Use Bash `cp` only... The template content must never pass through your context window"); update copy step: `plugin/skills/update/SKILL.md:40-62`.
- Claude Code docs (code.claude.com/docs/en/sub-agents, cached fetch 2026-07-23): frontmatter table (`model` row: "sonnet, opus, haiku, fable, a full model ID... or inherit. Defaults to inherit"; `effort` row: "Options: low, medium, high, xhigh, max"); "Choose a model" resolution order (env var -> per-invocation param -> frontmatter -> main conversation); `availableModels` skip-and-inherit; agents-dir file watching; plugin-scope field restrictions (model unaffected).
- GSD source (scratchpad clone `gsd-core/src/`): `model-resolver.cts:313-407` (resolveModelInternal precedence), `:42-125` (omit gate + runtime marker), `:174-182` (CLAUDE_POLICY_ID_TO_ALIAS, CLAUDE_AGENT_ALIASES incl. fable), `:186-195` (stdout/stderr contract), `:605-691` (effort resolver), `:455-506` (dynamic routing tier ladder); `model-catalog.cts:104-135` (derived maps), `:160-165` (nextTier light/standard/heavy), `:167-187` (roster table renderers), `:198-217` (EFFORT_RENDERING clamps), `:237-299` (EFFORT_ARGV + renderEffortArgv); `gsd-core/bin/shared/model-catalog.json:1-170` (full catalog incl. null host rows 45-94, agents map 133-169).
- Compass CLI: `plugin/cli/maincli.py:18-31` (COMMAND_SPECS), `:51-58`/`:61-70`/`:110-114` (never-exit-2 clamps).
- SPEC-005 model mentions: `.compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md:34-35, 51`.
- Hooks: `plugin/hooks/hooks.json:42-66` (Stop and SubagentStop are `type: agent` with no model field).
- Lessons applied: `LESSON-installer-removes-only-what-it-installed`, `LESSON-windows-crlf-breaks-linux-container-scripts`, `LESSON-autocrlf-churns-lf-writers`, `LESSON-no-agent-bookkeeping`.

</details>
