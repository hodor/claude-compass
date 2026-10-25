"""Tests for `compass placement <artifact>` and `compass placement --hints`.

The report is read-only and built from the vault scan. It is scoped to the
artifact's own type dir (at the vault root, or inside the artifact's unit),
excludes the archive, and prints these sections: `parents:`, `pairs:`,
`domains:`, `redirect:` and `hint:`. Every candidate line names its evidence
(shared tags, shared title and summary terms, hint mentions, links), and
candidates rank by evidence count.

Adversarial themes: candidates leaking in from another type dir, another
unit or the archive; the artifact or a domain index listed as a candidate;
an artifact with no tags; evidence that only the hint or a wikilink
carries; hints naming a stem that has since moved or never existed; exit
codes that must stay 0 or 1; and a report that must never write.

The command module is imported lazily inside each test so a missing
implementation fails the individual test, not the whole module.
"""

import importlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maincli  # noqa: E402

SECTION_LABELS = ("parents", "pairs", "domains", "redirect", "hint")

SUBJECT = "SPEC-040-tide-chart-reading"
ALMANAC = "SPEC-010-nautical-almanac"


def doc(title, doc_type="spec", tags=None, summary=None, hint=None, body=""):
    """A vault document. `tags=None` omits the key; `tags=[]` writes an
    explicit empty list."""
    lines = ["---", f'title: "{title}"', f"type: {doc_type}", "status: approved",
             "area: workflow"]
    if tags is not None:
        lines.append(f"tags: [{', '.join(tags)}]")
    if summary is not None:
        lines.append(f'summary: "{summary}"')
    if hint is not None:
        lines.append(f'taxonomy_hint: "{hint}"')
    lines += ["created: 2026-08-30", "updated: 2026-08-30", "---", "", body, ""]
    return "\n".join(lines)


def domain_doc(name, class_here, elsewhere=None, tags=None):
    scope = [f"Class here: {class_here}"]
    if elsewhere:
        scope.append(f"Class elsewhere: {elsewhere}")
    lines = ["---", f'title: "{name}"', "type: domain", "status: active",
             f"tags: [{', '.join(tags if tags is not None else [name])}]",
             f'summary: "{class_here}"', "created: 2026-08-30",
             "updated: 2026-08-30", "---", "", f"# {name}", "", "## Scope", ""]
    return "\n".join(lines + scope + [""])


def unit_doc(name):
    return (f'---\ntitle: "{name}"\ntype: unit\nstatus: active\n'
            "created: 2026-08-30\nupdated: 2026-08-30\n---\n\nunit\n")


def sections(output):
    """Split report text into {label: [lines]}. A line that starts (after
    indentation) with `<label>:` opens that section and is its first line;
    every following line belongs to it until the next label."""
    result = {label: [] for label in SECTION_LABELS}
    current = None
    for raw in output.splitlines():
        stripped = raw.strip()
        for label in SECTION_LABELS:
            if stripped.startswith(label + ":"):
                current = label
                break
        if current is not None:
            result[current].append(stripped)
    return result


def lines_naming(section_lines, needle):
    return " ".join(line for line in section_lines if needle in line).lower()


def snapshot(root):
    state = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            state[path.relative_to(root).as_posix()] = (
                path.read_bytes(), path.stat().st_mtime_ns)
    return state


