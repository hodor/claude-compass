---
title: "Code as Primary Research Source: Locating, Reading, and Tooling"
type: research
status: draft
confidence: medium
area: methodology
tags: [research, source-code, methodology, tooling, code-reading, mcp, documentation-drift]
created: 2026-09-13
updated: 2026-09-13
git_branch: master
git_commit: 50a2896
author: researcher
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
summary: "how to fetch canonical source per ecosystem, read it efficiently, evidence that docs drift from code, how Serena/Aider/Zoekt/Claude Code's own agents read code, and what tools this session can already discover and use"
---

# Code as Primary Research Source: Locating, Reading, and Tooling

Serves [[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-04 (code over documentation) and D-07 (use plugins present in the session).

## Question

When a library or API has source code available, how does a researcher locate the canonical source matched to the installed version, read an unfamiliar codebase efficiently, and use the code-reading tools and plugins already present in the session, instead of trusting documentation?

## Scope

In: per-ecosystem source location (PyPI, npm, crates.io, Go, Maven, NuGet), doc-vs-code empirical drift evidence, documented codebase-reading techniques, and the internal mechanisms of Serena, Aider's repo map, Zoekt, GitHub code search, and Compass's own codebase-locator/codebase-analyzer agents, plus runtime discovery of plugins/MCP servers in this session. Out: choosing a research methodology (covered by the parallel D-06 axis), source-reliability curation for non-code sources (D-03, covered elsewhere).

## Methodology

Technology Landscape survey (per-item profiles + comparison) for the tools and ecosystem mechanisms, since the question evaluates discrete options rather than one contested claim. For the doc-drift sub-question, a lighter scoping review of empirical software-engineering literature (ACM DL, arXiv, Semantic Scholar). Code-reading tools were verified by cloning and reading their actual source in `C:\Users\rtgasi\AppData\Local\Temp\claude\F--claude-plugins-compass\c0fc3fc7-fc23-4997-ab9e-419caebb5529\scratchpad\codesource\{serena,aider,zoekt}`, per D-04's own instruction to read code, not docs, about the tools that read code.

## Findings

### Locating canonical source across ecosystems

1. **PyPI exposes source links but not a tag** (confidence: high)
   `GET https://pypi.org/pypi/<pkg>/<version>/json` returns `info.project_urls` (free-form keys such as "Source", "Repository") and `info.home_page`, populated from `[project.urls]` in `pyproject.toml`. A green "verified" badge on PyPI only confirms the URL owner proved control of it, not that it points at the exact release.
   - https://docs.pypi.org/api/json/
   - https://docs.pypi.org/project_metadata/

2. **Fetching the sdist directly avoids pip's build-metadata step** (confidence: high)
   `pip download --no-deps --no-binary :all: <pkg>==<version>` forces a source distribution but still runs PEP 517 build-requirement resolution. The same JSON API's `urls` array has an entry with `packagetype: "sdist"` and a direct download URL, fetchable with a plain HTTP request.
   - https://pip.pypa.io/en/stable/cli/pip_download/

3. **No PyPI/npm packaging standard ties a version to a git tag** (confidence: high)
   Matching an installed version to a tag is a heuristic (`v1.2.3`, `1.2.3`, or a monorepo package-prefixed tag like `<name>@1.2.3`), and it varies per project, sometimes within one project's own history. Dependency-update tooling (Renovate) encodes this as configurable prefix/separator heuristics rather than a fixed rule.
   - https://docs.renovatebot.com/modules/versioning/
   - https://docs.renovatebot.com/modules/manager/github-actions/

4. **npm's `repository` field and `npm repo` resolve the source repo, not a ref** (confidence: high)
   `package.json`'s `repository.url` (or shorthand `"user/repo"`) is what `npm repo <pkg>` opens; the published registry tarball is not the git repo and carries no tag/commit metadata of its own.
   - https://docs.npmjs.com/files/package.json/

5. **crates.io's `repository` field is copied verbatim from `Cargo.toml`; docs.rs offers two distinct source views** (confidence: medium-high)
   `GET https://crates.io/api/v1/crates/<name>` returns `crate.repository` as published. Separately, docs.rs renders a rustdoc `[src]` view built for one target/feature set, and a distinct `docs.rs/crate/<crate>/<version>/source/` tab that serves the full raw published tarball independent of build target - the two have diverged in bug reports.
   - https://crates.io/data-access
   - https://internals.rust-lang.org/t/source-code-on-docs-rs-ambiguous-and-obscure/24438

6. **Go modules are the one ecosystem where the import path IS the VCS location and versions resolve natively to tags** (confidence: high)
   `go list -m -json <module>` and the module cache resolve straight to the VCS host via the import path; untagged commits get deterministic pseudo-versions like `v0.0.0-20191109021931-daa7c04131f5`. This makes Go the most reliable ecosystem for automated version-to-source matching.
   - https://go.dev/ref/mod
   - https://go.dev/doc/modules/version-numbers

7. **Maven's `<scm>` tag plus classifier source jars give two independent ways to reach source** (confidence: high)
   POM `<scm>` holds the repo URL (often parent-interpolated); Maven Central additionally serves prebuilt `-sources.jar` artifacts via `mvn dependency:sources`, letting an agent read the exact published source without cloning anything.
   - https://central.sonatype.org/search/rest-api-guide/
   - https://www.baeldung.com/maven-artifact-classifiers

8. **NuGet Source Link embeds the exact commit that built the package** (confidence: high)
   Packages built with `Microsoft.SourceLink.*` embed `<repository type="git" url="..." commit="...">` in the `.nuspec`, so the installed package names its own exact source commit - stronger than the tag-guessing needed elsewhere. Full step-through debugging additionally needs the `.snupkg` symbol package served from `symbols.nuget.org`.
   - https://github.com/dotnet/sourcelink
   - https://learn.microsoft.com/en-us/nuget/create-packages/symbol-packages-snupkg

9. **Google's deps.dev API unifies source-repo lookup across six ecosystems** (confidence: high)
   `GET https://api.deps.dev/v3/projects/<url-encoded-github.com%2Fuser%2Frepo>` returns project data cross-ecosystem (npm, PyPI, Cargo, Go, Maven, NuGet) with attestation data on the package-to-source link, letting a researcher check one API instead of six.
   - https://docs.deps.dev/api/v3/

10. **Version-to-tag matching is fundamentally heuristic everywhere except Go and NuGet Source Link** (confidence: high)
    Forks, vendored copies, monorepos, and unpublished/private versions all break automated matching; only Go (native VCS-path resolution) and NuGet (embedded commit) avoid the heuristic entirely.

### Reading an unfamiliar codebase efficiently

11. **Entry points, public surface, then implementation is the recurring documented order** (confidence: medium)
    Start from main functions, exported/public API, CLI parsers, or route tables; trace one real request/user action end-to-end before broad exploration; treat the public surface (`__init__.py`, `index.js`, a package's `pub` items) as the map, deferring internals.
    - https://code-reading.org/

12. **Type stubs are a compressed, tool-generated API summary** (confidence: high)
    `.pyi` files (via `stubgen`, mypy/pyright) and TypeScript's `.d.ts` (via `tsc --declaration`) strip implementation and leave only the public signature surface - a mechanical way to get "the API without the code."
    - https://mypy.readthedocs.io/en/stable/stubgen.html
    - https://typing.python.org/en/latest/guides/writing_stubs.html

13. **Martin Robillard's field study found professional code navigation is opportunistic, not systematic** (confidence: high)
    "How Effective Developers Investigate Source Code: A Field Study" observed developers on five medium codebases following ad hoc, need-driven paths through code (follow a call, check a definition, backtrack) rather than a planned top-down or bottom-up read.
    - DOI 10.1109/TSE.2004.101

14. **Felienne Hermans documents chunking and beacons as the cognitive units of code reading** (confidence: high)
    Experienced readers group code into higher-level chunks (estimated 2-6 held at once) instead of reading line by line, and recognize "beacons" - familiar patterns that confirm or refute a hypothesis about what code does.
    - Hermans, *The Programmer's Brain*, Manning 2021

15. **Michael Feathers documents techniques for understanding code before changing it** (confidence: high)
    Characterization tests (tests that pin down actual current behavior, used precisely because the real behavior isn't documented) and "Sprout Method/Class" (adding new, tested behavior around untested legacy code without modifying it) are his named techniques for this.
    - Feathers, *Working Effectively with Legacy Code*, Prentice Hall 2004

16. **The test suite is treated as executable, currently-true documentation in multiple sources** (confidence: medium)
    Tests can't drift from behavior the way prose can - a passing test asserts current real behavior. Documented as a deliberate reading strategy (read tests first to learn real usage patterns) distinct from and more reliable than changelog prose.
    - https://about.codecov.io/blog/learning-a-codebase-using-tests/

### Evidence that documentation drifts from code

17. **iComment (SOSP 2007) found comment-code inconsistencies that were confirmed bugs** (confidence: high)
    Mining Linux, Mozilla, Wine, and Apache, iComment extracted 1,832 rules from comments and found 60 inconsistencies between comment and code: 33 were later-confirmed new bugs, 27 were incorrect comments.
    - DOI 10.1145/1294261.1294276

18. **The largest-scale study to date found code-comment co-evolution is the exception, not the rule** (confidence: high)
    Wen, Nagy, Bavota, Lanza (ICPC 2019) mined 1.3 billion AST-level changes across 1,500 systems and found a comment update accompanied a code change only ~7% of the time for methods and ~13% for classes - most code changes do not trigger a matching comment update.
    - DOI 10.1109/ICPC.2019.00019

19. **A practitioner survey named ambiguity, incompleteness, and incorrectness as the most severe documentation failures** (confidence: high)
    Uddin & Robillard, "How API Documentation Fails" (IEEE Software 2015), surveyed practitioners across 10 documentation-problem types; three were rated most severe, and 6 of the 10 were rated frequent enough to force developers to seek alternative sources.
    - DOI 10.1109/MS.2014.80

20. **A retrospective study found the deprecate-then-remove protocol is often skipped** (confidence: medium-high)
    Zhou & Walker (FSE 2016) found Java framework APIs are frequently removed without prior deprecation notice; a 2020 follow-up on RESTful APIs found 87.3% of API versions with breaking changes deprecated no operations beforehand.
    - Zhou & Walker, ACM SIGSOFT FSE 2016, pp. 266-277; follow-up arXiv:2008.12808

21. **Developers turn to Stack Overflow specifically because official docs are incomplete** (confidence: high)
    Parnin & Treude found 87% of studied Android API classes were referenced in Stack Overflow questions; a stricter follow-up study (Delfim et al. 2016) found 69% of top-level Android API elements referenced specifically in "how-to" questions.
    - https://journal-bcs.springeropen.com/articles/10.1186/s13173-016-0049-0

### How Serena (MCP server, installed in this session) reads code

22. **Serena's tool schema is generated from Python introspection, not a manifest** (confidence: high)
    Tool name and the LLM-facing parameter description are derived at runtime from the class name and the `apply()` method's docstring, so the tool surface is always in sync with the actual callable.
    - `serena/src/serena/tools/tools_base.py:192-199,226-241`

23. **`find_symbol` operates on a name-path tree (e.g. `MyClass/my_method`), not a flat name index** (confidence: high)
    Supports substring matching, path scoping, a `depth` parameter to pull children, and a choice between full source body or hover-style signature-only info.
    - `serena/src/serena/tools/symbol_tools.py:134-233`

24. **`find_referencing_symbols` is a thin wrapper over the LSP `textDocument/references` call** (confidence: high)
    It resolves to a raw JSON-RPC LSP request and attaches ±1 line of surrounding source to each hit so the calling agent doesn't need a follow-up file read.
    - `serena/src/serena/tools/symbol_tools.py:252-307`, `serena/src/solidlsp/ls.py:1670-1722`

25. **`get_symbols_overview` is documented as "the first tool to call" on a new file** (confidence: high)
    Returns a kind-grouped outline (default depth 0, i.e. top-level only) and falls back to a bare symbol-kind count if the outline would exceed the answer size budget - a compression escape hatch for very large files.
    - `serena/src/serena/tools/symbol_tools.py:36-131`

26. **Serena's LSP layer (`solidlsp`) is a one-process-per-language-server subprocess+JSON-RPC wrapper, structurally derived from the `multilspy` project** (confidence: high)
    Manages the language-server subprocess lifecycle directly, including a clean LSP `shutdown`/`exit` notification pair on teardown.
    - `serena/src/solidlsp/ls_process.py:208-251,487,521`

27. **Serena's "onboarding" is a one-time prompted ritual, not an automatic index** (confidence: high)
    `OnboardingTool` returns a prompt instructing the agent to explore the project and write what it learns into named markdown memories; the compression into reusable project knowledge is done by the agent's own subsequent `write_memory` calls, not a built-in scanner.
    - `serena/src/serena/tools/workflow_tools.py:10-29`

28. **Serena memories are markdown files with `mem:`-prefixed cross-references, rewritten on rename** (confidence: high)
    `/`-delimited names give lightweight topic grouping (e.g. `global/...` for cross-project memories); renaming a memory propagates through other memories' references automatically.
    - `serena/src/serena/tools/memory_tools.py:9-123`

### How Aider's repo map decides what code to show an LLM

29. **Aider parses every file with tree-sitter and falls back to Pygments only when a language's query has no reference captures** (confidence: high)
    `.scm` tag queries yield `def`/`ref` tags per identifier; if a language's query only emits definitions, Aider lexes with Pygments and treats every name token as a synthetic reference so the graph is never empty.
    - `aider/aider/repomap.py:279-363`

30. **Aider ranks code relevance with personalized PageRank over a file-reference graph, not recency or file size** (confidence: high)
    Builds a weighted multigraph (`referencer -> definer` edges) with heuristic weights - 10x for identifiers the user explicitly mentioned, 10x for long meaningful names, 0.1x for private or heavily-duplicated names, 50x for files already open in chat - then runs personalized `networkx.pagerank` and redistributes rank across each definer's out-edges into per-`(file, identifier)` scores.
    - `aider/aider/repomap.py:365-382,470-514,519-545`

31. **The repo map fits a token budget via binary search, re-rendering the tree at each guess** (confidence: high)
    Searches over how many top-ranked tags to include, accepting a candidate once it's under budget and better than the previous best, stopping early within 15% of the target token count.
    - `aider/aider/repomap.py:666-706`

32. **Per-file output is signature-in-context, not full bodies** (confidence: high)
    Uses `grep_ast`'s `TreeContext` to mark ranked-tag lines as "of interest" and expand each to its enclosing scope (e.g. a function signature) while eliding the rest, truncating any line past 100 characters to defend against minified/generated files.
    - `aider/aider/repomap.py:710-784`

33. **Token counts for large files are estimated by sampling, not full tokenization** (confidence: high)
    Files over 200 characters are sampled every Nth line and extrapolated, trading exactness for speed since the estimator runs inside the binary-search loop repeatedly.
    - `aider/aider/repomap.py:89-100`

### How Zoekt indexes and queries code (installed in this session for UE5, Fortnite, Defold)

34. **Zoekt's trigram index reduces multi-character substring search to intersecting a couple of posting lists** (confidence: high)
    The design doc's own worked example ("banana" → `ban:0, ana:1,3, nan:2`) shows why only the first and last trigram's posting lists need checking for a longer query. ASCII trigrams get a directly-indexed array; non-ASCII trigrams use a map, both varint-delta-encoded.
    - `zoekt/doc/design.md:20-50`, `zoekt/index/shard_builder.go:71-133,160-220`

35. **Regex queries are prefiltered by extracting literal substrings from the parsed regex AST, then confirmed with the real regex engine** (confidence: high)
    Long literal fragments become trigram-index lookups; concatenation/alternation nodes combine into AND/OR trees of substring matches; only candidates surviving the prefilter get the actual compiled regex run against them.
    - `zoekt/index/eval.go:623-676`, `zoekt/index/matchtree.go:188-229`

36. **Zoekt's query language exposes field-scoped filters layered on the regex core** (confidence: high)
    `content:`/`c:`, `file:`/`f:`, `lang:`, `sym:`, `repo:`/`r:`, `branch:`/`b:`, plus boolean flags (`archived:`, `fork:`, `public:`) and `type:` to select result kind.
    - `zoekt/doc/query_syntax.md:1`

37. **The zoekt plugins installed in this session (`zoekt-ue5`, `zoekt-fortnite`, `zoekt-defold`, `zoekt-ue58`) each wrap the same binary over a different pre-built local index** (confidence: high)
    Each plugin's `skills/search/SKILL.md` differs only in the index path, the source tree root, and (for Defold) a tree-layout table pointing at sub-project language boundaries (C/C++ engine, Clojure editor, Java bob build tool); query syntax and gotchas (`OR` not valid, `AND` is file-level, quoting for literal phrases) are identical across all four.
    - `F:\claude\plugins\zoekt-ue5\skills\search\SKILL.md:15,24`, `F:\claude\plugins\zoekt-defold\skills\search\SKILL.md:15,24-34`

### GitHub code search API

38. **`GET https://api.github.com/search/code` searches code but cannot pin a package version** (confidence: high)
    Uses a legacy query syntax distinct from github.com's newer search UI (no `path:` qualifier, no regex), requires authentication, is rate-limited to 10 requests/minute (versus 30 for other search endpoints), and forks are only searchable if they have more stars than their parent - none of this lets a caller search "this exact release's source," only the default branch or whatever the indexer has crawled.
    - https://docs.github.com/en/rest/search/search#search-code
    - https://docs.github.com/en/search-github/searching-on-github/searching-code

### Claude Code's own code-reading agent patterns (this repo)

39. **Compass ships a locate/analyze split as two separate low-cost and high-cost agents** (confidence: high)
    `codebase-locator` (haiku model, Grep/Glob/LS only, no Read) finds WHERE code lives and is explicitly barred from reading file contents; `codebase-analyzer` (sonnet model, adds Read) is spawned afterward specifically to explain HOW the located code works with `file:line` references. Both are contractually barred from suggesting improvements - "you document, you do not critique."
    - `F:\claude\plugins\compass\plugin\templates\agents\codebase-locator.md:1-21`
    - `F:\claude\plugins\compass\plugin\templates\agents\codebase-analyzer.md:1-21`

40. **`research-codebase` runs locator/analyzer as a cheap-then-expensive pipeline, paired with an identical vault-side locator/analyzer** (confidence: high)
    Spawns `codebase-locator`+`vault-locator` in parallel first (cheap filters), then `codebase-analyzer`+`vault-analyzer` on the promising subset, optionally adding `pattern-finder` for "how do we usually do X" - the same two-stage economy pattern (cheap breadth, then expensive depth) that Aider's PageRank-then-token-budget and Serena's overview-then-detail both implement independently.
    - `F:\claude\plugins\compass\plugin\skills\research-codebase\SKILL.md:46-67`

### What's discoverable and usable in this session right now

41. **Two MCP servers are configured user-level, not project-level; no `.mcp.json` exists in this repo** (confidence: high)
    `claude mcp list` shows `headroom` (context-compression tool, unrelated to source code) and `serena` (semantic code navigation, see findings 22-28) as connected, both defined in the user-level `C:\Users\rtgasi\.claude.json` under `mcpServers`, not in a repo-local `.mcp.json`.

42. **`claude plugin list --json` enumerates installed plugins with scope, giving a mechanical way to discover session capabilities** (confidence: high)
    Output includes `id`, `version`, `scope` (`local`/`user`/`project`), `enabled`, and `installPath` for every installed plugin. In this session it surfaces, among others, a `rust-analyzer-lsp@claude-plugins-official` plugin - a fourth, LSP-based direct-source-access mechanism (parallel to Serena's) available for Rust code specifically.

43. **Compass's `research` and `research-codebase` skills have no step that enumerates installed MCP servers or plugins** (confidence: high)
    Neither `plugin/skills/research/SKILL.md` nor `plugin/skills/research-codebase/SKILL.md` mentions `claude mcp list` or `claude plugin list`; SPEC-023 D-07 ("research makes use of plugins present in the session") currently has no mechanical discovery step to hang off of.
    - `F:\claude\plugins\compass\plugin\skills\research\SKILL.md`, `F:\claude\plugins\compass\plugin\skills\research-codebase\SKILL.md`

44. **The `papers` skill and the `obsidian` skill's research template are the two other run-time-relevant capabilities already in this plugin** (confidence: high)
    `papers` fetches arXiv/Hugging Face paper markdown, structured metadata, and citation graphs with no auth (`plugin/skills/papers/SKILL.md:12-84`); `obsidian` carries the research document template used to write this document, including a four-approach methodology table (Scoping Review, Systematic Literature Review, Systematic Mapping Study, Technology Landscape).
    - `F:\claude\plugins\compass\plugin\skills\papers\SKILL.md:29-84`
    - `F:\claude\plugins\compass\plugin\skills\obsidian\SKILL.md:373-443`

## Taxonomy

| Mechanism | Ecosystem/tool | Version-exact? | Access method |
|---|---|---|---|
| Embedded commit (Source Link) | NuGet | Yes | `.nuspec` `<repository commit="...">` |
| Native VCS resolution | Go modules | Yes | import path = VCS location |
| Sources jar | Maven | Yes (published artifact) | `-sources.jar` classifier |
| sdist download | PyPI | Yes | JSON API `packagetype: sdist` |
| Registry field, no ref | npm, crates.io | No (heuristic tag guess) | `repository` field |
| LSP semantic navigation | Serena, rust-analyzer-lsp | N/A (reads local checkout) | MCP tool calls over JSON-RPC |
| Tree-sitter + PageRank | Aider repo map | N/A (reads local checkout) | in-process, no server |
| Trigram index | Zoekt | N/A (reads indexed snapshot) | CLI over pre-built index |
| Cross-ecosystem lookup | deps.dev | Best-effort, attested | REST API |
| Hosted search, no version pin | GitHub code search API | No | REST API, legacy syntax |

## Gaps

- Serena's actual behavior could not be exercised directly in this session - no `serena` tools were exposed to this agent's tool list, so findings 22-28 come from reading its cloned source (`oraios/serena`, commit `403ad0a`), not from invoking it live. A pass that runs Serena's tools against this repo would confirm the tool surface matches the source.
- The often-cited "25.5% of Python docstrings are inconsistent with their function signatures (Wen et al. 2023)" statistic could not be traced to a real paper in this pass; it appears in secondary blog summaries only and should not be cited until a primary source is found.
- No source location convention was verified against a live private/internal package (only public-registry behavior was checked) - internal monorepos may follow neither the tag heuristics nor deps.dev's coverage.
- `claude plugin list --json` was only sampled (piped through `head`), not read in full; a complete enumeration of every plugin available to this session (and which ones expose source-code or paper access) is a five-minute follow-up, not done here.
- Whether Compass's `pattern-finder` agent (`plugin/templates/agents/pattern-finder.md`, referenced in finding 40 but not itself read in this pass) also implements a locate-then-rank pattern comparable to Aider's was not checked.
