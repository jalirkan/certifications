"""Tests for difficulty selection.

The empty and short cases carry most of the weight here. Of the 180
topic-by-difficulty combinations in the real bank, 36 return nothing and another
83 return one or two questions, so "you asked for 20 and there are 7" is the
normal path rather than an error path.

The rules being defended:

* strict means strict - never a silent top-up from an adjacent band;
* the learner is told the count and the reason *before* the session starts;
* filtering must not silently defeat the scheduler's due queue;
* the labels are author-assigned, and every surface says so;
* the vocabulary cannot drift, because selection now depends on it.

    python tests/test_difficulty.py
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import difficulty, loader  # noqa: E402
from drillkit.loader import Question  # noqa: E402
from drillkit.webapi import Api, ApiError  # noqa: E402


def q(qid: str, level: str = "medium", topic: str = "Data Encryption",
      domain: str = "5") -> Question:
    return Question(
        id=qid, domain=domain, section="A", topic=topic,
        stem="Which control is BEST?",
        options={"A": "alpha", "B": "bravo", "C": "charlie", "D": "delta"},
        answer="B", why_correct="because",
        why_wrong={k: "no" for k in "ACD"},
        difficulty=level,
    )


def row(qid, correct, ts="2026-07-01T00:00:00+00:00"):
    return {"ts": ts, "session": "s", "question_id": qid, "cert": "CISA",
            "domain": "5", "section": "A", "topic": "Data Encryption",
            "chosen": "B", "answer": "B", "correct": correct,
            "seconds": 30.0, "mode": "smart"}


class TestVocabulary(unittest.TestCase):
    """A label outside the vocabulary would silently vanish from every filter."""

    def test_the_shipped_bank_uses_only_the_vocabulary(self):
        questions = loader.load_questions("cisa")
        errors, _ = loader.validate(questions, loader.load_outline("cisa"))
        self.assertEqual([e for e in errors if "difficulty" in e], [])

    def test_a_mangled_label_is_an_error_not_a_warning(self):
        errors, warnings = loader.validate([q("bad", level="Medium")])
        self.assertTrue(any("difficulty 'Medium'" in e for e in errors),
                        "case drift must be rejected: %s" % errors)
        self.assertFalse(any("difficulty" in w for w in warnings))

    def test_an_invented_label_is_rejected(self):
        errors, _ = loader.validate([q("bad", level="moderate")])
        self.assertTrue(any("difficulty 'moderate'" in e for e in errors))

    def test_normalise_accepts_the_vocabulary_and_ramp_only(self):
        for good in ("easy", "medium", "hard", "ramp", "HARD", " ramp "):
            self.assertTrue(difficulty.normalise(good))
        for bad in ("moderate", "very hard", None, "", "4"):
            self.assertEqual(difficulty.normalise(bad), "")


class TestStrictFiltering(unittest.TestCase):
    def test_a_band_is_never_topped_up_from_a_neighbour(self):
        pool = [q("e1", "easy"), q("m1", "medium"), q("m2", "medium"),
                q("h1", "hard")]
        hard = difficulty.filter_pool(pool, "hard")
        self.assertEqual([x.id for x in hard], ["h1"])
        self.assertEqual({x.difficulty for x in hard}, {"hard"})

    def test_asking_for_more_than_exists_yields_what_exists(self):
        pool = [q("h1", "hard")] + [q("m%d" % i, "medium") for i in range(20)]
        avail = difficulty.availability(pool, "hard", 20)
        self.assertEqual(avail.available, 1)
        self.assertTrue(avail.short)
        self.assertIn("rather than 20", avail.message())
        self.assertIn("nothing is topped up", avail.message().lower())

    def test_no_filter_leaves_the_pool_whole(self):
        pool = [q("e1", "easy"), q("h1", "hard")]
        self.assertEqual(len(difficulty.apply(pool, "")), 2)

    def test_ramp_does_not_filter(self):
        pool = [q("e1", "easy"), q("m1", "medium"), q("h1", "hard")]
        self.assertFalse(difficulty.is_filter("ramp"))
        self.assertEqual(len(difficulty.apply(pool, "ramp")), 3)


class TestTheEmptyCase(unittest.TestCase):
    """A fifth of topic-plus-difficulty combinations return nothing."""

    def test_an_empty_band_says_what_is_there_instead(self):
        pool = [q("e1", "easy"), q("m1", "medium"), q("m2", "medium")]
        avail = difficulty.availability(pool, "hard", 10)
        self.assertTrue(avail.empty)
        self.assertEqual(avail.available, 0)
        self.assertIn("No hard questions", avail.message())
        self.assertIn("3 question(s)", avail.message())
        self.assertEqual(avail.counts,
                         {"easy": 1, "medium": 2, "hard": 0, "expert": 0})

    def test_an_entirely_empty_pool_says_so_differently(self):
        avail = difficulty.availability([], "hard", 10)
        self.assertTrue(avail.empty)
        self.assertIn("Nothing matches those filters at all", avail.message())

    def test_the_real_bank_has_empty_combinations_and_they_are_handled(self):
        questions = loader.load_questions("cisa")
        topics = sorted({x.topic for x in questions})
        empty = None
        for topic in topics:
            pool = [x for x in questions if x.topic == topic]
            if not any(x.difficulty == "hard" for x in pool):
                empty = (topic, pool)
                break
        self.assertIsNotNone(empty, "expected at least one topic with no hard questions")
        avail = difficulty.availability(empty[1], "hard", 20)
        self.assertTrue(avail.empty)
        self.assertTrue(avail.message())

    def test_the_api_refuses_to_start_an_empty_session(self):
        api = Api("cisa", "difftest-empty-%s" % os.urandom(3).hex())
        questions = api.questions
        topic = next(t for t in sorted({x.topic for x in questions})
                     if not any(x.difficulty == "hard" for x in questions
                                if x.topic == t))
        with self.assertRaises(ApiError) as caught:
            api.drill_start({"mode": "random", "n": 5, "topic": topic,
                             "difficulty": "hard"})
        self.assertIn("No hard questions", str(caught.exception))

    def test_the_preview_answers_before_the_session_starts(self):
        api = Api("cisa", "difftest-preview-%s" % os.urandom(3).hex())
        preview = api.drill_preview({"difficulty": "hard", "n": 500})
        self.assertTrue(preview["short"])
        self.assertGreater(preview["matching"], 0)
        self.assertIn("caveat", preview)
        self.assertIn("message", preview)


class TestTheExpertBand(unittest.TestCase):
    """Added to the vocabulary before any question carries it.

    An empty band is the honest state: promoting existing `hard` questions
    into it would invent a distinction nobody made. These tests pin the
    behaviour so the band works the day content arrives, and reads correctly
    until then. Delete the emptiness assertion when questions land.
    """

    def test_expert_is_in_the_vocabulary_and_ranks_hardest(self):
        self.assertIn("expert", loader.DIFFICULTIES)
        self.assertEqual(difficulty.ORDER["expert"],
                         max(difficulty.ORDER.values()))
        self.assertGreater(difficulty.ORDER["expert"], difficulty.ORDER["hard"])

    def test_an_expert_label_now_validates(self):
        errors, _ = loader.validate([q("x1", level="expert")])
        self.assertEqual([e for e in errors if "difficulty" in e], [])

    def test_an_empty_band_says_so(self):
        """Kept as a unit test against a synthetic bank. It was written against
        the real bank while `expert` was still empty; the band has since been
        authored, so asserting emptiness there would fail for the one reason
        that means the work succeeded."""
        avail = difficulty.availability([q("h1", "hard")], "expert", 20)
        self.assertTrue(avail.empty)
        self.assertIn("No expert questions", avail.message())

    def test_the_shipped_expert_band_can_fill_a_session(self):
        questions = loader.load_questions("cisa")
        avail = difficulty.availability(questions, "expert", 20)
        self.assertFalse(avail.empty)
        expert = [x for x in questions if x.difficulty == "expert"]
        self.assertGreaterEqual(len(expert), 20,
                                "below ~20 the band cannot fill a session")
        # Weighted to the blueprint so a domain-filtered expert session works.
        for domain in ("4", "5"):
            self.assertGreaterEqual(
                sum(1 for x in expert if x.domain == domain), 10,
                "D%s should support a domain-filtered expert session" % domain)

    def test_the_ramp_places_expert_last_once_questions_exist(self):
        pool = [q("x1", "expert"), q("e1", "easy"), q("h1", "hard"),
                q("m1", "medium")]
        self.assertEqual([x.difficulty for x in difficulty.ramp_order(pool)],
                         ["easy", "medium", "hard", "expert"])

    def test_filtering_to_expert_is_strict_once_questions_exist(self):
        pool = [q("x1", "expert"), q("h1", "hard")]
        picked = difficulty.filter_pool(pool, "expert")
        self.assertEqual([x.id for x in picked], ["x1"])


class TestTheRamp(unittest.TestCase):
    """Built reorder-only: the scheduler still chooses, the ramp just sorts."""

    def test_it_orders_easiest_first(self):
        pool = [q("h1", "hard"), q("e1", "easy"), q("m1", "medium")]
        self.assertEqual([x.difficulty for x in difficulty.ramp_order(pool)],
                         ["easy", "medium", "hard"])

    def test_it_is_stable_inside_a_band(self):
        """The scheduler's priority order has to survive the sort."""
        pool = [q("m1", "medium"), q("m2", "medium"), q("m3", "medium"),
                q("e1", "easy")]
        ordered = difficulty.ramp_order(pool)
        self.assertEqual([x.id for x in ordered], ["e1", "m1", "m2", "m3"])

    def test_it_serves_exactly_what_it_was_given(self):
        pool = [q("h1", "hard"), q("e1", "easy"), q("m1", "medium")]
        self.assertEqual({x.id for x in difficulty.ramp_order(pool)},
                         {x.id for x in pool})

    def test_a_single_band_set_reports_no_ramp(self):
        flat = [q("m%d" % i, "medium") for i in range(5)]
        self.assertEqual(difficulty.ramp_spread(flat), 1)
        mixed = flat + [q("e1", "easy")]
        self.assertEqual(difficulty.ramp_spread(mixed), 2)

    def test_the_api_reports_the_band_spread(self):
        api = Api("cisa", "difftest-ramp-%s" % os.urandom(3).hex())
        data = api.drill_start({"mode": "random", "n": 20, "difficulty": "ramp"})
        self.assertEqual(data["difficulty"], "ramp")
        self.assertIn("ramp_bands", data)
        served = [x["difficulty"] for x in data["questions"]]
        ranks = [difficulty.ORDER[d] for d in served]
        self.assertEqual(ranks, sorted(ranks), "ramp must run easiest first")


