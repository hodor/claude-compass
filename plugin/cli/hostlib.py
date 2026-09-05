"""Host roster and per-host materializers for multi-host installs.

A project's `.compass/meta/plugin.yaml` may carry a `hosts:` list naming
every agent CLI the project uses (`claude-code`, `dsh`, ...). A plugin.yaml
without the field means `[claude-code]`, so every install that predates the
roster behaves exactly as before. `self_update._apply` refreshes every
rostered host in one run - the invariant that no two hosts of one project
can sit on different Compass versions (SPEC-006 D-04).

The dsh materializer generates `.dsh/hooks.json` from the canonical hook
manifest. dsh executes hooks through PowerShell on Windows, so the sh
wrapper (`if command -v python3 ...`) is reduced to the dialect-neutral
form `python "${CLAUDE_PROJECT_DIR}/..."`: dsh substitutes the `${...}`
token at parse time, and a POSIX shell reads the same token as an env-var
expansion. Events dsh's bridge does not parse and `if` fields (Claude Code
permission-pattern syntax) are dropped from the generated file.
"""

import json
import re
import shutil
import sys
from pathlib import Path

import vaultlib

DEFAULT_HOSTS = ["claude-code"]

# The events dsh's hooks-claude-code bridge parses
# (deepseek-harness packages/hooks/hooks-claude-code/src/config.ts).
DSH_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "SubagentStart",
    "SubagentStop",
}

# plugin.yaml nests its fields under a `plugin:` mapping, so the field is
# usually indented; a top-level `hosts:` is accepted too.
_HOSTS_LINE = re.compile(r"^[ \t]*hosts:\s*(\[.*\])\s*$", re.MULTILINE)

# The manifest's sh wrapper: `if command -v python3 ...; then python3 X; else python X; fi`.
# The python3 branch carries the invocation to keep.
_SH_WRAPPER = re.compile(r"^if command -v python3.*?then\s+python3\s+(.*?);\s*else.*fi$")


def read_hosts(vault_root):
    """The project's host roster from plugin.yaml; `[claude-code]` when the
    file or the field is absent. Unknown names pass through verbatim so a
    newer roster read by an older CLI is never silently narrowed."""
    path = Path(vault_root) / "meta" / "plugin.yaml"
    if not path.is_file():
        return list(DEFAULT_HOSTS)
    match = _HOSTS_LINE.search(vaultlib.read_vault_text(path))
    if not match:
        return list(DEFAULT_HOSTS)
    hosts = vaultlib._split_inline_list(match.group(1)[1:-1])
    return [h for h in hosts if h] or list(DEFAULT_HOSTS)


# Claude tool name -> dsh tool name, from dsh's generated tool catalog
# (deepseek-harness docs/tool-catalog.md). `Agent` maps to the delegation
# tool's default registered name. `Bash` is resolved per platform in
# `map_tools`: a Windows composition registers `pwsh` and no `bash`, and a
# tool filter naming an unregistered tool fails the child's start loudly.
TOOL_NAME_MAP = {
    "Read": "read",
    "Write": "write",
    "Edit": "edit",
    "MultiEdit": "edit",
    "Grep": "grep",
    "Glob": "glob",
    "WebSearch": "web_search",
    "WebFetch": "web_fetch",
    "Agent": "subagent",
}

# Claude tool names with no dsh equivalent: dsh has no standalone directory
# lister, and interactive question tools are host-specific. An agent whose
# filter names one of these simply lacks that tool on dsh.
KNOWN_UNMAPPED_TOOLS = {"LS", "AskUserQuestion", "NotebookEdit", "Task"}


def map_tools(names, platform=None):
    """Translate Claude tool names to dsh tool names for the composition
    this machine runs. Returns `(mapped, unmapped)`; an unknown name is
    reported in `unmapped`, never guessed at."""
    shell = "pwsh" if (platform or sys.platform) == "win32" else "bash"
    mapped, unmapped = [], []
    for name in names:
        target = shell if name == "Bash" else TOOL_NAME_MAP.get(name)
        if target is None:
            unmapped.append(name)
        elif target not in mapped:
            mapped.append(target)
    return mapped, unmapped


