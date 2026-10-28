"""Tests for the VS Code and Cursor review surfaces (`review_surfaces.vscode`
and the `cursor` surface that differs from it only in its command).

The surfaces launch an editor and install an extension, so every test replaces
`shutil.which` and the `subprocess` entry points with a recorder; no editor is
ever started. Calls to `git` pass through to the real program.

Adversarial themes: a command found for one editor and missing for the other,
a folder taken from the environment instead of from the document, a path with
a space reaching the editor as two arguments, an install that raises or claims
success when the editor failed, an extension listed under a longer name
counted as installed, and a shipped `.vsix` that no longer carries the sources
beside it.
"""

import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

CLI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLI))

import review_surfaces  # noqa: E402
import reviewlib  # noqa: E402

PLUGIN = CLI.parent
VSCODE_DIR = PLUGIN / "vscode"
EXTENSION_DIR = VSCODE_DIR / "compass-review"
COMMANDS = {"vscode": "code", "cursor": "cursor"}

REAL_RUN = subprocess.run
REAL_POPEN = subprocess.Popen


def _stem(argv):
    return Path(str(argv[0])).stem.lower() if argv else ""


def surface(name):
    """The registered surface called `name`; fails the test when none is."""
    importlib.import_module("review_surfaces.vscode")
    found = review_surfaces.named(name)
    if found is None:
        raise AssertionError(f"no review surface is registered as {name!r}")
    return found


def extension_id():
    """The id VS Code lists the shipped extension under: lower-cased
    `publisher.name` from its package.json."""
    package = json.loads((EXTENSION_DIR / "package.json").read_text(encoding="utf-8"))
    return f"{package['publisher']}.{package['name']}".lower()


