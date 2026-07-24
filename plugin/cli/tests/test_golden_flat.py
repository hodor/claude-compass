"""Golden regression guard for flat-vault sync/validate behavior.

The fixture vault under `fixtures/golden/vault/` mirrors the dogfood vault's
shapes: flat specs, a folder spec with nested children, plans, research, a
decision, lessons, a handoff, tags, an archived spec, and two deliberate
findings (a missing recommended field and a broken wikilink). The files under
`fixtures/golden/expected/` pin the exact bytes `sync` writes and the exact
report `validate` emits on that vault. Any change to sync emission, link
resolution, ordering, or report formatting on a units-free vault fails here.
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import sync as sync_cmd  # noqa: E402
from commands import validate as validate_cmd  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "golden"

GOLDEN_OUTPUTS = {
    "index.md": "index.md",
    "meta/tag-index.yaml": "tag-index.yaml",
    "meta/lessons-catalog.yaml": "lessons-catalog.yaml",
}


class GoldenFlatVaultTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.root = tmp / ".compass"
        shutil.copytree(FIXTURE / "vault", self.root)
        # Byte comparison requires LF fixtures; a CRLF checkout would fail
        # every assertion with a confusing diff, so fail fast with the cause.
        for path in FIXTURE.rglob("*"):
            if path.is_file():
                self.assertNotIn(
                    b"\r", path.read_bytes(),
                    f"fixture {path.name} contains CR bytes; expected LF-only checkout",
                )

    def _expected(self, name):
        return (FIXTURE / "expected" / name).read_bytes()

    def test_sync_reproduces_golden_files_byte_identically(self):
        sync_cmd.sync(self.root)
        for produced, golden in GOLDEN_OUTPUTS.items():
            self.assertEqual(
                (self.root / produced).read_bytes(),
                self._expected(golden),
                f"{produced} drifted from golden {golden}",
            )

    def test_validate_after_sync_reproduces_golden_report(self):
        sync_cmd.sync(self.root)
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.root.parent)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = validate_cmd.run([])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(
            err.getvalue().encode("utf-8"),
            self._expected("validate-report.txt"),
            "validate report drifted from golden",
        )


if __name__ == "__main__":
    unittest.main()
