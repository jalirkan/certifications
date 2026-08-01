"""What to do in the next thirty minutes, and why.

This module assembles nothing new. Every number in it already exists somewhere
- the rule rollup, the scheduler's tiers, the dangerous quadrant, the coverage
projection, the difficulty spread - and the only thing added here is the
arithmetic that turns them into an ordered list of things to do, each carrying
the evidence that put it there.

**The rule this module exists to enforce:** a recommendation states its reason
in one line with numbers, or it does not appear. "Drill `evidence-quality` -
5 of 14 correct, 95% CI 14-61%, spans 4 domains" is a recommendation.
"Recommended for you" is a slot machine. `build()` refuses to emit the second
kind: anything that cannot cite a count goes to `suppressed` with the reason it
was withheld, which is information in its own right - it tells the learner what
they have not measured yet.

**Nothing here predicts anything.** No readiness score, no pass likelihood, no
countdown implying one. The coverage projection is pace arithmetic and is
labelled as such (see `calibration.projection`), and the estimated scaled score
does not appear on this surface at all.

**Measured and unresolved are kept apart.** Below `MIN_RANK_ATTEMPTS` there is
nothing to rank on and the item is withheld with a reason. Above it, an item is
*measured* only if its interval is narrow enough to support the claim - see
`_claimable` - and otherwise *unresolved*. Both are worth drilling; only one is
a statement about the learner. "You are weak at this" and "you have not tested
this" are different sentences and four answers supports only the second.

The split exists because ranking everything on one number gets this wrong. The
topic rollup ranks by lower confidence bound deliberately, so that under-tested
topics surface alongside genuinely weak ones - correct for a list you browse.
Applied to a thirty-minute budget it fails: a topic seen 13 times (13-58%)
outranks a rule measured over 89 (23-42%) purely by being uncertain, and the
budget goes to the noisiest signal in the profile. Measured deficits therefore
rank among themselves by *upper* bound - most confidently bad first - and
unresolved ones rank by lower bound, in a group below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from . import calibration, difficulty, principles as principles_mod, scheduler, stats
from .itemanalysis import wilson_interval
from .loader import Question
from .store import history_by_question, parse_ts

# Below this there is nothing to rank on; the item is withheld with a reason.
MIN_RANK_ATTEMPTS = 4

# A weakness may be *claimed* only when its interval is narrow enough to mean
# something. Width, not raw count, because that is what actually decides it:
# 4 of 13 is 13-58%, which is not a finding, while 28 of 89 is 23-42%, which
# is. A count threshold would have called both of those measured.
MAX_CLAIM_WIDTH = 0.35
MIN_CLAIM_ATTEMPTS = 8

# Confident answers needed before the dangerous quadrant is worth acting on.
# Matches calibration.MIN_LEVEL - the same evidence gate, so the two surfaces
# cannot disagree about whether there is enough data.
MIN_CONFIDENT = calibration.MIN_LEVEL

# Answers needed before pacing off the learner's own timing rather than a guess.
MIN_TIMED = 20

# Used only when the learner has no timing history of their own, and labelled
# as an assumption wherever it reaches a screen.
ASSUMED_SECONDS = 75.0

DEFAULT_MINUTES = 30

# How many of each kind may compete for the budget. A screen that lists every
# weak rule is a report, not a plan.
PER_KIND = 3

# Ordering groups. Rank within a group is a float; the group decides first.
#
# The point of the split: a lower confidence bound is the right way to *rank*
# comparable items, and the wrong way to compare a rule measured over 89
# answers against a topic seen 13 times. The thin item wins on lower bound
# purely by being uncertain, and would spend the budget on the noisiest signal
# in the profile. So measured deficits are ranked among themselves by their
# *upper* bound - "we are confident this is bad" - and unresolved ones are
# ranked among themselves by lower bound, below.
GROUP_REPAIR = 0      # known wrong: misses, confident-and-wrong, an open case
GROUP_MEASURED = 1    # enough answers that the ordering means something
GROUP_UNRESOLVED = 2  # tried, but too thinly to say whether it is a weakness
GROUP_NEW = 3         # never served, never played: not a deficit at all
GROUP_CONTEXT = 4     # pace and coverage: never leads the screen


def _claimable(correct: int, attempts: int) -> bool:
    """Is the interval tight enough to call this a weakness rather than a gap?"""
    if attempts < MIN_CLAIM_ATTEMPTS:
        return False
    low, high = wilson_interval(correct, attempts)
    return (high - low) <= MAX_CLAIM_WIDTH


@dataclass
class Recommendation:
    """One thing to do, and the numbers that put it there.

    `evidence` is not optional and is not decoration. If a caller cannot fill
    it with counts, the recommendation does not belong on the screen.
    """

    kind: str
    title: str
    evidence: str
    minutes: int
    action: Dict[str, Any] = field(default_factory=dict)
    detail: Dict[str, Any] = field(default_factory=dict)
    basis: str = "measured"        # "measured" | "unresolved"
    group: int = 1                 # see GROUP_* above; decides before rank
    rank: float = 0.0              # lower is more urgent, within the group

    @property
    def order(self):
        return (self.group, self.rank)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "evidence": self.evidence,
            "minutes": self.minutes,
            "action": self.action,
            "detail": self.detail,
            "basis": self.basis,
            "group": self.group,
        }


@dataclass
class Withheld:
    """Something that would have been recommended if there were evidence.

    Kept and returned rather than dropped: "you have not answered enough
    confident-rated questions to know whether you are overconfident" is more
    useful than silence, and it is the honest form of an empty screen.
    """

    kind: str
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "reason": self.reason}


def _pct(x: float) -> str:
    return "%d%%" % round(x * 100)


def _interval(correct: int, attempts: int) -> str:
    low, high = wilson_interval(correct, attempts)
    return "95%% CI %s-%s" % (_pct(low), _pct(high))


def seconds_per_question(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The learner's own median seconds per question, or a stated assumption.

    Median rather than mean: one interrupted question left open for an hour
    would otherwise set the pace for the whole plan.
    """
    timed = sorted(float(r.get("seconds") or 0.0) for r in rows
                   if float(r.get("seconds") or 0.0) > 0)
    if len(timed) >= MIN_TIMED:
        mid = len(timed) // 2
        median = timed[mid] if len(timed) % 2 else (timed[mid - 1] + timed[mid]) / 2.0
        return {"seconds": median, "measured": True, "n": len(timed)}
    return {"seconds": ASSUMED_SECONDS, "measured": False, "n": len(timed)}


