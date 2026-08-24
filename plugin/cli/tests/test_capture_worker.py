"""Tests for `compass capture-worker <opp-id>` (`commands/capture_worker.py`)
and the capturelib/modelslib/capture_stats surface it depends on: the two
new config keys, the three flat state fields, the public `log_event`/
`read_log` pair, the `capture-worker` model roster row, and the ledger
vocabulary `capture_stats.KNOWN_EVENTS` gains.

Adversarial where the task's own binding vocabulary is easy to get subtly
wrong: the wrapper must write only END rows (never `worker-started`, which
belongs to the caller); the auth-shaped no-headless classifier is a
two-axis boundary (fast AND auth-token, not either alone); the worker's own
lock is owner-checked on release, not just staleness-checked; and the
child's environment must be inherited-plus, never replaced, since
`CLAUDE_PROJECT_DIR` and auth surviving is what keeps the child's own hooks
from breaking when TASK-092 later gates them on `COMPASS_WORKER_SESSION`.

`commands/capture_worker.py` does not exist yet. The import is guarded so
collection succeeds; every test that needs it fails on invocation
(`AttributeError` on `None`) rather than at collection time, so the red run
can be read per test per [[LESSON-revert-to-prove-a-regression-test]].

The worker lock's on-disk shape (`tmp/capture-worker.lock` holding pid and
ISO start) is not given a literal byte format by the plan. These tests
assume a JSON object `{"pid": <int>, "started_at": <iso>}`, the only shape
consistent with every other file this module writes (config, state, log
rows, opportunity records are all JSON) - flagged in the test report as an
inferred format, not a pinned one.
"""

import datetime
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capturelib  # noqa: E402
import modelslib  # noqa: E402
from commands import capture_stats  # noqa: E402

try:
    from commands import capture_worker
except ImportError:
    capture_worker = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_vault(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    root = tmp / ".compass"
    root.mkdir(parents=True)
    return root


def with_vault_env(test_case, project_root):
    old = os.environ.get("CLAUDE_PROJECT_DIR")
    os.environ["CLAUDE_PROJECT_DIR"] = str(project_root)

    def restore():
        if old is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = old

    test_case.addCleanup(restore)


def with_env(test_case, key, value):
    old = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value

    def restore():
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old

    test_case.addCleanup(restore)


def open_test_opportunity(root, kind="interval"):
    directory = capturelib.open_opportunity(root, kind, ["interval"], [])
    return directory.name, directory


def read_log_rows(vault_root):
    path = vault_root / "tmp" / "capture-log.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_capture_config(root, **overrides):
    config = dict(capturelib.DEFAULT_CONFIG)
    config.update(capture_worker_defaults())
    config.update(overrides)
    path = root / "meta" / "capture.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config), encoding="utf-8")
    return config


def capture_worker_defaults():
    # Mirrors the two new keys the plan requires in DEFAULT_CONFIG; kept
    # local rather than read from capturelib.DEFAULT_CONFIG so a fixture
    # write still produces a complete file before the keys exist there.
    return {"worker_grace_seconds": 600, "no_headless_retry_seconds": 86400}


LOCK_PATH_PARTS = ("tmp", "capture-worker.lock")


def lock_path(vault_root):
    return vault_root.joinpath(*LOCK_PATH_PARTS)


def write_lock(vault_root, pid, started_at, age_seconds=0):
    """Write an assumed-JSON worker lock and backdate its mtime by
    `age_seconds` so staleness is testable without sleeping."""
    path = lock_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "started_at": started_at}), encoding="utf-8")
    if age_seconds:
        past = capturelib._now() - datetime.timedelta(seconds=age_seconds)
        ts = past.timestamp()
        os.utime(path, (ts, ts))


