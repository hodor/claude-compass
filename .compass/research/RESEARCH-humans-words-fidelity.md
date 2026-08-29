---
title: "Keeping the Human's Words: Field Evidence, Human Disciplines, and LLM Techniques for Verbatim Fidelity"
type: research
status: complete
confidence: high
area: methodology
tags: [verbatim, capture, verbosity, transcription, in-vivo-coding, prompting, faithfulness]
created: 2026-08-29
updated: 2026-08-29
author: researcher-consolidation
summary: "verbosity and paraphrase infidelity are documented, mechanistic LLM failures; every discipline that must keep source words uses the same grammar (verbatim layer + bracketed insertions + speaker sign-off); positive extract-and-quote instructions beat do-not-paraphrase prohibitions"
depends_on: ["[[SPEC-021-capture-in-the-humans-words]]"]
---

# Keeping the Human's Words

## Question

[[SPEC-021-capture-in-the-humans-words]]: Compass's interview skills synthesize what the human dictates into agent prose, and the human feels unheard. Is AI verbosity/paraphrase infidelity a documented problem, how do disciplines whose craft is preserving source words operate, and which LLM instruction patterns actually preserve wording? Three researchers ran in parallel; full findings follow the synthesis verbatim.

## Synthesis

**The complaint is documented fact, at the mechanism level, on both halves.**

- Verbosity is trained in: RLHF reward models and DPO systematically prefer longer responses regardless of quality; verbosity also correlates with being wrong, not just long. The bias is heterogeneous and shrinking in frontier judges - one 2026 study finds Claude-family judges actually prefer shorter - but the training-side pressure is real literature, not vibes.
- Paraphrase infidelity is its own failure class, independent of verbosity: AI notetakers hallucinate quotes and misattribute speakers; Whisper fabricates whole sentences from silence; an LLM "cleanup" pass over a transcript adds a second, independent hallucination layer; newsrooms have had firings and suspensions over AI-altered quotes, and newsroom policy now warns that even benign grammar cleanup silently alters meaning. Mechanistically, LLMs silently normalize typos and disfluencies via subword merging and drop/alter tokens in long copies ("over-squashing") - the "Permis -> any other AI agent tool" incident is this class, not carelessness.
- Extraction beats abstraction, measurably: extractive summarization (copying source spans) is consistently more faithful than abstractive across multiple papers, and grounded-generation research shows attribution works best when source spans are selected BEFORE generating. Anthropic's own docs prescribe quote-word-for-word-first grounding; OpenAI's meta-prompting guidance includes an explicit "preserve user content" directive.

**Every human discipline that must keep source words converged on the same operational grammar:**

1. **A verbatim layer distinct from the synthesis layer.** Court reporting, oral history, AI notetakers (transcript vs summary, summaries citing segment IDs), Dovetail (every insight traces to a timestamped clip). The summary may exist, but it must point back at unaltered source.
2. **The speaker's words carry the analysis where possible.** Grounded theory's in-vivo coding makes the participant's exact phrase the code itself; UX personas require a real quote; Wikipedia renders POV material only as attributed quotation. The operational test is WHO speaks ("does this use the speaker's words or the researcher's?"), not "is it accurate".
3. **Insertions are bracketed, never blended.** [sic], [unclear: X], (ph), bracketed editorial insertions, ellipses - one shared convention across journalism, court reporting, oral history: anything the writer added is visibly the writer's. "Flag, don't fix" is the transcription-industry rule for uncertain words - exactly the opposite of substituting a generic.
4. **Cleaning is a declared tier, not a judgment call.** Transcription's true/clean/intelligent verbatim tiers differ only in which speech noise is dropped; the discipline is to pick one tier, state what it removes, and never mix. Filler/stammer removal is sanctioned (clean verbatim); grammar and word choice are not.
5. **The speaker signs off.** Member checking, oral history's narrator-holds-final-say, requirements engineering's validate-against-the-original-utterance loop (the named RE failure mode is the analyst silently translating stakeholder language into solution language - Compass's exact defect).
6. **The one deliberate inversion proves the rule:** conference interpreting drops literal wording for sense - and even there, legal/court settings push back to verbatim the moment consequences attach to specific words.

**For the fix itself (instruction-level facts):**

- Positive phrasing wins: "copy the human's sentences exactly" is measurably easier to enforce than "do not paraphrase" - negative instructions that fight a model's default behavior comply worst; Anthropic's own guidance says phrase positively.
- Even frontier models fail literal contiguous quoting on request, so the design must tolerate near-verbatim assembly and make the human's review (sign-off) the backstop - which Compass's approval gate already is.
- A relevant caution for Compass's own style rules: "be concise" instructions measurably increase hallucination on ambiguous/factual topics (task-dependent, doesn't hold for structured reasoning). Brevity pressure belongs on the agent's own prose, not on capture content - which is exactly SPEC-021's boundary.

Full findings, verbatim, per axis below.


## Axis: Field evidence (rs-verbosity-field)

Axis: field evidence for SPEC-021. No design recommendations below.

### Finding 1: RLHF reward models systematically prefer longer responses regardless of quality
Confidence: High
Evidence: Singhal et al. 2023, "A Long Way to Go: Investigating Length Correlations in RLHF" (cited as the foundational study in both papers below); FiMi-RM, arxiv.org/abs/2505.12843 (also ACL 2026, aclanthology.org/2026.acl-long.133); "Mitigating Length Bias in RLHF through a Causal Lens," arxiv.org/abs/2511.12573. Human annotators in RLHF pipelines display a preference for longer answers, which incentivizes PPO/DPO optimization toward length independent of content quality ("reward hacking").

### Finding 2: DPO training conflates response length with response quality during reward over-optimization
Confidence: High
Evidence: "Disentangling Length from Quality in Direct Preference Optimization," arxiv.org/pdf/2403.19159. Reward over-optimization (expected reward keeps rising while human-judged quality degrades) is confirmed both analytically and in user studies, with increased verbosity identified as the visible symptom.

