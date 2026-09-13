---
title: "Research Source Inventory: What Compass Could Embed Beyond ACM DL and arXiv"
type: research
status: draft
confidence: medium
area: methodology
tags: [research, sources, pipeline, methodology, bibliographic-apis, code-hosts, shadow-libraries]
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
created: 2026-09-13
updated: 2026-09-13
git_branch: "master"
git_commit: "50a2896"
author: "researcher"
summary: "profiles 34 research and code sources beyond ACM DL and arXiv - coverage, access mechanics, cost, terms of use, and reliability, each tested live where unauthenticated access exists - for the human to choose Compass's shipped starting list (SPEC-023 D-03, D-07)"
---

# Research Source Inventory: What Compass Could Embed Beyond ACM DL and arXiv

Serves [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-03 (curated source list, checked reliability) and D-07 (use plugins already present in the session). Reliability *criteria* (CRAAP, SIFT, venue rankings, how open-source agents filter sources) are covered by [[research/pipeline/RESEARCH-source-reliability-criteria]] and are not restated here. Locating and reading canonical source code for a given library version is covered by [[research/pipeline/RESEARCH-code-as-primary-source]]; this document instead profiles the source *services* themselves - what they hold, how an agent reaches them, and under what terms.

## Question

Beyond ACM Digital Library and arXiv, which research and code sources exist that Compass could embed as a curated starting list, and for each: what does it cover, how does an agent reach it (API, key, rate limit, scraping-only), what does it cost, what do its own terms say about automated access and redistribution, and how reliable is it - tested live wherever no key is required?

## Scope

In: bibliographic/metadata aggregators, paywalled publisher indexes, preprint and open-access archives, ML-specific paper/model hubs, code hosts and package registries, and shadow libraries (documented factually, no recommendation on use). Also in: what this session can already reach without any new integration (the `papers` skill, WebSearch/WebFetch, Serena, and any code-search tooling). Out: ACM DL and arXiv (already known to Compass, named directly in D-03), reliability-scoring methodology (separate research), and choosing which sources to actually ship (a planning decision for the human).

## Methodology

Technology Landscape survey (per-item profiles plus a comparison matrix) - the question evaluates ~34 discrete, comparable options rather than one contested claim. Per D-03/D-04: each service's own API documentation was treated as authoritative only where no client-side code exists to read (pure REST metadata contracts); where an official client library exists on GitHub, it was `git clone`d into the scratchpad and read directly for real endpoint, auth, and rate-limit behavior. Every source with an unauthenticated access path was tested live with a small request; the result (HTTP status, one-line description) is the evidence for that finding rather than a docs claim alone. Four parallel sub-agents each covered one cluster (bibliographic APIs, paywalled publishers, preprints/archives, shadow libraries) plus one for code hosts; findings below consolidate their reports. Clients cloned into `scratchpad/sources/`: `semanticscholar`, `pyalex`, `habanero` (Crossref), `elsapy` (Elsevier), `openreview-py`, `huggingface_hub`, `swh-web-client` (Software Heritage), and `cli/cli` (GitHub CLI, for code-search rate-limit behavior).

## Findings

### What this session already reaches

1. **The `papers` skill already covers Hugging Face paper pages and arXiv** (confidence: high)
   `plugin/skills/papers/SKILL.md:1-148` fetches paper markdown and structured metadata from `huggingface.co/papers/{id}.md` and `/api/papers/{id}`, plus arXiv-linked models/datasets/spaces and a papers search endpoint - all unauthenticated. Tested live in this session: `curl https://huggingface.co/api/papers/search?q=transformer&limit=1` -> HTTP 200; `curl https://huggingface.co/api/models?search=bert&limit=1` -> HTTP 200. It has no source-reliability filter of its own (see [[research/pipeline/RESEARCH-source-reliability-criteria]] finding 15).
   - `plugin/skills/papers/SKILL.md`

2. **No zoekt or dedicated code-search skill/MCP exists in this repository** (confidence: high)
   `Grep`/`Glob` for "zoekt" and "code search" across `plugin/` and `.claude/` returned zero matches; no `.mcp.json` at the project level references any code-search server. Whatever "zoekt code-search skills" a session has access to is host-provided, not shipped by Compass - Compass's own code-reading capability today is `Read`/`Grep`/`Glob`/`Bash git clone`, documented in [[research/pipeline/RESEARCH-code-as-primary-source]].

3. **Serena is configured at the session/MCP level, not tested in this pass** (confidence: low)
   A system-level instruction in this session references a `serena` MCP server with an `initial_instructions` tool, but that tool was not present in this research role's own tool list, so its behavior could not be independently verified here. Per general knowledge (not tested), Serena provides LSP-backed semantic code navigation for a local checkout, which is complementary to but distinct from external literature/source fetching - it would help *read* a cloned library, not discover new sources.

4. **WebSearch and WebFetch are the baseline reach for everything without a dedicated API** (confidence: high)
   Every source below without a documented API (Google Scholar, ResearchGate, university repositories individually) was profiled using only WebSearch/WebFetch - the same tools any Compass session already has, subject to the scraping/terms-of-use constraints each finding documents.

### Bibliographic metadata aggregators

5. **Semantic Scholar Graph API: huge free corpus, routinely throttled without a key** (confidence: high)
   ~214M papers, 79M authors, 2.49B citations across all fields; metadata/abstracts/TLDRs, full text only via linked open-access PDFs. Public REST API, JSON, no key required but an unauthenticated 429 is the documented normal case - the official community client `semanticscholar`'s `ApiRequester` retries on 429 with exponential backoff up to 10 attempts. A free key raises the floor to a guaranteed 1 req/sec. Tested live: `curl .../graph/v1/paper/search?query=...` -> HTTP 429 "apply for a key for higher rate limits." Gusenbauer & Haddaway (2020, doi:10.1002/jrsm.1378) group Semantic Scholar (with the now-defunct Microsoft Academic) as lacking field-code/Boolean structured search, weakening its use as a *sole* systematic-review search system.
   - `scratchpad/sources/semanticscholar/semanticscholar/ApiRequester.py`; tested as above; https://www.semanticscholar.org/product/api

6. **OpenAlex: largest fully open metadata graph, pricing model changed mid-2026, keyless access still works** (confidence: medium - two official-adjacent sources disagree)
   326,222,276 works (live count, tested), CC0 data, "1400 to 2024+" coverage, successor to Microsoft Academic Graph. `pyalex`'s own README states a key became "required" February 13, 2026; the official help.openalex.org page (updated August 11, 2026) instead describes a credit-metered model - free accounts get $1/day of usage, keyless calls are allowed but budget-limited, with paid tiers from $5,000/yr. Tested live with no key: `curl https://api.openalex.org/works?per-page=1` -> HTTP 200, response included a `cost_usd` field confirming the metering is live even unauthenticated. Hard ceiling 429 above 100 req/sec regardless of plan. Culbert et al. (2025, arXiv:2401.16359) found OpenAlex reference-coverage broadly comparable to Web of Science/Scopus on a 16.8M-publication sample but flag "volatility and data quality issues" for scientometric use.
   - `scratchpad/sources/pyalex/pyalex/api.py:47-53,207-219,395-411`; `pyalex/README.md` "Rate limits and authentication [Changed!]"; tested as above; https://help.openalex.org/access/pricing/

7. **CORE: largest full-text OA aggregator, documented key requirement doesn't match tested behavior** (confidence: medium-high)
   >400M scholarly resources per CORE's own 2023 Scientific Data paper (Knowles et al., doi in Nature Scientific Data); aggregates full text + metadata from repositories and OA/hybrid journals worldwide, framed as text-and-data-mining infrastructure. CORE's own FAQ says register for an API key; tested live with none supplied: `curl "https://api.core.ac.uk/v3/search/works/?q=...&limit=2"` -> HTTP 200 with real results (67M `totalHits` for one query) - a directly observed gap between stated policy and tested behavior for light use. Free tier is otherwise rate-limited to "one batch or five single requests per 10 seconds" without registration; explicitly prohibits bulk-scraping PDFs via the raw fileserver URL ("such usage will be blocked and associated API keys disabled").
   - tested as above; https://core.ac.uk/services/api; Knowles et al. 2023

8. **Crossref: free DOI-registration metadata for ~180M records, no key needed** (confidence: high)
   Journal articles, books, conference proceedings, datasets, dissertations, grants, preprints, reports, standards - metadata only, no full text, no code index. Fully public REST API; the community `habanero` client (`crossref.py:186-201`) confirms base URL, optional `api_key` for the paid Metadata Plus tier, and a `mailto` param for the "polite pool" (higher, prioritized limits communicated dynamically via `x-rate-limit-*` response headers rather than a fixed published number, changed December 2025 for the first time since 2013). Tested live: `curl "https://api.crossref.org/works?query.bibliographic=...&mailto=..."` -> HTTP 200, 1,235,794 total results. Crossref states "almost none of the metadata is subject to copyright"; some abstracts may carry publisher/author copyright.
   - `scratchpad/sources/habanero/habanero/crossref/crossref.py:15-81,186-201`; tested as above; https://www.crossref.org/blog/announcing-changes-to-rest-api-rate-limits/

9. **Unpaywall: free OA-location layer on top of Crossref DOIs, no key** (confidence: high for access; low for terms-of-use text)
   OA-status/full-text-location metadata for >120M DOIs; not a general index, a DOI-keyed layer returning direct OA PDF links. Auth is just an `email=` query parameter, no key. Suggested (not enforced) ceiling of 100,000 calls/day; bulk users are pointed to a full database snapshot instead of high-volume calls. Tested live: `curl "https://api.unpaywall.org/v2/10.1038/nature12373?email=..."` -> HTTP 200 with real OA-location JSON. The Terms of Service page is JavaScript-rendered and could not be read by an automated fetch in this pass - a genuine gap, not an inferred "no restrictions."
   - tested as above; https://unpaywall.org/products/api

10. **DBLP: free CS-only bibliography, currently gated by a bot-challenge from this network** (confidence: medium)
    Computer-science-only, 8M+ publications (July 2025 milestone), metadata only, CC0-licensed, three official public search endpoints (`/search/{publ,author,venue}/api`), no key, bulk XML dumps also available. Tested live: both a plain and a browser-User-Agent request to `/search/publ/api?...&format=json` returned HTTP 200 but the body was an Anubis-style proof-of-work bot-challenge page, not JSON - inconclusive rather than a clean pass or fail, and possibly network/IP-specific rather than a universal property of the API.
    - tested as above; https://dblp.org/faq/How+to+use+the+dblp+search+API.html

11. **Internet Archive Scholar / Fatcat: large full-text index, live reachability unresolved in this pass** (confidence: low-medium)
    Homepage advertises 85,899,891 full-text-searchable items (grown from ~25M at 2020 launch), aggregating Crossref, PubMed, arXiv, JSTOR, ORCID, DOAJ, CORE, Unpaywall, Semantic Scholar, CiteSeerX metadata via the open Fatcat catalog. Historically had a documented REST+OpenAPI backend (`guide.fatcat.wiki`), no key required for reads, AGPLv3-licensed server. Community reporting describes the project in a reduced-maintenance/transition state (funding lost, development moved to a newer, "source available" but unsupported successor repo). Tested live: `fatcat.wiki` connection timed out (inconclusive - may be this network); `scholar.archive.org/search` returned HTTP 200 but served a bot-verification interstitial, not results.
    - tested as above; https://github.com/internetarchive/scholar

12. **CiteSeerX: effectively down as a live API as of this test** (confidence: high for current unavailability)
    Historically a CS-literature metadata + cached-PDF index (~6M papers per one secondary citation, currency unverified) reachable via OAI-PMH at `citeseerx.ist.psu.edu/oai2`. Tested live: `curl http://citeseerx.ist.psu.edu/oai2?verb=Identify` -> HTTP 301, permanently redirecting to a December 2025 Wayback Machine snapshot; following that redirect returns HTTP 404. The site root and its data-download page both similarly redirect to Wayback snapshots. This is direct, unambiguous evidence CiteSeerX's live infrastructure is not currently serving requests and has been superseded by an Internet Archive proxy.
    - tested as above; https://csxstatic.ist.psu.edu/downloads/data.html (via cache)

### Paywalled / institutional publisher indexes

13. **IEEE Xplore: key-gated metadata API, full text requires a sales contract** (confidence: medium, docs-only)
    "More than 6 million documents" (journals, conference proceedings, books, courses, standards) via a metadata/abstract REST API at `ieeexploreapi.ieee.org`, requiring a free-registration API key; a separate Open Access API serves free full text for OA content only, while subscriber full text requires contacting IEEE sales (not self-service). `developer.ieee.org/API_Terms_of_Use2` explicitly bans redistributing content "in a form harvestable by humans or machines" and bans robots/spiders against the site. Tested live with no key: `curl https://ieeexploreapi.ieee.org/api/v1/search/articles?querytext=test` -> HTTP 403 "Developer Inactive."
    - tested as above; developer.ieee.org/API_Terms_of_Use2

14. **SpringerLink / Springer Nature API: key required even for metadata search** (confidence: medium, docs-only)
    Metadata plus Open Access full text are free via a self-service API key at `dev.springernature.com`; text-and-data-mining/full-text access for subscribed content requires an institutional TDM License. Terms ban circumventing rate limits via multiple accounts/keys; abstracts are licensed for personal/non-commercial use, broader reuse needs written permission. Tested live with no key: `curl https://api.springernature.com/metadata/json?q=test` -> HTTP 401 "Authentication failed. API key invalid or missing."
    - tested as above; dev.springernature.com/terms-conditions/, dev.springernature.com/docs/rate-limit-details/rate-limits/

15. **ScienceDirect (Elsevier): official client confirms key-gated API, IP-recognized subscriber access at institutions** (confidence: high for mechanics, code-read)
    ~18-20M articles/chapters across 2,500-4,000+ journals, archive back to 1823; full text requires subscription, abstracts/metadata are public via API key. The official `elsapy` client (cloned) confirms base URL `https://api.elsevier.com/`, auth header `X-ELS-APIKey` plus optional `X-ELS-Insttoken` for institutional full text, and a client-enforced minimum 1-second interval between requests. `ElsSearch` targets `content/search/{index}`, capped at 5,000 non-cursored results. Text-and-data-mining terms require attribution and restrict redistribution to academic non-commercial use; keys deactivate after 6-12 months of inactivity; no published hard numeric rate limit ("reasonable and customary"). Tested live with no key: `curl https://api.elsevier.com/content/search/scopus?query=test` -> HTTP 401 `AUTHENTICATION_ERROR`.
    - `scratchpad/sources/elsapy/elsapy/elsclient.py:22,24-25,93-121`; `elsapy/elssearch.py:19-22,78-86`; tested as above; dev.elsevier.com/tdm_service.html

16. **Scopus (Elsevier): same client and key model as ScienceDirect, larger record count** (confidence: high for mechanics, code-read)
    ~94-100M records (2025-2026 figures), 23,000-29,000 active journals, coverage back to 1788 though cited references are only reliably indexed from 1996 onward. Same `elsapy`/`api.elsevier.com` client and `X-ELS-APIKey` auth as ScienceDirect; academic/non-commercial API use is typically capped around 20,000-50,000 requests per 7 days per Elsevier's published quota documentation (third-party `pybliometrics` docs corroborate the same key/quota model). Tested live with no key: same HTTP 401 `AUTHENTICATION_ERROR` as ScienceDirect (shared endpoint family).
    - `scratchpad/sources/elsapy/elsapy/elssearch.py:19-22`; pybliometrics.readthedocs.io/en/stable/access.html

17. **Google Scholar: largest web-scale index, explicitly no API, robots.txt disallows the path it would need** (confidence: high, tested)
    Widely cited estimate ~389M documents ("the most comprehensive academic search engine," a >50% upward revision of earlier ~171-180M estimates); no stated year range or field taxonomy - it crawls scholarly web pages rather than curating a database. No public API, no developer portal; every commercial "Google Scholar API" (SerpApi and similar) is an unsanctioned scraper wrapping the public search UI. Tested live: `curl -A "Mozilla/5.0" https://scholar.google.com/robots.txt` shows `Disallow: /scholar` and `Disallow: /search` for essentially all user agents; a single unauthenticated `curl https://scholar.google.com/scholar?q=test` nonetheless returned HTTP 200 (one request isn't blocked; robots.txt still states the path is disallowed for crawling, and higher volume draws CAPTCHAs/IP blocks). Google sued the scraping vendor SerpApi in 2025 over anti-scraping circumvention. Gusenbauer & Haddaway (2020, doi:10.1002/jrsm.1378, 2,493 citations as of late 2025) judged Google Scholar (with Microsoft Academic) inadequate as a *principal* systematic-review search system because it cannot run complex Boolean queries and does not return reproducible result sets over time - a verdict later contested as overstated by a 2025/2026 MDPI critique, but still the dominant, most-cited position in the field.
    - tested as above; onlinelibrary.wiley.com/doi/10.1002/jrsm.1378

18. **JSTOR: metadata/text-mining request workflow, full text is subscription/JPASS only** (confidence: medium-high for terms, medium for current mechanics)
    2,800+ journals plus books, covering roughly 1665-2000 for much of its historical humanities/social-science holdings; the self-service "Data for Research" text-mining tool was retired in 2025 (successor "Constellate" also shut down July 2025), leaving bulk/full-text requests on a manual, negotiated, under-documented process. `about.jstor.org/terms/` explicitly prohibits "web scraping, web harvesting, web data extraction" and systematic bulk downloading/redistribution; `robots.txt` (tested) disallows crawlers from most content-serving paths (`/action`, `/api`, `/citation`, `/doi/abs`, `/stable/full`, `/stable/view`). Tested live: `curl https://www.jstor.org/api/` -> HTTP 404 (no public API surface at that path).
    - tested as above; about.jstor.org/terms/; labs.jstor.org/blog/constellate-an-experiment-and-retrospective

19. **Elsevier's TDM-reservation protocol is a machine-readable opt-out signal, not an access mechanism** (confidence: medium)
    Fetching `sciencedirect.com` returns `<meta name="tdm-reservation" content="1">` and a `tdm-policy` link in the page head, implementing the EU DSM Directive Article 4 text-and-data-mining opt-out signal in HTML. This is a legal/technical marker publishers use to assert TDM rights are reserved outside a licensed agreement; it does not itself grant or block API access.
    - tested via WebFetch of sciencedirect.com; https://www.elsevier.com/tdm/tdmrep-policy.json

### Preprint servers and open archives

20. **OpenReview: official API and client exist, this sandbox's IP was bot-challenged** (confidence: medium)
    ML conference peer-review platform; ICLR full open reviews 2017-2025 (28,358 submissions in one dataset), NeurIPS reviews since ~2021 (accepted papers only), TMLR since 2022. Metadata + PDFs + reviews/rebuttals as "notes." Official REST API (`api2.openreview.net`, legacy `api.openreview.net`) and official Python client `openreview-py` (cloned) confirm the URL structure; docs say auth mirrors the readers/writers permission fields but third parties report public conference data is readable without a token. Terms of Use require respecting those permission fields and ban impersonation/circumvention; no blanket ban on automated reads of public data found. Tested live: `curl https://api2.openreview.net/notes?...` -> HTTP 403 `ChallengeRequiredError` from this sandbox's network, with and without a browser User-Agent - bot mitigation tied to IP reputation, not a documented outage.
    - `scratchpad/sources/openreview-py/openreview/api/client.py:52-86`; tested as above; https://docs.openreview.net/getting-started/using-the-api

21. **PubMed / PMC: free, fast, high-volume, but the old full-text locator endpoint is dead** (confidence: high, tested)
    PubMed: >40M biomedical citations, metadata only. PMC: ~7M total full-text articles, of which the PMC Open Access Subset (~3.4M+, CC-licensed) is a strict, smaller subset - "most of PMC is free to read but not Open Access" per NLM's own FAQ. Official E-utilities REST API (esearch/esummary/efetch), JSON or XML, no key required; tested live: both `db=pubmed` and `db=pmc` esearch calls returned HTTP 200. Rate limit 3 req/sec without a key, 10 req/sec with a free NCBI API key. The legacy PMC OA Web Service (`oa.fcgi`, used to locate full-text packages) was retired in August 2026 and now 404s - tested live: `curl ".../pmc/utils/oa/oa.fcgi?id=PMC7619490"` -> HTTP 404; NCBI's replacement is the PMC Cloud Service on AWS, PMC OAI-PMH, or plain efetch.
    - tested as above; NLM KA-05317; ncbiinsights.ncbi.nlm.nih.gov/2026/02/12/pmc-article-dataset-distribution-services/

22. **SSRN: no API, ever, and its terms now reserve AI-training/TDM rights** (confidence: high)
    >1.4M working papers in social sciences/economics/finance/law, full text (PDF) plus abstracts. No public REST API has ever existed (confirmed across multiple independent sources going back to 2016). Elsevier acquired SSRN in May 2016, with documented community controversy over subsequent takedowns of CC-licensed/green-OA papers (later restored). Current Terms of Use state "all rights are reserved, including those for text and data mining, AI training, and similar technologies," except content explicitly marked open access, and reserve Elsevier's right to limit access or adjust usage stats for activity it deems abusive.
    - ssrn.com/index.cfm/en/terms-of-use/

23. **bioRxiv and medRxiv: free API, explicitly endorses machine access, screens but does not peer-review** (confidence: high, tested)
    Life-science and health/medical preprints, operated since March 2025 by openRxiv (nonprofit spun out of Cold Spring Harbor Laboratory); author-chosen license per preprint. Free `api.biorxiv.org` REST API, no key, JSON, paginated 30/page - tested live: `curl "https://api.biorxiv.org/details/biorxiv/2024-01-01/2024-01-02/0"` -> HTTP 200, real records with title/authors/DOI/abstract/license. Bulk full-text TDM access is additionally offered via a dedicated Amazon S3 resource. openRxiv states it provides access "not only to human readers but also to machine analysis" - an explicit TDM endorsement. Every preprint carries the source's own disclaimer that it "has not been certified by peer review" (documented caveat, not this document's opinion).
    - tested as above; biorxiv.org/tdm

24. **Zenodo: general-purpose open repository, no official client, tightening anti-harvesting limits** (confidence: high)
    CERN/OpenAIRE repository for any research output type (papers, data, software), DOI-minting, no discipline restriction. Official REST API at `zenodo.org/api`, no dedicated Zenodo client library - docs recommend generic `requests`/`curl`, or `Sickle` for OAI-PMH. Read endpoints work anonymously; deposits need an OAuth2 token. Documented rate limits: guests 60/min & 2,000/hr, authenticated 100/min & 5,000/hr, with search specifically capped at 30 req/min for both (a November 2025 anti-harvesting policy change) and anonymous search page size capped at 25 results. Bulk/monthly metadata dumps and OAI-PMH are the sanctioned route for large-scale harvesting instead of hammering the search endpoint. Tested live from this sandbox: connection timeout unauthenticated, and HTTP 403 "unusual traffic from your network" with a browser User-Agent - consistent with the documented tightening, though this specific result is network/IP-dependent rather than a documented general outage.
    - developers.zenodo.org; blog.zenodo.org/2025/11/25/2025-11-14-search-api-updates/; tested as above

25. **Papers with Code is dead; its data survives only as a frozen dump** (confidence: high, tested)
    Meta sunsetted the entire site and API on July 24, 2025; the domain now redirects to Hugging Face's "Trending Papers." Tested live: `curl -sIL "https://paperswithcode.com/api/v1/papers/?search=test"` -> HTTP 302 to `huggingface.co/papers/trending` -> HTTP 200. What remains is the frozen `paperswithcode-data` GitHub repo (JSON dumps, last updated September 8, 2025) and community Hugging Face dataset mirrors - no live API surface exists to embed.
    - tested as above; github.com/paperswithcode/paperswithcode-data/issues/116

26. **Hugging Face hub: general (non-paper) search across models/datasets/spaces is free and untested-limit** (confidence: high, code-read + tested)
    Beyond the arxiv-filtered endpoints the `papers` skill already documents, the hub exposes general search across its full model/dataset/space catalog. Tested live with no auth: `curl "https://huggingface.co/api/models?search=bert&limit=1"` -> HTTP 200. The official `huggingface_hub` client (cloned) confirms `HfApi` builds these paths off one endpoint constant and exposes `list_models`/`list_datasets`/`list_spaces`; the client flags only one endpoint (`/whoami-v2`) as "intentionally strict" (429 on abuse) - no blanket published rate limit was found for the public listing/search endpoints. Models/datasets/spaces carry individual per-repo licenses, not one hub-wide license.
    - `scratchpad/sources/huggingface_hub/src/huggingface_hub/hf_api.py:354,712,2290,2347,2406-2408,2435,2636,2905`; tested as above

27. **HAL: free national open archive, corpus size genuinely disputed across sources** (confidence: medium)
    French multidisciplinary national archive (CCSD/CNRS/Inria/INRAE); size estimates range from ~700,000 full-text open-access documents (a 2024 harvesting study, arXiv HALvest) to "more than 4.1 million documents" (a 2022 library citation) - the discrepancy tracks total-records vs. full-text-only counting, not a resolved single figure. Official REST/search API at `api.archives-ouvertes.fr`, tested live: `curl "https://api.archives-ouvertes.fr/search/?q=test&rows=1&wt=json"` -> HTTP 200, 139,892 hits. Also has OAI-PMH and a SWORD deposit API. No key needed for reads; open by design, interoperates with arXiv/PMC/RePEc.
    - tested as above; api.archives-ouvertes.fr/docs

28. **ResearchGate: no API, terms explicitly ban automated access, enforced by bot-challenge** (confidence: high)
    Academic social network of self-uploaded papers/preprints, uncurated (includes non-peer-reviewed uploads), size not independently verified. No official public API exists - none was found in any documentation search. Terms of Service explicitly prohibit "any robot, spider, scraper, data mining tools, data gathering and extraction tools, or other automated means," and separately ban imposing disproportionate load; enforced via Cloudflare bot-challenge/CAPTCHA that ResearchGate's own support states it "cannot manually bypass or remove."
    - researchgate.net/terms-of-service; help.researchgate.net "Security checks on ResearchGate"

29. **University institutional repositories: a category, not a source - OAI-PMH is the interoperable layer, CORE/BASE the practical single front end** (confidence: medium)
    Not one source but ~4,000-8,000+ individually run repositories (OpenDOAR/ROAR-indexed estimate; a 2017 six-catalog study found 4,776 distinct operational OAI-PMH repositories, noting roughly half of listed repositories are non-operational in practice), predominantly DSpace, also EPrints/Fedora. No cross-institution query interface exists; DSpace implements OAI-PMH 2.0 (e.g. MIT DSpace at `dspace.mit.edu/oai/request`). Aggregators like CORE (finding 7) or BASE serve as the practical single-API front end instead of querying each repository individually. Free, OAI-PMH harvesting permitted by design; per-item reuse rights follow the individual repository's or author's chosen license.
    - Knoth et al. 2023 (CORE harvesting scale); general OAI-PMH/DSpace documentation

### Shadow libraries (documented factually; legal position stated as courts/sources describe it, no recommendation)

30. **Sci-Hub: one credible independent coverage study, collection frozen since ~2022, no API** (confidence: high for the 2018 benchmark, medium for current scale)
    Himmelstein et al. 2018 (eLife, doi:10.7554/eLife.32822, peer-reviewed) found Sci-Hub held 68.9% of 81.6M Crossref-registered articles and 85.1% of toll-access-journal articles as of March 2017. Sci-Hub's own counter showed 88,343,822 documents in July 2022 and multiple 2025 sources still cite "88 million," indicating the collection has been effectively static since roughly 2022 (tied to Elbakyan's statement in Indian litigation that no further copyrighted uploads would be added while the case is pending). Access is browser-only via rotating mirror domains; no documented API - third-party scripts scrape `https://<domain>/<DOI>` HTML for a PDF link. No verified current Tor v3 onion address was found (the old v2 address stopped resolving after October 2021).
    - eLife 32822; pubmed.ncbi.nlm.nih.gov/29424689/; en.wikipedia.org/wiki/Sci-Hub

