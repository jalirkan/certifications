"""Load and validate question banks.

Question banks are plain data files, kept separate from code, so batches can be
added over time without touching the engine. JSON is the native format (stdlib
only, always works offline). YAML is also accepted if PyYAML happens to be
installed, but nothing in this project requires it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

OPTION_KEYS: Tuple[str, ...] = ("A", "B", "C", "D")

# What a stem is asking for. Optional per question: the Cold Read game derives
# this from the wording, and an explicit value here overrides that when the
# phrasing is ambiguous. Kept here rather than in games.py so validation does
# not require importing a game module.
VALID_ASKS: Tuple[str, ...] = ("first", "risk", "control", "evidence", "definition")

# Authored difficulty, ordered easiest first - the ramp relies on that order.
# These are one author's judgement and have never been checked against how the
# questions actually behave, so every surface that filters on them has to say
# so. What is enforced here is only that the vocabulary does not drift: a
# silently mangled "Medium" or "moderate" is data corruption, not a preference.
#
# `expert` was added after the other three and is deliberately empty until
# questions are authored into it. An empty band is honest; back-filling it by
# promoting existing `hard` questions would invent a distinction that nobody
# made. See EXPERT-BAND-BRIEF.md for what belongs in it.
DIFFICULTIES: Tuple[str, ...] = ("easy", "medium", "hard", "expert")

# CISA stems are judgment calls, not recall. We warn (never fail) when a stem
# does not contain one of these, because it usually means the question is
# testing memorization instead of auditor prioritization.
JUDGMENT_WORDS = (
    "BEST", "MOST", "FIRST", "GREATEST", "PRIMARY", "PRIMARILY",
    "LEAST", "NEXT", "MAJOR", "ALWAYS", "NEVER", "STRONGEST", "WEAKEST",
)


class QuestionError(Exception):
    """Raised when a question bank cannot be parsed or fails validation."""


@dataclass
class Question:
    id: str
    domain: str
    section: str
    topic: str
    stem: str
    options: Dict[str, str]
    answer: str
    why_correct: str
    why_wrong: Dict[str, str]
    difficulty: str = "medium"
    asks: str = ""
    # Reviewed and confirmed to have no governing decision rule. Distinct from
    # simply being unmapped: this is an explicit "I looked, it is fine" marker,
    # so `validate` stops reporting it and the remaining orphans stay visible.
    no_principle: bool = False
    cert: str = ""
    source_file: str = ""

    @property
    def tag(self) -> str:
        return "D%s%s" % (self.domain, self.section)

    @property
    def key(self) -> Tuple[str, str]:
        """(domain, topic) - the grouping key used by stats."""
        return (self.domain, self.topic)


@dataclass
class Outline:
    """The exam content outline, used to keep topic tags honest."""

    cert: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def topics_for(self, domain: str, section: str) -> List[str]:
        dom = self.raw.get("domains", {}).get(str(domain), {})
        sec = dom.get("sections", {}).get(str(section), {})
        return list(sec.get("topics", []))

    def all_topics(self) -> Dict[Tuple[str, str], List[str]]:
        out: Dict[Tuple[str, str], List[str]] = {}
        for dom_id, dom in self.raw.get("domains", {}).items():
            for sec_id, sec in dom.get("sections", {}).items():
                out[(dom_id, sec_id)] = list(sec.get("topics", []))
        return out

    def domain_name(self, domain: str) -> str:
        return self.raw.get("domains", {}).get(str(domain), {}).get("name", "")

    def domain_weight(self, domain: str) -> Optional[int]:
        return self.raw.get("domains", {}).get(str(domain), {}).get("weight")

    def section_name(self, domain: str, section: str) -> str:
        dom = self.raw.get("domains", {}).get(str(domain), {})
        return dom.get("sections", {}).get(str(section), {}).get("name", "")

    def knows_topic(self, domain: str, section: str, topic: str) -> bool:
        return topic in self.topics_for(domain, section)


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def repo_root() -> str:
    """The certifications/ folder, i.e. the parent of this package."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cert_dir(cert: str) -> str:
    return os.path.join(repo_root(), cert.lower())


def questions_dir(cert: str) -> str:
    return os.path.join(cert_dir(cert), "questions")


def _safe_profile(profile: Optional[str]) -> str:
    """Reduce a profile name to something safe to use as a folder name."""
    if not profile:
        return ""
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in profile.strip())
    return cleaned.strip("-").lower()[:40]


def results_dir(cert: str, profile: Optional[str] = None) -> str:
    """Where one person's answer history lives.

    The question bank is shared; results are not. Two people studying from the
    same bank need separate histories or the scheduler and the diagnostics are
    both measuring a person who does not exist.
    """
    name = _safe_profile(profile)
    base = os.path.join(cert_dir(cert), "results")
    return os.path.join(base, "profiles", name) if name else base


