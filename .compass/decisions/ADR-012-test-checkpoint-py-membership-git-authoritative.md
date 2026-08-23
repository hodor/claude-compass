---
title: "test-checkpoint verify Keeps `.py` Membership Git-Authoritative; a Non-`.py` File in the Commit Is Classified Only When Recorded"
type: decision
status: accepted
confidence: high
area: testing
tags: [test-checkpoint, tamper-evidence, verify, false-positive]
created: 2026-08-23
updated: 2026-08-23
author: "builder"
depends_on: ["[[SPEC-013-test-quality]]"]
summary: "verify still derives .py membership from the commit, not the index, so a bundled non-Python file no longer false-positives without reopening the JSON-tamper hole"
---

# test-checkpoint verify Keeps `.py` Membership Git-Authoritative; a Non-`.py` File in the Commit Is Classified Only When Recorded

## Context

`compass test-checkpoint verify` reproduced a false positive: a checkpoint commit that also touched an unrelated markdown file (a plan edited in the same commit as the checkpointed tests) got that file AST-classified too, and its parse error was reported as `modified` - a checkpoint nothing had tampered with failing the gate.

The obvious fix - iterate the checkpoint record's own `files` list instead of every file `git diff-tree` reports for the commit - was the literal instruction given for this task. `plugin/cli/tests/test_test_checkpoint.py::test_verify_json_file_list_edit_does_not_change_verdict` (pre-existing, adversarial) already pins the opposite property: editing the untracked index's `files` list to drop an entry must not stop `verify` from still catching a modification to that file. The module's own docstring names this as load-bearing (SPEC-013-test-quality D-04, D-06) - membership derived from the mutable, gitignored JSON index rather than the immutable commit is exactly the hole a builder editing their own checkpoint to hide a change would try to open.

Trusting `record["files"]` for membership would have closed today's false positive by reopening that hole: an index edited to `files: []` would make `verify` skip the file entirely instead of still catching the tamper.

## Decision

- **D-01:** Membership of `.py` files stays git-authoritative. `verify` still classifies every `.py` path `git diff-tree` reports for the checkpointed commit, regardless of what the index's `files` list says. Dropping an entry from the index cannot hide a `.py` file from verification.
- **D-02:** A non-`.py` path touched by the commit is classified only when it was itself passed to `record` (present in the index's `files` list). Otherwise it produces no finding. AST-classifying prose was never what the checkpoint was protecting, and a commit routinely carries files - a plan, a spec - with no bearing on the checkpoint at all.
- **D-03:** The `files` list is read defensively at `verify` time (non-list or non-dict entries or a missing `path` key are treated as absent) rather than indexed directly, since this is the first place `verify`'s plain (non-`--against-run`) path reads that field, and the module's contract is to degrade to an exit-1 finding on a corrupt index, never raise.

## Rationale

The reported bug and the pre-existing adversarial test both name real defect classes; neither should be sacrificed for the other. Filtering by extension resolves the false positive (a `.md` file is never AST-classified) while leaving `.py` membership exactly as git-authoritative as it was, so the existing test's premise - editing the index cannot launder a modification - continues to hold without change. D-03 exists because the fix's own diff was the first thing to make `record["files"]` reachable from a plain `verify` call; leaving it un-typechecked would have traded one false positive for a crash on a malformed index, caught in code review.

## Consequences

Easier: a checkpoint commit that legitimately bundles a non-Python file (a plan, a spec update) alongside the checkpointed tests verifies clean instead of failing on an unrelated file's tokenizer error.

Harder / unchanged risk: a checkpointed file recorded under a non-`.py` path (unusual - `record` does not require the `.py` extension, only that the content parses as Python) is invisible to `verify`'s git-derived membership scan unless it is still listed in the index's `files`; D-02's rescue clause (classify a recorded path regardless of extension) covers this, so no capability is lost relative to before the fix.

## Alternatives Considered

**Trust `record["files"]` for membership, as literally instructed.** Rejected: reopens the JSON-tamper hole `test_verify_json_file_list_edit_does_not_change_verdict` exists to close, and the docstring's SPEC-013 D-04/D-06 claim, without any human sign-off on the trade-off.

**Skip the `test_verify_json_file_list_edit_does_not_change_verdict` test / narrow it to match the new behavior.** Not pursued - the fix satisfies every required regression case (unrelated non-Python file clean; genuine modification still `modified`; deleted recorded file still `missing`; support-surface tampering still caught) without needing to weaken it.
