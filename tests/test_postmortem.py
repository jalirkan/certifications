"""Tests for the exam post-mortem: the waterfall and the timing split.

The ones that matter:

* the waterfall must decompose exactly - the costs it draws have to sum to the
  marks actually lost, or the chart is telling a story the score does not
  support.
* weighting must be able to invert accuracy order. A domain can be the worst
  answered and cost almost nothing, because Domain 3 is 12% of the exam and
  Domain 4 is 26%. That inversion is the whole reason for weighting, and an
  accuracy-sorted list hides it.
* the fast-versus-slow gap must carry an interval and must not claim a cause.

    python tests/test_postmortem.py
"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import loader, postmortem  # noqa: E402
from drillkit.itemanalysis import difference_of_proportions  # noqa: E402
from drillkit.webapi import Api, ApiError  # noqa: E402


def domain(did, weight, asked, correct, name=""):
    return {"domain": did, "name": name or ("Domain %s" % did), "weight": weight,
            "asked": asked, "correct": correct,
            "accuracy": (correct / asked) if asked else 0.0}


def timed(n, seconds, correct, start=0):
    return [{"id": "q%d" % (start + i), "topic": "T", "domain": "1",
             "seconds": seconds, "correct": correct, "answered": True}
            for i in range(n)]


class TestTheWaterfallDecomposes(unittest.TestCase):
    def test_the_costs_sum_to_what_was_lost(self):
        rows = [domain("1", 18, 27, 23), domain("2", 18, 27, 22),
                domain("3", 12, 18, 15), domain("4", 26, 39, 11),
                domain("5", 26, 39, 29)]
        w = postmortem.waterfall(rows)
        self.assertAlmostEqual(sum(s["cost"] for s in w["steps"]), w["lost"], places=6)
        self.assertAlmostEqual(w["available"] - w["lost"], w["earned"], places=6)

    def test_the_running_balance_is_continuous(self):
        """Each bar starts where the last one ended, or the chart lies."""
        rows = [domain("1", 18, 27, 20), domain("4", 26, 39, 12),
                domain("3", 12, 18, 18)]
        w = postmortem.waterfall(rows)
        self.assertAlmostEqual(w["steps"][0]["from"], w["available"], places=6)
        for a, b in zip(w["steps"], w["steps"][1:]):
            self.assertAlmostEqual(a["to"], b["from"], places=6)
        self.assertAlmostEqual(w["steps"][-1]["to"], w["earned"], places=6)

    def test_a_perfect_sitting_costs_nothing(self):
        rows = [domain("1", 18, 27, 27), domain("4", 26, 39, 39)]
        w = postmortem.waterfall(rows)
        self.assertAlmostEqual(w["lost"], 0.0, places=6)
        self.assertAlmostEqual(w["earned"], w["available"], places=6)

    def test_ordering_is_by_damage_not_by_accuracy(self):
        """The inversion weighting exists to expose.

        Domain 3 answered worse than Domain 4, and costing less than half as
        much, because it is 12% of the exam against 26%.
        """
        rows = [domain("3", 12, 18, 9),    # 50% correct, cost 6.0
                domain("4", 26, 39, 26)]   # 67% correct, cost 8.67
        w = postmortem.waterfall(rows)
        self.assertLess(rows[0]["accuracy"], rows[1]["accuracy"])
        self.assertEqual([s["domain"] for s in w["steps"]], ["4", "3"])
        self.assertGreater(w["steps"][0]["cost"], w["steps"][1]["cost"])

    def test_every_cost_carries_an_interval_that_contains_it(self):
        rows = [domain("1", 18, 27, 20), domain("4", 26, 39, 15)]
        for step in postmortem.waterfall(rows)["steps"]:
            self.assertIsNotNone(step["cost_low"])
            self.assertLessEqual(step["cost_low"], step["cost"] + 1e-9)
            self.assertGreaterEqual(step["cost_high"], step["cost"] - 1e-9)

    def test_a_thinly_sampled_domain_is_flagged(self):
        rows = [domain("3", 12, 4, 2), domain("4", 26, 39, 20)]
        steps = {s["domain"]: s for s in postmortem.waterfall(rows)["steps"]}
        self.assertFalse(steps["3"]["enough"])
        self.assertTrue(steps["4"]["enough"])

    def test_an_unasked_domain_does_not_invent_an_accuracy(self):
        rows = [domain("3", 12, 0, 0), domain("4", 26, 39, 20)]
        steps = {s["domain"]: s for s in postmortem.waterfall(rows)["steps"]}
        self.assertIsNone(steps["3"]["accuracy"])
        self.assertIsNone(steps["3"]["cost_low"])


class TestTimingSplitsAtTheLearnersOwnPace(unittest.TestCase):
    def test_the_split_is_the_median_of_this_sitting(self):
        rows = timed(20, 10.0, True) + timed(20, 100.0, False, start=100)
        data = postmortem.timing(rows)
        self.assertEqual(data["median"], 55.0)
        self.assertEqual(data["fast"]["n"], 20)
        self.assertEqual(data["slow"]["n"], 20)

    def test_untimed_questions_are_dropped_not_treated_as_instant(self):
        rows = timed(20, 30.0, True) + timed(5, 0.0, False, start=100)
        data = postmortem.timing(rows)
        self.assertEqual(data["untimed"], 5)
        self.assertEqual(data["fast"]["n"] + data["slow"]["n"], 20)

    def test_unanswered_questions_are_counted_apart_from_wrong_ones(self):
        """Running out of time is a different finding from rushing."""
        rows = timed(20, 30.0, True)
        rows += [{"id": "x%d" % i, "topic": "T", "domain": "1", "seconds": 5.0,
                  "correct": False, "answered": False} for i in range(4)]
        data = postmortem.timing(rows)
        self.assertEqual(data["unanswered"], 4)
        self.assertEqual(data["fast"]["n"] + data["slow"]["n"], 20)

    def test_the_gap_carries_an_interval_and_says_when_it_spans_zero(self):
        rows = timed(20, 10.0, True) + timed(20, 100.0, True, start=100)
        gap = postmortem.timing(rows)["gap"]
        self.assertEqual(gap["gap"], 0.0)
        self.assertTrue(gap["spans_zero"])

    def test_a_real_difference_does_not_span_zero(self):
        rows = (timed(40, 10.0, False) + timed(40, 100.0, True, start=100))
        gap = postmortem.timing(rows)["gap"]
        self.assertLess(gap["gap"], 0)
        self.assertFalse(gap["spans_zero"])

    def test_a_short_sitting_is_not_enough_to_call(self):
        rows = timed(5, 10.0, False) + timed(5, 100.0, True, start=100)
        data = postmortem.timing(rows)
        self.assertFalse(data["enough"])
        self.assertIsNone(postmortem.verdict(data))

    def test_an_untimed_sitting_returns_an_empty_shape_not_an_error(self):
        rows = timed(10, 0.0, True)
        data = postmortem.timing(rows)
        self.assertIsNone(data["median"])
        self.assertFalse(data["enough"])
        self.assertEqual(data["points"], [])

    def test_the_rushed_list_is_fast_and_wrong_fastest_first(self):
        rows = timed(20, 100.0, True)
        rows += [{"id": "r1", "topic": "T", "domain": "1", "seconds": 9.0,
                  "correct": False, "answered": True},
                 {"id": "r2", "topic": "T", "domain": "1", "seconds": 4.0,
                  "correct": False, "answered": True},
                 {"id": "ok", "topic": "T", "domain": "1", "seconds": 5.0,
                  "correct": True, "answered": True}]
        rushed = postmortem.timing(rows)["rushed"]
        self.assertEqual([r["id"] for r in rushed], ["r2", "r1"])


class TestTheVerdictStatesAssociationNotCause(unittest.TestCase):
    """An earlier draft called a negative gap "a pace problem rather than a
    knowledge one". Speed and difficulty are confounded, so it cannot."""

    def test_it_never_claims_a_cause(self):
        cases = [
            timed(40, 10.0, False) + timed(40, 100.0, True, start=100),
            timed(40, 10.0, True) + timed(40, 100.0, False, start=100),
            timed(40, 10.0, True) + timed(40, 100.0, True, start=100),
        ]
        banned = ("pace problem rather than", "because you rushed",
                  "proves", "means you were rushing")
        for rows in cases:
            text = postmortem.verdict(postmortem.timing(rows)) or ""
            for phrase in banned:
                self.assertNotIn(phrase, text.lower())

    def test_being_worse_when_fast_names_both_explanations(self):
        rows = timed(40, 10.0, False) + timed(40, 100.0, True, start=100)
        text = postmortem.verdict(postmortem.timing(rows))
        self.assertIn("rushing", text)
        self.assertIn("misjudging", text)

    def test_an_indistinguishable_gap_says_so_plainly(self):
        rows = timed(40, 10.0, True) + timed(40, 100.0, True, start=100)
        text = postmortem.verdict(postmortem.timing(rows))
        self.assertIn("not telling you anything yet", text)