def materialize_dsh_skills(project_root, skills_src):
    """Write every shipped skill to `.dsh/skills/compass-<name>/SKILL.md`
    in dsh's frontmatter dialect, body verbatim. Compass-owned dirs
    (`compass-*`) not shipped anymore are removed; everything else under
    `.dsh/skills/` belongs to the user and is never touched. Returns the
    number of skills written."""
    dest_root = Path(project_root) / ".dsh" / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)
    shipped = set()
    written = 0
    for skill_dir in sorted(Path(skills_src).iterdir()):
        source = skill_dir / "SKILL.md"
        if not source.is_file():
            continue
        text = vaultlib.read_vault_text(source)
        data, error = vaultlib.parse_frontmatter_text(text)
        if error:
            continue
        name = f"compass-{skill_dir.name}"
        shipped.add(name)
        body = text.split("---\n", 2)[2] if text.count("---\n") >= 2 else ""
        lines = ["---", f"name: {name}"]
        if data.get("description"):
            lines.append(f"description: {data['description']}")
        if data.get("when_to_use"):
            lines.append(f"whenToUse: {vaultlib.yaml_double_quote(data['when_to_use'])}")
        lines.append("---")
        dest = dest_root / name
        dest.mkdir(parents=True, exist_ok=True)
        vaultlib.write_text_lf(dest / "SKILL.md", "\n".join(lines) + "\n" + body)
        written += 1
    for existing in dest_root.iterdir():
        if existing.is_dir() and existing.name.startswith("compass-") \
                and existing.name not in shipped:
            shutil.rmtree(existing, ignore_errors=True)
    return written


RULES_BEGIN = "<!-- compass:rules:begin -->"
RULES_END = "<!-- compass:rules:end -->"


def materialize_dsh_instructions(project_root, rules_src):
    """Fold the shipped rules into a fenced managed section of the
    project's `AGENTS.md` - the instruction surface dsh loads and Claude
    Code does not, so a dual-host project sees each rule exactly once
    (SPEC-006 D-04). The section regenerates in place between its markers;
    every byte outside them is the user's and is never touched. Returns
    the path written."""
    body = []
    for path in sorted(Path(rules_src).glob("*.md")):
        body.append(vaultlib.read_vault_text(path).strip())
    section = "\n".join([
        RULES_BEGIN,
        "<!-- Generated by compass for the dsh host; self-update regenerates"
        " this section. Claude Code reads these rules from .claude/rules/"
        " instead and never loads this file. -->",
        "\n\n".join(body),
        RULES_END,
    ])
    dest = Path(project_root) / "AGENTS.md"
    if dest.is_file():
        text = vaultlib.read_vault_text(dest)
        begin, end = text.find(RULES_BEGIN), text.find(RULES_END)
        if begin != -1 and end != -1:
            text = text[:begin] + section + text[end + len(RULES_END):]
        else:
            text = text.rstrip("\n") + "\n\n" + section + "\n"
    else:
        text = section + "\n"
    vaultlib.write_text_lf(dest, text)
    return dest


def _neutral_command(command):
    """The dialect-neutral form of a manifest hook command: the sh
    python3/python fallback wrapper reduces to a bare `python` invocation
    with the `${CLAUDE_PROJECT_DIR}` token kept for parse-time
    substitution. A command that carries no wrapper passes through."""
    match = _SH_WRAPPER.match(command.strip())
    if match:
        command = "python " + match.group(1)
    return command.replace('"$CLAUDE_PROJECT_DIR', '"${CLAUDE_PROJECT_DIR}')


def _yaml_block(text, indent):
    """`text` as a YAML literal block scalar body, each line indented."""
    pad = " " * indent
    lines = [pad + line if line.strip() else "" for line in text.split("\n")]
    return "\n".join(lines).rstrip("\n")


