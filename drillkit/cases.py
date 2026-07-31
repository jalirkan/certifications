"""Branching audit cases: loading, validation and path resolution.

A case is a small directed acyclic graph of decisions. You are dropped into an
engagement, you choose, the situation moves, and you find out how it went at
the end — not at each step.

Three things make this different from a multiple-choice question, and all three
are deliberate:

* **Option quality is graded**, not binary: `best`, `defensible`, `poor`. Real
  audit judgment is rarely right-or-wrong, and the gradation is precisely what
  a four-option MCQ cannot express.
* **Feedback is deferred.** You get a neutral `consequence` as you move, never
  a verdict. Judging each step as you take it would turn the case into a series
  of MCQs with extra narration, and would destroy the thing being trained:
  living with a choice whose cost appears two steps later.
* **Some choices are unrecoverable.** An option can carry a `taint` that fixes
  the outcome regardless of what follows. Losing your independence is not
  something you recover from by answering the next question well.

This module handles data and graph integrity only. Running a case — session
state, scoring, the debrief — belongs to whatever front end drives it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .loader import Outline, cert_dir

QUALITIES = ("best", "defensible", "poor")
VERDICTS = ("strong", "acceptable", "weak", "failed")
START = "start"

REQUIRED_CASE_FIELDS = ("id", "title", "domain", "topics", "opening", "nodes", "endings")
REQUIRED_OPTION_FIELDS = ("key", "text", "quality", "next", "consequence", "why")
REQUIRED_ENDING_FIELDS = ("title", "verdict", "narrative", "why")


class CaseError(Exception):
    """Raised when a case file cannot be parsed."""


@dataclass
class Case:
    id: str
    title: str
    domain: str
    section: str = ""
    topics: List[str] = field(default_factory=list)
    principles: List[str] = field(default_factory=list)
    minutes: int = 10
    opening: str = ""
    origin: str = ""
    taints: Dict[str, str] = field(default_factory=dict)
    nodes: Dict[str, Any] = field(default_factory=dict)
    endings: Dict[str, Any] = field(default_factory=dict)
    source_file: str = ""

    # ---- graph helpers ------------------------------------------------
    def node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.nodes.get(node_id)

    def ending(self, ending_id: str) -> Optional[Dict[str, Any]]:
        return self.endings.get(ending_id)

    def is_ending(self, target: str) -> bool:
        return target in self.endings

    def option(self, node_id: str, key: str) -> Optional[Dict[str, Any]]:
        node = self.node(node_id)
        if not node:
            return None
        for opt in node.get("options", []):
            if str(opt.get("key", "")).upper() == str(key).upper():
                return opt
        return None

    def best_option(self, node_id: str) -> Optional[Dict[str, Any]]:
        node = self.node(node_id) or {}
        for opt in node.get("options", []):
            if opt.get("quality") == "best":
                return opt
        return None

    def resolve_ending(self, taints_collected: Sequence[str],
                       graph_ending: str) -> str:
        """A taint overrides wherever the graph led.

        Ordered by the case's own taint declaration, so an author controls
        precedence when a path picks up more than one.
        """
        for name, ending_id in self.taints.items():
            if name in taints_collected:
                return ending_id
        return graph_ending


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def cases_dir(cert: str) -> str:
    return os.path.join(cert_dir(cert), "cases")


def load_cases(cert: str) -> List[Case]:
    directory = cases_dir(cert)
    if not os.path.isdir(directory):
        return []

    out: List[Case] = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CaseError("%s is not valid JSON: %s" % (name, exc))
        if not isinstance(data, dict):
            raise CaseError("%s: expected an object at the top level" % name)

        known = {f for f in Case.__dataclass_fields__}
        out.append(Case(
            source_file=name,
            **{k: v for k, v in data.items() if k in known and k != "source_file"}
        ))
    return out


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate_case(case: Case, outline: Optional[Outline] = None,
                  principle_ids: Optional[Set[str]] = None
                  ) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for one case."""
    errors: List[str] = []
    warnings: List[str] = []
    at = case.id or case.source_file or "<unnamed case>"

    for f in REQUIRED_CASE_FIELDS:
        if not getattr(case, f, None):
            errors.append("%s: missing '%s'" % (at, f))
    if errors:
        return errors, warnings

    if case.source_file and case.source_file != "%s.json" % case.id:
        warnings.append("%s: id does not match filename %s" % (at, case.source_file))

    # ---- tags line up with the rest of the bank
    if outline is not None and outline.raw:
        known_topics = {t for topics in outline.all_topics().values() for t in topics}
        for topic in case.topics:
            if topic not in known_topics:
                errors.append("%s: topic '%s' is not in the outline" % (at, topic))
    if principle_ids is not None:
        for pid in case.principles:
            if pid not in principle_ids:
                errors.append("%s: principle '%s' does not exist" % (at, pid))

    # ---- endings
    for eid, ending in case.endings.items():
        for f in REQUIRED_ENDING_FIELDS:
            if not str(ending.get(f, "")).strip():
                errors.append("%s: ending '%s' missing '%s'" % (at, eid, f))
        verdict = ending.get("verdict")
        if verdict not in VERDICTS:
            errors.append("%s: ending '%s' verdict '%s' is not one of %s"
                          % (at, eid, verdict, ", ".join(VERDICTS)))

    # ---- taints must land somewhere real
    for name, ending_id in (case.taints or {}).items():
        if ending_id not in case.endings:
            errors.append("%s: taint '%s' points at unknown ending '%s'"
                          % (at, name, ending_id))

    # ---- nodes and options
    if START not in case.nodes:
        errors.append("%s: no '%s' node" % (at, START))

    declared_taints = set(case.taints or {})
    used_taints: Set[str] = set()

    for nid, node in case.nodes.items():
        where = "%s node '%s'" % (at, nid)
        if not str(node.get("situation", "")).strip():
            errors.append("%s: missing 'situation'" % where)
        if not str(node.get("prompt", "")).strip():
            errors.append("%s: missing 'prompt'" % where)

        options = node.get("options") or []
        if len(options) < 2:
            errors.append("%s: needs at least two options to be a decision" % where)

        keys = [str(o.get("key", "")).upper() for o in options]
        if len(set(keys)) != len(keys):
            errors.append("%s: duplicate option keys" % where)

        qualities = [o.get("quality") for o in options]
        if "best" not in qualities:
            errors.append("%s: no option marked 'best' — every decision needs a "
                          "defensibly correct answer" % where)
        if qualities.count("best") > 1:
            warnings.append("%s: more than one option marked 'best'" % where)

        for opt in options:
            key = opt.get("key", "?")
            for f in REQUIRED_OPTION_FIELDS:
                if not str(opt.get(f, "")).strip():
                    errors.append("%s option %s: missing '%s'" % (where, key, f))
            if opt.get("quality") not in QUALITIES:
                errors.append("%s option %s: quality '%s' is not one of %s"
                              % (where, key, opt.get("quality"), ", ".join(QUALITIES)))
            target = opt.get("next")
            if target and target not in case.nodes and target not in case.endings:
                errors.append("%s option %s: 'next' points at unknown '%s'"
                              % (where, key, target))
            taint = opt.get("taint")
            if taint:
                used_taints.add(taint)
                if taint not in declared_taints:
                    errors.append("%s option %s: undeclared taint '%s'"
                                  % (where, key, taint))

    for unused in sorted(declared_taints - used_taints):
        warnings.append("%s: taint '%s' is declared but no option applies it"
                        % (at, unused))

    # ---- graph shape
    errors.extend(_graph_errors(case))
    warnings.extend(_graph_warnings(case))

    return errors, warnings


