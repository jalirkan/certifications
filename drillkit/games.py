"""Short-form drills that target specific failure modes.

These are deliberately **not** normal drills. They train the substrate that
scenario judgment runs on, and they are logged to a separate file so that a
five-second answer can never be mistaken for a considered one:

* **Cold Read** - options hidden. Name what the question is actually asking
  for, then predict the answer before seeing the choices. Targets the most
  common real failure: answering a question you misread.
* **Autopsy** - the correct answer is given. Match each distractor to the
  explanation of why it is wrong. Teaches how the traps are built, which is
  what transfers to unseen questions.

Neither writes to attempts.jsonl. Game results do not feed headline accuracy,
item analysis, or the spaced-repetition scheduler.
"""

from __future__ import annotations

import json
import os
import random
import re
import textwrap
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, TextIO, Tuple

from .loader import OPTION_KEYS, Question
from .store import now_iso

WIDTH = 78
RULE = "=" * WIDTH
THIN = "-" * WIDTH


# --------------------------------------------------------------------------
# what is this question asking for?
# --------------------------------------------------------------------------

ASK_TYPES: Dict[str, Tuple[str, str]] = {
    "first":      ("FIRST / NEXT", "the first action to take"),
    "risk":       ("GREATEST RISK", "what is most dangerous or concerning"),
    "control":    ("BEST CONTROL", "what should be done or recommended"),
    "evidence":   ("BEST EVIDENCE", "what proves it, or what follows from the evidence"),
    "definition": ("DEFINITION", "what something is, or how two things differ"),
}

ASK_ORDER = ["first", "risk", "evidence", "definition", "control"]

# Ordered: the first family to match wins. Sequence questions are the most
# distinctive, then risk, then evidence; 'control' is deliberately last because
# its patterns are the broadest and would otherwise swallow the others.
_ASK_RULES: List[Tuple[str, List[str]]] = [
    ("first", [r"\bFIRST\b", r"\bNEXT\b"]),
    ("risk", [
        r"GREATEST risk", r"GREATEST concern", r"MOST concerned", r"GREATEST limitation",
        r"GREATEST challenge", r"GREATEST control risk", r"presents the GREATEST",
        r"MOST significant limitation", r"MOST likely to limit", r"MOST likely to be impaired",
        r"MOST likely to (?:result|undermine|reduce)", r"would MOST undermine",
        r"MOST likely consequence", r"MOST likely explanation", r"GREATEST",
    ]),
    ("evidence", [
        r"BEST evidence", r"BEST assurance", r"provides? the BEST", r"BEST demonstrates?",
        r"BEST supports? the reliability", r"MOST reliable form", r"BEST indicator",
        r"MOST appropriate conclusion", r"MOST appropriately conclude", r"BEST measures?",
        r"MOST useful for assessing", r"BEST source of assurance", r"BEST provides assurance",
        r"BEST validates?", r"STRONGEST basis",
    ]),
    ("definition", [
        r"BEST describes?", r"BEST distinguish", r"PRIMARY purpose", r"PRIMARY role",
        r"PRIMARY objective", r"PRIMARY difference", r"PRIMARY benefit", r"PRIMARY reason",
        r"MOST accurately", r"BEST characteriz", r"BEST understood", r"BEST represents?",
        r"BEST classified", r"BEST example", r"is BEST described", r"PRIMARILY because",
        r"should PRIMARILY", r"PRIMARILY:", r"BEST refers",
        r"PRIMARILY (?:ensure|determine|provide|address|serve|drive|refers|represent)",
    ]),
    ("control", [
        r"BEST address", r"BEST prevent", r"BEST control", r"MOST appropriate", r"BEST protect",
        r"BEST limits?", r"BEST mitigat", r"BEST ensures?", r"MOST important", r"BEST enables?",
        r"BEST supports?", r"BEST handled", r"recommendation is MOST", r"BEST be", r"should BEST",
        r"MOST effective", r"BEST determined", r"MOST directly driven", r"BEST structured",
        r"BEST assessed", r"BEST performed", r"MOST useful", r"BEST", r"MOST",
    ]),
]


def classify_stem(stem: str) -> Optional[str]:
    """Derive what a stem is asking for, or None when it cannot be told."""
    for name, patterns in _ASK_RULES:
        if any(re.search(p, stem) for p in patterns):
            return name
    return None


def ask_type(q: Question) -> Optional[str]:
    """An explicit `asks` field on the question always overrides the classifier."""
    explicit = (getattr(q, "asks", "") or "").strip().lower()
    if explicit in ASK_TYPES:
        return explicit
    return classify_stem(q.stem)


