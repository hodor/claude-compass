---
title: "Hermes skill and memory write-approval gate, and how Compass's review flow could hold the same gate"
type: research
status: complete
confidence: medium
area: learning
tags: [hermes-agent, skills, review, approval, learning-loop, write-approval]
created: 2026-11-04
updated: 2026-11-04
git_branch: "master"
git_commit: "e331edd"
author: "researcher (Claude)"
depends_on: ["[[SPEC-012-learning-loop]]", "[[SPEC-002-lessons-and-index-subsystem]]", "[[SPEC-029-human-verdicts-reach-compass]]"]
summary: "what a person sees and approves before a Hermes skill or memory write lands (staged JSON, /skills diff, approve/reject, silent background staging), and how compass review could hold the same gate"
---

# Hermes skill and memory write-approval gate, and how Compass's review flow could hold the same gate

## Question

What does a person see or approve before a new or changed Hermes skill (or memory entry) takes effect, and how could Compass's `compass review` hold the same gate for automatically created skills?

## Methodology

Repository mining of the hermes-agent clone at commit a212421d (2026-11-04): code read first, docs only to confirm. The Compass side is a direct read of `plugin/cli` and the lesson skills at commit e331edd. No grading: no disclosure reached this run, so findings are marked and ungraded.

Earlier passes ([[RESEARCH-hermes-memory-mechanics]] finding 10, [[RESEARCH-hermes-vs-compass-fit]] finding 9) record that `write_approval` exists, is off by default and stages writes. This document adds the store, the review surfaces, the diff rendering, the unattended behavior and the Compass mapping.

## Part 1: Hermes

### Findings

1. **One boolean per subsystem switches the gate; default off** (confidence: high)
   `memory.write_approval` and `skills.write_approval` default to `False`. Unset or invalid values read as off. There is no "block all writes" state; disabling a subsystem uses its own enable flag.
   - `hermes_cli/config_defaults.py:1305` (memory), `:1469` (skills)
   - `tools/write_approval.py:36-60` (config read, truthy strings `on/true/yes/1/approve/enabled`)
   - `hermes_cli/config_migrations.py:398-413` (an older tri-state `write_mode` became this boolean; only `approve` mapped to true)
   - Marks: code, owner checked (NousResearch repo); no retraction applicable; not a preprint; no citation count; 1 source

2. **The gate covers every `skill_manage` action from both origins; skills always stage** (confidence: high)
   `create`, `edit`, `patch`, `delete`, `write_file`, `remove_file` and batch `operations` all pass `_run_write_gate`. With the gate on, a skill write from a foreground turn or from the background review fork is never committed directly: it is staged. The code comment gives the reason: a SKILL.md is too large to review inline.
   - `tools/skill_manager_tool.py:672-690` (`_run_write_gate`), `:693-702` (`_apply_skill_write_gate`)
   - `tools/write_approval.py:201-216` (`evaluate_gate`: skills or background origin stage)
   - The gate fails open if `write_approval` cannot be imported (`tools/skill_manager_tool.py:677-679`).
   - Marks: code, owner checked; 1 source

3. **Memory has two paths: inline prompt for a live foreground turn, staging otherwise** (confidence: high)
   A foreground memory write in an interactive CLI calls the per-thread approval callback with title "Save to memory?" and choices once/session/deny. Background writes, messaging sessions, cron, kanban workers and `chat -q` stage at once instead of waiting for an answer nobody can give. An unknown prompt outcome stages rather than drops.
   - `tools/write_approval.py:219-248` (`_prompt_inline_memory_approval`), `:229-231` (`_no_user_can_answer` stages at once)
   - `tools/memory_tool.py:84-101` (`_gate_or_stage`)
   - The background fork's own dangerous-command prompts resolve to deny: `agent/background_review.py:1065-1069`.
   - Marks: code, owner checked; 1 source

4. **A staged write is a JSON file holding the exact replay payload plus a one-line gist** (confidence: high)
   Path: `<HERMES_HOME>/pending/{memory,skills}/<id8>.json`. Record fields: `id` (8 hex chars), `subsystem`, `action`, `summary`, `origin` (`foreground` or `background_review`), `created_at`, `payload` (the kwargs to replay). There is no session id, no transcript excerpt and no stated reason for the write. The files survive restarts.
   - `tools/write_approval.py:65-89` (`stage_write`), `:63-66` (path)
   - Disk failure loses the write; the docstring calls that the safe failure for a gate (`:74-78`).
   - `website/docs/user-guide/features/skills.md:681-686` (survives restarts)
   - Marks: code, owner checked; 1 source

