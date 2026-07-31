"""Diagnosis by transferable decision rule rather than by syllabus topic.

A topic report says "study encryption". A principle report says "you reach for
detective controls when the stem asks what prevents" - one habit, costing marks
in every domain, fixable in an afternoon.

It is also the only axis here that transfers to questions that do not exist yet,
which is the actual exam condition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .itemanalysis import wilson_interval
from .loader import Question


@dataclass
class PrincipleStats:
    principle_id: str
    name: str
    statement: str = ""
    misapplication: str = ""
    scope: str = ""
    attempts: int = 0
    correct: int = 0
    questions_total: int = 0
    questions_seen: int = 0
    domains: List[str] = field(default_factory=list)

    @property
    def accuracy(self) -> Optional[float]:
        return self.correct / self.attempts if self.attempts else None

    @property
    def interval(self) -> Tuple[float, float]:
        return wilson_interval(self.correct, self.attempts)

    @property
    def coverage(self) -> float:
        if not self.questions_total:
            return 0.0
        return self.questions_seen / self.questions_total


def summarize(principles: Sequence[Dict], questions: Sequence[Question],
              rows: Sequence[Dict]) -> List[PrincipleStats]:
    """Accuracy per principle, weakest first by lower confidence bound.

    Ranked on the lower bound rather than the point estimate, consistent with
    the topic rollup: a rule you have barely tested is a rule you cannot yet
    claim, and drilling it resolves the uncertainty either way.
    """
    by_question: Dict[str, List[Dict]] = {}
    for row in rows:
        by_question.setdefault(row.get("question_id", ""), []).append(row)

    known = {q.id: q for q in questions}
    out: List[PrincipleStats] = []

    for p in principles:
        qids = [q for q in (p.get("question_ids") or []) if q in known]
        stat = PrincipleStats(
            principle_id=p.get("id", "?"),
            name=p.get("name", ""),
            statement=p.get("statement", ""),
            misapplication=p.get("misapplication", ""),
            scope=p.get("scope", ""),
            questions_total=len(qids),
            domains=sorted({known[q].domain for q in qids}),
        )
        for qid in qids:
            attempts = by_question.get(qid, [])
            if attempts:
                stat.questions_seen += 1
            for a in attempts:
                stat.attempts += 1
                stat.correct += 1 if a.get("correct") else 0
        out.append(stat)

    return sorted(out, key=lambda s: (s.interval[0], s.accuracy if s.accuracy is not None else 1.0))


def weakest(stats: Sequence[PrincipleStats], minimum_attempts: int = 4
            ) -> List[PrincipleStats]:
    """Principles with enough evidence to be worth acting on."""
    return [s for s in stats if s.attempts >= minimum_attempts]


def untested(stats: Sequence[PrincipleStats], minimum_attempts: int = 4
             ) -> List[PrincipleStats]:
    return [s for s in stats if s.attempts < minimum_attempts]


def questions_for(principles: Sequence[Dict], principle_id: str,
                  questions: Sequence[Question]) -> List[Question]:
    known = {q.id: q for q in questions}
    for p in principles:
        if p.get("id") == principle_id:
            return [known[q] for q in (p.get("question_ids") or []) if q in known]
    return []


def one_per_domain(items: Sequence[Question], rng, seen: Optional[set] = None
                   ) -> List[Question]:
    """One question per domain, preferring ones not yet attempted.

    This is what makes the same rule visible in five different costumes:
    segregation of duties in audit staffing, code promotion, job scheduling and
    privileged access is one idea, and studying by domain hides that.
    """
    seen = seen or set()
    by_domain: Dict[str, List[Question]] = {}
    for q in items:
        by_domain.setdefault(q.domain, []).append(q)

    picked: List[Question] = []
    for domain in sorted(by_domain):
        pool = by_domain[domain]
        fresh = [q for q in pool if q.id not in seen]
        candidates = fresh or pool
        picked.append(rng.choice(candidates))
    return picked


def select_by_weak_principles(
    questions: Sequence[Question],
    principles: Sequence[Dict],
    rows: Sequence[Dict],
    count: int,
    rng,
    minimum_attempts: int = 4,
) -> Tuple[List[Question], List[str]]:
    """Pick questions that exercise the weakest rules, preferring unseen ones.

    Re-serving the same question tests memory of the answer. Serving a
    different question that turns on the same rule tests the rule.
    """
    stats = summarize(principles, questions, rows)
    ranked = weakest(stats, minimum_attempts) or stats
    seen = {r.get("question_id") for r in rows}
    known = {q.id: q for q in questions}

    picked: List[Question] = []
    used: set = set()
    targeted: List[str] = []

    for stat in ranked:
        if len(picked) >= count:
            break
        pool = [known[q] for q in _ids_for(principles, stat.principle_id) if q in known]
        fresh = [q for q in pool if q.id not in seen and q.id not in used]
        candidates = fresh or [q for q in pool if q.id not in used]
        if not candidates:
            continue
        rng.shuffle(candidates)
        take = candidates[:max(1, count // max(1, len(ranked)))]
        for q in take:
            if len(picked) >= count:
                break
            picked.append(q)
            used.add(q.id)
            if stat.principle_id not in targeted:
                targeted.append(stat.principle_id)

    # Top up from the weakest rules again if rounding left us short.
    if len(picked) < count:
        for stat in ranked:
            for qid in _ids_for(principles, stat.principle_id):
                if len(picked) >= count:
                    break
                if qid in known and qid not in used:
                    picked.append(known[qid])
                    used.add(qid)

    return picked[:count], targeted


def _ids_for(principles: Sequence[Dict], principle_id: str) -> List[str]:
    for p in principles:
        if p.get("id") == principle_id:
            return list(p.get("question_ids") or [])
    return []


# --------------------------------------------------------------------------
# study card
# --------------------------------------------------------------------------

def render_card(principles: Sequence[Dict], width: int = 78) -> str:
    """Generate the reference sheet from the taxonomy.

    Generated rather than written by hand so the card can never drift from the
    rules actually being tested.
    """
    import textwrap

    def wrap(text: str, indent: str = "  ") -> str:
        return textwrap.fill(" ".join(str(text).split()), width=width,
                             initial_indent=indent, subsequent_indent=indent)

    lines: List[str] = []
    lines.append("=" * width)
    lines.append("CISA DECISION RULES - generated from principles.json")
    lines.append("=" * width)
    lines.append(wrap("These are the rules that generate answers across domains. When a "
                      "question is unfamiliar, work out which rule it turns on.", "").strip())
    lines.append("")

    for n, p in enumerate(principles, start=1):
        lines.append("-" * width)
        lines.append("%d. %s" % (n, p.get("name", "")))
        lines.append("-" * width)
        lines.append(wrap(p.get("statement", "")))
        lines.append("")
        lines.append(wrap("WHY: %s" % p.get("why", "")))
        lines.append("")
        lines.append(wrap("TRAP: %s" % p.get("misapplication", "")))
        lines.append("")
        lines.append(wrap("NOT WHEN: %s" % p.get("scope", "")))
        lines.append("")

    lines.append("=" * width)
    return "\n".join(lines)
