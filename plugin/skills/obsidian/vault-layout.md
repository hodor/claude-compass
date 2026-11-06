# Obsidian skill: vault layout

Formulas, file naming and numbering, folder specs and plans, workstream folders, topic tags and vault search patterns.

## Math (LaTeX)

**Scope: `.md` files only.** LaTeX rules below apply to vault documents written to disk. Never use LaTeX in chat output, terminal responses, or agent reports surfaced to the user - the terminal does not render MathJax, so `$x^2$` displays as literal characters. For chat, use plain prose or unicode (≤, ≥, →, ∑, π, σ) or code-fenced expressions like `O(n log n)`.

Both Obsidian and GitHub render LaTeX math via MathJax. Use it when prose would be less clear than a formula. Especially common in research documents (statistical analysis, complexity, ML, probability) and in plans or specs that quantify behavior.

| Syntax | Use | Example |
|--------|-----|---------|
| `$...$` | Inline math | `the cost is $O(n \log n)$` |
| `$$...$$` | Block / display math | `$$P(A \cap B) = P(A) \cdot P(B \mid A)$$` |
| `\$` | Literal dollar sign in prose | `the budget was \$500` |

Rules:

- Use LaTeX standard syntax (`\frac`, `\sum`, `\sqrt`, `\cdot`, `\mid`, `\to`, Greek letters, etc.).
- Inline math goes inside one sentence. If the expression spans multiple lines or needs to be referenced, use block math.
- Escape literal `$` as `\$` to avoid the parser treating it as a math delimiter.
- Do NOT use math notation to dress up prose. If the formula does not add precision a sentence cannot, drop it.
- Research is the type most likely to need it; specs and plans use it sparingly; lessons and handoffs rarely.

Examples in context:

```markdown
The dedup judgment runs in $O(n)$ over the catalog where $n$ is the active lesson count.

Bayes update for relevance score:

$$P(\text{relevant} \mid \text{tags}) = \frac{P(\text{tags} \mid \text{relevant}) \cdot P(\text{relevant})}{P(\text{tags})}$$

Convergence threshold across $N$ agents is $\geq 0.8$ before promoting a finding.
```

## File naming

Pattern: `TYPE-NNN-descriptive-name.md`

| Type | Pattern | Example |
|------|---------|---------|
| Spec | `SPEC-NNN-descriptive-name.md` | `SPEC-001-compass-vision-and-architecture.md` |
| ADR | `ADR-NNN-descriptive-name.md` | `ADR-001-obsidian-over-structured-db.md` |
| Research | `RESEARCH-descriptive-name.md` | `RESEARCH-plugin-system-capabilities.md` |
| Plan | `PLAN-NNN-descriptive-name.md` | `PLAN-001-mvp-implementation.md` |
| Lesson | `LESSON-descriptive-name.md` | `LESSON-yaml-frontmatter-quoting.md` |
| Handoff | `YYYY-MM-DD_HH-MM-SS_descriptive-name.md` | `2026-03-12_14-30-00_implement-auth-flow.md` |

`NNN` numbers are computed JIT at creation, not stored anywhere. There is NO counter file. Numbers are LOCAL to each folder (resets at each level). See [[ADR-003-drop-counter-file-jit-compute]] for the rationale and [[ADR-004-hierarchical-specs-with-facets]] for the hierarchy rules.

**JIT compute rule (the single source of truth):**

| Artifact | Next-number rule |
|---|---|
| SPEC | `max(N from glob '**/.compass/specs/SPEC-N-*.md') + 1`, default 1 |
| ADR | `max(N from glob '**/.compass/decisions/ADR-N-*.md') + 1`, default 1 |
| PLAN | `max(N from glob '**/.compass/plans/PLAN-N-*.md') + 1`, default 1 |
| TASK | `max(N) + 1` across `grep -oE 'TASK-([0-9]+)' .compass/active.md .compass/backlog.md`, default 1 |
| RESEARCH | no number; descriptive name only |
| LESSON | no number; descriptive slug only |
| Handoff | no number; `YYYY-MM-DD_HH-MM-SS_name` timestamp |

The filesystem is the source of truth. Skip the `**/` prefix and Glob returns zero (see [[LESSON-glob-hidden-dirs-prefix]]).

Inside a unit folder the same rule scopes to the unit's own type dir: `compass next-num spec <unit>` computes max+1 over `<unit>/specs/`. Root numbering (`compass next-num spec`) never counts unit artifacts, and vice versa.

