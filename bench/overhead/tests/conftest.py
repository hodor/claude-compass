"""Fixtures and the module contract for the bench/overhead tests.

No test touches the real home folder, the real `claude` binary or the network:
every test runs with HOME and USERPROFILE pointing into a temporary folder, and
every session runs through `fake_claude.py`.

Module contract the tests pin
-----------------------------
sandbox.py
    new_project(projects_root) -> Path       fresh folder under the root, its own `git init`
    list_projects(projects_root) -> [Path]   sorted project folders
    keep_project(project, to) -> Path        copy of the project at `to`
    discard_project(project, *, config_dir, claude_cmd)
                                             delete the folder, run `claude purge <path> --yes`
                                             with CLAUDE_CONFIG_DIR=config_dir
    main(argv) -> int                        verbs: `--projects-root DIR new`, `list`,
                                             `keep PROJECT --to DIR`
    Refused                                  raised when a CLAUDE.md sits above the projects root

launch.py
    session_environment(parent_env, private_root) -> dict
    run_session(project, prompt, *, repo_root, private_root=None, plugin=False,
                claude_cmd=None, parent_env=None) -> LaunchResult
        LaunchResult.status       "done" | "failed" | "usage-limit"
        LaunchResult.events       the JSON objects read from stdout, in order
        LaunchResult.returncode   the process exit code
        LaunchResult.resets_at    unix time from a rejected rate_limit_event, else None
    Refused                       raised when plugin/ has uncommitted changes (or git cannot say)
    private_root defaults to ~/.compass/overhead; the sandbox Claude config is
    <private_root>/claude-config.

records.py
    record_session(events, *, role, outcome, arm=None, plugin_sha=None, private_root=None) -> dict
        appends one JSON row to <private_root>/records/<machine id>.jsonl and returns it
        role     "build" | "human" | "topic" | "goal" | "judge"
        outcome  "done" | "failed" | "usage-limit"
        arm      None | "compass" | "baseline"
        row["models"][model_id] -> {"input", "output", "cache_read", "cache_write"}
        row["weighted"]         list-price weighted token total (float)
    Refused       raised when the records folder would sit inside a git work tree
    ValueError    raised for a role, outcome or arm outside the enums
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
OVERHEAD_DIR = TESTS_DIR.parent
REPO_ROOT = OVERHEAD_DIR.parents[1]

for _path in (REPO_ROOT / "plugin" / "cli", TESTS_DIR, OVERHEAD_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

FAKE_CLAUDE = TESTS_DIR / "fake_claude.py"

CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)


def run_git(cwd, *args):
    """Run git in `cwd` with a fixed identity; return stripped stdout."""
    command = [
        "git", "-c", "user.name=tester", "-c", "user.email=tester@example.invalid",
        "-c", "commit.gpgsign=false", *args,
    ]
    done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def inside_git_work_tree(path):
    done = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    return done.returncode == 0 and done.stdout.strip() == "true"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """HOME and USERPROFILE inside the test's temporary folder."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ("HOMEDRIVE", "HOMEPATH", "CLAUDE_CONFIG_DIR", "FAKE_CLAUDE_SCENARIO", "FAKE_CLAUDE_LOG"):
        monkeypatch.delenv(name, raising=False)
    if inside_git_work_tree(home):
        pytest.skip("the temporary folder is inside a git work tree")
    return home


@pytest.fixture
def private_root(isolated_home):
    return isolated_home / ".compass" / "overhead"


@pytest.fixture
def projects_root(tmp_path):
    for ancestor in (tmp_path, *tmp_path.parents):
        if (ancestor / "CLAUDE.md").exists():
            pytest.skip("a CLAUDE.md sits above the temporary folder")
    return tmp_path / "projects"


@pytest.fixture
def fake_cmd():
    return [sys.executable, str(FAKE_CLAUDE)]


@pytest.fixture
def git():
    return run_git


class FakeLog:
    def __init__(self, path):
        self.path = path

    def calls(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def use_scenario(tmp_path, monkeypatch):
    """Select the fake claude's scenario; return the log of its invocations."""
    log = FakeLog(tmp_path / "fake-claude-log.jsonl")

    def use(name):
        monkeypatch.setenv("FAKE_CLAUDE_SCENARIO", name)
        monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log.path))
        return log

    return use


@pytest.fixture
def repo(tmp_path, git):
    """A committed git repository with a plugin/ folder and a README.md."""
    root = tmp_path / "repo"
    (root / "plugin" / "skills" / "demo").mkdir(parents=True)
    (root / "plugin" / "skills" / "demo" / "SKILL.md").write_text("demo skill\n", encoding="utf-8")
    (root / "plugin" / "keep.txt").write_text("keep\n", encoding="utf-8")
    (root / "README.md").write_text("readme\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "initial")
    return root


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "work" / "proj-zq81xk"
    folder.mkdir(parents=True)
    return folder