def _minutes_for(count: int, pace: Dict[str, Any]) -> int:
    return max(1, int(round(count * float(pace["seconds"]) / 60.0)))


# --------------------------------------------------------------------------
# the sources
# --------------------------------------------------------------------------

def _rules(rules: Sequence[Dict[str, Any]], questions: Sequence[Question],
           rows: Sequence[Dict[str, Any]], pace: Dict[str, Any],
           out: List[Recommendation], held: List[Withheld]) -> None:
    """Weakest decision rules first - the axis that transfers across domains."""
    ranked = principles_mod.summarize(rules, questions, rows)
    usable = [s for s in ranked if s.attempts >= MIN_RANK_ATTEMPTS]
    if not usable:
        held.append(Withheld(
            "rule",
            "No decision rule has %d answers yet, which is the least that can "
            "be ranked. Drill anything and they will start to fill."
            % MIN_RANK_ATTEMPTS))
        return

    for stat in usable[:PER_KIND]:
        low, high = stat.interval
        measured = _claimable(stat.correct, stat.attempts)
        count = min(10, stat.questions_total)
        out.append(Recommendation(
            kind="rule",
            title="Drill %s" % stat.name,
            evidence="%d of %d correct, %s, spans %d domain%s"
                     % (stat.correct, stat.attempts,
                        _interval(stat.correct, stat.attempts),
                        len(stat.domains), "" if len(stat.domains) == 1 else "s"),
            minutes=_minutes_for(count, pace),
            action={"screen": "drill", "mode": "costumes",
                    "principle": stat.principle_id, "n": count},
            detail={"principle": stat.principle_id,
                    "attempts": stat.attempts, "correct": stat.correct,
                    "low": low, "high": high,
                    "domains": stat.domains,
                    "misapplication": stat.misapplication},
            basis="measured" if measured else "unresolved",
            group=GROUP_MEASURED if measured else GROUP_UNRESOLVED,
            # A rule spans domains by construction, so among equally-evidenced
            # items it is the one whose repair transfers furthest.
            rank=(high if measured else low) - 0.01,
        ))


