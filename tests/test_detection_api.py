"""Tests for persisting a sweep and serving it to the app.

The properties that matter:

* the screen must never trigger a sweep - a full run is roughly fifteen minutes,
  so a surface that recomputed on load would be unusable;
* "no sweep has been run" is an honest answer and must be served as data, not
  as an error;
* the numbers in the JSON must be the same numbers as the markdown, because two
  artefacts from one run that disagree are worse than one;
* every rate keeps its interval and its denominator all the way to the client.

    python tests/test_detection_api.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import simulation  # noqa: E402
from drillkit.webapi import Api  # noqa: E402


def cell(check_id, attempts, hits, fp, runs=200):
    return simulation.CellResult(check_id, attempts,
                                 simulation.Rate(hits, runs),
                                 simulation.Rate(fp, runs))


class PayloadTestBase(unittest.TestCase):
    bank = None

    @classmethod
    def setUpClass(cls):
        cls.bank = simulation.Bank.load("cisa")


class TestThePayload(PayloadTestBase):
    def _payload(self):
        results = [
            cell("1", 300, 192, 12), cell("1", 3000, 200, 10),
            cell("4", 300, 8, 0), cell("4", 3000, 110, 176),
        ]
        return simulation.results_payload(
            results, self.bank, 200, (300, 3000), generated="2026-07-31T12:00:00")

    def test_it_serialises_to_json(self):
        text = json.dumps(self._payload())
        self.assertIn("checks", text)

    def test_every_rate_keeps_its_interval_and_denominator(self):
        for check in self._payload()["checks"]:
            for c in check["cells"]:
                for side in ("detection", "false_positive"):
                    rate = c[side]
                    self.assertIn("runs", rate)
                    self.assertIsNotNone(rate["low"], side)
                    self.assertIsNotNone(rate["high"], side)
                    self.assertLessEqual(rate["low"], rate["rate"])
                    self.assertGreaterEqual(rate["high"], rate["rate"])

    def test_what_was_planted_travels_with_the_numbers(self):
        """A detection rate is meaningless without knowing what produced it."""
        for check in self._payload()["checks"]:
            self.assertTrue(check["planted"], check["id"])
            self.assertTrue(check["diagnostic"], check["id"])

    def test_a_failing_check_reports_no_trustworthy_size(self):
        checks = {c["id"]: c for c in self._payload()["checks"]}
        self.assertIsNone(checks["4"]["trustworthy_from"])
        self.assertEqual(checks["1"]["trustworthy_from"], 300)

    def test_the_thresholds_are_published_not_implied(self):
        thresholds = self._payload()["thresholds"]
        self.assertEqual(thresholds["detection_floor"], simulation.TRUST_DETECTION)
        self.assertEqual(thresholds["false_positive_ceiling"],
                         simulation.TRUST_FALSE_POSITIVE)

    def test_the_findings_survive_into_the_payload(self):
        findings = self._payload()["findings"]
        self.assertTrue(findings)
        self.assertTrue(any("does not hold" in f for f in findings))

    def test_json_and_markdown_agree(self):
        """Two artefacts from one run that disagree are worse than one."""
        results = [cell("1", 300, 192, 12), cell("1", 3000, 200, 10)]
        payload = simulation.results_payload(
            results, self.bank, 200, (300, 3000), generated="2026-07-31")
        report = simulation.render_report(
            results, self.bank, 200, (300, 3000), generated="2026-07-31")
        self.assertIn("300 answers", report)
        self.assertEqual(payload["checks"][0]["trustworthy_from"], 300)
        self.assertIn(str(payload["seeds"]), report)

    def test_a_round_trip_through_disk_preserves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "detection.json")
            simulation.write_results(self._payload(), path)
            back = simulation.load_results(path)
        self.assertEqual(back["seeds"], 200)
        self.assertEqual(len(back["checks"]), 2)

    def test_a_missing_file_reads_as_none_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                simulation.load_results(os.path.join(tmp, "absent.json")))

    def test_a_corrupt_file_reads_as_none_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "detection.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{ truncated")
            self.assertIsNone(simulation.load_results(path))


class TestTheApi(unittest.TestCase):
    def test_it_serves_whatever_has_been_persisted(self):
        api = Api("cisa")
        data = api.detection()
        self.assertIn("available", data)
        if data["available"]:
            self.assertIn("checks", data)
            self.assertIn("seeds", data)
        else:
            self.assertIn("command", data)
            self.assertIn("reason", data)

    def test_the_empty_state_is_data_not_an_error(self):
        """'Nobody has measured this yet' is an honest answer for a screen
        whose whole subject is evidence."""
        import drillkit.simulation as sim
        original = sim.RESULTS_FILE
        try:
            sim.RESULTS_FILE = "definitely-not-a-real-file.json"
            data = Api("cisa").detection()
        finally:
            sim.RESULTS_FILE = original
        self.assertFalse(data["available"])
        self.assertIn("simulate", data["command"])

    def test_serving_never_runs_a_sweep(self):
        """A full sweep is minutes of CPU. The endpoint must only ever read."""
        import drillkit.simulation as sim
        called = []
        original = sim.run_sweep
        try:
            sim.run_sweep = lambda *a, **k: called.append(1) or []
            Api("cisa").detection()
        finally:
            sim.run_sweep = original
        self.assertEqual(called, [], "the endpoint triggered a sweep")

    def test_serving_does_not_read_the_learner_history(self):
        """The report card is about the tool, not about the person using it."""
        api = Api("cisa", "detect-%s" % os.urandom(3).hex())
        called = []
        original = api.rows
        api.rows = lambda: called.append(1) or []
        api.detection()
        api.rows = original
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
