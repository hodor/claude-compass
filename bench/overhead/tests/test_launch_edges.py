"""Edge tests for launch.py found by reading its code: how stdout and
transcripts are split into lines, how a timeout ends a session, which
repositories the clean-plugin check accepts and how the sandbox environment
treats key case.

Adversarial themes: text splitting on Unicode line separators that JSON leaves
unescaped drops whole events; a killed session whose grandchild keeps the output
pipe open hangs the harness; git environment variables inherited from a hook
point the plugin check at another repository; a malformed reset time becomes a
sleep the scheduler cannot honour.
"""

import json
import math
import os
import sys
import time

import pytest

import launch
from conftest import CREDENTIAL_VARS, TESTS_DIR

PROBE = TESTS_DIR / "probe_claude.py"

SUCCESS = {"type": "result", "subtype": "success", "is_error": False, "result": "ok", "modelUsage": {}}
INIT = {"type": "system", "subtype": "init", "session_id": "s-1", "claude_code_version": "2.1.316"}


def lines(*events):
    """Stream-json text for `events`, non-ASCII left raw as Node writes it."""
    return "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)


def probe_run(tmp_path, repo, project, private_root, spec, *, prompt="go", **kwargs):
    spec_path = tmp_path / "probe-spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    parent_env = {**os.environ, "PROBE_SPEC": str(spec_path)}
    return launch.run_session(
        project, prompt, repo_root=repo, private_root=private_root,
        claude_cmd=[sys.executable, str(PROBE)], parent_env=parent_env, **kwargs,
    )


# U+2028, U+2029 and U+0085 are legal unescaped inside a JSON string and are
# line boundaries to str.splitlines().
SEPARATORS = {"line-separator": " ", "paragraph-separator": " ", "next-line": "\x85"}


