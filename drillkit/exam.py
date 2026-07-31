"""Timed mock exam engine.

Different from a drill in every way that matters: questions are sampled to the
published blueprint weights rather than to what you keep missing, there is a
clock, and you get no feedback at all until you submit. The point is to
rehearse pacing and endurance, not to learn individual items.

Exam state is persisted after every action, so a session survives closing the
terminal, and the clock only advances while a sitting is actually open.
"""

from __future__ import annotations

import json
import os
import threading
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .loader import Outline, Question

# ISACA publishes 150 questions in 240 minutes for the CISA exam.
# Verified 2026-07-26; see cisa/outline.json for the source and date.
DEFAULT_QUESTIONS = 150
DEFAULT_MINUTES = 240


class ExamError(Exception):
    """Raised when an exam cannot be built, loaded or resumed."""


# --------------------------------------------------------------------------
# blueprint sampling
# --------------------------------------------------------------------------

def blueprint_counts(weights: Dict[str, int], total: int) -> Dict[str, int]:
    """Split `total` across domains by weight using the largest remainder method.

    Plain rounding does not sum back to the total. Largest remainder does, which
    matters when the whole point is a 150-question exam.
    """
    domains = sorted(weights)
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        raise ExamError("domain weights are missing or sum to zero")

    exact = {d: total * weights[d] / weight_sum for d in domains}
    counts = {d: int(exact[d]) for d in domains}

    shortfall = total - sum(counts.values())
    by_remainder = sorted(domains, key=lambda d: (-(exact[d] - counts[d]), d))
    for d in by_remainder[:shortfall]:
        counts[d] += 1
    return counts


