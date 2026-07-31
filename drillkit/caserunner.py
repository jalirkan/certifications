"""Terminal runner for branching cases.

Sits alongside `examsession.py` for the same reason: `casesession.py` owns state
and the debrief, this owns the conversation with a person at a prompt.

The interface is deliberately quiet during the run. No verdict, no colour, no
running tally, no "good choice" - only the situation, the prompt, the options
and the neutral consequence of what you did. Everything held back arrives at
the debrief. Reassuring the learner between decisions would turn the case into a
series of multiple-choice questions with narration, and destroy the thing the
format exists to train: living with a choice whose cost appears two steps later.
"""

from __future__ import annotations

import textwrap
from typing import Dict, List, Optional

from . import casesession
from .cases import Case, longest_path

WIDTH = 78
RULE = "=" * WIDTH
THIN = "-" * WIDTH

QUALITY_LABEL = {
    "best": "best",
    "defensible": "defensible",
    "poor": "poor",
}

VERDICT_LABEL = {
    "strong": "STRONG",
    "acceptable": "ACCEPTABLE",
    "weak": "WEAK",
    "failed": "FAILED",
}


def wrap(text: str, indent: str = "") -> str:
    out = []
    for para in str(text).split("\n"):
        para = para.strip()
        if not para:
            out.append("")
            continue
        out.append(textwrap.fill(" ".join(para.split()), width=WIDTH,
                                 initial_indent=indent, subsequent_indent=indent))
    return "\n".join(out)


class CaseRunner:
    def __init__(self, case: Case, cert: str, results_path: str):
        self.case = case
        self.cert = cert
        self.results_path = results_path

    # ---- the run ------------------------------------------------------
    def run(self, state: Optional[casesession.CaseSession] = None) -> int:
        case = self.case
        resuming = state is not None
        if state is None:
            state = casesession.start(case, self.cert)
            casesession.save(state, self.results_path)

        print()
        print(RULE)
        print("  %s" % case.title.upper())
        print("  D%s%s  ·  about %d minutes  ·  %d decisions at most"
              % (case.domain, case.section, case.minutes, longest_path(case)))
        print(RULE)

        if resuming:
            print()
            print(wrap("Resuming. %d decision(s) already made." % state.decisions))
            print()
            for entry in casesession.public_trail(case, state):
                print(wrap("[%s] you chose %s" % (entry["node"], entry["chosen"]), "  "))
                print(wrap(entry["consequence"], "    "))
                print()
        else:
            print()
            print(wrap(case.opening))

        longest = longest_path(case)
        while not state.finished:
            node = casesession.public_node(
                case, state.current, state.decisions + 1, longest)
            choice = self._ask(node)
            if choice is None:
                print()
                print(wrap("Saved. Resume with:  python drill.py case --resume %s"
                           % state.session_id))
                casesession.save(state, self.results_path)
                return 0
            result = casesession.choose(case, state, node["id"], choice)
            casesession.save(state, self.results_path)

            print()
            print(wrap(result["consequence"], "  "))
            print()

        casesession.record(case, state, self.results_path)
        self._debrief(state)
        return 0

    def _ask(self, node: Dict) -> Optional[str]:
        print(THIN)
        print("  Decision %d" % node["position"])
        print(THIN)
        print(wrap(node["situation"]))
        print()
        print(wrap(node["prompt"]))
        print()

        keys = []
        for opt in node["options"]:
            key = str(opt["key"]).upper()
            keys.append(key)
            print(wrap("%s)  %s" % (key, opt["text"]), "").replace("\n", "\n    "))
            print()

        while True:
            try:
                raw = input("  Your call (%s, or 'q' to save and stop): "
                            % "/".join(keys)).strip().upper()
            except (EOFError, KeyboardInterrupt):
                print()
                return None
            if raw in ("Q", "QUIT", "EXIT"):
                return None
            if raw in keys:
                return raw
            print("  Enter one of: %s" % ", ".join(keys))

    # ---- the debrief --------------------------------------------------
    def _debrief(self, state: casesession.CaseSession) -> None:
        data = casesession.debrief(self.case, state)

        print()
        print(RULE)
        print("  DEBRIEF — %s" % data["case"]["title"])
        print(RULE)

        ending = data["ending"]
        print()
        print("  Outcome: %s  [%s]" % (ending["title"],
                                       VERDICT_LABEL.get(ending["verdict"], ending["verdict"])))
        print()
        print(wrap(ending["narrative"], "  "))
        print()
        print(wrap(ending["why"], "  "))

        # The single most valuable thing this feature can say.
        if data["overridden"] and data["override"]:
            o = data["override"]
            print()
            print(THIN)
            print("  THE DECISION THAT FIXED THIS")
            print(THIN)
            print(wrap(
                "The graph you walked ended at \"%s\" (%s). That is not the outcome you got. "
                "Decision %d of %d — %d decision(s) before the end — carried a consequence "
                "you do not recover from by answering the rest well."
                % (data["graph_ending"]["title"], data["graph_ending"]["verdict"],
                   o["decision"], o["of"], o["decisions_before_end"]), "  "))
            print()
            print(wrap("You chose %s: %s" % (o["chosen"], o["text"]), "  "))
            print()
            print(wrap(o["why"], "    "))

        counts = data["counts"]
        print()
        print(THIN)
        # A profile, never a percentage: collapsing a path to one number throws
        # away the part that teaches.
        print("  %d decisions — %d best, %d defensible, %d poor"
              % (data["decisions"], counts["best"], counts["defensible"], counts["poor"]))
        print(THIN)

        for step in data["walk"]:
            print()
            print("  Decision %d — you chose %s (%s)"
                  % (step["index"], step["chosen"],
                     QUALITY_LABEL.get(step["quality"], step["quality"])))
            print(wrap(step["prompt"], "    "))
            print()
            for opt in step["options"]:
                mark = ">" if opt["chosen"] else " "
                label = QUALITY_LABEL.get(opt["quality"], opt["quality"])
                tag = "  [taint: %s]" % opt["taint"] if opt.get("taint") else ""
                print(wrap("%s %s) %s  — %s%s"
                           % (mark, opt["key"], opt["text"], label, tag), "    "))
                print(wrap(opt["why"], "        "))
                print()

        if data["principles"]:
            print(THIN)
            print(wrap("Decision rules this case turns on: %s"
                       % ", ".join(data["principles"]), "  "))
        print()
        print(wrap("Logged to cases.jsonl. Case results are kept out of drill and "
                   "exam accuracy, item analysis and the scheduler.", "  "))
        print()


def summarise(rows: List[Dict]) -> None:
    """`python drill.py case --stats` — history, without a score."""
    if not rows:
        print("No cases played yet. Try:  python drill.py case")
        return
    print(RULE)
    print("CASE HISTORY")
    print(RULE)
    by_case: Dict[str, List[Dict]] = {}
    for row in rows:
        by_case.setdefault(row.get("case_id", "?"), []).append(row)

    for case_id, runs in sorted(by_case.items()):
        print()
        print("  %s  (%d run%s)" % (case_id, len(runs), "" if len(runs) == 1 else "s"))
        for row in runs:
            # ASCII only: redirected stdout on Windows falls back to cp1252,
            # which cannot encode an arrow, and a history listing must not crash.
            flag = "  <- outcome fixed by an earlier decision" if row.get("overridden") else ""
            print("    %s  %-11s  %d best / %d defensible / %d poor%s"
                  % (str(row.get("ts", ""))[:16].replace("T", " "),
                     row.get("verdict", "?"),
                     row.get("best", 0), row.get("defensible", 0),
                     row.get("poor", 0), flag))
    print()
