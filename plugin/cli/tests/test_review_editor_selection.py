"""Tests for the one rule that picks the editor reviews open in, shared by the
delivery of a review, the update's automatic install and `compass doctor`, and
for `compass review --editor`.

Adversarial themes: the three consumers of the rule drifting apart (doctor
naming an editor the review does not go to, the update installing into an
editor the review ignores); a `review_editor` setting that cannot be honoured
sending the review to some other editor; Obsidian chosen while Obsidian does
not list the vault; `--editor` rewriting a plugin.yaml beyond its own line
(other lines, nested lines of the same name, comments, line endings, a byte-
order mark, a missing final newline) and touching Obsidian's global vault
list; `--install` losing its reach over every editor.

No editor is started and the user's editors are never touched: the VS Code and
Cursor command lines are recorded by the fakes of `test_review_unconfirmed.py`
and Obsidian's vault list is a file in the temporary folder.
"""

import importlib
import io
import itertools
import json
import os
import re
import shutil
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import review_surfaces  # noqa: E402
import reviewlib  # noqa: E402
import test_review_unconfirmed as un  # noqa: E402
import test_review_vscode as vs  # noqa: E402
from review_surfaces import obsidian as obsidian_surface  # noqa: E402

PLUGIN_YAML = (
    "plugin:\n"
    "  name: compass\n"
    "  version: 0.30.0\n"
    "  review_editor: vscode\n"
    "  notes: |\n"
    "    # review_editor: cursor\n"
    "    kept as written.\n"
)
STEP = re.compile(r"^In Obsidian: Open folder as vault, (?P<path>.+), then turn on Compass Review$")