class PlacementCase(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.project = tmp / "project"
        self.root = self.project / ".compass"
        (self.root / "meta").mkdir(parents=True)
        for type_dir in ("specs", "research", "lessons", "decisions", "plans"):
            (self.root / type_dir).mkdir()
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(self.project)
        self.addCleanup(
            lambda: os.environ.__setitem__("CLAUDE_PROJECT_DIR", old) if old
            else os.environ.pop("CLAUDE_PROJECT_DIR", None)
        )

    def add(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_placement(self, args):
        module = importlib.import_module("commands.placement")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = module.run(args)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def report(self, artifact):
        code, out, err = self.run_placement([artifact])
        self.assertEqual(code, 0, err)
        return out, sections(out)


class ParentTests(PlacementCase):
    def test_parents_list_flat_and_folder_artifacts_with_their_evidence(self):
        """Adversarial where: a parent candidate listed without the reason it
        is there, or a folder spec skipped because only flat files were
        scanned. Each line must carry its own shared tag or title term."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading at sea", tags=["oceanography", "charts"],
            summary="reading tide charts with lunar influence"))
        self.add(f"specs/{ALMANAC}.md", doc(
            "Lunar cycles almanac", tags=["oceanography", "astronomy"],
            summary="almanac for sailors"))
        self.add("specs/SPEC-011-harbor-ops/index.md", doc(
            "Harbor operations", tags=["charts", "ports"], summary="port procedures"))
        _, secs = self.report(SUBJECT)
        flat_line = lines_naming(secs["parents"], ALMANAC)
        folder_line = lines_naming(secs["parents"], "SPEC-011-harbor-ops")
        self.assertIn("oceanography", flat_line)
        self.assertIn("lunar", flat_line)
        self.assertIn("charts", folder_line)

    def test_domain_index_is_never_a_parent(self):
        """Adversarial where: a domain folder's index.md is a folder-index
        record sharing the subject's tag; listing it as a parent would
        propose nesting a spec under a topic folder."""
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading", tags=["oceanography"]))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        self.add("specs/seafaring/index.md", domain_doc(
            "seafaring", "tide tables and harbour approaches", tags=["oceanography"]))
        _, secs = self.report(SUBJECT)
        self.assertIn(ALMANAC, " ".join(secs["parents"]))
        self.assertNotIn("seafaring", " ".join(secs["parents"]))

    def test_candidates_never_come_from_other_type_dirs_or_the_archive(self):
        """Adversarial where: scanning every type dir would offer a research
        note, lesson, ADR, plan or archived spec as a home for a spec."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography", "charts"]))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        outsiders = {
            "research/RESEARCH-ocean-notes.md": doc(
                "Tide chart reading", "research", tags=["oceanography", "charts"]),
            "lessons/LESSON-chart-habits.md": doc(
                "Tide chart reading", "lesson", tags=["oceanography", "charts"]),
            "decisions/ADR-001-chart-datum.md": doc(
                "Tide chart reading", "decision", tags=["oceanography", "charts"]),
            "plans/PLAN-001-tide-chart-reading.md": doc(
                "Tide chart reading", "plan", tags=["oceanography", "charts"]),
            "archive/specs/SPEC-099-archived-tides.md": doc(
                "Tide chart reading", tags=["oceanography", "charts"]),
        }
        for rel, text in outsiders.items():
            self.add(rel, text)
        out, _ = self.report(SUBJECT)
        self.assertIn(ALMANAC, out)
        for rel in outsiders:
            stem = Path(rel).stem
            with self.subTest(outsider=stem):
                self.assertNotIn(stem, out)

    def test_unit_artifact_sees_only_its_own_unit_and_root_artifact_sees_no_unit(self):
        """Adversarial where: root and unit type dirs share local numbering
        and tags; a report that merges them proposes parents from another
        unit's vocabulary."""
        self.add("orbit-lab/index.md", unit_doc("orbit-lab"))
        self.add("deep-sea/index.md", unit_doc("deep-sea"))
        self.add("orbit-lab/specs/SPEC-001-ion-thrusters.md", doc(
            "Ion thrusters", tags=["propulsion", "plasma"]))
        self.add("orbit-lab/specs/SPEC-002-plasma-cathodes.md", doc(
            "Plasma cathodes", tags=["propulsion"]))
        self.add("deep-sea/specs/SPEC-001-hull-plating.md", doc(
            "Hull plating", tags=["propulsion"]))
        self.add("specs/SPEC-010-orbit-notes.md", doc("Orbit notes", tags=["propulsion"]))
        self.add("specs/SPEC-011-root-subject.md", doc("Root subject", tags=["propulsion"]))

        out, secs = self.report("SPEC-001-ion-thrusters")
        with self.subTest(subject="unit"):
            self.assertIn("SPEC-002-plasma-cathodes", " ".join(secs["parents"]))
            self.assertNotIn("SPEC-010-orbit-notes", out)
            self.assertNotIn("SPEC-001-hull-plating", out)
        out, secs = self.report("SPEC-011-root-subject")
        with self.subTest(subject="root"):
            self.assertIn("SPEC-010-orbit-notes", " ".join(secs["parents"]))
            for stem in ("SPEC-001-ion-thrusters", "SPEC-002-plasma-cathodes",
                         "SPEC-001-hull-plating"):
                self.assertNotIn(stem, out)

    def test_artifact_never_lists_itself_as_parent_or_pair(self):
        """Adversarial where: the subject shares every tag, term, link and
        hint with itself, so a scan that forgets to drop it ranks it first."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography", "charts"],
            summary="reading tide charts",
            hint=f"sits beside {SUBJECT} at the specs root",
            body=f"Self reference [[{SUBJECT}]]."))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        _, secs = self.report(SUBJECT)
        self.assertIn(ALMANAC, " ".join(secs["parents"]))
        self.assertNotIn(SUBJECT, " ".join(secs["parents"]))
        self.assertNotIn(SUBJECT, " ".join(secs["pairs"]))

    def test_untagged_artifact_still_gets_candidates_from_title_terms(self):
        """Adversarial where: an artifact with no `tags:` key, or an explicit
        empty list, crashes the tag comparison or reports nothing even though
        a title term is shared."""
        self.add(f"specs/{ALMANAC}.md", doc("Lunar cycles almanac", tags=["astronomy"]))
        rows = {
            "missing-key": doc("Lunar chart reading"),
            "empty-list": doc("Lunar chart reading", tags=[]),
        }
        for name, text in rows.items():
            with self.subTest(case=name):
                self.add(f"specs/{SUBJECT}.md", text)
                _, secs = self.report(SUBJECT)
                self.assertIn("lunar", lines_naming(secs["parents"], ALMANAC))

    def test_links_count_as_evidence_in_either_direction(self):
        """Adversarial where: a candidate sharing no tag or term with the
        subject but wikilinked from it, or linking to it with an alias and
        heading, is dropped or listed without naming the link."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"],
            body="Builds on [[SPEC-020-outbound-target]]."))
        self.add("specs/SPEC-020-outbound-target.md", doc(
            "Zebra husbandry", tags=["unrelated-a"]))
        self.add("specs/SPEC-021-inbound-source.md", doc(
            "Quantum ledger", tags=["unrelated-b"],
            body=f"Cites [[{SUBJECT}#Problem|the tide spec]]."))
        _, secs = self.report(SUBJECT)
        self.assertIn("link", lines_naming(secs["parents"], "SPEC-020-outbound-target"))
        self.assertIn("link", lines_naming(secs["parents"], "SPEC-021-inbound-source"))

    def test_candidates_rank_by_evidence_count_and_header_says_count(self):
        """Adversarial where: ranking by filename or scan order instead of
        evidence count, or presenting the count as a validated score. The
        stems are chosen so descending evidence is neither alphabetical nor
        scan order."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography", "charts", "sailing"]))
        self.add("specs/SPEC-010-first-stem.md", doc("One", tags=["charts"]))
        self.add("specs/SPEC-011-second-stem.md", doc("Two", tags=["oceanography", "charts"]))
        self.add("specs/SPEC-012-mid-stem.md", doc(
            "Three", tags=["oceanography", "charts", "sailing"]))
        out, secs = self.report(SUBJECT)
        text = "\n".join(secs["parents"])
        order = [text.index(s) for s in
                 ("SPEC-012-mid-stem", "SPEC-011-second-stem", "SPEC-010-first-stem")]
        self.assertEqual(order, sorted(order))
        lowered = out.lower()
        self.assertIn("count", lowered)
        self.assertIn("validated", lowered)


class PairTests(PlacementCase):
    def test_pairs_are_same_level_artifacts_named_with_shared_parent_dir(self):
        """Adversarial where: a pair drawn from a different depth (a cousin
        in a nested domain, or a root artifact for a domain member) proposes
        a domain that could not be formed from siblings."""
        self.add("specs/seafaring/index.md", domain_doc("seafaring", "tides and waves"))
        self.add("specs/seafaring/deep/index.md", domain_doc("deep", "currents"))
        self.add("specs/seafaring/SPEC-040-tide-chart-reading.md", doc(
            "Tide chart reading", tags=["oceanography"]))
        self.add("specs/seafaring/SPEC-041-wave-tables.md", doc(
            "Wave tables", tags=["oceanography"]))
        self.add("specs/seafaring/deep/SPEC-042-deep-currents.md", doc(
            "Deep currents", tags=["oceanography"]))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        self.add("specs/SPEC-050-root-subject.md", doc("Root subject", tags=["oceanography"]))

        _, secs = self.report("SPEC-040-tide-chart-reading")
        with self.subTest(subject="inside-domain"):
            self.assertIn("seafaring", lines_naming(secs["pairs"], "SPEC-041-wave-tables"))
            self.assertNotIn("SPEC-042-deep-currents", " ".join(secs["pairs"]))
            self.assertNotIn(ALMANAC, " ".join(secs["pairs"]))
        _, secs = self.report("SPEC-050-root-subject")
        with self.subTest(subject="type-dir-root"):
            self.assertIn("specs", lines_naming(secs["pairs"], ALMANAC))
            self.assertNotIn("SPEC-041-wave-tables", " ".join(secs["pairs"]))


class DomainTests(PlacementCase):
    def test_domains_match_class_here_words_and_skip_unrelated_domains(self):
        """Adversarial where: matching every domain, or matching on the
        domain name only, instead of the words in its `Class here:` line."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading at sea", tags=["oceanography"],
            summary="reading tide charts while at sea"))
        self.add("specs/seafaring/index.md", domain_doc(
            "seafaring", "tide tables, sextant use, harbour approaches"))
        self.add("specs/aviation/index.md", domain_doc(
            "aviation", "flight planning, runway lighting"))
        _, secs = self.report(SUBJECT)
        self.assertIn("tide", lines_naming(secs["domains"], "seafaring"))
        self.assertNotIn("aviation", " ".join(secs["domains"]))

    def test_class_elsewhere_match_prints_redirect_to_the_named_domain(self):
        """Adversarial where: a `Class elsewhere:` line ignored, or treated
        as a Class-here match, so the subject is offered the very domain
        that says it does not file there. A non-matching Class-elsewhere
        must not redirect."""
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading at sea", tags=["oceanography"],
            summary="reading tide charts while at sea"))
        self.add("specs/lunar-almanacs/index.md", domain_doc(
            "lunar-almanacs", "moon phases, almanac data"))
        self.add("specs/inland-waters/index.md", domain_doc(
            "inland-waters", "canals and locks",
            elsewhere="tide charts -> [[specs/lunar-almanacs/index|lunar-almanacs]]"))
        self.add("specs/airfields/index.md", domain_doc("airfields", "runways"))
        self.add("specs/aviation/index.md", domain_doc(
            "aviation", "flight planning",
            elsewhere="runway lighting -> [[specs/airfields/index|airfields]]"))
        out, secs = self.report(SUBJECT)
        self.assertIn("lunar-almanacs", " ".join(secs["redirect"]))
        self.assertNotIn("inland-waters", " ".join(secs["domains"]))
        self.assertNotIn("airfields", out)


