"""Tests for a review that never waits on an editor that cannot show it: the
VS Code, Cursor and Obsidian surfaces check (and install) their add-on before
a request is written, the add-on's claim of a request is a `<id>.seen` file
beside it, and `compass review` withdraws a request nobody claimed within
`ACK_SECONDS` instead of waiting without limit.

Adversarial themes: an extension that is listed but older than the shipped
one, listed under another case, listed under a longer id, or listed at a
version whose digits compare differently as text; a listing or an install that
fails, times out or vanishes; Obsidian files that are stale in only one of the
three, a plugin list that is not a list; a claim that arrives just inside the
window, an answer with no claim, another request's claim, a withdrawal inside
the window and a `--timeout` shorter than the window.

No editor is started: the VS Code and Cursor command lines are recorded by the
fakes of `test_review_vscode.py`, and the Obsidian opener and focus probe are
stubbed by `ReviewProject`. Every wait test patches `ACK_SECONDS` and
`POLL_SECONDS` of `commands.review` to fractions of a second and passes
`--timeout` so a missing acknowledgement ends the test instead of hanging it.
"""

import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import review_surfaces  # noqa: E402
import reviewlib  # noqa: E402
import test_review_vscode as vs  # noqa: E402
from review_surfaces import obsidian as obsidian_surface  # noqa: E402
from test_review import ReviewProject  # noqa: E402

ACK = 0.6
POLL = 0.05
LINE = r"^not configured: (?P<label>.+?) did not pick up review (?P<id>\S+) within [\d.]+ s; (?P<fix>.+)$"
REPO_PLUGIN = Path(__file__).resolve().parents[2]


def seen_beside(request_path):
    """The claim file beside a request file, named here so a test of the
    waiter or of cancel does not depend on `reviewlib.seen_path` existing."""
    path = Path(request_path)
    return path.with_name(path.name.replace(".request.json", ".seen"))


def shipped_version():
    package = json.loads((vs.EXTENSION_DIR / "package.json").read_text(encoding="utf-8"))
    return package["version"]


def just_below(version):
    """The largest version under `version` that differs in its last non-zero
    part: 0.2.0 gives 0.1.99, 0.2.5 gives 0.2.4."""
    parts = [int(p) for p in version.split(".")]
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] > 0:
            parts[i] -= 1
            parts[i + 1:] = [99] * (len(parts) - i - 1)
            return ".".join(str(p) for p in parts)
    raise AssertionError(f"nothing is below {version}")


def digits_greater_than_text(version):
    """A version numerically above `version` whose text sorts below it:
    0.2.0 gives 0.12.0."""
    major, minor, patch = (int(p) for p in version.split("."))
    return f"{major}.{10 + minor}.{patch}"


class Editors(vs.EditorFakes):
    """The VS Code fakes with a versioned extension list. `installed` holds
    `(id, version)` pairs the editor reports; a successful install adds the
    shipped extension at the shipped version. `rules` maps `(command, op)` or
    `(None, op)` to `{"exit", "stderr", "raises"}` for the operations `list`,
    `install` and `open`."""

    def setUp(self):
        super().setUp()
        self.installed = []
        self.rules = {}

    @staticmethod
    def op_of(argv):
        if "--list-extensions" in argv:
            return "list"
        if "--install-extension" in argv:
            return "install"
        return "open"

    def rule(self, argv):
        op = self.op_of(argv)
        return self.rules.get((vs._stem(argv), op)) or self.rules.get((None, op)) or {}

    def ops(self):
        return [self.op_of(list(a) if not isinstance(a, str) else [a]) for a, _ in self.launched]

    def _gate(self, args, kwargs):
        argv = list(args) if not isinstance(args, str) else [args]
        if vs._stem(argv) == "git":
            return
        raised = self.rule(argv).get("raises")
        if raised is not None:
            self.launched.append((args, kwargs))
            raise raised

    def _run(self, args, *rest, **kwargs):
        self._gate(args, kwargs)
        return super()._run(args, *rest, **kwargs)

    def _popen(self, args, *rest, **kwargs):
        self._gate(args, kwargs)
        return super()._popen(args, *rest, **kwargs)

    def _respond(self, argv):
        rule = self.rule(argv)
        code, err = rule.get("exit", 0), rule.get("stderr", "")
        op = self.op_of(argv)
        if op == "list":
            if code:
                return code, "", err
            lines = [f"{i}@{v}" if "--show-versions" in argv else i for i, v in self.installed]
            newline = "\r\n" if self.crlf else "\n"
            return 0, newline.join(lines) + (newline if lines else ""), err
        if op == "install" and code == 0:
            self.installed.append((vs.extension_id(), shipped_version()))
        return code, "", err