### Finding 3: LLM-as-judge verbosity bias is documented since 2023 but is heterogeneous and declining in frontier judges
Confidence: Medium
Evidence: Zheng et al. 2023 (MT-Bench) first identified position and verbosity bias in LLM judges. A 2026 large-scale study across 21 judges / ~541,000 judgments ("Reliability without Validity," arxiv.org/html/2606.19544v1) finds verbosity-bias scores below 0.011 for all judges tested, versus 20-40% reported in 2023-era literature. A separate 2026 study ("Judging the Judges," arxiv.org/pdf/2604.23178) finds the bias is not uniform: Gemini Pro/Flash and Llama show classical verbosity preference (+0.24 to +0.44), GPT-4o is neutral (-0.04), and Claude prefers *shorter* responses (-0.12).

### Finding 4: Verbosity correlates with being wrong, not just with being long
Confidence: Medium
Evidence: "Verbosity ≠ Veracity: Demystify Verbosity Compensation Behavior of Large Language Models," arxiv.org/pdf/2411.07858 (also ACL 2025 workshop version, aclanthology.org/2025.uncertainlp-main.14.pdf). Studied 14 LLMs (GPT, Claude, Gemini, Llama, Gemma, Mistral families); all models display "verbosity compensation" - producing longer answers when less certain/correct - with open-source models averaging 39.80% verbose responses vs. 28.96% for closed-source models.

### Finding 5: Length alone measurably swings automatic win-rate evaluations
Confidence: High
Evidence: "Length-Controlled AlpacaEval," arxiv.org/abs/2404.04475. On AlpacaEval 2.0, the baseline win rate (50%) rises to 64% when the model is prompted to give maximum detail, and falls to 23% when prompted to be as concise as possible, on the same underlying content quality. This motivated the length-controlled (regression-debiased) win-rate metric, which raised Spearman correlation with Chatbot Arena from 0.94 to 0.98 and cut length-gameability from ~21% to ~6%.

### Finding 6: Instructing models to "be concise" measurably increases hallucination on ambiguous/factual topics
Confidence: High
Evidence: Giskard (Paris), May 2025 study, widely covered (TechCrunch and others). Tested GPT-4o, Mistral Large, and Claude 3.7 Sonnet: "when forced to keep it short, models consistently choose brevity over accuracy," and even prompts as mild as "be concise" reduced models' willingness to debunk false premises, because rebuttals require space to state and refute the false claim.

### Finding 7: The concision-hurts-accuracy effect is task-dependent, not universal
Confidence: Medium
Evidence: ConciseHint paper, arxiv.org/pdf/2506.18810. On Qwen3-4B / GSM8K (structured math), a "Be concise" system prompt scored 94.60% vs. 94.81% baseline accuracy while cutting token usage from 2381 to 1597 - effectively flat accuracy with shorter output. The Giskard degradation (Finding 6) was concentrated in ambiguous/misinformation-debunking tasks, not well-structured reasoning tasks.

### Finding 8: Vendors themselves treat blanket "be concise" instructions as risky and carve out exceptions
Confidence: Medium
Evidence: Simon Willison's documentation of an apparent hidden system-prompt line in OpenAI's GPT-5 API: "Note: For ambiguous, technical, or safety-critical topics, I may add brief clarifications even when being concise" (simonwillison.net/tags/system-prompts/). OpenAI's own developer docs (for the verbosity-parameter migration) advise checking whether legacy "Be concise" instructions are still needed, since they "can sometimes make responses too brief," and recommend the dedicated `text.verbosity` parameter instead of a blanket instruction.

### Finding 9: Anthropic's own product (Claude Code) hardcodes an explicit terseness rule in its system prompt
Confidence: High
Evidence: Leaked/documented Claude Code system prompt (github.com/x1xhlol/system-prompts-and-models-of-ai-tools, Anthropic/Claude Code/Prompt.txt): "You MUST answer concisely with fewer than 4 lines (not including tool use or code generation), unless user asks for detail," plus an explicit instruction to minimize output tokens while maintaining accuracy - i.e., Anthropic treats default verbosity as a defect to be suppressed by instruction, in its own flagship coding product.

### Finding 10: Community pushback against chatbot verbosity/preamble is longstanding and organized around shared custom instructions
Confidence: Medium
Evidence: Andrew Chen's viral post/thread (andrewchen.com/ai-verbose-repetition-sorry, LinkedIn cross-post with 255+ comments), sourced from a Reddit user's (u/m4rM2oFnYTW) custom-instructions template banning filler phrases ("sorry," "apologies," AI self-disclosure) and demanding the model get to the point. This documents a standing practitioner-level mitigation: explicit negative-instruction lists targeting specific verbose habits rather than a single "be concise" directive.

### Finding 11: AI meeting notetakers are documented to hallucinate quotes and misattribute statements to the wrong speaker
Confidence: Medium
Evidence: Wikipedia, "AI notetaker" (en.wikipedia.org/wiki/AI_notetaker), states ethical concerns include the tool hallucinating and misrepresenting what was said. Careful Industries' "Nine risks caused by AI notetakers" (careful.industries/blog/2025-11-nine-risks-caused-by-ai-notetakers) and related analyses report state-of-the-art speaker-diarization error rates of 11-13% (mostly crosstalk), which cascade into action items and quotes attributed to the wrong person; independent testing cited in the same coverage found speaker misattribution reaching ~30% in multi-person calls and summary accuracy dropping to 60-70% under noise or accents.

### Finding 12: Whisper (ASR) fabricates entire sentences from silence or noise, not just mishears words
Confidence: High
Evidence: "Careless Whisper: Speech-to-text Hallucination Harms," arxiv.org/html/2402.08021v2 (also covered by Montreal AI Ethics Institute and Healthcare Brew). Roughly 1% of Whisper transcriptions contained hallucinated phrases/sentences absent from the underlying audio; 38% of sampled hallucinations included explicit harms (fabricated violence, false associations, invented authority). These hallucinations did not occur in the audited commercial alternatives (Google, Amazon, AssemblyAI, RevAI). Silence at the start/end of audio was a direct trigger. Whisper-based transcription is in clinical use (~30,000 clinicians, ~7 million medical visits via one vendor, per the same reporting), raising the stakes of fabricated content in transcripts.