class HintTests(PlacementCase):
    def test_hint_section_prints_own_hint_and_current_path_of_every_named_stem(self):
        """Adversarial where: a hint written when its target sat at the specs
        root keeps naming a stem that has since moved into a domain; the
        report must print where each named stem lives now, not echo the
        stale prose. A hint naming a stem that never existed must not crash
        the report."""
        self.add("specs/conversation/SPEC-029-questions-clear.md", doc("Questions clear"))
        self.add("specs/SPEC-018-scaffolding-hidden.md", doc("Scaffolding hidden"))
        self.add("specs/SPEC-030-review-surface.md", doc(
            "Review surface",
            hint="the review surface; sits beside SPEC-029-questions-clear at the specs root"))
        self.add("specs/SPEC-031-two-stems.md", doc(
            "Two stems",
            hint="twostemsphrase between SPEC-029-questions-clear and SPEC-018-scaffolding-hidden"))
        self.add("specs/SPEC-032-ghost-stem.md", doc(
            "Ghost stem", hint="ghostphrase beside SPEC-777-never-existed"))
        _, moved = self.report("SPEC-030-review-surface")
        with self.subTest(case="moved-stem"):
            hint_text = " ".join(moved["hint"])
            self.assertIn("review surface", hint_text)
            self.assertIn("conversation/SPEC-029-questions-clear", hint_text)
        _, two = self.report("SPEC-031-two-stems")
        with self.subTest(case="every-named-stem"):
            hint_text = " ".join(two["hint"])
            self.assertIn("conversation/SPEC-029-questions-clear", hint_text)
            self.assertIn("SPEC-018-scaffolding-hidden", hint_text)
        _, ghost = self.report("SPEC-032-ghost-stem")
        with self.subTest(case="never-existed"):
            self.assertIn("ghostphrase", " ".join(ghost["hint"]))

    def test_hint_mentions_count_as_evidence_whichever_artifact_holds_the_hint(self):
        """Adversarial where: a candidate sharing nothing with the subject
        except a hint that names the other is dropped or listed without the
        word hint, whether the subject's hint names the candidate or the
        candidate's hint names the subject."""
        self.add("specs/SPEC-029-questions-clear.md", doc(
            "Zebra husbandry", tags=["unrelated-a"]))
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"],
            hint="sits beside SPEC-029-questions-clear at the specs root"))
        self.add("specs/SPEC-051-points-at-subject.md", doc(
            "Quantum ledger", tags=["unrelated-b"],
            hint=f"sits beside {SUBJECT} at the specs root"))
        _, secs = self.report(SUBJECT)
        self.assertIn("hint", lines_naming(secs["parents"], "SPEC-029-questions-clear"))
        self.assertIn("hint", lines_naming(secs["parents"], "SPEC-051-points-at-subject"))

    def test_hints_flag_reports_every_pending_hint_and_nothing_else(self):
        """Adversarial where: `--hints` stopping at the first hinted artifact,
        missing hints in a domain, another type dir or a unit, or reporting
        artifacts with an empty `taxonomy_hint`. Unhinted artifacts live in
        plans/ so they can never appear as candidates of a hinted spec."""
        self.add("orbit-lab/index.md", unit_doc("orbit-lab"))
        self.add("specs/seafaring/index.md", domain_doc("seafaring", "tides"))
        hinted = {
            "specs/SPEC-001-root-hinted.md": ("rootphrase", "SPEC-001-root-hinted"),
            "specs/seafaring/SPEC-002-domain-hinted.md": ("domainphrase", "SPEC-002-domain-hinted"),
            "research/RESEARCH-research-hinted.md": ("researchphrase", "RESEARCH-research-hinted"),
            "orbit-lab/specs/SPEC-003-unit-hinted.md": ("unitphrase", "SPEC-003-unit-hinted"),
        }
        for rel, (phrase, _) in hinted.items():
            self.add(rel, doc(Path(rel).stem, hint=f"{phrase} sits nowhere yet"))
        self.add("plans/PLAN-001-unhinted.md", doc("Unhinted", "plan"))
        self.add("plans/PLAN-002-empty-hint.md", doc("Empty hint", "plan", hint=""))
        code, out, err = self.run_placement(["--hints"])
        self.assertEqual(code, 0, err)
        for rel, (phrase, stem) in hinted.items():
            with self.subTest(hinted=stem):
                self.assertIn(phrase, out)
        self.assertNotIn("PLAN-001-unhinted", out)
        self.assertNotIn("PLAN-002-empty-hint", out)

    def test_hints_flag_with_no_pending_hint_exits_zero(self):
        """Adversarial where: an empty queue treated as an error, which would
        fail the consolidation step that reads the queue on a clean vault."""
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading", tags=["oceanography"]))
        code, out, err = self.run_placement(["--hints"])
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", out + err)


