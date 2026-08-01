"""Tests for the next-session recommender.

Three of these matter more than the rest:

* every recommendation states its reason with numbers, or it does not appear.
  This is the whole difference between a recommender and a slot machine, and
  it is the one thing this screen can quietly lose.
* thin evidence is *withheld with a reason*, never guessed at. An empty plan
  with four stated reasons is the honest output for a new profile.
* a well-measured deficit outranks a barely-tested one. Ranking everything on
  the lower confidence bound - correct for a list you browse - spends a
  thirty-minute budget on whatever happens to be noisiest.

    python tests/test_nextsession.py
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import loader, nextsession, simulation, store  # noqa: E402
from drillkit.webapi import Api  # noqa: E402

# Language that would turn an evidence line into a forecast. CLAUDE.md 3.7.
FORECAST_WORDS = (
    "predict", "readiness", "ready to sit", "will pass", "likely to pass",
    "forecast", "chance of", "probability of passing", "on track to pass",
    "expected score", "projected score", "scaled score",
)


def rows_from(spec: simulation.LearnerSpec, bank: simulation.Bank):
    return simulation.generate(spec, bank)


class NextSessionBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = simulation.Bank.load("cisa")
        cls.questions = cls.bank.questions
        cls.rules = cls.bank.rules

    def build(self, rows, **kw):
        return nextsession.build(self.questions, rows, self.rules,
                                 kw.pop("cases", []), **kw)


class TestEveryRecommendationCarriesItsEvidence(NextSessionBase):
    """The rule the screen exists to enforce."""

    def test_no_recommendation_reaches_a_screen_without_numbers(self):
        spec = simulation.LearnerSpec(seed=3, attempts=500, baseline=0.75)
        data = self.build(rows_from(spec, self.bank))
        shown = data["recommendations"] + data["also"]
        self.assertTrue(shown, "fixture must produce something to check")
        for rec in shown:
            self.assertTrue(
                any(ch.isdigit() for ch in rec["evidence"]),
                "%r has no numbers in its evidence" % rec["title"])

    def test_the_guard_is_not_decorative(self):
        """A numberless reason raises rather than reaching a screen."""
        bad = nextsession.Recommendation(
            kind="rule", title="Trust me", evidence="Recommended for you",
            minutes=5)
        with self.assertRaises(ValueError):
            nextsession.require_evidence([bad])

    def test_the_guard_runs_on_every_build(self):
        spec = simulation.LearnerSpec(seed=12, attempts=300)
        rows = rows_from(spec, self.bank)
        original = nextsession._due

        def slogan(questions, rows_, pace, out, held, now=None):
            out.append(nextsession.Recommendation(
                kind="due", title="Just trust me", evidence="Recommended",
                minutes=5))

        nextsession._due = slogan
        try:
            with self.assertRaises(ValueError):
                self.build(rows)
        finally:
            nextsession._due = original

    def test_every_interval_is_reported_as_an_interval(self):
        spec = simulation.LearnerSpec(seed=4, attempts=500, baseline=0.7)
        data = self.build(rows_from(spec, self.bank))
        for rec in data["recommendations"] + data["also"]:
            if rec["kind"] in ("rule", "topic"):
                self.assertIn("95% CI", rec["evidence"],
                              "%r quotes an accuracy with no interval" % rec["title"])


class TestNothingPredicts(NextSessionBase):
    def test_no_forecast_language_in_anything_the_learner_reads(self):
        spec = simulation.LearnerSpec(seed=5, attempts=800, baseline=0.8)
        data = self.build(rows_from(spec, self.bank))
        read = []
        for rec in data["recommendations"] + data["also"]:
            read += [rec["title"], rec["evidence"]]
        read += [w["reason"] for w in data["withheld"]]
        for text in read:
            for word in FORECAST_WORDS:
                self.assertNotIn(word, text.lower(),
                                 "%r reads as a forecast" % text)

    def test_the_scaled_estimate_never_appears_here(self):
        spec = simulation.LearnerSpec(seed=6, attempts=400)
        blob = json.dumps(self.build(rows_from(spec, self.bank)))
        for field in ("scaled", "predicted", "readiness", "pass_probability"):
            self.assertNotIn(field, blob.lower())


class TestThinEvidenceIsWithheldNotGuessed(NextSessionBase):
    def test_a_cold_profile_recommends_only_what_it_can_justify(self):
        data = self.build([])
        for rec in data["recommendations"]:
            self.assertIn(rec["kind"], ("unseen", "case"),
                          "%r was recommended with no history at all" % rec["title"])

    def test_a_cold_profile_says_what_it_could_not_measure(self):
        data = self.build([])
        kinds = {w["kind"] for w in data["withheld"]}
        self.assertIn("rule", kinds)
        self.assertIn("topic", kinds)
        self.assertIn("dangerous", kinds)
        for item in data["withheld"]:
            self.assertTrue(item["reason"].strip().endswith("."),
                            "%r is not a sentence" % item["reason"])

    def test_withheld_reasons_state_the_threshold_they_failed(self):
        data = self.build([])
        for item in data["withheld"]:
            self.assertTrue(any(ch.isdigit() for ch in item["reason"]),
                            "%r does not say how much evidence is missing"
                            % item["reason"])

    def test_a_wide_interval_is_labelled_unresolved_not_weak(self):
        # 4 of 13 is 13-58%: a gap, not a finding.
        self.assertFalse(nextsession._claimable(4, 13))
        # 28 of 89 is 23-42%: narrow enough to claim.
        self.assertTrue(nextsession._claimable(28, 89))

    def test_the_claim_gate_is_about_width_not_count(self):
        """A count threshold alone would call 4-of-13 measured."""
        self.assertGreaterEqual(13, nextsession.MIN_CLAIM_ATTEMPTS)
        self.assertFalse(nextsession._claimable(4, 13))


class TestRankingSpendsTheBudgetOnTheBestEvidence(NextSessionBase):
    """The regression this ranking was rebuilt for.

    Found by running the recommender against a planted weakness: the rule
    carrying it, measured over 89 answers at 23-42%, was pushed out of the plan
    by a topic seen 13 times at 13-58%. The thin item won purely by being
    uncertain.
    """

    def test_a_measured_deficit_outranks_a_thin_one(self):
        measured = nextsession.Recommendation(
            kind="rule", title="measured", evidence="28 of 89", minutes=9,
            basis="measured", group=nextsession.GROUP_MEASURED, rank=0.42)
        thin = nextsession.Recommendation(
            kind="topic", title="thin", evidence="4 of 13", minutes=9,
            basis="unresolved", group=nextsession.GROUP_UNRESOLVED, rank=0.13)
        chosen = nextsession.plan([thin, measured], minutes=9)
        self.assertEqual([r.title for r in chosen], ["measured"])

    def test_the_planted_weakness_reaches_the_plan(self):
        spec = simulation.LearnerSpec(
            seed=7, attempts=600, baseline=0.78,
            weaknesses=(simulation.Weakness("principle", "evidence-quality", 0.30),))
        data = self.build(rows_from(spec, self.bank))
        planned = [r for r in data["recommendations"] if r["kind"] == "rule"]
        self.assertTrue(planned, "no rule made the plan at all")
        self.assertEqual(planned[0]["detail"]["principle"], "evidence-quality",
                         "the planted weakness did not lead the rules")

    def test_repair_outranks_every_measured_deficit(self):
        spec = simulation.LearnerSpec(seed=8, attempts=400, baseline=0.6)
        data = self.build(rows_from(spec, self.bank))
        groups = [r["group"] for r in data["recommendations"]]
        self.assertEqual(groups, sorted(groups), "the plan is not in group order")

    def test_context_never_leads(self):
        spec = simulation.LearnerSpec(seed=9, attempts=400, baseline=0.7)
        data = self.build(rows_from(spec, self.bank))
        shown = data["recommendations"] + data["also"]
        coverage = [i for i, r in enumerate(shown) if r["kind"] == "coverage"]
        for index in coverage:
            self.assertNotEqual(index, 0, "pace arithmetic led the screen")


class TestTheBudgetIsRespected(NextSessionBase):
    def test_the_plan_fits(self):
        spec = simulation.LearnerSpec(seed=10, attempts=500, baseline=0.7)
        for minutes in (10, 30, 60):
            data = self.build(rows_from(spec, self.bank), minutes=minutes)
            spent = sum(r["minutes"] for r in data["recommendations"])
            self.assertLessEqual(spent, minutes)

    def test_what_did_not_fit_is_still_reported(self):
        spec = simulation.LearnerSpec(seed=11, attempts=500, baseline=0.65)
        small = self.build(rows_from(spec, self.bank), minutes=10)
        large = self.build(rows_from(spec, self.bank), minutes=240)
        self.assertLess(len(small["recommendations"]), len(large["recommendations"]))
        self.assertEqual(
            len(small["recommendations"]) + len(small["also"]),
            len(large["recommendations"]) + len(large["also"]),
            "shrinking the budget dropped items instead of moving them")


class TestPaceIsMeasuredOrDeclared(NextSessionBase):
    def test_a_learners_own_timing_is_used_when_there_is_enough(self):
        rows = [{"seconds": 40.0} for _ in range(nextsession.MIN_TIMED)]
        pace = nextsession.seconds_per_question(rows)
        self.assertTrue(pace["measured"])
        self.assertEqual(pace["seconds"], 40.0)

    def test_too_little_timing_falls_back_and_says_so(self):
        pace = nextsession.seconds_per_question([{"seconds": 40.0}])
        self.assertFalse(pace["measured"])
        self.assertEqual(pace["seconds"], nextsession.ASSUMED_SECONDS)

    def test_one_abandoned_question_does_not_set_the_pace(self):
        """Median, not mean - a question left open over lunch is not evidence."""
        rows = [{"seconds": 40.0} for _ in range(nextsession.MIN_TIMED)]
        rows.append({"seconds": 9000.0})
        self.assertLess(nextsession.seconds_per_question(rows)["seconds"], 60)


class TestTheApiSurface(unittest.TestCase):
    def setUp(self):
        self.profile = "nexttest-%s" % os.urandom(4).hex()
        self.api = Api("cisa", self.profile)
        self.addCleanup(self._cleanup)

    def seed(self, spec):
        bank = simulation.Bank.load("cisa")
        rows = simulation.generate(spec, bank)
        os.makedirs(os.path.dirname(self.api.results_path), exist_ok=True)
        with open(self.api.results_path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def _cleanup(self):
        directory = loader.results_dir("cisa", self.profile)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)

    def test_the_endpoint_answers_for_a_profile_with_no_history(self):
        data = self.api.next_session()
        self.assertEqual(data["minutes"], nextsession.DEFAULT_MINUTES)
        self.assertTrue(data["withheld"], "a cold profile must explain itself")
        self.assertFalse(data["pace"]["measured"])

    def test_the_budget_is_clamped_to_something_sane(self):
        self.assertGreaterEqual(self.api.next_session(0)["minutes"], 5)
        self.assertLessEqual(self.api.next_session(100000)["minutes"], 240)

    def test_every_drill_action_actually_starts_that_drill(self):
        """The contract that keeps a recommendation from being decorative.

        Each row links somewhere using the `action` the engine chose. If those
        parameter names drift from what `drill_start` accepts, the screen still
        renders perfectly and every link quietly lands on an unconfigured
        session - a failure with no visible symptom.
        """
        self.seed(simulation.LearnerSpec(seed=21, attempts=500, baseline=0.7))
        data = self.api.next_session(240)
        actions = [r["action"] for r in data["recommendations"] + data["also"]
                   if r["action"].get("screen") == "drill"]
        self.assertTrue(actions, "fixture produced no drill recommendations")

        for action in actions:
            params = {k: v for k, v in action.items() if k != "screen"}
            started = self.api.drill_start(dict(params))
            self.assertTrue(started["questions"],
                            "%r started an empty drill" % params)
            if params.get("principle"):
                self.assertEqual(started["mode"], params.get("mode"))

    def test_a_topic_action_serves_that_topic(self):
        self.seed(simulation.LearnerSpec(seed=22, attempts=500, baseline=0.65))
        data = self.api.next_session(240)
        topics = [r["action"] for r in data["recommendations"] + data["also"]
                  if r["action"].get("topic")]
        self.assertTrue(topics, "fixture produced no topic recommendations")
        for action in topics:
            started = self.api.drill_start(
                {"topic": action["topic"], "n": action.get("n", 10)})
            for q in started["questions"]:
                self.assertIn(action["topic"].lower(), q["topic"].lower())

    def test_it_reads_the_profile_and_writes_nothing(self):
        before = os.path.exists(self.api.results_path)
        self.api.next_session()
        self.assertEqual(os.path.exists(self.api.results_path), before,
                         "asking what to study next created an attempt log")


if __name__ == "__main__":
    unittest.main(verbosity=2)
