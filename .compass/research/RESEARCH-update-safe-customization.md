---
title: "Update-Safe Customization: Overlay Prior Art, and the Corpus That Turned Out Empty"
type: research
status: complete
confidence: high
area: methodology
tags: [update, customization, overlays, drop-ins, patches, markers, corpus]
created: 2026-08-30
updated: 2026-08-30
author: researcher-consolidation
summary: "overlay mechanisms are well-charted (drop-in dirs dominate, patches fail loudest, markers fail silently), but SPEC-014's benchmark corpus does not exist: zero content customizations survive in the Defold projects and models.yaml is adopted nowhere"
depends_on: ["[[SPEC-014-update-safe-customizations]]", "[[ADR-015-self-update-on-session-start]]"]
---

# Update-Safe Customization

## Question

[[SPEC-014-update-safe-customizations]]: how should project-local workflow customizations survive an update that now fires at every session start? Two axes ran in parallel - external prior art for overlay mechanisms, and a codebase/corpus pass over what Compass actually overwrites and what real customizations exist.

## Synthesis

**The mechanism question is well-answered by prior art.**

- **Drop-in directories dominate** as the shape: systemd `.d/*.conf`, nginx/sshd `conf.d`, kustomize overlays, Compose override files. A local file states only its delta; the shipped file stays authoritative. The recurring trap is list-valued directives, where the merge *accumulates* rather than replaces and needs an explicit reset (systemd's empty `ExecStart=`, Compose's `!override` tag) - the same trap would apply to any list-shaped Compass content.
- **Patch-based approaches fail loudest, which is a feature**: Debian's `dpkg-source` demands zero-fuzz application, so upstream drift becomes a hard, visible failure rather than a silent wrong merge. `git rebase --onto` gets 3-way merge for free but inverts `ours`/`theirs`.
- **Marker splicing (Ansible `blockinfile`) fails silently and worst**: it locates its block by exact marker text, so if the marker or surrounding file changes, the old block is orphaned in place while a second copy is inserted. For markdown files a human also edits, this is the highest-risk option.
- **Claude Code answers this exact problem twice, differently, in one product**: `settings.json` uses a five-file precedence stack with list-union for keys like `permissions.allow`, while `CLAUDE.md` simply concatenates every discovered file root-to-leaf (with `CLAUDE.local.md` appended right after) - **shipped-plus-local with zero merge logic**. For prose-shaped content, concatenation is the precedent that needs no anchors, no patches, and cannot go stale.
- **A documented gap worth knowing**: Claude Code's *plugin* skills are namespaced (`plugin:name`) and therefore cannot be shadowed by a same-named local skill, unlike bundled skills which can. Several third-party posts generalize the bundled behavior to plugins incorrectly. The host tool does not solve this for plugin-shipped files.
- **Staleness detection has precedent** (`systemd-delta`, kustomize's `test` op, `claude doctor`), and none in AI tooling - no Cursor/Copilot/aider equivalent exists.

**The corpus question returned a result that undercuts the spec's premise.**

- Blast radius confirmed: `self_update.py:_apply()` wholesale-replaces `.claude/agents/*.md`, `.claude/rules/*.md`, `.claude/skills/*/*.md`, and deletes-and-recreates `.claude/cli/`. Only `settings.json` is merged. So the danger is real and, since [[ADR-015-self-update-on-session-start]], automatic.
- **Zero content customizations exist.** Diffing the Defold public and private clones against the Compass source at their installed commit (CRLF-normalized) found every shipped agent, rule, and skill **byte-identical**. There is nothing to protect on disk.
- **The benchmark named in the spec is gone.** Defold's own `ADR-001-upstream-first-workflow` states upstream-sweep customizations were written into `compass-pipeline.md`, `researcher.md`, `pr-describe.md`, and `autopilot/SKILL.md`. Grepping those four files for the ADR's own keyword returns nothing. `.claude/` carries no git history there (excluded via `.git/info/exclude`), so whether update wiped them or they were never applied cannot be determined from evidence.
- **The one real local addition is a new file, not a modification**: a `sync-forks` skill Compass does not ship, independently authored in both clones. New files already survive update - `_apply()` copies shipped skills and deletes only names in `RETIRED_SKILLS`. The customization form that actually exists is the one already safe.
- **The precedent is unadopted**: no `.compass/meta/models.yaml` exists in any of the three projects inspected. The mechanism SPEC-014 proposes to imitate has zero users.
- **Vault persistence is inconsistent** across the corpus: `.compass/` is git-excluded in the public Defold repo but tracked (56 files) in `defold-private`.

## What this means for the spec

SPEC-014's success criteria are written against a corpus that no longer exists ("the Defold customization set survives a real update round-trip intact"). That criterion currently defines no input class and cannot be tested, which is a spec defect to report rather than an equivalence class to invent ([[LESSON-untestable-criterion-is-a-spec-defect]]). The mechanism question is ready to decide; the validation question needs a human ruling on what the benchmark now is.


## Axis: Overlay prior art (rs-overlay-priorart)

Research axis for SPEC-014 ("project-local workflow customizations survive update"). Facts only, no Compass recommendation.

### Finding 1: systemd drop-ins: `.d` directory overlay with per-directive accumulate-vs-reset semantics

Mechanism: `systemctl edit <unit>` creates `/etc/systemd/system/<unit>.d/*.conf`; systemd loads the vendor unit first, then merges every `.conf` in the directory in lexicographic order (numeric prefixes like `10-`, `90-` control order). Only the changed directives need to be present; the rest of the vendor unit stays in effect. List-style directives (`ExecStart=`, `ListenStream=`) accumulate rather than replace, so replacing one requires an explicit empty-value reset line (`ExecStart=` followed by the new value) before retyping it.

Failure mode: if the reset line is omitted, the new value silently appends to the old list instead of replacing it (multiple `ExecStart=` is a hard error unless `oneshot`) — a silent-wrong-behavior class, not a rejection. Dependency directives (`After=`, `Requires=`) cannot be reset to empty in a drop-in at all; the only fix is `systemctl edit --full`, which copies the whole unit and stops receiving upstream changes to it.

Detection: `systemd-delta` lists every unit with an override (`--type=extended` shows only drop-in, not full-replacement, overrides); `systemctl show -p DropInPaths -p NeedDaemonReload <unit>` and `systemctl cat <unit>` show the effective merged result.

Confidence: high (official-adjacent docs, man-page-derived behavior, corroborated across multiple guides).
Evidence: https://www.baeldung.com/linux/systemd-modify-config, https://github.com/systemd/systemd/issues/21461 (open RFE for append-not-reset syntax), https://oneuptime.com/blog/post/2026-03-02-how-to-override-systemd-service-parameters-with-drop-in-files-on-ubuntu/view

### Finding 2: Kubernetes kustomize: strategic-merge vs JSON6902, and index-fragility as the JSON6902 failure mode

Mechanism: `patches` (or the older `patchesStrategicMerge`/`patchesJson6902`) apply on top of `resources` in a base; strategic merge patches follow JSON/YAML merge-by-key semantics (good for additive field changes, replacing scalars), JSON6902 (RFC 6902) uses explicit `add`/`remove`/`replace`/`move`/`test` ops addressed by JSON pointer path, needed for deletions and array-index surgery that strategic merge handles poorly or not at all.

Failure mode: JSON6902 patches are index-addressed, so if the base reorders or grows its list (e.g., a new sidecar container inserted upstream), an index-based `add`/`remove`/`replace` silently targets the wrong array element — no error, wrong resource state. The RFC's own `test` op can guard this (aborts if the value at a path doesn't match expectation) but only converts silent-wrong into a hard stop; it does not adapt to the new position.

