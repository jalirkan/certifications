"""Tests for the mock exam engine: sampling, timing, state and scoring.

    python tests/test_exam.py
"""

from __future__ import annotations

import io
import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import exam as exam_mod, examsession, loader, store  # noqa: E402
from drillkit.exam import ExamError, ExamState  # noqa: E402
from drillkit.loader import Outline, Question  # noqa: E402

CISA_WEIGHTS = {"1": 18, "2": 18, "3": 12, "4": 26, "5": 26}


def q(qid: str, domain: str = "5", topic: str = "Data Encryption",
      answer: str = "B") -> Question:
    others = [k for k in "ABCD" if k != answer]
    return Question(
        id=qid, domain=domain, section="A", topic=topic,
        stem="Which control is BEST?",
        options={"A": "one", "B": "two", "C": "three", "D": "four"},
        answer=answer, why_correct="because",
        why_wrong={k: "not this one" for k in others},
    )


def outline_for(weights=None) -> Outline:
    weights = weights or CISA_WEIGHTS
    return Outline(cert="CISA", raw={
        "domains": {
            d: {"name": "Domain %s" % d, "weight": w,
                "sections": {"A": {"name": "A", "topics": ["Data Encryption"]}}}
            for d, w in weights.items()
        }
    })


class FakeClock:
    """Controllable time source so tests never sleep."""

    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class TestBlueprintCounts(unittest.TestCase):
    def test_counts_sum_exactly_to_the_requested_total(self):
        counts = exam_mod.blueprint_counts(CISA_WEIGHTS, 150)
        self.assertEqual(sum(counts.values()), 150)

    def test_real_cisa_weights_produce_the_expected_split(self):
        counts = exam_mod.blueprint_counts(CISA_WEIGHTS, 150)
        self.assertEqual(counts, {"1": 27, "2": 27, "3": 18, "4": 39, "5": 39})

    def test_largest_remainder_still_sums_when_rounding_is_awkward(self):
        for total in (7, 13, 29, 41, 99, 151):
            counts = exam_mod.blueprint_counts(CISA_WEIGHTS, total)
            self.assertEqual(sum(counts.values()), total, "failed at total=%d" % total)

    def test_zero_total_weight_is_rejected(self):
        with self.assertRaises(ExamError):
            exam_mod.blueprint_counts({"1": 0, "2": 0}, 10)


class TestSampling(unittest.TestCase):
    def _bank(self, per_domain=60):
        questions = []
        for d in "12345":
            for i in range(per_domain):
                questions.append(q("d%s-%03d" % (d, i), domain=d))
        return questions

    def test_full_bank_produces_a_blueprint_weighted_exam(self):
        picked, targets, shortfall = exam_mod.sample_by_blueprint(
            self._bank(), outline_for(), 150, random.Random(1))
        self.assertEqual(len(picked), 150)
        self.assertEqual(shortfall, {})
        counts = {}
        for item in picked:
            counts[item.domain] = counts.get(item.domain, 0) + 1
        self.assertEqual(counts, targets)

    def test_a_thin_domain_reports_shortfall_and_reallocates(self):
        bank = [q("d5-%03d" % i, domain="5") for i in range(60)]
        bank += [q("d4-%03d" % i, domain="4") for i in range(60)]
        picked, targets, shortfall = exam_mod.sample_by_blueprint(
            bank, outline_for(), 150, random.Random(2))
        # Domains 1-3 have nothing to give, so they show shortfall...
        self.assertTrue(shortfall.get("1", 0) > 0)
        # ...and the exam is capped at what the bank can actually supply.
        self.assertEqual(len(picked), 120)

    def test_no_questions_at_all_is_an_error(self):
        with self.assertRaises(ExamError):
            exam_mod.sample_by_blueprint([], outline_for(), 150)

    def test_sampling_spreads_across_topics_rather_than_one_dominating(self):
        pool = ([q("big-%02d" % i, topic="Big Topic") for i in range(40)]
                + [q("small-%02d" % i, topic="Small Topic") for i in range(5)])
        picked = exam_mod._sample_across_topics(pool, 10, random.Random(3))
        topics = {item.topic for item in picked}
        self.assertEqual(len(picked), 10)
        self.assertIn("Small Topic", topics, "small topic should still be represented")

    def test_requesting_more_than_available_returns_everything(self):
        pool = [q("a"), q("b"), q("c")]
        picked = exam_mod._sample_across_topics(pool, 99, random.Random(4))
        self.assertEqual(len(picked), 3)

    def test_seeded_sampling_is_reproducible(self):
        bank = self._bank(20)
        first, _, _ = exam_mod.sample_by_blueprint(bank, outline_for(), 40, random.Random(9))
        second, _, _ = exam_mod.sample_by_blueprint(bank, outline_for(), 40, random.Random(9))
        self.assertEqual([x.id for x in first], [x.id for x in second])


