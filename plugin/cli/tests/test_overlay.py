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


class ImplementationBranchTests(OverlayFixture):
    """Adversarial classes the replace-from-marker implementation introduces:
    a marker found in text the block does not own, line-ending rewrites of
    text above the marker, an emptied local file, and targets or sources the
    filesystem makes unreadable or unwritable."""

    MARKER = "<!-- project-local overlay: meta/local/agents/researcher.md -->"

    def write_target(self, content):
        (self.claude / "agents" / "researcher.md").write_bytes(content)

    def target_raw(self):
        return (self.claude / "agents" / "researcher.md").read_bytes()

    def test_marker_text_inside_shipped_content_is_not_a_block_boundary(self):
        """Adversarial where: the block start is the first marker occurrence
        in the target, so a shipped file that quotes the marker (in a code
        fence, say) is cut from that quote to the end when an addition is
        applied or replaced."""
        shipped = (
            "# Researcher\n\nQuote of the provenance line:\n\n"
            f"    {self.MARKER}\n\nShipped tail that must survive.\n"
        )
        self.write_target(shipped.encode("utf-8"))
        self.local("agents/researcher.md", "Keep notes terse.\n")

        self.run_cmd(["--apply"])
        self.local("agents/researcher.md", "Write notes in plain words.\n")
        self.run_cmd(["--apply"])

        text = self.agent_text()
        self.assertTrue(text.startswith(shipped.rstrip("\n")))
        self.assertIn("Shipped tail that must survive.", text)
        self.assertEqual(text.count("Write notes in plain words."), 1)
        self.assertNotIn("Keep notes terse.", text)

    def test_crlf_text_above_the_marker_is_left_byte_identical(self):
        """Adversarial where: replacing an out-of-date block rewrites a CRLF
        shipped prefix to LF, so text above the marker changes although the
        contract says it is never rewritten."""
        prefix = b"# Researcher\r\n\r\nShipped protocol.\r\n"
        self.write_target(prefix)
        self.local("agents/researcher.md", "Keep notes terse.\n")
        self.run_cmd(["--apply"])
        self.local("agents/researcher.md", "Write notes in plain words.\n")

        self.run_cmd(["--apply"])

        raw = self.target_raw()
        self.assertTrue(raw.startswith(prefix), raw[:60])

    def test_crlf_target_with_matching_block_reads_current(self):
        """Adversarial where: a CRLF target compares unequal to the LF local
        file, so a block that matches reads out of date and is rewritten on
        every run."""
        self.local("agents/researcher.md", "Keep notes terse.\n")
        self.run_cmd(["--apply"])
        crlf = self.agent_text().replace("\n", "\r\n").encode("utf-8")
        self.write_target(crlf)

        _, out = self.run_cmd([])
        self.run_cmd(["--apply"])

        self.assertIn("current", out)
        self.assertEqual(self.target_raw(), crlf)

    def test_emptied_local_file_is_a_state_not_a_dangling_marker(self):
        """Adversarial where: a local file emptied after being applied is
        replaced into a bare marker line - the target then carries a block
        header with no addition."""
        self.local("agents/researcher.md", "Keep notes terse.\n")
        self.run_cmd(["--apply"])
        self.local("agents/researcher.md", "")

        _, listed = self.run_cmd([])
        self.run_cmd(["--apply"])

        text = self.agent_text()
        self.assertIn("out of date", listed)
        self.assertNotIn("Keep notes terse.", text)
        self.assertFalse(
            text.rstrip().endswith(self.MARKER),
            f"target ends in a bare marker: {text[-120:]!r}",
        )

    def test_unicode_addition_round_trips_and_reads_current(self):
        """Adversarial where: non-ASCII text (accents, CJK, a character
        outside the BMP) is mangled by an encoding default on write or
        compared as unequal on the next run."""
        body = "Priorize a revisão 日本語 \U0001f9ed\n"
        self.local("agents/researcher.md", body)
        self.run_cmd(["--apply"])
        first = self.target_raw()

        _, out = self.run_cmd([])
        self.run_cmd(["--apply"])

        self.assertIn(body.strip().encode("utf-8"), first)
        self.assertIn("current", out)
        self.assertEqual(self.target_raw(), first)

    def test_undecodable_local_file_does_not_raise_from_apply_overlays(self):
        """Adversarial where: apply_overlays documents that it never raises,
        but a local file that is not UTF-8 escapes as UnicodeDecodeError and
        takes the other additions down with it."""
        path = self.vault / "meta" / "local" / "agents" / "researcher.md"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"caf\xe9 bad bytes\n")
        self.local("rules/compass-pipeline.md", "Local rule.\n")

        try:
            self.apply()
        except UnicodeDecodeError as exc:
            self.fail(f"apply_overlays raised: {exc}")

        self.assertIn(
            "Local rule.",
            (self.claude / "rules" / "compass-pipeline.md").read_text(encoding="utf-8"),
        )

    def test_read_only_target_does_not_raise_from_apply_overlays(self):
        """Adversarial where: a read-only installed file makes the write
        fail, and the error escapes a function documented as never raising,
        skipping every later addition."""
        import stat

        target = self.claude / "agents" / "researcher.md"
        self.local("agents/researcher.md", "Keep notes terse.\n")
        self.local("rules/compass-pipeline.md", "Local rule.\n")
        target.chmod(stat.S_IREAD)
        self.addCleanup(target.chmod, stat.S_IWRITE | stat.S_IREAD)

        try:
            self.apply()
        except OSError as exc:
            self.fail(f"apply_overlays raised: {exc}")

        self.assertIn(
            "Local rule.",
            (self.claude / "rules" / "compass-pipeline.md").read_text(encoding="utf-8"),
        )

    def test_symlinked_target_keeps_its_link_and_edits_the_real_file(self):
        """Adversarial where: the atomic replace swaps the symlink itself for
        a regular file, so the real file the link points at is left without
        the addition and the link is gone."""
        real = self.project / "real-researcher.md"
        real.write_text("# Researcher\n\nShipped protocol.\n", encoding="utf-8")
        target = self.claude / "agents" / "researcher.md"
        os.remove(target)
        try:
            target.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not creatable here")
        self.local("agents/researcher.md", "Keep notes terse.\n")

        self.apply()

        self.assertTrue(target.is_symlink(), "the symlink was replaced")
        self.assertIn("Keep notes terse.", real.read_text(encoding="utf-8"))

    def test_apply_output_labels_current_orphan_and_written_rows(self):
        """Adversarial where: --apply labels a row it did not write as
        written, or a listing hint to run --apply survives a finished apply."""
        self.local("agents/researcher.md", "Keep notes terse.\n")
        self.run_cmd(["--apply"])
        self.local("agents/retired-agent.md", "x\n")
        self.local("rules/compass-pipeline.md", "Local rule.\n")

        _, out = self.run_cmd(["--apply"])

        lines = {ln.split(":")[0]: ln for ln in out.splitlines()}
        self.assertTrue(lines["agents/researcher.md"].endswith("current"))
        self.assertTrue(lines["agents/retired-agent.md"].endswith("no shipped file"))
        self.assertTrue(lines["rules/compass-pipeline.md"].endswith("applied"))
        self.assertNotIn("run `compass overlay --apply`", out)


