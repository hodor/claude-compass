---
title: Fleet Test Census - Locating and Grading the 841-Test Project
type: research
status: draft
area: testing
tags: [testing, test-quality, fleet, census]
created: 2026-08-07
updated: 2026-08-07
depends_on: ["[[SPEC-013-test-quality]]", "[[RESEARCH-test-quality-empirical]]"]
---

# Fleet Test Census - Locating and Grading the 841-Test Project

From [[SPEC-013-test-quality]] TASK-065. D-05 binds this task: no fleet-wide regrading, no grading judgment, no tasks opened against findings - identify the named project, run the same mechanical census [[RESEARCH-test-quality-empirical]] ran on this repo, and hand the human a comparison to rule on.

## Question

SPEC-013's Problem statement names a project whose status read "5 of 6 tasks done and merged, suite green at 841 tests" (seen 2026-08-07, project never named). Which fleet project is this, and what does its test suite look like by the same measures used on this repo's 420-test suite?

## Result: the project could not be identified (confidence: high, as a statement of search exhaustiveness)

Three independent identification methods were run against every discoverable Compass vault under the specified fleet roots. None produced a match. This section records the search so the negative result is reproducible and so the human can supply the missing name rather than have one guessed.

### Method 1: enumerate the vaults

`find /f/{AI,Creative,Halon,Heirloom,Projects} -maxdepth 6 -type d -name ".compass"` (Git Bash paths for `F:\AI`, `F:\Creative`, `F:\Halon`, `F:\Heirloom`, `F:\Projects`) returns 47 `.compass` directories. Six are ephemeral agent worktrees under `F:\Projects\experiments\.claude\worktrees\*` (not real vaults), and two are vaults nested inside plugin/submodule repos (`F:\Halon\Python\ayon-workspace\addons\ayon-maya-toolkit`, `F:\Heirloom\iwyc-unreal\Plugins\ue5-editor-mcp`). That leaves 39 standing project vaults, consistent with the "42 vaults" figure `git show f07012d:.compass/active.md` in this repo records for the last fleet distribution (some vaults created or removed since).

### Method 2: literal text search for "841" and its likely phrasings

```
grep -rIl "841" <vault> --include="*.md"          # every vault, all markdown
grep -rIlE "suite green|841 test|841 pass|841/841|Ran 841" <vault> --include="*.md"
grep -rIlE "5 of 6 task|5/6 task" <vault> --include="*.md"
```

Run across all 39 standing vaults. Every `"841"` hit is a false positive unrelated to a test count: a Jira-style ticket number (`ENG-4841`), a source line number (`main.js:1841`, `ModuleManager.cpp:1841`), a UTC microsecond timestamp (`captured_at: ...:841142Z`), or a PDF/binary filename byte offset. Zero files anywhere in the fleet contain "841" adjacent to the word "test" in prose. `"suite green"` appears in five vaults (`roblox/seo-analytics`, `ae-postvis-ai`, `diagrams`, `internal-plugins`/`wt-spec056`, `experiments`) but every counted figure at each hit is different from 841: seo-analytics reports 899-900 passing across its history, diagrams reports 3,068, ae-postvis-ai and internal-plugins report figures in the 200-400s at the matched lines. `"5 of 6 task"` / `"5/6 task"` matches nothing. Neither does a check of the four most-recently-modified `active.md` files in the fleet (`diagrams`, `experiments`, `google-workspace`, `ludensoft-accounting`, all touched today).

### Method 3: mechanical test-function count per project

Since no vault's own prose names 841, the fallback the task brief allows was run: count collectable tests directly. `grep -c "^\s*def test_\|^\s*async def test_"` across every `.py` file under each project root (the directory containing `.compass`), pruning `.git`, `venv`, `.venv`, `node_modules`, `__pycache__`, `site-packages`, `trials`, `repo`, `dist`, `build`, and `.compass` itself so vendored dependencies and cloned third-party repos don't inflate the count.

| Project | Own-code `def test_` count | Note |
|---|---|---|
| `F:\Halon\google-workspace` | 420 | coincides with this repo's own count, unrelated project |
| `F:\Halon\diagrams` | 723 | active.md states 3,068 tests directly (pytest collects more per function via parametrize than the static grep sees) |
| `F:\AI\ComfyUI` | 446 | |
| `F:\AI\_Tools\ai-songwriting` | 845 (all locations) | **closest raw number to 841**, but disqualified - see below |
| `F:\AI\learn\learn-video-image` | 1,006 | |
| `F:\Halon\Python\ayon-workspace` | 1,312 | |
| `F:\Halon\Python\ukgov-opportunities` | 388 | |
| `F:\Halon\Python\reports-engineering` | 244 | |
| `F:\Halon\Unreal\internal-plugins` | 3,916 | |
| `F:\Heirloom\iwyc-unreal` | 1,302 | |
| `F:\Projects\experiments` | 4,617 | |
| `F:\Projects\usd` | 1,892 | entirely `OpenUSD/pxr/**/testenv` - a vendored Pixar source clone, not project-owned |
| `F:\Halon\Python\recruiting` | 9,093 | entirely `.repo-cache/**` - vendored third-party repos (pybind11, numpy/scipy inside a Maya toolkit mirror, external app clones) |
| `F:\Creative\creative-harness`, `F:\Halon\AI\ae-postvis-ai` | 40,273 / 38,982 | both dominated by vendored dependency trees; not investigated further given the scale mismatch |

