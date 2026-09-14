---
name: research-methods
description: Catalog of established research methodologies for running a research pass - what each prescribes (steps, inputs, output, the question shape it fits, and its own authors' failure modes), plus a chooser that routes a question's shape to one.
version: 1.0.0
allowed-tools: [Read]
when_to_use: "Load before choosing how to run a research pass: which methodology fits the question's shape, and what its steps, inputs, output, and named failure modes are. Also load when writing up a review's report structure, or when registering a protocol before a review runs."
---

# Research Methodologies Catalog

Eight methodologies to run a research pass with, one reporting standard for writing a review up, and one format for locking a plan in before running it. Pick a conduct methodology from the chooser below, state which one was chosen in the research document, and follow its own steps.

## Scoping review

**Steps:** identify a deliberately broad research question and pair it with a scope statement (concept, population, outcomes) tied to the intended use; search as comprehensively as possible; screen with two independent reviewers using criteria refined iteratively as retrieval proceeds, a third reviewer arbitrating disagreement; chart data into a jointly built extraction form, piloted on five to ten studies before full charting; summarize numerically and thematically; optionally consult stakeholders as a knowledge-translation step (Arksey & O'Malley, 2005; Levac et al., 2010).

**Inputs:** a broad question and its scope statement.

**Output:** a numerical summary plus a thematic map of the literature; a PRISMA-ScR flow diagram if the report follows that checklist.

**Fits:** "what exists, and how broad or varied is it" questions, where the field is still being mapped rather than narrowed to one practice.

**Failure modes named by the authors:** quality appraisal has no standard method here and is commonly left out; screening reads as linear in the original framework but runs iteratively in practice; the "descriptive analytical method" the framework calls for at the summary stage is left undefined; terminology for the exercise itself varies across the field ("study," "review," "exercise").

## Rapid review

**Steps:** the same six generic systematic-review steps (search, inclusion criteria, screening, data extraction, quality appraisal, synthesis), with at least one deliberately abbreviated; a documented, bounded abbreviation looks like dual independent screening on a sample of abstracts followed by single-reviewer screening on the rest, single-reviewer extraction with second-reviewer verification, and single-reviewer quality rating with a second-reviewer check (Garritty et al., 2021).

**Inputs:** a defined question and search strategy, plus a publicly registered protocol even in abbreviated form.

**Output:** the same shape as a systematic literature review, synthesized narratively far more often than through meta-analysis.

**Fits:** "what exists, but time is short" questions, where a full systematic literature review's timeline does not fit.

**Failure modes named by the authors:** no single fixed method exists; one scan of 84 published rapid reviews found 50 distinct method combinations, and most reported no protocol or their own duration (Tricco et al., 2015); the abbreviated steps Cochrane's own methods group recommends are labeled "interim" by their authors and were already superseded once. Any fixed rapid-review recipe embedded here should be treated as provisional and checked against current guidance.

## Systematic literature review

**Steps:** Plan (state the need, define research questions framed with Population, Intervention, Comparison, Outcome, Context, write and evaluate a protocol), Conduct (search, select studies, assess quality, extract and monitor data, synthesize), Report (write and evaluate the report) (Kitchenham & Charters, 2007). The process loops back rather than running linearly: inclusion and exclusion criteria set during planning get refined once quality-assessment criteria exist.

**Inputs:** research questions framed with Population, Intervention, Comparison, Outcome, Context.

**Output:** a written review report plus a quality-assessed, extracted evidence set. A "light" variant for a lone researcher keeps every step but drops the dual-reviewer cross-checking machinery.

**Fits:** "what does the evidence say for or against a specific practice" questions, focused and evaluative rather than broad.

**Failure modes named by the authors:** digital-library searches are almost impossible to replicate; poor abstract quality in software-engineering venues makes title-and-abstract screening unreliable; the guidelines do not address how research questions should shape review procedure or specify meta-analysis mechanics in detail; most software-engineering reviews end up qualitative because primary-study reporting is too inconsistent to support meta-analysis.

## Systematic mapping study

The default conduct methodology when a question's shape does not point elsewhere, because it is the one methodology here that never asks the agent to judge a source's quality, only to find and classify what exists.

**Steps:** define research questions, conduct the search, screen for relevance, keyword abstracts into a classification scheme (cluster keywords into candidate categories, sort every paper into the scheme, updating the scheme as sorting proceeds; fall back to introduction and conclusion when an abstract is too sparse), extract data and produce the map (Petersen, Feldt, Mujtaba & Mattsson, 2008).

**Inputs:** a research question broad enough to structure a field rather than answer one narrow claim.

**Output:** a systematic map, a populated classification scheme with frequency counts, typically a two-axis bubble plot.

**Fits:** "what exists, and how broad or varied is it" questions, structuring a field broadly and shallowly. The authors recommend using a mapping study first, then a focused review.

**Failure modes named by the authors:** classification is judgment-based; one cited study found most papers of a given claimed type were actually misclassified; restricting the sample to only methodologically rigorous studies risks an incomplete picture, since rigor is unevenly distributed across a field's sub-areas.

## Snowballing

**Steps:** fix a tentative start set via inclusion and exclusion criteria; backward snowballing screens each included paper's reference list (title, venue, citation context) before full-text screening of candidates; forward snowballing runs citation tracking in parallel using the same screening steps; finalize a paper's inclusion or exclusion before using it for further snowballing, rolling back if it is later excluded after being used; stop once an iteration finds no new papers in either direction (Wohlin, 2014).

**Inputs:** a start set sized to the breadth of the area, drawn from multiple publishers, research communities, years, and authors, with keywords and synonyms taken from the research question.

**Output:** an extended paper set, plus a citation matrix and publication timeline as coverage sanity-check artifacts.

**Fits:** "how do I find everything connected to a paper already known to be relevant" questions. A search-expansion technique run inside another literature-based methodology.

**Failure modes named by the author:** heavy dependence on start-set quality; a non-decreasing rate of new-paper discovery across iterations signals a missed citation cluster and warrants a fresh database search with synonyms; confirmation bias when the researcher already knows the seed study before replicating it. A database search alone is "no better than the search string used," which is why the author frames snowballing as a complement to database search, not a replacement.

## Grey-literature review

**Steps:** Plan (state the need, set the goal, write research questions), Conduct (search, select sources through inclusion and exclusion, assess quality, extract data, synthesize), Report (match the write-up to its audience) (Garousi, Felderer & Mäntylä, 2019).

**Inputs:** a seven-question inclusion checklist decides whether grey literature belongs in the run at all: is the subject too new or complex for formal literature alone, is formal literature thin or low-quality or lacking consensus, is contextual or practitioner information important, is the goal to validate or challenge practice rather than research. One "yes" is enough to include grey literature.

Every candidate source, formal or grey, is classified into one of three tiers by outlet control: tier one (books, magazines, theses, government reports, white papers), tier two (annual reports, news articles, videos, Q&A sites, wikis), tier three (blog posts, presentations, emails, social posts). An eight-criterion instrument then scores every source: authority of the producer, methodology, objectivity, date, position relative to other sources, novelty, impact, and outlet tier, summed into a score recorded beside the finding. No source is excluded on score. A specialist's blog can score in the lowest tier and still be admitted; the score travels with the finding for a human to weigh case by case.

**Output:** a synthesis spanning formal and grey sources, each carrying its tier and score.

**Fits:** "what do practitioners actually say or do, beyond published research" questions, where formal literature alone is sparse or contested. The authors name where it does not fit: mature, bounded academic topics such as formal methods or mathematics, where formal literature is already sufficient on its own.

**Failure modes named by the authors:** grey-literature quality is more diverse and more laborious to assess than formal literature; impact metrics such as shares and comments can be gamed; search results are ranked by an opaque engine and evidence quality declines quickly deeper in the results; grey sources often omit the methodological detail needed for meta-analysis; vendor or vested-interest bias needs an explicit check; the authors call their own guidelines empirically unvalidated.

## Technology landscape / comparative evaluation

Grounded in DESMET (Kitchenham, Linkman & Law, 1997), a peer-reviewed methodology for evaluating and comparing software-engineering methods and tools. A second, independent peer-reviewed line answers the narrower case of choosing among software packages specifically: Jadhav & Sonar's systematic review of package evaluation and selection methodologies (2009). The two are listed beside each other rather than merged, since neither source unifies both questions (methods and tools in general, packages specifically) into one methodology.

**Steps:** pick an evaluation mode from DESMET's nine named types by the criteria it supplies for the case at hand: quantitative experiment, quantitative case study, quantitative survey, feature analysis in screening, case-study, or experiment mode, qualitative effects analysis, or benchmarking. Where a formal experiment or survey cannot be run (no valid control and treatment to isolate, or the technology is too new for a survey), fall back to case-study-based feature analysis: select relevant features, evaluate them through documentation review and tool trials, and hold a sufficient degree of objectivity throughout.

**Inputs:** a defined set of candidate methods, tools, or packages, and the criteria the comparison cares about.

**Output:** a scored or narrative comparison across the candidates, with the evaluation mode itself named and justified.

**Fits:** "which of several concrete options should I pick" questions.

The ThoughtWorks Technology Radar is a format precedent for presenting a comparison, quadrants by topic and rings by adoption recommendation, not a methodology of its own: the publisher states its own process represents a reasonable sample, not a comprehensive or systematic survey of the market, and its own guidance warns it should not be confused with a technology lifecycle assessment tool.

**Failure modes named by the authors:** DESMET's most rigorous modes need a controllable process, a department able to hold development steady enough for valid results, which is harder in loosely controlled or agile settings; weight elicitation in a multi-criteria comparison is unstable across raters and criteria sets, which is why a sensitivity analysis on weights and scores is a required step, not an optional check.

## Repository mining

**Steps:** run an exploratory survey to surface candidate problems; quantitatively analyze a repository-metadata snapshot; manually inspect a random, confidence-sized sample of repositories, since metadata alone cannot separate real projects from toy or dead ones; re-examine prior mining studies against the perils found, to show they create concrete validity threats (Kalliamvakou, Gousios, Blincoe, Singer, German & Damian, 2014).

**Inputs:** a repository-hosting platform's metadata or API, filtered before analysis: recent and balanced commit or pull-request activity, more than two committers or authors, and a check for bot-like commit-rate outliers.

**Output:** descriptive or trend claims about language use, tool adoption, or contribution size, triangulated with qualitative data such as surveys or interviews when the claim is an abstract construct like "success" or "collaboration intensity."

**Fits:** "how does an existing system, API, or codebase actually behave" questions. An empirical study of artifacts.

**Failure modes named by the authors:** a repository is not a project, forks must be unioned with their base repository; many repositories are personal, toy, or inactive; most pull requests are never merged even when nominally accepted; platform semantics change over time and only public activity is visible; a dataset built on a third-party mirror of the platform's API inherits that mirror's own best-effort gaps rather than the platform's full data.

## Reporting standard

PRISMA (Page et al., 2021) is a checklist for writing a review up: Title, Abstract, Introduction, Methods, Results, Discussion, and Other Information, plus a flow diagram. Its own authors state it explicitly, PRISMA is "not intended to guide systematic review conduct," and that judging methodological quality is a separate instrument's job.

**Pairs with:** a conduct methodology from above, most often the systematic literature review or the scoping review through its PRISMA-ScR extension. PRISMA reports the shape of a review that was already run through a conduct methodology; naming PRISMA alone as "the methodology" leaves nothing to actually run.

**Failure modes named by the authors:** evidence for which checklist-adherence strategies actually work is thin; the people affected by the reviews the checklist covers were not involved in developing it; the survey behind the checklist had roughly a fifty percent response rate; where a piece of information appears in the report is explicitly not prescriptive, only that it appear somewhere.

## Protocol registration

A pre-commitment format that locks in a conduct methodology's question, search strategy, inclusion and exclusion criteria, and analysis plan before execution starts, so a dated audit trail of any later amendment can be checked afterward.

**Registries:** PROSPERO (University of York) accepts reviews with a health-related outcome, spanning health, social care, welfare, public health, education, crime, justice, and international development, registered before data extraction begins; it captures the question in PICO form, the search strategy, eligibility criteria, outcomes, planned analysis, team, funder, and conflicts of interest. It does not accept a general software-engineering review with no health outcome. OSF preregistration is open to any field, including software engineering, and locks the question, hypotheses, design plan, sampling plan, and analysis plan before data collection, with an aligned Generalized Systematic Review Registration template for search strategies and inclusion criteria.

**Where no registry fits:** software-engineering reviews commonly ship a standalone protocol document instead, fixing research questions, search and selection strategy, a data-extraction form with a disagreement-handling process, and threats to validity before the review runs. The protocol's execution artifact, a spreadsheet tracking inclusion decisions and snowballing results, can itself be published and versioned in a repository alongside the paper.

**Failure modes:** a protocol locks in a plan before evidence is seen, so anything not listed in it must later be reported as exploratory rather than confirmatory; a registry's own domain scope can rule a question out entirely, as PROSPERO's health-related-outcome requirement does for most software-engineering questions.

## Choosing a methodology

No established procedure routes a question's shape to a methodology; each methodology states its own fit in isolation. The routing below follows from those individual fit statements.

- What exists, and how broad or varied is it: systematic mapping study (the default), scoping review, or a technology-landscape survey.
- What does the evidence say for or against a specific practice: systematic literature review.
- What exists, but time is short: rapid review, a documented abbreviation of the systematic literature review's six steps; state which steps were abbreviated and how.
- What do practitioners actually say or do, beyond published research: grey-literature review.
- How do I find everything connected to a paper already known to be relevant: snowballing, run inside whichever literature-based methodology above is already underway.
- How does an existing system, API, or codebase actually behave: repository mining, an empirical study of the artifact.
- Which of several concrete options should I pick: technology landscape and comparative evaluation, grounded in DESMET.

When no shape above fits, use the systematic mapping study. State the methodology chosen, by name, in the research document.

**Two cautions on the reliability check's standing:**

- Choosing a methodology never turns off the reliability check. Every finding still carries its mechanical marks (evidence type, retraction status, preprint status, citation count, convergence) whether or not the chosen methodology's own steps include a quality-assessment stage. The mapping study skips quality assessment by design; the marks still get recorded on everything it produces, because marking is mechanical, not a quality judgment a methodology could opt out of.
- Refusing the grade never turns off the reliability check either. The five marks get recorded on every finding regardless of whether grading was allowed or refused; refusal switches off only the extra step of weighing evidence type as a grade, not the marks themselves.
