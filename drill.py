#!/usr/bin/env python3
"""CISA / CPA study drill CLI.

    python drill.py drill --domain 5 -n 20
    python drill.py stats
    python drill.py validate
    python drill.py list --domain 5

Runs entirely offline on the Python standard library. No install step.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from drillkit import (  # noqa: E402
    calibration,
    cases as cases_mod,
    caserunner,
    difficulty as difficulty_mod,
    casesession,
    exam as exam_mod,
    examsession,
    games,
    itemanalysis,
    loader,
    principles as principles_mod,
    scheduler,
    session as session_mod,
    simulation,
    stats,
    store,
)
from drillkit.exam import ExamError  # noqa: E402
from drillkit.loader import Question, QuestionError  # noqa: E402

WIDTH = 78
RULE = "=" * WIDTH
THIN = "-" * WIDTH
WRAP_NOTE = ("These are kept out of your drill and exam accuracy on purpose. A\n"
             "five-second answer is not the same evidence as a worked scenario.")


def _bar(fraction: float, width: int = 12) -> str:
    filled = int(round(fraction * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _filter(questions: List[Question], args) -> List[Question]:
    out = questions
    if getattr(args, "domain", None):
        out = [q for q in out if q.domain == str(args.domain)]
    if getattr(args, "section", None):
        out = [q for q in out if q.section.upper() == args.section.upper()]
    if getattr(args, "topic", None):
        needle = args.topic.lower()
        out = [q for q in out if needle in q.topic.lower()]
    return out


def _load(args):
    outline = loader.load_outline(args.cert)
    questions = loader.load_questions(args.cert)
    return outline, questions


# ---------------------------------------------------------------- commands

def cmd_drill(args) -> int:
    outline, questions = _load(args)

    errors, _ = loader.validate(questions, outline)
    if errors:
        print("Question bank has %d error(s). Run 'validate' before drilling." % len(errors))
        for e in errors[:5]:
            print("  - %s" % e)
        return 1

    pool = _filter(questions, args)
    if not pool:
        print("No questions match those filters.")
        return 1

    rows = store.load(loader.results_path(args.cert, args.profile))
    history = store.history_by_question(rows)
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    header = None

    # Difficulty narrows the pool *before* the scheduler runs, so spaced
    # repetition still orders whatever survives. Whether the filter left enough
    # to work with is stated now, not discovered three questions in.
    wanted = difficulty_mod.normalise(getattr(args, "difficulty", ""))
    avail = difficulty_mod.availability(pool, wanted, args.number, history)
    if difficulty_mod.is_filter(wanted):
        print()
        print("Difficulty: %s  (%s)" % (wanted, difficulty_mod.CAVEAT))
        print("  %s" % avail.message())
        if avail.empty:
            spread = ", ".join("%s %d" % (k, v) for k, v in avail.counts.items())
            print("  That filter has %s available." % spread)
            print("  Nothing was served and nothing was logged.")
            return 1
        if avail.due_suppressed:
            print("  %d question(s) due for review are not %s and were excluded."
                  % (avail.due_suppressed, wanted))
        print()
    elif wanted == difficulty_mod.RAMP:
        print()
        print("Difficulty: ramp  (%s)" % difficulty_mod.CAVEAT)
        print("  %s" % avail.message())
        print()

    pool = difficulty_mod.apply(pool, wanted)

    if args.mode == "principle":
        rules = loader.load_principles(args.cert)
        if not rules:
            print("No principles defined for this cert.")
            return 1
        picked, targeted = principles_mod.select_by_weak_principles(
            pool, rules, rows, args.number, rng)
        names = {p["id"]: p.get("name", p["id"]) for p in rules}
        if targeted:
            header = "Targeting your weakest rules: %s" % "; ".join(
                names.get(t, t) for t in targeted[:3])
    else:
        picked = scheduler.select(pool, history, args.number, mode=args.mode, rng=rng)

    # Ramp reorders what the scheduler chose; it never re-selects.
    picked = difficulty_mod.present(picked, wanted)
    if wanted == difficulty_mod.RAMP and difficulty_mod.ramp_spread(picked) < 2:
        print("Note: every question the scheduler picked is '%s', so there is "
              "no ramp today." % (picked[0].difficulty if picked else "?"))
        print()

    reasons = {q.id: scheduler.explain_selection(q, history) for q in picked} if args.why else {}

    session_mod.run(
        picked,
        cert=args.cert,
        mode=args.mode,
        results_file=loader.results_path(args.cert, args.profile),
        reasons=reasons,
        principle_notes=_principle_notes(args.cert, picked),
        header=header,
    )

    # Closing disclosure: a learner must not be able to skip their due queue
    # without being told they did.
    if difficulty_mod.is_filter(wanted) and avail.due_suppressed:
        print()
        print(_wrap("Reminder: filtering to '%s' held back %d question(s) that "
                    "were due for review. They are still due; drop the filter "
                    "to see them." % (wanted, avail.due_suppressed)))
    return 0


def _principle_notes(cert: str, questions: List[Question]) -> dict:
    """Map each question to the decision rule that governs it, for in-drill display."""
    rules = loader.load_principles(cert)
    if not rules:
        return {}
    index = loader.principle_index(rules)
    names = {p["id"]: p for p in rules}
    notes = {}
    for q in questions:
        ids = index.get(q.id) or []
        if not ids:
            continue
        primary = names.get(ids[0], {})
        label = primary.get("name", ids[0])
        if len(ids) > 1:
            label += " (also: %s)" % ", ".join(names.get(i, {}).get("name", i)
                                               for i in ids[1:3])
        notes[q.id] = label
    return notes


def cmd_costumes(args) -> int:
    """One decision rule, one question from each domain it appears in."""
    outline, questions = _load(args)
    rules = loader.load_principles(args.cert)
    if not rules:
        print("No principles defined for this cert.")
        return 1

    rows = store.load(loader.results_path(args.cert, args.profile))
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    if args.principle:
        chosen = next((p for p in rules if p["id"] == args.principle), None)
        if chosen is None:
            print("Unknown principle '%s'. Available:" % args.principle)
            for p in rules:
                print("    %-24s %s" % (p["id"], p.get("name", "")))
            return 1
    else:
        stats = principles_mod.summarize(rules, questions, rows)
        weak = principles_mod.weakest(stats) or stats
        chosen = next(p for p in rules if p["id"] == weak[0].principle_id)

    pool = principles_mod.questions_for(rules, chosen["id"], questions)
    seen = {r.get("question_id") for r in rows}
    picked = principles_mod.one_per_domain(pool, rng, seen)
    if not picked:
        print("No questions mapped to that principle yet.")
        return 1

    print(RULE)
    print("SAME RULE, %d COSTUMES" % len(picked))
    print(RULE)
    print(chosen.get("name", ""))
    print()
    print(_wrap(chosen.get("statement", "")))
    print()
    print(_wrap("TRAP: %s" % chosen.get("misapplication", "")))
    print()
    print(_wrap("NOT WHEN: %s" % chosen.get("scope", "")))
    print(RULE)
    print()
    print(_wrap("The same rule now appears in %d different domains. The surface "
                "detail changes completely; the reasoning does not."
                % len({q.domain for q in picked})))

    session_mod.run(
        picked,
        cert=args.cert,
        mode="costumes",
        results_file=loader.results_path(args.cert, args.profile),
        principle_notes={q.id: chosen.get("name", "") for q in picked},
    )
    return 0


def cmd_principles(args) -> int:
    outline, questions = _load(args)
    rules = loader.load_principles(args.cert)
    if not rules:
        print("No principles defined for this cert.")
        return 1

    if args.card:
        card = principles_mod.render_card(rules)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(card + "\n")
            print("Study card written to %s" % args.out)
        else:
            print(card)
        return 0

    if args.list:
        for p in rules:
            qids = p.get("question_ids") or []
            doms = sorted({q.domain for q in questions if q.id in set(qids)})
            print("  %-24s %-46s %2d q  D%s"
                  % (p["id"], p.get("name", "")[:46], len(qids), ",".join(doms)))
        return 0

    rows = store.load(loader.results_path(args.cert, args.profile))
    if not rows:
        print("No attempts logged yet - the principle diagnostic needs data.")
        print("    python drill.py drill -n 20")
        return 0

    stats = principles_mod.summarize(rules, questions, rows)
    tested = principles_mod.weakest(stats, args.min_attempts)
    thin = principles_mod.untested(stats, args.min_attempts)

    print(RULE)
    print("DECISION RULES - %s" % args.cert.upper())
    print(RULE)
    print(_wrap("This asks a different question from 'stats'. Not which topics you "
                "are weak on, but which reasoning habits are costing you marks "
                "across all of them."))
    print()

    if tested:
        print("RANKED WEAKEST FIRST  (>=%d attempts)" % args.min_attempts)
        print("-" * WIDTH)
        print("  %-34s %6s %9s %6s" % ("Rule", "acc", "95% CI", "n"))
        for s in tested[:args.limit]:
            lo, hi = s.interval
            print("  %-34s %5.0f%% %3.0f-%3.0f%% %6d"
                  % (s.name[:34], (s.accuracy or 0) * 100, lo * 100, hi * 100, s.attempts))

        print()
        print("WHAT TO ACTUALLY FIX")
        print("-" * WIDTH)
        for s in tested[:3]:
            if (s.accuracy or 0) >= 0.8:
                continue
            print("  %s  (%.0f%%)" % (s.name, (s.accuracy or 0) * 100))
            print(_wrap("You are likely doing this instead: %s" % s.misapplication,
                        indent="    "))
            print(_wrap("Watch the boundary: %s" % s.scope, indent="    "))
            print("    Drill it:  python drill.py costumes --principle %s" % s.principle_id)
            print()

    if thin:
        print("NOT YET TESTED  (<%d attempts - no claim either way)" % args.min_attempts)
        print("-" * WIDTH)
        for s in thin[:args.limit]:
            print("  %-40s %d of %d questions seen"
                  % (s.name[:40], s.questions_seen, s.questions_total))

    print(RULE)
    return 0


def _wrap(text: str, indent: str = "") -> str:
    import textwrap
    return textwrap.fill(" ".join(str(text).split()), width=WIDTH,
                         initial_indent=indent, subsequent_indent=indent)


# ---------------------------------------------------------------- parser


def cmd_stats(args) -> int:
    outline, questions = _load(args)
    rows = store.load(loader.results_path(args.cert, args.profile))
    if args.domain:
        rows = [r for r in rows if str(r.get("domain")) == str(args.domain)]

    if not rows:
        print("No attempts logged yet. Run a drill first:")
        print("    python drill.py drill --domain 5 -n 10")
        return 0

    attempts, correct, acc = stats.overall(rows)
    seen, total = stats.coverage_summary(rows, questions)

    print(RULE)
    print("%s progress" % args.cert.upper())
    print(RULE)
    print("Lifetime      : %d/%d correct (%.0f%%)" % (correct, attempts, acc * 100))
    print("Question bank : %d of %d questions attempted at least once" % (seen, total))
    print("Study days    : %d" % stats.study_days(rows))

    last7 = stats.recent(rows, 7)
    if last7:
        a7, c7, acc7 = stats.overall(last7)
        print("Last 7 days   : %d/%d correct (%.0f%%)" % (c7, a7, acc7 * 100))

    print()
    print("BY DOMAIN")
    print("-" * WIDTH)
    for b in stats.by_domain(rows):
        print("  %-48s %s %3.0f%%  (%d/%d)" % (
            stats.domain_label(outline, b.label)[:48],
            _bar(b.accuracy), b.accuracy * 100, b.correct, b.attempts,
        ))

    print()
    print("BY TOPIC - weakest first")
    print("-" * WIDTH)
    topics = stats.by_topic(rows)
    shown = topics if args.all else topics[:args.limit]
    for b in shown:
        print("  %-48s %s %3.0f%%  (%d/%d)" % (
            b.label[:48], _bar(b.accuracy), b.accuracy * 100, b.correct, b.attempts,
        ))
    if not args.all and len(topics) > len(shown):
        print("  ... %d more (use --all)" % (len(topics) - len(shown)))

    misses = stats.unmastered(rows, questions)
    if misses:
        print()
        print("MOST-MISSED QUESTIONS")
        print("-" * WIDTH)
        for qid, topic, m, n in misses[:args.limit]:
            print("  %-16s missed %d of %d   %s" % (qid, m, n, topic[:38]))

    print()
    untouched = [q for q in questions if q.id not in {r.get("question_id") for r in rows}]
    if untouched:
        print("%d question(s) not yet seen - they are queued ahead of review items." % len(untouched))
    print(RULE)
    return 0


def cmd_simulate(args) -> int:
    """Score the diagnostics against learners whose weaknesses we planted.

    The only place in this project where the right answer is known in advance,
    which is the only way to find out whether a diagnostic works.
    """
    bank = simulation.Bank.load(args.cert)
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    checks = list(simulation.CHECKS)
    if args.checks:
        wanted = {c.strip() for c in args.checks.split(",") if c.strip()}
        checks = [c for c in checks if c.id in wanted]
        if not checks:
            print("No checks match %s. Available: %s"
                  % (args.checks, ", ".join(c.id for c in simulation.CHECKS)))
            return 1

    print(RULE)
    print("DETECTION HARNESS")
    print(RULE)
    print("  %d checks x %d sample sizes x %d seeds, against %d real questions"
          % (len(checks), len(sizes), args.seeds, len(bank.questions)))
    print("  Every check also runs against a learner with nothing planted.")
    print()

    measures: dict = {}
    started = time.time()
    results = simulation.run_sweep(
        bank, checks=checks, sizes=sizes, seeds=args.seeds,
        progress=lambda label: print("  running %s ..." % label, flush=True),
        measures=measures)
    print("  done in %.0fs" % (time.time() - started))
    print()

    print("  %-4s %-38s %-19s %-19s" % ("#", "check", "detected", "false positive"))
    print("  " + THIN[:84])
    for cell in results:
        check = simulation.check_by_id(cell.check_id)
        d, f = cell.detection, cell.false_positive
        print("  %-4s %-38s %5s [%3.0f-%3.0f]   %5s [%3.0f-%3.0f]  %s"
              % (("%s@%d" % (cell.check_id, cell.attempts)),
                 check.title[:38],
                 simulation._pct(d.rate), d.interval[0] * 100, d.interval[1] * 100,
                 simulation._pct(f.rate), f.interval[0] * 100, f.interval[1] * 100,
                 "TRUSTWORTHY" if cell.trustworthy else ""))

    print()
    print(THIN)
    print("TRUSTWORTHY FROM")
    print(THIN)
    for check in checks:
        n = simulation.trustworthy_from(results, check.id)
        print("  %-4s %-44s %s"
              % (check.id, check.title[:44],
                 ("%d answers" % n) if n else "never, in this sweep"))

    if args.write:
        report = simulation.render_report(results, bank, args.seeds, sizes,
                                          measures)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            args.out)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(report)
        print()
        print("Report written to %s" % path)
    else:
        print()
        print("Add --write to regenerate %s" % args.out)
    return 0


def cmd_calibration(args) -> int:
    """Did you know that you knew?

    Reports the curve, the gap and the lists. There is deliberately no single
    "calibration score" - collapsing this to one number is the same mistake
    ruled out for cases and for the scaled exam estimate.
    """
    outline, questions = _load(args)
    rules = loader.load_principles(args.cert)
    results_path = loader.results_path(args.cert, args.profile)

    if args.target is not None:
        settings = loader.load_settings(args.cert, args.profile)
        raw = args.target.strip()
        if raw and calibration.parse_target(raw) is None:
            print("Target date must be YYYY-MM-DD.")
            return 1
        if raw:
            settings["target_date"] = raw
        else:
            settings.pop("target_date", None)
        loader.save_settings(args.cert, settings, args.profile)
        print("Target date %s." % ("set to %s" % raw if raw else "cleared"))
        if not args.show:
            return 0

    target = calibration.parse_target(
        loader.load_settings(args.cert, args.profile).get("target_date"))
    rows = store.load(results_path)
    data = calibration.report(rows, questions, rules, target)

    print(RULE)
    print("CALIBRATION")
    print(RULE)
    if not data["labelled"]:
        print()
        print("No answers carry a confidence rating yet.")
        print("Confidence is captured with the answer - try:  python drill.py drill -n 10")
        if data["unlabelled"]:
            print("(%d earlier answer(s) predate the feature and stay unlabelled.)"
                  % data["unlabelled"])
        return 0

    print("%d of %d answers rated%s" % (
        data["labelled"], data["attempts"],
        "; %d predate the feature" % data["unlabelled"] if data["unlabelled"] else ""))
    print()
    print("  %-11s %-9s %-10s %s" % ("confidence", "answers", "accuracy", "95% interval"))
    print("  " + THIN[:64])
    for cell in data["curve"]:
        if not cell["attempts"]:
            print("  %-11s %-9s %-10s %s" % (cell["level"], "0", "-", "no data"))
            continue
        marker = "" if cell["enough"] else "   (too few to call)"
        print("  %-11s %-9d %-10s %d-%d%%%s" % (
            cell["level"], cell["attempts"],
            "%.0f%%" % (cell["accuracy"] * 100),
            round(cell["low"] * 100), round(cell["high"] * 100), marker))

    gap = data["gap"]
    print()
    if gap["gap"] is None:
        print("  Overconfidence gap: not enough rated answers yet.")
    else:
        print("  Overconfidence gap: %+.0f points  (confident %.0f%% vs %.0f%% when not confident)"
              % (gap["gap"] * 100, gap["confident_accuracy"] * 100,
                 gap["other_accuracy"] * 100))
        print("    95%% interval on the gap: %+.0f to %+.0f points, over %d confident "
              "and %d other answers%s"
              % (round(gap["gap_low"] * 100), round(gap["gap_high"] * 100),
                 gap["confident_attempts"], gap["other_attempts"],
                 "" if gap["enough"] else "  (too few to call)"))
        # The interval, not the point estimate, is what says whether there is
        # anything here. A +6 with a band from -7 to +19 is no relationship.
        if gap["spans_zero"]:
            print("    That range includes zero, so this is not yet evidence that your")
            print("    confidence tracks whether you are right. Keep answering.")
        else:
            print("    The range excludes zero: your confidence is carrying real signal.")

    if data["dangerous"]:
        print()
        print(THIN)
        print("CONFIDENT AND WRONG  (%d) - nothing else in the tool surfaces these"
              % len(data["dangerous"]))
        print(THIN)
        for item in data["dangerous"][:args.limit]:
            print("  %-16s %s" % (item["question_id"], item["topic"]))
            if item["rule"]:
                print("      rule: %s" % item["rule"])

    if data["lucky"]:
        print()
        print(THIN)
        print("CORRECT BUT NOT KNOWN  (%d) - guessed or unsure, and right"
              % len(data["lucky"]))
        print(THIN)
        for item in data["lucky"][:args.limit]:
            print("  %-16s %-9s %s"
                  % (item["question_id"], item["confidence"], item["topic"]))

    ranked = [b for b in data["by_rule"] if b["dangerous"]][:args.limit]
    if ranked:
        print()
        print(THIN)
        print("WHERE THE OVERCONFIDENCE LIVES - by decision rule")
        print(THIN)
        for bucket in ranked:
            note = "" if bucket["enough"] else "  (thin)"
            acc = ("%.0f%%" % (bucket["confident_accuracy"] * 100)
                   if bucket["confident_accuracy"] is not None else "-")
            print("  %-38s %d confident-wrong, %s of %d confident%s"
                  % (bucket["label"][:38], bucket["dangerous"], acc,
                     bucket["confident_attempts"], note))

    _print_projection(data["projection"])
    return 0


def _print_projection(p) -> None:
    print()
    print(THIN)
    print("COVERAGE PROJECTION")
    print(THIN)
    print("  %d of %d questions seen %d+ times" % (p["covered"], p["questions"],
                                                   p["coverage_target"]))
    if not p["enough"]:
        print("  %d answer(s) in the last %d days - too few to project a pace from."
              % (p["recent_attempts"], p["window_days"]))
        print("  Needs about %d before the arithmetic says anything."
              % p["min_pace_attempts"])
        if p["target"]:
            print("  Target %s (%d days away)." % (p["target"], p["days_to_target"]))
        return
    print("  Pace: %.1f answers/day over the last %d days (%d answers on %d active day%s)"
          % (p["pace_per_day"], p["window_days"], p["recent_attempts"],
             p["active_days"], "" if p["active_days"] == 1 else "s"))
    print("  At that pace, every question reaches %d attempts in %d days - around %s"
          % (p["coverage_target"], round(p["days_needed"]), p["projected_date"]))
    if p["target"]:
        if p["margin_days"] is None:
            print("  Target %s." % p["target"])
        elif p["margin_days"] >= 0:
            print("  Target %s - about %d days to spare." % (p["target"], p["margin_days"]))
        else:
            print("  Target %s - roughly %d days short at this pace."
                  % (p["target"], abs(p["margin_days"])))
    else:
        print("  No target date set.  python drill.py calibration --target YYYY-MM-DD")
    print()
    print("  Coverage arithmetic only. This is not a retention forecast and does not")
    print("  claim you will remember what you covered.")


def cmd_case(args) -> int:
    """Play a branching case in the terminal.

    Every other feature works from both the CLI and the web app; a case runner
    that only existed in the browser would break that symmetry, and the terminal
    is where the format gets stress-tested fastest.
    """
    results_path = loader.results_path(args.cert, args.profile)
    try:
        case_list = cases_mod.load_cases(args.cert)
    except cases_mod.CaseError as exc:
        print("Cannot load cases: %s" % exc)
        return 1

    if args.stats:
        caserunner.summarise(
            casesession.load_results(casesession.cases_log_path(results_path)))
        return 0

    if not case_list:
        print("No cases found in %s" % cases_mod.cases_dir(args.cert))
        return 1

    if args.resume:
        try:
            state = casesession.load(results_path, args.resume)
        except casesession.CaseSessionError as exc:
            print(str(exc))
            return 1
        if state.finished:
            print("That case is already finished. Its debrief:")
        case = next((c for c in case_list if c.id == state.case_id), None)
        if case is None:
            print("The case '%s' no longer exists." % state.case_id)
            return 1
        runner = caserunner.CaseRunner(case, args.cert, results_path)
        if state.finished:
            runner._debrief(state)
            return 0
        return runner.run(state)

    index = casesession.case_index(case_list, results_path)
    if args.list or not args.case_id:
        print(RULE)
        print("BRANCHING CASES")
        print(RULE)
        for entry in index:
            played = ("%d run(s)" % entry["attempts"]) if entry["attempts"] else "not played"
            openish = ("  [open session %s, %d decisions in]"
                       % (entry["open_session"], entry["open_decisions"])) if entry["open_session"] else ""
            print()
            print("  %-24s  D%s  %d nodes, %d endings  ~%d min"
                  % (entry["id"], entry["domain"], entry["nodes"],
                     entry["endings"], entry["minutes"]))
            print("    %s" % entry["title"])
            print("    %s%s" % (played, openish))
        print()
        if args.list:
            return 0
        print("Play one with:  python drill.py case <id>")
        return 0

    case = next((c for c in case_list if c.id == args.case_id), None)
    if case is None:
        print("No case with id '%s'. Try 'python drill.py case --list'." % args.case_id)
        return 1

    errors, _ = cases_mod.validate_case(case)
    if errors:
        print("That case has %d validation error(s). Run 'validate' first." % len(errors))
        return 1

    return caserunner.CaseRunner(case, args.cert, results_path).run()


def cmd_validate(args) -> int:
    try:
        outline, questions = _load(args)
    except QuestionError as exc:
        print("FAIL: %s" % exc)
        return 1

    errors, warnings = loader.validate(questions, outline)

    pairs = loader.load_pairs(args.cert)
    if pairs:
        perrors, pwarnings = loader.validate_pairs(pairs, questions)
        errors.extend(perrors)
        warnings.extend(pwarnings)

    rules = loader.load_principles(args.cert)
    if rules:
        rerrors, rwarnings = loader.validate_principles(rules, questions)
        errors.extend(rerrors)
        warnings.extend(rwarnings)

    try:
        case_list = cases_mod.load_cases(args.cert)
    except cases_mod.CaseError as exc:
        case_list = []
        errors.append(str(exc))
    if case_list:
        cerrors, cwarnings = cases_mod.validate_all(
            case_list, outline, {p["id"] for p in rules})
        errors.extend(cerrors)
        warnings.extend(cwarnings)

    print("Checked %d question(s) across %d file(s)."
          % (len(questions), len({q.source_file for q in questions})))
    if pairs:
        mapped = {qid for p in pairs for qid in (p.get("question_ids") or [])}
        print("Checked %d confusable pair(s) covering %d question(s)."
              % (len(pairs), len(mapped)))
    if case_list:
        print("Checked %d branching case(s): %d decision nodes, %d endings."
              % (len(case_list),
                 sum(len(c.nodes) for c in case_list),
                 sum(len(c.endings) for c in case_list)))
    if rules:
        index = loader.principle_index(rules)
        covered = sum(1 for q in questions if q.id in index)
        judgment_gaps = [q.id for q in questions
                         if q.id not in index and not q.no_principle
                         and games.ask_type(q) != "definition"]
        print("Checked %d decision rule(s) covering %d of %d question(s)."
              % (len(rules), covered, len(questions)))
        if judgment_gaps:
            # Worth surfacing: a judgment-worded stem with no governing rule is
            # usually a question that tests recall while promising judgment.
            warnings.append(
                "%d judgment-worded question(s) map to no decision rule, which "
                "usually means they test recall rather than judgment: %s"
                % (len(judgment_gaps), ", ".join(sorted(judgment_gaps)[:6])
                   + (" ..." if len(judgment_gaps) > 6 else "")))

    if warnings and not args.quiet:
        print()
        print("Warnings (%d):" % len(warnings))
        for w in warnings:
            print("  ! %s" % w)

    if errors:
        print()
        print("Errors (%d):" % len(errors))
        for e in errors:
            print("  X %s" % e)
        return 1

    print("OK - schema, answer keys, distractor explanations and topic tags all check out.")
    return 0


def cmd_list(args) -> int:
    outline, questions = _load(args)
    domains = sorted({q.domain for q in questions}) if not args.domain else [str(args.domain)]

    for dom in domains:
        print(RULE)
        print(stats.domain_label(outline, dom))
        print(RULE)
        rows = loader.coverage(questions, outline, dom)
        current_section = None
        for sec, topic, n in rows:
            if sec != current_section:
                current_section = sec
                name = outline.section_name(dom, sec)
                print("  %s - %s" % (sec, name.upper() if name else ""))
            flag = "     " if n else "  <-- "
            print("      %-52s %2d%s" % (topic[:52], n, flag.rstrip()))
        print("      %-52s %2d" % ("TOTAL", sum(n for _, _, n in rows)))
        print()
    return 0


def cmd_exam(args) -> int:
    outline, questions = _load(args)
    results_path = loader.results_path(args.cert, args.profile)

    if args.list:
        return _exam_list(results_path)
    if args.review:
        return _exam_review(args, outline, questions, results_path)

    errors, _ = loader.validate(questions, outline)
    if errors:
        print("Question bank has %d error(s). Run 'validate' first." % len(errors))
        return 1

    if args.resume:
        state = exam_mod.load(results_path, args.resume)
        if state.submitted:
            print("Exam %s was already submitted. Review it with:" % state.exam_id)
            print("    python drill.py exam --review %s" % state.exam_id)
            return 1
        lookup = {q.id: q for q in questions}
        missing = [qid for qid in state.question_ids if qid not in lookup]
        if missing:
            print("Cannot resume: %d question(s) in this exam are no longer in "
                  "the bank." % len(missing))
            return 1
        picked = [lookup[qid] for qid in state.question_ids]
        print("Resuming exam %s - %s remaining."
              % (state.exam_id, exam_mod.format_hms(
                  state.duration_seconds - state.elapsed_seconds)))
    else:
        pool = _filter(questions, args)
        if not pool:
            print("No questions match those filters.")
            return 1
        rng = random.Random(args.seed) if args.seed is not None else random.Random()
        state, picked = exam_mod.new_exam(
            pool, outline, args.cert, total=args.number,
            minutes=args.minutes, rng=rng,
        )
        exam_mod.save(state, results_path)

    runner = examsession.ExamRunner(state, picked, outline, results_path)
    result = runner.run()
    if result is not None:
        examsession.render_report(result, outline)
    return 0


def _exam_list(results_path: str) -> int:
    exams = exam_mod.list_exams(results_path)
    if not exams:
        print("No mock exams yet. Start one with:  python drill.py exam")
        return 0
    print("%-10s %-18s %-13s %-11s %s"
          % ("ID", "STARTED", "STATUS", "ANSWERED", "TIME USED"))
    print("-" * WIDTH)
    for s in exams:
        status = "submitted" if s.submitted else "in progress"
        print("%-10s %-18s %-13s %-11s %s" % (
            s.exam_id, s.created[:16].replace("T", " "), status,
            "%d/%d" % (s.answered, s.total),
            exam_mod.format_hms(s.elapsed_seconds),
        ))
    print()
    print("Resume:  python drill.py exam --resume <id>")
    print("Review:  python drill.py exam --review <id>")
    return 0


def _exam_review(args, outline, questions, results_path: str) -> int:
    state = exam_mod.load(results_path, args.review)
    result = exam_mod.score(state, questions, outline)
    if not state.submitted:
        print("Note: exam %s has not been submitted; scoring it as it stands.\n"
              % state.exam_id)
    examsession.render_report(result, outline)
    if result.missed:
        examsession.render_review(result, state)
    return 0


def cmd_items(args) -> int:
    outline, questions = _load(args)
    rows = store.load(loader.results_path(args.cert, args.profile))
    if args.domain:
        questions = [q for q in questions if q.domain == str(args.domain)]
        rows = [r for r in rows if str(r.get("domain")) == str(args.domain)]

    if not rows:
        print("No attempts logged yet - item analysis needs data to work from.")
        print("Drill for a while, then come back.")
        return 0

    item_stats = itemanalysis.analyze(rows, questions, args.min_attempts)
    health = itemanalysis.bank_health(item_stats)

    print(RULE)
    print("ITEM ANALYSIS - %s" % args.cert.upper())
    print(RULE)
    print("Questions in scope : %d" % health.total_questions)
    print("Served at least once: %d   never served: %d"
          % (health.served, health.never_served))
    print("With enough data for statistics (>=%d attempts): %d"
          % (args.min_attempts, health.with_stats))
    if health.mean_p_value is not None:
        print("Mean difficulty (p): %.2f" % health.mean_p_value)
    if health.mean_discrimination is not None:
        print("Mean discrimination: %+.2f" % health.mean_discrimination)

    if health.with_stats:
        print()
        print("DIFFICULTY SPREAD")
        print("-" * WIDTH)
        for label, n in health.difficulty_spread.items():
            share = n / health.with_stats if health.with_stats else 0
            print("  %-18s %s %3d" % (label, _bar(share), n))

    print()
    print("TOPICS - weakest first, ranked by lower confidence bound")
    print("-" * WIDTH)
    print("  %-42s %6s %8s  %s" % ("Topic", "p", "95% CI", "n"))
    rollup = itemanalysis.topic_rollup(item_stats)
    shown = rollup if args.all else rollup[:args.limit]
    for label, attempts, correct, p, (lo, hi) in shown:
        print("  %-42s %5.0f%% %3.0f-%3.0f%%  %d"
              % (label[:42], p * 100, lo * 100, hi * 100, attempts))
    if not args.all and len(rollup) > len(shown):
        print("  ... %d more (use --all)" % (len(rollup) - len(shown)))

    suspect = itemanalysis.needs_rewrite(item_stats)
    if suspect:
        print()
        print("QUESTIONS WORTH REWRITING")
        print("-" * WIDTH)
        print("  These flags describe the *question*, not you.")
        for s in suspect[:args.limit]:
            disc = "%+.2f" % s.discrimination if s.discrimination is not None else "  n/a"
            print("  %-16s p=%.2f disc=%s n=%-3d %s"
                  % (s.question_id, s.p_value or 0, disc, s.attempts,
                     ",".join(s.flags)[:28]))
        print()
        print("  TOO_EASY           everyone gets it; carries no information")
        print("  NEG_DISCRIMINATION you get it right on bad days, wrong on good ones")
        print("  KEY_CHALLENGED     a distractor beats the key; check for ambiguity")
        print("  DEAD_OPTION        an option nobody ever picks; wasted slot")

    hardest = sorted(
        [s for s in item_stats if s.has_stats],
        key=lambda s: (s.p_value or 0, -s.attempts),
    )
    if hardest:
        print()
        print("HARDEST ITEMS FOR YOU")
        print("-" * WIDTH)
        for s in hardest[:args.limit]:
            lo, hi = s.interval
            secs = "%4.0fs" % s.median_seconds if s.median_seconds else "   -"
            print("  %-16s %3.0f%% (%3.0f-%3.0f%%) n=%-3d %s  %s"
                  % (s.question_id, (s.p_value or 0) * 100, lo * 100, hi * 100,
                     s.attempts, secs, s.topic[:24]))

    print(RULE)
    return 0


def cmd_game(args) -> int:
    outline, questions = _load(args)
    gpath = games.games_path(loader.results_path(args.cert, args.profile))

    if args.which == "stats":
        return _game_stats(gpath)

    errors, _ = loader.validate(questions, outline)
    if errors:
        print("Question bank has %d error(s). Run 'validate' first." % len(errors))
        return 1

    pool = _filter(questions, args)
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    picked = games.pick(pool, args.number, args.which, rng)
    if not picked:
        print("No questions available for that game with those filters.")
        return 1

    cls = {"coldread": games.ColdRead, "autopsy": games.Autopsy}[args.which]
    cls(args.cert, gpath, rng=rng).run(picked)
    return 0


def _game_stats(gpath: str) -> int:
    rows = games.load_games(gpath)
    if not rows:
        print("No game results yet. Try:")
        print("    python drill.py game coldread -n 10")
        print("    python drill.py game autopsy -n 8")
        return 0

    print(RULE)
    print("GAME RESULTS")
    print(RULE)
    print(WRAP_NOTE)
    print()

    by_game: dict = {}
    for r in rows:
        b = by_game.setdefault(r.get("game", "?"), {"n": 0, "ok": 0, "secs": 0.0})
        b["n"] += 1
        b["ok"] += 1 if r.get("correct") else 0
        b["secs"] += float(r.get("seconds", 0) or 0)

    for name, b in sorted(by_game.items()):
        pace = b["secs"] / b["n"] if b["n"] else 0
        print("  %-12s %s %3.0f%%  (%d/%d)  %.0fs per item"
              % (name, _bar(b["ok"] / b["n"]), 100 * b["ok"] / b["n"],
                 b["ok"], b["n"], pace))

    # Cold Read: which question types get misread, and in what direction.
    misreads: dict = {}
    for r in rows:
        if r.get("game") != "coldread" or r.get("correct"):
            continue
        m = re.match(r"read=(\w+) expected=(\w+)", r.get("detail", "") or "")
        if m:
            misreads[(m.group(2), m.group(1))] = misreads.get((m.group(2), m.group(1)), 0) + 1
    if misreads:
        print()
        print("MOST COMMON MISREADS  (actual -> what you read it as)")
        print("-" * WIDTH)
        for (expected, read), n in sorted(misreads.items(), key=lambda kv: -kv[1])[:8]:
            print("  %-12s -> %-12s  %d time(s)" % (expected, read, n))

    # Cold Read self-report on prediction quality, kept apart from the graded part.
    reports: dict = {}
    for r in rows:
        if r.get("game") == "coldread" and r.get("self_report"):
            reports[r["self_report"]] = reports.get(r["self_report"], 0) + 1
    if reports:
        total = sum(reports.values())
        print()
        print("PREDICTION (self-reported, not graded)")
        print("-" * WIDTH)
        for key, label in (("y", "matched"), ("c", "close"), ("n", "missed")):
            n = reports.get(key, 0)
            print("  %-10s %s %3.0f%%  (%d/%d)"
                  % (label, _bar(n / total), 100 * n / total, n, total))

    topics: dict = {}
    for r in rows:
        key = "D%s%s | %s" % (r.get("domain", "?"), r.get("section", ""), r.get("topic", "?"))
        t = topics.setdefault(key, [0, 0])
        t[0] += 1
        t[1] += 1 if r.get("correct") else 0
    weak = sorted(topics.items(), key=lambda kv: (kv[1][1] / kv[1][0], -kv[1][0]))
    print()
    print("BY TOPIC - weakest first")
    print("-" * WIDTH)
    for label, (n, ok) in weak[:10]:
        print("  %-48s %s %3.0f%%  (%d/%d)"
              % (label[:48], _bar(ok / n), 100 * ok / n, ok, n))
    print(RULE)
    return 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="drill.py",
        description="Offline study drills for CISA (and later CPA).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python drill.py drill --domain 5 -n 20\n"
               "  python drill.py drill --topic encryption -n 10\n"
               "  python drill.py drill --mode weakest -n 15\n"
               "  python drill.py exam                      full 150q / 240min mock\n"
               "  python drill.py exam -n 50 --minutes 80   shorter timed set\n"
               "  python drill.py exam --list\n"
               "  python drill.py game coldread -n 10      options hidden\n"
               "  python drill.py game autopsy -n 8        why is each option wrong\n"
               "  python drill.py stats\n"
               "  python drill.py items\n"
               "  python drill.py validate\n",
    )
    p.add_argument("--cert", default="cisa", help="which cert folder to use (default: cisa)")
    p.add_argument("--profile", default=os.environ.get("DRILL_PROFILE"),
                   help="keep results separate per person sharing the bank "
                        "(also settable with the DRILL_PROFILE environment variable)")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("drill", help="run a quiz session")
    d.add_argument("-n", "--number", type=int, default=10, help="how many questions (default 10)")
    d.add_argument("--domain", help="restrict to one domain, e.g. 5")
    d.add_argument("--section", help="restrict to a section, e.g. A")
    d.add_argument("--topic", help="substring match on topic name")
    d.add_argument("--mode", default="smart",
                   choices=["smart", "due", "weakest", "random", "principle"],
                   help="selection strategy (default smart). 'principle' targets "
                        "your weakest decision rules, preferring unseen questions.")
    d.add_argument("--difficulty", choices=list(difficulty_mod.CHOICES),
                   help="author-assigned difficulty. easy/medium/hard filter "
                        "strictly (never topped up from another band); 'ramp' "
                        "keeps the scheduler's selection and orders it easiest "
                        "first. Labels are the author's, unchecked against results.")
    d.add_argument("--why", action="store_true", help="show why each question was selected")
    d.add_argument("--seed", type=int, help="fixed shuffle seed, for repeatable runs")
    d.set_defaults(func=cmd_drill)

    s = sub.add_parser("stats", help="accuracy by domain and topic, weakest first")
    s.add_argument("--domain", help="restrict to one domain")
    s.add_argument("--limit", type=int, default=12, help="rows per section (default 12)")
    s.add_argument("--all", action="store_true", help="show every topic")
    s.set_defaults(func=cmd_stats)

    v = sub.add_parser("validate", help="check the question bank for problems")
    v.add_argument("--quiet", action="store_true", help="errors only, hide warnings")
    v.set_defaults(func=cmd_validate)

    l = sub.add_parser("list", help="question counts per outline topic")
    l.add_argument("--domain", help="restrict to one domain")
    l.set_defaults(func=cmd_list)

    e = sub.add_parser("exam", help="timed mock exam under blueprint weights")
    e.add_argument("-n", "--number", type=int, default=exam_mod.DEFAULT_QUESTIONS,
                   help="questions in the exam (default %d, the real count)"
                        % exam_mod.DEFAULT_QUESTIONS)
    e.add_argument("--minutes", type=int, default=exam_mod.DEFAULT_MINUTES,
                   help="time limit (default %d, the real allowance)"
                        % exam_mod.DEFAULT_MINUTES)
    e.add_argument("--domain", help="restrict the pool to one domain")
    e.add_argument("--section", help="restrict the pool to one section")
    e.add_argument("--topic", help="restrict the pool by topic substring")
    e.add_argument("--resume", metavar="ID", help="continue a saved exam")
    e.add_argument("--review", metavar="ID", help="re-score and walk a finished exam")
    e.add_argument("--list", action="store_true", help="list saved exams")
    e.add_argument("--seed", type=int, help="fixed sampling seed")
    e.set_defaults(func=cmd_exam)

    i = sub.add_parser("items", help="item analysis: difficulty, discrimination, distractors")
    i.add_argument("--domain", help="restrict to one domain")
    i.add_argument("--min-attempts", type=int,
                   default=itemanalysis.MIN_ATTEMPTS_STATS,
                   help="attempts required before an item gets statistics "
                        "(default %d)" % itemanalysis.MIN_ATTEMPTS_STATS)
    i.add_argument("--limit", type=int, default=12, help="rows per section")
    i.add_argument("--all", action="store_true", help="show every topic")
    i.set_defaults(func=cmd_items)

    g = sub.add_parser("game", help="short-form drills; logged separately from stats")
    g.add_argument("which", choices=["coldread", "autopsy", "stats"],
                   help="coldread: options hidden, name what is being asked. "
                        "autopsy: match distractors to why they are wrong. "
                        "stats: results so far.")
    g.add_argument("-n", "--number", type=int, default=10, help="how many (default 10)")
    g.add_argument("--domain", help="restrict to one domain")
    g.add_argument("--section", help="restrict to one section")
    g.add_argument("--topic", help="substring match on topic name")
    g.add_argument("--seed", type=int, help="fixed shuffle seed")
    g.set_defaults(func=cmd_game)

    pr = sub.add_parser("principles",
                        help="diagnose which reasoning habits cost you marks")
    pr.add_argument("--min-attempts", type=int, default=4,
                    help="attempts before a rule gets a verdict (default 4)")
    pr.add_argument("--limit", type=int, default=12, help="rows per section")
    pr.add_argument("--list", action="store_true", help="list the rules and coverage")
    pr.add_argument("--card", action="store_true",
                    help="print the study card, generated from the taxonomy")
    pr.add_argument("--out", help="with --card, write to this file instead of stdout")
    pr.set_defaults(func=cmd_principles)

    c = sub.add_parser("costumes",
                       help="one decision rule, one question per domain")
    c.add_argument("--principle", help="rule id (default: your weakest)")
    c.add_argument("--seed", type=int, help="fixed shuffle seed")
    c.set_defaults(func=cmd_costumes)

    ca = sub.add_parser("case",
                        help="branching audit case: sequential judgment, graded options")
    ca.add_argument("case_id", nargs="?",
                    help="which case to play (default: pick from a list)")
    ca.add_argument("--list", action="store_true", help="list available cases")
    ca.add_argument("--resume", metavar="ID", help="continue a saved case session")
    ca.add_argument("--stats", action="store_true", help="your case history")
    ca.set_defaults(func=cmd_case)

    cb = sub.add_parser("calibration",
                        help="did you know that you knew? confidence vs accuracy")
    cb.add_argument("--target", metavar="YYYY-MM-DD",
                    help="set your target exam date (empty string clears it)")
    cb.add_argument("--show", action="store_true",
                    help="print the report as well when setting a target")
    cb.add_argument("--limit", type=int, default=12,
                    help="rows per list (default 12)")
    cb.set_defaults(func=cmd_calibration)

    sm = sub.add_parser("simulate",
                        help="score the diagnostics against planted weaknesses")
    sm.add_argument("--seeds", type=int, default=simulation.DEFAULT_SEEDS,
                    help="runs per cell (default %d); a single seed is a coin flip"
                         % simulation.DEFAULT_SEEDS)
    sm.add_argument("--sizes", default=",".join(
                        str(s) for s in simulation.DEFAULT_SAMPLE_SIZES),
                    help="comma-separated history sizes to sweep")
    sm.add_argument("--checks",
                    help="comma-separated check ids (default: all)")
    sm.add_argument("--write", action="store_true",
                    help="regenerate the committed report")
    sm.add_argument("--out", default="DETECTION.md",
                    help="report path, relative to the repo root")
    sm.set_defaults(func=cmd_simulate)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except QuestionError as exc:
        print("Question bank problem: %s" % exc)
        return 1
    except ExamError as exc:
        print("Exam problem: %s" % exc)
        return 1
    except KeyboardInterrupt:
        print("\nStopped. Answers up to this point were saved.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
