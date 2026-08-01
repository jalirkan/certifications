"""Exam post-mortem: where the marks went, and whether speed cost them.

Two readings of one sitting, both from data the exam already stores.

**The waterfall.** `cost` - blueprint weight times the fraction missed - is the
most actionable number the exam produces, and it rendered as a sorted list of
rows, which is the one shape that hides what it is. It is a decomposition: a
hundred points of blueprint weight are available, each domain takes some away,
and what is left is what was earned. Drawn as a waterfall that reads in one
look; drawn as a list you have to hold five numbers in your head to compare.

A domain can be your worst by accuracy and cost almost nothing, because Domain
3 is 12% of the exam and Domain 4 is 26%. That inversion is the entire point of
weighting by the blueprint, and it is invisible in an accuracy-sorted list.

**Time against correctness.** `seconds_per_question` has been stored since the
exam runner was written and has never reached a screen. The quadrant worth
knowing is *fast and wrong*: questions answered below your own median pace and
missed. Rushing and not knowing produce the same mark and want different
fixes - one is a habit, the other is study.

Three honesty constraints, all inherited:

* **The split is the learner's own median for that sitting**, not a fixed
  number of seconds. "Fast" only means anything relative to how they were
  working that day, and a fixed threshold would call a careful sitting slow
  throughout.
* **The gap between fast and slow accuracy carries an interval**, via the same
  arithmetic as the confidence gap, and `spans_zero` is reported. A twelve-point
  difference across 150 questions is frequently indistinguishable from nothing,
  and "your pace is not telling you anything yet" is the honest headline when
  it is.
* **No scaled score anywhere in here.** The estimate and its caveat stay where
  they are, unchanged. Nothing in this module is a prediction; it is arithmetic
  over one sitting that already happened.
* **Speed and difficulty are confounded, and the wording says so.** You go fast
  on questions that look easy, so a fast-and-wrong cluster is as consistent
  with misreading difficulty as with rushing - and if one domain is both weak
  and quick, the split is really measuring that domain. `verdict()` states the
  association and refuses to name the cause; the waterfall sits beside it
  because that is what tells the two apart.

Unanswered questions are held out of the timing comparison and counted
separately. Running out of time is a real finding, but it is not the same
finding as rushing, and folding the two together would name the wrong fix.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .itemanalysis import difference_of_proportions, median, wilson_interval

# Questions needed in both the fast and slow halves before the comparison is
# worth showing as a finding. A 20-question exam splits into two cells of ten,
# where a two-question difference moves the rate by twenty points.
MIN_PER_HALF = 15

# Blueprint weights are percentages, so this is the whole exam.
AVAILABLE = 100.0


def waterfall(by_domain: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The hundred available points, minus what each domain cost.

    Ordered by damage, which is the order to study in, and deliberately not by
    domain number or by accuracy.

    Each step carries an interval, because `cost` inherits all the uncertainty
    of the accuracy it is built from. Weight is exact - it comes from the
    published blueprint - so the interval is just the accuracy interval scaled:
    a domain sampled 18 times has a cost interval wide enough that its rank
    against its neighbour is often not resolvable, and the chart has to show
    that rather than imply a clean ordering.
    """
    steps: List[Dict[str, Any]] = []
    for d in by_domain:
        weight = float(d.get("weight") or 0.0)
        asked = int(d.get("asked") or 0)
        correct = int(d.get("correct") or 0)
        accuracy = float(d.get("accuracy") or 0.0)
        cost = weight * (1.0 - accuracy)

        # The accuracy interval, transformed. Higher accuracy means lower cost,
        # so the bounds swap.
        low, high = wilson_interval(correct, asked)
        steps.append({
            "domain": d.get("domain", "?"),
            "name": d.get("name", ""),
            "weight": weight,
            "asked": asked,
            "correct": correct,
            "accuracy": accuracy if asked else None,
            "cost": cost,
            "cost_low": weight * (1.0 - high) if asked else None,
            "cost_high": weight * (1.0 - low) if asked else None,
            "enough": asked >= 10,
        })

    steps.sort(key=lambda s: -s["cost"])

    # Running balance, so the chart can draw each bar as a drop from the last.
    running = sum(s["weight"] for s in steps) or AVAILABLE
    available = running
    for step in steps:
        step["from"] = running
        running -= step["cost"]
        step["to"] = running

    return {
        "available": available,
        "earned": running,
        "lost": available - running,
        "steps": steps,
    }


