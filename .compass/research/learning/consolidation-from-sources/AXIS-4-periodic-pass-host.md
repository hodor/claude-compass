---
title: "Axis 4: Where the recheck pass runs"
type: research
status: complete
confidence: medium
tags: [consolidation, drift, capture-worker, hooks, triggers, cost-bounds, reporting]
created: 2026-11-21
author: researcher
summary: "the detached capture worker traced end to end, what a periodic drift recheck could reuse from it, and where triggers-vs-cadence was decided"
area: methodology
updated: 2026-11-21
---

# Axis 4: Where the recheck pass runs

From [[SPEC-002-consolidation-grounded-in-sources]].

### Question
Which existing mechanism could host a periodic recheck of lessons and index lines against their sources, and what does each trigger, bound and reporting option cost or conflict with?

### Methodology
Repository mining of Compass's own code and decisions ("how does an existing system actually behave" shape in the research-methods chooser), which fits because every claim here is about shipped behavior; read code first, documents second. Grading was allowed by the brief: every finding below is primary-source (code read in this repo, run via the CLI) and graded by that.

## Findings

### A. The detached capture worker, end to end

1. **Two hook entries start the pipeline: Stop and SessionStart both run `capture-check --hook`.** Matchers, timeouts (30 s) and the python3/python fallback are in `plugin/hooks/hooks.json` (Stop and SessionStart rows; verified by loading the JSON). No other hook spawns a model. (confidence: high)
   - `plugin/hooks/hooks.json` Stop, SessionStart - `compass capture-check --hook`
   - Marks: code read; no retraction; not a preprint; no citations; convergence: ADR-013 D-01 agrees
   - Grade: high (primary source, measured by reading)

2. **capture-check decides due-ness by pure arithmetic, then spawns.** Order: skip if `COMPASS_WORKER_SESSION` is set (`capture_check.py:406`), take the run lock, bump the turn counter, handle an already-open opportunity via the fallback ladder (`:427-429`), honor the no-headless latch (`:431-441`), open a "phase" opportunity if a phase summary is pending (`:443-449`), else `capturelib.due_and_log` (`:451`). Due = any strong signal (`handoff-written`, `validator-finished`, `debug-finished`, `phase-summary`, `agent-noted`) or `interval` (12) turns with at least one signal (`capturelib.py` `due`, `STRONG_SIGNAL_KINDS`, `DEFAULT_CONFIG`). (confidence: high)
   - Marks: code read; convergence: `capturelib.py` docstring says the same
   - Grade: high

3. **Detach recipe.** Windows: `Popen(..., creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)`; Unix: `start_new_session=True` (`capture_check.py:208-217`). argv is `[sys.executable, COMPASS_SCRIPT, "capture-worker", <opp-id>]`: the detached process is a Python wrapper, which itself runs the model child. On success the hook logs `worker-started` with the pid (`:221`); on `OSError` it logs `worker-spawn-error` (`:219`). Survival of a hook grandchild past the hook exit was verified live per ADR-013 Context (undocumented harness behavior). (confidence: high for code, medium for harness guarantee: ADR says observed, not documented)
   - `plugin/cli/commands/capture_check.py:195-222`; `.compass/decisions/learning/ADR-013-detached-worker-quiet-fallback.md` Context
   - Marks: code read plus an in-repo decision record; convergence: 2 of 2 agree
   - Grade: high for code, medium for the platform guarantee

4. **The wrapper invokes `claude -p` with a scoped tool list and a timeout, no dollar budget.** argv: `claude -p <prompt> --model <resolved> --output-format json --allowedTools "Read,Write,Edit,Glob,Grep,Skill,Bash(python:*),Bash(python3:*)"` (`capture_worker.py:299-303`, tools at `:281`). Model comes from `modelslib.resolve("capture-worker")`, built-in tier `balanced` (`modelslib.py:58`; ADR-013 D-09 records that the cheap tier failed the blind judge). Cwd is the project root, stdin DEVNULL, env gets `COMPASS_WORKER_SESSION=1`, Windows adds `CREATE_NO_WINDOW` (`:305-327`). The only bound is `timeout=worker_grace_seconds` (600 s, `capturelib.py:40`), after which the child is killed and logged `timeout after 600s` (`:335-343`). The installed `claude --help` lists `--max-budget-usd <amount>`; the capture worker does not pass it. (confidence: high)
   - `plugin/cli/commands/capture_worker.py:277-327`; `plugin/cli/modelslib.py:58`; `claude --help` run in this session
   - Marks: code read plus CLI run; convergence: LESSON-headless-worker-denies-tools-silently agrees on the tool scoping
   - Grade: high

