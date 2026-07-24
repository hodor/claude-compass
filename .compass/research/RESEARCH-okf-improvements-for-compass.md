---
title: What Compass Can Borrow from the Open Knowledge Format (OKF)
type: research
status: complete
confidence: high
area: methodology
tags: [okf, knowledge-format, frontmatter, interoperability, vault-design, prior-art]
created: 2026-07-22
updated: 2026-07-22
depends_on: ["[[SPEC-001-compass-vision-and-architecture]]", "[[ADR-004-hierarchical-specs-with-facets]]"]
---

## Question

Google Cloud's Open Knowledge Format (OKF) looks structurally close to the Compass vault. Ignoring compatibility, is there anything in OKF worth adopting to make Compass better, and what would it cost against the four ranked goals (accuracy > perfect memory > near-zero cache misses > low tokens)?

## Methodology

Full read of the OKF v0.1 draft spec (`okf/SPEC.md`), its reference producer agent, index synthesizer, and three example bundles, plus GitHub repo metadata. Reference implementation cross-checked against the spec text. Framing is improvement-mining, not interoperability. Source: `github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`.

## Headline finding

OKF is convergent design with Compass, which is validation, not a blueprint. Its minimalism (one required field, permissive-by-mandate consumption) serves cross-organization exchange; Compass's strict schema serves cache and accuracy. There are exactly three cheap, additive things worth taking, and several tempting things that would trade a ranked goal for interoperability Compass does not need.

## What OKF is

- A **Knowledge Bundle** = a directory tree of markdown files; a **Concept** = one `.md` file; a **Concept ID** = the file path minus `.md` (`tables/users.md` -> `tables/users`). Path is identity - the same principle as [[ADR-004-hierarchical-specs-with-facets]].
- Frontmatter: only `type` is **required** (open free-string vocabulary, not registered). Recommended: `title`, `description`, `resource` (canonical URI of the underlying asset), `tags`, `timestamp`. Unknown keys must be preserved on round-trip.
- Two reserved files: `index.md` (progressive-disclosure listing, `* [Title](url) - description` per entry, no frontmatter except an optional root `okf_version`) and `log.md` (date-grouped change history, newest first).
- Links are markdown paths ending in `.md`; bundle-relative absolute (`/tables/x.md`) is recommended for move-stability. Links are **untyped** - relationship semantics live in surrounding prose.
- Citations: numbered list under a `# Citations` heading; a `references/` subdir mirrors external material as first-class concepts.
- Conformance floor: parseable frontmatter + non-empty `type` + reserved-file structure. Consumers **MUST tolerate** missing optional fields, unknown types/keys, and broken links (a dangling link may be not-yet-written knowledge).

## Findings

1. **Convergent, not novel (HIGH).** OKF independently landed on markdown + YAML frontmatter, a reserved progressive-disclosure `index.md` with one-line child descriptions, path-as-identity, a `tags` folksonomy, and git as the history layer. All already in Compass. Confidence this validates the existing design: high. Confidence it teaches the core model something new: low.

2. **The reference implementation is stricter than the spec (HIGH).** `document.py` hard-codes four required keys (`type`, `title`, `description`, `timestamp`) and raises on any missing, versus the spec's one. Even Google's own producer treats title/description/timestamp as de-facto required - which is closer to Compass's stance than the spec's one-field floor suggests. Source: `okf/src/reference_agent/bundle/document.py:8`.

3. **`resource:` is a genuinely useful field Compass lacks (HIGH).** OKF's `resource` = canonical URI of the external asset a concept describes. Compass has no equivalent because most artifacts are internal, but several are not: a spec about an existing API, a research doc about a paper, an ADR about an external tool. An optional `resource:` (or `source_uri:`) field is additive, aids traceability, and costs nothing when absent. Serves goal 1 (accuracy) and goal 2 (perfect memory).