def _due(questions: Sequence[Question], rows: Sequence[Dict[str, Any]],
         pace: Dict[str, Any], out: List[Recommendation],
         held: List[Withheld], now: Optional[datetime] = None) -> None:
    """The scheduler's own queue, split by why each question is due.

    Missed and unseen are different work and are not averaged into one number:
    revisiting a question you got wrong is repair, and a question never served
    is new ground.
    """
    now = now or datetime.now(timezone.utc)
    history = history_by_question(list(rows))
    progress = scheduler.build_progress(history)

    missed = unseen = 0
    for q in questions:
        tier = scheduler._tier(progress.get(q.id))
        if tier == scheduler.TIER_MISSED:
            missed += 1
        elif tier == scheduler.TIER_UNSEEN:
            unseen += 1

    if missed:
        count = min(10, missed)
        out.append(Recommendation(
            kind="due",
            title="Clear the questions you got wrong",
            evidence="%d question%s answered incorrectly and not revisited "
                     "since" % (missed, "" if missed == 1 else "s"),
            minutes=_minutes_for(count, pace),
            action={"screen": "drill", "mode": "smart", "n": count},
            detail={"missed": missed, "unseen": unseen},
            group=GROUP_REPAIR,
            rank=0.0,
        ))
    if unseen:
        count = min(10, unseen)
        out.append(Recommendation(
            kind="unseen",
            title="Cover new ground",
            evidence="%d of %d question%s never served"
                     % (unseen, len(questions), "" if unseen == 1 else "s"),
            minutes=_minutes_for(count, pace),
            action={"screen": "drill", "mode": "new", "n": count},
            detail={"unseen": unseen, "bank": len(questions)},
            group=GROUP_NEW,
            rank=1.5,   # new ground only once the known gaps are spoken for
        ))
    if not missed and not unseen:
        held.append(Withheld(
            "due", "Nothing is waiting: every question has been served and "
                   "none is currently marked wrong."))


def _dangerous(rows: Sequence[Dict[str, Any]], by_id: Dict[str, Question],
               rule_for: Dict[str, str], pace: Dict[str, Any],
               out: List[Recommendation], held: List[Withheld]) -> None:
    """Confident and wrong: the misses no other report can see."""
    confident = [r for r in rows if r.get("confidence") == "confident"]
    if len(confident) < MIN_CONFIDENT:
        held.append(Withheld(
            "dangerous",
            "%d of %d answers carry a confidence rating; %d confident answers "
            "are needed before overconfidence can be told from noise."
            % (len([r for r in rows if r.get("confidence")]), len(rows),
               MIN_CONFIDENT)))
        return

    hits = calibration.dangerous(rows, by_id, rule_for, limit=200)
    if not hits:
        held.append(Withheld(
            "dangerous",
            "None of your %d confident answers was wrong." % len(confident)))
        return

    wrong = len(hits)
    count = min(10, wrong)
    out.append(Recommendation(
        kind="dangerous",
        title="Review what you were sure about and got wrong",
        evidence="%d of %d confident answers were wrong (%s)"
                 % (wrong, len(confident),
                    _interval(wrong, len(confident))),
        minutes=max(4, _minutes_for(count, pace)),
        action={"screen": "calibration"},
        detail={"wrong": wrong, "confident": len(confident),
                "questions": [h.get("question_id") for h in hits[:count]]},
        group=GROUP_REPAIR,
        rank=-1.0,  # nothing else in the system can see these
    ))


