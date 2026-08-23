---
title: "Hybrid Hierarchy Implementation Impact: CLI, Skills, Wikilinks, Migration"
type: research
status: complete
confidence: high
area: architecture
tags: [hierarchy, hybrid, units-of-work, cli, wikilinks, migration, vault-structure]
created: 2026-07-23
updated: 2026-07-23
git_branch: "master"
git_commit: "fbc32c5"
author: "researcher agent"
depends_on: ["[[SPEC-010-universal-hybrid-hierarchy]]"]
summary: "CLI, skills, wikilinks, migration impact"
---

# Hybrid Hierarchy Implementation Impact

Answers the Open Questions of [[SPEC-010-universal-hybrid-hierarchy]] with as-is evidence from `plugin/cli/`, `plugin/skills/`, `plugin/templates/`, `plugin/hooks/`, and live experiments against the real CLI. Decided shape (not relitigated): a unit of work is a root-level folder named for the work, containing its own `specs/`, `research/`, `plans/`, `decisions/` with local numbering and its own `index.md`; reserved type-folder names stay type folders; small work stays flat.

## Question

Exactly which parts of the CLI, skills, templates, and hooks assume the flat type-first layout; what a root-level unit folder does to each today; how wikilink ambiguity behaves under local numbering; what a non-destructive migration of the compass-cli artifact set requires; and what promotion-trigger options exist.

## Methodology

Read every module in `plugin/cli/` in full; grepped `plugin/skills/`, `plugin/templates/`, `plugin/hooks/` for flat-path assumptions; then built a scratch vault containing a root unit folder (`compass-cli/` with `specs/`, `research/`, `decisions/` and its own `index.md`), a signal-less unit (`bare-unit/`), and a cross-unit stem collision, and ran the real CLI (`sync`, `validate`, `tree`, `hot-path`, `next-num`, `promote`) against it. Findings marked "verified live" were observed in that run, not inferred.

## Findings

### A. How type-dir discovery works today (the reserved-name question)

1. **Discovery is a three-part hybrid: denylist + core-name list + content signal** (confidence: high)
   - `plugin/cli/vaultlib.py:13` - `NON_TYPE_DIRS = {"meta", "tmp", "archive", ".annotations"}` (denylist, plus any dot-dir at `vaultlib.py:55`).
   - `plugin/cli/vaultlib.py:16` - `CORE_TYPE_DIRS = ["specs", "plans", "research", "decisions", "lessons", "handoffs", "prs"]`, always scanned even when empty.
   - `plugin/cli/vaultlib.py:31-40` - `_has_typed_artifact`: any other subdir is admitted as a type dir if a depth-1 `*.md` OR a `*/index.md` has a `type:` frontmatter field. Rationale in [[LESSON-type-dir-discovery-needs-content-signal]] (the iwyc-unreal `claude/` false-positive incident).

2. **A unit folder WITH its own typed `index.md` is misclassified as a type directory today** (confidence: high, verified live)
   - `vaultlib.py:35` - `directory.glob("*.md")` picks up `compass-cli/index.md`; if it has `type:`, the whole unit is treated as an artifact type named `compass-cli`.
   - Live result: `discover_type_dirs` returned `['compass-cli', 'specs']`; `sync` created a `## Compass-cli` index section; nested files were scanned as `kind: child` of a nonexistent folder artifact.

3. **A unit folder WITHOUT a depth-1 typed signal is completely invisible** (confidence: high, verified live)
   - `bare-unit/specs/SPEC-001-hidden.md` (typed file at depth 2, no `bare-unit/*.md`, no `bare-unit/*/index.md`) was never discovered: not scanned, not synced, not validated, not in the tag index.
   - Its stem still resolves for wikilink purposes, because `_resolvable_names` uses `all_markdown_files` which rglobs everything (`vaultlib.py:62-77`, `validate.py:43-58`). So links to it look fine while the artifact itself is dark.

