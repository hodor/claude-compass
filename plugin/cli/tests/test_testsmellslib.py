"""Tests for `testsmellslib` (the five checks) and `commands.test_smells`
(the CLI wrapper).

Every fixture module here is a string of Python source written to a
temporary file - the fixtures are never imported or executed, only parsed,
so an intentionally broken or nonsensical body is safe to write. Each
fixture pairs a positive case (the check must fire) with the near-miss
designed to break it (the check must stay silent).
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import testsmellslib  # noqa: E402
from commands import test_smells  # noqa: E402


def write_module(tmp, name, source):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(source)
    return path


def make_tmp(test_case):
    tmp = Path(tempfile.mkdtemp())
    test_case.addCleanup(shutil.rmtree, tmp, True)
    return tmp


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

EMPTY_SRC = '''\
import unittest


class EmptyTests(unittest.TestCase):
    def test_pass_body_is_empty(self):
        """Adversarial where: a body of only pass catches nothing."""
        pass

    def test_ellipsis_body_is_empty(self):
        """Adversarial where: a body of only ... catches nothing."""
        ...

    def test_bare_return_is_empty(self):
        """Adversarial where: a body of only return catches nothing."""
        return

    def test_docstring_only_is_empty(self):
        """Adversarial where: a docstring with no statements catches
        nothing."""

    def test_single_call_is_not_empty(self):
        """Adversarial where: a single call with a side effect must survive
        the empty-test check."""
        LOG.append("ran")


LOG = []
'''

DUPLICATE_ASSERT_SRC = '''\
import unittest

CONST = 1


class DuplicateAssertTests(unittest.TestCase):
    def test_duplicate_assert_is_flagged(self):
        """Adversarial where: the same assertion repeated twice adds no
        detection power."""
        self.assertEqual(CONST, 1)
        self.assertEqual(CONST, 1)

    def test_duplicate_assert_across_rebind_is_not_flagged(self):
        """Adversarial where: re-checking the same invariant after the
        value it reads is rebound is a legitimate check across a state
        change."""
        value = CONST
        self.assertEqual(value, 1)
        value = CONST
        self.assertEqual(value, 1)
'''

LITERAL_ONLY_SRC = '''\
import unittest

import modelslib


class LiteralOnlyTests(unittest.TestCase):
    def test_only_reads_constants(self):
        """Adversarial where: comparing an imported constant against a
        literal catches nothing about behavior."""
        self.assertEqual(modelslib.TIER_EFFORT["strong"], "high")

    def test_constants_but_calls_helper_is_not_flagged(self):
        """Adversarial where: a test that also calls a helper is exercising
        code, not just reading constants."""
        self.assertEqual(_load_effort(), "high")


def _load_effort():
    return modelslib.TIER_EFFORT["strong"]
'''

ASSERTION_FREE_SRC = '''\
import unittest

import modelslib


class AssertionFreeTests(unittest.TestCase):
    def test_no_assertion_is_flagged(self):
        """Adversarial where: a test that touches the subject but never
        checks anything gives false confidence."""
        modelslib.resolve("planner")

    def test_delegates_to_module_helper_is_not_flagged(self):
        """Adversarial where: delegating the check to a same-module helper
        must not be treated as assertion-free."""
        _assert_valid(modelslib.resolve("planner"))

    def test_ends_in_self_fail_is_not_flagged(self):
        """Adversarial where: a test that ends in self.fail still performed
        a real check."""
        if modelslib.resolve("planner") is None:
            self.fail("expected a resolution")


def _assert_valid(value):
    assert value is not None
'''

CLEAN_SRC = '''\
import unittest

import modelslib


class CleanTests(unittest.TestCase):
    def test_resolve_strong_agent_returns_opus(self):
        """Adversarial where: a strong-tier agent must resolve to opus, not
        silently fall back to inherit."""
        model, effort, source = modelslib.resolve(
            "planner", config=modelslib.empty_config(), environ={},
        )
        self.assertEqual(model, "opus")
        self.assertEqual(effort, "high")
        self.assertEqual(source, "built-in")
'''

PARSE_ERROR_SRC = "def test_broken(:\n    pass\n"

HELPER_ONLY_SRC = '''\
def make_widget():
    return {"kind": "widget"}
'''

REAL_TEST_SRC = '''\
import unittest


class RealTests(unittest.TestCase):
    def test_something(self):
        """Adversarial where: nothing, this only exists to be discovered."""
        self.assertTrue(True)
'''

NUL_BYTE_SRC = "def test_x():\n    pass\x00\n"

FROM_IMPORT_SRC = '''\
import unittest

from commands import sync as sync_cmd
from modelslib import TIER_EFFORT


class FromImportTests(unittest.TestCase):
    def test_from_import_module_call_is_not_literal_only(self):
        """Adversarial where: a from-imported module called through its
        alias is still a call into the code under test, not a read of an
        imported constant."""
        report = sync_cmd.sync("/tmp/does-not-exist")
        self.assertIsNotNone(report)

    def test_from_import_all_caps_constant_is_literal_only(self):
        """Adversarial where: a from-imported ALL_CAPS constant read
        through a container method must not be mistaken for a call into
        the code under test."""
        self.assertEqual(
            sorted(TIER_EFFORT.keys()), ["balanced", "cheap", "inherit", "strong"]
        )
'''

DECORATOR_SRC = '''\
import unittest

import modelslib


class DecoratorTests(unittest.TestCase):
    @unittest.skip("not needed")
    def test_decorator_call_does_not_count_as_a_code_call(self):
        """Adversarial where: a call inside the decorator list must not be
        mistaken for a call the test body makes."""
        self.assertEqual(modelslib.TIER_EFFORT["strong"], "high")
'''

ASSERTION_ROULETTE_SRC = '''\
import unittest


def _value(x):
    return x


class RouletteTests(unittest.TestCase):
    def test_two_unmessaged_assertions_is_below_threshold(self):
        """Adversarial where: one assertion short of the configured
        threshold must not fire - the boundary is exact, not a rough
        cutoff."""
        self.assertEqual(_value(1), 1)
        self.assertEqual(_value(2), 2)

    def test_three_unmessaged_assertions_hits_threshold(self):
        """Adversarial where: reaching the configured threshold exactly
        must fire, not require one more past it."""
        self.assertEqual(_value(1), 1)
        self.assertEqual(_value(2), 2)
        self.assertEqual(_value(3), 3)

    def test_messaged_assertions_are_never_counted(self):
        """Adversarial where: a message on every assertion removes the
        ambiguity Assertion Roulette targets and must suppress the finding
        even with enough assertions to reach the threshold."""
        self.assertEqual(_value(1), 1, msg="one is one")
        self.assertEqual(_value(2), 2, msg="two is two")
        self.assertEqual(_value(3), 3, msg="three is three")

    def test_subtest_assertions_do_not_count_toward_the_total(self):
        """Adversarial where: an assertion issued once per case inside
        self.subTest must not be penalized the way a flat run of
        undifferentiated assertions is - subTest already names which case
        failed."""
        for value in (1, 2, 3):
            with self.subTest(value=value):
                self.assertEqual(_value(value), value)
        self.assertEqual(_value(9), 9)

    def test_positional_fail_argument_counts_as_a_message(self):
        """Adversarial where: self.fail's only parameter is msg, so a
        positional argument to it is unambiguously a message, unlike the
        other assert methods whose arity varies - counting a positional
        self.fail argument as unmessaged would misclassify every
        fail-based assertion."""
        if _value(1) != 1:
            self.fail("one is one")
        if _value(2) != 2:
            self.fail("two is two")
        if _value(3) != 3:
            self.fail("three is three")
'''


# --------------------------------------------------------------------------
# empty-test
# --------------------------------------------------------------------------

class EmptyTestCheckTests(unittest.TestCase):
    def test_fires_on_every_empty_shape_and_not_on_the_near_miss(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_empty.py", EMPTY_SRC)
        findings = testsmellslib.run_checks([str(path)])
        empty_tests = {f["test"] for f in findings if f["check"] == "empty-test"}
        self.assertEqual(
            empty_tests,
            {
                "EmptyTests.test_pass_body_is_empty",
                "EmptyTests.test_ellipsis_body_is_empty",
                "EmptyTests.test_bare_return_is_empty",
                "EmptyTests.test_docstring_only_is_empty",
            },
        )
        self.assertNotIn("EmptyTests.test_single_call_is_not_empty", empty_tests)
        for f in findings:
            if f["check"] == "empty-test":
                self.assertEqual(f["severity"], testsmellslib.GATE)


# --------------------------------------------------------------------------
# duplicate-assert
# --------------------------------------------------------------------------

class DuplicateAssertCheckTests(unittest.TestCase):
    def test_fires_on_repeat_and_not_across_a_rebind(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_dup.py", DUPLICATE_ASSERT_SRC)
        findings = testsmellslib.run_checks([str(path)])
        dup_tests = {f["test"] for f in findings if f["check"] == "duplicate-assert"}
        self.assertEqual(dup_tests, {"DuplicateAssertTests.test_duplicate_assert_is_flagged"})
        self.assertNotIn(
            "DuplicateAssertTests.test_duplicate_assert_across_rebind_is_not_flagged",
            dup_tests,
        )
        for f in findings:
            if f["check"] == "duplicate-assert":
                self.assertEqual(f["severity"], testsmellslib.GATE)


# --------------------------------------------------------------------------
# literal-only
# --------------------------------------------------------------------------

class LiteralOnlyCheckTests(unittest.TestCase):
    def test_fires_on_constants_only_and_not_when_a_helper_is_called(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_literal.py", LITERAL_ONLY_SRC)
        findings = testsmellslib.run_checks([str(path)])
        literal_tests = {f["test"] for f in findings if f["check"] == "literal-only"}
        self.assertEqual(literal_tests, {"LiteralOnlyTests.test_only_reads_constants"})
        self.assertNotIn(
            "LiteralOnlyTests.test_constants_but_calls_helper_is_not_flagged",
            literal_tests,
        )
        for f in findings:
            if f["check"] == "literal-only":
                self.assertEqual(f["severity"], testsmellslib.GATE)

    def test_from_import_module_counts_but_from_import_constant_does_not(self):
        """Regression for the bug found during build: `_imported_module_names`
        originally treated every `from ... import` binding as a module,
        which suppressed literal-only on a test that only ever touches an
        imported ALL_CAPS constant through a container method."""
        tmp = make_tmp(self)
        path = write_module(tmp, "test_from_import.py", FROM_IMPORT_SRC)
        findings = testsmellslib.run_checks([str(path)])
        literal_tests = {f["test"] for f in findings if f["check"] == "literal-only"}
        self.assertEqual(
            literal_tests, {"FromImportTests.test_from_import_all_caps_constant_is_literal_only"}
        )
        self.assertNotIn(
            "FromImportTests.test_from_import_module_call_is_not_literal_only", literal_tests
        )

    def test_decorator_call_is_excluded_from_the_scan(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_decorator.py", DECORATOR_SRC)
        findings = testsmellslib.run_checks([str(path)])
        literal_tests = {f["test"] for f in findings if f["check"] == "literal-only"}
        self.assertIn("DecoratorTests.test_decorator_call_does_not_count_as_a_code_call", literal_tests)


# --------------------------------------------------------------------------
# assertion-free
# --------------------------------------------------------------------------

class AssertionFreeCheckTests(unittest.TestCase):
    def test_fires_on_no_assertion_and_not_on_helper_or_self_fail(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_free.py", ASSERTION_FREE_SRC)
        findings = testsmellslib.run_checks([str(path)])
        free_tests = {f["test"] for f in findings if f["check"] == "assertion-free"}
        self.assertEqual(free_tests, {"AssertionFreeTests.test_no_assertion_is_flagged"})
        self.assertNotIn(
            "AssertionFreeTests.test_delegates_to_module_helper_is_not_flagged", free_tests
        )
        self.assertNotIn("AssertionFreeTests.test_ends_in_self_fail_is_not_flagged", free_tests)
        for f in findings:
            if f["check"] == "assertion-free":
                self.assertEqual(f["severity"], testsmellslib.ADVISORY)


# --------------------------------------------------------------------------
# assertion-roulette
# --------------------------------------------------------------------------

class AssertionRouletteCheckTests(unittest.TestCase):
    def test_fires_at_threshold_and_not_one_below(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_roulette.py", ASSERTION_ROULETTE_SRC)
        findings = testsmellslib.run_checks([str(path)], roulette_threshold=3)
        roulette_tests = {f["test"] for f in findings if f["check"] == "assertion-roulette"}
        self.assertIn("RouletteTests.test_three_unmessaged_assertions_hits_threshold", roulette_tests)
        self.assertNotIn(
            "RouletteTests.test_two_unmessaged_assertions_is_below_threshold", roulette_tests
        )
        for f in findings:
            if f["check"] == "assertion-roulette":
                self.assertEqual(f["severity"], testsmellslib.ADVISORY)

    def test_message_on_every_assertion_suppresses_it(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_roulette.py", ASSERTION_ROULETTE_SRC)
        findings = testsmellslib.run_checks([str(path)], roulette_threshold=3)
        roulette_tests = {f["test"] for f in findings if f["check"] == "assertion-roulette"}
        self.assertNotIn("RouletteTests.test_messaged_assertions_are_never_counted", roulette_tests)

    def test_subtest_assertions_are_excluded_from_the_count(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_roulette.py", ASSERTION_ROULETTE_SRC)
        findings = testsmellslib.run_checks([str(path)], roulette_threshold=3)
        roulette_tests = {f["test"] for f in findings if f["check"] == "assertion-roulette"}
        self.assertNotIn(
            "RouletteTests.test_subtest_assertions_do_not_count_toward_the_total", roulette_tests
        )

    def test_positional_fail_argument_counts_as_a_message(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_roulette.py", ASSERTION_ROULETTE_SRC)
        findings = testsmellslib.run_checks([str(path)], roulette_threshold=3)
        roulette_tests = {f["test"] for f in findings if f["check"] == "assertion-roulette"}
        self.assertNotIn(
            "RouletteTests.test_positional_fail_argument_counts_as_a_message", roulette_tests
        )

    def test_threshold_is_configurable(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_roulette.py", ASSERTION_ROULETTE_SRC)
        findings_default = testsmellslib.run_checks([str(path)])
        roulette_default = {f["test"] for f in findings_default if f["check"] == "assertion-roulette"}
        self.assertEqual(roulette_default, set())
        findings_low = testsmellslib.run_checks([str(path)], roulette_threshold=2)
        roulette_low = {f["test"] for f in findings_low if f["check"] == "assertion-roulette"}
        self.assertIn("RouletteTests.test_two_unmessaged_assertions_is_below_threshold", roulette_low)

    def test_advisory_never_flips_the_exit_code(self):
        """Adversarial where: assertion-roulette is advisory permanently -
        a low threshold that fires on every test in the fixture must
        still exit 0."""
        tmp = make_tmp(self)
        path = write_module(tmp, "test_roulette.py", ASSERTION_ROULETTE_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path), "--roulette-threshold", "1"])
        self.assertEqual(code, 0)
        self.assertIn("PASS", out.getvalue())
        self.assertIn("assertion-roulette", out.getvalue())


# --------------------------------------------------------------------------
# clean tree, parse errors, directory discovery
# --------------------------------------------------------------------------

class CleanAndErrorCasesTests(unittest.TestCase):
    def test_clean_fixture_produces_no_findings(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_clean.py", CLEAN_SRC)
        findings = testsmellslib.run_checks([str(path)])
        self.assertEqual(findings, [])

    def test_unparseable_file_is_a_finding_not_a_crash(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_broken.py", PARSE_ERROR_SRC)
        findings = testsmellslib.run_checks([str(path)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "parse-error")
        self.assertEqual(findings[0]["severity"], testsmellslib.GATE)
        self.assertEqual(findings[0]["file"], str(path))

    def test_missing_path_is_a_finding_not_a_crash(self):
        tmp = make_tmp(self)
        missing = tmp / "does_not_exist.py"
        findings = testsmellslib.run_checks([str(missing)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "parse-error")
        self.assertEqual(findings[0]["severity"], testsmellslib.GATE)

    def test_directory_walk_uses_content_signal_not_path_shape(self):
        tmp = make_tmp(self)
        write_module(tmp, "helpers.py", HELPER_ONLY_SRC)
        real_path = write_module(tmp, "test_real.py", REAL_TEST_SRC)
        parsed, findings = testsmellslib.discover([str(tmp)])
        self.assertEqual(findings, [])
        parsed_paths = {str(p) for p, _ in parsed}
        self.assertIn(str(real_path), parsed_paths)
        self.assertEqual(len(parsed_paths), 1)

    def test_broken_file_inside_a_directory_walk_still_surfaces(self):
        tmp = make_tmp(self)
        broken_path = write_module(tmp, "test_broken.py", PARSE_ERROR_SRC)
        findings = testsmellslib.run_checks([str(tmp)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "parse-error")
        self.assertEqual(findings[0]["file"], str(broken_path))

    def test_source_with_a_nul_byte_is_a_finding_not_a_crash(self):
        """Adversarial where: a NUL byte makes `ast.parse` raise `ValueError`,
        a different exception class from the ordinary `SyntaxError` path -
        easy to leave out of the except clause and crash the whole walk."""
        tmp = make_tmp(self)
        path = write_module(tmp, "test_nul.py", NUL_BYTE_SRC)
        findings = testsmellslib.run_checks([str(path)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["check"], "parse-error")
        self.assertEqual(findings[0]["severity"], testsmellslib.GATE)

    def test_explicit_file_included_even_when_a_directory_arg_saw_it_first(self):
        """Regression for the bug found during build: an explicit file
        argument used to be silently dropped whenever a directory argument
        earlier in the same run had already walked past it and rejected it
        for lacking a content signal - argument order must not matter."""
        tmp = make_tmp(self)
        helper_path = write_module(tmp, "helpers.py", HELPER_ONLY_SRC)
        parsed, findings = testsmellslib.discover([str(tmp), str(helper_path)])
        self.assertEqual(findings, [])
        parsed_paths = {str(p) for p, _ in parsed}
        self.assertIn(str(helper_path), parsed_paths)


# --------------------------------------------------------------------------
# regression pin: the three known-WEAK RosterTests
# --------------------------------------------------------------------------

class RegressionPinTests(unittest.TestCase):
    def test_roster_tests_are_named_by_literal_only(self):
        """Regression pin (D-05): the three known-WEAK tests in this repo's
        own RosterTests class must still be named by literal-only. Matched
        by test name, tolerant of line drift."""
        target = Path(__file__).parent / "test_modelslib.py"
        findings = testsmellslib.run_checks([str(target)])
        literal_only_tests = {f["test"] for f in findings if f["check"] == "literal-only"}
        for name in (
            "RosterTests.test_roster_matches_d03_assignments",
            "RosterTests.test_agent_files_are_the_13_known_agents",
            "RosterTests.test_tier_effort_defaults",
        ):
            self.assertIn(name, literal_only_tests)


# --------------------------------------------------------------------------
# CLI: commands.test_smells
# --------------------------------------------------------------------------

class CliTests(unittest.TestCase):
    def test_no_paths_is_a_usage_error_exit_1(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = test_smells.run(["--json"])
        self.assertEqual(code, 1)
        self.assertIn("at least one path", err.getvalue())

    def test_unknown_flag_is_exit_1(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = test_smells.run(["some/path", "--bogus"])
        self.assertEqual(code, 1)
        self.assertIn("unknown flag", err.getvalue())

    def test_gate_finding_exits_1(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_empty.py", EMPTY_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out.getvalue())

    def test_advisory_only_flag_suppresses_the_gate_exit(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_empty.py", EMPTY_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path), "--advisory-only"])
        self.assertEqual(code, 0)
        self.assertIn("PASS", out.getvalue())

    def test_clean_tree_exits_0(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_clean.py", CLEAN_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path)])
        self.assertEqual(code, 0)
        self.assertIn("no findings", out.getvalue())

    def test_unparseable_file_exits_1_naming_the_file(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_broken.py", PARSE_ERROR_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path)])
        self.assertEqual(code, 1)
        self.assertIn(str(path), out.getvalue())

    def test_json_output_is_pure_json_with_no_summary_line_mixed_in(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_empty.py", EMPTY_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path), "--json"])
        self.assertEqual(code, 1)
        rows = json.loads(out.getvalue())
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(
                set(row.keys()), {"line", "test", "check", "severity", "detail", "file"}
            )

    def test_advisory_only_findings_exit_0_without_the_flag(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_free.py", ASSERTION_FREE_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path)])
        self.assertEqual(code, 0)
        self.assertIn("PASS", out.getvalue())

    def test_nul_byte_source_exits_1_not_2(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_nul.py", NUL_BYTE_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path)])
        self.assertEqual(code, 1)

    def test_roulette_threshold_flag_is_applied(self):
        tmp = make_tmp(self)
        path = write_module(tmp, "test_roulette.py", ASSERTION_ROULETTE_SRC)
        out = io.StringIO()
        with redirect_stdout(out):
            code = test_smells.run([str(path), "--roulette-threshold", "3"])
        self.assertEqual(code, 0)
        self.assertIn("assertion-roulette", out.getvalue())

    def test_roulette_threshold_missing_value_is_exit_1(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = test_smells.run(["some/path", "--roulette-threshold"])
        self.assertEqual(code, 1)
        self.assertIn("--roulette-threshold", err.getvalue())

    def test_roulette_threshold_non_integer_is_exit_1(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = test_smells.run(["some/path", "--roulette-threshold", "abc"])
        self.assertEqual(code, 1)
        self.assertIn("integer", err.getvalue())

    def test_roulette_threshold_below_one_is_exit_1(self):
        err = io.StringIO()
        with redirect_stderr(err):
            code = test_smells.run(["some/path", "--roulette-threshold", "0"])
        self.assertEqual(code, 1)
        self.assertIn("--roulette-threshold", err.getvalue())


if __name__ == "__main__":
    unittest.main()
