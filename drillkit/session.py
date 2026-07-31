"""The interactive drill loop.

Output is deliberately plain ASCII so it renders correctly in cmd.exe,
PowerShell and Windows Terminal alike.
"""

from __future__ import annotations

import textwrap
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, TextIO

from .loader import OPTION_KEYS, Question
from .store import Attempt, append, normalise_confidence, now_iso

WIDTH = 78
RULE = "=" * WIDTH
THIN = "-" * WIDTH


def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(
        " ".join(str(text).split()),
        width=WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )


class QuitDrill(Exception):
    """Raised when the user asks to stop early."""


class Session:
    def __init__(self, cert: str, mode: str, results_file: str,
                 out: Optional[TextIO] = None, reader=input,
                 principle_notes: Optional[Dict[str, str]] = None):
        self.cert = cert
        self.mode = mode
        self.results_file = results_file
        # question id -> the decision rule that governs it, shown after the
        # explanation so the rule is learned alongside the answer.
        self.principle_notes = principle_notes or {}
        self.session_id = uuid.uuid4().hex[:8]
        self.reader = reader
        self._out = out
        self.asked = 0
        self.right = 0
        self.missed: List[Question] = []
        self.started = time.time()

    def say(self, text: str = "") -> None:
        print(text, file=self._out)

    # ------------------------------------------------------------------
    def ask(self, q: Question, position: int, total: int, reason: str = "") -> bool:
        self.say()
        self.say(RULE)
        header = "Q%d/%d  %s" % (position, total, q.tag)
        if q.topic:
            header += "  " + q.topic
        self.say(header)
        if reason:
            self.say("(%s)" % reason)
        self.say(THIN)
        self.say(wrap(q.stem))
        self.say()
        for key in OPTION_KEYS:
            body = wrap(q.options.get(key, ""), indent="     ").lstrip()
            self.say("  %s. %s" % (key, body))
        self.say()

        chosen, confidence = self._prompt()
        elapsed = self._elapsed

        correct = chosen == q.answer
        self.asked += 1
        self.right += 1 if correct else 0
        if not correct:
            self.missed.append(q)

        self._feedback(q, chosen, correct)
        self._log(q, chosen, correct, elapsed, confidence)
        return correct

    def _prompt(self) -> tuple:
        """Answer and confidence, together and before any feedback.

        Confidence taken *after* seeing the result would be hindsight, so both
        are collected in one entry. `B2` answers and rates in a single line;
        a bare `B` falls through to a second prompt. Line-based input means
        Enter is unavoidable here without raw terminal mode, which would break
        the injected reader the tests rely on and stop working over a pipe.
        """
        start = time.time()
        while True:
            try:
                raw = self.reader(
                    "Your answer + confidence [e.g. B2 | 1 guess 2 unsure 3 confident, q to stop]: ")
            except EOFError:
                raise QuitDrill()
            if raw is None:
                raise QuitDrill()
            value = raw.strip().upper()
            if value in ("Q", "QUIT", "EXIT"):
                raise QuitDrill()

            letter, rest = (value[:1], value[1:].strip()) if value else ("", "")
            if letter not in OPTION_KEYS:
                self.say("  Enter A, B, C, D - optionally with 1/2/3 - or q to stop.")
                continue

            confidence = normalise_confidence(rest) if rest else ""
            if rest and not confidence:
                self.say("  Confidence is 1 (guess), 2 (unsure) or 3 (confident).")
                continue
            if not confidence:
                confidence = self._prompt_confidence()
            self._elapsed = round(time.time() - start, 1)
            return letter, confidence

    def _prompt_confidence(self) -> str:
        """Mandatory second step when it was not given inline.

        Mandatory on purpose: an optional control gets skipped exactly when the
        learner is tired, which is when the data is most interesting.
        """
        while True:
            try:
                raw = self.reader("  How sure? [1 guess / 2 unsure / 3 confident]: ")
            except EOFError:
                raise QuitDrill()
            if raw is None:
                raise QuitDrill()
            value = normalise_confidence(raw.strip())
            if value:
                return value
            self.say("  Enter 1, 2 or 3.")

    def _feedback(self, q: Question, chosen: str, correct: bool) -> None:
        self.say()
        if correct:
            self.say(">> CORRECT (%s)" % q.answer)
        else:
            self.say(">> INCORRECT. You chose %s; the answer is %s." % (chosen, q.answer))
        self.say()
        self.say(wrap("Why %s is right: %s" % (q.answer, q.why_correct)))
        for key in OPTION_KEYS:
            if key == q.answer:
                continue
            reason = q.why_wrong.get(key, "")
            if reason:
                self.say(wrap("Why %s is wrong: %s" % (key, reason)))
        note = self.principle_notes.get(q.id)
        if note:
            self.say()
            self.say(wrap("RULE: %s" % note))
        self.say(THIN)

    def _log(self, q: Question, chosen: str, correct: bool, seconds: float,
             confidence: str = "") -> None:
        append(self.results_file, Attempt(
            ts=now_iso(),
            session=self.session_id,
            question_id=q.id,
            cert=self.cert.upper(),
            domain=q.domain,
            section=q.section,
            topic=q.topic,
            chosen=chosen,
            answer=q.answer,
            correct=correct,
            seconds=seconds,
            mode=self.mode,
            confidence=confidence,
        ))

    # ------------------------------------------------------------------
    def summary(self) -> None:
        self.say()
        self.say(RULE)
        if not self.asked:
            self.say("No questions answered - nothing logged.")
            self.say(RULE)
            return

        minutes = (time.time() - self.started) / 60.0
        pct = 100.0 * self.right / self.asked
        self.say("Session %s: %d/%d correct (%.0f%%) in %.1f min"
                 % (self.session_id, self.right, self.asked, pct, minutes))

        if self.missed:
            self.say()
            self.say("Bring these back next time:")
            topics: Dict[str, int] = {}
            for q in self.missed:
                topics[q.topic] = topics.get(q.topic, 0) + 1
            for topic, n in sorted(topics.items(), key=lambda kv: -kv[1]):
                self.say("  - %s (%d)" % (topic, n))
            self.say()
            self.say("They are already queued to reappear first in your next drill.")
        else:
            self.say("Clean sweep. Those questions move further out in the rotation.")
        self.say(RULE)


def run(questions: List[Question], cert: str, mode: str, results_file: str,
        reasons: Optional[Dict[str, str]] = None, out: Optional[TextIO] = None,
        reader=input, principle_notes: Optional[Dict[str, str]] = None,
        header: Optional[str] = None) -> Session:
    session = Session(cert, mode, results_file, out=out, reader=reader,
                      principle_notes=principle_notes)
    reasons = reasons or {}
    total = len(questions)

    session.say(RULE)
    session.say("%s drill - %d questions - mode: %s" % (cert.upper(), total, mode))
    if header:
        session.say(wrap(header))
    session.say("Answers are logged to %s" % results_file)
    session.say(RULE)

    try:
        for i, q in enumerate(questions, start=1):
            session.ask(q, i, total, reasons.get(q.id, ""))
    except QuitDrill:
        session.say()
        session.say("Stopped early - everything answered so far was saved.")

    session.summary()
    return session