class OtherTypeTests(PlacementCase):
    def test_lesson_and_adr_are_placed_with_the_same_pairs_and_domains(self):
        """Adversarial where: placement hard-wired to specs, so a lesson or
        ADR gets no pairs or domains, or gets specs-dir candidates. Each row
        carries a same-tag spec that must not appear."""
        self.add("specs/SPEC-900-decoy-spec.md", doc(
            "Decoy", tags=["ticks", "eviction"], summary="rounding eviction ticks"))
        rows = [
            {
                "name": "lesson",
                "subject": "LESSON-tidal-rounding",
                "files": {
                    "lessons/LESSON-tidal-rounding.md": doc(
                        "Tidal rounding", "lesson", tags=["ticks", "drift"],
                        summary="rounding of clock ticks"),
                    "lessons/LESSON-clock-skew.md": doc(
                        "Clock skew", "lesson", tags=["ticks"]),
                    "lessons/clocks/index.md": domain_doc(
                        "clocks", "tick rounding, drift"),
                },
                "pair": "LESSON-clock-skew",
                "shared_tag": "ticks",
                "domain": "clocks",
            },
            {
                "name": "adr",
                "subject": "ADR-010-cache-eviction-policy",
                "files": {
                    "decisions/ADR-010-cache-eviction-policy.md": doc(
                        "Cache eviction policy", "decision", tags=["cache", "eviction"],
                        summary="chooses an eviction policy for the cache"),
                    "decisions/ADR-011-cache-sizing.md": doc(
                        "Cache sizing", "decision", tags=["eviction"]),
                    "decisions/performance/index.md": domain_doc(
                        "performance", "cache sizing, eviction, latency budgets"),
                },
                "pair": "ADR-011-cache-sizing",
                "shared_tag": "eviction",
                "domain": "performance",
            },
        ]
        for row in rows:
            for rel, text in row["files"].items():
                self.add(rel, text)
        for row in rows:
            with self.subTest(kind=row["name"]):
                out, secs = self.report(row["subject"])
                self.assertIn(row["shared_tag"], lines_naming(secs["pairs"], row["pair"]))
                self.assertIn(row["domain"], " ".join(secs["domains"]))
                self.assertNotIn("SPEC-900-decoy-spec", out)