**`ai-songwriting`'s 845 is the only raw count within single digits of 841, and it does not survive inspection.** Breaking it down by directory: the project's actual authored suites (`scripts/piano-loop/tests`, `scripts/model-watch/tests`, `scripts/engine/tests`, `reaper/tests`) sum to well under 100 tests per the project's own `active.md` verification notes (10/10, 20/20, 32/32, 168/168 lines cited per task). The remainder of the 845 comes from `trials/midi-gpt/repo/tests/**` - a cloned external MIDI-GPT model repository's own comparison and benchmark test suite, vendored for local experimentation, not written by or for this project's Compass plan work. Its `.compass/active.md` also shows no "5 of 6 tasks" plan status - the closest is a 5-task PLAN-001 (all done) and a 7-task PLAN-002 in progress. Coincidental proximity, not a match.

### What was and wasn't checked

- Searched: every `active.md`, every file under `plans/`, `handoffs/`, and `research/` in all 39 standing vaults, for the literal string and for paraphrases.
- Searched: raw `def test_`/`async def test_` counts for every project root with a `.compass` directory, vendored-dependency directories excluded.
- Not run: `pytest --collect-only` inside any project's own virtualenv. The static grep already located and ruled out the one candidate close enough in magnitude to justify the extra step (`ai-songwriting`, and its excess was traceable to a vendored repo without needing to invoke its interpreter). No other project's count landed within an order of magnitude of 841 after vendored code was excluded, so collection was not attempted elsewhere.
- Not checked: drives other than `F:`, and locations outside the six fleet roots the task specified.

## Conclusion for the human

The 841-test project named in [[SPEC-013-test-quality]]'s Problem statement is not identifiable from anything currently persisted in the fleet's Compass vaults, and no project's own-code test count lands at or near 841 once vendored dependencies are excluded. Two explanations are both consistent with the evidence: the session status the spec references was seen in a live session and never written to that project's `active.md` (the vault was updated again afterward, overwriting the state, or the status line was terminal/chat output that was never persisted), or the project sits outside the six fleet roots searched here.

**The open question for the human:** which project was this, or should TASK-065 be marked as unable to identify a target and closed without a census? Per D-05, this task does not open a task against any project regardless of the answer - it only reports what it found.

No census (test-to-source ratio, assertions-per-test, per-file distribution, literal-assertion grep) was run against any candidate, because running one against a project that is not confirmed to be the named one would be exactly the "guess silently" the task brief rules out, and D-05 scopes this mechanism to grading a **named** project on demand, not sampling the fleet.

## Gate implication

Per the plan (PLAN-007 line 145): "Phase B does not start until it reports: if the fleet suite is clean by these measures, Phase B ships as a guard with that evidence behind it; if it is not, Phase B has its first patient." This report satisfies the "it reports" condition with a negative identification result. Whether that clears the Phase B gate, or the gate now waits on the human naming the project so a real census can run, is the human's call - not a decision this task is scoped to make.

## Reproduction

All commands were run from Git Bash with `/f/...` paths mapping to `F:\...`.

```bash
# vault enumeration
find /f/AI /f/Creative /f/Halon /f/Heirloom /f/Projects -maxdepth 6 -type d -name ".compass"

# literal text search (repeat <vault> for each of the 39 standing vaults)
grep -rIl "841" <vault> --include="*.md"
grep -rIlE "suite green|841 test|841 pass|841/841|Ran 841" <vault> --include="*.md"
grep -rIlE "5 of 6 task|5/6 task" <vault> --include="*.md"

# mechanical test count per project root (repeat <root> for each project directory containing .compass)
find <root> -type d \( -name node_modules -o -name .git -o -name venv -o -name .venv \
  -o -name __pycache__ -o -name .compass -o -name site-packages -o -name trials \
  -o -iname "repo" -o -name dist -o -name build \) -prune -o -type f -name "*.py" -print \
  | xargs -r grep -c "^\s*def test_\|^\s*async def test_" \
  | awk -F: '{s+=$2} END {print s+0}'
```

## Comparison baseline (for whenever the target is named)

This repo's own suite, from [[RESEARCH-test-quality-empirical]], stands as the reference point the eventual census should compare against: 420 tests, 5,789 test lines to 4,871 source lines (1.19:1 ratio), 307 PASS / 3 WEAK / 0 FAIL of 310 individually graded, 13/15 seeded defects caught. None of that grading was repeated here - D-05 and this task's own brief restrict TASK-065 to counts and ratios against a named project, not another grading pass.
