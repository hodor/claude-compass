"""Model policy for Compass agents: tiers, host catalog, roster, resolution.

The policy vocabulary is abstract tiers (`strong` / `balanced` / `cheap` /
`inherit`). A per-host catalog maps tiers to that host's model names; a host
absent from the catalog maps every tier to nothing, which resolves to
`inherit`. Resolution precedence, lowest to highest: built-in roster, project
override (`.compass/meta/models.yaml`), environment (`COMPASS_MODEL_<AGENT>`
and `COMPASS_EFFORT_<AGENT>`, agent name uppercased with `-` as `_`).
Resolution bottoms out at `inherit` plus the tier-default effort and never
raises.
"""

import os
import re
from pathlib import Path

import vaultlib

TIERS = ("strong", "balanced", "cheap", "inherit")

# Effort vocabulary accepted by Claude Code agent frontmatter.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

DEFAULT_HOST = "claude-code"

# Per-host tier catalog: tier -> model name the host accepts. A host with no
# entry here resolves every tier to `inherit`.
HOST_CATALOGS = {
    "claude-code": {"strong": "opus", "balanced": "sonnet", "cheap": "haiku"},
}

# Built-in tier per agent. `index-summary` is the detached vault index summary
# job, which runs headless and has no agent definition file.
DEFAULT_ROSTER = {
    "planner": "strong",
    "validator": "strong",
    "reviewer": "strong",
    "debug": "strong",
    "builder": "balanced",
    "researcher": "balanced",
    "tester": "balanced",
    "vault-analyzer": "balanced",
    "codebase-analyzer": "balanced",
    "pattern-finder": "balanced",
    "vault-locator": "cheap",
    "codebase-locator": "cheap",
    "pr-describe": "cheap",
    "index-summary": "cheap",
}

# The agent definition filenames Compass installs. apply-models rewrites these
# and nothing else: any other file in the target directory is user-authored
# and is never read or written.
AGENT_FILES = tuple(
    f"{name}.md" for name in DEFAULT_ROSTER if name != "index-summary"
)

# Default effort per tier, used when no override names an effort.
TIER_EFFORT = {"strong": "high", "balanced": "high", "cheap": "low", "inherit": "high"}


def _strip_quotes(value):
    """Strip one layer of matching quotes from a scalar value."""
    value = value.strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return value[1:-1]
    return value


def empty_config():
    """A project-override config with nothing overridden."""
    return {"tiers": {}, "agents": {}}


def parse_models_yaml(text):
    """Parse the `.compass/meta/models.yaml` project override.

    Returns `(config, warnings)`. `config` is
    `{"tiers": {tier: model}, "agents": {agent: {"tier"|"model"|"effort": v}}}`.

    Accepted shape (a two-level subset, stdlib-parsed like the frontmatter
    parser):

        tiers:
          cheap: sonnet          # remap what a tier resolves to
        agents:
          vault-locator: opus    # scalar pin: a model name or a tier name
          planner:
            tier: balanced
            effort: medium

    Unparseable or unknown lines are skipped with a warning; the function
    never raises.
    """
    config = empty_config()
    warnings = []
    section = None
    agent = None
    agent_indent = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw.strip())
        if not match:
            warnings.append(f"models.yaml:{lineno}: unparseable line skipped")
            continue
        key, value = match.group(1), _strip_quotes(match.group(2))
        if indent == 0:
            agent = None
            agent_indent = None
            if key in ("tiers", "agents"):
                section = key
            else:
                section = None
                warnings.append(f"models.yaml:{lineno}: unknown key '{key}' ignored")
        elif section == "tiers":
            if key in TIERS and key != "inherit":
                config["tiers"][key] = value
            else:
                warnings.append(f"models.yaml:{lineno}: unknown tier '{key}' ignored")
        elif section == "agents":
            if agent is not None and agent_indent is not None and indent > agent_indent:
                if key in ("tier", "model", "effort"):
                    config["agents"].setdefault(agent, {})[key] = value
                else:
                    warnings.append(
                        f"models.yaml:{lineno}: unknown agent key '{key}' ignored"
                    )
            elif value == "":
                agent = key
                agent_indent = indent
                config["agents"].setdefault(agent, {})
            else:
                agent = None
                agent_indent = None
                field = "tier" if value in TIERS else "model"
                config["agents"][key] = {field: value}
        else:
            warnings.append(f"models.yaml:{lineno}: line outside a known section skipped")
    return config, warnings


