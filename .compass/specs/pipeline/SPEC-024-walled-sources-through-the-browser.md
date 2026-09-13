---
title: "Sources That Wall Scripts Are Read Through the Human's Browser"
type: spec
status: draft
confidence: medium
area: methodology
tags: [research, sources, browser, acm, dblp, bot-wall, plugins]
created: 2026-09-13
updated: 2026-09-13
depends_on: ["[[specs/pipeline/SPEC-023-research-covers-the-whole-spec]]"]
summary: "ACM, DBLP, and Internet Archive Scholar refuse every scripted request; research reaches them through the human's own browser, page by page, under the sites' reading terms (draft)"
---

# Sources That Wall Scripts Are Read Through the Human's Browser

## Problem

Three sources on the curated list refuse every scripted request. ACM Digital Library challenges any non-browser client on every subdomain, even for open-access papers, and its terms ban scripted harvesting. DBLP and Internet Archive Scholar answer a JSON call with HTTP 200 and a bot-challenge page, so a status check reports them reachable when they are not. An agent using curl, WebFetch, or a client library never reads them, and a research run that lists them as sources silently covers less than it claims ([[research/pipeline/RESEARCH-source-inventory]], findings 40 to 53).

A real browser passes. The Claude in Chrome extension, driving the human's own Chrome, reached a full ACM article page logged out: abstract, references, cited-by. That path exists in the session and no research skill knows to use it.

## Desired Outcome

When a research run needs one of these sources, it reads it through the human's browser and records what it read, the same way it records a file and line. The reading stays within what the site grants a person: one page at a time, for the question at hand. A run that cannot reach the browser says so in its Gaps instead of claiming the source.

## Needs

- Research discovers whether a browser extension is present in the session, the same way it discovers other research plugins ([[specs/pipeline/SPEC-023-research-covers-the-whole-spec]] D-07).
- The curated source list marks which sources are browser-only, so the agent routes those lookups through the browser and never through a scripted client.
- A browser read yields evidence the document can cite: URL, page title, and the passage, with the same confidence rules as any other finding.
- Reading stays per page and per question. Bulk collection through the browser is out of scope; ACM's text-and-data-mining exception is the route for that, and it is the human's to request.
- When no browser is available, the run reports the source as unreachable in its Gaps.

## Non-Goals

- Bypassing a bot wall from a script.
- Bulk download or mirroring of any walled source.
- Solving interactive challenges. A challenge that does not clear on its own stops the read and is reported.

## Success criteria

- A research run for a spec that needs an ACM paper cites its page from the browser, with URL and passage.
- A research run in a session without a browser lists ACM, DBLP, and Internet Archive Scholar under Gaps as unreachable, never as consulted.
