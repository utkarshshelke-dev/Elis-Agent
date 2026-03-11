"""
Module: services/scorer.py
Description: Profile scoring logic for IQC qualification pipeline.
Author: IQC Team
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from data.schemas import CRITERIA, QUALIFY_THRESHOLD, QUESTIONS, is_empty

logger = logging.getLogger(__name__)


def score_profile(
    base_profile:      Dict[str, Any],
    session_collected: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int, int, bool, List[str], str, str]:
    """
    Score a profile against the 10 CRITERIA.

    Merges session_collected on top of base_profile so in-session answers
    count toward the score without requiring a DB write first.

    Args:
        base_profile:      Profile dict loaded from DB.
        session_collected: Fields collected this session (not yet saved).

    Returns:
        Tuple of:
          score_pct        — e.g. "70%"
          met_count        — number of criteria met
          total            — always len(CRITERIA)
          qualified        — True if confidence >= QUALIFY_THRESHOLD
          missing_fields   — list of field names still missing
          next_field       — first missing field name, or ""
          next_question    — question string for next_field, or ""
    """
    merged = dict(base_profile)
    if session_collected:
        for k, v in session_collected.items():
            if not is_empty(v):
                merged[k] = v

    missing    = [k for k in CRITERIA if is_empty(merged.get(k))]
    met        = len(CRITERIA) - len(missing)
    confidence = round(met / len(CRITERIA), 3)
    qualified  = confidence >= QUALIFY_THRESHOLD
    next_field = missing[0] if missing else ""

    return (
        f"{int(confidence * 100)}%",
        met,
        len(CRITERIA),
        qualified,
        missing,
        next_field,
        QUESTIONS.get(next_field, "") if next_field else "",
    )


def build_summary(
    profile:           Dict[str, Any],
    session_collected: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a human-readable qualification summary string.

    Args:
        profile:           Base profile from DB.
        session_collected: In-session fields not yet saved.

    Returns:
        Multi-line summary string.
    """
    merged = dict(profile)
    if session_collected:
        for k, v in session_collected.items():
            if not is_empty(v): merged[k] = v

    lines = []
    for i, key in enumerate(CRITERIA, 1):
        val   = merged.get(key)
        label = key.replace("_", " ").title()
        if is_empty(val):
            lines.append(f"  {i:2}. {label}:   Not provided yet")
        else:
            display = ", ".join(str(x) for x in val) if isinstance(val, list) else str(val)
            lines.append(f"  {i:2}. {label}:   {display}")

    filled = sum(1 for k in CRITERIA if not is_empty(merged.get(k)))
    pct    = int(filled / len(CRITERIA) * 100)
    status = "Fully qualified!" if filled == len(CRITERIA) else f"{len(CRITERIA) - filled} field(s) still needed."

    return (
        "Here is your current qualification profile:\n\n"
        + "\n".join(lines)
        + f"\n\nScore: {filled}/{len(CRITERIA)} ({pct}%)\n{status}"
    )


__all__ = ["score_profile", "build_summary"]