STUB_BODY = textwrap.dedent(
    """
    import json
    import os
    import sys
    import threading
    import time

    def _watchdog():
        time.sleep(20)
        os._exit(9)

    threading.Thread(target=_watchdog, daemon=True).start()

    stdin_data = sys.stdin.read()

    sleep_for = os.environ.get("STUB_SLEEP")
    if sleep_for:
        time.sleep(float(sleep_for))

    close_path = os.environ.get("STUB_CLOSE_OPP_PATH")
    if close_path and os.path.isfile(close_path):
        with open(close_path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        record["outcome"] = os.environ.get("STUB_CLOSE_OUTCOME", "fired")
        record["closed_at"] = "2026-08-24T00:00:00Z"
        with open(close_path, "w", encoding="utf-8") as fh:
            json.dump(record, fh)

    tamper_path = os.environ.get("STUB_TAMPER_LOCK_PATH")
    if tamper_path:
        with open(tamper_path, "w", encoding="utf-8") as fh:
            json.dump({"pid": 999999, "started_at": "2020-01-01T00:00:00Z"}, fh)

    marker = os.environ.get("STUB_MARKER")
    if marker:
        with open(marker, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "argv": sys.argv[1:],
                    "cwd": os.getcwd(),
                    "env": dict(os.environ),
                    "stdin": stdin_data,
                },
                fh,
            )

    stdout_text = os.environ.get("STUB_STDOUT", "")
    stderr_text = os.environ.get("STUB_STDERR", "")
    if stdout_text:
        sys.stdout.write(stdout_text)
    if stderr_text:
        sys.stderr.write(stderr_text)

    sys.exit(int(os.environ.get("STUB_EXIT_CODE", "0")))
    """
)


def make_stub(test_case):
    """Write a stub binary `COMPASS_CLAUDE_BIN` can point at: a `.bat`
    launcher (directly runnable by `Popen` on Windows given an absolute
    path, verified empirically - a bare relative filename is not found by
    `CreateProcess`) plus the Python body it invokes. Behavior is entirely
    env-var driven so one stub serves every scenario below."""
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    body = tmp / "stub_body.py"
    body.write_text(STUB_BODY, encoding="utf-8")
    launcher = tmp / "stub.bat"
    launcher.write_text(
        '@echo off\r\n"' + sys.executable + '" "' + str(body) + '" %*\r\n',
        encoding="utf-8",
    )
    return launcher


