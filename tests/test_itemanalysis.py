"""Tests for item analysis: difficulty, discrimination and distractor quality.

    python tests/test_itemanalysis.py

The statistical helpers are checked against hand-computed values rather than
against themselves, so an error in the implementation cannot pass by agreeing
with its own output.
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import itemanalysis, loader, store  # noqa: E402
from drillkit.loader import Question  # noqa: E402

NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


def q(qid: str, answer: str = "B", topic: str = "Data Encryption",
      domain: str = "5") -> Question:
    others = [k for k in "ABCD" if k != answer]
    return Question(
        id=qid, domain=domain, section="A", topic=topic,
        stem="Which control is BEST?",
        options={"A": "one", "B": "two", "C": "three", "D": "four"},
        answer=answer, why_correct="because",
        why_wrong={k: "no" for k in others},
    )


def row(qid, correct, chosen="B", session="s1", days_ago=0, seconds=30.0,
        topic="Data Encryption", domain="5"):
    return {
        "ts": (NOW - timedelta(days=days_ago)).isoformat(),
        "session": session, "question_id": qid, "cert": "CISA",
        "domain": domain, "section": "A", "topic": topic,
        "chosen": chosen, "answer": "B", "correct": correct,
        "seconds": seconds, "mode": "drill",
    }


class TestStatisticalHelpers(unittest.TestCase):
    def test_pearson_matches_a_hand_computed_value(self):
        # xs mean 0.5, ys mean 0.5; sxy = 0.4, sxx = 1.0, syy = 0.2
        # r = 0.4 / sqrt(0.2) = 0.894427...
        xs = [1, 0, 1, 0]
        ys = [0.8, 0.2, 0.6, 0.4]
        self.assertAlmostEqual(itemanalysis.pearson(xs, ys), 0.4 / math.sqrt(0.2), places=6)

    def test_pearson_detects_perfect_negative_correlation(self):
        self.assertAlmostEqual(itemanalysis.pearson([1, 0, 1, 0], [0, 1, 0, 1]), -1.0)

    def test_pearson_is_undefined_without_variance(self):
        self.assertIsNone(itemanalysis.pearson([1, 1, 1], [0.5, 0.7, 0.9]))
        self.assertIsNone(itemanalysis.pearson([1, 0], [0.5, 0.5]))
        self.assertIsNone(itemanalysis.pearson([1], [0.5]))

    def test_wilson_interval_is_wide_when_the_sample_is_tiny(self):
        low, high = itemanalysis.wilson_interval(2, 2)
        self.assertAlmostEqual(low, 0.342, places=2)
        self.assertAlmostEqual(high, 1.0, places=6)
        self.assertLess(low, 0.5, "2/2 should not read as near-certain")

    def test_wilson_interval_tightens_as_evidence_accumulates(self):
        narrow = itemanalysis.wilson_interval(80, 100)
        wide = itemanalysis.wilson_interval(8, 10)
        self.assertLess(narrow[1] - narrow[0], wide[1] - wide[0])

    def test_wilson_interval_stays_within_zero_and_one(self):
        for correct, n in [(0, 5), (5, 5), (0, 1), (1, 1), (0, 0)]:
            low, high = itemanalysis.wilson_interval(correct, n)
            self.assertGreaterEqual(low, 0.0)
            self.assertLessEqual(high, 1.0)

    def test_median_handles_even_and_odd_lengths(self):
        self.assertEqual(itemanalysis.median([3, 1, 2]), 2)
        self.assertEqual(itemanalysis.median([4, 1, 3, 2]), 2.5)
        self.assertIsNone(itemanalysis.median([]))


class TestItemStatistics(unittest.TestCase):
    def test_difficulty_is_the_proportion_correct(self):
        rows = [row("q1", True), row("q1", False), row("q1", True), row("q1", True)]
        stats = itemanalysis.analyze(rows, [q("q1")])
        item = stats[0]
        self.assertEqual(item.attempts, 4)
        self.assertEqual(item.correct, 3)
        self.assertAlmostEqual(item.p_value, 0.75)

    def test_option_choices_are_counted(self):
        rows = [row("q1", True, chosen="B"), row("q1", False, chosen="A"),
                row("q1", False, chosen="A"), row("q1", False, chosen="C")]
        item = itemanalysis.analyze(rows, [q("q1", answer="B")])[0]
        self.assertEqual(item.option_counts, {"B": 1, "A": 2, "C": 1})

    def test_first_attempt_outcome_is_captured(self):
        rows = [row("q1", False, days_ago=5), row("q1", True, days_ago=1)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertIs(item.first_attempt_correct, False)

    def test_consecutive_recent_misses_are_counted(self):
        rows = [row("q1", True, days_ago=5), row("q1", False, days_ago=3),
                row("q1", False, days_ago=2), row("q1", False, days_ago=1)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertEqual(item.recent_streak_wrong, 3)
        self.assertIn("PERSISTENT_MISS", item.flags)

    def test_median_response_time_is_reported(self):
        rows = [row("q1", True, seconds=10), row("q1", True, seconds=20),
                row("q1", True, seconds=90), row("q1", True, seconds=30),
                row("q1", True, seconds=40)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertEqual(item.median_seconds, 30)

    def test_questions_never_served_are_reported_separately(self):
        stats = itemanalysis.analyze([row("q1", True)], [q("q1"), q("q2")])
        never = [s for s in stats if s.question_id == "q2"][0]
        self.assertEqual(never.attempts, 0)
        self.assertIn("NEVER_SERVED", never.flags)


class TestFlags(unittest.TestCase):
    def test_thin_data_suppresses_other_flags(self):
        rows = [row("q1", True) for _ in range(3)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertEqual(item.flags, ["THIN_DATA"])

    def test_an_item_everyone_gets_right_is_flagged_as_uninformative(self):
        """Enough of them that the interval, not the streak, says so.

        Ten straight correct is a 95% interval of 72-100%: consistent with a
        75% question having a good run. The flag now needs the lower bound
        above the threshold, so the fixture carries the evidence that claim
        requires.
        """
        rows = [row("q1", True, session="s%d" % i) for i in range(25)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertIn("TOO_EASY", item.flags)

    def test_a_short_lucky_run_is_not_called_too_easy(self):
        """The regression this gating exists for: 79% of items on a clean
        3000-answer history used to be flagged, mostly like this."""
        rows = [row("q1", True, session="s%d" % i) for i in range(8)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertNotIn("TOO_EASY", item.flags)

    def test_an_item_almost_always_missed_is_flagged(self):
        rows = [row("q1", False, chosen="A", session="s%d" % i) for i in range(15)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertIn("TOO_HARD", item.flags)

    def test_options_nobody_ever_picks_are_flagged_as_dead(self):
        """Gated on wrong answers, since that is what a distractor draws from.

        Four wrong answers over three distractors leaves most of them empty by
        arithmetic; eight makes an empty one worth remarking on - under 4% by
        chance if picks were even.
        """
        rows = ([row("q1", True, chosen="B") for _ in range(6)]
                + [row("q1", False, chosen="A") for _ in range(9)])
        item = itemanalysis.analyze(rows, [q("q1", answer="B")])[0]
        dead = [f for f in item.flags if f.startswith("DEAD_OPTION")]
        self.assertEqual(dead, ["DEAD_OPTION:CD"])

    def test_a_distractor_beating_the_key_is_flagged(self):
        rows = ([row("q1", False, chosen="C") for _ in range(6)]
                + [row("q1", True, chosen="B") for _ in range(2)])
        item = itemanalysis.analyze(rows, [q("q1", answer="B")])[0]
        self.assertIn("KEY_CHALLENGED:C", item.flags)

    def test_negative_discrimination_is_flagged(self):
        # Correct on the auditor's weak sessions, wrong on the strong ones.
        # Twenty sessions, not six. A Pearson correlation over six points has a
        # standard error near 0.45 - about half of clean items came back
        # negative on noise alone, which is what made this flag fire on four
        # items in five. The gate is twenty; the fixture meets it.
        rows = []
        pattern = [(True, False)] * 10 + [(False, True)] * 10
        for i, (target_ok, other_ok) in enumerate(pattern):
            session = "s%d" % i
            rows.append(row("target", target_ok, chosen="B" if target_ok else "A",
                            session=session))
            for j in range(4):
                rows.append(row("other%d" % j, other_ok, session=session))
        stats = {s.question_id: s for s in itemanalysis.analyze(
            rows, [q("target")] + [q("other%d" % j) for j in range(4)])}
        target = stats["target"]
        self.assertIsNotNone(target.discrimination)
        self.assertLess(target.discrimination, 0)
        self.assertIn("NEG_DISCRIMINATION", target.flags)

    def test_positive_discrimination_is_not_flagged(self):
        rows = []
        for i, ok in enumerate([True] * 10 + [False] * 10):
            session = "s%d" % i
            rows.append(row("target", ok, chosen="B" if ok else "A", session=session))
            for j in range(4):
                rows.append(row("other%d" % j, ok, session=session))
        stats = {s.question_id: s for s in itemanalysis.analyze(
            rows, [q("target")] + [q("other%d" % j) for j in range(4)])}
        target = stats["target"]
        self.assertGreater(target.discrimination, 0)
        self.assertNotIn("NEG_DISCRIMINATION", target.flags)

    def test_discrimination_needs_enough_attempts_and_sessions(self):
        rows = [row("q1", i % 2 == 0, session="s1") for i in range(8)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertIsNone(item.discrimination, "one session cannot support a correlation")


class TestRollups(unittest.TestCase):
    def test_bank_health_counts_served_and_unserved(self):
        rows = [row("q1", True) for _ in range(6)]
        stats = itemanalysis.analyze(rows, [q("q1"), q("q2"), q("q3")])
        health = itemanalysis.bank_health(stats)
        self.assertEqual(health.total_questions, 3)
        self.assertEqual(health.served, 1)
        self.assertEqual(health.never_served, 2)
        self.assertEqual(health.with_stats, 1)

    def test_difficulty_spread_buckets_add_up(self):
        rows = []
        for qid, hits in [("easy", 6), ("mid", 3), ("hard", 0)]:
            for i in range(6):
                rows.append(row(qid, i < hits, session="s%d" % i))
        stats = itemanalysis.analyze(rows, [q("easy"), q("mid"), q("hard")])
        health = itemanalysis.bank_health(stats)
        self.assertEqual(sum(health.difficulty_spread.values()), health.with_stats)
        self.assertEqual(health.difficulty_spread["trivial >=95%"], 1)
        self.assertEqual(health.difficulty_spread["very hard <25%"], 1)

    def test_topic_rollup_ranks_by_lower_confidence_bound(self):
        rows = ([row("a", False, topic="Shaky", session="s%d" % i) for i in range(2)]
                + [row("b", True, topic="Solid", session="s%d" % i) for i in range(20)])
        stats = itemanalysis.analyze(rows, [q("a", topic="Shaky"), q("b", topic="Solid")])
        rollup = itemanalysis.topic_rollup(stats)
        self.assertIn("Shaky", rollup[0][0])
        self.assertIn("Solid", rollup[-1][0])

    def test_thin_evidence_can_outrank_a_better_evidenced_topic(self):
        # Documented, intended behavior: 1/2 has a lower Wilson bound than 5/20,
        # because two attempts cannot rule out that the topic is worse. Drilling
        # it is the right response either way, since it resolves the uncertainty.
        rows = ([row("small", True, topic="Small", session="s1"),
                 row("small", False, topic="Small", session="s2")]
                + [row("big", i < 5, topic="Big", session="s%d" % i) for i in range(20)])
        stats = itemanalysis.analyze(rows, [q("small", topic="Small"), q("big", topic="Big")])
        rollup = itemanalysis.topic_rollup(stats)
        bounds = {label: interval[0] for label, _, _, _, interval in rollup}
        small = [v for k, v in bounds.items() if "Small" in k][0]
        big = [v for k, v in bounds.items() if "Big" in k][0]
        self.assertLess(small, big)
        self.assertIn("Small", rollup[0][0])

    def test_with_comparable_evidence_the_weaker_topic_ranks_first(self):
        rows = ([row("weak", i < 5, topic="Weak", session="s%d" % i) for i in range(20)]
                + [row("strong", i < 16, topic="Strong", session="s%d" % i) for i in range(20)])
        stats = itemanalysis.analyze(rows, [q("weak", topic="Weak"), q("strong", topic="Strong")])
        rollup = itemanalysis.topic_rollup(stats)
        self.assertIn("Weak", rollup[0][0])
        self.assertIn("Strong", rollup[-1][0])

    def test_rewrite_candidates_exclude_healthy_items(self):
        rows = ([row("fine", i < 4, session="s%d" % i) for i in range(6)]
                + [row("trivial", True, session="s%d" % i) for i in range(25)])
        stats = itemanalysis.analyze(rows, [q("fine"), q("trivial")])
        suspects = {s.question_id for s in itemanalysis.needs_rewrite(stats)}
        self.assertIn("trivial", suspects)
        self.assertNotIn("fine", suspects)


class TestTheEvidenceGatesStay(unittest.TestCase):
    """The gates are a decision, not a tuning knob.

    `DETECTION.md` check 4 is failing and will stay failing: discrimination
    needs about twenty attempts on one question and one learner's answers give
    about seven. The tempting "fix" is to lower these thresholds until the
    check passes again - which is exactly the original bug, where the flags
    fired on 79% of all items and their apparent detection was the
    false-positive rate in disguise. See CLAUDE.md section 4.
    """

    def test_discrimination_needs_a_real_sample(self):
        self.assertGreaterEqual(itemanalysis.MIN_ATTEMPTS_DISC, 20)

    def test_a_negative_correlation_must_be_meaningfully_negative(self):
        self.assertLessEqual(itemanalysis.NEG_DISCRIMINATION_AT, -0.1)

    def test_dead_options_are_gated_on_wrong_answers(self):
        """Total attempts is the wrong denominator: a distractor can only be
        picked by someone getting the question wrong."""
        self.assertGreaterEqual(itemanalysis.MIN_WRONG_FOR_DEAD, 8)

    def test_difficulty_flags_read_a_bound_not_a_point_estimate(self):
        """Eight straight correct is a lucky run, not a too-easy question."""
        rows = [row("q1", True, session="s%d" % i) for i in range(8)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertNotIn("TOO_EASY", item.flags)

    def test_the_easy_threshold_stays_reachable(self):
        """The opposite failure: requiring the lower bound to clear 0.95 needs
        about 73 consecutive correct answers, a flag that never fires."""
        rows = [row("q1", True, session="s%d" % i) for i in range(30)]
        item = itemanalysis.analyze(rows, [q("q1")])[0]
        self.assertIn("TOO_EASY", item.flags)


class TestAgainstRealBank(unittest.TestCase):
    def test_analysis_runs_over_the_shipped_bank_without_error(self):
        questions = loader.load_questions("cisa")
        rows = [row(questions[i].id, i % 3 != 0, session="s%d" % (i % 5))
                for i in range(len(questions))]
        stats = itemanalysis.analyze(rows, questions)
        health = itemanalysis.bank_health(stats)
        self.assertEqual(health.total_questions, len(questions))
        self.assertEqual(health.never_served, 0)
        self.assertIsNotNone(itemanalysis.topic_rollup(stats))


if __name__ == "__main__":
    unittest.main(verbosity=2)