5. **The prompt tells the child to read `extract-lessons/SKILL.md` as a file, never through the Skill tool, and forbids subagents.** Reason in the code comment: a Skill-tool invocation hangs in a non-main context (GitHub #25) (`capture_worker.py:82-96`). A periodic pass would be a second prompt template of the same shape. (confidence: high)
   - Marks: code read; convergence: single source
   - Grade: high

6. **Lock: one worker per vault via `tmp/capture-worker.lock`.** Atomic `O_CREAT|O_EXCL`, payload `{pid, started_at}`, one 50 ms retry, then log `worker-failed reason=lock-held` and exit 0; a lock older than `worker_grace_seconds` is broken; release is owner-checked by pid (`capture_worker.py:115-174`). The hook has a separate 60 s run lock for capture-check itself (`capturelib.RUN_LOCK_STALE_SECONDS`). ADR-013 D-06 records that interleaving with main-session vault writes is tolerated: append-only logs, derived state regenerated by sync. (confidence: high)
   - Marks: code read; convergence: ADR-013 D-06 agrees
   - Grade: high

7. **Logging and ledger.** Child stdout/stderr go to `.compass/tmp/worker-logs/<opp-id>.log` (`capture_worker.py:242-253`). Ledger `.compass/tmp/capture-log.jsonl` receives `worker-started` (hook), then exactly one of `worker-finished` (carrying the `extracted: ...` line) or `worker-failed` with a reason (`lock-held`, `no-headless`, `timeout`, `exit N`, `exit 0 (opportunity not closed)`) (`:350-369`). `sync` ages old logs into `.compass/archive/logs/` (moved, never deleted; `sync.py:1056-1106`). (confidence: high)
   - Marks: code read; convergence: ADR-013 D-03/D-07 agree
   - Grade: high

8. **Closing is a CLI call the child makes, and success is judged on its effect, not on exit code.** The child runs `compass capture-close <opp-id> --outcome ... [--written N ...]` (`capture_close.py:46-119`); the wrapper counts a run finished only if exit is 0 and `opportunity.json` carries a non-null `outcome` (`capture_worker.py:205-211,350`). The lesson record explains why: headless `-p` denies unlisted tools silently and exits 0 (`.compass/lessons/subagents/LESSON-headless-worker-denies-tools-silently.md`). (confidence: high)
   - Marks: code read plus lesson; convergence: 2 of 2
   - Grade: high

9. **Failure ladder is per-opportunity and built for one in-flight job.** Dead worker (started row older than grace) triggers up to 2 attempts (`MAX_WORKER_ATTEMPTS`), then `additionalContext` quiet fallback, then a rendered block, then auto-abandon (`capture_check.py:236-400`). `no-headless` (binary missing, or fast nonzero exit with an auth-shaped stderr) latches `no_headless_at` and suspends new opportunities for 86400 s (`capture_worker.py:34-43,257-266`; `capturelib.py:41`). `doctor` reconciles the ledger rows (`doctor.py:477-573`). (confidence: high)
   - Marks: code read; convergence: ADR-013 D-04/D-05/D-10
   - Grade: high

10. **Everything in the worker is keyed to one opportunity id and one open-opportunity mutex.** State holds a single `open_opportunity` (`capturelib.DEFAULT_STATE`); the worker wrapper only accepts ids matching `OPP-<digits>Z` that exist under `tmp/capture-opportunities/` (`capture_worker.py:68,381-391`). A recheck job would either mint its own opportunity kind (the code already has `kind` values `signal`, `interval`, `phase`; `capture_check.py:443-453`) or need its own state key and ledger vocabulary. (confidence: high for the coupling, no source says which a recheck would use)
   - Marks: code read; no other source
   - Grade: high

### B. What a periodic recheck could reuse, and the options the code exposes

11. **Trigger inputs that already exist as recorded state.** Turn counter and signal list in capture state (`capturelib.py` state, `MAX_SIGNALS=50`); `last_opportunity_at` (state key); capture config in `.compass/meta/capture.json` (`enabled`, `interval`, `max_reemits`); ledger timestamps in `capture-log.jsonl`; `sync` already runs on every vault write (PostToolUse Write/Edit/MultiEdit, 30 s). Not present: a recorded "last drift pass" timestamp. Hermes's curator gate (7 days since last run plus 2 h idle, seeded on first sight so a fresh install never mutates at once) is a documented reference for a time-since-last gate (`.compass/research/hermes/RESEARCH-hermes-fit-2026-11.md` item 13, `agent/curator.py:31-33,160-181`). (confidence: high for the inventory, medium for Hermes mapping per that doc's own "low on mapping")
    - Options the code supports without new infrastructure: (a) a new strong-signal kind or a count of closed opportunities since the last pass, evaluated in `due()`; (b) a time-since-last-pass gate stored in capture state or a new `.compass/meta` file, checked in capture-check at SessionStart; (c) a `sync` counter of vault writes; (d) a standing validate/doctor warning that tells the agent to run the pass (the existing bloat-trigger shape).
    - Marks: code read; convergence: 2 sources (Compass code, Hermes research doc)
    - Grade: high for inventory, low for the Hermes transfer (vendor-style asserted in a vault doc)