def read_marker(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class WorkerHarness(unittest.TestCase):
    """Common setup: a vault, a fresh opportunity, a stub binary, and the
    env plumbing (`CLAUDE_PROJECT_DIR`, `COMPASS_CLAUDE_BIN`) every
    `capture_worker.run` call needs."""

    def setUp(self):
        # capture_worker may be None (module not built yet); tests still
        # run and fail on invocation rather than at collection time.
        self.root = make_vault(self)
        with_vault_env(self, self.root.parent)
        write_capture_config(self.root)
        self.opp_id, self.opp_dir = open_test_opportunity(self.root)
        self.stub = make_stub(self)
        with_env(self, "COMPASS_CLAUDE_BIN", str(self.stub))
        self.marker_path = self.opp_dir.parent / f"{self.opp_id}-marker.json"
        with_env(self, "STUB_MARKER", str(self.marker_path))
        with_env(self, "STUB_EXIT_CODE", "0")
        with_env(self, "STUB_SLEEP", None)
        with_env(self, "STUB_STDOUT", None)
        with_env(self, "STUB_STDERR", None)
        with_env(self, "STUB_CLOSE_OPP_PATH", None)
        with_env(self, "STUB_TAMPER_LOCK_PATH", None)

    def close_via_stub(self, outcome="fired"):
        with_env(self, "STUB_CLOSE_OPP_PATH", str(self.opp_dir / "opportunity.json"))
        with_env(self, "STUB_CLOSE_OUTCOME", outcome)

    def run_worker(self, opp_id=None):
        return capture_worker.run([opp_id if opp_id is not None else self.opp_id])


# ---------------------------------------------------------------------------
# capturelib: config keys, state fields, log_event/read_log
# ---------------------------------------------------------------------------


class CapturelibDefaultsTests(unittest.TestCase):
    """Adversarial where: the plan requires these additions to land in
    DEFAULT_CONFIG/DEFAULT_STATE (not just be used ad hoc somewhere), since
    test_capturelib.py's state-equality pins compare against
    `capturelib.DEFAULT_STATE` itself and would silently stop pinning
    anything if the fields lived elsewhere."""

    def test_default_config_gains_worker_grace_and_no_headless_retry_keys(self):
        # Through load_config, not the raw constant: this is what a fresh
        # vault actually materializes to disk, the real observable surface.
        root = make_vault(self)
        config = capturelib.load_config(root)
        self.assertEqual(config.get("worker_grace_seconds"), 600)
        self.assertEqual(config.get("no_headless_retry_seconds"), 86400)

    def test_default_state_gains_worker_flat_fields_with_correct_defaults(self):
        root = make_vault(self)
        state = capturelib.load_state(root)
        self.assertEqual(state.get("worker_attempts"), 0)
        self.assertIsNone(state.get("worker_quiet_at"))
        self.assertIsNone(state.get("no_headless_at"))
        # Flat, not nested - a dict value here would defeat the documented
        # reason these fields exist outside `_default_state`'s deep-copy.
        for key in ("worker_attempts", "worker_quiet_at", "no_headless_at"):
            self.assertNotIsInstance(state.get(key), dict)


class LogEventReadLogTests(unittest.TestCase):
    """Adversarial where: `log_event`/`read_log` are new public surface: a
    round trip that only exercises the four pre-existing kinds would pass
    even if the five new worker kinds were never wired into whatever
    filter `read_log` applies."""

    def test_log_event_and_read_log_round_trip_all_five_new_kinds(self):
        root = make_vault(self)
        kinds = [
            "worker-started",
            "worker-spawn-error",
            "worker-finished",
            "worker-failed",
            "fallback-fired",
        ]
        for kind in kinds:
            capturelib.log_event(root, kind, id="OPP-x", marker=kind)
        rows = capturelib.read_log(root)
        seen = [row["event"] for row in rows if row.get("marker") in kinds]
        self.assertEqual(seen, kinds)

    def test_capture_stats_known_events_gains_five_worker_kinds(self):
        # Through load_rows, not the raw frozenset: a kind absent from
        # KNOWN_EVENTS is silently dropped by the parser, which is the
        # actual failure mode this guards against.
        root = make_vault(self)
        log_path = root / "tmp" / "capture-log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        kinds = [
            "worker-started",
            "worker-spawn-error",
            "worker-finished",
            "worker-failed",
            "fallback-fired",
        ]
        with open(log_path, "w", encoding="utf-8") as fh:
            for kind in kinds:
                fh.write(json.dumps({"at": "2026-08-24T00:00:00Z", "event": kind}) + "\n")
        rows = capture_stats.load_rows(root)
        self.assertEqual([row["event"] for row in rows], kinds)


# ---------------------------------------------------------------------------
# modelslib: the capture-worker roster row
# ---------------------------------------------------------------------------


class ModelRosterTests(unittest.TestCase):
    """Adversarial where: `capture-worker` is a non-agent CLI job like
    `index-summary` - it must resolve a real tier AND be excluded from
    `AGENT_FILES` (which rewrites agent-definition frontmatter); landing it
    in the roster without the exclusion would make `apply-models` try to
    rewrite a `capture-worker.md` that never existed."""

    def test_capture_worker_roster_row_resolves_cheap_excluded_from_agent_files(self):
        # Through resolve(), not the raw DEFAULT_ROSTER dict: the same
        # precedent row as index-summary (test_modelslib.py:63), no project
        # override, no env override, default host.
        self.assertEqual(
            modelslib.resolve("capture-worker"), ("haiku", "low", "built-in")
        )
        # A distinct fact resolve() cannot show: apply-models rewrites every
        # name in AGENT_FILES as an agent-definition file, so a roster row
        # for a headless job with no agent file must be excluded from it.
        self.assertNotIn("capture-worker.md", modelslib.AGENT_FILES)


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------