class InvocationTests(PlacementCase):
    def test_artifact_may_be_named_by_vault_relative_path(self):
        """Adversarial where: only bare stems resolve, while the spec skill
        runs the command on the path of the draft it just wrote."""
        self.add(f"specs/{SUBJECT}.md", doc("Tide chart reading", tags=["oceanography"]))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        _, secs = self.report(f"specs/{SUBJECT}.md")
        self.assertIn(ALMANAC, " ".join(secs["parents"]))

    def test_exit_codes_are_zero_or_one_and_failures_print_no_report(self):
        """Adversarial where: an unresolvable stem, an ambiguous stem (the
        same name at the root and in a unit), a missing argument or an
        unknown flag exiting 2 (which would block the user's write) or
        returning 0 with a report for the wrong artifact."""
        self.add("orbit-lab/index.md", unit_doc("orbit-lab"))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        self.add("specs/SPEC-005-shared-name.md", doc("Shared", tags=["oceanography"]))
        self.add("orbit-lab/specs/SPEC-005-shared-name.md", doc("Shared", tags=["oceanography"]))
        rows = [
            ("resolvable", [ALMANAC], 0),
            ("unresolvable", ["SPEC-404-missing"], 1),
            ("ambiguous", ["SPEC-005-shared-name"], 1),
            ("no-argument", [], 1),
            ("unknown-flag", ["--bogus"], 1),
        ]
        for name, args, expected in rows:
            with self.subTest(case=name):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    try:
                        code = maincli.main(["placement"] + args)
                    except SystemExit as exc:
                        code = exc.code
                self.assertEqual(code, expected, err.getvalue())
                if expected == 0:
                    self.assertIn("parents:", out.getvalue())
                else:
                    self.assertNotIn("parents:", out.getvalue())

    def test_placement_is_a_registered_command(self):
        """Adversarial where: the module exists but is absent from the
        command table, so bare `compass` never lists it."""
        help_text = maincli.build_parser().format_help()
        self.assertIn("placement", help_text)


class ReadOnlyTests(PlacementCase):
    def test_reports_never_change_any_file_in_the_vault(self):
        """Adversarial where: a report that writes (a cache, a usage row, a
        normalised frontmatter, a created domain) when the human has not
        approved a move. Runs the single-artifact, hints and failing forms."""
        self.add("orbit-lab/index.md", unit_doc("orbit-lab"))
        self.add("specs/seafaring/index.md", domain_doc("seafaring", "tide tables"))
        self.add(f"specs/{SUBJECT}.md", doc(
            "Tide chart reading", tags=["oceanography"],
            hint="sits beside SPEC-010-nautical-almanac at the specs root"))
        self.add(f"specs/{ALMANAC}.md", doc("Lunar almanac", tags=["oceanography"]))
        self.add("orbit-lab/specs/SPEC-001-ion-thrusters.md", doc("Ion", tags=["oceanography"]))
        before = snapshot(self.project)
        codes = [self.run_placement(args)[0] for args in (
            [SUBJECT], ["--hints"], ["SPEC-404-missing"], ["SPEC-001-ion-thrusters"])]
        self.assertEqual(codes, [0, 0, 1, 0])
        self.assertEqual(snapshot(self.project), before)


if __name__ == "__main__":
    unittest.main()
