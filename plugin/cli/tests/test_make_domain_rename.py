"""Tests for `compass make-domain --undo` archiving, `--rename`, and `--title`.

Adversarial themes: undo must keep the scope text (identical bytes, both
copies on a name collision) instead of deleting it; rename must move the
folder with its scope text untouched, rewrite only path-qualified links, and
refuse every bad input with zero changes; `--title` must survive characters
YAML treats as syntax.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vaultlib  # noqa: E402
from commands import make_domain  # noqa: E402

# Scope text chosen to break naive handling: a `---` line (frontmatter
# delimiter lookalike), the old folder name inside the text, accents, trailing
# spaces, a tab, and one CRLF line ending that text-mode I/O would normalize.
SCOPE_BYTES = (
    "## Scope\n\n"
    "Class here: network routing and the network cache, ação e coração.  \n"
    "---\n"
    "\tIndented line with trailing spaces   \n"
    "crlf line\r\n"
    "last line without final newline"
).encode("utf-8")


def index_bytes(name, tags, scope=SCOPE_BYTES):
    head = (
        f"---\ntitle: {name}\ntype: domain\nstatus: active\n"
        f"tags: [{', '.join(tags)}]\nsummary: \"{name} things\"\n"
        f"sizing_id: sz-20260830-000000-aaaa\n"
        f"created: 2026-08-30\nupdated: 2026-08-30\n---\n\n"
    )
    return head.encode("utf-8") + scope


def scope_of(raw):
    return raw[raw.index(b"## Scope"):]


def spec_body(name):
    return (
        f"---\ntitle: {name}\ntype: spec\nstatus: approved\narea: w\n"
        f"tags: [x]\ncreated: 2026-08-30\nupdated: 2026-08-30\n---\n\nbody\n"
    )


class DomainFixture(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        for sub in ("meta", "specs", "research", "plans", "lessons"):
            (self.root / sub).mkdir(parents=True)
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )
        cwd = os.getcwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)

    def run_cmd(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = make_domain.run(args)
        return code, out.getvalue(), err.getvalue()

    def make(self, path, class_here="what belongs here"):
        return self.run_cmd(
            [path, "--apply", "--reason", "test", "--class-here", class_here])

    def put(self, rel, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return p

    def snapshot(self):
        snap = {}
        for p in sorted(self.project.rglob("*")):
            rel = p.relative_to(self.project).as_posix()
            if ".git/" in rel + "/" or rel == ".git":
                continue
            snap[rel] = p.read_bytes() if p.is_file() else None
        return snap

    def archived_indexes(self):
        base = self.root / "archive" / "domains"
        return sorted(base.rglob("index.md")) if base.is_dir() else []


class UndoArchiveTests(DomainFixture):
    def test_undo_archives_scope_bytes_then_removes_folder(self):
        """Adversarial where: undo still deletes the folder with `rmtree`
        and the scope text is lost, or the archived copy is re-encoded
        (CRLF, accents, trailing spaces) rather than moved as-is; a dry run
        or a refused undo must archive nothing."""
        original = index_bytes("network", ["network"])
        self.put("specs/network/index.md", original)

        code, out, _ = self.run_cmd(["--undo", "specs/network"])
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "specs" / "network").is_dir())
        self.assertEqual(self.archived_indexes(), [])

        self.put("specs/network/SPEC-001-a.md", spec_body("A"))
        code, _, _ = self.run_cmd(
            ["--undo", "specs/network", "--apply", "--reason", "x"])
        self.assertEqual(code, 1)
        self.assertFalse(self.archived_indexes(), "refused undo must archive nothing")
        (self.root / "specs" / "network" / "SPEC-001-a.md").unlink()

        code, out, _ = self.run_cmd(
            ["--undo", "specs/network", "--apply", "--reason", "scratch"])
        self.assertEqual(code, 0)
        self.assertFalse((self.root / "specs" / "network").exists())
        archived = self.root / "archive" / "domains" / "specs" / "network" / "index.md"
        self.assertTrue(archived.is_file())
        self.assertEqual(archived.read_bytes(), original)
        self.assertIn("archive/domains/specs/network", out.replace("\\", "/"))

    def test_undo_twice_on_same_named_folders_keeps_both_copies(self):
        """Adversarial where: the second undo of a same-named folder
        overwrites the first archived scope text (or fails on the occupied
        path) instead of taking a numbered suffix."""
        first = index_bytes("network", ["network"], b"## Scope\n\nClass here: FIRST copy.\n")
        second = index_bytes("network", ["network"], b"## Scope\n\nClass here: SECOND copy.\n")
        for raw in (first, second):
            self.put("specs/network/index.md", raw)
            code, _, _ = self.run_cmd(
                ["--undo", "specs/network", "--apply", "--reason", "scratch"])
            self.assertEqual(code, 0)
            self.assertFalse((self.root / "specs" / "network").exists())

        found = [p.read_bytes() for p in self.archived_indexes()]
        self.assertEqual(sorted(found), sorted([first, second]))
        plain = self.root / "archive" / "domains" / "specs" / "network" / "index.md"
        self.assertEqual(plain.read_bytes(), first)


class RenameTests(DomainFixture):
    def _seed(self):
        self.original = index_bytes("network", ["network", "extra"])
        self.put("specs/network/index.md", self.original)
        self.put("specs/network/SPEC-001-a.md", spec_body("A"))
        self.put("specs/network/cache/index.md",
                 index_bytes("cache", ["cache"], b"## Scope\n\nClass here: cache.\n"))
        self.put("specs/network/cache/SPEC-002-c.md", spec_body("C"))
        self.put("specs/network-extra/index.md",
                 index_bytes("network-extra", ["network-extra"],
                             b"## Scope\n\nClass here: lookalike prefix.\n"))
        self.put("specs/network-extra/SPEC-009-z.md", spec_body("Z"))
        self.put("specs/gpu/index.md",
                 index_bytes("gpu", ["gpu"], b"## Scope\n\nClass here: gpu.\n"))

    def rename(self, old, new, apply=True, reason="renamed"):
        args = ["--rename", old, new]
        if apply:
            args += ["--apply", "--reason", reason]
        return self.run_cmd(args)

    def test_rename_moves_tree_keeps_scope_bytes_and_sets_title_and_first_tag(self):
        """Adversarial where: the rename rewrites the whole index with a
        text-mode read/write or a blanket old-name replace, corrupting the
        Scope text (CRLF, `---` line, the old name inside it); or it swaps
        every tag instead of only the first; or members and child domains
        stay behind; or no `action: rename` sizing row is logged."""
        self._seed()
        code, _, err = self.rename("specs/network", "specs/web")
        self.assertEqual(code, 0, err)

        self.assertFalse((self.root / "specs" / "network").exists())
        web = self.root / "specs" / "web"
        for member in ("SPEC-001-a.md", "cache/index.md", "cache/SPEC-002-c.md"):
            self.assertTrue((web / member).is_file(), member)

        raw = (web / "index.md").read_bytes()
        self.assertEqual(scope_of(raw), scope_of(self.original))
        data, error = vaultlib.parse_frontmatter(web / "index.md")
        self.assertIsNone(error)
        self.assertEqual(data.get("title"), "web")
        self.assertEqual(data.get("tags"), ["web", "extra"])

        log = (self.root / "meta" / "sizing-log.yaml").read_text(encoding="utf-8")
        self.assertIn("action: rename", log)

    def test_rename_rewrites_only_path_qualified_links(self):
        """Adversarial where: the link rewrite also touches a bare link, an
        inline-code mention, or a link into a lookalike-prefix sibling
        (`specs/network-extra/...`), or drops the alias of a piped link."""
        self._seed()
        plan = (
            "---\ntitle: P\ntype: plan\nstatus: active\narea: w\ntags: [x]\n"
            "created: 2026-08-30\nupdated: 2026-08-30\n---\n\n"
            "qualified [[specs/network/cache]] and [[specs/network/SPEC-001-a]]\n"
            "aliased [[specs/network/cache|the cache]]\n"
            "bare [[cache]] and [[SPEC-001-a]]\n"
            "inline `[[specs/network/cache]]` in code\n"
            "lookalike [[specs/network-extra/SPEC-009-z]]\n"
        )
        unrelated = spec_body("Unrelated")
        self.put("plans/PLAN-001-p.md", plan)
        self.put("specs/SPEC-050-u.md", unrelated)

        code, _, err = self.rename("specs/network", "specs/web")
        self.assertEqual(code, 0, err)

        expected = (
            "---\ntitle: P\ntype: plan\nstatus: active\narea: w\ntags: [x]\n"
            "created: 2026-08-30\nupdated: 2026-08-30\n---\n\n"
            "qualified [[specs/web/cache]] and [[specs/web/SPEC-001-a]]\n"
            "aliased [[specs/web/cache|the cache]]\n"
            "bare [[cache]] and [[SPEC-001-a]]\n"
            "inline `[[specs/network/cache]]` in code\n"
            "lookalike [[specs/network-extra/SPEC-009-z]]\n"
        )
        self.assertEqual(
            (self.root / "plans" / "PLAN-001-p.md").read_bytes(),
            expected.encode("utf-8"))
        self.assertEqual(
            (self.root / "specs" / "SPEC-050-u.md").read_bytes(),
            unrelated.encode("utf-8"))

    def test_rename_refuses_each_bad_input_with_zero_changes(self):
        """Adversarial where: a refusal still moves, half-writes, or logs
        something before it notices the input is bad; or a bad input slips
        through (missing source, existing target, target in another type
        dir, target that is not a sibling of the source, a name that is not
        a valid folder name)."""
        self._seed()
        self.put("plans/PLAN-001-p.md",
                 "---\ntitle: P\ntype: plan\n---\n\n[[specs/network/cache]]\n")
        before = self.snapshot()
        cases = {
            "missing source": ("specs/ghost", "specs/web"),
            "existing target": ("specs/network", "specs/gpu"),
            "other type dir": ("specs/network", "research/network"),
            "not a sibling": ("specs/network", "specs/gpu/network"),
            "invalid name": ("specs/network", "specs/bad name"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name=name):
                code, _, err = self.rename(old, new)
                self.assertEqual(code, 1, err)
                self.assertEqual(self.snapshot(), before)
        code, _, err = self.rename("specs/network", "specs/web")
        self.assertEqual(code, 0, f"control: a valid rename must succeed: {err}")

    def test_rename_dry_run_default_and_apply_needs_reason(self):
        """Adversarial where: the rename moves on a bare invocation (no
        `--apply`) or applies without the mandatory `--reason`."""
        self._seed()
        before = self.snapshot()
        code, _, _ = self.rename("specs/network", "specs/web", apply=False)
        self.assertEqual(code, 0)
        self.assertEqual(self.snapshot(), before, "dry run changed the vault")

        code, _, err = self.run_cmd(
            ["--rename", "specs/network", "specs/web", "--apply"])
        self.assertEqual(code, 1)
        self.assertIn("--reason", err)
        self.assertEqual(self.snapshot(), before, "apply without reason changed the vault")

    def test_rename_of_git_tracked_folder_leaves_new_path_tracked(self):
        """Adversarial where: a tracked folder is renamed with a plain
        filesystem move, so git sees the old files deleted and the new ones
        untracked instead of a staged rename."""
        if shutil.which("git") is None:
            self.skipTest("git not available")
        self._seed()
        git = ["git", "-c", "core.autocrlf=false"]
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        subprocess.run(git + ["add", ".compass"], cwd=self.project, check=True)

        code, _, err = self.rename("specs/network", "specs/web")
        self.assertEqual(code, 0, err)

        tracked = subprocess.run(
            ["git", "ls-files", ".compass/specs"], cwd=self.project,
            capture_output=True, text=True, check=True).stdout.split()
        self.assertIn(".compass/specs/web/SPEC-001-a.md", tracked)
        self.assertIn(".compass/specs/web/cache/SPEC-002-c.md", tracked)
        self.assertFalse([t for t in tracked if t.startswith(".compass/specs/network/")])


class TitleTests(DomainFixture):
    def test_title_survives_yaml_syntax_and_folder_name_comes_from_path(self):
        """Adversarial where: `--title` text holding a double quote, a
        colon, a backslash, a hash, a leading dash or accents is written
        unescaped, so the index no longer parses or the title reads back
        changed; or the title leaks into the folder name or tag."""
        titles = {
            "quotes and colon": 'He said "hi": now',
            "backslash and hash": r"back\slash # not a comment",
            "leading dash": "- leading dash",
            "accents": "Mundo: ação e coração",
        }
        for name, title in titles.items():
            with self.subTest(name=name):
                shutil.rmtree(self.root / "specs" / "network", ignore_errors=True)
                code, _, err = self.run_cmd(
                    ["specs/network", "--apply", "--reason", "t",
                     "--class-here", "routing", "--title", title])
                self.assertEqual(code, 0, err)
                path = self.root / "specs" / "network" / "index.md"
                data, error = vaultlib.parse_frontmatter(path)
                self.assertIsNone(error)
                self.assertEqual(data.get("title"), title)
                self.assertEqual(data.get("type"), "domain")
                self.assertEqual(data.get("tags"), ["network"])


if __name__ == "__main__":
    unittest.main()
