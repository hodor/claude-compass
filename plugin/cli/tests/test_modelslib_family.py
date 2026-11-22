"""Tests for model family classification and `compass resolve-model --family`.

Adversarial themes: prefix collisions between families (`opus` vs `o1`),
case-insensitive matching, version and date suffixes, the empty and
unrecognised inputs, and the two-field output of `resolve-model` staying
byte-identical when the flag is absent.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modelslib  # noqa: E402
from commands import resolve_model  # noqa: E402


class FamilyTests(unittest.TestCase):
    def test_family_classification_table(self):
        """Adversarial where: a family matcher that uses a loose prefix
        (`o` for the o-series) would send `opus` to gpt, or one that is
        case-sensitive or keyed on the bare name would miss suffixed,
        dated, or capitalised ids and return `unknown`."""
        cases = [
            # claude: bare names, full ids, date suffix, mixed case
            ("opus", "claude"),
            ("sonnet", "claude"),
            ("haiku", "claude"),
            ("claude-opus-4-1-20250805", "claude"),
            ("claude-3-5-sonnet-20241022", "claude"),
            ("Claude-Haiku-4-5", "claude"),
            ("OPUS", "claude"),
            ("Sonnet", "claude"),
            # gpt: gpt-* and the o-series with suffixes
            ("gpt-4o", "gpt"),
            ("gpt-4o-2024-08-06", "gpt"),
            ("GPT-5", "gpt"),
            ("o1", "gpt"),
            ("o3", "gpt"),
            ("o4", "gpt"),
            ("o1-mini", "gpt"),
            ("o3-mini-2025-01-31", "gpt"),
            ("o4-mini", "gpt"),
            ("O3", "gpt"),
            # other families
            ("gemini-2.5-pro", "gemini"),
            ("Gemini-1.5-Flash-002", "gemini"),
            ("llama-3.1-70b-instruct", "llama"),
            ("Llama3", "llama"),
            ("qwen3-coder", "qwen"),
            ("Qwen2.5-72B-Instruct", "qwen"),
            ("deepseek-v3", "deepseek"),
            ("DeepSeek-R1", "deepseek"),
            ("mistral-large-latest", "mistral"),
            ("Mistral-7B-Instruct-v0.3", "mistral"),
            # inherit passes through as its own value
            ("inherit", "inherit"),
            # unrecognised
            ("", "unknown"),
            ("totally-made-up-model", "unknown"),
            ("o2", "unknown"),
            ("o5-mini", "unknown"),
        ]
        for model, expected in cases:
            with self.subTest(model=model):
                self.assertEqual(modelslib.family(model), expected)


class ResolveModelFamilyTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / ".compass" / "meta").mkdir(parents=True)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COMPASS_MODEL_", "COMPASS_EFFORT_"))
        }
        env["CLAUDE_PROJECT_DIR"] = str(tmp)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_resolve(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = resolve_model.run(args)
        return code, out.getvalue(), err.getvalue()

    def test_family_flag_appends_family_as_third_field(self):
        """Adversarial where: the flag path could print the family on a
        separate line, drop the effort, or classify the built-in tier
        model wrongly; the output must be exactly `<model> <effort>
        <family>` on one line, for built-in, pinned, and unknown agents."""
        cases = [
            ("planner", {}, "opus high claude"),
            ("vault-locator", {}, "haiku low claude"),
            ("builder", {"COMPASS_MODEL_BUILDER": "gpt-4o-2024-08-06"},
             "gpt-4o-2024-08-06 high gpt"),
            ("tester", {"COMPASS_MODEL_TESTER": "Gemini-1.5-Flash-002"},
             "Gemini-1.5-Flash-002 high gemini"),
            ("researcher", {"COMPASS_MODEL_RESEARCHER": "o3-mini"},
             "o3-mini high gpt"),
            ("reviewer", {"COMPASS_MODEL_REVIEWER": "mystery-model-9"},
             "mystery-model-9 high unknown"),
            ("no-such-agent", {}, "inherit high inherit"),
        ]
        for agent, env, expected in cases:
            with self.subTest(agent=agent, env=env):
                with mock.patch.dict(os.environ, env):
                    code, out, err = self.run_resolve(["--family", agent])
                self.assertEqual(code, 0)
                self.assertEqual(out, expected + "\n")
                self.assertEqual(err, "")

    def test_without_flag_output_stays_two_fields(self):
        """Adversarial where: adding the family column unconditionally
        would break every caller that parses `<model> <effort>`; a pinned
        non-claude model must still print exactly two fields."""
        cases = [
            ("planner", {}, "opus high\n"),
            ("builder", {"COMPASS_MODEL_BUILDER": "gpt-4o-2024-08-06"},
             "gpt-4o-2024-08-06 high\n"),
            ("no-such-agent", {}, "inherit high\n"),
        ]
        for agent, env, expected in cases:
            with self.subTest(agent=agent, env=env):
                with mock.patch.dict(os.environ, env):
                    code, out, _ = self.run_resolve([agent])
                self.assertEqual(code, 0)
                self.assertEqual(out, expected)

    def test_family_flag_without_agent_is_a_usage_error(self):
        """Adversarial where: treating `--family` as the agent name would
        exit 0 and print `inherit high` for an agent called `--family`;
        the bare flag must exit 1 with a usage message and no stdout."""
        code, out, err = self.run_resolve(["--family"])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("usage", err)

    def test_family_flag_keeps_warnings_on_stderr(self):
        """Adversarial where: with the flag on, config warnings could leak
        into stdout and corrupt the three-field line the reviewer parses."""
        vault = Path(os.environ["CLAUDE_PROJECT_DIR"]) / ".compass" / "meta"
        (vault / "models.yaml").write_text(":::garbage:::\n", encoding="utf-8")
        code, out, err = self.run_resolve(["--family", "planner"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "opus high claude\n")
        self.assertIn("models.yaml", err)


if __name__ == "__main__":
    unittest.main()