Confidence: high (practitioner consensus across independent sources, aligned with RFC 6902 semantics).
Evidence: https://www.fractolog.com/2025/09/kustomize-strategic-merge-patches-are-incomplete/, https://oneuptime.com/blog/post/2026-02-09-kustomize-patchesjson6902-arrays/view

### Finding 3: Docker Compose override files: per-key merge rules plus explicit escape tags

Mechanism: `compose.yaml` + `compose.override.yaml` (or `-f a -f b`, later file wins on conflict) merge per attribute type: scalars replace, mappings deep-merge by key, sequences append (not replace) by default. Compose 2.24+ adds two YAML tags to break the default: `!override` fully replaces an attribute (e.g., replacing a whole `ports` list instead of appending), `!reset` removes a declaration entirely from the merged result.

Failure mode: the append-by-default rule for sequences is a common silent surprise — an override file adding a port mapping duplicates rather than replaces unless `!override` is used, producing two exposed ports instead of one, with no warning.

Detection: `docker compose config` renders and prints the fully merged, resolved configuration before anything starts, letting you diff expected vs actual merge result.

Confidence: high (official Docker docs).
Evidence: https://docs.docker.com/reference/compose-file/merge/

### Finding 4: nginx `include`/conf.d vs sshd `Include`/conf.d: opposite precedence direction for the same drop-in pattern

Mechanism: both use glob-based `include`/`Include` directives to pull a directory of numbered files into the main config. nginx merges included directives into the current context and **the last-defined value wins** on conflict. Recent OpenSSH's `sshd_config`, by contrast, honors **only the first occurrence** of a given keyword — later ones are ignored — so distros differ on whether to put `Include /etc/ssh/sshd_config.d/*.conf` at the top (drop-ins win) or the bottom (drop-ins lose unless numbered to sort first... actually still lose, since first-wins means top-of-file wins regardless of position of Include).

Failure mode: an admin who assumes nginx's last-wins model when writing an sshd drop-in gets silently ignored settings — no error, `sshd -t` reports valid syntax because the directive is syntactically fine, it's just shadowed by an earlier occurrence. Neither tool has a built-in "is my override actually in effect" check beyond re-deriving the merged semantics by hand or running the dump commands below.