class ArgHandlingTests(WorkerHarness):
    def test_missing_opp_id_exits_1_no_rows(self):
        code = capture_worker.run([])
        self.assertEqual(code, 1)
        self.assertEqual(read_log_rows(self.root), [])
        self.assertFalse(self.marker_path.exists())

    def test_opp_id_shaped_but_no_matching_directory_exits_1_no_rows(self):
        # Asymmetric malformation: the id is well-formed (matches the
        # OPP-<timestamp>Z shape a real caller would produce) but nothing
        # on disk backs it - a different failure surface than a garbage
        # string, and one a shape-only validator would miss.
        code = capture_worker.run(["OPP-20260101T000000000000Z"])
        self.assertEqual(code, 1)
        self.assertEqual(read_log_rows(self.root), [])
        self.assertFalse(self.marker_path.exists())

    def test_malformed_opp_id_string_exits_1_no_rows(self):
        code = capture_worker.run(["../../not/an/opportunity;$(rm)"])
        self.assertEqual(code, 1)
        self.assertEqual(read_log_rows(self.root), [])

    def test_never_returns_exit_code_2_on_any_malformed_invocation(self):
        for bad_args in ([], ["nonexistent-id"], ["../evil"], ["OPP-x", "extra-arg"]):
            code = capture_worker.run(bad_args)
            self.assertNotEqual(code, 2, f"args={bad_args!r} returned exit 2")
            # Every one of these shapes is a refusal, not a partial attempt -
            # none of them may leave a trace row behind either.
            self.assertEqual(read_log_rows(self.root), [], f"args={bad_args!r} wrote a row")


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class SuccessPathTests(WorkerHarness):
    def test_success_writes_only_finished_row_never_a_started_row(self):
        with_env(self, "STUB_STDOUT", "extracted: 2 written, 0 revised, 1 rejected - ok\n")
        self.close_via_stub()

        code = self.run_worker()
        self.assertEqual(code, 0)

        rows = read_log_rows(self.root)
        events = [row["event"] for row in rows]
        self.assertIn("worker-finished", events)
        self.assertNotIn(
            "worker-started", events,
            "worker-started belongs to the caller (capture-check), not the wrapper",
        )

    def test_finished_row_carries_the_extracted_line(self):
        line = "extracted: 2 written, 0 revised, 1 rejected - looks solid"
        with_env(self, "STUB_STDOUT", line + "\n")
        self.close_via_stub()

        self.run_worker()
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-finished"]
        self.assertEqual(len(rows), 1)
        self.assertIn(line, json.dumps(rows[0]))

    def test_success_releases_its_own_lock(self):
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - none\n")
        self.close_via_stub()

        self.run_worker()
        self.assertFalse(lock_path(self.root).exists())


# ---------------------------------------------------------------------------
# Failure classification: plain failure vs no-headless
# ---------------------------------------------------------------------------


