---
title: "Taxonomy for Unambiguous Placement: Classification Science, the Design Space, and the Full Ripple"
type: research
status: complete
confidence: high
area: methodology
tags: [taxonomy, classification, faceted, inter-indexer, scope-notes, ripple, per-folder-index]
created: 2026-08-30
updated: 2026-08-30
author: researcher-consolidation
summary: "filers inherently disagree (10-60% consistency), so unambiguity is engineered on the finder's side: few broad human-curated top levels, scope notes on every category, one primary home plus facet cross-refs, corpus-warranted categories; the codebase mostly tolerates nesting already, with five named gaps"
depends_on: ["[[SPEC-022-vault-organized-per-domain]]", "[[SPEC-005-index-auto-maintained-and-mirrored-per-folder]]", "[[SPEC-003-hierarchical-vault-organization]]", "[[SPEC-010-universal-hybrid-hierarchy]]", "[[RESEARCH-hierarchical-knowledge-base-design]]"]
---

# Taxonomy for Unambiguous Placement

## Question

[[SPEC-022-vault-organized-per-domain]], the stated goal verbatim: "how humans organize topics and how machines organize topics - the main goal is to have it organized in a way that there is no ambiguity in which main area you should go to find the info you need." Three axes, classification science primary per D-06; full findings verbatim below the synthesis.

## Synthesis

**The CS axis is the critical one (SPEC-022 D-06): computer science applies classification as delegated namespaces, and four of its results transfer structurally, not metaphorically.**

