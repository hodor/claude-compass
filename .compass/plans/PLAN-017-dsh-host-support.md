---
title: "DeepSeek Harness as a Compass Host"
type: plan
status: approved
approved: 2026-09-05
confidence: medium
area: distribution
tags: [multi-host, dsh, deepseek, materializers, hooks, bundles, dual-host, distribution]
created: 2026-09-05
updated: 2026-09-05
author: "planner"
summary: "dsh is a native Compass host from the one canonical plugin source (v0.19-0.22: materializers, model routes, doctor, capture worker, global auto-installed bundle, dual-host acceptance at 0 errors); reopened for Wave 6 - SPEC-006 D-05 zero-decision: no roster question, dsh-first bootstrap, both-direction acceptance"
depends_on: ["[[specs/distribution/SPEC-006-multi-host-agent-cli-support]]", "[[research/distribution/RESEARCH-deepseek-harness-fit]]", "[[specs/distribution/SPEC-008-central-model-resolution-table]]"]
lessons: ["[[LESSON-hook-payloads-observe-before-coding]]", "[[LESSON-self-update-corrections-lag-one-version]]", "[[LESSON-installer-removes-only-what-it-installed]]", "[[LESSON-revert-to-prove-a-regression-test]]", "[[LESSON-hook-if-clause-no-or]]", "[[LESSON-autocrlf-churns-lf-writers]]", "[[LESSON-hooks-load-only-from-settings]]", "[[LESSON-hook-cli-gate-stdin-on-flag]]"]
---

# DeepSeek Harness as a Compass Host

## Goal

Make DeepSeek Harness (`dsh`) a host Compass runs on natively, from the same `plugin/` source that serves Claude Code, so a developer working in either CLI - or both, in one project - gets the full pipeline against one shared `.compass/` vault. This plan implements [[specs/distribution/SPEC-006-multi-host-agent-cli-support]] D-01 through D-04, building on the fit assessment in [[research/distribution/RESEARCH-deepseek-harness-fit]]. The shape of the work is set by what that research found: the vault, the `compass` CLI, the hook loop, and the skill bundles carry over with configuration changes, while agents and rules have no dsh equivalent and must be generated at install time.

## The waves

**Wave 1 answers the three questions that decide whether the design survives contact with a real dsh.** The research read dsh's source but never ran it, and three of its load-bearing claims are inferences. First, nobody has authored a dsh profile bundle, so "ship a generated Compass profile" is an assumption about mechanics we have only read about. Second, Compass's capture loop depends on a Stop hook that can interrupt the agent and hand it a follow-up instruction; dsh implements that interruption differently from Claude Code, and the loop either survives the difference or the capture design needs rethinking on that host. Third, the same self-update hook has to recognise the start of a dsh session, and the value dsh reports there is unconfirmed. Alongside these, Wave 1 settles on paper which instruction file each host reads, so that a project holding both hosts never feeds the same rule text into a session twice. The wave ends when all three probes have produced a written answer and the design is either confirmed or amended.

**Later waves build what those answers license.** An install-time seam teaches setup, update, and self-update which hosts a project actually uses and refreshes every one of them together, so the two materializations can never drift to different Compass versions. On top of that seam sit the translators: skills reworded into dsh's frontmatter dialect and installed where dsh looks for them, the thirteen agent definitions compiled into dsh delegation tools, the rules folded into the instruction file dsh reads, and the model policy extended with a dsh column so an agent's tier resolves to a DeepSeek route instead of a Claude model name. The install doctor learns to check all of it. The final wave is the acceptance: one project, both CLIs, the whole pipeline driven from each, and a vault that is still correct afterwards.

## Prerequisites