4. **Permissive-consumption is a good reader posture Compass under-specifies (MEDIUM).** OKF mandates that consumers never reject a bundle for a missing optional field or a dangling link. Compass is producer-strict (good) but does not tell its *reader* agents to tolerate a `[[link]]` to not-yet-written knowledge. Encoding "tolerate the incomplete" for agents (templates/methodology) is a robustness win for goal 2, and is a posture, not a schema change.

5. **`log.md` per-directory change history duplicates what Compass already has (HIGH).** Git history + handoffs already record change chronology. Adopting `log.md` would duplicate, add write churn, and ride the sync hot path for no goal gain. Skip unless a git-free downstream consumer becomes a requirement.

6. **Structural-markdown-over-prose guidance matches Compass ethos (HIGH).** OKF's "favor headings, lists, tables, fenced code over freeform prose, since structure aids agent retrieval" is the same principle as the Compass "short, sweet, structural" document rule. No change needed; it corroborates the existing convention.

7. **Maturity is thin - do not chase the format (HIGH).** OKF is v0.1 Draft, ~2.5 months old, ~10 contributors, with major-version breaking changes (renamed required fields) explicitly on the table. The repo's ~7.6K stars reflect the parent knowledge-catalog / Google Cloud brand, not OKF-specific adoption. Aligning Compass's native format to a moving v0.x target works against goal 2 (stable memory).

8. **Tooling worth noting, not adopting (MEDIUM).** OKF ships a reference producer agent (Google ADK + Gemini, two-pass BigQuery + web-crawl enrichment), an `index.md` synthesizer, and a per-bundle static graph viewer (`viz.html`). No standalone conformance validator ships - validation is only the in-process `OKFDocument.validate()`. The graph-viewer idea (a static per-vault visual of the wikilink graph) is a possible future nicety but orthogonal to the ranked goals.

## Recommendation for Compass

**Adopt (low cost, goal-positive):**
- Optional **`resource:` / `source_uri:` frontmatter field** for artifacts that describe an external asset. Additive; serves goals 1 and 2. (Finding 3.)
- A **reader-side "tolerate the incomplete" posture** in agent templates/methodology: a missing optional field or a dangling `[[link]]` is not-yet-written knowledge, not an error. Serves goal 2. (Finding 4.)
- Treat OKF as **external validation** of the vault model in [[SPEC-001-compass-vision-and-architecture]] - useful citation, not a redesign trigger. (Finding 1.)

**Consider later (higher cost, optional):**
- An **OKF export mode** (`compass -> OKF bundle`: rewrite `[[wikilinks]]` to `/path.md`, strip folder-index frontmatter, emit `type` as-is) *if* a future need for interop with Obsidian/MkDocs/Notion/OKF consumers appears. This buys portability without disturbing the native hot-path/cache design. Cost: a serializer + tests + tracking OKF's unstable v0.x.

**Do NOT adopt:**
- Do not weaken the required-frontmatter schema to OKF's one-field floor - the strict schema is load-bearing for goals 1 and 3.
- Do not switch native links from `[[wikilinks]]` to `.md` paths - it breaks grep-based backlinks and the Obsidian graph for no goal gain. Export, don't migrate.
- Do not adopt `log.md` - git + handoffs already cover change history.
- Do not read the star count as adoption proof or align the native format to a v0.1 draft.

## Open questions

- Field name: `resource` (OKF's word) vs a Compass-native `source_uri` - pick for clarity, not compatibility.
- Whether the reader-side tolerance posture belongs in the methodology skill, the agent templates, or both.

## Sources

- Spec: `github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`
- Reference producer + validator gap: `okf/src/reference_agent/bundle/document.py`
- Index synthesizer: `okf/src/reference_agent/bundle/index.py`, `synthesizer.py`
- Example bundles: `okf/bundles/{ga4,stackoverflow,crypto_bitcoin}/`
- Repo metadata via `gh api repos/GoogleCloudPlatform/knowledge-catalog` (v0.1 Draft, ~10 contributors, created 2026-05-04).
