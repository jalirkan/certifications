"""Accuracy roll-ups: weakest areas first."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .loader import Outline, Question
from .store import parse_ts


@dataclass
class Bucket:
    label: str
    attempts: int = 0
    correct: int = 0
    questions_seen: set = field(default_factory=set)

    @property
    def accuracy(self) -> float:
        return self.correct / self.attempts if self.attempts else 0.0


def _bump(buckets: Dict[str, Bucket], key: str, row: Dict) -> None:
    b = buckets.setdefault(key, Bucket(label=key))
    b.attempts += 1
    b.correct += 1 if row.get("correct") else 0
    b.questions_seen.add(row.get("question_id"))


def by_domain(rows: List[Dict]) -> List[Bucket]:
    buckets: Dict[str, Bucket] = {}
    for row in rows:
        _bump(buckets, str(row.get("domain", "?")), row)
    return sorted(buckets.values(), key=lambda b: b.label)


def by_topic(rows: List[Dict]) -> List[Bucket]:
    buckets: Dict[str, Bucket] = {}
    for row in rows:
        key = "D%s%s | %s" % (row.get("domain", "?"), row.get("section", ""), row.get("topic", "?"))
        _bump(buckets, key, row)
    # Weakest first; among equals, the one with more attempts is better evidenced.
    return sorted(buckets.values(), key=lambda b: (b.accuracy, -b.attempts))


def recent(rows: List[Dict], days: int, now: Optional[datetime] = None) -> List[Dict]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    out = []
    for row in rows:
        ts = parse_ts(row.get("ts", ""))
        if ts is not None and ts >= cutoff:
            out.append(row)
    return out


def overall(rows: List[Dict]) -> Tuple[int, int, float]:
    attempts = len(rows)
    correct = sum(1 for r in rows if r.get("correct"))
    return attempts, correct, (correct / attempts if attempts else 0.0)


def study_days(rows: List[Dict]) -> int:
    days = set()
    for row in rows:
        ts = parse_ts(row.get("ts", ""))
        if ts is not None:
            days.add(ts.astimezone().date())
    return len(days)


def unmastered(rows: List[Dict], questions: List[Question]) -> List[Tuple[str, str, int, int]]:
    """Questions missed at least once: (id, topic, misses, attempts)."""
    by_q: Dict[str, List[Dict]] = {}
    for row in rows:
        by_q.setdefault(row["question_id"], []).append(row)

    lookup = {q.id: q for q in questions}
    out = []
    for qid, attempts in by_q.items():
        misses = sum(1 for a in attempts if not a.get("correct"))
        if misses:
            topic = lookup[qid].topic if qid in lookup else attempts[-1].get("topic", "?")
            out.append((qid, topic, misses, len(attempts)))
    return sorted(out, key=lambda r: (-r[2], r[0]))


def coverage_summary(rows: List[Dict], questions: List[Question]) -> Tuple[int, int]:
    """(distinct questions attempted, total questions in bank)."""
    seen = {r.get("question_id") for r in rows}
    ids = {q.id for q in questions}
    return len(seen & ids), len(ids)


def domain_label(outline: Outline, domain: str) -> str:
    name = outline.domain_name(domain)
    weight = outline.domain_weight(domain)
    if name and weight:
        return "D%s %s [%d%%]" % (domain, name, weight)
    if name:
        return "D%s %s" % (domain, name)
    return "D%s" % domain
