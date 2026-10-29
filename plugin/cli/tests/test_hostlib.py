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

    def test_context_check_is_left_out_while_sync_stays(self):
        # Defect class: dsh pays a Python start on every tool call for a
        # check that reads an empty transcript path and can never halt.
        data, _ = self._materialize()
        commands = [h["command"] for groups in data["hooks"].values()
                    for g in groups for h in g["hooks"]]
        self.assertFalse(any("context-check" in c for c in commands))
        self.assertTrue(any(" sync --hook" in c for c in commands))

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

    def test_guard_prelude_and_stdin_pipe_reduce_to_the_bare_invocation(self):
        # Defect class: the guard's shell prelude (CLI-exists check, agent-id
        # pre-filter, printf pipe) survives into the dsh form, where no sh
        # runs it, or the regex misses and the whole sh wrapper ships.
        data, _ = self._materialize()
        cmds = [h["command"] for g in data["hooks"].get("PreToolUse", []) for h in g["hooks"]]
        self.assertEqual(len(cmds), 1, cmds)
        cmd = cmds[0]
        self.assertTrue(cmd.endswith('/.claude/cli/compass" guard --hook'), cmd)
        for leftover in ("input=", "case ", "printf", "[ -f", "exit 0"):
            self.assertNotIn(leftover, cmd)

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
    tool names; a name with no dsh equivalent is reported, never guessed.

    The shipped agents live at `templates/agents/` in the plugin source and
    at `agents/` in a vendored `.claude/` install; both layouts carry the
    same `tools:` fields, so the whole-roster sweep runs in either."""

    _BASE = Path(__file__).resolve().parents[2]
    AGENTS_DIR = (_BASE / "templates" / "agents") if (
        _BASE / "templates" / "agents").is_dir() else (_BASE / "agents")

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


# ---------------------------------------------------------------------------
# Local additions in the dsh materializations
# ---------------------------------------------------------------------------

SHIPPED_SKILL = (
    "---\n"
    "name: lessons\n"
    "description: How to search lessons.\n"
    'when_to_use: "Use when searching lessons."\n'
    "---\n\n# Lessons\n\nBody text.\n")

# The dsh dialect output for SHIPPED_SKILL when no addition exists.
SHIPPED_SKILL_AS_DSH = (
    "---\n"
    "name: compass-lessons\n"
    "description: How to search lessons.\n"
    'whenToUse: "Use when searching lessons."\n'
    "---\n\n# Lessons\n\nBody text.\n")

OTHER_SKILL = (
    "---\nname: pipeline\ndescription: Pipeline skill.\n---\n\n# Pipe\n\nText.\n")

RULES_COMMENT = (
    "<!-- Generated by compass for the dsh host; self-update regenerates"
    " this section. Claude Code reads these rules from .claude/rules/"
    " instead and never loads this file. -->")

PIPELINE_RULE = "# Pipeline Rules\n\nSpecs capture the problem.\n"
WIKILINKS_RULE = "# Wikilinks\n\nUse wikilinks.\n"


def _marker(kind, name):
    from commands import overlay
    return overlay.MARKER.format(source=f"{overlay.LOCAL_DIR}/{kind}/{name}.md")


def _write_addition(project, kind, name, text=None, raw=None):
    path = Path(project) / ".compass" / "meta" / "local" / kind / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw if raw is not None else text.encode("utf-8"))
    return path


def _skills_src(test_case, skills):
    src = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, src, True)
    for name, text in skills.items():
        d = src / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(text, encoding="utf-8")
    return src / "skills"


def _rules_src(test_case):
    src = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, src, True)
    rules = src / "rules"
    rules.mkdir()
    (rules / "pipeline.md").write_text(PIPELINE_RULE, encoding="utf-8")
    (rules / "wikilinks.md").write_text(WIKILINKS_RULE, encoding="utf-8")
    return rules


def _dsh_skill(project, name="lessons"):
    return (Path(project) / ".dsh" / "skills" / f"compass-{name}" / "SKILL.md"
            ).read_text(encoding="utf-8")


def _tree(root):
    """Relative path -> bytes for every file under `root`."""
    root = Path(root)
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _rules_section(bodies):
    return "\n".join([
        hostlib.RULES_BEGIN, RULES_COMMENT, "\n\n".join(bodies), hostlib.RULES_END])


class DshSkillAdditionTests(unittest.TestCase):
    """A shipped skill's local addition reaches `.dsh/skills/compass-<name>`
    under the marker `compass overlay` uses, and nothing else does."""

    def _build(self, project, skills=None):
        skills = skills or {"lessons": SHIPPED_SKILL, "pipeline": OTHER_SKILL}
        hostlib.materialize_dsh_skills(project, _skills_src(self, skills))

    def test_addition_lands_once_at_the_end_under_the_marker(self):
        """Adversarial where: an addition is dropped, doubled, put above the
        shipped body, or mangled by the frontmatter split (an addition that
        itself holds `---` lines), or leaks a BOM or CR from a Windows-edited
        local file; or it bleeds into a sibling skill."""
        marker = _marker("skills", "lessons")
        rows = {
            "plain": ("Prefer lessons tagged `dsh`.\n", "Prefer lessons tagged `dsh`."),
            "padded with blank lines": (
                "\n\n  Indented first line.\nSecond.\n\n\n",
                "Indented first line.\nSecond."),
            "holds frontmatter-like fences": (
                "---\nname: evil\n---\nAfter the fence.\n",
                "---\nname: evil\n---\nAfter the fence."),
        }
        for label, (written, expected) in rows.items():
            with self.subTest(row=label):
                project = make_project(self)
                _write_addition(project, "skills", "lessons", written)
                self._build(project)
                text = _dsh_skill(project)
                tail = f"\n\n{marker}\n\n{expected}\n"
                self.assertEqual(text.count(marker), 1)
                self.assertEqual(text.count(expected), 1)
                self.assertTrue(text.endswith(tail), text)
                self.assertEqual(text[: -len(tail)] + "\n", SHIPPED_SKILL_AS_DSH)
                self.assertEqual(_dsh_skill(project, "pipeline").count(marker), 0)
        with self.subTest(row="windows-edited file"):
            project = make_project(self)
            _write_addition(project, "skills", "lessons",
                            raw=b"\xef\xbb\xbfWin line one.\r\nWin line two.\r\n")
            self._build(project)
            text = _dsh_skill(project)
            self.assertTrue(
                text.endswith(f"\n\n{marker}\n\nWin line one.\nWin line two.\n"), text)
            self.assertNotIn("\r", text)
            self.assertNotIn("\ufeff", text)

    def test_rerun_is_stable_and_an_edit_replaces_its_own_block(self):
        """Adversarial where: a second build stacks a second copy of the
        addition, an edited addition leaves its old text beside the new, or a
        removed or emptied addition leaves its block in the skill."""
        marker = _marker("skills", "lessons")
        project = make_project(self)
        path = _write_addition(project, "skills", "lessons", "Version one.\n")
        self._build(project)
        first = _dsh_skill(project)
        self._build(project)
        self.assertEqual(_dsh_skill(project), first)
        self.assertEqual(first.count("Version one."), 1)

        path.write_text("Version two.\n", encoding="utf-8")
        self._build(project)
        edited = _dsh_skill(project)
        self.assertNotIn("Version one.", edited)
        self.assertEqual(edited.count("Version two."), 1)
        self.assertEqual(edited.count(marker), 1)

        path.write_text("  \n\n", encoding="utf-8")
        self._build(project)
        self.assertEqual(_dsh_skill(project), SHIPPED_SKILL_AS_DSH)

        path.write_text("Version three.\n", encoding="utf-8")
        self._build(project)
        path.unlink()
        self._build(project)
        self.assertEqual(_dsh_skill(project), SHIPPED_SKILL_AS_DSH,
                         "a deleted addition file leaves no block")

    def test_without_an_applicable_addition_the_output_is_byte_identical(self):
        """Adversarial where: the append path perturbs a skill that has no
        addition (extra newline, marker, changed frontmatter), or an
        unrelated local file (an agent addition, a rule addition, a
        whitespace-only skill addition) changes the dsh tree."""
        baseline_project = make_project(self)
        self._build(baseline_project)
        self.assertEqual(_dsh_skill(baseline_project), SHIPPED_SKILL_AS_DSH)
        baseline = _tree(baseline_project / ".dsh")

        project = make_project(self)
        _write_addition(project, "agents", "researcher", "Agent-only text.\n")
        _write_addition(project, "rules", "lessons", "Rule-only text.\n")
        _write_addition(project, "skills", "lessons", " \n\n")
        self._build(project)
        self.assertEqual(_tree(project / ".dsh"), baseline)

    def test_addition_with_no_shipped_skill_reaches_nothing(self):
        """Adversarial where: an addition keyed on a name that is not a
        shipped skill (a project's own skill, a stale name, the
        `compass-`-prefixed dsh name, a different case, a prefix of a shipped
        name) creates a `compass-*` skill or lands in a sibling."""
        baseline_project = make_project(self)
        self._build(baseline_project)
        baseline = _tree(baseline_project / ".dsh")

        project = make_project(self)
        for name in ("my-own", "compass-lessons", "Lessons", "less"):
            _write_addition(project, "skills", name, f"Orphan text for {name}.\n")
        self._build(project)
        self.assertEqual(_tree(project / ".dsh"), baseline)
        self.assertFalse((project / ".dsh" / "skills" / "compass-my-own").exists())

    def test_a_rule_addition_does_not_reach_a_skill_of_the_same_name(self):
        """Adversarial where: the lookup ignores the kind directory, so
        `meta/local/rules/pipeline.md` is appended to the shipped skill
        `pipeline`."""
        baseline_project = make_project(self)
        self._build(baseline_project)
        project = make_project(self)
        _write_addition(project, "rules", "pipeline", "Rule text only.\n")
        self._build(project)
        self.assertEqual(_tree(project / ".dsh"), _tree(baseline_project / ".dsh"))

    def test_an_unreadable_addition_leaves_the_other_additions_landing(self):
        """Adversarial where: one addition with bytes that are not UTF-8
        raises out of the builder, so the update's dsh step dies and a good
        addition on a sibling skill never lands; asymmetric input, one bad
        file among a good one."""
        marker_good = _marker("skills", "lessons")
        project = make_project(self)
        _write_addition(project, "skills", "lessons", "Good text.\n")
        _write_addition(project, "skills", "pipeline", raw=b"ok \xff\xfe broken")
        self._build(project)
        self.assertTrue(
            _dsh_skill(project).endswith(f"\n\n{marker_good}\n\nGood text.\n"))
        self.assertNotIn("<!-- project-local overlay", _dsh_skill(project, "pipeline"))


class DshRuleAdditionTests(unittest.TestCase):
    """A shipped rule's local addition reaches the managed rules section of
    `AGENTS.md` under the overlay marker, and every byte outside that
    section stays the user's."""

    def _fold(self, project):
        hostlib.materialize_dsh_instructions(project, _rules_src(self))
        return (Path(project) / "AGENTS.md").read_text(encoding="utf-8")

    def test_rule_addition_lands_once_inside_the_section_after_its_rule(self):
        """Adversarial where: the addition lands outside the managed
        section, is doubled, attaches to the wrong rule, or moves bytes of
        the user's AGENTS.md text before or after the section."""
        marker = _marker("rules", "pipeline")
        before = "# My project\n\nNotes above.\n\n"
        after = "\n\nNotes below.\n"
        project = make_project(self)
        (project / "AGENTS.md").write_text(
            before + hostlib.RULES_BEGIN + "\nOLD\n" + hostlib.RULES_END + after,
            encoding="utf-8")
        _write_addition(project, "rules", "pipeline", "\nNo force pushes.\n\n")
        text = self._fold(project)

        self.assertTrue(text.startswith(before + hostlib.RULES_BEGIN))
        self.assertTrue(text.endswith(hostlib.RULES_END + after))
        begin, end = text.index(hostlib.RULES_BEGIN), text.index(hostlib.RULES_END)
        section = text[begin:end]
        self.assertEqual(text.count(marker), 1)
        self.assertEqual(text.count("No force pushes."), 1)
        self.assertEqual(section.count(marker), 1)
        self.assertEqual(section.count("No force pushes."), 1)
        self.assertLess(section.index("Specs capture the problem."), section.index(marker))
        self.assertLess(section.index("No force pushes."), section.index("# Wikilinks"))

    def test_rerun_is_stable_and_an_edit_replaces_its_own_block(self):
        """Adversarial where: refolding stacks another copy of the addition,
        an edited addition keeps its old text, or an emptied or removed
        addition leaves its block in the section."""
        project = make_project(self)
        path = _write_addition(project, "rules", "pipeline", "Rule v1.\n")
        first = self._fold(project)
        self.assertEqual(self._fold(project), first)
        self.assertEqual(first.count("Rule v1."), 1)

        path.write_text("Rule v2.\n", encoding="utf-8")
        edited = self._fold(project)
        self.assertNotIn("Rule v1.", edited)
        self.assertEqual(edited.count("Rule v2."), 1)
        self.assertEqual(edited.count(_marker("rules", "pipeline")), 1)

        path.write_text("\n \n", encoding="utf-8")
        plain = _rules_section([PIPELINE_RULE.strip(), WIKILINKS_RULE.strip()]) + "\n"
        self.assertEqual(self._fold(project), plain)

    def test_without_an_applicable_addition_the_output_is_byte_identical(self):
        """Adversarial where: the append path perturbs the section when no
        rule has an addition, or an unrelated local file (a skill addition,
        an agent addition, a whitespace-only rule addition) changes it."""
        plain = _rules_section([PIPELINE_RULE.strip(), WIKILINKS_RULE.strip()]) + "\n"
        clean = make_project(self)
        self.assertEqual(self._fold(clean), plain)

        project = make_project(self)
        _write_addition(project, "skills", "pipeline", "Skill-only text.\n")
        _write_addition(project, "agents", "builder", "Agent-only text.\n")
        _write_addition(project, "rules", "wikilinks", "   \n")
        self.assertEqual(self._fold(project), plain)

    def test_addition_with_no_shipped_rule_reaches_nothing(self):
        """Adversarial where: an addition keyed on a name that is not a
        shipped rule (a project-only rule, a prefix of a shipped name,
        a different case) is folded into the section."""
        plain = _rules_section([PIPELINE_RULE.strip(), WIKILINKS_RULE.strip()]) + "\n"
        project = make_project(self)
        for name in ("project-only", "pipe", "Pipeline"):
            _write_addition(project, "rules", name, f"Orphan text {name}.\n")
        self.assertEqual(self._fold(project), plain)


