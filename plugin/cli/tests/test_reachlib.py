"""Tests for reachlib: coverage report parsing, diff line extraction, and the
reach verdict.

Public contract exercised here:

    is_test_path(path) -> bool
    changed_lines_from_diff(diff_text) -> {repo-relative POSIX path: [new-side line numbers]}
        for added and changed lines of non-test files, from `git diff -U0` text
    repo_relative(report_path, repo_root=None) -> repo-relative POSIX path
    parse_lcov(text, repo_root=None) / parse_cobertura(text, repo_root=None) / parse_report(text, repo_root=None)
        -> {path: {"lines": {lineno: hits}, "functions": [(name, line, hits), ...]}}
    evaluate(coverage, changed) -> {"verdict": "PASS" | "FINDING" | "SKIP" | "N/A",
        "reason": str | None,
        "files": [{"path", "run", "total", "unrun": [lines], "unreached_functions": [names]}]}
        `coverage` is None when no report exists; `changed` is the diff mapping.

Adversarial themes: substring matches on test-path patterns, CRLF and
path-with-space diff headers, silent fallbacks that read as 0% or PASS, and
line-run coverage that hides an unreached one-line function.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reachlib  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "reach"


def nonempty(mapping):
    return {path: lines for path, lines in mapping.items() if lines}


def cov(lines, functions=()):
    return {"lines": dict(lines), "functions": list(functions)}


class IsTestPathTests(unittest.TestCase):
    def test_test_path_patterns(self):
        """Adversarial where: a substring match ('test' anywhere) would drop real
        source such as contest.py or attests/ from the diff, hiding unrun lines;
        a missed pattern would count test files as changed source."""
        rows = [
            ("tests/a.py", True),
            ("plugin/cli/tests/a.py", True),
            ("test_a.py", True),
            ("src/test_a.py", True),
            ("src/a_test.py", True),
            ("src/a_test.go", True),
            ("web/a.test.js", True),
            ("web/a.test.tsx", True),
            ("web/a.spec.ts", True),
            ("src/app.py", False),
            ("src/contest.py", False),
            ("src/attests/a.py", False),
            ("contest/a.py", False),
            ("src/testing.py", False),
            ("src/mytest.py", False),
            ("src/aspec.js", False),
        ]
        for path, expected in rows:
            with self.subTest(path=path):
                self.assertIs(reachlib.is_test_path(path), expected)


class ChangedLinesTests(unittest.TestCase):
    def test_changed_lines_from_unified_zero_diff(self):
        """Adversarial where: hunk headers with an omitted count, a zero count
        (pure deletion), a deleted file, test files, CRLF line endings and a
        space-bearing path are each a way to misattribute or lose changed lines."""
        rows = {
            "added block": (
                "diff --git a/src/a.py b/src/a.py\n"
                "--- a/src/a.py\n+++ b/src/a.py\n"
                "@@ -1,0 +2,3 @@\n+x\n+y\n+z\n",
                {"src/a.py": [2, 3, 4]},
            ),
            "omitted count means one line": (
                "--- a/src/a.py\n+++ b/src/a.py\n@@ -5 +5 @@\n-old\n+new\n",
                {"src/a.py": [5]},
            ),
            "pure deletion has no new-side lines": (
                "--- a/src/a.py\n+++ b/src/a.py\n@@ -5,2 +4,0 @@\n-gone\n-gone2\n",
                {},
            ),
            "changed run": (
                "--- a/src/a.py\n+++ b/src/a.py\n@@ -7,2 +7,2 @@\n-a\n-b\n+c\n+d\n",
                {"src/a.py": [7, 8]},
            ),
            "several hunks, several files": (
                "--- a/src/a.py\n+++ b/src/a.py\n"
                "@@ -1 +1 @@\n-a\n+b\n"
                "@@ -10,0 +11,2 @@\n+c\n+d\n"
                "--- a/src/b.js\n+++ b/src/b.js\n"
                "@@ -3 +3 @@\n-a\n+b\n",
                {"src/a.py": [1, 11, 12], "src/b.js": [3]},
            ),
            "no-newline marker is not a line": (
                "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-a\n"
                "\\ No newline at end of file\n+b\n"
                "\\ No newline at end of file\n",
                {"src/a.py": [1]},
            ),
            "deleted file": (
                "--- a/src/old.py\n+++ /dev/null\n@@ -1,3 +0,0 @@\n-a\n-b\n-c\n",
                {},
            ),
            "test files dropped, source kept": (
                "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -1 +1 @@\n-a\n+b\n"
                "--- a/src/a.py\n+++ b/src/a.py\n@@ -2 +2 @@\n-a\n+b\n"
                "--- a/web/a.spec.ts\n+++ b/web/a.spec.ts\n@@ -1 +1 @@\n-a\n+b\n",
                {"src/a.py": [2]},
            ),
            "only test files": (
                "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -1 +1 @@\n-a\n+b\n",
                {},
            ),
            "CRLF diff": (
                "diff --git a/src/a.py b/src/a.py\r\n"
                "--- a/src/a.py\r\n+++ b/src/a.py\r\n"
                "@@ -1,0 +4,2 @@\r\n+x\r\n+y\r\n",
                {"src/a.py": [4, 5]},
            ),
            "path with a space carries a trailing tab": (
                "--- a/my dir/a.py\t\n+++ b/my dir/a.py\t\n@@ -1 +1 @@\n-a\n+b\n",
                {"my dir/a.py": [1]},
            ),
            "empty diff": ("", {}),
        }
        for name, (diff, expected) in rows.items():
            with self.subTest(case=name):
                self.assertEqual(
                    nonempty(reachlib.changed_lines_from_diff(diff)), expected
                )


class RepoRelativeTests(unittest.TestCase):
    def test_report_paths_map_to_repo_relative_posix(self):
        """Adversarial where: a Windows-style or absolute report path that is not
        normalized never matches the diff's POSIX path, so measured files read
        as missed (SKIP) or unmeasured."""
        rows = [
            ("src/app.py", "/work/proj", "src/app.py"),
            ("src\\app.py", "/work/proj", "src/app.py"),
            ("./src/app.py", "/work/proj", "src/app.py"),
            ("/work/proj/src/app.py", "/work/proj", "src/app.py"),
            ("/work/proj/src/app.py", "/work/proj/", "src/app.py"),
            ("C:\\work\\proj\\src\\app.py", "C:/work/proj", "src/app.py"),
            ("c:\\work\\proj\\src\\app.py", "C:/work/proj", "src/app.py"),
            ("C:\\work\\proj\\src\\app.py", "C:\\work\\proj", "src/app.py"),
            ("src\\sub dir\\app.py", None, "src/sub dir/app.py"),
        ]
        for report_path, root, expected in rows:
            with self.subTest(path=report_path, root=root):
                self.assertEqual(reachlib.repo_relative(report_path, root), expected)

    def test_sibling_directory_sharing_a_root_prefix_is_not_stripped(self):
        """Adversarial where: stripping the repo root as a plain string prefix turns
        /work/proj2/src/app.py into 2/src/app.py instead of leaving it outside
        the repo."""
        mapped = reachlib.repo_relative("/work/proj2/src/app.py", "/work/proj")
        self.assertNotEqual(mapped, "2/src/app.py")
        self.assertNotEqual(mapped, "src/app.py")


class ParseLcovTests(unittest.TestCase):
    def test_lcov_records(self):
        """Adversarial where: DA hits read from the wrong field, FNDA names split
        on every comma, CRLF leaving a carriage return in a path, repeated SF
        records overwriting a run line with an unrun one."""
        text = (FIXTURES / "lcov_c8.info").read_text(encoding="utf-8")
        parsed = reachlib.parse_lcov(text)
        self.assertEqual(
            parsed["src/route.js"]["lines"], {1: 1, 3: 5, 4: 5}
        )
        self.assertEqual(
            sorted(parsed["src/route.js"]["functions"]),
            [("exports.routeDead", 1, 0), ("exports.routeNew", 3, 5)],
        )
        self.assertEqual(parsed["src/util.js"]["lines"], {2: 0})

    def test_lcov_edge_records(self):
        """Adversarial where: CRLF leaving a carriage return in a path, FNDA names
        split on every comma, repeated SF records overwriting a run line with an
        unrun one."""
        text = (FIXTURES / "lcov_c8.info").read_text(encoding="utf-8")
        crlf = reachlib.parse_lcov(text.replace("\n", "\r\n"))
        self.assertEqual(sorted(crlf), ["src/route.js", "src/util.js"])
        self.assertEqual(crlf["src/route.js"]["lines"], {1: 1, 3: 5, 4: 5})

        comma = reachlib.parse_lcov(
            "SF:a.cc\nFN:5,ns::f(int,int)\nFNDA:0,ns::f(int,int)\nDA:5,0,abc123\nend_of_record\n"
        )
        self.assertEqual(comma["a.cc"]["functions"], [("ns::f(int,int)", 5, 0)])
        self.assertEqual(comma["a.cc"]["lines"], {5: 0})

        merged = reachlib.parse_lcov(
            "SF:a.py\nDA:3,0\nend_of_record\nSF:a.py\nDA:3,2\nDA:4,0\nend_of_record\n"
        )
        self.assertGreater(merged["a.py"]["lines"][3], 0)
        self.assertEqual(merged["a.py"]["lines"][4], 0)

    def test_lcov_empty_text_has_no_files(self):
        """Adversarial where: an empty report parsed into a placeholder file entry
        would later read as measured-but-0%."""
        self.assertEqual(reachlib.parse_lcov(""), {})

    def test_lcov_maps_paths_with_repo_root(self):
        """Adversarial where: an absolute SF path ignoring repo_root never matches
        the diff."""
        parsed = reachlib.parse_lcov(
            "SF:/work/proj/src/a.js\nDA:1,1\nend_of_record\n", repo_root="/work/proj"
        )
        self.assertEqual(list(parsed), ["src/a.js"])


class ParseCoberturaTests(unittest.TestCase):
    def test_cobertura_documents(self):
        """Adversarial where: an XML declaration with an encoding in a str input
        raises in ElementTree; repeated class elements for one file dropping all
        but the last; backslash filenames left unmapped."""
        plain = reachlib.parse_cobertura(
            (FIXTURES / "coverage_py.xml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            plain["src/app.py"]["lines"], {1: 1, 3: 7, 4: 7, 6: 0, 7: 0}
        )

        declared = reachlib.parse_cobertura(
            (FIXTURES / "coverage_decl.xml").read_text(encoding="utf-8")
        )
        self.assertEqual(list(declared), ["src/front.ts"])
        self.assertEqual(
            declared["src/front.ts"]["lines"], {10: 3, 11: 3, 20: 0, 21: 0}
        )

    def test_cobertura_without_classes_has_no_files(self):
        """Adversarial where: a report with packages but no classes parsed into a
        placeholder entry would read as measured."""
        text = '<?xml version="1.0" ?><coverage><packages/></coverage>'
        self.assertEqual(reachlib.parse_cobertura(text), {})


class ParseReportTests(unittest.TestCase):
    def test_format_is_detected_from_content(self):
        """Adversarial where: sniffing by file extension, or by the first byte
        without skipping whitespace, sends a report to the wrong parser."""
        lcov = (FIXTURES / "lcov_c8.info").read_text(encoding="utf-8")
        xml = (FIXTURES / "coverage_py.xml").read_text(encoding="utf-8")
        self.assertEqual(reachlib.parse_report(lcov), reachlib.parse_lcov(lcov))
        self.assertEqual(reachlib.parse_report(xml), reachlib.parse_cobertura(xml))
        self.assertEqual(
            reachlib.parse_report("\n\n  " + xml), reachlib.parse_cobertura(xml)
        )
        self.assertEqual(reachlib.parse_report(""), {})


class EvaluateTests(unittest.TestCase):
    def test_verdicts(self):
        """Adversarial where: a threshold or percentage hiding one unrun line, a
        line-covered one-line function that never ran, a missing or foreign
        report read as 0% or PASS, non-executable changed lines inflating the
        total."""
        all_run = cov({1: 1, 2: 4})
        hundred = cov({n: 1 for n in range(1, 101)})
        hundred["lines"][57] = 0
        arrow = cov(
            {1: 1, 3: 5, 4: 5},
            [("exports.routeDead", 1, 0), ("exports.routeNew", 3, 5)],
        )
        rows = {
            "all changed lines run": (
                {"a.py": all_run}, {"a.py": [1, 2]}, "PASS", None,
                {"a.py": (2, 2, [], [])},
            ),
            "one of two unrun": (
                {"a.py": cov({1: 1, 2: 0})}, {"a.py": [1, 2]}, "FINDING", None,
                {"a.py": (1, 2, [2], [])},
            ),
            "99 of 100 run is still a finding": (
                {"a.py": hundred}, {"a.py": list(range(1, 101))}, "FINDING", None,
                {"a.py": (99, 100, [57], [])},
            ),
            "non-executable changed lines are not counted": (
                {"a.py": cov({2: 1, 3: 1})}, {"a.py": [1, 2, 3]}, "PASS", None,
                {"a.py": (2, 2, [], [])},
            ),
            "line run but function unreached": (
                {"r.js": arrow}, {"r.js": [1, 3, 4]}, "FINDING", None,
                {"r.js": (3, 3, [], ["exports.routeDead"])},
            ),
            "unreached function on an unchanged line is not named": (
                {"r.js": arrow}, {"r.js": [3, 4]}, "PASS", None,
                {"r.js": (2, 2, [], [])},
            ),
            "two files, one clean one not": (
                {"a.py": all_run, "b.py": cov({1: 0})},
                {"a.py": [1, 2], "b.py": [1]}, "FINDING", None,
                {"a.py": (2, 2, [], []), "b.py": (0, 1, [1], [])},
            ),
            "no report": (
                None, {"a.py": [1]}, "SKIP", "no measurement", None,
            ),
            "empty report": (
                {}, {"a.py": [1]}, "SKIP", "no measurement", None,
            ),
            "report names other files": (
                {"other.py": all_run}, {"a.py": [1]}, "SKIP",
                "measurement missed the changed files", None,
            ),
            "no changed lines": (
                {"a.py": all_run}, {}, "N/A", None, None,
            ),
            "only non-executable changed lines": (
                {"a.py": cov({10: 1})}, {"a.py": [1, 2]}, "N/A", None, None,
            ),
            "nothing changed outside tests, report names other files": (
                {"other.py": all_run}, {}, "N/A", None, None,
            ),
        }
        for name, (coverage, changed, verdict, reason, files) in rows.items():
            with self.subTest(case=name):
                result = reachlib.evaluate(coverage, changed)
                self.assertEqual(result["verdict"], verdict)
                if reason is not None:
                    self.assertEqual(result["reason"], reason)
                if files is not None:
                    by_path = {f["path"]: f for f in result["files"]}
                    for path, (run, total, unrun, unreached) in files.items():
                        entry = by_path[path]
                        self.assertEqual(
                            (entry["run"], entry["total"]), (run, total)
                        )
                        self.assertEqual(sorted(entry["unrun"]), unrun)
                        self.assertEqual(
                            sorted(entry["unreached_functions"]), unreached
                        )


if __name__ == "__main__":
    unittest.main()
