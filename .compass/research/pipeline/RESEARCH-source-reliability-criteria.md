---
title: "How Source Reliability Is Judged, and How to Check It Mechanically"
type: research
status: draft
confidence: high
area: methodology
tags: [research, sources, reliability, curation, methodology, pipeline]
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
created: 2026-09-13
updated: 2026-09-13
git_branch: "master"
git_commit: "50a2896"
author: "researcher"
summary: "library-science source evaluation frameworks, venue-quality signals, GitHub and blog vetting, and how four open-source research agents implement source filtering in code"
---

# How Source Reliability Is Judged, and How to Check It Mechanically

## Question

[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-03 requires research to draw from curated sources whose reliability was checked, never an uncurated pile of blogs, while admitting a specialist's blog. This research asks: what frameworks exist for judging source reliability, and what would let an agent check reliability mechanically and record the check, rather than judging by feel?

## Scope

Covered: library-science evaluation frameworks (CRAAP, SIFT, lateral reading), peer-review and venue-quality signals for papers, preprint caveats, GitHub repository and owner vetting, blog-author specialist criteria, and what four open-source research agents (GPT-Researcher, STORM, Open Deep Research, Perplexica) implement as source filtering, read from their cloned source. Excluded: ACM Digital Library has no public API and no open-source agent surveyed integrates it directly (see Gaps).

## Methodology

Scoping review (Arksey and O'Malley) - the question is broad and exploratory ("what is the extent and nature of source-reliability practice"), spanning library science, bibliometrics, and software engineering. Web search against library guides and primary sources for the frameworks; `git clone` of four agent repos into the scratchpad per D-04, then `grep`/`Read` of the actual filtering code rather than each project's README.

## Findings

### Library-science frameworks

1. **CRAAP test** (confidence: high)
   Five-question checklist - Currency, Relevance, Authority, Accuracy, Purpose - developed by Sarah Blakeslee's team at CSU Chico (Blakeslee, "The CRAAP Test," *LOEX Quarterly* 31(3), 2004). Designed for vertical reading: examine the page you're on. It is checklist-shaped, so it mechanizes into a rubric an agent can walk (author named? affiliation stated? date present? claims cited?) but every question still resolves by human or LLM judgment, not a lookup.
   - [CSU Chico Meriam Library PDF](https://library.csuchico.edu/sites/default/files/craap-test.pdf)
   - Caveat: several library guides now present CRAAP as the older method, superseded for web content by lateral-reading approaches (below).

2. **SIFT / lateral reading** (confidence: high)
   Mike Caulfield's four moves: Stop; Investigate the source; Find better coverage; Trace claims to the original context. Supersedes his earlier "Four Moves and a Habit." Core mechanism is lateral reading - leave the source, open other tabs, and check what independent sources say about the source itself, rather than evaluating it in isolation (vertical reading). Licensed CC BY 4.0.
   - [Caulfield, "SIFT (The Four Moves)," Hapgood, 2019-06-19](https://hapgood.us/2019/06/19/sift-the-four-moves/)
   - Directly applicable to an agent: "find better coverage" and "trace to original context" both map to a WebSearch-then-corroborate step already available as a tool.

3. **Stanford History Education Group: lateral reading is what fact-checkers do, not what novices do** (confidence: high)
   Wineburg and McGrew's foundational study (Working Paper 2017-A1, SSRN) found professional fact-checkers read laterally while Stanford undergraduates and even professors read vertically (stayed on the page). A 2019 follow-up with 3,446 high-school students found 52% treated a low-quality video as "strong evidence," two-thirds could not distinguish sponsored content from news, and 96% did not weigh a website's funding ties when judging credibility.
   - [Wineburg & McGrew, Teachers College Record 121 (2019)](https://misinforeview.hks.harvard.edu/article/lateral-reading-college-students-learn-to-critically-evaluate-internet-sources-in-an-online-course/)
   - Implication for Compass: an agent defaulting to "read the page and judge it" reproduces the novice failure mode this research documents; the corrective (lateral reading) is a WebSearch call away, not additional reasoning depth.

### Venue and peer-review quality signals

4. **CORE conference rankings (A*/A/B/C) are conference-only** (confidence: high)
   CORE (now ICORE) ranks computing conferences A* (flagship) through C (meets basic peer-review standards) using citation rates, acceptance rates, and program-committee track record. CORE's journal rankings were discontinued in 2022 for lack of resources - there is no current CORE journal list to check against.
   - [portal.core.edu.au/conf-ranks](https://portal.core.edu.au/conf-ranks/)

5. **Scimago Journal Rank (SJR) quartiles are a quality signal, not an allowlist** (confidence: medium)
   SJR buckets journals into quartiles (Q1-Q4) from Scopus data. Indexing in Scopus/SJR is commonly used as a safelist proxy for avoiding predatory venues, but multiple sources caution Scopus is not a whitelist: predatory journals have been indexed, and legitimate ones delisted. Scimago does not itself vet for predation - Scopus's advisory board does the inclusion, and quartile position measures citation impact, not editorial integrity.
   - [ResearchGate discussion: Beall's list vs. SJR contradiction](https://www.researchgate.net/post/Is_there_a_contradiction_between_Bealls_List_and_SCImago_Journal_Country_Rank)

6. **Beall's List is defunct; Cabells Predatory Reports is its subscription successor** (confidence: medium)
   Beall's list (blacklist of ~1,289 journals / 1,162 publishers) is no longer maintained ("RIP" editorial, 2017) though archived copies circulate. Cabells now sells "Predatory Reports" with graded criteria, but its methodology is itself contested in the literature (2023 *Journal of Academic Librarianship* critique of Cabells' criteria). A cross-sectional study found overlap and outright contradictions between blacklists and whitelists - one publisher appeared in both Cabells' blacklist and whitelist simultaneously.
   - [Beall's List of Predatory Open-Access Journals: RIP](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5340161/)
   - [Strinzel et al., "Blacklists and Whitelists to Tackle Predatory Publishing," erratum](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8545100/)
   - Gap/caveat: no single list is authoritative; the field's own literature says treat any one list as a signal, not a verdict.

7. **Preprints carry an explicit no-peer-review disclaimer at the source** (confidence: high)
   bioRxiv stamps every PDF and posts a banner stating content is not peer-reviewed, may contain errors, and carries no endorsement from bioRxiv or the scientific community. A study of COVID-19 preprint citations in BMJ/Lancet/JAMA/NEJM found title, data, or conclusion differed between the preprint and its eventual published version in nearly half of cases, and over a quarter of citing papers cited a preprint that had, by then, already been superseded by a peer-reviewed version.
   - [bioRxiv FAQ](https://www.biorxiv.org/about/FAQ)
   - [Reliability of medRxiv preprint citations, PMC9365132](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9365132/)
   - Practical rule the literature converges on: mark a preprint citation explicitly as `[Preprint]` with its version/date, and check whether a peer-reviewed version has since superseded it before citing.

### GitHub repository and owner vetting

8. **Star count is a weak, gameable signal** (confidence: high)
   A Carnegie Mellon study presented at ICSE 2026 found ~6 million fake stars across 18,617 repositories from ~301,000 accounts; AI/LLM repos were the largest non-malicious recipient category. Stars measure past popularity, not current health - a 40k-star repo with one active maintainer is more fragile than a 2k-star repo with thirty.
   - [How to Spot Fake GitHub Stars, DEV Community](https://dev.to/alanwest/how-to-spot-fake-github-stars-before-they-burn-you-28op)

9. **The signals that do carry weight: maintainer concentration, commit/release cadence, issue responsiveness, org domain verification** (confidence: medium)
   Consensus checklist across sources: recent commits, regular releases, multiple active contributors ("bus factor" - does it survive if one maintainer leaves), and timely issue responses. GitHub's own domain-verification mechanism ties an org's "Verified" badge to a matching website/email domain, giving a mechanical check that a repo under a company name is actually that company's. OpenSSF Scorecard computes a score from branch protection, code review presence, CI/CD, and dependency pinning, but its authors note it does not assess whether maintainers are known entities with a track record - that check stays human.
   - [OpenSSF Scorecard checks](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
   - [GitHub org domain verification](https://docs.github.com/en/organizations/managing-organization-settings/verifying-or-approving-a-domain-for-your-organization)
   - Directly checkable via `gh api repos/{owner}/{repo}` (contributor count, last push, open/closed issue ratio) and `gh api orgs/{org}` (verified domain) without any external tool.

### Blog-author specialist criteria

10. **Authority = credentials + affiliation + a checkable publication record** (confidence: high)
    Library guides converge on three checks for a blog author: stated credentials/education/work experience in the field; affiliation with a "distinguished organization or university" (the organization's own reputation transfers, for good or ill - Johns Hopkins's guide flags checking whether the domain belongs to a party with a stake in the topic); and a publication record findable by searching the author's name in a database or general search engine. A Bryant University library chapter applies CRAAP specifically to blogs, cautioning that blog authors "may not be who they say they are" - identity itself needs a lateral check, not just credential claims taken at face value.
    - [Murray State University Library guide](https://lib.murraystate.edu/libSOC359POL359/evaluate)
    - Mechanical proxy an agent can run: search `"<author name>" <topic>` and check for independent citation, prior first-party writing, or conference talks - the same lateral-reading move as finding #2, applied to a person instead of a page.

### How open-source research agents implement source filtering (read from cloned code, D-04)

11. **GPT-Researcher: LLM judgment for general curation, but mechanical for two other layers** (confidence: high)
    `SourceCurator.curate_sources` (`gpt_researcher/skills/curator.py:35-111`) sends every scraped source to an LLM with a prompt (`gpt_researcher/prompts.py:318-350`) instructing it to favor "authoritative sources" and retain others "unless clearly untrustworthy" - reliability judgment is entirely delegated to the model, with no mechanical scoring. Two mechanical layers sit outside that LLM step:
    - A user-supplied denylist: `filter_urls` (`gpt_researcher/actions/web_scraping.py:52-70`) drops any URL containing a substring from `config.excluded_domains` - opt-out only, no default list shipped.
    - Dedicated first-party retrievers for scholarly venues instead of generic web search: `gpt_researcher/retrievers/{arxiv,semantic_scholar,pubmed_central,openalex}/` - reliability here is enforced by routing to a specific venue's API, not by scoring results after the fact.
    - The Semantic Scholar retriever (`gpt_researcher/retrievers/semantic_scholar/semantic_scholar.py:61-63`) silently drops every paper that is not open access with a direct PDF link - an accessibility filter that functions as a reliability filter (no result without an inspectable full text), undocumented outside the code.

12. **STORM: a pluggable `is_valid_source` predicate, with Wikipedia's own reliability taxonomy as one concrete instance** (confidence: high)
    Every retriever's `forward()` (e.g. `knowledge_storm/rm.py:67`, `:713`, `:841`) filters results through `self.is_valid_source(url)`, a callback injected at construction and defaulting to `lambda x: True` (`knowledge_storm/rm.py:14,27-30`) - reliability filtering is an architectural seam, not baked into the retriever.
    - The wiki-generation pipeline supplies a concrete predicate, `is_valid_wikipedia_source` (`knowledge_storm/storm_wiki/modules/retriever.py:225-233`), which checks the result's netloc substring against three sets copied from Wikipedia's own "Reliable sources/Perennial sources" list: `GENERALLY_UNRELIABLE`, `DEPRECATED`, `BLACKLISTED` (`retriever.py:11-222`).
    - Caveat load-bearing for Compass: this list is Wikipedia's *encyclopedic* policy, which excludes arXiv, bioRxiv, SSRN, and ResearchGate as "generally unreliable" (`retriever.py:21,97-98,102,110`) - not because the underlying work is untrustworthy, but because Wikipedia requires secondary, independently-published sources and treats preprints/repositories as primary. Reusing this list verbatim would blacklist exactly the sources [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-03 names as trusted (arXiv, GitHub). The list is a real, working reliability taxonomy, but its exclusions are tuned for an encyclopedia's sourcing policy, not for technical research.

13. **Open Deep Research: mutually-exclusive include/exclude domain lists as a first-class search parameter** (confidence: high)
    The Exa-backed search function accepts `include_domains` and `exclude_domains` and raises `ValueError` if both are set (`src/legacy/utils.py:410-412`), then forwards whichever is set straight to the Exa API (`utils.py:436-439`) - an allowlist and a denylist are treated as the same mechanism, chosen per call, never combined. Academic sourcing is handled the same way GPT-Researcher does it: a dedicated `arxiv_search_async` using LangChain's `ArxivRetriever` (`utils.py:577-728`) rather than generic web search filtered after the fact, including a hard-coded delay to respect arXiv's documented rate limit.

14. **Perplexica: an upstream LLM classifier decides whether to route to a fixed, curated engine list** (confidence: high)
    `academicSearchAction` (`src/lib/agents/search/researcher/actions/search/academicSearch.ts:22-60`) is only `enabled` when a prior classification step sets `classification.academicSearch === true` (`academicSearch.ts:28-31`) - an LLM decides *whether* the query needs scholarly sourcing before any search runs. Once enabled, the engine list is hard-coded and curated by the maintainers, not learned or user-editable at call time: `engines: ['arxiv', 'google scholar', 'pubmed']` (`academicSearch.ts:51`), executed through a shared SearXNG-backed `executeSearch` helper.

15. **Compass's own `papers` skill has no reliability filter today** (confidence: high)
    `plugin/skills/papers/SKILL.md` fetches whatever Hugging Face's paper-pages API or arXiv returns, with no curation, corroboration, or peer-review check anywhere in its documented flow. It is closer in shape to GPT-Researcher's plain arXiv retriever (a venue-routing filter, since HF/arXiv content is at least self-selected as "a paper") than to STORM's or Perplexica's explicit reliability gate - there is no analogue in Compass today to STORM's `is_valid_source` seam or Perplexica's classify-then-route step.
    - `plugin/skills/papers/SKILL.md:12,26-84`

### Cross-cutting pattern across all four agents

16. **No agent scores reliability with a single number; every implementation is either an LLM prompt, a venue-routing choice, or a domain list - never all three combined** (confidence: medium)
    GPT-Researcher: prompt-only for general sources, list-only for exclusions, routing-only for scholarly APIs. STORM: list-only, injectable. Open Deep Research: list-only (mutually exclusive with itself), routing-only for arXiv. Perplexica: classifier decides binary routing to a fixed list, no per-source scoring at all. None of the four computes a continuous "reliability score"; all reduce to a binary admit/reject at either the domain level or the venue-routing level, with LLM judgment reserved for content quality within an already-admitted source.

## Taxonomy

Three independent axes recur across both the library-science material and the agent code, and an agent could check each mechanically:

| Axis | Mechanical check available | Source |
|---|---|---|
| **Venue-routing** (is this the right kind of source for the question) | Route scholarly questions to arXiv / Semantic Scholar / PubMed retrievers instead of generic web search | Findings 11, 13, 14 |
| **Domain admit/deny** (is this specific domain trusted) | Curated allowlist or denylist checked against the result's netloc | Findings 6, 12, 13 |
| **Owner/author check** (is the entity behind the content credible) | `gh api` for repo/org signals (finding 9); name search + affiliation + publication-record check for a blog author (finding 10); lateral read for any page (findings 2-3) | Findings 8, 9, 10 |

Preprint status (finding 7) cuts across all three - a preprint can pass venue-routing (it's on arXiv, the right venue for a technical paper) and domain admission (arXiv is trusted), yet still needs a recorded caveat that it is not peer-reviewed.

## Contradictions

- STORM's `is_valid_wikipedia_source` (finding 12) blacklists arXiv, bioRxiv, and ResearchGate; SPEC-023 D-03 and GPT-Researcher's own retriever roster (finding 11) both treat arXiv as a first-tier trusted source. Not a factual disagreement - Wikipedia's policy optimizes for tertiary-source encyclopedic sourcing, Compass's need is primary technical evidence - but it means the most complete off-the-shelf domain list found in this research is unusable for Compass without being filtered down to its general web-junk entries (tabloids, fan wikis, social media) and stripped of its academic exclusions.
- SJR/Scopus indexing is cited by some guides as a de facto safelist and by others as explicitly not a whitelist (finding 5). Both are in the current literature; treat SJR quartile as a corroborating signal, never a sole gate.

## Gaps

- **ACM Digital Library has no public API and no code precedent.** None of the four surveyed agents integrate ACM DL directly (it is paywalled); the only mechanical proxy found is venue-prestige rankings (CORE for conferences, finding 4) applied to a paper's publication venue rather than the DL itself. A further pass fetching ACM's own author/venue metadata format (if reachable without a subscription) would close this.
- **No usable general-purpose domain allowlist/denylist was found ready to embed.** STORM's list (finding 12) is the only complete one in the wild and is wrong-shaped for Compass's needs (see Contradictions). Building Compass's own curated list is `.compass/specs/pipeline/SPEC-023...` D-03's "researched a bit more" step and was out of this pass's scope - it is a planning decision, not a research finding.
- **No source in this pass addresses how to mechanically verify a blog author's claimed affiliation** (e.g., cross-checking a claimed employer) beyond "search their name" - the library guides recommend it but none describe a verifiable procedure beyond manual lateral reading.