31. **Sci-Hub legal position: US civil judgments unpaid, EU country-level site-blocking under Article 8(3), no Brazil-specific ruling found** (confidence: high for US/EU facts, low for Brazil)
    US: Elsevier Inc. v. Sci-Hub (SDNY, 2017) - $15M default judgment plus permanent injunction; American Chemical Society v. Sci-Hub (E.D. Va., 2017) - $4.8M default judgment plus injunction recommending ISP/registry blocking; neither judgment (~$20M combined) has been paid, and the US has not applied domestic ISP-level blocking against Sci-Hub. EU: no CJEU ruling specific to Sci-Hub was found, but individual member-state blocking orders exist under Article 8(3) InfoSoc Directive - Sweden (2018, Bahnhof ordered to block 20 domains), France (2019, Paris High Court ordered four major ISPs to DNS-block 57 Sci-Hub/LibGen domains). India (not EU): Delhi High Court ordered a nationwide block in August 2025. Brazil: no Brazil-specific court ruling or Anatel block naming Sci-Hub was found in this pass; only general Lei 9.610/98 statutory context exists - flagged as a gap requiring a targeted Brazilian case-database search, not general web search, to resolve.
    - editage.com summary; chemistryworld.com; techcrunch.com (Sweden); slashdot/TorrentFreak (France); spicyip.com (India, Aug 2025)