class _FakeProcess:
    """What `subprocess.Popen` returns for an editor command."""

    def __init__(self, owner, args, argv, kwargs):
        owner.launched.append((args, kwargs))
        if owner.raises is not None:
            raise owner.raises
        if owner.on_launch:
            owner.on_launch(argv)
        code, out, err = owner._respond(argv)
        text = kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding")
        self.args, self.returncode, self.pid = args, code, 1
        self._streams = (out if text else out.encode(), err if text else err.encode())
        self.stdout = io.StringIO(out) if text else io.BytesIO(out.encode())
        self.stderr = io.StringIO(err) if text else io.BytesIO(err.encode())

    def communicate(self, *args, **kwargs):
        return self._streams

    def wait(self, *args, **kwargs):
        return self.returncode

    def poll(self):
        return self.returncode

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class EditorFakes(unittest.TestCase):
    """A temporary folder, a fake PATH and a recorder standing in for the
    editor's command line. `launched` holds `(args, kwargs)` for every call
    that is not `git`; `fakes()` installs the recorder for the length of a
    `with` block."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.on_path = {}
        self.launched = []
        self.extensions = []
        self.exit_code = 0
        self.stderr = ""
        self.raises = None
        self.on_launch = None
        self.crlf = False

    @contextmanager
    def fakes(self):
        with ExitStack() as stack:
            for target, replacement in (("shutil.which", self._which), ("subprocess.run", self._run),
                                        ("subprocess.Popen", self._popen), ("os.system", self._system)):
                stack.enter_context(mock.patch(target, replacement))
            yield

    def put_on_path(self, *commands):
        bin_dir = self.tmp / "bin"
        self.on_path = {command: str(bin_dir / command) for command in commands}

    def _which(self, cmd, *args, **kwargs):
        return self.on_path.get(Path(str(cmd)).stem.lower())

    def _respond(self, argv):
        if "--list-extensions" in argv:
            shown = [f"{e}@0.0.1" if "--show-versions" in argv else e for e in self.extensions]
            newline = "\r\n" if self.crlf else "\n"
            return self.exit_code, newline.join(shown) + (newline if shown else ""), self.stderr
        return self.exit_code, "", self.stderr

    def _run(self, args, *rest, **kwargs):
        argv = list(args) if not isinstance(args, str) else [args]
        if _stem(argv) == "git":
            return REAL_RUN(args, *rest, **kwargs)
        self.launched.append((args, kwargs))
        if self.raises is not None:
            raise self.raises
        if self.on_launch:
            self.on_launch(argv)
        code, out, err = self._respond(argv)
        if kwargs.get("check") and code:
            raise subprocess.CalledProcessError(code, args, out, err)
        text = kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding")
        return subprocess.CompletedProcess(
            args, code, out.replace("\r\n", "\n") if text else out.encode(), err if text else err.encode())

    def _popen(self, args, *rest, **kwargs):
        argv = list(args) if not isinstance(args, str) else [args]
        if _stem(argv) == "git":
            return REAL_POPEN(args, *rest, **kwargs)
        return _FakeProcess(self, args, argv, kwargs)

    def _system(self, command):
        self.launched.append((command, {}))
        return 0

    def make_project(self, name="orchard"):
        project = self.tmp / name
        spec = project / ".compass" / "specs" / "SPEC-001-x.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("# X\n", encoding="utf-8")
        return project, spec


class Registry(unittest.TestCase):
    def test_the_surfaces_are_registered_after_obsidian_under_their_own_names(self):
        """Adversarial where: a surface is missing from SURFACES, registered
        ahead of Obsidian (changing which editor a project without a setting
        gets), or both variants answer to one name."""
        module = importlib.import_module("review_surfaces.vscode")
        names = [s.NAME for s in review_surfaces.SURFACES]
        self.assertEqual(names[0], "obsidian")
        self.assertEqual(len(names), len(set(names)))
        for name in COMMANDS:
            self.assertIn(name, names)
        self.assertEqual(module.NAME, "vscode")


class Configuration(EditorFakes):
    def test_found_when_the_command_is_on_the_path_with_the_folder_holding_the_vault(self):
        """Adversarial where: the folder returned is the vault itself (or a
        parent of the project) instead of the folder holding `.compass`, a
        deep document is not traced back to its vault, or configuring the
        surface launches the editor."""
        project, spec = self.make_project()
        deep = project / ".compass" / "specs" / "network" / "cache" / "SPEC-001-eviction.md"
        deep.parent.mkdir(parents=True)
        deep.write_text("# E\n", encoding="utf-8")
        with self.fakes():
            for name, command in COMMANDS.items():
                self.put_on_path(command)
                for document in (spec, deep):
                    with self.subTest(surface=name, document=document.name):
                        context, reason = surface(name).configuration(document)
                        self.assertIsNone(reason)
                        self.assertEqual(Path(context["root"]).resolve(), project.resolve())
        self.assertEqual(self.launched, [])

    def test_each_variant_needs_its_own_command(self):
        """Adversarial where: cursor is configured because `code` exists (or
        the reverse), or the reason for a missing command names neither
        command."""
        _, spec = self.make_project()
        rows = (
            ("only code", ("code",), {"vscode": True, "cursor": False}),
            ("only cursor", ("cursor",), {"vscode": False, "cursor": True}),
            ("both", ("code", "cursor"), {"vscode": True, "cursor": True}),
            ("neither", (), {"vscode": False, "cursor": False}),
        )
        with self.fakes():
            for label, commands, expected in rows:
                self.put_on_path(*commands)
                for name, command in COMMANDS.items():
                    with self.subTest(row=label, surface=name):
                        context, reason = surface(name).configuration(spec)
                        self.assertEqual(context is not None, expected[name])
                        if context is None:
                            self.assertIn(command, reason)

    def test_the_folder_comes_from_the_document_not_the_environment(self):
        """Adversarial where: the nearest `.compass` above the document is
        ignored for the one `CLAUDE_PROJECT_DIR` names, so a review of a file
        in one project opens another project's window; or an outer vault wins
        over the inner one."""
        outer, _ = self.make_project("outer")
        inner = outer / "inner"
        document = inner / ".compass" / "plans" / "PLAN-001-y.md"
        document.parent.mkdir(parents=True)
        document.write_text("# Y\n", encoding="utf-8")
        elsewhere, _ = self.make_project("elsewhere")
        self.put_on_path("code")
        with self.fakes(), mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(elsewhere)}):
            context, reason = surface("vscode").configuration(document)
        self.assertIsNone(reason)
        self.assertEqual(Path(context["root"]).resolve(), inner.resolve())

    def test_a_document_outside_every_vault_is_not_configured_even_with_the_command(self):
        """Adversarial where: a document with no `.compass` above it is
        accepted because the command exists, so a request would be written
        beside nothing."""
        stray = self.tmp / "stray" / "note.md"
        stray.parent.mkdir()
        stray.write_text("# N\n", encoding="utf-8")
        self.put_on_path("code", "cursor")
        with self.fakes():
            for name in COMMANDS:
                with self.subTest(surface=name):
                    context, reason = surface(name).configuration(stray)
                    self.assertIsNone(context)
                    self.assertTrue(reason)


class Deliver(EditorFakes):
    def test_runs_the_command_with_the_folder_holding_the_vault_as_one_argument(self):
        """Adversarial where: the editor is started through a shell string, so
        a folder with a space reaches it as two arguments; `deliver` passes
        the vault instead of the folder holding it; or it adds arguments
        beyond `<command> <folder>`."""
        for folder_name in ("orchard", "my orchard & co"):
            project, spec = self.make_project(folder_name)
            for name, command in COMMANDS.items():
                with self.subTest(surface=name, folder=folder_name), self.fakes():
                    self.put_on_path(command)
                    self.launched.clear()
                    context, reason = surface(name).configuration(spec)
                    self.assertIsNone(reason)
                    request = project / ".compass" / "tmp" / "review" / "r1.request.json"
                    surface(name).deliver(context, request)
                    (args, kwargs), = self.launched
                    self.assertIsInstance(args, (list, tuple))
                    self.assertFalse(kwargs.get("shell"))
                    self.assertEqual(_stem(args), command)
                    self.assertEqual(len(args), 2)
                    self.assertEqual(Path(args[1]).resolve(), project.resolve())


class Install(EditorFakes):
    def shipped_root(self, with_vsix=True):
        root = self.tmp / "claude"
        shutil.rmtree(root, ignore_errors=True)
        for folder in (root / "vscode", root / "vscode" / "compass-review"):
            folder.mkdir(parents=True, exist_ok=True)
            if with_vsix:
                (folder / "compass-review-9.9.9.vsix").write_bytes(b"PK")
        return root

    def test_runs_install_extension_on_the_shipped_vsix(self):
        """Adversarial where: the install command is missing `--install-extension`,
        names a path that is not the shipped `.vsix`, runs the other editor's
        command, or returns no line saying what was done."""
        project, _ = self.make_project()
        root = self.shipped_root()
        for name, command in COMMANDS.items():
            with self.subTest(surface=name), self.fakes():
                self.put_on_path(command)
                self.launched.clear()
                line = surface(name).install(project / ".compass", root)
                (args, _kwargs), = self.launched
                self.assertEqual(_stem(args), command)
                vsix = Path(args[list(args).index("--install-extension") + 1])
                self.assertTrue(vsix.is_file())
                self.assertEqual(vsix.suffix, ".vsix")
                self.assertIn(root.resolve(), vsix.resolve().parents)
                self.assertTrue(line.strip())
                self.assertNotIn("\n", line.strip())

    def test_default_location_is_the_vsix_shipped_beside_the_extension(self):
        """Adversarial where: with no `shipped_root` the install looks in a
        folder where no `.vsix` ships, so a source checkout installs nothing."""
        project, _ = self.make_project()
        self.put_on_path("code")
        with self.fakes():
            surface("vscode").install(project / ".compass")
        (args, _kwargs), = self.launched
        vsix = Path(args[list(args).index("--install-extension") + 1])
        self.assertTrue(vsix.is_file(), vsix)
        self.assertIn(VSCODE_DIR.resolve(), vsix.resolve().parents)

    def test_install_reports_a_failure_in_a_line_and_never_raises(self):
        """Adversarial where: a missing command, a missing `.vsix`, a non-zero
        exit, a vanished executable or a hung editor raises out of
        `compass review --install`, or a failed install is reported as
        `installed`."""
        project, _ = self.make_project()
        rows = (
            ("command missing", {"commands": (), "vsix": True, "launches": 0}),
            ("no vsix shipped", {"commands": ("code",), "vsix": False, "launches": 0}),
            ("non-zero exit", {"commands": ("code",), "vsix": True, "launches": 1,
                               "exit_code": 1, "stderr": "boom"}),
            ("executable vanished", {"commands": ("code",), "vsix": True, "launches": 1,
                                     "raises": FileNotFoundError("code")}),
            ("editor hung", {"commands": ("code",), "vsix": True, "launches": 1,
                             "raises": subprocess.TimeoutExpired("code", 1)}),
        )
        for label, row in rows:
            with self.subTest(row=label), self.fakes():
                self.launched.clear()
                self.exit_code = row.get("exit_code", 0)
                self.stderr = row.get("stderr", "")
                self.raises = row.get("raises")
                self.put_on_path(*row["commands"])
                root = self.shipped_root(with_vsix=row["vsix"])
                line = surface("vscode").install(project / ".compass", root)
                self.assertEqual(len(self.launched), row["launches"])
                self.assertTrue(line.strip())
                self.assertNotRegex(line, r"(?i)^\s*installed")


class Doctor(EditorFakes):
    def test_the_extension_missing_warns_with_the_install_command_and_present_is_ok(self):
        """Adversarial where: the extension is judged installed because its id
        is a prefix of a longer id, because the listing's Windows line endings
        leave a stray character on the id, or it is never looked for; the fix
        does not name the command that installs it."""
        project, _ = self.make_project()
        eid = extension_id()
        self.put_on_path("code", "cursor")
        rows = (
            ("no extensions", [], False, "WARN"),
            ("other extensions", ["ms-python.python", "esbenp.prettier-vscode"], False, "WARN"),
            ("longer id with the same start", [eid + "-mockup"], False, "WARN"),
            ("listed exactly", ["ms-python.python", eid], False, "OK"),
            ("listed with Windows line endings", ["ms-python.python", eid], True, "OK"),
        )
        with self.fakes():
            for name in COMMANDS:
                for label, listed, crlf, expected in rows:
                    with self.subTest(surface=name, row=label):
                        self.extensions, self.crlf = listed, crlf
                        status, detail, fix = surface(name).doctor(project / ".compass")
                        self.assertEqual(status, expected, detail)
                        if expected == "WARN":
                            self.assertIn("compass review --install", fix)

    def test_doctor_without_the_command_or_with_a_failing_listing_neither_raises_nor_launches(self):
        """Adversarial where: a missing editor makes doctor run a command
        that does not exist, or a listing that fails (non-zero exit, vanished
        executable, timeout) crashes `compass doctor`."""
        project, _ = self.make_project()
        rows = (
            ("command missing", (), None, 0, 0),
            ("non-zero exit", ("code",), None, 2, 1),
            ("executable vanished", ("code",), FileNotFoundError("code"), 0, 1),
            ("editor hung", ("code",), subprocess.TimeoutExpired("code", 1), 0, 1),
        )
        for label, commands, raises, exit_code, launches in rows:
            with self.subTest(row=label), self.fakes():
                self.launched.clear()
                self.put_on_path(*commands)
                self.raises, self.exit_code = raises, exit_code
                result = surface("vscode").doctor(project / ".compass")
                self.assertEqual(len(result), 3)
                self.assertIn(result[0], ("OK", "WARN"))
                self.assertEqual(len(self.launched), launches)


class FocusAndResolve(EditorFakes):
    def test_has_focus_is_a_bool_and_false_off_windows(self):
        """Adversarial where: the focus check raises or returns a truthy
        non-bool where there is no Windows foreground API, so a review would
        wrongly ask the editor to stay in front."""
        for name in COMMANDS:
            with self.subTest(surface=name, platform="linux"), mock.patch.object(sys, "platform", "linux"):
                self.assertIs(surface(name).has_focus(), False)
            with self.subTest(surface=name, platform="this machine"):
                self.assertIsInstance(surface(name).has_focus(), bool)

    def test_resolve_and_the_review_guard_reach_every_listed_file_through_the_folder(self):
        """Adversarial where: `resolve` joins the file to the vault instead of
        the folder holding it (so `.compass/` is doubled), returns a path for a
        request with no usable `file`, or the guard misses a file that only
        the request's `files` list names."""
        project, spec = self.make_project()
        plan = project / ".compass" / "plans" / "PLAN-001-y.md"
        plan.parent.mkdir()
        plan.write_text("# Y\n", encoding="utf-8")
        other = project / ".compass" / "plans" / "PLAN-002-z.md"
        other.write_text("# Z\n", encoding="utf-8")
        vault = project / ".compass"
        for name in COMMANDS:
            with self.subTest(surface=name):
                found = surface(name).resolve({"file": ".compass/specs/SPEC-001-x.md"}, vault)
                self.assertEqual(Path(found).resolve(), spec.resolve())
                self.assertIsNone(surface(name).resolve({"file": 7}, vault))
                self.assertIsNone(surface(name).resolve({}, vault))
        directory = reviewlib.review_dir(vault)
        directory.mkdir(parents=True)
        (directory / "r1.request.json").write_text(json.dumps({
            "id": "r1", "surface": "vscode", "file": ".compass/specs/SPEC-001-x.md",
            "files": [{"file": ".compass/specs/SPEC-001-x.md", "why": None},
                      {"file": ".compass/plans/PLAN-001-y.md", "why": None}]}), encoding="utf-8")
        with mock.patch.object(review_surfaces, "SURFACES", [surface("vscode")]):
            self.assertEqual(reviewlib.under_review(vault, plan)["id"], "r1")
            self.assertIsNone(reviewlib.under_review(vault, other))