def results_path(cert: str, profile: Optional[str] = None) -> str:
    return os.path.join(results_dir(cert, profile), "attempts.jsonl")


def settings_path(cert: str, profile: Optional[str] = None) -> str:
    """Per-profile preferences, beside that profile's results.

    Separate from the answer log because it is mutable state rather than
    history: the log is append-only and never rewritten, this file is replaced
    whenever a setting changes.
    """
    return os.path.join(results_dir(cert, profile), "settings.json")


def load_settings(cert: str, profile: Optional[str] = None) -> Dict[str, Any]:
    path = settings_path(cert, profile)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return {}  # a corrupt settings file must not stop you studying
    return data if isinstance(data, dict) else {}


def save_settings(cert: str, settings: Dict[str, Any],
                  profile: Optional[str] = None) -> str:
    path = settings_path(cert, profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
    os.replace(tmp, path)  # atomic, so an interrupted write cannot corrupt it
    return path


def list_profiles(cert: str) -> List[str]:
    """Profiles that have been used at least once, plus the shared default."""
    found = []
    holder = os.path.join(cert_dir(cert), "results", "profiles")
    if os.path.isdir(holder):
        found = sorted(n for n in os.listdir(holder)
                       if os.path.isdir(os.path.join(holder, n)))
    return found


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

def _read_data_file(path: str) -> Any:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            raise QuestionError(
                "%s is YAML but PyYAML is not installed. Either run "
                "'pip install pyyaml' or store the batch as .json "
                "(the format the rest of the bank uses)." % os.path.basename(path)
            )
        return yaml.safe_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise QuestionError("%s is not valid JSON: %s" % (os.path.basename(path), exc))


def load_outline(cert: str) -> Outline:
    path = os.path.join(cert_dir(cert), "outline.json")
    if not os.path.exists(path):
        return Outline(cert=cert.upper(), raw={})
    return Outline(cert=cert.upper(), raw=_read_data_file(path))


def load_questions(cert: str, paths: Optional[List[str]] = None) -> List[Question]:
    """Read every question file for a cert and return Question objects.

    Structural problems (missing fields, bad answer keys) raise QuestionError,
    because a malformed bank should fail loudly rather than silently drop items.
    """
    if paths is None:
        qdir = questions_dir(cert)
        if not os.path.isdir(qdir):
            raise QuestionError("No questions folder at %s" % qdir)
        paths = sorted(
            os.path.join(qdir, name)
            for name in os.listdir(qdir)
            if os.path.splitext(name)[1].lower() in (".json", ".yaml", ".yml")
        )

    questions: List[Question] = []
    for path in paths:
        data = _read_data_file(path)
        if isinstance(data, dict):
            meta = data.get("meta", {}) or {}
            items = data.get("questions", [])
        elif isinstance(data, list):
            meta, items = {}, data
        else:
            raise QuestionError("%s: expected an object or a list" % os.path.basename(path))

        if not isinstance(items, list):
            raise QuestionError("%s: 'questions' must be a list" % os.path.basename(path))

        for idx, item in enumerate(items):
            questions.append(_build_question(item, meta, path, idx, cert))

    return questions


def _build_question(item: Any, meta: Dict[str, Any], path: str, idx: int, cert: str) -> Question:
    where = "%s[%d]" % (os.path.basename(path), idx)
    if not isinstance(item, dict):
        raise QuestionError("%s: expected an object" % where)

    def pick(name: str, default: Any = None) -> Any:
        if item.get(name) is not None:
            return item[name]
        if meta.get(name) is not None:
            return meta[name]
        return default

    qid = item.get("id")
    if not qid:
        raise QuestionError("%s: missing 'id'" % where)

    options = item.get("options")
    if not isinstance(options, dict):
        raise QuestionError("%s (%s): 'options' must be an object keyed A-D" % (where, qid))

    explanation = item.get("explanation", {}) or {}
    why_correct = item.get("why_correct") or explanation.get("correct") or ""
    why_wrong = item.get("why_wrong") or explanation.get("wrong") or {}

    return Question(
        id=str(qid),
        domain=str(pick("domain", "")),
        section=str(pick("section", "")),
        topic=str(pick("topic", "")),
        stem=str(item.get("stem", "")),
        options={str(k): str(v) for k, v in options.items()},
        answer=str(item.get("answer", "")).strip().upper(),
        why_correct=str(why_correct),
        why_wrong={str(k).upper(): str(v) for k, v in (why_wrong or {}).items()},
        difficulty=str(pick("difficulty", "medium")),
        asks=str(item.get("asks", "") or "").strip().lower(),
        no_principle=bool(item.get("no_principle", False)),
        cert=str(pick("cert", cert.upper())),
        source_file=os.path.basename(path),
    )


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate(questions: List[Question], outline: Optional[Outline] = None
             ) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings). Errors mean the bank is broken."""
    errors: List[str] = []
    warnings: List[str] = []

    seen_ids: Dict[str, str] = {}
    seen_stems: Dict[str, str] = {}

    for q in questions:
        at = "%s (%s)" % (q.id, q.source_file)

        if q.id in seen_ids:
            errors.append("%s: duplicate id, also in %s" % (at, seen_ids[q.id]))
        seen_ids[q.id] = q.source_file

        if not q.stem.strip():
            errors.append("%s: empty stem" % at)
        norm_stem = " ".join(q.stem.lower().split())
        if norm_stem and norm_stem in seen_stems:
            warnings.append("%s: stem is identical to %s" % (at, seen_stems[norm_stem]))
        seen_stems[norm_stem] = q.id

        missing = [k for k in OPTION_KEYS if k not in q.options]
        if missing:
            errors.append("%s: missing option(s) %s" % (at, ", ".join(missing)))
        extra = [k for k in q.options if k not in OPTION_KEYS]
        if extra:
            errors.append("%s: unexpected option key(s) %s" % (at, ", ".join(extra)))
        for k, v in q.options.items():
            if not str(v).strip():
                errors.append("%s: option %s is empty" % (at, k))

        blanks = [str(v).strip().lower() for v in q.options.values()]
        if len(set(blanks)) != len(blanks):
            errors.append("%s: two options have the same text" % at)

        if q.answer not in OPTION_KEYS:
            errors.append("%s: answer '%s' is not one of A-D" % (at, q.answer))
        elif q.answer not in q.options:
            errors.append("%s: answer '%s' has no matching option" % (at, q.answer))

        if not q.why_correct.strip():
            errors.append("%s: no explanation for the correct answer" % at)

        expected_wrong = [k for k in OPTION_KEYS if k != q.answer]
        for k in expected_wrong:
            if not q.why_wrong.get(k, "").strip():
                errors.append("%s: no explanation for why %s is wrong" % (at, k))
        for k in q.why_wrong:
            if k == q.answer:
                warnings.append("%s: why_wrong includes the correct answer %s" % (at, k))
            elif k not in OPTION_KEYS:
                errors.append("%s: why_wrong has unknown key %s" % (at, k))

        if q.asks and q.asks not in VALID_ASKS:
            errors.append("%s: asks '%s' is not one of %s"
                          % (at, q.asks, ", ".join(VALID_ASKS)))

        # An error rather than a warning: selection now depends on this field,
        # and a label outside the vocabulary would silently drop the question
        # out of every difficulty filter without anything saying so.
        if q.difficulty not in DIFFICULTIES:
            errors.append("%s: difficulty '%s' is not one of %s"
                          % (at, q.difficulty, ", ".join(DIFFICULTIES)))

        if not q.domain:
            errors.append("%s: missing domain tag" % at)
        if not q.topic:
            errors.append("%s: missing topic tag" % at)

        if outline is not None and outline.raw and q.domain and q.section and q.topic:
            if not outline.knows_topic(q.domain, q.section, q.topic):
                known = outline.topics_for(q.domain, q.section)
                if known:
                    errors.append(
                        "%s: topic '%s' is not in the D%s%s outline" % (at, q.topic, q.domain, q.section)
                    )
                else:
                    warnings.append("%s: outline has no topics for D%s%s" % (at, q.domain, q.section))

        if not any(w in q.stem for w in JUDGMENT_WORDS):
            warnings.append("%s: stem has no BEST/MOST/FIRST-style judgment word" % at)
        # Both forms are valid CISA style: a direct question, or a completion
        # stem that the options finish ("The GREATEST risk is that:").
        if not q.stem.strip().endswith(("?", ":")):
            warnings.append("%s: stem is neither a question nor a completion stem" % at)

    warnings.extend(_key_balance_warnings(questions))
    return errors, warnings


# A batch is written in one sitting by one author, and authors have a favourite
# letter without noticing. Two consecutive batches here came out 1/5/5/1 and
# 1/8/5/2 before anyone looked. Checked per file rather than bank-wide, because
# the bank average stays respectable while individual files skew badly - and a
# learner drills a topic, which draws from one file.
KEY_BALANCE_MIN_QUESTIONS = 8
KEY_BALANCE_MAX_SHARE = 0.45


def _key_balance_warnings(questions: List[Question]) -> List[str]:
    by_file: Dict[str, List[Question]] = {}
    for q in questions:
        by_file.setdefault(q.source_file or "(unknown)", []).append(q)

    out = []
    for path, items in sorted(by_file.items()):
        if len(items) < KEY_BALANCE_MIN_QUESTIONS:
            continue
        counts = {k: 0 for k in "ABCD"}
        for q in items:
            if q.answer in counts:
                counts[q.answer] += 1
        worst, n = max(counts.items(), key=lambda kv: kv[1])
        share = n / len(items)
        if share > KEY_BALANCE_MAX_SHARE:
            out.append(
                "%s: answer keys are skewed - %s is correct for %d of %d questions "
                "(%.0f%%). Spread them so there is no positional pattern to exploit."
                % (path, worst, n, len(items), share * 100))
    return out


def load_pairs(cert: str) -> List[Dict[str, Any]]:
    """Confusable concept pairs, if the cert defines any."""
    path = os.path.join(cert_dir(cert), "confusable-pairs.json")
    if not os.path.exists(path):
        return []
    data = _read_data_file(path)
    pairs = data.get("pairs", []) if isinstance(data, dict) else data
    return pairs if isinstance(pairs, list) else []


def validate_pairs(pairs: List[Dict[str, Any]], questions: List[Question]
                   ) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for the confusable-pair file."""
    errors: List[str] = []
    warnings: List[str] = []
    known = {q.id for q in questions}
    seen: Dict[str, bool] = {}

    for pair in pairs:
        pid = pair.get("id") or "<missing id>"
        if pid in seen:
            errors.append("pair %s: duplicate id" % pid)
        seen[pid] = True

        for field in ("label", "discriminator"):
            if not str(pair.get(field, "")).strip():
                errors.append("pair %s: missing '%s'" % (pid, field))

        terms = pair.get("terms") or []
        if len(terms) < 2:
            errors.append("pair %s: needs at least two terms to be a confusion" % pid)

        qids = pair.get("question_ids") or []
        for qid in qids:
            if qid not in known:
                errors.append("pair %s: question '%s' is not in the bank" % (pid, qid))
        if not qids:
            # Deliberately a warning: an unmapped pair is a real bank gap worth
            # seeing, not a broken file.
            warnings.append("pair %s: no bank questions cover this yet" % pid)

    return errors, warnings


