---
name: test-design
description: The operational admission bar for tests - what a single test must demonstrate to exist, the classes that never qualify, and per-type design guidance. Loaded by the tester agent in both its pre-build and post-build stations; the validator audits against the same names.
version: 1.0.0
allowed-tools: [Glob, Grep, Read]
when_to_use: "Load before writing tests in either tester station: pre-build, where tests are authored from the task's spec and acceptance criteria with no implementation yet to read; and post-build, where tests target defect classes only the implementation can reveal. Also load when auditing an existing suite against the bar."
---

# Test Design - The Admission Bar

A test earns its place by the defect it can catch. Nothing else buys admission: not coverage percentage, not suite size, not "it's good practice to test this." If you cannot say what real mistake this test would catch, do not write it.

## The bar: name the defect before you write the test

Before any test code, write a docstring stating the claim under test using the convention:

```python
def test_close_opportunity_rejects_negative_written_count(self):
    """Adversarial where: a negative `written` count should raise, not
    silently produce a negative total in the log row."""
```

Write the docstring first, as a decision, not a caption added after the fact. If you cannot finish the sentence "Adversarial where:" before you have a passing test, you do not yet know what you are testing, and the test that follows will assert whatever the code happens to do rather than what it must do.

A module-level docstring naming the file's adversarial themes is good framing, but it does not substitute for the per-test claim. The per-test docstring is what a reviewer, human or mechanical, checks against.

## Four classes that never qualify

A test in any of these classes gets deleted, not merged, no matter how much coverage it reports.

- **Implementation-detail assertions.** Asserting on a private variable, an internal call sequence, or a call count breaks on every refactor and catches nothing a behavior change would not also break. Assert on what the function returns, raises, or writes, not on how it gets there.
- **Duplicated coverage.** Two tests that exercise the same equivalence class through different call shapes are one test wearing two names. If a second test cannot fail without the first also failing, it is not adding detection power.
- **Framework or standard-library tests.** A test that verifies `json.dumps` serializes a dict, or that `unittest` reports a failure, is testing code you did not write and cannot break. Test the boundary where your code hands data to the library or receives it back.
- **Restated happy paths.** The fifth test asserting the same well-formed input produces the same well-formed output as the first four is not a new defect class. One happy-path test per behavior is enough; every test after it needs its own claim.

## The boundary-and-fixture rule

Co-equal with the bar above, not a footnote to it. Three rules, all three checked on every test that touches a bounded or configurable value:

1. **Exercise the exact boundary value, not only values comfortably on either side.** A test at `interval=5` and `interval=20` says nothing about what happens at exactly `interval=10` if 10 is the cutoff. Off-by-one defects live on the line, not near it.
2. **Never let a fixture value equal the constant it is meant to override.** If the fixture sets `interval=12` and the code's own default is also `12`, a broken lookup that silently falls back to the default is invisible: the test passes whether the override works or not. Pick a fixture value that could not be produced by the code failing to read it.
3. **Supply asymmetrically malformed input, not only well-formed and fully-malformed input.** A record with one bad field and nine good ones exercises a different code path than a record that is garbage end to end. Well-formed and totally-broken inputs are the two easiest cases to handle correctly; the partially-broken one is where real defects live.

These three failures are mechanically undetectable from the diff: nothing can tell you a fixture happens to alias a default, or that a boundary was avoided rather than missed. Checking them is the author's job, every time, not a one-off review pass.

## Selecting inputs: classes before edges

Before choosing which values to test, enumerate the equivalence classes: the groups of inputs the code is meant to treat identically. Cover one case per class, then apply the boundary-and-fixture rule to find the edge of each class. Boundary values chosen without first naming the class they bound are guesses; the class tells you which edge matters and which values inside it are redundant with each other.

## Cases are rows, not tests

A test function exists per public behavior, never per case. The equivalence classes and boundaries of one behavior are named rows in one table-driven test (or one function with named sub-cases); a change under test that fires ten rows still reads as one failing behavior. Test count tracks the number of behaviors the code promises; case count tracks the input space. A feature promising two behaviors gets two tests, however many rows each carries. Each row's claim is one line; a claim needing a paragraph is a sign the row is really a different behavior.

## Test the public contract; helpers are covered through it

An internal helper - private, or existing only to serve one public function - gets no test suite of its own. Its failure modes are rows in the public contract's test, reached the way production reaches them. Testing a helper only directly is how a suite goes green while the helper's call site is deleted: the direct test keeps passing against code nothing uses. A helper earns its own test only when it is a public contract itself (exported, reused across modules, or a boundary another module parses).

## Design guidance by test type

**Table-driven tests.** Each case needs a descriptive name, not an index. Run each case as its own subtest (`self.subTest(name=...)` or the framework's equivalent) so one failing case does not hide the rest. Assert with a real diff, not blind equality, so a failure shows what differed rather than just that something did. A table-driven test's natural row is one equivalence class or one boundary value; if two rows exist only to pad the count, drop one.

**Property-based tests.** Allowed, never mandated. Where the specification is concrete enough to state an invariant, name which of these four shapes the property is in its docstring: round-trip (`decode(encode(x)) == x`), invariant-preservation (the output stays sorted, stays a permutation, stays within bounds), metamorphic (a defined relationship between outputs of two related inputs, used when no single output has an obvious right answer), or differential (two implementations must agree). A property test that cannot be named as one of these four is probably a fuzz test wearing a property-based label, and belongs in the fuzzing section below instead.

**Golden and snapshot tests.** Regenerating a golden file is a behavior change, and it gets the same review scrutiny as any other: reading the diff between the old snapshot and the new one and deciding whether the new output is correct, not clicking "accept." A snapshot that fails because of nondeterministic content (timestamps, ordering, floating-point noise) is a test defect: normalize or exclude the nondeterministic field rather than re-recording the snapshot around it.

**Integration tests.** Assert on behavior and output: the response returned, the file written, the state observably changed. Never assert on the internal call sequence that produced it, or on private state along the way. A test that pins the call sequence breaks the moment the implementation is refactored to do the same thing a different way, which is exactly the change an integration test should survive.

## What counts as behavior

If another module parses the output, its shape is behavior, whether or not a human ever reads it directly. A log row's field names, a trace record's schema, a serialized payload's keys: if a downstream command or library depends on that shape, a test that pins it is testing a real contract, not an implementation detail. This resolves trace and observability code the same way it resolves any other output: the question is never "is a human looking at this," it's "does anything depend on this staying the same shape."

## Out of scope, and the condition that changes it

- **Fuzzing** targets untrusted external input: security and robustness against malformed or hostile data crossing a trust boundary. It is not a substitute for the equivalence-class and boundary work above, which targets functional correctness for a defined input domain. Revisit when a component parses input that did not originate from a trusted caller inside the same process.
- **Contract tests** verify that two independently-deployed components agree on an interface without running both together. They solve a problem a single-process codebase does not have. Revisit if the hook, CLI, or skill boundary is ever split across components that deploy and version independently of each other.
