"""Tests for the warnings `compass loop activate` prints before it activates.

Contract choices these tests pin:

* `activate` always exits 0 and changes only the `status` line of the index,
  whatever is unfilled; the warnings are advice.
* Each unfilled part prints one `warning:` line on stderr: a `loop.json` that
  fails `looplib.load_definition` (the line names the field), an `actuator.md`
  equal to the template, and a missing or template-text end state (step 0) or
  sensor (step 1) section of the index.
* Any edit away from the template text counts as filled, however short.
* A loop with a sensor command has the sensor run once: an invalid reading
  warns with its reason, a valid reading is printed on stdout.

Adversarial themes: a warning that fires for a part that is filled, a part
that is unfilled with no warning, a fill of one step that silences the other,
a sensor run that leaks into the loop's files, and a template copy with CRLF
line endings that must still read as the template.
"""

import importlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import looplib  # noqa: E402

TEMPLATES = Path(CLI_DIR) / "loop_templates"
ROOT_INDEX = "# Index\n\n## Specs\n\n## Plans\n\n## Research\n"
WARNING = "compass loop: warning: "

VALID_SENSOR = (
    "import json\n"
    "print(json.dumps({'valid': True, 'value': 2, 'items': ['a.py::x', 'b.py::y']}))\n"
)
INVALID_SENSOR = "print('this is not json')\n"

STEP_ZERO = "## Step 0: End state"
STEP_ONE = "## Step 1: Sensor"