def _redistribute(counts: Dict[str, int], available: Dict[str, int]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Cap each domain at what the bank can supply, spreading the slack elsewhere.

    Returns (final counts, shortfall per domain). While Domains 1-4 are thin,
    an honest exam is one that tells you it could not fill the blueprint.
    """
    final = {}
    shortfall = {}
    spare = 0
    for d, want in counts.items():
        have = available.get(d, 0)
        if have < want:
            final[d] = have
            shortfall[d] = want - have
            spare += want - have
        else:
            final[d] = want

    # Hand the leftovers to domains that still have unused questions, biggest
    # blueprint share first so the mix stays as close to weighted as possible.
    while spare > 0:
        candidates = [d for d in sorted(final, key=lambda x: -counts[x])
                      if available.get(d, 0) > final[d]]
        if not candidates:
            break
        for d in candidates:
            if spare <= 0:
                break
            final[d] += 1
            spare -= 1

    return final, shortfall


def sample_by_blueprint(
    questions: Sequence[Question],
    outline: Outline,
    total: int = DEFAULT_QUESTIONS,
    rng: Optional[random.Random] = None,
) -> Tuple[List[Question], Dict[str, int], Dict[str, int]]:
    """Pick `total` questions weighted by domain, spread evenly across topics.

    Returns (questions in exam order, target counts, shortfall per domain).
    """
    rng = rng or random.Random()

    by_domain: Dict[str, List[Question]] = {}
    for q in questions:
        by_domain.setdefault(q.domain, []).append(q)
    if not by_domain:
        raise ExamError("no questions available to build an exam from")

    # Weights come from the outline, not from whatever happens to be in the
    # bank. A domain with no questions must still appear in the blueprint, so
    # that the shortfall is reported rather than silently redistributed.
    outline_domains = outline.raw.get("domains", {})
    if outline_domains:
        weights = {d: (outline.domain_weight(d) or 1) for d in outline_domains}
    else:
        weights = {d: 1 for d in by_domain}
    for d in by_domain:
        weights.setdefault(d, 1)

    targets = blueprint_counts(weights, total)
    available = {d: len(by_domain.get(d, [])) for d in weights}
    final, shortfall = _redistribute(targets, available)

    picked: List[Question] = []
    for domain, want in final.items():
        picked.extend(_sample_across_topics(by_domain.get(domain, []), want, rng))

    rng.shuffle(picked)
    return picked, targets, shortfall


def _sample_across_topics(pool: List[Question], want: int,
                          rng: random.Random) -> List[Question]:
    """Spread the draw over topics instead of letting one topic dominate.

    Deals round-robin from shuffled per-topic piles, so a domain with one large
    topic and several small ones still produces a balanced sample.
    """
    if want <= 0 or not pool:
        return []
    if want >= len(pool):
        return list(pool)

    piles: Dict[str, List[Question]] = {}
    for q in pool:
        piles.setdefault(q.topic, []).append(q)
    for pile in piles.values():
        rng.shuffle(pile)

    order = sorted(piles, key=lambda t: (-len(piles[t]), t))
    picked: List[Question] = []
    while len(picked) < want:
        dealt = False
        for topic in order:
            if piles[topic]:
                picked.append(piles[topic].pop())
                dealt = True
                if len(picked) == want:
                    break
        if not dealt:
            break
    return picked


# --------------------------------------------------------------------------
# exam state
# --------------------------------------------------------------------------

@dataclass
class ExamState:
    exam_id: str
    cert: str
    created: str
    duration_seconds: int
    question_ids: List[str]
    answers: Dict[str, str] = field(default_factory=dict)
    flagged: List[str] = field(default_factory=list)
    position: int = 0
    elapsed_seconds: float = 0.0
    sittings: int = 0
    submitted: bool = False
    submitted_at: Optional[str] = None
    blueprint: Dict[str, int] = field(default_factory=dict)
    shortfall: Dict[str, int] = field(default_factory=dict)
    seconds_per_question: Dict[str, float] = field(default_factory=dict)
    # question id -> guess | unsure | confident. Captured with the answer, so a
    # question answered then changed keeps the confidence of the final answer.
    # Exams written before this feature simply have an empty dict.
    confidence: Dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.question_ids)

    @property
    def answered(self) -> int:
        return len(self.answers)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.duration_seconds - self.elapsed_seconds)

    @property
    def expired(self) -> bool:
        return self.remaining_seconds <= 0


def exams_dir(cert_results_path: str) -> str:
    return os.path.join(os.path.dirname(cert_results_path), "exams")


def exam_path(cert_results_path: str, exam_id: str) -> str:
    return os.path.join(exams_dir(cert_results_path), "%s.json" % exam_id)


def save(state: ExamState, cert_results_path: str) -> str:
    path = exam_path(cert_results_path, state.exam_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Unique temp name per call. A shared "<file>.tmp" looks atomic but is not:
    # the server is threaded, and one user action can produce two writes in
    # flight at once (answering and rating a question). Two writers sharing one
    # temp file interleave their bytes and the replace publishes the wreckage.
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), threading.get_ident())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(state), fh, indent=2)
        _replace_with_retry(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return path


def _replace_with_retry(tmp: str, path: str, attempts: int = 40) -> None:
    """Atomic publish, with a short retry for Windows file locking.

    os.replace is atomic on both platforms, but on Windows it raises
    PermissionError if anything else has the destination open - including a
    concurrent reader. That is transient, so a brief retry turns a lost save
    into a slightly delayed one. Losing exam state is the thing this file
    exists to prevent.
    """
    for attempt in range(attempts):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.01)


def load(cert_results_path: str, exam_id: str) -> ExamState:
    path = exam_path(cert_results_path, exam_id)
    if not os.path.exists(path):
        raise ExamError("no exam found with id '%s'" % exam_id)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    known = {f for f in ExamState.__dataclass_fields__}
    return ExamState(**{k: v for k, v in data.items() if k in known})


def list_exams(cert_results_path: str) -> List[ExamState]:
    directory = exams_dir(cert_results_path)
    if not os.path.isdir(directory):
        return []
    out = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        try:
            out.append(load(cert_results_path, name[:-5]))
        except (ExamError, json.JSONDecodeError, TypeError):
            continue
    return sorted(out, key=lambda s: s.created, reverse=True)


def new_exam(
    questions: Sequence[Question],
    outline: Outline,
    cert: str,
    total: int = DEFAULT_QUESTIONS,
    minutes: int = DEFAULT_MINUTES,
    rng: Optional[random.Random] = None,
) -> Tuple[ExamState, List[Question]]:
    picked, targets, shortfall = sample_by_blueprint(questions, outline, total, rng)
    state = ExamState(
        exam_id=uuid.uuid4().hex[:8],
        cert=cert.upper(),
        created=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        duration_seconds=minutes * 60,
        question_ids=[q.id for q in picked],
        blueprint=targets,
        shortfall=shortfall,
    )
    return state, picked


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

# ISACA converts raw scores to a 200-800 scale using a psychometric process it
# does not publish, and the raw threshold moves between exam forms. The mapping
# below is a transparent approximation anchored on the two published facts (450
# passes; the scale runs 200-800) plus the widely reported observation that
# passing candidates tend to be around 70% raw. Treat it as a rough gauge of
# where you stand, never as a predicted score.
SCALE_MIN, SCALE_MAX, SCALE_PASS = 200, 800, 450
ASSUMED_PASS_RAW = 0.70


def estimated_scaled_score(raw_fraction: float) -> int:
    raw = max(0.0, min(1.0, raw_fraction))
    if raw <= ASSUMED_PASS_RAW:
        value = SCALE_MIN + (raw / ASSUMED_PASS_RAW) * (SCALE_PASS - SCALE_MIN)
    else:
        above = (raw - ASSUMED_PASS_RAW) / (1.0 - ASSUMED_PASS_RAW)
        value = SCALE_PASS + above * (SCALE_MAX - SCALE_PASS)
    return int(round(value))


@dataclass
class DomainResult:
    domain: str
    name: str
    weight: Optional[int]
    asked: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.asked if self.asked else 0.0


@dataclass
class ExamResult:
    exam_id: str
    total: int
    answered: int
    correct: int
    unanswered: int
    raw_fraction: float
    scaled_estimate: int
    passed_estimate: bool
    elapsed_seconds: float
    duration_seconds: int
    by_domain: List[DomainResult]
    missed: List[Question]
    flagged: List[Question]
    slowest: List[Tuple[Question, float]]
    guessed_right: List[Question]


def score(state: ExamState, questions: Sequence[Question],
          outline: Outline) -> ExamResult:
    lookup = {q.id: q for q in questions}
    ordered = [lookup[qid] for qid in state.question_ids if qid in lookup]

    correct = 0
    unanswered = 0
    missed: List[Question] = []
    per_domain: Dict[str, DomainResult] = {}

    for q in ordered:
        bucket = per_domain.setdefault(q.domain, DomainResult(
            domain=q.domain,
            name=outline.domain_name(q.domain),
            weight=outline.domain_weight(q.domain),
            asked=0, correct=0,
        ))
        bucket.asked += 1

        chosen = state.answers.get(q.id)
        if chosen is None:
            unanswered += 1
            missed.append(q)
            continue
        if chosen == q.answer:
            correct += 1
            bucket.correct += 1
        else:
            missed.append(q)

    total = len(ordered)
    raw = correct / total if total else 0.0

    timed = [(q, state.seconds_per_question.get(q.id, 0.0)) for q in ordered]
    slowest = sorted(timed, key=lambda pair: -pair[1])[:10]

    flagged = [lookup[qid] for qid in state.flagged if qid in lookup]
    # Flagged but answered correctly: you got there, but you were not sure.
    # Worth revisiting even though the score looks fine.
    guessed_right = [q for q in flagged if state.answers.get(q.id) == q.answer]

    return ExamResult(
        exam_id=state.exam_id,
        total=total,
        answered=state.answered,
        correct=correct,
        unanswered=unanswered,
        raw_fraction=raw,
        scaled_estimate=estimated_scaled_score(raw),
        passed_estimate=estimated_scaled_score(raw) >= SCALE_PASS,
        elapsed_seconds=state.elapsed_seconds,
        duration_seconds=state.duration_seconds,
        by_domain=sorted(per_domain.values(), key=lambda d: d.domain),
        missed=missed,
        flagged=flagged,
        slowest=slowest,
        guessed_right=guessed_right,
    )


# --------------------------------------------------------------------------
# clock
# --------------------------------------------------------------------------

class Clock:
    """Wall-clock timer that only runs while a sitting is open.

    Injectable time source so tests do not have to sleep.
    """

    def __init__(self, now=time.time):
        self._now = now
        self._started: Optional[float] = None

    def start(self) -> None:
        self._started = self._now()

    def sitting_seconds(self) -> float:
        if self._started is None:
            return 0.0
        return max(0.0, self._now() - self._started)

    def stop(self) -> float:
        elapsed = self.sitting_seconds()
        self._started = None
        return elapsed


def format_hms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return "%d:%02d:%02d" % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def format_ms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)
