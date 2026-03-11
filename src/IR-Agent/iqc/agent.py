"""
Module: agent.py
Description: IQC Agent — ADK entry point.
             All business logic lives in services/ and data/.
             ADK discovers root_agent at module load.
Author: IQC Team
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import uuid
import logging
from typing import Optional

from google.adk.agents import Agent

from config.settings    import settings
from data.repository    import IQCRepository
from data.schemas       import CRITERIA, is_empty
from services.extractor import extract_fields
from services.scorer    import score_profile, build_summary
from services.logging_service import setup_logging, get_logger

setup_logging(level=settings.log_level, log_dir=settings.log_dir)
logger = get_logger("iqc_agent")

_repo = IQCRepository()


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — check_user
# ─────────────────────────────────────────────────────────────────────────────

def check_user(user_id: str) -> str:
    """
    Check whether a user exists and whether they are an investor or founder.
    Returns session_id — must be stored and appended to every response as
    __SESSION__{"session_id":"..."} so IR Domain Agent can track IQC session.

    Args:
        user_id: UUID string from basic_profiles.id
    """
    bp = _repo.get_basic_profile(user_id)
    if not bp:
        return json.dumps({
            "status":  "not_found",
            "message": "No account found for that ID. Please double-check the user ID.",
        })

    first_name = (bp.get("first_name") or "").strip()
    last_name  = (bp.get("last_name")  or "").strip()
    full_name  = f"{first_name} {last_name}".strip()
    category   = (bp.get("primary_category") or "").lower().strip()

    # Role override from investor_profile
    role_override = _repo.get_profile_role(user_id)
    if role_override:
        category = role_override

    if "founder" in category:
        role = "founder"
    elif category in (
        "investor", "angel", "vc", "lp", "angel_investor",
        "vc_fund", "family_office", "corporate_vc", "accelerator",
    ):
        role = "investor"
    else:
        role = "investor"   # default — let IQC handle unknown types

    session_id = str(uuid.uuid4())
    logger.info("check_user | user=%s | role=%s | sid=%s", user_id, role, session_id[:8])

    return json.dumps({
        "status":     "success",
        "user_id":    user_id,
        "name":       full_name,
        "first_name": first_name,
        "company":    bp.get("company", ""),
        "role":       role,
        "session_id": session_id,
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — load_investor_profile
# ─────────────────────────────────────────────────────────────────────────────

def load_investor_profile(user_id: str) -> str:
    """
    Load all 10 qualification fields for an investor from the database.

    Args:
        user_id: UUID of the investor
    """
    profile = _repo.get_investor_profile(user_id)
    filled  = [k for k in CRITERIA if not is_empty(profile.get(k))]
    missing = [k for k in CRITERIA if     is_empty(profile.get(k))]

    logger.info(
        "load_investor_profile | user=%s | filled=%d | missing=%d",
        user_id, len(filled), len(missing),
    )
    return json.dumps({
        "status":        "success",
        "profile":       profile,
        "filled_fields": filled,
        "missing_fields": missing,
        "filled_count":  len(filled),
        "missing_count": len(missing),
    }, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — score_profile_tool
# ─────────────────────────────────────────────────────────────────────────────

def score_profile_tool(
    user_id:           str,
    session_collected: Optional[str] = None,
) -> str:
    """
    Score the investor profile. Credits session fields not yet saved to DB.

    Args:
        user_id:           UUID of the investor
        session_collected: JSON string of fields gathered this conversation
    """
    base = _repo.get_investor_profile(user_id)

    sc: dict = {}
    if session_collected:
        try:
            sc = json.loads(session_collected) if isinstance(session_collected, str) else session_collected
        except Exception:
            sc = {}

    score_pct, met, total, qualified, missing, next_field, next_q = score_profile(base, sc)

    logger.info(
        "score_profile_tool | user=%s | score=%s | qualified=%s | missing=%d",
        user_id, score_pct, qualified, len(missing),
    )
    return json.dumps({
        "status":              "success",
        "score":               score_pct,
        "met_count":           met,
        "total":               total,
        "qualified":           qualified,
        "missing_fields":      missing,
        "missing_count":       len(missing),
        "next_question_field": next_field,
        "next_question":       next_q,
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — extract_fields_from_message
# ─────────────────────────────────────────────────────────────────────────────

def extract_fields_from_message(
    message:          str,
    last_asked_field: Optional[str] = None,
) -> str:
    """
    Parse user message and extract any investor profile fields found.

    Args:
        message:          Raw text the user just sent
        last_asked_field: Criterion key asked last turn (e.g. stage_focus)
    """
    extracted = extract_fields(message, last_asked_field)
    logger.info("extract_fields_from_message | found=%s", list(extracted.keys()))
    return json.dumps({"status": "success", "extracted": extracted})


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — save_qualified_fields
# ─────────────────────────────────────────────────────────────────────────────

def save_qualified_fields(user_id: str, fields_json: str) -> str:
    """
    Persist newly-collected qualification fields to DB.
    Call ONLY once investor reaches 85% threshold. Never overwrites existing data.

    Args:
        user_id:     UUID of the investor
        fields_json: JSON string of newly-collected fields
    """
    try:
        new_fields = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
    except Exception:
        new_fields = {}

    if not new_fields:
        return json.dumps({"status": "skipped", "message": "Nothing to save."})

    success, saved = _repo.save_qualified_fields(user_id, new_fields)

    if success:
        logger.info("save_qualified_fields | user=%s | saved=%s", user_id, saved)
        return json.dumps({
            "status":       "success",
            "saved_fields": saved,
            "count":        len(saved),
            "message":      f"Saved {len(saved)} new field(s).",
        })
    return json.dumps({"status": "error", "message": "DB write failed."})


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — get_qualification_summary
# ─────────────────────────────────────────────────────────────────────────────

def get_qualification_summary(
    user_id:           str,
    session_collected: Optional[str] = None,
) -> str:
    """
    Show the investor a full summary of their qualification status.

    Args:
        user_id:           UUID of the investor
        session_collected: JSON string of fields gathered this session
    """
    profile = _repo.get_investor_profile(user_id)

    sc: dict = {}
    if session_collected:
        try:
            sc = json.loads(session_collected) if isinstance(session_collected, str) else session_collected
        except Exception:
            sc = {}

    summary = build_summary(profile, sc)
    filled  = sum(1 for k in CRITERIA if not is_empty({**profile, **sc}.get(k)))
    pct     = int(filled / len(CRITERIA) * 100)
    missing = [k for k in CRITERIA if is_empty({**profile, **sc}.get(k))]

    return json.dumps({
        "status":        "success",
        "summary":       summary,
        "score":         f"{pct}%",
        "filled":        filled,
        "missing_fields": missing,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Root Agent
# ─────────────────────────────────────────────────────────────────────────────

root_agent = Agent(
    name="investor_qualification_agent",
    model="gemini-2.0-flash",
    tools=[
        check_user,
        load_investor_profile,
        score_profile_tool,
        extract_fields_from_message,
        save_qualified_fields,
        get_qualification_summary,
    ],
    instruction="""
