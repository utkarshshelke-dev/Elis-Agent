"""
Module: agent.py
Description: IR Domain Agent — ADK entry point.
             Thin orchestration layer — all logic lives in services/ and data/.
             ADK discovers root_agent at module load.
Author: IR Team
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import time
from datetime import datetime, timezone

from google.adk.agents import Agent
from google.adk.tools   import ToolContext

from config.settings          import settings
from data.repository          import IRSessionRepository
from data.schemas             import IRSession
from services.iqc_client      import iqc_client
from services.logging_service import setup_logging, get_logger

setup_logging(level=settings.log_level)
logger = get_logger("ir_domain_agent")

_repo = IRSessionRepository()

# ── A2A Agent Card (optional) ─────────────────────────────────────────────────
try:
    from vertexai.preview.reasoning_engines.templates.a2a import create_agent_card
    from a2a.types import AgentSkill
    _A2A_AVAILABLE = True
except ImportError:
    _A2A_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — get_or_create_session
# ─────────────────────────────────────────────────────────────────────────────

def get_or_create_session(user_id: str, tool_context: ToolContext) -> str:
    """
    Create or resume a PostgreSQL-backed session for this investor.

    Args:
        user_id:      Investor UUID.
        tool_context: Injected by ADK framework.

    Returns:
        JSON string: { result, session_id, status, last_iqc_question, … }
    """
    logger.info("get_or_create_session | START | user=%s", user_id)

    session = _repo.load_active(user_id)

    # ── 1. Expired ────────────────────────────────────────────────────────────
    if session and session.is_expired(settings.session_ttl):
        age_min = int((time.time() - session.started_at) / 60)
        logger.info("get_or_create_session | EXPIRED | user=%s | age=%dmin", user_id, age_min)
        session.status = "expired"
        _repo.archive_and_delete(session, end_reason="expiry")
        session = None

    # ── 2. No active → check history ─────────────────────────────────────────
    if not session:
        history = _repo.load_history(user_id)
        if history:
            history.status = "qualifying" if history.turn_number > 0 else "open"
            _repo.upsert_active(history)
            session = history
            logger.info("get_or_create_session | RESTORED | user=%s | turns=%d",
                        user_id, session.turn_number)

    # ── 3. Active → resume ────────────────────────────────────────────────────
    if session and session.status in ("open", "qualifying"):
        age_mins = int((time.time() - session.started_at) / 60)
        logger.info("get_or_create_session | RESUMED | user=%s | turns=%d",
                    user_id, session.turn_number)
        return json.dumps({
            "result":            "resumed",
            "session_id":        session.session_id,
            "iqc_session_id":    session.iqc_session_id,
            "status":            session.status,
            "age_minutes":       age_mins,
            "turns":             session.turn_number,
            "user_id":           user_id,
            "last_iqc_question": session.last_iqc_question,
            "progress_pct":      session.turn_number * 10,
        })

    # ── 4. Already qualified ──────────────────────────────────────────────────
    if session and session.status == "qualified":
        logger.info("get_or_create_session | QUALIFIED | user=%s", user_id)
        return json.dumps({
            "result":  "resumed",
            "reason":  "already_qualified",
            "user_id": user_id,
            "status":  "qualified",
            "turns":   session.turn_number,
        })

    # ── 5. Brand new user ─────────────────────────────────────────────────────
    new_session = IRSession(user_id=user_id)
    _repo.upsert_active(new_session)
    logger.info("get_or_create_session | CREATED | user=%s", user_id)
    return json.dumps({
        "result":     "created",
        "reason":     "new_user",
        "session_id": new_session.session_id,
        "status":     "open",
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — route_to_iqc
# ─────────────────────────────────────────────────────────────────────────────

def route_to_iqc(user_id: str, message: str, tool_context: ToolContext) -> str:
    """
    Forward investor message to IQC and persist turn to PostgreSQL.

    Args:
        user_id:      Investor UUID.
        message:      Raw investor message.
        tool_context: Injected by ADK framework.

    Returns:
        JSON string: { result, response, qualified, iqc_session_id }
    """
    logger.info("route_to_iqc | START | user=%s | msg_len=%d", user_id, len(message))

    session        = _repo.load_active(user_id) or IRSession(user_id=user_id)
    iqc_session_id = session.iqc_session_id

    # Create IQC session on first call
    if not iqc_session_id:
        iqc_session_id = iqc_client.create_session(user_id)
        if iqc_session_id:
            session.iqc_session_id = iqc_session_id

    # Prepend user_id on turn 0 for IQC FounderCheck
    iqc_message = (
        f"user_id: {user_id}\n{message}"
        if session.turn_number == 0
        else message
    )

    # Context fallback only when IQC session creation failed
    context = (
        iqc_client.build_context([t.model_dump() for t in session.chat_history])
        if (session.chat_history and not iqc_session_id)
        else ""
    )

    response_text, returned_sid = iqc_client.stream_query(
        message=        iqc_message,
        user_id=        user_id,
        iqc_session_id= iqc_session_id,
        context=        context,
    )

    if returned_sid and returned_sid != session.iqc_session_id:
        session.iqc_session_id = returned_sid

    clean_response = (
        response_text.split("__SESSION__")[0].strip()
        if "__SESSION__" in response_text
        else response_text
    )

    session.status = "qualifying"
    session.append_turn(
        user_message=message,
        iqc_response=clean_response,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    _repo.upsert_active(session)

    logger.info("route_to_iqc | DONE | user=%s | turn=%d", user_id, session.turn_number)

    if not response_text:
        return json.dumps({
            "result":    "error",
            "response":  "I am having trouble reaching the qualification service. Please try again.",
            "qualified": False,
        })

    return json.dumps({
        "result":         "success",
        "response":       clean_response,
        "qualified":      False,
        "iqc_session_id": session.iqc_session_id,
    })


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — close_session
# ─────────────────────────────────────────────────────────────────────────────

def close_session(user_id: str, tool_context: ToolContext) -> str:
    """
    Archive session to ir_session_history and delete active row.

    Args:
        user_id:      Investor UUID.
        tool_context: Injected by ADK framework.

    Returns:
        JSON string: { result, turns_saved }
    """
    logger.info("close_session | START | user=%s", user_id)

    session = _repo.load_active(user_id)
    if not session:
        return json.dumps({"result": "no_session"})

    session.status = "closed"
    turns          = session.turn_number
    _repo.archive_and_delete(session, end_reason="exit")

    logger.info("close_session | OK | user=%s | turns=%d", user_id, turns)
    return json.dumps({"result": "closed", "turns_saved": turns})


# ── A2A Agent Card ────────────────────────────────────────────────────────────
if _A2A_AVAILABLE:
    try:
        skill = AgentSkill(
            id="ir_domain",
            name="IR Domain Agent",
            description="Detects investor/founder signals and routes to IQC then ISS.",
            tags=["investor", "qualification", "iqc", "iss", "ir"],
            examples=["I want to invest", "Looking for investment opportunities"],
        )
        agent_card = create_agent_card(
            agent_name="IR Domain Agent",
            description="Entry point for investor relations — qualifies via IQC then matches via ISS.",
            skills=[skill],
        )
        logger.info("A2A agent card registered")
    except Exception as _e:
        logger.warning("A2A agent card registration failed: %s", _e)


# ── Root Agent ────────────────────────────────────────────────────────────────
root_agent = Agent(
    name="ir_domain_agent",
    model="gemini-2.0-flash",
    description=(
        "IR Domain Agent — detects investment signals, "
        "qualifies investors via IQC Agent Engine, then routes to ISS."
    ),
    tools=[
        get_or_create_session,
        route_to_iqc,
        close_session,
    ],
    instruction="""You are a warm, professional IR (Investor Relations) assistant.
