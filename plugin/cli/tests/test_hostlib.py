"""Tests for the host seam: dsh detection, the roster in plugin.yaml, and
the dsh hooks-file materializer.

Adversarial classes: a machine without dsh must see zero dsh-shaped writes
even when a committed roster names dsh, and a machine with dsh must
materialize with no plugin.yaml field at all (SPEC-006 D-05); the
generated dsh hooks file must carry no sh-dialect syntax dsh's PowerShell
executor would choke on, no events dsh's bridge does not parse, and no
`if` fields; and regeneration must be idempotent. Every test that reaches
detection pins it, so the suite passes identically on machines with and
without dsh.
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


def pin_dsh(test_case, present):
    """Pin `hostlib.dsh_available` so the test's outcome does not depend on
    whether the machine running the suite has dsh."""
    real = hostlib.dsh_available
    hostlib.dsh_available = lambda: present
    test_case.addCleanup(setattr, hostlib, "dsh_available", real)


def with_env(test_case, name, value):
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    test_case.addCleanup(
        lambda: os.environ.__setitem__(name, old) if old is not None
        else os.environ.pop(name, None))


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


class DshAvailableTests(unittest.TestCase):
    """Detection reads the machine: the binary on PATH, or the harness
    home directory a dsh install leaves behind."""

    def _pin_which(self, result):
        real = shutil.which
        shutil.which = lambda name: result if name == "dsh" else None
        self.addCleanup(setattr, shutil, "which", real)

    def test_binary_on_path_counts(self):
        self._pin_which("X:/dsh.cmd")
        with_env(self, "DSH_HOME", str(Path(tempfile.mkdtemp()) / "absent"))
        self.assertTrue(hostlib.dsh_available())

    def test_harness_home_directory_counts_without_binary(self):
        self._pin_which(None)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        with_env(self, "DSH_HOME", str(home))
        self.assertTrue(hostlib.dsh_available())

    def test_neither_means_no_dsh(self):
        self._pin_which(None)
        with_env(self, "DSH_HOME", str(Path(tempfile.mkdtemp()) / "absent"))
        self.assertFalse(hostlib.dsh_available())


class EffectiveHostsTests(unittest.TestCase):
    """The hosts an apply serves: the machine is the truth for dsh, in
    both directions (SPEC-006 D-05)."""

    def test_machine_with_dsh_adds_it_to_a_hostless_project(self):
        pin_dsh(self, True)
        project = make_project(self, "source: F:/x\nversion: 0.22.0\n")
        self.assertEqual(
            hostlib.effective_hosts(project / ".compass"),
            ["claude-code", "dsh"])

    def test_machine_with_dsh_does_not_double_a_rostered_entry(self):
        pin_dsh(self, True)
        project = make_project(self, "hosts: [claude-code, dsh]\n")
        self.assertEqual(
            hostlib.effective_hosts(project / ".compass"),
            ["claude-code", "dsh"])

    def test_machine_without_dsh_drops_an_explicit_roster_entry(self):
        # A committed roster travels with the repo to machines that have no
        # dsh; those machines must see zero dsh-shaped behavior.
        pin_dsh(self, False)
        project = make_project(self, "hosts: [claude-code, dsh]\n")
        self.assertEqual(
            hostlib.effective_hosts(project / ".compass"), ["claude-code"])

    def test_unknown_host_names_survive_detection(self):
        pin_dsh(self, False)
        project = make_project(self, "hosts: [claude-code, kimi-code]\n")
        self.assertEqual(
            hostlib.effective_hosts(project / ".compass"),
            ["claude-code", "kimi-code"])


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
                    # Absolute project path baked in: the global bundle sets
                    # no projectDir, so no substitution token may survive.
                    self.assertNotIn("${CLAUDE_PROJECT_DIR}", cmd)
                    self.assertTrue(cmd.startswith('python "'), cmd)
                    self.assertIn("/.claude/cli/compass", cmd)

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


class MaterializeDshInstructionsTests(unittest.TestCase):
    """Rules folded into a fenced managed section of AGENTS.md - the one
    instruction surface dsh reads and Claude Code does not (the Wave 1
    matrix). User text outside the markers is never touched."""

    def _rules_src(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        rules = src / "templates" / "rules"
        rules.mkdir(parents=True)
        (rules / "pipeline.md").write_text(
            "# Pipeline Rules\n\nSpecs capture the problem.\n", encoding="utf-8")
        (rules / "wikilinks.md").write_text(
            "# Wikilinks\n\nUse wikilinks.\n", encoding="utf-8")
        return src

    def test_creates_agents_md_with_managed_section(self):
        project = make_project(self)
        hostlib.materialize_dsh_instructions(
            project, self._rules_src() / "templates" / "rules")
        text = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("compass:rules:begin", text)
        self.assertIn("Specs capture the problem.", text)
        self.assertIn("Use wikilinks.", text)
        self.assertIn("compass:rules:end", text)

    def test_user_content_preserved_byte_for_byte(self):
        project = make_project(self)
        user = "# My project\n\nHand-written notes stay.\n"
        (project / "AGENTS.md").write_text(user, encoding="utf-8")
        hostlib.materialize_dsh_instructions(
            project, self._rules_src() / "templates" / "rules")
        text = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith(user))
        self.assertIn("Specs capture the problem.", text)

    def test_refold_is_idempotent_and_replaces_in_place(self):
        project = make_project(self)
        (project / "AGENTS.md").write_text(
            "top\n<!-- compass:rules:begin -->\nOLD RULES\n"
            "<!-- compass:rules:end -->\nbottom\n", encoding="utf-8")
        src = self._rules_src() / "templates" / "rules"
        hostlib.materialize_dsh_instructions(project, src)
        first = (project / "AGENTS.md").read_text(encoding="utf-8")
        hostlib.materialize_dsh_instructions(project, src)
        self.assertEqual(first, (project / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertNotIn("OLD RULES", first)
        self.assertTrue(first.startswith("top\n"))
        self.assertTrue(first.rstrip().endswith("bottom"))


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
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        hostlib.materialize_dsh_bundle(home, self._src())
        pkg = json.loads(
            (home / "compass-bundle" / "package.json").read_text(
                encoding="utf-8"))
        patch = (home / "compass-bundle" / "cordis.patch.yml").read_text(
            encoding="utf-8")
        return pkg, patch

    def test_manifest_contract_and_version_mirror(self):
        pkg, _ = self._generate()
        self.assertEqual(pkg["dsh"]["bundle"]["patch"], "./cordis.patch.yml")
        self.assertEqual(pkg["version"], "9.9.9")

    def test_hooks_mount_is_project_agnostic(self):
        # One global bundle serves every folder: configPath resolves against
        # the launch cwd, and no projectDir ties the mount to one project -
        # the per-project hooks file carries absolute commands instead.
        _, patch = self._generate()
        self.assertIn("'@deepseek-ai/dsh-hooks-claude-code'", patch)
        self.assertIn("configPath: .dsh/hooks.json", patch)
        self.assertNotIn("projectDir", patch)

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

    def test_rows_carry_model_routes_from_the_dsh_catalog(self):
        # debug is a strong-tier agent, builder balanced; the dsh column
        # resolves tiers to provider routes written as agentOptions -
        # never into agent frontmatter.
        _, patch = self._generate()
        self.assertIn("provider: deepseek-official", patch)
        self.assertIn("model: deepseek-v4-pro", patch)
        self.assertIn("model: deepseek-v4-flash", patch)

    def test_no_service_rows_the_base_bundle_already_registers(self):
        # dsh-base mounts the subagents service and the `spawn` provider;
        # re-mounting either fails the boot loudly ("service ... has been
        # registered"). The bundle only adds delegation-tool instances.
        _, patch = self._generate()
        self.assertNotIn("'@deepseek-ai/dsh-subagent'", patch)
        self.assertNotIn("'@deepseek-ai/dsh-subagent-spawn-in-process'", patch)


class BootstrapMaterializerTests(unittest.TestCase):
    """The dsh-first bootstrap (SPEC-006 D-05): the bundle mounts a second
    bridge instance at an absolute machine-level hooks file whose one
    SessionStart command runs the generated bootstrap script against a
    plugin snapshot beside it. Adversarial classes from the live probes:
    dsh's hook sandbox silently blocks writes outside the session
    workspace, so the script must write only into the launch cwd; and a
    backslash in any generated command or script breaks silently across
    the nested quoting layers, so every generated string is escape-free."""

    def _src(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "compass", "version": "9.9.9"}', encoding="utf-8")
        (src / "templates" / "agents").mkdir(parents=True)
        (src / "templates" / "agents" / "builder.md").write_text(
            "---\nname: builder\ndescription: Builds.\ntools: [Read]\n---\n\nBody.\n",
            encoding="utf-8")
        (src / "templates" / "rules").mkdir(parents=True)
        (src / "templates" / "rules" / "r.md").write_text("A rule.\n", encoding="utf-8")
        (src / "skills" / "s").mkdir(parents=True)
        (src / "skills" / "s" / "SKILL.md").write_text(
            "---\nname: s\ndescription: d\n---\n\nbody\n", encoding="utf-8")
        shutil.copytree(
            Path(__file__).resolve().parents[1], src / "cli",
            ignore=shutil.ignore_patterns("__pycache__", "tests"))
        (src / "hooks").mkdir()
        shutil.copy2(MANIFEST, src / "hooks" / "hooks.json")
        return src

    def _home(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        with_env(self, "DSH_HOME", str(home))
        return home

    def test_bundle_mounts_both_bridge_instances(self):
        home = self._home()
        hostlib.materialize_dsh_bundle(home, self._src())
        patch = (home / "compass-bundle" / "cordis.patch.yml").read_text(
            encoding="utf-8")
        self.assertEqual(patch.count("'@deepseek-ai/dsh-hooks-claude-code'"), 2)
        self.assertIn("configPath: .dsh/hooks.json", patch)
        self.assertIn(
            f"configPath: {(home / 'compass-bootstrap-hooks.json').as_posix()}",
            patch)

    def test_bootstrap_artifacts_are_generated_and_escape_free(self):
        home = self._home()
        hostlib.materialize_dsh_bundle(home, self._src())
        hooks = json.loads(
            (home / "compass-bootstrap-hooks.json").read_text(encoding="utf-8"))
        row = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertIn((home / "compass-bootstrap.py").as_posix(), row["command"])
        self.assertIn("timeout", row)
        script = (home / "compass-bootstrap.py").read_text(encoding="utf-8")
        # The silent-mangling class: a backslash anywhere in a generated
        # command or script dies in some nested quoting layer.
        self.assertNotIn(chr(92), row["command"])
        self.assertNotIn(chr(92), script)
        self.assertTrue((home / "compass-plugin-src" / "cli").is_dir())
        self.assertTrue(
            (home / "compass-plugin-src" / "hooks" / "hooks.json").is_file())

    def _run_bootstrap(self, home, cwd):
        import subprocess
        return subprocess.run(
            [sys.executable, str(home / "compass-bootstrap.py")],
            capture_output=True, text=True, timeout=120, cwd=str(cwd),
            env={**os.environ, "DSH_HOME": str(home)})

    def test_bootstrap_ignores_a_folder_without_a_vault(self):
        home = self._home()
        hostlib.materialize_dsh_bundle(home, self._src())
        plain = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, plain, True)
        result = self._run_bootstrap(home, plain)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(list(plain.iterdir()), [])

    def test_bootstrap_materializes_a_dsh_first_project(self):
        home = self._home()
        hostlib.materialize_dsh_bundle(home, self._src())
        project = make_project(
            self, "plugin:\n  name: compass\n  version: 9.9.9\n")
        result = self._run_bootstrap(home, project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bootstrapped", result.stdout)
        self.assertTrue((project / ".claude" / "cli" / "compass").is_file())
        self.assertTrue((project / ".dsh" / "hooks.json").is_file())
        self.assertTrue((project / "AGENTS.md").is_file())

    def test_bootstrap_leaves_a_complete_install_untouched(self):
        home = self._home()
        hostlib.materialize_dsh_bundle(home, self._src())
        project = make_project(self)
        sentinel_hooks = project / ".dsh" / "hooks.json"
        sentinel_hooks.parent.mkdir(parents=True)
        sentinel_hooks.write_text("{}", encoding="utf-8")
        sentinel_cli = project / ".claude" / "cli" / "compass"
        sentinel_cli.parent.mkdir(parents=True)
        sentinel_cli.write_text("sentinel", encoding="utf-8")
        result = self._run_bootstrap(home, project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(sentinel_cli.read_text(encoding="utf-8"), "sentinel")
        self.assertEqual(sentinel_hooks.read_text(encoding="utf-8"), "{}")


class ApplyHostLoopTests(unittest.TestCase):
    """`self_update._apply` refreshes every effective host in one run;
    which hosts are effective is detected, never read from a question."""

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

    def _isolate_home(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        old = os.environ.get("DSH_HOME")
        os.environ["DSH_HOME"] = str(home)
        self.addCleanup(
            lambda: os.environ.__setitem__("DSH_HOME", old) if old
            else os.environ.pop("DSH_HOME", None))
        return home

    def test_machine_with_dsh_materializes_from_a_hostless_project(self):
        # No plugin.yaml field, no question: dsh on the machine is the
        # whole trigger (SPEC-006 D-05).
        from commands import self_update
        pin_dsh(self, True)
        home = self._isolate_home()
        project = make_project(self, "source: F:/x\nversion: 0.18.4\n")
        self_update._apply(self._src(), project, apply_models=False)
        self.assertTrue((project / ".claude" / "agents" / "builder.md").is_file())
        self.assertTrue((project / ".dsh" / "hooks.json").is_file())
        self.assertTrue((home / "compass-bundle" / "package.json").is_file())

    def test_machine_without_dsh_writes_nothing_dsh_shaped(self):
        # Even an explicit committed roster must not produce dsh writes on
        # a machine that has no dsh - the no-pollution guard.
        from commands import self_update
        pin_dsh(self, False)
        home = self._isolate_home()
        project = make_project(
            self, "source: F:/x\nversion: 0.18.4\nhosts: [claude-code, dsh]\n")
        self_update._apply(self._src(), project, apply_models=False)
        self.assertTrue((project / ".claude" / "agents" / "builder.md").is_file())
        self.assertFalse((project / ".dsh").exists())
        self.assertFalse((home / "compass-bundle").exists())


if __name__ == "__main__":
    unittest.main()


class InstallDshBundleTests(unittest.TestCase):
    """The generated bundle installs itself into every profile under the
    harness home: copied into node_modules, recorded as a file: dependency
    so pnpm operations keep it, and listed in dsh.profile.bundles - no
    manual `dsh plugin add`, refreshed on every apply."""

    def _home_with_profile(self, name="headless"):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        profile = home / "profiles" / name
        profile.mkdir(parents=True)
        (profile / "package.json").write_text(json.dumps({
            "name": f"dsh-profile-{name}", "private": True,
            "dependencies": {},
            "dsh": {"profile": {"bundles": ["@deepseek-ai/dsh-base"],
                                "patchReload": "startup"}},
        }), encoding="utf-8")
        return home

    def _src(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "compass", "version": "9.9.9"}', encoding="utf-8")
        (src / "templates" / "agents").mkdir(parents=True)
        return src

    def test_bundle_lands_in_profile_and_manifest(self):
        home = self._home_with_profile()
        hostlib.materialize_dsh_bundle(home, self._src())
        installed = hostlib.install_dsh_bundle(home)
        self.assertEqual(installed, ["headless"])
        profile = home / "profiles" / "headless"
        self.assertTrue(
            (profile / "node_modules" / "compass-dsh-bundle" / "package.json").is_file())
        pkg = json.loads((profile / "package.json").read_text(encoding="utf-8"))
        self.assertIn("compass-dsh-bundle", pkg["dsh"]["profile"]["bundles"])
        self.assertIn("compass-dsh-bundle", pkg["dependencies"])

    def test_reinstall_refreshes_the_copy(self):
        home = self._home_with_profile()
        hostlib.materialize_dsh_bundle(home, self._src())
        hostlib.install_dsh_bundle(home)
        stale = (home / "profiles" / "headless" / "node_modules"
                 / "compass-dsh-bundle" / "cordis.patch.yml")
        stale.write_text("stale", encoding="utf-8")
        hostlib.install_dsh_bundle(home)
        self.assertNotEqual(stale.read_text(encoding="utf-8"), "stale")

    def test_no_profiles_is_a_reported_noop(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        hostlib.materialize_dsh_bundle(home, self._src())
        self.assertEqual(hostlib.install_dsh_bundle(home), [])