class ExtensionCheck(Editors):
    def configure_with(self, name, document):
        self.launched.clear()
        self.put_on_path(vs.COMMANDS[name])
        return vs.surface(name).configuration(document)

    def test_the_shipped_extension_is_installed_unless_the_editor_lists_it_at_that_version_or_later(self):
        """Adversarial where: a missing, older or longer-id extension is
        accepted as installed (so the request waits on an editor with no
        extension), a current one is reinstalled on every review, versions are
        compared as text (0.12.0 below 0.2.0), the id is compared
        case-sensitively, a Windows line ending sticks to the version, or the
        listing is read without `--show-versions`."""
        project, spec = self.make_project()
        eid, version = vs.extension_id(), shipped_version()
        rows = (
            ("not listed", [], False, True),
            ("only other extensions", [("ms-python.python", "2025.1.0")], False, True),
            ("listed one step below", [(eid, just_below(version))], False, True),
            ("listed far below", [(eid, "0.0.1")], False, True),
            ("longer id with the same start", [(eid + "-mockup", "99.0.0")], False, True),
            ("exactly the shipped version", [(eid, version)], False, False),
            ("newer", [(eid, "99.0.0")], False, False),
            ("digits above, text below", [(eid, digits_greater_than_text(version))], False, False),
            ("other case", [(eid.upper(), version)], False, False),
            ("Windows line endings", [(eid, version)], True, False),
        )
        with self.fakes():
            for name, command in vs.COMMANDS.items():
                for label, installed, crlf, installs in rows:
                    with self.subTest(surface=name, row=label):
                        self.installed, self.crlf = list(installed), crlf
                        context, reason = self.configure_with(name, spec)
                        self.assertIsNone(reason)
                        self.assertEqual(Path(context["root"]).resolve(), project.resolve())
                        self.assertEqual(self.ops(), ["list", "install"] if installs else ["list"])
                        listing = list(self.launched[0][0])
                        self.assertEqual(vs._stem(listing), command)
                        self.assertIn("--show-versions", listing)
                        if installs:
                            install = list(self.launched[1][0])
                            self.assertEqual(vs._stem(install), command)
                            vsix = Path(install[install.index("--install-extension") + 1])
                            self.assertTrue(vsix.is_file(), vsix)
                            self.assertIn(vs.VSCODE_DIR.resolve(), vsix.resolve().parents)

    def test_a_listing_or_install_that_fails_is_not_configured_with_a_reason_and_never_raises(self):
        """Adversarial where: a listing that exits non-zero, vanishes or hangs
        raises out of the review or is read as "extension missing" and
        followed by an install; an install that fails is reported as
        configured, so the request is written for an editor with no extension."""
        _, spec = self.make_project()
        rows = (
            ("listing exits 1", {"list": {"exit": 1, "stderr": "boom"}}, ["list"]),
            ("listing vanished", {"list": {"raises": FileNotFoundError("code")}}, ["list"]),
            ("listing hung", {"list": {"raises": subprocess.TimeoutExpired("code", 1)}}, ["list"]),
            ("install exits 1", {"install": {"exit": 1, "stderr": "boom"}}, ["list", "install"]),
            ("install vanished", {"install": {"raises": FileNotFoundError("code")}}, ["list", "install"]),
            ("install hung", {"install": {"raises": subprocess.TimeoutExpired("code", 1)}}, ["list", "install"]),
        )
        with self.fakes():
            for name in vs.COMMANDS:
                for label, rules, ops in rows:
                    with self.subTest(surface=name, row=label):
                        self.rules = {(None, op): rule for op, rule in rules.items()}
                        self.installed = []
                        context, reason = self.configure_with(name, spec)
                        self.assertIsNone(context)
                        self.assertIsInstance(reason, str)
                        self.assertTrue(reason.strip())
                        self.assertEqual(self.ops(), ops)
                        if "install" in rules:
                            self.assertIn("install", reason.lower())

    def test_a_variant_without_its_command_launches_nothing(self):
        """Adversarial where: the listing runs for an editor whose command is
        not on the PATH (the other editor's, or none), so a missing command
        raises or lists through the wrong program."""
        _, spec = self.make_project()
        with self.fakes():
            for name, command in vs.COMMANDS.items():
                other = next(c for c in vs.COMMANDS.values() if c != command)
                for present in ((), (other,)):
                    with self.subTest(surface=name, on_path=present):
                        self.launched.clear()
                        self.put_on_path(*present)
                        context, reason = vs.surface(name).configuration(spec)
                        self.assertIsNone(context)
                        self.assertIn(command, reason)
                        self.assertEqual(self.launched, [])