### Finding 13: Using an LLM to "clean up" an ASR transcript introduces a second, independent hallucination risk
Confidence: Medium
Evidence: "Fewer Hallucinations, More Verification: A Three-Stage LLM-Based Framework for ASR Error Correction," arxiv.org/pdf/2505.24347. Directly applying an LLM to correct ASR output "may lead to the modification of correct text" - the cleanup step can introduce new errors, not just fix old ones, motivating pre-detection and verification stages. Separately, research on Answer Error Rate (AER) vs. Word Error Rate (WER) finds AER (semantic-level divergence in downstream task output) exceeds raw WER by 10-30 percentage points, meaning low WER can mask meaning-altering errors that traditional transcription metrics do not catch.

### Finding 14: AI-generated paraphrase/summarization has produced real newsroom misquote incidents and led to firings/suspensions
Confidence: High
Evidence: Multiple independent, named incidents: The New York Times published a quote attributed to Canadian opposition leader Pierre Poilievre that was actually an AI-generated summary of his views, using words he never said (per Columbia Journalism Review's "Did I Really Say That?", cjr.org/tow_center/did-i-really-say-that-dutch-journalist-ai-fabricate-quotes-vandermeersch-mediahuis.php); a Cody Enterprise (Wyoming) reporter resigned after using AI-generated quotes (Wyoming Public Media, wyomingpublicmedia.org/2024-08-16); Danish outlet Berlingske suspended a journalist after AI-fabricated and misquoted sources appeared in a published article, prompting removal of a full section and correction of two quotes. Press Gazette maintains a live tracker of such incidents (pressgazette.co.uk/publishers/digital-journalism/ai-journalism-mistakes/).

### Finding 15: Newsroom policy explicitly warns that even "benign" AI cleanup (grammar, typos) can silently alter quote meaning
Confidence: High
Evidence: The Globe and Mail's updated AI guidelines (theglobeandmail.com/standards-editor/article-the-globe-has-updated-its-newsroom-ai-guidelines): "Even seemingly innocuous requests like cleaning up typos and grammar can introduce errors, and summarization can combine ideas in subtle ways that alter the meaning of a passage or quote. This risks our reputation and the accuracy of our reporting." Some outlets have adopted stricter language still: "AI tools must not be used to generate, extract, or summarise material that is then attributed to a named source, whether as a direct quote, a paraphrase, or a characterisation of someone's views" (per the same source roundup).

### Finding 16: Extractive summarization (copying source text) is measurably more faithful than abstractive (paraphrasing) summarization
Confidence: High
Evidence: "The Extractive-Abstractive Spectrum: Uncovering Verifiability Trade-offs in LLM Generations," arxiv.org/pdf/2411.17375; "Extractive Summarization via ChatGPT for Faithful Summary Generation," arxiv.org/pdf/2304.04193. Extractive methods directly select source sentences, producing summaries that are faithful by construction; abstractive methods paraphrase and are measurably more prone to introducing unsupported content, with unfaithfulness correlating with degree of abstraction (n-gram divergence from source) across models. "Extract-then-generate" pipelines are used specifically as a faithfulness-improving technique for LLM summarizers. One caveat: UniSumEval (arxiv.org/pdf/2409.19898) finds this trade-off holds for non-LLM and open-source models but may weaken for strong proprietary LLMs, which can be abstractive without proportional faithfulness loss.

### Finding 17: Product-level mitigation pattern - human-authored anchor text plus visually distinguished, source-traceable AI additions
Confidence: Medium
Evidence: Granola's documented workflow (granola.ai/blog/how-to-take-good-meeting-notes-ai; docs.granola.ai/help-center/taking-notes/ai-enhanced-notes): the human's own typed notes ("jot") guide what the AI enhances with verbatim transcript quotes; the user's original text renders in black, AI-added text renders in gray, and each AI-added note can be traced back to its transcript source via a magnifying-glass lookup. Granola's own marketing specifically calls out reference checks and customer research as cases where "exact quotes matter most."

### Finding 18: Product-level "verbatim quote" AI features are reported unreliable enough to require manual verification
Confidence: Medium
Evidence: Hands-on review of Dovetail's AI auto-highlighting for interview transcripts (per cleverx.com/blog/dovetail-review-2026 and related reviews cited in search results): reported roughly 40-50% success rate identifying truly important passages, with reviewers "spending about the same amount of time reviewing highlights as they would have without AI." Dovetail visually marks AI-contributed content (a distinct icon) so users can tell what the AI added versus what a human tagged, but the vendor's own UI pattern assumes AI quote-pulling needs to be checked, not trusted.

## Axis: Human disciplines (rs-verbatim-practice)

Axis: prior art for verbatim/source-word preservation across disciplines whose craft is turning spoken words into structured documents without losing the speaker's own language. No Compass design recommendation - facts and operational rules only.

### Finding 1: Grounded theory: in-vivo coding uses the participant's exact words as the analytic code itself
Pattern: instead of researcher-generated abstractions ("academic pressure"), the code IS the participant's own phrase ("drowning in deadlines"), placed in quotation marks in the codebook to visually distinguish it from researcher-authored labels.
Confidence: high
Evidence: Johnny Saldana, *The Coding Manual for Qualitative Researchers* (described via https://delvetool.com/blog/invivocoding and https://qualitativeresearchers.com/blog/in-vivo-coding/) - in-vivo codes are one of the most essential first-cycle coding methods, quotation-marked to signal "participant's words, not the researcher's label."

### Finding 2: In-vivo coding is explicitly contrasted with descriptive coding by WHO speaks, not WHAT is captured
Pattern: descriptive coding = researcher's language summarizing the topic; in-vivo coding = participant's language regardless of topic. The operational test practitioners use: "does this code use the researcher's words or the speaker's words?" - not "is this code accurate?"
Confidence: high
Evidence: https://delvetool.com/blog/invivocoding - "descriptive coding tells you what participants talked about; in vivo coding tells you how they talked about it."

### Finding 3: Verbatim transcription has three recognized tiers, distinguished by what speech noise they keep vs. discard, not by accuracy
Pattern:
- True/full verbatim: keeps everything - fillers, false starts, stutters, repeated words, grammar errors, nonverbal sounds. Standard for legal proceedings and close qualitative analysis.
- Clean verbatim: strips fillers ("um," "uh"), false starts, stutters, run-on repetition, coughs, background noise - but preserves the speaker's actual wording, sentence structure, and intent. Standard for most qualitative-research interview transcripts.
- "Intelligent verbatim" / edited transcript (a further, non-universally-agreed tier some vendors use): also fixes grammar, restructures sentences, substitutes words for clarity - at this point it is no longer a word-for-word record.
Confidence: high
Evidence: https://www.rev.com/resources/what-does-clean-verbatim-transcription-mean , https://ticnote.com/en/blog/transcribe-verbatim-guide - worked example: full verbatim "I, um, really like making br-breakfast..." becomes clean verbatim "I really like making breakfast. Eggs are good but pancakes are better."

### Finding 4: The verbatim-tier boundary is not industry-standardized - practitioners are told to specify removal rules explicitly per job
Pattern: because "clean" vs "intelligent" verbatim definitions vary by vendor, the operational discipline is: pick your convention once, state exactly what categories of noise get removed (fillers, false starts, stutters, grammar), and never mix tiers within a single transcript, because a mixed transcript makes it impossible for a reviewer to tell what was removed vs. never said.
Confidence: medium
Evidence: https://ticnote.com/en/blog/transcribe-verbatim-guide , https://subanana.com/en/blog/transcript-formats-verbatim-clean-read

### Finding 5: Member checking closes the loop by having the source person validate the write-up, and has two distinct operational levels
Pattern:
- Transcript review (lower level): return the raw or partial transcript, ask only "did I get your words right, is anything missing/unclear" - no interpretation requested. Universally recommended, low-risk, but validates fidelity of the record only, not the analysis.
- Interpretation/synthesized review (higher level): return the researcher's derived output - themes, a findings draft, or specific quotes attributed to the participant - and ask whether the interpretation still resonates. This is the version that validates the analytic leap, not just the record.
Confidence: high
Evidence: Lincoln & Guba (1985) origin; Birt et al. 2016 "Synthesized Member Checking," *Qualitative Health Research* (via https://heymarvin.com/resources/member-checking-in-qualitative-research and https://en.wikipedia.org/wiki/Member_check).

### Finding 6: BABOK formalizes "Glossary" as a distinct elicitation technique to fix shared vocabulary from stakeholder language
Pattern: the Glossary technique (BABOK v3, Ch.10, technique 10.23) exists specifically to lock terms as stakeholders use them, so the same word means the same thing across the initiative - it is listed alongside Data Dictionary and Concept Modelling as vocabulary-oriented techniques, separate from the requirements themselves.
Confidence: medium (technique's existence and purpose confirmed; exact BABOK wording not directly quoted from primary text)
Evidence: https://www.iiba.org/knowledgehub/business-analysis-body-of-knowledge-babok-guide/4-elicitation-and-collaboration/ ; BABOK Guide v3 Chapter 10 technique list.

### Finding 7: BABOK explicitly separates "elicitation" from "gathering" because most requirements knowledge is never documented anywhere before the interview
Pattern: BABOK deliberately chose the word "elicitation" over PMBOK's "collect requirements" - the operational implication is that the analyst must draw out tacit knowledge through interactive technique, not passively receive a pre-written document. This framing is the root justification for verbatim-adjacent techniques (glossaries, direct quoting) elsewhere in the discipline.
Confidence: medium
Evidence: BABOK Guide v3, quoted via https://aoteastudios.com/2012/01/the-babok-requirements-elicitation/ - "It is the drawing forth or receiving of information from stakeholders or other sources."

### Finding 8: Requirements engineering names a specific, well-documented failure mode - stakeholders speak in solution language, and analysts silently re-translate meaning during write-up
Pattern: business stakeholders describe outcomes/pain points in their own vocabulary; engineers/analysts convert that into data-model or feature language. The named failure: a stakeholder says "we need to see all our customers in one place," an engineer hears a customer-list screen, and six weeks later delivers the wrong thing because the analyst's translation silently substituted a different concept for the stakeholder's actual words. The documented mitigation is a validation loop: elicit, write as a precise requirement, then check back with the stakeholder that the requirement still says what they meant - i.e., verify against the original utterance, not against the analyst's paraphrase of it.
Confidence: medium
Evidence: https://agenticskillset.org/en/topics/business-to-technical-specs/ ; https://reqi.io/articles/transforming-stakeholder-needs-into-requirements ; arXiv:2601.16699 (empirical RE research on articulation barriers between stakeholders and engineers).

### Finding 9: AP, NYT, and Washington Post style all prohibit altering direct quotations, even to fix grammar
Pattern: the rule is binary, not graduated - a quotation inside quotation marks must be the exact words uttered in that form. AP: "never alter quotations even to correct minor grammatical errors or word usage." NYT: "The Times does not 'clean up' quotations." If a quote is in doubt, the prescribed action is not to fix it but to drop it or ask the speaker to clarify.
Confidence: high
Evidence: AP Stylebook guidance summarized via https://writingexplained.org/ap-style/ap-style-quotes and https://www.ragan.com/ap-style-quotation-marks/; NYT/WaPo policy cited via https://writersguide.substack.com/p/the-mechanics-of-attribution-quoting.

### Finding 10: Journalism's actual mechanism for handling "messy" speech is not cleaning the quote in place - it is choosing a different quoting mode (paraphrase, partial quote, or [sic]) around an unaltered quote
Pattern: three sanctioned moves, none of which touch the quoted words themselves:
- Paraphrase entirely (no quotation marks) when the literal phrasing is not needed.
- Partial/fragmentary quoting - quote only the clean, unambiguous portion, paraphrase the rest.
- Full direct quote plus "(sic)" appended to flag a grammatical error as the speaker's, not the transcriber's.
Casual minor tongue-slips may be trimmed with an ellipsis, but AP guidance calls for "extreme caution" even here.
Confidence: high
Evidence: https://newsliteracymatters.com/2019/10/23/q-should-a-journalist-use-direct-quotations-with-someone-whose-english-is-poor-or-should-they-clean-up-the-quotes/ ; https://slate.com/news-and-politics/2010/03/do-newspapers-ever-correct-a-speaker-s-broken-english.html (the 2007 Clinton Portis case, where one Washington Post reporter quoted verbatim and another normalized the same remarks, triggered an ombudsman ruling against altering quotes).

### Finding 11: [sic] is an authenticity marker, not a correction - it tells the reader "this error is the source's, not the transcriber's"
Pattern: sic is inserted in brackets immediately after a reproduced error, in italics, to certify the error was copied faithfully rather than introduced by transcription mistake. Usage guides caution it should function as a reader aid, not as editorial mockery or disagreement.
Confidence: high
Evidence: https://en.wikipedia.org/wiki/Sic ; https://editingandindexing.com/altering-quotes/ - oral history convention combines sic with a bracketed correction in the same bracket, e.g. "Clay Spohm [sic Spohn -Ed]."

### Finding 12: Square brackets and ellipses have a fixed grammar for marking editorial intrusion into quoted speech, distinct across contexts
Pattern:
- Square brackets mark ANY words added by someone other than the speaker - corrections, clarifications, grammatical adjustments (e.g., verb tense) needed to fit the quote into surrounding prose.
- Ellipses mark omission of original material.
- When the source speech itself contains natural pauses/ellipses (faltering speech), the transcriber's OWN omission-ellipsis must be additionally bracketed - "[...]" - to distinguish "I cut this" from "the speaker paused here."
- Across academic quoting, brackets mark changes to a fixed original text; across oral history and court reporting, brackets instead mark the transcriber's own voice intruding on a verbatim record (annotations, inaudible-flags, guesses) while the verbatim record itself stays untouched.
Confidence: high
Evidence: https://ww1.up.edu/learningcommons/tutoring-services/writing-center/resources/ellipses-brackets-and-sic.html ; Columbia Center for Oral History Research Transcript Style Guide (2022), https://static1.squarespace.com/static/575a10ba27d4bd5d7300a207/t/621cf621281bcd63d23a3dde/1646065186028/CCOHR+Transcript+Style+Guide+2022.pdf.

### Finding 13: Oral history's stated "fidelity principle" is to change as little as possible, including grammar and speech patterns, with the narrator holding final sign-off
Pattern: style guides (Columbia CCOHR, Margaret Walker Center) instruct transcribers to represent the narrator's actual word choice, grammar, and speech patterns accurately; any "significant departure from the recording" must be bracket-marked as an editorial insertion, not silently smoothed. The narrator (source speaker), not the transcriber or researcher, makes the final call on whether a departure is acceptable when reviewing the transcript.
Confidence: high
Evidence: Margaret Walker Center Oral History Transcription Style Guide, https://www.jsums.edu/margaretwalkercenter/files/2024/10/Margaret-Walker-Center-OH-Transcription-Style-Guide.pdf ; Columbia CCOHR guide (above).

### Finding 14: Oral history's handling of unclear speech uses two distinct bracket idioms, not a single "unclear" catch-all
Pattern:
- Genuinely inaudible speech: bracket the word "inaudible" in place of the unintelligible segment - e.g., "Our first home was in east Portland on [inaudible] Street."
- Speech that is heard but uncertain (a name, technical term): bracket the guessed word followed by "(ph)" for phonetic guess - e.g., "[a quick brown fox (ph)]." This is distinct from [sic], which marks a confirmed error rather than an uncertain hearing.
Confidence: high
Evidence: Smithsonian Archives of American Art, Oral History Program Style Guide Section 2, https://www.aaa.si.edu/documentation/oral-history-program-style-guide-section-2-treatment-of-text.

### Finding 15: Court reporting separates the verbatim speech record from the reporter's own annotations using the same bracket/parenthetical device, but the underlying record is never abridged for readability
Pattern: parenthetical notations (in parentheses or brackets) are explicitly the court reporter's own words describing an event ("(witness nods)", swearing-in language) - never a rendering of anything a participant said. Every effort must be made to produce a COMPLETE transcript; a reporter may only mark a passage "indiscernible"/"inaudible" when transcription is genuinely impossible, not for readability.
Confidence: medium
Evidence: Texas Judicial Branch Uniform Format Manual (court reporters certification), https://www.txcourts.gov/jbcc/court-reporters-certification/statutes-rules-and-resources-for-court-reporters-firms/uniform-format-manual/ ; Indiana Courts Appendix A Standards for Electronic Transcripts, https://rules.incourts.gov/Content/appellate/appendix-a/current.htm.

### Finding 16: UX research tooling (Dovetail) operationalizes verbatim preservation as forced traceability from every derived claim back to a timestamped source clip
Pattern: highlights made on a transcript become individually searchable, timestamped clips; AI-generated themes/insights are required to trace back to the source evidence that produced them, and answering a research question surfaces the original clip playing inline rather than only a written summary. The stated purpose is turning "the research team said so" into "here is the participant, here is the moment, here is the evidence" - i.e. the deliverable is structurally required to carry a pointer to the raw utterance, not just a paraphrase of it.
Confidence: medium
Evidence: https://docs.dovetail.com/help/highlights ; GitLab UX Research handbook page on Dovetail usage, https://handbook.gitlab.com/handbook/product/ux/dovetail ; Dovetail AI Projects product page, https://dovetail.com/product/ai-projects/.

### Finding 17: UX personas conventionally embed one verbatim quote, sourced from actual interviews, functioning as a mnemonic anchor for the synthesized profile
Pattern: persona templates include a short quote in the persona's own voice pulled directly from interview data, distinct from the surrounding synthesized (paraphrased) narrative sections of the same document - the quote is explicitly called out as needing to be real, not invented, because "proto-personas" built without underlying research/quotes are flagged as unreliable for design decisions.
Confidence: medium
Evidence: https://www.brandvm.com/post/user-persona-template ; IxDF literature on persona design, https://ixdf.org/literature/article/user-persona-for-mobile-design-and-development-a-winning-technique-for-great-ux.

### Finding 18: Wikipedia requires every direct quotation to carry an inline citation to a source that directly supports it, and treats quotation as a sanctioned way to include point-of-view material without it becoming the encyclopedia's own voice
Pattern: "Material challenged or likely to be challenged, and all quotations, must be attributed to a reliable, published source" - quotations are explicitly named as a way to comply with the No Original Research policy, on the condition they are attributed and used carefully. Biased/POV language must be rendered as an attributed quote rather than stated in Wikipedia's own voice - i.e., the discipline uses verbatim quoting as the escape hatch for including a claim the encyclopedia cannot itself assert.
Confidence: high
Evidence: https://en.wikipedia.org/wiki/Wikipedia:Verifiability ; https://en.wikipedia.org/wiki/Wikipedia:Quotations ; https://en.wikipedia.org/wiki/Wikipedia:No_original_research.

### Finding 19: Conference interpreting's dominant professional norm is the opposite of verbatim fidelity - it favors sense-for-sense meaning transfer, and explicitly de-prioritizes literal wording
Pattern: the "Paris school" (Seleskovitch, ESIT) taught that fidelity is achieved only through interpreting de-verbalized MEANING, not word-for-word transcoding - summarized in the literature as the paradox "in order to be faithful to the speaker, the interpreter must betray them" (Jones, 2002). This is the one practice surveyed where the operational rule runs counter to the others: the source's literal words are treated as disposable so long as intent, tone, and communicative effect survive.
Confidence: medium
Evidence: https://www.researchgate.net/publication/313824428_Variability_in_the_perception_of_fidelity_in_simultaneous_interpretation ; ISO 23155 (conference interpreting services) and ISO 20108 (quality/accuracy of spoken language interpretation) referenced via https://atlasls.com/iso-standards-for-conference-interpreting/.

### Finding 20: Interpreting fidelity judgments are empirically unreliable even among trained assessors, and legal/court interpreting settings push back toward verbatim over sense-for-sense
Pattern: Daniel Gile's study had professional interpreters, students, and other assessors rate the same interpreted speech for fidelity and found high intra-group variability, interpreters rating more leniently than non-interpreters, and no clear correlation between counted errors/omissions and overall fidelity scores - i.e., "faithful" is not a stable, independently checkable property under this norm. By contrast, legal/court interpreting contexts are noted as pulling toward more literal, verbatim renderings than conference interpreting does, because legal consequences attach to specific wording (e.g., an asylum hearing where a culturally veiled reference must be judged for literal vs. explicit rendering).
Confidence: medium
Evidence: Daniel Gile fidelity-perception study, https://www.researchgate.net/publication/313824428_Variability_in_the_perception_of_fidelity_in_simultaneous_interpretation ; NCIHC National Code of Ethics, https://www.ncihc.org/assets/z2021Images/NCIHC%20National%20Code%20of%20Ethics.pdf.

### Contradictions
- Finding 3/9/13 (verbatim disciplines: transcription, journalism, oral history, court reporting, Wikipedia) all treat the speaker's literal words as the thing to protect, with editorial marks (brackets, ellipses, sic) reserved for the editor's own visible intrusions. Finding 19/20 (conference interpreting) inverts this: the professional norm explicitly sacrifices literal wording to preserve meaning, and treats word-for-word rendering as a form of unfaithfulness ("betrayal"). These are not reconcilable into one universal rule - the disciplines diverge by whether the record needs to be replayable as evidence (transcription/court/journalism/Wikipedia: yes) or needs to be understood in real time across languages (interpreting: no).
- Journalism (Finding 9) categorically bans quote alteration; the qualitative-research and UX disciplines (Findings 3, 4) treat "clean verbatim" - removing fillers/false starts while keeping wording - as the accepted default, not a violation. The difference is what the artifact is for: journalism's quote is evidentiary and publicly attributed to a named individual: any edit is reputational risk. Clean verbatim's transcript is an internal analysis tool where filler removal aids the analyst without changing intent.

### Gaps
- No source directly discussing "the customer's voice" as a named BABOK term was found (BABOK's own term is "Glossary" / "elicitation," not "voice of customer" - that phrase is more QFD/quality-management lineage). Would need direct access to the BABOK v3 PDF text (paywalled/membership-gated on iiba.org) to confirm whether the phrase appears verbatim.
- No primary-source IEEE requirements standard (e.g., IEEE 830/29148) was directly retrieved on paraphrase-vs-verbatim guidance; findings on RE failure modes come from secondary/blog sources (agenticskillset.org, reqi.io) and one arXiv empirical paper, not the standards documents themselves.
- Translation (written, non-interpreting) fidelity norms (e.g., ATA certification standards, "formal equivalence vs dynamic equivalence") were not separately investigated in depth; only conference/simultaneous interpreting was covered per the "if cheap, one more" instruction.

## Axis: LLM techniques (rs-llm-technique)

Axis: which INSTRUCTION patterns reliably make an LLM preserve source wording, for SPEC-021 ("capture documents keep the human's own words").

### Finding 1: Anthropic officially recommends "quote-first" grounding for long documents

Anthropic's own hallucination-reduction guide instructs: for tasks involving long documents (>20K tokens), ask the model to extract word-for-word quotes first, before performing the actual task. The rationale given is that this grounds the response in actual text rather than the model's paraphrase/memory of it, and complements this with a "verify with citations" pattern: have the model find a supporting quote for each claim after generating output, and retract the claim if no quote is found.
Confidence: high
Evidence: https://docs.claude.com/en/docs/test-and-evaluate/strengthen-guardrails/reduce-hallucinations (Anthropic vendor doc, "Reduce hallucinations" guide)

### Finding 2: Claude's Citations API structurally extracts spans rather than asking the model to reproduce them

Rather than prompting the model to type out a quote (which risks drift), Anthropic's Citations feature chunks source documents into sentences and has the model select/point to chunks; the API then extracts `cited_text` directly from the source, so citations are guaranteed to contain valid pointers to the provided text rather than model-typed reproductions. Anthropic's evaluations found this generates citations with higher recall and precision than purely prompt-based ("please quote your source") approaches, and one customer (Endex) reported source hallucinations dropping from 10% to 0% after switching to it.
Confidence: high
Evidence: https://platform.claude.com/docs/en/build-with-claude/citations ; https://claude.com/blog/introducing-citations-api

### Finding 3: Extractive framing is inherently more faithful than abstractive/summarize framing, at a measured scale

Maynez et al. 2020 found hallucinations (content unsupported by or contradicting the source) appeared in over 70% of single-sentence abstractive summaries in their human evaluation, and 64.1% of a BERT-based abstractive model's summaries on XSUM contained hallucinations; Falke et al. found ~25% of summaries from state-of-the-art abstractive systems contained hallucinated content. Because extractive summarization selects sentences from the source directly, it is faithful by construction, which is the standard cited reason to prefer "extract" over "summarize/rewrite" framing for fidelity-critical tasks.
Confidence: high
Evidence: arXiv:2005.00661 (Maynez et al., "On Faithfulness and Factuality in Abstractive Summarization")

### Finding 4: Extraction is not perfectly safe either -- removing context from an extracted span can itself mislead

A counter-finding: "Extractive is not Faithful" (Zhang et al. 2022) shows extracted sentences can still mislead readers when stripped of surrounding context, e.g. through unresolved coreference (a pronoun whose referent was in a now-removed sentence). This means verbatim-extraction instructions should keep enough surrounding context/attribution to avoid meaning loss, not just guarantee word-for-word copying.
Confidence: high
Evidence: arXiv:2209.03549 ("Extractive is not Faithful: An Investigation of Broad Unfaithfulness Problems in Extractive Summarization")

### Finding 5: Even frontier models fail at literal, contiguous verbatim quoting on request

TimeStampEval tested GPT-5 on returning the final three sentences of a passage verbatim (a proxy for exact quoting). Task completion rate was above 90%, but the returned spans were frequently non-contiguous fragments recombined from the reference text rather than an exact contiguous quote. The paper also warns that ASR-style noise in the source (punctuation, contractions, disfluencies) interacts with this failure mode, making "return the exact sentence" requests prone to mismatched or incomplete spans.
Confidence: medium
Evidence: arXiv:2511.11594 ("TimeStampEval: A Simple LLM Eval and a Little Fuzzy Matching Trick to Improve Search Accuracy")

### Finding 6: Verbatim copy failures at the token/digit level are attributed to "over-squashing," and are silent

A paper on verbatim data transcription failures in LLM code generation traces copy errors (digit-level corruption when reproducing long literal sequences) to information "over-squashing," where the influence of many earlier tokens vanishes over a long context. Critically, the paper stresses these errors are silent data corruption: the output looks plausible, executes/reads without error, and passes superficial review while being subtly wrong -- i.e. verbatim-copy failures do not announce themselves.
Confidence: medium
Evidence: arXiv:2601.03640 ("Verbatim Data Transcription Failures in LLM Code Generation")

### Finding 7: LLMs silently "fix" typos/disfluencies via a mechanistic subword-merging behavior, sometimes corrupting meaning

Research shows LLMs often answer correctly on typo-laden input, implying an internal typo-correction behavior; a mechanistic interpretability investigation identified a "subword merging head" that moves information between tokens of the same word when that word is rare or corrupted by a typo, which is the likely mechanism behind silent auto-correction. The correction is sometimes imperfect and can damage downstream fidelity precisely because it happens invisibly rather than being surfaced to the user.
Confidence: medium
Evidence: LessWrong, "Tracing Typos in LLMs" (https://www.lesswrong.com/posts/523bkuMjSjKjG8jn6/tracing-typos-in-llms-my-attempt-at-understanding-how-models)

### Finding 8: Negative ("do not") instructions are measurably harder to enforce than positive ones when they conflict with a model's default behavior

An empirical study of constraint compliance in LLM code generation found a 9.3-percentage-point compliance gap (d=0.55, p<0.001) between constraints that align with the model's default "implementation priors" (99%+ compliance) versus counter-intuitive/negative constraints that conflict with those priors (compliance drops sharply). The authors' interpretation: negative constraints ("do not do X") require actively suppressing an already-activated default pattern, which fails more often than simply specifying the desired positive pattern ("do Y").
Confidence: medium
Evidence: arXiv:2604.07192 ("Compact Constraint Encoding for LLM Code Generation: An Empirical Study of Token Economics and Constraint Compliance")

### Finding 9: Anthropic's own documented advice is to phrase instructions positively, not as prohibitions

Anthropic's stated prompting guidance (cited via a third-party analysis of the official docs) is "tell Claude what to do instead of what not to do" -- i.e. replace "don't summarize/paraphrase" with an explicit statement of the desired action ("copy this section's wording exactly as given"). This is consistent with the "Pink Elephant" framing that negative instructions can paradoxically prime the very behavior being forbidden.
Confidence: medium
Evidence: https://eval.16x.engineer/blog/the-pink-elephant-negative-instructions-llms-effectiveness-analysis (cites Anthropic's official prompting guidance)

### Finding 10: Instruction-position effects on compliance are inconsistent and model-dependent -- no universal "put it at the end" rule

The "lost in the middle" U-shaped retrieval-position effect (Liu et al.) is well established for information retrieval from long contexts, but does not reliably transfer to instruction-following: one scaling study found no consistent relationship between instruction position and compliance rate. A granular compliance benchmark found some model families (Llama, Qwen3, DeepSeek) show a primacy effect (earlier constraints followed more reliably) while others (Mixtral, Gemini, and notably Claude) show a recency effect (later constraints followed more reliably) -- meaning for Claude specifically, placing a verbatim-preservation instruction later/closer to the task is the evidence-backed choice, not earlier.
Confidence: medium
Evidence: arXiv (granular instruction-compliance benchmark, cited in search synthesis; original "lost in the middle" is Liu et al., "Lost in the Middle: How Language Models Use Long Contexts")

### Finding 11: System-prompt vs. user-message placement of an instruction produces divergent compliance depending on model and task type

A controlled experiment found placing an instruction in the user message produced 64% compliance versus 8% in the system prompt and 2% in a tool description for one model (Qwen 2.5-Coder 3B) -- but Claude Haiku 4.5 and Claude Sonnet 4.6 followed the instruction perfectly regardless of placement in the same test. Separately, an agentic-task study found system-prompt placement produced the highest task accuracy, hypothesizing that user-prompt placement causes "over-compliance" (the agent halts/short-circuits rather than continuing). Net: placement effects exist but are not uniform across models, and Claude models in the tested cases were comparatively placement-insensitive.
Confidence: medium
Evidence: cited within search synthesis of position-bias literature (specific experiment source not independently re-verified beyond the search summary; treat placement-insensitivity claim for Claude as single-source)

### Finding 12: IFEval-style instruction-following, including keyword-exclusion (a "do not include X" instruction type), is a recognized benchmark category, but per-type verbatim/quote compliance is not separately published

IFEval (Zhou et al. 2023, arXiv:2311.07911) defines 25 programmatically verifiable instruction types across 541 prompts, one of which is keyword include/exclude ("do not include the following keywords"). Frontier models fail 20-40% of formatting-type instructions in aggregate; GPT-4-class models score ~80% on strict IFEval, smaller models 30-40%. A follow-up, IFEval++, found performance can drop by up to 61.8% under nuanced prompt rephrasing of the same instructions, showing instruction-following is brittle to phrasing even when the underlying model "knows" the rule. No dedicated published breakout exists specifically for verbatim-copy or quote-fidelity compliance as its own IFEval category.
Confidence: medium
Evidence: arXiv:2311.07911 (IFEval); search-cited IFEval++ results

### Finding 13: Shipped AI notetaker products architecturally separate a verbatim transcript layer from a generated summary layer, and ground the summary back onto transcript segment IDs

The documented pattern across meeting-notetaker system designs: store the transcript segments (near-verbatim, speaker-attributed) as the source of truth; derive the summary/recap from that layer rather than storing only the polished summary, because "keep only the derivative and you can never re-derive, re-verify, or answer what exactly was said." A concrete grounding mechanism: the summarization LLM's structured outputs (decisions, action items) must cite the segment IDs/timestamps they derive from, with low-confidence audio explicitly flagged rather than paraphrased confidently -- explicitly framed as a defense against "a fluent summary of things nobody said."
Confidence: medium
Evidence: Vibe Engines system-design writeup, "Design an AI Meeting Notetaker" (https://vibeengines.com/ai-system-design/ai-meeting-notetaker-system-design); Circleback pipeline explainer (https://circleback.ai/blog/how-ai-meeting-notes-work)

### Finding 14: Established transcription-industry convention for uncertain/noisy source material is "flag, don't fix" using bracketed markers, never silent guessing

Multiple professional transcription style guides converge on the same pattern: `[inaudible HH:MM:SS]` for undecipherable speech, and a distinct `[word?]` / `[?flagged word?]` marker for a low-confidence best guess -- explicitly not to be used interchangeably. The stated rationale (from legal-transcription guidance) is that "a marked gap is always better than an incorrect word," because a wrong silent guess "becomes part of the official record." Recommended workflow for ASR cleanup: normalize text, restore punctuation, then explicitly verify proper nouns/terms flagged as uncertain, rather than letting the LLM correct them inline.
Confidence: high (converges across 5+ independent professional transcription vendors/guides)
Evidence: Rev Transcription Style Guide v4.0.2 (https://cf-public.rev.com/styleguide/transcription/Rev+Transcription+Style+Guide+v4.0.1.pdf); 3Play Media editing-flags docs; TranscribeMe research-transcription conventions

### Finding 15: Grounded/attributable generation research shows attribution works best when the model selects source spans BEFORE generating text, not after

"Attribute First, then Generate" (ACL 2024) restructures generation into content selection -> sentence planning -> sequential generation, so the selected source segments serve as the fine-grained attribution directly, rather than asking a model to generate freely and then retroactively cite. On multi-document summarization and long-form QA, this produced more concise, more accurate citations than baselines that generate first and attribute after. This is a structural instantiation of the same principle as Finding 1 (quote/select before synthesizing) at the architecture level rather than the single-instruction level.
Confidence: high
Evidence: arXiv / ACL Anthology 2024.acl-long.182 ("Attribute First, then Generate: Locally-attributable Grounded Text Generation")

### Finding 16: OpenAI's own meta-prompting guidance includes an explicit "preserve user content" directive

OpenAI's Prompt Generation documentation (behind the Playground "Generate" button's meta-prompt) states: "Preserve User Content: If the input task or prompt includes extensive guidelines or examples, preserve them entirely, or as closely as possible." This is OpenAI's closest published analogue to an explicit verbatim-preservation instruction, though it is scoped to preserving prompt content/examples supplied by a user, not specifically to dictated interview answers.
Confidence: medium
Evidence: https://platform.openai.com/docs/guides/prompt-generation

### Findings from question 5 not covered above are folded into Finding 14 (ASR noise handling)

### Contradictions
- Finding 10 and Finding 11 report inconsistent, model-dependent effects for both context position and system/user placement; there is no single "safe" instruction position that generalizes. For Claude specifically, the available evidence points toward late/close-to-task placement and general placement-insensitivity, but this rests on limited, indirectly-sourced data (see Gaps).
- Finding 3 (extractive = faithful) and Finding 4 (extractive can still mislead via lost context) are not fully contradictory but sit in tension: extraction is the safer default, but is not sufficient on its own without preserving surrounding context/attribution.

### Gaps
- No study was found that isolates verbatim-copy or quote-fidelity as its own measured IFEval-style category (Finding 12) -- would need the IFEval per-instruction-type appendix or a purpose-built benchmark.
- Claim in Finding 11 that Claude models are comparatively placement-insensitive rests on a single search-synthesized secondary source, not a primary paper directly read; would need the original experiment paper to confirm methodology and model versions tested.
- No direct academic study was found benchmarking Claude specifically (vs. GPT/Llama/Qwen) on "extract verbatim span" vs "summarize" instructions for dictated/spoken interview-style input (as opposed to written documents or code); the closest analogues are Findings 5 and 6, which test written text/code, not conversational dictation.
- The EU regulatory-consultation "Traceable by Design" paper (arXiv:2605.30995) looked directly relevant to verbatim citizen-comment preservation but its full text could not be extracted (PDF binary-only fetch); its "Limitations and Practical Considerations" section likely contains directly relevant failure-mode findings that remain unverified.
