---
title: "Handoff: dsh host shipped through v0.22.0; Wave 6 zero-decision queued"
type: handoff
status: active
area: distribution
tags: [handoff, dsh, multi-host, zero-decision]
summary: "PLAN-017 waves 1-5 shipped (v0.19-0.22): dsh is a native host, cold start works after one apply; reopened for Wave 6 - SPEC-006 D-05 demands zero user decisions (no roster question, dsh-first bootstrap); tasks scoped, rig standing in the scratchpad"
created: 2026-09-05
updated: 2026-09-05
git_branch: master
git_commit: "6b7435b"
plan: "[[PLAN-017-dsh-host-support]]"
---

# Handoff: dsh host shipped through v0.22.0; Wave 6 zero-decision queued

## Start Here
1. [[specs/distribution/SPEC-006-multi-host-agent-cli-support]] - D-05 is the human's bar, verbatim; D-01..04 are landed
2. [[PLAN-017-dsh-host-support]] - waves 1-5 elaborated with everything learned; `## Later` holds Wave 6's three intent lines
3. [[research/distribution/RESEARCH-dsh-live-probes]] - every live-verified dsh fact; treat it as the source of truth over re-derivation
4. `plugin/cli/hostlib.py` - all materializers and the profile installer live here

## Session Summary
PLAN-017 went from planning to shipped across v0.19.0-v0.22.0: hooks bridge, skills, native agents with model routes, rules fold, host-aware doctor, dsh capture worker, and a global auto-installed bundle - each wave suite-green and live-verified under both hosts. The human then raised the final bar (D-05): the user must not know or decide ANYTHING - either host, either order, it just works. Wave 6 is scoped for that and nothing of it is built.

## Tasks
| Task | Status | Notes |
|------|--------|-------|
| Waves 1-5 (TASK-001..014 + cold start) | done | evidence in the probes doc; 930 tests green at 6b7435b |
| TASK-015 auto host detection | scoped | kill the roster question; dsh-on-machine triggers materialization |
| TASK-016 dsh-first bootstrap | scoped | the hard one - see Context |
| TASK-017 both-direction acceptance | scoped | fresh projects, zero prompts, both orders |

## Learnings
- A config value duplicated into skill prose is a copy a code sweep misses: TASK-014's matcher had a fourth copy in the update skill (capture-note filed).
- pnpm `file:` installs snapshot; the installer now refreshes copies on every apply, so never rely on editing a bundle source in place.

## Action Items
1. [ ] Elaborate + build TASK-015: `hostlib.read_hosts` roster becomes automatic detection (dsh on PATH or harness home exists); remove the setup skill's "ask which hosts" instruction; hostless machines must see zero dsh writes (tests exist for today's default - repoint them).
2. [ ] Probe then build TASK-016 (design sketch, unverified): the global bundle mounts a SECOND `hooks-claude-code` instance with an ABSOLUTE `configPath` at `<dsh-home>/compass-bootstrap-hooks.json` (generated), whose SessionStart command runs a bootstrap from a CLI copy the bundle itself carries; the bootstrap materializes the launch-cwd project iff it holds `.compass/`, else no-ops. Verify: two bridge instances coexist (distinct ids), SessionStart fires before project hooks exist, bootstrap materializes, SECOND session in the same project is fully wired. Alternative if two instances collide: one machine-level configPath whose file merges bootstrap + a dispatcher.
3. [ ] TASK-017 acceptance both directions on fresh projects; then close the plan again and ship (v0.23.0).

## Context for Resuming
- **The rig** (everything scratchpad-isolated, rebuild recipe in the probes doc): dsh 0.1.2-rc.1 via portable Node 24 at `<scratchpad>/node24` + `<scratchpad>/dsh-prefix/dsh`; `DSH_HOME=<scratchpad>/dsh-home` (headless profile carries the bundle); projects `dsh-rig/`, `fresh-project/`, `empty-folder/`. Scratchpad may be wiped between sessions - rebuild is ~5 minutes from the recipe.
- **The DeepSeek API key is the human's**: he exported `DEEPSEEK_API_KEY` in-session (2026-09-05); it is in no file. Ask him to `! export DEEPSEEK_API_KEY=...` again before any live dsh run.
- **Load-bearing dsh facts** (all live-verified, in the probes doc): hooks run under pwsh on win32 (commands must be dialect-neutral, absolute paths baked); SessionStart `source` is `"startup"`; a Stop block's reason becomes a real steer turn; one-shot headless tree-reaps detached workers; dsh-base already registers `subagents` + `spawn` (re-mount fails boot); tool filters fail loudly on unknown names (`pwsh` not `bash` on Windows); the bridge tolerates a missing relative `configPath` (inert in non-Compass folders).
- **Fleet safety**: everything ships inert - no existing project has a dsh roster; TASK-015's auto-detection changes that on machines WITH dsh, so its no-pollution guard is the critical test class.
- The dsh source clone lives in the scratchpad (`deepseek-harness/`); re-clone if wiped - several plan tasks cite file:line into it.