class ObsidianCheck(ReviewProject):
    def shipped(self):
        return obsidian_surface.shipped_plugin_dir()

    def seed(self, files, enabled):
        """Put `files` (name to bytes, None leaves the file out) in the
        plugin folder and write the community-plugins list."""
        self.configure(plugin="absent")
        folder = self.vault / ".obsidian" / "plugins" / obsidian_surface.PLUGIN_ID
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            if data is not None:
                (folder / name).write_bytes(data)
        if enabled is not None:
            (self.vault / ".obsidian" / "community-plugins.json").write_text(json.dumps(enabled), encoding="utf-8")
        return folder

    def shipped_bytes(self):
        return {n: (self.shipped() / n).read_bytes() for n in obsidian_surface.PLUGIN_FILES}

    def test_an_absent_off_or_stale_plugin_is_installed_and_the_vault_is_configured(self):
        """Adversarial where: a plugin that is absent, off, or differs from
        the shipped file in only one of main.js, manifest.json and styles.css
        (or lacks styles.css) is left as found, so the request waits on a
        plugin that is not loaded or runs an old one; the install drops
        another plugin from the list or lists this one twice."""
        shipped = self.shipped_bytes()
        pid = obsidian_surface.PLUGIN_ID
        stale = lambda name: {**shipped, name: b"// old " + name.encode()}  # noqa: E731
        rows = (
            ("absent, no list", {}, None),
            ("files current, not listed", shipped, ["other-plugin"]),
            ("off, main.js old", {"main.js": b"//"}, ["other-plugin"]),
            ("on, main.js old", stale("main.js"), ["other-plugin", pid]),
            ("on, manifest.json old", stale("manifest.json"), ["other-plugin", pid]),
            ("on, styles.css old", stale("styles.css"), ["other-plugin", pid]),
            ("on, styles.css missing", {**shipped, "styles.css": None}, ["other-plugin", pid]),
        )
        for label, files, enabled in rows:
            with self.subTest(row=label):
                shutil.rmtree(self.vault / ".obsidian", ignore_errors=True)
                folder = self.seed(files, enabled)
                context, reason = obsidian_surface.configuration(self.doc)
                self.assertIsNone(reason)
                self.assertEqual(context["vault_id"], "abc123")
                self.assertEqual(obsidian_surface.plugin_state(self.vault), "on")
                for name, data in shipped.items():
                    self.assertEqual((folder / name).read_bytes(), data, name)
                listed = json.loads((self.vault / ".obsidian" / "community-plugins.json").read_text(encoding="utf-8"))
                self.assertEqual(listed.count(pid), 1)
                if enabled and "other-plugin" in enabled:
                    self.assertIn("other-plugin", listed)

    def test_a_current_plugin_that_is_on_is_not_installed_again(self):
        """Adversarial where: every review reinstalls the plugin (rewriting
        files Obsidian has loaded) because the comparison with the shipped
        files is wrong."""
        shipped = self.shipped_bytes()
        folder = self.seed(shipped, ["other-plugin", obsidian_surface.PLUGIN_ID])
        before = {p.name: p.stat().st_mtime_ns for p in folder.iterdir()}
        with mock.patch.object(obsidian_surface, "install_plugin", side_effect=AssertionError("reinstalled")):
            context, reason = obsidian_surface.configuration(self.doc)
        self.assertIsNone(reason)
        self.assertIsNotNone(context)
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in folder.iterdir()}, before)

    def test_a_vault_obsidian_does_not_list_is_left_alone(self):
        """Adversarial where: the plugin is installed into a vault Obsidian
        has never opened, so the check writes into a folder the human did not
        set up."""
        self.configure(listed=False, plugin="absent")
        context, reason = obsidian_surface.configuration(self.doc)
        self.assertIsNone(context)
        self.assertIn("does not list", reason)
        self.assertFalse((self.vault / ".obsidian" / "plugins").exists())
        self.assertFalse((self.vault / ".obsidian" / "community-plugins.json").exists())

    def test_a_plugin_list_that_is_not_a_list_stays_untouched_and_the_vault_is_not_configured(self):
        """Adversarial where: an unparseable list, an object or a string that
        contains the plugin id as text is overwritten by the install, or is
        taken as listing the plugin so the vault reads as configured."""
        for label, text in (("object", '{"compass-review": true}'), ("string holding the id", '"compass-review"'),
                            ("unparseable", "{oops")):
            with self.subTest(row=label):
                shutil.rmtree(self.vault / ".obsidian", ignore_errors=True)
                self.seed({"main.js": b"//"}, None)
                listing = self.vault / ".obsidian" / "community-plugins.json"
                listing.write_text(text, encoding="utf-8")
                context, reason = obsidian_surface.configuration(self.doc)
                self.assertIsNone(context)
                self.assertTrue(reason)
                self.assertEqual(listing.read_text(encoding="utf-8"), text)

    def test_a_review_of_a_vault_with_the_plugin_off_installs_it_and_delivers(self):
        """Adversarial where: `compass review` still refuses with "plugin is
        off" (the install is only reachable through `--install`), or installs
        but writes no request."""
        self.configure(plugin="off")
        code, out, err = self.review(str(self.doc), "--no-wait")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("requested "), out)
        self.assertEqual(obsidian_surface.plugin_state(self.vault), "on")
        self.assertEqual(len(self.opened), 1)


