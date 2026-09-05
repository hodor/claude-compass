"""Tests for the host seam: the roster in plugin.yaml and the dsh
hooks-file materializer.

Adversarial classes: a hostless plugin.yaml must behave exactly as today
(claude-code only, no .dsh/ artifacts created); the generated dsh hooks
file must carry no sh-dialect syntax dsh's PowerShell executor would choke
on, no events dsh's bridge does not parse, and no `if` fields; and
regeneration must be idempotent.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hostlib  # noqa: E402


def make_project(test_case, plugin_yaml=None):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    (tmp / ".compass" / "meta").mkdir(parents=True)
    if plugin_yaml is not None:
        (tmp / ".compass" / "meta" / "plugin.yaml").write_text(
            plugin_yaml, encoding="utf-8")
    return tmp


MANIFEST = Path(__file__).resolve().parents[2] / "hooks" / "hooks.json"


class ReadHostsTests(unittest.TestCase):
    def test_missing_plugin_yaml_defaults_to_claude_code(self):
        project = make_project(self)
        self.assertEqual(hostlib.read_hosts(project / ".compass"), ["claude-code"])

    def test_hostless_plugin_yaml_defaults_to_claude_code(self):
        project = make_project(self, "source: F:/x\nversion: 0.18.4\n")
        self.assertEqual(hostlib.read_hosts(project / ".compass"), ["claude-code"])

    def test_roster_parses_inline_list(self):
        project = make_project(
            self, "source: F:/x\nversion: 0.18.4\nhosts: [claude-code, dsh]\n")
        self.assertEqual(
            hostlib.read_hosts(project / ".compass"), ["claude-code", "dsh"])

    def test_roster_parses_nested_under_plugin_mapping(self):
        # The shape setup actually writes: fields indented under `plugin:`.
        project = make_project(
            self,
            "plugin:\n  name: compass\n  version: 0.18.4\n"
            "  hosts: [claude-code, dsh]\n")
        self.assertEqual(
            hostlib.read_hosts(project / ".compass"), ["claude-code", "dsh"])

    def test_unknown_host_names_survive_verbatim(self):
        # A newer roster read by an older CLI must not be silently dropped.
        project = make_project(
            self, "hosts: [claude-code, kimi-code]\n")
        self.assertIn("kimi-code", hostlib.read_hosts(project / ".compass"))


class MaterializeDshHooksTests(unittest.TestCase):
    def _materialize(self):
        project = make_project(self)
        hostlib.materialize_dsh_hooks(project, MANIFEST)
        out = project / ".dsh" / "hooks.json"
        self.assertTrue(out.is_file())
        return json.loads(out.read_text(encoding="utf-8")), project

    def test_commands_are_dialect_neutral(self):
        data, _ = self._materialize()
        for groups in data["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    cmd = h["command"]
                    self.assertNotIn("command -v", cmd)
                    self.assertNotIn("; then", cmd)
                    self.assertNotIn("fi", cmd.split()[-1])
                    self.assertTrue(cmd.startswith('python "${CLAUDE_PROJECT_DIR}'), cmd)

    def test_no_if_fields_and_no_unsupported_events(self):
        data, _ = self._materialize()
        self.assertNotIn("TeammateIdle", data["hooks"])
        for groups in data["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    self.assertNotIn("if", h)

    def test_posttooluse_matchers_cover_dsh_tool_names(self):
        data, _ = self._materialize()
        matchers = "|".join(
            g.get("matcher", "") for g in data["hooks"]["PostToolUse"])
        self.assertIn("write", matchers)
        self.assertIn("edit", matchers)

    def test_sessionstart_startup_matcher_survives(self):
        data, _ = self._materialize()
        self.assertIn(
            "startup",
            [g.get("matcher") for g in data["hooks"]["SessionStart"]])

    def test_regeneration_is_idempotent(self):
        data, project = self._materialize()
        hostlib.materialize_dsh_hooks(project, MANIFEST)
        again = json.loads(
            (project / ".dsh" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(data, again)


class ToolNameMapTests(unittest.TestCase):
    """Claude tool names from agent `tools:` frontmatter translate to dsh
    tool names; a name with no dsh equivalent is reported, never guessed."""

    AGENTS_DIR = Path(__file__).resolve().parents[2] / "templates" / "agents"

    def test_core_names_map_to_dsh_catalog_names(self):
        mapped, unmapped = hostlib.map_tools(
            ["Read", "Write", "Edit", "Bash", "Grep", "Glob",
             "WebSearch", "WebFetch", "Agent"], platform="linux")
        self.assertEqual(
            mapped,
            ["read", "write", "edit", "bash", "grep", "glob",
             "web_search", "web_fetch", "subagent"])
        self.assertEqual(unmapped, [])

    def test_bash_resolves_to_pwsh_on_windows_compositions(self):
        # A win32 composition registers pwsh and no bash; a filter naming
        # an unregistered tool fails the child's start loudly.
        mapped, _ = hostlib.map_tools(["Bash"], platform="win32")
        self.assertEqual(mapped, ["pwsh"])

    def test_unknown_name_lands_in_unmapped_not_guessed(self):
        mapped, unmapped = hostlib.map_tools(["Read", "LS", "AskUserQuestion"])
        self.assertEqual(mapped, ["read"])
        self.assertEqual(unmapped, ["LS", "AskUserQuestion"])

    def test_every_shipped_agent_tool_is_mapped_or_known_unmapped(self):
        # The table must consciously cover the whole shipped roster: every
        # name either maps or is a documented gap - nothing falls through.
        names = set()
        for f in self.AGENTS_DIR.glob("*.md"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("tools:"):
                    inner = line.split(":", 1)[1].strip().strip("[]")
                    names.update(n.strip() for n in inner.split(",") if n.strip())
        mapped, unmapped = hostlib.map_tools(sorted(names))
        self.assertTrue(names)
        for name in unmapped:
            self.assertIn(name, hostlib.KNOWN_UNMAPPED_TOOLS, name)


class MaterializeDshSkillsTests(unittest.TestCase):
    """Shipped skills rewritten into dsh's frontmatter dialect under
    `.dsh/skills/compass-<name>/`, never touching anything else there."""

    def _src_skills(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        d = src / "skills" / "lessons"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\n"
            "name: lessons\n"
            "description: How to search lessons.\n"
            "version: 1.0.0\n"
            "allowed-tools: [Read, Grep]\n"
            'when_to_use: "Use when searching lessons."\n'
            "---\n\n# Lessons\n\nBody text.\n",
            encoding="utf-8")
        return src

    def test_skill_transposed_into_dsh_dialect(self):
        project = make_project(self)
        hostlib.materialize_dsh_skills(project, self._src_skills() / "skills")
        out = project / ".dsh" / "skills" / "compass-lessons" / "SKILL.md"
        self.assertTrue(out.is_file())
        text = out.read_text(encoding="utf-8")
        self.assertIn("name: compass-lessons\n", text)
        self.assertIn("description: How to search lessons.\n", text)
        self.assertIn('whenToUse: "Use when searching lessons."\n', text)
        self.assertIn("# Lessons\n\nBody text.\n", text)

    def test_user_skills_in_dsh_dir_never_touched(self):
        project = make_project(self)
        mine = project / ".dsh" / "skills" / "my-own" / "SKILL.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("---\nname: my-own\ndescription: mine\n---\nkeep\n",
                        encoding="utf-8")
        hostlib.materialize_dsh_skills(project, self._src_skills() / "skills")
        self.assertEqual(
            mine.read_text(encoding="utf-8"),
            "---\nname: my-own\ndescription: mine\n---\nkeep\n")

    def test_stale_compass_skill_removed_on_rematerialize(self):
        # A skill retired upstream must not linger; only compass-* dirs are
        # ours to remove.
        project = make_project(self)
        stale = project / ".dsh" / "skills" / "compass-retired" / "SKILL.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("---\nname: compass-retired\ndescription: old\n---\n",
                         encoding="utf-8")
        hostlib.materialize_dsh_skills(project, self._src_skills() / "skills")
        self.assertFalse(stale.parent.exists())
        self.assertTrue(
            (project / ".dsh" / "skills" / "compass-lessons").is_dir())


class MaterializeDshBundleTests(unittest.TestCase):
    """The generated bundle: dsh's manifest contract, one delegation-tool
    row per shipped agent (persona from the markdown body, tool filter
    through the map), version mirroring the plugin so every update forces
    a pnpm re-add of the snapshot."""

    def _src(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "compass", "version": "9.9.9"}', encoding="utf-8")
        agents = src / "templates" / "agents"
        agents.mkdir(parents=True)
        (agents / "builder.md").write_text(
            "---\nname: builder\ndescription: Builds things.\n"
            "tools: [Read, Grep, Glob, Write, Edit, Bash, Agent]\n---\n\n"
            "You are the builder. Follow the plan.\n", encoding="utf-8")
        (agents / "debug.md").write_text(
            "---\nname: debug\ndescription: Investigates.\n"
            "tools: [Read, Grep, Glob, Bash, LS]\n---\n\n"
            "You investigate, read-only.\n", encoding="utf-8")
        return src

    def _generate(self):
        project = make_project(self)
        hostlib.materialize_dsh_bundle(project, self._src())
        pkg = json.loads(
            (project / ".dsh" / "compass-bundle" / "package.json").read_text(
                encoding="utf-8"))
        patch = (project / ".dsh" / "compass-bundle" / "cordis.patch.yml").read_text(
            encoding="utf-8")
        return pkg, patch

    def test_manifest_contract_and_version_mirror(self):
        pkg, _ = self._generate()
        self.assertEqual(pkg["dsh"]["bundle"]["patch"], "./cordis.patch.yml")
        self.assertEqual(pkg["version"], "9.9.9")

    def test_hooks_mount_relative_config_path_absolute_project_dir(self):
        _, patch = self._generate()
        self.assertIn("'@deepseek-ai/dsh-hooks-claude-code'", patch)
        self.assertIn("configPath: .dsh/hooks.json", patch)
        # Without projectDir the ${CLAUDE_PROJECT_DIR} token reaches
        # PowerShell unsubstituted; the generated bundle carries the
        # absolute path.
        self.assertIn("projectDir: '", patch)

    def test_one_delegation_row_per_agent_with_persona_and_filter(self):
        _, patch = self._generate()
        self.assertIn("toolName: compass_builder", patch)
        self.assertIn("toolName: compass_debug", patch)
        self.assertIn("You are the builder. Follow the plan.", patch)
        self.assertIn("provider: spawn", patch)
        # debug's filter: mapped names only; LS has no dsh equivalent, and
        # the shell resolves per the generating machine's platform.
        shell = "pwsh" if sys.platform == "win32" else "bash"
        self.assertIn(f"allow: [read, grep, glob, {shell}]", patch)

    def test_agent_tool_grants_the_other_delegation_instances(self):
        _, patch = self._generate()
        # builder carries Agent: its allow list names the compass_* tools,
        # never a bare `subagent` (no tool of that name exists here, and an
        # unknown name fails the mount).
        self.assertNotIn("subagent]", patch.replace("compass_debug]", ""))
        builder_allow = [l for l in patch.splitlines()
                        if "allow:" in l and "compass_debug" in l]
        self.assertTrue(builder_allow, patch)

    def test_no_service_rows_the_base_bundle_already_registers(self):
        # dsh-base mounts the subagents service and the `spawn` provider;
        # re-mounting either fails the boot loudly ("service ... has been
        # registered"). The bundle only adds delegation-tool instances.
        _, patch = self._generate()
        self.assertNotIn("'@deepseek-ai/dsh-subagent'", patch)
        self.assertNotIn("'@deepseek-ai/dsh-subagent-spawn-in-process'", patch)


class ApplyHostLoopTests(unittest.TestCase):
    """`self_update._apply` refreshes every rostered host in one run."""

    def _src(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "compass", "version": "9.9.9"}', encoding="utf-8")
        (src / "templates" / "agents").mkdir(parents=True)
        (src / "templates" / "agents" / "builder.md").write_text("agent", encoding="utf-8")
        (src / "templates" / "rules").mkdir(parents=True)
        (src / "skills" / "s").mkdir(parents=True)
        (src / "skills" / "s" / "SKILL.md").write_text("skill", encoding="utf-8")
        (src / "cli").mkdir()
        (src / "cli" / "compass").write_text("#!", encoding="utf-8")
        (src / "hooks").mkdir()
        shutil.copy2(MANIFEST, src / "hooks" / "hooks.json")
        return src

    def test_dual_roster_gets_both_materializations_in_one_apply(self):
        from commands import self_update
        project = make_project(
            self, "source: F:/x\nversion: 0.18.4\nhosts: [claude-code, dsh]\n")
        self_update._apply(self._src(), project, apply_models=False)
        self.assertTrue((project / ".claude" / "agents" / "builder.md").is_file())
        self.assertTrue((project / ".dsh" / "hooks.json").is_file())

    def test_default_roster_behaves_exactly_as_today(self):
        from commands import self_update
        project = make_project(self, "source: F:/x\nversion: 0.18.4\n")
        self_update._apply(self._src(), project, apply_models=False)
        self.assertTrue((project / ".claude" / "agents" / "builder.md").is_file())
        self.assertFalse((project / ".dsh").exists())


if __name__ == "__main__":
    unittest.main()
