"""The Fountain Obsidian plugin ships inside `plugin/obsidian/fountain/` as the
exact upstream 0.34.3 release bytes with its license text. Adversarial themes:
a byte changed by a line-ending rewrite or a wrong release, a missing or
truncated license, an attribute pattern too narrow or too broad, and a README
that names the bundle outside its License section."""

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FOUNTAIN_DIR = REPO / "plugin" / "obsidian" / "fountain"

RELEASE_DIGESTS = {
    "main.js": "4a8815180e5fb35bbf03870579352360e5f0ab6dcd2b8ac560a331cb5924ea8a",
    "manifest.json": "797ede0e7ea10cfa5b82b087e67988a04f9a6a123b6e8fa8b175be49a5e9581f",
    "styles.css": "cfdc14afce627463150ae8edde35e5b2a37d55056ee581a42b9fa3771457fe2c",
}


LICENSE_MARKERS = (b"MIT License", b"Permission is hereby granted", b"THE SOFTWARE IS PROVIDED")


def bundled_names():
    """File names present in the bundle folder."""
    return {p.name for p in FOUNTAIN_DIR.iterdir()}


def text_attribute(path):
    """The value git reports for the `text` attribute of `path`, from the repo's .gitattributes."""
    result = subprocess.run(
        ["git", "check-attr", "text", "--", path],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().rsplit(": ", 1)[-1]


class BundledFountainFiles(unittest.TestCase):
    def test_release_files_are_the_exact_upstream_bytes(self):
        """Adversarial where: a release file that was line-ending rewritten,
        taken from another release, or left missing must fail its digest;
        the digest is compared on raw bytes so CRLF conversion cannot hide."""
        for name, digest in RELEASE_DIGESTS.items():
            with self.subTest(file=name):
                path = FOUNTAIN_DIR / name
                self.assertTrue(path.is_file(), f"{path} is missing")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_manifest_identifies_fountain_0_34_3(self):
        """Adversarial where: a manifest whose id is not `fountain` would
        install into a folder Obsidian refuses to load, and a stale version
        would bundle an older release than the digests describe."""
        manifest = json.loads((FOUNTAIN_DIR / "manifest.json").read_bytes().decode("utf-8"))
        self.assertEqual(manifest["id"], "fountain")
        self.assertEqual(manifest["version"], "0.34.3")

    def test_license_is_the_full_mit_text(self):
        """Adversarial where: a LICENSE that starts with a byte-order mark or
        a blank line, or holds only a title with the grant truncated, fails
        the bundling obligation."""
        path = FOUNTAIN_DIR / "LICENSE"
        self.assertTrue(path.is_file(), f"{path} is missing")
        data = path.read_bytes()
        self.assertTrue(data.startswith(LICENSE_MARKERS[0]), data[:40])
        for marker in LICENSE_MARKERS[1:]:
            with self.subTest(marker=marker):
                self.assertIn(marker, data)

    def test_bundle_holds_exactly_the_release_files_and_license(self):
        """Adversarial where: a stray file in the bundle folder (saved plugin
        data, a source map) would be copied into every user's vault."""
        self.assertTrue(FOUNTAIN_DIR.is_dir(), f"{FOUNTAIN_DIR} is missing")
        self.assertEqual(bundled_names(), set(RELEASE_DIGESTS) | {"LICENSE"})


class GitAttributesProtectBytes(unittest.TestCase):
    def test_text_attribute_is_unset_exactly_where_bytes_must_survive(self):
        """Adversarial where: a pattern naming only main.js leaves LICENSE and
        the CSS open to LF rewriting, a pattern covering all of
        `plugin/obsidian/` strips normalization from Compass Review, and a
        missing fixtures rule lets git rewrite the CRLF test scripts."""
        rows = {
            "plugin/obsidian/fountain/main.js": "unset",
            "plugin/obsidian/fountain/manifest.json": "unset",
            "plugin/obsidian/fountain/styles.css": "unset",
            "plugin/obsidian/fountain/LICENSE": "unset",
            "plugin/cli/tests/fixtures/fountain/pilot.fountain": "unset",
            "plugin/cli/tests/fixtures/fountain/sub/other.fountain": "unset",
            "plugin/obsidian/compass-review/main.js": "auto",
            "plugin/obsidian/fountain-notes.md": "auto",
            "plugin/cli/tests/fixtures/golden/anything.txt": "auto",
        }
        for path, expected in rows.items():
            with self.subTest(path=path):
                self.assertEqual(text_attribute(path), expected)


class ReadmeLicenseLine(unittest.TestCase):
    def test_license_section_credits_the_bundled_plugin(self):
        """Adversarial where: a credit placed outside the License section, or
        one missing the version, author, license name or text location,
        leaves the bundle unattributed where readers look for it."""
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        match = re.search(r"^## License\s*$(.*?)(?=^## |\Z)", readme, re.M | re.S)
        self.assertIsNotNone(match, "README has no License section")
        lines = [line for line in match.group(1).splitlines() if "Fountain" in line]
        self.assertTrue(lines, "License section has no line naming Fountain")
        line = lines[0]
        for needle in ("0.34.3", "bgrundmann", "MIT", "plugin/obsidian/fountain/LICENSE"):
            with self.subTest(needle=needle):
                self.assertIn(needle, line)
        self.assertIn("Apache 2.0", match.group(1))


if __name__ == "__main__":
    unittest.main()