def _targets(case: Case, node_id: str) -> List[str]:
    node = case.node(node_id) or {}
    return [o.get("next") for o in node.get("options", []) if o.get("next")]


def _graph_errors(case: Case) -> List[str]:
    errors: List[str] = []
    if START not in case.nodes:
        return errors

    # Cycles would let a case run forever, and a decision you can return to
    # unchanged is not a decision.
    colour: Dict[str, int] = {}

    def visit(nid: str, trail: List[str]) -> None:
        if case.is_ending(nid):
            return
        state = colour.get(nid, 0)
        if state == 1:
            errors.append("%s: cycle in the decision graph: %s"
                          % (case.id, " -> ".join(trail + [nid])))
            return
        if state == 2:
            return
        colour[nid] = 1
        for target in _targets(case, nid):
            visit(target, trail + [nid])
        colour[nid] = 2

    visit(START, [])
    return errors


def _graph_warnings(case: Case) -> List[str]:
    warnings: List[str] = []
    reachable_nodes, reachable_endings = reachable(case)

    for nid in case.nodes:
        if nid not in reachable_nodes:
            warnings.append("%s: node '%s' cannot be reached from start" % (case.id, nid))

    taint_endings = set((case.taints or {}).values())
    for eid in case.endings:
        if eid not in reachable_endings and eid not in taint_endings:
            warnings.append("%s: ending '%s' cannot be reached by any path" % (case.id, eid))
    return warnings


