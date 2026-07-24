"""Tests for the model policy library: roster, catalog, override parsing,
and precedence resolution."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import modelslib  # noqa: E402


def resolve(agent, config=None, environ=None, **kwargs):
    """Resolve with an isolated config and environment by default."""
    return modelslib.resolve(
        agent,
        config=config if config is not None else modelslib.empty_config(),
        environ=environ if environ is not None else {},
        **kwargs,
    )


class RosterTests(unittest.TestCase):
    def test_roster_matches_d03_assignments(self):
        by_tier = {}
        for agent, tier in modelslib.DEFAULT_ROSTER.items():
            by_tier.setdefault(tier, set()).add(agent)
        self.assertEqual(by_tier["strong"], {"planner", "validator", "reviewer", "debug"})
        self.assertEqual(by_tier["balanced"], {
            "builder", "researcher", "tester",
            "vault-analyzer", "codebase-analyzer", "pattern-finder",
        })
        self.assertEqual(by_tier["cheap"], {
            "vault-locator", "codebase-locator", "pr-describe", "index-summary",
        })

    def test_agent_files_are_the_13_known_agents(self):
        self.assertEqual(len(modelslib.AGENT_FILES), 13)
        self.assertNotIn("index-summary.md", modelslib.AGENT_FILES)
        self.assertIn("planner.md", modelslib.AGENT_FILES)
        self.assertIn("vault-locator.md", modelslib.AGENT_FILES)

    def test_tier_effort_defaults(self):
        self.assertEqual(modelslib.TIER_EFFORT["strong"], "high")
        self.assertEqual(modelslib.TIER_EFFORT["balanced"], "high")
        self.assertEqual(modelslib.TIER_EFFORT["cheap"], "low")


class BuiltinResolutionTests(unittest.TestCase):
    def test_strong_agent_resolves_opus_high(self):
        self.assertEqual(resolve("planner"), ("opus", "high", "built-in"))

    def test_balanced_agent_resolves_sonnet_high(self):
        self.assertEqual(resolve("builder"), ("sonnet", "high", "built-in"))

    def test_cheap_agent_resolves_haiku_low(self):
        self.assertEqual(resolve("vault-locator"), ("haiku", "low", "built-in"))

    def test_index_summary_job_resolves_cheap(self):
        self.assertEqual(resolve("index-summary"), ("haiku", "low", "built-in"))

    def test_unknown_agent_resolves_inherit(self):
        self.assertEqual(resolve("no-such-agent"), ("inherit", "high", "built-in"))

    def test_unknown_host_all_tiers_inherit(self):
        for agent in modelslib.DEFAULT_ROSTER:
            model, _effort, _source = resolve(agent, host="kimi-code")
            self.assertEqual(model, "inherit", agent)


class PrecedenceTests(unittest.TestCase):
    def test_project_tier_remap_wins_over_builtin(self):
        config = {"tiers": {"cheap": "sonnet"}, "agents": {}}
        self.assertEqual(resolve("vault-locator", config), ("sonnet", "low", "project"))

    def test_project_agent_model_pin_wins_over_builtin(self):
        config = {"tiers": {}, "agents": {"vault-locator": {"model": "opus"}}}
        self.assertEqual(resolve("vault-locator", config), ("opus", "low", "project"))

    def test_project_agent_tier_reassign_moves_effort_default(self):
        config = {"tiers": {}, "agents": {"vault-locator": {"tier": "balanced"}}}
        self.assertEqual(resolve("vault-locator", config), ("sonnet", "high", "project"))

    def test_project_effort_override_keeps_builtin_model(self):
        config = {"tiers": {}, "agents": {"planner": {"effort": "medium"}}}
        self.assertEqual(resolve("planner", config), ("opus", "medium", "built-in"))

    def test_env_model_wins_over_project(self):
        config = {"tiers": {}, "agents": {"vault-locator": {"model": "sonnet"}}}
        environ = {"COMPASS_MODEL_VAULT_LOCATOR": "opus"}
        self.assertEqual(resolve("vault-locator", config, environ), ("opus", "low", "env"))

    def test_env_tier_token_maps_through_catalog(self):
        environ = {"COMPASS_MODEL_PLANNER": "cheap"}
        self.assertEqual(resolve("planner", environ=environ), ("haiku", "low", "env"))

    def test_env_effort_wins_over_project(self):
        config = {"tiers": {}, "agents": {"planner": {"effort": "medium"}}}
        environ = {"COMPASS_EFFORT_PLANNER": "low"}
        self.assertEqual(resolve("planner", config, environ), ("opus", "low", "built-in"))

    def test_model_pin_inherit_resolves_inherit(self):
        config = {"tiers": {}, "agents": {"builder": {"model": "inherit"}}}
        self.assertEqual(resolve("builder", config), ("inherit", "high", "project"))

    def test_full_model_id_pin_passes_verbatim(self):
        environ = {"COMPASS_MODEL_BUILDER": "claude-opus-4-8"}
        self.assertEqual(resolve("builder", environ=environ), ("claude-opus-4-8", "high", "env"))


class ResolveWarningTests(unittest.TestCase):
    def test_invalid_env_effort_ignored_with_warning(self):
        warnings = []
        result = resolve("planner", environ={"COMPASS_EFFORT_PLANNER": "turbo"},
                         warnings=warnings)
        self.assertEqual(result, ("opus", "high", "built-in"))
        self.assertTrue(any("turbo" in w for w in warnings))

    def test_invalid_project_effort_ignored_with_warning(self):
        warnings = []
        config = {"tiers": {}, "agents": {"planner": {"effort": "extreme"}}}
        result = resolve("planner", config, warnings=warnings)
        self.assertEqual(result, ("opus", "high", "built-in"))
        self.assertTrue(any("extreme" in w for w in warnings))

    def test_unknown_project_tier_falls_through_with_warning(self):
        warnings = []
        config = {"tiers": {}, "agents": {"planner": {"tier": "turbo"}}}
        result = resolve("planner", config, warnings=warnings)
        self.assertEqual(result, ("opus", "high", "built-in"))
        self.assertTrue(any("turbo" in w for w in warnings))

    def test_resolve_never_raises_on_junk_config(self):
        junk = {"tiers": None, "agents": {"planner": "not-a-dict"}}
        try:
            modelslib.resolve("planner", config=junk, environ={})
        except Exception as exc:  # pragma: no cover
            self.fail(f"resolve raised {exc!r}")


class ParseModelsYamlTests(unittest.TestCase):
    def test_tier_remap_and_agent_block_parsed(self):
        text = (
            "tiers:\n"
            "  cheap: sonnet\n"
            "agents:\n"
            "  planner:\n"
            "    tier: balanced\n"
            "    effort: medium\n"
        )
        config, warnings = modelslib.parse_models_yaml(text)
        self.assertEqual(warnings, [])
        self.assertEqual(config["tiers"], {"cheap": "sonnet"})
        self.assertEqual(config["agents"], {"planner": {"tier": "balanced", "effort": "medium"}})

    def test_scalar_agent_pin_classified_as_model_or_tier(self):
        config, _ = modelslib.parse_models_yaml(
            "agents:\n  planner: opus\n  vault-locator: balanced\n"
        )
        self.assertEqual(config["agents"]["planner"], {"model": "opus"})
        self.assertEqual(config["agents"]["vault-locator"], {"tier": "balanced"})

    def test_malformed_text_warns_and_returns_empty(self):
        config, warnings = modelslib.parse_models_yaml("{{{ not yaml :::\n\t???\n")
        self.assertEqual(config, modelslib.empty_config())
        self.assertTrue(warnings)

    def test_unknown_top_level_key_warned(self):
        _, warnings = modelslib.parse_models_yaml("profiles:\n  x: y\n")
        self.assertTrue(any("profiles" in w for w in warnings))

    def test_unknown_tier_key_dropped_with_warning(self):
        config, warnings = modelslib.parse_models_yaml("tiers:\n  turbo: opus\n")
        self.assertEqual(config["tiers"], {})
        self.assertTrue(any("turbo" in w for w in warnings))

    def test_inherit_tier_not_remappable(self):
        config, warnings = modelslib.parse_models_yaml("tiers:\n  inherit: opus\n")
        self.assertEqual(config["tiers"], {})
        self.assertTrue(warnings)

    def test_comments_and_blank_lines_skipped(self):
        config, warnings = modelslib.parse_models_yaml(
            "# project model policy\n\ntiers:\n  # cheaper still\n  cheap: haiku\n"
        )
        self.assertEqual(warnings, [])
        self.assertEqual(config["tiers"], {"cheap": "haiku"})


class LoadProjectConfigTests(unittest.TestCase):
    def _vault(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / ".compass"
        (root / "meta").mkdir(parents=True)
        return root

    def test_missing_file_is_empty_config_no_warnings(self):
        root = self._vault()
        config, warnings = modelslib.load_project_config(root)
        self.assertEqual(config, modelslib.empty_config())
        self.assertEqual(warnings, [])

    def test_override_file_loaded(self):
        root = self._vault()
        (root / "meta" / "models.yaml").write_text(
            "agents:\n  vault-locator: sonnet\n", encoding="utf-8"
        )
        config, warnings = modelslib.load_project_config(root)
        self.assertEqual(warnings, [])
        self.assertEqual(
            modelslib.resolve("vault-locator", config=config, environ={}),
            ("sonnet", "low", "project"),
        )

    def test_malformed_override_warns_and_uses_builtins(self):
        root = self._vault()
        (root / "meta" / "models.yaml").write_text(":::garbage:::\n", encoding="utf-8")
        config, warnings = modelslib.load_project_config(root)
        self.assertTrue(warnings)
        self.assertEqual(
            modelslib.resolve("planner", config=config, environ={}),
            ("opus", "high", "built-in"),
        )


if __name__ == "__main__":
    unittest.main()
