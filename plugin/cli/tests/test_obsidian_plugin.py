"""Runs the Compass Review Obsidian plugin's Node test harness
(`plugin/obsidian/tests/test_main.js`) inside the Python suite, so a broken
plugin fails the same run as a broken CLI. Skipped when Node is absent."""

import shutil
import subprocess
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "obsidian"
HARNESS = PLUGIN_DIR / "tests" / "test_main.js"
MAIN = PLUGIN_DIR / "compass-review" / "main.js"


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ObsidianPluginHarness(unittest.TestCase):
    def test_main_js_parses(self):
        result = subprocess.run(["node", "--check", str(MAIN)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_harness_passes(self):
        result = subprocess.run(["node", "--test", str(HARNESS)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:])
        self.assertIn("# fail 0", result.stdout)


class ShippedPluginFiles(unittest.TestCase):
    def test_manifest_names_the_id_reviewlib_checks(self):
        import json
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import reviewlib
        manifest = json.loads((PLUGIN_DIR / "compass-review" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], reviewlib.PLUGIN_ID)
        self.assertTrue(manifest["isDesktopOnly"])
        for name in ("main.js", "manifest.json", "styles.css"):
            self.assertTrue((PLUGIN_DIR / "compass-review" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
