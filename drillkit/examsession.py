"""Interactive runner and report renderer for timed mock exams.

Kept separate from exam.py so that the state machine, sampling and scoring stay
testable without any terminal involvement.
"""

from __future__ import annotations

import textwrap
import time
from typing import Dict, List, Optional, Sequence, TextIO

from . import exam as exam_mod
from .exam import Clock, ExamResult, ExamState, format_hms, format_ms
from .loader import OPTION_KEYS, Outline, Question
from .store import Attempt, append, normalise_confidence, now_iso

WIDTH = 78
RULE = "=" * WIDTH
THIN = "-" * WIDTH

HELP = """
  A B C D   answer the current question and move on
  n / p     next / previous question
  g N       go to question number N
  f         flag or unflag this question for review
  r         list flagged and unanswered questions
  s         progress summary
  e         end the exam and score it
  x         save and exit, resume later with --resume
  ?         this help
""".rstrip()


def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(
        " ".join(str(text).split()), width=WIDTH,
        initial_indent=indent, subsequent_indent=indent,
    )


class ExamRunner:
    def __init__(self, state: ExamState, questions: Sequence[Question],
                 outline: Outline, results_path: str,
                 out: Optional[TextIO] = None, reader=input, now=time.time):
        self.state = state
        self.outline = outline
        self.results_path = results_path
        self.lookup = {q.id: q for q in questions}
        self.order = [self.lookup[qid] for qid in state.question_ids
                      if qid in self.lookup]
        self._out = out
        self.reader = reader
        self.clock = Clock(now=now)
        self._question_entered: Optional[float] = None
        self._now = now
        # Time carried in from previous sittings. Held separately from
        # state.elapsed_seconds because _persist writes the running total back
        # to the state; adding the live sitting to an already-updated total
        # would count the current sitting twice on every save.
        self._base_elapsed = float(state.elapsed_seconds)

    # ------------------------------------------------------------------
    def say(self, text: str = "") -> None:
        print(text, file=self._out)

    @property
    def current(self) -> Question:
        return self.order[self.state.position]

    def elapsed(self) -> float:
        return self._base_elapsed + self.clock.sitting_seconds()

    def remaining(self) -> float:
        return max(0.0, self.state.duration_seconds - self.elapsed())

    def _commit_time_on_question(self) -> None:
        """Accumulate wall time spent on the question we are leaving."""
        if self._question_entered is None:
            return
        spent = max(0.0, self._now() - self._question_entered)
        qid = self.current.id
        prior = self.state.seconds_per_question.get(qid, 0.0)
        self.state.seconds_per_question[qid] = round(prior + spent, 1)
        self._question_entered = None

    def _stop_clock(self) -> None:
        """Close the sitting, folding its duration into the carried-forward base."""
        self._base_elapsed += self.clock.stop()

    def _persist(self) -> None:
        self.state.elapsed_seconds = round(self.elapsed(), 1)
        exam_mod.save(self.state, self.results_path)

    # ------------------------------------------------------------------
    def run(self) -> Optional[ExamResult]:
        """Returns a result if the exam was submitted, None if saved for later."""
        self.state.sittings += 1
        self._base_elapsed = float(self.state.elapsed_seconds)
        self.clock.start()

        self._banner()

        while True:
            if self.remaining() <= 0:
                self._commit_time_on_question()
                self.say()
                self.say("TIME EXPIRED - submitting automatically.")
                return self._submit()

            self._render_question()
            self._question_entered = self._now()

            try:
                raw = self.reader(
                    "Command (A-D[1-3], n/p, g N, f, r, s, e, x, ?): ")
            except EOFError:
                raw = "x"
            if raw is None:
                raw = "x"

            outcome = self._handle(raw.strip())
            if outcome == "submit":
                return self._submit()
            if outcome == "exit":
                self._commit_time_on_question()
                self._stop_clock()
                self._persist()
                self.say()
                self.say("Saved. Resume with:  python drill.py exam --resume %s"
                         % self.state.exam_id)
                self.say("The clock is stopped; %s of exam time remains."
                         % format_hms(self.remaining()))
                return None

    # ------------------------------------------------------------------
    def _banner(self) -> None:
        s = self.state
        self.say(RULE)
        self.say("%s MOCK EXAM   id %s   sitting %d" % (s.cert, s.exam_id, s.sittings))
        self.say("%d questions | %s total | no feedback until you submit"
                 % (s.total, format_hms(s.duration_seconds)))
        if s.shortfall:
            gaps = ", ".join("D%s short %d" % (d, n)
                             for d, n in sorted(s.shortfall.items()) if n)
            if gaps:
                self.say("Blueprint not fully met (%s) - bank needs more questions."
                         % gaps)
        self.say("Type ? for commands.")
        self.say(RULE)

    def _render_question(self) -> None:
        q = self.current
        s = self.state
        self.say()
        self.say(THIN)
        status = "[Q %d/%d]   %s left   answered %d   flagged %d" % (
            s.position + 1, s.total, format_hms(self.remaining()),
            s.answered, len(s.flagged),
        )
        self.say(status)
        self.say(THIN)
        self.say(wrap(q.stem))
        self.say()
        for key in OPTION_KEYS:
            marker = ">" if s.answers.get(q.id) == key else " "
            body = wrap(q.options.get(key, ""), indent="      ").lstrip()
            self.say(" %s %s. %s" % (marker, key, body))
        self.say()
        notes = []
        if q.id in s.answers:
            notes.append("answered %s" % s.answers[q.id])
        if q.id in s.flagged:
            notes.append("FLAGGED")
        if notes:
            self.say("  (%s)" % ", ".join(notes))

    # ------------------------------------------------------------------
    def _handle(self, raw: str) -> Optional[str]:
        s = self.state
        value = raw.upper()

        # "B" answers; "B2" answers and rates confidence in one entry. No
        # feedback is given during an exam anyway, so confidence here cannot be
        # contaminated by knowing the result - but it still has to be recorded
        # with the answer, because it cannot be recovered afterwards.
        if value[:1] in OPTION_KEYS and (len(value) == 1 or
                                         normalise_confidence(value[1:])):
            self._commit_time_on_question()
            qid = self.current.id
            s.answers[qid] = value[:1]
            confidence = normalise_confidence(value[1:]) if len(value) > 1 else ""
            if confidence:
                s.confidence[qid] = confidence
            else:
                s.confidence.pop(qid, None)
            self._advance(1)
            self._persist()
            return None

        if value in ("N", ""):
            self._commit_time_on_question()
            self._advance(1)
            self._persist()
            return None

        if value == "P":
            self._commit_time_on_question()
            self._advance(-1)
            self._persist()
            return None

        if value == "F":
            self._commit_time_on_question()
            qid = self.current.id
            if qid in s.flagged:
                s.flagged.remove(qid)
            else:
                s.flagged.append(qid)
            self._persist()
            return None

        if value.startswith("G"):
            self._commit_time_on_question()
            self._goto(value[1:].strip())
            self._persist()
            return None

        if value == "R":
            self._commit_time_on_question()
            self._review_list()
            return None

        if value == "S":
            self._commit_time_on_question()
            self._summary()
            return None

        if value == "E":
            self._commit_time_on_question()
            return self._confirm_submit()

        if value == "X":
            return "exit"

        if value == "?":
            self.say(HELP)
            return None

        self.say("  Unrecognized command. Type ? for the list.")
        return None

    def _advance(self, step: int) -> None:
        self.state.position = max(0, min(self.state.total - 1,
                                         self.state.position + step))

    def _goto(self, token: str) -> None:
        try:
            target = int(token)
        except ValueError:
            self.say("  Use 'g' followed by a question number, e.g. g 42.")
            return
        if not 1 <= target <= self.state.total:
            self.say("  Question number must be between 1 and %d." % self.state.total)
            return
        self.state.position = target - 1

    def _review_list(self) -> None:
        s = self.state
        flagged = [(i + 1, qid) for i, qid in enumerate(s.question_ids)
                   if qid in s.flagged]
        blank = [(i + 1, qid) for i, qid in enumerate(s.question_ids)
                 if qid not in s.answers]

        self.say()
        self.say("FLAGGED (%d): %s" % (
            len(flagged), ", ".join(str(n) for n, _ in flagged) or "none"))
        self.say("UNANSWERED (%d): %s" % (
            len(blank), ", ".join(str(n) for n, _ in blank) or "none"))
        self.say("Jump with 'g <number>'.")

    def _summary(self) -> None:
        s = self.state
        used = self.elapsed()
        pace = used / max(1, s.answered)
        left = self.remaining()
        todo = s.total - s.answered
        self.say()
        self.say("Answered %d of %d, %d flagged." % (s.answered, s.total, len(s.flagged)))
        self.say("Elapsed %s, remaining %s." % (format_hms(used), format_hms(left)))
        if s.answered:
            self.say("Averaging %s per answered question." % format_ms(pace))
        if todo and left > 0:
            self.say("Budget for the rest: %s each." % format_ms(left / todo))
        elif todo:
            self.say("No time left for the remaining %d questions." % todo)

    def _confirm_submit(self) -> Optional[str]:
        s = self.state
        blank = s.total - s.answered
        if blank:
            self.say()
            self.say("%d question(s) are still unanswered and will score as wrong."
                     % blank)
        try:
            answer = self.reader("Submit and score the exam? [y/N]: ")
        except EOFError:
            answer = "y"
        if (answer or "").strip().lower() in ("y", "yes"):
            return "submit"
        self.say("  Not submitted.")
        return None

    # ------------------------------------------------------------------
    def _submit(self) -> ExamResult:
        self._stop_clock()
        self.state.submitted = True
        self.state.submitted_at = now_iso()
        self._persist()
        self._log_attempts()
        return exam_mod.score(self.state, list(self.lookup.values()), self.outline)

    def _log_attempts(self) -> None:
        """Feed answered exam questions into the main attempt log.

        Tagged mode='exam' so stats and item analysis include them, and so the
        drill scheduler knows to bring back what you missed under exam pressure.
        """
        ts = now_iso()
        for qid, chosen in self.state.answers.items():
            q = self.lookup.get(qid)
            if q is None:
                continue
            append(self.results_path, Attempt(
                ts=ts, session="exam-%s" % self.state.exam_id, question_id=q.id,
                cert=self.state.cert, domain=q.domain, section=q.section,
                topic=q.topic, chosen=chosen, answer=q.answer,
                correct=chosen == q.answer,
                seconds=self.state.seconds_per_question.get(q.id, 0.0),
                mode="exam",
                confidence=self.state.confidence.get(q.id, ""),
            ))


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def _bar(fraction: float, width: int = 12) -> str:
    filled = int(round(fraction * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def render_report(result: ExamResult, outline: Outline,
                  out: Optional[TextIO] = None) -> None:
    def say(text: str = "") -> None:
        print(text, file=out)

    say()
    say(RULE)
    say("EXAM RESULT   id %s" % result.exam_id)
    say(RULE)
    say("Raw score      : %d/%d correct (%.1f%%)"
        % (result.correct, result.total, result.raw_fraction * 100))
    if result.unanswered:
        say("Unanswered     : %d (scored as incorrect)" % result.unanswered)
    say("Time used      : %s of %s"
        % (format_hms(result.elapsed_seconds), format_hms(result.duration_seconds)))
    if result.total:
        say("Pace           : %s per question"
            % format_ms(result.elapsed_seconds / result.total))
    say()
    say("Estimated scaled score: %d  (%s)"
        % (result.scaled_estimate,
           "above the 450 pass mark" if result.passed_estimate else "below the 450 pass mark"))
    say(wrap("This is an approximation, not ISACA's number. ISACA scales raw "
             "scores psychometrically using a process it does not publish, and "
             "the raw threshold shifts between exam forms. Treat anything within "
             "roughly 50 points of 450 as too close to call."))

    say()
    say("BY DOMAIN")
    say(THIN)
    say("  %-36s %-14s %4s %7s %5s" % ("Domain", "Accuracy", "", "Score", "Wt"))
    for d in result.by_domain:
        label = "D%s %s" % (d.domain, d.name)
        weight = "%d%%" % d.weight if d.weight else "-"
        say("  %-36s %s %4.0f%% %7s %5s" % (
            label[:36], _bar(d.accuracy), d.accuracy * 100,
            "%d/%d" % (d.correct, d.asked), weight))

    weak = [d for d in result.by_domain if d.asked >= 5 and d.accuracy < 0.65]
    if weak:
        say()
        say("Where the lost marks actually are (accuracy gap x domain weight):")
        for d in sorted(weak, key=lambda x: -((x.weight or 0) * (1 - x.accuracy))):
            cost = (d.weight or 0) * (1 - d.accuracy)
            say("  D%s %-30s %3.0f%%  ~%.1f%% of the exam"
                % (d.domain, d.name[:30], d.accuracy * 100, cost))

    if result.guessed_right:
        say()
        say("Flagged but answered correctly (%d) - you were unsure and got lucky:"
            % len(result.guessed_right))
        for q in result.guessed_right[:10]:
            say("  %-16s %s" % (q.id, q.topic[:52]))

    if result.slowest and result.slowest[0][1] > 0:
        say()
        say("SLOWEST QUESTIONS")
        say(THIN)
        for q, seconds in result.slowest[:5]:
            if seconds <= 0:
                continue
            say("  %-16s %6s  %s" % (q.id, format_ms(seconds), q.topic[:44]))

    say()
    say("%d question(s) missed. Review them with:" % len(result.missed))
    say("    python drill.py exam --review %s" % result.exam_id)
    say(RULE)


def render_review(result: ExamResult, state: ExamState,
                  out: Optional[TextIO] = None, reader=input,
                  paginate: bool = True) -> None:
    """Walk the missed questions with full explanations."""
    def say(text: str = "") -> None:
        print(text, file=out)

    if not result.missed:
        say("Nothing missed on exam %s." % result.exam_id)
        return

    say(RULE)
    say("REVIEW - %d missed question(s) from exam %s"
        % (len(result.missed), result.exam_id))
    say(RULE)

    for i, q in enumerate(result.missed, start=1):
        chosen = state.answers.get(q.id)
        say()
        say(THIN)
        say("%d/%d  %s  %s" % (i, len(result.missed), q.tag, q.topic))
        say(THIN)
        say(wrap(q.stem))
        say()
        for key in OPTION_KEYS:
            mark = " "
            if key == q.answer:
                mark = "*"
            elif key == chosen:
                mark = "x"
            body = wrap(q.options.get(key, ""), indent="      ").lstrip()
            say(" %s %s. %s" % (mark, key, body))
        say()
        if chosen is None:
            say("You left this blank. Correct answer: %s" % q.answer)
        else:
            say("You chose %s. Correct answer: %s" % (chosen, q.answer))
        say()
        say(wrap("Why %s is right: %s" % (q.answer, q.why_correct)))
        for key in OPTION_KEYS:
            if key == q.answer:
                continue
            reason = q.why_wrong.get(key, "")
            if reason:
                say(wrap("Why %s is wrong: %s" % (key, reason)))

        if paginate and i < len(result.missed):
            try:
                more = reader("[enter for next, q to stop] ")
            except EOFError:
                return
            if (more or "").strip().lower() == "q":
                return

    say()
    say(RULE)