def snapshot(directory):
    return {
        p.relative_to(directory).as_posix(): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def set_section(text, heading, body):
    """`text` with the body under `heading` replaced by `body`."""
    pattern = re.compile(rf"({re.escape(heading)}\n\n).*?(?=\n## |\Z)", re.DOTALL)
    result, count = pattern.subn(lambda m: m.group(1) + body + "\n", text, count=1)
    assert count == 1, f"{heading} not found"
    return result


def template_body(heading):
    """The body of `heading` in the index template."""
    text = (TEMPLATES / "index.md").read_text(encoding="utf-8")
    pattern = rf"{re.escape(heading)}\n\n(.*?)\n\n## "
    return re.search(pattern, text, re.DOTALL).group(1)


def without_status(text):
    return re.sub(r"^status: .*$", "status: X", text, count=1, flags=re.MULTILINE)


class SoftGuardCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp
        self.root = tmp / ".compass"
        (self.root / "meta").mkdir(parents=True)
        (self.root / "index.md").write_text(ROOT_INDEX, encoding="utf-8")
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp)

        def restore():
            if old is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old

        self.addCleanup(restore)
        code, _, err = self.loop("new", "tidy")
        self.assertEqual(code, 0, err)
        self.folder = next((self.root / "loops").glob("LOOP-001-*"))

    def loop(self, *args):
        module = importlib.import_module("commands.loop")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = module.run(list(args))
            except SystemExit as exit_:
                code = exit_.code
        return (0 if code is None else code), out.getvalue(), err.getvalue()

    def write_sensor(self, source):
        script = self.project / "sensor.py"
        script.write_text(source, encoding="utf-8", newline="\n")
        return f'"{sys.executable}" "{script}"'

    def edit_definition(self, **changes):
        path = self.folder / "loop.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(changes)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")

    def edit_index(self, heading, body):
        path = self.folder / "index.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(set_section(text, heading, body), encoding="utf-8", newline="\n")

    def fill_everything(self, sensor_source=VALID_SENSOR):
        self.edit_definition(sensor_command=self.write_sensor(sensor_source))
        (self.folder / "actuator.md").write_text("Fix one file.\n", encoding="utf-8", newline="\n")
        self.edit_index(STEP_ZERO, "No file imports the legacy client.")
        self.edit_index(STEP_ONE, "A grep that counts imports.")

    def activate(self):
        """(code, stdout, warning lines) of `activate LOOP-001`; asserts that
        only the index status line changed."""
        before = snapshot(self.folder)
        code, out, err = self.loop("activate", "LOOP-001")
        after = snapshot(self.folder)
        self.assertEqual(
            {k: v for k, v in after.items() if k != "index.md"},
            {k: v for k, v in before.items() if k != "index.md"},
        )
        self.assertEqual(
            without_status(after["index.md"].decode("utf-8")),
            without_status(before["index.md"].decode("utf-8")),
        )
        self.assertIn("status: active", after["index.md"].decode("utf-8"))
        return code, out, [line for line in err.splitlines() if line.strip()]

    def test_a_fresh_draft_warns_once_for_each_unfilled_part_and_still_activates(self):
        code, out, lines = self.activate()
        self.assertEqual(code, 0)
        self.assertIn("is active", out)
        self.assertTrue(all(line.startswith(WARNING) for line in lines), lines)
        self.assertEqual(len(lines), 4, lines)
        text = "\n".join(lines)
        self.assertIn("sensor_command", text)
        self.assertIn("actuator.md", text)
        self.assertIn("end state", text)
        self.assertIn("index.md sensor section", text)

    def test_a_filled_loop_activates_without_a_warning(self):
        self.fill_everything()
        code, out, lines = self.activate()
        self.assertEqual(code, 0)
        self.assertEqual(lines, [])
        self.assertIn("is active", out)

    def test_each_unfilled_part_alone_gives_exactly_one_warning_naming_it(self):
        template_actuator = (TEMPLATES / "actuator.md").read_bytes()
        cases = {
            "sensor_command": (
                lambda: self.edit_definition(sensor_command=""),
                "sensor_command",
            ),
            "other loop.json field": (
                lambda: self.edit_definition(wip_limit=-1),
                "wip_limit",
            ),
            "actuator": (
                lambda: (self.folder / "actuator.md").write_bytes(template_actuator),
                "actuator.md",
            ),
            "actuator with CRLF": (
                lambda: (self.folder / "actuator.md").write_bytes(
                    template_actuator.replace(b"\n", b"\r\n")
                ),
                "actuator.md",
            ),
            "actuator missing": (
                lambda: (self.folder / "actuator.md").unlink(),
                "actuator.md",
            ),
            "end state template": (
                lambda: self.edit_index(STEP_ZERO, template_body(STEP_ZERO)),
                "end state",
            ),
            "sensor blank": (
                lambda: self.edit_index(STEP_ONE, ""),
                "sensor section",
            ),
        }
        for name, (unfill, expected) in cases.items():
            with self.subTest(name):
                shutil.rmtree(self.folder)
                self.loop("new", "tidy")
                self.folder = next((self.root / "loops").glob("LOOP-*-tidy"))
                self.fill_everything()
                unfill()
                _, _, lines = self.activate()
                self.assertEqual(len(lines), 1, lines)
                self.assertIn(expected, lines[0])
                self.assertTrue(lines[0].startswith(WARNING), lines)

    def test_a_missing_step_section_warns_for_that_step_only(self):
        self.fill_everything()
        path = self.folder / "index.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(STEP_ONE, "## Measure"), encoding="utf-8", newline="\n")
        _, _, lines = self.activate()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("no sensor section", lines[0])

    def test_filling_one_step_does_not_silence_the_other(self):
        self.edit_index(STEP_ZERO, "Done.")
        _, _, lines = self.activate()
        text = "\n".join(lines)
        self.assertNotIn("end state", text)
        self.assertIn("index.md sensor section", text)

    def test_a_one_word_edit_of_each_part_counts_as_filled(self):
        self.fill_everything()
        (self.folder / "actuator.md").write_text("x", encoding="utf-8", newline="\n")
        self.edit_index(STEP_ZERO, "x")
        self.edit_index(STEP_ONE, "y")
        _, _, lines = self.activate()
        self.assertEqual(lines, [])

    def test_an_invalid_sensor_reading_warns_with_its_reason(self):
        self.fill_everything(INVALID_SENSOR)
        code, out, lines = self.activate()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith(WARNING), lines)
        self.assertIn("sensor reading is invalid", lines[0])
        self.assertIn("not JSON", lines[0])
        self.assertNotIn("sensor reading:", out)
        self.assertIn("is active", out)

    def test_a_sensor_that_cannot_start_warns_instead_of_crashing(self):
        self.fill_everything()
        self.edit_definition(sensor_command="no-such-binary-for-compass-tests")
        code, _, lines = self.activate()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("sensor reading is invalid", lines[0])

    def test_a_valid_sensor_reading_is_printed_and_does_not_warn(self):
        self.fill_everything()
        code, out, lines = self.activate()
        self.assertEqual(code, 0)
        self.assertEqual(lines, [])
        self.assertIn("sensor reading: value 2, 2 items", out)

    def test_an_invalid_definition_with_a_sensor_command_still_runs_the_sensor(self):
        self.fill_everything()
        self.edit_definition(wip_limit=-1)
        code, out, lines = self.activate()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("wip_limit", lines[0])
        self.assertIn("sensor reading: value 2, 2 items", out)

    def test_a_draft_without_a_sensor_command_runs_no_sensor(self):
        _, out, lines = self.activate()
        self.assertNotIn("sensor reading", out)
        self.assertFalse(any("sensor reading" in line for line in lines), lines)

    def test_state_and_ledger_are_untouched_by_activation(self):
        self.fill_everything(INVALID_SENSOR)
        before = looplib.read_state(self.folder)
        self.activate()
        self.assertEqual(looplib.read_state(self.folder), before)
        self.assertFalse((self.folder / looplib.LEDGER_FILE).exists())


if __name__ == "__main__":
    unittest.main()
