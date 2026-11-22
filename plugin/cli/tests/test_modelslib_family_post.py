"""Post-build tests for model family classification.

Adversarial themes: normalisation the matcher applies before classifying
(whitespace, case, None), the o-series pattern's anchors, the flag's
position on the command line, and the real command-line entry point.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modelslib  # noqa: E402

CLI_DIR = Path(__file__).resolve().parent.parent


class FamilyNormalisationTests(unittest.TestCase):
    def test_family_normalises_input_and_anchors_o_series(self):
        """Adversarial where: a matcher that skips strip() or lower() before
        the `inherit` comparison misses ` opus `, `INHERIT`, and a None
        model; an o-series pattern without its end anchor or its dash
        boundary would send `o10`, `o1x` or `o1_mini` to gpt, and one
        without its start anchor would send `foo1-bar` to gpt."""
        cases = [
            ("surrounding whitespace", " opus\t", "claude"),
            ("whitespace around inherit", "  inherit \n", "inherit"),
            ("upper-case inherit", "INHERIT", "inherit"),
            ("None model", None, "unknown"),
            ("whitespace only", "   ", "unknown"),
            ("o-series two digits", "o10", "unknown"),
            ("o-series glued letter", "o1x", "unknown"),
            ("o-series underscore suffix", "o1_mini", "unknown"),
            ("o-series dash with empty suffix", "o1-", "gpt"),
            ("o-series embedded", "foo1-bar", "unknown"),
            ("o-series embedded newline suffix", "o1-a\nb", "unknown"),
            ("bare claude without dash", "claude", "unknown"),
            ("bare gpt without dash", "gpt", "unknown"),
            ("tier name with version suffix", "opus-4", "unknown"),
        ]
        for name, model, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(modelslib.family(model), expected)


class ResolveModelEntryPointTests(unittest.TestCase):
    def run_cli(self, args, vault_text=None):
        tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        meta = Path(tmp) / ".compass" / "meta"
        meta.mkdir(parents=True)
        if vault_text is not None:
            (meta / "models.yaml").write_text(vault_text, encoding="utf-8")
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COMPASS_MODEL_", "COMPASS_EFFORT_"))
        }
        env["CLAUDE_PROJECT_DIR"] = tmp
        return subprocess.run(
            [sys.executable, str(CLI_DIR / "compass"), "resolve-model", *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp,
        )

    def test_family_flag_through_the_compass_entry_point(self):
        """Adversarial where: the flag works when `run` is called directly
        but the dispatcher in front of it swallows or reorders the flag, or
        a project tier pin to a non-claude model is not classified; also
        the flag after the agent name must be a usage error, not an agent
        called `--family`."""
        proc = self.run_cli(["--family", "planner"])
        self.assertEqual((proc.returncode, proc.stdout), (0, "opus high claude\n"))

        proc = self.run_cli(["planner"])
        self.assertEqual((proc.returncode, proc.stdout), (0, "opus high\n"))

        proc = self.run_cli(
            ["--family", "planner"],
            vault_text="agents:\n  planner: Qwen3-Coder\n",
        )
        self.assertEqual((proc.returncode, proc.stdout), (0, "Qwen3-Coder high qwen\n"))

        proc = self.run_cli(["planner", "--family"])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("usage", proc.stderr)

        proc = self.run_cli(["--family", "--family", "planner"])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
