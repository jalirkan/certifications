"""Append-only attempt log.

One JSON object per line so the file stays diffable, greppable and easy to
recover if a session is interrupted. Nothing here ever rewrites history.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional


CONFIDENCE = ("guess", "unsure", "confident")

# Keyed 1/2/3 in both front ends. Three levels, not a slider: people cannot
# produce calibrated numbers without training, and a coarse scale answered
# honestly beats a fine one answered carelessly.
CONFIDENCE_KEYS = {"1": "guess", "2": "unsure", "3": "confident"}

CONFIDENCE_LABEL = {
    "guess": "no better than picking",
    "unsure": "leaning one way, could not defend it",
    "confident": "would defend this in a review",
}


def normalise_confidence(value: object) -> str:
    """Accept a level, a 1/2/3 key, or nothing at all.

    Returns "" for anything unrecognised rather than raising: an unreadable
    confidence must never cost the learner the answer itself.
    """
    text = str(value or "").strip().lower()
    if text in CONFIDENCE:
        return text
    return CONFIDENCE_KEYS.get(text, "")


@dataclass
class Attempt:
    ts: str
    session: str
    question_id: str
    cert: str
    domain: str
    section: str
    topic: str
    chosen: str
    answer: str
    correct: bool
    seconds: float
    mode: str
    # Added after the log already had history in it. Empty string means "not
    # recorded", which is what every row written before this feature reads as.
    # Never backfill it: an invented confidence is worse than a missing one.
    confidence: str = ""


def now_iso() -> str:
    """Local time with an explicit UTC offset, so logs stay unambiguous."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append(path: str, attempt: Attempt) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(attempt), ensure_ascii=True) + "\n")


def load(path: str) -> List[Dict]:
    """Read the log, skipping any line that got truncated mid-write."""
    if not os.path.exists(path):
        return []
    rows: List[Dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("question_id"):
                rows.append(row)
    return rows


def parse_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def history_by_question(rows: List[Dict]) -> Dict[str, List[Dict]]:
    """question_id -> attempts, oldest first."""
    out: Dict[str, List[Dict]] = {}
    for row in rows:
        out.setdefault(row["question_id"], []).append(row)
    for attempts in out.values():
        attempts.sort(key=lambda r: r.get("ts", ""))
    return out
