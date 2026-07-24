"""Tests for `compass apply-models`: known-files-only rewrite, idempotency,
LF preservation, and the inherit omission gate."""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import apply_models  # noqa: E402

PLANNER = (
    "---\n"
    "name: planner\n"
    "description: \"Plans work\"\n"
    "model: inherit\n"
    "effort: high\n"
    "color: blue\n"
    "---\n"
    "\n"
    "Planner body text.\n"
)
RESEARCHER = (
    "---\n"
    "name: researcher\n"
    "description: \"Investigates\"\n"
    "effort: high\n"
    "---\n"
    "\n"
    "Researcher body text.\n"
)
VAULT_LOCATOR = (
    "---\n"
    "name: vault-locator\n"
    "model: sonnet\n"
    "effort: high\n"
    "---\n"
    "\n"
    "Locator body text.\n"
)
REVIEWER_BARE = (
    "---\n"
    "name: reviewer\n"
    "color: green\n"
    "---\n"
    "\n"
    "Reviewer body text.\n"
)
USER_AGENT = (
    "---\n"
    "name: custom-user-agent\n"
    "model: opus\n"
    "effort: max\n"
    "---\n"
    "\n"
    "User-authored agent. Never touched by apply-models.\n"
)


def scrub_compass_env(test_case):
    """Remove COMPASS_MODEL_*/COMPASS_EFFORT_* vars for the test's duration."""
    saved = {
        key: os.environ.pop(key)
        for key in list(os.environ)
        if key.startswith("COMPASS_MODEL_") or key.startswith("COMPASS_EFFORT_")
    }
    test_case.addCleanup(os.environ.update, saved)


def set_env(test_case, key, value):
    old = os.environ.get(key)

    def restore():
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old

    test_case.addCleanup(restore)
    os.environ[key] = value


class RewriteFrontmatterTests(unittest.TestCase):
    def test_replaces_existing_fields_only(self):
        new_text, error = apply_models.rewrite_frontmatter(PLANNER, "opus", "high")
        self.assertIsNone(error)
        self.assertIn("model: opus\n", new_text)
        self.assertIn("effort: high\n", new_text)
        self.assertIn("color: blue\n", new_text)
        self.assertIn("Planner body text.\n", new_text)
        self.assertNotIn("model: inherit", new_text)

    def test_inserts_model_above_existing_effort(self):
        new_text, error = apply_models.rewrite_frontmatter(RESEARCHER, "sonnet", "high")
        self.assertIsNone(error)
        self.assertIn("model: sonnet\neffort: high\n", new_text)

    def test_inserts_both_fields_when_absent(self):
        new_text, error = apply_models.rewrite_frontmatter(REVIEWER_BARE, "opus", "high")
        self.assertIsNone(error)
        self.assertIn("color: green\nmodel: opus\neffort: high\n---\n", new_text)

    def test_inherit_removes_model_line(self):
        new_text, error = apply_models.rewrite_frontmatter(PLANNER, "inherit", "high")
        self.assertIsNone(error)
        self.assertNotIn("model:", new_text)
        self.assertIn("effort: high\n", new_text)

    def test_no_frontmatter_is_error(self):
        _, error = apply_models.rewrite_frontmatter("just a body\n", "opus", "high")
        self.assertEqual(error, "no frontmatter")

    def test_unterminated_frontmatter_is_error(self):
        _, error = apply_models.rewrite_frontmatter("---\nname: x\n", "opus", "high")
        self.assertEqual(error, "unterminated frontmatter")

    def test_crlf_input_normalized_to_lf(self):
        new_text, error = apply_models.rewrite_frontmatter(
            PLANNER.replace("\n", "\r\n"), "opus", "high"
        )
        self.assertIsNone(error)
        self.assertNotIn("\r", new_text)


