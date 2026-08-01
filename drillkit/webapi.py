"""JSON API over the study engine, for the local web front end.

Pure functions returning JSON-able dicts, deliberately independent of HTTP so
they can be tested without a server.

**Answer keys never reach the client before the user commits.** A question sent
to the browser carries the stem and the options and nothing else; the key, the
rationale and the distractor explanations come back in the response to the
answer. That keeps devtools from being a cheat menu, and it matters most during
a timed exam.
"""

from __future__ import annotations

import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from . import (
    calibration as calibration_mod,
    cases as cases_mod,
    difficulty,
    casesession,
    exam as exam_mod,
    games,
    itemanalysis,
    loader,
    principles as principles_mod,
    scheduler,
    stats as stats_mod,
    store,
)
from .loader import Question


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# One lock per exam id, so two requests touching the same sitting cannot
# interleave their read-modify-write. Keyed rather than global because a lock
# shared across exams would serialise unrelated work for no benefit.
_EXAM_LOCKS: Dict[str, threading.Lock] = {}
_EXAM_LOCKS_GUARD = threading.Lock()


def _exam_lock(exam_id: str) -> threading.Lock:
    with _EXAM_LOCKS_GUARD:
        lock = _EXAM_LOCKS.get(exam_id)
        if lock is None:
            lock = threading.Lock()
            _EXAM_LOCKS[exam_id] = lock
        return lock


# --------------------------------------------------------------------------
# serialization
# --------------------------------------------------------------------------

def public_question(q: Question, position: int = 0, total: int = 0) -> Dict[str, Any]:
    """Everything the browser needs to render a question, and nothing more."""
    return {
        "id": q.id,
        "domain": q.domain,
        "section": q.section,
        "topic": q.topic,
        "tag": q.tag,
        "difficulty": q.difficulty,
        "stem": q.stem,
        "options": {k: q.options.get(k, "") for k in loader.OPTION_KEYS},
        "position": position,
        "total": total,
    }


def reveal(q: Question, chosen: Optional[str],
           principle: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": q.id,
        "answer": q.answer,
        "chosen": chosen,
        "correct": chosen == q.answer,
        "why_correct": q.why_correct,
        "why_wrong": {k: v for k, v in q.why_wrong.items()},
        "principle": principle,
    }


# --------------------------------------------------------------------------
# api
# --------------------------------------------------------------------------

