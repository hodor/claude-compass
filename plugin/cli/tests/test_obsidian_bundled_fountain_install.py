"""The install path that carries `plugin/obsidian/` into a project's
`.claude/obsidian/` moves the bundled Fountain plugin without changing a byte.
Adversarial themes: a tree copy that skips, truncates or re-encodes a large
file, and a copy that drops the license."""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import self_update  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SHIPPED = REPO / "plugin" / "obsidian"
FOUNTAIN_FILES = ("main.js", "manifest.json", "styles.css", "LICENSE")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FountainBundleSurvivesTheInstallCopy(unittest.TestCase):
    def test_install_copy_of_the_obsidian_tree_keeps_every_fountain_byte(self):
        """Adversarial where: the best-effort tree copy swallows per-file
        OSError, so a large file that failed to copy (550 KB `main.js`) or a
        copy that rewrote bytes would leave a project with a broken or
        unlicensed Fountain and no error; compare against the shipped bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "obsidian"
            self_update._copy_tree_best_effort(SHIPPED, dest)
            for name in FOUNTAIN_FILES:
                with self.subTest(file=name):
                    copied = dest / "fountain" / name
                    self.assertTrue(copied.is_file(), f"{copied} was not installed")
                    self.assertEqual(digest(copied), digest(SHIPPED / "fountain" / name))


if __name__ == "__main__":
    unittest.main()