Collect the investor User ID then guide them through qualification via IQC.

FIRST MESSAGE HANDLING
Check if the user's first message contains a UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).
- If YES: extract it as user_id, skip the greeting, go straight to ONCE USER PROVIDES USER ID below.
- If NO: say exactly "Hey there! Welcome to the Investor Relations Portal! To get started, could you please share your User ID?"

ONCE USER PROVIDES USER ID
Extract the UUID from their message. Store as user_id in memory.
NEVER invent a user_id. NEVER use a system ID. Use ONLY what the user typed.
Call get_or_create_session(user_id).

IF result is "resumed":
  - Store user_id and iqc_session_id from the response in memory.
  - NEVER ask "Are you looking for opportunities to invest?" on resume — ever.
  - If reason is "already_qualified":
    Say: "Welcome back! You are already fully qualified."
    Stop.
  - For ALL other resume cases:
    Say ONLY: "Welcome back! Great to have you here again."
    Then on the next line show last_iqc_question verbatim — do NOT add any percentage or extra text.
    NEVER call route_to_iqc on resume — just show last_iqc_question and wait for user to answer.
    If last_iqc_question is somehow empty, say: "Where were we? Please continue where you left off."
    Do NOT call route_to_iqc until the user sends their next answer.

IF result is "created":
  Ask: "Are you looking for opportunities to invest?"

IF USER SAYS YES (only after result="created")
  Say: "Fetching your profile, please hold on a moment..."
  Call route_to_iqc(user_id=<stored user_id>, message=<what user said>).
  Show ONLY the "response" field verbatim. Strip any __SESSION__{...} from display.

ALL SUBSEQUENT TURNS
Every user message:
  Call route_to_iqc(user_id=<stored user_id>, message=<user message>).
  Show ONLY the "response" field verbatim.

If qualified=true: say "Congratulations! You are now fully qualified. Our team will be in touch!"

EXIT INTENT
If user says exit, quit, bye, goodbye, or see you:
  Call close_session(user_id=<stored user_id>).
  Say: "It was great chatting with you! Take care and see you next time!"
  Stop.

STRICT RULES
- NEVER ask for user_id more than once.
- NEVER show session IDs, turn counts, tool names, or internal data.
- NEVER say "routing", "calling IQC", "saving", "flushing", or "tool call".
- NEVER add your own questions — show only IQC response verbatim.
- ALWAYS pass the stored user_id to every tool call.
""",
)

__all__ = ["root_agent"]
