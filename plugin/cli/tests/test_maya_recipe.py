"""Tests for `plugin/skills/loop/maya-recipe.md`, the control-loop recipe for
animation work in Maya.

Public contract these tests pin:

    Sections headed `## Step N: ...` for N = 0 to 7, in order.

    A statement that the recipe is untested on this machine, carrying the date
    (YYYY-MM-DD) Maya was looked for.

    Every fenced `python` block compiles with `compile()`.

    The sensor block (the fenced `python` block that imports `maya.standalone`)
    runs under `mayapy` as `mayapy <script> <shot sheet>`. The shot sheet is a
    JSON object `{"scene", "beats": [{"control", "frame"}], "playblast",
    "frame_range": [first, last]}`, `scene` and `playblast` relative to the
    shot sheet's folder, `playblast` an image sequence pattern with `####` for
    the zero-padded frame. The script opens the scene and prints one JSON
    object `{"valid", "value", "items"}`: an item `<control>:<frame>` for each
    beat with no key on that control at that frame, and an item
    `playblast:<frame>` for each frame of the range whose image is missing;
    `value` counts the items and the items are sorted. A shot sheet that
    cannot be read prints `valid: false`.

    Every `compass loop <subcommand>` the recipe names is in `USAGE`, and the
    loop skill links `maya-recipe.md`.

The sensor is run here against a fake `maya` package (`maya.standalone` and
`maya.cmds`) whose keys come from the `FAKE_KEYS` environment variable, so the
contract is checked without a Maya licence.

Adversarial themes: a key on a neighbouring frame counted as present, a
control with no keys at all crashing the script, the playblast check counting
files instead of frames, a line number or path leaking into an item, and a
sensor that prints prose or raises instead of an invalid reading.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLI_DIR))

from commands import loop as loop_command  # noqa: E402

PLUGIN = CLI_DIR.parent
RECIPE = PLUGIN / "skills" / "loop" / "maya-recipe.md"
SKILL = PLUGIN / "skills" / "loop" / "SKILL.md"

STEP_HEADING = re.compile(r"^## Step (\d+)\b", re.MULTILINE)
PYTHON_BLOCK = re.compile(r"^```python[ \t]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
LOOP_SUBCOMMAND = re.compile(r"\bcompass[ \t]+loop[ \t]+([a-z][a-z0-9-]*)")

FAKE_STANDALONE = "def initialize(name='python'):\n    pass\n\ndef uninitialize():\n    pass\n"
FAKE_CMDS = r'''
import json, os
_KEYS = json.loads(os.environ.get("FAKE_KEYS", "{}"))
OPENED = []

def file(path=None, **kwargs):
    if kwargs.get("open") or kwargs.get("o"):
        if not os.path.exists(path):
            raise RuntimeError("File not found: %s" % path)
        OPENED.append(path)
    return path

def objExists(name):
    return name in _KEYS

def keyframe(*args, **kwargs):
    control = args[0] if args else kwargs.get("name")
    frames = _KEYS.get(control)
    if frames is None:
        return None
    t = kwargs.get("time") or kwargs.get("t")
    if t is not None:
        lo, hi = t if isinstance(t, (tuple, list)) else (t, t)
        frames = [f for f in frames if lo <= f <= hi]
    if kwargs.get("keyframeCount") or kwargs.get("kc"):
        return len(frames)
    return [float(f) for f in frames] or None
'''


def recipe_text():
    return RECIPE.read_text(encoding="utf-8")


def python_blocks(text):
    return [m.group(1) for m in PYTHON_BLOCK.finditer(text)]


def sensor_block(text):
    blocks = [b for b in python_blocks(text) if "maya.standalone" in b]
    return blocks[0] if blocks else None


class RecipeTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = recipe_text()

    def test_sections_for_steps_zero_to_seven(self):
        numbers = [int(m.group(1)) for m in STEP_HEADING.finditer(self.text)]
        self.assertEqual(numbers, list(range(8)))

    def test_states_it_is_untested_with_a_date(self):
        paragraphs = re.split(r"\n\s*\n", self.text)
        found = [p for p in paragraphs if re.search(r"(?i)untested on this machine", p)]
        self.assertTrue(found, "no untested statement")
        self.assertTrue(any(re.search(r"\b20\d\d-\d\d-\d\d\b", p) for p in found),
                        "the untested statement carries no date")

    def test_every_python_block_compiles(self):
        blocks = python_blocks(self.text)
        self.assertTrue(blocks, "the recipe holds no python block")
        for index, block in enumerate(blocks):
            with self.subTest(block=index):
                compile(block, f"<maya-recipe block {index}>", "exec")

    def test_sensor_block_prints_the_contract_keys(self):
        block = sensor_block(self.text)
        self.assertIsNotNone(block, "no python block imports maya.standalone")
        for key in ('"valid"', '"value"', '"items"'):
            self.assertIn(key, block)
        self.assertIn("print(", block)

    def test_every_loop_subcommand_named_is_in_usage(self):
        named = set(LOOP_SUBCOMMAND.findall(self.text))
        self.assertTrue(named, "the recipe names no compass loop subcommand")
        known = set(re.findall(r"compass loop ([a-z][a-z0-9-]*)", loop_command.USAGE))
        self.assertEqual(sorted(named - known), [])

    def test_names_the_local_lane_and_the_wip_limit(self):
        self.assertIn("compass loop schedule", self.text)
        self.assertIn("--local", self.text)
        self.assertIn("wip_limit", self.text)
        self.assertIn("commandPort", self.text)
        self.assertIn("Bash(mayapy:*)", self.text)

    def test_skill_links_the_recipe(self):
        self.assertRegex(SKILL.read_text(encoding="utf-8"), r"\]\(maya-recipe\.md\)")


class SensorRunTests(unittest.TestCase):
    """Run the recipe's sensor block under plain Python with a fake `maya`."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="maya-recipe-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        fake = self.tmp / "fake" / "maya"
        fake.mkdir(parents=True)
        (fake / "__init__.py").write_text("", encoding="utf-8")
        (fake / "standalone.py").write_text(FAKE_STANDALONE, encoding="utf-8")
        (fake / "cmds.py").write_text(FAKE_CMDS, encoding="utf-8")
        block = sensor_block(recipe_text())
        self.assertIsNotNone(block)
        self.script = self.tmp / "shot_sensor.py"
        self.script.write_text(block, encoding="utf-8")
        self.shot = self.tmp / "shot"
        (self.shot / "playblast").mkdir(parents=True)
        (self.shot / "sh010.ma").write_text("//Maya ASCII\n", encoding="utf-8")

    def write_sheet(self, beats, frame_range=(1001, 1004), **extra):
        sheet = {
            "scene": "sh010.ma",
            "beats": [{"control": c, "frame": f} for c, f in beats],
            "playblast": "playblast/sh010.####.png",
            "frame_range": list(frame_range),
        }
        sheet.update(extra)
        path = self.shot / "shot.json"
        path.write_text(json.dumps(sheet), encoding="utf-8")
        return path

    def frames(self, *numbers):
        for n in numbers:
            (self.shot / "playblast" / f"sh010.{n:04d}.png").write_bytes(b"png")

    def run_sensor(self, sheet, keys):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(self.tmp / "fake")
        env["FAKE_KEYS"] = json.dumps(keys)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, str(self.script), str(sheet)],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(self.tmp), timeout=60,
        )
        try:
            reading = json.loads(proc.stdout)
        except ValueError:
            self.fail(f"stdout is not one JSON object: {proc.stdout!r} {proc.stderr!r}")
        return reading

    def test_all_keys_and_frames_present_reads_zero(self):
        self.frames(1001, 1002, 1003, 1004)
        sheet = self.write_sheet([("ctrl_hand_L", 1001), ("ctrl_head", 1003)])
        reading = self.run_sensor(sheet, {"ctrl_hand_L": [1001, 1010], "ctrl_head": [1003]})
        self.assertIs(reading["valid"], True, reading)
        self.assertEqual(reading["value"], 0)
        self.assertEqual(reading["items"], [])

    def test_missing_key_is_a_control_frame_item(self):
        """Adversarial where: a key one frame away is counted as the beat."""
        self.frames(1001, 1002, 1003, 1004)
        sheet = self.write_sheet([("ctrl_hand_L", 1002), ("ctrl_head", 1003)])
        reading = self.run_sensor(sheet, {"ctrl_hand_L": [1001, 1003], "ctrl_head": [1003]})
        self.assertTrue(reading["valid"], reading)
        self.assertEqual(reading["items"], ["ctrl_hand_L:1002"])
        self.assertEqual(reading["value"], 1)

    def test_control_with_no_keys_reports_every_beat(self):
        self.frames(1001, 1002, 1003, 1004)
        sheet = self.write_sheet([("ctrl_foot_R", 1004), ("ctrl_foot_R", 1001)])
        reading = self.run_sensor(sheet, {"ctrl_foot_R": []})
        self.assertTrue(reading["valid"], reading)
        self.assertEqual(reading["items"], ["ctrl_foot_R:1001", "ctrl_foot_R:1004"])

    def test_missing_playblast_frames_are_items(self):
        """Adversarial where: the check counts files, so a stray extra file
        hides a missing frame."""
        self.frames(1001, 1003, 1005)
        sheet = self.write_sheet([], frame_range=(1001, 1004))
        reading = self.run_sensor(sheet, {})
        self.assertTrue(reading["valid"], reading)
        self.assertEqual(reading["items"], ["playblast:1002", "playblast:1004"])
        self.assertEqual(reading["value"], 2)

    def test_items_are_sorted_and_hold_no_path(self):
        self.frames(1001, 1002, 1004)
        sheet = self.write_sheet([("ctrl_b", 1002), ("ctrl_a", 1001)])
        reading = self.run_sensor(sheet, {"ctrl_a": [], "ctrl_b": []})
        self.assertEqual(reading["items"], sorted(reading["items"]))
        for item in reading["items"]:
            self.assertNotIn("/", item)
            self.assertNotIn("\\", item)

    def test_unreadable_shot_sheet_is_invalid(self):
        bad = self.shot / "shot.json"
        bad.write_text("{not json", encoding="utf-8")
        reading = self.run_sensor(bad, {})
        self.assertFalse(reading["valid"])

    def test_missing_scene_is_invalid(self):
        self.frames(1001, 1002, 1003, 1004)
        sheet = self.write_sheet([("ctrl_head", 1001)], scene="absent.ma")
        reading = self.run_sensor(sheet, {"ctrl_head": [1001]})
        self.assertFalse(reading["valid"])


if __name__ == "__main__":
    unittest.main()