def load_principles(cert: str) -> List[Dict[str, Any]]:
    """Transferable decision rules, if the cert defines any."""
    path = os.path.join(cert_dir(cert), "principles.json")
    if not os.path.exists(path):
        return []
    data = _read_data_file(path)
    items = data.get("principles", []) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def validate_principles(principles: List[Dict[str, Any]], questions: List[Question]
                        ) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings) for the principle file."""
    errors: List[str] = []
    warnings: List[str] = []
    by_id = {q.id: q for q in questions}
    seen: Dict[str, bool] = {}

    for p in principles:
        pid = p.get("id") or "<missing id>"
        if pid in seen:
            errors.append("principle %s: duplicate id" % pid)
        seen[pid] = True

        for field in ("name", "statement", "why", "misapplication", "scope"):
            if not str(p.get(field, "")).strip():
                errors.append("principle %s: missing '%s'" % (pid, field))

        qids = p.get("question_ids") or []
        for qid in qids:
            if qid not in by_id:
                errors.append("principle %s: question '%s' is not in the bank" % (pid, qid))

        domains = {by_id[q].domain for q in qids if q in by_id}
        if not qids:
            warnings.append("principle %s: no bank questions apply it yet" % pid)
        elif len(domains) < 2:
            # A principle confined to one domain cannot demonstrate transfer,
            # which is the whole reason for tagging by principle.
            warnings.append("principle %s: only appears in domain %s, so it cannot "
                            "show cross-domain transfer" % (pid, ",".join(sorted(domains))))

    return errors, warnings


def principle_index(principles: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """question id -> the principle ids that decide it."""
    index: Dict[str, List[str]] = {}
    for p in principles:
        for qid in p.get("question_ids") or []:
            index.setdefault(qid, []).append(p["id"])
    return index


def coverage(questions: List[Question], outline: Outline, domain: str
             ) -> List[Tuple[str, str, int]]:
    """Per-topic question counts for one domain: (section, topic, count)."""
    counts: Dict[Tuple[str, str], int] = {}
    for q in questions:
        if q.domain == str(domain):
            counts[(q.section, q.topic)] = counts.get((q.section, q.topic), 0) + 1

    rows: List[Tuple[str, str, int]] = []
    dom = outline.raw.get("domains", {}).get(str(domain), {})
    for sec_id in sorted(dom.get("sections", {})):
        for topic in dom["sections"][sec_id].get("topics", []):
            rows.append((sec_id, topic, counts.pop((sec_id, topic), 0)))
    for (sec_id, topic), n in sorted(counts.items()):
        rows.append((sec_id, topic, n))
    return rows