32. **LibGen: no single coverage benchmark, 2024 US injunction is broad but doesn't ISP-block residential internet, Belgium and France block it** (confidence: medium for coverage, high for the US case)
    Self-reported figures vary widely (2.5-15M+ books depending on source/date); no peer-reviewed coverage study comparable to Sci-Hub's exists. Has an informal, undocumented-for-public-use JSON API originally built for mirror-sync, not general search; bulk database dumps and torrents are the documented programmatic access path. US: a 2024 SDNY default judgment (publishers v. LibGen operators) awarded $30M and ordered a broad injunction covering ad networks, payment processors, hosting/CDN providers, and domain registries, explicitly excluding residential ISP-level blocking. EU: covered by the same 2019 French DNS-blocking order as Sci-Hub; Belgium's Commercial Court ordered ISP blocking in July 2025 (with LibGen, Z-Library, and Anna's Archive together) under threat of a EUR 500,000 fine. Brazil: no LibGen-specific ruling found; only general STJ digital-copyright precedent (REsp 2.057.908) on platform liability under Lei 9.610/98 Art. 104.
    - torrentfreak.com (2024 US judgment); STJ REsp 2.057.908

33. **Anna's Archive: an aggregator/index rather than a primary host, four separate US civil judgments in a five-month span (Jan-May 2026)** (confidence: high for the litigation timeline, low for any headline scale figure)
    Self-describes as cataloging all books in existence; self-reported scale figures are inconsistent across the operator's own announcements (ranging roughly 42-69M books and 13-156M papers depending on date). Architecturally an aggregator that mirrors Sci-Hub/LibGen open-data releases and separately scrapes libraries unwilling to share in bulk (notably Z-Library); no documented public API (a single fast-download JSON endpoint exists for paying members, with the project's own FAQ directing programmatic/bulk use to torrent metadata dumps instead). US: OCLC v. Anna's Archive (S.D. Ohio) - January 2026 default judgment on breach-of-contract/trespass-to-chattels theory ordering it to stop scraping WorldCat and delete all WorldCat data; Spotify/UMG/WMG/Sony v. Anna's Archive (SDNY) - $307M combined judgment (April 2026) over music-metadata scraping; a 13-publisher coalition (SDNY) - $19.5M default judgment plus a global takedown injunction (May 2026), explicitly framed around AI-training-data-pipeline use. EU: Italy's AGCOM ordered ISP DNS-blocking in January 2024 following a publisher complaint; Netherlands/UK/Belgium/Germany reportedly block it too, though only Italy's order was independently verified in this pass. Brazil: no domestic ruling found; the site maintains a Portuguese-language front end and Brazilian press covered the January 2026 domain suspension as a foreign event, not a domestic action.
    - torrentfreak.com/Slashdot (OCLC ruling, Jan 2026); torrentfreak.com (Italy AGCOM order, Jan 2024)