class SeenFile(ReviewProject):
    def request_path(self, rid="20260101T000000-abcdef"):
        return reviewlib.review_dir(self.vault) / f"{rid}.request.json"

    def test_seen_path_swaps_only_the_suffix_of_the_request_file(self):
        """Adversarial where: the claim lands beside the wrong file: a folder
        named like a request file gets rewritten, the id is cut at its first
        dot, or the `.request.json` suffix is left on."""
        for given, expected in (
            ("/v/.compass/tmp/review/20260101T000000-abcdef.request.json", "/v/.compass/tmp/review/20260101T000000-abcdef.seen"),
            ("/x.request.json/tmp/review/1.request.json", "/x.request.json/tmp/review/1.seen"),
            ("/v/review/a.b.request.json", "/v/review/a.b.seen"),
        ):
            with self.subTest(given=given):
                self.assertEqual(Path(reviewlib.seen_path(given)).as_posix(), expected)

    def test_cancel_removes_the_claim_with_the_request_and_only_that_requests_claim(self):
        """Adversarial where: a withdrawn request leaves its `.seen` behind,
        a cancel removes every claim in the folder, or a request that was
        never claimed makes the cancel fail."""
        self.configure()
        doc2 = self.vault / "specs" / "SPEC-002-y.md"
        doc2.write_text("# Y\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "second")
        a = self.review(str(self.doc), "--no-wait")[1].split()[1]
        b = self.review(str(doc2), "--no-wait")[1].split()[1]
        directory = reviewlib.review_dir(self.vault)
        for rid in (a, b):
            seen_beside(directory / f"{rid}.request.json").write_text("", encoding="utf-8")
        self.assertEqual(self.review("--cancel", a)[0], 0)
        self.assertFalse(seen_beside(directory / f"{a}.request.json").exists())
        self.assertTrue(seen_beside(directory / f"{b}.request.json").exists())
        seen_beside(directory / f"{b}.request.json").unlink()
        self.assertEqual(self.review("--cancel", b)[0], 0, "a request with no claim cancels")
        self.assertEqual(sorted(p.name for p in directory.iterdir()), [])

    def test_a_claimed_request_is_still_pending(self):
        """Adversarial where: `.seen` counts as an answer, so the pending set
        the guard and `--status` read drops a request nobody answered."""
        self.configure()
        rid = self.review(str(self.doc), "--no-wait")[1].split()[1]
        seen_beside(self.request_path(rid)).write_text("", encoding="utf-8")
        self.assertEqual([r["id"] for r in reviewlib.pending(self.vault)], [rid])
        self.assertEqual(self.review("--status")[1].strip(), f"pending {rid} specs/SPEC-001-x.md")


class AckWait(ReviewProject):
    def setUp(self):
        super().setUp()
        self.module = importlib.import_module("commands.review")
        self.default_ack = getattr(self.module, "ACK_SECONDS", None)
        for name, value in (("ACK_SECONDS", ACK), ("POLL_SECONDS", POLL)):
            patcher = mock.patch.object(self.module, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.configure()

    def when_requested(self, delay, action):
        """Run `action(request_path, request)` `delay` seconds after the first
        request appears."""
        directory = reviewlib.review_dir(self.vault)

        def run():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                found = sorted(directory.glob("*.request.json")) if directory.is_dir() else []
                if found:
                    time.sleep(delay)
                    action(found[0], json.loads(found[0].read_text(encoding="utf-8")))
                    return
                time.sleep(0.02)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def claim(path, _request):
        seen_beside(path).write_text("", encoding="utf-8")

    @staticmethod
    def answer(path, request):
        reviewlib.verdict_path(path).write_text(json.dumps(
            {"id": request["id"], "file": request["file"], "verdict": "approved", "notes": "n", "at": "t"}),
            encoding="utf-8")

    def test_an_unclaimed_request_is_withdrawn_after_the_window_with_the_surface_and_the_fix(self):
        """Adversarial where: the waiter outlives the window when no add-on
        claimed the request (the bug), withdraws at once instead of after the
        window, leaves the request for the next review to find, prints
        `timeout` or `withdrawn` instead of the not-configured line, or the
        line names no fix; the window is not sixty seconds."""
        self.assertEqual(self.default_ack, 60)
        started = time.monotonic()
        code, out, err = self.review(str(self.doc), "--timeout", "10")
        elapsed = time.monotonic() - started
        self.assertEqual(code, 1, out + err)
        lines = out.splitlines()
        rid = lines[0].split()[1]
        found = re.match(LINE, lines[-1])
        self.assertIsNotNone(found, lines[-1])
        self.assertEqual(found["label"], "Obsidian")
        self.assertEqual(found["id"], rid)
        self.assertIn(obsidian_surface.ENABLE_STEPS, found["fix"])
        self.assertIn("reload", found["fix"].lower())
        self.assertFalse([ln for ln in lines if ln.startswith(("timeout ", "withdrawn "))], out)
        self.assertGreaterEqual(elapsed, ACK - 0.1)
        self.assertLess(elapsed, 5)
        directory = reviewlib.review_dir(self.vault)
        self.assertEqual(list(directory.glob("*.request.json")), [])
        self.assertEqual(list(directory.glob("*.seen")), [])

    def test_a_claim_inside_the_window_removes_the_limit(self):
        """Adversarial where: the window keeps running after the claim, so a
        human who takes longer than the window to answer finds the request
        withdrawn under them."""
        self.when_requested(0.2, self.claim)
        self.when_requested(ACK + 1.0, self.answer)
        code, out, err = self.review(str(self.doc), "--timeout", "10")
        self.assertEqual(code, 0, out + err)
        self.assertIn('"verdict": "approved"', out)
        self.assertNotIn("not configured", out)

    def test_an_answer_without_a_claim_is_accepted(self):
        """Adversarial where: an add-on that answers before it writes a claim
        (or never writes one) has its verdict discarded for lack of `.seen`."""
        self.when_requested(0.2, self.answer)
        code, out, err = self.review(str(self.doc), "--timeout", "10")
        self.assertEqual(code, 0, out + err)
        self.assertIn('"verdict": "approved"', out)

    def test_another_requests_claim_does_not_confirm_this_one(self):
        """Adversarial where: any `.seen` in the folder is taken as the
        claim (a stale file from an earlier review, or one from another
        editor's request), so an unclaimed request waits without limit."""
        directory = reviewlib.review_dir(self.vault)
        directory.mkdir(parents=True)
        (directory / "20000101T000000-aaaaaa.seen").write_text("", encoding="utf-8")
        code, out, _ = self.review(str(self.doc), "--timeout", "10")
        self.assertEqual(code, 1)
        self.assertRegex(out.splitlines()[-1], LINE)
        self.assertTrue((directory / "20000101T000000-aaaaaa.seen").exists(), "another request's claim is not ours to remove")

    def test_a_timeout_shorter_than_the_window_still_ends_the_wait_with_timeout(self):
        """Adversarial where: the window replaces `--timeout` instead of
        sitting inside it, so a one-second timeout waits for the whole window
        and ends with the wrong line."""
        with mock.patch.object(self.module, "ACK_SECONDS", 5.0, create=True):
            started = time.monotonic()
            code, out, _ = self.review(str(self.doc), "--timeout", "0.5")
        self.assertEqual(code, 1)
        self.assertLess(time.monotonic() - started, 3)
        self.assertTrue(out.splitlines()[-1].startswith("timeout "), out)
        self.assertNotIn("not configured", out)

    def test_a_withdrawal_inside_the_window_ends_with_withdrawn_not_the_not_configured_line(self):
        """Adversarial where: the unclaimed-request check runs before the
        withdrawal check, so a request cancelled during the window is reported
        as an editor that did not pick it up."""
        with mock.patch.object(self.module, "ACK_SECONDS", 3.0, create=True):
            self.when_requested(0.2, lambda path, request: self.review("--cancel", request["id"]))
            started = time.monotonic()
            code, out, _ = self.review(str(self.doc), "--timeout", "10")
        self.assertLess(time.monotonic() - started, 2.5, "the cancel ends the wait, not the window")
        self.assertEqual(code, 1)
        self.assertRegex(out.splitlines()[-1], r"^withdrawn ")
        self.assertNotIn("not configured", out)

    def test_no_wait_neither_waits_for_a_claim_nor_withdraws(self):
        """Adversarial where: `--no-wait` blocks for the window or withdraws
        the request it just delivered."""
        with mock.patch.object(self.module, "ACK_SECONDS", 30.0, create=True):
            started = time.monotonic()
            code, out, _ = self.review(str(self.doc), "--no-wait")
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("requested "), out)
        self.assertEqual(len(list(reviewlib.review_dir(self.vault).glob("*.request.json"))), 1)


class VsCodeFamilyWait(Editors):
    def setUp(self):
        super().setUp()
        self.project, self.spec = self.make_project()
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
            vs.REAL_RUN(["git", *args], cwd=self.project, check=True, capture_output=True)
        self.module = importlib.import_module("commands.review")
        for name, value in (("ACK_SECONDS", ACK), ("POLL_SECONDS", POLL)):
            patcher = mock.patch.object(self.module, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in vs.COMMANDS:
            patcher = mock.patch.object(vs.surface(name), "has_focus", lambda: False)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_review(self, surfaces, *args):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(review_surfaces, "SURFACES", surfaces), redirect_stdout(out), redirect_stderr(err):
            code = self.module.run([str(self.spec), *args])
        return code, out.getvalue(), err.getvalue()

    def requests(self):
        return sorted((self.project / ".compass" / "tmp" / "review").glob("*.request.json"))

    def test_an_editor_that_never_claims_the_request_is_named_in_the_withdrawal(self):
        """Adversarial where: the not-configured line names the wrong
        surface (Obsidian, or both editors under one label), or gives the
        Obsidian fix for an editor that needs its window reloaded."""
        for name, label in (("vscode", "VS Code"), ("cursor", "Cursor")):
            with self.subTest(surface=name), self.fakes():
                self.installed = [(vs.extension_id(), shipped_version())]
                self.launched.clear()
                self.put_on_path(vs.COMMANDS[name])
                code, out, err = self.run_review([vs.surface(name)], "--timeout", "10")
                self.assertEqual(code, 1, out + err)
                found = re.match(LINE, out.splitlines()[-1])
                self.assertIsNotNone(found, out)
                self.assertEqual(found["label"], label)
                self.assertIn("reload", found["fix"].lower())
                self.assertIn("Compass Review", found["fix"])
                self.assertNotIn(obsidian_surface.ENABLE_STEPS, found["fix"])
                self.assertEqual(self.requests(), [])
                self.assertEqual(vs.surface(name).unconfirmed_fix(), found["fix"])

    def test_a_surface_that_fails_its_check_falls_through_to_the_next_and_to_not_configured(self):
        """Adversarial where: a failed listing or install stops the choice
        instead of passing to the next surface, or, with no surface left,
        a request is written anyway and the editor opened on it."""
        with self.fakes():
            self.put_on_path("code", "cursor")
            self.installed = [(vs.extension_id(), shipped_version())]
            self.rules = {("code", "list"): {"exit": 1}}
            surfaces = [vs.surface("vscode"), vs.surface("cursor")]
            code, out, err = self.run_review(surfaces, "--no-wait")
            self.assertEqual(code, 0, out + err)
            request = json.loads(self.requests()[0].read_text(encoding="utf-8"))
            self.assertEqual(request["surface"], "cursor")
            shutil.rmtree(self.project / ".compass" / "tmp")
            self.launched.clear()
            self.rules = {(None, "list"): {"exit": 1}}
            code, out, err = self.run_review(surfaces, "--no-wait")
            self.assertEqual(code, 1, out + err)
            self.assertTrue(out.startswith("not configured:"), out)
            self.assertEqual(self.requests(), [])
            self.assertNotIn("open", self.ops())


class Contract(unittest.TestCase):
    def test_every_surface_names_one_line_to_fix_an_unconfirmed_delivery(self):
        """Adversarial where: a surface lacks `unconfirmed_fix()`, so the
        waiter cannot say what to do; it returns several lines, which breaks
        the one-line `not configured:` output; or Obsidian's omits the
        community-plugins steps."""
        importlib.import_module("review_surfaces.vscode")
        for surface in review_surfaces.SURFACES:
            with self.subTest(surface=surface.NAME):
                fix = surface.unconfirmed_fix()
                self.assertIsInstance(fix, str)
                self.assertTrue(fix.strip())
                self.assertNotIn("\n", fix.strip())
                self.assertIn("reload", fix.lower())
        self.assertIn(obsidian_surface.ENABLE_STEPS, obsidian_surface.unconfirmed_fix())

    def test_the_new_line_and_file_are_documented(self):
        """Adversarial where: the module docstrings that other agents read to
        learn the output of `compass review` and the surface functions omit
        the `.seen` file, the not-configured line or `unconfirmed_fix()`."""
        module = importlib.import_module("commands.review")
        self.assertIn(".seen", module.__doc__)
        self.assertIn("did not pick up", module.__doc__)
        self.assertIn("unconfirmed_fix", review_surfaces.__doc__)

    def test_versions_are_bumped_and_the_vsix_is_rebuilt_for_the_new_extension(self):
        """Adversarial where: a changed extension ships under the old version
        (so an editor holding 0.1.0 is never offered the update and the check
        compares equal), the Obsidian manifest or the plugin version is not
        bumped, or the `.vsix` is not rebuilt under the new version."""
        self.assertEqual(shipped_version(), "0.4.0")
        manifest = json.loads((REPO_PLUGIN / "obsidian" / "compass-review" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.7.0")
        plugin = json.loads((REPO_PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], "0.34.5")
        packed = [p.name for p in (REPO_PLUGIN / "vscode").rglob("*.vsix") if "node_modules" not in p.parts]
        self.assertEqual(packed, ["compass-review-0.4.0.vsix"])


if __name__ == "__main__":
    unittest.main()
