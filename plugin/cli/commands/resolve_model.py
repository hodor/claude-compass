"""`compass resolve-model <agent>` - resolved model and effort for one agent.

The result is a single stdout line, `<model> <effort>`, so callers can parse
it; warnings go to stderr. Every resolution outcome exits 0, including an
unknown agent (which resolves to `inherit` plus the default effort).
"""

import sys

import modelslib


def run(args):
    if len(args) != 1 or args[0].startswith("-"):
        sys.stderr.write("usage: compass resolve-model <agent>\n")
        return 1
    warnings = []
    config, config_warnings = modelslib.load_project_config()
    warnings.extend(config_warnings)
    model, effort, _source = modelslib.resolve(args[0], config=config, warnings=warnings)
    for warning in warnings:
        sys.stderr.write(warning + "\n")
    sys.stdout.write(f"{model} {effort}\n")
    return 0
