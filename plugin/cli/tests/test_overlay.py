"""Tests for `compass overlay` - project-local addenda that survive update.

Adversarial classes: the shipped content must still be there after an
overlay lands, a second apply on the same file must not double-append, an
overlay naming a file that no longer ships must report rather than vanish,
and CLAUDE.md must come through an update byte-identical - the guarantee
SPEC-014 D-02 names first.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import overlay as overlay_cmd  # noqa: E402


class OverlayFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.vault = self.project / ".compass"
        (self.vault / "meta").mkdir(parents=True)
        # pin host detection off: the self-update apply tests below must
        # neither depend on the machine having dsh nor write into its real
        # harness home
        import hostlib
        self.addCleanup(setattr, hostlib, "dsh_available", hostlib.dsh_available)
        hostlib.dsh_available = lambda: False
        self.claude = self.project / ".claude"
        (self.claude / "agents").mkdir(parents=True)
        (self.claude / "rules").mkdir(parents=True)
        (self.claude / "skills" / "autopilot").mkdir(parents=True)
        (self.claude / "agents" / "researcher.md").write_text(
            "# Researcher\n\nShipped protocol.\n", encoding="utf-8"
        )
        (self.claude / "rules" / "compass-pipeline.md").write_text(
            "# Pipeline\n\nShipped rules.\n", encoding="utf-8"
        )
        (self.claude / "skills" / "autopilot" / "SKILL.md").write_text(
            "# Autopilot\n\nShipped steps.\n", encoding="utf-8"
        )

    def local(self, rel, text):
        path = self.vault / "meta" / "local" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def apply(self):
        return overlay_cmd.apply_overlays(self.vault)

    def agent_text(self):
        return (self.claude / "agents" / "researcher.md").read_text(encoding="utf-8")

    def run_cmd(self, args):
        cwd = os.getcwd()
        os.chdir(self.project)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = overlay_cmd.run(args)
        finally:
            os.chdir(cwd)
        return code, buf.getvalue()


class ApplyTests(OverlayFixture):
    def test_addendum_appended_and_shipped_content_survives(self):
        self.local("agents/researcher.md", "Always sweep upstream issues first.\n")
        report = self.apply()
        text = self.agent_text()
        self.assertIn("Shipped protocol.", text)
        self.assertIn("Always sweep upstream issues first.", text)
        self.assertTrue(text.index("Shipped protocol.") < text.index("Always sweep"))
        self.assertEqual(report["applied"], ["agents/researcher.md"])

    def test_rules_and_skills_targets_resolve(self):
        self.local("rules/compass-pipeline.md", "Local rule.\n")
        self.local("skills/autopilot.md", "Local step.\n")
        report = self.apply()
        self.assertIn(
            "Local rule.",
            (self.claude / "rules" / "compass-pipeline.md").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "Local step.",
            (self.claude / "skills" / "autopilot" / "SKILL.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(len(report["applied"]), 2)

    def test_second_apply_without_refresh_does_not_double_append(self):
        self.local("agents/researcher.md", "Sweep upstream.\n")
        self.apply()
        first = self.agent_text()
        report = self.apply()
        self.assertEqual(self.agent_text(), first)
        self.assertEqual(self.agent_text().count("Sweep upstream."), 1)
        self.assertEqual(report["applied"], [])
        self.assertEqual(report["skipped"], ["agents/researcher.md"])

    def test_refresh_then_apply_restores_the_addendum(self):
        """The real update path: the shipped file is replaced pristine, then
        overlays are re-applied. The addendum must come back."""
        self.local("agents/researcher.md", "Sweep upstream.\n")
        self.apply()
        (self.claude / "agents" / "researcher.md").write_text(
            "# Researcher\n\nShipped protocol, v2.\n", encoding="utf-8"
        )
        self.apply()
        text = self.agent_text()
        self.assertIn("Shipped protocol, v2.", text)
        self.assertEqual(text.count("Sweep upstream."), 1)

    def test_orphan_overlay_is_reported_and_applied_nowhere(self):
        self.local("agents/retired-agent.md", "orphaned content\n")
        report = self.apply()
        self.assertEqual(report["orphans"], ["agents/retired-agent.md"])
        self.assertFalse((self.claude / "agents" / "retired-agent.md").exists())

    def test_no_local_dir_is_a_clean_noop(self):
        report = self.apply()
        self.assertEqual(report, {"applied": [], "skipped": [], "orphans": []})

    def test_provenance_names_the_source_file(self):
        self.local("agents/researcher.md", "Sweep upstream.\n")
        self.apply()
        self.assertIn("meta/local/agents/researcher.md", self.agent_text())


class ClaudeMdTests(OverlayFixture):
    def test_claude_md_is_never_touched_by_overlay(self):
        original = "# Project\n\nMy own instructions.\n"
        (self.project / "CLAUDE.md").write_text(original, encoding="utf-8")
        self.local("agents/researcher.md", "Sweep upstream.\n")
        self.apply()
        self.assertEqual(
            (self.project / "CLAUDE.md").read_text(encoding="utf-8"), original
        )

    def test_claude_md_survives_a_full_self_update_apply(self):
        """SPEC-014 D-02's first named guarantee, pinned against the real
        update path rather than against overlay alone."""
        from commands import self_update

        original = "# Project\n\nMy own instructions.\n"
        (self.project / "CLAUDE.md").write_text(original, encoding="utf-8")

        src = self.project.parent / "plugin-src"
        (src / ".claude-plugin").mkdir(parents=True)
        (src / ".claude-plugin" / "plugin.json").write_text('{"version": "9.9.9"}', encoding="utf-8")
        for sub in ("templates/agents", "templates/rules", "skills/autopilot", "cli", "hooks"):
            (src / sub).mkdir(parents=True, exist_ok=True)
        (src / "templates" / "agents" / "researcher.md").write_text("shipped", encoding="utf-8")
        (src / "templates" / "rules" / "r.md").write_text("rule", encoding="utf-8")
        (src / "skills" / "autopilot" / "SKILL.md").write_text("skill", encoding="utf-8")
        (src / "hooks" / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")

        self_update._apply(src, self.project, apply_models=False)
        self.assertEqual(
            (self.project / "CLAUDE.md").read_text(encoding="utf-8"), original
        )

    def test_self_update_apply_reapplies_overlays(self):
        from commands import self_update

        self.local("agents/researcher.md", "Sweep upstream.\n")
        src = self.project.parent / "plugin-src2"
        (src / ".claude-plugin").mkdir(parents=True)
        (src / ".claude-plugin" / "plugin.json").write_text('{"version": "9.9.9"}', encoding="utf-8")
        for sub in ("templates/agents", "templates/rules", "skills/autopilot", "cli", "hooks"):
            (src / sub).mkdir(parents=True, exist_ok=True)
        (src / "templates" / "agents" / "researcher.md").write_text(
            "# Researcher\n\nShipped v2.\n", encoding="utf-8"
        )
        (src / "hooks" / "hooks.json").write_text('{"hooks": {}}', encoding="utf-8")

        self_update._apply(src, self.project, apply_models=False)
        text = self.agent_text()
        self.assertIn("Shipped v2.", text)
        self.assertIn("Sweep upstream.", text)


class CliTests(OverlayFixture):
    def test_list_is_the_default_and_writes_nothing(self):
        self.local("agents/researcher.md", "Sweep upstream.\n")
        code, out = self.run_cmd([])
        self.assertEqual(code, 0)
        self.assertIn("agents/researcher.md", out)
        self.assertNotIn("Sweep upstream.", self.agent_text())

    def test_apply_flag_writes(self):
        self.local("agents/researcher.md", "Sweep upstream.\n")
        code, out = self.run_cmd(["--apply"])
        self.assertEqual(code, 0)
        self.assertIn("Sweep upstream.", self.agent_text())

    def test_no_overlays_reports_cleanly(self):
        code, out = self.run_cmd([])
        self.assertEqual(code, 0)
        self.assertIn("no project-local overlays", out)


if __name__ == "__main__":
    unittest.main()
