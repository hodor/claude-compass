"""Tests for `compass promote` accepting every argument form its usage line
names: a bare spec id (`SPEC-027`), a vault-relative path with or without the
`.md` suffix, and a path that starts with the vault's own folder name
(`.compass/specs/...`), the form a shell in the project root completes.

Adversarial themes: an id shared by two specs (two stems starting with the
same number) is refused and nothing moves, an id that is a prefix of a
longer number (`SPEC-02` against `SPEC-027`) matches nothing, and an exact
stem still beats an id match."""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import promote  # noqa: E402


def spec(title):
    return (f'---\ntitle: "{title}"\ntype: spec\nstatus: approved\narea: workflow\n'
            "tags: [x]\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n")


def domain(name):
    return (f'---\ntitle: "{name}"\ntype: domain\nstatus: active\ntags: [{name}]\n'
            f'summary: "{name} things"\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\n'
            f"## Scope\n\nClass here: {name} things\n")


class PromoteArgumentFormsTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        self.add("specs/tooling/index.md", domain("tooling"))
        self.add("specs/tooling/SPEC-027-fewer-tokens.md", spec("Fewer tokens"))
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def add(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def promote(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = promote.run(args)
        return code, out.getvalue(), err.getvalue()

    def test_every_documented_form_resolves_the_spec(self):
        forms = [
            "SPEC-027",
            "specs/tooling/SPEC-027-fewer-tokens",
            "specs/tooling/SPEC-027-fewer-tokens.md",
            ".compass/specs/tooling/SPEC-027-fewer-tokens.md",
            ".compass/specs/tooling/SPEC-027-fewer-tokens".replace("/", "\\"),
        ]
        for form in forms:
            with self.subTest(form=form):
                code, out, err = self.promote([form])
                self.assertEqual(code, 0, err)
                self.assertIn("specs/tooling/SPEC-027-fewer-tokens/index.md", out)

    def test_bare_id_moves_the_spec_with_apply(self):
        code, _, err = self.promote(["SPEC-027", "--apply", "--reason", "grew a child"])
        self.assertEqual(code, 0, err)
        self.assertTrue((self.root / "specs/tooling/SPEC-027-fewer-tokens/index.md").is_file())

    def test_id_borne_by_two_specs_is_refused_and_nothing_moves(self):
        self.add("specs/tooling/SPEC-027-other.md", spec("Other"))
        code, _, err = self.promote(["SPEC-027", "--apply", "--reason", "r"])
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", err)
        self.assertTrue((self.root / "specs/tooling/SPEC-027-fewer-tokens.md").is_file())
        self.assertTrue((self.root / "specs/tooling/SPEC-027-other.md").is_file())

    def test_shorter_number_matches_nothing(self):
        code, _, err = self.promote(["SPEC-02"])
        self.assertEqual(code, 1)
        self.assertIn("spec not found", err)

    def test_exact_stem_beats_an_id_match(self):
        self.add("specs/tooling/SPEC-030.md", spec("Bare"))
        self.add("specs/tooling/SPEC-030-longer.md", spec("Longer"))
        code, out, err = self.promote(["SPEC-030"])
        self.assertEqual(code, 0, err)
        self.assertIn("specs/tooling/SPEC-030/index.md", out)


if __name__ == "__main__":
    unittest.main()
