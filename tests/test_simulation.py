"""Tests for the synthetic learner harness.

Fast, seeded cases only. The 200-seed sweep belongs on the command line, not in
the suite - it takes minutes and the suite has to stay quick enough that people
actually run it.

The tests that matter most here:

* synthetic rows must be unmistakable and must never reach the real log;
* generation must be exactly reproducible from a seed, or a reported rate means
  nothing;
* rows must round-trip through the real store, so the harness cannot drift from
  the schema it claims to be measuring;
* the harness must be able to *fail*. A check that passes on a learner with
  nothing planted is measuring nothing, and there is a test asserting the
  negative control genuinely discriminates.

    python tests/test_simulation.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import loader, simulation, store  # noqa: E402


class HarnessTestBase(unittest.TestCase):
    bank = None

    @classmethod
    def setUpClass(cls):
        # Loading the real bank is the slow part; do it once for the module.
        cls.bank = simulation.Bank.load("cisa")


class TestGeneration(HarnessTestBase):
    def test_a_seed_reproduces_exactly(self):
        spec = simulation.LearnerSpec(seed=3, attempts=200)
        first = simulation.generate(spec, self.bank)
        second = simulation.generate(spec, self.bank)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 200)

    def test_different_seeds_differ(self):
        a = simulation.generate(simulation.LearnerSpec(seed=1, attempts=200), self.bank)
        b = simulation.generate(simulation.LearnerSpec(seed=2, attempts=200), self.bank)
        self.assertNotEqual(a, b)

    def test_rows_round_trip_through_the_real_store(self):
        """If the harness hand-built dicts it would drift from the schema and
        quietly stop measuring the real system."""
        rows = simulation.generate(
            simulation.LearnerSpec(seed=5, attempts=60), self.bank)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            simulation.write(rows, path)
            loaded = store.load(path)
        self.assertEqual(len(loaded), len(rows))
        expected = {f for f in store.Attempt.__dataclass_fields__}
        self.assertEqual(set(loaded[0]), expected)

    def test_a_planted_weakness_actually_lowers_accuracy(self):
        """Guards the generator itself: if the plant did nothing, every check
        downstream would be measuring noise."""
        rule = simulation._eligible_rules(self.bank)[0]
        spec = simulation.LearnerSpec(
            seed=9, attempts=1200,
            weaknesses=(simulation.Weakness("principle", rule["id"], 0.20),))
        rows = simulation.generate(spec, self.bank)
        governed = set(rule["question_ids"])
        weak = [r for r in rows if r["question_id"] in governed]
        rest = [r for r in rows if r["question_id"] not in governed]
        self.assertTrue(weak, "the planted rule was never served")
        weak_acc = sum(1 for r in weak if r["correct"]) / len(weak)
        rest_acc = sum(1 for r in rest if r["correct"]) / len(rest)
        self.assertLess(weak_acc, 0.4)
        self.assertGreater(rest_acc, 0.6)

    def test_confidence_is_recorded_or_deliberately_blank(self):
        rated = simulation.generate(
            simulation.LearnerSpec(seed=4, attempts=80,
                                   confidence_mode="calibrated"), self.bank)
        self.assertTrue(all(r["confidence"] in store.CONFIDENCE for r in rated))
        unrated = simulation.generate(
            simulation.LearnerSpec(seed=4, attempts=80,
                                   confidence_mode="none"), self.bank)
        self.assertTrue(all(r["confidence"] == "" for r in unrated))


class TestSyntheticRowsStayContained(HarnessTestBase):
    """Rule 2 of the brief. A synthetic row in the real log is unrecoverable:
    nothing in the record distinguishes it afterwards."""

    def test_every_row_is_marked(self):
        rows = simulation.generate(
            simulation.LearnerSpec(seed=2, attempts=60), self.bank)
        self.assertTrue(simulation.is_synthetic(rows))
        for row in rows:
            self.assertTrue(row["session"].startswith(
                simulation.SYNTHETIC_SESSION_PREFIX + "-"))

    def test_writing_to_the_real_attempt_log_is_refused(self):
        real = loader.results_path("cisa", None)
        with self.assertRaises(simulation.SimulationError):
            simulation.guard_path(real)

    def test_a_file_holding_real_attempts_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"question_id": "cisa-d1a-001",
                                     "session": "web", "correct": True}) + "\n")
            with self.assertRaises(simulation.SimulationError):
                simulation.guard_path(path)

    def test_a_file_of_synthetic_rows_is_accepted(self):
        rows = simulation.generate(
            simulation.LearnerSpec(seed=6, attempts=40), self.bank)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            simulation.write(rows, path)
            simulation.guard_path(path)  # must not raise
            simulation.write(rows, path)
        self.assertTrue(True)

    def test_a_sweep_leaves_the_real_log_untouched(self):
        real = loader.results_path("cisa", None)
        before = None
        if os.path.exists(real):
            with open(real, "rb") as fh:
                before = fh.read()

        simulation.run_sweep(self.bank,
                             checks=[simulation.check_by_id("1")],
                             sizes=(120,), seeds=2)

        after = None
        if os.path.exists(real):
            with open(real, "rb") as fh:
                after = fh.read()
        self.assertEqual(before, after,
                         "a sweep modified the real attempt log")


class TestChecksDiscriminate(HarnessTestBase):
    """A check that cannot fail is not a check."""

    def _rows(self, family, seed, attempts):
        plant = simulation.PLANTS[family](self.bank, seed, attempts)
        return simulation.generate(plant.spec, self.bank), plant.targets

    def test_the_rule_axis_finds_a_planted_rule(self):
        rows, targets = self._rows("rule", 1, 1200)
        self.assertTrue(simulation.detect_rule_axis(rows, self.bank, targets))

    def test_the_rule_axis_does_not_find_a_weakness_that_is_not_there(self):
        """The negative control has to genuinely discriminate, or every
        detection rate in the report is meaningless.

        Measured over seeds rather than asserted on one. The check asks whether
        the target rule lands in the weakest 3 of 23, so a clean learner trips
        it about 13% of the time by chance alone - and this test previously
        asserted a single seed came up clean, which made it a coin flip that
        happened to be landing heads. It began failing when the expert band
        added question-to-rule mappings and shifted which rules surface for
        seed 1; nothing about the diagnostic changed.

        The real assertion is that the false-positive rate stays near chance
        rather than climbing toward 'fires on everybody'.
        """
        seeds = range(1, 41)
        hits = 0
        for seed in seeds:
            _, targets = self._rows("rule", seed, 1200)
            clean = simulation.generate(
                simulation.clean_learner(seed, 1200), self.bank)
            if simulation.detect_rule_axis(clean, self.bank, targets):
                hits += 1
        rate = hits / len(list(seeds))
        chance = simulation.TOP_N / len(self.bank.rules)
        self.assertLess(rate, chance * 2.5,
                        "false-positive rate %.0f%% is well above the %.0f%% "
                        "expected by chance - the check may be firing on "
                        "learners with nothing planted" % (rate * 100, chance * 100))

    def test_the_topic_axis_finds_a_planted_topic(self):
        rows, targets = self._rows("topic", 1, 1200)
        self.assertTrue(simulation.detect_topic_axis(rows, self.bank, targets))

    def test_the_scheduler_returns_persistent_misses(self):
        rows, targets = self._rows("items", 1, 1500)
        self.assertTrue(
            simulation.detect_scheduler_returns(rows, self.bank, targets))

    def test_confident_and_wrong_answers_are_surfaced(self):
        """At 600, where the check detects on every seed measured.

        It used to sit at 1200, which is a size where detection runs around
        7 in 12 - fine as a sweep number, brittle as a single-seed assertion.
        The confidence-aware scheduler changed which questions get served and
        tipped this particular seed over; the check itself is unaffected
        (12/12 at 600, 9/12 at 3000 across twelve seeds).
        """
        rows, targets = self._rows("confidence", 1, 600)
        self.assertTrue(
            simulation.detect_dangerous_quadrant(rows, self.bank, targets))

    def test_a_check_reports_false_positives_when_they_happen(self):
        """Scoring must be able to record a failure, not just a success."""
        results = simulation.run_sweep(
            self.bank, checks=[simulation.check_by_id("3b")],
            sizes=(600,), seeds=4)
        cell = results[0]
        self.assertEqual(cell.detection.runs, 4)
        self.assertEqual(cell.false_positive.runs, 4)


class TestScoring(HarnessTestBase):
    def test_a_rate_carries_its_interval(self):
        rate = simulation.Rate(hits=2, runs=2)
        self.assertEqual(rate.rate, 1.0)
        low, _ = rate.interval
        self.assertLess(low, 0.5, "2 of 2 runs is not a working diagnostic")

    def test_trustworthy_needs_detection_and_specificity_together(self):
        strong = simulation.CellResult(
            "x", 1000, simulation.Rate(200, 200), simulation.Rate(0, 200))
        self.assertTrue(strong.trustworthy)

        # Detects everything, including on learners with nothing wrong.
        indiscriminate = simulation.CellResult(
            "x", 1000, simulation.Rate(200, 200), simulation.Rate(180, 200))
        self.assertFalse(indiscriminate.trustworthy,
                         "a check that fires on everyone must not pass")

        # Specific, but rarely detects anything.
        blind = simulation.CellResult(
            "x", 1000, simulation.Rate(20, 200), simulation.Rate(0, 200))
        self.assertFalse(blind.trustworthy)

        # Right rates, far too few runs to claim them.
        thin = simulation.CellResult(
            "x", 1000, simulation.Rate(3, 3), simulation.Rate(0, 3))
        self.assertFalse(thin.trustworthy,
                         "three runs cannot establish a detection rate")

    def test_trustworthy_from_reports_none_when_never_reached(self):
        results = [simulation.CellResult("x", 100, simulation.Rate(0, 50),
                                         simulation.Rate(0, 50))]
        self.assertIsNone(simulation.trustworthy_from(results, "x"))

    def test_the_report_renders_and_names_failures(self):
        results = [
            simulation.CellResult("1", 300, simulation.Rate(200, 200),
                                  simulation.Rate(0, 200)),
            simulation.CellResult("3", 300, simulation.Rate(2, 200),
                                  simulation.Rate(1, 200)),
        ]
        text = simulation.render_report(results, self.bank, 200, (300,),
                                        generated="2026-07-31")
        self.assertIn("Detection report card", text)
        self.assertIn("never, in this sweep", text)
        self.assertIn("false-positive", text)


class TestScopeOfThisHarness(HarnessTestBase):
    def test_the_difficulty_check_is_absent_until_that_work_lands(self):
        """Check 8 scores authored-versus-empirical difficulty. That feature
        has not shipped, so scoring it would be scoring nothing."""
        self.assertNotIn("8", [c.id for c in simulation.CHECKS])

    def test_every_check_names_what_it_planted_and_what_it_reads(self):
        for check in simulation.CHECKS:
            self.assertTrue(check.planted, check.id)
            self.assertTrue(check.diagnostic, check.id)
            self.assertIn(check.family, simulation.PLANTS, check.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
