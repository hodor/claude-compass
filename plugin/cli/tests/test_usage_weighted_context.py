"""Tests for the usage-weighted context sensor: `compass loop usage-scan`
(counts which Compass sources real sessions load) and `compass loop
sense-context --usage DIR` (weights every shipped source by those counts).

Public contract these tests pin:

    usage-scan reads `*.jsonl` transcripts under `--projects` modified within
    `--days`, one file per session, and writes
    {"machine", "scanned_at", "days", "sessions", "loads"} to `--out`.
    `loads` keys are `skills/<name>/<rest>` and `templates/agents/<type>.md`;
    each counts the sessions that loaded it. The file holds no project name,
    path, session id or content. `--out` inside the current git work tree is
    refused with exit 1.

    sense-context adds, to the always-loaded text, every skill body, every
    other file in a skill folder and every agent body, each weighted by
    summed loads over summed sessions across the `*.json` files in `--usage`.

Scratch plugin trees and transcript trees live in temp dirs; HOME and
USERPROFILE point at a temp home so no default path reaches the real one.

Adversarial themes: transcript content leaking into the usage file, a string
prefix standing in for "inside the git tree", counting calls where sessions
are counted, rounding per source instead of at the end, averaging per-machine
ratios instead of summing loads and sessions, and a malformed input that
aborts the run instead of being skipped.
"""

import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

CLI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, CLI_DIR)

import maincli  # noqa: E402
import sensorlib  # noqa: E402
from commands import loop as loop_command  # noqa: E402

COMPASS = os.path.join(CLI_DIR, "compass")

PROJECT_PATH = "C:\\Users\\jdoe\\secretclient-acme\\app"
PROJECT_FOLDER = "C--Users-jdoe-secretclient-acme-app"
SESSION_ID = "9f3c1a77-5d2e-4b08-a1c4-7e60d2b9c3aa"
SECRET = "s" + "k-live-ZZtop99SECRETvalue"  # assembled at run time so the source holds no token shape
USER_TEXT = "please refactor the confidential payroll module"
LEAK_FRAGMENTS = ("secretclient", "acme", "jdoe", SESSION_ID, "9f3c1a77", SECRET,
                  "payroll", "confidential", "refactor")


def tool_use(name, **tool_input):
    return {"type": "tool_use", "id": "toolu_01", "name": name, "input": tool_input}


def assistant(*blocks):
    return {"type": "assistant", "sessionId": SESSION_ID, "cwd": PROJECT_PATH,
            "message": {"role": "assistant", "content": list(blocks)}}


def user_message(text):
    return {"type": "user", "sessionId": SESSION_ID, "cwd": PROJECT_PATH,
            "message": {"role": "user", "content": text}}