34. **Z-Library: the one criminal (not civil) US case among the four, custody of the founders unresolved** (confidence: high for the criminal case, low for current domain status)
    Self-reported scale grew from ~10M books/85M articles (2022) to "25M+ ebooks, ~100M articles" in recent marketing claims - unverifiable and unaudited. No official API; multiple unofficial reverse-engineered Python wrappers exist against the Android app's internal endpoints, one noting it now works "only through Tor" post-seizure. US: EDNY criminal indictment (November 2022) of two named Russian nationals for criminal copyright infringement, wire fraud, and money laundering, with 241 domains seized at arrest in Argentina; extradition was approved in Argentina (2024) but the pair reportedly vanished from house arrest and remain unrecaptured per the most recent sources found. EU: France ordered DNS-blocking of 209 domains in August 2022 (Tribunal Judiciaire de Paris) and ~98 more in September 2024; Germany's CUII mechanism reportedly covers it (specific decision not independently confirmed); Belgium's July 2025 order named it alongside LibGen/Anna's Archive. Brazil: no domestic ruling found. Security: a named Cybernews report (2024) documented a data breach of a Z-Library clone site exposing 10M users' credentials and crypto-wallet addresses - the most concrete single security incident found across all four shadow libraries.
    - justice.gov/usao-edny press release; TorrentFreak (Nov 2022 indictment); EUIPO case-law note (French injunction); cybernews.com (clone breach)