def _topics(rows: Sequence[Dict[str, Any]], pace: Dict[str, Any],
            out: List[Recommendation], held: List[Withheld]) -> None:
    """Weakest topics by lower bound - what to study, as opposed to how."""
    buckets = [b for b in stats.by_topic(list(rows))
               if b.attempts >= MIN_RANK_ATTEMPTS]
    if not buckets:
        held.append(Withheld(
            "topic",
            "No topic has %d answers yet." % MIN_RANK_ATTEMPTS))
        return

    ranked = sorted(buckets,
                    key=lambda b: wilson_interval(b.correct, b.attempts)[0])
    for bucket in ranked[:PER_KIND]:
        low, high = wilson_interval(bucket.correct, bucket.attempts)
        measured = _claimable(bucket.correct, bucket.attempts)
        # by_topic labels as "D5A | Topic name"; the filter wants the topic.
        topic = bucket.label.split("|", 1)[-1].strip()
        out.append(Recommendation(
            kind="topic",
            title="Drill %s" % topic,
            evidence="%d of %d correct, %s"
                     % (bucket.correct, bucket.attempts,
                        _interval(bucket.correct, bucket.attempts)),
            minutes=_minutes_for(10, pace),
            action={"screen": "drill", "topic": topic, "n": 10},
            detail={"topic": topic, "label": bucket.label,
                    "attempts": bucket.attempts,
                    "correct": bucket.correct, "low": low, "high": high},
            basis="measured" if measured else "unresolved",
            group=GROUP_MEASURED if measured else GROUP_UNRESOLVED,
            rank=high if measured else low,
        ))


def _cases(case_rows: Sequence[Dict[str, Any]],
           out: List[Recommendation], held: List[Withheld]) -> None:
    """Cases are the only surface that tests sequence rather than recall."""
    unplayed = [c for c in case_rows if not c.get("attempts")]
    resumable = [c for c in case_rows if c.get("open_session")]

    if resumable:
        case = resumable[0]
        out.append(Recommendation(
            kind="case",
            title="Finish %s" % case.get("title", case.get("id", "")),
            evidence="%d decision%s in, not yet finished"
                     % (case.get("open_decisions", 0),
                        "" if case.get("open_decisions") == 1 else "s"),
            minutes=int(case.get("minutes") or 12),
            action={"screen": "case", "session": case.get("open_session")},
            detail={"case": case.get("id")},
            group=GROUP_REPAIR,
            rank=-0.5,
        ))
    if unplayed:
        case = unplayed[0]
        out.append(Recommendation(
            kind="case",
            title="Play %s" % case.get("title", case.get("id", "")),
            evidence="%d of %d case%s never played"
                     % (len(unplayed), len(case_rows),
                        "" if len(case_rows) == 1 else "s"),
            minutes=int(case.get("minutes") or 12),
            action={"screen": "case", "case_id": case.get("id")},
            detail={"case": case.get("id"), "unplayed": len(unplayed)},
            group=GROUP_NEW,
            rank=1.6,
        ))
    if case_rows and not unplayed and not resumable:
        held.append(Withheld(
            "case", "All %d cases have been played through." % len(case_rows))
        )


def _bands(questions: Sequence[Question], out: List[Recommendation],
           held: List[Withheld]) -> None:
    """Which difficulty bands exist to be drilled, and which are empty.

    An empty band is a fact about the bank, not about the learner, so it is
    reported as a limit rather than as something to do. Without this the Drill
    screen offers a filter that silently returns nothing.
    """
    spread = difficulty.counts(questions)
    empty = [name for name, n in spread.items() if not n]
    if empty:
        held.append(Withheld(
            "band",
            "No questions are tagged %s, so that filter has nothing to serve."
            % ", ".join(empty)))