5. **The reviewer sees a heuristic gist, then asks for the diff** (confidence: high)
   `/skills pending` lists `<id> [auto] <gist>` per staged write; `[auto]` marks `origin == background_review`. The gist is computed without a model call: for create/rewrite it is the frontmatter `description` (cut to 140 chars) plus size; for patch it is `+added/-removed lines`. `/skills diff <id>` prints the full SKILL.md for a create, and a unified diff against the on-disk file for edit/patch/write_file. A batch renders one diff per operation, each against the earlier operations' result.
   - `hermes_cli/write_approval_commands.py:17-32` (list format), `:157-163` (`_diff`)
   - `tools/write_approval.py:257-275` (`skill_gist`), `:305-344` (`skill_pending_diff`), `:395-413` (batch)
   - Marks: code, owner checked; 1 source

6. **The patch preview runs the same matcher approval runs** (confidence: high)
   `_fold_patch` uses `fuzzy_find_and_replace`, the matcher `_patch_skill` and `apply_skill_pending` use, so the previewed diff equals what approval commits. A patch that approval would reject renders as `(patch would fail: <reason>)`.
   - `tools/write_approval.py:347-365`
   - Marks: code, owner checked; 1 source

7. **Approve replays the payload; reject deletes the file; there is no "changes" verb** (confidence: high)
   `/skills approve <id|all>` calls `apply_skill_pending`, which sets a context flag so `skill_manage` skips the gate, then runs the original call. Success discards the pending file; failure leaves it pending and prints `<id>: <error>`. `/skills reject <id|all>` discards the file. The reviewer cannot attach a note or edit the staged text from the command; edits happen by hand in the JSON file or by rejecting and asking the agent again.
   - `hermes_cli/write_approval_commands.py:64-107` (approve), `:145-154` (reject), `:128-142` (`_apply_one`)
   - `tools/skill_manager_tool.py:716-722` (`apply_skill_pending`), `:667-670` (`_skill_gate_bypass`)
   - Memory approvals print the whole entry a replace/patch/remove touched, so the approver sees what was lost (`write_approval_commands.py:91-103`).
   - Marks: code, owner checked; 1 source

8. **Review surfaces: classic CLI, chat gateway, Desktop and TUI slash, all through one handler** (confidence: high)
   `handle_pending_subcommand` serves `pending`, `approve`, `reject`, `diff`, `approval on|off`. The CLI mixin, the messaging gateway (`gateway/slash_commands.py`) and the TUI gateway (`tui_gateway/methods_tools.py`, for Desktop and TUI) all call it. The gateway truncates `/skills diff` at 3000 characters and points to the pending JSON file. `/skills` answers when the gate is on or staged writes remain, so turning the gate off never strands staged writes. Desktop allows only `pending, approve, reject, diff, approval` of the `/skills` subcommands.
   - `hermes_cli/write_approval_commands.py:35-57`, `hermes_cli/cli_commands_mixin.py:1264-1296`
   - `gateway/slash_commands.py:925-945`, `tui_gateway/methods_tools.py:924-1000`, `hermes_cli/commands.py:251-262`
   - Marks: code, owner checked; 1 source

9. **No web-dashboard or file-editor review surface for staged writes was found** (confidence: medium)
   Searches of `web/src` and `ui-tui/src` for `write_approval`, `pending/skills`, `/skills pending` returned nothing relevant; Desktop reaches the gate only as slash commands. The docs refer to "CLI or dashboard" for viewing diffs, but no dashboard code for it was located.
   - `apps/desktop/src/lib/desktop-slash-commands.ts:385-389` (slash route only)
   - `website/docs/user-guide/features/skills.md:690` ("best viewed in CLI or dashboard")
   - Caveat: absence found by grep, not by reading all UI code.
   - Marks: code, owner checked; negative search; 1 source

10. **Staged background skill writes produce no notification** (confidence: medium)
    The post-review summary (`_action_lines`) skips every result with `staged: true` unless it also has `proposal_staged`. Only memory consolidation proposals set `proposal_staged`. The skill gate's result carries `staged`, `pending_id`, `gist`, `message` and no `proposal_staged`, so a staged skill from the background fork adds no line to the user-facing summary; it is found by running `/skills pending`. `pending_count` (documented as "for notification badges") has no caller other than the gate-off check in the gateway and TUI gateway.
    - `agent/background_review.py:677-682` (`_action_lines`), `:1239-1244` (`_publish_review_summary`)
    - `tools/skill_manager_tool.py:685-689` (skill result shape), `tools/memory_tool.py:205-215` (`proposal_staged`)
    - `tools/write_approval.py:131-138` (`pending_count`), `gateway/slash_commands.py:933`, `tui_gateway/methods_tools.py:993`
    - Caveat: derived from reading the control flow; no test or run confirmed the silence.
    - Marks: code, owner checked; 1 source

