"""Tests for principle tagging, diagnosis and principle-aware selection.

    python tests/test_principles.py

The test that matters most is the planted-weakness one: given a learner who is
bad at exactly two rules and fine at everything else, the diagnostic has to
name those two rules and not the topics they happen to appear in.
"""

from __future__ import annotations

import io
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from drillkit import games, loader, principles as principles_mod, session as session_mod  # noqa: E402
from drillkit.loader import Question  # noqa: E402


def q(qid: str, domain: str = "5", topic: str = "Data Encryption",
      answer: str = "B") -> Question:
    others = [k for k in "ABCD" if k != answer]
    return Question(
        id=qid, domain=domain, section="A", topic=topic,
        stem="Which control is BEST?",
        options={"A": "alpha", "B": "bravo", "C": "charlie", "D": "delta"},
        answer=answer, why_correct="because",
        why_wrong={k: "no" for k in others},
    )


def principle(pid, qids, name=None):
    return {
        "id": pid, "name": name or pid.replace("-", " ").title(),
        "statement": "Statement for %s." % pid,
        "why": "Why %s holds." % pid,
        "misapplication": "What people do instead of %s." % pid,
        "scope": "When %s does not apply." % pid,
        "question_ids": list(qids),
    }


def row(qid, correct, domain="5", session="s1"):
    return {"ts": "2026-07-27T00:00:00+00:00", "session": session,
            "question_id": qid, "cert": "CISA", "domain": domain, "section": "A",
            "topic": "Data Encryption", "chosen": "B", "answer": "B",
            "correct": correct, "seconds": 40.0, "mode": "smart"}


class TestLoaderValidation(unittest.TestCase):
    def test_the_shipped_principle_file_is_valid(self):
        rules = loader.load_principles("cisa")
        questions = loader.load_questions("cisa")
        errors, _ = loader.validate_principles(rules, questions)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(rules), 15)

    def test_unknown_question_reference_is_an_error(self):
        errors, _ = loader.validate_principles(
            [principle("p", ["ghost"])], [q("real")])
        self.assertTrue(any("not in the bank" in e for e in errors))

    def test_duplicate_principle_ids_are_an_error(self):
        errors, _ = loader.validate_principles(
            [principle("dupe", []), principle("dupe", [])], [])
        self.assertTrue(any("duplicate id" in e for e in errors))

    def test_missing_required_fields_are_errors(self):
        bad = principle("p", [])
        del bad["misapplication"]
        del bad["scope"]
        errors, _ = loader.validate_principles([bad], [])
        self.assertTrue(any("misapplication" in e for e in errors))
        self.assertTrue(any("scope" in e for e in errors))

    def test_a_single_domain_principle_warns_because_it_cannot_show_transfer(self):
        items = [q("a", domain="5"), q("b", domain="5")]
        _, warnings = loader.validate_principles(
            [principle("p", ["a", "b"])], items)
        self.assertTrue(any("cannot show cross-domain transfer" in w for w in warnings))

    def test_a_multi_domain_principle_does_not_warn(self):
        items = [q("a", domain="1"), q("b", domain="4")]
        _, warnings = loader.validate_principles(
            [principle("p", ["a", "b"])], items)
        self.assertFalse(any("cross-domain" in w for w in warnings))

    def test_index_maps_questions_to_every_rule_that_claims_them(self):
        index = loader.principle_index(
            [principle("p1", ["a", "b"]), principle("p2", ["b"])])
        self.assertEqual(index["a"], ["p1"])
        self.assertEqual(sorted(index["b"]), ["p1", "p2"])

    def test_every_shipped_rule_appears_in_at_least_two_domains(self):
        rules = loader.load_principles("cisa")
        by_id = {x.id: x for x in loader.load_questions("cisa")}
        for p in rules:
            domains = {by_id[i].domain for i in p["question_ids"] if i in by_id}
            self.assertGreaterEqual(
                len(domains), 2,
                "%s only appears in domain(s) %s" % (p["id"], domains))


