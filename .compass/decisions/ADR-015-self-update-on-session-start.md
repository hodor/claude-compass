---
title: "A SessionStart Hook Runs compass self-update: Mandatory, sha-Gated, Local-Source Aware, Never Blocking"
type: decision
status: accepted
confidence: high
area: methodology
tags: [update, hooks, session-start, cli, distribution, zero-touch]
created: 2026-08-28
updated: 2026-08-28
author: "orchestrator"
summary: "SessionStart(startup) runs compass self-update: ls-remote sha gate, clone-and-apply replicating the update skill mechanically, dev repos copy from local plugin/, one context line on update, silence and exit 0 on every failure"
depends_on: ["[[SPEC-020-compass-updates-itself]]", "[[RESEARCH-self-update-surfaces]]", "[[compass-cli/decisions/ADR-005-compass-cli-for-mechanical-work]]"]
---

# A SessionStart Hook Runs compass self-update

## Context

[[SPEC-020-compass-updates-itself]]: updating must stop being a human chore, and D-01 makes it mandatory - no opt-out, no pin. [[RESEARCH-self-update-surfaces]]: the whole `/compass:update` flow is already mechanical; SessionStart(startup) is a proven, non-blocking, context-visible channel; a stored commit sha reduces the current-check to one `ls-remote`.

## Decision

- **D-01: New CLI command `compass self-update`, run by a new SessionStart hook entry with matcher `startup`** (60s timeout). It replicates the update skill's apply steps in Python: copy agents/rules/skills/CLI/hooks manifest, remove retired skills, merge-register hooks into `.claude/settings.json`, run apply-models, record version/commit/date in `plugin.yaml`. `/compass:update` remains the manual, force-and-verify path.
- **D-02: sha gate.** `plugin.yaml` gains `commit:`. The check is `git ls-remote <repository> HEAD`; matching sha means silently current, no clone. A re-check floor of 1 hour (sentinel in `.compass/tmp/`) covers rapid restarts; `--force` bypasses both.
- **D-03: Local-source mode.** When `plugin.yaml` `source:` resolves to a directory inside the project root (the dev repo bootstrapping itself), self-update copies from that directory instead of cloning - the repo IS the canonical source there, and pulling GitHub over an in-flight dev tree would destroy work. Every other install updates from `repository:`.
- **D-04: Mandatory (SPEC-020 D-01).** No opt-out flag, no pin. A bad release is fixed by pushing a good release.
- **D-05: Never blocks, never speaks unless it acted.** Exit 0 on every path. Silent when current, offline, git-less, or failed mid-apply (next startup retries); one stdout line on success - SessionStart stdout enters context, so the session learns its tooling changed. Updates and failures append to `.compass/tmp/self-update.log`; no-op checks are not logged.
- **D-06: Staged apply.** Clone lands in a temp dir and is verified (`plugin/.claude-plugin/plugin.json` exists, version readable) before any file in `.claude/` is touched. The running CLI overwriting its own `.py` files is safe: Python holds the modules in memory, and each hook invocation is a fresh process.

## Consequences

- Existing installs need one ordinary `/compass:update` to receive the command and the hook entry; from then on the fleet carries itself forward.
- The update skill's settings-merge logic now exists twice (skill prose and CLI). The CLI is the maintained one; the skill will shed its inline copy when next touched.
- A pushed regression reaches every vault within a session start. The remedy is fast-forward fixes, per D-04 - and `self-update.log` says who got what, when.