- `dsh` installed and runnable wherever this plan is executed. It is absent from the Compass development machine as of 2026-09-05, which has Node v20.13.1. TASK-001 installs it, and every other Wave 1 task depends on that task.
- A checkout of the dsh source (`github.com/deepseek-ai/deepseek-harness`) for reference, since several tasks cite its internals by path and line. Clone it fresh rather than depending on an existing local copy.
- [[specs/distribution/SPEC-006-multi-host-agent-cli-support]] is approved and its decisions D-01..D-04 are settled. [[research/distribution/RESEARCH-deepseek-harness-fit]] is complete.

## Desired End State

A project can hold a Compass install for Claude Code, for dsh, or for both. One `compass self-update` run refreshes every host present, so the two can never sit on different versions. On dsh a user invokes Compass skills as slash commands, delegates to Compass agents as native dsh subagent tools, and the vault stays indexed by the same hook-driven `compass sync` that runs under Claude Code. Nothing in `plugin/` is authored twice: the per-host difference lives entirely in materializers that run at install time.

## What We're NOT Doing

- Kimi Code and Codex. Both are named in the spec; both wait until dsh proves the adapter seam.
- `subagent-claude-code`, dsh's ability to run a real Claude Code child. D-02 rules it out as the mechanism.
- Any change to the vault format, the pipeline stages, or the artifact schema.
- Publishing a Compass bundle to a package registry. The install channel stays the file copy that [[SPEC-020-compass-updates-itself]] describes.

## Phases

### Wave 1 (detailed): Probe the three unverified dsh mechanics

- [ ] TASK-001: Stand up a live dsh rig - install `dsh`, create a scratch project holding a `.compass/` vault with a current Compass install, and record the installed dsh version and its resolved harness home in the probe notes that TASK-002..004 append to - complexity: S, depends_on: none, files: [.compass/research/distribution/RESEARCH-dsh-live-probes.md], decisions: [SPEC-006-multi-host-agent-cli-support/D-01]
  - Automated verification: `dsh --version` prints a version; `python .claude/cli/compass doctor` in the scratch project exits 0.
  - Manual verification: a `dsh` session starts in the scratch project and responds to one trivial prompt.

- [ ] TASK-002: Author a minimal installable Compass profile bundle for dsh and prove the hook loop runs through it - a `package.json` declaring `dsh.bundle.patch` plus a `cordis.patch.yml` that mounts `hooks-claude-code` with `configPath` pointed at the project's `.claude/settings.json`, installed as a profile whose `dsh.profile.bundles` lists `@deepseek-ai/dsh-base` and the Compass bundle - complexity: M, depends_on: TASK-001, files: [.compass/research/distribution/RESEARCH-dsh-live-probes.md, plugin/hosts/dsh/bundle/package.json, plugin/hosts/dsh/bundle/cordis.patch.yml], decisions: [SPEC-006-multi-host-agent-cli-support/D-01, SPEC-006-multi-host-agent-cli-support/D-03], lessons: [LESSON-hooks-load-only-from-settings, LESSON-hook-cli-gate-stdin-on-flag, LESSON-autocrlf-churns-lf-writers]
  - The falsifiable claim: a hand-authored bundle of that shape loads under `dsh --profile`, and a vault file written from inside a dsh session fires `compass sync`. The design proceeds as drafted only if it holds; if the bundle mechanism cannot point at a per-project hooks file, the plan needs a different way to reach the hook loop.
  - Bundle and profile contracts are defined in the dsh source at `packages/boot/app-boot/src/profile.ts:50-61`; resolution runs through `loadProfile` (`profile.ts:805-844`) and `resolveBundleDir` (`profile.ts:778-789`); `packages/bundle/base/` is the in-tree example to copy. The bridge's config schema is at `packages/hooks/hooks-claude-code/src/index.ts:72-78`, where `configPath` is required and read once at launch.
  - Automated verification: `dsh --profile compass` starts without error; after a write to `.compass/specs/SPEC-001-probe.md` from a dsh session, `.compass/index.md` contains a link to that file and `git diff` shows sync regenerated it.
  - Manual verification: the bundle's file list is small enough to generate mechanically from a template - confirm no hand-written step would have to be repeated per project.