class TestTheDueQueueIsNotSilentlySkipped(unittest.TestCase):
    def test_suppressed_due_questions_are_counted(self):
        pool = [q("m1", "medium"), q("m2", "medium"), q("h1", "hard")]
        # Both medium questions were missed, so both are due.
        history = {"m1": [row("m1", False)], "m2": [row("m2", False)],
                   "h1": [row("h1", True)]}
        avail = difficulty.availability(pool, "hard", 10, history)
        self.assertEqual(avail.due_suppressed, 2)

    def test_nothing_is_reported_when_the_filter_hides_nothing(self):
        pool = [q("h1", "hard"), q("h2", "hard")]
        history = {"h1": [row("h1", False)]}
        avail = difficulty.availability(pool, "hard", 10, history)
        self.assertEqual(avail.due_suppressed, 0)

    def test_an_unfiltered_session_reports_no_suppression(self):
        pool = [q("m1", "medium"), q("h1", "hard")]
        history = {"m1": [row("m1", False)]}
        self.assertEqual(
            difficulty.availability(pool, "", 10, history).due_suppressed, 0)

    def test_a_question_still_inside_its_interval_is_not_due(self):
        recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        pool = [q("m1", "medium"), q("h1", "hard")]
        history = {"m1": [row("m1", True, ts=recent)]}
        avail = difficulty.availability(pool, "hard", 10, history)
        self.assertEqual(avail.due_suppressed, 0,
                         "a correctly-answered question inside its interval "
                         "is not being skipped")