class Selection(un.Editors):
    """A git project with one committed spec, the editor fakes, and an
    Obsidian vault list that lists nothing until a test lists it."""

    def setUp(self):
        super().setUp()
        self.project, self.spec = self.make_project()
        self.vault = self.project / ".compass"
        self.config = self.tmp / "obsidian.json"
        (self.tmp / "gitconfig").write_text("", encoding="utf-8")
        env = {
            "CLAUDE_PROJECT_DIR": str(self.project),
            "COMPASS_OBSIDIAN_CONFIG": str(self.config),
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
            vs.REAL_RUN(["git", *args], cwd=self.project, check=True, capture_output=True)
        self.opened = []
        stubs = [(obsidian_surface, "open_uri", self.opened.append), (obsidian_surface, "has_focus", lambda: False)]
        stubs += [(vs.surface(name), "has_focus", lambda: False) for name in vs.COMMANDS]
        for target, attr, value in stubs:
            patcher = mock.patch.object(target, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @property
    def plugin_yaml(self):
        return self.vault / "meta" / "plugin.yaml"

    def arrange(self, setting=None, commands=(), extension=False, obsidian="none"):
        """Put the project in one state: the `review_editor` line (None for no
        line), the editor commands on the PATH, whether the editors list the
        extension, and Obsidian's view of the project (`none`, `unlisted` for a
        `.obsidian/` Obsidian does not list, `listed` for one it lists with the
        plugin installed)."""
        self.plugin_yaml.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_yaml.write_text("plugin:\n  name: compass\n  version: 0.30.0\n"
                                    + (f"review_editor: {setting}\n" if setting else ""), encoding="utf-8")
        self.put_on_path(*commands)
        self.installed = [(vs.extension_id(), un.shipped_version())] if extension else []
        self.launched.clear()
        obsidian_dir = self.vault / ".obsidian"
        shutil.rmtree(obsidian_dir, ignore_errors=True)
        self.config.unlink(missing_ok=True)
        if obsidian != "none":
            obsidian_dir.mkdir()
        if obsidian == "listed":
            self.config.write_text(json.dumps({"vaults": {"abc123": {"path": str(self.vault)}}}), encoding="utf-8")
            obsidian_surface.install_plugin(self.vault, with_bases=False)

    def review(self, *args):
        module = importlib.import_module("commands.review")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = module.run(list(args))
        return code, out.getvalue(), err.getvalue()

    def requests(self):
        return sorted((self.vault / "tmp" / "review").glob("*.request.json"))


class SharedRule(Selection):
    def test_an_unset_editor_with_code_on_the_path_is_vscode_for_doctor_update_and_delivery(self):
        """Adversarial where: doctor says VS Code while the update skips its
        extension (or the review ignores it), so a review waits on an editor
        without the extension."""
        with self.fakes():
            for installed in (False, True):
                with self.subTest(extension_installed=installed):
                    self.arrange(commands=("code",), extension=installed)
                    status, detail, _ = reviewlib.editor_report(self.vault)
                    self.assertEqual(status, "OK", detail)
                    self.assertIn("vscode", detail)
                    self.arrange(commands=("code",), extension=installed)
                    lines = reviewlib.install(self.vault, automatic=True)
                    self.assertTrue(lines[1].startswith("vscode: installed"), lines)
                    self.assertIn("installed nothing", lines[2], lines)
                    self.arrange(commands=("code",), extension=installed)
                    surface, _, reason = reviewlib.choose(self.spec)
                    self.assertEqual((surface.NAME, reason), ("vscode", None))
                    self.assertEqual(self.ops().count("install"), 0 if installed else 1)

    def test_the_review_installs_the_missing_extension_before_it_is_written(self):
        """Adversarial where: `compass review` writes a request for an editor
        that has no extension, so nothing shows it and the agent waits."""
        with self.fakes():
            self.arrange(commands=("code",), extension=False)
            code, out, err = self.review(str(self.spec), "--no-wait")
            self.assertEqual(code, 0, out + err)
            ops = self.ops()
            self.assertIn("install", ops)
            self.assertLess(ops.index("install"), ops.index("open"))
            self.assertEqual(json.loads(self.requests()[0].read_text(encoding="utf-8"))["surface"], "vscode")

    def test_only_the_selected_per_user_editor_gets_its_extension_from_an_update(self):
        """Adversarial where: an update installs into Cursor because it is on
        the PATH although VS Code is what reviews open in, or into neither."""
        rows = (
            ("code and cursor", ("code", "cursor"), "vscode"),
            ("only cursor", ("cursor",), "cursor"),
            ("only code", ("code",), "vscode"),
        )
        with self.fakes():
            for label, commands, expected in rows:
                with self.subTest(label):
                    self.arrange(commands=commands)
                    lines = reviewlib.install(self.vault, automatic=True)
                    done = [line.split(":")[0] for line in lines if ": installed" in line and "nothing" not in line]
                    self.assertEqual([n for n in done if n != "obsidian"], [expected], lines)
            self.arrange(commands=())
            lines = reviewlib.install(self.vault, automatic=True)
            self.assertNotIn("install", self.ops())
            self.assertEqual(reviewlib.editor_report(self.vault)[:2],
                             ("OK", "no review editor is set up; reviews are asked in the terminal"))
            self.assertEqual(reviewlib.choose(self.spec)[0], None)
            self.assertEqual(len(lines), 3)

    def test_obsidian_wins_an_unset_project_only_when_a_vault_folder_exists(self):
        """Adversarial where: Obsidian is preferred for every project (so a
        project that never used it waits on a missing app), or never preferred
        (so an Obsidian project is sent to an editor on the PATH)."""
        with self.fakes():
            self.arrange(commands=("code",), extension=False, obsidian="unlisted")
            self.assertEqual(reviewlib.selected_surface(self.vault).NAME, "obsidian")
            self.arrange(commands=("code",), extension=False, obsidian="none")
            self.assertEqual(reviewlib.selected_surface(self.vault).NAME, "vscode")
            self.arrange(commands=("code",), extension=True, obsidian="unlisted")
            self.assertEqual(reviewlib.selected_surface(self.vault).NAME, "vscode",
                             "a surface that is ready beats one that could be installed")

    def test_obsidian_named_without_a_vault_gives_the_step_and_never_falls_to_vscode(self):
        """Adversarial where: `review_editor: obsidian` with no vault leaves
        doctor silent and sends the review to VS Code."""
        with self.fakes():
            for obsidian in ("none", "unlisted"):
                with self.subTest(obsidian=obsidian):
                    self.arrange(setting="obsidian", commands=("code",), extension=True, obsidian=obsidian)
                    status, detail, fix = reviewlib.editor_report(self.vault)
                    self.assertEqual(status, "WARN", detail)
                    found = STEP.match(fix or "")
                    self.assertIsNotNone(found, fix)
                    self.assertEqual(Path(found["path"]), self.vault.resolve())
                    surface, _, reason = reviewlib.choose(self.spec)
                    self.assertIsNone(surface)
                    self.assertIn(fix, reason)
                    code, out, _ = self.review(str(self.spec), "--no-wait")
                    self.assertEqual(code, 1, out)
                    self.assertTrue(out.startswith("not configured:"), out)
                    self.assertEqual(self.requests(), [])
                    self.assertNotIn("open", self.ops())
                    lines = reviewlib.install(self.vault, automatic=True)
                    self.assertIn("installed nothing", lines[1], lines)

    def test_a_vault_obsidian_lists_with_the_plugin_on_is_ready_and_has_no_step(self):
        """Adversarial where: doctor keeps asking for the step after the human
        did it, or delivery still refuses a listed vault."""
        with self.fakes():
            self.arrange(setting="obsidian", obsidian="listed")
            status, detail, fix = reviewlib.editor_report(self.vault)
            self.assertEqual((status, fix), ("OK", None), detail)
            self.assertEqual(reviewlib.choose(self.spec)[0].NAME, "obsidian")

    def test_an_unknown_editor_is_refused_by_delivery_and_failed_by_doctor(self):
        """Adversarial where: a typo in `review_editor` sends the review to
        another editor while doctor reports an error."""
        with self.fakes():
            self.arrange(setting="emacs", commands=("code",), extension=True)
            self.assertEqual(reviewlib.editor_report(self.vault)[0], "FAIL")
            surface, _, reason = reviewlib.choose(self.spec)
            self.assertIsNone(surface)
            self.assertIn("emacs", reason)
            self.assertIn("vscode", reason)

    def test_doctor_and_delivery_never_contradict_each_other(self):
        """Adversarial where: some mix of setting, commands on the PATH,
        extension state and Obsidian state makes doctor name an editor the
        review does not use, report no editor while one is used, or warn of a
        step for an editor the review goes to anyway."""
        settings = (None, "obsidian", "vscode", "cursor")
        paths = ((), ("code",), ("cursor",), ("code", "cursor"))
        states = list(itertools.product(settings, paths, (False, True), ("none", "unlisted", "listed")))
        with self.fakes():
            for setting, commands, extension, obsidian in states:
                label = f"setting={setting} path={commands} extension={extension} obsidian={obsidian}"
                with self.subTest(label):
                    self.arrange(setting, commands, extension, obsidian)
                    status, detail, fix = reviewlib.editor_report(self.vault)
                    self.arrange(setting, commands, extension, obsidian)
                    surface, _, reason = reviewlib.choose(self.spec)
                    self.assertNotEqual(status, "FAIL", detail)
                    opens_in = re.match(r"reviews open in (\w+)", detail)
                    if surface is not None:
                        self.assertIn(surface.NAME, detail)
                        self.assertFalse(STEP.match(fix or ""), f"doctor asks for a step, delivery works: {fix}")
                        if opens_in:
                            self.assertEqual(opens_in[1], surface.NAME)
                    else:
                        self.assertFalse(status == "OK" and opens_in, f"doctor: {detail}; delivery: {reason}")
                        if setting:
                            self.assertEqual(status, "WARN", detail)
                    if status == "OK" and "no review editor" in detail:
                        self.assertIsNone(surface, label)
                    if STEP.match(fix or ""):
                        self.assertIsNone(surface, label)
                        self.assertIn(fix, reason)


class EditorFlag(Selection):
    def test_the_line_is_added_without_touching_any_other_line(self):
        """Adversarial where: `--editor` rewrites the file (losing a comment,
        a nested `review_editor` of the notes block, the line endings, the
        byte-order mark) or leaves the last line glued to the new one."""
        texts = {
            "plain": "plugin:\n  name: compass\n  notes: |\n    review_editor: cursor\n# review_editor: cursor\n",
            "no final newline": "plugin:\n  name: compass",
            "CRLF": "plugin:\r\n  name: compass\r\n",
            "byte-order mark": "﻿plugin:\n  name: compass\n",
            "empty file": "",
        }
        with self.fakes():
            for label, text in texts.items():
                with self.subTest(label):
                    self.plugin_yaml.parent.mkdir(parents=True, exist_ok=True)
                    self.plugin_yaml.write_bytes(text.encode("utf-8"))
                    code, out, err = self.review("--editor", "vscode")
                    self.assertEqual(code, 0, out + err)
                    written = self.plugin_yaml.read_bytes().decode("utf-8")
                    newline = "\r\n" if "\r\n" in text else "\n"
                    self.assertTrue(written.startswith(text.rstrip("\r\n")), written)
                    self.assertTrue(written.endswith(f"review_editor: vscode{newline}"), repr(written))
                    self.assertEqual(written.count("review_editor: vscode"), 1)
                    self.assertEqual(reviewlib.review_editor(self.vault), "vscode")

    def test_an_existing_line_is_replaced_in_place_and_nothing_else_changes(self):
        """Adversarial where: the nested `review_editor` line inside the
        notes block, or the commented one, is replaced instead of the
        top-level line; the new line moves to the end; a second run adds a
        second line."""
        lines = ["name: compass\n", "review_editor: vscode   # old\n", "notes: |\n", "  review_editor: cursor\n",
                 "# review_editor: cursor\n", "tail: x\n"]
        with self.fakes():
            for target in ("obsidian", "cursor", "vscode"):
                with self.subTest(target):
                    self.plugin_yaml.parent.mkdir(parents=True, exist_ok=True)
                    self.plugin_yaml.write_text("".join(lines), encoding="utf-8")
                    self.assertEqual(self.review("--editor", target)[0], 0)
                    self.assertEqual(self.review("--editor", target)[0], 0)
                    expected = list(lines)
                    expected[1] = f"review_editor: {target}\n"
                    self.assertEqual(self.plugin_yaml.read_text(encoding="utf-8"), "".join(expected))
                    self.assertEqual(reviewlib.review_editor(self.vault), target)

    def test_a_yaml_null_line_and_a_replaced_line_with_a_bom_are_replaced(self):
        """Adversarial where: a line `review_editor: null` is kept next to a
        new line (the parser reads the first), or a replaced first line loses
        its byte-order mark."""
        with self.fakes():
            for text in ("review_editor: null\nname: x\n", "﻿review_editor: ~\nname: x\n"):
                with self.subTest(text=text):
                    self.plugin_yaml.parent.mkdir(parents=True, exist_ok=True)
                    self.plugin_yaml.write_bytes(text.encode("utf-8"))
                    self.assertEqual(self.review("--editor", "cursor")[0], 0)
                    written = self.plugin_yaml.read_bytes().decode("utf-8")
                    self.assertEqual(written, text.split("review_editor")[0] + "review_editor: cursor\nname: x\n")
                    self.assertEqual(reviewlib.review_editor(self.vault), "cursor")

    def test_a_name_that_is_not_a_review_editor_changes_nothing(self):
        """Adversarial where: a typo is written into plugin.yaml and doctor
        then fails every later run, or the exit code is 0."""
        self.plugin_yaml.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_yaml.write_text(PLUGIN_YAML, encoding="utf-8")
        for name in ("emacs", "", "obsidian,vscode"):
            with self.subTest(name=name):
                code, out, err = self.review("--editor", name)
                self.assertEqual(code, 1)
                self.assertIn("not a review editor", err)
                self.assertEqual(self.plugin_yaml.read_text(encoding="utf-8"), PLUGIN_YAML)

    def test_the_flag_is_a_run_of_its_own(self):
        """Adversarial where: `--editor` combined with `--install`, a file or
        no name runs part of both or raises."""
        for args in (["--editor"], ["--editor", "vscode", "--install"], ["--editor", "vscode", "--status"],
                     ["--selected"]):
            with self.subTest(args=args):
                code, out, err = self.review(*args)
                self.assertEqual(code, 1, out)
                self.assertIn("compass review:", err)
        self.assertFalse(self.plugin_yaml.exists())

    def test_no_vault_is_reported(self):
        """Adversarial where: `--editor` outside a Compass project creates a
        plugin.yaml in the working folder."""
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(elsewhere)}), \
                mock.patch("os.getcwd", return_value=str(elsewhere)):
            code, out, _ = self.review("--editor", "vscode")
        self.assertEqual(code, 1)
        self.assertIn("no .compass vault", out)
        self.assertFalse((elsewhere / "meta").exists())

    def test_obsidian_gets_a_vault_folder_the_plugin_and_the_one_human_step(self):
        """Adversarial where: the plugin is not installed or not enabled
        because `.obsidian/` was missing, the step names the wrong folder,
        or Obsidian's own vault list is written."""
        self.config.write_text(json.dumps({"vaults": {"zzz": {"path": str(self.tmp / "other")}}}), encoding="utf-8")
        before = self.config.read_bytes()
        with self.fakes():
            code, out, err = self.review("--editor", "obsidian")
        self.assertEqual(code, 0, out + err)
        listing = self.vault / ".obsidian" / "community-plugins.json"
        self.assertEqual(json.loads(listing.read_text(encoding="utf-8")), ["compass-review"])
        for name in obsidian_surface.PLUGIN_FILES:
            self.assertTrue((self.vault / ".obsidian" / "plugins" / "compass-review" / name).is_file(), name)
        self.assertEqual(obsidian_surface.plugin_state(self.vault), "on")
        self.assertTrue(obsidian_surface.plugin_current(self.vault))
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(reviewlib.review_editor(self.vault), "obsidian")
        last = out.splitlines()[-1]
        found = STEP.match(last)
        self.assertIsNotNone(found, out)
        self.assertEqual(Path(found["path"]), self.vault.resolve())
        self.assertEqual(self.opened, [], "Obsidian is not opened")

    def test_obsidian_that_lists_the_vault_prints_no_step(self):
        """Adversarial where: the step is printed again for a vault the human
        already opened, so he is sent to do it twice."""
        self.config.write_text(json.dumps({"vaults": {"abc": {"path": str(self.vault)}}}), encoding="utf-8")
        (self.vault / ".obsidian").mkdir()
        code, out, err = self.review("--editor", "Obsidian")
        self.assertEqual(code, 0, out + err)
        self.assertFalse([line for line in out.splitlines() if STEP.match(line)], out)
        self.assertEqual(reviewlib.review_editor(self.vault), "obsidian")

    def test_a_vault_folder_around_the_project_is_used_instead_of_a_new_one(self):
        """Adversarial where: `--editor obsidian` creates `.compass/.obsidian/`
        although the project root is already a vault, leaving two vaults."""
        (self.project / ".obsidian").mkdir()
        code, out, err = self.review("--editor", "obsidian")
        self.assertEqual(code, 0, out + err)
        self.assertFalse((self.vault / ".obsidian").exists())
        self.assertEqual(obsidian_surface.plugin_state(self.project), "on")
        found = STEP.match(out.splitlines()[-1])
        self.assertEqual(Path(found["path"]), self.project.resolve())

    def test_vscode_and_cursor_get_their_extension_and_no_step(self):
        """Adversarial where: `--editor cursor` installs into VS Code, or
        asks the human for an Obsidian step."""
        with self.fakes():
            for name, command in vs.COMMANDS.items():
                with self.subTest(name):
                    self.arrange(commands=("code", "cursor"))
                    code, out, err = self.review("--editor", name)
                    self.assertEqual(code, 0, out + err)
                    installs = [vs._stem(list(a)) for a, _ in self.launched if "--install-extension" in list(a)]
                    self.assertEqual(installs, [command])
                    self.assertFalse([line for line in out.splitlines() if STEP.match(line)], out)
                    self.assertIn(f"{name}: installed", out)

    def test_an_extension_that_cannot_be_installed_is_a_failed_run(self):
        """Adversarial where: the install fails and `--editor` still exits 0,
        so setup believes the editor is ready."""
        with self.fakes():
            self.arrange(commands=("code",))
            self.rules = {("code", "install"): {"exit": 1, "stderr": "no network"}}
            code, out, err = self.review("--editor", "vscode")
            self.assertEqual(code, 1, out + err)
            self.assertIn("vscode: failed", out)
            self.assertEqual(reviewlib.review_editor(self.vault), "vscode")

    def test_a_plugin_yaml_that_cannot_be_written_is_reported_not_raised(self):
        """Adversarial where: an unwritable meta folder ends in a traceback and
        leaves a temporary file behind."""
        self.plugin_yaml.parent.mkdir(parents=True, exist_ok=True)
        with mock.patch("os.replace", side_effect=PermissionError("locked")):
            code, out, err = self.review("--editor", "vscode")
        self.assertEqual(code, 1, out)
        self.assertIn("could not write plugin.yaml", err)
        self.assertEqual(list(self.plugin_yaml.parent.iterdir()), [])

    def test_the_editor_set_by_the_flag_is_the_one_delivery_and_doctor_use(self):
        """Adversarial where: the line `--editor` writes is not read back the
        way `choose` and doctor read it."""
        with self.fakes():
            self.arrange(commands=("code", "cursor"), extension=True)
            self.assertEqual(self.review("--editor", "cursor")[0], 0)
            self.assertEqual(reviewlib.choose(self.spec)[0].NAME, "cursor")
            self.assertEqual(reviewlib.editor_report(self.vault)[:2],
                             ("OK", "reviews open in cursor (review_editor in plugin.yaml)"))


