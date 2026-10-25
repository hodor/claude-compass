"""The shipped Bases views (`plugin/obsidian/bases/*.base`) parse as YAML in
the shape Obsidian reads, and filter, group and show only frontmatter keys
the vault schema defines, so a renamed key cannot leave a view silently
empty."""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reviewlib  # noqa: E402

BASES = reviewlib.shipped_bases_dir()
SCHEMA = Path(__file__).resolve().parents[2] / "skills" / "obsidian" / "SKILL.md"
FILE_KEYS = {"file.name", "file.ext", "file.path", "file.folder"}
KEY_IN_EXPR = re.compile(r"(?<![\w.])([a-z_]+)\s*(?:==|!=|>=|<=|>|<)")


def load_yaml(text):
    try:
        import yaml
    except ImportError:
        return None
    return yaml.safe_load(text)


def schema_keys():
    """Every `key:` the obsidian skill's frontmatter templates name."""
    text = SCHEMA.read_text(encoding="utf-8")
    return set(re.findall(r"^([a-z_]+):", text, re.M))


def referenced_keys(text):
    keys = set(KEY_IN_EXPR.findall(text))
    keys |= set(re.findall(r"^\s+property:\s*([a-z_.]+)\s*$", text, re.M))
    keys |= set(re.findall(r"^\s+-\s+([a-z_.]+)\s*$", text, re.M))
    keys |= set(re.findall(r"^  ([a-z_]+):\s*$", text.split("views:")[0], re.M)) - {"and", "or", "not"}
    return {k for k in keys if k not in FILE_KEYS}


class ShippedBases(unittest.TestCase):
    def test_every_base_file_ships(self):
        for name in reviewlib.BASE_FILES:
            self.assertTrue((BASES / name).is_file(), name)

    def test_bases_parse_with_views(self):
        for name in reviewlib.BASE_FILES:
            data = load_yaml((BASES / name).read_text(encoding="utf-8"))
            if data is None:
                self.skipTest("PyYAML is not installed")
            self.assertIsInstance(data, dict, name)
            self.assertTrue(data.get("views"), name)
            for view in data["views"]:
                self.assertEqual(view["type"], "table", name)
                self.assertTrue(view["name"], name)

    def test_bases_use_only_schema_keys(self):
        known = schema_keys()
        self.assertIn("status", known)
        for name in reviewlib.BASE_FILES:
            used = referenced_keys((BASES / name).read_text(encoding="utf-8"))
            self.assertTrue(used, name)
            self.assertEqual(used - known, set(), f"{name} names keys the schema lacks")

    def test_key_scan_sees_a_bogus_key(self):
        self.assertIn("staus", referenced_keys("filters:\n  and:\n    - 'staus == \"draft\"'\n"))


if __name__ == "__main__":
    unittest.main()
