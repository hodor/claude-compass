Directory contents:

```
.compass/tmp/capture-opportunities/<opp-id>/
└── opportunity.json        # kind, fired triggers, evidence paths, outcome
```

`opportunity.json` fields:

```json
{
  "id": "OPP-20260805T142200123456Z",
  "kind": "phase",
  "triggers": ["phase-summary"],
  "evidence": ["tmp/phase-reports/PHASE-001-plan-001"],
  "opened_at": "2026-08-05T14:22:00.123456Z",
  "closed_at": null,
  "outcome": null
}
```

`kind` is one of `phase`, `signal`, or `interval`. `triggers` names the signal kinds that made the opportunity due. `evidence` is a list of vault-relative paths the extractor reads; which paths and how many depends on `kind`:

- **`phase`** - one path, a `.compass/tmp/phase-reports/<phase-id>/` directory. Read `phase-summary.yaml` from it exactly as before, plus the per-task report files it names.
- **`signal`** - one or more paths: a `tmp/subagent-captures/` file (a validator or debug subagent's captured report, or an agent's `capture-note` observation) and/or a `handoffs/` path when a `handoff-written` trigger fired.
- **`interval`** - one or more paths recorded in the window that reached the turn interval: `tmp/subagent-captures/` files and/or whatever vault artifact a `vault-write` trigger names.
