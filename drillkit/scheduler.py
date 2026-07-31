"""Spaced-repetition-lite question selection.

The rule of thumb: anything you just missed comes back fast, anything you have
never seen comes next, and anything you keep getting right drifts further out
on a Leitner-style ladder. Lifetime accuracy is a tiebreaker throughout, so a
question you have missed three times does not disappear just because you
happened to get it right once.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from .loader import Question
from .store import parse_ts

# Days to wait after n consecutive correct answers. Index = streak length.
INTERVALS_DAYS: Sequence[float] = (0.0, 1.0, 3.0, 7.0, 16.0, 35.0)

TIER_MISSED = 0    # got it wrong last time -> highest urgency
TIER_UNSEEN = 1    # never served
TIER_SPACED = 2    # answered correctly last time, waiting out its interval


@dataclass
class Progress:
    question_id: str
    attempts: int = 0
    correct: int = 0
    streak: int = 0
    last_correct: Optional[bool] = None
    last_seen: Optional[datetime] = None

    @property
    def accuracy(self) -> float:
        return self.correct / self.attempts if self.attempts else 0.0

    @property
    def box(self) -> int:
        return min(self.streak, len(INTERVALS_DAYS) - 1)

    @property
    def interval_days(self) -> float:
        return INTERVALS_DAYS[self.box]

    def days_since(self, now: datetime) -> float:
        if self.last_seen is None:
            return float("inf")
        return max(0.0, (now - self.last_seen).total_seconds() / 86400.0)

    def due_ratio(self, now: datetime) -> float:
        """>= 1.0 means the spacing interval has elapsed."""
        interval = self.interval_days
        if interval <= 0:
            return float("inf")
        return self.days_since(now) / interval


def build_progress(history: Dict[str, List[Dict]]) -> Dict[str, Progress]:
    out: Dict[str, Progress] = {}
    for qid, attempts in history.items():
        p = Progress(question_id=qid)
        for row in attempts:
            ok = bool(row.get("correct"))
            p.attempts += 1
            p.correct += 1 if ok else 0
            p.streak = p.streak + 1 if ok else 0
            p.last_correct = ok
            ts = parse_ts(row.get("ts", ""))
            if ts is not None:
                p.last_seen = ts
        out[qid] = p
    return out


def _tier(p: Optional[Progress]) -> int:
    if p is None or p.attempts == 0:
        return TIER_UNSEEN
    return TIER_MISSED if p.last_correct is False else TIER_SPACED


def sort_key(q: Question, p: Optional[Progress], now: datetime, jitter: float):
    """Lower sorts first."""
    tier = _tier(p)
    if tier == TIER_MISSED:
        assert p is not None
        # Worst accuracy first, then whichever has been sitting longest.
        return (tier, p.accuracy, -p.days_since(now), jitter)
    if tier == TIER_UNSEEN:
        return (tier, 0.0, 0.0, jitter)
    assert p is not None
    # Most overdue first; break ties toward the shakier question.
    return (tier, -p.due_ratio(now), p.accuracy, jitter)


def select(
    questions: List[Question],
    history: Dict[str, List[Dict]],
    count: int,
    mode: str = "smart",
    now: Optional[datetime] = None,
    rng: Optional[random.Random] = None,
) -> List[Question]:
    """Pick up to `count` questions.

    smart   - missed first, then unseen, then most-overdue (the default)
    due     - smart, but skip anything still inside its spacing interval
    weakest - purely worst lifetime accuracy first, unseen last
    random  - shuffle
    """
    now = now or datetime.now(timezone.utc)
    rng = rng or random.Random()
    progress = build_progress(history)

    if mode == "random":
        pool = list(questions)
        rng.shuffle(pool)
        return pool[:count]

    if mode == "weakest":
        def weak_key(q: Question):
            p = progress.get(q.id)
            if p is None or p.attempts == 0:
                return (1, 0.0, rng.random())
            return (0, p.accuracy, rng.random())
        return sorted(questions, key=weak_key)[:count]

    ordered = sorted(
        questions,
        key=lambda q: sort_key(q, progress.get(q.id), now, rng.random()),
    )

    if mode == "due":
        ready = []
        held = []
        for q in ordered:
            p = progress.get(q.id)
            if _tier(p) == TIER_SPACED and p is not None and p.due_ratio(now) < 1.0:
                held.append(q)
            else:
                ready.append(q)
        # Fall back to held-back items only if there is nothing else to serve.
        ordered = ready + held

    return ordered[:count]


def explain_selection(q: Question, history: Dict[str, List[Dict]],
                      now: Optional[datetime] = None) -> str:
    """One-line reason a question came up - useful for sanity-checking runs."""
    now = now or datetime.now(timezone.utc)
    p = build_progress(history).get(q.id)
    tier = _tier(p)
    if tier == TIER_UNSEEN:
        return "new"
    assert p is not None
    if tier == TIER_MISSED:
        return "missed last time (%d/%d lifetime)" % (p.correct, p.attempts)
    return "review, box %d, %.1fd since last (%d/%d)" % (
        p.box, p.days_since(now), p.correct, p.attempts,
    )