11. **Notification of applied background writes is a separate three-mode setting** (confidence: high)
    `display.memory_notifications` takes `off`, `on` (generic "updated" lines) or `verbose` (content previews). The summary prints to the CLI and calls `background_review_callback` for gateway delivery; the TUI shows it as a system line in the transcript. This reports writes that landed, so with the gate on it reports nothing for staged ones (finding 10).
    - `hermes_cli/config_defaults.py:849`, `agent/background_review.py:718-752`, `:1239-1244`
    - `ui-tui/src/app/createGatewayEventHandler.ts:1672-1684` (`review.summary` event)
    - Marks: code, owner checked; 1 source

12. **With no answer, a staged write waits indefinitely and nothing is applied** (confidence: medium)
    No expiry, TTL or auto-apply for pending records was found: a record leaves the directory only by approve (success) or reject. The agent's tool result says `Staged for approval ... Not yet saved`. In headless contexts (cron, kanban, webhook, api_server) the message names the pending directory rather than a slash command nobody can type.
    - `tools/write_approval.py:166-198` (`_slash_review_surface`, `_staged`)
    - Caveat: absence of a TTL found by reading `write_approval.py` and its callers, not by a repository-wide search for cleanup jobs.
    - Marks: code, owner checked; negative search; 1 source

13. **Other controls near the gate are independent switches** (confidence: high)
    - `skills.guard_agent_created` (default off): content scanner on agent-written skills; a dangerous verdict is a tool error the agent can retry. Documented as not an approval gate (`hermes_cli/config_defaults.py:1456-1460`, `tools/skill_manager_tool.py:41-61`, `website/docs/user-guide/features/skills.md:707-709`).
    - `skills.ledger` (default on): every skill mutation appends a JSONL entry with before/after hashes; "telemetry, not a gate"; powers `hermes curator ledger` and `rollback <entry-id>` (`tools/skill_ledger.py:1-8`, `hermes_cli/config_defaults.py:1470-1474`).
    - `hermes curator lock <skill>`: the agent cannot change that skill at all (`website/docs/user-guide/features/curator.md:344-354`).
    - `auxiliary.background_review.enabled` (default true): `false` stops automatic review forks while `/refine` still works (`hermes_cli/config_defaults.py:788-798`).
    - `skills.creation_nudge_interval: 15` (`cli-config.yaml.example`, skills section).
    - Marks: code, owner checked; 1 source

14. **Provenance decides what the unattended fork may touch** (confidence: high)
    A context variable carries the write origin (`foreground` or `background_review`); an `attended` flag separates a user-requested `/refine` fork from an automatic one. Only background-created skills get `created_by: agent` and become curator-managed. The background fork archives instead of hard-deleting; unattended memory deletions are staged as proposals.
    - `tools/skill_provenance.py:1-40`, `tools/skill_manager_tool.py:598-610`, `:770-775`, `tools/memory_tool.py:185-216`
    - Marks: code, owner checked; 1 source

## Part 2: Compass's review flow as the same gate

### Findings

15. **`compass review` sends committed documents inside a vault and returns a verdict** (confidence: high)
    - Request: `tmp/review/<id>.request.json` with `id, surface, file, title, return, commit`; several-file requests add `files[{file, why}]`, `session`, `project` (`plugin/cli/reviewlib.py:1-16`, `:217-244`).
    - Verdict: `<id>.verdict.json` with `verdict` `approved` or `changes`, `notes`, optional `comments`, `edited`, `files[{file, read, note, verdict}]` (`plugin/cli/reviewlib.py:17-26`, `:443-461`).
    - On a verdict the CLI prints the JSON, `comment` and `edited` lines, per-file lines, `git diff <commit>` for the reviewed and edited files, and the document text as left (`plugin/cli/commands/review.py:274-291`).
    - A repeated review of the same document adds `<id>.changes.diff` so the surface can show what changed since the human last saw it (`plugin/cli/commands/review.py:51-58`, `plugin/cli/reviewlib.py:407-425`).
    - Marks: code, owner checked; 1 source