class TestHonestyAboutTheLabels(unittest.TestCase):
    def test_the_caveat_names_the_basis(self):
        self.assertIn("Author-assigned", difficulty.CAVEAT)
        self.assertIn("not yet checked", difficulty.CAVEAT)

    def test_every_availability_payload_carries_the_caveat(self):
        payload = difficulty.availability([q("h1", "hard")], "hard", 1).as_dict()
        self.assertEqual(payload["caveat"], difficulty.CAVEAT)

    def test_nothing_here_claims_the_labels_are_measured(self):
        with open(difficulty.__file__, "r", encoding="utf-8") as fh:
            source = fh.read().lower()
        for banned in ("measured difficulty", "empirical label",
                       "validated label"):
            self.assertNotIn(banned, source)

    def test_labels_are_never_rewritten(self):
        """Rule 4: an invented label is worse than an unvalidated one."""
        original = [q("e1", "easy"), q("h1", "hard")]
        difficulty.filter_pool(original, "hard")
        difficulty.ramp_order(original)
        self.assertEqual([x.difficulty for x in original], ["easy", "hard"])


class TestFilteringHappensBeforeScheduling(unittest.TestCase):
    def test_the_scheduler_orders_only_what_survived_the_filter(self):
        api = Api("cisa", "difftest-order-%s" % os.urandom(3).hex())
        data = api.drill_start({"mode": "smart", "n": 15, "difficulty": "hard"})
        self.assertTrue(data["questions"])
        self.assertEqual({x["difficulty"] for x in data["questions"]}, {"hard"})

    def test_availability_is_reported_back_from_start(self):
        api = Api("cisa", "difftest-report-%s" % os.urandom(3).hex())
        data = api.drill_start({"mode": "random", "n": 500, "difficulty": "hard"})
        self.assertTrue(data["availability"]["short"])
        self.assertEqual(data["availability"]["caveat"], difficulty.CAVEAT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