4. **The reserved-name set the CLI already encodes** (confidence: high)
   - Type names: `specs, plans, research, decisions, lessons, handoffs, prs` (`vaultlib.py:16`); infra names: `meta, tmp, archive, .annotations` + dot-dirs (`vaultlib.py:13,55`). SPEC-010's proposed reserved set matches this union exactly, plus `prs` which the spec's list omits at `SPEC-010:86` but includes in the task brief.
   - Classification options for a non-reserved root dir (do not decide here):
     - (a) Pure name rule: non-reserved = unit. Breaks custom type dirs like `retro/` that the content signal exists to keep working (`vaultlib.py:48-50`, the lesson).
     - (b) Structural signal: contains reserved-named subdirs holding artifacts = unit; depth-1 typed `*.md` = custom type dir; neither = incidental, skipped. Preserves both the lesson's cases and needs no new metadata.
     - (c) Positive marker: the unit's `index.md` carries an explicit frontmatter marker (e.g. `type: unit`). Strongest signal, consistent with the lesson's "discovery needs a positive signal" principle; tooling can write it at promotion. (b) and (c) compose.

### B. CLI impact, function by function

5. **`scan_artifacts` has no unit concept; it is the root of every downstream break** (confidence: high)
   - `vaultlib.py:180-219` - iterates `discover_type_dirs`, classifies files as `flat` / `folder-index` / `child` relative to the TYPE dir. A unit needs a fourth dimension (which unit a record belongs to) and recursion into the unit's own type dirs. Change size: M; every command consumes these records, so this is the single highest-leverage edit.

6. **`next-num`: unit-local numbering only works by accidental path traversal** (confidence: high, verified live)
   - `next_num.py:35-37` - `base = vault_root / type_dir [/ parent]`; parent is a folder-spec name inside the type dir. `compass next-num spec ../compass-cli/specs` returns the right answer purely via `..` escaping.
   - Needs a supported unit-scoped form (flag or path). Numbering logic itself (`max+1` over one directory, `next_num.py:39-46`) already IS local-per-folder and needs no change. Size: S.

7. **`sync` index generation writes links that its own `validate` flags as broken** (confidence: high, verified live)
   - `sync.py:58-65` - entry label is `[[{record['name']}]]` where `name` is TYPE-DIR-relative (`vaultlib.py:199-209`). For the unit this produced `[[specs/SPEC-001-cli-spec]]` under `## Compass-cli`.
   - `validate.py:43-58` - resolvable names are bare stems + VAULT-relative paths. `specs/SPEC-001-cli-spec` matches neither, so validate reported 3 `broken_wikilink` warnings on lines sync had just written.
   - Also `section_for` (`sync.py:25-29`) would title-case each unit into a fake type section (`## Compass-cli`). Size: M, and interacts with [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]]'s decision that indexes become fully regenerated machine artifacts - the append-only `_sync_index` (`sync.py:76-125`) is scheduled to be replaced anyway.

8. **`sync` tag index already handles units correctly** (confidence: high, verified live)
   - `sync.py:165-181` - paths are emitted vault-relative (`compass-cli/specs/SPEC-001-cli-spec.md` appeared correctly). Full regeneration each run means it self-heals after any move. No change needed once discovery classifies units.

9. **`sync` lessons catalog silently ignores any lesson not in the root `lessons/` dir** (confidence: high)
   - `sync.py:151-152` - `if record["type_dir"] != "lessons": continue`. Under "any artifact type can nest," a lesson inside a unit would never reach `meta/lessons-catalog.yaml`, i.e. never reach the hot path. Same class of filter in `_check_caps` lesson counting (`sync.py:196-199`). Size: S once records carry unit info; the design question (are lessons unit-nestable or global-only?) is the planner's.