class TestTheSharedDifferenceHelper(unittest.TestCase):
    def test_calibration_and_the_post_mortem_use_the_same_arithmetic(self):
        """One implementation, so the two surfaces cannot drift apart."""
        from drillkit import calibration
        rows = ([{"confidence": "confident", "correct": True}] * 30
                + [{"confidence": "confident", "correct": False}] * 10
                + [{"confidence": "unsure", "correct": True}] * 12
                + [{"confidence": "unsure", "correct": False}] * 18)
        gap = calibration.overconfidence_gap(rows)
        direct = difference_of_proportions(30, 40, 12, 30)
        self.assertAlmostEqual(gap["gap"], direct["gap"], places=12)
        self.assertAlmostEqual(gap["gap_low"], direct["low"], places=12)
        self.assertAlmostEqual(gap["gap_high"], direct["high"], places=12)
        self.assertEqual(gap["spans_zero"], direct["spans_zero"])

    def test_an_empty_cell_yields_no_claim(self):
        self.assertIsNone(difference_of_proportions(0, 0, 5, 10)["gap"])
        self.assertIsNone(difference_of_proportions(5, 10, 0, 0)["spans_zero"])


class TestTheExamResultSurface(unittest.TestCase):
    def setUp(self):
        self.profile = "pmtest-%s" % os.urandom(4).hex()
        self.api = Api("cisa", self.profile)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        directory = loader.results_dir("cisa", self.profile)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)

    def sit(self, rushed_domain="4", n=150):
        keys = {q.id: q.answer for q in self.api.questions}
        exam_id = self.api.exam_new({"n": n})["id"]
        state = self.api.exam_get(exam_id)
        rng = random.Random(5)
        for q in state["questions"]:
            fast = q["domain"] == rushed_domain
            seconds = rng.uniform(8, 22) if fast else rng.uniform(45, 130)
            right = rng.random() < (0.30 if fast else 0.78)
            key = keys[q["id"]]
            chosen = key if right else rng.choice([k for k in "ABCD" if k != key])
            self.api.exam_update({"id": exam_id, "action": "answer",
                                  "question_id": q["id"], "chosen": chosen,
                                  "seconds": round(seconds, 1)})
        self.api.exam_submit({"id": exam_id, "elapsed": 9000})
        return self.api.exam_result(exam_id)

    def test_the_waterfall_lands_on_the_score_that_was_scored(self):
        result = self.sit()
        w = result["waterfall"]
        # The exam samples to the blueprint, so weighted and raw agree.
        self.assertAlmostEqual(w["earned"] / 100.0, result["raw"], places=2)

    def test_the_rushed_domain_leads_the_waterfall(self):
        result = self.sit(rushed_domain="4")
        self.assertEqual(result["waterfall"]["steps"][0]["domain"], "4")

    def test_timing_reaches_the_payload_with_a_point_per_question(self):
        result = self.sit()
        timing = result["timing"]
        self.assertEqual(len(timing["points"]), result["total"])
        self.assertTrue(timing["enough"])
        self.assertFalse(timing["gap"]["spans_zero"])

    def test_the_scaled_estimate_is_untouched_by_any_of_this(self):
        result = self.sit()
        self.assertIn("scaled", result)
        self.assertIn("pass_mark", result)
        for key in ("waterfall", "timing"):
            self.assertNotIn("scaled", str(result[key]))

    def test_an_answer_without_a_question_id_is_refused(self):
        """It used to save under `state.answers[None]` and report ok.

        Found by sending the wrong parameter name: a 150-question exam came
        back with zero answers, a clean save and no error anywhere.
        """
        exam_id = self.api.exam_new({"n": 20})["id"]
        with self.assertRaises(ApiError):
            self.api.exam_update({"id": exam_id, "action": "answer",
                                  "chosen": "A", "seconds": 5})
        with self.assertRaises(ApiError):
            self.api.exam_update({"id": exam_id, "action": "flag"})
        self.assertEqual(self.api.exam_get(exam_id)["answers"], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
