"""Tests for the project snapshot the loop runner takes around a judge run:
files other processes rewrite on their own (everything under
`.compass/meta/`, which `compass sync` and every `compass` call regenerate,
and Obsidian's
`.obsidian/` app state, written by a running Obsidian) never count as a
change the judge made, in a git work tree or a plain directory.

Adversarial themes: the record and app state change between two snapshots
while a real document also changes (the document must still be seen), and a
file merely named like the record outside `.compass/meta/` is still seen."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import looprunner  # noqa: E402


def _changed(before, after):
    return sorted(n for n in before.keys() | after.keys() if before.get(n) != after.get(n))


class SnapshotChurnTest(unittest.TestCase):
    def _project(self, tmp, git):
        project = Path(tmp)
        (project / ".compass" / "meta").mkdir(parents=True)
        (project / ".compass" / ".obsidian").mkdir()
        (project / ".obsidian").mkdir()
        (project / "docs").mkdir()
        loop_dir = project / ".compass" / "loops" / "LOOP-001-x"
        loop_dir.mkdir(parents=True)
        if git:
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        return project, loop_dir

    def _churn(self, project):
        (project / ".compass" / "meta" / "usage.yaml").write_text("sync: 2\n", encoding="utf-8")
        (project / ".compass" / "meta" / "tag-index.yaml").write_text("tags: {}\n", encoding="utf-8")
        (project / ".compass" / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")
        (project / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")

    def _check(self, git):
        with tempfile.TemporaryDirectory() as tmp:
            project, loop_dir = self._project(tmp, git)
            before = looprunner._project_snapshot(project, loop_dir)
            self._churn(project)
            (project / "docs" / "usage.yaml").write_text("x", encoding="utf-8")
            (project / "docs" / "a.md").write_text("changed", encoding="utf-8")
            after = looprunner._project_snapshot(project, loop_dir)
            self.assertEqual(_changed(before, after), ["docs/a.md", "docs/usage.yaml"])

    def test_git_snapshot_skips_usage_record_and_obsidian_state(self):
        self._check(git=True)

    def test_walk_snapshot_skips_usage_record_and_obsidian_state(self):
        self._check(git=False)


if __name__ == "__main__":
    unittest.main()
