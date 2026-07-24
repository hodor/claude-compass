"""`compass models` - the full resolved model/effort roster.

Prints one row per roster entry (the 13 agents plus the detached
`index-summary` job) and any extra agent named in the project override, with
a source column showing which precedence rung won: built-in, project, or env.
Warnings go to stderr; exit 0 always.
"""

import sys

import modelslib


def run(args):
    warnings = []
    config, config_warnings = modelslib.load_project_config()
    warnings.extend(config_warnings)

    agents = list(modelslib.DEFAULT_ROSTER)
    agents += sorted(set(config.get("agents", {})) - set(agents))

    rows = [("agent", "model", "effort", "source")]
    for agent in agents:
        model, effort, source = modelslib.resolve(agent, config=config, warnings=warnings)
        rows.append((agent, model, effort, source))

    widths = [max(len(row[col]) for row in rows) for col in range(4)]
    for row in rows:
        line = "  ".join(cell.ljust(width) for cell, width in zip(row, widths))
        sys.stdout.write(line.rstrip() + "\n")
    for warning in warnings:
        sys.stderr.write(warning + "\n")
    return 0
