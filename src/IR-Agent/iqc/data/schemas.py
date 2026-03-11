"""
Module: data/schemas.py
Description: Constants and domain types for IQC qualification pipeline.
Author: IQC Team
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# ── Qualification constants ───────────────────────────────────────────────────

CRITERIA: List[str] = [
    "investor_type", "stage_focus", "sector_focus", "fund_size_usd",
    "average_check_size_usd", "portfolio_size", "investments_last_12_months",
    "has_unicorns_or_ipos", "goals", "seeking",
]

JSONB_KEYS = {
    "investor_type", "stage_focus", "sector_focus", "fund_size_usd",
    "average_check_size_usd", "portfolio_size", "investments_last_12_months",
    "has_unicorns_or_ipos",
}

QUALIFY_THRESHOLD = 0.85

QUESTIONS: Dict[str, str] = {
    "investor_type":              "Are you an angel investor, VC fund, family office, corporate VC, or an accelerator?",
    "stage_focus":                "Which investment stages do you focus on? (e.g. Pre-Seed, Seed, Series A, Series B+)",
    "sector_focus":               "What sectors or industries excite you most? (e.g. Fintech, HealthTech, SaaS, AI, CleanTech)",
    "fund_size_usd":              "What is your total fund size or AUM? (e.g. $10M, $50M)",
    "average_check_size_usd":     "What is your typical check size per investment? (e.g. $250K, $1M)",
    "portfolio_size":             "How many portfolio companies do you currently hold?",
    "investments_last_12_months": "How many new investments did you make in the last 12 months?",
    "has_unicorns_or_ipos":       "Have any portfolio companies become unicorns or had an IPO? (Yes / No)",
    "goals":                      "What are your main investment goals for the next 12-24 months?",
    "seeking":                    "What kind of startups or founders are you actively looking to invest in right now?",
}

# ── Pydantic models ───────────────────────────────────────────────────────────

class UserCheckResult(BaseModel):
    status:     str = ""
    user_id:    str = ""
    name:       str = ""
    first_name: str = ""
    company:    str = ""
    role:       str = ""
    session_id: str = ""
    message:    str = ""


class ProfileResult(BaseModel):
    status:         str = ""
    profile:        Dict[str, Any] = Field(default_factory=dict)
    filled_fields:  List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    filled_count:   int = 0
    missing_count:  int = 0


class ScoreResult(BaseModel):
    status:              str  = ""
    score:               str  = "0%"
    met_count:           int  = 0
    total:               int  = 0
    qualified:           bool = False
    missing_fields:      List[str] = Field(default_factory=list)
    missing_count:       int  = 0
    next_question_field: str  = ""
    next_question:       str  = ""


def is_empty(v: Any) -> bool:
    """Return True if a value is meaningfully empty."""
    return v is None or v == "" or v == [] or v == {}


__all__ = [
    "CRITERIA", "JSONB_KEYS", "QUALIFY_THRESHOLD", "QUESTIONS",
    "UserCheckResult", "ProfileResult", "ScoreResult", "is_empty",
]