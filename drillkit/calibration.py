"""Calibration: did you know that you knew?

The rest of the system measures whether an answer was **right**. This measures
whether the learner **knew** it was right, which is a different question, and
the gap between the two is where exam failures live.

Four states; only two were previously visible:

                 correct                     wrong
    confident    genuinely known             THE DANGEROUS QUADRANT
    unsure       lucky - counted as learned  known unknown, least dangerous
    guess        lucky - no longer counted    known unknown, least dangerous

The dangerous quadrant is the one that sinks people. You are confident, you are
wrong, and nothing else in this system will ever bring that question back as a
problem - it reads as a win. Surfacing it is the single most actionable thing
this module does.

Three rules govern everything here:

* **Never a "calibration score".** The curve, the gap and the lists are the
  output. Collapsing them to one number is the same mistake ruled out for
  cases and for the scaled exam estimate.
* **Wilson intervals on every rate, gated on a minimum sample.** With a handful
  of answers per confidence level all three cells are noise and must visibly
  read as noise.
* **Unlabelled rows are counted, never guessed at.** Every attempt logged
  before confidence capture existed carries `confidence == ""`. Those rows stay
  in accuracy figures and are reported separately here; they are never
  redistributed across the three levels.

This module still only reads. The scheduler now reads confidence too, which was
the highest-value application of this data and was deliberately deferred until
the signal had been measured - `DETECTION.md` check 7 puts it at 96% detection
with no false positives. A correct answer the learner called a guess no longer
advances the spacing ladder; see `scheduler.ADVANCING_CONFIDENCE`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from .itemanalysis import difference_of_proportions, wilson_interval
from .loader import Question
from .store import CONFIDENCE, parse_ts

# Below this many answers at a confidence level, the rate is noise. Reported,
# but flagged so no surface can present it as a finding.
MIN_LEVEL = 8

# Attempts per question that counts as "covered" for the projection. Matches
# the item-analysis threshold for giving a question statistics at all.
COVERAGE_TARGET = 5

# Answers needed inside the pace window before a projection means anything.
# Five answers in four weeks extrapolates to a date decades out, which is
# arithmetically true and completely uninformative - the same reason every
# other rate here is gated on a minimum sample.
MIN_PACE_ATTEMPTS = 20


@dataclass
class Cell:
    """One confidence level, with its uncertainty attached."""
    level: str
    attempts: int = 0
    correct: int = 0

    @property
    def accuracy(self) -> Optional[float]:
        return (self.correct / self.attempts) if self.attempts else None

    @property
    def interval(self):
        return wilson_interval(self.correct, self.attempts)

    @property
    def enough(self) -> bool:
        return self.attempts >= MIN_LEVEL

    def as_dict(self) -> Dict[str, Any]:
        low, high = self.interval
        return {
            "level": self.level,
            "attempts": self.attempts,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "low": low if self.attempts else None,
            "high": high if self.attempts else None,
            "enough": self.enough,
        }


def _labelled(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if str(r.get("confidence", "")) in CONFIDENCE]


def curve(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Accuracy at each confidence level, lowest first.

    Well calibrated is a rising line. The interesting failure is a flat one:
    it means the learner's confidence carries no information about whether they
    are right, which is worse than being uniformly overconfident because there
    is nothing to correct for.
    """
    cells = {level: Cell(level) for level in CONFIDENCE}
    for row in _labelled(rows):
        cell = cells[row["confidence"]]
        cell.attempts += 1
        cell.correct += 1 if row.get("correct") else 0
    return [cells[level].as_dict() for level in CONFIDENCE]


def unlabelled_count(rows: Sequence[Dict[str, Any]]) -> int:
    """Answers from before capture existed, or where it was not recorded."""
    return sum(1 for r in rows if str(r.get("confidence", "")) not in CONFIDENCE)


