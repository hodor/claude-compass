"""Seams between the loop modules and the vault.

Adversarial themes: the ledger rows `looplib` writes are the rows `sensorlib`
sums for budget decisions, and a loop folder assembled by hand from the files
`looplib` reads is a clean vault artifact.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import looplib  # noqa: E402
import sensorlib  # noqa: E402
from commands import validate  # noqa: E402

LOOP_INDEX = (
    "---\ntitle: Remove bad pattern\ntype: loop\nstatus: active\narea: workflow\n"
    "tags: [loops]\ncreated: 2026-10-18\nupdated: 2026-10-18\n"
    'summary: "drives the bad pattern count to zero"\n---\n\n# Loop\n'
)

DEFINITION = {
    "sensor_command": "python count.py",
    "sensor_timeout_s": 30,
    "target": 0,
    "direction": "down",
    "controller": "first",
    "model": "sonnet",
    "max_turns": 10,
    "max_budget_usd": 1.5,
    "timeout_s": 600,
    "allowed_tools": ["Read", "Edit"],
    "daily_budget_usd": 5,
    "total_budget_usd": 50,
    "wip_limit": 2,
    "max_actuator_failures": 3,
    "max_harmful_runs": 2,
    "max_runs_without_help": 4,
}


class LoopSeamTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "index.md").write_text("# Index\n", encoding="utf-8")
        self.loop = self.root / "loops" / "LOOP-001-remove-bad"
        self.loop.mkdir(parents=True)
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old)
            if old else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def test_ledger_rows_written_by_looplib_sum_correctly_in_sensorlib(self):
        """Adversarial where: looplib's stamped `ts` or `cost_usd` key not being
        what sensorlib reads, so budget gates see zero spend; or a non-UTC
        offset row, a cost-free row and a row from another day leaking into
        today's sum."""
        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(days=1)).isoformat()
        looplib.append_ledger(self.loop, {"type": "run", "outcome": "helpful", "cost_usd": 0.25})
        looplib.append_ledger(self.loop, {"type": "run", "outcome": "neutral", "cost_usd": 0.5})
        looplib.append_ledger(self.loop, {"type": "transition", "event": "start"})
        looplib.append_ledger(
            self.loop, {"type": "run", "outcome": "harmful", "cost_usd": 4.0, "ts": yesterday}
        )
        rows, skipped = looplib.read_ledger(self.loop)
        self.assertEqual(skipped, [])
        later = datetime.now(timezone.utc) + timedelta(seconds=1)
        # Across a UTC midnight the stamped rows fall on different days; compare
        # only when the clock stayed on one day.
        if later.date() == now.date():
            self.assertAlmostEqual(sensorlib.spend_today(rows, later), 0.75)
        self.assertAlmostEqual(sensorlib.spend_lifetime(rows), 4.75)

    def test_hand_made_loop_folder_validates_clean(self):
        """Adversarial where: validate flagging a loop's `loop.json`, `state.json`,
        `ledger.jsonl` or `feedback.md` (no frontmatter) as stray or misshapen
        artifacts, or the loop `index.md` failing its required-field check."""
        (self.loop / "index.md").write_text(LOOP_INDEX, encoding="utf-8")
        (self.loop / "loop.json").write_text(json.dumps(DEFINITION), encoding="utf-8")
        (self.loop / "feedback.md").write_text("# Feedback\n\nnothing yet\n", encoding="utf-8")
        looplib.write_state(self.loop, {"state": "idle"})
        looplib.append_ledger(self.loop, {"type": "run", "outcome": "helpful", "cost_usd": 0.1})
        self.assertEqual(looplib.load_definition(self.loop), DEFINITION)
        errors, warnings = validate.check_vault(self.root)
        self.assertEqual((errors, warnings), ([], []))


if __name__ == "__main__":
    unittest.main()
