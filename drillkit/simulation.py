"""Synthetic learners, and scoring the diagnostics against them.

This is the piece that lets the project make claims about itself.

The tool asserts two things that were never tested: that reporting weakness by
decision rule finds problems a topic report hides, and that item analysis
identifies badly written questions. Neither can be established from real study
history, because with real data nobody knows the right answer in advance - if
the tool reports a weakness in `evidence-quality`, there is no independent way
to confirm the learner actually has one.

Synthetic data inverts that. Plant a weakness, generate a history, run the
diagnostic, and check whether it found what you put there. The answer is known
before you look.

Two properties make this an instrument rather than a decoration:

* **A negative control on every check.** The same check runs against a learner
  with nothing planted, and any "detection" there is a false positive. A
  detection rate reported without its false-positive rate is not evidence - a
  diagnostic that fires on a uniformly average learner would send someone to
  study something that is not wrong with them.
* **A sample-size sweep.** Each check runs at several history sizes, so the
  output is a curve rather than a verdict, and the curve answers the question
  that actually blocks the project: how many answers must exist before this
  diagnostic says something true.

Rates carry Wilson intervals, because CLAUDE.md 3.6 applies to the harness's own
statistics exactly as it applies to the learner's. Two successes out of two runs
is not a working diagnostic.

**Do not tune a diagnostic to make a check pass.** A failing check at realistic
sample sizes is the most valuable output available here. Adjusting thresholds
until the number looks good converts the instrument back into a decoration.

Generation is driven by the **real scheduler**, not by uniform sampling. A
learner sits down, `scheduler.select` picks a set, they answer it, repeat. That
matters: the scheduler concentrates repeats on missed questions, which is what
gives item analysis anything to work with, and it means check 6 measures the
real selection code rather than a model of it.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import (
    calibration as calibration_mod,
    itemanalysis,
    loader,
    principles as principles_mod,
    scheduler,
    stats as stats_mod,
    store,
)
from .loader import Question

# Every synthetic row carries this in its session id. Rule 2 of the brief: a
# synthetic row that reaches the real log is unrecoverable, because nothing in
# the record would distinguish it afterwards.
SYNTHETIC_SESSION_PREFIX = "sim"
SYNTHETIC_PROFILE = "__synthetic__"

# Where a completed sweep is persisted, beside DETECTION.md at the repo root.
RESULTS_FILE = "detection.json"

QUESTIONS_PER_SESSION = 20
DEFAULT_SAMPLE_SIZES = (100, 300, 1000, 3000)
DEFAULT_SEEDS = 200


class SimulationError(Exception):
    """Raised when the harness is asked to do something unsafe."""


# --------------------------------------------------------------------------
# the learner
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Weakness:
    """A planted deficit. `ability` is p(correct) on matching questions."""
    axis: str          # principle | topic | domain
    key: str
    ability: float


@dataclass
class LearnerSpec:
    """A synthetic learner, specified explicitly and reproducibly.

    Independence between questions is a deliberate simplification: a real
    learner who misses a question learns something from the explanation, and
    these learners do not. That makes detection *harder* than reality for the
    repeat-driven checks (a real learner's second attempt is better than their
    first, which sharpens the signal), and slightly easier for the ability
    checks (no drift to blur the planted deficit). It is noted in DETECTION.md
    rather than hidden.
    """
    seed: int = 0
    attempts: int = 1000
    baseline: float = 0.78
    weaknesses: Tuple[Weakness, ...] = ()

    # Item-level plants. These describe the *question*, not the learner.
    miskeyed: Tuple[str, ...] = ()
    no_discrimination: Tuple[str, ...] = ()
    persistent: Tuple[str, ...] = ()

    # Confidence. "calibrated" tracks correctness; "flat" carries no
    # information, which is the failure calibration.py exists to name.
    confidence_mode: str = "calibrated"
    confident_wrong: Tuple[str, ...] = ()

    days: int = 45
    mode: str = "smart"

    def ability_for(self, q: Question, rules_by_question: Dict[str, List[str]]) -> float:
        """Probability this learner answers `q` correctly."""
        if q.id in self.no_discrimination:
            # Everyone performs the same on it, regardless of ability. This is
            # what a question that measures nothing looks like.
            return 0.5
        if q.id in self.miskeyed:
            # The *key* is wrong, so someone who knows the material is marked
            # incorrect most of the time. Modelling this as an ordinary hard
            # question would never produce the KEY_CHALLENGED signature, which
            # is the whole thing the check is asking about.
            return 0.20
        if q.id in self.confident_wrong:
            # Sure, and wrong: the quadrant nothing else in the tool surfaces.
            return 0.25
        if q.id in self.persistent:
            return 0.05
        worst = self.baseline
        for w in self.weaknesses:
            if _matches(w, q, rules_by_question):
                worst = min(worst, w.ability)
        return worst


def _matches(w: Weakness, q: Question, rules_by_question: Dict[str, List[str]]) -> bool:
    if w.axis == "principle":
        return w.key in rules_by_question.get(q.id, ())
    if w.axis == "topic":
        return q.topic == w.key
    if w.axis == "domain":
        return q.domain == w.key
    raise SimulationError("unknown weakness axis '%s'" % w.axis)


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

@dataclass
class Bank:
    """The real question bank plus the lookups generation needs."""
    questions: List[Question]
    rules: List[Dict[str, Any]]
    rules_by_question: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, cert: str = "cisa") -> "Bank":
        questions = loader.load_questions(cert)
        rules = loader.load_principles(cert)
        return cls(questions=questions, rules=rules,
                   rules_by_question=loader.principle_index(rules))

    def by_id(self) -> Dict[str, Question]:
        return {q.id: q for q in self.questions}


def generate(spec: LearnerSpec, bank: Bank) -> List[Dict[str, Any]]:
    """Produce an attempt log for this learner.

    Rows are built through the real `store.Attempt` dataclass, never as
    hand-written dicts - a hand-built row would drift from the schema and the
    harness would quietly stop measuring the actual system.
    """
    rng = random.Random(spec.seed)
    rows: List[Dict[str, Any]] = []
    history: Dict[str, List[Dict[str, Any]]] = {}

    sessions = max(1, spec.attempts // QUESTIONS_PER_SESSION)
    start = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    spacing = timedelta(days=max(1, spec.days) / sessions)

    served = 0
    for index in range(sessions):
        when = start + spacing * index
        remaining = spec.attempts - served
        if remaining <= 0:
            break
        want = min(QUESTIONS_PER_SESSION, remaining)

        # The real selector, so the harness measures the shipped scheduler
        # rather than a stand-in for it.
        picked = scheduler.select(bank.questions, history, want,
                                  mode=spec.mode, now=when, rng=rng)
        session_id = "%s-%d-%03d" % (SYNTHETIC_SESSION_PREFIX, spec.seed, index)

        for q in picked:
            p = spec.ability_for(q, bank.rules_by_question)
            correct = rng.random() < p
            chosen = _chosen_letter(q, correct, spec, rng)
            confidence = _confidence(q, correct, spec, rng)

            attempt = store.Attempt(
                ts=when.astimezone().isoformat(timespec="seconds"),
                session=session_id,
                question_id=q.id,
                cert="CISA",
                domain=q.domain,
                section=q.section,
                topic=q.topic,
                chosen=chosen,
                answer=q.answer,
                correct=correct,
                seconds=round(rng.uniform(20, 90), 1),
                mode=spec.mode,
                confidence=confidence,
            )
            row = asdict(attempt)
            rows.append(row)
            history.setdefault(q.id, []).append(row)
            served += 1
            when = when + timedelta(seconds=45)

    return rows


def _chosen_letter(q: Question, correct: bool, spec: LearnerSpec,
                   rng: random.Random) -> str:
    """Which option was picked.

    Matters for item analysis: a miskeyed question is one where the crowd
    converges on a single distractor, which is what KEY_CHALLENGED detects.
    Scattering wrong answers uniformly would hide exactly that signature.
    """
    if correct:
        return q.answer
    distractors = [k for k in loader.OPTION_KEYS if k != q.answer]
    if q.id in spec.miskeyed:
        # Everyone who gets it "wrong" picks the same option - the fingerprint
        # of a question whose key is wrong.
        return distractors[0]
    return rng.choice(distractors)


def _confidence(q: Question, correct: bool, spec: LearnerSpec,
                rng: random.Random) -> str:
    if spec.confidence_mode == "none":
        return ""
    if q.id in spec.confident_wrong:
        # Confident every time, right or wrong. Rating these honestly would
        # make them ordinary misses and there would be nothing to detect.
        return "confident"
    if spec.confidence_mode == "flat":
        # Confidence carries no information about correctness. This is the
        # failure mode calibration.py exists to name, not mere overconfidence.
        return rng.choice(("guess", "unsure", "confident"))
    # Calibrated: confident when right, hedged when wrong, with some slippage
    # so the relationship is strong rather than perfect.
    if correct:
        return "confident" if rng.random() < 0.8 else "unsure"
    return "guess" if rng.random() < 0.5 else "unsure"


# --------------------------------------------------------------------------
# writing, when a run is being inspected rather than scored
# --------------------------------------------------------------------------

def write(rows: Sequence[Dict[str, Any]], path: str) -> str:
    """Append synthetic rows to `path` through the real writer.

    Refuses to touch a file that already holds anything but synthetic rows.
    Rule 1 and 2 of the brief: real study history is small and unrecoverable,
    and nothing in a row distinguishes it after the fact.
    """
    guard_path(path)
    for row in rows:
        store.append(path, store.Attempt(**row))
    return path


def guard_path(path: str) -> None:
    """Refuse any path that holds real attempts."""
    real = loader.results_path("cisa", None)
    if os.path.abspath(path) == os.path.abspath(real):
        raise SimulationError(
            "refusing to write synthetic rows to the real attempt log (%s)" % real)
    if not os.path.exists(path):
        return
    for row in store.load(path):
        session = str(row.get("session", ""))
        if not session.startswith(SYNTHETIC_SESSION_PREFIX + "-"):
            raise SimulationError(
                "%s already contains non-synthetic attempts; refusing to mix "
                "real and generated history" % path)


def is_synthetic(rows: Sequence[Dict[str, Any]]) -> bool:
    return all(str(r.get("session", "")).startswith(SYNTHETIC_SESSION_PREFIX + "-")
               for r in rows)


# --------------------------------------------------------------------------
# what gets planted, and what counts as finding it
# --------------------------------------------------------------------------

TOP_N = 3                  # "surfaced it" means: in the weakest this many
SERVE_PERCENTILE = 0.90    # check 6: how high a planted question must rank

# The bar a check must clear to be called trustworthy, judged at the pessimistic
# end of both intervals. Named rather than inlined because the report and the
# app both state them, and a threshold quoted in prose that disagrees with the
# one in the code would be worse than no threshold at all.
TRUST_DETECTION = 0.80        # detection, at the bottom of its interval
TRUST_FALSE_POSITIVE = 0.20   # false positives, at the top of theirs


@dataclass
class Plant:
    """A learner, plus the identity of what was hidden inside them."""
    spec: LearnerSpec
    targets: Dict[str, Any]


@dataclass
class Check:
    id: str
    title: str
    planted: str
    diagnostic: str
    family: str
    detect: Callable[[List[Dict[str, Any]], "Bank", Dict[str, Any]], bool]
    note: str = ""


def _eligible_rules(bank: Bank) -> List[Dict[str, Any]]:
    """Rules with enough questions, over enough topics, to be findable at all.

    A rule attached to three questions inside one topic cannot demonstrate the
    asymmetry claim in either direction, so including it would measure the
    bank's sparsity rather than the diagnostic.
    """
    by_id = bank.by_id()
    out = []
    for rule in bank.rules:
        qids = [q for q in (rule.get("question_ids") or []) if q in by_id]
        topics = {by_id[q].topic for q in qids}
        if len(qids) >= 8 and len(topics) >= 4:
            out.append(rule)
    return out


def _eligible_topics(bank: Bank) -> List[str]:
    counts: Dict[str, int] = {}
    for q in bank.questions:
        counts[q.topic] = counts.get(q.topic, 0) + 1
    return sorted(t for t, n in counts.items() if n >= 5)


def _topic_label(q: Question) -> str:
    """Mirror the label stats.by_topic() builds, so comparisons line up."""
    return "D%s%s | %s" % (q.domain, q.section, q.topic)


# ---- the plants ----------------------------------------------------------

def plant_rule(bank: Bank, seed: int, attempts: int) -> Plant:
    rng = random.Random("rule-%d" % seed)
    rule = rng.choice(_eligible_rules(bank))
    return Plant(
        spec=LearnerSpec(seed=seed, attempts=attempts,
                         weaknesses=(Weakness("principle", rule["id"], 0.30),),
                         confidence_mode="none"),
        targets={"rule": rule["id"]},
    )


def plant_topic(bank: Bank, seed: int, attempts: int) -> Plant:
    rng = random.Random("topic-%d" % seed)
    topic = rng.choice(_eligible_topics(bank))
    return Plant(
        spec=LearnerSpec(seed=seed, attempts=attempts,
                         weaknesses=(Weakness("topic", topic, 0.30),),
                         confidence_mode="none"),
        targets={"topic": topic},
    )


def plant_items(bank: Bank, seed: int, attempts: int) -> Plant:
    """Three separate item pathologies, on three separate questions."""
    rng = random.Random("items-%d" % seed)
    picked = rng.sample([q.id for q in bank.questions], 5)
    return Plant(
        spec=LearnerSpec(seed=seed, attempts=attempts,
                         no_discrimination=(picked[0],),
                         miskeyed=(picked[1],),
                         persistent=tuple(picked[2:5]),
                         confidence_mode="none"),
        targets={"no_discrimination": picked[0], "miskeyed": picked[1],
                 "persistent": tuple(picked[2:5])},
    )


def plant_confidence(bank: Bank, seed: int, attempts: int) -> Plant:
    rng = random.Random("conf-%d" % seed)
    marked = tuple(rng.sample([q.id for q in bank.questions], 4))
    return Plant(
        spec=LearnerSpec(seed=seed, attempts=attempts,
                         confident_wrong=marked,
                         weaknesses=(Weakness("domain", "4", 0.30),),
                         confidence_mode="flat"),
        targets={"confident_wrong": marked},
    )


def clean_learner(seed: int, attempts: int) -> LearnerSpec:
    """No plant of any kind. Any detection against this is a false positive."""
    return LearnerSpec(seed=seed, attempts=attempts, confidence_mode="calibrated")


PLANTS: Dict[str, Callable[[Bank, int, int], Plant]] = {
    "rule": plant_rule,
    "topic": plant_topic,
    "items": plant_items,
    "confidence": plant_confidence,
}


# ---- the detectors -------------------------------------------------------

def _weakest_rule_ids(rows, bank: Bank) -> List[str]:
    summary = principles_mod.summarize(bank.rules, bank.questions, rows)
    ranked = principles_mod.weakest(summary) or summary
    return [s.principle_id for s in ranked]


def detect_rule_axis(rows, bank: Bank, targets) -> bool:
    """Check 1: is the planted rule near the top of the rule diagnostic?"""
    return targets["rule"] in _weakest_rule_ids(rows, bank)[:TOP_N]


def detect_topic_axis(rows, bank: Bank, targets) -> bool:
    """Check 2: is the planted topic the weakest topic reported?"""
    buckets = stats_mod.by_topic(rows)
    return bool(buckets) and buckets[0].label.endswith("| %s" % targets["topic"])


def _rule_topic_labels(bank: Bank, rule_id: str) -> set:
    by_id = bank.by_id()
    rule = next((r for r in bank.rules if r["id"] == rule_id), None)
    if rule is None:
        return set()
    return {_topic_label(by_id[q]) for q in (rule.get("question_ids") or [])
            if q in by_id}


def _topic_axis_points_at_rule(rows, bank: Bank, targets) -> bool:
    buckets = stats_mod.by_topic(rows)
    if not buckets:
        return False
    return buckets[0].label in _rule_topic_labels(bank, targets["rule"])


def detect_asymmetry(rows, bank: Bank, targets) -> bool:
    """Check 3, the claim the whole principle axis rests on.

    The rule axis surfaces the planted rule *and* the topic axis does not point
    at it - meaning someone reading only the topic report would go and study
    the wrong thing.
    """
    return (detect_rule_axis(rows, bank, targets)
            and not _topic_axis_points_at_rule(rows, bank, targets))


def detect_asymmetry_rule_half(rows, bank: Bank, targets) -> bool:
    """Half of check 3, reported separately so the reader sees which half carries it."""
    return detect_rule_axis(rows, bank, targets)


def detect_asymmetry_topic_half(rows, bank: Bank, targets) -> bool:
    """The other half: the topic axis fails to point at the cause."""
    return not _topic_axis_points_at_rule(rows, bank, targets)


def _rewrite_flags(rows, bank: Bank) -> Dict[str, List[str]]:
    item_stats = itemanalysis.analyze(rows, bank.questions,
                                      itemanalysis.MIN_ATTEMPTS_STATS)
    return {s.question_id: s.flags for s in itemanalysis.needs_rewrite(item_stats)}


def detect_dead_item(rows, bank: Bank, targets) -> bool:
    """Check 4: a question that measures nothing."""
    return targets["no_discrimination"] in _rewrite_flags(rows, bank)


def detect_miskeyed(rows, bank: Bank, targets) -> bool:
    """Check 5: wrong answers converge on a single distractor."""
    flags = _rewrite_flags(rows, bank).get(targets["miskeyed"], [])
    return any(f.split(":")[0] in ("KEY_CHALLENGED", "NEG_DISCRIMINATION")
               for f in flags)


def detect_scheduler_returns(rows, bank: Bank, targets) -> bool:
    """Check 6: do persistently-missed questions come back more often?

    The threshold is deliberately strict - every planted question must reach
    the top decile by serve count. The looser test (mean above mean) fires
    roughly half the time on an unplanted learner, which would make the check
    uninformative rather than merely weak.
    """
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["question_id"]] = counts.get(r["question_id"], 0) + 1
    if len(counts) < 10:
        return False
    ordered = sorted(counts.values())
    cutoff = ordered[min(len(ordered) - 1, int(len(ordered) * SERVE_PERCENTILE))]
    return all(counts.get(qid, 0) >= cutoff and counts.get(qid, 0) > 1
               for qid in targets["persistent"])


def detect_dangerous_quadrant(rows, bank: Bank, targets) -> bool:
    """Check 7: are the planted confident-and-wrong answers surfaced?"""
    listed = {item["question_id"]
              for item in calibration_mod.dangerous(rows, bank.by_id())}
    return any(qid in listed for qid in targets["confident_wrong"])


CHECKS: List[Check] = [
    Check("1", "Weak decision rule is surfaced",
          "A learner 30% accurate on every question governed by one rule",
          "principles.weakest()", "rule", detect_rule_axis,
          "Detected when the planted rule lands in the weakest %d." % TOP_N),
    Check("2", "Weak topic is surfaced",
          "A learner 30% accurate on every question in one topic",
          "stats.by_topic()", "topic", detect_topic_axis,
          "Detected when the planted topic ranks weakest of all topics."),
    Check("3", "Rule axis finds what the topic axis hides",
          "A rule-level weakness spread thinly across many topics",
          "principles vs stats", "rule", detect_asymmetry,
          "The claim the principle axis exists for. Both halves must hold."),
    Check("3a", "- rule half: the rule axis finds it",
          "Same learner as check 3", "principles.weakest()", "rule",
          detect_asymmetry_rule_half, "Component of check 3."),
    Check("3b", "- topic half: the topic axis misses it",
          "Same learner as check 3", "stats.by_topic()", "rule",
          detect_asymmetry_topic_half, "Component of check 3."),
    Check("4", "A question that measures nothing is flagged",
          "One question answered at chance regardless of ability",
          "itemanalysis.needs_rewrite()", "items", detect_dead_item),
    Check("5", "A miskeyed question is flagged",
          "One question whose wrong answers converge on a single distractor",
          "itemanalysis.needs_rewrite()", "items", detect_miskeyed),
    Check("6", "Persistent misses come back sooner",
          "Three questions the learner reliably gets wrong",
          "scheduler.select()", "items", detect_scheduler_returns,
          "Detected when all three reach the top decile by times served."),
    Check("7", "Confident-and-wrong answers are surfaced",
          "Four questions answered confidently and incorrectly",
          "calibration.dangerous()", "confidence", detect_dangerous_quadrant),
]


def check_by_id(check_id: str) -> Check:
    for check in CHECKS:
        if check.id == check_id:
            return check
    raise SimulationError("no check '%s'" % check_id)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

@dataclass
class Rate:
    """A proportion of runs, with the interval that says how much to trust it."""
    hits: int = 0
    runs: int = 0

    @property
    def rate(self) -> Optional[float]:
        return (self.hits / self.runs) if self.runs else None

    @property
    def interval(self) -> Tuple[float, float]:
        return itemanalysis.wilson_interval(self.hits, self.runs)

    def as_dict(self) -> Dict[str, Any]:
        low, high = self.interval
        return {"hits": self.hits, "runs": self.runs, "rate": self.rate,
                "low": low if self.runs else None,
                "high": high if self.runs else None}


def measure_rule_coverage(rows, bank: Bank, targets) -> Optional[float]:
    """How much of a rule weakness you would reach by studying the top topics.

    Check 3 asks a yes/no question and the answer turns out to be no: on the
    real bank the topic axis *does* point at a planted rule weakness. This
    measures what that pointing is worth, which is the part that survives.

    A rule spans many topics. Studying the three weakest topics reaches
    whatever fraction of the rule's questions happens to live there; drilling
    the rule reaches all of them. The gap between those two numbers is the
    honest residual value of the rule axis once the binary claim has failed.
    """
    by_id = bank.by_id()
    rule = next((r for r in bank.rules if r["id"] == targets["rule"]), None)
    if rule is None:
        return None
    qids = [q for q in (rule.get("question_ids") or []) if q in by_id]
    if not qids:
        return None
    top_labels = {b.label for b in stats_mod.by_topic(rows)[:TOP_N]}
    reached = sum(1 for q in qids if _topic_label(by_id[q]) in top_labels)
    return reached / len(qids)


MEASURES: Dict[str, Tuple[str, str, Callable]] = {
    "rule_coverage": (
        "rule", "Share of a planted rule's questions reached by studying the "
                "three weakest topics", measure_rule_coverage),
}


@dataclass
class CellResult:
    """One check at one sample size: detection beside its false-positive rate."""
    check_id: str
    attempts: int
    detection: Rate
    false_positive: Rate

    @property
    def trustworthy(self) -> bool:
        """Detects reliably *and* rarely fires on a learner with nothing wrong.

        Both halves are required. A check that fires on everyone detects
        everything and means nothing.
        """
        d, f = self.detection, self.false_positive
        if d.rate is None or f.rate is None:
            return False
        # Judged on the conservative end of detection and the pessimistic end
        # of false positives, so a thin run cannot look trustworthy by luck.
        return (d.interval[0] >= TRUST_DETECTION
                and f.interval[1] <= TRUST_FALSE_POSITIVE)

    def as_dict(self) -> Dict[str, Any]:
        return {"check": self.check_id, "attempts": self.attempts,
                "detection": self.detection.as_dict(),
                "false_positive": self.false_positive.as_dict(),
                "trustworthy": self.trustworthy}


def run_sweep(bank: Bank,
              checks: Sequence[Check] = tuple(CHECKS),
              sizes: Sequence[int] = DEFAULT_SAMPLE_SIZES,
              seeds: int = DEFAULT_SEEDS,
              progress: Optional[Callable[[str], None]] = None,
              measures: Optional[Dict[str, List[float]]] = None
              ) -> List[CellResult]:
    """Score every check at every sample size, with a negative control.

    Generation is shared per (family, seed, size): checks 4, 5 and 6 read the
    same item-plant learner, and every check's negative control reads one
    clean learner. That is a cost saving, not a shortcut - the plants within a
    family sit on different questions and do not interact.
    """
    results: List[CellResult] = []
    families = sorted({c.family for c in checks})

    for attempts in sizes:
        if progress:
            progress("n=%d" % attempts)
        cells = {c.id: CellResult(c.id, attempts, Rate(), Rate()) for c in checks}

        for seed in range(seeds):
            # One clean learner serves as the control for every check.
            control_rows = generate(clean_learner(seed, attempts), bank)
            planted: Dict[str, Plant] = {}
            planted_rows: Dict[str, List[Dict[str, Any]]] = {}
            for family in families:
                plant = PLANTS[family](bank, seed, attempts)
                planted[family] = plant
                planted_rows[family] = generate(plant.spec, bank)

            for check in checks:
                targets = planted[check.family].targets
                cell = cells[check.id]

                if check.detect(planted_rows[check.family], bank, targets):
                    cell.detection.hits += 1
                cell.detection.runs += 1

                # Same check, same targets, a learner with nothing wrong.
                if check.detect(control_rows, bank, targets):
                    cell.false_positive.hits += 1
                cell.false_positive.runs += 1

            if measures is not None:
                for name, (family, _, fn) in MEASURES.items():
                    if family not in planted:
                        continue
                    value = fn(planted_rows[family], bank, planted[family].targets)
                    if value is not None:
                        measures.setdefault("%s@%d" % (name, attempts), []).append(value)

        results.extend(cells[c.id] for c in checks)
    return results


def results_payload(results: Sequence[CellResult], bank: Bank, seeds: int,
                    sizes: Sequence[int],
                    measures: Optional[Dict[str, List[float]]] = None,
                    generated: Optional[str] = None) -> Dict[str, Any]:
    """The sweep as structured data, for anything that is not markdown.

    Written beside DETECTION.md so the app can show the same numbers without
    re-running anything. A full sweep is roughly twelve minutes; a screen that
    recomputed on load would be unusable, and one that parsed the markdown back
    out would break the first time the prose changed.

    The check metadata travels with the numbers deliberately. A detection rate
    is meaningless without knowing what was planted to produce it, and a reader
    who has the JSON but not this module should still be able to tell.
    """
    measures = measures or {}
    ids = [c.id for c in CHECKS if any(r.check_id == c.id for r in results)]
    return {
        "generated": generated or datetime.now(timezone.utc)
                                          .astimezone().isoformat(timespec="seconds"),
        "seeds": seeds,
        "sizes": list(sizes),
        "bank": {"questions": len(bank.questions), "rules": len(bank.rules)},
        "thresholds": {
            "detection_floor": TRUST_DETECTION,
            "false_positive_ceiling": TRUST_FALSE_POSITIVE,
        },
        "checks": [
            {
                "id": check.id,
                "title": check.title,
                "planted": check.planted,
                "diagnostic": check.diagnostic,
                "note": check.note,
                "component": check.id.rstrip("ab") != check.id,
                "trustworthy_from": trustworthy_from(results, check.id),
                "cells": [
                    cell.as_dict()
                    for cell in sorted((r for r in results if r.check_id == check.id),
                                       key=lambda r: r.attempts)
                ],
            }
            for check in CHECKS if check.id in ids
        ],
        "measures": [
            {
                "name": name,
                "label": label,
                "points": [
                    {"attempts": size,
                     "mean": sum(values) / len(values),
                     "runs": len(values)}
                    for size, values in (
                        (s, measures.get("%s@%d" % (name, s), [])) for s in sizes)
                    if values
                ],
            }
            for name, (_family, label, _fn) in MEASURES.items()
        ],
        "findings": _findings(results, sizes),
    }


def write_results(payload: Dict[str, Any], path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path


def load_results(path: str) -> Optional[Dict[str, Any]]:
    """Read a persisted sweep. None when none has been run."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return None
    return data if isinstance(data, dict) else None