def reachable(case: Case) -> Tuple[Set[str], Set[str]]:
    """(nodes, endings) reachable from start by following options."""
    seen_nodes: Set[str] = set()
    seen_endings: Set[str] = set()
    if START not in case.nodes:
        return seen_nodes, seen_endings

    stack = [START]
    while stack:
        nid = stack.pop()
        if nid in seen_nodes:
            continue
        seen_nodes.add(nid)
        for target in _targets(case, nid):
            if case.is_ending(target):
                seen_endings.add(target)
            elif target in case.nodes:
                stack.append(target)
    return seen_nodes, seen_endings


def validate_all(cases: Sequence[Case], outline: Optional[Outline] = None,
                 principle_ids: Optional[Set[str]] = None
                 ) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    seen: Dict[str, str] = {}
    for case in cases:
        if case.id in seen:
            errors.append("duplicate case id '%s' in %s and %s"
                          % (case.id, seen[case.id], case.source_file))
        seen[case.id] = case.source_file
        e, w = validate_case(case, outline, principle_ids)
        errors.extend(e)
        warnings.extend(w)
    return errors, warnings


# --------------------------------------------------------------------------
# path analysis — what the debrief is built from
# --------------------------------------------------------------------------

@dataclass
class PathStep:
    node_id: str
    chosen: str
    quality: str
    best_key: str
    taint: Optional[str] = None


def score_path(case: Case, steps: Sequence[PathStep], graph_ending: str
               ) -> Dict[str, Any]:
    """Summarise a completed run.

    Deliberately not a percentage. A path is a profile of judgments plus an
    outcome, and collapsing that to one number would throw away the part that
    teaches.
    """
    counts = {q: 0 for q in QUALITIES}
    for step in steps:
        if step.quality in counts:
            counts[step.quality] += 1

    taints = [s.taint for s in steps if s.taint]
    ending_id = case.resolve_ending(taints, graph_ending)
    ending = case.ending(ending_id) or {}

    return {
        "case": case.id,
        "decisions": len(steps),
        "counts": counts,
        "taints": taints,
        "ending": ending_id,
        "verdict": ending.get("verdict"),
        "overridden": bool(taints) and ending_id != graph_ending,
        "principles": list(case.principles),
    }


def longest_path(case: Case) -> int:
    """Most decisions a run could require — useful for pacing estimates."""
    memo: Dict[str, int] = {}

    def depth(nid: str) -> int:
        if case.is_ending(nid) or nid not in case.nodes:
            return 0
        if nid in memo:
            return memo[nid]
        memo[nid] = 0  # guards against cycles; validation reports them separately
        best = 0
        for target in _targets(case, nid):
            best = max(best, depth(target))
        memo[nid] = best + 1
        return memo[nid]

    return depth(START) if START in case.nodes else 0