16. **A reviewed file must be committed, inside a `.compass` vault, and inside the surface's root** (confidence: high)
    `_check_documents` refuses a file that is not a file, that has no `.compass` ancestor ("is outside a .compass vault"), that has uncommitted changes, or that is untracked. Both surfaces also require the vault: VS Code finds the folder holding the nearest `.compass` ancestor; Obsidian needs an ancestor with `.obsidian/`. Review files `tmp/review/` sit under the gitignored `.compass/tmp/`.
    - `plugin/cli/commands/review.py:335-356`, `plugin/cli/reviewlib.py:281-297` (`committed_head`)
    - `plugin/cli/review_surfaces/vscode.py:38-44`, `plugin/cli/review_surfaces/obsidian.py:55-63`
    - Consequence by code reading: a draft under `.compass/tmp/` is untracked and refused; a SKILL.md under `.claude/skills/` has no `.compass` ancestor and is refused.
    - Marks: code, owner checked; 1 source

17. **Skill locations relative to that constraint** (confidence: high)
    - Shipped skills: `plugin/skills/<name>/SKILL.md`, in the Compass repo, outside any `.compass` vault.
    - Installed skills: `.claude/skills/<name>/SKILL.md`; `.claude/` is gitignored in the Compass repo and is rebuilt by update (`.gitignore:17`, `plugin/cli/commands/overlay.py:1-12`).
    - Project-local skill additions: `.compass/meta/local/skills/<name>.md`, inside the vault, version-controlled where the project tracks `.compass/`, re-applied after update by `compass overlay` as an addendum appended to a shipped skill's target (`plugin/cli/commands/overlay.py:1-30`).
    - Overlay applies to existing shipped skills (state `no shipped file` when the target is missing); a wholly new skill has no documented overlay path in that file.
    - Marks: code, owner checked; 1 source

18. **What the reviewer would see for a skill draft** (confidence: medium)
    Described from the code paths above, none built for skills.
    - Surface: the draft SKILL.md opens in Obsidian or VS Code as a document, with the request `title` ("the gate's question") and, for several files, a per-file `why` line.
    - The pipeline rule asks a reviewed document to open with a picture and a "You decide" callout; a SKILL.md carries its own frontmatter and shipped text, so whether those additions fit a skill file is open (`plugin/templates/rules/compass-pipeline.md:18`).
    - Why created and evidence: the request has no field for them. A second file (an evidence note listing the opportunity, trigger and source excerpts) could ride in a several-file review with its `why`; Hermes stores neither (finding 4).
    - Change view: `<id>.changes.diff` for a revised or re-sent draft; for an edit to an existing skill the reviewer sees the draft file against its earlier committed version through the same `git diff <sha>`.
    - Marks: code read plus inference; 1 source

19. **What approve and changes do, against Hermes's approve and reject** (confidence: medium)
    - Compass `approved`: the rule defines it as the gate's recommended approve option, with notes and `comment` lines steering what follows (`plugin/templates/rules/compass-pipeline.md:18`). Applying a skill (placing it where skills load) is a step the caller performs; no code in `plugin/cli` does this today.
    - Compass `changes`: notes, comments and the human's edits come back (`edited` lines plus `git diff`); the rule says to apply them and send the document again with a "Since your last review" callout. Hermes has no equivalent verb: reject discards (finding 7).
    - Human edits made in the editor arrive as a diff, which Hermes's staged JSON does not support.
    - Per-file verdicts in a several-file review apply to each document alone (`plugin/cli/commands/review.py:213-217`, `:240-245`).
    - Marks: code read plus rule text; 1 source

20. **When no one answers** (confidence: high for the flow, medium for its use by an unattended pass)
    - Not claimed within `ACK_SECONDS` (60): the request is withdrawn and the CLI prints `not configured: <surface> did not pick up review <id> ...`; the rule then falls back to `AskUserQuestion` (`plugin/cli/commands/review.py:97-98`, `:294-318`).
    - Claimed (`<id>.seen` exists): no limit; the human may answer hours later (`plugin/cli/commands/review.py:60-68`).
    - `--timeout S` bounds the wait and prints `timeout <id>`, exit 1; the code does not cancel the request, so it remains in `--status` as pending (`plugin/cli/commands/review.py:294-318`; `plugin/cli/reviewlib.py:464-480`).
    - `--no-wait` returns after `requested <id> <file>` and leaves the request pending (`plugin/cli/commands/review.py:410-411`).
    - A new request for the same document withdraws the older one (`plugin/cli/commands/review.py:394-399`).
    - The stored pending requests have no expiry in `reviewlib.py`; only orphan `.seen` files age out after an hour (`plugin/cli/reviewlib.py:197-208`).
    - Marks: code, owner checked; 1 source

