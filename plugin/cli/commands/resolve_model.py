"""`compass resolve-model [--family] <agent>` - resolved model and effort for one agent.

The result is a single stdout line, `<model> <effort>`, so callers can parse
it; with `--family` the line is `<model> <effort> <family>`, the family being
the model's family from `modelslib.family`. Warnings go to stderr. Every
resolution outcome exits 0, including an unknown agent (which resolves to
`inherit` plus the default effort).
"""

import sys

import modelslib

USAGE = "usage: compass resolve-model [--family] <agent>\n"


def run(args):
    with_family = bool(args) and args[0] == "--family"
    if with_family:
        args = args[1:]
    if len(args) != 1 or args[0].startswith("-"):
        sys.stderr.write(USAGE)
        return 1
    warnings = []
    config, config_warnings = modelslib.load_project_config()
    warnings.extend(config_warnings)
    model, effort, _source = modelslib.resolve(args[0], config=config, warnings=warnings)
    for warning in warnings:
        sys.stderr.write(warning + "\n")
    line = f"{model} {effort}"
    if with_family:
        line += f" {modelslib.family(model)}"
    sys.stdout.write(line + "\n")
    return 0