class TestScoring(unittest.TestCase):
    def test_scale_anchors_match_the_published_values(self):
        self.assertEqual(exam_mod.estimated_scaled_score(0.0), 200)
        self.assertEqual(exam_mod.estimated_scaled_score(exam_mod.ASSUMED_PASS_RAW), 450)
        self.assertEqual(exam_mod.estimated_scaled_score(1.0), 800)

    def test_scale_is_monotonic_and_interpolates_sensibly(self):
        self.assertEqual(exam_mod.estimated_scaled_score(0.35), 325)
        self.assertEqual(exam_mod.estimated_scaled_score(0.85), 625)
        previous = -1
        for i in range(0, 101):
            value = exam_mod.estimated_scaled_score(i / 100.0)
            self.assertGreaterEqual(value, previous)
            previous = value

    def test_out_of_range_input_is_clamped(self):
        self.assertEqual(exam_mod.estimated_scaled_score(-5), 200)
        self.assertEqual(exam_mod.estimated_scaled_score(99), 800)

    def test_unanswered_questions_score_as_incorrect(self):
        questions = [q("a", answer="B"), q("b", answer="C"), q("c", answer="D")]
        state = ExamState(
            exam_id="t1", cert="CISA", created="2026-07-26T00:00:00+00:00",
            duration_seconds=600, question_ids=["a", "b", "c"],
            answers={"a": "B"},  # b and c left blank
        )
        result = exam_mod.score(state, questions, outline_for())
        self.assertEqual(result.correct, 1)
        self.assertEqual(result.unanswered, 2)
        self.assertEqual(len(result.missed), 2)
        self.assertAlmostEqual(result.raw_fraction, 1 / 3)

    def test_per_domain_results_carry_weights_from_the_outline(self):
        questions = [q("a", domain="4", answer="B"), q("b", domain="5", answer="B")]
        state = ExamState(
            exam_id="t2", cert="CISA", created="2026-07-26T00:00:00+00:00",
            duration_seconds=600, question_ids=["a", "b"],
            answers={"a": "B", "b": "A"},
        )
        result = exam_mod.score(state, questions, outline_for())
        by_domain = {d.domain: d for d in result.by_domain}
        self.assertEqual(by_domain["4"].correct, 1)
        self.assertEqual(by_domain["5"].correct, 0)
        self.assertEqual(by_domain["4"].weight, 26)

    def test_flagged_but_correct_answers_are_surfaced(self):
        questions = [q("a", answer="B")]
        state = ExamState(
            exam_id="t3", cert="CISA", created="2026-07-26T00:00:00+00:00",
            duration_seconds=600, question_ids=["a"],
            answers={"a": "B"}, flagged=["a"],
        )
        result = exam_mod.score(state, questions, outline_for())
        self.assertEqual([x.id for x in result.guessed_right], ["a"])


class TestStatePersistence(unittest.TestCase):
    def test_state_survives_a_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "results", "attempts.jsonl")
            state = ExamState(
                exam_id="abc12345", cert="CISA", created="2026-07-26T10:00:00+00:00",
                duration_seconds=14400, question_ids=["a", "b", "c"],
                answers={"a": "B"}, flagged=["c"], position=1,
                elapsed_seconds=125.5, sittings=2,
                seconds_per_question={"a": 30.0},
            )
            exam_mod.save(state, results)
            loaded = exam_mod.load(results, "abc12345")
            self.assertEqual(loaded.answers, {"a": "B"})
            self.assertEqual(loaded.flagged, ["c"])
            self.assertEqual(loaded.position, 1)
            self.assertEqual(loaded.elapsed_seconds, 125.5)
            self.assertEqual(loaded.seconds_per_question, {"a": 30.0})

    def test_loading_an_unknown_exam_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ExamError):
                exam_mod.load(os.path.join(tmp, "results", "attempts.jsonl"), "nope")

    def test_listing_returns_newest_first_and_skips_corrupt_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "results", "attempts.jsonl")
            for i, created in enumerate(["2026-07-01T00:00:00+00:00",
                                         "2026-07-20T00:00:00+00:00"]):
                exam_mod.save(ExamState(
                    exam_id="id%d" % i, cert="CISA", created=created,
                    duration_seconds=600, question_ids=["a"],
                ), results)
            with open(os.path.join(exam_mod.exams_dir(results), "broken.json"),
                      "w", encoding="utf-8") as fh:
                fh.write("{not json")
            exams = exam_mod.list_exams(results)
            self.assertEqual([e.exam_id for e in exams], ["id1", "id0"])

    def test_derived_properties_behave(self):
        state = ExamState(
            exam_id="x", cert="CISA", created="2026-07-26T00:00:00+00:00",
            duration_seconds=100, question_ids=["a", "b"], answers={"a": "B"},
            elapsed_seconds=40,
        )
        self.assertEqual(state.total, 2)
        self.assertEqual(state.answered, 1)
        self.assertEqual(state.remaining_seconds, 60)
        self.assertFalse(state.expired)
        state.elapsed_seconds = 100
        self.assertTrue(state.expired)
        self.assertEqual(state.remaining_seconds, 0)