class Api:
    def __init__(self, cert: str = "cisa", profile: Optional[str] = None):
        self.cert = cert
        self.profile = profile
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._cache: Dict[str, Any] = {}

    # ---- shared loading, cached because the bank does not change at runtime
    @property
    def questions(self) -> List[Question]:
        if "questions" not in self._cache:
            self._cache["questions"] = loader.load_questions(self.cert)
        return self._cache["questions"]

    @property
    def outline(self):
        if "outline" not in self._cache:
            self._cache["outline"] = loader.load_outline(self.cert)
        return self._cache["outline"]

    @property
    def rules(self) -> List[Dict[str, Any]]:
        if "rules" not in self._cache:
            self._cache["rules"] = loader.load_principles(self.cert)
        return self._cache["rules"]

    @property
    def pairs(self) -> List[Dict[str, Any]]:
        if "pairs" not in self._cache:
            self._cache["pairs"] = loader.load_pairs(self.cert)
        return self._cache["pairs"]

    def set_profile(self, profile: Optional[str]) -> None:
        self.profile = profile or None

    @property
    def results_path(self) -> str:
        return loader.results_path(self.cert, self.profile)

    @property
    def games_path(self) -> str:
        return games.games_path(self.results_path)

    def rows(self) -> List[Dict[str, Any]]:
        return store.load(self.results_path)

    def by_id(self) -> Dict[str, Question]:
        return {q.id: q for q in self.questions}

    def principle_for(self, question_id: str) -> Optional[Dict[str, Any]]:
        index = loader.principle_index(self.rules)
        ids = index.get(question_id) or []
        if not ids:
            return None
        for p in self.rules:
            if p["id"] == ids[0]:
                return {"id": p["id"], "name": p.get("name", ""),
                        "statement": p.get("statement", ""),
                        "misapplication": p.get("misapplication", ""),
                        "scope": p.get("scope", "")}
        return None

    # ------------------------------------------------------------------
    def bootstrap(self) -> Dict[str, Any]:
        outline = self.outline
        domains = []
        for did in sorted(outline.raw.get("domains", {})):
            dom = outline.raw["domains"][did]
            topics = []
            for sid in sorted(dom.get("sections", {})):
                for t in dom["sections"][sid].get("topics", []):
                    topics.append({"section": sid, "topic": t})
            domains.append({
                "id": did,
                "name": dom.get("name", ""),
                "weight": dom.get("weight"),
                "topics": topics,
                "questions": sum(1 for q in self.questions if q.domain == did),
            })

        return {
            "cert": self.cert.upper(),
            "profile": self.profile or "",
            "profiles": loader.list_profiles(self.cert),
            "questions": len(self.questions),
            "domains": domains,
            "exam": outline.raw.get("exam_format", {}),
            "principles": [
                {"id": p["id"], "name": p.get("name", ""),
                 "statement": p.get("statement", ""),
                 "why": p.get("why", ""),
                 "misapplication": p.get("misapplication", ""),
                 "scope": p.get("scope", ""),
                 "questions": len(p.get("question_ids") or [])}
                for p in self.rules
            ],
            "pairs": [
                {"id": p["id"], "label": p.get("label", ""),
                 "domain": p.get("domain", ""),
                 "terms": p.get("terms", []),
                 "discriminator": p.get("discriminator", ""),
                 "trap": p.get("trap", ""),
                 "questions": len(p.get("question_ids") or [])}
                for p in self.pairs
            ],
        }

    # ------------------------------------------------------------------
    def overview(self) -> Dict[str, Any]:
        rows = self.rows()
        attempts, correct, acc = stats_mod.overall(rows)
        seen, total = stats_mod.coverage_summary(rows, self.questions)

        domains = []
        by_domain = {b.label: b for b in stats_mod.by_domain(rows)}
        weighted_num = 0.0
        weighted_den = 0.0
        for did in sorted(self.outline.raw.get("domains", {})):
            dom = self.outline.raw["domains"][did]
            bucket = by_domain.get(did)
            a = bucket.accuracy if bucket else None
            n = bucket.attempts if bucket else 0
            weight = dom.get("weight") or 0
            if bucket and n:
                weighted_num += a * weight
                weighted_den += weight
            lo, hi = itemanalysis.wilson_interval(bucket.correct if bucket else 0, n)
            domains.append({
                "id": did, "name": dom.get("name", ""), "weight": weight,
                "accuracy": a, "attempts": n, "low": lo, "high": hi,
                "questions": sum(1 for q in self.questions if q.domain == did),
            })

        topics = [
            {"label": b.label, "accuracy": b.accuracy, "attempts": b.attempts,
             "correct": b.correct,
             "low": itemanalysis.wilson_interval(b.correct, b.attempts)[0],
             "high": itemanalysis.wilson_interval(b.correct, b.attempts)[1]}
            for b in stats_mod.by_topic(rows)
        ]

        rule_stats = principles_mod.summarize(self.rules, self.questions, rows)
        rules = [{
            "id": s.principle_id, "name": s.name, "accuracy": s.accuracy,
            "attempts": s.attempts, "low": s.interval[0], "high": s.interval[1],
            "misapplication": s.misapplication, "scope": s.scope,
            "seen": s.questions_seen, "total": s.questions_total,
        } for s in rule_stats]

        last_7 = stats_mod.recent(rows, 7)
        exams = exam_mod.list_exams(self.results_path)

        return {
            "attempts": attempts,
            "correct": correct,
            "accuracy": acc if attempts else None,
            "coverage_seen": seen,
            "coverage_total": total,
            "study_days": stats_mod.study_days(rows),
            "last7": stats_mod.overall(last_7)[2] if last_7 else None,
            "last7_attempts": len(last_7),
            # Weighted by exam weight. Deliberately NOT called a predicted score.
            "weighted_accuracy": (weighted_num / weighted_den) if weighted_den else None,
            "domains": domains,
            "topics": topics,
            "rules": rules,
            "games": len(games.load_games(self.games_path)),
            "exams": [{"id": e.exam_id, "created": e.created, "submitted": e.submitted,
                       "answered": e.answered, "total": e.total,
                       "elapsed": e.elapsed_seconds, "duration": e.duration_seconds}
                      for e in exams[:6]],
        }

    # ------------------------------------------------------------------
    def trend(self, days: int = 90, window: int = 7) -> Dict[str, Any]:
        """Accuracy over time, per domain, from the timestamped attempt log.

        Two series per point, because they answer different questions and a
        single line would quietly conflate them:

        * ``cum_*`` is accuracy over everything answered up to that day. Its
          Wilson band starts wide and narrows as evidence accrues, which is the
          honest picture of "what do I actually know about myself yet".
        * ``roll_*`` is a trailing ``window``-day view, which moves when recent
          work differs from the record but is noisy on light study days.

        Cumulative figures span the whole log; ``days`` only bounds how far back
        points are emitted, so capping the window never understates history.
        Every accuracy here ships with its interval and its denominator - a day
        with three attempts must not be able to render as a confident number.
        """
        days = max(1, min(int(days), 3650))
        window = max(1, min(int(window), 365))

        rows = self.rows()
        by_day: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            ts = store.parse_ts(row.get("ts", ""))
            if ts is None:
                continue
            by_day.setdefault(ts.astimezone().date().isoformat(), []).append(row)
        if not by_day:
            return {"days": days, "window": window, "points": [],
                    "domains": self._trend_domains(), "total_attempts": 0}

        first = datetime.fromisoformat(min(by_day)).date()
        last = datetime.fromisoformat(max(by_day)).date()
        today = datetime.now(timezone.utc).astimezone().date()
        if today > last:
            last = today
        start = max(first, last - timedelta(days=days - 1))

        domain_ids = [d["id"] for d in self._trend_domains()]
        cum = {"attempts": 0, "correct": 0}
        cum_dom = {d: {"attempts": 0, "correct": 0} for d in domain_ids}
        daily: Dict[str, Dict[str, int]] = {}
        points: List[Dict[str, Any]] = []

        day = first
        while day <= last:
            key = day.isoformat()
            todays = by_day.get(key, [])
            hits = sum(1 for r in todays if r.get("correct"))
            daily[key] = {"attempts": len(todays), "correct": hits}
            cum["attempts"] += len(todays)
            cum["correct"] += hits
            for r in todays:
                bucket = cum_dom.get(str(r.get("domain", "")))
                if bucket is not None:
                    bucket["attempts"] += 1
                    bucket["correct"] += 1 if r.get("correct") else 0

            if day >= start:
                roll = {"attempts": 0, "correct": 0}
                for back in range(window):
                    seen = daily.get((day - timedelta(days=back)).isoformat())
                    if seen:
                        roll["attempts"] += seen["attempts"]
                        roll["correct"] += seen["correct"]
                points.append({
                    "date": key,
                    "attempts": len(todays),
                    "correct": hits,
                    **self._trend_stat("cum", cum["correct"], cum["attempts"]),
                    **self._trend_stat("roll", roll["correct"], roll["attempts"]),
                    "domains": {
                        d: self._trend_stat("cum", cum_dom[d]["correct"],
                                            cum_dom[d]["attempts"], counts=True)
                        for d in domain_ids
                    },
                })
            day += timedelta(days=1)

        return {"days": days, "window": window, "points": points,
                "domains": self._trend_domains(), "total_attempts": cum["attempts"]}

    def _trend_domains(self) -> List[Dict[str, Any]]:
        outline = self.outline.raw.get("domains", {})
        return [{"id": did, "name": outline[did].get("name", ""),
                 "weight": outline[did].get("weight")} for did in sorted(outline)]

    @staticmethod
    def _trend_stat(prefix: str, correct: int, attempts: int,
                    counts: bool = False) -> Dict[str, Any]:
        """A proportion is never returned without its denominator and interval."""
        lo, hi = itemanalysis.wilson_interval(correct, attempts)
        out = {
            "%s_accuracy" % prefix: (correct / attempts) if attempts else None,
            "%s_low" % prefix: lo if attempts else None,
            "%s_high" % prefix: hi if attempts else None,
            "%s_attempts" % prefix: attempts,
            "%s_correct" % prefix: correct,
        }
        if counts:  # nested per-domain form uses bare keys
            return {k.split("_", 1)[1]: v for k, v in out.items()}
        return out

    # ------------------------------------------------------------------
    def _filtered(self, params: Dict[str, Any]) -> List[Question]:
        pool = self.questions
        if params.get("domain"):
            pool = [q for q in pool if q.domain == str(params["domain"])]
        if params.get("section"):
            pool = [q for q in pool if q.section.upper() == str(params["section"]).upper()]
        if params.get("topic"):
            needle = str(params["topic"]).lower()
            pool = [q for q in pool if needle in q.topic.lower()]
        if params.get("principle"):
            ids = set(principles_mod._ids_for(self.rules, str(params["principle"])))
            pool = [q for q in pool if q.id in ids]
        return pool

    def drill_preview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """What a difficulty filter would actually yield, before committing.

        Exists so the browser can show a short or empty result *before* the
        learner starts, rather than letting them discover it three questions in.
        A fifth of topic-plus-difficulty combinations return nothing, so this is
        the normal path, not an edge case.
        """
        pool = self._filtered(params)
        count = max(1, min(int(params.get("n", 10)), 150))
        wanted = difficulty.normalise(params.get("difficulty"))
        history = store.history_by_question(self.rows())
        return difficulty.availability(pool, wanted, count, history).as_dict()

    def drill_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        pool = self._filtered(params)
        if not pool:
            raise ApiError("No questions match those filters.")

        count = max(1, min(int(params.get("n", 10)), 150))
        mode = params.get("mode", "smart")
        rng = random.Random(params.get("seed"))
        rows = self.rows()
        header = None

        # Strict: the pool is narrowed before the scheduler sees it, and is
        # never topped up from an adjacent band.
        wanted = difficulty.normalise(params.get("difficulty"))
        avail = difficulty.availability(
            pool, wanted, count, store.history_by_question(rows))
        if difficulty.is_filter(wanted):
            if avail.empty:
                raise ApiError(avail.message())
            pool = difficulty.apply(pool, wanted)

        if mode == "principle":
            picked, targeted = principles_mod.select_by_weak_principles(
                pool, self.rules, rows, count, rng)
            names = {p["id"]: p.get("name", p["id"]) for p in self.rules}
            if targeted:
                header = "Targeting: " + "; ".join(names.get(t, t) for t in targeted[:3])
        elif mode == "costumes":
            chosen = params.get("principle")
            if not chosen:
                ranked = principles_mod.weakest(
                    principles_mod.summarize(self.rules, self.questions, rows))
                ranked = ranked or principles_mod.summarize(self.rules, self.questions, rows)
                chosen = ranked[0].principle_id
            pool = principles_mod.questions_for(self.rules, chosen, self.questions)
            seen = {r.get("question_id") for r in rows}
            picked = principles_mod.one_per_domain(pool, rng, seen)
            rule = next((p for p in self.rules if p["id"] == chosen), {})
            header = rule.get("name", "")
        else:
            history = store.history_by_question(rows)
            picked = scheduler.select(pool, history, count, mode=mode, rng=rng)

        if not picked:
            raise ApiError("Nothing to serve for that selection.")

        # Ramp reorders what the scheduler chose; it never re-selects.
        picked = difficulty.present(picked, wanted)

        session_id = uuid.uuid4().hex[:10]
        self._sessions[session_id] = {"kind": "drill", "mode": mode,
                                      "ids": [q.id for q in picked],
                                      "started": time.time()}
        return {
            "session": session_id,
            "mode": mode,
            "header": header,
            "difficulty": wanted,
            "availability": avail.as_dict(),
            "ramp_bands": difficulty.ramp_spread(picked),
            "questions": [public_question(q, i + 1, len(picked))
                          for i, q in enumerate(picked)],
        }

    def drill_answer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        qid = params.get("question_id")
        chosen = str(params.get("chosen", "")).upper()
        q = self.by_id().get(qid)
        if q is None:
            raise ApiError("Unknown question '%s'." % qid, 404)
        if chosen not in loader.OPTION_KEYS:
            raise ApiError("Answer must be one of A, B, C, D.")

        store.append(self.results_path, store.Attempt(
            ts=store.now_iso(), session=str(params.get("session", "web"))[:32],
            question_id=q.id, cert=self.cert.upper(), domain=q.domain,
            section=q.section, topic=q.topic, chosen=chosen, answer=q.answer,
            correct=chosen == q.answer,
            seconds=round(float(params.get("seconds", 0) or 0), 1),
            mode=str(params.get("mode", "smart"))[:20],
            # Sent with the answer, so it is recorded before the learner sees
            # whether they were right. Confidence taken afterwards is hindsight.
            confidence=store.normalise_confidence(params.get("confidence")),
        ))
        return reveal(q, chosen, self.principle_for(q.id))

    # ------------------------------------------------------------------
    def game_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        which = params.get("game", "coldread")
        if which not in ("coldread", "autopsy"):
            raise ApiError("Unknown game '%s'." % which)
        count = max(1, min(int(params.get("n", 10)), 60))
        rng = random.Random(params.get("seed"))
        picked = games.pick(self._filtered(params), count, which, rng)
        if not picked:
            raise ApiError("No questions available for that game.")

        session_id = uuid.uuid4().hex[:10]
        payload: List[Dict[str, Any]] = []
        shuffles: Dict[str, Dict[str, str]] = {}

        for i, q in enumerate(picked):
            item = public_question(q, i + 1, len(picked))
            if which == "coldread":
                item["options"] = {}  # hidden until the read is committed
            else:
                distractors = [k for k in loader.OPTION_KEYS
                               if k != q.answer and q.why_wrong.get(k, "").strip()]
                order = list(distractors)
                rng.shuffle(order)
                labels = ["X", "Y", "Z"][:len(order)]
                label_for = {opt: labels[n] for n, opt in enumerate(order)}
                shuffles[q.id] = label_for
                item["answer"] = q.answer  # revealed by design in Autopsy
                item["distractors"] = distractors
                item["explanations"] = [
                    {"label": label_for[opt], "text": q.why_wrong[opt]}
                    for opt in sorted(distractors, key=lambda o: label_for[o])
                ]
            payload.append(item)

        self._sessions[session_id] = {"kind": which, "shuffles": shuffles,
                                      "started": time.time()}
        return {"session": session_id, "game": which,
                "ask_types": [{"id": k, "label": v[0], "gloss": v[1]}
                              for k, v in ((k, games.ASK_TYPES[k]) for k in games.ASK_ORDER)],
                "questions": payload}

    def game_answer(self, params: Dict[str, Any]) -> Dict[str, Any]:
        which = params.get("game", "coldread")
        qid = params.get("question_id")
        q = self.by_id().get(qid)
        if q is None:
            raise ApiError("Unknown question '%s'." % qid, 404)
        session_id = str(params.get("session", ""))
        seconds = round(float(params.get("seconds", 0) or 0), 1)

        if which == "coldread":
            expected = games.ask_type(q)
            guess = params.get("read")
            correct = guess == expected
            games.append_game(self.games_path, games.GameAttempt(
                ts=store.now_iso(), session=session_id, game="coldread",
                question_id=q.id, cert=self.cert.upper(), domain=q.domain,
                section=q.section, topic=q.topic, correct=correct,
                detail="read=%s expected=%s" % (guess, expected),
                self_report=str(params.get("self_report", ""))[:8], seconds=seconds))
            payload = reveal(q, None, self.principle_for(q.id))
            payload.update({"expected": expected, "read": guess, "read_correct": correct,
                            "options": {k: q.options.get(k, "") for k in loader.OPTION_KEYS}})
            return payload

        mapping = params.get("mapping") or {}
        truth = self._sessions.get(session_id, {}).get("shuffles", {}).get(q.id)
        if not truth:
            raise ApiError("That autopsy session has expired; start a new one.")
        hits = sum(1 for opt, label in truth.items()
                   if str(mapping.get(opt, "")).upper() == label)
        correct = hits == len(truth)
        games.append_game(self.games_path, games.GameAttempt(
            ts=store.now_iso(), session=session_id, game="autopsy",
            question_id=q.id, cert=self.cert.upper(), domain=q.domain,
            section=q.section, topic=q.topic, correct=correct,
            detail="matched=%d/%d" % (hits, len(truth)), seconds=seconds))
        return {"id": q.id, "correct": correct, "matched": hits,
                "total": len(truth), "truth": truth,
                "why_correct": q.why_correct,
                "principle": self.principle_for(q.id)}

    def game_stats(self) -> Dict[str, Any]:
        rows = games.load_games(self.games_path)
        by_game: Dict[str, Dict[str, Any]] = {}
        misreads: Dict[str, int] = {}
        reports: Dict[str, int] = {}
        for r in rows:
            b = by_game.setdefault(r.get("game", "?"), {"n": 0, "ok": 0, "secs": 0.0})
            b["n"] += 1
            b["ok"] += 1 if r.get("correct") else 0
            b["secs"] += float(r.get("seconds", 0) or 0)
            if r.get("game") == "coldread" and not r.get("correct"):
                detail = r.get("detail", "") or ""
                parts = dict(p.split("=", 1) for p in detail.split() if "=" in p)
                if parts.get("expected") and parts.get("read"):
                    key = "%s|%s" % (parts["expected"], parts["read"])
                    misreads[key] = misreads.get(key, 0) + 1
            if r.get("self_report"):
                reports[r["self_report"]] = reports.get(r["self_report"], 0) + 1
        return {
            "total": len(rows),
            "by_game": [{"game": k, **v, "accuracy": v["ok"] / v["n"] if v["n"] else None}
                        for k, v in sorted(by_game.items())],
            "misreads": sorted(
                [{"expected": k.split("|")[0], "read": k.split("|")[1], "count": v}
                 for k, v in misreads.items()], key=lambda x: -x["count"])[:8],
            "self_report": reports,
        }

    # ------------------------------------------------------------------
    def exam_list(self) -> Dict[str, Any]:
        return {"exams": [
            {"id": e.exam_id, "created": e.created, "submitted": e.submitted,
             "answered": e.answered, "total": e.total, "flagged": len(e.flagged),
             "elapsed": e.elapsed_seconds, "duration": e.duration_seconds,
             "shortfall": e.shortfall}
            for e in exam_mod.list_exams(self.results_path)]}

    def exam_new(self, params: Dict[str, Any]) -> Dict[str, Any]:
        pool = self._filtered(params)
        total = max(1, min(int(params.get("n", exam_mod.DEFAULT_QUESTIONS)), 300))
        minutes = max(1, min(int(params.get("minutes", exam_mod.DEFAULT_MINUTES)), 600))
        rng = random.Random(params.get("seed"))
        state, picked = exam_mod.new_exam(pool, self.outline, self.cert,
                                          total=total, minutes=minutes, rng=rng)
        exam_mod.save(state, self.results_path)
        return self.exam_get(state.exam_id)

    def exam_get(self, exam_id: str) -> Dict[str, Any]:
        state = exam_mod.load(self.results_path, exam_id)
        known = self.by_id()
        ordered = [known[q] for q in state.question_ids if q in known]
        return {
            "id": state.exam_id,
            "submitted": state.submitted,
            "duration": state.duration_seconds,
            "elapsed": state.elapsed_seconds,
            "remaining": state.remaining_seconds,
            "position": state.position,
            "answers": state.answers,
            "confidence": state.confidence,
            "flagged": state.flagged,
            "blueprint": state.blueprint,
            "shortfall": state.shortfall,
            "questions": [public_question(q, i + 1, len(ordered))
                          for i, q in enumerate(ordered)],
        }

    def exam_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read-modify-write, serialised per exam.

        One user action can produce two requests almost at once - answering a
        question and rating confidence on it - and the server is threaded. Two
        handlers loading the same state independently would let the second
        overwrite the first's change. Writing the file atomically is not enough
        on its own; the whole read-modify-write has to be the unit.
        """
        with _exam_lock(str(params.get("id", ""))):
            return self._exam_update_locked(params)

    def _exam_update_locked(self, params: Dict[str, Any]) -> Dict[str, Any]:
        state = exam_mod.load(self.results_path, str(params.get("id", "")))
        if state.submitted:
            raise ApiError("That exam has already been submitted.")

        qid = params.get("question_id")
        if qid and qid not in set(state.question_ids):
            raise ApiError("That question is not part of this exam.")

        action = params.get("action", "answer")
        if action == "answer":
            chosen = str(params.get("chosen", "")).upper()
            if chosen in loader.OPTION_KEYS:
                state.answers[qid] = chosen
                confidence = store.normalise_confidence(params.get("confidence"))
                if confidence:
                    state.confidence[qid] = confidence
            elif chosen == "":
                state.answers.pop(qid, None)
                state.confidence.pop(qid, None)
            spent = float(params.get("seconds", 0) or 0)
            if spent > 0:
                prior = state.seconds_per_question.get(qid, 0.0)
                state.seconds_per_question[qid] = round(prior + spent, 1)
        elif action == "flag":
            if qid in state.flagged:
                state.flagged.remove(qid)
            else:
                state.flagged.append(qid)
        elif action == "position":
            state.position = max(0, min(state.total - 1, int(params.get("position", 0))))
        elif action == "tick":
            # The browser owns the clock while a sitting is open; it reports
            # elapsed time so a closed tab cannot keep the timer running.
            state.elapsed_seconds = round(max(state.elapsed_seconds,
                                              float(params.get("elapsed", 0) or 0)), 1)
        else:
            raise ApiError("Unknown action '%s'." % action)

        exam_mod.save(state, self.results_path)
        return {"ok": True, "answered": state.answered,
                "flagged": state.flagged, "elapsed": state.elapsed_seconds,
                "remaining": state.remaining_seconds}

    def exam_submit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        state = exam_mod.load(self.results_path, str(params.get("id", "")))
        if not state.submitted:
            elapsed = float(params.get("elapsed", 0) or 0)
            state.elapsed_seconds = round(max(state.elapsed_seconds, elapsed), 1)
            state.submitted = True
            state.submitted_at = store.now_iso()
            exam_mod.save(state, self.results_path)
            ts = store.now_iso()
            known = self.by_id()
            for qid, chosen in state.answers.items():
                q = known.get(qid)
                if q is None:
                    continue
                store.append(self.results_path, store.Attempt(
                    ts=ts, session="exam-%s" % state.exam_id, question_id=q.id,
                    cert=self.cert.upper(), domain=q.domain, section=q.section,
                    topic=q.topic, chosen=chosen, answer=q.answer,
                    correct=chosen == q.answer,
                    seconds=state.seconds_per_question.get(q.id, 0.0), mode="exam",
                    confidence=state.confidence.get(q.id, "")))
        return self.exam_result(state.exam_id)

    def exam_result(self, exam_id: str) -> Dict[str, Any]:
        state = exam_mod.load(self.results_path, exam_id)
        result = exam_mod.score(state, self.questions, self.outline)
        known = self.by_id()
        return {
            "id": result.exam_id,
            "total": result.total,
            "correct": result.correct,
            "unanswered": result.unanswered,
            "raw": result.raw_fraction,
            "scaled": result.scaled_estimate,
            "passed": result.passed_estimate,
            "elapsed": result.elapsed_seconds,
            "duration": result.duration_seconds,
            "pass_mark": exam_mod.SCALE_PASS,
            "by_domain": [{"domain": d.domain, "name": d.name, "weight": d.weight,
                           "asked": d.asked, "correct": d.correct,
                           "accuracy": d.accuracy,
                           "cost": (d.weight or 0) * (1 - d.accuracy)}
                          for d in result.by_domain],
            "slowest": [{"id": q.id, "topic": q.topic, "seconds": s}
                        for q, s in result.slowest if s > 0][:6],
            "guessed_right": [{"id": q.id, "topic": q.topic}
                              for q in result.guessed_right],
            "missed": [
                {**public_question(known[q.id]),
                 **reveal(known[q.id], state.answers.get(q.id),
                          self.principle_for(q.id))}
                for q in result.missed if q.id in known
            ],
        }

    # ------------------------------------------------------------------
    # calibration
    # ------------------------------------------------------------------
    def settings(self) -> Dict[str, Any]:
        data = loader.load_settings(self.cert, self.profile)
        return {"target_date": str(data.get("target_date", "") or "")}

    def save_settings(self, params: Dict[str, Any]) -> Dict[str, Any]:
        current = loader.load_settings(self.cert, self.profile)
        if "target_date" in params:
            raw = str(params.get("target_date", "") or "").strip()
            if raw and calibration_mod.parse_target(raw) is None:
                raise ApiError("Target date must be YYYY-MM-DD.")
            if raw:
                current["target_date"] = raw
            else:
                current.pop("target_date", None)
        loader.save_settings(self.cert, current, self.profile)
        return self.settings()

    def calibration(self) -> Dict[str, Any]:
        """Whether the learner knew, not just whether they were right.

        Deliberately returns the curve, the gap and the lists rather than any
        single figure. There is no "calibration score" here and there should
        not be one.
        """
        target = calibration_mod.parse_target(
            loader.load_settings(self.cert, self.profile).get("target_date"))
        return calibration_mod.report(self.rows(), self.questions, self.rules, target)

    # ------------------------------------------------------------------
    # branching cases
    #
    # `quality` and `why` never appear in any payload below except the debrief,
    # which is only reachable once the run has finished. Same rule as answer
    # keys, same reason: if the browser can see which option is best, the
    # format is pointless. casesession.public_node() is the only thing that
    # builds a mid-run node, and it is an allow-list.
    # ------------------------------------------------------------------
    @property
    def cases(self) -> List[cases_mod.Case]:
        if "cases" not in self._cache:
            self._cache["cases"] = cases_mod.load_cases(self.cert)
        return self._cache["cases"]

    def case_by_id(self, case_id: str) -> cases_mod.Case:
        for case in self.cases:
            if case.id == case_id:
                return case
        raise ApiError("Unknown case '%s'." % case_id, 404)

    def _case_session(self, session_id: str):
        try:
            return casesession.load(self.results_path, session_id)
        except casesession.CaseSessionError as exc:
            raise ApiError(str(exc), 404)

    def case_list(self) -> Dict[str, Any]:
        return {"cases": casesession.case_index(self.cases, self.results_path)}

    def case_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        case = self.case_by_id(str(params.get("case_id", "")))
        state = casesession.start(case, self.cert)
        casesession.save(state, self.results_path)
        return {
            "session": state.session_id,
            "case": casesession._case_header(case),
            "opening": case.opening,
            "node": casesession.public_node(case, state.current, 1,
                                            cases_mod.longest_path(case)),
            "trail": [],
            "finished": False,
        }

    def case_get(self, session_id: str) -> Dict[str, Any]:
        """Resume. A case is 10-15 minutes; a closed tab must not lose it."""
        state = self._case_session(session_id)
        case = self.case_by_id(state.case_id)
        return {
            "session": state.session_id,
            "case": casesession._case_header(case),
            "opening": case.opening,
            "node": None if state.finished else casesession.public_node(
                case, state.current, state.decisions + 1,
                cases_mod.longest_path(case)),
            "trail": casesession.public_trail(case, state),
            "finished": state.finished,
            "decisions": state.decisions,
        }

    def case_choose(self, params: Dict[str, Any]) -> Dict[str, Any]:
        state = self._case_session(str(params.get("session", "")))
        case = self.case_by_id(state.case_id)
        try:
            payload = casesession.choose(
                case, state,
                str(params.get("node", "")),
                str(params.get("key", "")),
                float(params.get("seconds", 0) or 0),
            )
        except casesession.CaseSessionError as exc:
            raise ApiError(str(exc))

        casesession.save(state, self.results_path)
        if state.finished:
            # Logged to cases.jsonl only. A case is not an MCQ and must never
            # reach item analysis or the scheduler.
            casesession.record(case, state, self.results_path)
        return payload

    def case_debrief(self, session_id: str) -> Dict[str, Any]:
        state = self._case_session(session_id)
        case = self.case_by_id(state.case_id)
        try:
            return casesession.debrief(case, state)
        except casesession.CaseSessionError as exc:
            raise ApiError(str(exc))

    # ------------------------------------------------------------------
    def items(self, min_attempts: int = 5) -> Dict[str, Any]:
        rows = self.rows()
        item_stats = itemanalysis.analyze(rows, self.questions, min_attempts)
        health = itemanalysis.bank_health(item_stats)
        return {
            "total": health.total_questions,
            "served": health.served,
            "never_served": health.never_served,
            "with_stats": health.with_stats,
            "mean_p": health.mean_p_value,
            "mean_discrimination": health.mean_discrimination,
            "spread": health.difficulty_spread,
            "flags": health.flag_counts,
            "suspect": [{"id": s.question_id, "topic": s.topic,
                         "p": s.p_value, "attempts": s.attempts,
                         "discrimination": s.discrimination, "flags": s.flags}
                        for s in itemanalysis.needs_rewrite(item_stats)[:20]],
            "hardest": [{"id": s.question_id, "topic": s.topic, "p": s.p_value,
                         "attempts": s.attempts, "low": s.interval[0],
                         "high": s.interval[1], "seconds": s.median_seconds}
                        for s in sorted([s for s in item_stats if s.has_stats],
                                        key=lambda s: (s.p_value or 0))[:20]],
        }

    def card(self) -> Dict[str, Any]:
        return {"text": principles_mod.render_card(self.rules)}