- [ ] TASK-003: Probe dsh's Stop-hook block contract and its SessionStart source values against a live run, and record whether Compass's capture loop and self-update hook survive unchanged - complexity: M, depends_on: TASK-002, files: [.compass/research/distribution/RESEARCH-dsh-live-probes.md], decisions: [SPEC-006-multi-host-agent-cli-support/D-01, SPEC-006-multi-host-agent-cli-support/D-02], lessons: [LESSON-hook-payloads-observe-before-coding]
  - Two falsifiable claims. First: `compass capture-check`'s `{"decision": "block", "reason": ...}` on stdout (`plugin/cli/commands/capture_check.py:123`) causes dsh to continue the turn with the reason delivered to the model, the way it does under Claude Code. dsh reaches that outcome by a different route - a blocking result becomes `agent.steer()`, injecting a user message rather than halting the run (`packages/hooks/hooks-claude-code/src/index.ts:270-277`), it parses stdout JSON only on exit code 0 (`packages/hooks/hook-protocol/src/codec.ts:59-89`), it never sets `stop_hook_active` (`index.ts:344-346`), and `continue: false` is recorded but not acted on (`index.ts:189`). Confirm the capture pass actually runs, and confirm nothing in Compass's loop guard depends on `stop_hook_active`. Second: the `source` string dsh passes to SessionStart (`index.ts:206-215`, `index.ts:332-334`) is unenumerated in its own source; capture the literal value so the `startup` matcher on the `compass self-update` hook entry can be widened correctly rather than guessed.
  - Automated verification: a scripted dsh session with a forced-due capture opportunity produces a `worker-finished` or `worker-failed` row in the capture ledger; a `dsh` session start writes a self-update log line or an observed no-op with the captured `source` value recorded verbatim in the probe notes.
  - Manual verification: read the transcript of the blocked turn and confirm the model received the capture instruction as a turn, not as discarded output.

- [ ] TASK-004: Build the instruction-surface placement matrix - for each host, name every file it loads as instructions, and assign each Compass instruction surface (the three rules files, the CLAUDE.md Compass section, agent personas, skill bodies) to exactly one slot per host, so no text is delivered twice into one context - complexity: M, depends_on: TASK-001, files: [.compass/research/distribution/RESEARCH-dsh-live-probes.md], decisions: [SPEC-006-multi-host-agent-cli-support/D-04]
  - The falsifiable claim: a single assignment exists that gives every host every instruction exactly once. dsh's instruction loader takes same-directory filename candidates `['AGENTS.md', 'CLAUDE.md']` walking up to a `.git` root and never loads a directory, so `.claude/rules/*.md` reaches it only by being folded into one of those two files - which means a dual-host project where both hosts read `CLAUDE.md` would double the rules unless the matrix separates the surfaces. If no assignment satisfies every host, D-04's "exactly once" invariant needs an amendment from the human before the materializers are built.
  - Automated verification: a check script reads the matrix and asserts that no instruction surface maps to two files a single host loads.
  - Manual verification: start one dsh session and one Claude Code session in the same scratch project and confirm from each transcript that the rules text appears once.

**Pause point:** when automated verification passes, wait for the human to confirm manual verification succeeded before the next wave. The three probes may amend the materializer design; the later waves are written against the design as drafted.

### Wave 2 (detailed): the host seam and the shared manifest

Every task in this and later waves verifies two ways, by the human's ruling at the Wave 1 gate: the full CLI test suite passes (no regressions), and the change is exercised live under BOTH Claude Code and dsh before the wave closes.

  - Automated verification: `pytest plugin/cli/tests/test_self_update.py` passes with a new case asserting the registered matcher; reverting the `merge_settings` change alone makes that case fail.
  - Manual verification: `.claude/settings.json` in this repo shows the widened matcher after a self-update run, and a vault write from Claude Code still triggers sync.