### Code hosts and package registries

35. **`git clone` is itself the highest-fidelity, zero-quota API for any of these hosts (D-04)** (confidence: high, tested)
    Tested unauthenticated on both GitHub (`git clone https://github.com/octocat/Hello-World.git`, 0.67s) and GitLab (1.85s) for public repos - full history and content, no rate-limit interaction at all, since git's smart-HTTP protocol is separate from each host's REST/GraphQL/search API. This is the only mechanism among the six code sources profiled that gives complete history plus full source at zero API-quota cost, directly instantiating D-04's preference for reading code over documentation.

36. **GitHub: code search requires auth unconditionally and is far more rate-limited than general REST** (confidence: high, code-read + tested)
    REST `/search/code` requires authentication even for a single query - tested: `curl https://api.github.com/search/code?q=test` -> HTTP 401 "Requires authentication"; GraphQL has no unauthenticated tier at all (tested: HTTP 403 rate-limit-exceeded on an unauthenticated POST). Reading the official `cli/cli` source confirms code search is throttled at 10 requests/minute even authenticated (`pkg/cmd/skills/search/search.go:738`), with a 1,000-result hard cap (`:34`) and a note that results come from "what is now a legacy GitHub code search engine" that may not match the web UI. General REST: unauthenticated 60/hr (tested via `/rate_limit` -> `"core":{"limit":60}`), authenticated 5,000/hr (15,000/hr for Enterprise Cloud apps); non-code search 10/min unauthenticated, 30/min authenticated; GraphQL 5,000 points/hr authenticated. ToS's API Terms ban sharing tokens or exceeding rate limits and using the API "for spamming purposes," but explicitly do not restrict lawful access to public-repository contents by third parties; redistribution of cloned code is governed by the repo's own license, not GitHub's ToS.
    - `scratchpad/sources/cli/pkg/cmd/skills/search/search.go:34,695-711,738`; tested as above; docs.github.com/en/rest/search/search