def classifiable(questions: Sequence[Question]) -> List[Question]:
    return [q for q in questions if ask_type(q) is not None]


# --------------------------------------------------------------------------
# separate log
# --------------------------------------------------------------------------

@dataclass
class GameAttempt:
    ts: str
    session: str
    game: str
    question_id: str
    cert: str
    domain: str
    section: str
    topic: str
    correct: bool
    detail: str = ""
    self_report: str = ""
    seconds: float = 0.0


def games_path(cert_results_path: str) -> str:
    """Sits beside attempts.jsonl but is a different file, on purpose."""
    return os.path.join(os.path.dirname(cert_results_path), "games.jsonl")


def append_game(path: str, attempt: GameAttempt) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(attempt), ensure_ascii=True) + "\n")


def load_games(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("question_id"):
                rows.append(row)
    return rows


# --------------------------------------------------------------------------
# shared plumbing
# --------------------------------------------------------------------------

def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(" ".join(str(text).split()), width=WIDTH,
                         initial_indent=indent, subsequent_indent=indent)


class QuitGame(Exception):
    pass


class BaseGame:
    name = "game"
    title = "GAME"

    def __init__(self, cert: str, games_file: str, out: Optional[TextIO] = None,
                 reader=input, rng: Optional[random.Random] = None,
                 now=time.time):
        self.cert = cert
        self.games_file = games_file
        self.session_id = uuid.uuid4().hex[:8]
        self.reader = reader
        self._out = out
        self.rng = rng or random.Random()
        self._now = now
        self.asked = 0
        self.right = 0
        self.started = now()

    def say(self, text: str = "") -> None:
        print(text, file=self._out)

    def prompt(self, message: str, valid: Sequence[str],
               allow_blank: bool = False) -> str:
        while True:
            try:
                raw = self.reader(message)
            except EOFError:
                raise QuitGame()
            if raw is None:
                raise QuitGame()
            value = raw.strip().lower()
            if value in ("q", "quit"):
                raise QuitGame()
            if allow_blank and value == "":
                return ""
            if value in valid:
                return value
            self.say("  Enter one of: %s" % ", ".join(valid))

    def log(self, q: Question, correct: bool, detail: str = "",
            self_report: str = "", seconds: float = 0.0) -> None:
        append_game(self.games_file, GameAttempt(
            ts=now_iso(), session=self.session_id, game=self.name,
            question_id=q.id, cert=self.cert.upper(), domain=q.domain,
            section=q.section, topic=q.topic, correct=correct,
            detail=detail, self_report=self_report, seconds=round(seconds, 1),
        ))

    def banner(self, total: int, subtitle: str) -> None:
        self.say(RULE)
        self.say("%s  -  %d question(s)" % (self.title, total))
        self.say(wrap(subtitle))
        self.say("Logged separately from your drill and exam stats.")
        self.say(RULE)

    def summary(self) -> None:
        self.say()
        self.say(RULE)
        if not self.asked:
            self.say("Nothing answered - nothing logged.")
        else:
            elapsed = self._now() - self.started
            per = elapsed / self.asked if self.asked else 0
            self.say("%s: %d/%d (%.0f%%)  |  %.0fs total, %.0fs per item"
                     % (self.title, self.right, self.asked,
                        100.0 * self.right / self.asked, elapsed, per))
        self.say(RULE)


# --------------------------------------------------------------------------
# Cold Read
# --------------------------------------------------------------------------

class ColdRead(BaseGame):
    name = "coldread"
    title = "COLD READ"

    def run(self, questions: Sequence[Question]) -> None:
        self.banner(len(questions),
                    "Options are hidden. Name what the question is asking for, "
                    "predict the answer, then check yourself.")
        try:
            for i, q in enumerate(questions, start=1):
                self._one(q, i, len(questions))
        except QuitGame:
            self.say()
            self.say("Stopped - everything answered so far was saved.")
        self.summary()

    def _one(self, q: Question, position: int, total: int) -> None:
        expected = ask_type(q)
        start = self._now()

        self.say()
        self.say(THIN)
        self.say("[%d/%d]  %s  %s" % (position, total, q.tag, q.topic))
        self.say(THIN)
        self.say(wrap(q.stem))
        self.say()
        self.say("What is this question asking for?")
        for n, key in enumerate(ASK_ORDER, start=1):
            label, gloss = ASK_TYPES[key]
            self.say("  %d  %-14s %s" % (n, label, gloss))
        self.say()

        choice = self.prompt("Your read [1-5, s skip, q quit]: ",
                             [str(n) for n in range(1, len(ASK_ORDER) + 1)] + ["s"])
        if choice == "s":
            return

        guess = ASK_ORDER[int(choice) - 1]
        correct = guess == expected
        self.asked += 1
        self.right += 1 if correct else 0

        self.say()
        if correct:
            self.say("  Right - this is a %s question." % ASK_TYPES[expected][0])
        else:
            self.say("  Not quite. You read it as %s; it is asking for %s."
                     % (ASK_TYPES[guess][0], ASK_TYPES[expected][0]))

        self.say()
        self.say(wrap("Now say the answer out loud, in your own words, before you "
                      "look. Press enter when you have committed to one."))
        self.prompt("", [], allow_blank=True)

        self.say()
        for key in OPTION_KEYS:
            marker = "*" if key == q.answer else " "
            body = wrap(q.options.get(key, ""), indent="      ").lstrip()
            self.say(" %s %s. %s" % (marker, key, body))
        self.say()
        self.say(wrap("Keyed answer %s. %s" % (q.answer, q.why_correct)))
        self.say()

        matched = self.prompt("Did your prediction match? [y yes, c close, n no]: ",
                              ["y", "c", "n"])
        self.log(q, correct, detail="read=%s expected=%s" % (guess, expected),
                 self_report=matched, seconds=self._now() - start)


# --------------------------------------------------------------------------
# Autopsy
# --------------------------------------------------------------------------

class Autopsy(BaseGame):
    name = "autopsy"
    title = "AUTOPSY"

    def run(self, questions: Sequence[Question]) -> None:
        self.banner(len(questions),
                    "The correct answer is given. Work out why each wrong option "
                    "is wrong by matching it to its explanation.")
        try:
            for i, q in enumerate(questions, start=1):
                self._one(q, i, len(questions))
        except QuitGame:
            self.say()
            self.say("Stopped - everything answered so far was saved.")
        self.summary()

    def _one(self, q: Question, position: int, total: int) -> None:
        distractors = [k for k in OPTION_KEYS if k != q.answer
                       and q.why_wrong.get(k, "").strip()]
        if len(distractors) < 2:
            return  # not enough explanations to make a matching puzzle

        start = self._now()
        labels = ["X", "Y", "Z"][:len(distractors)]
        shuffled = list(distractors)
        self.rng.shuffle(shuffled)
        label_for = {opt: labels[i] for i, opt in enumerate(shuffled)}

        self.say()
        self.say(THIN)
        self.say("[%d/%d]  %s  %s" % (position, total, q.tag, q.topic))
        self.say(THIN)
        self.say(wrap(q.stem))
        self.say()
        for key in OPTION_KEYS:
            marker = "*" if key == q.answer else " "
            body = wrap(q.options.get(key, ""), indent="      ").lstrip()
            self.say(" %s %s. %s" % (marker, key, body))
        self.say()
        self.say("* %s is correct. Below are the reasons the other options fail,"
                 % q.answer)
        self.say("  in scrambled order. Match each option to its reason.")
        self.say()
        for opt in shuffled:
            self.say(wrap("%s. %s" % (label_for[opt], q.why_wrong[opt]), indent="  "))
            self.say()

        answers: Dict[str, str] = {}
        for opt in distractors:
            pick = self.prompt("  Option %s -> [%s]: " % (opt, "/".join(labels)),
                               [lab.lower() for lab in labels])
            answers[opt] = pick.upper()

        hits = sum(1 for opt in distractors if answers.get(opt) == label_for[opt])
        correct = hits == len(distractors)
        self.asked += 1
        self.right += 1 if correct else 0

        self.say()
        for opt in distractors:
            got = answers.get(opt, "?")
            ok = got == label_for[opt]
            self.say("    %s -> %s   %s" % (opt, got,
                     "correct" if ok else "should be %s" % label_for[opt]))
        self.say("  %d of %d matched." % (hits, len(distractors)))

        self.log(q, correct,
                 detail="matched=%d/%d" % (hits, len(distractors)),
                 seconds=self._now() - start)


# --------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------

def pick(questions: Sequence[Question], count: int, game: str,
         rng: Optional[random.Random] = None) -> List[Question]:
    """Choose questions a given game can actually run on."""
    rng = rng or random.Random()
    pool = list(questions)
    if game == "coldread":
        pool = classifiable(pool)
    elif game == "autopsy":
        pool = [q for q in pool
                if len([k for k in OPTION_KEYS
                        if k != q.answer and q.why_wrong.get(k, "").strip()]) >= 2]
    rng.shuffle(pool)
    return pool[:count]
