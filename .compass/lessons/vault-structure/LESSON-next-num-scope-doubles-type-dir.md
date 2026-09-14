---
title: "next-num's scope argument doubles the type dir for domain-topic folders"
type: lesson
status: active
category: process
area: methodology
tags: [cli, next-num, numbering, domain-folders, scope]
created: 2026-09-13
updated: 2026-09-13
score: 5
summary: "compass next-num <type> <domain/path> builds type_dir/scope; a scope that already includes the type dir doubles it and silently answers 001"
source: extract-lessons:signal-OPP-20260913T193036373302Z
seen: []
---

`compass next-num spec specs/pipeline` resolves to `specs/specs/pipeline`, which doesn't exist, so it silently returns `001` instead of erroring or scanning `specs/pipeline`'s real max (`SPEC-015`).
Pass only the part after the type dir (`pipeline`), never the type-prefixed path.
That silent wrong answer is why specs placed in domain folders have in practice been numbered off the global vault max instead of the folder-local max the tool intends.
Verify the returned number against the target folder's actual contents before trusting it for a domain folder.