def _agent_rows(agents_src, vault_root=None):
    """One delegation-tool row per agent markdown file: persona from the
    body, tool filter through the name map, model route from the model
    policy's dsh column as `agentOptions`. An agent whose `tools:` carry
    `Agent` is granted the other agents' delegation tools by their real
    registered names - a bare `subagent` names no tool in this composition
    and would fail the mount."""
    import modelslib
    config, _ = modelslib.load_project_config(vault_root)
    agents = []
    for path in sorted(Path(agents_src).glob("*.md")):
        text = vaultlib.read_vault_text(path)
        data, error = vaultlib.parse_frontmatter_text(text)
        if error:
            continue
        body = text.split("---\n", 2)[2].strip() if text.count("---\n") >= 2 else ""
        tools = data.get("tools") or []
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.strip("[]").split(",") if t.strip()]
        agents.append({"stem": path.stem, "body": body, "tools": tools})

    all_tool_names = [f"compass_{a['stem']}" for a in agents]
    rows = []
    for agent in agents:
        mapped, _ = map_tools([t for t in agent["tools"] if t != "Agent"])
        allow = list(mapped)
        if "Agent" in agent["tools"]:
            allow.extend(n for n in all_tool_names
                         if n != f"compass_{agent['stem']}")
        model, _, _ = modelslib.resolve(agent["stem"], config=config, host="dsh")
        options = ""
        if model != "inherit" and "/" in model:
            route_provider, route_model = model.split("/", 1)
            options = (
                f"        agentOptions:\n"
                f"          provider: {route_provider}\n"
                f"          model: {route_model}\n"
            )
        rows.append(
            f"    - id: compass-agent-{agent['stem']}\n"
            f"      name: '@deepseek-ai/dsh-tool-subagent'\n"
            f"      config:\n"
            f"        provider: spawn\n"
            f"        toolName: compass_{agent['stem']}\n"
            + options +
            f"        toolFilter:\n"
            f"          allow: [{', '.join(allow)}]\n"
            f"        persona: |\n{_yaml_block(agent['body'], 10)}\n"
        )
    return rows


def materialize_dsh_bundle(project_root, src):
    """Generate the installable Compass bundle at `.dsh/compass-bundle/`:
    the hooks-bridge mount (relative `configPath`, resolved against the
    launch cwd so one profile serves every project), the subagent service
    with the in-process spawn provider, and one delegation tool per shipped
    agent. The bundle version mirrors the plugin version: pnpm `file:`
    installs are snapshots, and the version change is what makes
    `dsh plugin add` refresh the profile copy on update. Returns the bundle
    directory."""
    src = Path(src)
    plugin_meta = json.loads(
        (src / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    dest = Path(project_root) / ".dsh" / "compass-bundle"
    dest.mkdir(parents=True, exist_ok=True)
    vaultlib.write_text_lf(dest / "package.json", json.dumps({
        "name": "compass-dsh-bundle",
        "version": plugin_meta.get("version", "0.0.0"),
        "private": True,
        "dsh": {"bundle": {"patch": "./cordis.patch.yml"}},
    }, indent=2) + "\n")
    parts = [
        "# Generated by compass from the canonical plugin source for the dsh",
        "# host. Do not hand-edit; self-update regenerates it, and a version",
        "# bump makes `dsh plugin add` refresh the profile's snapshot copy.",
        "- insert:",
        "    - id: compass-hooks",
        "      name: '@deepseek-ai/dsh-hooks-claude-code'",
        "      config:",
        # configPath resolves against the launch cwd; projectDir must be
        # absolute - without it the ${CLAUDE_PROJECT_DIR} token in commands
        # stays unsubstituted, and PowerShell reads it as an unset pwsh
        # variable. The bundle is generated per project, so the absolute
        # path is available and correct.
        "        configPath: .dsh/hooks.json",
        f"        projectDir: '{Path(project_root).resolve().as_posix()}'",
        # The delegation rows reuse the `spawn` provider dsh-base already
        # registers; re-mounting the subagents service or the provider
        # fails the boot loudly ("service ... has been registered").
    ]
    parts.extend(_agent_rows(src / "templates" / "agents", Path(project_root) / ".compass"))
    vaultlib.write_text_lf(dest / "cordis.patch.yml", "\n".join(parts) + "\n")
    return dest


def materialize_dsh_hooks(project_root, manifest_path):
    """Generate `.dsh/hooks.json` for `project_root` from the canonical
    manifest. Returns the path written."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    hooks = {}
    for event, groups in manifest.get("hooks", {}).items():
        if event not in DSH_EVENTS:
            continue
        out_groups = []
        for group in groups:
            cleaned = {k: v for k, v in group.items() if k != "hooks"}
            cleaned["hooks"] = [
                {**{k: v for k, v in h.items() if k != "if"},
                 "command": _neutral_command(h["command"])}
                for h in group.get("hooks", [])
            ]
            out_groups.append(cleaned)
        hooks[event] = out_groups
    dest = Path(project_root) / ".dsh" / "hooks.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    vaultlib.write_text_lf(dest, json.dumps({
        "description": (
            "Generated by compass from the canonical hook manifest for the "
            "dsh host. Do not hand-edit; self-update regenerates it."
        ),
        "hooks": hooks,
    }, indent=2) + "\n")
    return dest
