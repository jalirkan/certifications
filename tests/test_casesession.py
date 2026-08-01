"""Tests for running a branching case.

Three of these matter more than the rest, and each guards a rule that the
feature is pointless without:

* `quality` and `why` must not reach the client before the debrief. If the
  browser can see which option is best, a case is a multiple-choice question
  with extra narration.
* a case must never write to `attempts.jsonl`. Letting a case reach item
  analysis or the spaced-repetition scheduler would corrupt both.
* a taint must override wherever the graph led, and the debrief must name the
  decision that did it. That sentence is the most valuable output of the whole
  feature.

    python tests/test_casesession.py
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import cases as cases_mod  # noqa: E402
from drillkit import casesession, loader, store  # noqa: E402
from drillkit.webapi import Api  # noqa: E402

# Anything that would give away the grading before the debrief.
SECRET_FIELDS = ("quality", "why", "taint", "verdict", "narrative", "best_key")


class CaseTestBase(unittest.TestCase):
    """Each test gets its own profile so nothing touches real study history."""

    def setUp(self):
        self.profile = "casetest-%s" % os.urandom(4).hex()
        self.api = Api("cisa", self.profile)
        self.cases = {c.id: c for c in cases_mod.load_cases("cisa")}
        self.results_path = self.api.results_path
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        directory = loader.results_dir("cisa", self.profile)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)

    def play(self, case_id, keys):
        """Walk a case by option key and return (state, case)."""
        case = self.cases[case_id]
        state = casesession.start(case, "cisa")
        for key in keys:
            casesession.choose(case, state, state.current, key, seconds=5.0)
        return state, case


class TestTheRunRevealsNothing(CaseTestBase):
    """The rule the feature depends on."""

    def test_public_option_is_an_allow_list(self):
        case = self.cases["d5-encrypted-share"]
        raw = case.node("start")["options"][0]
        self.assertIn("why", raw, "fixture must have something to leak")
        public = casesession.public_option(raw)
        self.assertEqual(set(public), {"key", "text"})

    def test_no_payload_during_the_run_carries_grading(self):
        for case_id, keys in (("d1-one-exception", ["B"]),
                              ("d4-the-successful-test", ["B", "A"]),
                              ("d5-encrypted-share", ["B", "B"])):
            case = self.cases[case_id]
            state = casesession.start(case, "cisa")
            casesession.save(state, self.results_path)

            payloads = [self.api.case_start({"case_id": case_id})]
            session_id = payloads[0]["session"]
            for key in keys:
                live = casesession.load(self.results_path, session_id)
                payloads.append(self.api.case_choose({
                    "session": session_id, "node": live.current, "key": key,
                }))
            payloads.append(self.api.case_get(session_id))
            payloads.append(self.api.case_list())

            for payload in payloads:
                blob = json.dumps(payload)
                for field in SECRET_FIELDS:
                    self.assertNotIn(
                        '"%s"' % field, blob,
                        "%s leaked '%s' before the debrief" % (case_id, field))

    def test_the_consequence_is_sent_but_the_reason_is_not(self):
        data = self.api.case_start({"case_id": "d4-the-successful-test"})
        result = self.api.case_choose({
            "session": data["session"], "node": "start", "key": "B"})
        self.assertTrue(result["consequence"])
        self.assertNotIn("why", result)
        self.assertNotIn("quality", result)

    def test_options_reach_the_client_as_key_and_text_only(self):
        data = self.api.case_start({"case_id": "d1-one-exception"})
        for opt in data["node"]["options"]:
            self.assertEqual(set(opt), {"key", "text"})


class TestCasesStayOutOfTheRealEvidence(CaseTestBase):
    def test_a_finished_case_never_touches_attempts(self):
        attempts = self.results_path
        os.makedirs(os.path.dirname(attempts), exist_ok=True)
        with open(attempts, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"question_id": "sentinel"}) + "\n")
        with open(attempts, "rb") as fh:
            before = fh.read()

        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        casesession.record(case, state, self.results_path)

        with open(attempts, "rb") as fh:
            self.assertEqual(fh.read(), before,
                             "a case run modified attempts.jsonl")
        rows = casesession.load_results(
            casesession.cases_log_path(self.results_path))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["case_id"], "d4-the-successful-test")

    def test_the_log_sits_beside_the_others_under_its_own_name(self):
        path = casesession.cases_log_path(self.results_path)
        self.assertTrue(path.endswith("cases.jsonl"))
        self.assertEqual(os.path.dirname(path), os.path.dirname(self.results_path))

    def test_the_record_carries_a_profile_not_a_score(self):
        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        casesession.record(case, state, self.results_path)
        row = casesession.load_results(
            casesession.cases_log_path(self.results_path))[0]
        for banned in ("score", "percent", "percentage", "grade"):
            self.assertNotIn(banned, row)
        self.assertEqual(row["best"] + row["defensible"] + row["poor"],
                         row["decisions"])


class TestTaintsFixTheOutcome(CaseTestBase):
    def test_a_taint_overrides_where_the_graph_led(self):
        # Best containment, then lose independence, then answer well.
        state, case = self.play("d5-encrypted-share", ["B", "A", "B", "B"])
        self.assertTrue(state.finished)
        self.assertEqual(state.graph_ending, "end-strong")
        self.assertEqual(state.ending, "end-compromised",
                         "losing independence must not be recoverable")

        data = casesession.debrief(case, state)
        self.assertTrue(data["overridden"])
        self.assertEqual(data["ending"]["verdict"], "weak")
        self.assertEqual(data["graph_ending"]["verdict"], "strong")

    def test_the_debrief_names_the_deciding_decision(self):
        state, case = self.play("d5-encrypted-share", ["B", "A", "B", "B"])
        override = casesession.debrief(case, state)["override"]
        self.assertEqual(override["taint"], "independence-lost")
        self.assertEqual(override["decision"], 2)
        self.assertEqual(override["of"], 4)
        self.assertEqual(override["decisions_before_end"], 2)
        self.assertEqual(override["node"], "security-arrives")
        self.assertTrue(override["why"], "the deciding decision must explain itself")

    def test_an_untainted_path_reports_no_override(self):
        state, case = self.play("d5-encrypted-share", ["B", "B", "B", "B"])
        data = casesession.debrief(case, state)
        self.assertFalse(data["overridden"])
        self.assertIsNone(data["override"])
        self.assertIsNone(data["graph_ending"])
        self.assertEqual(data["ending"]["verdict"], "strong")

    def test_declaration_order_is_precedence(self):
        case = self.cases["d5-encrypted-share"]
        # 'suppressed' is declared first, so it wins over 'independence-lost'.
        self.assertEqual(
            case.resolve_ending(["independence-lost", "suppressed"], "end-strong"),
            "end-failed")


class TestDebriefTeaches(CaseTestBase):
    def test_the_debrief_is_refused_until_the_case_ends(self):
        case = self.cases["d4-the-successful-test"]
        state = casesession.start(case, "cisa")
        with self.assertRaises(casesession.CaseSessionError):
            casesession.debrief(case, state)

    def test_the_debrief_shows_the_branches_not_taken(self):
        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        data = casesession.debrief(case, state)

        first = data["walk"][0]
        self.assertEqual(len(first["options"]), 4, "all options, not just the one taken")
        self.assertEqual(sum(1 for o in first["options"] if o["chosen"]), 1)
        for opt in first["options"]:
            self.assertTrue(opt["why"], "every branch must explain itself")
            self.assertIn(opt["quality"], cases_mod.QUALITIES)

    def test_endings_index_labels_where_a_branch_would_have_gone(self):
        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        data = casesession.debrief(case, state)
        self.assertIn("end-unproven", data["endings_index"])
        self.assertEqual(data["endings_index"]["end-unproven"]["verdict"], "weak")

    def test_the_debrief_reports_counts_and_never_a_percentage(self):
        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        data = casesession.debrief(case, state)
        self.assertEqual(data["counts"], {"best": 5, "defensible": 0, "poor": 0})
        blob = json.dumps(data)
        self.assertNotIn('"score"', blob)
        self.assertNotIn('"percent"', blob)

    def test_every_case_can_reach_a_strong_ending(self):
        """If a case cannot be played well, the format is not teaching."""
        for case_id, keys in (("d1-one-exception", ["B", "B", "B", "B", "B", "B", "B"]),
                              ("d4-the-successful-test", ["B", "A", "A", "A", "B"]),
                              ("d5-encrypted-share", ["B", "B", "B", "B"])):
            case = self.cases[case_id]
            state = casesession.start(case, "cisa")
            for key in keys:
                if state.finished:
                    break
                opt = case.option(state.current, key)
                # Fall back to whatever is marked best if this key is absent.
                if opt is None:
                    opt = case.best_option(state.current)
                casesession.choose(case, state, state.current, opt["key"])
            self.assertTrue(state.finished, "%s did not finish" % case_id)
            verdict = (case.ending(state.ending) or {}).get("verdict")
            self.assertEqual(verdict, "strong",
                             "%s: playing the best option at every node gave '%s'"
                             % (case_id, verdict))


class TestTheGraphIsDebriefOnly(CaseTestBase):
    """The drawing of the case is the answer key in another shape.

    A picture showing which branch reaches `end-strong` gives the case away
    more completely than any single field would, so it is built beside the
    debrief and must not appear anywhere a running session can reach.
    """

    def test_no_payload_before_the_debrief_carries_a_graph(self):
        for case_id, keys in (("d1-one-exception", ["B", "A"]),
                              ("d4-the-successful-test", ["B", "A"]),
                              ("d5-encrypted-share", ["B", "B"])):
            data = self.api.case_start({"case_id": case_id})
            session_id = data["session"]
            payloads = [data, self.api.case_list()]
            for key in keys:
                live = self.api.case_get(session_id)
                payloads.append(live)
                if live["finished"]:
                    break
                payloads.append(self.api.case_choose({
                    "session": session_id, "node": live["node"]["id"], "key": key,
                }))

            for payload in payloads:
                self.assertNotIn(
                    '"graph"', json.dumps(payload),
                    "%s served the graph before the debrief" % case_id)

    def test_the_debrief_carries_it(self):
        state, case = self.play("d5-encrypted-share", ["B", "B", "B", "B"])
        graph = casesession.debrief(case, state)["graph"]
        self.assertEqual(graph["start"], cases_mod.START)
        self.assertTrue(graph["nodes"] and graph["edges"] and graph["endings"])

    def test_the_graph_is_the_whole_case_not_the_walk(self):
        """Drawing only the walked path would teach nothing new."""
        state, case = self.play("d5-encrypted-share", ["B", "B", "B", "B"])
        graph = casesession.debrief(case, state)["graph"]

        self.assertEqual(len(graph["nodes"]), len(case.nodes))
        self.assertEqual(len(graph["endings"]), len(case.endings))
        walked = [n for n in graph["nodes"] if n["walked"]]
        self.assertLess(len(walked), len(graph["nodes"]),
                        "a case with no unwalked node cannot show a road not taken")

    def test_the_walked_path_is_numbered_in_order(self):
        state, case = self.play("d5-encrypted-share", ["B", "B", "B", "B"])
        graph = casesession.debrief(case, state)["graph"]

        walked = sorted((n for n in graph["nodes"] if n["walked"]),
                        key=lambda n: n["position"])
        self.assertEqual([n["position"] for n in walked],
                         list(range(1, len(walked) + 1)))
        self.assertEqual(walked[0]["id"], cases_mod.START)
        self.assertEqual([n["id"] for n in walked],
                         [s["node_id"] for s in state.steps])

    def test_every_edge_lands_somewhere_drawable(self):
        """A dangling edge would be a line to nowhere on the canvas."""
        for case in self.cases.values():
            state = casesession.start(case, "cisa")
            graph = casesession.public_graph(case, state)
            targets = {n["id"] for n in graph["nodes"]}
            targets |= {e["id"] for e in graph["endings"]}
            for edge in graph["edges"]:
                self.assertIn(edge["from"], targets, case.id)
                self.assertIn(edge["to"], targets, case.id)

    def test_exactly_one_edge_is_chosen_per_walked_node(self):
        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        graph = casesession.debrief(case, state)["graph"]

        chosen = [e for e in graph["edges"] if e["chosen"]]
        self.assertEqual(len(chosen), len(state.steps))
        self.assertEqual([e["from"] for e in chosen],
                         [s["node_id"] for s in state.steps])

    def test_a_taint_draws_an_override_edge_the_case_does_not_own(self):
        """The whole point of the picture: your path went there, the taint
        dragged the outcome here."""
        # Sound work after decision 2, but conceding independence there fixed
        # the outcome: the path walks on to end-strong and lands compromised.
        state, case = self.play("d5-encrypted-share", ["B", "A", "B", "B"])
        graph = casesession.debrief(case, state)["graph"]
        override = graph["override"]

        self.assertIsNotNone(override, "fixture must be a tainted run")
        self.assertEqual(override["taint"], "independence-lost")
        self.assertEqual(override["decision"], 2)
        self.assertEqual(override["to"], state.ending)
        self.assertNotEqual(state.ending, state.graph_ending)
        self.assertNotIn((override["from"], override["to"]),
                         {(e["from"], e["to"]) for e in graph["edges"]},
                         "the override is what the taint did, not a case edge")

        reached = [e for e in graph["endings"] if e["reached"]]
        heading = [e for e in graph["endings"] if e["graph_reached"]]
        self.assertEqual([e["id"] for e in reached], [state.ending])
        self.assertEqual([e["id"] for e in heading], [state.graph_ending])

    def test_a_clean_run_has_no_override_and_one_marked_ending(self):
        state, case = self.play("d5-encrypted-share", ["B", "B", "B", "B"])
        graph = casesession.debrief(case, state)["graph"]

        self.assertIsNone(graph["override"])
        self.assertEqual([e["id"] for e in graph["endings"] if e["reached"]],
                         [state.ending])
        self.assertEqual([e["id"] for e in graph["endings"] if e["graph_reached"]], [],
                         "nothing was redirected, so nothing is left dangling")

    def test_an_unfinished_run_claims_no_outcome(self):
        case = self.cases["d1-one-exception"]
        state = casesession.start(case, "cisa")
        casesession.choose(case, state, state.current, "B")
        graph = casesession.public_graph(case, state)

        self.assertIsNone(graph["override"])
        self.assertEqual([e for e in graph["endings"] if e["reached"]], [])


class TestSessionRules(CaseTestBase):
    def test_a_session_survives_a_restart(self):
        data = self.api.case_start({"case_id": "d5-encrypted-share"})
        session_id = data["session"]
        self.api.case_choose({"session": session_id, "node": "start", "key": "B"})

        # A brand-new Api, as a reopened browser would get.
        fresh = Api("cisa", self.profile)
        resumed = fresh.case_get(session_id)
        self.assertFalse(resumed["finished"])
        self.assertEqual(resumed["node"]["id"], "security-arrives")
        self.assertEqual(len(resumed["trail"]), 1)
        self.assertTrue(resumed["trail"][0]["consequence"])

    def test_you_cannot_answer_a_node_you_are_not_on(self):
        case = self.cases["d4-the-successful-test"]
        state = casesession.start(case, "cisa")
        with self.assertRaises(casesession.CaseSessionError):
            casesession.choose(case, state, "who-set-the-rto", "A")

    def test_an_unknown_option_is_refused(self):
        case = self.cases["d4-the-successful-test"]
        state = casesession.start(case, "cisa")
        with self.assertRaises(casesession.CaseSessionError):
            casesession.choose(case, state, "start", "Z")

    def test_a_finished_case_cannot_be_replayed(self):
        state, case = self.play("d4-the-successful-test", ["A"])
        self.assertTrue(state.finished)
        with self.assertRaises(casesession.CaseSessionError):
            casesession.choose(case, state, "start", "B")

    def test_the_index_reports_history_and_open_sessions(self):
        cases = list(self.cases.values())
        started = self.api.case_start({"case_id": "d5-encrypted-share"})
        self.api.case_choose({
            "session": started["session"], "node": "start", "key": "B"})

        index = {e["id"]: e for e in casesession.case_index(cases, self.results_path)}
        self.assertEqual(index["d5-encrypted-share"]["open_session"],
                         started["session"])
        self.assertEqual(index["d5-encrypted-share"]["open_decisions"], 1)
        self.assertEqual(index["d5-encrypted-share"]["attempts"], 0)

        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        casesession.record(case, state, self.results_path)
        index = {e["id"]: e for e in casesession.case_index(cases, self.results_path)}
        self.assertEqual(index["d4-the-successful-test"]["attempts"], 1)
        self.assertEqual(index["d4-the-successful-test"]["verdicts"], ["strong"])

    def test_results_are_per_profile(self):
        state, case = self.play("d4-the-successful-test", ["B", "A", "A", "A", "B"])
        casesession.record(case, state, self.results_path)

        other = Api("cisa", "casetest-other-%s" % os.urandom(3).hex())
        try:
            rows = casesession.load_results(
                casesession.cases_log_path(other.results_path))
            self.assertEqual(rows, [], "another profile saw these case results")
        finally:
            directory = os.path.dirname(other.results_path)
            if os.path.isdir(directory):
                for root, _, files in os.walk(directory, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    os.rmdir(root)


class TestTerminalOutputSurvivesRedirection(CaseTestBase):
    """A history listing must not crash when stdout is not a console.

    Windows falls back to the locale encoding (cp1252 here) when output is
    redirected to a file or a pipe, and it cannot encode arrows or box drawing.
    This caught a real crash on the one row that reports an overridden outcome.
    """

    def test_runner_source_is_cp1252_safe(self):
        from drillkit import caserunner
        for module in (caserunner, casesession):
            with open(module.__file__, "r", encoding="utf-8") as fh:
                source = fh.read()
            for char in sorted(set(source)):
                if ord(char) < 128:
                    continue
                try:
                    char.encode("cp1252")
                except UnicodeEncodeError:
                    self.fail("%s contains U+%04X, which breaks redirected "
                              "output on Windows" % (module.__name__, ord(char)))

    def test_summarise_renders_an_overridden_run(self):
        import io
        from contextlib import redirect_stdout
        from drillkit import caserunner

        state, case = self.play("d5-encrypted-share", ["B", "A", "B", "B"])
        casesession.record(case, state, self.results_path)
        rows = casesession.load_results(
            casesession.cases_log_path(self.results_path))
        self.assertTrue(rows[0]["overridden"])

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            caserunner.summarise(rows)
        text = buffer.getvalue()
        self.assertIn("d5-encrypted-share", text)
        text.encode("cp1252")  # would raise if a stray glyph came back


class TestStoreIsUntouched(CaseTestBase):
    def test_case_module_cannot_reach_the_attempt_store(self):
        """Structural guard, not a text search.

        `store.append` is the only thing that writes attempts.jsonl. If this
        module never imports it, no future edit here can write there by
        accident — the failure would be an ImportError, not silent corruption.
        """
        self.assertFalse(hasattr(casesession, "store"),
                         "casesession imported the attempt store")
        self.assertFalse(hasattr(casesession, "append"),
                         "casesession exposes a bare append()")

    def test_store_still_owns_its_own_path(self):
        self.assertTrue(self.results_path.endswith("attempts.jsonl"))
        self.assertNotEqual(self.results_path,
                            casesession.cases_log_path(self.results_path))
        self.assertTrue(callable(store.append))


if __name__ == "__main__":
    unittest.main(verbosity=2)
