"""Running a branching case: session state, choosing, and the debrief.

`cases.py` deliberately stops at data and graph integrity. This module is the
part that drives a case for a learner, and it is separate for the same reason
`exam.py` is separate from the question bank: the graph is content, a session is
someone's history.

Three rules shape everything here, and all three are easy to break by accident:

* **`quality` and `why` never leave this module before the debrief.** A case
  where the browser can see which option is `best` is pointless. `public_node()`
  emits `key` and `text` only, the same discipline `webapi.public_question()`
  applies to answer keys, and there is a test asserting it.
* **No verdict during the run.** `choose()` returns the neutral `consequence`
  and the next node. It does not return quality, running counts, or the ending's
  narrative - reaching the end returns a bare `finished` marker and the client
  then asks for the debrief. Sitting with an uncertain choice is the thing being
  trained.
* **Cases log to `cases.jsonl`**, never `attempts.jsonl`. A case is not a
  four-option MCQ; letting it reach item analysis or the spaced-repetition
  scheduler would corrupt both.

The debrief is where the value is. It carries the walked path, the options *not*
taken at each node, and - when a taint fired - the specific decision that fixed
the outcome regardless of what came after.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from . import exam as exam_mod
from .cases import Case, PathStep, score_path


class CaseSessionError(Exception):
    """Raised when a session cannot be found, or a move is not legal."""


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

@dataclass
class Step:
    """One decision, as stored. Quality is recorded but never served early."""
    node_id: str
    chosen: str
    quality: str
    best_key: str
    taint: Optional[str] = None
    seconds: float = 0.0


@dataclass
class CaseSession:
    session_id: str
    case_id: str
    cert: str
    created: str
    current: str = ""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    taints: List[str] = field(default_factory=list)
    finished: bool = False
    # Where the graph led, before taints are applied. Kept separately so the
    # debrief can say "you reached X, but Y was fixed four decisions earlier".
    graph_ending: str = ""
    ending: str = ""
    finished_at: str = ""
    seconds: float = 0.0

    @property
    def decisions(self) -> int:
        return len(self.steps)

    def path_steps(self) -> List[PathStep]:
        return [
            PathStep(
                node_id=s["node_id"], chosen=s["chosen"], quality=s["quality"],
                best_key=s.get("best_key", ""), taint=s.get("taint"),
            )
            for s in self.steps
        ]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# persistence — mirrors exam.py, including the atomic replace
# --------------------------------------------------------------------------

def sessions_dir(cert_results_path: str) -> str:
    return os.path.join(os.path.dirname(cert_results_path), "cases")


def session_path(cert_results_path: str, session_id: str) -> str:
    return os.path.join(sessions_dir(cert_results_path), "%s.json" % session_id)


def save(state: CaseSession, cert_results_path: str) -> str:
    path = session_path(cert_results_path, state.session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Unique temp name per call - see the note in exam.save(). A shared
    # "<file>.tmp" is not safe under a threaded server.
    tmp = "%s.%d.%d.tmp" % (path, os.getpid(), threading.get_ident())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(state), fh, indent=2)
        exam_mod._replace_with_retry(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return path


def load(cert_results_path: str, session_id: str) -> CaseSession:
    path = session_path(cert_results_path, session_id)
    if not os.path.exists(path):
        raise CaseSessionError("no case session found with id '%s'" % session_id)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    known = {f for f in CaseSession.__dataclass_fields__}
    return CaseSession(**{k: v for k, v in data.items() if k in known})


def list_sessions(cert_results_path: str) -> List[CaseSession]:
    directory = sessions_dir(cert_results_path)
    if not os.path.isdir(directory):
        return []
    out: List[CaseSession] = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        try:
            out.append(load(cert_results_path, name[:-5]))
        except (CaseSessionError, json.JSONDecodeError, TypeError, ValueError):
            continue  # a half-written file must not break the list
    return sorted(out, key=lambda s: s.created, reverse=True)


# --------------------------------------------------------------------------
# the separate log — same reasoning as games.jsonl
# --------------------------------------------------------------------------

@dataclass
class CaseResult:
    ts: str
    session: str
    case_id: str
    cert: str
    domain: str
    title: str
    decisions: int
    best: int
    defensible: int
    poor: int
    taints: str
    ending: str
    verdict: str
    overridden: bool
    seconds: float


def cases_log_path(cert_results_path: str) -> str:
    """Sits beside attempts.jsonl but is a different file, on purpose."""
    return os.path.join(os.path.dirname(cert_results_path), "cases.jsonl")


def append_result(path: str, result: CaseResult) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(result), ensure_ascii=True) + "\n")


def load_results(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("case_id"):
                rows.append(row)
    return rows


# --------------------------------------------------------------------------
# what the client is allowed to see mid-run
# --------------------------------------------------------------------------

def public_option(opt: Dict[str, Any]) -> Dict[str, Any]:
    """Key and text. Nothing else.

    Not a filter over the full option - an explicit allow-list, so a field added
    to the schema later cannot leak by default.
    """
    return {"key": opt.get("key", ""), "text": opt.get("text", "")}


def public_node(case: Case, node_id: str, position: int = 0,
                total: int = 0) -> Dict[str, Any]:
    node = case.node(node_id) or {}
    return {
        "id": node_id,
        "situation": node.get("situation", ""),
        "prompt": node.get("prompt", ""),
        "options": [public_option(o) for o in node.get("options", [])],
        # Position is how many decisions have been made, not progress toward a
        # score. Paths differ in length, so there is no honest denominator.
        "position": position,
        "longest": total,
    }


def public_trail(case: Case, state: CaseSession) -> List[Dict[str, Any]]:
    """What the learner has already seen, for resuming mid-case.

    Consequences only - they were shown during the run. No quality, no why.
    """
    trail: List[Dict[str, Any]] = []
    for step in state.steps:
        node = case.node(step["node_id"]) or {}
        opt = case.option(step["node_id"], step["chosen"]) or {}
        trail.append({
            "node": step["node_id"],
            "situation": node.get("situation", ""),
            "prompt": node.get("prompt", ""),
            "chosen": step["chosen"],
            "text": opt.get("text", ""),
            "consequence": opt.get("consequence", ""),
        })
    return trail


# --------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------

def start(case: Case, cert: str) -> CaseSession:
    from .cases import START
    if START not in case.nodes:
        raise CaseSessionError("case '%s' has no start node" % case.id)
    return CaseSession(
        session_id=uuid.uuid4().hex[:10],
        case_id=case.id,
        cert=cert.upper(),
        created=now_iso(),
        current=START,
    )


def choose(case: Case, state: CaseSession, node_id: str, key: str,
           seconds: float = 0.0) -> Dict[str, Any]:
    """Take one decision. Returns the consequence and where you now are.

    Deliberately returns no verdict, no quality and no running tally. The only
    thing that changes on reaching an ending is that `finished` goes true - the
    narrative and the teaching come from the debrief, after the run.
    """
    if state.finished:
        raise CaseSessionError("that case has already finished")
    if node_id != state.current:
        # Guards replay and skipping ahead: the client cannot answer a node it
        # is not on, whatever it posts.
        raise CaseSessionError(
            "this session is at '%s', not '%s'" % (state.current, node_id))

    opt = case.option(node_id, key)
    if opt is None:
        raise CaseSessionError("'%s' is not an option at '%s'" % (key, node_id))

    best = case.best_option(node_id) or {}
    taint = opt.get("taint")
    state.steps.append(asdict(Step(
        node_id=node_id,
        chosen=str(opt.get("key", key)).upper(),
        quality=opt.get("quality", ""),
        best_key=str(best.get("key", "")).upper(),
        taint=taint,
        seconds=round(float(seconds or 0), 1),
    )))
    if taint and taint not in state.taints:
        state.taints.append(taint)
    state.seconds = round(state.seconds + float(seconds or 0), 1)

    target = opt.get("next", "")
    payload: Dict[str, Any] = {
        "session": state.session_id,
        "consequence": opt.get("consequence", ""),
        "chosen": str(opt.get("key", key)).upper(),
        "decisions": state.decisions,
    }

    if case.is_ending(target):
        state.graph_ending = target
        # A taint fixes the outcome regardless of where the graph led.
        state.ending = case.resolve_ending(state.taints, target)
        state.finished = True
        state.finished_at = now_iso()
        state.current = ""
        payload["finished"] = True
        payload["next"] = None
    else:
        state.current = target
        payload["finished"] = False
        payload["next"] = public_node(
            case, target, position=state.decisions + 1,
            total=_longest(case))
    return payload


def _longest(case: Case) -> int:
    from .cases import longest_path
    return longest_path(case)


def record(case: Case, state: CaseSession, cert_results_path: str) -> None:
    """Append a finished run to cases.jsonl. Never touches attempts.jsonl."""
    if not state.finished:
        raise CaseSessionError("cannot record a case that has not finished")
    profile = score_path(case, state.path_steps(), state.graph_ending)
    counts = profile["counts"]
    append_result(cases_log_path(cert_results_path), CaseResult(
        ts=state.finished_at or now_iso(),
        session=state.session_id,
        case_id=case.id,
        cert=state.cert,
        domain=case.domain,
        title=case.title,
        decisions=profile["decisions"],
        best=counts.get("best", 0),
        defensible=counts.get("defensible", 0),
        poor=counts.get("poor", 0),
        taints=",".join(profile["taints"]),
        ending=profile["ending"],
        verdict=profile["verdict"] or "",
        overridden=bool(profile["overridden"]),
        seconds=state.seconds,
    ))


# --------------------------------------------------------------------------
# the debrief — the part that teaches
# --------------------------------------------------------------------------

def debrief(case: Case, state: CaseSession) -> Dict[str, Any]:
    """Everything held back during the run.

    Per node: what they chose and why it was graded that way, what the best
    option was, and *every option they did not take*. The branches not walked
    are most of the teaching - the learner has seen one thread through a graph
    and the alternatives are where the judgment lives.
    """
    if not state.finished:
        raise CaseSessionError("the debrief is only available once the case ends")

    profile = score_path(case, state.path_steps(), state.graph_ending)

    walk: List[Dict[str, Any]] = []
    for index, step in enumerate(state.steps):
        node = case.node(step["node_id"]) or {}
        chosen_key = step["chosen"]
        options = []
        for opt in node.get("options", []):
            key = str(opt.get("key", "")).upper()
            options.append({
                "key": key,
                "text": opt.get("text", ""),
                "quality": opt.get("quality", ""),
                "why": opt.get("why", ""),
                "consequence": opt.get("consequence", ""),
                "chosen": key == chosen_key,
                "taint": opt.get("taint"),
                "leads_to": opt.get("next", ""),
                # Where this option would have taken you instead. Naming the
                # divergence is what turns a list of options into a map.
                "diverges": opt.get("next", "") != _next_of(case, step),
            })
        walk.append({
            "index": index + 1,
            "node": step["node_id"],
            "situation": node.get("situation", ""),
            "prompt": node.get("prompt", ""),
            "chosen": chosen_key,
            "quality": step["quality"],
            "best": step.get("best_key", ""),
            "seconds": step.get("seconds", 0.0),
            "options": options,
        })

    ending = case.ending(state.ending) or {}
    graph_ending = case.ending(state.graph_ending) or {}

    return {
        "session": state.session_id,
        "case": _case_header(case),
        "decisions": profile["decisions"],
        "counts": profile["counts"],
        "taints": profile["taints"],
        "ending": {
            "id": state.ending,
            "title": ending.get("title", ""),
            "verdict": ending.get("verdict", ""),
            "narrative": ending.get("narrative", ""),
            "why": ending.get("why", ""),
        },
        "overridden": profile["overridden"],
        # Populated only when a taint changed the outcome. This is the single
        # most valuable thing the feature can say, so it is a first-class field
        # rather than something the client has to infer.
        "override": _override_detail(case, state) if profile["overridden"] else None,
        "graph_ending": {
            "id": state.graph_ending,
            "title": graph_ending.get("title", ""),
            "verdict": graph_ending.get("verdict", ""),
        } if profile["overridden"] else None,
        "walk": walk,
        # So the client can label where an option you did not take would have
        # led. "Option C would have ended the case here, weakly" is a much
        # sharper lesson than "option C was poor".
        "endings_index": {
            eid: {"title": e.get("title", ""), "verdict": e.get("verdict", "")}
            for eid, e in case.endings.items()
        },
        "principles": list(case.principles),
        "seconds": state.seconds,
        "finished_at": state.finished_at,
    }


def _next_of(case: Case, step: Dict[str, Any]) -> str:
    opt = case.option(step["node_id"], step["chosen"]) or {}
    return opt.get("next", "")


def _override_detail(case: Case, state: CaseSession) -> Dict[str, Any]:
    """Name the decision that fixed the outcome, and how far back it was.

    "Your final answers were sound, but the outcome was determined four
    decisions earlier when you agreed to omit the finding" - that sentence is
    the reason this function exists.
    """
    total = len(state.steps)
    for index, step in enumerate(state.steps):
        taint = step.get("taint")
        if not taint:
            continue
        if case.resolve_ending([taint], state.graph_ending) != state.graph_ending:
            opt = case.option(step["node_id"], step["chosen"]) or {}
            node = case.node(step["node_id"]) or {}
            return {
                "taint": taint,
                "decision": index + 1,
                "of": total,
                "decisions_before_end": total - (index + 1),
                "node": step["node_id"],
                "prompt": node.get("prompt", ""),
                "chosen": step["chosen"],
                "text": opt.get("text", ""),
                "why": opt.get("why", ""),
            }
    return {}


def _case_header(case: Case) -> Dict[str, Any]:
    return {
        "id": case.id,
        "title": case.title,
        "domain": case.domain,
        "section": case.section,
        "topics": list(case.topics),
        "principles": list(case.principles),
        "minutes": case.minutes,
    }


# --------------------------------------------------------------------------
# listing
# --------------------------------------------------------------------------

def case_index(cases: Sequence[Case], cert_results_path: str) -> List[Dict[str, Any]]:
    """Cases with the learner's own history attached.

    Counts of completions and any open session, so the list can offer 'resume'
    without the client having to cross-reference two endpoints.
    """
    results = load_results(cases_log_path(cert_results_path))
    done: Dict[str, List[Dict[str, Any]]] = {}
    for row in results:
        done.setdefault(row.get("case_id", ""), []).append(row)

    open_by_case: Dict[str, CaseSession] = {}
    for state in list_sessions(cert_results_path):
        if not state.finished and state.case_id not in open_by_case:
            open_by_case[state.case_id] = state

    out = []
    for case in cases:
        runs = done.get(case.id, [])
        pending = open_by_case.get(case.id)
        out.append({
            **_case_header(case),
            "nodes": len(case.nodes),
            "endings": len(case.endings),
            "longest": _longest(case),
            "attempts": len(runs),
            "verdicts": [r.get("verdict", "") for r in runs],
            "last_played": runs[-1].get("ts") if runs else None,
            "open_session": pending.session_id if pending else None,
            "open_decisions": pending.decisions if pending else 0,
        })
    return out