class TestSummarize(unittest.TestCase):
    def test_accuracy_is_aggregated_per_rule(self):
        items = [q("a", domain="1"), q("b", domain="4")]
        rules = [principle("p", ["a", "b"])]
        rows = [row("a", True), row("a", False), row("b", True), row("b", True)]
        stat = principles_mod.summarize(rules, items, rows)[0]
        self.assertEqual((stat.attempts, stat.correct), (4, 3))
        self.assertAlmostEqual(stat.accuracy, 0.75)
        self.assertEqual(stat.questions_total, 2)
        self.assertEqual(stat.questions_seen, 2)

    def test_a_rule_with_no_attempts_reports_no_accuracy(self):
        stat = principles_mod.summarize(
            [principle("p", ["a"])], [q("a")], [])[0]
        self.assertIsNone(stat.accuracy)
        self.assertEqual(stat.questions_seen, 0)

    def test_ranking_puts_the_weakest_rule_first(self):
        items = [q("a", domain="1"), q("b", domain="4")]
        rules = [principle("strong", ["a"]), principle("weak", ["b"])]
        rows = ([row("a", True) for _ in range(10)]
                + [row("b", False) for _ in range(10)])
        ranked = principles_mod.summarize(rules, items, rows)
        self.assertEqual(ranked[0].principle_id, "weak")

    def test_the_weak_untested_split_respects_the_minimum(self):
        items = [q("a"), q("b")]
        rules = [principle("tested", ["a"]), principle("thin", ["b"])]
        rows = [row("a", True) for _ in range(6)] + [row("b", True)]
        stats = principles_mod.summarize(rules, items, rows)
        self.assertEqual([s.principle_id for s in principles_mod.weakest(stats, 4)],
                         ["tested"])
        self.assertEqual([s.principle_id for s in principles_mod.untested(stats, 4)],
                         ["thin"])

    def test_the_misapplication_text_travels_with_the_stat(self):
        stat = principles_mod.summarize(
            [principle("p", ["a"])], [q("a")], [row("a", False)])[0]
        self.assertIn("What people do instead", stat.misapplication)
        self.assertIn("does not apply", stat.scope)


class TestSelection(unittest.TestCase):
    def test_one_per_domain_returns_exactly_one_from_each(self):
        items = [q("d1a", domain="1"), q("d1b", domain="1"),
                 q("d4a", domain="4"), q("d5a", domain="5")]
        picked = principles_mod.one_per_domain(items, random.Random(1))
        self.assertEqual(sorted(x.domain for x in picked), ["1", "4", "5"])

    def test_one_per_domain_prefers_questions_not_yet_seen(self):
        items = [q("seen", domain="1"), q("fresh", domain="1")]
        picked = principles_mod.one_per_domain(items, random.Random(1), seen={"seen"})
        self.assertEqual([x.id for x in picked], ["fresh"])

    def test_one_per_domain_falls_back_when_everything_is_seen(self):
        items = [q("a", domain="1")]
        picked = principles_mod.one_per_domain(items, random.Random(1), seen={"a"})
        self.assertEqual([x.id for x in picked], ["a"])

    def test_weak_principle_selection_targets_the_weak_rule(self):
        items = ([q("w%d" % i, domain="1") for i in range(6)]
                 + [q("s%d" % i, domain="4") for i in range(6)])
        rules = [principle("weak", ["w%d" % i for i in range(6)]),
                 principle("strong", ["s%d" % i for i in range(6)])]
        rows = ([row("w0", False) for _ in range(6)]
                + [row("s0", True) for _ in range(6)])
        picked, targeted = principles_mod.select_by_weak_principles(
            items, rules, rows, 4, random.Random(2))
        self.assertEqual(targeted[0], "weak")
        self.assertTrue(any(x.id.startswith("w") for x in picked))

    def test_weak_principle_selection_prefers_unseen_questions(self):
        items = [q("seen", domain="1"), q("fresh", domain="4")]
        rules = [principle("p", ["seen", "fresh"])]
        rows = [row("seen", False) for _ in range(5)]
        picked, _ = principles_mod.select_by_weak_principles(
            items, rules, rows, 1, random.Random(3))
        self.assertEqual([x.id for x in picked], ["fresh"],
                         "a different question tests the rule; the same one tests recall")

    def test_selection_never_returns_duplicates(self):
        items = [q("a", domain="1"), q("b", domain="4"), q("c", domain="5")]
        rules = [principle("p", ["a", "b", "c"])]
        picked, _ = principles_mod.select_by_weak_principles(
            items, rules, [], 3, random.Random(4))
        self.assertEqual(len(picked), len({x.id for x in picked}))

    def test_questions_for_returns_only_known_questions(self):
        found = principles_mod.questions_for(
            [principle("p", ["a", "ghost"])], "p", [q("a")])
        self.assertEqual([x.id for x in found], ["a"])

    def test_questions_for_an_unknown_rule_is_empty(self):
        self.assertEqual(principles_mod.questions_for([], "nope", [q("a")]), [])