def render_report(results: Sequence[CellResult], bank: Bank, seeds: int,
                  sizes: Sequence[int],
                  measures: Optional[Dict[str, List[float]]] = None,
                  generated: Optional[str] = None) -> str:
    """The detection report card, as committed markdown.

    Written for someone who has never seen the repository, and written to be
    readable when the answer is unflattering.
    """
    measures = measures or {}
    when = generated or datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    ids = [c.id for c in CHECKS if any(r.check_id == c.id for r in results)]
    out: List[str] = []
    w = out.append

    w("# Detection report card")
    w("")
    w("*Generated by `python drill.py simulate --write` on %s. "
      "Do not edit by hand.*" % when)
    w("")
    w("This file exists because the study system makes claims about itself, and "
      "claims should be tested. Every number below comes from planting a known "
      "weakness in a synthetic learner, running the real diagnostic over the "
      "generated history, and checking whether it found what was planted.")
    w("")
    w("**How to read it.** A detection rate on its own means nothing. Beside it "
      "is the *false-positive rate*: the same check run against a learner with "
      "nothing wrong. A diagnostic that fires on everybody detects everything "
      "and tells you nothing, and would send you off to study a weakness you do "
      "not have. Both rates carry 95%% Wilson intervals, because %d runs is a "
      "sample like any other." % seeds)
    w("")
    w("A check is called **trustworthy** only where detection is at least %d%% "
      "at the bottom of its interval *and* false positives are at most %d%% at "
      "the top of theirs." % (round(TRUST_DETECTION * 100),
                              round(TRUST_FALSE_POSITIVE * 100)))
    w("")
    w("Method: %d seeds per cell, sample sizes %s, drawn against the real "
      "bank of %d questions and %d decision rules. Histories are generated "
      "through the real scheduler and written as real `store.Attempt` rows."
      % (seeds, ", ".join(str(s) for s in sizes), len(bank.questions),
         len(bank.rules)))
    w("")
    w("---")
    w("")
    w("## Summary")
    w("")
    w("| # | Check | Diagnostic | Trustworthy from |")
    w("|---|---|---|---|")
    for cid in ids:
        check = check_by_id(cid)
        n = trustworthy_from(results, cid)
        verdict = ("%d answers" % n) if n else "**never, in this sweep**"
        w("| %s | %s | `%s` | %s |" % (cid, check.title, check.diagnostic, verdict))
    w("")
    w("---")
    w("")
    w("## What this says")
    w("")
    for line in _findings(results, sizes):
        w(line)
        w("")
    w("---")
    w("")
    w("## Per check")
    w("")

    for cid in ids:
        check = check_by_id(cid)
        cells = sorted((r for r in results if r.check_id == cid),
                       key=lambda r: r.attempts)
        w("### %s. %s" % (cid, check.title))
        w("")
        w("**Planted:** %s  " % check.planted)
        w("**Diagnostic:** `%s`" % check.diagnostic)
        if check.note:
            w("  ")
            w("%s" % check.note)
        w("")
        w("| Answers | Detected | 95% CI | False positive | 95% CI | Trustworthy |")
        w("|---|---|---|---|---|---|")
        for cell in cells:
            d, f = cell.detection, cell.false_positive
            w("| %d | %s | %s | %s | %s | %s |" % (
                cell.attempts, _pct(d.rate), _ci(d), _pct(f.rate), _ci(f),
                "yes" if cell.trustworthy else "—"))
        w("")

    if measures:
        w("---")
        w("")
        w("## Measured, not scored")
        w("")
        for name, (_, label, _fn) in MEASURES.items():
            points = [(size, measures.get("%s@%d" % (name, size), []))
                      for size in sizes]
            points = [(s, v) for s, v in points if v]
            if not points:
                continue
            w("**%s**" % label)
            w("")
            w("| Answers | Mean |")
            w("|---|---|")
            for size, values in points:
                w("| %d | %.0f%% |" % (size, 100 * sum(values) / len(values)))
            w("")
    return "\n".join(out) + "\n"


