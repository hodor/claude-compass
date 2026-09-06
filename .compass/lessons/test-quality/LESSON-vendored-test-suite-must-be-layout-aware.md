---
title: "Vendored test suite must be layout-aware"
type: lesson
status: active
category: process
area: test-quality
tags: [testing, vendored-install, layout, path-assumptions, host-install]
created: 2026-09-06
updated: 2026-09-06
score: 5
summary: "A vendored test suite must be layout-aware"
source: "extract-lessons:agent-noted"
seen: []
---

Tests that reference plugin-source-only paths (`templates/`, `.claude-plugin/`) fail in every host install, where those paths don't exist. Run the suite inside a faithful vendored install, not just against the plugin source tree, to catch this class of failure.