class Workspace(unittest.TestCase):
    """A temp home, a temp working directory outside any git tree, and a
    projects folder for fixture transcripts."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.tmp = tmp
        self.home = tmp / "home"
        self.home.mkdir()
        self.work = tmp / "work"
        self.work.mkdir()
        self.projects = tmp / "projects"
        self.projects.mkdir()
        self.out_dir = tmp / "out"
        self.out_dir.mkdir()
        # The plugin tree `usage-scan` keeps keys for: every source the scan
        # tests name exists in it.
        self.scan_plugin = tmp / "scan-plugin"
        for rel in ("skills/build/SKILL.md", "skills/build/ref.md", "skills/plan/SKILL.md",
                    "skills/plan/ref/a.md", "templates/agents/tester.md",
                    "templates/agents/builder.md", "templates/agents/validator.md"):
            (self.scan_plugin / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.scan_plugin / rel).write_text("x", encoding="utf-8")

    def run_cli(self, *args, cwd=None):
        cwd = Path(cwd or self.work)
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        env["CLAUDE_PROJECT_DIR"] = str(cwd)
        return subprocess.run(
            [sys.executable, COMPASS, "loop", *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
            cwd=str(cwd), timeout=120,
        )

    def write_session(self, folder, name, lines, age_days=0.0, raw=None):
        path = self.projects / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw is not None:
            path.write_bytes(raw)
        else:
            path.write_text("\n".join(json.dumps(line) for line in lines) + "\n",
                            encoding="utf-8")
        if age_days:
            stamp = time.time() - age_days * 86400
            os.utime(path, (stamp, stamp))
        return path

    def scan(self, *extra, projects=None, out=None):
        out = out or (self.out_dir / "usage.json")
        plugin = getattr(self, "plugin", self.scan_plugin)
        proc = self.run_cli("usage-scan", "--projects", str(projects or self.projects),
                            "--out", str(out), "--plugin", str(plugin), *extra)
        return proc, out

    def scan_ok(self, *extra, projects=None):
        proc, out = self.scan(*extra, projects=projects)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(Path(out).read_text(encoding="utf-8"))


class ScanKeyTests(Workspace):
    def test_each_call_shape_counts_to_its_source_key(self):
        """Adversarial where: a `compass:` prefix left on the skill name, a
        `Task` call ignored beside `Agent`, a Read path matched in only one
        slash direction, a path outside `/.claude/` counted, a key built from
        the whole path instead of the part after `/.claude/`, or a skill or
        agent counted once per call where it is counted once per session."""
        skill = "skills/build/SKILL.md"
        rows = {
            "skill with compass prefix": (
                [tool_use("Skill", skill="compass:build")], {skill: 1}),
            "skill without prefix": (
                [tool_use("Skill", skill="build")], {skill: 1}),
            "Agent by subagent_type": (
                [tool_use("Agent", subagent_type="tester", prompt="x")],
                {"templates/agents/tester.md": 1}),
            "Task by subagent_type": (
                [tool_use("Task", subagent_type="builder", prompt="x")],
                {"templates/agents/builder.md": 1}),
            "read of a skill file, forward slashes": (
                [tool_use("Read", file_path="/home/u/proj/.claude/skills/plan/ref/a.md")],
                {"skills/plan/ref/a.md": 1}),
            "read of a skill file, backslashes": (
                [tool_use("Read", file_path="C:\\Users\\u\\proj\\.claude\\skills\\plan\\ref\\a.md")],
                {"skills/plan/ref/a.md": 1}),
            "read of an agent file, forward slashes": (
                [tool_use("Read", file_path="/home/u/proj/.claude/agents/validator.md")],
                {"templates/agents/validator.md": 1}),
            "read of an agent file, backslashes": (
                [tool_use("Read", file_path="C:\\Users\\u\\proj\\.claude\\agents\\validator.md")],
                {"templates/agents/validator.md": 1}),
            "read of a skill under a path with no .claude folder": (
                [tool_use("Read", file_path="/home/u/repo/plugin/skills/plan/SKILL.md"),
                 tool_use("Bash", command="compass status")],
                {}),
            "same skill called twice in one session": (
                [tool_use("Skill", skill="build"), tool_use("Skill", skill="compass:build")],
                {skill: 1}),
        }
        for name, (blocks, expected) in rows.items():
            with self.subTest(name):
                shutil.rmtree(self.projects)
                self.projects.mkdir()
                self.write_session("p1", "s1.jsonl", [assistant(*blocks)])
                data = self.scan_ok()
                self.assertEqual(data["loads"], expected)
                self.assertEqual(data["sessions"], 1)

    def test_prefixed_and_bare_skill_calls_in_two_sessions_share_one_key(self):
        """Adversarial where: `compass:build` and `build` keyed separately,
        so the same skill is split into two sources each with half its real
        weight."""
        self.write_session("p1", "a.jsonl", [assistant(tool_use("Skill", skill="compass:build"))])
        self.write_session("p1", "b.jsonl", [assistant(tool_use("Skill", skill="build"))])
        data = self.scan_ok()
        self.assertEqual(data["loads"], {"skills/build/SKILL.md": 2})
        self.assertEqual(data["sessions"], 2)


class ScanSessionTests(Workspace):
    def test_only_sessions_with_a_compass_trace_count(self):
        """Adversarial where: every transcript counted as a session, which
        dilutes every weight with unrelated work; or a user message that
        merely mentions compass counted as a trace."""
        self.write_session("p1", "keyed.jsonl", [assistant(tool_use("Skill", skill="plan"))])
        self.write_session("p1", "shell.jsonl", [
            assistant(tool_use("Bash", command="compass loop status LOOP-003"))])
        self.write_session("p1", "plain1.jsonl", [
            user_message("hello"), assistant(tool_use("Bash", command="ls"))])
        self.write_session("p2", "plain2.jsonl", [
            user_message("tell me about compass headings"),
            assistant({"type": "text", "text": "ok"})])
        self.write_session("p2", "empty.jsonl", [])
        data = self.scan_ok()
        self.assertEqual(data["sessions"], 2)
        self.assertEqual(data["loads"], {"skills/plan/SKILL.md": 1})

    def test_every_project_folder_and_nested_subagent_transcript_is_read(self):
        """Adversarial where: only top-level `*.jsonl` of one project folder
        read, so subagent transcripts in nested folders and other projects
        never count; or a non-`.jsonl` file read as a session."""
        call = [assistant(tool_use("Skill", skill="build"))]
        self.write_session("p1", "s1.jsonl", call)
        self.write_session("p2", "s2.jsonl", call)
        self.write_session("p1", "sid-1/subagents/agent-a.jsonl", call)
        self.write_session("p1", "sid-1/subagents/deeper/agent-b.jsonl", call)
        (self.projects / "p1" / "notes.json").write_text(json.dumps(call[0]), encoding="utf-8")
        (self.projects / "p1" / "notes.txt").write_text(json.dumps(call[0]), encoding="utf-8")
        data = self.scan_ok()
        self.assertEqual(data["sessions"], 4)
        self.assertEqual(data["loads"], {"skills/build/SKILL.md": 4})

    def test_days_window_selects_transcripts_by_modification_time(self):
        """Adversarial where: the window ignored so old transcripts count, the
        default not 30 days, or the cutoff applied to the wrong side."""
        call = [assistant(tool_use("Skill", skill="build"))]
        self.write_session("p1", "new.jsonl", call, age_days=6.5)
        self.write_session("p1", "old.jsonl", call, age_days=7.5)
        data = self.scan_ok("--days", "7")
        self.assertEqual((data["sessions"], data["days"]), (1, 7))
        self.assertEqual(data["loads"], {"skills/build/SKILL.md": 1})

        self.write_session("p1", "month.jsonl", call, age_days=20)
        self.write_session("p1", "ancient.jsonl", call, age_days=40)
        data = self.scan_ok()
        self.assertEqual(data["days"], 30)
        self.assertEqual(data["sessions"], 3)

    def test_malformed_lines_are_skipped_counted_on_stderr_and_good_lines_kept(self):
        """Adversarial where: one undecodable line aborts the whole file, the
        run, or the exit code; the skip is silent; or the good lines around
        the bad ones are lost."""
        good = json.dumps(assistant(tool_use("Skill", skill="plan"))).encode("utf-8")
        raw = b"\n".join([b"not json at all", good, b"\xff\xfe\x00 broken bytes",
                          b'{"type": "assistant", "message": {', b"{truncated"]) + b"\n"
        self.write_session("p1", "mixed.jsonl", None, raw=raw)
        self.write_session("p1", "garbage.jsonl", None, raw=b"\xff\xfe\xfd\n\x00\x01\n")
        proc, out = self.scan()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(Path(out).read_text(encoding="utf-8"))
        self.assertEqual(data["sessions"], 1)
        self.assertEqual(data["loads"], {"skills/plan/SKILL.md": 1})
        self.assertIn("5", proc.stderr)

    def test_zero_matching_sessions_writes_an_empty_valid_file(self):
        """Adversarial where: an empty scan crashes, divides by zero, or
        writes nothing, so the sensor later reads a missing file as a
        failure."""
        self.write_session("p1", "plain.jsonl", [user_message("hi")])
        data = self.scan_ok()
        self.assertEqual((data["sessions"], data["loads"]), (0, {}))


class ScanOutputTests(Workspace):
    def test_file_schema_and_the_one_line_report(self):
        """Adversarial where: the machine id is not a 12 hex hash (or leaks
        the hostname), `scanned_at` is not ISO, the printed line differs from
        `scanned <sessions> sessions, <keys> sources, wrote <path>`, a stale
        file is not replaced, or a temp file is left beside the output."""
        self.write_session("p1", "a.jsonl", [assistant(
            tool_use("Skill", skill="plan"), tool_use("Agent", subagent_type="tester"))])
        out = self.out_dir / "usage.json"
        out.write_text("stale junk", encoding="utf-8")
        proc, _ = self.scan()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"machine", "scanned_at", "days", "sessions", "loads"})
        self.assertRegex(data["machine"], r"^[0-9a-f]{12}$")
        host = socket.gethostname()
        self.assertNotIn(host.lower(), out.read_text(encoding="utf-8").lower())
        from datetime import datetime
        datetime.fromisoformat(data["scanned_at"].replace("Z", "+00:00"))
        lines = proc.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        match = re.match(r"^scanned (\d+) sessions, (\d+) sources, wrote (.+)$", lines[0])
        self.assertIsNotNone(match, lines[0])
        self.assertEqual((int(match.group(1)), int(match.group(2))), (1, 2))
        self.assertTrue(os.path.samefile(match.group(3), out))
        self.assertEqual(sorted(p.name for p in self.out_dir.iterdir()), ["usage.json"])

    def test_defaults_read_and_write_under_the_home_folder(self):
        """Adversarial where: defaults resolve to a path other than
        `~/.claude/projects` and `~/.compass/usage/<machine>.json`, or the
        missing `~/.compass/usage/` folder is not created."""
        session = self.home / ".claude" / "projects" / "p1" / "s.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text(json.dumps(assistant(tool_use("Skill", skill="plan"))) + "\n",
                           encoding="utf-8")
        proc = self.run_cli("usage-scan")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        written = sorted((self.home / ".compass" / "usage").glob("*.json"))
        self.assertEqual(len(written), 1, proc.stdout)
        data = json.loads(written[0].read_text(encoding="utf-8"))
        self.assertEqual(written[0].stem, data["machine"])
        self.assertEqual(data["loads"], {"skills/plan/SKILL.md": 1})

    def test_usage_file_holds_only_source_names_and_counts(self):
        """Adversarial where: a project path, project folder name, session id,
        secret-looking string or user message from the transcript reaches the
        usage file, through a Read path, a Bash command, a Skill argument, a
        message body or the folder names; asserted on the raw bytes."""
        lines = [
            user_message(USER_TEXT),
            assistant({"type": "text", "text": f"working on {PROJECT_PATH} {USER_TEXT}"}),
            assistant(
                tool_use("Skill", skill="compass:build", args=f"{SECRET} {PROJECT_PATH}"),
                tool_use("Agent", subagent_type="tester", description=USER_TEXT,
                         prompt=f"{SECRET} in {PROJECT_PATH}"),
                tool_use("Read", file_path=PROJECT_PATH + "\\.claude\\skills\\build\\ref.md"),
                tool_use("Read", file_path=PROJECT_PATH.replace("\\", "/") + "/.claude/agents/builder.md"),
                tool_use("Read", file_path=PROJECT_PATH + "\\notes\\" + SESSION_ID + ".md"),
                tool_use("Bash", command=f"compass loop status && echo {SECRET}"),
            ),
        ]
        self.write_session(PROJECT_FOLDER, SESSION_ID + ".jsonl", lines)
        self.write_session(PROJECT_FOLDER, SESSION_ID + "/subagents/agent-1.jsonl", lines)
        proc, out = self.scan()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        raw = Path(out).read_bytes().decode("utf-8").lower()
        for fragment in LEAK_FRAGMENTS:
            with self.subTest(fragment):
                self.assertNotIn(fragment.lower(), raw)
        self.assertNotIn(SESSION_ID.lower(), proc.stdout.lower())
        data = json.loads(raw)
        self.assertEqual(data["sessions"], 2)
        self.assertEqual(data["loads"], {
            "skills/build/SKILL.md": 2,
            "templates/agents/tester.md": 2,
            "skills/build/ref.md": 2,
            "templates/agents/builder.md": 2,
        })
        for key in data["loads"]:
            self.assertTrue(key.startswith(("skills/", "templates/agents/")), key)


class ScanOutRefusalTests(Workspace):
    def git_init(self, path):
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)

    def test_out_inside_the_git_work_tree_is_refused_and_nothing_is_written(self):
        """Adversarial where: the repository guard missing, or fooled by a
        relative path, a `..` hop, a nested folder that does not exist yet, or
        the `.git` folder; or the refused run still creates the file or its
        parent folders."""
        repo = self.tmp / "repo"
        self.git_init(repo)
        (repo / "sub").mkdir()
        self.write_session("p1", "s.jsonl", [assistant(tool_use("Skill", skill="plan"))])
        rows = {
            "relative file at the root": (repo, "usage.json", repo / "usage.json"),
            "absolute file in a subfolder": (repo, str(repo / "sub" / "usage.json"),
                                             repo / "sub" / "usage.json"),
            "new nested folder": (repo, str(repo / "new" / "deep" / "usage.json"),
                                  repo / "new"),
            "dot-dot hop that stays inside": (repo / "sub", "../usage.json",
                                              repo / "usage.json"),
            "dot-dot hop through the tree": (repo, str(repo / "sub" / ".." / "usage.json"),
                                             repo / "usage.json"),
            "inside .git": (repo, str(repo / ".git" / "usage.json"),
                            repo / ".git" / "usage.json"),
        }
        for name, (cwd, out_arg, created) in rows.items():
            with self.subTest(name):
                proc = self.run_cli("usage-scan", "--projects", str(self.projects),
                                    "--out", out_arg, cwd=cwd)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertIn("outside the repository", proc.stderr)
                self.assertFalse(created.exists(), f"{created} was created")

    def test_out_beside_or_above_the_git_tree_is_allowed(self):
        """Adversarial where: the guard is a string-prefix test, so a sibling
        folder whose name starts with the repository's name (`repo-data`) is
        refused, or a `..` hop that leaves the tree is refused."""
        repo = self.tmp / "repo"
        self.git_init(repo)
        sibling = self.tmp / "repo-data"
        sibling.mkdir()
        self.write_session("p1", "s.jsonl", [assistant(tool_use("Skill", skill="plan"))])
        rows = {
            "sibling sharing the name prefix": (str(sibling / "usage.json"), sibling / "usage.json"),
            "dot-dot hop out of the tree": ("../outside.json", self.tmp / "outside.json"),
        }
        for name, (out_arg, expected) in rows.items():
            with self.subTest(name):
                proc = self.run_cli("usage-scan", "--projects", str(self.projects),
                                    "--out", out_arg, cwd=repo)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertTrue(expected.is_file())
                self.assertEqual(json.loads(expected.read_text(encoding="utf-8"))["sessions"], 1)


class SensorCase(Workspace):
    """A scratch plugin tree plus helpers for usage files."""

    def setUp(self):
        super().setUp()
        self.plugin = self.tmp / "plugin"
        (self.plugin / "templates" / "rules").mkdir(parents=True)
        (self.plugin / "templates" / "rules" / "r.md").write_bytes(b"r" * 40)
        self.usage = self.tmp / "usage"
        self.usage.mkdir()
        self.empty = self.tmp / "empty-usage"
        self.empty.mkdir()
        self.write_skill("alpha")
        self.write_agent("beta")

    def write_skill(self, name, body="skill body text\n"):
        path = self.plugin / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {name}\ndescription: {'a' * 40}\nwhen_to_use: {'b' * 40}\n---\n{body}",
            encoding="utf-8", newline="\n")
        return path

    def write_agent(self, name, body="agent body text\n"):
        path = self.plugin / "templates" / "agents" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {name}\ndescription: {'c' * 40}\nwhen_to_use: {'d' * 40}\n---\n{body}",
            encoding="utf-8", newline="\n")
        return path

    def write_skill_file(self, rel, data):
        path = self.plugin / "skills" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def usage_file(self, name, sessions, loads, directory=None):
        path = (directory or self.usage) / name
        path.write_text(json.dumps({
            "machine": "a" * 12, "scanned_at": "2026-01-01T00:00:00+00:00",
            "days": 30, "sessions": sessions, "loads": loads}), encoding="utf-8")
        return path

    def sense(self, usage=None, extra=()):
        args = ["sense-context", "--plugin", str(self.plugin)]
        if usage is not None:
            args += ["--usage", str(usage)]
        proc = self.run_cli(*args, *extra)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        reading = json.loads(proc.stdout)
        self.assertTrue(reading["valid"], reading)
        return reading

    def baseline(self):
        return self.sense(self.empty)

    @staticmethod
    def tokens(data):
        return math.ceil(len(data) / 4)


class StartupOnlyTests(SensorCase):
    def test_no_usable_usage_gives_the_startup_reading_marked_none(self):
        """Adversarial where: an absent folder, an empty folder or a file with
        zero sessions divides by zero, raises the value, or reports a usage
        block instead of `"none"`."""
        reference = sensorlib.sense_context(self.plugin)
        zero_dir = self.tmp / "zero"
        zero_dir.mkdir()
        self.usage_file("zero.json", 0, {"skills/alpha/SKILL.md": 5}, directory=zero_dir)
        rows = {
            "absent folder": self.tmp / "no-such-folder",
            "empty folder": self.empty,
            "zero-session file": zero_dir,
        }
        for name, folder in rows.items():
            with self.subTest(name):
                reading = self.sense(folder)
                self.assertEqual(reading["value"], reference.value)
                self.assertEqual(reading["items"], reference.items)
                self.assertEqual(reading["usage"], "none")

    def test_sense_context_function_defaults_to_no_weights(self):
        """Adversarial where: `usage_dir=None` falls back to the real
        `~/.compass/usage/`, so library callers and the checkpointed sensor
        tests read the machine's usage instead of startup text."""
        self.usage_file("m.json", 4, {"skills/alpha/SKILL.md": 4})
        plain = sensorlib.sense_context(self.plugin)
        explicit_none = sensorlib.sense_context(self.plugin, usage_dir=None)
        weighted = sensorlib.sense_context(self.plugin, usage_dir=self.usage)
        self.assertEqual(plain.value, explicit_none.value)
        self.assertEqual(plain.items, explicit_none.items)
        self.assertEqual(weighted.value, plain.value + self.tokens(
            (self.plugin / "skills" / "alpha" / "SKILL.md").read_bytes()))

    def test_cli_default_usage_folder_is_under_the_home_folder(self):
        """Adversarial where: the CLI omits the `~/.compass/usage/` default
        and reads startup text only, or reads a different folder."""
        home_usage = self.home / ".compass" / "usage"
        home_usage.mkdir(parents=True)
        self.usage_file("m.json", 2, {"skills/alpha/SKILL.md": 2}, directory=home_usage)
        reading = self.sense()
        self.assertEqual(reading["usage"], {"machines": 1, "sessions": 2})
        self.assertGreater(reading["value"], self.baseline()["value"])