Detection: `nginx -T` dumps the fully merged config; for sshd there is no direct equivalent, only `sshd -t` (syntax only, not precedence-aware) and manual reasoning about `Match`/`Host` block boundaries (concatenating included files changes `Match` scoping, so files can't just be diffed/concatenated to infer effective config).

Confidence: medium (distro conventions and precedence-direction claims are corroborated across sources but not one single canonical citation; verify against `man sshd_config` for a given OpenSSH version).
Evidence: https://ostechnix.com/drop-in-d-directories-linux-configuration-explained/, https://www.baeldung.com/linux/nginx-configuration-include-directive

### Finding 5: Debian quilt/dpkg-source patch series: zero-fuzz requirement turns upstream drift into a hard build failure (mostly)

Mechanism: a Debian source package keeps local patches as a `debian/patches/series` list of unified diffs (quilt format) applied with `-p1` over a pristine upstream tarball at build time. dpkg-source enforces stricter application than quilt's own default: patches must apply with **zero fuzz** (no ignored context lines); "offset" (same context, shifted line numbers) is fine, "fuzz" (context itself had to be guessed) is not.

Failure mode: when a new upstream tarball changes the surrounding lines, the patch either applies with fuzz (dpkg-source treats this as a build error, forcing a `quilt pop -a` / `push+refresh` loop to regenerate the diff) or fails outright, leaving a `.pc/` directory in a broken partially-applied state that must be cleaned before retry. A documented historical gotcha: `dpkg-source --before-build` could silently continue if the *first* patch in the series applied but a later one didn't (e.g., because upstream had merged it) — producing a package silently missing patches with no build error at all.

Confidence: high (Debian policy documents, bug tracker, maintainer guide agree).
Evidence: https://www.man7.org/linux/man-pages/man1/dpkg-source.1.html, https://raphaelhertzog.com/2012/08/08/how-to-use-quilt-to-manage-patches-in-debian-packages/, https://bugs.debian.org/652970

### Finding 6: Nix overlays/overrideAttrs: customization as functional composition, not file splicing — a different failure class entirely

Mechanism: `.override` rebinds the *arguments* a package's build function was called with (derivation store path name unchanged); `.overrideAttrs` rewrites the *derivation attributes themselves* (build inputs, `src`, `version`) via a function taking `(finalAttrs, prevAttrs)`. Neither alone changes the shared package set; an **overlay** (`final: prev: { ... }`) is the delivery mechanism that applies such overrides globally so other packages depending on the same attribute see the change too. `lib.composeExtensions` is needed to layer overlays on nested/scoped package sets (Python, Haskell) without discarding earlier overlays' overrides.

Failure mode: because there is no textual patch to reject, "upstream changed underneath" surfaces as an **evaluation-time or build-time error** instead — a hash mismatch when `src` is overridden and the tarball changed shape, or a missing/renamed attribute when the base expression's structure moved. There is no fuzz/offset concept; it's binary: either the Nix expression still evaluates and builds, or it errors with a stack trace pointing at the failing attribute.

Confidence: high (official-adjacent wiki and nixpkgs docs, internally consistent).
Evidence: https://wiki.nixos.org/wiki/Overlays, https://ryantm.github.io/nixpkgs/using/overrides/

### Finding 7: Homebrew formula DATA/external patches: strip-level and whitespace fragility, `inreplace` as the version-churn-resistant escape hatch

Mechanism: formulas patch source either via `patch do ... end` blocks (external URL+sha256, or repo-local files) or inline `__END__`-delimited `DATA` patches embedded in the formula file, applied with a declared strip level (`:p1` default, `:p0` alternative). `inreplace` is a separate, non-diff mechanism: a literal string/regex substitution instead of a context patch.

Failure mode: two independent fragility sources compound on upstream version bumps — (a) wrong strip level silently fails to locate files if the diff wasn't generated with `a/`/`b/` prefixes, (b) any context-diff patch is exposed to the same fuzz/offset problem as quilt when the tarball changes around the patched lines. Homebrew's own guidance recommends `inreplace` specifically because a literal substitution has no "context" to go stale — it either finds the string or it doesn't, collapsing the fuzzy-match failure mode into a clean pass/fail.

Detection: `patch -p1 --dry-run < patch` plus inspection of the resulting `.rej` reject files; `brew info --json` surfaces each patch's declared `strip`/`url`/`file`/`data` metadata for audit.

Confidence: medium (Homebrew docs plus secondary tutorials agree; the `inreplace`-as-mitigation framing is a documented convention, not a formal spec).
Evidence: https://docs.brew.sh/Formula-Cookbook, https://github.com/Homebrew/brew/pull/22144

### Finding 8: `git rebase --onto` as a maintenance model: transplants a patch series, with an inverted `ours`/`theirs` in the underlying 3-way merge

Mechanism: `git rebase --onto <new-upstream> <old-upstream> <patch-branch>` replays each local commit, one at a time, as a diff applied on top of the new upstream tip — each replay is a 3-way merge (common ancestor = the commit's own parent before rebase, "ours" = the rebase-in-progress branch, "theirs" = the original commit being replayed). Because replay is commit-by-commit, `rerere` (reuse recorded resolution) auto-resolves conflicts identical to ones already resolved earlier in the same rebase, and squashing local commits first reduces the number of hunks replayed against a moved target.

Failure mode: conflicts are the explicit, blocking failure mode — git stops, names the exact commit ("could not apply <sha>... <subject>"), and requires `--continue`/`--skip`/`--abort`. The documented gotcha specific to this workflow: the conflict-marker sides are **swapped** relative to intuition — "ours" is the already-rebased result (i.e., new upstream), "theirs" is your own patch — so blindly taking "ours" during a downstream-patch rebase discards your customization, not upstream's change.

Detection: `git rebase --show-current-patch` (equivalent to `git show REBASE_HEAD`) shows exactly what failed to apply; there is no silent-failure path — an unresolved conflict always blocks progress.

Confidence: high (official git-scm documentation plus independent corroboration on the ours/theirs inversion).
Evidence: https://git-scm.com/docs/git-rebase, https://medium.com/@yussufshaikh/power-of-git-rebase-to-resolve-conflicts-from-upstream-7f2aefbd19f

### Finding 9: Ansible `blockinfile`: marker-comment splicing, idempotent by construction, but silently orphans blocks if the marker text itself changes

Mechanism: `blockinfile` injects a multi-line block wrapped in `# BEGIN ... #{mark}` / `# END ... {mark}` comment markers (customizable text and comment-character per file format); on each run it searches the target file for those exact marker strings, and if found, replaces everything between them with the current `block:` content — this marker lookup, not line-diffing, is what makes repeated runs idempotent ("ok" if unchanged, block replaced if changed).

Failure mode: the module's own documentation-derived gotcha is that if you change the `marker`/`mark_begin`/`mark_end` value between playbook versions, the old marked block is no longer found by string match — Ansible doesn't detect "this looks like an old version of my block," it just doesn't find a match and inserts a brand-new block, leaving the orphaned old one in the file (silent duplication, not an error). This is the direct marker-based analogue of the JSON6902 index-fragility failure: a stable identity string standing in for a stable position, both breaking silently when that identity changes upstream.

Confidence: high (module documentation and consistent secondary sources).
Evidence: https://labex.io/tutorials/ansible-ansible-blockinfile-391150, https://www.ansiblebyexample.com/articles/ansible-blockinfile-module-manage-text-blocks

### Finding 10: VS Code settings: five-tier precedence stack with an orthogonal language-specific override cutting across it

Mechanism: precedence lowest-to-highest is default → extension-contributed default → user (`~/…/settings.json`) → workspace (`.code-workspace`) → folder (`.vscode/settings.json`); extensions register their own defaults into the same "Default Settings" tier user/workspace settings then override. Language-specific settings (`"[python]": {...}`) sit on a separate axis that always outranks non-language-specific settings at any lower or equal scope — e.g., a language-specific *user* setting beats a non-language-specific *workspace* setting, inverting the normal scope order.

Failure mode: not a rejection/silent-noop system — it's pure declarative merge with no "did this apply" ambiguity beyond the two orthogonal axes (scope vs. language-specificity) interacting non-obviously. The main practical friction the docs flag: workspace/folder settings committed to a repo leave no built-in way for an individual to opt out short of gitignoring the file themselves.

Confidence: high (official VS Code docs).
Evidence: https://code.visualstudio.com/docs/configure/settings

### Finding 11: Claude Code `settings.json`: five explicit files with list-union merge, so local additions to a list-valued key always survive a shared-file refresh

Mechanism: five sources form a strict override stack (highest first): managed (`managed-settings.json`/MDM/console) → `--settings` CLI flag → `.claude/settings.local.json` (personal, per-project) → `.claude/settings.json` (shared, committed) → `~/.claude/settings.json` (personal, global). Critically, when the *same list-valued key* (e.g. `permissions.allow`) is set in more than one file, Claude Code **unions the lists** rather than letting the higher file replace the lower one's entries — so a local addition to `permissions.allow` is preserved even after the shared project file is rewritten by an update, because the local file's entries are combined in, not overridden out. Three specific keys are carved out as *not* following list-union: `fallbackModel` (ordered chain, whole value taken from highest-precedence definer), `modelPicker` (single ordered list, never merged across sources), and `availableModels` (managed value wins outright and ignores lower-scope additions when a managed source defines it).

Failure mode/detection: `/status` shows a `Setting sources` line naming every settings file actually loaded (but not which file supplied which key); `claude doctor` lists entries Claude Code rejected as invalid JSON or unrecognized values. A broken/invalid local file degrades to "Settings Warning" (skip just the bad entries) or "Settings Error" (skip the whole file) at session start rather than silently vanishing.

Confidence: high (official Claude Code docs, directly fetched).
Evidence: https://code.claude.com/docs/en/settings (sections "Settings precedence", "Lists merge instead of overriding", "Confirm what loaded")

### Finding 12: Claude Code `CLAUDE.md`: concatenation, not override — a structurally different answer to the same problem within the same product

Mechanism: unlike `settings.json`'s override stack, every discovered `CLAUDE.md`/`CLAUDE.local.md` in the directory hierarchy is **concatenated into context**, ordered root-to-leaf (ancestor directories first, working directory last), with `CLAUDE.local.md` appended immediately after `CLAUDE.md` within each directory. `@path/to/file` import syntax pulls in additional files at launch (max 4 hops recursive), resolved relative to the importing file. A managed/enterprise `CLAUDE.md` (or a `claudeMd` key in managed settings) loads before user and project files and cannot be excluded; `claudeMdExcludes` lets a user/project/local scope skip specific ancestor files by glob (useful in monorepos), merging across scopes as an array.

Because the shipped file (`CLAUDE.md`) and the local-only file (`CLAUDE.local.md`) are two separate files that both always load, a customization written into `CLAUDE.local.md` survives an update overwriting `CLAUDE.md`, with zero merge logic required — this is the simplest possible variant of the shipped-plus-local-delta pattern (two files, both loaded, no splicing).

Failure mode: none in the "rejected/orphaned" sense — the only way an addition stops applying is if the file itself is deleted, exceeds the 4 MiB hard skip limit, or (per the docs' own adherence caveat) contradicts another loaded file, in which case Claude "may pick one arbitrarily" with no error surfaced. `/context` lists which memory files actually loaded, serving as the equivalent of a "doctor" check for this mechanism.

Confidence: high (official Claude Code docs, directly fetched).
Evidence: https://code.claude.com/docs/en/memory (sections "Choose where to put CLAUDE.md files", "How CLAUDE.md files load", "Exclude specific CLAUDE.md files")

### Finding 13: Claude Code skills/commands: bundled skills can be shadowed by same-named user/project skills, but plugin skills cannot — they're namespaced instead, which is a documented gap for the exact "override a plugin file" case

Mechanism, verbatim from official docs: "When skills share the same name, Claude Code resolves the conflict by source: Across levels, enterprise overrides personal, and personal overrides project... A skill at any of these levels also overrides a **bundled** skill with the same name, but not the bundled skill's aliases... **Plugin skills use a `plugin-name:skill-name` namespace, so they can't conflict with other levels**" — a plugin's `deploy` skill becomes `/my-plugin:deploy` and loads *alongside*, not instead of, a project's own `/deploy`.

Failure mode/gap: this means the "create a same-named override at a higher-precedence location" pattern — which does work for the built-in bundled skills — does **not** work for plugin-shipped skills at all, because namespacing prevents the name collision from ever occurring; there is no shadow-by-name mechanism for plugin content. The only documented ways to change a plugin skill's *visibility* without editing it are `skillOverrides` in settings (on/off/name-only/user-invocable-only, explicitly "for skills whose SKILL.md you don't want to edit"), which the docs explicitly state does **not** apply to plugin skills ("Plugin skills are not affected by `skillOverrides`. Manage those through `/plugin` instead") — leaving disable/uninstall the plugin as the only sanctioned lever, not partial customization.

Contradiction flagged: multiple secondary/blog sources (e.g., shiplight.ai, mdskills.ai) claim a general "personal beats bundled, project beats bundled" **priority chain** that they describe as also covering plugin-vs-personal collisions, implying you can shadow a plugin skill by name. The official docs contradict this for plugin skills specifically — namespacing, not override, is the actual mechanism, and it is explicitly not a solution to "shipped-plus-local-delta" for plugins.

Confidence: high for the official-docs claims (direct quote); low for the secondary-source "priority chain overrides plugins too" claim, which appears to be an inaccurate generalization from the bundled-skill case.
Evidence: https://code.claude.com/docs/en/skills (section on name-collision resolution, `skillOverrides`), contradicted-secondary: https://www.shiplight.ai/blog/claude-code-plugins

### Finding 14: Cursor rules: three merged (not override-replace) sources plus a legacy file with unreliable partial support

Mechanism: Team Rules (dashboard, org-wide) → Project Rules (`.cursor/rules/*.mdc`, versioned with the repo) → User Rules (plain text, machine-global) — per official docs, "all applicable rules are merged" and loaded together; conflicts are resolved by the stated precedence order (Team > Project > User) only when guidance actually contradicts. `.mdc` frontmatter (`description`, `globs`, `alwaysApply`) is what enables conditional/scoped loading; plain `.md` files in the same directory work but lose that conditional-loading capability. `AGENTS.md` (plain, no config) is the cross-tool fallback Cursor also reads, with more specific directory locations taking precedence over less specific ones.

Failure mode: the deprecated single-file `.cursorrules` at project root is the interesting case — sources disagree on whether it silently stops working (one source says Agent mode ignores it entirely while completions still honor it) or merely "still works, but migrate." This is a documented **silent partial-support** failure mode: the file appears present and correctly formatted, gives no error, but may be silently inert for a subset of the tool's surfaces (Agent mode) while still active for others (Tab completion).

Confidence: medium (official Cursor docs confirm the merge-and-precedence model; the exact `.cursorrules`-in-Agent-mode behavior is only corroborated by secondary sources and conflicts between them).
Evidence: https://cursor.com/docs/rules, https://forum.cursor.com/t/rules-hierarchy-in-cursor/108589

### Finding 15: GitHub Copilot custom instructions: two-tier files with per-surface silent absence as the failure mode

Mechanism: `.github/copilot-instructions.md` (repo-wide) and one or more `.github/instructions/*.instructions.md` files (path-specific, via an `applyTo` glob in YAML frontmatter — Copilot does not infer scope from filename, only from this field) are supplied to Copilot alongside personal and organization-level instructions; documented precedence when they overlap in relevance is personal > repository > organization, but the docs are explicit that "all relevant instruction sets are provided to Copilot" simultaneously rather than the lower ones being dropped — reconciling contradictions is left to the model, not the loading mechanism.

Failure mode: path-specific `.instructions.md` support is **surface-dependent** — supported in VS Code Copilot Chat and the Copilot coding agent, but on GitHub.com's web Copilot Chat, path-specific instructions are simply not read at all (repo-wide only), and Copilot CLI only includes a path-specific file when its `applyTo` glob happens to match a file already in play. A correctly authored, well-formed instructions file can therefore be **silently inert** purely because of which client surface is being used, with no error or warning surfaced anywhere.

Confidence: high (official GitHub docs).
Evidence: https://docs.github.com/en/copilot/reference/custom-instructions-support, https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot

### Finding 16: Aider conventions: no built-in scoping primitive at all — customization is "which whole file did you tell it to read," and the config-layering that picks that file has a known silent path-resolution bug

Mechanism: aider has no `applyTo`/glob concept inside a conventions file the way Copilot or Cursor do; a `CONVENTIONS.md` is loaded wholesale, read-only, and prompt-cached, either ad hoc (`/read` or `--read`) or persistently via `read: CONVENTIONS.md` (or a list) in `.aider.conf.yml`. That config file itself layers conventionally — aider looks in home directory, git repo root, and current directory, "with files loaded later taking priority" — separating personal defaults (home) from project-specific behavior (repo root), which is the config-file-layering pattern applied to aider's own operational settings, distinct from the conventions content itself.

Failure mode: a documented, still-open gap — if a global conventions file is referenced from the global `.aider.conf.yml` via a relative path (e.g. `read: .aider.conventions.md`), aider resolves that path **relative to the directory aider is launched from, not the home directory the config file lives in** — so the same global config silently picks up a different (or no) file depending on where you run aider, with the only workaround being a hardcoded absolute path. There is no `applyTo`-style scoping inside the conventions file itself to fall back on; splitting into multiple files and choosing which to `read` is the only substitute, and aider is also documented to deprioritize rules near the bottom of a long conventions file as conversation length grows.

Confidence: medium (official aider docs for the loading/config mechanism; the path-resolution bug is sourced from an open GitHub issue, not yet fixed/documented as expected behavior).
Evidence: https://aider.chat/docs/usage/conventions.html, https://github.com/Aider-AI/aider/issues/3433

### Contradictions

- Finding 13: official Claude Code docs (namespacing, no plugin-skill override) directly contradict secondary-source blog claims of a general "personal beats bundled, project beats bundled, user beats plugin" priority chain that supposedly extends to plugin-shipped skills.
- Finding 4: sources agree nginx is last-wins and sshd is first-wins in direction, but disagree on the *consequence* for `Include` placement in sshd_config (top vs. bottom) — flagged as needing verification against the specific OpenSSH version's man page rather than distro convention.
- Finding 14: sources disagree on whether legacy `.cursorrules` is inert in Agent mode specifically, or generally-working-but-deprecated.

### Gaps

- No source found describing a system where a shipped file and a local-delta file are mechanically reconciled at the level of **individual code changes inside a directory of Python modules** (all patch/overlay examples here operate on config text, YAML manifests, or whole-file markdown, not on a package of `.py` files needing per-function overrides) — closest analogues are quilt/dpkg-source (patch-based, works on any text) and Nix `overrideAttrs` (functional, needs an evaluatable build description, not directly applicable to arbitrary Python).
- No official documentation was found for a "stale customization" detection command in any of the AI-tooling systems (Cursor, Copilot, aider) comparable to Claude Code's `/status`/`claude doctor` or systemd's `systemd-delta` — worth flagging since Compass's `doctor` goal (detecting a stale customization) has no direct AI-tooling precedent to draw an implementation pattern from; the config-management-tool precedents (systemd, dpkg, kustomize `test` op) are the strongest examples of built-in staleness/mismatch detection.

## Axis: Compass surfaces and corpus (rs-surfaces)

### Finding 1: `_apply()` replaces four directories wholesale, merges one file, leaves the vault untouched

`self_update.py:215-254` (`_apply`) and mirrored by `update/SKILL.md:36-79` (step 4):

- `.claude/agents/*.md` - every `*.md` in `src/templates/agents/` is `shutil.copy2`'d over the matching name in the destination (`self_update.py:222-223`). Existing files with the same name are overwritten byte-for-byte; a file in `.claude/agents/` whose name does **not** match a shipped template is left alone (never enumerated, never deleted).
- `.claude/rules/*.md` - same copy pattern, `self_update.py:224-227`.
- `.claude/skills/<name>/*.md` - for every subdirectory of `src/skills/`, every `.md` inside it is copied over the same-named destination directory (`self_update.py:228-234`). A user-authored skill directory whose name isn't in `src/skills/` is never touched (the loop only walks `src/skills`, never `claude/skills`).
- `.claude/cli/` - **wholesale replace**, not per-file copy: `_copy_tree_best_effort` (`self_update.py:145-170`) first deletes every entry currently in `claude/cli` (`rmtree` dirs, `unlink` files, `self_update.py:149-156`), then copies everything from `src/cli` in (`self_update.py:157-170`), skipping `__pycache__`. Any hand-added file inside `.claude/cli/` is destroyed on every update.
- `.claude/hooks/hooks.json` - single-file overwrite (`self_update.py:242`).
- `.claude/settings.json` - **merged**, not overwritten: `merge_settings()` (`self_update.py:173-212`) replaces only hook groups whose commands mention `"compass"`; every other top-level key and every non-Compass hook group is preserved. `.claude/settings.local.json` is never written by Compass (confirmed: no reference to `settings.local.json` anywhere in `self_update.py`).
- `.compass/` vault - untouched by `_apply`; only `meta/plugin.yaml`'s known `key: value` lines are rewritten in place (`_write_plugin_yaml`, `self_update.py:66-89`), preserving unknown lines/notes blocks verbatim. `update/SKILL.md:12` states explicitly: "The `.compass/` vault is never touched."

Confidence: high. Evidence: direct read of `self_update.py:145-254` and `plugin/skills/update/SKILL.md:36-152`.

### Finding 2: `RETIRED_SKILLS` deletion is a hardcoded allowlist, not a diff

`RETIRED_SKILLS = ["bootstrap"]` (`self_update.py:46`). On every apply, `claude/skills/<name>` is `rmtree`'d for each name in that list if the directory exists (`self_update.py:235-238`). Nothing else in `.claude/skills/` is ever deleted - a skill directory Compass no longer ships but that isn't named in `RETIRED_SKILLS` would simply stop receiving updates, not be removed. Verified empirically: `F:/Creative/Game/Defold/defold/.claude/skills/bootstrap` does not exist (retired cleanly by this mechanism).

Confidence: high. Evidence: `self_update.py:43-46,235-238`; filesystem check, absent.

### Finding 3: models.yaml precedent - file location, schema, precedence order

Full mechanism lives in `plugin/cli/modelslib.py`:

- **Location**: `<vault_root>/meta/models.yaml`, i.e. `.compass/meta/models.yaml` (`modelslib.py:161`, via `load_project_config` at `modelslib.py:150-168`). No vault or missing file -> empty config, no warning (`modelslib.py:162-163`). Present-but-unreadable file -> empty config plus one warning, never raises (`modelslib.py:164-167`).
- **Schema** (`parse_models_yaml`, `modelslib.py:81-147`), a hand-rolled two-level parser (not YAML-library-based):
  ```yaml
  tiers:
    cheap: sonnet          # remap a tier's model for this host
  agents:
    vault-locator: opus    # scalar pin: literal model name OR a tier name
    planner:
      tier: balanced
      effort: medium
  ```
  Unparseable lines, unknown top-level keys, unknown tiers, and unknown per-agent keys are all skipped with a `warnings` entry appended - the parser never raises (`modelslib.py:110-146`).
- **Precedence, lowest to highest** (doc header `modelslib.py:1-11`, implemented in `resolve()` `modelslib.py:198-272`): built-in `DEFAULT_ROSTER` tier -> project override (`models.yaml` `agents.<name>.model`/`.tier`) -> environment (`COMPASS_MODEL_<AGENT>`, `COMPASS_EFFORT_<AGENT>`, agent name uppercased with `-`->`_`, `modelslib.py:219,233,257`). A `tiers:` remap in `models.yaml` also outranks the built-in `HOST_CATALOGS` mapping for that tier (`_merged_tier_map`, `modelslib.py:177-185`) - so a tier-level override affects every agent resolved through that tier, not just one named agent.
- **Application point**: `commands/apply_models.py`. `run()` (`apply_models.py:91-132`) resolves `target = <vault_root>/../.claude/agents` by default, or `--dir DIR` (`_target_dir`, `apply_models.py:73-88`). It iterates only `modelslib.AGENT_FILES` - the 13 Compass agent filenames minus the two headless jobs (`modelslib.py:35-62`) - and for each, if the file exists, rewrites **only** its frontmatter `model:`/`effort:` lines via `rewrite_frontmatter` (`apply_models.py:30-70`); every other byte of the file (body, other frontmatter keys) is untouched. `model == "inherit"` deletes the `model:` line entirely rather than writing the literal string (`apply_models.py:54-56`, `modelslib.py:191-195`) - omission is how "inherit" is expressed on every host. `vaultlib.write_text_lf` is used so output is always LF (`apply_models.py:120`); a file already matching the resolved policy produces no write (`apply_models.py:119-125`, idempotent).
- **Invocation points**: called automatically at the end of `_apply()` in `self_update.py:244-254` (subprocess, best-effort, swallowed exceptions/timeout) when `apply_models=True` (the default), and explicitly in step 4 of `update/SKILL.md:70-78`. Also runnable standalone as `compass apply-models [--dir DIR]`.
- **Reporting**: `apply_models.py` writes one `updated <file>: model <x>, effort <y>` line per changed file to stdout, then a summary `apply-models: N updated, N unchanged, N absent` (`apply_models.py:122-129`); warnings go to stderr. `commands/models.py` prints the **full resolved roster** as a table (`agent, model, effort, source`) for the 13 roster agents plus any extra agent named only in the override (`models.py:19-30`); `commands/resolve_model.py` prints a single agent's resolution as one line `<model> <effort>` for scripting (`resolve_model.py:20-24`).
- **Unknown agent named in the override**: `resolve()` never raises for an agent outside `DEFAULT_ROSTER` - it falls back to `builtin_tier = DEFAULT_ROSTER.get(agent, "inherit")` (`modelslib.py:222`), so an agent name in `models.yaml` that doesn't correspond to any shipped agent resolves cleanly to `inherit` + default effort and is simply never written anywhere (because `apply_models.py`'s loop only ever touches `modelslib.AGENT_FILES`, and a made-up name isn't in that list - so it's silently inert, not an error). `commands/models.py:19-20` will still list it in the printed roster table if the override references it, since it unions override-named agents into the display set.

Confidence: high. Evidence: `modelslib.py:1-273`, `commands/apply_models.py:1-133`, `commands/models.py:1-30`, `commands/resolve_model.py:1-25`, all read in full.

### Finding 4: The models.yaml precedent is currently unused in the real corpus

No `.compass/meta/models.yaml` exists in any of the three inspected projects: `F:/Creative/Game/Defold/defold/.compass/meta/` (contents: `capture.json`, `lessons-catalog.yaml`, `plugin.yaml`, `tag-index.yaml` - no `models.yaml`), `F:/Creative/Game/Defold/defold-private/.compass/meta/` (same four files plus `usage.yaml`, still no `models.yaml`), and this repo's own `.compass/meta/` (same set, no `models.yaml`). The mechanism is fully built and wired into every update path but has zero live adopters among the projects checked.

Confidence: high. Evidence: `ls` of all three `meta/` directories, file not found in any.

### Finding 5: Real customization corpus - zero content overlays found; one whole-new-skill fork

Diffed `F:/Creative/Game/Defold/defold/.claude/{agents,rules,skills/*/SKILL.md}` against this repo's `plugin/{templates/agents,templates/rules,skills/*/SKILL.md}` **at the git commit Defold's `plugin.yaml` records as installed** (`9d63a69918dca99e07243d1f6e0f45a059b43f59`, `installed_mode: update`, `installed_at: 2026-08-28`) using `git show <commit>:<path>` vs. the installed file, both normalized to strip `\r` (the installed files are CRLF, the repo's git blobs are LF - an unnormalized `diff -u` reports every single line as changed, which is a line-ending artifact, not content drift).

Result after normalization: **every** shipped agent, rule, and skill file installed in the Defold project is byte-identical (modulo line endings) to the plugin source at the commit it was installed from. Zero content customizations exist anywhere in the corpus. The one difference found is `.claude/skills/sync-forks/SKILL.md` - a skill with no corresponding path in `plugin/skills/` at all: a wholly new, wholly local skill, not an overlay on a shipped file. It exists independently (and with genuinely different content, not just formatting) in both `defold/.claude/skills/sync-forks/` and `defold-private/.claude/skills/sync-forks/` - two separately-authored copies of the same idea, one per clone, referencing that clone's own remotes.

This directly falsifies the standing assumption in the Defold project's own `ADR-001-upstream-first-workflow.md:51`: *"These rules are written into `.claude/rules/compass-pipeline.md`, `.claude/agents/researcher.md`, `.claude/agents/pr-describe.md`, and `.claude/skills/autopilot/SKILL.md`... `/compass:update` overwrites those files; after an update, re-apply from this ADR."* A targeted grep for `"upstream"` (case-insensitive) in all four named files returns **zero matches** in the currently installed copies - none of the ADR's documented customizations are present today. Whether they were written once and later wiped by an update with no re-application, or never actually applied to begin with, cannot be determined from the filesystem alone: `.claude/` is untracked in the Defold repo (see Finding 7), so there is no git history to inspect. Either way, the ADR itself documents the exact failure mode SPEC-014 targets, and the current state confirms the loss actually happened (the files read as pure stock Compass, with no trace of the ADR's content).

Confidence: high (diff results and grep are direct filesystem evidence). Confidence: medium on which specific event (never-applied vs. applied-then-wiped) caused the absence - no git history exists for `.claude/` to distinguish the two.

Evidence:
- Diff commands run: `git show 9d63a69...:plugin/templates/agents/<name>.md`, `...templates/rules/<name>.md`, `...skills/<name>/SKILL.md`, each piped through `tr -d '\r'` and diffed against the installed file, for every file in `defold/.claude/{agents,rules}` and every skill directory under `defold/.claude/skills`.
- `grep -i upstream` against `defold/.claude/rules/compass-pipeline.md`, `defold/.claude/agents/researcher.md`, `defold/.claude/agents/pr-describe.md`, `defold/.claude/skills/autopilot/SKILL.md` - all four empty.
- `F:\Creative\Game\Defold\defold\.compass\decisions\ADR-001-upstream-first-workflow.md:51` (the claim).

### Customization corpus

| File / Skill | Shipped in `plugin/`? | Differs from shipped source (normalized)? | Overlay form required |
|---|---|---|---|
| `.claude/agents/*.md` (13 files) | Yes | No - identical | N/A (no live customization) |
| `.claude/rules/*.md` (4 files) | Yes | No - identical | N/A (no live customization) |
| `.claude/skills/*/SKILL.md` (32 shipped skills) | Yes | No - identical | N/A (no live customization) |
| `.claude/skills/sync-forks/SKILL.md` | No (not in `plugin/skills/`) | N/A - wholly new | Whole-file fork (new skill, not an overlay of a shipped one); exists as two independently-authored copies (defold and defold-private) |
| `.compass/decisions/ADR-001` claims of customization to `compass-pipeline.md`, `researcher.md`, `pr-describe.md`, `autopilot/SKILL.md` | Yes (all four are shipped files) | Documented as intended in the ADR, but **absent today** (grep for the ADR's own keyword finds nothing) | Would have needed insert-at-anchor or append (ADR text describes adding upstream-sweep steps to existing protocols) - but no surviving evidence of the actual patch shape, since it isn't present to inspect |

Count: 0 live content overlays of any form (append, insert-at-anchor, replace-a-passage) found anywhere in the corpus. 1 whole-file-fork (new skill) found, duplicated independently across 2 clones. 1 documented-but-currently-absent customization intent (ADR-001), which is evidence *for* the need but not a surviving example of a working overlay.

### Finding 6: `.claude/` gitignore treatment differs from `.compass/` and differs per project

- This repo (`F:\claude\plugins\compass\.gitignore:17`): `.claude/` is listed - a plain `.gitignore` entry, so `.claude/` here is the generated local install per `CLAUDE.md`'s repo-layout table.
- `defold/.git/info/exclude` (not `.gitignore` - a local-only, uncommitted exclude list): lines listing `.compass/`, `.claude/`, `CLAUDE.md`, `CLAUDE/`, `.mcp.json`. Matches ADR-001's own claim (`ADR-001:49`): *"`.compass/`, `.claude/`, `CLAUDE.md`, and `CLAUDE/` are in `.git/info/exclude` and are never committed or pushed."*
- `defold-private/.git/info/exclude`: lists only `.claude/`, `.mcp.json`, `.internal/` - **`.compass/` is absent from this list**. Verified empirically: `git ls-files .compass` inside `defold-private` returns 56 tracked files (`active.md`, `backlog.md`, every ADR, etc.) - `.compass/` is actually committed to the `defold-private` repository, unlike its public sibling `defold`. Only `.compass/tmp/` shows as untracked there.

This means vault persistence-via-git is not a Compass-enforced invariant; it is a per-project, per-clone choice that already diverges between two clones of what is otherwise "the same" project.

Confidence: high. Evidence: `F:\claude\plugins\compass\.gitignore:17`; `F:\Creative\Game\Defold\defold\.git\info\exclude` (full contents read); `F:\Creative\Game\Defold\defold-private\.git\info\exclude` (full contents read); `git ls-files .compass` run inside `defold-private`, 56 results, `.compass/decisions/ADR-001-upstream-first-workflow.md` among them.

### Finding 7: `.claude/` is fully untracked in the public Defold clone - no history exists to recover past customizations

`git log --oneline --all -- .claude` inside `F:\Creative\Game\Defold\defold` returns nothing; `git check-ignore -v .claude` resolves the exclusion to `.git/info/exclude:8:.claude/`. There is no commit history for any file under `.claude/` in this repo - if a customization existed and was later overwritten by update, there is no git-based way to recover what it said.

Confidence: high. Evidence: commands run directly, empty log output, exclude-file resolution shown.

### Finding 8: `.compass/meta/` today holds exactly four survivor files, all of them narrow single-purpose state, not general overlay stores

Both `defold/.compass/meta/` and this repo's `.compass/meta/` contain: `capture.json`, `lessons-catalog.yaml`, `plugin.yaml`, `tag-index.yaml` (`defold-private` additionally has `usage.yaml`). None of these is a generic customization file; each is a single generated or narrowly-scoped artifact (capture worker state, lesson tag index, install/version record, facet tag index, usage counters). `models.yaml` is documented and coded for (Finding 3/4) but not present as a file anywhere - it is the one designed-but-dormant precedent for a *human-authored* override file living in `meta/`, as opposed to the other four files which are machine-generated/maintained.

Confidence: high. Evidence: directory listings of all three `meta/` folders (Finding 4's evidence), cross-referenced against each file's stated purpose in `CLAUDE.md`'s vault-structure table and `modelslib.py:1-11`.

### Finding 9: `doctor`'s Check pattern - the shape a new "customization applied?" check would follow

`plugin/cli/commands/doctor.py` defines one dataclass-like class, `Check` (`doctor.py:58-69`): constructor `Check(name, status, detail, fix=None)`, `status` one of module-level constants `OK`, `WARN`, `FAIL` (`doctor.py:40`), `to_dict()` for `--json` output including `fix` only when set. `_run_checks()` (`doctor.py:408-430`) is a flat list-builder: each check function takes `vault_root` or `project_root` and returns either one `Check` (e.g. `_plugin_yaml_check`, `doctor.py:72-81`; `_cli_completeness_check`, `doctor.py:176-207`; `_dir_check`, `doctor.py:210-216`) or a small list of them (`_hooks_checks`, `doctor.py:115-173`, returns 1 or 2 rows: the required-event FAIL/OK plus an optional WARN-only informational row for `TeammateIdle`). Every check function is wrapped in its own `try/except` when it does nontrivial filesystem/parsing work (`_unit_candidates_check` `doctor.py:272-294`, `_worker_ledger_check` `doctor.py:306-405`) specifically so one check's internal failure degrades to a WARN naming the failure rather than collapsing the whole run into one opaque FAIL via the outer handler in `run()` (`doctor.py:451-463`). FAIL is reserved for genuine install defects that should move the exit code (`doctor.py:27-28`: "Exit 1 on any FAIL, 0 otherwise"); WARN is for advisory/non-blocking conditions (explicitly named as such for `TeammateIdle` registration, `doctor.py:22-26`, and unit-promotion candidates, worker-ledger conditions). Every non-OK check that has one prints a one-line imperative `fix:` string, collected and printed as a block at the end of the table (`_format_table`, `doctor.py:433-448`) - e.g. `"run /compass:setup to install a versioned plugin.yaml"` (`doctor.py:74`), `"run /compass:update (or copy plugin/cli/ into .claude/cli/) to refresh the installed CLI"` (`doctor.py:179`).

Confidence: high. Evidence: `doctor.py:1-464` read in full.

### Gaps

- Whether the ADR-001-documented customizations to `compass-pipeline.md`/`researcher.md`/`pr-describe.md`/`autopilot/SKILL.md` were ever actually written to disk (and later wiped by an update) or simply never applied cannot be determined - no git history exists for `.claude/` in the Defold repo to check (Finding 5, Finding 7).
- No project in the corpus has ever exercised the `models.yaml` mechanism end-to-end with real content (Finding 4) - its behavior under `apply-models` is verified only by reading the code, not by observing it run against a populated override file in the wild.
- `defold-private`'s `.compass/` being git-tracked while `defold`'s is excluded (Finding 6) was not something this research was asked to explain further; it is reported as a fact, not investigated for cause.