class DshAdditionsThroughUpdateTests(unittest.TestCase):
    """`self_update._apply` on a machine with dsh builds both dsh surfaces
    from the shipped source and the project's local additions together."""

    def _src(self):
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src, True)
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "plugin.json").write_text(
            '{"name": "compass", "version": "9.9.9"}', encoding="utf-8")
        (src / "templates" / "agents").mkdir(parents=True)
        (src / "templates" / "agents" / "builder.md").write_text("agent", encoding="utf-8")
        (src / "templates" / "rules").mkdir(parents=True)
        (src / "templates" / "rules" / "pipeline.md").write_text(
            PIPELINE_RULE, encoding="utf-8")
        (src / "skills" / "lessons").mkdir(parents=True)
        (src / "skills" / "lessons" / "SKILL.md").write_text(
            SHIPPED_SKILL, encoding="utf-8")
        (src / "cli").mkdir()
        (src / "cli" / "compass").write_text("#!", encoding="utf-8")
        (src / "hooks").mkdir()
        shutil.copy2(MANIFEST, src / "hooks" / "hooks.json")
        return src

    def test_update_puts_additions_in_dsh_and_never_copies_project_skills(self):
        """Adversarial where: the additions never reach `.dsh/skills` and
        `AGENTS.md` when the update builds them, or a project's own skill
        (installed under `.claude/skills`, with an addition of its own)
        becomes a `compass-*` copy."""
        from commands import self_update
        pin_dsh(self, True)
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        with_env(self, "DSH_HOME", str(home))
        project = make_project(self, "source: F:/x\nversion: 0.18.4\n")
        own = project / ".claude" / "skills" / "my-own" / "SKILL.md"
        own.parent.mkdir(parents=True)
        own.write_text(
            "---\nname: my-own\ndescription: Mine.\n---\n\nMine.\n", encoding="utf-8")
        _write_addition(project, "skills", "lessons", "Skill addition.\n")
        _write_addition(project, "skills", "my-own", "Own-skill addition.\n")
        _write_addition(project, "rules", "pipeline", "Rule addition.\n")

        self_update._apply(self._src(), project, apply_models=False)

        skill = _dsh_skill(project)
        self.assertEqual(skill.count(_marker("skills", "lessons")), 1)
        self.assertTrue(skill.endswith("Skill addition.\n"))
        self.assertFalse((project / ".dsh" / "skills" / "compass-my-own").exists())
        agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(_marker("rules", "pipeline")), 1)
        self.assertEqual(agents.count("Rule addition."), 1)
        self.assertNotIn("Own-skill addition.", agents)


class UpdateSkillStep4aTests(unittest.TestCase):
    """The update skill's step 4a regenerates the dsh surfaces from the
    clone the way `self_update.py` does."""

    def test_step_4a_builds_from_the_clone_not_the_installed_copy(self):
        """Adversarial where: step 4a feeds `.claude/skills` or
        `.claude/rules` to the dsh builders, so a project's own skills turn
        into `compass-*` copies and an installed file already holding a
        local addition is built a second time on top of it."""
        import re
        path = Path(__file__).resolve().parents[2] / "skills" / "update" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        start = text.index("### 4a.")
        section = text[start: text.index("### 4b.", start)]
        skills_call = re.search(r"materialize_dsh_skills\([^)]*\)", section)
        rules_call = re.search(r"materialize_dsh_instructions\([^)]*\)", section)
        self.assertIsNotNone(skills_call)
        self.assertIsNotNone(rules_call)
        self.assertIn("$SRC/skills", skills_call.group(0))
        self.assertIn("$SRC/templates/rules", rules_call.group(0))
        self.assertNotIn(".claude/skills", section)
        self.assertNotIn(".claude/rules", section)
        self.assertEqual(text.count("'.claude/skills'"), 0)