@pytest.mark.parametrize("char", SEPARATORS.values(), ids=SEPARATORS.keys())
def test_events_whose_text_holds_a_unicode_line_separator_are_not_split_or_lost(
    char, tmp_path, repo, project, private_root
):
    """Adversarial where: splitting stdout with str.splitlines() cuts a JSON line
    at U+2028, U+2029 or U+0085 inside a model's text, both halves fail to parse,
    and the `result` event vanishes: a finished session is then classified
    `failed` and its tokens are never counted."""
    text = f"first{char}second"
    stream = lines(INIT, {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
                   {**SUCCESS, "result": text})

    result = probe_run(tmp_path, repo, project, private_root, {"stdout_text": stream})

    assert [event["type"] for event in result.events] == ["system", "assistant", "result"]
    assert result.status == launch.DONE


@pytest.mark.parametrize("char", SEPARATORS.values(), ids=SEPARATORS.keys())
def test_transcript_tail_with_a_unicode_line_separator_in_its_text_is_still_read_whole(
    char, tmp_path, repo, project, private_root
):
    """Adversarial where: the transcript tail is found by splitting the file into
    lines; a last entry whose message text holds U+2028, U+2029 or U+0085 is cut
    in two, the fragment is not JSON, and a real usage limit is reported `failed`."""
    entry = {"type": "assistant", "isApiErrorMessage": True, "message": {"content": f"limit{char}reached"}}
    spec = {"code": 1, "transcript": {"text": json.dumps(entry, ensure_ascii=False) + "\n"}}

    result = probe_run(tmp_path, repo, project, private_root, spec)

    assert result.status == launch.USAGE_LIMIT


ERROR_ENTRY = json.dumps({"type": "assistant", "isApiErrorMessage": True})
PLAIN_ENTRY = json.dumps({"type": "assistant", "isApiErrorMessage": False})

TAIL_CASES = [
    # name, stdout text, exit code, transcript text, transcript age, expected
    ("error-tail", "", 1, ERROR_ENTRY + "\n", 0, "usage-limit"),
    ("trailing-blank-lines", "", 1, ERROR_ENTRY + "\n\n  \n", 0, "usage-limit"),
    ("crlf-endings", "", 1, PLAIN_ENTRY + "\r\n" + ERROR_ENTRY + "\r\n", 0, "usage-limit"),
    ("whitespace-only-stdout", "\n \n", 1, ERROR_ENTRY + "\n", 0, "usage-limit"),
    ("error-entry-not-last", "", 1, ERROR_ENTRY + "\n" + PLAIN_ENTRY + "\n", 0, "failed"),
    ("tail-flag-is-a-string", "", 1, json.dumps({"isApiErrorMessage": "true"}) + "\n", 0, "failed"),
    ("tail-flag-is-one", "", 1, json.dumps({"isApiErrorMessage": 1}) + "\n", 0, "failed"),
    ("tail-is-a-list", "", 1, json.dumps([{"isApiErrorMessage": True}]) + "\n", 0, "failed"),
    ("tail-is-null", "", 1, "null\n", 0, "failed"),
    ("tail-cut-off", "", 1, ERROR_ENTRY[:-3] + "\n", 0, "failed"),
    ("empty-transcript", "", 1, "", 0, "failed"),
    ("stale-error-tail", "", 1, ERROR_ENTRY + "\n", 3600, "failed"),
    ("exit-zero", "", 0, ERROR_ENTRY + "\n", 0, "failed"),
    ("exit-two", "", 2, ERROR_ENTRY + "\n", 0, "failed"),
    ("stdout-holds-garbage", "not json\n", 1, ERROR_ENTRY + "\n", 0, "failed"),
]


@pytest.mark.parametrize("name,stdout,code,text,age,expected", TAIL_CASES, ids=[row[0] for row in TAIL_CASES])
def test_a_silent_exit_is_a_usage_limit_only_for_exit_one_with_an_error_tail_in_a_fresh_transcript(
    name, stdout, code, text, age, expected, tmp_path, repo, project, private_root
):
    """Adversarial where: the silent-limit rule has four conditions (exit exactly
    1, nothing on stdout, a transcript from this session, a last entry whose
    `isApiErrorMessage` is the boolean true); dropping or loosening any one turns
    a crash into a halt or a halt into a crash."""
    spec = {"stdout_text": stdout, "code": code, "transcript": {"text": text, "age": age}}

    result = probe_run(tmp_path, repo, project, private_root, spec)

    assert result.status == expected


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_rejected_limit_event_with_a_non_finite_reset_time_reports_none_not_the_number(
    token, tmp_path, repo, project, private_root
):
    """Adversarial where: Python's json accepts the bare tokens NaN and Infinity,
    so a malformed `resetsAt` arrives as a float that passes the numeric check
    and reaches the scheduler as a wait it can never reach."""
    raw = '{"type": "rate_limit_event", "status": "rejected", "resetsAt": %s}\n' % token

    result = probe_run(tmp_path, repo, project, private_root, {"stdout_text": raw, "code": 1})

    assert result.status == launch.USAGE_LIMIT
    assert result.resets_at is None or math.isfinite(result.resets_at)


def test_the_prompt_reaches_the_session_on_stdin_with_its_text_intact(tmp_path, repo, project, private_root):
    """Adversarial where: the prompt is sent as text; a large multi-line prompt
    with non-ASCII characters must arrive whole (no truncation at a pipe-buffer
    boundary, no encoding loss), apart from line-ending translation."""
    prompt = "".join(f"line {number}: café 世界 \U0001f9ed\n" for number in range(60000))
    received = tmp_path / "stdin.bin"

    probe_run(tmp_path, repo, project, private_root, {"stdin_out": str(received), "stdout_text": lines(INIT, SUCCESS)},
              prompt=prompt)

    assert received.read_bytes().replace(b"\r\n", b"\n") == prompt.encode("utf-8")


def test_a_timed_out_session_keeps_the_events_written_before_the_kill_and_is_failed(
    tmp_path, repo, project, private_root
):
    """Adversarial where: on a timeout the partial stdout (bytes on some
    platforms) must still be parsed; a complete success result already printed
    must not make the killed session `done`; the half-written last line must be
    dropped."""
    stream = lines(INIT, SUCCESS) + '{"type": "assist'

    result = probe_run(tmp_path, repo, project, private_root, {"stdout_text": stream, "sleep": 30}, timeout=2)

    assert result.status == launch.FAILED
    assert result.returncode == launch.TIMED_OUT
    assert [event["type"] for event in result.events] == ["system", "result"]


def test_a_timeout_returns_promptly_when_a_grandchild_keeps_the_output_pipe_open(
    tmp_path, repo, project, private_root
):
    """Adversarial where: killing only the direct child leaves a grandchild (the
    node process behind a `.cmd` shim) holding the stdout pipe, and reading the
    pipe to its end after the kill blocks until that grandchild exits, so the
    timeout does not bound the session."""
    spec = {"stdout_text": lines(INIT), "grandchild": 10, "sleep": 60}
    began = time.monotonic()

    result = probe_run(tmp_path, repo, project, private_root, spec, timeout=1)

    assert time.monotonic() - began < 6
    assert result.status == launch.FAILED
    assert result.returncode == launch.TIMED_OUT


def test_check_plugin_clean_answers_for_a_linked_worktree_and_refuses_what_is_not_a_repository_top(
    tmp_path, repo, git
):
    """Adversarial where: the repository is named by a folder, and only a checkout
    top qualifies: a linked worktree (its `.git` is a file) is a valid top, while
    a sub-folder, a missing folder, a plain folder, a bare repository and a
    repository with no commit must each be refused rather than answered for some
    other repository."""
    git(repo, "worktree", "add", "-q", str(tmp_path / "linked"), "-b", "side")
    plain = tmp_path / "plain"
    plain.mkdir()
    bare = tmp_path / "bare.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    git(unborn, "init", "-q")

    assert launch.check_plugin_clean(tmp_path / "linked") == git(tmp_path / "linked", "rev-parse", "HEAD")
    for name, folder in [("subfolder", repo / "plugin"), ("missing", tmp_path / "nowhere"), ("plain", plain),
                         ("bare", bare), ("unborn", unborn)]:
        try:
            launch.check_plugin_clean(folder)
        except launch.Refused:
            continue
        pytest.fail(f"{name} was accepted as a repository top")


def test_check_plugin_clean_ignores_git_environment_variables_inherited_from_a_hook(
    tmp_path, repo, git, monkeypatch
):
    """Adversarial where: run from a git hook, GIT_DIR and GIT_WORK_TREE point at
    the hooked repository; `git -C <repo>` still honours them, so the check
    answers about the wrong repository and records the wrong commit."""
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q")
    (other / "other.txt").write_text("other\n", encoding="utf-8")
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "other work")
    expected = git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))

    assert launch.check_plugin_clean(repo) == expected