class FailureClassificationTests(WorkerHarness):
    def test_nonzero_exit_without_auth_token_is_plain_failure_with_exit_code(self):
        with_env(self, "STUB_EXIT_CODE", "3")
        with_env(self, "STUB_STDERR", "unexpected internal error\n")

        code = self.run_worker()
        self.assertEqual(code, 0)  # the hook path never exits 2/fails the caller's turn
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertEqual(len(rows), 1)
        text = json.dumps(rows[0])
        self.assertIn("3", text)
        self.assertNotIn("no-headless", text)

    def test_missing_binary_is_classified_no_headless(self):
        with_env(self, "COMPASS_CLAUDE_BIN", str(self.root.parent / "does-not-exist-binary"))

        code = self.run_worker()
        self.assertEqual(code, 0)
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertEqual(len(rows), 1)
        self.assertIn("no-headless", json.dumps(rows[0]))

    def test_fast_nonzero_with_auth_token_is_no_headless(self):
        with_env(self, "STUB_EXIT_CODE", "1")
        with_env(self, "STUB_STDERR", "Error: authentication required\n")

        self.run_worker()
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertEqual(len(rows), 1)
        self.assertIn("no-headless", json.dumps(rows[0]))

    def test_fast_nonzero_without_auth_token_is_plain_failure(self):
        # Same speed as the case above; the only variable is the token -
        # isolates the classifier's second axis from the first.
        with_env(self, "STUB_EXIT_CODE", "1")
        with_env(self, "STUB_STDERR", "generic transient network error\n")

        self.run_worker()
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("no-headless", json.dumps(rows[0]))

    def test_slow_nonzero_with_auth_token_is_plain_failure(self):
        # Same token as the no-headless case; the only variable is timing -
        # isolates the classifier's first axis (fast) from the second.
        with_env(self, "STUB_EXIT_CODE", "1")
        with_env(self, "STUB_STDERR", "Error: authentication required\n")
        with_env(self, "STUB_SLEEP", "6")

        self.run_worker()
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("no-headless", json.dumps(rows[0]))


class NoHeadlessLatchTests(WorkerHarness):
    def test_no_headless_sets_latch_then_later_success_clears_it(self):
        with_env(self, "STUB_EXIT_CODE", "1")
        with_env(self, "STUB_STDERR", "credential expired\n")
        self.run_worker()
        state = capturelib.load_state(self.root)
        self.assertIsNotNone(state.get("no_headless_at"))

        # A second, working stub run on a fresh opportunity clears the latch.
        with_env(self, "STUB_EXIT_CODE", "0")
        with_env(self, "STUB_STDERR", None)
        with_env(self, "STUB_STDOUT", "extracted: 1 written, 0 revised, 0 rejected - ok\n")
        second_id, second_dir = open_test_opportunity(self.root)
        with_env(self, "STUB_MARKER", str(second_dir.parent / f"{second_id}-marker.json"))
        with_env(self, "STUB_CLOSE_OPP_PATH", str(second_dir / "opportunity.json"))
        with_env(self, "STUB_CLOSE_OUTCOME", "fired")

        self.run_worker(second_id)
        state = capturelib.load_state(self.root)
        self.assertIsNone(state.get("no_headless_at"))


# ---------------------------------------------------------------------------
# The worker lock: contention, staleness, owner-checked release
# ---------------------------------------------------------------------------