21. **The capture worker is a detached headless `claude` child with a bounded run** (confidence: high)
    It runs the extract-lessons pass with tools `Read,Write,Edit,Glob,Grep,Skill,Bash(python:*),Bash(python3:*)`, a `worker_grace_seconds` of 600, and writes one ledger end row per run. `capture-note` hands an observation to it as evidence and a strong signal.
    - `plugin/cli/commands/capture_worker.py:281`, `plugin/cli/capturelib.py:40`, `plugin/cli/commands/capture_note.py:1-20`
    - Open point (low): whether a `compass review` wait fits inside that child is not established. The child has `Bash(python:*)` allowed and the review CLI is Python, but `compass review` can wait without limit once claimed while the child's grace is 600 s; a pass that ends before the verdict leaves the request pending (finding 20). No code connecting the two was found.
    - Marks: code, owner checked; 1 source

22. **Compass lesson capture writes with no human review: the closest existing path** (confidence: high)
    - Trigger: the `Stop` hook runs `compass capture-check`; a due opportunity opens `OPP-<UTC>/opportunity.json` and the worker runs `extract-lessons` (`plugin/skills/lessons/SKILL.md`, capture loop section).
    - Filter: `extract-lessons` applies binary triggers and the anti-list, then step 6 hands survivors to `lesson-write` (`plugin/skills/extract-lessons/SKILL.md`, steps 4a to 6).
    - Write: `lesson-write` judges dedup against the catalog (recurrence, refinement, new), enforces the 5-line body cap and writes the lesson file; the PostToolUse hook adds the catalog row and index line (`plugin/skills/lesson-write/SKILL.md`, steps 3 and 4a to 4c).
    - Record: the pass writes `.compass/tmp/extraction-log-YYYY-MM-DD.md` and closes the opportunity with counts; nothing is shown to the human (`plugin/skills/extract-lessons/SKILL.md`, steps 7 and 9).
    - Rule: "Capture is never the human's job"; the human is never asked (`.claude/rules/compass-pipeline.md`, Lessons section; `plugin/skills/lessons/SKILL.md`, "Creating lessons").
    - A lesson revision (refine, revise, archive) is also written without review; an escalated lesson is not archived autonomously and is flagged instead (`plugin/skills/lesson-write/SKILL.md`, failure modes).
    - Anti-list excludes anything already stated in "the text of a shipped skill" (`plugin/skills/lesson-write/SKILL.md`, Anti-list).
    - Marks: code, owner checked; 1 source

23. **Where Hermes's gate pieces have a Compass counterpart and where none exists** (confidence: medium)
    | Hermes piece | Compass counterpart found |
    |---|---|
    | `write_approval` on/off boolean | none; `review_editor` in `.compass/meta/plugin.yaml` names the editor, not a gate (`plugin/cli/reviewlib.py:66`) |
    | staged JSON record with replay payload | `tmp/review/<id>.request.json` holds a file path and commit, not a replay payload |
    | `/skills pending` list | `compass review --status` prints `pending <id> <file>` (`plugin/cli/commands/review.py:179-189`) |
    | `/skills diff <id>` | the document opens in the editor; `<id>.changes.diff` for a repeat review |
    | `[auto]` origin tag | none in a request; `source` is persisted in lesson frontmatter by `lesson-write` |
    | approve replays, reject discards | verdict `approved` / `changes`; applying is the caller's step |
    | per-mutation ledger and rollback | git history of the committed document |
    | provenance flag `created_by: agent` | none for skills; lessons carry `source` |
    - Marks: code read plus comparison; 2 sources

## Contradictions

- Hermes docs describe `/skills pending` as the place staged background writes are found ("review ... with `/skills pending`"), while the notification code reports none of them (findings 10, 11). The docs point to the command; the code never tells the user a write is waiting.
- `pending_count` is documented as for notification badges (`tools/write_approval.py:131`) but its only callers are the gate-off checks (finding 10).

## Gaps

- No run of the Hermes gate was done; findings 10 and 12 rest on reading control flow (confidence medium). A run with `skills.write_approval: true` and a background review would settle both.
- Dashboard or Desktop visual review of staged skill writes: only slash routes were found (finding 9); `apps/desktop` components beyond the slash table were not read.
- Hermes `/learn` and `/refine` flows with the gate on were not traced beyond the docs line that the gate applies.
- Where an automatically created Compass skill would live so that `compass review` accepts it (finding 17): `.compass/meta/local/skills/` covers additions to shipped skills only; a path for new skills was not found. Low confidence on any answer here.
- Whether `compass review` can be invoked from the detached capture worker and what the worker does when its grace runs out first (finding 21): not established.
- Whether the "picture plus You decide" document form applies to a SKILL.md (finding 18): the rule text speaks of documents the human decides on; skills are not named in it.
- The reviewed `.compass/specs/learning/SPEC-012-learning-loop.md` was not read in full; its stated scope for skills was not extracted.