def load_project_config(vault_root=None):
    """Load `.compass/meta/models.yaml` for the current project.

    Returns `(config, warnings)`. No vault or no override file yields an
    empty config with no warnings; an unreadable or malformed file yields the
    built-ins with a warning. Never raises.
    """
    try:
        root = Path(vault_root) if vault_root else vaultlib.find_vault_root()
    except Exception:
        return empty_config(), []
    path = root / "meta" / "models.yaml"
    if not path.is_file():
        return empty_config(), []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return empty_config(), [f"models.yaml unreadable ({exc}); using built-in defaults"]
    return parse_models_yaml(text)


def _section(config, key):
    """The dict under `config[key]`, or an empty dict for any other shape."""
    value = config.get(key) if isinstance(config, dict) else None
    return value if isinstance(value, dict) else {}


def _merged_tier_map(config, host):
    """The effective tier -> model map plus per-tier source labels."""
    merged = dict(HOST_CATALOGS.get(host, {}))
    sources = {tier: "built-in" for tier in merged}
    for tier, value in _section(config, "tiers").items():
        if tier in TIERS and tier != "inherit":
            merged[tier] = value
            sources[tier] = "project"
    return merged, sources


def _map_tier(tier, tier_map):
    """Model name for a tier: `inherit` for the inherit tier or a tier the
    host maps to nothing; None for a name outside the tier vocabulary."""
    if tier == "inherit":
        return "inherit"
    if tier not in TIERS:
        return None
    return tier_map.get(tier) or "inherit"


def resolve(agent, config=None, environ=None, host=DEFAULT_HOST, warnings=None):
    """Resolve `agent` to `(model, effort, source)`. Never raises.

    `source` names the precedence rung that determined the model: `built-in`,
    `project`, or `env`. An agent outside the roster with no overrides
    resolves to `("inherit", "high", "built-in")`. Ignored override values
    (unknown tier, invalid effort) are appended to `warnings` when a list is
    given, and resolution falls through to the next rung.
    """
    if warnings is None:
        warnings = []
    if environ is None:
        environ = os.environ
    if config is None:
        config, config_warnings = load_project_config()
        warnings.extend(config_warnings)

    tier_map, tier_sources = _merged_tier_map(config, host)
    agent_cfg = _section(config, "agents").get(agent)
    if not isinstance(agent_cfg, dict):
        agent_cfg = {}
    env_key = agent.upper().replace("-", "_")

    # Effective tier, highest rung first; it drives the effort default.
    builtin_tier = DEFAULT_ROSTER.get(agent, "inherit")
    tier = builtin_tier
    cfg_tier = agent_cfg.get("tier")
    if cfg_tier:
        if cfg_tier in TIERS:
            tier = cfg_tier
        else:
            warnings.append(f"{agent}: unknown tier '{cfg_tier}' in models.yaml ignored")

    model = None
    source = None
    env_model = environ.get(f"COMPASS_MODEL_{env_key}", "").strip()
    if env_model:
        if env_model in TIERS:
            tier = env_model
            model = _map_tier(env_model, tier_map)
        else:
            model = env_model
        source = "env"
    if model is None and agent_cfg.get("model"):
        value = agent_cfg["model"]
        if value in TIERS:
            tier = value
            model = _map_tier(value, tier_map)
        else:
            model = value
        source = "project"
    if model is None and cfg_tier in TIERS:
        model = _map_tier(cfg_tier, tier_map)
        source = "project"
    if model is None:
        model = _map_tier(builtin_tier, tier_map)
        source = tier_sources.get(builtin_tier, "built-in")

    effort = None
    env_effort = environ.get(f"COMPASS_EFFORT_{env_key}", "").strip()
    if env_effort:
        if env_effort in EFFORT_LEVELS:
            effort = env_effort
        else:
            warnings.append(f"{agent}: invalid effort '{env_effort}' in environment ignored")
    if effort is None and agent_cfg.get("effort"):
        cfg_effort = agent_cfg["effort"]
        if cfg_effort in EFFORT_LEVELS:
            effort = cfg_effort
        else:
            warnings.append(f"{agent}: invalid effort '{cfg_effort}' in models.yaml ignored")
    if effort is None:
        effort = TIER_EFFORT.get(tier, "high")

    return model, effort, source