def overconfidence_gap(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Accuracy when confident, minus accuracy when NOT confident.

    Two decisions here, both corrections to the original brief, which asked for
    confident minus *overall* accuracy with the confident cell's interval
    attached.

    First, the contrast. Overall accuracy contains the confident answers, so
    comparing the two dilutes the difference by roughly the confident share of
    the log. On a real 240-answer sample the same data read +6 points against
    the total and +13 against the complement - the diluted figure understated
    the effect by more than half. Comparing a subgroup with the group that
    excludes it is the comparison that isolates what confidence is worth.

    Second, the uncertainty. A difference between two rates has its own
    standard error, and the interval of one of the two rates is not it. Without
    an interval on the difference there is no way to see that +6 points on
    these numbers is indistinguishable from no relationship at all. `spans_zero`
    says so directly, because that is the finding a learner needs: not "you are
    slightly overconfident" but "your confidence is not yet telling you
    anything."
    """
    labelled = _labelled(rows)
    confident = [r for r in labelled if r["confidence"] == "confident"]
    other = [r for r in labelled if r["confidence"] != "confident"]

    conf_n, other_n, overall_n = len(confident), len(other), len(labelled)
    conf_ok = sum(1 for r in confident if r.get("correct"))
    other_ok = sum(1 for r in other if r.get("correct"))
    overall_ok = sum(1 for r in labelled if r.get("correct"))

    conf = (conf_ok / conf_n) if conf_n else None
    other_rate = (other_ok / other_n) if other_n else None
    overall = (overall_ok / overall_n) if overall_n else None

    # Standard error of a difference of two independent proportions, shared
    # with the exam post-mortem so the two cannot drift apart. `enough` still
    # gates on a minimum count in both cells: the approximation is crude in
    # the tails and the interval alone will not say so.
    diff = difference_of_proportions(conf_ok, conf_n, other_ok, other_n)
    gap, low, high = diff["gap"], diff["low"], diff["high"]

    return {
        "gap": gap,
        "gap_low": low,
        "gap_high": high,
        "spans_zero": diff["spans_zero"],
        "confident_accuracy": conf,
        "confident_attempts": conf_n,
        "confident_low": wilson_interval(conf_ok, conf_n)[0] if conf_n else None,
        "confident_high": wilson_interval(conf_ok, conf_n)[1] if conf_n else None,
        "other_accuracy": other_rate,
        "other_attempts": other_n,
        "overall_accuracy": overall,
        "overall_attempts": overall_n,
        "enough": conf_n >= MIN_LEVEL and other_n >= MIN_LEVEL,
    }


# --------------------------------------------------------------------------
# the lists
# --------------------------------------------------------------------------

def _decorate(row: Dict[str, Any], by_id: Dict[str, Question],
              rule_for: Dict[str, str]) -> Dict[str, Any]:
    qid = row.get("question_id", "")
    question = by_id.get(qid)
    return {
        "question_id": qid,
        "ts": row.get("ts", ""),
        "topic": row.get("topic", "") or (question.topic if question else ""),
        "domain": row.get("domain", ""),
        "chosen": row.get("chosen", ""),
        "answer": row.get("answer", ""),
        "confidence": row.get("confidence", ""),
        "mode": row.get("mode", ""),
        "seconds": row.get("seconds", 0),
        "rule": rule_for.get(qid, ""),
        "stem": question.stem if question else "",
    }


def dangerous(rows: Sequence[Dict[str, Any]], by_id: Dict[str, Question],
              rule_for: Optional[Dict[str, str]] = None,
              limit: int = 50) -> List[Dict[str, Any]]:
    """Confident and wrong, most recent first.

    The single most actionable output of the feature. Nothing else in the
    system will ever surface these: they are answered, they are logged, and to
    every other report they look like ordinary misses among many.
    """
    rule_for = rule_for or {}
    hits = [r for r in rows
            if r.get("confidence") == "confident" and not r.get("correct")]
    hits.sort(key=lambda r: str(r.get("ts", "")), reverse=True)
    return [_decorate(r, by_id, rule_for) for r in hits[:limit]]


def lucky(rows: Sequence[Dict[str, Any]], by_id: Dict[str, Question],
          rule_for: Optional[Dict[str, str]] = None,
          limit: int = 50) -> List[Dict[str, Any]]:
    """Guessed or unsure, and correct.

    Not failures, but not learned either - and currently indistinguishable from
    mastery to every other diagnostic.
    """
    rule_for = rule_for or {}
    hits = [r for r in rows
            if r.get("confidence") in ("guess", "unsure") and r.get("correct")]
    hits.sort(key=lambda r: str(r.get("ts", "")), reverse=True)
    return [_decorate(r, by_id, rule_for) for r in hits[:limit]]


# --------------------------------------------------------------------------
# breakdowns
# --------------------------------------------------------------------------

@dataclass
class Breakdown:
    key: str
    label: str = ""
    cells: Dict[str, Cell] = field(default_factory=dict)
    dangerous: int = 0
    lucky: int = 0

    @property
    def attempts(self) -> int:
        return sum(c.attempts for c in self.cells.values())


def _breakdown(rows: Sequence[Dict[str, Any]], key_of, label_of=None
               ) -> List[Dict[str, Any]]:
    buckets: Dict[str, Breakdown] = {}
    for row in _labelled(rows):
        key = key_of(row)
        if not key:
            continue
        bucket = buckets.get(key)
        if bucket is None:
            bucket = Breakdown(key=key,
                               label=label_of(key) if label_of else key,
                               cells={lv: Cell(lv) for lv in CONFIDENCE})
            buckets[key] = bucket
        level = row["confidence"]
        bucket.cells[level].attempts += 1
        if row.get("correct"):
            bucket.cells[level].correct += 1
            if level in ("guess", "unsure"):
                bucket.lucky += 1
        elif level == "confident":
            bucket.dangerous += 1

    out = []
    for bucket in buckets.values():
        conf = bucket.cells["confident"]
        low, high = conf.interval
        out.append({
            "key": bucket.key,
            "label": bucket.label,
            "attempts": bucket.attempts,
            "dangerous": bucket.dangerous,
            "lucky": bucket.lucky,
            "confident_attempts": conf.attempts,
            "confident_accuracy": conf.accuracy,
            "confident_low": low if conf.attempts else None,
            "confident_high": high if conf.attempts else None,
            "enough": conf.attempts >= MIN_LEVEL,
            "cells": [bucket.cells[lv].as_dict() for lv in CONFIDENCE],
        })
    # Worst first by dangerous count, then by how much evidence there is.
    out.sort(key=lambda b: (-b["dangerous"], -b["attempts"]))
    return out


def by_topic(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _breakdown(
        rows,
        key_of=lambda r: "D%s%s | %s" % (r.get("domain", "?"),
                                         r.get("section", ""),
                                         r.get("topic", "?")),
    )


def by_rule(rows: Sequence[Dict[str, Any]], rules: Sequence[Dict[str, Any]],
            rule_for: Dict[str, str]) -> List[Dict[str, Any]]:
    """The breakdown the brief cares most about.

    "You are overconfident specifically on evidence-quality questions" is far
    more actionable than a global figure, because it names the reasoning habit
    rather than the subject matter.
    """
    names = {r["id"]: r.get("name", r["id"]) for r in rules}
    return _breakdown(
        rows,
        key_of=lambda r: rule_for.get(r.get("question_id", ""), ""),
        label_of=lambda key: names.get(key, key),
    )


def rule_index(rules: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """question id -> the first decision rule that governs it."""
    out: Dict[str, str] = {}
    for rule in rules:
        for qid in rule.get("question_ids") or []:
            out.setdefault(qid, rule["id"])
    return out


# --------------------------------------------------------------------------
# study horizon
# --------------------------------------------------------------------------

def parse_target(value: object) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def projection(rows: Sequence[Dict[str, Any]], questions: Sequence[Question],
               target: Optional[date] = None, window_days: int = 28,
               today: Optional[date] = None) -> Dict[str, Any]:
    """Coverage projection: honest arithmetic over the attempt log.

    Deliberately **not** a retention forecast. That needs the FSRS work, which
    waits until there are enough reviews to fit and test against - a decay curve
    drawn from published defaults would look authoritative and mean nothing.

    All this says is: at the pace you have actually been going, here is when
    every question will have been seen `COVERAGE_TARGET` times.
    """
    today = today or datetime.now(timezone.utc).astimezone().date()
    total_questions = len(questions)
    known = {q.id for q in questions}

    seen: Dict[str, int] = {}
    for row in rows:
        qid = row.get("question_id", "")
        if qid in known:
            seen[qid] = seen.get(qid, 0) + 1

    # Answers still needed for every question to reach the coverage target.
    remaining = sum(max(0, COVERAGE_TARGET - seen.get(q.id, 0)) for q in questions)
    covered = sum(1 for q in questions if seen.get(q.id, 0) >= COVERAGE_TARGET)

    cutoff = today - timedelta(days=window_days - 1)
    recent = 0
    active_days = set()
    for row in rows:
        ts = parse_ts(str(row.get("ts", "")))
        if ts is None:
            continue
        day = ts.astimezone().date()
        if day >= cutoff:
            recent += 1
            active_days.add(day)

    # Pace over the window, not over active days only: rest days are part of
    # how fast you actually get through material.
    pace = recent / float(window_days) if recent else 0.0
    enough = recent >= MIN_PACE_ATTEMPTS
    days_needed = (remaining / pace) if (pace > 0 and enough) else None
    finish = (today + timedelta(days=round(days_needed))) if days_needed else None

    out: Dict[str, Any] = {
        "questions": total_questions,
        "coverage_target": COVERAGE_TARGET,
        "covered": covered,
        "attempts_remaining": remaining,
        "window_days": window_days,
        "recent_attempts": recent,
        "active_days": len(active_days),
        "pace_per_day": pace,
        "enough": enough,
        "min_pace_attempts": MIN_PACE_ATTEMPTS,
        "days_needed": days_needed,
        "projected_date": finish.isoformat() if finish else None,
        "target": target.isoformat() if target else None,
        "days_to_target": (target - today).days if target else None,
        "margin_days": None,
        "on_track": None,
        "today": today.isoformat(),
    }
    if target and finish:
        margin = (target - finish).days
        out["margin_days"] = margin
        out["on_track"] = margin >= 0
    return out


# --------------------------------------------------------------------------
# one call for a front end
# --------------------------------------------------------------------------

def report(rows: Sequence[Dict[str, Any]], questions: Sequence[Question],
           rules: Sequence[Dict[str, Any]],
           target: Optional[date] = None) -> Dict[str, Any]:
    by_id = {q.id: q for q in questions}
    index = rule_index(rules)
    labelled = _labelled(rows)

    return {
        "attempts": len(rows),
        "labelled": len(labelled),
        "unlabelled": unlabelled_count(rows),
        "min_level": MIN_LEVEL,
        "curve": curve(rows),
        "gap": overconfidence_gap(rows),
        "dangerous": dangerous(rows, by_id, index),
        "lucky": lucky(rows, by_id, index),
        "by_rule": by_rule(rows, rules, index),
        "by_topic": by_topic(rows),
        "projection": projection(rows, questions, target),
    }