12. **Compass already has a budgeted, ledgered, scheduled model-run harness: control loops.** `compass loop run` runs one iteration: lock, sense, gate on daily and lifetime budget, actuate with `claude -p` under caps, re-sense, optional judge with its own model and caps (`looprunner.py:1-60`). `loop.json` carries `max_turns`, `max_budget_usd`, `timeout_s`, `daily_budget_usd`, `total_budget_usd`, a `wip_limit`, halt counters, and a `judge` block (`.compass/loops/LOOP-003-session-context/loop.json`). A deterministic sensor command supplies the reading and runs before any model; throttled runs cost nothing. `loop schedule <id> --github [--cron]` renders a GitHub workflow, `--local` prints a `schtasks`/crontab line (`commands/loop.py` docstring). (confidence: high)
    - Marks: code read; convergence: SPEC-026 names scheduling as the intended step ("you can schedule this loop to run every day", `SPEC-026-control-theory-for-loops.md:37`)
    - Grade: high

13. **Split between zero-token checks and a bounded judge already has a precedent in both mechanisms.** In loops: deterministic sensor, then actuator, then deterministic re-sense, then an advisory judge (`looprunner.py` docstring: "The reading is advisory: it reaches no transition and no exit code"). In capture: `due()` is pure arithmetic and logs a `skipped` reason when nothing is due (`capturelib.py` `due_and_log`). Mechanical drift candidates from code are cheap to script: `compass validate` already reports `broken_wikilink` with `file:line` and the CLI has `graph`, `lessons`, `lesson-coverage` commands (`validate.py:75-96`; command list from `python .claude/cli/compass`). Whether any command today checks a `file:line` reference against the target file's current content was not found in this read. (confidence: medium)
    - Marks: code read; convergence: 2 mechanisms agree on the shape
    - Grade: high for the shapes, low for the absence claim (a grep, not exhaustive)

14. **Concurrency: the lock is per-vault and scoped to the capture worker.** A second kind of worker sharing `capture-worker.lock` would serialize against extraction and hit `lock-held` with a respawn path that is hard-coded to capture opportunities; a separate lock file would allow two model children at once, which no code currently arbitrates. Loops use their own lock (`LOOP-003.../ledger.jsonl.lock`, `looplib.acquire_lock`). Lesson writes are append-only or per-file with sync regenerating derived state (ADR-013 D-06). (confidence: medium: reasoning from the lock code, nothing tested)
    - `capture_worker.py:115-154`; `looprunner.py:470-476`
    - Marks: code read plus inference
    - Grade: medium

