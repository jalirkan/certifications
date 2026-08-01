"""Self-contained checks for the drill engine.

    python tests/test_engine.py

Uses only unittest from the standard library, so it runs offline anywhere.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import loader, scheduler, session as session_mod, stats, store  # noqa: E402
from drillkit.loader import Question  # noqa: E402

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


def q(qid: str, topic: str = "Data Encryption", answer: str = "B") -> Question:
    others = [k for k in "ABCD" if k != answer]
    return Question(
        id=qid, domain="5", section="A", topic=topic,
        stem="Which control is BEST?",
        options={"A": "one", "B": "two", "C": "three", "D": "four"},
        answer=answer,
        why_correct="because",
        why_wrong={k: "not this one" for k in others},
    )


def attempt(qid, correct, days_ago=0, now=NOW):
    return {
        "ts": (now - timedelta(days=days_ago)).isoformat(),
        "question_id": qid, "domain": "5", "section": "A",
        "topic": "Data Encryption", "correct": correct,
        "chosen": "B", "answer": "B", "seconds": 5.0, "mode": "smart",
    }


class TestScheduler(unittest.TestCase):
    def test_missed_questions_are_served_before_unseen(self):
        questions = [q("seen-right"), q("unseen"), q("missed")]
        history = store.history_by_question([
            attempt("seen-right", True, days_ago=0),
            attempt("missed", False, days_ago=0),
        ])
        order = [x.id for x in scheduler.select(questions, history, 3, now=NOW)]
        self.assertEqual(order[0], "missed")
        self.assertEqual(order[1], "unseen")
        self.assertEqual(order[2], "seen-right")

    def test_chronic_misses_outrank_occasional_ones(self):
        questions = [q("chronic"), q("occasional")]
        history = store.history_by_question([
            attempt("chronic", False, 5), attempt("chronic", False, 3),
            attempt("chronic", True, 2), attempt("chronic", False, 1),
            attempt("occasional", True, 5), attempt("occasional", True, 3),
            attempt("occasional", True, 2), attempt("occasional", False, 1),
        ])
        order = [x.id for x in scheduler.select(questions, history, 2, now=NOW)]
        self.assertEqual(order[0], "chronic")

    def test_streak_pushes_a_question_further_out(self):
        history = store.history_by_question([
            attempt("q1", True, 3), attempt("q1", True, 2), attempt("q1", True, 1),
        ])
        prog = scheduler.build_progress(history)["q1"]
        self.assertEqual(prog.streak, 3)
        self.assertEqual(prog.interval_days, scheduler.INTERVALS_DAYS[3])

    def test_a_wrong_answer_resets_the_streak(self):
        history = store.history_by_question([
            attempt("q1", True, 4), attempt("q1", True, 3), attempt("q1", False, 1),
        ])
        prog = scheduler.build_progress(history)["q1"]
        self.assertEqual(prog.streak, 0)
        self.assertIs(prog.last_correct, False)

    def test_due_mode_holds_back_questions_inside_their_interval(self):
        questions = [q("fresh"), q("overdue")]
        history = store.history_by_question([
            attempt("fresh", True, 0),      # box 1, interval 1 day, not due
            attempt("overdue", True, 30),   # box 1, 30 days elapsed, very overdue
        ])
        order = [x.id for x in scheduler.select(questions, history, 2, mode="due", now=NOW)]
        self.assertEqual(order[0], "overdue")

    def test_weakest_mode_sorts_by_lifetime_accuracy(self):
        questions = [q("strong"), q("weak"), q("new")]
        history = store.history_by_question([
            attempt("strong", True, 2), attempt("strong", True, 1),
            attempt("weak", False, 2), attempt("weak", True, 1),
        ])
        order = [x.id for x in scheduler.select(questions, history, 3, mode="weakest", now=NOW)]
        self.assertEqual(order[0], "weak")
        self.assertEqual(order[-1], "new")

    def test_seeded_runs_are_reproducible(self):
        import random
        questions = [q("a"), q("b"), q("c"), q("d")]
        first = [x.id for x in scheduler.select(questions, {}, 4, rng=random.Random(42), now=NOW)]
        second = [x.id for x in scheduler.select(questions, {}, 4, rng=random.Random(42), now=NOW)]
        self.assertEqual(first, second)


class TestKeyBalance(unittest.TestCase):
    """Two consecutive hand-written batches came out 1/5/5/1 and 1/8/5/2 before
    anyone counted. An author's favourite letter is invisible from inside the
    batch, so the check has to be mechanical."""

    @staticmethod
    def batch(keys, source="batch.json"):
        items = []
        for i, key in enumerate(keys):
            item = q("q%d" % i)
            item.answer = key
            item.why_wrong = {k: "because" for k in "ABCD" if k != key}
            item.source_file = source
            items.append(item)
        return items

    def test_a_skewed_batch_is_flagged(self):
        _, warnings = loader.validate(self.batch("BBBBBBBBACCCDA"))
        self.assertTrue(any("keys are skewed" in w and "B is correct for 8" in w
                            for w in warnings), warnings)

    def test_an_even_batch_is_not_flagged(self):
        _, warnings = loader.validate(self.batch("ABCDABCDABCD"))
        self.assertFalse(any("keys are skewed" in w for w in warnings), warnings)

    def test_a_batch_below_the_minimum_size_says_nothing(self):
        """Four questions from one file will always look skewed. Reporting that
        would train the reader to ignore the warning."""
        _, warnings = loader.validate(self.batch("AAAA"))
        self.assertFalse(any("keys are skewed" in w for w in warnings), warnings)

    def test_skew_is_measured_per_file_not_across_the_bank(self):
        """Two files skewed in opposite directions average out to a healthy
        bank, and a learner drilling one topic still sees a pattern."""
        rows = self.batch("AAAAAAAABCD", "one.json") + self.batch("BBBBBBBBACD", "two.json")
        _, warnings = loader.validate(rows)
        flagged = [w for w in warnings if "keys are skewed" in w]
        self.assertEqual(len(flagged), 2, warnings)

    def test_the_shipped_bank_is_balanced_in_every_file(self):
        questions = loader.load_questions("cisa")
        _, warnings = loader.validate(questions)
        self.assertEqual([w for w in warnings if "keys are skewed" in w], [])


class TestValidation(unittest.TestCase):
    def test_a_clean_question_passes(self):
        errors, _ = loader.validate([q("ok")])
        self.assertEqual(errors, [])

    def test_answer_key_outside_ad_is_an_error(self):
        bad = q("bad")
        bad.answer = "E"
        errors, _ = loader.validate([bad])
        self.assertTrue(any("not one of A-D" in e for e in errors))

    def test_missing_distractor_explanation_is_an_error(self):
        bad = q("bad")
        bad.why_wrong.pop("A")
        errors, _ = loader.validate([bad])
        self.assertTrue(any("why A is wrong" in e for e in errors))

    def test_duplicate_ids_are_an_error(self):
        errors, _ = loader.validate([q("dupe"), q("dupe")])
        self.assertTrue(any("duplicate id" in e for e in errors))

    def test_identical_option_text_is_an_error(self):
        bad = q("bad")
        bad.options["C"] = bad.options["B"]
        errors, _ = loader.validate([bad])
        self.assertTrue(any("same text" in e for e in errors))

    def test_topic_outside_the_outline_is_an_error(self):
        outline = loader.Outline(cert="CISA", raw={
            "domains": {"5": {"sections": {"A": {"topics": ["Data Encryption"]}}}}
        })
        bad = q("bad", topic="Cryptography Stuff")
        errors, _ = loader.validate([bad], outline)
        self.assertTrue(any("not in the D5A outline" in e for e in errors))

    def test_the_real_cisa_bank_is_valid(self):
        outline = loader.load_outline("cisa")
        questions = loader.load_questions("cisa")
        errors, _ = loader.validate(questions, outline)
        self.assertEqual(errors, [], "shipped question bank should have no errors")
        self.assertGreaterEqual(len(questions), 50)

    def test_every_d5_outline_topic_has_questions(self):
        outline = loader.load_outline("cisa")
        questions = loader.load_questions("cisa")
        gaps = [t for _, t, n in loader.coverage(questions, outline, "5") if n == 0]
        self.assertEqual(gaps, [], "these D5 topics have no questions: %s" % gaps)


class TestStore(unittest.TestCase):
    def test_attempts_round_trip_through_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "results", "attempts.jsonl")
            store.append(path, store.Attempt(
                ts=store.now_iso(), session="abc123", question_id="cisa-d5a-001",
                cert="CISA", domain="5", section="A", topic="Data Encryption",
                chosen="B", answer="B", correct=True, seconds=12.5, mode="smart",
            ))
            rows = store.load(path)
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["correct"])
            self.assertEqual(rows[0]["question_id"], "cisa-d5a-001")

    def test_a_truncated_line_does_not_break_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"question_id": "a", "correct": True}) + "\n")
                fh.write('{"question_id": "b", "corr\n')  # interrupted mid-write
                fh.write(json.dumps({"question_id": "c", "correct": False}) + "\n")
            rows = store.load(path)
            self.assertEqual([r["question_id"] for r in rows], ["a", "c"])


class TestStats(unittest.TestCase):
    def test_topics_are_reported_weakest_first(self):
        rows = [
            {"question_id": "1", "domain": "5", "section": "A", "topic": "Strong", "correct": True},
            {"question_id": "2", "domain": "5", "section": "A", "topic": "Strong", "correct": True},
            {"question_id": "3", "domain": "5", "section": "A", "topic": "Weak", "correct": False},
            {"question_id": "4", "domain": "5", "section": "A", "topic": "Weak", "correct": False},
        ]
        buckets = stats.by_topic(rows)
        self.assertIn("Weak", buckets[0].label)
        self.assertEqual(buckets[0].accuracy, 0.0)

    def test_overall_accuracy(self):
        rows = [{"question_id": str(i), "correct": i % 2 == 0} for i in range(10)]
        attempts, correct, acc = stats.overall(rows)
        self.assertEqual((attempts, correct), (10, 5))
        self.assertAlmostEqual(acc, 0.5)

    def test_most_missed_questions_rank_highest(self):
        questions = [q("q1"), q("q2")]
        rows = [
            attempt("q1", False), attempt("q1", False), attempt("q1", True),
            attempt("q2", False), attempt("q2", True),
        ]
        ranked = stats.unmastered(rows, questions)
        self.assertEqual(ranked[0][0], "q1")
        self.assertEqual(ranked[0][2], 2)


class TestSession(unittest.TestCase):
    def _run(self, answers, questions):
        import io
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            supplied = iter(answers)

            def reader(_prompt=""):
                try:
                    return next(supplied)
                except StopIteration:
                    raise EOFError()

            sess = session_mod.run(questions, "cisa", "smart", path,
                                   out=out, reader=reader)
            return sess, out.getvalue(), store.load(path)

    def test_a_full_session_scores_and_logs_every_answer(self):
        questions = [q("q1", answer="B"), q("q2", answer="C")]
        sess, text, rows = self._run(["B2", "A1"], questions)
        self.assertEqual((sess.asked, sess.right), (2, 1))
        self.assertEqual(len(rows), 2)
        self.assertIn("CORRECT", text)
        self.assertIn("INCORRECT", text)
        self.assertEqual([r["correct"] for r in rows], [True, False])

    def test_invalid_input_is_rejected_without_being_logged(self):
        sess, text, rows = self._run(["X", "", "B3"], [q("q1", answer="B")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(sess.right, 1)
        self.assertIn("Enter A, B, C, D", text)

    def test_quitting_early_preserves_answers_already_given(self):
        questions = [q("q1", answer="B"), q("q2", answer="B"), q("q3", answer="B")]
        sess, text, rows = self._run(["B2", "q"], questions)
        self.assertEqual(sess.asked, 1)
        self.assertEqual(len(rows), 1)
        self.assertIn("Stopped early", text)

    def test_lowercase_answers_are_accepted(self):
        sess, _, rows = self._run(["b2"], [q("q1", answer="B")])
        self.assertEqual(sess.right, 1)

    def test_feedback_explains_the_correct_answer_and_every_distractor(self):
        _, text, _ = self._run(["A3"], [q("q1", answer="B")])
        self.assertIn("Why B is right", text)
        for letter in "ACD":
            self.assertIn("Why %s is wrong" % letter, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