- **Hop count is the cost unit, quantitatively** (B-tree theory: cost = depth x per-hop fetch): in the vault one hop is one folder marker doc read, so fewer, broader top domains beat many fine ones - the same conclusion the human-classification data reaches by inter-indexer agreement.
- **A folder's marker doc is a RAPTOR summary node**: retrievable as an answer on its own AND the signal to descend. That is the retrieval shape the per-folder index already has; RAPTOR is evidence it wins on multi-hop questions.
- **Generality at the parent, autonomy at the child** (DNS zone delegation, Bazel package trees): the root never re-explains what a domain's own doc explains; a domain governs everything under it. Independent confirmation of the depth gradient.
- **Names are load-bearing and expensive to change** (Java/Go/Rust package norms, npm's scoping retrofit): fix the naming convention before the corpus grows; dumping-ground names (common, util, misc) are forbidden everywhere the pattern appears.
- **Convention over configuration kills filer choice** (Rails/Maven/FHS): where placement is decided by stated convention, the filer never chooses, so filer disagreement stops mattering.
- **The spec's metric has no ready-made instrument** - nothing in the literature measures "tokens loaded but unused by the task's output"; effective-context-length and lost-in-the-middle curves measure adjacent things. The metric must be defined and baselined fresh.
- **One flagged tension, surfaced not resolved**: type-dir-first with domains nested inside is closer to package-by-layer than package-by-feature, which the software literature associates with lower cohesion; the tag-index is the cross-cutting compensation.

**The human-classification and design-space findings (below, as reference)** supply the operating rules the CS axis does not: scope notes at the point of doubt (DDC/MSC two-tier), one primary home plus facet cross-references, shallow-when-unsure under top-down error propagation, categories born from warrant, splits triggered by ceiling, human-curated tops with machine-assisted placement, and the measured 10-60% filer disagreement that all of it must tolerate.

### Original synthesis (framed by the human-classification science)

**1. Perfect placement agreement does not exist - design for the finder, not just the filer.**
Inter-indexer consistency runs 10-60% and the literature calls the inconsistency inherent (Markey: 7% exact-term, 13% concept-level agreement). Card sorting shows organizers and finders use different mental models. So "no ambiguity" cannot be achieved by drawing better categories alone; it is engineered by making every reasonable path lead to the document: one physical home plus cross-cutting facets (Compass's tag-index already is this - ADR-004's design is validated, though its Ranganathan citation is metaphor, not mechanism), cross-references, and scope notes.

**2. What measurably raises agreement maps directly onto vault design:**
- FEW, BROAD top levels (agreement rises as depth-per-item falls; concept-level grouping is ~2x more reproducible than fine labels). MSC has 63 top classes for all of mathematics; ACM CCS has 13 roots. A vault needs a handful, not dozens.
- Top-level label quality is decisive: tree-testing's first click is the single best predictor of retrieval success, and hierarchical classification's textbook failure is top-down error propagation - a wrong first branch is unrecoverable below. Corollary the literature states outright: when placement confidence is low, STOP AT THE COARSER CORRECT ANCESTOR rather than force a wrong leaf.
- SCOPE NOTES are the operational device that kills filing ambiguity: DDC's "class here"/"class elsewhere" lines, MSC's binding {For X see Y} vs advisory [See also] - two tiers, one binding, one advisory. Every domain index should carry them.
- ONE PRIMARY HOME plus optional secondary pointers (MSC's primary/secondary codes) - not poly-hierarchy for the physical tree; facets carry the multi-parent axis.
- LITERARY WARRANT: categories are created only when the corpus already justifies them, never invented ahead. Domains come from what exists - exactly SPEC-022's non-goal against speculative domains.
- HARD SPLIT TRIGGERS beat judgment calls (Johnny.Decimal's numeric ceilings): a category-size threshold that mechanically flags "split me" avoids the documented too-late-to-split failure.
- Human-curated top levels with machine-assisted leaf placement is the literature's recommended division of labor - which is precisely the consolidate-proposes/the human-approves gate already ruled in ADR-021 D-03.

**3. The design space is narrower than it looked (design axis):**
ADR-021 already ruled domains reuse the folder-spec kind via existing commands. The real open decisions the ADR left unmade: (a) the THIN domain (no natural parent spec - "distribution", "pipeline") has no creating command and no content template - and the folder-spec template's Problem/Decisions framing does not fit a topical bag; (b) folder Children listings are hand-written or one-shot, never synced - SPEC-005's auto-regeneration was specced and never built, held ONLY on unproven LLM-summary cost, not design disagreement; (c) naming: numbered SPEC-NNN-name/ (promoted parents) vs bare names (thin domains) already coexist in the live proposal, and local numbering inside domains reopens ADR-006's bare-stem collision for a case its unit-only path-qualification never covered; (d) taxonomy_hint has zero implementation; (e) area: frontmatter is a near-domain field already drifted past its documented enum, unenforced.

**4. The code mostly tolerates the change already (ripple axis):**
Nesting classification, next-num at arbitrary depth, make-unit path checks, validate sizing reconciliation, and vaultgraph containment all work at any depth today. Five named gaps: sync never regenerates per-folder Children sections (the SPEC-005 gap); _is_generated_output endswith-matches EVERY nested index.md - the loop guard silently suppresses capture signals for all folder-spec writes today and would mask per-folder index writes, untested either way; same-name domains across type dirs (specs/distribution + research/distribution) produce ambiguous_wikilinks; promote already works on research docs (the promote-spec skill's "CLI refuses" claim is false); methodology/setup skills still document research/ and friends as "flat, one file each", contradicting D-02.

**5. Open empirical question, flagged not assumed:** all consistency data is human-indexer; whether the 10-60% baseline transfers to LLM filers is unmeasured. The design should not depend on agents agreeing more than humans do.

Full findings verbatim per axis below.


## Axis: CS-applied classification (rs-cs-classification, PRIMARY per SPEC-022 D-06)

### Research: How Computer Science Applies Classification/Taxonomy to Navigable Namespaces

From [[SPEC-022-vault-organized-per-domain]], axis: what CS itself (as opposed to library/information science, covered separately) does when it builds navigable hierarchical namespaces, and what is measurably true about retrieval cost as depth/fanout vary.

#### Question

What do filesystem/OS taxonomies, language/package namespaces, distributed naming schemes, monorepo code organization, and retrieval-cost theory (B-trees, RAG/LLM literature) establish about organizing a namespace so placement is unambiguous and retrieval is cheap - and which of those findings are structural maps onto a markdown vault versus loose metaphors?

#### Methodology

WebSearch across six sub-axes (filesystem/OS, language namespaces, distributed naming, monorepo code organization, retrieval-cost theory, convention-over-configuration), cross-checked against official specs/docs and primary sources (RFC-adjacent specs, language blogs, original papers) per claim. Per [[LESSON-human-practice-rationing-assumes-human-scarcity]], every finding below is checked for the precondition its source mechanism depends on before being offered as a transfer.

#### Findings

1. **FHS's own placement rule rests on two orthogonal axes (shareable/unshareable, variable/static), not topical meaning - and FHS documents its own ambiguous zones rather than hiding them** (confidence: high)
   /usr is defined as shareable, read-only data; anything host-specific or time-varying goes elsewhere - `/bin` vs `/usr/bin` is a documented historical accident (a 1970s two-disk split), and FHS 3.0 §4.6/§4.11 explicitly discusses the /usr/lib vs /usr/share fuzziness (executable-vs-data is "the key factor," but interpreted-language modules don't cleanly split) rather than resolving it, leaving distributors discretion.
   - https://refspecs.linuxfoundation.org/FHS_3.0/fhs/ch04s06.html
   - https://sinclairtarget.com/blog/2024/11/making-sense-of-the-linux-filesystem-hierarchy/

2. **Plan 9's union directories compose a namespace from ordered, non-merging layers, replacing PATH-style search lists with the filesystem itself** (confidence: high)
   A union directory concatenates several directories bound at one mount point in a fixed order (first match wins); it does not recursively merge subdirectories - `/bin` is a union of several binary directories instead of a `$PATH` variable. Namespaces are private per process, built by explicit bind/mount operations, not inferred.
   - http://man.cat-v.org/plan_9/4/namespace
   - https://en.wikipedia.org/wiki/Union_mount

3. **XDG Base Directory splits user files by volatility/portability (config/data/state/cache), not by application identity, and defines a precedence order for multi-directory search** (confidence: high)
   Four axes: `XDG_CONFIG_HOME` (user edits), `XDG_DATA_HOME` (survives cache cleanup), `XDG_STATE_HOME` (persists across restarts but not "real" data), `XDG_CACHE_HOME` (safely deletable). Search-path directories are ordered by importance; the first hit wins, exactly like Plan 9's union order.
   - https://specifications.freedesktop.org/basedir/latest/

4. **Reverse-domain package naming (Java) solves namespace collision by delegating to an existing external authority (domain registration), not by better classification** (confidence: high)
   `com.example.foo` is unique because DNS ownership is already unique; Oracle's own docs call this a convention, not a compiler-enforced rule, and note the escape hatch for developers who own no domain (fall back to a platform username, e.g. `com.github.user`). This is a different unambiguity mechanism than a classification scheme: it borrows uniqueness from another namespace instead of producing it locally.
   - https://docs.oracle.com/javase/tutorial/java/package/namingpkgs.html

5. **Every language style guide converges on the same granularity anti-pattern: avoid dumping-ground package/module names, and package/module names become de-facto public API that is expensive to rename later** (confidence: high)
   Google's Java style guide bans underscores and generic catch-alls like `common`/`base`; Go's blog explicitly tells developers to avoid `util` in favor of a specific name (`ioutil`, not `util`); Rust's style guide treats the module tree as part of the crate's API surface, gating what's public via `pub`/`pub use` rather than folder location alone. All three treat renaming a package/module as one of the most disruptive refactors because it breaks every import path referencing the fully-qualified name.
   - https://go.dev/blog/package-names
   - https://pingcap.github.io/style-guide/rust/modules.html

6. **Ousterhout's deep-vs-shallow module framing gives a concrete cost/benefit test for "how much should live at one level": benefit is functionality exposed, cost is interface complexity, and both matter independently of tree depth** (confidence: high)
   A deep module (Unix file I/O: 5 syscalls, huge functionality) hides much behind a simple interface; a shallow module has a complex interface hiding little. Ousterhout names "classitis" - many small shallow classes - as increasing total system complexity even though each individual class looks simple, because the reader now must learn N interfaces instead of one deep one.
   - https://milkov.tech/assets/psd.pdf

7. **npm's scoped-namespace fix (2014) could not retrofit onto the pre-existing flat namespace, and the two other major package ecosystems chose the opposite trade-off at inception** (confidence: high)
   Packagist (Composer) required `vendor/package` from day one, pushing the collision problem up one level but never leaving a flat legacy tier; npm's most-used packages (`express`, `lodash`, `react`) predate scopes and cannot move into a scope without breaking the world, so scopes ended up used mainly by new/organizational packages. PyPI's PEP 752 explicitly cites npm's retrofit cost as the reason to weigh scoping trade-offs before, not after, ecosystem growth.
   - https://blog.npmjs.org/post/116936804365/solving-npms-hard-problem-naming-packages.html
   - https://peps.python.org/pep-0752/

8. **DNS enforces a strict generality gradient by delegation: the root knows only TLDs, each zone is authoritative only for its own namespace, and resolution recurses top-down while caching narrows the walk on repeat lookups** (confidence: high)
   No server holds global knowledge; a domain owner can delegate an entire subtree (`eu.example.com`) to a different administrative authority without coordinating with the parent again after delegation. This is the canonical instance of "generality forced at the top, specificity pushed down," with autonomy - not just naming - transferred at each delegation boundary.
   - https://en.wikipedia.org/wiki/DNS_root_zone
   - https://www.cloudns.net/blog/dns-delegation/

9. **Kubernetes separates two different classification problems into two different mechanisms: API groups organize by function/extensibility, while namespaces solve name collision and policy scoping - conflating them was an explicit early design mistake the group-split fixed** (confidence: high)
   API groups (`apps`, `batch`, `/apis/<group>/<version>`) exist so the API can grow without bloating one monolithic v1 surface, and each carries its own version-maturity signal (alpha/beta/stable) with a round-trip-safety guarantee across versions. Namespaces are explicitly documented as optional, needed only "when multiple teams/tenants share a cluster" - not a general-purpose classification device.
   - https://kubernetes.io/docs/concepts/overview/kubernetes-api/
   - https://github.com/kubernetes/design-proposals-archive/blob/main/api-machinery/api-group.md

10. **Bazel makes the directory itself the unit of access control, and provides an explicit binding/advisory-style scope-note mechanism (`package_group`) instead of leaving cross-package use to convention** (confidence: high)
    Default visibility is private (own package only); `//foo:__subpackages__` grants an entire subtree; `package_group` names a reusable allowlist so many targets share one written scope rule instead of drifting out of sync. Google's own guidance explicitly warns against defaulting to public, "the risk of inadvertently creating public targets increases as the codebase grows" - i.e., ambiguity is cheap to introduce and must be actively fenced.
    - https://bazel.build/concepts/visibility

11. **The feature-folders vs. layer-folders debate has a measured cohesion argument on one side (feature folders) and a predictability/onboarding argument on the other (layer folders), and the field's converged answer is hybrid, not a clean winner** (confidence: medium, practitioner sources, not peer-reviewed)
    Layer-first ("package by layer") has documented low intra-package cohesion and high inter-package coupling because unrelated classes share a technical role; feature-first ("package by feature"/"screaming architecture") groups by business concept, improving discoverability and enabling package-private encapsulation, at the cost of deciding where shared/cross-cutting code lives. Multiple practitioner reports describe migrating from layer-first to feature-first for delivery speed, but no source claims feature-first is strictly superior at all scales.
    - https://milanjovanovic.tech/blog/screaming-architecture
    - https://dvmhn07.medium.com/screaming-architecture-letting-your-code-tell-its-story-203de594cf74

12. **DDD's bounded context makes orthogonality explicit by letting the same word carry different meanings in different regions of the system on purpose, with the boundary drawn along team/codebase/schema lines - not resolved by better shared vocabulary** (confidence: high)
    Evans' own guidance: "explicitly set boundaries in terms of team organization, usage within specific parts of the application, and physical manifestations such as code bases and database schemas." A word like "Creator" legitimately means different things in Onboarding vs. Payment Processing; DDD's answer to ambiguity is not a universal ontology but a fence plus an explicit translation layer between fenced regions.
    - https://www.domainlanguage.com/wp-content/uploads/2016/05/DDD_Reference_2015-03.pdf

13. **B-tree analysis gives a hard cost model for depth vs. fanout: lookup cost is height x per-level fetch cost, and height is logarithmic in the branching factor, so wide-and-shallow beats narrow-and-deep exactly when per-level fetch is cheap relative to the number of levels saved** (confidence: high)
    Formally O(log_B N) I/Os for an N-node tree with branching factor B; a billion keys need ~30 levels at branching factor 2 but only 3-4 levels at branching factor ~200. The "optimal" fanout is not fixed - it is set by matching node size to the medium's latency/bandwidth (SSD favors smaller nodes/faster fetch, high-latency stores favor huge nodes/fewer hops), which is a directly quantified version of "few broad top levels beat many fine ones," but with an explicit variable (per-hop cost) the library-science literature does not name.
    - https://www.usenix.org/system/files/login/articles/login_oct15_05_bender.pdf
    - https://pages.cs.ubc.ca/~laks/Btrees.pdf

14. **RAPTOR demonstrates that a recursively-summarized tree over a corpus measurably beats flat chunk retrieval on multi-hop questions, because summary nodes at higher tree levels are retrievable in the same pass as leaf-level detail** (confidence: medium, single architecture, self-reported gains not independently replicated at scale)
    RAPTOR clusters and LLM-summarizes chunks bottom-up into a tree, then retrieves by flattening all levels into one candidate pool ("collapsed tree traversal") so a query can pull a high-level summary and a granular leaf in the same retrieval step. Reported to outperform flat RAG specifically on cross-chunk reasoning, the failure mode flat chunking has no answer for.
    - https://arxiv.org/abs/2401.18059 (Sarthi et al., "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval")
    - https://superlinked.com/vectorhub/articles/improve-rag-with-raptor

15. **MemGPT's OS-paging metaphor treats forgetting/summarization as a designed feature, not data loss: the agent itself decides what to page out of the active context and into searchable cold storage, and recursive summarization compresses evicted history rather than dropping it** (confidence: high)
    Three tiers mirror OS virtual memory: main context (RAM-equivalent, actively in the prompt), recall storage (all past messages, disk-equivalent), archival storage (vector-indexed cold store). The LLM calls functions (`archival_memory_search`, `core_memory_append`) to move data between tiers itself, and demonstrated a large task-accuracy gain (89% vs. 63% baseline) on document analysis specifically from this self-directed paging.
    - https://arxiv.org/abs/2310.08560

16. **"Lost in the middle" is a measured, position-driven accuracy curve independent of how well-organized the source corpus is: relevant information in the middle of a long context is retrieved 15-30 points worse than the same information at the start or end, across six+ model families** (confidence: high)
    This is a property of what's inside the active context window at generation time, not of folder/index structure - it does not directly measure "useless tokens loaded for a task." The literature's closest proxy for that metric is *effective context length* benchmarks (RULER, BABILong): the fraction of an advertised context window a model can actually use before accuracy collapses, reported as low as 5-50% of the nominal window depending on task and model. No source located defines a token-level "used vs. loaded-but-unused" attribution metric directly; this is a gap, not a finding.
    - https://arxiv.org/abs/2307.03172 (Liu et al., "Lost in the Middle")
    - https://redis.io/blog/context-rot/

17. **Convention-over-configuration (Rails, Maven) eliminates the filing decision entirely for the common case by fixing directory meaning ahead of time, so ambiguity can only occur for genuinely novel content, never for standard artifacts** (confidence: high)
    Maven's `src/main/java`, `src/test/java`, `src/main/resources` are fixed; deviating is "strongly discouraged" because tooling and cross-developer familiarity both depend on the convention holding everywhere. This is a stronger unambiguity guarantee than any scope-note or facet system: it removes the decision point rather than disambiguating it after the fact.
    - https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html

#### Transfers

Each rule states whether it is a structural **map** (the vault has the same mechanism/precondition) or a **metaphor** (borrowed language, precondition absent or unverified), per [[LESSON-human-practice-rationing-assumes-human-scarcity]].

1. **Fewer, broader top-level domains reduce hop count, and hop count is the real cost unit** (MAPS). B-tree theory (Finding 13) makes this quantitative: cost = depth x per-hop cost. In the vault, one hop = one agent reading one folder's `index.md`; this is a direct structural analog (each level read gates descent into the next), not a metaphor - the vault's hop cost and a B-tree's page-fetch cost are the same shape of problem (bounded lookahead, sequential descent).

2. **A domain's `index.md` should behave like a RAPTOR summary node: retrievable on its own as an answer, or as a signal to descend** (MAPS). Compass's index-per-folder design (D-05, D-03) already gives an agent exactly what RAPTOR's collapsed-tree retrieval exploits - a summary usable standalone plus a pointer to more detail below it. Unlike RAPTOR's clustering (unsupervised, corpus-driven), Compass's grouping is human-approved, but the retrieval-time shape (summary-or-descend, one item per level) is identical.

3. **Generality-forced-at-the-parent, autonomy-delegated-to-the-child (DNS/Bazel)**: the root index should never re-explain what a domain folder's own index already explains, and a domain folder should be self-governing for everything under it once created (MAPS). This is already SPEC-022's D-03 and ADR-021's D-01; DNS and Bazel are independent confirmations that this is the standard solution wherever delegation-based namespaces scale, not a Compass-specific choice.

4. **Fix the domain-folder naming convention once, before the vault has many domains, because retrofitting a naming scheme after growth is a documented, expensive migration** (MAPS, with the precondition named explicitly). npm's flat-legacy-vs-scoped split (Finding 7) is the direct precedent: once enough content exists under one naming convention, changing it stops being a local edit and becomes an ecosystem-wide compatibility cost. The vault's open question (bare-name vs. `SPEC-NNN-name/` for domain folders, per the sibling design-axis research) is exactly this decision point, made while switching cost is still low.

5. **Visibility/scope notes should be an explicit, written rule on the folder, not an inferred one** (MAPS for the mechanism, METAPHOR for the enforcement guarantee). Bazel's `package_group` and DDD's bounded-context boundary both make disambiguation a first-class artifact, not tribal knowledge - this maps directly onto writing binding/advisory scope notes into each domain's `index.md` (already recommended by the sibling classification-science research). It is a metaphor at the enforcement level: Bazel's rule is compiler-checked and DDD's is team/codebase-enforced, while a markdown scope note has no mechanical gate unless `compass validate` is taught to check placement against it - that gate does not exist today.

6. **Domain-folder names are load-bearing like package names: avoid dumping-ground names (`common`, `util`, `misc`), and treat a chosen name as expensive to change later** (MAPS). Findings 5's cross-language convergence (Java/Go/Rust all independently forbid the generic catch-all) applies unchanged to a vault domain folder, since Compass already treats folder names as part of a stable wikilink path.

7. **"Useless tokens loaded per task" has no ready-made literature metric to borrow - the nearest instruments (lost-in-the-middle position curves, effective-context-length benchmarks) measure something adjacent, not identical** (GAP, not a transfer). Do not adopt "attention utilization" or "effective context fraction" as SPEC-022's metric without first checking whether either instrument's precondition (a fixed context window being probed by a single model call) matches Compass's actual mechanism (bounded hot-path inclusion decided by file-loading, not by attention weight inside one long prompt). The metric SPEC-022 wants - bytes/tokens read into an agent's context that its final output never used - would need to be defined and measured fresh; no existing benchmark reports it directly.

8. **A markdown vault's type-dir-first, domain-nested-within structure is closer to "package by layer" than "package by feature," which the software-organization literature (Finding 11) reports as the choice associated with lower cohesion and more cross-cutting navigation** (flagged, not a transfer - a tension for the planner). Specs, research, decisions, and plans about the same real-world topic (e.g. "domain taxonomy" itself) currently live in four different type-dirs rather than one feature folder; screaming-architecture/feature-folder evidence would suggest the opposite grouping (by topic first, artifact-type second) for discoverability, while Compass's existing tag-index is the mechanism that currently substitutes for feature-first cohesion. This is presented as a documented trade-off in the literature, not a recommendation to restructure.

#### Gaps

- No literature source directly defines or measures "tokens loaded into context but unused by the task's final output" - the exact metric SPEC-022 names as its goal (Transfer 7). The closest instruments (RULER/BABILong effective-context-length, Liu et al.'s lost-in-the-middle position curves) measure retrieval accuracy by position or by nominal-vs-effective window size, not token-level load/use attribution.
- All B-tree/DNS/Bazel cost evidence is about machine-executed lookups (page reads, resolver hops, compiler visibility checks) with zero-latency-variance repeatability; whether an LLM agent's "cost" of reading one extra folder's `index.md` behaves the same way (same log-linear scaling with fanout) is asserted by structural analogy in Transfer 1, not independently measured for an agent-driven vault.
- RAPTOR's reported gains (Finding 14) are from the paper's own benchmarks; no independent replication was located confirming the magnitude of the multi-hop improvement generalizes outside its original evaluation corpora.

## Axis: Classification science (rs-taxonomy-science, reference)

From [[SPEC-022-vault-organized-per-domain]].

### Question

What do human classification science (library/information science) and machine classification/taxonomy-induction literatures say about building recursive domain hierarchies where a filer's placement decision and a finder's retrieval path agree - i.e., no ambiguity about which top-level area holds a given document?

### Methodology

WebSearch across four sub-axes (human classification theory, measured filing/retrieval ambiguity, machine taxonomy construction, operational disambiguation devices), cross-checked against multiple independent sources per claim where possible. One PDF fetch (arXiv:1706.07931) failed to decode (binary PDF, no OCR available) - excluded, noted as a gap. Cross-referenced Compass's own [[ADR-004-hierarchical-specs-with-facets]] where the human explicitly asked whether it maps.

### Findings

#### Human classification theory

1. **MECE is an ideal that fails on real, multi-dimensional items** (confidence: high)
 Mutually Exclusive/Collectively Exhaustive (Minto, McKinsey, traces to Aristotle) requires picking one basis of segmentation at a time; mixing dimensions (e.g., age AND occupation in one category set) breaks mutual exclusivity. Real documents routinely span more than one dimension (a book both "Science" and "History"), which pure MECE cannot resolve without an arbitrary tie-break rule. "Exhaustive" is also scope-relative: a MECE set only covers what was declared in scope, so it can quietly omit new material.
 - https://en.wikipedia.org/wiki/MECE_principle

2. **Enumerative classification (Dewey/LCC) pre-lists every class; faceted classification (Ranganathan's Colon Classification, 1933) synthesizes a notation from independent facets instead** (confidence: high)
 Ranganathan's PMEST (Personality, Matter, Energy, Space, Time) analyzes any subject into up to five facets and combines them with colon separators into one compound notation, rather than looking up a pre-enumerated single class number. This was a direct response to enumerative schemes being unable to keep pace with new interdisciplinary subjects. UDC is a hybrid ("almost-faceted": enumerative base plus facet indicators); DDC added auxiliary tables (faceting grafted onto an enumerative base) starting with its 18th edition (1971).
 - https://www.redalyc.org/journal/3843/384357586006/html/
 - https://ebooks.inflibnet.ac.in/lisp2/chapter/species-of-bibliographic-classifications-enumerative-and-faceted/

3. **Compass's tag facets are folksonomy post-coordination, not Ranganathan-style pre-coordinate faceting - maps as metaphor, not mechanism** (confidence: high, direct comparison)
 Ranganathan's facets are combined at classification time into a single compound call number that still fixes one shelf location; multi-parent access in CC comes from chain-indexing/cross-references, not from the primary notation living in two places. Compass's own [[ADR-004-hierarchical-specs-with-facets]] tags are explicitly "folksonomy (free-form, not controlled vocabulary)" (`ADR-004-hierarchical-specs-with-facets.md:54`) used for a separate `tag-index.yaml` lookup - closer to post-coordinate keyword indexing than to PMEST notation-building. Per [[LESSON-human-practice-rationing-assumes-human-scarcity]]'s naming discipline: the precondition Ranganathan's facets need (a controlled, analyzed set of fundamental categories synthesized into one address) is absent; Compass's tags are an orthogonal retrieval index layered over a single-path folder tree, which is closer to what CC calls chain indexing than to CC's own classification act.

4. **Living recursive domain taxonomies (MSC, ACM CCS) solve multi-topic placement two different ways: single-primary-plus-secondary vs. true poly-hierarchy** (confidence: high)
 - MSC2020 (Mathematical Reviews/zbMATH): every item gets exactly **one** primary code - "the MSC code that describes its principal contribution" - chosen as the *most important* contribution when several exist, plus optional secondary codes for the rest. Hierarchical, 2/3/5-digit levels (63 top-level, 529 three-digit, 6,022 five-digit as of 2020).
 - ACM CCS 2012 replaced the 1998 letter-number scheme with a **poly-hierarchical** ontology: one concept (e.g., "Cluster analysis") legitimately sits under six different branches at once (Theory of computation, Machine learning, Information retrieval, etc.), with 13 top-level roots.
 - Both schemes require literature to actually justify a class (see Finding 6) and both are periodically revised by an editorial board rather than fixed once.
 - https://msc2020.org/MSC_2020.pdf
 - https://www.acm.org/publications/class-2012 ; https://en.wikipedia.org/wiki/ACM_Computing_Classification_System

5. **MSC2020's cross-reference syntax distinguishes mandatory redirection from optional related-topic pointers** (confidence: high)
 Braces `{For A, see X}` mean "contributions described by A should usually be assigned X, not this section" (a placement override); brackets `[See also ...]` / `[See mainly ...]` mean the classifier may but need not also use that code, and must judge which is most appropriate. This is a two-tier disambiguation device: one binding, one advisory.
 - https://msc2020.org/MSC_2020.pdf (§ classification instructions)

6. **Literary warrant: categories are only created once the corpus already contains enough documents to justify them, not invented ahead of the fact** (confidence: high)
 Coined by E. Wyndham Hulme (1911-1912): "if there are books on the subject of electricity and magnetism, there is literary warrant for providing a number for such a class." Ranganathan folded this into his laws of classification (arrange isolates by decreasing published quantity). Both LCC and DDC explicitly trace their scope to the literary warrant of their host collections; DDC's editions have been revised under this principle for over a century.
 - https://www.isko.org/cyclo/literary_warrant
 - https://www.researchgate.net/publication/357117744

7. **Literary warrant is one of a family of "warrants"; Beghtol's 1986 typology names at least a dozen, several directly relevant to a vault used by both a human and agents** (confidence: medium)
 Beghtol (1986, 1992) and later Barité group warrants into tiers; besides literary warrant, named warrants include user warrant (users' participation in shaping the scheme - Beghtol cites Patterson et al. 2000: "collaboration of potential users... in the development and use of any knowledge management system"), organizational warrant, cultural warrant ("every classification system is based on the assumptions and preoccupations of a certain culture," Beghtol 2002), structural warrant, and scientific/educational warrant. No single canonical list exists across scholars (Barité notes the literature "lacks a homogeneous, stable body of ideas").
 - https://www.researchgate.net/publication/312094149_Warrant_as_a_means_to_study_classification_system_design (Bullard 2017)
 - Beghtol, C. (2002). "A proposed ethical warrant for global knowledge representation and organization systems." Journal of Documentation, 58(5), 507-532.

#### Measured ambiguity (does this actually work when tried)

8. **Inter-indexer consistency is low and considered inherent, not a fixable anomaly** (confidence: high)
 Since the 1960s, studies converge on "inconsistency is an inherent feature of indexing." Markey (1984): 39 indexers on 100 art works, 7% exact-term agreement, 13% concept-level agreement. Across the heterogeneous body of studies (different methodologies, not directly comparable), reported consistency ranges roughly 10-60%.
 - https://asistdl.onlinelibrary.wiley.com/doi/full/10.1002/meet.14504301274
 - https://www.researchgate.net/publication/235290123_Inter-indexer_Consistency_in_Graphic_Materials_Indexing_at_the_National_Library_of_Wales

9. **What raises consistency: fewer/broader terms, conceptual (not exact-string) matching, and indexer expertise - with at least one contradicting study** (confidence: medium)
 Sievert & Andrews (1991): 50.4% consistency at mean depth of 1 term vs 33.9% at depth 7.48 terms - more categories assigned per item lowers agreement. Neshat & Horri (2006) state the same direction generally. Markey (1984) found concept-level agreement (13%) nearly double exact-term agreement (7%) - broader/conceptual grouping is more reproducible than literal labels. Shoham & Kedar (2001): novice/expert indexer agreement is low; Saarti (2002): professional indexers agree more than patrons. Contradiction: an unnamed earlier study cited in the same review found consistency "does not seem to change much with depth" - the depth-consistency relationship is not universally replicated.
 - https://informationr.net/ir/16-4/paper502.html

10. **Card sorting shows a structural gap between organizer categories and user (finder) mental models** (confidence: high)
 Teams often sort by their own organization (e.g., "Product," "Support," "Engineering") while users group by goal (e.g., "Getting Started," "Troubleshooting"). Open card sorts (participant-defined categories) reveal mental models but are less consistent across participants than closed sorts (fixed categories) - and closed sorts, by construction, cannot tell you whether the given categories were right to begin with.
 - https://www.nngroup.com/articles/card-sorting-definition/

11. **Tree testing's "first click" on the top-level category is the single best predictor of a finder locating the right document** (confidence: high)
 Because subcategories are invisible until a top-level node is opened, the first click is necessarily a top-level choice, and getting it right correlates strongly with ultimate task success. A documented failure pattern: correct top-level chosen first by only 48% of participants but visited eventually (after backtracking) by 71% - the gap between "first click %" and "visited during %" is the diagnostic for an unclear top-level label.
 - https://www.nngroup.com/articles/interpreting-tree-test-results/
 - https://www.optimalworkshop.com/101-guides/tree-testing-101/first-click-tab

#### Machine organization

12. **Two competing paradigms for corpus-driven taxonomy construction, each with a documented failure mode** (confidence: medium, active research area, mostly 2024-2026 arXiv preprints not yet fully peer-reviewed)
 Corpus-driven methods (embedding clustering, e.g. UMAP+HDBSCAN, k-means-based HERCULES) capture domain nuance but suffer from data sparsity producing fragmented/overly-narrow structures on small corpora. LLM-driven methods (prompt the model to propose a taxonomy directly, e.g. CHIME, TNT-LLM) give broader conceptual coverage but miss emerging topics absent from pretraining. Recent hybrids (TaxoAdapt, TIER, SCYCHIC) combine embedding clustering with LLM-generated labels/refinement and report gains over either paradigm alone on their own benchmarks (e.g., TaxoAdapt: +26.5% path granularity, +50.4% coherence vs. LLM-only/corpus-only baselines - self-reported, not independently replicated).
 - https://arxiv.org/pdf/2510.15125 (iterative topic taxonomy induction)
 - https://arxiv.org/pdf/2506.10737 (TaxoAdapt)
 - https://en.wikipedia.org/wiki/Automatic_taxonomy_construction

13. **Hierarchical classification's central documented weakness is top-down error propagation: a wrong top-level pick cannot be corrected lower in the tree** (confidence: high, this is the standard/textbook finding, Silla & Freitas survey is the most-cited reference in the field)
 "An incorrect parent node almost guarantees an incorrect prediction" - errors at higher levels compound downward and cannot be rectified at lower levels. A related, distinct failure is "blocking": items wrongly rejected by a high-level classifier never reach the lower-level classifiers that could have placed them correctly. One deliberate mitigation trades recall for safety: only pass an item down a level if confidence exceeds a threshold, otherwise stop it at a coarser, correct-but-less-specific ancestor node rather than force a wrong leaf.
 - https://www.cs.kent.ac.uk/people/staff/aaf/pub_papers.dir/DMKD-J-2010-Silla.pdf (Silla & Freitas, widely-cited survey)
 - https://arxiv.org/pdf/1706.01214 (inconsistent-node flattening as one fix)

14. **The literature explicitly recommends human-curated top levels with machine-assisted lower-level placement over full automation, for taxonomy-building specifically (not just classification of pre-existing items)** (confidence: medium)
 Meier & Glinka (arXiv:2307.16481, "To Classify is to Interpret") argue explicitly against relying only on black-boxed ML systems for taxonomy building because it sidelines user/domain expertise, proposing instead an iterative process where humans take multiple model outputs into their own sensemaking loop. A CHIIR 2026 system and an industry case study (Coreon) both describe the same division of labor in practice: embedding-based clustering produces a structured first-pass tree, and a human does final curation - the clustering's value is making the human's work methodical and distributable, not replacing the human's placement judgment.
 - https://arxiv.org/pdf/2307.16481
 - https://dl.acm.org/doi/10.1145/3786304.3787912
 - https://coreon.com/2021/01/11/keeping-your-sanity-with-machine-taxonomization/

#### Operational disambiguation devices

15. **DDC's "class here" / "class elsewhere" notes are the explicit textual device schemes use to pre-empt filer ambiguity, and they follow a fixed ordering** (confidence: high)
 A class-here note lists topics that approximate the whole of a class (so standard subdivisions may attach to any of them). A class-elsewhere note tells the classifier where an interrelated topic actually belongs instead - it can set a preference order, redirect to an interdisciplinary number, or point across a hierarchical array. Rule for telling them apart: any note starting with the word "class" is class-elsewhere *unless* it starts with "class here." Notes in a DDC schedule entry appear in a fixed sequence (definition, scope, including, class-here, ..., class-elsewhere, see-reference, see-also) - the scheme itself enforces where disambiguating text lives so classifiers check it in the same order every time.
 - https://help.oclc.org/Librarian_Toolbox/OCLC_glossaries/Dewey_Decimal_Classification_glossary
 - https://ddc.typepad.com/025431/2017/12/class-here-notes.html

16. **Johnny.Decimal enforces disambiguation with a hard numeric ceiling rather than a semantic rule: max 10 areas x max 10 categories x max 100 items, and files must live inside a category, never loose at the area or category level** (confidence: high)
 The system's own documentation frames the ceiling as the mechanism, not the decimal notation: "these structural rules are what make JD powerful... not necessarily the [decimal] prefix." When a category would exceed 100 items, the documented remedy is an appended identifier or splitting into a new category - the limit is the trigger for reorganization, not a hint to ignore. A forum-reported failure mode: teams often can't tell in advance whether an emerging cluster of files should become its own category or stay a "bucket" inside an existing one, and by the time a category nears 100 items it is already too late to cleanly re-split.
 - https://johnnydecimal.com/documentation/philosophy
 - https://forum.johnnydecimal.com/t/using-johnny-decimal-with-more-than-100-files-per-category/441

17. **PARA organizes by actionability (Projects/Areas/Resources/Archives), not by topic - a different axis than Johnny.Decimal's topical numbering, and practitioners report combining or abandoning one for the other rather than running both cleanly forever** (confidence: low, practitioner blog reports, not peer-reviewed)
 PARA's top-level split answers "how soon will I act on this," while Johnny.Decimal's areas/categories answer "what is this about." Multiple independent practitioner write-ups describe migrating between the two or nesting one inside the other (JD's 10-way split applied inside each PARA bucket) rather than finding either sufficient alone; one write-up called PARA "philosophical rather than taxonomical" and reported it not scaling past a year of use.
 - https://help.noteplan.co/article/155-how-to-organize-your-notes-and-folders-using-johnny-decimal-and-para
 - https://crystaljjlee.com/blog/two-approaches-to-pkm/

### Contradictions

- Finding 9 reports two directly conflicting results on whether indexing depth (more categories per item) lowers consistency: Sievert & Andrews found a clear negative relationship, but the same review cites an unnamed earlier study finding "consistency does not seem to change much with depth." The relationship is not settled in the literature.
- Finding 2/3 vs. Compass's own ADR-004: ADR-004's "Alternatives considered" section invokes Ranganathan as justification for tags ("Ranganathan demonstrated in 1933 that strict hierarchy cannot accommodate multi-perspective content"), but Compass's actual tag mechanism (folksonomy keyword index, `ADR-004-hierarchical-specs-with-facets.md:54`) is structurally closer to post-coordinate indexing than to Ranganathan's own pre-coordinate PMEST notation-building. The citation supports the general problem (strict hierarchy can't hold multi-perspective content) but not the specific mechanism chosen to solve it.

### Gaps

- arXiv:1706.07931 ("Challenges of facet analysis and concept placement in universal classifications: the example of architecture in UDC") could not be read - WebFetch received only the undecoded compressed PDF binary. This paper looked directly on-point (UDC placement ambiguity for a genuinely multi-disciplinary subject) and should be re-fetched via a PDF-to-text tool or manual retrieval if the planner wants it.
- No inter-indexer consistency study located that tests a *recursive folder-of-folders* domain scheme specifically (all located studies test flat or shallow controlled-vocabulary indexing, not deep hierarchical filing of documents into nested directories). This is the closest structural analog to SPEC-022's design but is an inference gap, not a directly measured one.
- No study located that measures inter-indexer consistency specifically for LLM agents (all consistency literature is human-indexer studies); whether the low human baseline (10-60%) transfers to an LLM filer is unverified and should be flagged as an open empirical question for SPEC-022, not assumed.

## Axis: Design space (rs-taxonomy-design)

Grounded in [[SPEC-022-vault-organized-per-domain]], [[ADR-021-index-speaks-in-domains]] (accepted same day, already shipped v0.15.0), [[SPEC-005-index-auto-maintained-and-mirrored-per-folder]] (on hold), [[SPEC-003-hierarchical-vault-organization]] / [[ADR-004-hierarchical-specs-with-facets]], [[SPEC-010-universal-hybrid-hierarchy]] / [[ADR-006-hybrid-hierarchy-implementation]], the vault's own live grouping proposal `.compass/tmp/domain-proposal-2026-08-30.md`, `plugin/skills/consolidate/SKILL.md`, and `plugin/skills/obsidian/SKILL.md`.

### Finding 1: A decision on domain-folder mechanics was already made same-day, in ADR-021

ADR-021 (accepted 2026-08-30, shipped v0.15.0) rules D-01 (root index lists depth-0 entries only; a folder line with child count is the pointer) and D-04 (grouping moves are the *existing* commands - `compass promote`, `compass make-unit`, plain `git mv` into folder specs - "no new migration machinery"). It does not introduce a `type: domain` artifact kind. Any design-space mapping here must treat ADR-021 as already-decided ground, not an open option. (Confidence: high - `.compass/decisions/ADR-021-index-speaks-in-domains.md:22-26`, `.compass/active.md:16`)

### Finding 2: The vault's own live proposal already exercises three distinct domain-folder shapes

`.compass/tmp/domain-proposal-2026-08-30.md` (Structure-pass output, awaiting the human's approval per `.compass/active.md:17`) groups 22 root specs into 5 lines and 35 research docs into ~9, using three different realizations:
- **Promoted-natural-parent** (D1, D2): an existing spec already conceptually parents its group; `compass promote` turns it into the folder, e.g. `SPEC-003-hierarchical-vault-organization` promoted to hold SPEC-005, SPEC-010, SPEC-016, SPEC-019, SPEC-011, SPEC-022 as children.
- **Thin synthetic grouping, no natural parent** (D3 `specs/distribution/`, D4 `specs/pipeline/`): explicitly labeled "new grouping folder ... thin domain index" - no existing spec is promoted; the folder and its `index.md` are created fresh.
- **Research folder backed by a synthesis doc** (R1, R2) vs **"thin index"** research folder with no synthesis doc (R3-R6, e.g. `research/hermes/`, `research/distribution/`).

Units (`compass make-unit`) are available but unused in this round - none of the proposed groups is framed as an ongoing workstream. (Confidence: high - `.compass/tmp/domain-proposal-2026-08-30.md:5-42`)

### Finding 3: `compass promote` cannot originate a domain folder from nothing - it requires an existing source file

`promote.py` moves `specs/SPEC-NNN-name.md` to `specs/SPEC-NNN-name/index.md` via `git mv` and stamps `children_count: 0`; its `_resolve()` fails if no such file exists. There is no CLI path that creates a brand-new folder + hand-authored `index.md` when no natural parent spec exists. The "thin index" cases in Finding 2 (D3, D4, R3-R6) therefore fall outside both `compass promote` and `compass make-unit` (root-only, see Finding 4) - the consolidate skill's own S4 names the fallback explicitly: "`git mv` into folder specs," i.e. a manual mkdir + move + hand-write, not a dedicated command. (Confidence: high - `plugin/cli/commands/promote.py:1-33`, `plugin/skills/consolidate/SKILL.md:164`)

### Finding 4: `compass make-unit` is root-only and multi-type; a domain folder as proposed is same-type and can nest anywhere

`make_unit.py` refuses any name in `RESERVED_NAMES` and writes the unit directly under the vault root (`vault_root / name`), with per-artifact-type subdirectories (`specs/`, `research/`, `plans/`, `decisions/`, `lessons/`) inside it (ADR-006 D-01: units live at the vault root only). A SPEC-022 domain folder (e.g. `specs/distribution/`) is a same-type grouping one level inside an existing type dir, and D-02 requires it to recurse to any depth - structurally the opposite shape from a unit (cross-type, root-only, one level). Units and domain folders are not the same mechanism despite both being folders with `index.md`. (Confidence: high - `plugin/cli/commands/make_unit.py:61,119-171`, `.compass/decisions/ADR-006-hybrid-hierarchy-implementation.md:25`)

### Finding 5: The team lead's tension - "a domain is not itself a problem statement" - is visible in the vault's own naming choice, unresolved in template terms

The folder-spec template (`plugin/skills/obsidian/SKILL.md:169-193`) requires the folder body to be "the parent spec body... Hold decisions and concerns that stay at this level," and the wikilinks rule states "the parent holds the decisions shared by every child; a child exists to diverge on something the parent left open" (ADR-011 D-06, cited in `.claude/rules/wikilinks.md` is not itself the source - the rule is stated in `CLAUDE.md`'s Hierarchical specs section, mirrored in obsidian SKILL.md:144). A domain like "distribution" or "pipeline" has no such shared decision - it's a topical bag, not a problem with sub-concerns. The live proposal marks this by literally distinguishing "parent: promote X" (has decisions) from "thin domain index" (does not) - the vocabulary exists in practice but no template defines what a "thin" index's body should contain in place of a Problem/Decisions section. (Confidence: high - `plugin/skills/obsidian/SKILL.md:144,171-191`; gap confirmed absent from ADR-021 and consolidate SKILL.md)

### Finding 6: ADR-021 asserts the domain index IS "the spec/domain document itself," but does not specify the thin-index content shape

ADR-021 D-01: "the folder's own `index.md` (the spec/domain document itself) names what matters about them" - collapsing the domain-folder question into the existing folder-spec kind (Option a in the team lead's framing) by fiat, without addressing Finding 5's tension. The consolidate skill's S2 only says specs "fold as children into a folder spec" and research docs "fold into a folder named for the domain," with no worked example of a thin body. No implementation of this proposal has landed yet (it's still `.compass/tmp/`, unapplied), so there is no real thin-index file in the vault to point to as precedent. (Confidence: medium - decision is explicit but the content template is not; inferred gap, not directly tested)

### Finding 7: SPEC-005's per-folder index design (machine-only, fully regenerated) was never built; ADR-021 shipped a much thinner mechanism instead

SPEC-005 (drafted 2026-06-19, status still `draft`, ON HOLD per its own handoff pending proof that LLM-summary cost is bounded) specified: `index.md` is machine-only, never human-edited, fully regenerated on every sync including a per-folder contents listing, with detached `claude -p` haiku summaries and a backfill-on-update. None of that shipped. What actually shipped (ADR-021 + `sync.py`) only changes the ROOT index to stop listing depth>0 entries (`sync.py:180-190`); it does not touch or regenerate any folder's own `index.md` contents section. SPEC-005's open questions (delimiter format, regeneration boundary, reconcile triggers, summary tool) remain fully open. (Confidence: high - `.compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md:4,79-86`, `plugin/cli/commands/sync.py:147-190`)

### Finding 8: In the shipped code, a folder's own `## Children` listing is hand-authored or one-shot-written, never continuously synced

- `compass promote` (`promote.py:54-59`, `_add_children_count`) inserts only `children_count: 0` into frontmatter - it writes NO `## Children` section at all. Per the obsidian template, the agent must hand-author that section afterward.
- `compass make-unit` (`make_unit.py:174-196`, `_unit_index_text`) writes a full `## Children` listing, but only once, at creation/move time - there is no later sync step that refreshes it as the unit's contents change; refresh is left to `/compass:consolidate` (obsidian SKILL.md:193: "the `## Children` section must be refreshed (`/compass:consolidate` does this)").
So today's actual answer to "generated, hand-authored, or hybrid" (team lead's Q2) is: hybrid, but inconsistent across the two existing mechanisms, and never continuously regenerated by `sync` the way SPEC-005 envisioned. (Confidence: high - direct code read)

### Finding 9: `area` frontmatter looks like a domain field but has already drifted past its documented enum

`obsidian/SKILL.md:38` documents `area` as REQUIRED for all types with enum `architecture | frontend | backend | testing | devops | infra | docs | workflow`. Every spec/ADR/research doc read for this task instead carries `area: methodology`, which is not in that enum (SPEC-003, SPEC-005, SPEC-010, SPEC-022, ADR-004, ADR-006, the RAPTOR/MemGPT research doc all use `area: methodology`). `validate.py`'s `REQUIRED_FIELDS` table checks only field *presence*, not enum membership (`validate.py:40-44`), so nothing enforces the documented set. This means a controlled-vocabulary-shaped field already exists and is already being used folksonomy-style in practice - relevant prior art for whether "domain" needs a wholly new field or could ride on fixing `area`. (Confidence: medium - enum drift confirmed by direct read of 7+ files; absence of enum enforcement confirmed by reading `validate.py`'s field list, not its full logic)

### Finding 10: Facets (tags) and folder-domains are designed as orthogonal, non-competing axes - no contradiction found

ADR-004 Part 3 and obsidian SKILL.md's "Facet tags" section keep `tags:` as free-form folksonomy resolved via `.compass/meta/tag-index.yaml`, explicitly the "multi-parent retrieval primitive" so agents don't crawl folders. SPEC-022's Non-Goals states grouping does not change "the facet/tag system." The consolidate Structure pass (S2) explicitly keeps both: grouping by folder AND flagging tag-vocabulary repairs in the same pass. One artifact: one folder (single physical parent), many tags (many logical parents) - this is exactly ADR-004's original answer to Ranganathan's multi-parent problem, undisturbed by SPEC-022. (Confidence: high - `.compass/decisions/ADR-004-hierarchical-specs-with-facets.md:52-56`, `.compass/specs/SPEC-022-vault-organized-per-domain/index.md:44`, `plugin/skills/consolidate/SKILL.md:156`)

### Finding 11: `taxonomy_hint` (SPEC-022 D-04) is a named concept with zero implementation - not even a stub field

the human's D-04: "when making a new spec is a good point to reorganize if needed, and at least mark for the next consolidate/taxonomize a hint - by the agent who understands the spec better than others." A repo-wide grep for `taxonomy_hint` returns zero matches anywhere in `plugin/` or `.compass/` - no frontmatter field, no capture-note integration, no mention in ADR-021 or the consolidate skill (which only reacts to a hard-cap warning, not to a per-spec hint left at creation time). This is a genuinely open question, not merely under-specified: ADR-021 resolved D-01/D-02/D-03/D-04 of its own numbering but never addresses SPEC-022's D-04 at all. (Confidence: high - repo-wide grep returned zero hits; ADR-021 text re-read confirms no mention)

### Finding 12: Two incompatible naming conventions already coexist for domain folders depending on origin

Promoted-natural-parent domains keep their numbered stem (`SPEC-003-hierarchical-vault-organization/`, following the existing `SPEC-NNN-name/` folder-spec convention from ADR-004/obsidian SKILL.md:142-157). Thin/synthetic domains in the live proposal use bare descriptive names with no number or prefix (`specs/distribution/`, `specs/pipeline/`, `research/hermes/`, `research/vault-structure/`). Both are root type-dir subfolders, so both resolve today under the existing "folder spec" bare-stem wikilink rule (obsidian SKILL.md's "Bare stems vs path-qualified links" table only mandates path-qualification for *unit* artifacts, not for domain folders). This works only as long as domain-folder names and numbered spec-folder names never collide vault-wide - untested at scale. (Confidence: medium - naming forms directly observed in the live proposal; collision behavior is inferred, not tested)

### Finding 13: Local numbering inside domain folders reopens the exact ambiguity ADR-006 already solved once, for a case ADR-006 didn't cover

ADR-006 D-02/D-03 solved bare-stem collision across *unit* folders by mandating path-qualified links (`[[<unit>/specs/SPEC-001-name]]`) and adding an `ambiguous_wikilink` validate warning, explicitly rejecting "shortest-path tiebreak" as a silent-wrong-pick failure mode. SPEC-022 D-02's recursive domain folders under `specs/`/`research/` also number locally per folder (per the general JIT max+1 rule, obsidian SKILL.md:120-136), so `specs/distribution/SPEC-001-x` and `specs/pipeline/SPEC-001-y` can both exist. But domain folders are not units, so ADR-006's path-qualification mandate does not obviously apply to them - the wikilinks rule's step 3 tiebreak ("prefer the shortest path... check whether the linking document sits inside a unit folder") only special-cases units. Whether domain-folder children need the same path-qualified treatment is an open question ADR-021 did not address. (Confidence: high - direct comparison of `.compass/decisions/ADR-006-hybrid-hierarchy-implementation.md:26-27,37,49` against `.claude/rules/wikilinks.md:1-16` and `plugin/skills/obsidian/SKILL.md:217-232`)

### Finding 14: Promote/demote's classification list would need extension for nested (non-root) grouping folders

`make_unit.py`'s `RESERVED_NAMES = CORE_TYPE_DIRS | NON_TYPE_DIRS` and `vaultlib.classify_root_dirs` classify folders only at the vault root (units) or via the folder-spec `index.md` marker convention (`type: spec`/`type: plan` implied by presence of `index.md`, per ADR-004 - no explicit "domain" marker exists in `vaultlib.py`'s classification logic beyond what's used for units, `CORE_TYPE_DIRS = ["specs","plans","research","decisions","lessons","handoffs","prs"]`). A `specs/distribution/` grouping folder with a "thin" index.md that carries `type: spec` frontmatter (per Finding 6's fiat) will classify identically to a genuine folder-spec today - no code distinguishes "domain grouping" from "spec with real sub-concerns" at the classification layer, which is consistent with Option (a) but means nothing in the CLI currently tracks *why* a folder exists (grouping vs genuine hierarchy). (Confidence: medium - inferred from `vaultlib.py:14-17` constants plus absence of any `domain` marker in grep results across `plugin/cli/`)

### Option matrix

| # | Question | Options mapped | What the vault's own evidence shows | Recommendation (not decision) |
|---|---|---|---|---|
| 1 | What IS a domain folder? | (a) folder-spec index.md IS the spec; (b) new `type: domain`; (c) unit; (d) plain grouping folder + generated index | ADR-021 already picked (a) for all cases, including "thin" ones with no natural parent (Findings 1, 6). (c) is structurally wrong-shaped for same-type nested grouping (Finding 4). (d) is what actually happens mechanically for thin domains today, just wearing `type: spec` frontmatter (Finding 3, 6). | Ratify ADR-021's choice for the natural-parent case; for the thin/synthetic case, decide explicitly whether `type: spec` is honest or whether a distinct, lighter frontmatter shape (still not a whole new artifact type) is warranted, since the folder-spec template's "Problem"/"Decisions" framing does not fit a topical bag (Finding 5). |
| 2 | What does a folder's index.md contain? | generated; hand-authored; hybrid (generated Contents in an authored doc) | Today: `promote` writes no listing at all (hand-author required); `make-unit` writes it once, never refreshes; SPEC-005's full auto-regeneration design was never built (Findings 7, 8). | Close the gap named in Finding 8 before or alongside SPEC-022's build: either extend `sync` to also maintain each folder's `## Children` section (the SPEC-005 ambition, minus its unbuilt LLM-summary layer), or explicitly accept hand-authored/consolidate-refreshed as the permanent answer and update the obsidian template to say so plainly. |
| 3 | Facets vs domain folders | facets redundant vs facets remain cross-cutting | No contradiction found; SPEC-022 explicitly preserves ADR-004's tag system as orthogonal (Finding 10). `area` is a near-domain field already drifting into folksonomy use unenforced (Finding 9). | Keep facets as designed; separately consider whether `area`'s enum drift (Finding 9) should be reconciled now, since it is adjacent surface area a domain-folder change will make more visible. |
| 4 | taxonomy_hint mechanics | frontmatter field vs capture-note vs both | Zero implementation exists; ADR-021 did not resolve SPEC-022 D-04 at all (Finding 11). | This is a genuine open design question for the planner, not a re-litigation - no prior art to ground a recommendation. |
| 5 | Domain folder naming | numbered `SPEC-NNN-name/` vs bare descriptive name | Both already coexist in the live unapplied proposal depending on origin (promoted vs thin) (Finding 12); local numbering inside nested domains reopens the collision problem ADR-006 solved for units but did not extend to non-unit nested folders (Finding 13); classification tooling does not distinguish domain groupings from ordinary folder specs (Finding 14). | Decide whether nested domain folders get the same path-qualified-link treatment ADR-006 mandated for units, since local numbering makes bare-stem collisions structurally possible the moment two domains each reach a `SPEC-001`. |

#### Gaps
- No worked example of a "thin domain index" exists in the vault yet (the proposal is unapplied) - the content shape in Finding 6 is asserted by ADR-021, not demonstrated.
- No PLAN-003 or later ADR implementing SPEC-005 was found anywhere in `.compass/plans/` or `.compass/decisions/` - confirm this negative before assuming SPEC-005 is fully abandoned rather than merely still on hold.

## Axis: Ripple (rs-taxonomy-ripple)

Traces to [[SPEC-022-vault-organized-per-domain]]. Documentarian pass only - no recommendations.

### Finding 1: Domain folders and folder specs are the same code-level object

`vaultlib._scan_type_dir` (`plugin/cli/vaultlib.py:229-278`) classifies every `.md` file under a type dir purely by path depth: an `index.md` at `len(parts) > 1` becomes `kind="folder-index"` regardless of whether the folder is a spec, a plan, or a bare grouping folder. There is no `is_domain` or `is_spec` flag - a domain folder created for SPEC-022 (e.g. `research/distribution/index.md`) is structurally indistinguishable from a folder spec.
Confidence: high. Evidence: `plugin/cli/vaultlib.py:229-278`; confirmed by existing passing test `test_folder_spec_child_still_gets_bare_stem_link` in `plugin/cli/tests/test_sync.py:578`, which uses a `research/pack/index.md` fixture and asserts it is classified/linked exactly like a spec folder.

### Finding 2: `classify_root_dirs` never sees nested domain folders

`classify_root_dirs(root)` (`plugin/cli/vaultlib.py:55-82`) only classifies DIRECT children of the vault root (or a unit root) into `type_dirs` / `units` / `unclassified`. A domain folder nested inside `specs/` or `research/` never passes through this function - it is only ever discovered later, inside `_scan_type_dir`'s `rglob`. Unit-detection (`type: unit` frontmatter) is therefore never checked for a domain subfolder; a domain folder can never itself become a "unit" through this code path today.
Confidence: high. Evidence: `plugin/cli/vaultlib.py:55-82`, `:229-278`.

### Finding 3: Arbitrary-depth nesting already works and is already tested

Three-level folder-index nesting (`SPEC-002-tile-editor/SPEC-002-brush/SPEC-001-stroke`, depth 2) is exercised by an existing passing test.
Confidence: high. Evidence: `plugin/cli/tests/test_vaultlib.py:79-98` (`test_flat_folder_and_nested_classification`).

### Finding 4: `_sync_index` only ever writes the ROOT `index.md`

`_sync_index(vault_root, records)` (`plugin/cli/commands/sync.py:147-269`) appends missing entries into the single root `.compass/index.md`, one section per root type dir/unit. Line 187-190 implements the already-shipped ADR-021 rule: `if record["depth"] > 0 and not vaultlib.is_loose_nested(...): continue` - any record nested under a folder that already owns an `index.md`, at any depth, is skipped from the root listing. There is no code path anywhere in `sync.py` that regenerates a per-folder `index.md`'s own children listing. That refresh is currently a human/agent judgment call, per the obsidian skill's note that a folder-index's `## Children` section "must be refreshed by `/compass:consolidate`" - not automatic.
Confidence: high. Evidence: `plugin/cli/commands/sync.py:147-269`, specifically `:187-190`.

### Finding 5: `_is_generated_output`'s loop guard matches ANY path ending in "index.md", not just root

```python
def _is_generated_output(file_path):
 norm = str(file_path).replace("\\", "/")
 return any(norm.endswith(suffix) for suffix in GENERATED_OUTPUTS)
```
(`plugin/cli/commands/sync.py:583-585`, `GENERATED_OUTPUTS` at `:42-47`). Verified by direct execution: `.compass/specs/SPEC-010-foo/index.md`, `.compass/specs/domain-x/index.md`, `.compass/specs/domain-x/SPEC-001-y/index.md`, and `.compass/research/domain-x/index.md` all return `True`; only a non-index file like `.compass/research/domain-x/RESEARCH-001.md` returns `False`. This is the PostToolUse hook's loop guard (`run(args)`, `:621-648`): today it happens to also suppress the capture-signal / recursive-sync check for every nested folder-spec's own `index.md` write, not only the root's. This behavior is completely untested - `test_own_output_write_is_noop` and `test_generated_output_records_nothing` (`plugin/cli/tests/test_sync.py:719`, `:799`) only exercise the literal root `self.root / "index.md"` path.
Confidence: high (verified by direct test execution, reproduced above; test-suite gap confirmed by grep).

### Finding 6: `_link_name` treats every folder-index identically regardless of type dir

`_link_name(record)` (`plugin/cli/commands/sync.py:100-117`): for `kind == "folder-index"` with `unit is None`, returns `record["path"].parent.name` - the bare folder name - with no distinction between a spec folder and a research/anything-else domain folder. `_child_count` (`:139-144`) counts records whose name starts with `folder_record["name"] + "/"` with no further `/` in the remainder; manually traced to generalize correctly to arbitrary nesting depth (each level's own folder-index record only ever counts its own direct children).
Confidence: high. Evidence: `plugin/cli/commands/sync.py:100-117`, `:139-144`.

### Finding 7: Ambiguous-wikilink collision risk across type dirs for same-named domains

`resolvable_names_map(vault_root)` (`plugin/cli/vaultlib.py:304-326`) builds one name-to-paths map from every markdown file vault-wide (`all_markdown_files`, `:99-114`), adding for every `index.md` file both the bare parent-folder name and its path-qualified name. If two domain folders share a bare name across different type dirs (e.g. `specs/distribution/index.md` and `research/distribution/index.md`), the bare name `distribution` maps to two paths - `validate.py`'s `_check_links` flags this as `ambiguous_wikilink`. Domain folders have no path-qualification convention of their own (unlike units, whose artifacts are always linked path-qualified per `.claude/rules/wikilinks.md`).
Confidence: medium (code-traced, not reproduced with an actual same-named collision in this vault).

### Finding 8: `compass next-num` already supports arbitrary multi-level nested domain scopes

`next_num.py:41-49` treats `scope` as an opaque string that may contain `/`; if it doesn't match a known unit name, `base = vault_root / type_dir / scope` is used directly - this already works transparently for scopes that don't exist yet. Verified live against this repo (read-only):
```
python .claude/cli/compass next-num spec specs/SPEC-022-vault-organized-per-domain -> 001, exit 0
python .claude/cli/compass next-num spec nonexistent-domain/nonexistent-subdomain -> 001, exit 0
```
No existing test exercises a multi-level scope - `test_commands.py` only covers single-level scopes (`"compass-cli"`, `"SPEC-002-tile"`) and `".."`-rejection.
Confidence: high (verified by live command execution against the real repo, non-destructive).

### Finding 9: `compass promote` has no type restriction - it already works on non-spec artifacts

`promote.py`'s `_resolve` (`plugin/cli/commands/promote.py:25-33`) calls `vaultlib.discover_type_dirs(vault_root)` and searches EVERY type dir for `<target>.md` - specs, research, decisions, plans, lessons, handoffs, prs alike. There is no `data.get("type")` gate anywhere in `run()`. Verified live: `python .claude/cli/compass promote RESEARCH-rag-fit-for-large-vaults` (dry-run) succeeds and reports `research\RESEARCH-rag-fit-for-large-vaults.md -> research\RESEARCH-rag-fit-for-large-vaults\index.md`.
This directly contradicts `plugin/skills/promote-spec/SKILL.md:35`: "Promoting a non-spec/plan/decision artifact - the CLI refuses; respect it." The skill's documented failure mode does not match current CLI behavior.
Confidence: high (verified by live dry-run command execution).

### Finding 10: `make-unit`'s type-dir check already tolerates nested domain paths

`make_unit.py`'s `_plan_moves` checks `parts[0] not in type_dirs`, where `type_dirs = set(vaultlib.classify_root_dirs(vault_root)["type_dirs"])` - only the FIRST path segment is checked, so an artifact at any nesting depth inside a recognized type dir (including a deep domain/subdomain path) passes this check unchanged.
Confidence: high. Evidence: `plugin/cli/commands/make_unit.py` (`_plan_moves`, lines 119-171 per prior full read).

### Finding 11: `validate.py`'s sizing reconciliation already covers every folder-index at any depth

`_reconcile_sizing` (`plugin/cli/commands/validate.py:115-136`) iterates every unit folder AND every record where `record["kind"] == "folder-index"` - i.e. every domain/folder-spec index.md at any depth - checking for `sizing_unrecorded` / `sizing_orphaned_id`. No new code is needed for domain-folder creation via `promote`/`make-unit` to be covered by this existing reconciliation, since both commands already sizing-log their moves.
Confidence: high. Evidence: `plugin/cli/commands/validate.py:115-136`.

### Finding 12: `vaultgraph` containment edges already compose across arbitrary domain nesting

`build_graph(vault_root)` (`plugin/cli/vaultgraph.py`) generates a `containment` edge from each `index.md` to its own DIRECT children only (`path.parent.iterdir()`). This composes correctly for nested domains because each nested folder's own `index.md` independently generates edges to its own direct children - no global tree-walk is needed.
Confidence: high. Evidence: `plugin/cli/vaultgraph.py` (containment edge generation, full read).

### Finding 13: The consolidate skill's Structure pass already documents domain-folder grouping for research, pre-dating full code support

`plugin/skills/consolidate/SKILL.md:144-168` (Structure pass, S1-S5) already instructs: "research docs fold into a folder named for the domain," "subdomains nest inside domains at any depth," applied via `compass promote --apply`, `compass make-unit --apply`, and plain `git mv`, with `compass validate` run after each domain move. This is the skill layer already anticipating what SPEC-022 D-02/D-04 ask for, even though (per Finding 1/2) the CLI has no distinct code-level concept of "domain folder" versus "folder spec" - the skill's design already treats them as unified via existing commands.
Confidence: high. Evidence: `plugin/skills/consolidate/SKILL.md:144-168`.

### Finding 14: The obsidian skill is the authoritative "where a new artifact goes" contract; the spec skill assumes manual index update

`plugin/skills/spec/SKILL.md` step 5 routes new specs via "the `obsidian` skill's 'Where a new artifact goes' rule" and creates `specs/SPEC-NNN-name/index.md` per that rule; step 6 explicitly instructs "Edit `.compass/index.md`, add the new spec... A spec not in `index.md` is invisible to the next session" - this is a MANUAL step in the skill's own protocol, not solely reliant on the sync hook. SPEC-022's D-04 ("taxonomize applies at spec creation too... mark a taxonomy_hint") would need to be threaded into this exact step.
Confidence: high. Evidence: `plugin/skills/spec/SKILL.md:65,89-91`.

### Finding 15: The vision skill's "Spec Roadmap" section pre-lists specs before they exist, with no domain-hint field

`plugin/skills/vision/SKILL.md:99-103` template lists proposed specs as flat `[[SPEC-NNN-name]] - [one-line problem] - status: not yet created` with no domain/taxonomy field. If D-04's `taxonomy_hint` mechanism is meant to originate as early as vision capture, this template has no slot for it today.
Confidence: high. Evidence: `plugin/skills/vision/SKILL.md:99-107`.

### Finding 16: methodology and setup skills both document research/plans/decisions/lessons/handoffs/prs as "flat, one file each" - a documentation claim SPEC-022 D-02 directly contradicts

`plugin/skills/methodology/SKILL.md:269`: `research/ plans/ decisions/ lessons/ handoffs/ prs/ - flat, one file each`. This is a Claude-facing statement of the vault-tree contract. SPEC-022 D-02 explicitly extends the domain-folder taxonomy to "specs, research, anything else inside Compass" - meaning this documented contract would no longer hold for `research/` (and potentially others) once domain grouping is adopted there.
`plugin/skills/setup/SKILL.md:232-251` (new-project scaffold) shows a flat directory tree for `.compass/` with `research/`, `plans/`, `decisions/`, `lessons/`, `handoffs/`, `prs/` as plain directories (no nested example) - consistent with, but not as explicit as, methodology's "flat, one file each" line. Neither skill currently shows a nested-domain example under `research/` the way the obsidian skill does for `specs/`.
Confidence: high. Evidence: `plugin/skills/methodology/SKILL.md:269`; `plugin/skills/setup/SKILL.md:232-251`.

### Finding 17: SPEC-005 (revived by D-05) specified machine-only, cost-bounded per-folder index generation - and was held specifically on unproven LLM cost, not on design disagreement

`.compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md` (status: draft, on hold since 2026-06-19) decided: fully-regenerated (not append-only) per-folder `index.md`; automatic invisible summaries via a detached `claude -p` (haiku) subprocess with content-hash caching and a hard call budget; backfill-on-update; root index depth-capped (<=2 levels / <=3 steps). The hold reason, per `.compass/handoffs/2026-06-19_10-33-39_cli-shipped-spec005-on-hold.md`: the haiku-summary prototype worked (10-30s latency, ~$0.005/page) but "an ADR/build must enforce and a real-session measurement should confirm" the cost stays bounded - that measurement never happened. SPEC-022 D-05 revives this exact spec ("Each folder should have its own index.md!") without addressing the original hold condition.
Confidence: high. Evidence: `.compass/specs/SPEC-005-index-auto-maintained-and-mirrored-per-folder.md` (full read); `.compass/handoffs/2026-06-19_10-33-39_cli-shipped-spec005-on-hold.md` (full read).

### Finding 18: ADR-021 already shipped D-01/D-03's root-index depth-0 rule and constrained grouping to existing commands only

`.compass/decisions/ADR-021-index-speaks-in-domains.md` (already shipped) already decided: root index lists depth-0 entries only (D-01, implemented in `sync.py:187-190` per Finding 4); migration is a human-approved diff proposal, never automatic (D-03); grouping moves use ONLY existing commands - promote, make-unit, plain `git mv`, all sizing-logged - with explicitly "no new migration machinery" (D-04 of the ADR, distinct numbering from SPEC-022's own D-04). SPEC-022 builds directly on top of this already-shipped decision rather than starting fresh.
Confidence: high. Evidence: `.compass/decisions/ADR-021-index-speaks-in-domains.md` (full read).

### Finding 19: Graph impact edges for the four specs at the center of this change

Run: `python .claude/cli/compass graph impact <name>` (read-only, non-destructive) for each:
- **SPEC-003-hierarchical-vault-organization**: inbound edges from ADR-004, RESEARCH-rag-fit-for-large-vaults, and (depends_on/wikilink) SPEC-005, SPEC-010, SPEC-016, SPEC-019, SPEC-022.
- **SPEC-005-index-auto-maintained-and-mirrored-per-folder**: inbound edges from ADR-008, the on-hold handoff (`2026-06-19_10-33-39_cli-shipped-spec005-on-hold`), several RESEARCH-* docs, SPEC-001, SPEC-010, SPEC-022.
- **SPEC-010-universal-hybrid-hierarchy**: inbound edges from `backlog.md`, ADR-006, ADR-021, PLAN-003, RESEARCH-hybrid-hierarchy-impl, SPEC-001, SPEC-016, SPEC-022.
- **SPEC-022-vault-organized-per-domain**: inbound edges from ADR-021 (both depends_on and wikilink) and SPEC-001 (wikilink).
Confidence: high (direct command output, this session).

### Contradictions

- Finding 9 (verified: `compass promote` has no type gate, works on research docs today) directly contradicts the documented claim in `plugin/skills/promote-spec/SKILL.md:35` ("Promoting a non-spec/plan/decision artifact - the CLI refuses").
- Finding 16 (methodology/setup skills document `research/` etc. as flat) contradicts SPEC-022 D-02's mandate that domain grouping applies to "specs, research, anything else."

### Gaps

- No test exercises `_is_generated_output` against a nested (non-root) `index.md` path (Finding 5) - actual runtime consequence of the loop-guard's over-broad match for D-05's per-folder writes is unverified beyond the unit-test-level string check performed here.
- No same-name collision across type dirs (Finding 7) has been reproduced in this vault; risk is code-traced only.
- SPEC-005's original hold condition (bounded LLM cost proven via real-session measurement) remains unmet; Finding 17 documents the gap, does not close it.
