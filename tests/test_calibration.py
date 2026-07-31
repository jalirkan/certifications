"""Tests for confidence capture and the calibration reports.

The ones that matter most:

* an attempt written before this feature existed must still load, still be
  counted, and never be assigned a confidence it did not have;
* every rate carries a Wilson interval and is gated on a minimum sample, so a
  cell built on three answers cannot read as a finding;
* nothing here is collapsed into a single "calibration score";
* the scheduler is untouched - using confidence to shorten intervals is
  explicitly a later phase.

    python tests/test_calibration.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import (  # noqa: E402
    calibration, loader, scheduler, session as session_mod, store,
)
from drillkit.loader import Question  # noqa: E402
from drillkit.webapi import Api  # noqa: E402


def q(qid: str, domain: str = "5", answer: str = "B") -> Question:
    others = [k for k in "ABCD" if k != answer]
    return Question(
        id=qid, domain=domain, section="A", topic="Data Encryption",
        stem="Which control is BEST?",
        options={"A": "alpha", "B": "bravo", "C": "charlie", "D": "delta"},
        answer=answer, why_correct="because",
        why_wrong={k: "no" for k in others},
    )


def row(qid, correct, confidence=None, ts="2026-07-27T00:00:00+00:00", domain="5"):
    """A stored attempt. `confidence=None` omits the key entirely."""
    out = {"ts": ts, "session": "s1", "question_id": qid, "cert": "CISA",
           "domain": domain, "section": "A", "topic": "Data Encryption",
           "chosen": "B", "answer": "B", "correct": correct,
           "seconds": 40.0, "mode": "smart"}
    if confidence is not None:
        out["confidence"] = confidence
    return out


class TestExistingHistoryKeepsWorking(unittest.TestCase):
    """Rule 1: this feature must not invalidate a single existing row."""

    def test_a_record_without_the_field_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            legacy = row("q1", True)  # no confidence key at all
            self.assertNotIn("confidence", legacy)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(legacy) + "\n")
            rows = store.load(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("confidence", ""), "")

    def test_unlabelled_rows_are_counted_not_guessed_at(self):
        rows = [row("q1", True), row("q2", False),
                row("q3", True, "confident")]
        report = calibration.report(rows, [q("q1"), q("q2"), q("q3")], [])
        self.assertEqual(report["attempts"], 3)
        self.assertEqual(report["labelled"], 1)
        self.assertEqual(report["unlabelled"], 2)
        # The two unlabelled rows must not appear in any confidence cell.
        self.assertEqual(sum(c["attempts"] for c in report["curve"]), 1)

    def test_an_attempt_defaults_to_no_confidence(self):
        attempt = store.Attempt(
            ts="t", session="s", question_id="q", cert="CISA", domain="5",
            section="A", topic="t", chosen="B", answer="B", correct=True,
            seconds=1.0, mode="smart")
        self.assertEqual(attempt.confidence, "")

    def test_unknown_confidence_values_are_dropped_not_stored(self):
        for junk in ("maybe", "4", None, "", "  "):
            self.assertEqual(store.normalise_confidence(junk), "")
        for key, level in (("1", "guess"), ("2", "unsure"), ("3", "confident")):
            self.assertEqual(store.normalise_confidence(key), level)
        self.assertEqual(store.normalise_confidence("CONFIDENT"), "confident")


class TestTheCurve(unittest.TestCase):
    def test_accuracy_is_reported_per_level_with_an_interval(self):
        rows = ([row("q1", True, "confident") for _ in range(9)]
                + [row("q1", False, "confident")]
                + [row("q2", False, "guess") for _ in range(10)])
        curve = {c["level"]: c for c in calibration.curve(rows)}
        self.assertEqual(curve["confident"]["attempts"], 10)
        self.assertAlmostEqual(curve["confident"]["accuracy"], 0.9)
        self.assertEqual(curve["guess"]["accuracy"], 0.0)
        for cell in curve.values():
            if cell["attempts"]:
                self.assertIsNotNone(cell["low"])
                self.assertIsNotNone(cell["high"])
                self.assertLessEqual(cell["low"], cell["accuracy"])
                self.assertGreaterEqual(cell["high"], cell["accuracy"])

    def test_a_thin_level_is_flagged_as_not_enough(self):
        rows = [row("q1", True, "confident"), row("q1", True, "confident")]
        cell = {c["level"]: c for c in calibration.curve(rows)}["confident"]
        self.assertEqual(cell["accuracy"], 1.0)
        self.assertFalse(cell["enough"], "2 of 2 must not read as a finding")
        self.assertLess(cell["low"], 0.5, "2/2 is not certainty")

    def test_an_untouched_level_claims_nothing(self):
        cell = {c["level"]: c for c in calibration.curve([])}["guess"]
        self.assertEqual(cell["attempts"], 0)
        self.assertIsNone(cell["accuracy"])
        self.assertIsNone(cell["low"])


class TestTheQuadrants(unittest.TestCase):
    def test_confident_and_wrong_is_surfaced_most_recent_first(self):
        rows = [
            row("q1", False, "confident", ts="2026-07-01T00:00:00+00:00"),
            row("q2", False, "confident", ts="2026-07-20T00:00:00+00:00"),
            row("q3", False, "guess", ts="2026-07-25T00:00:00+00:00"),
            row("q4", True, "confident", ts="2026-07-26T00:00:00+00:00"),
        ]
        items = calibration.dangerous(rows, {x.id: x for x in
                                             [q("q1"), q("q2"), q("q3"), q("q4")]})
        self.assertEqual([i["question_id"] for i in items], ["q2", "q1"])

    def test_lucky_covers_guessed_and_unsure_correct_answers(self):
        rows = [row("q1", True, "guess"), row("q2", True, "unsure"),
                row("q3", True, "confident"), row("q4", False, "guess")]
        items = calibration.lucky(rows, {})
        self.assertEqual({i["question_id"] for i in items}, {"q1", "q2"})

    def test_the_governing_rule_travels_with_a_dangerous_item(self):
        rules = [{"id": "evidence-quality", "name": "Evidence quality",
                  "question_ids": ["q1"]}]
        index = calibration.rule_index(rules)
        items = calibration.dangerous([row("q1", False, "confident")],
                                      {"q1": q("q1")}, index)
        self.assertEqual(items[0]["rule"], "evidence-quality")


class TestTheGap(unittest.TestCase):
    def test_the_gap_contrasts_confident_against_not_confident(self):
        rows = ([row("q1", True, "confident") for _ in range(8)]
                + [row("q2", False, "guess") for _ in range(8)])
        gap = calibration.overconfidence_gap(rows)
        self.assertAlmostEqual(gap["confident_accuracy"], 1.0)
        self.assertAlmostEqual(gap["other_accuracy"], 0.0)
        self.assertAlmostEqual(gap["gap"], 1.0)
        self.assertTrue(gap["enough"])

    def test_the_contrast_is_not_diluted_by_the_confident_answers_themselves(self):
        """Overall accuracy contains the confident answers, so measuring against
        it shrinks the gap by roughly the confident share of the log. This is
        the bug the original brief specified; the assertion pins the fix."""
        rows = ([row("q1", True, "confident") for _ in range(50)]
                + [row("q2", False, "guess") for _ in range(50)])
        gap = calibration.overconfidence_gap(rows)
        diluted = gap["confident_accuracy"] - gap["overall_accuracy"]
        self.assertAlmostEqual(diluted, 0.5)
        self.assertAlmostEqual(gap["gap"], 1.0)
        self.assertGreater(gap["gap"], diluted)

    def test_a_thin_gap_is_gated(self):
        gap = calibration.overconfidence_gap([row("q1", True, "confident")])
        self.assertFalse(gap["enough"])

    def test_a_flat_curve_produces_a_gap_near_zero(self):
        rows = []
        for level in ("guess", "unsure", "confident"):
            rows += [row("q1", i % 2 == 0, level) for i in range(10)]
        gap = calibration.overconfidence_gap(rows)
        self.assertLess(abs(gap["gap"]), 0.05,
                        "confidence carrying no information must show as ~0")

    def test_a_flat_curve_reports_an_interval_that_includes_zero(self):
        """The point estimate is not the finding. A gap whose interval spans
        zero must be readable as 'no relationship yet', or a learner will act
        on noise."""
        rows = []
        for level in ("guess", "unsure", "confident"):
            rows += [row("q1", i % 2 == 0, level) for i in range(10)]
        gap = calibration.overconfidence_gap(rows)
        self.assertIsNotNone(gap["gap_low"])
        self.assertTrue(gap["spans_zero"])
        self.assertLessEqual(gap["gap_low"], 0.0)
        self.assertGreaterEqual(gap["gap_high"], 0.0)

    def test_a_real_separation_reports_an_interval_that_excludes_zero(self):
        rows = ([row("q1", i < 45, "confident") for i in range(50)]
                + [row("q2", i < 10, "guess") for i in range(50)])
        gap = calibration.overconfidence_gap(rows)
        self.assertFalse(gap["spans_zero"])
        self.assertGreater(gap["gap_low"], 0.0)

    def test_the_gap_interval_is_absent_rather_than_invented_when_a_cell_is_empty(self):
        rows = [row("q1", True, "confident") for _ in range(8)]
        gap = calibration.overconfidence_gap(rows)
        self.assertIsNone(gap["gap"])
        self.assertIsNone(gap["gap_low"])
        self.assertIsNone(gap["spans_zero"])
        self.assertFalse(gap["enough"])


class TestBreakdowns(unittest.TestCase):
    def test_overconfidence_is_reported_per_decision_rule(self):
        rules = [{"id": "r1", "name": "Rule one", "question_ids": ["q1"]},
                 {"id": "r2", "name": "Rule two", "question_ids": ["q2"]}]
        index = calibration.rule_index(rules)
        rows = ([row("q1", False, "confident") for _ in range(3)]
                + [row("q2", True, "confident")])
        buckets = {b["key"]: b for b in calibration.by_rule(rows, rules, index)}
        self.assertEqual(buckets["r1"]["dangerous"], 3)
        self.assertEqual(buckets["r1"]["label"], "Rule one")
        self.assertEqual(buckets["r2"]["dangerous"], 0)

    def test_topics_are_broken_out_too(self):
        buckets = calibration.by_topic([row("q1", False, "confident")])
        self.assertEqual(len(buckets), 1)
        self.assertIn("Data Encryption", buckets[0]["key"])
        self.assertEqual(buckets[0]["dangerous"], 1)


class TestNoSingleScore(unittest.TestCase):
    """Rule 2: the curve, the gap and the lists - never one number."""

    def test_the_report_contains_no_score_field(self):
        rows = [row("q%d" % i, i % 2 == 0, "confident") for i in range(20)]
        blob = json.dumps(calibration.report(rows, [q("q1")], []))
        for banned in ('"score"', '"calibration_score"', '"grade"',
                       '"rating"', '"percentile"'):
            self.assertNotIn(banned, blob)


class TestProjection(unittest.TestCase):
    def test_pace_projects_to_a_coverage_date(self):
        today = date(2026, 7, 31)
        questions = [q("q%d" % i) for i in range(10)]
        rows = []
        for d in range(28):
            day = (today - timedelta(days=d)).isoformat()
            rows += [row("q%d" % (i % 10), True, "unsure",
                         ts=day + "T10:00:00+00:00") for i in range(5)]
        p = calibration.projection(rows, questions, target=date(2026, 12, 31),
                                   today=today)
        self.assertTrue(p["enough"])
        self.assertAlmostEqual(p["pace_per_day"], 5.0)
        self.assertIsNotNone(p["projected_date"])
        self.assertTrue(p["on_track"])

    def test_a_thin_pace_refuses_to_project(self):
        today = date(2026, 7, 31)
        rows = [row("q1", True, "unsure", ts="2026-07-30T10:00:00+00:00")]
        p = calibration.projection(rows, [q("q1")], today=today)
        self.assertFalse(p["enough"])
        self.assertIsNone(p["days_needed"])
        self.assertIsNone(p["projected_date"],
                          "five answers must not extrapolate to a date decades out")

    def test_no_retention_forecast_is_offered(self):
        p = calibration.projection([], [q("q1")])
        for banned in ("retention", "forecast", "recall", "half_life", "decay"):
            self.assertNotIn(banned, p)

    def test_a_bad_target_date_is_rejected_not_guessed(self):
        self.assertIsNone(calibration.parse_target("not-a-date"))
        self.assertIsNone(calibration.parse_target(""))
        self.assertEqual(calibration.parse_target("2027-01-31"), date(2027, 1, 31))


class TestCaptureInTheDrillLoop(unittest.TestCase):
    def _run(self, answers, questions):
        """Returns (printed output, prompts the user was shown, logged rows).

        Prompts are collected separately because `input()` writes them to the
        terminal itself - with an injected reader they never reach `out`, so
        asserting on the printed text alone would silently test nothing.
        """
        out = io.StringIO()
        prompts = []
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            supplied = iter(answers)

            def reader(prompt=""):
                prompts.append(prompt)
                try:
                    return next(supplied)
                except StopIteration:
                    raise EOFError()

            session_mod.run(questions, "cisa", "smart", path, out=out, reader=reader)
            return out.getvalue(), prompts, store.load(path)

    def test_answer_and_confidence_can_be_given_in_one_entry(self):
        _, prompts, rows = self._run(["B3"], [q("q1")])
        self.assertEqual(rows[0]["chosen"], "B")
        self.assertEqual(rows[0]["confidence"], "confident")
        self.assertEqual(len(prompts), 1, "one entry should mean one prompt")

    def test_a_bare_answer_is_asked_for_confidence(self):
        _, prompts, rows = self._run(["B", "2"], [q("q1")])
        self.assertTrue(any("How sure?" in p for p in prompts))
        self.assertEqual(rows[0]["confidence"], "unsure")

    def test_an_invalid_confidence_is_rejected_without_losing_the_answer(self):
        text, _, rows = self._run(["B9", "B1"], [q("q1")])
        self.assertIn("Confidence is 1", text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["confidence"], "guess")

    def test_confidence_is_mandatory_and_precedes_the_result(self):
        """Ordering is the whole point: a rating given after the reveal is hindsight.

        Supplying only an answer must not produce a logged row - the session
        asks again, and here runs out of input instead of guessing a level.
        """
        text, prompts, rows = self._run(["B"], [q("q1")])
        self.assertTrue(any("How sure?" in p for p in prompts),
                        "a bare answer must be challenged for confidence")
        self.assertNotIn("CORRECT", text,
                         "the result was revealed before confidence was given")
        self.assertEqual(rows, [], "an unrated answer must not be logged")

    def test_a_rated_answer_is_logged_and_then_revealed(self):
        text, _, rows = self._run(["B1"], [q("q1")])
        self.assertEqual(rows[0]["confidence"], "guess")
        self.assertIn("CORRECT", text)


class TestApiCapture(unittest.TestCase):
    def setUp(self):
        self.profile = "caltest-%s" % os.urandom(4).hex()
        self.api = Api("cisa", self.profile)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        directory = loader.results_dir("cisa", self.profile)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)

    def test_the_api_stores_confidence_with_the_answer(self):
        data = self.api.drill_start({"mode": "random", "n": 1, "seed": 3})
        qid = data["questions"][0]["id"]
        self.api.drill_answer({"question_id": qid, "chosen": "A",
                               "session": data["session"], "mode": "random",
                               "confidence": "confident"})
        rows = self.api.rows()
        self.assertEqual(rows[-1]["confidence"], "confident")

    def test_a_missing_confidence_stores_empty_not_a_guess(self):
        data = self.api.drill_start({"mode": "random", "n": 1, "seed": 4})
        qid = data["questions"][0]["id"]
        self.api.drill_answer({"question_id": qid, "chosen": "A",
                               "session": data["session"], "mode": "random"})
        self.assertEqual(self.api.rows()[-1]["confidence"], "")

    def test_the_target_date_round_trips_and_is_validated(self):
        self.assertEqual(self.api.settings()["target_date"], "")
        self.api.save_settings({"target_date": "2027-06-01"})
        self.assertEqual(self.api.settings()["target_date"], "2027-06-01")
        with self.assertRaises(Exception):
            self.api.save_settings({"target_date": "next June"})
        self.api.save_settings({"target_date": ""})
        self.assertEqual(self.api.settings()["target_date"], "")

    def test_settings_are_per_profile(self):
        self.api.save_settings({"target_date": "2027-06-01"})
        other = Api("cisa", "caltest-other-%s" % os.urandom(3).hex())
        try:
            self.assertEqual(other.settings()["target_date"], "")
        finally:
            directory = loader.results_dir("cisa", other.profile)
            if os.path.isdir(directory):
                for root, _, files in os.walk(directory, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    os.rmdir(root)

    def test_calibration_runs_against_the_real_bank(self):
        report = self.api.calibration()
        self.assertIn("curve", report)
        self.assertIn("projection", report)
        self.assertEqual(len(report["curve"]), 3)


class TestConcurrentWritesDoNotCorruptState(unittest.TestCase):
    """Regression: answering and rating fire two requests almost at once.

    The server is threaded. Both handlers used to write to the same
    "<file>.tmp" and their bytes interleaved, publishing a corrupt exam file
    and losing the sitting. Found by driving the real browser, not by reasoning
    about the code.
    """

    def setUp(self):
        self.profile = "concur-%s" % os.urandom(4).hex()
        self.api = Api("cisa", self.profile)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        directory = loader.results_dir("cisa", self.profile)
        if os.path.isdir(directory):
            for root, _, files in os.walk(directory, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                os.rmdir(root)

    def test_parallel_updates_leave_a_readable_exam(self):
        import threading
        from drillkit import exam as exam_mod

        state = self.api.exam_new({"n": 12, "minutes": 30})
        exam_id = state["id"]
        qids = [q["id"] for q in state["questions"]]
        errors = []

        def answer(qid, letter, level):
            try:
                self.api.exam_update({"id": exam_id, "action": "answer",
                                      "question_id": qid, "chosen": letter,
                                      "confidence": level, "seconds": 1.0})
            except Exception as exc:  # noqa: BLE001 - recorded and asserted below
                errors.append(exc)

        threads = []
        for i, qid in enumerate(qids):
            level = ("guess", "unsure", "confident")[i % 3]
            threads.append(threading.Thread(target=answer, args=(qid, "A", level)))
            threads.append(threading.Thread(target=answer, args=(qid, "B", level)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], "concurrent updates raised")
        reloaded = exam_mod.load(self.api.results_path, exam_id)
        self.assertEqual(len(reloaded.answers), len(qids),
                         "an answer was lost to a concurrent write")
        self.assertEqual(len(reloaded.confidence), len(qids),
                         "a confidence rating was lost to a concurrent write")

    def test_concurrent_saves_never_publish_a_half_written_file(self):
        """Targets save() itself, below the lock in exam_update.

        The invariant: whatever ends up on disk is one complete document from
        one writer. With a shared "<file>.tmp" two writers of different sizes
        interleave and the shorter one leaves the longer one's tail behind,
        which is exactly how a real exam file was destroyed.

        Writers only - reading while another thread replaces the file is a
        separate concern, handled by the retry in _replace_with_retry and by
        the per-exam lock on the API path.
        """
        import threading
        from drillkit import exam as exam_mod

        state = self.api.exam_new({"n": 40, "minutes": 60})
        loaded = exam_mod.load(self.api.results_path, state["id"])
        errors = []
        barrier = threading.Barrier(6)

        def writer(n):
            copy = exam_mod.load(self.api.results_path, state["id"])
            # Different sizes on purpose: unequal interleaved writes are what
            # leave trailing bytes behind.
            copy.answers = {qid: "ABCD"[n % 4]
                            for qid in loaded.question_ids[:n * 7 + 1]}
            try:
                barrier.wait(timeout=5)
                for _ in range(15):
                    exam_mod.save(copy, self.api.results_path)
            except Exception as exc:  # noqa: BLE001 - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual([type(e).__name__ for e in errors], [],
                         "a concurrent save raised")
        # The real assertion: the published file parses and is one writer's work.
        final = exam_mod.load(self.api.results_path, state["id"])
        self.assertIn(len(final.answers),
                      {n * 7 + 1 for n in range(6)},
                      "the file on disk is a blend of two writers")

    def test_no_temp_files_are_left_behind(self):
        from drillkit import exam as exam_mod
        state = self.api.exam_new({"n": 3, "minutes": 10})
        self.api.exam_update({"id": state["id"], "action": "answer",
                              "question_id": state["questions"][0]["id"],
                              "chosen": "A", "confidence": "unsure"})
        leftovers = [n for n in os.listdir(exam_mod.exams_dir(self.api.results_path))
                     if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class TestSchedulerIsUntouched(unittest.TestCase):
    """Rule 4: capture first, prove the signal, then touch a working scheduler."""

    def test_the_scheduler_does_not_read_confidence(self):
        with open(scheduler.__file__, "r", encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("confidence", source,
                         "the scheduler must not use confidence in this phase")

    def test_selection_is_identical_with_and_without_confidence(self):
        questions = [q("q%d" % i) for i in range(12)]
        plain = [row("q%d" % i, i % 2 == 0) for i in range(12)]
        rated = [row("q%d" % i, i % 2 == 0, "confident") for i in range(12)]

        import random
        a = scheduler.select(questions, store.history_by_question(plain), 6,
                             mode="smart", rng=random.Random(1))
        b = scheduler.select(questions, store.history_by_question(rated), 6,
                             mode="smart", rng=random.Random(1))
        self.assertEqual([x.id for x in a], [x.id for x in b],
                         "adding confidence changed scheduling")


if __name__ == "__main__":
    unittest.main(verbosity=2)
