---
title: Python text-mode open() on Windows writes CRLF which breaks bash scripts mounted into Linux containers
type: lesson
status: active
category: process
area: workflow
tags: [windows, crlf, docker, line-endings, cross-platform]
created: 2026-06-10
updated: 2026-06-10
score: 5
summary: "Python `open(p, 'w')` on Windows writes CRLF; mount that into a Linux container and bash chokes on $'\\\\r'"
seen: []
---

Python's text-mode `open(path, 'w')` writes the platform's native line endings: LF on Unix, CRLF on Windows.
A shell script written with CRLF and mounted into a Linux Docker container produces silent failures with errors like `cd: $'/app\\r': No such file or directory` and `error: can't open patch '/workspace/patch.diff?': No such file or directory`.
Always pass `newline="\n"` to `open()` when writing shell scripts or any file destined for a Linux environment.
Caught in SWE-bench Pro eval `write_files_local`; the container exited in 1.5s with no test output, eval scored false, root cause hidden until tracing the entryscript with `set -ex`.
The same risk applies to patches, makefiles, dockerfiles, and any line-oriented file crossing the Windows-Linux boundary.