class ReviewThroughTheCli(EditorFakes):
    def setUp(self):
        super().setUp()
        self.project, self.spec = self.make_project()
        self.plan = self.project / ".compass" / "plans" / "PLAN-001-y.md"
        self.plan.parent.mkdir()
        self.plan.write_text("# Y\n", encoding="utf-8")
        (self.tmp / "gitconfig").write_text("", encoding="utf-8")
        env = {
            "CLAUDE_PROJECT_DIR": str(self.project),
            "CLAUDE_CODE_SESSION_ID": "7f3a91c2-4d1b-4e8a-9b2f-5c06d83e1a47",
            "GIT_CEILING_DIRECTORIES": str(self.tmp),
            "GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for args in (["init", "-q"], ["config", "user.name", "Tester"],
                     ["config", "user.email", "tester@example.invalid"],
                     ["add", ".compass"], ["commit", "-q", "-m", "first"]):
            REAL_RUN(["git", *args], cwd=self.project, check=True, capture_output=True)

    def test_a_several_file_review_reaches_the_editor_and_its_answer_comes_back(self):
        """Adversarial where: the request is written under a different folder
        than the one the editor is opened on (so the extension never sees
        it), its `file` paths are relative to the vault rather than to that
        folder, or its `surface` names the wrong editor."""
        module = importlib.import_module("commands.review")
        for name, command in COMMANDS.items():
            with self.subTest(surface=name), self.fakes():
                shutil.rmtree(self.project / ".compass" / "tmp", ignore_errors=True)
                self.launched.clear()
                self.put_on_path(command)
                seen = []

                def answer(argv):
                    folder = Path(argv[-1])
                    for path in sorted((folder / ".compass" / "tmp" / "review").glob("*.request.json")):
                        request = json.loads(path.read_text(encoding="utf-8"))
                        seen.append(request)
                        reviewlib.verdict_path(path).write_text(json.dumps({
                            "id": request["id"], "file": request["file"], "verdict": "approved",
                            "notes": "", "comments": [], "edited": [], "at": "t",
                            "files": [{"file": f["file"], "read": True} for f in request["files"]]}),
                            encoding="utf-8")

                self.on_launch = answer
                chosen = surface(name)
                out, err = io.StringIO(), io.StringIO()
                with mock.patch.object(review_surfaces, "SURFACES", [chosen]), \
                        mock.patch.object(chosen, "has_focus", lambda: False), \
                        redirect_stdout(out), redirect_stderr(err):
                    code = module.run([str(self.spec), str(self.plan), "--why", f"{self.spec}=The need",
                                       "--timeout", "5"])
                text = out.getvalue()
                self.assertEqual(code, 0, text + err.getvalue())
                self.assertTrue(text.startswith("requested "), text)
                self.assertIn("file .compass/specs/SPEC-001-x.md read", text)
                self.assertIn("file .compass/plans/PLAN-001-y.md read", text)
                request, = seen
                self.assertEqual(request["surface"], name)
                self.assertEqual(request["file"], ".compass/specs/SPEC-001-x.md")
                self.assertEqual(request["files"], [
                    {"file": ".compass/specs/SPEC-001-x.md", "why": "The need"},
                    {"file": ".compass/plans/PLAN-001-y.md", "why": None}])
                self.assertEqual(request["project"], "orchard")
                (args, _kwargs), = self.launched
                self.assertEqual(_stem(args), command)