class TestClock(unittest.TestCase):
    def test_clock_accumulates_only_while_running(self):
        fake = FakeClock()
        clock = exam_mod.Clock(now=fake)
        self.assertEqual(clock.sitting_seconds(), 0.0)
        clock.start()
        fake.advance(30)
        self.assertEqual(clock.sitting_seconds(), 30.0)
        self.assertEqual(clock.stop(), 30.0)
        fake.advance(500)  # time passes while stopped
        self.assertEqual(clock.sitting_seconds(), 0.0)

    def test_hms_and_ms_formatting(self):
        self.assertEqual(exam_mod.format_hms(3661), "1:01:01")
        self.assertEqual(exam_mod.format_hms(-5), "0:00:00")
        self.assertEqual(exam_mod.format_ms(95), "1:35")


class TestExamRunner(unittest.TestCase):
    def _runner(self, questions, commands, tmp, state=None, clock=None,
                duration=600):
        state = state or ExamState(
            exam_id="run01", cert="CISA", created="2026-07-26T00:00:00+00:00",
            duration_seconds=duration,
            question_ids=[item.id for item in questions],
        )
        results = os.path.join(tmp, "results", "attempts.jsonl")
        supplied = iter(commands)
        out = io.StringIO()

        def reader(_prompt=""):
            try:
                return next(supplied)
            except StopIteration:
                raise EOFError()

        runner = examsession.ExamRunner(
            state, questions, outline_for(), results,
            out=out, reader=reader, now=clock or FakeClock(),
        )
        return runner, out, results

    def test_answering_records_responses_and_advances(self):
        questions = [q("a", answer="B"), q("b", answer="C"), q("c", answer="D")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, out, results = self._runner(
                questions, ["B", "C", "D", "e", "y"], tmp)
            result = runner.run()
            self.assertIsNotNone(result)
            self.assertEqual(result.correct, 3)
            self.assertEqual(result.unanswered, 0)

    def test_navigation_and_flagging(self):
        questions = [q("a"), q("b"), q("c")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, out, _ = self._runner(
                questions, ["n", "f", "g 1", "p", "x"], tmp)
            runner.run()
            self.assertIn("b", runner.state.flagged)
            self.assertEqual(runner.state.position, 0)

    def test_goto_rejects_out_of_range_and_non_numeric_input(self):
        questions = [q("a"), q("b")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, out, _ = self._runner(questions, ["g 99", "g xyz", "x"], tmp)
            runner.run()
            text = out.getvalue()
            self.assertIn("between 1 and 2", text)
            self.assertIn("followed by a question number", text)

    def test_unrecognized_command_is_reported_not_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, out, _ = self._runner([q("a")], ["zz", "x"], tmp)
            runner.run()
            self.assertIn("Unrecognized command", out.getvalue())

    def test_save_and_exit_returns_none_and_persists_progress(self):
        questions = [q("a", answer="B"), q("b", answer="B")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, out, results = self._runner(questions, ["B", "x"], tmp)
            result = runner.run()
            self.assertIsNone(result)
            reloaded = exam_mod.load(results, "run01")
            self.assertEqual(reloaded.answers, {"a": "B"})
            self.assertFalse(reloaded.submitted)
            self.assertIn("Resume with", out.getvalue())

    def test_resuming_preserves_answers_and_continues(self):
        questions = [q("a", answer="B"), q("b", answer="C")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, _, results = self._runner(questions, ["B", "x"], tmp)
            runner.run()
            resumed_state = exam_mod.load(results, "run01")
            runner2, _, _ = self._runner(
                questions, ["C", "e", "y"], tmp, state=resumed_state)
            result = runner2.run()
            self.assertEqual(result.correct, 2)
            self.assertEqual(runner2.state.sittings, 2)

    def test_declining_the_submit_prompt_keeps_the_exam_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, out, _ = self._runner([q("a")], ["e", "n", "x"], tmp)
            result = runner.run()
            self.assertIsNone(result)
            self.assertIn("Not submitted", out.getvalue())

    def test_expiry_submits_automatically(self):
        clock = FakeClock()
        questions = [q("a", answer="B"), q("b", answer="B")]

        def commands():
            yield "B"
            clock.advance(5000)  # blow through the time limit
            yield "B"

        with tempfile.TemporaryDirectory() as tmp:
            runner, out, _ = self._runner(
                questions, commands(), tmp, clock=clock, duration=100)
            result = runner.run()
            self.assertIsNotNone(result)
            self.assertIn("TIME EXPIRED", out.getvalue())
            self.assertTrue(runner.state.submitted)

    def test_submitted_answers_are_written_to_the_attempt_log(self):
        questions = [q("a", answer="B"), q("b", answer="C")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, _, results = self._runner(questions, ["B", "A", "e", "y"], tmp)
            runner.run()
            rows = store.load(results)
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(r["mode"] == "exam" for r in rows))
            self.assertEqual({r["question_id"]: r["correct"] for r in rows},
                             {"a": True, "b": False})

    def test_elapsed_time_is_not_double_counted_across_saves(self):
        """Regression: _persist writes the running total back to the state, so
        elapsed() must work from a fixed base rather than from that total."""
        clock = FakeClock()
        questions = [q("q%d" % i, answer="B") for i in range(6)]

        def commands():
            for _ in range(5):
                clock.advance(10)  # exactly 10 seconds per answer
                yield "B"
            yield "x"

        with tempfile.TemporaryDirectory() as tmp:
            runner, _, results = self._runner(
                questions, commands(), tmp, clock=clock, duration=3600)
            runner.run()
            saved = exam_mod.load(results, "run01")
            self.assertAlmostEqual(saved.elapsed_seconds, 50.0, delta=1.0)

    def test_elapsed_time_accumulates_correctly_across_sittings(self):
        clock = FakeClock()
        questions = [q("a", answer="B"), q("b", answer="B")]

        def first():
            clock.advance(30)
            yield "B"
            yield "x"

        with tempfile.TemporaryDirectory() as tmp:
            runner, _, results = self._runner(
                questions, first(), tmp, clock=clock, duration=3600)
            runner.run()
            state = exam_mod.load(results, "run01")
            self.assertAlmostEqual(state.elapsed_seconds, 30.0, delta=1.0)

            clock.advance(10_000)  # a week passes between sittings

            def second():
                clock.advance(20)
                yield "B"
                yield "x"

            runner2, _, _ = self._runner(
                questions, second(), tmp, state=state, clock=clock, duration=3600)
            runner2.run()
            final = exam_mod.load(results, "run01")
            self.assertAlmostEqual(final.elapsed_seconds, 50.0, delta=1.0)

    def test_time_is_attributed_to_the_question_being_viewed(self):
        clock = FakeClock()
        questions = [q("a", answer="B"), q("b", answer="B")]

        def commands():
            clock.advance(42)
            yield "B"
            yield "x"

        with tempfile.TemporaryDirectory() as tmp:
            runner, _, _ = self._runner(
                questions, commands(), tmp, clock=clock, duration=6000)
            runner.run()
            self.assertGreaterEqual(runner.state.seconds_per_question.get("a", 0), 42)

    def test_report_and_review_render_without_error(self):
        questions = [q("a", answer="B"), q("b", answer="C")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, _, _ = self._runner(questions, ["A", "A", "e", "y"], tmp)
            result = runner.run()
            report = io.StringIO()
            examsession.render_report(result, outline_for(), out=report)
            text = report.getvalue()
            self.assertIn("EXAM RESULT", text)
            self.assertIn("Estimated scaled score", text)
            self.assertIn("approximation", text)  # the caveat must be present

            review = io.StringIO()
            examsession.render_review(result, runner.state, out=review,
                                      paginate=False)
            self.assertIn("Why B is right", review.getvalue())

    def test_report_lines_stay_within_terminal_width(self):
        questions = [q("a", domain="4", answer="B"), q("b", domain="5", answer="C")]
        with tempfile.TemporaryDirectory() as tmp:
            runner, _, _ = self._runner(questions, ["A", "A", "e", "y"], tmp)
            result = runner.run()
            report = io.StringIO()
            examsession.render_report(result, outline_for(), out=report)
            for line in report.getvalue().splitlines():
                self.assertLessEqual(len(line), 82, "too wide: %r" % line)


class TestAgainstRealBank(unittest.TestCase):
    def test_a_full_150_question_exam_can_be_built_from_the_shipped_bank(self):
        outline = loader.load_outline("cisa")
        questions = loader.load_questions("cisa")
        picked, targets, shortfall = exam_mod.sample_by_blueprint(
            questions, outline, 150, random.Random(11))
        self.assertEqual(targets, {"1": 27, "2": 27, "3": 18, "4": 39, "5": 39})
        self.assertEqual(len(picked), 150)
        self.assertEqual(len({x.id for x in picked}), 150, "no duplicates in one exam")
        self.assertEqual(shortfall, {}, "bank should be deep enough for a full mock")


if __name__ == "__main__":
    unittest.main(verbosity=2)