def test_a_repository_with_no_plugin_folder_is_not_started_in_the_compass_arm(
    tmp_path, project, private_root, git
):
    """Adversarial where: `git status -- plugin` is empty when the folder does not
    exist, so a repository without `plugin/` passes as clean and the compass arm
    runs with `--plugin-dir` at nothing, measuring the baseline under the
    compass label."""
    bare_checkout = tmp_path / "no-plugin"
    bare_checkout.mkdir()
    git(bare_checkout, "init", "-q")
    (bare_checkout / "README.md").write_text("readme\n", encoding="utf-8")
    git(bare_checkout, "add", ".")
    git(bare_checkout, "commit", "-q", "-m", "initial")
    received = tmp_path / "stdin.bin"

    with pytest.raises(launch.Refused):
        probe_run(tmp_path, bare_checkout, project, private_root, {"stdin_out": str(received)}, plugin=True)

    assert not received.exists()


def test_session_environment_matches_credential_and_path_keys_whatever_their_case(private_root):
    """Adversarial where: Windows environments carry `Path` and tools set
    `Github_Token`; matching the exact upper-case names leaves a credential in
    the child or the editor folders on its PATH; the parent mapping must stay
    unchanged."""
    editor = os.sep.join(["", "opt", "Cursor", "bin"])
    keep = os.sep.join(["", "usr", "bin"])
    parent = {"Path": os.pathsep.join([editor, keep]), "keep_me": "1"}
    for name in CREDENTIAL_VARS:
        parent[name.title()] = "secret"
        parent[name.lower()] = "secret"
    snapshot = dict(parent)

    env = launch.session_environment(parent, private_root)

    assert parent == snapshot
    assert not [key for key in env if key.upper() in CREDENTIAL_VARS]
    assert env["Path"] == keep
    assert env["keep_me"] == "1"