def _findings(results: Sequence[CellResult], sizes: Sequence[int]) -> List[str]:
    """Plain-language conclusions, computed from the numbers rather than typed.

    Hand-writing the interpretation would leave it asserting last month's result
    after the next re-run. Every sentence below is derived from the cells, so a
    change in the data changes the prose with it.
    """
    lines: List[str] = []
    biggest = max(sizes)
    at = {(r.check_id, r.attempts): r for r in results}

    def cell(cid, n):
        return at.get((cid, n))

    works, never = [], []
    for check in CHECKS:
        if not any(r.check_id == check.id for r in results):
            continue
        if check.id.endswith(("a", "b")):
            continue  # components, discussed with their parent
        n = trustworthy_from(results, check.id)
        (works if n else never).append((check, n))

    if works:
        lines.append("**What holds up.** " + "; ".join(
            "*%s* from about **%d answers**" % (c.title, n) for c, n in works)
            + ".")

    for check, _ in never:
        big = cell(check.id, biggest)
        if big is None:
            continue
        d, f = big.detection, big.false_positive
        small = cell(check.id, min(sizes))
        detail = []
        if f.rate is not None and f.interval[1] > 0.20:
            detail.append(
                "at %d answers it also fires on **%s** of learners with nothing "
                "planted, so a hit carries little information"
                % (biggest, _pct(f.rate)))
        if d.rate is not None and d.rate < 0.5:
            detail.append("it detects only %s of planted cases at %d answers"
                          % (_pct(d.rate), biggest))
        if (small and small.detection.rate is not None and d.rate is not None
                and d.rate + 0.10 < small.detection.rate):
            detail.append(
                "detection *falls* as history grows - %s at %d answers against "
                "%s at %d, which is the signature of a claim that is wrong "
                "rather than one that is merely under-powered"
                % (_pct(d.rate), biggest, _pct(small.detection.rate), min(sizes)))
        if not detail:
            detail.append("it never reached the bar inside the sizes swept")
        body = detail[0][0].upper() + detail[0][1:]
        if len(detail) > 1:
            body += ". " + "; and ".join(
                d[0].upper() + d[1:] for d in detail[1:])
        lines.append("**%s (check %s) does not hold.** %s."
                     % (check.title, check.id, body))

    # The asymmetry claim gets its own paragraph: it is the justification for
    # an entire diagnostic axis, so a bare row in a table under-reports it.
    rule_half = cell("3a", biggest)
    topic_half = cell("3b", biggest)
    if rule_half and topic_half:
        lines.append(
            "**On the asymmetry claim specifically.** The rule axis finds a "
            "planted rule weakness %s of the time at %d answers. The topic axis "
            "*also* finds it: the weakest topic is one of the rule's own topics "
            "in %s of runs. The claim that a rule-level weakness hides from a "
            "topic report does not reproduce against this bank. The reason is "
            "visible in the data rather than mysterious - rules are not spread "
            "evenly over topics here, and the median rule has some topic where "
            "most of the questions are governed by it, so a rule weakness drags "
            "that topic down far enough to rank it worst. The rule axis is "
            "still the more useful readout, because it names one transferable "
            "cause instead of one affected subject, but that is a different and "
            "weaker claim than the one currently written down."
            % (_pct(rule_half.detection.rate), biggest,
               _pct(1 - (topic_half.detection.rate or 0))))

    lines.append(
        "**A caution about what is *not* modelled.** These learners do not "
        "improve: a missed question is missed at the same rate next time. Real "
        "learners read the explanation and get better, which sharpens the "
        "repeat-driven checks and blurs the ability ones. Questions are also "
        "treated as independent, which they are not. Treat the sample sizes "
        "above as the right order of magnitude, not as precise thresholds.")
    return lines


def _pct(value: Optional[float]) -> str:
    return "—" if value is None else "%.0f%%" % (100 * value)


def _ci(rate: Rate) -> str:
    if not rate.runs:
        return "—"
    low, high = rate.interval
    return "%.0f–%.0f%%" % (100 * low, 100 * high)


def trustworthy_from(results: Sequence[CellResult], check_id: str
                     ) -> Optional[int]:
    """Smallest swept sample size at which this check becomes trustworthy.

    None means it never got there inside the sizes swept, which is a finding
    rather than a gap - it says the diagnostic needs more history than the
    sweep covered, and possibly more than the learner will ever produce.
    """
    for cell in sorted((r for r in results if r.check_id == check_id),
                       key=lambda r: r.attempts):
        if cell.trustworthy:
            return cell.attempts
    return None
