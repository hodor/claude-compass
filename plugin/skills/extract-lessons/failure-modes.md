## Failure modes worth naming

- Asking the model "did anything surprise you?" The triggers are binary; do not introspect.
- Writing lessons without going through `lesson-write`. The single writer enforces dedup, anti-list, and the cap.
- Skipping the extraction log when no lesson is written. The log records `triggered: false` or `all rejected`; absence of log = bug.
- Inventing a candidate to justify the run. If the anti-list rejects everything, the right number of lessons is zero.
- Forgetting the `.processed` marker on a `phase` kind opportunity. The Stop hook backstop will re-extract the same phase on the next turn.
- Treating the trigger list as the candidate list. A trigger fires the run; candidates come from reading the evidence.
- Inventing a contradiction to justify revising or archiving a lesson. The 4a check runs against real tag/area overlap and real falsifying evidence, same discipline as any other candidate.
- Skipping `compass capture-close`. Without it the opportunity never closes, and `capture-stats` cannot tell "reviewed and found nothing" apart from "never ran."
