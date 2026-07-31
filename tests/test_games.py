"""Tests for the short-form games, the stem classifier and the pair taxonomy.

    python tests/test_games.py

The most important test in this file is the isolation one: game results must
never reach attempts.jsonl, because a five-second answer is not the same
evidence as a worked scenario and would corrupt both the stats and the
spaced-repetition scheduler.
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

from drillkit import games, loader, store  # noqa: E402
from drillkit.loader import Question  # noqa: E402


def q(qid: str, stem: str = "Which control is BEST?", answer: str = "B",
      asks: str = "", topic: str = "Data Encryption", domain: str = "5",
      why_wrong=None) -> Question:
    others = [k for k in "ABCD" if k != answer]
    if why_wrong is None:
        why_wrong = {k: "reason %s is wrong" % k for k in others}
    return Question(
        id=qid, domain=domain, section="A", topic=topic, stem=stem,
        options={"A": "alpha", "B": "bravo", "C": "charlie", "D": "delta"},
        answer=answer, why_correct="because", why_wrong=why_wrong, asks=asks,
    )


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def scripted(commands):
    supplied = iter(commands)

    def reader(_prompt=""):
        try:
            return next(supplied)
        except StopIteration:
            raise EOFError()
    return reader


class TestClassifier(unittest.TestCase):
    def test_first_and_next_win_over_everything_else(self):
        self.assertEqual(games.classify_stem(
            "Which of the following should the auditor do FIRST?"), "first")
        self.assertEqual(games.classify_stem(
            "The team's NEXT priority should BEST be to:"), "first")

    def test_risk_beats_the_generic_control_patterns(self):
        self.assertEqual(games.classify_stem(
            "The GREATEST risk is that the control fails."), "risk")
        self.assertEqual(games.classify_stem(
            "An IS auditor should be MOST concerned to find that:"), "risk")

    def test_primary_concern_reads_as_risk_not_definition(self):
        """PRIMARY normally signals a definition stem, so these two phrasings
        have to be caught by the risk family before the definition family sees
        them. They ask what is dangerous, not what something is."""
        self.assertEqual(games.classify_stem(
            "Which should the IS auditor identify as the PRIMARY concern?"), "risk")
        self.assertEqual(games.classify_stem(
            "The PRIMARY risk of this arrangement is that:"), "risk")
        # the definition sense of PRIMARY must still classify as before
        self.assertEqual(games.classify_stem(
            "The PRIMARY purpose of a control self-assessment is to:"), "definition")

    def test_strongest_is_recognized_without_swallowing_strongest_basis(self):
        """House style permits STRONGEST and the classifier did not handle it.
        The evidence family already claims 'STRONGEST basis', and that reading
        has to keep winning."""
        self.assertEqual(games.classify_stem(
            "Which asset should receive the STRONGEST authentication controls?"), "control")
        self.assertEqual(games.classify_stem(
            "Which provides the STRONGEST basis for concluding on the control?"), "evidence")

    def test_evidence_beats_definition_and_control(self):
        self.assertEqual(games.classify_stem(
            "Which provides the BEST evidence that the review was effective?"), "evidence")
        self.assertEqual(games.classify_stem(
            "Which of the following BEST demonstrates compliance?"), "evidence")

    def test_definition_beats_control(self):
        self.assertEqual(games.classify_stem(
            "Which of the following BEST describes middleware?"), "definition")
        self.assertEqual(games.classify_stem(
            "The PRIMARY purpose of a business case is to:"), "definition")

    def test_control_is_the_fallback_for_action_questions(self):
        self.assertEqual(games.classify_stem(
            "Which control would BEST address this weakness?"), "control")
        self.assertEqual(games.classify_stem(
            "Which of the following is MOST important to verify?"), "control")

    def test_a_stem_with_no_judgment_wording_is_unclassifiable(self):
        self.assertIsNone(games.classify_stem("The capital of France is:"))

    def test_an_explicit_asks_field_overrides_the_classifier(self):
        item = q("x", stem="Which control would BEST address this?", asks="definition")
        self.assertEqual(games.classify_stem(item.stem), "control")
        self.assertEqual(games.ask_type(item), "definition")

    def test_an_invalid_asks_value_falls_back_to_the_classifier(self):
        item = q("x", stem="Which control would BEST address this?", asks="nonsense")
        self.assertEqual(games.ask_type(item), "control")

    def test_the_game_taxonomy_matches_the_loader_whitelist(self):
        self.assertEqual(set(games.ASK_TYPES), set(loader.VALID_ASKS))
        self.assertEqual(set(games.ASK_ORDER), set(loader.VALID_ASKS))

    def test_every_shipped_question_can_be_classified(self):
        questions = loader.load_questions("cisa")
        unresolved = [x.id for x in questions if games.ask_type(x) is None]
        self.assertEqual(unresolved, [],
                         "Cold Read cannot serve these: %s" % unresolved)


class TestSelection(unittest.TestCase):
    def test_coldread_only_serves_classifiable_questions(self):
        pool = [q("good", stem="Which is BEST?"), q("bad", stem="Paris is in:")]
        picked = games.pick(pool, 10, "coldread", random.Random(1))
        self.assertEqual([x.id for x in picked], ["good"])

    def test_autopsy_needs_at_least_two_distractor_explanations(self):
        thin = q("thin", why_wrong={"A": "only one"})
        fat = q("fat")
        picked = games.pick([thin, fat], 10, "autopsy", random.Random(1))
        self.assertEqual([x.id for x in picked], ["fat"])

    def test_selection_respects_the_requested_count(self):
        pool = [q("q%d" % i) for i in range(20)]
        self.assertEqual(len(games.pick(pool, 5, "autopsy", random.Random(2))), 5)


class TestColdRead(unittest.TestCase):
    def _run(self, questions, commands):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            gpath = os.path.join(tmp, "results", "games.jsonl")
            game = games.ColdRead("cisa", gpath, out=out, reader=scripted(commands),
                                  rng=random.Random(3), now=FakeClock())
            game.run(questions)
            return game, out.getvalue(), games.load_games(gpath)

    def test_correct_read_is_scored_and_logged(self):
        item = q("q1", stem="The GREATEST risk is that:")  # risk -> option 2
        game, text, rows = self._run([item], ["2", "", "y"])
        self.assertEqual((game.asked, game.right), (1, 1))
        self.assertIn("Right", text)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["correct"])
        self.assertEqual(rows[0]["self_report"], "y")
        self.assertEqual(rows[0]["game"], "coldread")

    def test_incorrect_read_names_both_types(self):
        item = q("q1", stem="The GREATEST risk is that:")
        game, text, rows = self._run([item], ["1", "", "n"])
        self.assertEqual(game.right, 0)
        self.assertIn("GREATEST RISK", text)
        self.assertIn("FIRST / NEXT", text)
        self.assertFalse(rows[0]["correct"])
        self.assertIn("read=first", rows[0]["detail"])
        self.assertIn("expected=risk", rows[0]["detail"])

    def test_options_are_hidden_until_after_the_read(self):
        item = q("q1", stem="The GREATEST risk is that:")
        _, text, _ = self._run([item], ["2", "", "y"])
        read_prompt = text.index("What is this question asking for?")
        first_option = text.index("bravo")
        self.assertLess(read_prompt, first_option,
                        "the options must not appear before the read is committed")

    def test_skip_records_nothing(self):
        game, _, rows = self._run([q("q1")], ["s"])
        self.assertEqual(game.asked, 0)
        self.assertEqual(rows, [])

    def test_quitting_preserves_earlier_answers(self):
        items = [q("q1", stem="The GREATEST risk is that:"),
                 q("q2", stem="The GREATEST risk is that:")]
        game, text, rows = self._run(items, ["2", "", "y", "q"])
        self.assertEqual(game.asked, 1)
        self.assertEqual(len(rows), 1)
        self.assertIn("Stopped", text)

    def test_invalid_input_is_rejected_then_accepted(self):
        item = q("q1", stem="The GREATEST risk is that:")
        game, text, _ = self._run([item], ["9", "2", "", "c"])
        self.assertIn("Enter one of", text)
        self.assertEqual(game.right, 1)


class TestAutopsy(unittest.TestCase):
    def _run(self, questions, commands, seed=5):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            gpath = os.path.join(tmp, "results", "games.jsonl")
            game = games.Autopsy("cisa", gpath, out=out, reader=scripted(commands),
                                 rng=random.Random(seed), now=FakeClock())
            game.run(questions)
            return game, out.getvalue(), games.load_games(gpath)

    def _correct_sequence(self, item, seed=5):
        """Work out the right matching for a given shuffle seed."""
        rng = random.Random(seed)
        distractors = [k for k in "ABCD" if k != item.answer]
        shuffled = list(distractors)
        rng.shuffle(shuffled)
        labels = ["X", "Y", "Z"]
        label_for = {opt: labels[i] for i, opt in enumerate(shuffled)}
        return [label_for[opt].lower() for opt in distractors]

    def test_a_full_correct_match_scores(self):
        item = q("q1")
        game, text, rows = self._run([item], self._correct_sequence(item))
        self.assertEqual((game.asked, game.right), (1, 1))
        self.assertIn("3 of 3 matched", text)
        self.assertTrue(rows[0]["correct"])
        self.assertEqual(rows[0]["detail"], "matched=3/3")

    def test_a_partial_match_does_not_score(self):
        item = q("q1")
        right = self._correct_sequence(item)
        wrong = [right[1], right[0], right[2]]  # swap the first two
        game, text, rows = self._run([item], wrong)
        self.assertEqual(game.right, 0)
        self.assertIn("1 of 3 matched", text)
        self.assertFalse(rows[0]["correct"])

    def test_the_correct_answer_is_marked_before_matching(self):
        item = q("q1", answer="C")
        _, text, _ = self._run([item], self._correct_sequence(item))
        self.assertIn("* C is correct", text)

    def test_questions_without_enough_explanations_are_skipped(self):
        item = q("thin", why_wrong={"A": "only one"})
        game, _, rows = self._run([item], [])
        self.assertEqual(game.asked, 0)
        self.assertEqual(rows, [])

    def test_feedback_names_the_right_label_for_each_miss(self):
        item = q("q1")
        right = self._correct_sequence(item)
        wrong = [right[1], right[0], right[2]]
        _, text, _ = self._run([item], wrong)
        self.assertIn("should be", text)


class TestIsolationFromDrillStats(unittest.TestCase):
    """The point of the whole design: games must not pollute real evidence."""

    def test_games_write_to_a_different_file_than_attempts(self):
        results = os.path.join("cisa", "results", "attempts.jsonl")
        gpath = games.games_path(results)
        self.assertNotEqual(os.path.abspath(gpath), os.path.abspath(results))
        self.assertTrue(gpath.endswith("games.jsonl"))
        self.assertEqual(os.path.dirname(gpath), os.path.dirname(results))

    def test_playing_a_game_leaves_the_attempt_log_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts = os.path.join(tmp, "results", "attempts.jsonl")
            os.makedirs(os.path.dirname(attempts), exist_ok=True)
            with open(attempts, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "ts": "2026-07-27T00:00:00+00:00", "session": "real",
                    "question_id": "cisa-d5a-001", "cert": "CISA", "domain": "5",
                    "section": "A", "topic": "Data Encryption", "chosen": "B",
                    "answer": "B", "correct": True, "seconds": 45.0, "mode": "smart",
                }) + "\n")
            before = open(attempts, encoding="utf-8").read()

            gpath = games.games_path(attempts)
            item = q("q1", stem="The GREATEST risk is that:")
            games.ColdRead("cisa", gpath, out=io.StringIO(),
                           reader=scripted(["2", "", "y"]),
                           rng=random.Random(1), now=FakeClock()).run([item])
            games.Autopsy("cisa", gpath, out=io.StringIO(),
                          reader=scripted(["x", "y", "z"]),
                          rng=random.Random(1), now=FakeClock()).run([q("q2")])

            after = open(attempts, encoding="utf-8").read()
            self.assertEqual(before, after, "games must not write to attempts.jsonl")
            self.assertEqual(len(store.load(attempts)), 1)
            self.assertEqual(len(games.load_games(gpath)), 2)

    def test_a_corrupt_game_line_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            gpath = os.path.join(tmp, "games.jsonl")
            with open(gpath, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"question_id": "a", "correct": True}) + "\n")
                fh.write('{"question_id": "b", "corr\n')
                fh.write(json.dumps({"question_id": "c", "correct": False}) + "\n")
            rows = games.load_games(gpath)
            self.assertEqual([r["question_id"] for r in rows], ["a", "c"])


class TestConfusablePairs(unittest.TestCase):
    def test_the_shipped_pair_file_is_valid(self):
        pairs = loader.load_pairs("cisa")
        questions = loader.load_questions("cisa")
        errors, _ = loader.validate_pairs(pairs, questions)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(pairs), 20)

    def test_a_reference_to_a_missing_question_is_an_error(self):
        pairs = [{"id": "p", "label": "L", "discriminator": "D",
                  "terms": ["a", "b"], "question_ids": ["nope"]}]
        errors, _ = loader.validate_pairs(pairs, [q("real")])
        self.assertTrue(any("not in the bank" in e for e in errors))

    def test_a_pair_needs_two_terms_to_be_a_confusion(self):
        pairs = [{"id": "p", "label": "L", "discriminator": "D",
                  "terms": ["only one"], "question_ids": []}]
        errors, _ = loader.validate_pairs(pairs, [])
        self.assertTrue(any("at least two terms" in e for e in errors))

    def test_duplicate_pair_ids_are_an_error(self):
        pair = {"id": "dupe", "label": "L", "discriminator": "D",
                "terms": ["a", "b"], "question_ids": []}
        errors, _ = loader.validate_pairs([dict(pair), dict(pair)], [])
        self.assertTrue(any("duplicate id" in e for e in errors))

    def test_an_unmapped_pair_warns_rather_than_failing(self):
        pairs = [{"id": "gap", "label": "L", "discriminator": "D",
                  "terms": ["a", "b"], "question_ids": []}]
        errors, warnings = loader.validate_pairs(pairs, [])
        self.assertEqual(errors, [])
        self.assertTrue(any("no bank questions" in w for w in warnings))

    def test_every_pair_carries_a_usable_discriminator(self):
        for pair in loader.load_pairs("cisa"):
            self.assertGreater(len(pair.get("discriminator", "")), 40,
                               "pair %s has a thin discriminator" % pair.get("id"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
