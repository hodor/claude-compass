"""Controller for LOOP-003-session-context.

Prints Compass's text sources ranked by what each costs an average session,
largest first, one `<tokens per session> <path under plugin/>` line each, ten
lines at most. The first line is the selected work; the rest let the actuator
take the next one when feedback.md rules the first out.

An always-loaded source (a rules file, a skill or agent's frontmatter, the
setup CLAUDE.md block) costs its estimated tokens in every session. A source
loaded on demand (a skill body, a file in a skill folder, an agent body)
costs its tokens times the share of sessions that load it, read from the usage
files `compass loop usage-scan` writes to ~/.compass/usage/. Token estimates
are the context sensor's own: UTF-8 bytes divided by 4, rounded up.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "plugin" / "cli"))

import sensorlib  # noqa: E402

PLUGIN = ROOT / "plugin"
USAGE = Path.home() / ".compass" / "usage"


def startup_cost(rel, path):
    raw = path.read_bytes()
    if rel.startswith("templates/rules/"):
        return sensorlib._estimate(len(raw))
    size, text = sensorlib._field_bytes(rel, raw)
    total = sensorlib._estimate(size)
    if rel == sensorlib.SETUP_SKILL:
        proposal = sensorlib._claude_md_proposal(text)
        if proposal is not None:
            total += sensorlib._estimate(len(proposal.encode("utf-8")))
    return total


def main():
    costs = {}
    for rel, path in sensorlib._context_sources(PLUGIN):
        costs[rel] = costs.get(rel, 0) + startup_cost(rel, path)
    loads, sessions, _machines, _skipped = sensorlib._load_usage(USAGE)
    for key, count in loads.items():
        path = PLUGIN / key
        if sessions and count > 0 and sensorlib._loaded_on_demand(key) and path.is_file():
            costs[key] = costs.get(key, 0) + sensorlib._estimate(len(path.read_bytes())) * count / sessions
    ranked = sorted(costs.items(), key=lambda pair: (-pair[1], pair[0]))
    for rel, tokens in ranked[:10]:
        print(f"{round(tokens)} {rel}")


if __name__ == "__main__":
    main()
