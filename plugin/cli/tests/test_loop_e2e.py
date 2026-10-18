"""End-to-end flow of `compass loop` through the real CLI process, with a stub
standing in for the actuator binary.

Adversarial themes: a seam between two loop commands that only breaks when
they run as separate processes (state on disk, the run lock, the ledger), a
dry run that writes, a paused loop that still spends, and a console whose
code page cannot encode the prompt the runner prints.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPASS = os.path.join(CLI_DIR, "compass")
RESULT_EVENT = Path(CLI_DIR) / "tests" / "fixtures" / "result_events" / "r2.json"

SENSOR_PY = """\
import json, pathlib, sys
items = []
for path in sorted(pathlib.Path(sys.argv[1]).glob("src/*.py")):
    for line in path.read_text(encoding="utf-8").splitlines():
        if "print(" in line:
            items.append(path.name + "::" + line.strip())
print(json.dumps({"valid": True, "value": len(items), "items": items}))
"""

# Removes the first line holding `print(` under the working directory, then
# prints the recorded result event.
ACTUATOR_PY = """\
import os, pathlib, sys
sys.stdin.buffer.read()
for path in sorted(pathlib.Path(os.getcwd()).glob("src/*.py")):
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if "print(" in line:
            del lines[index]
            path.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
            sys.stdout.write(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
            sys.exit(0)
sys.stdout.write(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
"""


def snapshot(project):
    """Relative path -> bytes for every file in the project outside `.git`,
    leaving out `meta/usage.yaml`, the command-invocation counter every
    compass command bumps."""
    return {
        p.relative_to(project).as_posix(): p.read_bytes()
        for p in sorted(project.rglob("*"))
        if p.is_file()
        and ".git" not in p.relative_to(project).parts
        and p.relative_to(project).as_posix() != ".compass/meta/usage.yaml"
    }


class LoopEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.project = self.base / "proj"
        (self.project / "src").mkdir(parents=True)
        (self.project / ".compass" / "meta").mkdir(parents=True)
        (self.project / "src" / "one.py").write_text('print("a")\nprint("b")\n', encoding="utf-8")
        (self.project / "src" / "two.py").write_text('x = 1\nprint("c")\n', encoding="utf-8")
        tools = self.base / "tools"
        tools.mkdir()
        (tools / "sensor.py").write_text(SENSOR_PY, encoding="utf-8")
        (tools / "actuator.py").write_text(ACTUATOR_PY, encoding="utf-8")
        if sys.platform == "win32":
            self.stub = tools / "stub.bat"
            self.stub.write_text(
                '@echo off\r\n"%s" "%s" "%s"\r\n' % (sys.executable, tools / "actuator.py", RESULT_EVENT),
                encoding="utf-8",
            )
        else:
            self.stub = tools / "stub.sh"
            self.stub.write_text(
                '#!/bin/sh\nexec "%s" "%s" "%s"\n' % (sys.executable, tools / "actuator.py", RESULT_EVENT),
                encoding="utf-8",
            )
            self.stub.chmod(0o755)
        self.sensor_command = '"%s" "%s" "%s"' % (
            Path(sys.executable).as_posix(),
            (tools / "sensor.py").as_posix(),
            self.project.as_posix(),
        )
        self.env = {
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(self.project),
            "COMPASS_CLAUDE_BIN": str(self.stub),
        }
        self.env.pop("COMPASS_WORKER_SESSION", None)

    def compass(self, *args, env=None):
        result = subprocess.run(
            [sys.executable, COMPASS, *args],
            capture_output=True,
            env=env or self.env,
            cwd=self.project,
            timeout=120,
        )
        return (
            result.returncode,
            result.stdout.decode("utf-8", "replace"),
            result.stderr.decode("utf-8", "replace"),
        )

    def loop_dir(self):
        return next((self.project / ".compass" / "loops").glob("LOOP-001-*"))

    def configure_loop(self):
        code, out, err = self.compass("loop", "new", "remove-prints")
        self.assertEqual(code, 0, err)
        definition_path = self.loop_dir() / "loop.json"
        definition = json.loads(definition_path.read_text(encoding="utf-8"))
        definition["sensor_command"] = self.sensor_command
        definition["model"] = "stub-model"
        definition_path.write_text(json.dumps(definition), encoding="utf-8")

    def test_full_lifecycle_through_separate_cli_processes(self):
        """Adversarial where: each loop command reads what the previous
        process left on disk, so a state, ledger or lock seam that only works
        in-process shows up here as a wrong exit code or a wrong count."""
        self.configure_loop()
        steps = [
            (("loop", "activate", "LOOP-001"), 0),
            (("loop", "baseline", "LOOP-001"), 0),
            (("loop", "check", "LOOP-001", "--blocking"), 0),
        ]
        for args, expected in steps:
            with self.subTest(command=" ".join(args)):
                code, out, err = self.compass(*args)
                self.assertEqual(code, expected, out + err)
        baseline = json.loads((self.loop_dir() / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(len(baseline["items"]), 3)

        before = snapshot(self.project)
        code, out, err = self.compass("loop", "run", "LOOP-001", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("Selected work", out)
        self.assertEqual(snapshot(self.project), before, "a dry run changed the project")

        code, out, err = self.compass("loop", "run", "LOOP-001")
        self.assertEqual(code, 0, out + err)
        match = re.search(r"(RUN-\d{8}T\d{6}\d*Z): helpful", out)
        self.assertIsNotNone(match, out)
        run_id = match.group(1)
        remaining = "".join(
            (self.project / "src" / name).read_text(encoding="utf-8") for name in ("one.py", "two.py")
        )
        self.assertEqual(remaining.count("print("), 2)

        code, out, err = self.compass("loop", "status")
        self.assertEqual(code, 0, err)
        self.assertIn("wip: 1 of 3", out)
        self.assertIn("2 items", out)

        code, out, err = self.compass("loop", "review", "LOOP-001", run_id, "accept")
        self.assertEqual(code, 0, out + err)
        code, out, err = self.compass("loop", "status")
        self.assertIn("wip: 0 of 3", out)

        code, out, err = self.compass("loop", "pause", "LOOP-001")
        self.assertEqual(code, 0, err)
        spent = snapshot(self.project)
        code, out, err = self.compass("loop", "run", "LOOP-001")
        self.assertEqual(code, 1, "a paused loop must refuse to run")
        self.assertEqual(snapshot(self.project), spent, "a refused run on a paused loop wrote to disk")

        code, out, err = self.compass("loop", "resume", "LOOP-001")
        self.assertEqual(code, 0, err)
        code, out, err = self.compass("validate")
        self.assertEqual(code, 0, out + err)

    def test_run_under_a_cp1252_console_survives_characters_it_cannot_encode(self):
        """Adversarial where: feedback holding characters outside cp1252 is
        printed by the dry run to a console that cannot encode them; the run
        and its dry run must exit 0 rather than die on a UnicodeEncodeError."""
        self.configure_loop()
        (self.loop_dir() / "feedback.md").write_text(
            "Explique a ação → não só o código 日本\n", encoding="utf-8"
        )
        (self.project / "src" / "three.py").write_text('print("ação")\nprint("日本→")\n', encoding="utf-8")
        for args in (("loop", "activate", "LOOP-001"), ("loop", "baseline", "LOOP-001")):
            code, out, err = self.compass(*args)
            self.assertEqual(code, 0, out + err)
        narrow = {**self.env, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
        for args in (("loop", "run", "LOOP-001", "--dry-run"), ("loop", "check", "LOOP-001"),
                     ("loop", "run", "LOOP-001")):
            with self.subTest(command=" ".join(args)):
                code, out, err = self.compass(*args, env=narrow)
                self.assertEqual(code, 0, out + err)
                self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