class TestStudyCard(unittest.TestCase):
    def test_the_card_contains_every_rule_with_all_four_parts(self):
        rules = loader.load_principles("cisa")
        card = principles_mod.render_card(rules)
        for p in rules:
            self.assertIn(p["name"], card)
        self.assertEqual(card.count("WHY:"), len(rules))
        self.assertEqual(card.count("TRAP:"), len(rules))
        self.assertEqual(card.count("NOT WHEN:"), len(rules))

    def test_the_card_stays_within_terminal_width(self):
        card = principles_mod.render_card(loader.load_principles("cisa"), width=78)
        for line in card.splitlines():
            self.assertLessEqual(len(line), 78, "too wide: %r" % line)

    def test_the_card_is_generated_so_it_cannot_drift(self):
        rules = [principle("only", ["a"], name="The Only Rule")]
        card = principles_mod.render_card(rules)
        self.assertIn("The Only Rule", card)
        self.assertNotIn("Risk assessment", card,
                         "card must reflect the taxonomy passed in, not a hard-coded list")


class TestInDrillDisplay(unittest.TestCase):
    def test_the_governing_rule_is_shown_after_the_explanation(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            supplied = iter(["B"])

            def reader(_p=""):
                try:
                    return next(supplied)
                except StopIteration:
                    raise EOFError()

            session_mod.run([q("a")], "cisa", "smart", path, out=out, reader=reader,
                            principle_notes={"a": "Prevent beats detect"})
            text = out.getvalue()
            self.assertIn("RULE: Prevent beats detect", text)
            self.assertLess(text.index("Why B is right"), text.index("RULE:"))

    def test_no_rule_line_appears_when_the_question_is_untagged(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attempts.jsonl")
            supplied = iter(["B"])

            def reader(_p=""):
                try:
                    return next(supplied)
                except StopIteration:
                    raise EOFError()

            session_mod.run([q("a")], "cisa", "smart", path, out=out, reader=reader)
            self.assertNotIn("RULE:", out.getvalue())


class TestDiagnosisFindsPlantedWeakness(unittest.TestCase):
    """The whole point: name the reasoning habit, not the topic it appeared in."""

    def test_a_learner_weak_on_two_rules_has_those_two_ranked_first(self):
        rng = random.Random(11)
        items = []
        rules = []
        for pid in ("alpha", "beta", "gamma", "delta"):
            qids = []
            for n, domain in enumerate(("1", "2", "4", "5")):
                qid = "%s-%d" % (pid, n)
                items.append(q(qid, domain=domain, topic="Topic %s" % n))
                qids.append(qid)
            rules.append(principle(pid, qids))

        weak = {"beta", "delta"}
        rows = []
        for p in rules:
            for qid in p["question_ids"]:
                for _ in range(4):
                    ok = rng.random() < (0.15 if p["id"] in weak else 0.9)
                    rows.append(row(qid, ok))

        ranked = principles_mod.summarize(rules, items, rows)
        self.assertEqual({ranked[0].principle_id, ranked[1].principle_id}, weak)
        self.assertLess(ranked[0].accuracy, 0.5)
        self.assertGreater(ranked[-1].accuracy, 0.7)

    def test_the_weakness_is_invisible_by_topic_because_it_is_spread_across_them(self):
        """A rule-level weakness spread thinly over many topics hides from a
        topic report. That asymmetry is the reason this axis exists."""
        rng = random.Random(12)
        items, rules, rows = [], [], []
        for pid in ("alpha", "beta"):
            qids = []
            for n in range(8):
                qid = "%s-%d" % (pid, n)
                items.append(q(qid, domain=str((n % 4) + 1), topic="Topic %d" % n))
                qids.append(qid)
            rules.append(principle(pid, qids))
        # Enough attempts per question that the comparison reflects the
        # expectation rather than one noisy draw. The claim is about where a
        # spread-out weakness shows up, not about small-sample luck.
        for p in rules:
            for qid in p["question_ids"]:
                for _ in range(15):
                    rows.append(row(qid, rng.random() < (0.2 if p["id"] == "beta" else 0.9)))

        ranked = principles_mod.summarize(rules, items, rows)
        self.assertEqual(ranked[0].principle_id, "beta")

        # By topic, every topic contains one weak and one strong question, so
        # each lands near 55% and nothing stands out.
        by_topic = {}
        lookup = {x.id: x for x in items}
        for r in rows:
            t = lookup[r["question_id"]].topic
            agg = by_topic.setdefault(t, [0, 0])
            agg[0] += 1
            agg[1] += 1 if r["correct"] else 0
        spread = [ok / n for n, ok in by_topic.values()]
        self.assertLess(max(spread) - min(spread), 0.4,
                        "topics should look uniformly mediocre, hiding the real cause")


if __name__ == "__main__":
    unittest.main(verbosity=2)
