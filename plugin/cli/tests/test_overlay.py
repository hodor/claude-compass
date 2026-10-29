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


class AdditionStateTests(OverlayFixture):
    """Adversarial classes: an edited local addition must reach the install
    exactly once with the shipped text untouched; a read-only listing must
    tell the four states apart and write nothing; and the block's own
    marker string appearing inside the addition must not confuse where the
    block starts."""

    V1 = "Sweep upstream issues first.\nKeep notes terse.\n"
    V2 = "Sweep upstream issues first.\nWrite notes in plain words.\n"

    def target_bytes(self, rel="agents/researcher.md"):
        return (self.claude / rel).read_bytes()

    def state_line(self, out, rel):
        lines = [ln.lower() for ln in out.splitlines() if rel in ln]
        self.assertEqual(len(lines), 1, f"want one line naming {rel}, got {out!r}")
        return lines[0]

    def test_list_names_each_of_the_four_states(self):
        """Adversarial where: the listing collapses states - an out-of-date
        or never-applied addition reads the same as a current one, or an
        orphan reads as an ordinary state."""
        self.local("agents/researcher.md", self.V1)
        self.local("skills/autopilot.md", self.V1)
        self.run_cmd(["--apply"])
        self.local("skills/autopilot.md", self.V2)
        self.local("rules/compass-pipeline.md", self.V1)
        self.local("agents/retired-agent.md", self.V1)

        code, out = self.run_cmd([])

        self.assertEqual(code, 0)
        phrases = ("not applied", "current", "out of date", "no shipped file")
        rows = [
            ("current", "agents/researcher.md"),
            ("out of date", "skills/autopilot.md"),
            ("not applied", "rules/compass-pipeline.md"),
            ("no shipped file", "agents/retired-agent.md"),
        ]
        for state, rel in rows:
            with self.subTest(state=state):
                line = self.state_line(out, rel)
                self.assertIn(state, line)
                for other in phrases:
                    if other != state:
                        self.assertNotIn(other, line)

    def test_list_reports_out_of_date_and_writes_nothing(self):
        """Adversarial where: list mode repairs an out-of-date block as a
        side effect of describing it."""
        self.local("agents/researcher.md", self.V1)
        self.local("rules/compass-pipeline.md", self.V1)
        self.run_cmd(["--apply"])
        self.local("agents/researcher.md", self.V2)
        self.local("rules/compass-pipeline.md", self.V2)
        agent_before = self.target_bytes()
        rule_before = self.target_bytes("rules/compass-pipeline.md")

        code, out = self.run_cmd([])

        self.assertEqual(code, 0)
        self.assertIn("out of date", self.state_line(out, "agents/researcher.md"))
        self.assertEqual(self.target_bytes(), agent_before)
        self.assertEqual(self.target_bytes("rules/compass-pipeline.md"), rule_before)

    def test_apply_replaces_out_of_date_block_and_keeps_shipped_text(self):
        """Adversarial where: --apply on an edited addition appends a second
        block, leaves the old text behind, or rewrites text above the
        marker."""
        self.local("agents/researcher.md", self.V1)
        self.local("rules/compass-pipeline.md", "Local rule.\n")
        self.run_cmd(["--apply"])
        before = self.agent_text()
        marker = overlay_cmd.MARKER.format(source="meta/local/agents/researcher.md")
        above = before[: before.index(marker)]
        rule_before = self.target_bytes("rules/compass-pipeline.md")
        self.local("agents/researcher.md", self.V2)

        code, _ = self.run_cmd(["--apply"])

        text = self.agent_text()
        self.assertEqual(code, 0)
        self.assertEqual(text.count("Write notes in plain words."), 1)
        self.assertEqual(text.count("Sweep upstream issues first."), 1)
        self.assertNotIn("Keep notes terse.", text)
        self.assertEqual(text.count(marker), 1)
        self.assertTrue(text.startswith(above))
        self.assertEqual(text.count("Shipped protocol."), 1)
        self.assertEqual(self.target_bytes("rules/compass-pipeline.md"), rule_before)

    def test_second_apply_after_replacement_is_byte_stable(self):
        """Adversarial where: a replaced block compares unequal to its own
        local file on the next run (trailing newline or whitespace drift)
        and is rewritten forever."""
        self.local("agents/researcher.md", self.V1)
        self.run_cmd(["--apply"])
        self.local("agents/researcher.md", self.V2)
        self.run_cmd(["--apply"])
        after_first = self.target_bytes()
        self.assertIn(b"Write notes in plain words.", after_first)

        self.run_cmd(["--apply"])

        self.assertEqual(self.target_bytes(), after_first)

    def test_applied_addition_reads_current_whatever_the_local_file_ends_with(self):
        """Adversarial where: block comparison is sensitive to trailing blank
        lines or CRLF line endings, so an applied addition reads out of date
        straight away."""
        shapes = {
            "plain": b"Sweep upstream issues first.\n",
            "trailing blank lines": b"Sweep upstream issues first.\n\n\n\n",
            "no final newline": b"Sweep upstream issues first.",
            "crlf": b"Sweep upstream issues first.\r\nKeep notes terse.\r\n",
        }
        for name, content in shapes.items():
            with self.subTest(shape=name):
                path = self.vault / "meta" / "local" / "agents" / "researcher.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                (self.claude / "agents" / "researcher.md").write_text(
                    "# Researcher\n\nShipped protocol.\n", encoding="utf-8"
                )
                self.run_cmd(["--apply"])
                applied = self.target_bytes()

                _, out = self.run_cmd([])
                self.run_cmd(["--apply"])

                self.assertIn("current", self.state_line(out, "agents/researcher.md"))
                self.assertEqual(self.target_bytes(), applied)

    def test_addition_containing_the_marker_string_applies_once_and_replaces_cleanly(self):
        """Adversarial where: the block's start is found by the last marker
        in the file, or the comparison trips on a marker inside the
        addition, so the addition is duplicated, truncated, or reads out of
        date forever."""
        marker = overlay_cmd.MARKER.format(source="meta/local/agents/researcher.md")
        v1 = f"Header note.\n{marker}\nKeep notes terse.\n"
        v2 = f"Header note.\n{marker}\nWrite notes in plain words.\n"
        self.local("agents/researcher.md", v1)

        self.run_cmd(["--apply"])
        first = self.agent_text()
        shipped_prefix = first[: first.index(marker)]
        self.assertEqual(first.count("Keep notes terse."), 1)
        self.assertEqual(first.count("Header note."), 1)
        self.run_cmd(["--apply"])
        self.assertEqual(self.agent_text(), first)
        _, out = self.run_cmd([])
        self.assertIn("current", self.state_line(out, "agents/researcher.md"))

        self.local("agents/researcher.md", v2)
        self.run_cmd(["--apply"])

        text = self.agent_text()
        self.assertNotIn("Keep notes terse.", text)
        self.assertEqual(text.count("Write notes in plain words."), 1)
        self.assertEqual(text.count("Header note."), 1)
        self.assertEqual(text.count("Shipped protocol."), 1)
        self.assertTrue(text.startswith(shipped_prefix))
        stable = self.agent_text()
        self.run_cmd(["--apply"])
        self.assertEqual(self.agent_text(), stable)


if __name__ == "__main__":
    unittest.main()