15. **Cost bounds available today.** Worker: wall-clock timeout only (600 s); tier from the model table; no `--max-budget-usd`. Loops: per-run `max_budget_usd` and `max_turns`, daily and lifetime ceilings enforced before launch with a float epsilon (`looprunner.py:87,576-592`), judge budgets charged up front. Cost of the worker is "made measurable for the first time" via ledger rows (ADR-013 Consequences); the loop ledger records `cost_usd` per run. (confidence: high)
    - Marks: code read; convergence: ADR-013 agrees
    - Grade: high

### C. Triggers versus cadence: where it was decided and whether a drift recheck conflicts

16. **The no-cadence rule is scoped to consolidation and recorded in the lessons-and-index spec, then repeated in the skill.** `SPEC-002-lessons-and-index-subsystem.md:119` ("runs only on bloat trigger ... no fixed cadence") and `:141` (out of scope: "Automatic consolidation on cadence. Bloat-only trigger keeps cost zero in low-usage projects"). The consolidate skill repeats it (`plugin/skills/consolidate/SKILL.md` front matter `when_to_use`; "Running on fixed cadence" is a listed failure mode; "A trigger contract; do not run unprompted"). The stated reason is cost in low-usage projects, not an accuracy argument. Introduced in commit 1b08764. (confidence: high)
    - Marks: code and vault read; convergence: 3 places agree
    - Grade: high

17. **A second, independent rejection of fixed cadence exists for planning waves.** `RESEARCH-rolling-wave-synthesis.md:88` ("Fixed cadence dead", 3 of 3 axes agree, in the planning domain, not consolidation). It argues deviation-triggered over fixed-cadence. (confidence: high that it says this; low that it transfers to memory drift)
    - Marks: vault research doc; convergence: 3/3 in-doc
    - Grade: medium

18. **Where cadence-like machinery is already accepted:** (a) the `interval` trigger (every 12 turns with a signal) in capture, which is turn-count cadence, not wall-clock; (b) `self-update` is sha-gated and throttled at SessionStart; (c) `loop schedule` renders GitHub cron/schtasks; (d) the no-headless latch retries after 86400 s. So time and count gates exist; the rule that was written is specific to `/compass:consolidate` and its warning-driven trigger. Whether the spec's "bloat trigger" wording extends to a drift recheck is not stated anywhere read: SPEC-002's problem (drift) was approved after that sentence and does not mention it. (confidence: medium; the conflict question is open, see Gaps)
    - Marks: code and vault read
    - Grade: medium

19. **No-daemon is a standing rule that constrains where a periodic pass may live.** `SPEC-004-mechanical-work-off-the-agent-budget.md:67` ("A daemon or background watcher ... invoked per-event by the hook and per-command by humans") and ADR-013 D-08 ("No standing daemon and no cron. The worker is per-event"; "Standing per-machine sweeper. Rejected outright"). Compass's own `loop schedule` renders an OS or GitHub schedule while leaving the scheduler outside Compass, which is a different shape from a Compass-shipped scheduler. SPEC-004's own success criteria are about PostToolUse bookkeeping tokens (zero agent tokens on the hook path); a model judge on a worker is not on that path. (confidence: high for the text; medium for how a reviewer would read the interplay)
    - Marks: vault read; convergence: 2 of 2 agree on no-daemon
    - Grade: high for text

### D. Prior evidence reused (not redone)

20. **Periodic hygiene passes exist in industry as asserted practice.** OpenAI doc-gardening agents (6 f11) and Devin's daily pass (6 f12) are vendor-asserted; Anthropic dreaming (1 f4) is measured on small n; per the review document at `.compass/research/llm-research/REVIEW-llm-research-for-compass.md:124`. Not re-verified here. (confidence: medium)
    - Marks: secondary (vault review of vendor posts); convergence: 3 in-doc
    - Grade: low to medium (vendor, asserted)

### E. Reporting without chat noise