def timing(questions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Seconds against correctness, split at the learner's own median.

    `questions` carries one entry per item: id, topic, domain, seconds, correct
    and answered. Items with no recorded time are dropped rather than treated
    as instant - a zero here means the runner never saw the question focused,
    not that it was answered in no time.
    """
    timed = [q for q in questions if float(q.get("seconds") or 0.0) > 0]
    answered = [q for q in timed if q.get("answered")]
    skipped = [q for q in questions if not q.get("answered")]

    mid = median([float(q["seconds"]) for q in answered]) if answered else None
    if mid is None:
        return {
            "median": None, "enough": False, "min_per_half": MIN_PER_HALF,
            "points": [], "fast": _cell([]), "slow": _cell([]),
            "gap": {"gap": None, "low": None, "high": None, "spans_zero": None},
            "rushed": [], "verdict": None,
            "unanswered": len(skipped),
            "untimed": len(questions) - len(timed),
        }

    fast = [q for q in answered if float(q["seconds"]) < mid]
    slow = [q for q in answered if float(q["seconds"]) >= mid]

    fast_ok = sum(1 for q in fast if q.get("correct"))
    slow_ok = sum(1 for q in slow if q.get("correct"))

    points = [{
        "id": q.get("id", ""),
        "topic": q.get("topic", ""),
        "domain": q.get("domain", ""),
        "seconds": round(float(q["seconds"]), 1),
        "correct": bool(q.get("correct")),
        "answered": bool(q.get("answered")),
        "fast": float(q["seconds"]) < mid,
    } for q in timed]

    data: Dict[str, Any] = {
        "median": mid,
        "enough": len(fast) >= MIN_PER_HALF and len(slow) >= MIN_PER_HALF,
        "min_per_half": MIN_PER_HALF,
        "points": points,
        "fast": _cell(fast),
        "slow": _cell(slow),
        "gap": difference_of_proportions(fast_ok, len(fast), slow_ok, len(slow)),
        # Fast and wrong: the quadrant this view exists for.
        "rushed": [{
            "id": q.get("id", ""), "topic": q.get("topic", ""),
            "domain": q.get("domain", ""),
            "seconds": round(float(q["seconds"]), 1),
        } for q in sorted((q for q in fast if not q.get("correct")),
                          key=lambda q: float(q["seconds"]))[:12]],
        "unanswered": len(skipped),
        "untimed": len(questions) - len(timed),
    }
    # Travels with the data rather than being rebuilt client-side. The wording
    # is the honesty-critical part of this module - it is the sentence that
    # must not name a cause - and two copies of it would be one too many.
    data["verdict"] = verdict(data)
    return data


def _cell(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(items)
    ok = sum(1 for q in items if q.get("correct"))
    low, high = wilson_interval(ok, n)
    seconds = [float(q.get("seconds") or 0.0) for q in items]
    return {
        "n": n,
        "correct": ok,
        "accuracy": (ok / n) if n else None,
        "low": low if n else None,
        "high": high if n else None,
        "median_seconds": median(seconds),
    }


def verdict(data: Dict[str, Any]) -> Optional[str]:
    """One sentence about pace, or nothing.

    Returns None rather than a hedge when the evidence will not carry a
    sentence. A screen showing "no clear relationship" for every learner who
    has sat one exam teaches nothing; showing the numbers and no claim is
    honest, and the caller renders the cells either way.

    **States the association, never the cause.** An earlier draft of this said
    a negative gap was "a pace problem rather than a knowledge one", which the
    data cannot support: speed and difficulty are confounded. You go fast on
    questions that *look* easy, so fast-and-wrong is equally consistent with
    rushing and with misjudging which questions were hard - and if a whole
    domain is both weak and quick, the split is measuring the domain. The
    numbers say the two groups differ; which of those it is takes the domain
    breakdown next to it, which is why both live on one screen.
    """
    if not data.get("enough"):
        return None
    gap = data["gap"]
    if gap["gap"] is None:
        return None
    if gap["spans_zero"]:
        return ("Your pace is not telling you anything yet: the difference "
                "between your faster and slower answers is within the margin "
                "of error on this sitting.")
    if gap["gap"] < 0:
        return ("You were less accurate on the questions you answered fastest. "
                "That is consistent with rushing, and equally consistent with "
                "misjudging which questions were hard - check the domain "
                "breakdown before deciding which.")
    return ("You were more accurate on the questions you answered fastest, "
            "which usually means the slow ones were the genuinely hard ones "
            "rather than that hurrying helped.")