class WorkerLockTests(WorkerHarness):
    def test_lock_held_skips_stub_never_invoked_and_logs_lock_held_reason(self):
        write_lock(self.root, pid=424242, started_at=capturelib._iso(capturelib._now()))

        code = self.run_worker()
        self.assertEqual(code, 0)
        self.assertFalse(self.marker_path.exists(), "stub must never run under contention")
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertEqual(len(rows), 1)
        self.assertIn("lock-held", json.dumps(rows[0]))

    def test_lock_not_yet_stale_is_respected_at_grace_minus_one(self):
        # Fixture (5) deliberately not the module default (600): a broken
        # lookup that silently falls back to the default would treat this
        # lock as fresh either way and this test alone couldn't tell -
        # the paired stale-lock test below is what makes the override
        # observable.
        write_capture_config(self.root, worker_grace_seconds=5)
        write_lock(
            self.root, pid=424242, started_at=capturelib._iso(capturelib._now()),
            age_seconds=4,
        )

        self.run_worker()
        self.assertFalse(self.marker_path.exists())
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertIn("lock-held", json.dumps(rows[0]))

    def test_stale_lock_past_grace_is_broken_and_run_proceeds(self):
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - ok\n")
        self.close_via_stub()
        write_capture_config(self.root, worker_grace_seconds=5)
        write_lock(
            self.root, pid=424242, started_at=capturelib._iso(capturelib._now()),
            age_seconds=10,
        )

        code = self.run_worker()
        self.assertEqual(code, 0)
        self.assertTrue(self.marker_path.exists(), "stale lock must be broken and the run proceed")
        rows = [r for r in read_log_rows(self.root) if r["event"] == "worker-failed"]
        self.assertEqual(rows, [], "a broken-stale-lock run is not a lock-held failure")

    def test_owner_check_never_deletes_a_lock_tampered_to_a_foreign_pid(self):
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - ok\n")
        self.close_via_stub()
        with_env(self, "STUB_TAMPER_LOCK_PATH", str(lock_path(self.root)))

        self.run_worker()
        self.assertTrue(
            lock_path(self.root).exists(),
            "a lock now owned by a different pid must survive this run's release",
        )
        content = json.loads(lock_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(content.get("pid"), 999999)


# ---------------------------------------------------------------------------
# The child invocation: argv, stdin, cwd, env
# ---------------------------------------------------------------------------


class ChildInvocationTests(WorkerHarness):
    def test_child_argv_pins_model_never_inherit_and_output_format_json(self):
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - ok\n")
        self.close_via_stub()

        self.run_worker()
        marker = read_marker(self.marker_path)
        argv = marker["argv"]

        self.assertIn("--model", argv, "no --model flag in the child argv")
        model = argv[argv.index("--model") + 1]
        self.assertEqual(model, "haiku", f"resolved model was {model!r}, never inherit")

        self.assertIn("--output-format", argv, "no --output-format flag in the child argv")
        output_format = argv[argv.index("--output-format") + 1]
        self.assertEqual(output_format, "json", f"--output-format was {output_format!r}")

    def test_child_argv_carries_the_full_worker_prompt(self):
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - ok\n")
        self.close_via_stub()

        self.run_worker()
        marker = read_marker(self.marker_path)
        joined = " ".join(marker["argv"])

        for expected in (
            self.opp_id,
            "extract-lessons",
            "do not spawn subagents",
            "compass capture-close",
        ):
            self.assertIn(expected, joined, f"worker prompt argv missing {expected!r}")

    def test_child_receives_closed_stdin(self):
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - ok\n")
        self.close_via_stub()

        self.run_worker()
        marker = read_marker(self.marker_path)
        self.assertEqual(marker["stdin"], "")

    def test_child_cwd_is_project_root(self):
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - ok\n")
        self.close_via_stub()

        self.run_worker()
        marker = read_marker(self.marker_path)
        self.assertEqual(
            os.path.normcase(os.path.normpath(marker["cwd"])),
            os.path.normcase(os.path.normpath(str(self.root.parent))),
        )

    def test_child_env_adds_worker_session_without_removing_existing_vars(self):
        with_env(self, "COMPASS_TEST_CANARY", "canary-value")
        with_env(self, "STUB_STDOUT", "extracted: 0 written, 0 revised, 0 rejected - ok\n")
        self.close_via_stub()

        self.run_worker()
        marker = read_marker(self.marker_path)
        child_env = marker["env"]
        self.assertEqual(child_env.get("COMPASS_WORKER_SESSION"), "1")
        self.assertEqual(child_env.get("COMPASS_TEST_CANARY"), "canary-value")
        self.assertEqual(child_env.get("CLAUDE_PROJECT_DIR"), str(self.root.parent))

    def test_worker_log_file_carries_child_stdout_and_stderr(self):
        with_env(self, "STUB_STDOUT", "extracted: 1 written, 0 revised, 0 rejected - hi\n")
        with_env(self, "STUB_STDERR", "a warning line on stderr\n")
        self.close_via_stub()

        self.run_worker()
        log_file = self.root / "tmp" / "worker-logs" / f"{self.opp_id}.log"
        self.assertTrue(log_file.is_file())
        text = log_file.read_text(encoding="utf-8")
        self.assertIn("extracted: 1 written, 0 revised, 0 rejected - hi", text)
        self.assertIn("a warning line on stderr", text)


if __name__ == "__main__":
    unittest.main()
