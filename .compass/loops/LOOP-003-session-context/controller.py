"""Controller for LOOP-003-session-context.

Prints the always-loaded sources of `plugin/` ranked by their estimated token
cost, largest first, one `<tokens> <item>` line each, ten lines at most. The
first line is the selected work; the rest let the actuator take the next one
when feedback.md rules the first out. Token estimates are the context
sensor's own: UTF-8 bytes divided by 4, rounded up.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "plugin" / "cli"))

import sensorlib  # noqa: E402

PLUGIN = ROOT / "plugin"


def cost(rel, path):
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
    ranked = sorted(
        ((cost(rel, path), rel) for rel, path in sensorlib._context_sources(PLUGIN)),
        key=lambda pair: (-pair[0], pair[1]),
    )
    for tokens, rel in ranked[:10]:
        print(f"{tokens} {rel}")


if __name__ == "__main__":
    main()