class InstallStillCoversEveryEditor(Selection):
    def test_install_reaches_every_editor_whatever_the_setting_says(self):
        """Adversarial where: the shared rule narrows the asked-for
        `--install` to the selected editor, so a human cannot prepare a second
        editor."""
        with self.fakes():
            self.arrange(setting="obsidian", commands=("code", "cursor"))
            code, out, err = self.review("--install")
            self.assertEqual(code, 0, out + err)
            names = [line.split(":")[0] for line in out.splitlines()]
            self.assertEqual(names, ["obsidian", "vscode", "cursor"])
            installs = [vs._stem(list(a)) for a, _ in self.launched if "--install-extension" in list(a)]
            self.assertEqual(installs, ["code", "cursor"])

    def test_install_selected_is_what_an_update_does(self):
        """Adversarial where: `--install --selected` installs into editors the
        project does not review in, or into none."""
        with self.fakes():
            self.arrange(setting="cursor", commands=("code", "cursor"))
            code, out, err = self.review("--install", "--selected")
            self.assertEqual(code, 0, out + err)
            installs = [vs._stem(list(a)) for a, _ in self.launched if "--install-extension" in list(a)]
            self.assertEqual(installs, ["cursor"])


class SurfaceAnswers(unittest.TestCase):
    def test_every_registered_surface_answers_the_selection_questions(self):
        """Adversarial where: a registered surface lacks `installable`,
        `pending_step` or `prepare`, so the rule skips it silently."""
        for surface in review_surfaces.SURFACES:
            for attr in ("installable", "pending_step", "prepare"):
                self.assertTrue(callable(getattr(surface, attr, None)), f"{surface.NAME} lacks {attr}")


if __name__ == "__main__":
    unittest.main()