37. **GitLab: unauthenticated API works but its terms explicitly ban bulk/systematic scraping, unlike GitHub's** (confidence: high, tested)
    `git clone` of a public GitLab repo succeeded anonymously (1.85s, tested). REST/GraphQL v4 JSON API works unauthenticated - tested: `curl "https://gitlab.com/api/v4/projects?search=test"` -> HTTP 200 with real data, response headers showing `ratelimit-limit: 500` (500 req/min per IP unauthenticated, per docs 2,000 req/min authenticated). GitLab's separate "API Terms of Use" (handbook.gitlab.com/handbook/legal/api-terms) states a user must "not use GitLab APIs for bulk collection or scraping of information, including repeated, systematic, or bulk exporting of GitLab API Data, except as permitted by applicable law" - a materially stricter clause than GitHub's, restricting bulk harvesting even though the API itself needs no key.
    - tested as above; handbook.gitlab.com/handbook/legal/api-terms

38. **Software Heritage: a write-once preservation archive, not a live mirror - full-repo reconstruction is asynchronous** (confidence: medium-high)
    Archives origins (repo URLs) as immutable, content-deduplicated snapshots spanning GitHub, GitLab, PyPI, npm, crates.io, Debian, and more; there is no direct `git clone` of an arbitrary origin from Software Heritage itself - full-repo reconstruction goes through an asynchronous "vault" cooking endpoint that builds a downloadable bundle. REST-like JSON API works unauthenticated - tested: `curl .../api/1/origin/search/test/` -> HTTP 200. The official `swh-web-client` (cloned) implements a `_RateLimitEnforcer` that paces requests off the server's live rate-limit headers rather than a fixed constant, and accepts an optional bearer token for authenticated calls with higher limits. Tested anonymous rate limit on the search endpoint: `X-Ratelimit-Limit: 10` per ~46-second window. Free, non-commercial preservation mission; preserves whatever license the original repo carried.
    - `scratchpad/sources/swh-web-client/swh/web/client/client.py:263-484,649,844`; tested as above

