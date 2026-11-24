# Sizing rubric candidate: a task's tests counted apart

A candidate for the planner's `## Task Sizing` table, measured with
`letters.py run --rubric bench/overhead/rubrics/sizing-tests-apart.md`. It
differs from the shipped table at the three places blind raters and planners
parted in the letter-repeatability measurement: a task's own test files do
not count toward its size, the file ranges no longer share the count of five,
and L names what makes a task large below five files. Its Scope column is
shorter than the shipped one.

## Task Sizing

| Size | Scope | Example |
|------|-------|---------|
| S | One file and its tests | Add a field to a schema, write a utility function |
| M | 2-4 files and their tests | Implement a new agent, refactor a module |
| L | 5+ files, or a new subsystem | New feature end-to-end, major refactor |

Tasks larger than L get broken into subtasks.
