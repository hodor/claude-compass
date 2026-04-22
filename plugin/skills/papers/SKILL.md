---
name: papers
description: Look up and read academic papers from Hugging Face paper pages or arXiv. Fetches paper markdown, structured metadata, linked models/datasets, citing papers, and the citation graph. Use for deep research on techniques, algorithms, and implementations.
version: 1.0.0
allowed-tools: [Bash, Read, WebFetch, WebSearch]
when_to_use: "Use when researching a specific paper, algorithm, or technique. Triggers: 'look up this paper', 'explain this paper', 'what cites X', 'find the paper for Y', 'read arxiv 1234.5678'. Also used automatically by /compass:research deep."
argument-hint: "<arxiv ID, HF paper URL, or search query>"
---

# Papers — Academic Paper Lookup

Fetches academic papers as markdown, structured metadata, linked resources, and citation information. Based on the [Hugging Face paper pages API](https://huggingface.co/papers) — no authentication required for reads.

## Parsing the paper ID

Parse the arXiv ID from whatever the user provides:

| Input | Paper ID |
| --- | --- |
| `https://huggingface.co/papers/2602.08025` | `2602.08025` |
| `https://huggingface.co/papers/2602.08025.md` | `2602.08025` |
| `https://arxiv.org/abs/2602.08025` | `2602.08025` |
| `https://arxiv.org/pdf/2602.08025` | `2602.08025` |
| `2602.08025v1` | `2602.08025v1` |
| `2602.08025` | `2602.08025` |

## Core Operations

### Fetch Paper as Markdown

```bash
curl -s "https://huggingface.co/papers/{PAPER_ID}.md"
```

Returns the paper content as markdown. Uses arXiv HTML version when available, falls back to HF paper page HTML.

### Fetch Structured Metadata

```bash
curl -s "https://huggingface.co/api/papers/{PAPER_ID}"
```

Returns JSON with:
- Authors (names + HF usernames if claimed)
- Abstract and AI-generated summary
- Media URLs, project page, GitHub repo
- Organization info, engagement metrics (upvotes)
- Linked models, datasets, and spaces

### Find Linked Models

```bash
curl -s "https://huggingface.co/api/models?filter=arxiv:{PAPER_ID}"
```

### Find Linked Datasets

```bash
curl -s "https://huggingface.co/api/datasets?filter=arxiv:{PAPER_ID}"
```

### Find Linked Spaces

```bash
curl -s "https://huggingface.co/api/spaces?filter=arxiv:{PAPER_ID}"
```

### Search Papers

Hybrid semantic + full-text search:

```bash
curl -s "https://huggingface.co/api/papers/search?q={QUERY}&limit=20"
```

Searches paper title, authors, and content. Use for finding papers by topic when you don't have an arXiv ID.

### Daily Papers Feed

```bash
curl -s "https://huggingface.co/api/daily_papers?limit=20&sort=trending"
```

For discovering recent trending papers in ML.

## Integration with Deep Research

The `/compass:research deep` pattern uses three researchers: Current, Backward, Forward. This skill powers all three:

### Current Researcher (read the paper itself)

1. Fetch the paper as markdown: `curl -s "https://huggingface.co/papers/{ID}.md"`
2. Fetch structured metadata for authors, abstract, linked artifacts
3. Follow the GitHub repo link if present — read the source code
4. Note: assumptions, limitations, stated trade-offs

### Backward Researcher (find ancestors — why it works)

1. Fetch the paper markdown
2. Extract the References / Bibliography section
3. For each significant reference:
   - If cited by arXiv ID → fetch via this skill
   - If cited by title → search via `/api/papers/search?q=<title>`
4. Focus on papers cited in Background, Related Work, or Method sections
5. Build the ancestor graph — what prior work the original builds on

### Forward Researcher (find descendants — how it evolved)

1. Use search to find papers that cite the original's title or key concepts:
   ```bash
   curl -s "https://huggingface.co/api/papers/search?q=<original title keywords>"
   ```
2. Check the HF paper page's linked models/datasets — these are real-world implementations
3. Look at arXiv for papers published AFTER the original on the same topic
4. Focus on papers that extend, improve, or challenge the original

## Error Handling

- **404 on `/papers/{ID}.md` or `/papers/{ID}`**: paper not indexed on HF
- **404 on `/api/papers/{ID}`**: paper may not be indexed
- **Paper ID not found**: verify extracted arXiv ID including version suffix

### Fallbacks

If HF doesn't have the paper, fall back to arXiv directly:
- `https://arxiv.org/abs/{PAPER_ID}` — abstract page
- `https://arxiv.org/pdf/{PAPER_ID}` — full PDF

## When to Use

- Implementing a technique from a paper
- Understanding an algorithm's foundations
- Finding real-world implementations of a paper (linked models/datasets)
- Exploring the citation graph (backward and forward)
- Discovering recent work in a specific area

## When NOT to Use

- Non-ML papers (HF index may not have them — use arXiv directly)
- Informal technical blog posts (not papers)
- API/library documentation (use WebFetch or the docs directly)

## Notes

- No auth required for public reads
- Prefer the `.md` endpoint for reliable machine-readable output
- Prefer `/api/papers/{ID}` for structured JSON when you need specific fields
- Based on Hugging Face paper pages: https://huggingface.co/papers
