"""Selecting on authored difficulty, and being honest about what that is.

The `difficulty` field has been on every question since the bank was written and
has never selected anything. This module makes it selectable. It does not make
it *trustworthy*: the labels are one author's judgement, roughly 70% of the bank
carries the default value, and nothing has ever compared them against how the
questions actually behave. Every surface that filters on them has to say so, and
`CAVEAT` below is the sentence they all use.

Three decisions shape this module.

**Filtering is strict.** Asking for `hard` serves hard questions only. It is
never topped up from medium, because a session that quietly mixes bands is
lying about what it is, and because the thinness of these labels should be
visible rather than papered over. There are 51 hard questions in a bank of 346,
and a learner is entitled to see that.

**Short and empty results are the normal case, not the edge case.** Of the 180
topic-by-difficulty combinations, 36 are empty and another 83 hold one or two
questions. Asking for 20 and receiving 7 has to be stated up front, with the
reason, rather than discovered part-way through a session.

**The ramp reorders; it does not re-select.** `scheduler.select` picks the
session exactly as it does today, and the ramp then sorts what it picked easy to
hard. The alternative - drawing a quota per band - is a truer ramp but it
changes what gets served, which means overriding the spaced-repetition queue and
exhausting 51 hard questions quickly. Reordering keeps the scheduler in charge
and still gives a gentle start. The honest limitation is that a set which
happens to be all one band produces no ramp that day, and `ramp_spread()` exists
so a caller can say that out loud.

Nothing here modifies the scheduler. Filtering happens to the pool *before*
selection, so spaced repetition still orders whatever survives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from . import scheduler
from .loader import DIFFICULTIES, Question

RAMP = "ramp"
CHOICES = DIFFICULTIES + (RAMP,)

# The one sentence every difficulty surface carries. These labels were assigned
# by the person who wrote the questions and have never been checked against
# results; presenting them as measured would be the same mistake as presenting
# the scaled exam estimate as a prediction.
CAVEAT = "Author-assigned, not yet checked against your results"

# Order matters: the ramp walks it left to right.
ORDER = {name: index for index, name in enumerate(DIFFICULTIES)}


def normalise(value: object) -> str:
    """Accept a level or `ramp`; anything else is empty, meaning no filter."""
    text = str(value or "").strip().lower()
    return text if text in CHOICES else ""


def is_filter(value: str) -> bool:
    """True when this selection actually narrows the pool.

    `ramp` does not: it reorders whatever the scheduler picked, so the pool it
    is given must stay whole.
    """
    return normalise(value) in DIFFICULTIES


def filter_pool(questions: Sequence[Question], difficulty: str) -> List[Question]:
    """Strict. No top-up from an adjacent band, ever."""
    level = normalise(difficulty)
    if level not in DIFFICULTIES:
        return list(questions)
    return [q for q in questions if q.difficulty == level]


def counts(questions: Sequence[Question]) -> Dict[str, int]:
    out = {name: 0 for name in DIFFICULTIES}
    for q in questions:
        if q.difficulty in out:
            out[q.difficulty] += 1
    return out


def ramp_order(questions: Sequence[Question]) -> List[Question]:
    """Sort easy to hard, stable, so the scheduler's order survives inside bands.

    Stability is the point: within a band the questions stay in the order
    spaced repetition chose, so the ramp changes the sequence of the session
    without overriding its priorities.
    """
    return sorted(questions, key=lambda q: ORDER.get(q.difficulty, len(ORDER)))


def ramp_spread(questions: Sequence[Question]) -> int:
    """How many distinct bands this set spans. One means there is no ramp."""
    return len({q.difficulty for q in questions if q.difficulty in ORDER})


# --------------------------------------------------------------------------
# what the learner is told before, and after
# --------------------------------------------------------------------------

@dataclass
class Availability:
    """What a filter will actually yield, computed before the session starts."""
    difficulty: str
    requested: int
    pool_total: int          # questions matching the other filters, any difficulty
    matching: int            # ...and this difficulty
    available: int           # what will actually be served
    counts: Dict[str, int]   # the whole spread, so the learner can pick another band
    due_suppressed: int = 0  # due questions this filter excluded

    @property
    def short(self) -> bool:
        return self.available < self.requested

    @property
    def empty(self) -> bool:
        return self.available == 0

    def as_dict(self) -> Dict[str, object]:
        return {
            "difficulty": self.difficulty,
            "requested": self.requested,
            "pool_total": self.pool_total,
            "matching": self.matching,
            "available": self.available,
            "counts": dict(self.counts),
            "due_suppressed": self.due_suppressed,
            "short": self.short,
            "empty": self.empty,
            "caveat": CAVEAT,
            "message": self.message(),
        }

    def message(self) -> str:
        """The sentence shown before the session starts. Plain, and specific."""
        level = self.difficulty
        if not is_filter(level):
            if level == RAMP:
                return ("Ramp orders the questions the scheduler already chose, "
                        "easiest first. It does not change which are served.")
            return ""
        if self.empty:
            if self.pool_total == 0:
                return "Nothing matches those filters at all."
            return ("No %s questions match your other filters. That combination "
                    "holds %d question(s), none of them %s."
                    % (level, self.pool_total, level))
        if self.short:
            return ("Only %d %s question(s) match, so the session will be %d "
                    "rather than %d. Strict filtering: nothing is topped up "
                    "from another band." % (self.available, level,
                                            self.available, self.requested))
        return "%d %s questions available." % (self.matching, level)


def _due_ids(questions: Sequence[Question],
             history: Dict[str, List[Dict]],
             now: Optional[datetime] = None) -> set:
    """Questions the scheduler would consider due right now.

    Mirrors the tiers `scheduler.select` uses in `due` mode rather than
    reimplementing the spacing rule: anything missed or unseen is due, and a
    spaced question is due once its interval has elapsed.
    """
    now = now or datetime.now(timezone.utc)
    progress = scheduler.build_progress(history)
    due = set()
    for q in questions:
        p = progress.get(q.id)
        if p is None or p.last_correct is False or p.attempts == 0:
            due.add(q.id)
        elif p.due_ratio(now) >= 1.0:
            due.add(q.id)
    return due


def availability(pool: Sequence[Question], difficulty: str, requested: int,
                 history: Optional[Dict[str, List[Dict]]] = None,
                 now: Optional[datetime] = None) -> Availability:
    """Everything the learner should know before committing to the session."""
    level = normalise(difficulty)
    filtered = filter_pool(pool, level)
    matching = len(filtered) if is_filter(level) else len(pool)

    suppressed = 0
    if is_filter(level) and history:
        # Due questions that this filter removed. A learner should not be able
        # to skip their due queue without being told they did.
        kept = {q.id for q in filtered}
        suppressed = sum(1 for qid in _due_ids(pool, history, now)
                         if qid not in kept)

    return Availability(
        difficulty=level,
        requested=max(0, int(requested)),
        pool_total=len(pool),
        matching=matching,
        available=min(matching, max(0, int(requested))),
        counts=counts(pool),
        due_suppressed=suppressed,
    )


def apply(pool: Sequence[Question], difficulty: str) -> List[Question]:
    """The pool the scheduler should be given. Ramp leaves it whole."""
    return filter_pool(pool, difficulty) if is_filter(difficulty) else list(pool)


def present(selected: Sequence[Question], difficulty: str) -> List[Question]:
    """The order the session should run in, after the scheduler has chosen."""
    return ramp_order(selected) if normalise(difficulty) == RAMP else list(selected)