You are a warm, friendly investor qualification assistant. Help investors complete
their qualification profile through natural conversation, one question at a time.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — WHEN A USER FIRST MESSAGES YOU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Call check_user(user_id).

   status=not_found:
     Say: "Hmm, I could not find an account with that ID. Could you double-check?"
     Stop.

   role=founder:
     Say: "Hi [first_name]! This is the Investor Portal — your account is registered
     as a founder. Please head over to the Founder Portal instead."
     Stop.

   role=investor:
     Greet them warmly by first_name.
     Store session_id from check_user in memory — needed for SESSION MARKER.

2. Call load_investor_profile(user_id).

3. Call score_profile_tool(user_id).

   Score >= 85%:
     Congratulate them. Call get_qualification_summary(user_id) and display it.

   Score < 85%:
     Say: "Great to meet you, [first_name]! Your profile is at [score] —
     let us fill in the remaining details together. It won't take long!
     First up: [next_question from score_profile_tool]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — EACH SUBSEQUENT TURN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Call extract_fields_from_message(message, last_asked_field=<last field asked>).
   Add extracted fields to your running session_collected dict.

2. Call score_profile_tool(user_id, session_collected=<JSON>).

3a. qualified=true:
    Call save_qualified_fields(user_id, fields_json=<JSON of session_collected>).
    Say: "Congratulations [first_name]! You are now fully qualified with a score
    of [score]! Your profile has been saved. Welcome aboard!"

3b. qualified=false:
    Say: "You are at [score] — great progress!"
    Ask exactly ONE question: next_question from score_profile_tool.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPECIAL CASES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
User asks "show my profile" / "what is my score":
  Call get_qualification_summary(user_id, session_collected=<JSON>) and display it.

User shares multiple answers at once:
  Capture all in extract_fields_from_message. Skip already-answered fields.

Never ask for a field already answered this session.
Never ask two questions in the same message.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SESSION MARKER (REQUIRED — never skip)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
At the very end of EVERY response, append on a new line:
__SESSION__{"session_id":"<session_id stored from check_user>"}

Example:
  Hi Carrie! Your profile is at 30% — which investment stages do you focus on?
  __SESSION__{"session_id":"abc-123-def-456"}

Rules:
- Store session_id from check_user on first call. Reuse every turn.
- Append to EVERY response without exception.
- Never mention it to the user. Never explain it. Invisible metadata only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Always use the investor's first name. Be encouraging and conversational.
Qualification threshold = 85% (9 of 10 criteria). Write to DB only when qualified.
""",
)

__all__ = ["root_agent"]
