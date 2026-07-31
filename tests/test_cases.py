"""Tests for the branching case format, loader and graph validation.

    python tests/test_cases.py

The validator is the specification made executable. It caught a dangling node
reference and two unreachable endings on its first run against real content,
which is the standard it needs to keep meeting as the library grows.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import cases as C, loader  # noqa: E402


def minimal(**overrides):
    """A valid two-decision case, for mutating into invalid ones."""
    case = {
        "id": "t-case", "title": "Test Case", "domain": "5", "section": "A",
        "topics": ["Data Encryption"], "principles": [], "minutes": 5,
        "opening": "You arrive on site.",
        "taints": {},
        "nodes": {
            "start": {
                "situation": "Something is wrong.", "prompt": "What now?",
                "options": [
                    {"key": "A", "text": "Escalate.", "quality": "best",
                     "next": "second", "consequence": "You escalate.", "why": "Correct."},
                    {"key": "B", "text": "Wait.", "quality": "poor",
                     "next": "end-weak", "consequence": "Time passes.", "why": "Delay costs."},
                ],
            },
            "second": {
                "situation": "They responded.", "prompt": "And now?",
                "options": [
                    {"key": "A", "text": "Report it.", "quality": "best",
                     "next": "end-strong", "consequence": "Reported.", "why": "Right."},
                    {"key": "B", "text": "Drop it.", "quality": "poor",
                     "next": "end-weak", "consequence": "Dropped.", "why": "Wrong."},
                ],
            },
        },
        "endings": {
            "end-strong": {"title": "Good", "verdict": "strong",
                           "narrative": "It went well.", "why": "You escalated."},
            "end-weak": {"title": "Poor", "verdict": "weak",
                         "narrative": "It went badly.", "why": "You waited."},
        },
    }
    case.update(overrides)
    return C.Case(source_file="t-case.json", **case)


class TestShippedCases(unittest.TestCase):
    def setUp(self):
        self.cases = C.load_cases("cisa")
        self.outline = loader.load_outline("cisa")
        self.pids = {p["id"] for p in loader.load_principles("cisa")}

    def test_the_shipped_cases_are_valid(self):
        errors, warnings = C.validate_all(self.cases, self.outline, self.pids)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_there_are_cases_across_multiple_domains(self):
        domains = {c.domain for c in self.cases}
        self.assertGreaterEqual(len(self.cases), 3)
        self.assertGreaterEqual(len(domains), 3,
                                "cases should span domains, not cluster in one")

    def test_every_shipped_case_declares_its_origin(self):
        for case in self.cases:
            self.assertIn("Original", case.origin,
                          "%s must state that the scenario is original" % case.id)

    def test_every_node_offers_a_defensibly_correct_action(self):
        for case in self.cases:
            for nid in case.nodes:
                self.assertIsNotNone(case.best_option(nid),
                                     "%s node %s has no 'best' option" % (case.id, nid))

    def test_consequences_never_deliver_the_verdict(self):
        """Judgment belongs in `why`, shown at debrief. A consequence that says
        'which was a mistake' turns the case back into a quiz."""
        tells = ("was a mistake", "was wrong", "incorrect", "you should have",
                 "this was poor", "good choice", "correct choice")
        for case in self.cases:
            for nid, node in case.nodes.items():
                for opt in node["options"]:
                    text = opt["consequence"].lower()
                    for tell in tells:
                        self.assertNotIn(tell, text,
                                         "%s %s/%s leaks the verdict into the consequence"
                                         % (case.id, nid, opt["key"]))

    def test_cases_are_a_reasonable_length(self):
        for case in self.cases:
            self.assertGreaterEqual(len(case.nodes), 4, "%s is too short" % case.id)
            self.assertLessEqual(len(case.nodes), 12, "%s is too long" % case.id)


class TestLoading(unittest.TestCase):
    def test_missing_directory_returns_nothing_rather_than_failing(self):
        self.assertEqual(C.load_cases("does-not-exist"), [])

    def test_malformed_json_is_reported_with_the_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = os.path.join(tmp, "cisa", "cases")
            os.makedirs(directory)
            with open(os.path.join(directory, "broken.json"), "w", encoding="utf-8") as fh:
                fh.write("{not json")
            original = C.cert_dir
            try:
                C.cert_dir = lambda cert: os.path.join(tmp, "cisa")  # type: ignore
                with self.assertRaises(C.CaseError) as ctx:
                    C.load_cases("cisa")
                self.assertIn("broken.json", str(ctx.exception))
            finally:
                C.cert_dir = original  # type: ignore

    def test_unknown_fields_are_ignored_rather_than_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = os.path.join(tmp, "cisa", "cases")
            os.makedirs(directory)
            payload = {"id": "x", "title": "T", "domain": "5", "opening": "o",
                       "nodes": {}, "endings": {}, "invented_field": 1}
            with open(os.path.join(directory, "x.json"), "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            original = C.cert_dir
            try:
                C.cert_dir = lambda cert: os.path.join(tmp, "cisa")  # type: ignore
                loaded = C.load_cases("cisa")
                self.assertEqual(loaded[0].id, "x")
            finally:
                C.cert_dir = original  # type: ignore


class TestValidation(unittest.TestCase):
    def _errors(self, case, **kw):
        return C.validate_case(case, **kw)[0]

    def _warnings(self, case, **kw):
        return C.validate_case(case, **kw)[1]

    def test_a_clean_case_passes(self):
        self.assertEqual(self._errors(minimal()), [])

    def test_a_dangling_next_is_an_error(self):
        case = minimal()
        case.nodes["start"]["options"][0]["next"] = "nowhere"
        self.assertTrue(any("unknown 'nowhere'" in e for e in self._errors(case)))

    def test_a_node_with_one_option_is_not_a_decision(self):
        case = minimal()
        case.nodes["start"]["options"] = case.nodes["start"]["options"][:1]
        self.assertTrue(any("at least two options" in e for e in self._errors(case)))

    def test_a_node_with_no_best_option_is_an_error(self):
        case = minimal()
        for opt in case.nodes["start"]["options"]:
            opt["quality"] = "defensible"
        self.assertTrue(any("no option marked 'best'" in e for e in self._errors(case)))

    def test_two_best_options_warn(self):
        case = minimal()
        for opt in case.nodes["start"]["options"]:
            opt["quality"] = "best"
        self.assertTrue(any("more than one option marked 'best'" in w
                            for w in self._warnings(case)))

    def test_an_invalid_quality_is_an_error(self):
        case = minimal()
        case.nodes["start"]["options"][0]["quality"] = "excellent"
        self.assertTrue(any("is not one of" in e for e in self._errors(case)))

    def test_duplicate_option_keys_are_an_error(self):
        case = minimal()
        case.nodes["start"]["options"][1]["key"] = "A"
        self.assertTrue(any("duplicate option keys" in e for e in self._errors(case)))

    def test_a_missing_option_field_is_an_error(self):
        case = minimal()
        del case.nodes["start"]["options"][0]["why"]
        self.assertTrue(any("missing 'why'" in e for e in self._errors(case)))

    def test_a_missing_start_node_is_an_error(self):
        case = minimal()
        case.nodes.pop("start")
        self.assertTrue(any("no 'start' node" in e for e in self._errors(case)))

    def test_a_cycle_is_an_error(self):
        case = minimal()
        case.nodes["second"]["options"][0]["next"] = "start"
        self.assertTrue(any("cycle" in e for e in self._errors(case)))

    def test_an_unreachable_node_warns(self):
        case = minimal()
        case.nodes["orphan"] = copy.deepcopy(case.nodes["second"])
        self.assertTrue(any("cannot be reached from start" in w
                            for w in self._warnings(case)))

    def test_an_unreachable_ending_warns(self):
        case = minimal()
        case.endings["end-nobody-gets-here"] = {
            "title": "T", "verdict": "failed", "narrative": "n", "why": "w"}
        self.assertTrue(any("end-nobody-gets-here" in w for w in self._warnings(case)))

    def test_an_ending_reachable_only_by_taint_does_not_warn(self):
        case = minimal()
        case.endings["end-tainted"] = {
            "title": "T", "verdict": "failed", "narrative": "n", "why": "w"}
        case.taints = {"fatal": "end-tainted"}
        case.nodes["start"]["options"][1]["taint"] = "fatal"
        self.assertFalse(any("end-tainted" in w for w in self._warnings(case)))

    def test_an_undeclared_taint_is_an_error(self):
        case = minimal()
        case.nodes["start"]["options"][0]["taint"] = "mystery"
        self.assertTrue(any("undeclared taint 'mystery'" in e for e in self._errors(case)))

    def test_a_taint_pointing_nowhere_is_an_error(self):
        case = minimal(taints={"fatal": "end-missing"})
        case.nodes["start"]["options"][1]["taint"] = "fatal"
        self.assertTrue(any("unknown ending 'end-missing'" in e for e in self._errors(case)))

    def test_an_inert_taint_warns(self):
        """A taint whose option already leads to the taint's ending cannot
        change anything, so `overridden` is permanently false and the debrief
        silently loses its most useful sentence. Found in real content."""
        case = minimal(taints={"fatal": "end-weak"})
        case.nodes["start"]["options"][1]["taint"] = "fatal"   # already next=end-weak
        self.assertTrue(any("is inert" in w for w in self._warnings(case)))

    def test_a_taint_that_can_override_does_not_warn(self):
        case = minimal(taints={"fatal": "end-weak"})
        case.nodes["start"]["options"][0]["taint"] = "fatal"   # next=second, so it fires
        self.assertFalse(any("is inert" in w for w in self._warnings(case)))

    def test_no_shipped_taint_is_inert(self):
        for case in C.load_cases("cisa"):
            inert = [w for w in C.validate_case(case)[1] if "is inert" in w]
            self.assertEqual(inert, [], "%s has a taint that cannot fire" % case.id)

    def test_a_declared_but_unused_taint_warns(self):
        case = minimal(taints={"fatal": "end-weak"})
        self.assertTrue(any("no option applies it" in w for w in self._warnings(case)))

    def test_an_invalid_verdict_is_an_error(self):
        case = minimal()
        case.endings["end-weak"]["verdict"] = "mediocre"
        self.assertTrue(any("verdict 'mediocre'" in e for e in self._errors(case)))

    def test_an_unknown_topic_is_an_error(self):
        case = minimal(topics=["Underwater Basket Weaving"])
        errors = self._errors(case, outline=loader.load_outline("cisa"))
        self.assertTrue(any("not in the outline" in e for e in errors))

    def test_an_unknown_principle_is_an_error(self):
        case = minimal(principles=["invented-rule"])
        errors = self._errors(case, principle_ids={"contain-first"})
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_a_filename_mismatch_warns(self):
        case = minimal()
        case.source_file = "something-else.json"
        self.assertTrue(any("does not match filename" in w for w in self._warnings(case)))

    def test_duplicate_case_ids_across_files_are_an_error(self):
        a, b = minimal(), minimal()
        b.source_file = "other.json"
        errors, _ = C.validate_all([a, b])
        self.assertTrue(any("duplicate case id" in e for e in errors))


class TestGraphAnalysis(unittest.TestCase):
    def test_reachability_walks_the_whole_graph(self):
        nodes, endings = C.reachable(minimal())
        self.assertEqual(nodes, {"start", "second"})
        self.assertEqual(endings, {"end-strong", "end-weak"})

    def test_longest_path_counts_decisions_not_nodes_visited(self):
        self.assertEqual(C.longest_path(minimal()), 2)

    def test_option_lookup_is_case_insensitive(self):
        case = minimal()
        self.assertEqual(case.option("start", "a")["key"], "A")
        self.assertIsNone(case.option("start", "Z"))

    def test_the_shipped_cases_have_sensible_depth(self):
        for case in C.load_cases("cisa"):
            depth = C.longest_path(case)
            self.assertGreaterEqual(depth, 3, "%s resolves too quickly" % case.id)
            self.assertLessEqual(depth, 10, "%s is a novel, not a case" % case.id)


class TestScoring(unittest.TestCase):
    def _steps(self, *qualities, taint=None):
        return [C.PathStep(node_id="n%d" % i, chosen="A", quality=q, best_key="A",
                           taint=taint if i == 0 else None)
                for i, q in enumerate(qualities)]

    def test_a_clean_path_reports_its_profile(self):
        result = C.score_path(minimal(), self._steps("best", "best"), "end-strong")
        self.assertEqual(result["counts"], {"best": 2, "defensible": 0, "poor": 0})
        self.assertEqual(result["verdict"], "strong")
        self.assertFalse(result["overridden"])

    def test_a_taint_overrides_wherever_the_graph_led(self):
        case = minimal(taints={"fatal": "end-weak"})
        result = C.score_path(case, self._steps("best", "best", taint="fatal"), "end-strong")
        self.assertEqual(result["ending"], "end-weak")
        self.assertTrue(result["overridden"],
                        "the debrief must be able to say the outcome was fixed earlier")

    def test_taint_precedence_follows_declaration_order(self):
        case = minimal(taints={"worst": "end-weak", "bad": "end-strong"})
        steps = [C.PathStep("n0", "A", "poor", "A", taint="bad"),
                 C.PathStep("n1", "A", "poor", "A", taint="worst")]
        result = C.score_path(case, steps, "end-strong")
        self.assertEqual(result["ending"], "end-weak",
                         "the author orders taints by severity; worst declared first wins")

    def test_scoring_is_a_profile_not_a_percentage(self):
        result = C.score_path(minimal(), self._steps("best", "poor"), "end-weak")
        self.assertNotIn("score", result)
        self.assertNotIn("percentage", result)
        self.assertIn("counts", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
