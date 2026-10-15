"""Tests for `compass context-check`, the PostToolUse hook that halts the main
agent once per crossing of the context threshold and suggests a handoff.
Fixtures are transcripts in the shape Claude Code writes: a model
attachment line and assistant lines carrying `message.usage`."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands import context_check  # noqa: E402


# A model whose window is 200,000 (Sonnet 4.6 without `[1m]`).
STANDARD_MODEL = "claude-sonnet-4-6"


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
        for name in ("COMPASS_WORKER_SESSION", "COMPASS_CONTEXT_WINDOW", "COMPASS_CONTEXT_FINAL_THRESHOLD",
                     "CLAUDE_CODE_DISABLE_1M_CONTEXT", "CLAUDE_CODE_MAX_CONTEXT_TOKENS"):
            os.environ.pop(name, None)
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
        self.write(model_line(STANDARD_MODEL), assistant_line(input_tokens=10, cache_read=159_989))
        self.assertIsNone(self.hook())

    def test_exactly_80_percent_halts_with_continue_false_and_handoff(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(input_tokens=10, cache_read=159_990))
        out = self.hook()
        self.assertIs(out["continue"], False)
        self.assertIn("80%", out["stopReason"])
        self.assertIn("/compass:handoff", out["stopReason"])

    def test_output_tokens_do_not_count_toward_usage(self):
        # Defect class: output tokens are added, so the hook disagrees with
        # the statusline and halts early.
        self.write(model_line(STANDARD_MODEL), assistant_line(input_tokens=150_000, output=20_000))
        self.assertIsNone(self.hook())

    def test_cache_creation_counts_toward_usage(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(input_tokens=5, cache_creation=165_000))
        self.assertIsNotNone(self.hook())

    def test_extended_window_model_uses_one_million(self):
        # Defect class: a 1M session is judged against 200K and halts at 16%.
        self.write(model_line("claude-opus-5-5[1m]"), assistant_line(cache_read=500_000))
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=850_000))
        self.assertIn("85%", self.hook()["stopReason"])

    def test_latest_usage_wins_over_earlier_ones(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=190_000), assistant_line(cache_read=20_000))
        self.assertIsNone(self.hook())

    def test_sidechain_and_zero_usage_lines_are_ignored(self):
        # Defect class: a synthetic all-zero message after a real one reads
        # as 0% and re-arms or hides the crossing.
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000),
                   assistant_line(cache_read=1, sidechain=True),
                   {"type": "assistant", "message": {"usage": {"input_tokens": 0}}})
        self.assertIsNotNone(self.hook())

    def test_threshold_env_override(self):
        os.environ["COMPASS_CONTEXT_THRESHOLD"] = "10"
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=25_000))
        self.assertIn("12%", self.hook()["stopReason"])

    def test_invalid_threshold_env_falls_back_to_80(self):
        for bad in ("abc", "0", "150", ""):
            os.environ["COMPASS_CONTEXT_THRESHOLD"] = bad
            self.assertEqual(context_check.threshold(), 80, bad)


class WindowTests(ContextCheckFixture):
    def test_native_1m_models_without_suffix_use_one_million(self):
        # Defect class: the window is read from a `[1m]` suffix only, so a
        # native-1M model is judged against 200K and halts at 16%.
        for model_id in ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5", "claude-sonnet-5-5",
                         "claude-fable-5-1", "claude-haiku-5-5", "claude-opus-4-7",
                         "us.anthropic.claude-opus-4-7-v1"):
            self.assertEqual(context_check.window_for(model_id), 1_000_000, model_id)

    def test_200k_models_use_two_hundred_thousand(self):
        for model_id in ("claude-sonnet-4-6", "claude-opus-4-6", "claude-opus-4-1-20250805",
                         "claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001",
                         "claude-3-5-sonnet-20241022", "claude-3-opus-20240229",
                         "us.anthropic.claude-sonnet-4-5-20250929-v1:0"):
            self.assertEqual(context_check.window_for(model_id), 200_000, model_id)

    def test_1m_suffix_lifts_a_200k_model(self):
        self.assertEqual(context_check.window_for("claude-sonnet-4-6[1m]"), 1_000_000)
        self.assertEqual(context_check.window_for("claude-opus-4-6[1M]"), 1_000_000)

    def test_disable_1m_holds_native_models_at_200k_but_not_explicit_1m(self):
        os.environ["CLAUDE_CODE_DISABLE_1M_CONTEXT"] = "1"
        self.assertEqual(context_check.window_for("claude-opus-5-5"), 200_000)
        os.environ["CLAUDE_CODE_DISABLE_1M_CONTEXT"] = "0"
        self.assertEqual(context_check.window_for("claude-opus-5-5"), 1_000_000)

    def test_unknown_model_is_never_judged_against_a_smaller_guessed_window(self):
        # Defect class: an unrecognized id falls to 200K and halts early.
        self.assertEqual(context_check.window_for("gpt-6-sol"), 1_000_000)
        self.assertEqual(context_check.window_for(""), 1_000_000)
        self.assertEqual(context_check.window_for(None), 1_000_000)

    def test_unknown_model_takes_claude_code_max_context_tokens(self):
        os.environ["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = "128000"
        self.assertEqual(context_check.window_for("gpt-6-sol"), 128_000)
        self.assertEqual(context_check.window_for("claude-opus-5-5"), 1_000_000)

    def test_compass_window_override_beats_everything(self):
        os.environ["COMPASS_CONTEXT_WINDOW"] = "300000"
        self.assertEqual(context_check.window_for("claude-opus-5-5[1m]"), 300_000)
        self.assertEqual(context_check.window_for("claude-sonnet-4-6"), 300_000)
        os.environ["COMPASS_CONTEXT_WINDOW"] = "junk"
        self.assertEqual(context_check.window_for("claude-sonnet-4-6"), 200_000)

    def test_reported_session_passes_at_16_percent(self):
        # The reported session: Opus 5.5 with no suffix, 160.9k used.
        self.write(model_line("claude-opus-5-5"), assistant_line(input_tokens=6, cache_read=160_900))
        self.assertIsNone(self.hook())

    def test_stale_200k_window_in_state_from_an_older_version_is_ignored(self):
        # Defect class: a wrong window cached per session stays wrong for the
        # session's whole life.
        state_path = self.project / ".compass" / "tmp" / "context-state.json"
        state_path.write_text(json.dumps({"s1": {"window": 200000, "halted": True}}), encoding="utf-8")
        self.write(model_line("claude-opus-5-5"), assistant_line(cache_read=160_900))
        self.assertIsNone(self.hook())
        self.assertEqual(json.loads(state_path.read_text())["s1"],
                         {"model": "claude-opus-5-5", "offered": 0})

    def test_model_line_after_the_latest_usage_updates_the_cached_model(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=100_000))
        self.assertIsNone(self.hook())
        self.append(model_line("claude-opus-5-5"), {"type": "user", "message": {"content": "next"}},
                    assistant_line(cache_read=170_000))
        self.assertIsNone(self.hook())  # 17% of 1M, not 85% of 200K


class SecondOfferTests(ContextCheckFixture):
    """SPEC-025 D-04: suggested once at 80%; if declined, work continues and
    the handoff is suggested one more time at 95%."""

    def test_declined_at_80_continues_until_95_then_offers_once_more(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=161_000))
        self.assertIn("80%", self.hook()["stopReason"])
        for used in (165_000, 175_000, 185_000, 189_000):  # the human said no; work goes on
            self.append(assistant_line(cache_read=used))
            self.assertIsNone(self.hook(), used)
        self.append(assistant_line(cache_read=190_500))
        out = self.hook()
        self.assertIs(out["continue"], False)
        self.assertIn("95%", out["stopReason"])
        self.assertIn("/compass:handoff", out["stopReason"])

    def test_no_third_offer_after_95(self):
        # Defect class: every call past 95% halts, so a declined session
        # can never finish its work.
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=161_000))
        self.hook()
        self.append(assistant_line(cache_read=191_000))
        self.assertIsNotNone(self.hook())
        for used in (193_000, 196_000, 199_000):
            self.append(assistant_line(cache_read=used))
            self.assertIsNone(self.hook(), used)

    def test_dip_between_levels_after_95_does_not_rearm_95(self):
        # Defect class: usage falling from 96% to 85% (a partial trim) and
        # back re-arms 95%, giving a third offer.
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=161_000))
        self.hook()
        self.append(assistant_line(cache_read=192_000))
        self.assertIsNotNone(self.hook())
        self.append(assistant_line(cache_read=170_000))
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=192_000))
        self.assertIsNone(self.hook())

    def test_jump_past_both_levels_offers_once(self):
        # Defect class: a session that crosses 80 and 95 between two calls
        # is stopped twice in a row.
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=100_000))
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=192_000))
        self.assertIn("96%", self.hook()["stopReason"])
        self.append(assistant_line(cache_read=193_000))
        self.assertIsNone(self.hook())

    def test_first_and_final_messages_differ(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=161_000))
        first = self.hook()["stopReason"]
        self.append(assistant_line(cache_read=191_000))
        final = self.hook()["stopReason"]
        self.assertNotEqual(first.replace("80%", "N"), final.replace("95%", "N"))

    def test_compaction_rearms_both_levels(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=161_000))
        self.hook()
        self.append(assistant_line(cache_read=191_000))
        self.hook()
        self.append(assistant_line(cache_read=30_000))  # after /compact
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=161_000))
        self.assertIn("80%", self.hook()["stopReason"])

    def test_state_from_the_single_level_version_counts_as_offered_at_80(self):
        # Defect class: an older `halted: true` entry is read as never
        # offered, so a session that already declined is stopped again.
        state_path = self.project / ".compass" / "tmp" / "context-state.json"
        state_path.write_text(json.dumps({"s1": {"model": STANDARD_MODEL, "halted": True}}), encoding="utf-8")
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=191_000))
        self.assertIsNotNone(self.hook())

    def test_final_level_env_and_degenerate_values(self):
        os.environ["COMPASS_CONTEXT_FINAL_THRESHOLD"] = "90"
        self.assertEqual(context_check.levels(), [80, 90])
        os.environ["COMPASS_CONTEXT_FINAL_THRESHOLD"] = "70"
        self.assertEqual(context_check.levels(), [80])
        os.environ["COMPASS_CONTEXT_FINAL_THRESHOLD"] = "junk"
        self.assertEqual(context_check.levels(), [80, 95])
        os.environ["COMPASS_CONTEXT_THRESHOLD"] = "95"
        self.assertEqual(context_check.levels(), [95])


class OncePerCrossingTests(ContextCheckFixture):
    def test_second_call_after_a_halt_passes_so_the_handoff_can_run(self):
        # Defect class: every tool call halts, so /compass:handoff is stopped
        # at its first step and the session is stuck.
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook())
        self.append(assistant_line(cache_read=175_000))
        self.assertIsNone(self.hook())
        self.assertIsNone(self.hook())

    def test_dropping_under_the_line_rearms_the_next_crossing(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook())
        self.append(assistant_line(cache_read=30_000))  # after /compact
        self.assertIsNone(self.hook())
        self.append(assistant_line(cache_read=165_000))
        self.assertIsNotNone(self.hook())

    def test_crossing_is_tracked_per_session(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook(self.event(session_id="a")))
        self.assertIsNotNone(self.hook(self.event(session_id="b")))

    def test_corrupt_state_file_is_treated_as_empty(self):
        (self.project / ".compass" / "tmp" / "context-state.json").write_text("{not json", encoding="utf-8")
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook())

    def test_state_keeps_a_bounded_number_of_sessions(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=10))
        for i in range(context_check.STATE_SESSIONS_KEPT + 10):
            self.hook(self.event(session_id=f"s{i}"))
        state = json.loads((self.project / ".compass" / "tmp" / "context-state.json").read_text())
        self.assertEqual(len(state), context_check.STATE_SESSIONS_KEPT)
        self.assertIn(f"s{context_check.STATE_SESSIONS_KEPT + 9}", state)


class ConcurrentStateTests(ContextCheckFixture):
    """Parallel tool calls fire one PostToolUse hook process each, all
    saving the same state file at once."""

    def bugs_captured(self):
        return sorted(p.name for p in (self.project / ".compass" / "tmp" / "compass-bugs").glob("*.json"))

    def test_concurrent_processes_save_without_a_fault(self):
        # Defect class: processes share one temp name, so one replace moves
        # another's temp away (FileNotFoundError), or Windows refuses the
        # replace while another process holds the file (PermissionError).
        state_path = self.project / ".compass" / "tmp" / "context-state.json"
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path;"
            "from commands import context_check as c; p = Path(sys.argv[2]);"
            "[c._save_state(p, dict(c._load_state(p), **{sys.argv[3]: {'offered': i}})) for i in range(150)]"
        )
        cli_dir = str(Path(__file__).resolve().parents[1])
        procs = [subprocess.Popen([sys.executable, "-c", script, cli_dir, str(state_path), f"s{n}"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for n in range(8)]
        for proc in procs:
            _, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, err.decode(errors="replace"))
        self.assertIsInstance(json.loads(state_path.read_text()), dict)
        self.assertEqual(list(state_path.parent.glob("*.tmp")), [])

    def test_a_replace_refused_briefly_still_saves(self):
        # Windows refuses the replace while another process holds the file open.
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        real_replace = os.replace
        refusals = iter([PermissionError(32, "in use")] * 2)

        def flaky_replace(src, dst):
            error = next(refusals, None)
            if error:
                raise error
            real_replace(src, dst)

        with unittest.mock.patch.object(context_check.os, "replace", flaky_replace), \
                unittest.mock.patch.object(context_check.time, "sleep"):
            self.assertIsNotNone(self.hook())
        self.assertIsNone(self.hook())  # the crossing was recorded
        self.assertEqual(self.bugs_captured(), [])

    def test_a_read_refused_briefly_still_sees_the_recorded_crossing(self):
        # Defect class: a refused read is taken as an empty state, the
        # crossing is forgotten, and the session is halted a second time.
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        self.assertIsNotNone(self.hook())
        real_read = Path.read_text
        refusals = iter([PermissionError(32, "in use")] * 2)

        def flaky_read(path, *args, **kwargs):
            if path.name == "context-state.json":
                error = next(refusals, None)
                if error:
                    raise error
            return real_read(path, *args, **kwargs)

        with unittest.mock.patch.object(Path, "read_text", flaky_read), \
                unittest.mock.patch.object(context_check.time, "sleep"):
            self.assertIsNone(self.hook())

    def test_a_replace_refused_throughout_passes_and_leaves_no_temp(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000))
        with unittest.mock.patch.object(context_check.os, "replace", side_effect=PermissionError(32, "in use")), \
                unittest.mock.patch.object(context_check.time, "sleep"):
            self.assertIsNotNone(self.hook())
        self.assertEqual(list((self.project / ".compass" / "tmp").glob("*.tmp")), [])
        self.assertEqual(self.bugs_captured(), [])


class TranscriptReadingTests(ContextCheckFixture):
    def test_usage_far_before_the_tail_chunk_is_still_found(self):
        # Defect class: the backward read stops at its first chunk and
        # misses usage when the tail is one huge tool result.
        filler = {"type": "user", "message": {"content": "x" * (context_check.TAIL_CHUNK * 3)}}
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000), filler)
        self.assertIsNotNone(self.hook())

    def test_line_split_across_chunk_boundary_parses(self):
        # Defect class: a record straddling two chunks is dropped as garbage.
        pad = {"type": "user", "message": {"content": "y" * (context_check.TAIL_CHUNK - 40)}}
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000), pad)
        self.assertEqual(context_check.measure(self.transcript)[0], 170_000)

    def test_model_cached_from_an_earlier_call_is_used_when_the_model_line_is_not_reached(self):
        self.write(model_line("m[1m]"), assistant_line(cache_read=10))
        self.hook()
        self.write(assistant_line(cache_read=500_000))  # model line gone from this file
        self.assertIsNone(self.hook())  # 50% of the cached 1M window

    def test_garbage_lines_are_skipped(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=170_000),
                   raw_lines=["{broken", "[1,2]", "\x00\x01", "null"])
        self.assertIsNotNone(self.hook())


class PassTests(ContextCheckFixture):
    def test_subagent_event_passes(self):
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=190_000))
        self.assertIsNone(self.hook(self.event(agent_id="abc", agent_type="builder")))

    def test_worker_session_passes(self):
        os.environ["COMPASS_WORKER_SESSION"] = "1"
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=190_000))
        self.assertIsNone(self.hook())

    def test_missing_transcript_passes(self):
        self.assertIsNone(self.hook(self.event(transcript_path=str(self.project / "nope.jsonl"))))
        self.assertIsNone(self.hook(self.event(transcript_path="")))

    def test_no_usage_yet_passes(self):
        self.write(model_line(STANDARD_MODEL))
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
        self.write(model_line(STANDARD_MODEL), assistant_line(cache_read=190_000))
        cwd = os.getcwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, cwd)
        self.assertIsNone(self.hook())


if __name__ == "__main__":
    unittest.main()