class WeightTests(SensorCase):
    def test_a_source_loaded_in_every_session_adds_its_whole_file_tokens(self):
        """Adversarial where: only a frontmatter slice or the body without its
        frontmatter counted; characters counted for bytes (the multi-byte row);
        a nested file under a skill folder skipped; agent bodies skipped; the
        round-up of bytes/4 per source lost."""
        self.write_skill_file("alpha/ref/deep/chain/note.md", "é" * 10)
        self.write_skill_file("alpha/ref/odd.txt", "x" * 13)
        rows = {
            "skill body": (self.plugin / "skills/alpha/SKILL.md", "skills/alpha/SKILL.md"),
            "agent body": (self.plugin / "templates/agents/beta.md", "templates/agents/beta.md"),
            "deep multi-byte file": (self.plugin / "skills/alpha/ref/deep/chain/note.md",
                                     "skills/alpha/ref/deep/chain/note.md"),
            "thirteen byte file": (self.plugin / "skills/alpha/ref/odd.txt",
                                   "skills/alpha/ref/odd.txt"),
        }
        base = self.baseline()["value"]
        for name, (path, key) in rows.items():
            with self.subTest(name):
                for old in self.usage.glob("*.json"):
                    old.unlink()
                self.usage_file("m.json", 5, {key: 5})
                reading = self.sense(self.usage)
                self.assertEqual(reading["value"], base + self.tokens(path.read_bytes()))
                self.assertIsInstance(reading["value"], int)
        self.assertEqual(self.tokens("é".encode("utf-8") * 10), 5)

    def test_loads_and_sessions_sum_across_machines_before_dividing(self):
        """Adversarial where: per-machine ratios are averaged (0.5 here
        instead of 0.25), or a machine that never loaded the source is left
        out of the sessions total."""
        self.write_skill_file("alpha/ref.md", b"x" * 400)
        key = "skills/alpha/ref.md"
        base = self.baseline()["value"]
        self.usage_file("one.json", 2, {key: 2})
        self.usage_file("two.json", 6, {})
        reading = self.sense(self.usage)
        self.assertEqual(reading["value"], base + 25)
        self.assertEqual(reading["usage"], {"machines": 2, "sessions": 8})

    def test_total_is_rounded_once_at_the_end(self):
        """Adversarial where: each weighted source is rounded (or ceiled)
        before summing: two one-token files at weight 1/3 total 0.67 and
        round to 1, where per-source rounding gives 0 and per-source ceiling
        gives 2; at weight 2/3 the total 1.33 rounds to 1 where per-source
        rounding gives 2."""
        self.write_skill_file("alpha/a.md", b"aaaa")
        self.write_skill_file("alpha/b.md", b"bbbb")
        base = self.baseline()["value"]
        for loads, sessions, expected in [(1, 3, 1), (2, 3, 1)]:
            with self.subTest(loads=loads, sessions=sessions):
                for old in self.usage.glob("*.json"):
                    old.unlink()
                self.usage_file("m.json", sessions, {
                    "skills/alpha/a.md": loads, "skills/alpha/b.md": loads})
                self.assertEqual(self.sense(self.usage)["value"], base + expected)

    def test_unknown_keys_binary_files_and_zero_weights_add_nothing(self):
        """Adversarial where: a usage key naming no source under the plugin
        raises or adds tokens, a binary file in a skill folder is counted as
        text or crashes the read, or a weight-0 source is listed as an item
        (which would make every unused file look like churn)."""
        self.write_skill_file("alpha/img.png", b"\x89PNG\r\n\x1a\n\x00\xff\xfe" * 50)
        self.write_skill_file("alpha/unused.md", b"u" * 400)
        base = self.baseline()
        self.usage_file("m.json", 4, {
            "skills/ghost/SKILL.md": 4,
            "templates/agents/nobody.md": 4,
            "skills/alpha/img.png": 4,
        })
        reading = self.sense(self.usage)
        self.assertEqual(reading["value"], base["value"])
        self.assertEqual(reading["items"], base["items"])
        self.assertNotIn("skills/alpha/unused.md", reading["items"])
        self.assertNotIn("skills/ghost/SKILL.md", reading["items"])

    def test_items_list_a_weighted_source_once_with_forward_slashes(self):
        """Adversarial where: a weighted file is not an item, a skill body
        that already has its frontmatter item appears twice (the judge counts
        items as a multiset, so the second copy reads as a new item), or the
        path is built with the platform separator."""
        self.write_skill_file("alpha/ref/deep.md", b"d" * 40)
        self.usage_file("m.json", 4, {
            "skills/alpha/ref/deep.md": 2, "skills/alpha/SKILL.md": 4,
            "templates/agents/beta.md": 1})
        items = self.sense(self.usage)["items"]
        self.assertEqual(items.count("skills/alpha/ref/deep.md"), 1)
        self.assertEqual(items.count("skills/alpha/SKILL.md"), 1)
        self.assertEqual(items.count("templates/agents/beta.md"), 1)
        self.assertEqual(items.count("templates/rules/r.md"), 1)
        self.assertFalse([item for item in items if "\\" in item], items)