39. **PyPI, npm, crates.io: all free and keyless, but each enforces access differently** (confidence: high, tested)
    PyPI's JSON API (`pypi.org/pypi/<pkg>/json`) works with a plain unauthenticated GET (tested: HTTP 200); its Acceptable Use Policy (adapted from GitHub's) states no hard resource caps but reserves the right to throttle/suspend disproportionately heavy usage. npm's registry (`registry.npmjs.org/<pkg>`) also works unauthenticated (tested: HTTP 200, Cloudflare-cached); its published crawler policy asks for max 1 req/sec and recommends CouchDB-replicating the entire public registry for bulk needs instead of crawling. crates.io's API (`crates.io/api/v1/crates/<name>`) actively blocks requests without a distinctive User-Agent header - tested: no UA -> HTTP 403, with a UA string -> HTTP 200 - a hard, currently-enforced technical requirement rather than a documented preference; its own written crawler-policy text could not be retrieved live in this pass (client-rendered page). All three carry whatever license the package/crate author declared, unverified by the registry itself.
    - tested as above (three separate curl calls); docs.npmjs.com/policies/crawlers; policies.python.org/pypi.org/Acceptable-Use-Policy/

## Taxonomy

### By kind

| Kind | Sources |
|---|---|
| Bibliographic metadata aggregator | Semantic Scholar, OpenAlex, CORE, Crossref, Unpaywall, DBLP, Internet Archive Scholar, CiteSeerX |
| Paywalled / institutional full-text publisher | IEEE Xplore, SpringerLink, ScienceDirect, Scopus, JSTOR |
| Web-scale index, no API | Google Scholar |
| Preprint server / open archive | OpenReview, PubMed/PMC, SSRN, bioRxiv/medRxiv, Zenodo, HAL, university institutional repositories |
| ML-specific paper/model hub | Papers with Code (defunct), Hugging Face papers and hub |
| Uncurated social platform | ResearchGate |
| Code host | GitHub, GitLab, Software Heritage |
| Package registry | PyPI, npm, crates.io |
| Shadow library | Sci-Hub, LibGen, Anna's Archive, Z-Library |

### Comparison matrix (access and coverage)