10. **`validate`: field checks are layout-agnostic; name resolution is the gap** (confidence: high, verified live)
    - `validate.py:90-93` - `EXPECTED_FIELDS` keyed by frontmatter `type`, works anywhere a file is scanned; nested unit artifacts were checked correctly in the live run.
    - `validate.py:43-58` - `_resolvable_names` already includes vault-relative path names, so path-qualified links to unit artifacts (`[[compass-cli/specs/SPEC-001-cli-spec]]`) resolve today with zero changes.
    - What it lacks: any concept of ambiguity (see Findings D). Size: S-M depending on the ambiguity option chosen.

11. **`tree` renders only the root `specs/` type dir; units are invisible** (confidence: high, verified live)
    - `tree.py:22` - `if r["type_dir"] == "specs"`. The live tree showed only `SPEC-001-root-thing`; the unit's spec never appeared. SPEC-010 open question "does hybrid change tree/hot-path rendering": tree yes (must render units, probably unit-first with type subtrees); size S-M.

12. **`hot-path`, `touched`, `admit-check`, `clean-tmp`, `capture-bug`, `maincli` are unaffected** (confidence: high)
    - `hot_path.py:11` - fixed file list (`index.md`, `active.md`, `meta/lessons-catalog.yaml`); measured 64/5000 in the unit vault, indifferent to layout.
    - `touched.py`/`admit_check.py` treat the spec argument as an opaque vault-relative path (`admit_check.py:25-28`), which works for unit paths as-is. `bugs.py` touches only `tmp/compass-bugs` (`bugs.py:18-19`). No changes.

13. **`fix-frontmatter` would invent a bogus `type: compass-cli` for unit files missing `type:`** (confidence: high)
    - `fix_frontmatter.py:20-34` - `SINGULAR.get(type_dir, type_dir)` falls back to the directory name; with the unit misclassified as a type dir, a typeless file inside gets `type: compass-cli` instead of deriving from the sub-path (`specs/` -> `spec`). Size: S once records carry the real type dir.

14. **`promote` finds only depth-1 flat specs by ID; explicit paths already work on nested files** (confidence: high, verified live)
    - `promote.py:20-24` - `_resolve` checks `vault_root/type_dir/<target>.md` only; `promote SPEC-001-cli-spec` failed, `promote compass-cli/specs/SPEC-001-cli-spec.md` succeeded and produced a correct nested folder spec. `_git_mv` (`promote.py:27-35`) is a reusable helper; the rest of unit promotion is new code.

### C. Skills, templates, hooks

15. **hooks.json matchers already cover unit folders** (confidence: high)
    - `plugin/hooks/hooks.json:12,24,36` - `Write/Edit/MultiEdit(.compass/**/*.md)`; `**` matches any depth, so a write inside `.compass/compass-cli/specs/` fires `compass sync` today. The Stop/SubagentStop hooks reference only `tmp/` paths. No hook changes needed.
    - `sync.py:279` - the hook path filter is just "`/.compass/` in path"; layout-agnostic.

16. **Skills that hardcode flat write destinations (would drop unit artifacts in the wrong place)** (confidence: high)
    - `plugin/skills/spec/SKILL.md:59` - new specs always to `.compass/specs/` with the root-glob JIT rule.
    - `plugin/skills/retroactive/SKILL.md:48,95` - specs/ADRs always root.
    - `plugin/skills/research-codebase/SKILL.md:82`, `research-papers/SKILL.md:82` - research always to `.compass/research/`.
    - `plugin/templates/agents/researcher.md:65`, `reviewer.md:63`, `planner.md:117`, `builder.md:74` - same pattern in agent templates.
    - Each needs a "resolve the destination root: vault root or current unit" step; the pattern is one shared paragraph, not per-skill logic.

17. **The documented JIT numbering globs are root-only and now wrong for units** (confidence: high)
    - `plugin/skills/obsidian/SKILL.md:125-127` - `glob '**/.compass/specs/SPEC-N-*.md'` etc. only sees root type dirs; a unit's local numbering has no documented rule. The CLI's `next-num` (Finding 6) is the natural single source of truth to point these at.