- [ ] TASK-005: the host seam - `hostlib.py` reads the project's host roster from `.compass/meta/plugin.yaml` (`hosts:`, defaulting to `[claude-code]` when absent so every existing install behaves exactly as today), and `self_update._apply` becomes a per-host loop: the claude-code manifest is today's copy unchanged; the dsh manifest generates `.dsh/hooks.json` from `plugin/hooks/hooks.json` by the Wave 1 transform (dialect-neutral `python "${CLAUDE_PROJECT_DIR}/..."` commands, lowercase-widened matchers) so one run refreshes every listed host and no two can sit on different versions - complexity: M, depends_on: TASK-014, files: [plugin/cli/hostlib.py, plugin/cli/commands/self_update.py, plugin/cli/tests/test_hostlib.py, plugin/cli/tests/test_self_update.py, plugin/skills/setup/SKILL.md, plugin/skills/update/SKILL.md], decisions: [SPEC-006-multi-host-agent-cli-support/D-03, SPEC-006-multi-host-agent-cli-support/D-04], lessons: [LESSON-self-update-corrections-lag-one-version, LESSON-installer-removes-only-what-it-installed]
  - Automated verification: new tests prove a `hosts: [claude-code, dsh]` project gets both materializations from one `_apply` and a hostless plugin.yaml gets only today's behavior; the generated `.dsh/hooks.json` parses, carries no sh-dialect syntax, and its matchers include the lowercase names; full suite green.
  - Manual verification: in the rig, repoint the bundle's `configPath` at the generated `.dsh/hooks.json`, then a vault write inside a dsh session updates the index AND a `claude -p` write in the same rig updates it too - both hosts, one project, one install.

**Wave 2 pause point:** same contract as Wave 1 - suite green and both live checks pass before Wave 3 elaborates.

### Wave 3 (detailed): dsh sessions speak Compass

- [ ] TASK-007: the tool-name mapping table in `hostlib` - Claude tool names from agent `tools:` frontmatter translated to dsh tool names (Read->read, Write->write, Edit->edit, Bash->bash, Grep->grep, Glob->glob, ...), derived from dsh's generated tool catalog; a name with no dsh equivalent maps to nothing and is reported, never guessed - complexity: S, depends_on: none, files: [plugin/cli/hostlib.py, plugin/cli/tests/test_hostlib.py], decisions: [SPEC-006-multi-host-agent-cli-support/D-02]
  - Automated verification: table covers every name used across the 13 shipped agents' `tools:` fields or explicitly marks it unmapped; full suite green.
  - Manual verification: the unmapped set is reviewed - nothing in it should surprise (host-specific tools like AskUserQuestion are expected there).

  - Automated verification: materialized skills parse under dsh's documented frontmatter rules (kebab name, description present); non-Compass files already in `.dsh/skills/` are never touched; full suite green.
  - Manual verification: a live dsh session lists the `compass-*` skills in its catalog and loads one on request.

- [ ] TASK-008: the bundle generator - `hostlib` emits the installable Compass bundle (hooks mount, the skill capability rows when the profile lacks them, and one delegation-tool row per Compass agent with persona from the agent markdown and tool filter through the TASK-007 map), written to `.dsh/compass-bundle/`; probe whether a relative `configPath` resolving at launch cwd lets ONE global profile serve every project, else the bundle stays per-project - complexity: L, depends_on: TASK-007, files: [plugin/cli/hostlib.py, plugin/cli/tests/test_hostlib.py, plugin/hosts/dsh/], decisions: [SPEC-006-multi-host-agent-cli-support/D-02, SPEC-006-multi-host-agent-cli-support/D-03], lessons: [LESSON-hook-payloads-observe-before-coding]
  - Automated verification: the generated bundle round-trips dsh's manifest contract (package.json `dsh.bundle.patch` + patch YAML parse); agent rows carry persona text and mapped tool filters; full suite green.
  - Manual verification: in the rig, `dsh plugin add` of the generated bundle boots; a dsh session delegates to one Compass agent natively and the hook loop still runs.