| Source | Key needed? | Free-tier reach (tested) | Full text? | Redistribution stance | Confidence |
|---|---|---|---|---|---|
| Semantic Scholar | No (helps) | Works, frequent 429 | Linked OA only | No explicit restriction found | High |
| OpenAlex | No (metered $) | Works, budget-capped | No (metadata) | CC0 | Medium |
| CORE | Docs say yes; tested no | Works unauth. (light use) | Yes (largest OA aggregator) | No bulk PDF scraping | Medium-high |
| Crossref | No | Works, generous | No (metadata) | Mostly uncopyrighted | High |
| Unpaywall | No (email param) | Works | Links to OA PDFs | ToS text unread (gap) | High/Low (mixed) |
| DBLP | No | Bot-blocked in this test | No (metadata) | CC0 | Medium |
| IA Scholar/Fatcat | No | Bot-blocked/timeout in this test | Yes (full-text index) | AGPLv3 server; TDM-oriented | Low-medium |
| CiteSeerX | No | Down - 301/404 | Was yes | Unclear (site defunct) | High (defunct) |
| IEEE Xplore | Yes | Blocked without key | Subscriber only | No harvestable redistribution | Medium |
| SpringerLink | Yes | Blocked without key | OA content only free | Personal/non-commercial only | Medium |
| ScienceDirect | Yes | Blocked without key | Subscriber only | Academic non-commercial TDM | High |
| Scopus | Yes | Blocked without key | No (metadata/abstracts) | Academic non-commercial | High |
| Google Scholar | No API exists | Single request works; volume blocked | Links out | Automated access disallowed | High |
| JSTOR | No public API | 404 (no API surface) | Subscriber/JPASS | No scraping/bulk redistribution | Medium-high |
| OpenReview | No (policy-based) | Bot-challenged in this test | Yes (PDFs + reviews) | Respect readers/writers fields | Medium |
| PubMed/PMC | No (helps) | Works | PMC OA subset only | Free-to-read ≠ open license | High |
| SSRN | No API exists | N/A | Yes (PDF) | AI-training/TDM rights reserved | High |
| bioRxiv/medRxiv | No | Works | Yes | Explicit TDM endorsement | High |
| Zenodo | No (helps) | Timeout/403 in this test | Yes (any output type) | Sanctioned bulk via OAI-PMH/dumps | High |
| Papers with Code | N/A | Redirects to HF | N/A | Dead; frozen GitHub dump only | High |
| Hugging Face hub | No | Works | Varies (per repo) | Per-repo license | High |
| HAL | No | Works | Yes (subset) | Open by design | Medium |
| ResearchGate | No API exists | N/A | N/A | Automated access explicitly banned | High |
| University repositories | No (OAI-PMH) | Varies per institution | Varies | Per-repo/author license | Medium |
| GitHub | No for clone; yes for code search | Clone works; search 401 | Full source via clone | Governed by repo license | High |
| GitLab | No | Clone and REST both work | Full source via clone | Bulk/systematic scraping banned by ToS | High |
| Software Heritage | No (helps) | Works, ~10 req/window | Yes, via async vault | Per-origin license preserved | Medium-high |
| PyPI | No | Works | Full source via sdist | Per-package license | High |
| npm | No | Works | Full source via tarball | Per-package license | High |
| crates.io | No (UA required) | Works with UA header | Full source via tarball | Per-crate license | Medium |
| Sci-Hub | N/A (scraping only) | N/A | Yes (paywalled papers) | Under US injunction; unpaid | High |
| LibGen | N/A (scraping/dumps) | N/A | Yes (books + papers) | Under US injunction | Medium |
| Anna's Archive | N/A (aggregator) | N/A | Yes (via mirrors) | Four active US judgments (2026) | Low-medium |
| Z-Library | N/A (scraping only) | N/A | Yes (books + papers) | Criminal US case, founders at large | Low |

## Contradictions

- OpenAlex: `pyalex`'s README states a key became mandatory February 13, 2026; the official help.openalex.org page (updated August 11, 2026) describes keyless access as still allowed under a metered budget. Live testing supports the official page - keyless calls worked - but does not explain why the two official-adjacent sources disagree (finding 6).
- CORE: the service's own FAQ says register for an API key; unauthenticated calls succeeded in this pass anyway for light/occasional use (finding 7). Whether this is a documented allowance for low volume or an unenforced policy was not resolved.
- Google Scholar's Gusenbauer & Haddaway (2020) "unsuitable as principal search system" verdict is the dominant, most-cited position in the field, but a 2025/2026 MDPI critique argues the same underlying data overstates the reproducibility problem (finding 17). Both are in the current literature.
- Z-Library domain status: one source lists `z-lib.id` as a current legitimate SSO portal; a separate security-community thread flags the same domain as a scam site compromising visitor safety (finding 34) - directly contradictory, illustrating that any shadow-library domain list is unreliable at the moment of reading, not just stale over time.
- Self-reported scale figures for LibGen, Anna's Archive, and Z-Library are inconsistent even across each operator's own sequential announcements (findings 32-34), unlike Sci-Hub, which has one independent peer-reviewed benchmark (Himmelstein et al. 2018) that is now eight years old.

## Gaps

- Brazil-specific legal status is unresolved for all four shadow libraries (findings 31-34) - only general Lei 9.610/98 and STJ digital-copyright jurisprudence was found; closing this needs a targeted search of Brazilian court databases (e.g., JusBrasil case search by defendant name), not general web search.
- Unpaywall's actual Terms of Service text could not be read (JavaScript-rendered page) - finding 9's redistribution-stance claim is a gap, not a verified "no restriction."
- Whether DBLP's and OpenReview's JSON APIs respond to any unauthenticated script at all is unresolved - both were bot-challenged from this sandbox's network in this pass (findings 10, 20); this may be IP-reputation-specific rather than a documented universal property, and should be re-tested from Compass's actual deployment network before being relied on.
- Internet Archive Scholar / Fatcat's live reachability is unresolved (finding 11) - one endpoint timed out, another served a bot-check page; neither confirms nor rules out a working public API today.
- CORE's exact numeric free-tier daily quota (beyond the documented per-10-second batch limit) was not found; nor was CORE's precise classification in the Gusenbauer & Haddaway (2020) 27-criterion comparison table (full paper was not independently retrievable, only secondary summaries).
- No successor to Gusenbauer & Haddaway (2020) was found that head-to-head evaluates OpenAlex, CORE, Unpaywall, DBLP, Internet Archive Scholar, or CiteSeerX the way the original paper did for Google Scholar/Scopus/Web of Science - the closest post-2020 work found is scattered single-topic OpenAlex-vs-WoS/Scopus coverage studies (Culbert et al. 2025, Alperin et al. 2024).
- crates.io's formal written crawler/data-access policy text could not be retrieved (client-rendered SPA); its access rules in this document are inferred from tested behavior (User-Agent gating) rather than a read policy document.
- No authenticated live call was made against any key-gated source (IEEE Xplore, Springer, Elsevier, Scopus, GitHub code search) - all authenticated-tier behavior above comes from official docs or client-library source, not a live authenticated test, since no keys were available in this pass.
- Serena's actual capabilities were not independently tested in this research role (finding 3) - a further pass with access to the tool itself, or a report from an agent that has it, would close this.