18. **Skills with flat-scope flags or dir checklists** (confidence: high)
    - `plugin/skills/taxonomize/SKILL.md:18-19` - `--specs`/`--plans` operate only on root dirs.
    - `plugin/skills/checkup/SKILL.md:27` - required-directories list is the flat set; a unit folder would be unexpected (whether it errors depends on the skill's prose interpretation - it lists "required", not "exclusive").
    - `plugin/skills/promote-spec/SKILL.md:12,23,30` - flat-spec-to-folder-spec only; the unit case is a different operation.
    - `plugin/skills/methodology/SKILL.md:250-266` and `plugin/skills/obsidian/SKILL.md:144-156` - the canonical layout diagrams show only the flat scheme; these are the documents every agent learns the layout from.
    - Unaffected: `annotate` (keys by vault-relative path, any depth), `handoff` (own subdir scheme), `lessons`/`lesson-write` (root `lessons/` - see Finding 9's design question), `setup`/`update` (copy plugin files, don't touch layout), `vault-health`/`index-sync` (thin CLI wrappers, inherit whatever the CLI does).

### D. Wikilink resolution and ambiguity

19. **Validate does set-membership, not resolution; it cannot detect ambiguity at all** (confidence: high, verified live)
    - `validate.py:43-58` - names is a `set`; two files with the same stem collapse into one entry. A cross-unit collision (`specs/SPEC-002-setup.md` vs `other-unit/specs/SPEC-002-setup.md`) produced zero warnings; `[[SPEC-002-setup]]` "resolved" with no notice of which file.
    - The agent-side convention (`plugin/templates/rules/wikilinks.md:15`: glob `.compass/**/<name>*.md`, shortest path wins) silently picks the root file - verified: the glob returned both, and shortest-path tie-breaking selects `specs/SPEC-002-setup.md`.

20. **Collision surface under local numbering is stem-level, not number-level** (confidence: high)
    - Stems include the descriptive slug (`SPEC-001-cli-spec`), so two units collide only when BOTH number and slug match (e.g. every unit having a `SPEC-001-setup`). Bare-number links like `[[SPEC-001]]` (used in `wikilinks.md:11` examples) prefix-match every unit's SPEC-001 and become ambiguous immediately.

21. **Path-qualified links already work end-to-end; that is the only currently-supported disambiguation** (confidence: high)
    - `validate.py:56-57` adds the vault-relative path (`compass-cli/specs/SPEC-001-cli-spec`) to resolvable names; Obsidian accepts slashes in wikilinks (`obsidian/SKILL.md:158-163` documents the type-dir version of this).
    - Handling options (planner/human decide):
      - (i) Require path-qualified links whenever the target lives in a unit; sync emits them. Deterministic; verbose; existing short links to migrated files must be rewritten or left relying on (iii).
      - (ii) Unit-qualified short form (`[[compass-cli/SPEC-001-cli-spec]]`, unit + stem, eliding the type dir): shorter, but a new name shape that `_resolvable_names`, sync, and the agent glob convention must all learn.
      - (iii) Keep short links + add ambiguity detection: build a name-to-paths map instead of a set in `validate.py:43-58` and warn `ambiguous_wikilink` when a stem maps to >1 file; the shortest-path rule stays as documented tie-break. Cheapest; makes the failure visible instead of impossible.
      - (i)/(ii) compose with (iii); (iii) alone leaves silent-wrong-target possible only until the warning is acted on.

### E. Migration of this vault's compass-cli set

22. **The obvious first unit is the five files SPEC-010 itself names** (confidence: high)
    - `specs/SPEC-004-mechanical-work-off-the-agent-budget.md`, `decisions/ADR-005-compass-cli-for-mechanical-work.md`, `plans/PLAN-002-compass-cli-implementation.md`, `research/RESEARCH-cli-and-hook-command-contract.md`, `research/RESEARCH-cli-token-reduction-measurement.md` (`SPEC-010:20`). Their `depends_on` graph is closed over each other plus foundation ADRs/lessons that stay put. Borderline, human's call: [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] (an index feature the CLI implements) and the two CLI handoffs (handoffs are session continuity; nothing scans `handoffs/` per-unit today).

23. **A pure move breaks zero wikilinks; stems keep resolving from anywhere** (confidence: high, verified live)
    - Both resolution paths are vault-wide: `validate.py` via `all_markdown_files` rglob (`vaultlib.py:62-77`) and the agent glob `.compass/**/<name>*.md`. Inbound references (30+ sites: `index.md:23,37-38,46,54`, `active.md:48,66`, SPEC-001/006/007/008/009/010, RESEARCH-gsd, RESEARCH-rag, the handoffs) all use stems, so no link rewriting is needed as long as filenames are unchanged.
    - Keeping original numbers (SPEC-004 stays SPEC-004 inside `compass-cli/specs/`) preserves numbering history; `next-num`'s max+1 tolerates the resulting gaps in root `specs/` and continues from 004 inside the unit (`next_num.py:39-46`).

24. **What migration MUST rewrite: the root index; what self-heals: the tag index** (confidence: high)
    - `sync.py:76-78` - `_sync_index` is append-only; after a move the old `## Specs`/`## Plans`/`## Decisions`/`## Research` entries stay, and because stems still resolve (Finding 23), `validate` will NOT flag them as stale (`validate.py:99-105` only catches dangling names). Migration must edit `index.md` entries itself - or land after SPEC-005's full-regeneration index, which erases the problem.
    - `meta/tag-index.yaml` fully regenerates each sync (`sync.py:165-181`) - no action. `active.md`/`backlog.md` prose links survive via stems.
    - The unit additionally needs its own `index.md` authored (SPEC-010's "presents the unit as one thing"), which is also the discovery/marker surface from Finding 4(c).

25. **`compass promote` is a partial base: the git-mv helper reuses; the operation is new** (confidence: high)
    - Reusable: `_git_mv` with rename fallback (`promote.py:27-35`, fallback verified live in a non-repo dir), the resolve-by-id-or-path pattern (`promote.py:16-24`), `write_text_lf` frontmatter editing (`promote.py:38-43`).
    - Not reusable: promote moves ONE file into a folder named after itself; unit promotion moves N files from up to 4 type dirs into `unit/<type>/`, creates the unit `index.md`, and fixes the root index (Finding 24). Shape: a new subcommand (or `promote --unit`) sharing helpers, roughly the size of `promote.py` + `sync`'s index-edit logic.

### F. Promotion trigger options (for the ADR; human decides)

26. **Existing precedent: the folder-spec trigger is "3+ sub-concerns OR ~2K tokens"** (confidence: high)
    - `.compass/decisions/ADR-004-hierarchical-specs-with-facets.md:38`; operationalized in `promote-spec/SKILL.md:7,12`. SPEC-010 requires the unit trigger to be "clear, mechanical" (`SPEC-010:42`) yet leaves it open (`SPEC-010:87`).
    - Candidate triggers:
      - **T1 - Type-spread threshold:** work traceable to one spec has artifacts in >=3 distinct type folders (spec + plan + ADR, spec + research + plan, ...). Mechanical: computable from `depends_on` frontmatter, which every CLI-set file already carries (e.g. `PLAN-002:11`, `ADR-005:13`). Misses artifacts whose authors omitted `depends_on`; measures cohesion, which is what "unit of work" means.
      - **T2 - Artifact-count threshold:** >=N artifacts (e.g. 5, the CLI set's size) reference one root spec, regardless of type spread. Simplest to compute; blind to cohesion (5 research docs on one spec is a folder-spec case, not a unit).
      - **T3 - Human choice at plan approval:** the planner proposes a unit when a plan will produce multiple artifact types; the human approves with the plan. Matches the governance gradient (structure is strategic) but is not by itself the mechanical rule SPEC-010 demands.
      - **T1+T3 hybrid:** the CLI detects T1 and reports it (a `validate`/`checkup` advisory, like the existing cap warnings at `sync.py:184-208`); the human approves the promotion. Detection mechanical, decision human - the same split promote-spec already uses ("the CLI does the move; this skill decides when," `promote-spec/SKILL.md:3`).

27. **Depth interaction: a unit adds one navigation level against SPEC-005's 3-step cap** (confidence: medium)
    - `SPEC-005:37,61` decides "no path is more than three steps deep from the root" and a root index descending <=2 levels. Root -> unit index -> unit type dir -> folder-spec index -> child is 4 steps if folder specs nest inside units. Either the cap counts from the unit index (units become sub-roots, consistent with "local numbering, own index"), or folder-spec nesting inside units is depth-limited. SPEC-005 is still `draft`/on-hold (handoff `2026-06-19_10-33-39`), so the two specs can be reconciled in one ADR. Confidence medium: the caps are spec text, not shipped code.

## Contradictions

- `sync` and `validate` disagree on link identity today: sync writes type-dir-relative names (`vaultlib.py:199-209` via `sync.py:63`), validate resolves stems and vault-relative paths (`validate.py:43-58`). Invisible in a flat vault (depth-1 stems equal their rel names); a unit or any nested artifact under a discovered extra dir exposes it as self-inflicted broken-link warnings (verified live).
- SPEC-010's reserved-name list (`SPEC-010:86`) omits `prs` and `tmp`; the CLI's actual sets include both (`vaultlib.py:13,16`). The ADR should state the union explicitly.
- [[LESSON-type-dir-discovery-needs-content-signal]] pushes for content signals over name lists, while the decided reserved-name rule is a name list. Not a true conflict - the reserved names classify KNOWN dirs, the lesson governs UNKNOWN dirs - but the ADR must keep the content signal for non-reserved, non-unit dirs (`retro/`-style custom types) or it regresses the lesson's fix.

## Gaps

- No code path was tested for `compass sync` running INSIDE a unit after discovery is fixed (the fix does not exist yet); the sync findings describe today's misclassification behavior, not post-fix behavior.
- Whether lessons and handoffs may nest inside units is undecided; Findings 9 and 22 show the concrete cost of each answer (catalog invisibility; nothing scans unit handoffs).
- The unit `index.md` authored-body + machine-listing delimiter is deferred to SPEC-005's ADR (`SPEC-005:80`); this research only establishes that the unit index doubles as the classification marker if option 4(c) is chosen.
- Obsidian's own link-autocomplete behavior with duplicate stems across folders was not tested (agent-side resolution was); Obsidian resolves short links to "closest by path," which may differ from the vault's shortest-path rule.

## Recommendation

Proposed for the human's decision, not decided here:

- **Classification:** reserved-name list for the root (union of `vaultlib.py:13,16` + `archive`), plus a positive marker in the unit's `index.md` (option 4(c)), keeping the content signal for non-reserved custom type dirs. Two positive signals, no guessing, no regression of the discovery lesson.
- **Ambiguity:** ship ambiguity detection in `validate` first (option 21(iii), a set-to-map change), with sync emitting path-qualified links for unit artifacts (21(i)) so machine-written links are never ambiguous; humans may keep writing short links until validate warns.
- **Trigger:** T1+T3 - mechanical type-spread detection reported by the CLI, human approves the promotion. It is the only candidate that satisfies both SPEC-010's "clear, mechanical rule" and the methodology's human-owns-structure gradient, and it mirrors the proven promote-spec split.
- **Sequencing:** the sync/validate name-identity contradiction and `scan_artifacts` unit-awareness are the load-bearing changes; everything else (tree, next-num, fix-frontmatter, skills prose) follows mechanically from records that know their unit.
