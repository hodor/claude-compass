"""Tests for `compass context-check`, the PostToolUse hook that halts the main
agent once per crossing of the context threshold and suggests a handoff.
Fixtures are transcripts in the shape Claude Code writes: a model
attachment line and assistant lines carrying `message.usage`."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import context_check  # noqa: E402


def model_line(model_id):
    return {"type": "attachment", "attachment": {"type": "model", "identity": {"modelId": model_id}}}


def assistant_line(input_tokens=0, cache_read=0, cache_creation=0, output=500, sidechain=False):
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"usage": {
            "input_tokens": input_tokens,
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_creation,
            "output_tokens": output,
        }},
    }


class ContextCheckFixture(unittest.TestCase):
    def setUp(self):
        self.project = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.project, True)
        (self.project / ".compass" / "tmp").mkdir(parents=True)
        self.transcript = self.project / "session.jsonl"
        self.env_backup = dict(os.environ)
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        os.environ.pop("COMPASS_CONTEXT_THRESHOLD", None)
        os.environ.pop("COMPASS_WORKER_SESSION", None)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.env_backup)))

    def write(self, *records, raw_lines=()):
        lines = [json.dumps(r) for r in records] + list(raw_lines)
        self.transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def append(self, *records):
        with open(self.transcript, "a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")

    def event(self, **extra):
        return dict({"hook_event_name": "PostToolUse", "session_id": "s1",
                     "transcript_path": str(self.transcript), "tool_name": "Bash"}, **extra)

    def hook(self, event=None):
        out = io.StringIO()
        payload = json.dumps(self.event() if event is None else event)
        with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO(payload)):
            code = context_check.run(["--hook"])
        self.assertEqual(code, 0)
        text = out.getvalue()
        return json.loads(text) if text else None


class ThresholdTests(ContextCheckFixture):
    def test_just_under_80_percent_passes(self):
        # Defect class: an off-by-one or rounding halts a session that has
        # not reached the line.
        self.write(model_line("claude-opus-5-5"), assistant_line(input_tokens=10, cache_read=159_989))
        self.assertIsNone(self.hook())

    def test_exactly_80_percent_halts_with_continue_false_and_handoff(self):
        self.write(model_line("claude-opus-5-5"), assistant_line(input_tokens=10, cache_read=159_990))
        out = self.hook()
        self.assertIs(out["continue"], False)
        self.assertIn("80%", out["stopReason"])
        self.assertIn("/compass:handoff", out["stopReason"])

    def test_output_tokens_do_not_count_toward_usage(self):
        # Defect class: output tokens are added, so the hook disagrees with
        # the statusline and halts early.
        self.write(model_line("claude-opus-5-5"), assistant_line(input_tokens=150_000, output=20_000))
        self.assertIsNone(self.hook())

    def test_cache_creation_counts_toward_usage(self):
        self.write(model_line("claude-opus-5-5"), assistant_line(input_tokens=5, cache_creation=165_000))
        self.assertIsNotNone(self.hook())

    def test_extended_window_model_uses_one_million(self):
        # Defect class: a 1M session is judged against 200K and halts at 16%.
        self.write(model_line("claude-opus-5-5[1m]"), assistant_line(cache_read=500_000))
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=850_000))
        self.assertIn("85%", self.hook()["stopReason"])

    def test_latest_usage_wins_over_earlier_ones(self):
        self.write(model_line("m"), assistant_line(cache_read=190_000), assistant_line(cache_read=20_000))
        self.assertIsNone(self.hook())

    def test_sidechain_and_zero_usage_lines_are_ignored(self):
        # Defect class: a synthetic all-zero message after a real one reads
        # as 0% and re-arms or hides the crossing.
        self.write(model_line("m"), assistant_line(cache_read=170_000),
                   assistant_line(cache_read=1, sidechain=True),
                   {"type": "assistant", "message": {"usage": {"input_tokens": 0}}})
        self.assertIsNotNone(self.hook())

    def test_threshold_env_override(self):
        os.environ["COMPASS_CONTEXT_THRESHOLD"] = "10"
        self.write(model_line("m"), assistant_line(cache_read=25_000))
        self.assertIn("12%", self.hook()["stopReason"])

    def test_invalid_threshold_env_falls_back_to_80(self):
        for bad in ("abc", "0", "150", ""):
            os.environ["COMPASS_CONTEXT_THRESHOLD"] = bad
            self.assertEqual(context_check.threshold(), 80, bad)


class OncePerCrossingTests(ContextCheckFixture):
    def test_second_call_after_a_halt_passes_so_the_handoff_can_run(self):
        # Defect class: every tool call halts, so /compass:handoff is stopped
        # at its first step and the session is stuck.
        self.write(model_line("m"), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook())
        self.append(assistant_line(cache_read=175_000))
        self.assertIsNone(self.hook())
        self.assertIsNone(self.hook())

    def test_dropping_under_the_line_rearms_the_next_crossing(self):
        self.write(model_line("m"), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook())
        self.append(assistant_line(cache_read=30_000))  # after /compact
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=165_000))
        self.assertIsNotNone(self.hook())

    def test_crossing_is_tracked_per_session(self):
        self.write(model_line("m"), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook(self.event(session_id="a")))
        self.assertIsNotNone(self.hook(self.event(session_id="b")))

    def test_corrupt_state_file_is_treated_as_empty(self):
        (self.project / ".compass" / "tmp" / "context-state.json").write_text("{not json", encoding="utf-8")
        self.write(model_line("m"), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook())

    def test_state_keeps_a_bounded_number_of_sessions(self):
        self.write(model_line("m"), assistant_line(cache_read=10))
        for i in range(context_check.STATE_SESSIONS_KEPT + 10):
            self.hook(self.event(session_id=f"s{i}"))
        state = json.loads((self.project / ".compass" / "tmp" / "context-state.json").read_text())
        self.assertEqual(len(state), context_check.STATE_SESSIONS_KEPT)
        self.assertIn(f"s{context_check.STATE_SESSIONS_KEPT + 9}", state)


class TranscriptReadingTests(ContextCheckFixture):
    def test_usage_far_before_the_tail_chunk_is_still_found(self):
        # Defect class: the backward read stops at its first chunk and
        # misses usage when the tail is one huge tool result.
        filler = {"type": "user", "message": {"content": "x" * (context_check.TAIL_CHUNK * 3)}}
        self.write(model_line("m"), assistant_line(cache_read=170_000), filler)
        self.assertIsNotNone(self.hook())

    def test_line_split_across_chunk_boundary_parses(self):
        # Defect class: a record straddling two chunks is dropped as garbage.
        pad = {"type": "user", "message": {"content": "y" * (context_check.TAIL_CHUNK - 40)}}
        self.write(model_line("m"), assistant_line(cache_read=170_000), pad)
        self.assertEqual(context_check.measure(self.transcript)[0], 170_000)

    def test_window_cached_from_an_earlier_call_is_used_when_the_model_line_is_not_reached(self):
        self.write(model_line("m[1m]"), assistant_line(cache_read=10))
        self.hook()
        self.write(assistant_line(cache_read=500_000))  # model line gone from this file
        self.assertIsNone(self.hook())  # 50% of the cached 1M window

    def test_garbage_lines_are_skipped(self):
        self.write(model_line("m"), assistant_line(cache_read=170_000),
                   raw_lines=["{broken", "[1,2]", "\x00\x01", "null"])
        self.assertIsNotNone(self.hook())


class PassTests(ContextCheckFixture):
    def test_subagent_event_passes(self):
        self.write(model_line("m"), assistant_line(cache_read=190_000))
        self.assertIsNone(self.hook(self.event(agent_id="abc", agent_type="builder")))

    def test_worker_session_passes(self):
        os.environ["COMPASS_WORKER_SESSION"] = "1"
        self.write(model_line("m"), assistant_line(cache_read=190_000))
        self.assertIsNone(self.hook())

    def test_missing_transcript_passes(self):
        self.assertIsNone(self.hook(self.event(transcript_path=str(self.project / "nope.jsonl"))))
        self.assertIsNone(self.hook(self.event(transcript_path="")))

    def test_no_usage_yet_passes(self):
        self.write(model_line("m"))
        self.assertIsNone(self.hook())

    def test_empty_and_malformed_stdin_pass(self):
        for payload in ("", "not json", "[1]"):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO(payload)):
                self.assertEqual(context_check.run(["--hook"]), 0)
            self.assertEqual(out.getvalue(), "")

    def test_no_vault_passes(self):
        shutil.rmtree(self.project / ".compass")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.write(model_line("m"), assistant_line(cache_read=190_000))
        cwd = os.getcwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)
        self.assertIsNone(self.hook())


if __name__ == "__main__":
    unittest.main()
