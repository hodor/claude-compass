---
title: "Research Methodologies Catalog"
type: research
status: draft
confidence: high
area: methodology
tags: [research, methodology, pipeline, scoping-review, systematic-review, mapping-study, snowballing, grey-literature, repository-mining, protocol]
created: 2026-09-13
updated: 2026-09-13
git_branch: "master"
git_commit: "50a2896"
author: "researcher"
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
summary: "catalog of established research methodologies (scoping, SLR, mapping, rapid, grey-literature/MLR, snowballing, tech landscape, repository mining) plus how protocols are registered, each with its own steps, inputs, output, fit, and named failure modes"
---

# Research Methodologies Catalog

## Question

Which established research methodologies exist that an AI research agent could follow step by step, and what does each prescribe (steps, inputs, output, when it fits, failure modes its own authors name)? Also: how do research groups formally publish a protocol before running a study, and what does a protocol contain? This serves [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-06 (research follows a chosen methodology, stated in the document) and touches D-03/D-04/D-07 (source curation, code-over-docs, plugin use) where the sources themselves illustrate those points.

## Scope

In scope: methodology-defining papers/guidance for scoping reviews, rapid reviews, SLRs, PRISMA, systematic mapping studies, snowballing, grey-literature/multivocal reviews, technology-landscape/comparative evaluation, code study/repository mining, and protocol registration practice (PROSPERO, OSF, standalone SE protocols). Out of scope: which methodology Compass should mandate or how the chooser mechanism should work - that is a design decision for the plan, not this research.

## Methodology

Five parallel literature passes, one per methodology cluster, each instructed to fetch and read primary sources directly (not summaries) via WebSearch/WebFetch, preferring the original paper, the venue's open-access page, or a freely mirrored PDF (author page, technical-report server, arXiv) over secondary blogs. This is itself an instance of the **technology-landscape / comparative-evaluation** approach applied to methodologies as the object of study: each methodology profiled on the same dimensions (steps, inputs, output, fit, failure modes) side by side. Access was medicine/social-science-journal paywalls in a few cases (noted per finding), which is why the report leans on Semantic Scholar / open-access mirrors rather than ACM DL or Elsevier directly for those.

## Findings

### Scoping review

1. **Six-stage framework** (confidence: medium)
   Arksey & O'Malley (2005) define five mandatory stages plus an optional sixth: identify a deliberately broad research question; identify relevant studies as comprehensively as possible; select studies via post-hoc, iteratively refined criteria; chart data by sifting/sorting into key issues and themes; collate, summarize, and report as a numerical summary plus thematic analysis; optionally consult stakeholders.
   - https://eprints.whiterose.ac.uk/id/eprint/1618/1/scopingstudies.pdf (DOI 10.1080/1364557032000119616)
   - Caveat: full text not directly parseable, reconstructed via a widely-cited secondary summary (Daudt et al. 2013), not the primary PDF's own wording.

2. **Levac et al. (2010) operationalize the same six stages** (confidence: high)
   Stage 1 pairs the broad question with an explicit scope statement (concept/population/outcomes) tied to the intended end use. Stage 3 becomes iterative (search, refine, review) with two independent reviewers screening abstracts and full texts and a third reviewer arbitrating disputes. Stage 4 requires a jointly built charting form piloted and calibrated on 5-10 studies before full charting. Stage 6 upgrades stakeholder consultation from optional to a recommended knowledge-translation step.
   - Implementation Science 2010;5:69, full text https://pmc.ncbi.nlm.nih.gov/articles/PMC2954944/ (Methods/Discussion)

3. **Named limitations** (confidence: high)
   Levac et al. flag that risk-of-bias/quality appraisal is not standardized in scoping reviews; that stage 3 was wrongly presented as linear in the original 2005 framework; that stage 5's "descriptive analytical method" is left undefined; that terminology is inconsistent across the field ("study" vs. "review" vs. "exercise"); and that their own refinements are untested beyond the three example reviews they ran.
   - Implementation Science 2010;5:69, Discussion/Conclusions

4. **PRISMA-ScR reporting checklist** (confidence: medium)
   Tricco et al. (2018) publish a 20-item-plus-2-optional checklist requiring an explicit rationale for why the question suits a scoping rather than systematic approach (item 3) and a PRISMA-style flow diagram (item 14). Critical-appraisal items are optional, consistent with Levac's finding that quality appraisal is not standard practice in scoping reviews.
   - Annals of Internal Medicine 2018;169:467-473, DOI 10.7326/M18-0850
   - Caveat: reconstructed from EQUATOR Network tip sheets, not the primary PDF directly.

### Rapid review

5. **No single fixed method - a family of abbreviations of the SLR steps** (confidence: high)
   Tricco et al. (2015) coded 84 published rapid reviews against the same six generic SLR steps (search, inclusion criteria, screening, data abstraction, quality appraisal, synthesis) and found 50 distinct method combinations, only 16 of which recurred more than once. "Rapid review" names a class of shortcuts taken against those six steps, not one fixed recipe.
   - BMC Medicine 2015;13:224, full text https://pmc.ncbi.nlm.nih.gov/articles/PMC4574114/

6. **Practice profile from the same scan** (confidence: high)
   98% of the 84 sampled rapid reviews reported no protocol; 73% did not report their own duration (reported durations ranged under 1 month to 12 months); synthesis was narrative in 78% of cases versus meta-analysis in 22%.
   - BMC Medicine 2015;13:224

7. **Cochrane Rapid Reviews Methods Group guidance names concrete, bounded abbreviations** (confidence: medium-high)
   Garritty et al. (2021) recommend dual independent screening on at least 20% of abstracts, then single-reviewer screening for the rest with a second reviewer checking exclusions only; single-reviewer data extraction with second-reviewer verification; single-reviewer risk-of-bias rating with full second-reviewer check. A publicly registered protocol allowing documented post-hoc changes is still required even in the abbreviated form.
   - J Clin Epidemiol 2021;130:13-22, DOI 10.1016/j.jclinepi.2020.10.007
   - Caveat: drawn from a secondary summary of the paper, not a direct full-text fetch.

8. **The guidance is explicitly interim and was already superseded** (confidence: high)
   The 2021 authors label their own guidance "interim," citing insufficient evidence for some abbreviated methods. It was superseded by Garritty et al. (2024, BMJ 2024;384:e076335) with updated recommendations - a signal that any fixed description of "rapid review" embedded in a tool will drift out of date.
   - https://pubmed.ncbi.nlm.nih.gov/38320771/

### Systematic Literature Review (software engineering)

9. **Three mandatory phases** (confidence: high; primary PDF read in full)
   Kitchenham & Charters (2007), EBSE-2007-01 v2.3: Planning the review (identify need, commission, define research questions, develop and evaluate a protocol) - Conducting the review (identify research, select studies, assess quality, extract and monitor data, synthesize data) - Reporting the review (write the report, evaluate the report).
   - EBSE-2007-01, Section 4, p.6

10. **Iterative, not linear** (confidence: high)
    Only the two "evaluating" sub-steps (protocol evaluation, report evaluation) are optional; everything else is mandatory. The process still loops back - e.g., inclusion/exclusion criteria set during protocol development get refined once quality-assessment criteria exist.
    - EBSE-2007-01, p.6

11. **PICOC framing for research questions** (confidence: high)
    Research questions use Population, Intervention, Comparison, Outcome, Context - extending medicine's PICO with Context because SE studies vary by academic vs. industrial setting and by participant type (students vs. practitioners).
    - EBSE-2007-01, Section 5.3.2, pp.10-12

12. **Quality-assessment instrument adapted from medicine, not copied** (confidence: high)
    Built around four bias types (selection, performance, measurement, attrition), each with a "protection mechanism" column. The authors note explicitly that some medical protection mechanisms, such as blinding, are "usually impossible" in software engineering experiments.
    - EBSE-2007-01, Table 4, p.22

13. **Authors' own named limitations** (confidence: high)
    The guidelines "do not consider the impact of research questions on review procedures," nor do they specify meta-analysis mechanics in detail; SE reviews are "likely qualitative" because primary-study reporting is too inconsistent to support meta-analysis; digital-library searches are "almost impossible to replicate"; poor abstract quality in SE venues makes title/abstract-only screening unreliable.
    - EBSE-2007-01, Executive Summary p.vi; Section 6.5.8 p.39-40; Section 2.4 p.4; Section 6.2.2 p.19

14. **A stated fallback for a lone researcher** (confidence: high)
    The authors describe a "light" SLR for solo PhD-style researchers that keeps protocol, research questions, inclusion/exclusion criteria, search strategy, extraction, quality assessment, synthesis, and reporting, but drops the dual-reviewer cross-checking machinery.
    - EBSE-2007-01, Section 9, pp.44-45

### PRISMA (reporting standard, not a conduct method)

15. **27-item checklist plus a 12-item abstract checklist** (confidence: high; primary text read via PMC)
    Page et al. (2021) structure the checklist across Title, Abstract, Introduction, Methods, Results, Discussion, and Other Information, with several lettered sub-items (e.g. 13a-13f for synthesis methods) and a separate flow-diagram item.
    - PMC8008539, Fig.1 and item list

16. **PRISMA reports, it does not prescribe conduct** (confidence: high)
    PRISMA states explicitly it is "not intended to guide systematic review conduct" and should not be used to judge methodological quality - that is ROBIS/AMSTAR2's job. This is the structural line between PRISMA and Kitchenham & Charters or the MLR guidelines below, which govern how to run a review, not only how to write it up.
    - PMC8008539, Limitations section

17. **Stated scope and the extensions that exist for what it doesn't cover** (confidence: high)
    Designed primarily for systematic reviews of health-intervention effects, extended by convention to aetiology/prevalence/prognosis and social/educational interventions; protocols are covered by a separate PRISMA-P extension; qualitative/mixed-methods synthesis is pointed to separate guidance (ENTREQ, eMERGe) rather than folded into PRISMA itself.
    - PMC8008539, Scope statement

18. **Authors' own named limitations** (confidence: high)
    Evidence for which checklist-adherence strategies actually work is thin (only 11 of 31 proposed strategies evaluated, mostly via confounded observational studies); patients/public were not involved in developing the checklist; the development survey had roughly a 50% response rate (110 of 220 invited); item placement within a report is explicitly "not prescriptive," only that the information appear somewhere.
    - PMC8008539, Discussion/Limitations

### Systematic mapping study

19. **Five-step pipeline with named intermediate outputs** (confidence: high; primary PDF read)
    Petersen, Feldt, Mujtaba & Mattsson (2008): define research questions -> conduct search for papers -> screen for relevance -> keyword abstracts to build a classification scheme -> extract data and produce the map. Each step names its output: Review Scope -> All Papers -> Relevant Papers -> Classification Scheme -> Systematic Map.
    - https://www.cse.chalmers.se/~feldt/publications/petersen_ease08_sysmap_studies_in_se.pdf, Section 2, Fig.1

20. **Keywording sub-procedure** (confidence: high)
    Reviewers read abstracts to extract keywords/concepts reflecting each paper's contribution and context, cluster keywords into candidate categories, then sort every paper into the resulting scheme, updating the scheme (merge/split/add categories) as sorting proceeds. When abstracts are too sparse, reviewers fall back to reading the introduction and conclusion.
    - Same paper, Section 2.4, Fig.2

21. **Output is a bubble-plot map, not a narrative synthesis** (confidence: high)
    The systematic map is a populated classification scheme with frequency counts, typically visualized as a two-axis scatter plot where bubble size encodes article count per category intersection.
    - Same paper, Section 2.5, Fig.3

22. **Authors' own distinction from a full SLR** (confidence: high)
    Mapping studies and SLRs sit on a breadth-versus-depth continuum: a map structures a research area broadly and shallowly, a review evaluates a narrow question in detail. Maps do not assess study quality; reviews do. The paper recommends using them complementarily - map first, then a focused review.
    - Same paper, Section 3.2

23. **Named failure mode: classification is judgment-based** (confidence: high)
    The authors cite Mendes (2005) finding 73% of papers misclassified in one case (papers claiming to be experiments that weren't) and warn that restricting a map's sample to only methodologically rigorous studies risks an incomplete or biased picture of the field, since methodological rigor is unevenly distributed across its sub-areas.
    - Same paper, Section 3.2, "Validity Consideration"

### Snowballing

24. **Iterative backward/forward procedure** (confidence: high; primary PDF read)
    Wohlin (2014): fix a tentative start set via inclusion/exclusion; backward snowballing screens each included paper's reference list (title, venue, citation context) before full-text screening of candidates; forward snowballing runs in parallel via citation tracking (Google Scholar recommended) using the same screening steps; a paper's inclusion/exclusion must be finalized before it is itself used for further snowballing, requiring a "rollback" if it is later excluded after being used.
    - https://www.wohlin.eu/ease14.pdf, Section 3, Fig.1

25. **Start-set guidance, with an admitted gap** (confidence: high)
    Avoid publisher bias by preferring multi-publisher citation trackers; cover multiple research communities, publishers, years, and authors to avoid missing an independent citation cluster; size it to the breadth of the area; derive keywords from the research question including synonyms. The paper states plainly: "there is no silver bullet for identifying a good start set... it is an area of future research."
    - Same paper, Section 3.1

26. **Stopping criterion and sanity-check artifacts** (confidence: high)
    The loop ends once an iteration finds no new papers via either backward or forward snowballing. A citation matrix and publication timeline are recommended as sanity-check artifacts for coverage before the final set feeds into data extraction.
    - Same paper, Sections 3.2-3.4, 4.8

27. **Complement to database search, not a replacement** (confidence: high)
    "Snowballing should not necessarily [be] seen as an alternative to database searches" - a database search is "no better than the search string used," and inconsistent SE terminology causes misses that citation context catches. The paper frames snowballing as "particularly useful for extending" an existing systematic study, since new studies almost certainly cite at least one already-known relevant paper.
    - Same paper, Section 5

28. **Named failure modes from the paper's own replication** (confidence: high)
    Heavy dependence on start-set quality (their own start set had three papers sharing one author - called suboptimal in hindsight); risk of missing an independent citation cluster unlinked to the start set; a named diagnostic that a non-decreasing rate of new-paper discovery signals a missed cluster and warrants a fresh database search with synonyms; a self-reported confirmation-bias threat, since the researcher had read the original study before replicating it.
    - Same paper, Sections 4.2, 4.9.1-4.9.2

### Grey literature / multivocal literature review (MLR)

29. **Three phases adapted from Kitchenham & Charters** (confidence: high; primary PDF fetched from arXiv)
    Garousi, Felderer & Mäntylä (2019): Planning (establish need, set goal, research questions) - Conducting (search -> source selection via inclusion/exclusion -> quality assessment -> data extraction -> synthesis) - Reporting (dissemination matched to audience).
    - arXiv:1707.02553, Section 3.4/Fig.7

30. **Three-tier source classification by outlet control/credibility** (confidence: high)
    Tier 1 (high control: books, magazines, theses, government reports, white papers); tier 2 (moderate: annual reports, news articles, videos, Q&A sites like Stack Overflow, wikis); tier 3 (low: blog posts, presentations, emails, tweets). Tier is one of eight scored quality criteria, not a standalone admission gate.
    - Same paper, Table 7 / Fig.1

31. **Seven-question inclusion checklist decides whether grey literature belongs at all** (confidence: high)
    Includes questions such as "is the subject too complex/new for formal literature alone?", "is there a lack of volume/quality/consensus in formal literature?", "is contextual/practitioner information important?", "is the goal to validate or challenge practice vs. research?" A single "yes" justifies including grey literature.
    - Same paper, Table 4

32. **Eight-criterion quality-assessment instrument** (confidence: high)
    Authority of the producer, methodology, objectivity, date, position relative to other sources, novelty, impact (citations/backlinks/social shares/comments), and outlet tier - each scored on a Likert scale, summed, and normalized to a 0-1 inclusion threshold.
    - Same paper, Table 7

33. **When the authors say MLR does not fit** (confidence: high)
    They explicitly recommend excluding grey literature for "relatively mature and bounded academic topics," such as formal methods or mathematics, citing Adams et al. - MLR fits when formal literature is sparse, low-quality, or lacks consensus, not universally.
    - Same paper, Section 4.2

34. **Named limitations** (confidence: high)
    Grey-literature quality is "more diverse and often more laborious to assess"; impact metrics (comments, shares) can be gamed; search result volumes are huge and ranked only by an opaque engine algorithm, with evidence quality "quickly declined" deeper in results; grey sources often omit standard deviations or controlled-experiment design, blocking meta-analysis; vendor/vested-interest bias must be checked explicitly; the authors admit their own guidelines are empirically unvalidated.
    - Same paper, pp.17-28 (multiple sections)

### Technology landscape / comparative evaluation

35. **ThoughtWorks Technology Radar process** (confidence: high)
    Practitioners nominate "blips" from real client-project use; a roughly 20-person Technology Advisory Board debates each candidate twice yearly (plus biweekly virtual sessions), votes to cull an overcrowded quadrant, assigns a champion to write up each accepted blip, then an internal review and design pass produces the published graphic. No vendor submissions or external nomination channel are accepted.
    - https://www.thoughtworks.com/en-us/radar/faq

36. **Output format and its own stated limits** (confidence: high)
    A biannual snapshot across four topic quadrants x four adoption rings (Adopt/Trial/Assess/Hold), each ring carrying an explicit recommendation strength; blips fade out after roughly two unchanged editions. The publishers state the method is subjective/opinion-based and recency-biased, not a systematic survey.
    - Same source

37. **Multi-criteria decision analysis (MCDA) as the formal alternative** (confidence: medium)
    Define a hierarchical criteria/sub-criteria tree (e.g., functional suitability, performance, maintainability, security, cost), normalize weights to sum to 1, score each alternative 0-100 per criterion, aggregate via weighted sum or weighted product, rank, then run a sensitivity analysis on weights and scores.
    - scielo.org.mx/S1405-55462018000100203; 1000minds.com/decision-making/what-is-mcdm-mcda
    - Caveat: no single canonical peer-reviewed SE-specific methodology paper was pinned; this synthesizes general MCDA literature.

38. **Named failure mode** (confidence: medium)
    Weight elicitation is unstable across raters and criteria sets, which is why sensitivity analysis and robustness techniques (e.g. rough best-worst method) are recommended as a standard part of the method, not an optional check.
    - Same sources

### Code study / repository mining as a method

39. **Four-stage empirical pipeline** (confidence: high; primary PDF read in full)
    Kalliamvakou, Gousios, Blincoe, Singer, German & Damian (2014; extended version, Empirical Software Engineering 21(5), 2016): exploratory survey (1,000 invited GitHub users, 240 responses) to surface candidate problems -> quantitative analysis of a GHTorrent snapshot (6.8M public repos, ~3M "base" projects after dedup) -> manual inspection of a random sample of 434 repositories (95% confidence, +/-5% margin) because metadata alone can't separate real projects from toy/dead ones -> re-examination of four MSR'14 Mining Challenge papers to show the perils create concrete validity threats.
    - https://gousios.org/pub/promises-perils-github-extended.pdf, pp.6-8

40. **Named perils, grouped** (confidence: high)
    Project-related: a "repository" is not a "project" - forks must be unioned with the base repo; many repos are personal/toy/inactive; only a minority of pull requests are ever actually merged even when nominally "successful." GitHub-related: the API doesn't expose all data for moved/renamed/deleted repos; platform semantics change over time (e.g. "watching" became "starring"); only public activity is visible, and roughly half of registered users have none.
    - Same paper, Table 1 p.8, pp.30-31

41. **Stated fit and mitigation** (confidence: high)
    GitHub mining supports solid descriptive/trend claims (language use, tool adoption, contribution size) but is risky for abstract constructs like "success" or "collaboration intensity" without first filtering the sample. The authors recommend a concrete filter (recent, balanced commit/PR activity; more than two committers/authors; watch for bot-like commit-rate outliers) and recommend triangulating quantitative mining with qualitative data (surveys, interviews).
    - Same paper, pp.33-36

42. **Perils recur across platform generations** (confidence: high)
    The authors explicitly connect their 13 perils to Howison & Crowston's 2004 SourceForge-era peril taxonomy (spidering/parsing/summarizing/testing; dirty/skewed data; research-design threats) - the same three-category threat structure recurs regardless of the platform being mined.
    - Same paper, pp.33-36

43. **A named dependency risk in the tooling itself** (confidence: high)
    GHTorrent, the dataset this and much other MSR work is built on, is described by its own creators as "best-effort," not a full mirror of the GitHub API - any study built on it inherits that gap.
    - Same paper, p.5, p.34

### Protocol registration (how a methodology gets locked in before execution)

44. **PROSPERO** (confidence: high)
    University of York's Centre for Reviews and Dissemination register (crd.york.ac.uk/prospero): free registration before data extraction begins, capturing the research question in PICO form, the full search strategy, eligibility/inclusion criteria, outcomes of interest, planned analysis method, team composition, funder, and conflict-of-interest declarations. Scoped to health-related reviews; does not accept general software-engineering reviews.
    - https://www.crd.york.ac.uk/prospero/

45. **OSF preregistration** (confidence: high)
    A template locks research question(s), hypotheses (specific, testable, direction stated), a design plan (study type), a sampling plan (data source, sample-size rationale), and an analysis plan (named statistical model, all variables/covariates, planned contrasts) before data collection - anything not listed must later be reported as exploratory. OSF also ships a "Generalized Systematic Review Registration" template aligned to PRISMA (search strategies, databases, exact query strings, inclusion/exclusion criteria), open to any field including SE.
    - https://help.osf.io/article/330-welcome-to-registrations; https://www.cos.io/blog/generalized-systematic-review-template-joins-osf-registries

46. **SE fills the PROSPERO gap with standalone protocol documents** (confidence: medium)
    Zapata et al.'s SLR protocol on interpersonal trust in global software development (arXiv:2002.04974) fixes, before the review runs: research/publication questions, search strategy (automated search string, manual search, snowballing), selection strategy (inclusion/exclusion criteria), a named data-extraction form with a disagreement-handling process, planned data visualization, and threats to validity.
    - arXiv:2002.04974
    - Caveat: structure confirmed via a secondary description of the paper's contents, not a direct re-fetch of the full PDF text.

47. **A protocol's execution artifact can itself be published on GitHub** (confidence: medium)
    The SLR "Bridging MDE and AI" (arXiv:2307.04599) publishes its protocol-execution spreadsheet in a GitHub repository, tracking inclusion/exclusion decisions at title/abstract and full-text stages plus forward/backward snowballing results - the protocol as a living, versioned artifact rather than a static document.
    - arXiv:2307.04599; github.com/sraedler/Model-Driven-Engineering4Artificial-Intelligence
    - Caveat: repo owner's activity/reliability was not independently verified beyond the paper's own link (per D-03's "check the owner" rule, this needs a follow-up look before being cited as a curated source).

## Taxonomy

Classified by the kind of question each methodology answers:

- **"What exists, and how broad or varied is it?"** (exploratory, low depth, high breadth) - scoping review, systematic mapping study, technology-landscape survey.
- **"What does the evidence say for or against a specific practice?"** (focused, evaluative, higher depth) - systematic literature review (Kitchenham & Charters); PRISMA governs how such a review is reported, not how it is conducted.
- **"What exists, but time is short?"** - rapid review: the SLR's six steps, deliberately abbreviated, with the abbreviation itself varying study to study.
- **"What do practitioners actually say or do, beyond published research?"** - grey literature / multivocal literature review, for topics where formal literature is sparse or contested.
- **"How do I find everything connected to a paper I already know is relevant?"** - snowballing: a search-expansion technique usable inside any literature-based methodology above, not a standalone review type on its own.
- **"How does an existing system, API, or codebase actually behave?"** - code study / repository mining: empirical study of artifacts, not a literature survey.
- **"Which of several concrete options should I pick?"** - technology landscape / comparative evaluation, informally (ThoughtWorks Radar) or formally (MCDA).
- **Protocol registration (PROSPERO, OSF, standalone SE protocol) is not itself a methodology that answers a research question** - it is a pre-commitment format that locks in one of the above literature-based methodologies before execution, so its own audit trail (dated amendments) can be checked afterward.

## Contradictions

- Wohlin's snowballing paper argues a database search alone is "no better than the search string used" and treats snowballing as necessary to compensate; Kitchenham & Charters treat database search as the default, sufficient primary method. Not a direct contradiction - Wohlin frames snowballing as a complement for extending an existing search, not a replacement - but the two papers weight the reliability of keyword search differently.
- Petersen's mapping-study guidance states maps deliberately skip quality assessment; Kitchenham & Charters mandate it. This is by design (different depth targets), not a disagreement, but conflating "do a mapping study" with "do an SLR" would silently drop the quality-assessment step.
- PRISMA states it is a reporting standard "not intended to guide conduct," while Kitchenham & Charters and the Garousi MLR guidelines are conduct methodologies. An agent that treats PRISMA alone as "the methodology" would have no conduct steps to follow - PRISMA needs pairing with a conduct method (SLR, scoping review, or mapping study).

## Gaps

- No source provides a ready-made decision procedure ("if the question looks like X, use scoping review; if Y, use SLR") - each paper states its own fit condition in isolation. A chooser mechanism, if Compass wants one, would need to be authored by synthesizing these fit statements, not lifted from a single source.
- Rapid review is a moving target by its own methodologists' admission (50 method combinations found in one 84-paper scan; Cochrane's own guidance was updated 2021 to 2024). Anything Compass embeds about "rapid review" should point to current Cochrane Rapid Reviews Methods Group guidance rather than freeze a specific recipe.
- Technology-landscape/comparative-evaluation rests on one company's public methodology (ThoughtWorks) plus general MCDA theory, not a single canonical peer-reviewed SE methodology paper the way the other methodologies have one. A further ACM DL / IEEE Xplore pass for an SE-specific tool-selection methodology paper would raise this finding's confidence.
- Two protocol-document findings (44/46/47) rest on secondary description or an unconfirmed GitHub repo owner rather than a direct re-fetch and owner-reliability check. A follow-up pass re-fetching arXiv:2002.04974 in full and checking the `sraedler` repository's commit history and affiliation would raise both to high confidence and satisfy D-03's owner-check requirement before either is cited as a curated Compass source.
