# Gathering candidate findings

For each fired trigger, read the corresponding evidence from the table in `triggers.md`:

- fix-loop >=2 → scan the looping task's build report for what was unexpected.
- validator deviation (phase) → scan `validator.md`'s Deviation (problem) entries for what broke the plan-vs-reality match. validator deviation (signal) → scan the named subagent-capture file the same way.
- debug invoked (phase) → the "Root Cause" + "Remediation" sections of the task's debug report are candidate sources. debug invoked (signal) → the same sections in the named subagent-capture file.
- STOP-and-report → the "Found" vs "Expected" mismatch in the build report carrying the event is a candidate.
- plan revised → the revision rationale in the plan diff or revision note is a candidate.
- handoff written → what the handoff records as open work or a surprising finding is a candidate source.
- agent noted → the note body is one candidate as stated: the agent already judged it worth remembering, so the anti-list and dedup in steps 5-6 are the only filters. A note that names the incident but not the rule still yields a candidate; state the rule the incident implies.
- interval reached with signal(s) → read every evidence file in the window. An interval opportunity fires on volume, not on one strong signal, so a finding only becomes a candidate if it would independently justify a lesson - the anti-list in step 5 is the filter that keeps this permissive read from flooding the catalog.