class BadUsageFileTests(SensorCase):
    def test_a_file_that_does_not_parse_is_skipped_named_and_the_rest_used(self):
        """Adversarial where: one corrupt usage file aborts the reading or
        voids the valid files beside it, is skipped silently, or is still
        counted in `machines`."""
        self.write_skill_file("alpha/ref.md", b"x" * 400)
        base = self.baseline()["value"]
        self.usage_file("good.json", 4, {"skills/alpha/ref.md": 4})
        (self.usage / "broken-garbage.json").write_bytes(b"\xff\xfe not json {{{")
        (self.usage / "broken-truncated.json").write_text('{"sessions": 3, "loads": {',
                                                          encoding="utf-8")
        reading = self.sense(self.usage)
        self.assertEqual(reading["value"], base + 100)
        self.assertEqual(reading["usage"], {"machines": 1, "sessions": 4})
        skipped = " ".join(reading["skipped"])
        self.assertIn("broken-garbage.json", skipped)
        self.assertIn("broken-truncated.json", skipped)
        self.assertNotIn("good.json", skipped)

    def test_only_garbage_files_give_the_startup_reading_and_name_them(self):
        """Adversarial where: when no file parses the sensor errors out or
        reports a usage block of zero machines instead of `"none"`."""
        (self.usage / "broken.json").write_text("{{{", encoding="utf-8")
        reading = self.sense(self.usage)
        self.assertEqual(reading["usage"], "none")
        self.assertEqual(reading["value"], self.baseline()["value"])
        self.assertIn("broken.json", " ".join(reading["skipped"]))