class ExtractTests(OverlayFixture):
    """`compass overlay --extract <name>` turns a hand-edited file saved by
    update into a local addition.

    Assumed shapes: `<name>` is the addition's path under `meta/local/`
    (`agents/researcher.md`, `skills/autopilot.md`); the saved copy is
    `meta/local/kept/<name>` and the shipped text is the installed target.
    Lines the saved copy holds after the whole shipped text become the
    addition, which is applied to the target at once so the listing reads
    `current`. Each shipped line the saved copy rewords or drops is printed
    on a line of its own."""

    TARGETS = {
        "agents": lambda claude, stem: claude / "agents" / f"{stem}.md",
        "rules": lambda claude, stem: claude / "rules" / f"{stem}.md",
        "skills": lambda claude, stem: claude / "skills" / stem / "SKILL.md",
    }

    def target(self, rel):
        kind, name = rel.split("/", 1)
        return self.TARGETS[kind](self.claude, name[: -len(".md")])

    def install(self, rel, text):
        path = self.target(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def keep(self, rel, text):
        path = self.vault / "meta" / "local" / "kept" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def local_path(self, rel):
        return self.vault / "meta" / "local" / rel

    def lines_naming(self, out, text):
        return [ln for ln in out.splitlines() if text in ln]

    def test_appended_lines_become_an_addition_that_reads_current(self):
        """Adversarial where: extraction keeps the shipped text in the
        addition (so it is appended twice), drops the last appended line or
        the blank line inside it, or writes the local file without applying
        it so the listing says `not applied`. One agent, rule and skill each
        take lines after the shipped text: with a blank line inside the
        addition, with no blank line before it, and after shipped text that
        lacks a final newline."""
        rows = {
            "agents/researcher.md": (
                "# Researcher\n\nShipped protocol.\n",
                "\nAlways sweep upstream issues first.\n\nThen file a note.\n",
            ),
            "rules/compass-pipeline.md": (
                "# Pipeline\n\nShipped rules.\n",
                "Extra rule line.\n",
            ),
            "skills/autopilot.md": (
                "# Autopilot\n\nShipped steps.",
                "\nLocal step.\n",
            ),
        }
        for rel, (shipped, appended) in rows.items():
            with self.subTest(rel=rel):
                self.install(rel, shipped)
                self.keep(rel, shipped + appended)

                code, _ = self.run_cmd(["--extract", rel])

                self.assertEqual(code, 0)
                self.assertEqual(
                    self.local_path(rel).read_bytes().decode("utf-8").strip(),
                    appended.strip(),
                )
                _, listing = self.run_cmd([])
                row = [ln for ln in listing.splitlines() if ln.startswith(rel)]
                self.assertEqual(len(row), 1, listing)
                self.assertTrue(row[0].endswith("current"), row[0])
                text = self.target(rel).read_bytes().decode("utf-8")
                self.assertTrue(text.startswith(shipped.rstrip("\n")))
                self.assertEqual(text.count(shipped.strip().splitlines()[-1]), 1)
                self.assertIn(appended.strip(), text)

    def test_reworded_or_removed_shipped_lines_are_each_named_on_their_own_line(self):
        """Adversarial where: a reworded shipped line is silently turned
        into an addition (the shipped line and its reword both survive), a
        removed line is not reported at all, two such lines share one
        output line, or an untouched shipped line is reported. Rows: one
        reword, one removal, both together, and a reword with a real
        appended line, which still becomes the addition."""
        shipped = "# Researcher\n\nLine one.\nLine two.\nLine three.\n"
        rows = {
            "reword": (
                "# Researcher\n\nLine one.\nLine 2 reworded.\nLine three.\n",
                ["Line two."],
                ["Line one.", "Line three."],
            ),
            "removal": (
                "# Researcher\n\nLine one.\nLine three.\n",
                ["Line two."],
                ["Line one.", "Line three."],
            ),
            "reword and removal": (
                "# Researcher\n\nLine 1 reworded.\nLine two.\n",
                ["Line one.", "Line three."],
                ["Line two."],
            ),
            "reword and appended": (
                "# Researcher\n\nLine one.\nLine 2 reworded.\nLine three.\nAppended note.\n",
                ["Line two."],
                ["Line one.", "Line three."],
            ),
        }
        rel = "agents/researcher.md"
        for name, (kept, named, unnamed) in rows.items():
            with self.subTest(row=name):
                shutil.rmtree(self.vault / "meta" / "local", ignore_errors=True)
                self.install(rel, shipped)
                self.keep(rel, kept)

                _, out = self.run_cmd(["--extract", rel])

                hits = []
                for line in named:
                    found = self.lines_naming(out, line)
                    self.assertEqual(len(found), 1, f"{line!r} in {out!r}")
                    hits.append(found[0])
                self.assertEqual(len(set(hits)), len(named), out)
                for line in unnamed:
                    self.assertEqual(self.lines_naming(out, line), [], out)
                added = (
                    self.local_path(rel).read_bytes().decode("utf-8")
                    if self.local_path(rel).exists()
                    else ""
                )
                self.assertNotIn("reworded", added)
                if "appended" in name:
                    self.assertEqual(added.strip(), "Appended note.")

    def test_nothing_to_extract_creates_no_addition_and_leaves_the_install_alone(self):
        """Adversarial where: extraction writes an empty local addition (a
        marker-only block in the install), or crashes, when there is no
        saved copy for the name or the saved copy equals the shipped text.
        Neither creates a local file or changes the installed bytes."""
        rel = "agents/researcher.md"
        shipped = "# Researcher\n\nShipped protocol.\n"
        self.install(rel, shipped)
        before = self.target(rel).read_bytes()

        self.run_cmd(["--extract", rel])
        self.assertFalse(self.local_path(rel).exists(), "no saved copy, yet a local file")
        self.assertEqual(self.target(rel).read_bytes(), before)

        self.keep(rel, shipped)
        self.run_cmd(["--extract", rel])
        self.assertFalse(self.local_path(rel).exists(), "identical copy, yet a local file")

        self.keep(rel, shipped + "One added line.\n")
        self.run_cmd(["--extract", rel])
        self.assertEqual(
            self.local_path(rel).read_bytes().decode("utf-8").strip(), "One added line."
        )


if __name__ == "__main__":
    unittest.main()
