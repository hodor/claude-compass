"""The user's Compass home (`COMPASS_HOME`, default `~/.compass`) holds kept
session clones and private stores; a directory under the home folder with no
vault of its own must not resolve to it as a project vault."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402


class CompassHomeIsNeverAVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.home_store = self.tmp / ".compass"
        (self.home_store / "sessions").mkdir(parents=True)
        self.work = self.tmp / "work" / "nested"
        self.work.mkdir(parents=True)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env["COMPASS_HOME"] = str(self.home_store)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def resolves_elsewhere_or_nowhere(self):
        try:
            found = vaultlib.find_vault_root(self.work)
        except FileNotFoundError:
            return
        self.assertNotEqual(found.resolve(), self.home_store)

    def test_walk_up_skips_the_compass_home(self):
        self.resolves_elsewhere_or_nowhere()

    def test_project_dir_pointing_at_the_home_folder_is_skipped(self):
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.tmp)
        self.resolves_elsewhere_or_nowhere()

    def test_a_home_store_is_recognised_without_compass_home_set(self):
        del os.environ["COMPASS_HOME"]
        self.resolves_elsewhere_or_nowhere()

    def test_a_dot_compass_with_an_index_is_a_vault_even_beside_sessions(self):
        (self.home_store / "index.md").write_text("# index\n", encoding="utf-8")
        del os.environ["COMPASS_HOME"]
        self.assertEqual(vaultlib.find_vault_root(self.work).resolve(), self.home_store)

    def test_a_project_vault_below_the_home_folder_still_resolves(self):
        project_vault = self.tmp / "work" / ".compass"
        project_vault.mkdir()
        self.assertEqual(vaultlib.find_vault_root(self.work), project_vault)

    def test_a_vault_named_by_project_dir_resolves(self):
        project = self.tmp / "proj"
        (project / ".compass").mkdir(parents=True)
        os.environ["CLAUDE_PROJECT_DIR"] = str(project)
        self.assertEqual(vaultlib.find_vault_root(self.work), project / ".compass")


if __name__ == "__main__":
    unittest.main()