class ScanFeedsSensorTests(SensorCase):
    def test_scanned_file_weights_the_sensor_end_to_end(self):
        """Adversarial where: the scan's keys and the sensor's source paths
        disagree, so a real scan never weights any source: two of four
        sessions load a skill file, one a skill and one an agent."""
        self.write_skill_file("alpha/ref.md", b"x" * 400)
        usage_dir = self.tmp / "scanned"
        usage_dir.mkdir()
        self.write_session("p1", "a.jsonl", [assistant(
            tool_use("Read", file_path="C:\\w\\.claude\\skills\\alpha\\ref.md"))])
        self.write_session("p1", "b.jsonl", [assistant(
            tool_use("Read", file_path="/w/.claude/skills/alpha/ref.md"))])
        self.write_session("p1", "c.jsonl", [assistant(tool_use("Skill", skill="compass:alpha"))])
        self.write_session("p1", "d.jsonl", [assistant(tool_use("Bash", command="compass status"))])
        proc, out = self.scan(out=usage_dir / "m.json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        base = self.baseline()["value"]
        reading = self.sense(usage_dir)
        skill_tokens = self.tokens((self.plugin / "skills/alpha/SKILL.md").read_bytes())
        expected = base + 100 * 2 / 4 + skill_tokens * 1 / 4
        self.assertEqual(reading["value"], round(expected))
        self.assertEqual(reading["usage"], {"machines": 1, "sessions": 4})


class RegistrationTests(unittest.TestCase):
    def test_help_line_and_usage_text_name_usage_scan_beside_the_existing_modes(self):
        """Adversarial where: `usage-scan` missing from the `loop` help line
        or from the USAGE text, or added by replacing `sense-context`."""
        line = dict(maincli.COMMAND_SPECS)["loop"]
        for text in (line, loop_command.USAGE):
            for mode in ("usage-scan", "sense-context"):
                with self.subTest(mode=mode, where=text[:20]):
                    self.assertIn(mode, text)
        self.assertIn("--usage", loop_command.USAGE)


if __name__ == "__main__":
    unittest.main()
