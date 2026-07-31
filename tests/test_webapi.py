"""Tests for the JSON API and the local server.

    python tests/test_webapi.py

Two tests here matter more than the rest:

* the answer key must never reach the client before the user commits, or
  devtools becomes a cheat menu during a timed exam;
* two profiles sharing one question bank must not see each other's results,
  or both people are drilling against a learner who does not exist.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import serve  # noqa: E402
from drillkit import loader  # noqa: E402
from drillkit.webapi import Api, ApiError, public_question  # noqa: E402

SECRET_FIELDS = ("answer", "why_correct", "why_wrong", "asks")


class ApiTestBase(unittest.TestCase):
    """Each test gets its own profile so nothing touches real study history."""

    def setUp(self):
        self.profile = "test-%s" % os.urandom(4).hex()
        self.api = Api("cisa", self.profile)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        directory = loader.results_dir("cisa", self.profile)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)


class TestBootstrap(ApiTestBase):
    def test_bootstrap_describes_the_bank(self):
        b = self.api.bootstrap()
        self.assertEqual(b["cert"], "CISA")
        self.assertEqual(b["questions"], len(self.api.questions))
        self.assertEqual(len(b["domains"]), 5)
        self.assertGreaterEqual(len(b["principles"]), 15)
        self.assertGreaterEqual(len(b["pairs"]), 20)

    def test_bootstrap_carries_the_verified_exam_format(self):
        exam = self.api.bootstrap()["exam"]
        self.assertEqual(exam["questions"], 150)
        self.assertEqual(exam["minutes"], 240)
        self.assertEqual(exam["passing_score"], 450)

    def test_every_principle_carries_its_trap_and_scope(self):
        for p in self.api.bootstrap()["principles"]:
            self.assertTrue(p["misapplication"], p["id"])
            self.assertTrue(p["scope"], p["id"])


class TestAnswerKeyIsNotLeaked(ApiTestBase):
    def test_public_question_omits_everything_that_gives_it_away(self):
        q = self.api.questions[0]
        payload = public_question(q)
        for field in SECRET_FIELDS:
            self.assertNotIn(field, payload)
        self.assertIn("stem", payload)
        self.assertEqual(sorted(payload["options"]), ["A", "B", "C", "D"])

    def test_drill_start_sends_no_answer_keys(self):
        data = self.api.drill_start({"mode": "random", "n": 8})
        blob = json.dumps(data)
        for item in data["questions"]:
            for field in SECRET_FIELDS:
                self.assertNotIn(field, item)
        # A crude but decisive check: no keyed rationale text in the payload.
        for q in self.api.questions[:40]:
            self.assertNotIn(q.why_correct, blob)

    def test_exam_payload_sends_no_answer_keys(self):
        data = self.api.exam_new({"n": 12, "minutes": 20})
        for item in data["questions"]:
            for field in SECRET_FIELDS:
                self.assertNotIn(field, item)

    def test_the_key_arrives_only_in_the_answer_response(self):
        data = self.api.drill_start({"mode": "random", "n": 1})
        qid = data["questions"][0]["id"]
        res = self.api.drill_answer({"question_id": qid, "chosen": "A",
                                     "session": data["session"], "mode": "random"})
        self.assertIn("answer", res)
        self.assertIn("why_correct", res)
        self.assertEqual(sorted(res["why_wrong"]),
                         sorted(k for k in "ABCD" if k != res["answer"]))

    def test_autopsy_reveals_the_key_by_design_but_not_the_mapping(self):
        data = self.api.game_start({"game": "autopsy", "n": 3})
        for item in data["questions"]:
            self.assertIn("answer", item)          # the point of the game
            self.assertNotIn("why_wrong", item)    # the mapping is the puzzle
            labels = [e["label"] for e in item["explanations"]]
            self.assertEqual(sorted(labels), sorted(set(labels)))

    def test_coldread_hides_the_options_entirely(self):
        data = self.api.game_start({"game": "coldread", "n": 3})
        for item in data["questions"]:
            self.assertEqual(item["options"], {})


class TestProfileIsolation(unittest.TestCase):
    def setUp(self):
        self.a = "iso-a-%s" % os.urandom(3).hex()
        self.b = "iso-b-%s" % os.urandom(3).hex()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in (self.a, self.b):
            directory = loader.results_dir("cisa", name)
            if os.path.isdir(directory):
                for root, _, files in os.walk(directory, topdown=False):
                    for f in files:
                        os.remove(os.path.join(root, f))
                    os.rmdir(root)

    def test_two_people_sharing_a_bank_keep_separate_histories(self):
        api_a = Api("cisa", self.a)
        api_b = Api("cisa", self.b)

        data = api_a.drill_start({"mode": "random", "n": 3, "seed": 1})
        for item in data["questions"]:
            api_a.drill_answer({"question_id": item["id"], "chosen": "A",
                                "session": data["session"], "mode": "random"})

        self.assertEqual(len(api_a.rows()), 3)
        self.assertEqual(len(api_b.rows()), 0, "profiles must not see each other")
        self.assertNotEqual(api_a.results_path, api_b.results_path)

    def test_the_shared_default_profile_is_a_different_path_again(self):
        shared = Api("cisa", None)
        named = Api("cisa", self.a)
        self.assertNotEqual(shared.results_path, named.results_path)

    def test_profile_names_cannot_escape_the_results_directory(self):
        evil = Api("cisa", "../../../etc/passwd")
        base = os.path.abspath(loader.cert_dir("cisa"))
        self.assertTrue(os.path.abspath(evil.results_path).startswith(base))


class TestDrillAndGames(ApiTestBase):
    def test_filters_narrow_the_pool(self):
        data = self.api.drill_start({"mode": "random", "n": 5, "domain": "5"})
        ids = {q["id"] for q in data["questions"]}
        known = self.api.by_id()
        self.assertTrue(all(known[i].domain == "5" for i in ids))

    def test_an_impossible_filter_is_an_error_not_an_empty_screen(self):
        with self.assertRaises(ApiError):
            self.api.drill_start({"mode": "random", "n": 5, "topic": "zzz-nothing"})

    def test_a_bad_answer_letter_is_rejected(self):
        qid = self.api.questions[0].id
        with self.assertRaises(ApiError):
            self.api.drill_answer({"question_id": qid, "chosen": "Z"})

    def test_an_unknown_question_is_rejected(self):
        with self.assertRaises(ApiError):
            self.api.drill_answer({"question_id": "nope", "chosen": "A"})

    def test_costumes_serves_one_question_per_domain(self):
        data = self.api.drill_start({"mode": "costumes", "principle": "segregation"})
        known = self.api.by_id()
        domains = [known[q["id"]].domain for q in data["questions"]]
        self.assertEqual(len(domains), len(set(domains)))
        self.assertGreaterEqual(len(domains), 2)

    def test_games_write_to_the_games_log_not_the_attempt_log(self):
        data = self.api.game_start({"game": "coldread", "n": 2})
        q = data["questions"][0]
        self.api.game_answer({"game": "coldread", "question_id": q["id"],
                              "session": data["session"], "read": "risk"})
        self.assertEqual(len(self.api.rows()), 0, "games must not reach attempts.jsonl")
        from drillkit import games as games_mod
        self.assertEqual(len(games_mod.load_games(self.api.games_path)), 1)

    def test_autopsy_grades_the_mapping_server_side(self):
        data = self.api.game_start({"game": "autopsy", "n": 1})
        q = data["questions"][0]
        truth = self.api._sessions[data["session"]]["shuffles"][q["id"]]
        res = self.api.game_answer({"game": "autopsy", "question_id": q["id"],
                                    "session": data["session"], "mapping": truth})
        self.assertTrue(res["correct"])
        self.assertEqual(res["matched"], res["total"])

    def test_an_expired_autopsy_session_fails_cleanly(self):
        with self.assertRaises(ApiError):
            self.api.game_answer({"game": "autopsy", "session": "gone",
                                  "question_id": self.api.questions[0].id,
                                  "mapping": {}})


class TestExamFlow(ApiTestBase):
    def test_a_full_exam_round_trip(self):
        created = self.api.exam_new({"n": 10, "minutes": 15, "seed": 3})
        exam_id = created["id"]
        self.assertEqual(len(created["questions"]), 10)

        known = self.api.by_id()
        for i, item in enumerate(created["questions"]):
            correct = known[item["id"]].answer
            chosen = correct if i < 7 else ("A" if correct != "A" else "B")
            self.api.exam_update({"id": exam_id, "action": "answer",
                                  "question_id": item["id"], "chosen": chosen,
                                  "seconds": 20})

        self.api.exam_update({"id": exam_id, "action": "flag",
                              "question_id": created["questions"][0]["id"]})
        state = self.api.exam_get(exam_id)
        self.assertEqual(len(state["answers"]), 10)
        self.assertEqual(len(state["flagged"]), 1)

        result = self.api.exam_submit({"id": exam_id, "elapsed": 300})
        self.assertEqual(result["correct"], 7)
        self.assertEqual(result["total"], 10)
        self.assertEqual(len(result["missed"]), 3)
        self.assertIn("scaled", result)

        # Submitted answers become real evidence in the attempt log.
        self.assertEqual(len(self.api.rows()), 10)

    def test_missed_questions_come_back_with_full_explanations(self):
        created = self.api.exam_new({"n": 4, "minutes": 10, "seed": 5})
        known = self.api.by_id()
        for item in created["questions"]:
            correct = known[item["id"]].answer
            self.api.exam_update({"id": created["id"], "action": "answer",
                                  "question_id": item["id"],
                                  "chosen": "A" if correct != "A" else "B"})
        result = self.api.exam_submit({"id": created["id"]})
        for q in result["missed"]:
            self.assertTrue(q["why_correct"])
            self.assertTrue(q["options"]["A"])
            self.assertEqual(len(q["why_wrong"]), 3)

    def test_answering_a_submitted_exam_is_refused(self):
        created = self.api.exam_new({"n": 2, "minutes": 5})
        self.api.exam_submit({"id": created["id"]})
        with self.assertRaises(ApiError):
            self.api.exam_update({"id": created["id"], "action": "answer",
                                  "question_id": created["questions"][0]["id"],
                                  "chosen": "A"})

    def test_a_question_outside_the_exam_is_refused(self):
        created = self.api.exam_new({"n": 2, "minutes": 5})
        outside = next(q.id for q in self.api.questions
                       if q.id not in {x["id"] for x in created["questions"]})
        with self.assertRaises(ApiError):
            self.api.exam_update({"id": created["id"], "action": "answer",
                                  "question_id": outside, "chosen": "A"})

    def test_elapsed_time_only_moves_forward(self):
        created = self.api.exam_new({"n": 2, "minutes": 5})
        self.api.exam_update({"id": created["id"], "action": "tick", "elapsed": 120})
        self.api.exam_update({"id": created["id"], "action": "tick", "elapsed": 30})
        state = self.api.exam_get(created["id"])
        self.assertEqual(state["elapsed"], 120,
                         "a reloaded tab must not be able to rewind the clock")


class TestReports(ApiTestBase):
    def test_overview_is_safe_with_no_data(self):
        o = self.api.overview()
        self.assertEqual(o["attempts"], 0)
        self.assertIsNone(o["accuracy"])
        self.assertEqual(len(o["domains"]), 5)
        self.assertGreaterEqual(len(o["rules"]), 15)

    def test_overview_reflects_answers(self):
        data = self.api.drill_start({"mode": "random", "n": 4, "seed": 2})
        known = self.api.by_id()
        for item in data["questions"]:
            self.api.drill_answer({"question_id": item["id"],
                                   "chosen": known[item["id"]].answer,
                                   "session": data["session"], "mode": "random"})
        o = self.api.overview()
        self.assertEqual(o["attempts"], 4)
        self.assertEqual(o["accuracy"], 1.0)
        self.assertEqual(o["coverage_seen"], 4)

    def test_weighted_accuracy_is_not_presented_as_a_score(self):
        o = self.api.overview()
        self.assertIn("weighted_accuracy", o)
        self.assertNotIn("predicted_score", o)
        self.assertNotIn("readiness", o)

    def test_items_and_card_render(self):
        self.assertIn("total", self.api.items())
        self.assertIn("Risk assessment", self.api.card()["text"])


class TestHttpLayer(unittest.TestCase):
    """Drive the real server over HTTP, not just the Api object."""

    @classmethod
    def setUpClass(cls):
        serve.Handler.pool = serve.ApiPool("cisa")
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        cls.port = cls.srv.server_address[1]
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()
        cls.profile = "http-%s" % os.urandom(3).hex()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        directory = loader.results_dir("cisa", cls.profile)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for f in files:
                    os.remove(os.path.join(root, f))
                os.rmdir(root)

    def call(self, path, body=None, profile=None):
        url = "http://127.0.0.1:%d%s" % (self.port, path)
        req = urllib.request.Request(url, method="POST" if body is not None else "GET")
        req.add_header("X-Profile", profile if profile is not None else self.profile)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data, timeout=10) as res:
                return res.status, json.loads(res.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_bootstrap_over_http(self):
        status, data = self.call("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(data["questions"], 292)

    def test_drill_round_trip_over_http(self):
        status, data = self.call("/api/drill/start", {"mode": "random", "n": 2})
        self.assertEqual(status, 200)
        qid = data["questions"][0]["id"]
        status, res = self.call("/api/drill/answer",
                                {"question_id": qid, "chosen": "A",
                                 "session": data["session"], "mode": "random"})
        self.assertEqual(status, 200)
        self.assertIn("why_correct", res)

    def test_static_files_are_served(self):
        for path in ("/", "/style.css", "/app.js"):
            url = "http://127.0.0.1:%d%s" % (self.port, path)
            with urllib.request.urlopen(url, timeout=10) as res:
                self.assertEqual(res.status, 200)
                self.assertGreater(len(res.read()), 100)

    def test_path_traversal_is_refused(self):
        for path in ("/../drill.py", "/..%2fdrill.py", "/web/../../drill.py"):
            url = "http://127.0.0.1:%d%s" % (self.port, path)
            try:
                with urllib.request.urlopen(url, timeout=10) as res:
                    body = res.read().decode("utf-8", "replace")
                    self.assertNotIn("import argparse", body,
                                     "served a file outside web/: %s" % path)
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)

    def test_unknown_routes_return_json_errors(self):
        status, data = self.call("/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("error", data)

    def test_malformed_json_is_reported_not_crashed(self):
        url = "http://127.0.0.1:%d/api/drill/start" % self.port
        req = urllib.request.Request(url, method="POST", data=b"{not json")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                self.fail("expected an error, got %s" % res.status)
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            self.assertIn("error", json.loads(exc.read().decode()))

    def test_the_profile_header_routes_to_a_separate_history(self):
        other = "http-other-%s" % os.urandom(3).hex()
        # Measure the delta rather than assuming this profile starts empty:
        # other tests in this class share it, and test order is not guaranteed.
        _, before = self.call("/api/overview")

        status, data = self.call("/api/drill/start", {"mode": "random", "n": 1},
                                 profile=other)
        self.assertEqual(status, 200)
        self.call("/api/drill/answer",
                  {"question_id": data["questions"][0]["id"], "chosen": "A",
                   "session": data["session"], "mode": "random"}, profile=other)

        _, after = self.call("/api/overview")
        _, theirs = self.call("/api/overview", profile=other)
        self.assertEqual(theirs["attempts"], 1, "the other profile logged its own answer")
        self.assertEqual(after["attempts"], before["attempts"],
                         "answering as one profile must not change another's history")
        directory = loader.results_dir("cisa", other)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for f in files:
                    os.remove(os.path.join(root, f))
                os.rmdir(root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