Names must be self-descriptive - `SPEC-001.md` is never acceptable. Lowercase kebab-case for the descriptive part.

## Hierarchical specs and plans (folders)

A spec is a file; the folder shape is earned by the second member. When a spec gains its first child, it becomes `.compass/specs/SPEC-NNN-descriptive-name/index.md` (`compass promote`) with children inside, recursively and with no depth limit - and a folder that drops back to its index alone gets demoted to a file again. Path is identity; numbering resets at each level.

**The parent holds the decisions shared by every child; a child exists to diverge on something the parent left open.** Divergence sharing no root decision with the parent is a sibling spec, not a child (ADR-011 D-06).

```
.compass/specs/
├── SPEC-001-flat-thing/                     leaf: index.md only, no children
├── SPEC-002-tile-editor/                    parent with children
│   ├── index.md                             the parent spec at this level
│   ├── SPEC-001-master-material/            child (local numbering resets)
│   ├── SPEC-002-brush-system/               nested: same shape, recursively
│   │   ├── index.md
│   │   ├── SPEC-001-stroke-rendering/
│   │   └── SPEC-002-blending-modes/
│   └── SPEC-003-tile-grid/
```

Same convention for `plans/`. Plans typically map to specs and inherit the spec's structure.

### Wikilinks across folders

Obsidian wikilinks accept slashes. Reference a child spec by its full path inside the type root:

- `[[SPEC-002-tile-editor]]` resolves to `SPEC-002-tile-editor/index.md`
- `[[SPEC-002-tile-editor/SPEC-001-master-material]]` resolves to the child
- `[[SPEC-002-tile-editor/SPEC-002-brush-system/SPEC-001-stroke-rendering]]` for nested

### Folder-level index.md (the warm tier branch summary)

A folder's `index.md` is the parent spec body PLUS a RAPTOR-style summary of its children. Required structure for folder index.md:

```markdown
---
title: "..."
type: spec | plan
status: ...
area: ...
tags: [...]            # REQUIRED - facets for this branch
children_count: N      # REQUIRED - synced by index-sync
summary: "..."         # REQUIRED - one-line representation of the branch
---

[Parent spec body. Hold decisions and concerns that stay at this level. Delegate sub-concerns to children.]

## Children

- [[SPEC-001-master-material]] — one-line summary of what the child covers
- [[SPEC-002-brush-system]] — one-line summary
- [[SPEC-003-tile-grid]] — one-line summary
```

The folder is the listing: members are read live (`ls`/Glob), never maintained inside the doc. A folder doc found carrying an old `## Children` section gets it removed on the next touch - a derived listing whose facts live in the filesystem and in each child's own `summary:`.

### Scope notes (domain folders)

A domain's `index.md` carries a `## Scope` section - the placement answer at the point of doubt, hand-authored, never regenerated:

- `Class here:` names what belongs, in finder words.
- `Class elsewhere: X -> [[<type-dir>/<domain>/index|<domain>]]` is a binding redirect: X does not file here.
- `See also:` points sideways, advisory only.

The domain's `summary:` frontmatter reads as its class-here digest, so the root index line answers the obvious case without opening the doc.

## Unit folders (the hybrid root)

The vault root is hybrid. Type-first dirs (`specs/`, `plans/`, ...) hold standalone work; a large unit of work gets its own folder at the vault root, named for the work itself, holding its own type subdirs:

```
.compass/
├── specs/                            root type dir - standalone work
├── plans/
├── compass-cli/                      unit folder - one large unit of work
│   ├── index.md                      type: unit marker, title, children listing
│   ├── specs/
│   │   └── SPEC-001-cli-contract.md  numbering local to the unit
│   ├── plans/
│   ├── research/
│   └── lessons/                      aggregated into meta/lessons-catalog.yaml by sync
└── ...
```