21. **Existing quiet channels.** (a) `compass validate` warnings, which are plain-word sentences per class (`validate.py:337-410` sentence builders) and never touch the exit code for the warning classes; (b) `sync` writes in-file warning comments when caps are exceeded (`sync.py:1005-1051`), read by agents at the next session; (c) `doctor` rows reconcile worker ledger rows (`doctor.py:477-573`); (d) `compass review <file>... --why` sends a committed vault document to the configured review surface and ends the turn with one line (`commands/review.py` docstring; project rule "Review in a visual surface"); (e) ledger rows in `capture-log.jsonl` / loop `ledger.jsonl`. A recheck that finds drift can land as a vault document plus a validate warning pointing at it; whether a drift report reaches the human at all unprompted is gated by the existing "silence between gates" rule. (confidence: high for the channels, medium for fit)
    - Marks: code read; convergence: 5 mechanisms
    - Grade: high

22. **Observability requirement is already stated for any invisible worker.** ADR-013 D-03: a zero-failure log with zero finishes is read as breakage; D-04: dead workers are detected mechanically; D-10: doctor reconciles. Origin: Hermes's equivalent pass swallows spawn errors (`try/except: pass`) so "ran, found nothing" is indistinguishable from "never ran" (ADR-013 Rationale). A periodic pass inherits this requirement; a "ran, nothing drifted" result needs its own ledger row. (confidence: high)
    - Marks: vault read; convergence: ADR-013 and ADR-010 D-06 agree
    - Grade: high

## Candidate changes for Compass

Presented as options with their costs; no choice is made here.

1. **Reuse the control-loop harness for the recheck (sensor = scripted drift scan, actuator/judge = bounded model).** North star: low token usage (zero tokens when the sensor reads clean, budgets enforced before launch), accuracy (re-sense verifies). Changes in `plugin/`: a loop template or a `sense-drift` sensor command beside `sense-context`; the schedule option already exists. Already covered: the budget, ledger, judge, halt and schedule machinery (`looprunner.py`, `loop schedule`); not covered: a drift sensor. Conflicts: ADR-013 D-08 no-cron is satisfied only if scheduling stays an opt-in rendered workflow, not shipped.
2. **Extend capture-check with a new opportunity kind (`recheck`) triggered by closed-opportunity count or time since last pass at SessionStart.** North star: perfect memory, low token usage. Changes: `capturelib.due` and state key, `capture_check.py` kind branch, a worker prompt template, `doctor` row. Already covered: spawn, detach, lock, log, ladder. Costs: the one-open-opportunity mutex and the single lock serialize it against extraction; the worker has only a timeout, so a `--max-budget-usd` flag would be new.
3. **Make the recheck a validate/doctor-driven trigger, same shape as the bloat trigger.** Mechanical script finds candidate drift (zero tokens), writes a standing warning; `/compass:consolidate` or a new skill runs the model judge on that trigger. North star: low token usage; is the only option that does not touch the "no fixed cadence" text. Changes: new warning class in `validate.py`/`sync.py`, sentence builder, skill routing. Already covered: the warning-to-skill pattern.
4. **Add a "last drift pass" record under `.compass/meta` plus ledger rows for every run including clean ones.** Serves D-03's "ran, found nothing" requirement under any of the three options above.

## Contradictions
- Worker spawning is described as "no cron, no daemon, per-event" (ADR-013 D-08) while `compass loop schedule --local/--github` ships cron and schtasks rendering (`commands/loop.py`). The two coexist because the scheduler is the OS or GitHub's, not Compass's; no document reconciles them explicitly.
- `SPEC-002-lessons-and-index-subsystem.md:141` rejects "automatic consolidation on cadence" for cost reasons, while the approved [[SPEC-002-consolidation-grounded-in-sources]] needs rechecks that no cap hit will ever trigger. The spec text for the new SPEC-002 is silent on trigger.

## Gaps
- Whether a drift recheck counts as "consolidation" for the no-cadence rule is a decision no read document makes; needs a human or an ADR.
- No source read states how many tokens or dollars one worker pass costs in practice; the ledger holds `extracted` lines but no cost field for the capture worker (the loop ledger records `cost_usd`). `compass capture-stats` was not run here.
- Hermes mapping rests on a vault research doc (not the Hermes source) and is flagged low on mapping there; not re-read in source.
- Whether any current command verifies a `file:line` reference against current file content was only grepped, not exhaustively ruled out.
- Windows-specific detach behavior (DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW) was read but not exercised in this session.
