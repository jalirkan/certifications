"""Classical item analysis over your own attempt log.

Standard psychometrics assumes many examinees taking one test. Here there is
one examinee taking many sessions, so the usual statistics are adapted:

* **Difficulty (p-value)** is the proportion answered correctly, same as usual.
* **Discrimination** normally compares high scorers against low scorers. With a
  single learner the analogue is: on sessions where you performed well overall,
  did you also get this item right? Ability is measured as your score on the
  *other* items in the same session, which avoids the item inflating its own
  correlation.
* **Distractor analysis** counts how often each option was chosen. An option
  nobody ever picks is dead weight teaching nothing, and a distractor picked
  more often than the key usually means the item is ambiguous or mis-keyed.

Everything is gated on a minimum sample, because a p-value from three attempts
is noise. Wilson score intervals are reported so the width of that noise is
visible rather than implied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .loader import OPTION_KEYS, Question

# Below these counts a statistic is reported as unknown rather than as a number.
MIN_ATTEMPTS_STATS = 5      # difficulty and flags
MIN_SESSIONS_DISC = 3       # discrimination needs this many distinct sessions
ATTRACTIVE_DISTRACTOR = 0.20

# Judged on the interval rather than the point estimate, so these are the
# levels a *bound* has to clear, and they are deliberately reachable. Requiring
# the lower bound to clear 0.95 - the old point-estimate threshold - would need
# about 73 consecutive correct answers, which is a flag that never fires: the
# same failure as the original in the opposite direction. 0.85 is cleared by a
# little over 20 straight correct, which is a real amount of evidence and an
# attainable one for a heavily-drilled item.
EASY_THRESHOLD = 0.85
HARD_THRESHOLD = 0.30

# ---------------------------------------------------------------------------
# Why the rewrite flags are gated the way they are
#
# `DETECTION.md` scored these against synthetic learners and two checks failed
# outright: a question that measures nothing, and a miskeyed question, both
# fired on learners with *nothing planted* - 64% and 26% of them. Measured
# directly, 79% of scored items were flagged on a clean 3000-answer history.
# A flag that fires on four items in five is not a finding.
#
# The cause was the same in every flag and is not subtle in hindsight: they
# tested point estimates from a handful of attempts. The median item in a
# 3000-answer history has about **seven** attempts. Seven attempts is not a
# sample you can call a question too easy from - 7 of 7 correct happens 20% of
# the time on a question the learner simply knows - and it is not a sample you
# can compute a correlation from at all.
#
# This is the one place the rule in CLAUDE.md 3.6 was never applied: every
# other statistic in this project carries an interval and a minimum sample.
# These now do too. Each threshold below is set so the flag fires when the
# observation would be *surprising*, not merely possible.
# ---------------------------------------------------------------------------

# A correlation over six points is noise: roughly half of clean items came back
# negative. Twenty is the point at which a negative value is worth reporting,
# and it must be meaningfully negative rather than a hair below zero.
MIN_ATTEMPTS_DISC = 20
NEG_DISCRIMINATION_AT = -0.15

# Dead options are gated on *wrong* answers, not total attempts, which was the
# real error: with seven attempts at 78% accuracy there are about one and a
# half wrong answers to spread over three distractors, so most distractors show
# zero picks by arithmetic rather than by being unattractive. With W wrong
# answers spread evenly, the chance a given distractor draws none is (2/3)^W;
# at W = 8 that is under 4%, which makes a zero worth remarking on.
MIN_WRONG_FOR_DEAD = 8


# --------------------------------------------------------------------------
# small statistics helpers (stdlib only, by design)
# --------------------------------------------------------------------------

def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None  # no variance on one side, correlation undefined
    return sxy / math.sqrt(sxx * syy)


def wilson_interval(correct: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Confidence interval for a proportion that behaves sensibly at small n.

    The naive interval says 2/2 correct means 100% with zero uncertainty, which
    is exactly the wrong conclusion to draw from two attempts.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = correct / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def difference_of_proportions(a_ok: int, a_n: int, b_ok: int, b_n: int,
                              z: float = 1.96) -> Dict[str, Optional[float]]:
    """Rate in group A minus rate in group B, with an interval on the gap.

    A difference between two rates has its own standard error, and the interval
    of either rate alone is not it. Without this, a six-point gap that is
    indistinguishable from no relationship at all reads as a finding -
    `spans_zero` says so directly, which is usually the honest headline.

    The normal approximation is crude in the tails, so callers still gate on a
    minimum count in both cells rather than trusting the interval alone.

    Shared by `calibration.overconfidence_gap` (confident vs not) and
    `postmortem.timing` (fast vs slow). One implementation on purpose: two
    copies of this arithmetic would drift, and the second copy would be the
    one nobody re-derived.
    """
    if not a_n or not b_n:
        return {"gap": None, "low": None, "high": None, "spans_zero": None}
    a = a_ok / a_n
    b = b_ok / b_n
    se = math.sqrt(a * (1 - a) / a_n + b * (1 - b) / b_n)
    gap = a - b
    return {"gap": gap, "low": gap - z * se, "high": gap + z * se,
            "spans_zero": (gap - z * se) <= 0 <= (gap + z * se)}


def median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


# --------------------------------------------------------------------------
# per-item statistics
# --------------------------------------------------------------------------

@dataclass
class ItemStats:
    question_id: str
    domain: str
    section: str
    topic: str
    attempts: int = 0
    correct: int = 0
    sessions: int = 0
    option_counts: Dict[str, int] = field(default_factory=dict)
    answer_key: str = ""
    first_attempt_correct: Optional[bool] = None
    recent_streak_wrong: int = 0
    discrimination: Optional[float] = None
    median_seconds: Optional[float] = None
    flags: List[str] = field(default_factory=list)

    @property
    def p_value(self) -> Optional[float]:
        return self.correct / self.attempts if self.attempts else None

    @property
    def interval(self) -> Tuple[float, float]:
        return wilson_interval(self.correct, self.attempts)

    @property
    def has_stats(self) -> bool:
        return self.attempts >= MIN_ATTEMPTS_STATS

    def distractor_share(self, key: str) -> float:
        if not self.attempts:
            return 0.0
        return self.option_counts.get(key, 0) / self.attempts


def _session_scores(rows: Sequence[Dict]) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for row in rows:
        out.setdefault(row.get("session", "?"), []).append(row)
    return out


def analyze(rows: Sequence[Dict], questions: Sequence[Question],
            min_attempts: int = MIN_ATTEMPTS_STATS) -> List[ItemStats]:
    """Build per-item statistics from the attempt log."""
    lookup = {q.id: q for q in questions}
    sessions = _session_scores(rows)

    # ability[session] = list of (question_id, correct) so we can exclude the
    # item under test when measuring how well the session went overall.
    session_items: Dict[str, List[Tuple[str, int]]] = {
        sid: [(r["question_id"], 1 if r.get("correct") else 0) for r in srows]
        for sid, srows in sessions.items()
    }

    by_item: Dict[str, List[Dict]] = {}
    for row in rows:
        by_item.setdefault(row["question_id"], []).append(row)
    for attempts in by_item.values():
        attempts.sort(key=lambda r: r.get("ts", ""))

    stats: List[ItemStats] = []
    for qid, attempts in by_item.items():
        q = lookup.get(qid)
        item = ItemStats(
            question_id=qid,
            domain=str(attempts[-1].get("domain", q.domain if q else "")),
            section=str(attempts[-1].get("section", q.section if q else "")),
            topic=str(attempts[-1].get("topic", q.topic if q else "")),
            answer_key=q.answer if q else str(attempts[-1].get("answer", "")),
        )
        item.attempts = len(attempts)
        item.correct = sum(1 for a in attempts if a.get("correct"))
        item.sessions = len({a.get("session") for a in attempts})
        item.first_attempt_correct = bool(attempts[0].get("correct"))

        for a in attempts:
            chosen = str(a.get("chosen", "")).upper()
            if chosen:
                item.option_counts[chosen] = item.option_counts.get(chosen, 0) + 1

        streak = 0
        for a in reversed(attempts):
            if a.get("correct"):
                break
            streak += 1
        item.recent_streak_wrong = streak

        times = [float(a.get("seconds", 0) or 0) for a in attempts]
        times = [t for t in times if t > 0]
        item.median_seconds = median(times)

        item.discrimination = _discrimination(qid, attempts, session_items)
        item.flags = _flags(item, q, min_attempts)
        stats.append(item)

    # Questions that exist in the bank but have never been served.
    seen = set(by_item)
    for q in questions:
        if q.id not in seen:
            stats.append(ItemStats(
                question_id=q.id, domain=q.domain, section=q.section,
                topic=q.topic, answer_key=q.answer, flags=["NEVER_SERVED"],
            ))

    return stats


def _discrimination(qid: str, attempts: Sequence[Dict],
                    session_items: Dict[str, List[Tuple[str, int]]]) -> Optional[float]:
    """Point-biserial between this item and ability on the rest of the session."""
    if len(attempts) < MIN_ATTEMPTS_DISC:
        return None
    if len({a.get("session") for a in attempts}) < MIN_SESSIONS_DISC:
        return None

    xs: List[float] = []
    ys: List[float] = []
    for a in attempts:
        sid = a.get("session", "?")
        others = [ok for other_qid, ok in session_items.get(sid, [])
                  if other_qid != qid]
        if not others:
            continue  # single-question session tells us nothing about ability
        xs.append(1.0 if a.get("correct") else 0.0)
        ys.append(sum(others) / len(others))

    return pearson(xs, ys)


def _flags(item: ItemStats, q: Optional[Question], min_attempts: int) -> List[str]:
    flags: List[str] = []

    # Repeated recent misses describe the learner, not the item, so this is
    # actionable immediately and is not gated on having a statistical sample.
    if item.recent_streak_wrong >= 3:
        flags.append("PERSISTENT_MISS")

    if item.attempts < min_attempts:
        flags.append("THIN_DATA")
        return flags

    # Difficulty is judged on the interval, not the point estimate. A question
    # answered 7 of 7 has a Wilson bound from 65% to 100% - easy is plausible,
    # but so is 70%, and only the lower bound clearing the threshold means the
    # question really is too easy rather than briefly lucky.
    low, high = wilson_interval(item.correct, item.attempts)
    if low >= EASY_THRESHOLD:
        flags.append("TOO_EASY")
    if high <= HARD_THRESHOLD:
        flags.append("TOO_HARD")

    if (item.discrimination is not None
            and item.attempts >= MIN_ATTEMPTS_DISC
            and item.discrimination <= NEG_DISCRIMINATION_AT):
        flags.append("NEG_DISCRIMINATION")

    if q is not None:
        distractors = [k for k in OPTION_KEYS if k != q.answer]
        key_count = item.option_counts.get(q.answer, 0)

        # Gated on wrong answers, because that is what a distractor can draw
        # from. Total attempts is the wrong denominator entirely.
        wrong = sum(item.option_counts.get(k, 0) for k in distractors)
        if wrong >= MIN_WRONG_FOR_DEAD:
            dead = [k for k in distractors if item.option_counts.get(k, 0) == 0]
            if dead:
                flags.append("DEAD_OPTION:%s" % "".join(sorted(dead)))

        challenger = max(distractors, key=lambda k: item.option_counts.get(k, 0))
        if item.option_counts.get(challenger, 0) > key_count:
            flags.append("KEY_CHALLENGED:%s" % challenger)

    return flags


# --------------------------------------------------------------------------
# bank-level roll-up
# --------------------------------------------------------------------------

@dataclass
class BankHealth:
    total_questions: int = 0
    served: int = 0
    never_served: int = 0
    with_stats: int = 0
    mean_p_value: Optional[float] = None
    mean_discrimination: Optional[float] = None
    flag_counts: Dict[str, int] = field(default_factory=dict)
    difficulty_spread: Dict[str, int] = field(default_factory=dict)


def bank_health(stats: Sequence[ItemStats]) -> BankHealth:
    health = BankHealth(total_questions=len(stats))
    health.never_served = sum(1 for s in stats if s.attempts == 0)
    health.served = health.total_questions - health.never_served

    scored = [s for s in stats if s.has_stats]
    health.with_stats = len(scored)
    if scored:
        health.mean_p_value = sum(s.p_value or 0 for s in scored) / len(scored)

    discs = [s.discrimination for s in stats if s.discrimination is not None]
    if discs:
        health.mean_discrimination = sum(discs) / len(discs)

    buckets = {"very hard <25%": 0, "hard 25-50%": 0, "moderate 50-75%": 0,
               "easy 75-95%": 0, "trivial >=95%": 0}
    for s in scored:
        p = s.p_value or 0.0
        if p < 0.25:
            buckets["very hard <25%"] += 1
        elif p < 0.50:
            buckets["hard 25-50%"] += 1
        elif p < 0.75:
            buckets["moderate 50-75%"] += 1
        elif p < EASY_THRESHOLD:
            buckets["easy 75-95%"] += 1
        else:
            buckets["trivial >=95%"] += 1
    health.difficulty_spread = buckets

    for s in stats:
        for flag in s.flags:
            key = flag.split(":")[0]
            health.flag_counts[key] = health.flag_counts.get(key, 0) + 1

    return health


def topic_rollup(stats: Sequence[ItemStats]) -> List[Tuple[str, int, int, float, Tuple[float, float]]]:
    """(label, attempts, correct, p_value, wilson interval) per topic, weakest first.

    Sorted by the *lower* bound of the interval rather than the point estimate.
    This is deliberately conservative: it answers "where can I not yet
    demonstrate competence", which surfaces both genuinely weak topics and
    thinly tested ones. A topic at 1/2 can rank above one at 5/20, because two
    attempts cannot rule out that it is worse. Drilling an under-tested topic
    is the right response either way, since it resolves the uncertainty.

    Where two topics carry comparable evidence, the lower accuracy ranks first.
    """
    agg: Dict[str, List[int]] = {}
    for s in stats:
        if not s.attempts:
            continue
        label = "D%s%s | %s" % (s.domain, s.section, s.topic)
        bucket = agg.setdefault(label, [0, 0])
        bucket[0] += s.attempts
        bucket[1] += s.correct

    rows = []
    for label, (attempts, correct) in agg.items():
        p = correct / attempts if attempts else 0.0
        rows.append((label, attempts, correct, p, wilson_interval(correct, attempts)))
    return sorted(rows, key=lambda r: (r[4][0], r[3]))


def needs_rewrite(stats: Sequence[ItemStats]) -> List[ItemStats]:
    """Items whose own statistics suggest the question is the problem."""
    suspect = ("NEG_DISCRIMINATION", "KEY_CHALLENGED", "TOO_EASY", "DEAD_OPTION")
    out = [s for s in stats
           if any(f.split(":")[0] in suspect for f in s.flags)]
    return sorted(out, key=lambda s: (s.discrimination if s.discrimination is not None else 0,
                                      -(s.p_value or 0)))