class ApplyModelsRunTests(unittest.TestCase):
    def _project(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        scrub_compass_env(self)
        set_env(self, "CLAUDE_PROJECT_DIR", str(tmp))
        (tmp / ".compass" / "meta").mkdir(parents=True)
        agents = tmp / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "planner.md").write_text(PLANNER, encoding="utf-8")
        (agents / "researcher.md").write_text(RESEARCHER, encoding="utf-8")
        (agents / "vault-locator.md").write_text(VAULT_LOCATOR, encoding="utf-8")
        (agents / "reviewer.md").write_text(REVIEWER_BARE, encoding="utf-8")
        (agents / "custom-user-agent.md").write_text(USER_AGENT, encoding="utf-8")
        return tmp, agents

    def _run(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = apply_models.run(args)
        return code, out.getvalue(), err.getvalue()

    def test_rewrites_known_files_from_the_table(self):
        _, agents = self._project()
        code, out, _ = self._run(["--dir", str(agents)])
        self.assertEqual(code, 0)
        planner = (agents / "planner.md").read_text(encoding="utf-8")
        self.assertIn("model: opus\n", planner)
        self.assertIn("effort: high\n", planner)
        self.assertIn("Planner body text.\n", planner)
        researcher = (agents / "researcher.md").read_text(encoding="utf-8")
        self.assertIn("model: sonnet\neffort: high\n", researcher)
        locator = (agents / "vault-locator.md").read_text(encoding="utf-8")
        self.assertIn("model: haiku\n", locator)
        self.assertIn("effort: low\n", locator)
        reviewer = (agents / "reviewer.md").read_text(encoding="utf-8")
        self.assertIn("model: opus\neffort: high\n", reviewer)
        self.assertIn("4 updated", out)

    def test_user_authored_agent_byte_identical(self):
        _, agents = self._project()
        before = (agents / "custom-user-agent.md").read_bytes()
        code, _, _ = self._run(["--dir", str(agents)])
        self.assertEqual(code, 0)
        self.assertEqual((agents / "custom-user-agent.md").read_bytes(), before)

    def test_second_run_is_a_no_op(self):
        _, agents = self._project()
        self._run(["--dir", str(agents)])
        snapshot = {p.name: p.read_bytes() for p in agents.iterdir()}
        code, out, _ = self._run(["--dir", str(agents)])
        self.assertEqual(code, 0)
        self.assertIn("0 updated", out)
        self.assertNotIn("updated planner.md", out)
        self.assertEqual({p.name: p.read_bytes() for p in agents.iterdir()}, snapshot)

    def test_rewritten_files_contain_no_cr_bytes(self):
        _, agents = self._project()
        (agents / "planner.md").write_bytes(PLANNER.replace("\n", "\r\n").encode("utf-8"))
        self._run(["--dir", str(agents)])
        for name in ("planner.md", "researcher.md", "vault-locator.md", "reviewer.md"):
            self.assertNotIn(b"\r", (agents / name).read_bytes(), name)

    def test_inherit_resolution_omits_model_line(self):
        _, agents = self._project()
        set_env(self, "COMPASS_MODEL_PLANNER", "inherit")
        code, _, _ = self._run(["--dir", str(agents)])
        self.assertEqual(code, 0)
        planner = (agents / "planner.md").read_text(encoding="utf-8")
        self.assertNotIn("model:", planner)
        self.assertIn("effort: high\n", planner)

    def test_project_override_applied(self):
        tmp, agents = self._project()
        (tmp / ".compass" / "meta" / "models.yaml").write_text(
            "agents:\n  vault-locator: sonnet\n", encoding="utf-8"
        )
        code, _, _ = self._run(["--dir", str(agents)])
        self.assertEqual(code, 0)
        locator = (agents / "vault-locator.md").read_text(encoding="utf-8")
        self.assertIn("model: sonnet\n", locator)
        self.assertIn("effort: low\n", locator)

    def test_default_dir_is_the_installed_claude_agents(self):
        _, agents = self._project()
        code, out, _ = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("model: opus", (agents / "planner.md").read_text(encoding="utf-8"))
        self.assertIn("4 updated", out)

    def test_missing_target_dir_warns_exit_zero(self):
        tmp, _ = self._project()
        code, out, err = self._run(["--dir", str(tmp / "nowhere")])
        self.assertEqual(code, 0)
        self.assertIn("target dir not found", err)
        self.assertIn("0 updated", out)

    def test_absent_known_files_counted_not_created(self):
        _, agents = self._project()
        code, out, _ = self._run(["--dir", str(agents)])
        self.assertEqual(code, 0)
        # 13 known files, 4 present in the fixture.
        self.assertIn("9 absent", out)
        self.assertFalse((agents / "builder.md").exists())

    def test_malformed_agent_file_skipped_with_warning(self):
        _, agents = self._project()
        (agents / "builder.md").write_text("no frontmatter here\n", encoding="utf-8")
        code, _, err = self._run(["--dir", str(agents)])
        self.assertEqual(code, 0)
        self.assertIn("builder.md", err)
        self.assertEqual(
            (agents / "builder.md").read_text(encoding="utf-8"), "no frontmatter here\n"
        )

    def test_usage_error_exits_one_never_two(self):
        code, _, err = self._run(["--dir"])
        self.assertEqual(code, 1)
        self.assertIn("usage", err)
        code, _, err = self._run(["unexpected"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