class ShippedFiles(unittest.TestCase):
    def test_exactly_one_vsix_ships_carrying_the_current_sources_and_is_not_ignored(self):
        """Adversarial where: the `.vsix` was packed before the last edit to
        extension.js or card.js, an older `.vsix` lingers beside the new one,
        the archive lacks the files an editor needs to install it, or git
        ignores the artifact so a fresh checkout ships none."""
        packed = sorted(p for p in VSCODE_DIR.rglob("*.vsix") if "node_modules" not in p.parts)
        self.assertEqual(len(packed), 1, [str(p) for p in packed])
        ignored = REAL_RUN(["git", "check-ignore", "-q", str(packed[0])], cwd=PLUGIN, capture_output=True)
        self.assertEqual(ignored.returncode, 1, "git ignores the shipped .vsix")
        with zipfile.ZipFile(packed[0]) as archive:
            names = set(archive.namelist())
            self.assertIn("extension.vsixmanifest", names)
            self.assertIn("[Content_Types].xml", names)
            for member, source in (("extension/package.json", EXTENSION_DIR / "package.json"),
                                   ("extension/extension.js", EXTENSION_DIR / "extension.js"),
                                   ("extension/media/card.js", EXTENSION_DIR / "media" / "card.js")):
                with self.subTest(member=member):
                    self.assertEqual(archive.read(member).replace(b"\r\n", b"\n"),
                                     source.read_bytes().replace(b"\r\n", b"\n"))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ExtensionHarness(unittest.TestCase):
    """Runs the extension's Node harness inside the Python suite, as the
    Obsidian plugin's is, so a broken extension fails the same run."""

    def test_the_extension_and_its_card_parse(self):
        """Adversarial where: a syntax error in extension.js or card.js that
        only a real VS Code would reveal."""
        for source in (EXTENSION_DIR / "extension.js", EXTENSION_DIR / "media" / "card.js"):
            with self.subTest(source=source.name):
                result = subprocess.run(["node", "--check", str(source)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_the_node_harness_passes(self):
        """Adversarial where: the extension's behavior tests fail while the
        Python suite alone reads green."""
        harness = VSCODE_DIR / "tests" / "test_extension.js"
        result = subprocess.run(["node", "--test", str(harness)], capture_output=True, text=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:])
        self.assertIn("# fail 0", result.stdout)


if __name__ == "__main__":
    unittest.main()