def _coverage(rows: Sequence[Dict[str, Any]], questions: Sequence[Question],
              target: Optional[Any], out: List[Recommendation],
              held: List[Withheld]) -> None:
    """Pace arithmetic over the log. Deliberately not a forecast."""
    proj = calibration.projection(list(rows), list(questions), target=target)
    if not proj["enough"]:
        held.append(Withheld(
            "coverage",
            "%d answers in the last %d days; %d are needed before a pace is "
            "worth quoting."
            % (proj["recent_attempts"], proj["window_days"],
               proj["min_pace_attempts"])))
        return

    out.append(Recommendation(
        kind="coverage",
        title="Keep the pace up",
        evidence="%d of %d questions seen %d times; %d answers to go at "
                 "%.1f a day"
                 % (proj["covered"], proj["questions"], proj["coverage_target"],
                    proj["attempts_remaining"], proj["pace_per_day"]),
        minutes=_minutes_for(int(proj["pace_per_day"]) or 1, {"seconds": 75.0}),
        action={"screen": "calibration"},
        detail=proj,
        group=GROUP_CONTEXT,
        rank=0.0,
    ))


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------

def require_evidence(recommendations: Sequence[Recommendation]) -> None:
    """The invariant this module exists for.

    A recommendation whose reason cites no count is a slogan. Raising here
    rather than filtering is deliberate: a slogan reaching this point is a bug
    in whichever source built it, and silently dropping it would hide that the
    screen had quietly stopped saying why.
    """
    for rec in recommendations:
        if not any(ch.isdigit() for ch in rec.evidence):
            raise ValueError(
                "recommendation %r has no numbers in its evidence: %r"
                % (rec.title, rec.evidence))


def plan(recommendations: Sequence[Recommendation], minutes: int
         ) -> List[Recommendation]:
    """Fill the budget in rank order, skipping anything that will not fit.

    Greedy on purpose. A knapsack solution would reorder the list to pack it
    tighter, which would quietly demote the most urgent item to save two
    minutes - the wrong trade for the one screen whose job is to say what
    matters most.
    """
    left = minutes
    out: List[Recommendation] = []
    for rec in sorted(recommendations, key=lambda r: r.order):
        if rec.minutes <= left:
            out.append(rec)
            left -= rec.minutes
    return out


def build(questions: Sequence[Question], rows: Sequence[Dict[str, Any]],
          rules: Sequence[Dict[str, Any]],
          case_rows: Sequence[Dict[str, Any]] = (),
          minutes: int = DEFAULT_MINUTES,
          target: Optional[Any] = None) -> Dict[str, Any]:
    """Everything worth doing next, ordered, with what was withheld and why."""
    rows = list(rows)
    pace = seconds_per_question(rows)
    by_id = {q.id: q for q in questions}
    rule_for = calibration.rule_index(list(rules))

    found: List[Recommendation] = []
    held: List[Withheld] = []

    _due(questions, rows, pace, found, held)
    _dangerous(rows, by_id, rule_for, pace, found, held)
    _rules(rules, questions, rows, pace, found, held)
    _topics(rows, pace, found, held)
    _cases(case_rows, found, held)
    _coverage(rows, questions, target, found, held)
    _bands(questions, found, held)

    require_evidence(found)
    chosen = plan(found, minutes)
    chosen_ids = {id(r) for r in chosen}

    return {
        "minutes": minutes,
        "pace": pace,
        "recommendations": [r.as_dict() for r in chosen],
        "also": [r.as_dict() for r in sorted(found, key=lambda r: r.order)
                 if id(r) not in chosen_ids],
        "withheld": [w.as_dict() for w in held],
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