**Wave 3 pause point:** same contract - suite green, both hosts live, before Wave 4 (model column, rules folding, doctor, capture worker, acceptance).

### Wave 4 (detailed): rules, models, doctor, capture, acceptance

Ruling for TASK-012, delegated by the human ("do what will be the best for all compass users"): `claude` remains the preferred worker binary wherever present; a dsh-rostered project without `claude` spawns a dsh headless worker instead; a project with neither headless host relies on the proven steer fallback - and doctor names the project's capture posture so no path is silent.

- [ ] TASK-010: rules folded into a fenced managed section of `AGENTS.md` per the Wave 1 matrix - existing user content never touched, section regenerated in place on every apply - complexity: M, depends_on: none, files: [plugin/cli/hostlib.py, plugin/cli/tests/test_hostlib.py, plugin/cli/commands/self_update.py], decisions: [SPEC-006-multi-host-agent-cli-support/D-03, SPEC-006-multi-host-agent-cli-support/D-04], lessons: [LESSON-installer-removes-only-what-it-installed]
  - Automated verification: fold into an existing AGENTS.md preserves user text byte-for-byte outside the markers; refold is idempotent; suite green.
  - Manual verification: a dsh session quotes a rules sentence; a Claude Code session in the same project sees the rules exactly once (via .claude/rules, not AGENTS.md).