A unit declares itself with `type: unit` in the frontmatter of its own `index.md`. The marker is what classifies the folder: a non-reserved root folder without it is ignored by the CLI and reported by `compass validate` as `unclassified_root_folder`, never guessed at. The unit `index.md` carries the title (used as the unit's section header in the root index) and a one-line-per-child listing, refreshed by `/compass:consolidate`.

Inside a unit, folder specs follow the same [[ADR-004-hierarchical-specs-with-facets]] rules as at the root. Unit `lessons/` stay on the hot path: `compass sync` aggregates them into `meta/lessons-catalog.yaml` (filename is the row key, so lesson filenames must be unique vault-wide).

### Bare stems vs path-qualified links

Numbering is local per unit, so `SPEC-001-...` can exist at the root and inside any unit - bare stems are genuinely ambiguous across units. The link form depends on where the target lives:

| Target | Link form | Example |
|--------|-----------|---------|
| Root flat artifact | bare stem | `[[SPEC-004-mechanical-work-off-the-agent-budget]]` |
| Root folder spec | folder name | `[[SPEC-002-tile-editor]]` |
| Unit artifact | path-qualified `<unit>/<type-dir>/<stem>` | `[[compass-cli/specs/SPEC-001-cli-contract]]` |
| Folder spec inside a unit | folder's vault-relative path | `[[compass-cli/specs/SPEC-002-brush-system]]` |
| Artifact below a domain | path-qualified vault-relative | `[[specs/network/cache/SPEC-001-eviction]]` |
| Domain or folder-spec line on a generated surface | piped full path to its index | `[[specs/network/index\|network]]` |

Always author unit-artifact and below-domain links path-qualified - domain names reuse across branches (`specs/network/cache` and `specs/gpu-hardware/cache` coexist), so the path is the identity. The convention is forward-only: links written before a target moved stay valid, and `compass validate` warns `ambiguous_wikilink` only when a bare stem actually resolves to more than one file. Generated surfaces emit folder links as piped full paths because Obsidian opens files, never folders - the piped form displays as the plain name and clicks through. The rule text for resolving, authoring and ambiguity of path-qualified links: `path-qualified-links.md` in this skill's folder.

### Where a new artifact goes

Before creating an artifact, resolve its destination root: if the work belongs to an existing unit (its spec, plan, or research lives under `.compass/<unit>/`), create the artifact in that unit's type dir, number it with `compass next-num <type> <unit>`, and link it path-qualified. Otherwise create it in the root type dir with a bare-stem link. Inside that type dir, `compass placement <path>` lists where the artifact could live: existing artifacts it could sit under, same-level artifacts it would pair with to form a domain, and domains whose scope fits. A move it surfaces goes to the human as one question. Detection of root artifact sets that have outgrown the flat layout is mechanical (`compass unit-check` reports candidates when 3+ artifact types trace to one spec); promotion is the human's decision.

## Facet tags (the multi-parent layer)

Every spec, plan, lesson, ADR, and research doc has a `tags: [...]` frontmatter field. Tags are folksonomy - free-form, not a controlled vocabulary. A spec belongs to whatever facets describe it. A master material spec is `tags: [rendering, tile-editor, materials, shaders]` even though its folder is `tile-editor/`.

Tags are the multi-parent retrieval primitive. The agent reaches multi-perspective specs by reading `.compass/meta/tag-index.yaml`, not by crawling folders.

### Tag index file (auto-generated)

`.compass/meta/tag-index.yaml` is regenerated by `index-sync` whenever a tagged file is written. Format:

```yaml
tags:
  rendering:
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
    - specs/SPEC-002-tile-editor/SPEC-002-brush-system/SPEC-001-stroke-rendering.md
  tile-editor:
    - specs/SPEC-002-tile-editor/index.md
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
    - specs/SPEC-002-tile-editor/SPEC-002-brush-system/index.md
  materials:
    - specs/SPEC-002-tile-editor/SPEC-001-master-material.md
```

The tag index is NOT in the hot path. The agent reads it only when answering a multi-tag question. This is the cold-tier retrieval primitive.

### Tag hygiene

Folksonomy invites synonyms (`tile-editor`, `tileEditor`, `tile_editor`) and typos. `/compass:consolidate` runs a vocabulary pass that proposes merges and rewrites all spec frontmatter atomically. Human approves.

## Vault search patterns

```
# by tag
Grep pattern: "tags:.*\\btarget-tag\\b" in .compass/ glob: "*.md"

# by area
Grep pattern: "area: target-area" in .compass/ glob: "*.md"

# by status
Grep pattern: "status: active" in .compass/ glob: "*.md"

# backlinks
Grep pattern: "\\[\\[SPEC-001" in .compass/ glob: "*.md"

# by type
Grep pattern: "type: spec" in .compass/ glob: "*.md"
```