- [ ] TASK-009: a dsh column in the model policy - tiers resolve to DeepSeek routes written into the generated bundle's delegation rows as `agentOptions`, never into agent frontmatter - complexity: M, depends_on: none, files: [plugin/cli/modelslib.py, plugin/cli/hostlib.py, plugin/cli/tests/test_hostlib.py], decisions: [SPEC-006-multi-host-agent-cli-support/D-02, SPEC-006-multi-host-agent-cli-support/D-03]
  - Automated verification: bundle rows carry per-agent model routes from the table; overrides in meta/models.yaml respected; suite green.
  - Manual verification: a delegation in the rig runs the child on the routed model (visible in the child's declared model).
- [ ] TASK-011: host-aware doctor - per-host checks: dsh materializations present and current, bundle snapshot in the profile not stale against the generated bundle version, version skew between hosts, capture posture named - complexity: M, depends_on: TASK-010, files: [plugin/cli/commands/doctor.py, plugin/cli/tests/test_doctor.py], decisions: [SPEC-006-multi-host-agent-cli-support/D-04]
  - Automated verification: fixture projects with skew/stale/missing artifacts each produce the named FAIL/WARN; clean dual-host fixture passes; suite green.
  - Manual verification: doctor in the rig reports the real install truthfully.
- [ ] TASK-012: host-aware capture worker - worker resolution tries `claude`, then (dsh rostered) `dsh --profile headless`, else latches no-headless as today; the dsh invocation shape verified end-to-end by a standalone worker run producing a worker-finished row - complexity: M, depends_on: none, files: [plugin/cli/commands/capture_worker.py, plugin/cli/tests/test_capture_worker.py], decisions: [SPEC-006-multi-host-agent-cli-support/D-02], lessons: [LESSON-headless-worker-denies-tools-silently, LESSON-hook-payloads-observe-before-coding]
  - Automated verification: resolution order unit-tested; suite green.
  - Manual verification: in the rig with `claude` masked, a forced opportunity's worker completes through dsh and writes its ledger row; the one-shot reap remains documented, not "fixed".
- [ ] TASK-013: live dual-host acceptance - one project, both CLIs, the pipeline exercised from each, vault correct afterwards - complexity: M, depends_on: TASK-009, TASK-010, TASK-011, TASK-012, files: [.compass/research/distribution/RESEARCH-dsh-live-probes.md], decisions: [SPEC-006-multi-host-agent-cli-support/D-01, SPEC-006-multi-host-agent-cli-support/D-04]
  - Automated verification: after both drives, `compass validate` reports 0 errors in the rig and sync's index matches the artifacts on disk.
  - Manual verification: the human reviews the acceptance transcript summary at the plan's close.

## Wave 6: zero-decision (SPEC-006 D-05)

The plan reopens for D-05: the user must not know or be forced to decide anything - either host, either order, no setup question. Known gaps against that bar: the `hosts:` roster is opt-in and setup asks for it; a project never opened in Claude Code cannot bootstrap its dsh materializations.

- [x] TASK-015: automatic host detection replaces the roster question - `hostlib.dsh_available()` (binary on PATH, or the harness home directory existing) and `hostlib.effective_hosts(vault_root)`: the plugin.yaml roster with `dsh` added when the machine has it and dropped when it does not - the machine is the truth for dsh, so a dsh-less machine sees zero dsh-shaped writes even against an explicit roster, and unknown host names still pass through verbatim. `self_update._apply`, doctor's host rows, and the capture worker's binary resolution all consume `effective_hosts`; the setup skill stops writing `hosts:` and stops asking; the update skill's regeneration snippet gates on `effective_hosts` - complexity: M, depends_on: none, files: [plugin/cli/hostlib.py, plugin/cli/commands/self_update.py, plugin/cli/commands/doctor.py, plugin/cli/commands/capture_worker.py, plugin/cli/tests/test_hostlib.py, plugin/cli/tests/test_self_update.py, plugin/cli/tests/test_doctor.py, plugin/cli/tests/test_capture_worker.py, plugin/cli/tests/test_overlay.py, plugin/skills/setup/SKILL.md, plugin/skills/update/SKILL.md], decisions: [SPEC-006-multi-host-agent-cli-support/D-05], lessons: [LESSON-installer-removes-only-what-it-installed, LESSON-sweep-misses-config-in-skill-prose]
  - Automated verification: a hostless plugin.yaml with detection true gets the full dsh materialization from one `_apply`; detection false gets zero dsh-shaped writes even when the roster names dsh; every test that reaches `_apply`, doctor's host rows, or worker resolution pins detection so the suite is machine-independent; full suite green.
  - Manual verification: in the rig (DSH_HOME set), one apply on a hostless fresh project materializes dsh with no question asked; on the dev machine outside the rig, this repo's own apply leaves no `.dsh/` behind.
  - Landed 2026-09-05, 937 tests green. Live: a project with `hosts: [claude-code, dsh]` committed applied on a dsh-less environment with zero dsh writes; a hostless project on the rig materialized everything (hooks, 32 skills, AGENTS.md section, bundle 0.22.0 into the headless profile) with no question. The home-directory prong proved load-bearing immediately: the dev machine carries real dsh traces at `~/.dsh` (credentials, sessions) while no shell's PATH has the binary. `.dsh/` and `AGENTS.md` joined this repo's .gitignore as generated installs. The old capture-worker bar "claude-only roster never resolves dsh" inverted by design: the machine is the truth, so dsh-with-no-claude resolves dsh regardless of roster.
- [ ] TASK-016: dsh-first bootstrap - a Compass project whose first-ever session is dsh materializes itself: probe a second bridge mount in the global bundle pointed at a machine-level bootstrap hooks file (under the harness home, absolute path) whose SessionStart command runs a bootstrap from a CLI copy the bundle itself carries, materializing the launch-cwd project when it holds `.compass/` and doing nothing otherwise - files: [plugin/cli/hostlib.py, plugin/cli/commands/self_update.py], decisions: [SPEC-006-multi-host-agent-cli-support/D-05], lessons: [LESSON-hook-payloads-observe-before-coding, LESSON-scratch-vaults-need-compass-dir]
- [ ] TASK-017: zero-decision acceptance both directions - two fresh projects on the rig, one driven dsh-first and one Claude-Code-first, no prompts, no manual steps, both hosts working in both projects afterwards, validate 0 errors - files: [.compass/research/distribution/RESEARCH-dsh-live-probes.md], decisions: [SPEC-006-multi-host-agent-cli-support/D-05]

## Wave 5 elaborated (2026-09-05) - the cold-start bar

The human's closing requirement reopened the plan for one wave: "I just start deepseek on the same folder and it should just work." What stood in the way: the bundle was per-project and manually `dsh plugin add`-ed, re-added by hand after every update, and carried an absolute `projectDir` that would misfire from any other folder.

The shape that ships (v0.22.0): the bundle is global and project-agnostic - generated under the harness home (`$DSH_HOME` or `~/.dsh`) and copied by the installer into every profile there (as a `file:` dependency plus a `dsh.profile.bundles` entry, refreshed on every apply, so the pnpm-snapshot staleness class is gone and no manual step exists). Its hooks mount reads the launch cwd's own `.dsh/hooks.json`, whose commands now carry the project's absolute path baked in (no substitution tokens, no `projectDir`), making the mount inert in non-Compass folders - proven by a clean boot in an empty directory. Presets were investigated first and ruled out: dsh discovers them from global roots only, never per project.

Live bars: a fresh project with one apply answered everything in a single dsh session - vault write indexed by sync, delegation to `compass_vault-locator`, `compass-lessons` in the catalog; `claude -p` in the same project indexed its own write; the empty folder stayed clean; the rig needed exactly one re-apply to shed its token-era hooks file (the drift class doctor's host rows and normal self-update cover). A fourth unwidened copy of the PostToolUse matcher surfaced in the update skill's translation script and is fixed - TASK-014 counted three. 930 tests green.

## Wave 4 elaborated (2026-09-05) - plan complete

All five tasks landed (927 tests green) and every live bar passed; per-task evidence in [[research/distribution/RESEARCH-dsh-live-probes]]. The TASK-012 ruling held its shape in practice: `claude` first, a dsh-rostered claude-less environment completed a real extract pass through `dsh --profile headless` (worker-finished, correct anti-list judgment), and doctor names every project's capture posture. The acceptance closed the plan: one rig project, a spec written and a delegation run from dsh, a dependent plan written from Claude Code, both indexed by their own host's hooks, `compass validate` at 0 errors.

## Wave 3 elaborated (2026-09-05)

All three tasks landed (916 tests green) and every live bar passed in the rig: 32 `compass-*` skills in a dsh session's catalog and one loaded verbatim on request; a dsh session delegated to `compass_debug` natively and relayed the child's report; the hook loop ran through the generated bundle with a RELATIVE `configPath` - launch-cwd resolution works, so one global profile can serve every project. Claude Code is untouched by construction (materializers run only on a dsh roster, proven by test) and its hooks fired throughout the session. What the wave learned:

- dsh-base already registers the `subagents` service and the `spawn` provider; a bundle re-mounting either fails the boot loudly. The generated bundle carries only delegation-tool rows.
- Windows compositions register `pwsh` and no `bash`, and a tool filter naming an unregistered tool fails the child's start. `map_tools` resolves `Bash` per the generating machine's platform.
- `projectDir` must stay absolute in the generated bundle: without it the `${CLAUDE_PROJECT_DIR}` token reaches PowerShell unsubstituted. The bundle is per-project-generated, so the absolute path is correct by construction.
- Hyphenated delegation tool names (`compass_codebase-analyzer`) register fine.

## Wave 2 elaborated (2026-09-05)

Both tasks landed and both live bars passed: 904 tests green, and in one rig project a dsh vault write synced through the generated `.dsh/hooks.json` while a `claude -p` vault write synced through the widened settings matcher - one install, both hosts, one index. What the wave adds downstream:

- The roster lives at `plugin.hosts:` in plugin.yaml (nested under the `plugin:` mapping setup actually writes); absent means `[claude-code]`, and unknown names pass through so an older CLI never narrows a newer roster.
- pnpm `file:` bundle installs are snapshots: a bundle content change reaches the profile only through a fresh `dsh plugin add`. TASK-008's generated bundle must re-add on refresh; TASK-011's doctor learns stale-bundle detection.

## Later (intent only)

These carry intent, not instructions: each is written out in full only once the wave before it has landed and its outcome is known.

  - Automated verification: `pytest plugin/cli/tests/test_self_update.py` passes with a new case asserting the registered matcher; reverting the `merge_settings` change alone makes that case fail.
  - Manual verification: `.claude/settings.json` in this repo shows the widened matcher after a self-update run, and a vault write from Claude Code still triggers sync.

## Wave 1 elaborated (2026-09-05)

All four probes ran against a live dsh 0.1.2-rc.1 (portable Node 24, everything scratchpad-isolated); full evidence in [[research/distribution/RESEARCH-dsh-live-probes]]. What the wave learned, and what it changes downstream:

- The bundle mechanics hold: a 2-file installable bundle mounts the bridge and the vault-write -> `compass sync` -> index loop runs end to end. TASK-002's fallback risk (per-project profile generation) was not needed.
- New fact the research missed: dsh executes hooks through PowerShell on Windows, so the materializer emits a generated dsh hooks file in a dialect-neutral command form (`python "${CLAUDE_PROJECT_DIR}/..."` - parse-time substitution on dsh, env expansion under Claude Code) with lowercase-widened matchers, and `configPath` points at that file rather than `.claude/settings.json`. This folds into TASK-005/TASK-014's scope.
- SessionStart `source` is literally `"startup"`; the self-update hook needs no matcher change at all.
- The steer contract works: a Stop block's reason reaches the model as a real turn. But one-shot headless sessions reap the detached capture worker at process exit (dsh tree-kills hook children); the ladder's grace/respawn behavior was observed working as designed. TASK-012 inherits "headless dsh never completes a detached worker" as a design fact.
- The instruction matrix has a clean exactly-once assignment (rules -> `.claude/rules/` for CC and a managed `AGENTS.md` section for dsh; `CLAUDE.md` the only shared surface), measured by sentinel codewords from both hosts' own transcripts. D-04 needs no amendment. TASK-010 must fold into existing user `AGENTS.md` files, never overwrite.

Two written bars were met in substance rather than letter: TASK-003's "worker-finished or worker-failed row" could not exist on one-shot headless (the finding is precisely that the worker dies rowless), and TASK-004's "check script" became the sentinel measurement itself, which asserts the same invariant against reality instead of against a data file.

## Risks

- **dsh's bundle mechanism cannot point at a per-project hooks file.** Their source carries an open `TODO(per-session-hook-config)` and the bridge reads `configPath` once at launch. TASK-002 is the probe; if it fails, the fallback is a per-project profile generated at install time, which costs one more materializer.
- **The Stop-block difference breaks the capture loop.** dsh steers rather than halts, and never sets `stop_hook_active`. TASK-003 decides it. The degradation, if needed, is that capture on dsh runs at session start instead of at every Stop - explicit and documented, per the spec's requirement that any lost guarantee be visible rather than silent.
- **Two hosts, one vault, concurrent sessions.** D-04 leans on `compass sync` self-healing rather than locking. The dual-host acceptance is where that assumption meets a real double write.
- **A correction shipped in the materializer runs under the previous updater first.** Anything that changes how the install applies itself takes effect one version late; the version that introduces per-host manifests will refresh only the Claude Code side on the machines that receive it ([[LESSON-self-update-corrections-lag-one-version]]).

## Inherited Questions (from spec)

The spec's open questions concern Kimi Code and Codex, which this plan does not touch. Its dsh-specific unknowns, carried in from [[research/distribution/RESEARCH-deepseek-harness-fit]], are resolved here rather than deferred: bundle authoring is TASK-002, the Stop and SessionStart semantics are TASK-003, and the headless capture worker is TASK-012, which may land as a documented degradation rather than a port.
